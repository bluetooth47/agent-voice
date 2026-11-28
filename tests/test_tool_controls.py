"""Real tool controls (master plan, phase M10): what each switch changes in
what an agent is really given.

* Claude Code: only the servers Agent Voice names (--strict-mcp-config), in
  a 0600 file and never argv; a CLI switched off is refused in its plain
  forms; the init event's server list is kept for the page.
* Codex: every server in its config.toml not switched on starts with
  enabled=false, read at the turn, only names that are there.
* The permission hook refuses a server switched off since its process
  started, before any grant, and asks about one that is on below Trusted.
* The daemon hands each agent its own, and a change lets the idle process go.
* The pages: one writer for an agent's switches (setAgentTool, run here in
  node), and nothing turns a found tool on outside a confirm.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

import permission_hook as hook
import runtime
import tooldetect

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "tools"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")
FP = "0123456789abcdef0123456789abcdef"
SECRET = "ghp_DONOTLEAK1234567890"
SPEC = {"command": "npx", "args": ["-y", "server-github"], "env": {"GITHUB_TOKEN": SECRET}}


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


# --- Claude Code -----------------------------------------------------------------

def test_every_claude_turn_is_strict_and_carries_no_mcp_json_in_argv():
    from adapters.claude_code import ClaudeCode
    a = ClaudeCode(named="sora")
    a.desktop_tools = True
    a.detected_servers = {"github": SPEC}
    argv = a._argv("", None)
    assert argv.count("--strict-mcp-config") == 1
    for word in argv:
        assert "mcpServers" not in word and SECRET not in word and "server-github" not in word
    path = Path(argv[argv.index("--mcp-config") + 1])
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    servers = json.loads(path.read_text())["mcpServers"]
    assert set(servers) == {"agentvoice-desktop", "agentvoice-crew", "github"}
    assert servers["github"]["env"]["GITHUB_TOKEN"] == SECRET
    # The name is random, not the content's hash: the path is in argv.
    import hashlib
    assert hashlib.sha256(path.read_bytes()).hexdigest()[:10] not in path.name
    # The same servers reuse the file; other servers get another.
    assert a._argv("", None)[argv.index("--mcp-config") + 1] == str(path)
    a.detected_servers = {}
    assert a._argv("", None)[argv.index("--mcp-config") + 1] != str(path)


def test_a_detected_server_never_replaces_one_of_ours():
    from adapters.claude_code import ClaudeCode
    a = ClaudeCode()
    a.detected_servers = {"agentvoice-crew": {"command": "impostor"}}
    argv = a._argv("", None)
    servers = json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text())["mcpServers"]
    assert servers["agentvoice-crew"]["command"] != "impostor"


def test_try_it_and_side_turns_get_no_detected_server():
    from adapters.claude_code import ClaudeCode
    a = ClaudeCode()
    a.no_tools = True
    a.detected_servers = {"github": SPEC}
    a.clis_denied = ("gh",)
    argv = a._argv("", None)
    assert "--mcp-config" not in argv and argv.count("--strict-mcp-config") == 1
    assert "permissions" not in json.loads(argv[argv.index("--settings") + 1])


@pytest.mark.parametrize("trusted", [False, True])
def test_a_cli_switched_off_is_denied_in_its_plain_forms(trusted):
    """The recording (claude-deny-rules.json): Bash(name) and Bash(name *)
    refuse `gh`, `gh pr list`, a path to it and a && chain, even when the
    hook answers allow; `sh -c` gets past them, hence "told, not enforced"."""
    from adapters.claude_code import ClaudeCode
    a = ClaudeCode(ask_permission=not trusted)
    a.clis_denied = ("gh", "docker")
    settings = json.loads(a._argv("", None)[a._argv("", None).index("--settings") + 1])
    assert settings["permissions"]["deny"] == ["Bash(gh)", "Bash(gh *)", "Bash(docker)", "Bash(docker *)"]
    assert not any(":*" in rule for rule in settings["permissions"]["deny"])
    rec = fixture("claude-deny-rules.json")
    assert rec["space_form_only"]["deny_rules"] == ["Bash(spikecli)", "Bash(spikecli *)"]
    assert all(f["denied"] for f in rec["space_form_only"]["forms"])
    assert any(not f["denied"] for f in rec["forms"])          # sh -c ran: not enforced


def test_at_trusted_the_hook_sees_the_detected_servers():
    """So a switch turned off reaches a warm trusted process at its next call."""
    from adapters.claude_code import ClaudeCode
    a = ClaudeCode(ask_permission=False)
    a.detected_servers = {"github": SPEC, "plugin_x_y": {"command": "z"}}
    matcher = json.loads(a._argv("", None)[a._argv("", None).index("--settings") + 1])[
        "hooks"]["PreToolUse"][0]["matcher"]
    assert re.fullmatch(matcher, "mcp__github__create_issue")
    assert re.fullmatch(matcher, "mcp__plugin_x_y__go")
    assert not re.fullmatch(matcher, "mcp__agentvoice-crew__notes_read")
    b = ClaudeCode(ask_permission=False)
    assert "mcp__" not in json.loads(b._argv("", None)[b._argv("", None).index("--settings") + 1])[
        "hooks"]["PreToolUse"][0]["matcher"]


def test_the_init_events_server_list_is_kept_from_a_recorded_turn(monkeypatch):
    from adapters.claude_code import ClaudeCode
    rec = fixture("claude-strict-mcp.json")
    init = {"type": "system", "subtype": "init", "session_id": "s1",
            "mcp_servers": rec["strict"]["init"]["mcp_servers"]}
    lines = [json.dumps(init) + "\n",
             json.dumps({"type": "result", "subtype": "success", "session_id": "s1"}) + "\n"]

    class Proc:
        def __init__(self):
            self.stdout = type("S", (), {"readline": lambda s: lines.pop(0) if lines else ""})()
            self.stdin = type("I", (), {"write": lambda s, x: None, "flush": lambda s: None})()
            self.stderr = None

        def poll(self):
            return None

        def wait(self):
            return 0

    a = ClaudeCode()
    monkeypatch.setattr(a, "_take", lambda sid, fresh=False: (Proc(), None, None))
    list(a.send("hi"))
    assert a.live_servers == [{"name": "spike-file", "status": "connected"}]


def test_the_recordings_say_what_the_design_rests_on():
    rec = fixture("claude-strict-mcp.json")
    loose = {s["source"] for s in rec["loose"]["init"]["mcp_servers"]}
    assert {"user", "project", "dynamic"} <= loose                 # what strict mode closes
    assert [s["source"] for s in rec["strict"]["init"]["mcp_servers"]] == ["dynamic"]
    assert rec["strict"]["started"] == ["spike-file.started"]      # the others never started
    assert [s["source"] for s in rec["plugin_strict"]["init"]["mcp_servers"]] == ["dynamic"]
    assert rec["strict"]["skills_left_out"] == ["minecraft"]       # for M11
    codex = fixture("codex-mcp-enabled.json")
    assert codex["on"]["started"] and not codex["off"]["started"]
    assert codex["call_below_trusted"]["item"]["status"] == "failed"
    assert codex["call_at_trusted"]["called"] is True


# --- Codex -----------------------------------------------------------------------

def codex_home(tmp_path, monkeypatch, text):
    home = tmp_path / "codex"
    home.mkdir()
    (home / "config.toml").write_text(text)
    monkeypatch.setenv("CODEX_HOME", str(home))


def test_codex_starts_config_servers_not_switched_on_disabled(tmp_path, monkeypatch):
    from adapters.codex import Codex
    codex_home(tmp_path, monkeypatch,
               '[mcp_servers.node_repl]\ncommand = "x"\n[mcp_servers.github]\ncommand = "y"\n')
    c = Codex()
    argv = c._argv("", None)
    flags = [argv[i + 1] for i, w in enumerate(argv) if w == "-c"]
    assert "mcp_servers.node_repl.enabled=false" in flags
    assert "mcp_servers.github.enabled=false" in flags
    c.mcp_on = {"github": tooldetect.spec_digest({"command": "y"})}
    flags = [w for w in c._argv("", None) if "enabled=false" in w]
    assert flags == ["mcp_servers.node_repl.enabled=false"]
    # Options stay before `resume`.
    argv = c._argv("", "thread-1")
    assert argv.index("mcp_servers.node_repl.enabled=false") < argv.index("resume")


def test_codex_never_names_a_server_its_config_does_not_have(tmp_path, monkeypatch):
    """Naming one stops Codex from starting at all ("invalid transport",
    recorded): so the names come from the file at the turn, not the scan."""
    from adapters.codex import Codex
    codex_home(tmp_path, monkeypatch, 'model = "m"\n')
    assert not any("enabled=false" in w for w in Codex()._argv("", None))
    (tmp_path / "codex" / "config.toml").unlink()
    assert not any("enabled=false" in w for w in Codex()._argv("", None))      # no file: none


@pytest.mark.parametrize("text", ["[[[ broken",
                                  "".join(f'[mcp_servers.s{i}]\ncommand = "x"\n' for i in range(1001))])
def test_codex_does_not_start_when_its_servers_cannot_all_be_named(tmp_path, monkeypatch, text):
    """A config.toml that cannot be read whole would leave some of its
    servers on with every switch off (Codex review of M10): no turn."""
    from adapters.codex import Codex, ConfigUnaccounted
    codex_home(tmp_path, monkeypatch, text)
    with pytest.raises(ConfigUnaccounted):
        Codex()._argv("", None)
    started = []
    monkeypatch.setattr("adapters.codex.subprocess.Popen", lambda *a, **k: started.append(a))
    chunks = list(Codex().send("hi"))
    assert started == [] and chunks[0].error and "not started" in chunks[0].error


def test_codex_does_not_start_an_approved_server_whose_definition_changed(tmp_path, monkeypatch):
    """Between the scan and the turn the file can change under the same
    name (Codex review of M10): the digest of what was approved is checked
    at the turn."""
    from adapters.codex import Codex
    codex_home(tmp_path, monkeypatch, '[mcp_servers.github]\ncommand = "gh-mcp"\n')
    c = Codex()
    c.mcp_on = {"github": tooldetect.spec_digest({"command": "gh-mcp"})}
    assert not any("enabled=false" in w for w in c._argv("", None))
    (tmp_path / "codex" / "config.toml").write_text('[mcp_servers.github]\ncommand = "evil"\n')
    assert "mcp_servers.github.enabled=false" in c._argv("", None)


# --- the CLI line ----------------------------------------------------------------

def test_the_cli_line_is_told_once_and_only_to_a_backend_that_runs_commands():
    from adapters.base import cli_line
    from adapters.codex import Codex
    from adapters.openai_compat import OpenAICompatible
    assert cli_line([], []) == ""
    line = cli_line(["gh"], ["docker", "aws"])
    assert line.startswith("Command-line tools found on this machine: you may use gh;")
    assert "docker, aws are switched off for you in Agent Voice: do not run them" in line
    c = Codex(spoken=False)
    c.clis_on, c.clis_off = ("gh",), ("docker",)
    assert c.preamble().count("Command-line tools found on this machine") == 1
    e = OpenAICompatible(base_url="http://localhost:1/v1", model="m", is_agent=False)
    e.clis_on = ("gh",)
    assert "Command-line tools" not in e.preamble()


# --- the permission hook ---------------------------------------------------------

@pytest.fixture
def settings(monkeypatch):
    """shell.json with this widget's entry, removed afterwards."""
    def write(**entry):
        runtime.SHELL_JSON.write_text(json.dumps(
            {"bar": {"layout": {"right": [{"id": runtime.PLUGIN_ID, **entry}]}}}))
    yield write
    try:
        runtime.SHELL_JSON.unlink()
    except FileNotFoundError:
        pass


def as_agent(monkeypatch, program="claude", named=""):
    monkeypatch.setattr("sys.argv", ["permission_hook.py", program] + ([named] if named else []))


def test_a_server_switched_off_is_refused_even_with_a_grant(settings, monkeypatch):
    as_agent(monkeypatch)
    monkeypatch.setattr(hook, "_settings", lambda: ("trusted", None))
    monkeypatch.setattr(hook, "granted", lambda session: True)
    settings(mainTools={"mcp:github": "off"})
    decision, why = hook.decide("mcp__github__create_issue", {"title": "x"}, "s")
    assert decision == "deny" and "switched off" in why
    settings(mainTools={"mcp:github": "on:" + FP})
    assert hook.decide("mcp__github__create_issue", {"title": "x"}, "s")[0] == "allow"


def test_a_server_switched_on_is_asked_about_below_trusted(settings, monkeypatch, card_desk):
    import cardhelp
    as_agent(monkeypatch)
    monkeypatch.setattr(hook, "_settings", lambda: ("ask", None))
    settings(sharedTools={"mcp:github": "on:" + FP})
    seen = {}
    cardhelp.peek(card_desk, seen)
    monkeypatch.setattr(hook, "TIMEOUT", 0.3)
    assert hook.decide("mcp__github__create_issue", {"title": "x"})[0] == "deny"   # nobody answered
    assert seen["tool"] == "mcp__github__create_issue"


@pytest.mark.parametrize("tool", ["mcp__nobody__x", "mcp__githubx__y", "mcp__git__hub__x", "mcp__github_admin__x"])
def test_a_server_nobody_switched_on_is_refused(settings, monkeypatch, tool):
    as_agent(monkeypatch)
    monkeypatch.setattr(hook, "_settings", lambda: ("trusted", None))
    settings(mainTools={"mcp:github": "on:" + FP})
    assert hook.decide(tool, {})[0] == "deny"


def test_the_switches_of_the_agent_that_asks_are_the_ones_read(settings, monkeypatch):
    agents = [{"id": "sora", "name": "sora", "agent": "claude", "tools": {"mcp:github": "on:" + FP}}]
    monkeypatch.setattr(hook, "_settings", lambda: ("trusted", None))
    settings(voiceAgents=agents)
    as_agent(monkeypatch, named="sora")
    assert hook.decide("mcp__github__x", {})[0] == "allow"
    as_agent(monkeypatch)                                       # the main agent
    assert hook.decide("mcp__github__x", {})[0] == "deny"
    as_agent(monkeypatch, program="codex", named="sora")        # now another program
    assert hook.decide("mcp__github__x", {})[0] == "deny"


def test_unreadable_settings_and_failures_refuse(settings, monkeypatch):
    as_agent(monkeypatch)
    monkeypatch.setattr(hook, "_settings", lambda: ("trusted", None))
    runtime.SHELL_JSON.write_text("{ broken")
    assert hook.decide("mcp__github__x", {})[0] == "deny"
    settings(mainTools={"mcp:github": "on:" + FP})

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(tooldetect, "switched_on_keys", boom)
    assert hook.decide("mcp__github__x", {})[0] == "deny"


def test_our_own_servers_keep_their_own_rules(settings, monkeypatch):
    as_agent(monkeypatch)
    settings()
    assert hook.decide("mcp__agentvoice-crew__notes_read", {"name": "n"})[0] == "allow"
    assert hook.detected_refusal("mcp__agentvoice-desktop__list_windows") == ""
    assert hook.detected_refusal("mcp__claude-in-chrome__navigate") == ""
    assert hook.detected_refusal("Bash") == ""


def test_the_hook_process_refuses_an_off_server_end_to_end(settings, tmp_path):
    """Through main(), as Claude Code runs it: a decision on stdout, deny."""
    import sys
    settings(mainTools={"mcp:github": "off"})
    env = {**os.environ, "XDG_CONFIG_HOME": str(runtime.SHELL_JSON.parent.parent),
           "PYTHONDONTWRITEBYTECODE": "1"}
    payload = json.dumps({"tool_name": "mcp__github__x", "tool_input": {}, "session_id": "s"})
    # The hook reads runtime.SHELL_JSON from XDG_CONFIG_HOME/omarchy/shell.json.
    conf = tmp_path / "config" / "omarchy"
    conf.mkdir(parents=True)
    shutil.copy(runtime.SHELL_JSON, conf / "shell.json")
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    p = subprocess.run([sys.executable, str(ROOT / "daemon" / "permission_hook.py"), "claude"],
                       input=payload, capture_output=True, text=True, env=env, timeout=30)
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "switched off" in out["permissionDecisionReason"]


# --- the daemon ------------------------------------------------------------------

class P:
    def __init__(self, pid="", spec=None, main=False):
        self.id, self.spec, self.main, self.label = pid, spec or {}, main, pid or "main"


def daemon_with(cfg, monkeypatch, scanned, defs):
    from wake_listen import Daemon
    import omarchy_skill
    d = Daemon.__new__(Daemon)
    d.cfg = cfg
    monkeypatch.setattr(omarchy_skill, "plugin_dir", lambda: None)
    monkeypatch.setattr(tooldetect, "scan_cached",
                        lambda cfg, force=False, with_defs=False: (scanned, defs) if with_defs else scanned)
    return d


def fake_scan():
    defs = [{"name": "github", "backend": "claude", "scope": "user", "source": "~/.claude.json",
             "project": "", "spec": SPEC},
            {"name": "node_repl", "backend": "codex", "scope": "codex", "source": "~/.codex/config.toml",
             "project": "", "spec": {"command": "n"}}]
    tools = [{"id": "mcp:github", "kind": "mcp", "name": "github", "label": "github",
              "backends": ["claude"], "defs": [{"backend": "claude", "scope": "user", "where": "",
                                                "source": "~/.claude.json", "project": "", "command": "npx"}],
              "fp": FP, "found": True},
             {"id": "mcp:node_repl", "kind": "mcp", "name": "node_repl", "label": "node_repl",
              "backends": ["codex"], "defs": [{"backend": "codex", "scope": "codex", "where": "",
                                               "source": "", "project": "", "command": "n"}],
              "fp": FP, "found": True},
             {"id": "cli:gh", "kind": "cli", "name": "gh", "label": "GitHub CLI",
              "backends": list(tooldetect.CLI_PROGRAMS), "defs": [], "fp": FP, "found": True}]
    return {"tools": tools}, defs


def test_switching_a_server_on_and_off_reaches_a_warm_claude_process(cfg_factory, monkeypatch):
    from adapters.claude_code import ClaudeCode
    scanned, defs = fake_scan()
    d = daemon_with(cfg_factory(mainTools={"mcp:github": "on:" + FP}), monkeypatch, scanned, defs)
    a = ClaudeCode()
    cancelled = []
    a.cancel = lambda: cancelled.append(1)
    assert d.apply_extras(a, P(main=True)) is True
    assert a.detected_servers == {"github": SPEC}
    assert a.clis_denied == ("gh",) and a.clis_off == ("gh",) and a.clis_on == ()
    cancelled.clear()
    d.cfg = cfg_factory(mainTools={"mcp:github": "off", "cli:gh": "on:" + FP})
    assert d.apply_extras(a, P(main=True)) is True
    assert cancelled == [1]                       # the idle process is let go
    assert a.detected_servers == {} and a.clis_on == ("gh",) and a.clis_denied == ()
    assert d.apply_extras(a, P(main=True)) is False   # nothing changed: nothing let go


def test_a_switch_turned_off_mid_turn_is_held_by_the_hook(cfg_factory, monkeypatch, settings):
    """The process keeps what it started with until the turn ends (the
    daemon passes a busy agent by), so the hook is what holds it: the next
    call to the server is refused, read fresh."""
    as_agent(monkeypatch)
    monkeypatch.setattr(hook, "_settings", lambda: ("trusted", None))
    settings(mainTools={"mcp:github": "on:" + FP})
    assert hook.decide("mcp__github__x", {})[0] == "allow"
    settings(mainTools={"mcp:github": "off"})       # turned off while it works
    assert hook.decide("mcp__github__x", {})[0] == "deny"


def test_codex_and_an_endpoint_get_what_they_can_take(cfg_factory, monkeypatch):
    from adapters.codex import Codex
    from adapters.openai_compat import OpenAICompatible
    scanned, defs = fake_scan()
    d = daemon_with(cfg_factory(mainTools={"mcp:node_repl": "on:" + FP}), monkeypatch, scanned, defs)
    c = Codex()
    c.cancel = lambda: None
    d.apply_extras(c, P(main=True))
    assert c.mcp_on == {"node_repl": tooldetect.spec_digest({"command": "n"})} and c.clis_off == ("gh",)
    e = OpenAICompatible(base_url="http://localhost:1/v1", model="m", is_agent=True)
    e.cancel = lambda: None
    d.apply_extras(e, P(main=True))
    assert getattr(e, "clis_on", ()) == () and getattr(e, "clis_off", ()) == ()


def test_a_failed_scan_hands_nothing(cfg_factory, monkeypatch):
    from adapters.claude_code import ClaudeCode
    from wake_listen import Daemon
    d = Daemon.__new__(Daemon)
    d.cfg = cfg_factory(mainTools={"mcp:github": "on:" + FP})
    said = []
    d.say_once = lambda key, text: said.append(text)

    def boom(*a, **k):
        raise OSError("disk")
    monkeypatch.setattr(tooldetect, "scan_cached", boom)
    a = ClaudeCode()
    a.detected_servers = {"github": SPEC}
    a.cancel = lambda: None
    d.apply_extras(a, P(main=True))
    assert a.detected_servers == {} and said and SECRET not in said[0]


def test_the_journal_line_names_no_tool(cfg_factory, monkeypatch, capsys):
    from adapters.claude_code import ClaudeCode
    scanned, defs = fake_scan()
    d = daemon_with(cfg_factory(mainTools={"mcp:github": "on:" + FP, "cli:gh": "on:" + FP}),
                    monkeypatch, scanned, defs)
    a = ClaudeCode()
    a.cancel = lambda: None
    d.apply_extras(a, P(main=True))
    out = capsys.readouterr().out
    assert "1 found server" in out and "1 CLI" in out
    assert "github" not in out and "gh " not in out


def test_live_status_is_written_when_it_changes(monkeypatch, tmp_path):
    from wake_listen import Daemon
    monkeypatch.setattr(tooldetect, "live_path", lambda: tmp_path / "live.json")
    d = Daemon.__new__(Daemon)
    agent = type("A", (), {"live_servers": [{"name": "github", "status": "connected"}]})()
    import threading
    p = type("Pe", (), {"main": True, "id": "", "agent": agent})()
    d._main, d._here = p, threading.local()
    d.publish_live_tools([p])
    assert json.loads((tmp_path / "live.json").read_text()) == {
        "main": {"servers": [{"name": "github", "status": "connected"}]}}
    assert stat.S_IMODE((tmp_path / "live.json").stat().st_mode) == 0o600


# --- taint -----------------------------------------------------------------------

def test_an_agent_with_a_detected_server_on_writes_tainted_notes(settings, monkeypatch):
    import crew_mcp
    monkeypatch.setattr(crew_mcp, "LAUNCHED_WITH_BROWSER", False)
    monkeypatch.setattr(crew_mcp, "program", lambda: "claude")
    monkeypatch.setattr(crew_mcp, "named", lambda: "")
    monkeypatch.setattr(crew_mcp, "_config", lambda: runtime.Config())
    settings()
    assert crew_mcp.could_browse() is False
    settings(mainTools={"mcp:github": "on:" + FP})
    assert crew_mcp.could_browse() is True
    monkeypatch.setattr(crew_mcp, "program", lambda: "gemini")
    assert crew_mcp.could_browse() is False


# --- the pages ---------------------------------------------------------------------

def function_source(path: Path, name: str) -> str:
    from qml_scan import scan
    s = scan(path)
    m = re.search(r"\bfunction " + re.escape(name) + r"\(", s.clean)
    assert m, f"{path.name} has no function {name}"
    brace = s.clean.index("{", m.end())
    return s.src[m.start():s.closes[brace] + 1]


AGENTS = [{"id": "sora", "name": "sora", "agent": "claude", "tools": {"desktop": "on", "mcp:x": "off"},
           "future": {"kept": [1, 2.5]}},
          {"name": "hazel bee", "agent": "codex"}]


def run_set_agent_tool(calls, main_tools=None, agents=None):
    fn = function_source(ROOT / "Settings.qml", "setAgentTool")
    agent_id = function_source(ROOT / "Settings.qml", "agentId")
    script = f"""
{agent_id}
var AGENTS = JSON.parse({json.dumps(json.dumps(agents if agents is not None else AGENTS))});
var MAIN = {json.dumps(main_tools if main_tools is not None else {"browser": "off"})};
var CALLS = {json.dumps(calls)};
var out = [];
for (var c = 0; c < CALLS.length; c++) {{
  var root = {{ voiceAgents: JSON.parse(JSON.stringify(AGENTS)), puts: [],
    put: function(k, v) {{ this.puts.push([k, JSON.parse(JSON.stringify(v))]) }},
    setting: function(k, d) {{ return k === "mainTools" ? JSON.parse(JSON.stringify(MAIN)) : d }},
    agentId: agentId }};
  {fn.replace("function setAgentTool", "root.setAgentTool = function")}
  var ok = eval(CALLS[c]);
  out.push({{ ok: ok, puts: root.puts }});
}}
console.log(JSON.stringify(out));
"""
    p = subprocess.run([NODE], input=script, capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


@needs_node
def test_set_agent_tool_changes_one_key_of_one_agents_tools():
    cases = [('root.setAgentTool("sora", "browser", "on")', 0, {"desktop": "on", "mcp:x": "off", "browser": "on"}),
             ('root.setAgentTool("sora", "desktop", "inherit")', 0, {"mcp:x": "off"}),
             ('root.setAgentTool("sora", "mcp:x", "on:' + FP + '")', 0, {"desktop": "on", "mcp:x": "on:" + FP}),
             ('root.setAgentTool("hazel-bee", "cli:gh", "off")', 1, {"cli:gh": "off"})]
    results = run_set_agent_tool([c for c, _, _ in cases])
    for (call, index, tools), r in zip(cases, results):
        assert r["ok"] is True and [k for k, _ in r["puts"]] == ["voiceAgents"], call
        want = json.loads(json.dumps(AGENTS))
        want[1]["id"] = "hazel-bee"           # an entry from before ids gets its derived id
        want[index]["tools"] = tools
        assert json.dumps(r["puts"][0][1]) == json.dumps(want), call


@needs_node
def test_set_agent_tool_for_the_main_agent_writes_main_tools_only():
    r = run_set_agent_tool(['root.setAgentTool("", "mcp:x", "on:' + FP + '")',
                            'root.setAgentTool("main", "browser", "inherit")'])
    assert r[0]["puts"] == [["mainTools", {"browser": "off", "mcp:x": "on:" + FP}]]
    assert r[1]["puts"] == [["mainTools", {}]]


@needs_node
@pytest.mark.parametrize("call", [
    'root.setAgentTool("sora", "mcp:x", "on")',            # a found tool needs its fingerprint
    'root.setAgentTool("sora", "browser", "on:' + FP + '")',
    'root.setAgentTool("sora", "mcp:x", "on:abc")',
    'root.setAgentTool("sora", "voice", "on")',            # not a tool switch
    'root.setAgentTool("sora", "mcp:../x", "off")',
    'root.setAgentTool("nobody", "browser", "on")',
])
def test_set_agent_tool_refuses_what_it_cannot_write(call):
    r = run_set_agent_tool([call])[0]
    assert r["ok"] is False and r["puts"] == []


@needs_node
def test_set_agent_tool_keeps_a_field_named_proto():
    agents = json.loads('[{"id": "sora", "name": "sora", "__proto__": {"x": 1}, "tools": {"__proto__": 2}}]')
    r = run_set_agent_tool(['root.setAgentTool("sora", "browser", "off")'], agents=agents)[0]
    saved = r["puts"][0][1][0]
    assert saved["__proto__"] == {"x": 1} and saved["tools"] == {"__proto__": 2, "browser": "off"}


def handlers_writing(path: Path, pattern: str) -> list[str]:
    from qml_scan import scan
    s = scan(path)
    out = []
    for m in re.finditer(pattern, s.nocomment):
        if s.clean[m.start()] == s.src[m.start()]:
            out.append(s.handler_of(m.start()) or "nothing")
    return out


def test_nothing_turns_a_found_tool_on_outside_a_confirm():
    """An approval ("on:" + its fingerprint) is written in a ToolConfirm's
    onConfirmed and nowhere else, on both pages that can write one; and
    following every agent while that is on asks the same way (askTool)."""
    details = ROOT / "pages" / "AgentDetailsPage.qml"
    communal = ROOT / "pages" / "CommunalPage.qml"
    approval = r'\b(?:setAgentTool|putShared)\([^;{}]*?"on:" \+'
    assert handlers_writing(details, approval) == ["onConfirmed"]
    assert handlers_writing(communal, approval) == ["onConfirmed"]
    # And every "on:" + on those pages is either that write or a comparison.
    from qml_scan import scan as _scan
    for page in (details, communal):
        src = _scan(page).nocomment
        for m in __import__("re").finditer(r'"on:" \+', src):
            line = src[src.rfind("\n", 0, m.start()) + 1:src.find("\n", m.start())]
            before = src[max(0, m.start() - 300):m.start()]
            assert "===" in line or "!==" in line or \
                __import__("re").search(r"(setAgentTool|putShared)\([^;{}]*$", before), line
    from qml_scan import scan
    src = scan(details).nocomment
    ask = function_source(details, "askTool")
    assert "turnsOn" in ask and 'v === "on") return' in ask
    # The only other writes: built-in chips, and askTool's off/inherit.
    assert sorted(handlers_writing(details, r"setAgentTool\(")) == [
        "function askTool", "onCommitted", "onConfirmed"]
    # One again since M31, which took the skill import (M11's second
    # ToolConfirm) off the page.
    assert src.count("ToolConfirm {") == 1


def test_the_tools_tab_writes_through_set_agent_tool_alone():
    from qml_scan import scan
    src = scan(ROOT / "pages" / "AgentDetailsPage.qml").nocomment
    # Since M17 the page puts the main agent's launch settings, in one
    # function (test_agent_pages holds which keys); nothing else is put.
    at = src.index("function putLaunch(")
    src = src[:at] + src[src.index("\n  }", at):]
    assert not re.search(r"\b(put|putMap)\(", src)
    assert 'command = ["agentvoice", "tools", "dismiss", page.target]' in src
    assert '["agentvoice", "tools", "scan", "--rescan", "--json"]' in src


def test_a_found_tool_and_a_command_line_are_shown_as_plain_text():
    """A server's name and command come out of somebody's config file."""
    for name in ("ui/ToolConfirm.qml", "pages/AgentDetailsPage.qml", "pages/CommunalPage.qml"):
        src = (ROOT / name).read_text()
        block_starts = [m.start() for m in re.finditer(r"\bText \{", src)]
        for start in block_starts:
            body = src[start:src.index("\n  }", start) if "\n  }" in src[start:] else len(src)]
            head = body[:body.index("\n", body.index("text:")) if "text:" in body else 0] if "text:" in body else ""
            text_line = body[body.index("text:"):].split("\n")[0] if "text:" in body else ""
            if re.search(r"(modelData\.(name|defs|command)|d\.command|box\.title|modelData\.value)", text_line):
                assert "Text.PlainText" in body[:900], (name, body[:200])


def test_the_catalog_lists_found_tools_and_the_notice(cfg_factory, monkeypatch, tmp_path):
    import agentfs
    scanned, defs = fake_scan()
    monkeypatch.setattr(tooldetect, "scan_cached", lambda cfg, force=False, with_defs=False: scanned)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("adapters.main_program", lambda v: "claude")
    cat = agentfs.catalog("main", cfg_factory(mainProgram="claude"))
    ids = {r["id"]: r for r in cat["detected"]}
    assert set(ids) == {"mcp:github", "mcp:node_repl", "cli:gh"}
    assert not any(r["on"] for r in ids.values())
    assert {n["id"] for n in cat["notice"]} == {"mcp:github", "cli:gh"}
    assert cat["scan"]["error"] == ""


def test_a_server_switch_alone_lets_the_warm_process_go(cfg_factory, monkeypatch):
    """Only the server changes here -- no CLI, no built-in switch -- so it is
    the server's own change that lets the idle process go."""
    from adapters.claude_code import ClaudeCode
    scanned, defs = fake_scan()
    on = {"mcp:github": "on:" + FP, "cli:gh": "off"}
    d = daemon_with(cfg_factory(mainTools=on), monkeypatch, scanned, defs)
    a = ClaudeCode()
    cancelled = []
    a.cancel = lambda: cancelled.append(1)
    d.apply_extras(a, P(main=True))
    cancelled.clear()
    d.cfg = cfg_factory(mainTools={**on, "mcp:github": "off"})
    assert d.apply_extras(a, P(main=True)) is True
    assert cancelled == [1] and a.detected_servers == {}
    # And a Codex agent's switch alone, too.
    from adapters.codex import Codex
    c = Codex()
    c.cancel = lambda: cancelled.append(2)
    d.cfg = cfg_factory(mainTools={"mcp:node_repl": "on:" + FP, "cli:gh": "off"})
    d.apply_extras(c, P(main=True))
    cancelled.clear()
    d.cfg = cfg_factory(mainTools={"mcp:node_repl": "off", "cli:gh": "off"})
    assert d.apply_extras(c, P(main=True)) is True and c.mcp_on == {}


def test_a_revoked_server_cannot_hide_behind_an_approved_ones_name(settings, monkeypatch):
    """Codex review of M10: with prefix matching, approving "docs" let a
    revoked "docs__admin" through. Keys never hold "__" now, and the hook
    reads the key exactly."""
    as_agent(monkeypatch)
    monkeypatch.setattr(hook, "_settings", lambda: ("trusted", None))
    settings(mainTools={"mcp:docs": "on:" + FP, "mcp:docs__admin": "off"})
    assert tooldetect.server_key("docs__admin") == "docs_admin"
    assert hook.decide("mcp__docs_admin__wipe", {})[0] == "deny"
    assert hook.decide("mcp__docs__search", {})[0] == "allow"
    assert hook.decide("mcp__docs__admin__wipe", {})[0] == "allow"      # docs's own tool "admin__wipe"


@pytest.mark.parametrize("name,key", [("docs__admin", "docs_admin"), ("plugin:x:y", "plugin_x_y"),
                                      ("_a__", "a"), ("a b.c", "a_b_c"), ("___", "server"),
                                      ("ok-name_1", "ok-name_1")])
def test_a_server_key_never_holds_a_double_underscore_or_an_edge_one(name, key):
    got = tooldetect.server_key(name)
    assert got == key and "__" not in got and not got.startswith("_") and not got.endswith("_")


def test_a_codex_server_cannot_be_named_does_not_start_codex_until_switched_on(tmp_path, monkeypatch):
    """`-c` takes a dotted path and refuses a quoted key (tried against
    0.171.0), so a server named "has.dot" cannot be left out: off means no
    turn (Codex review of M10, pass 2); switched on, it starts as approved."""
    from adapters.codex import Codex, ConfigUnaccounted
    codex_home(tmp_path, monkeypatch, '[mcp_servers."has.dot"]\ncommand = "z"\n')
    with pytest.raises(ConfigUnaccounted, match="has.dot"):
        Codex()._argv("", None)
    c = Codex()
    c.mcp_on = {"has.dot": tooldetect.spec_digest({"command": "z"})}
    assert not any("has.dot" in w for w in c._argv("", None))
    (tmp_path / "codex" / "config.toml").write_text('[mcp_servers."has.dot"]\ncommand = "changed"\n')
    with pytest.raises(ConfigUnaccounted):
        c._argv("", None)


def test_a_stale_approval_cannot_vouch_for_a_server_of_the_same_key(cfg_factory):
    """"docs.api" and "docs_api" are one key: with one switched off the key
    is off, whatever the other's approval says (Codex review, pass 2)."""
    cfg = cfg_factory(mainTools={"mcp:docs.api": "off", "mcp:docs_api": "on:" + FP})
    assert tooldetect.switched_on_keys(cfg, "") == set()
    cfg = cfg_factory(mainTools={"mcp:docs_api": "on:" + FP})
    assert tooldetect.switched_on_keys(cfg, "") == {"docs_api"}
