"""Phase M16: Agent details → Advanced, what is running. Read only.

What is proven here, from the plan's Tests line:

- the command line shown is the adapter's own argv -- the one its turn
  hands to Popen -- with no prompt or instruction text in it, for every
  backend that starts a process;
- the hook decides exactly the same when its audit write raises, hangs or
  is interrupted (silence still denies);
- permission audit lines hold no arguments: by shape (audit's fixed lists)
  and by the AST walk in test_notes, which this phase's call joins;
- two agents on one backend are told apart, in the record, the ring and the
  decisions;
- a synthetic secret in a launch line is redacted, in the record, the
  published file and the CLI's output;
- the log ring cannot hold text: every field typed, every call parsed.
"""
from __future__ import annotations

import ast
import fcntl
import io
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

import pytest

import audit
import permission_hook as hook
import runinfo

ROOT = Path(__file__).resolve().parent.parent
CANARY = "PELICAN-4356"
SID = "0b6c2f3e-1111-2222-3333-444455556666"


# --- the command line is the adapter's own ---------------------------------------------

def _claude(**kw):
    from adapters.claude_code import ClaudeCode
    a = ClaudeCode(model="haiku", cwd="/tmp", **kw)
    a.instructions = f"Standing order {CANARY}"
    a.parts = {"rules": f"Rule {CANARY}", "personality": f"Me {CANARY}", "name": "Sora",
               "roster": [f"Theo: {CANARY}"]}
    return a


def _codex(**kw):
    from adapters.codex import Codex
    a = Codex(model="gpt-5", cwd="/tmp", **kw)
    a.instructions = f"Standing order {CANARY}"
    return a


def _gemini():
    from adapters.gemini import Gemini
    a = Gemini(model="gemini-3-pro", cwd="/tmp")
    a.instructions = f"Standing order {CANARY}"
    return a


def _agy():
    from adapters.antigravity import Antigravity
    a = Antigravity(cwd="/tmp")
    a.instructions = f"Standing order {CANARY}"
    return a


def _copilot():
    from adapters.cli_agent import CliAgent
    a = CliAgent("copilot", cwd="/tmp")
    a.instructions = f"Standing order {CANARY}"
    return a


BUILDERS = {"claude": _claude, "codex": _codex, "gemini": _gemini, "agy": _agy,
            "copilot": _copilot}


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_the_line_shown_is_the_adapters_own_argv_with_no_text(name):
    a = BUILDERS[name]()
    rec = runinfo.record_for(a, session_id=SID)
    if name == "copilot":
        want = a._argv(a.PROMPT_SLOT)
    else:
        want = a._argv("a spoken request " + CANARY, SID)
    assert rec["argv"] == want
    assert rec["error"] == ""
    joined = "\n".join(rec["argv"])
    assert CANARY not in joined
    assert "spoken request" not in joined


class _Proc:
    """Enough of a Popen for a turn that ends at once."""
    pid = 4242

    def __init__(self, argv, **kw):
        self.argv = argv
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("")
        self.stderr = io.StringIO("")
        self.returncode = 0

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass

    terminate = kill


@pytest.mark.parametrize("name", ["codex", "gemini", "agy", "copilot"])
def test_the_line_shown_is_what_the_turn_hands_to_popen(name, monkeypatch):
    """Not just the same builder: the very list Popen received, recorded as
    the last launch, equals what launch_argv says the next one is."""
    import subprocess
    a = BUILDERS[name]()
    if name == "gemini":
        monkeypatch.setattr(type(a), "available", lambda self: True)
    seen = []

    def fake(argv, **kw):
        seen.append(list(argv))
        return _Proc(argv)
    monkeypatch.setattr(subprocess, "Popen", fake)
    list(a.send("hello there " + CANARY, None))
    assert seen, "the turn never started a process"
    assert a.last_launch["argv"] == seen[0]
    assert a.last_launch["pid"] == 4242
    assert runinfo.record_for(a)["argv"] == seen[0]
    assert CANARY not in "\n".join(seen[0])


def test_claudes_spawn_records_the_line_it_started(monkeypatch):
    import subprocess
    a = _claude()
    seen = []

    def fake(argv, **kw):
        seen.append(list(argv))
        return _Proc(argv)
    monkeypatch.setattr(subprocess, "Popen", fake)
    a.prepare(SID)
    a.cancel()
    assert seen and a.last_launch["argv"] == seen[0]
    rec = runinfo.record_for(a, session_id=SID)
    assert rec["argv"] == seen[0]
    assert rec["last"]["argv"] == seen[0]
    assert "--resume" in seen[0] and SID in seen[0]
    assert CANARY not in "\n".join(seen[0])


def test_an_endpoint_has_no_line_and_says_where_it_goes():
    from adapters.openai_compat import OpenAICompatible
    a = OpenAICompatible("https://user:pw@api.example.com:8443/v1?key=sekrit", "m-1",
                         api_key="sk-live-abcdef0123456789")
    rec = runinfo.record_for(a)
    assert rec["argv"] is None
    assert rec["endpoint"]["host"] == "api.example.com:8443"
    assert "sekrit" not in json.dumps(rec) and "abcdef0123" not in json.dumps(rec)


def test_codex_refusing_to_start_is_shown_in_its_own_words(monkeypatch):
    from adapters import codex
    monkeypatch.setattr(codex, "config_servers", lambda: None)
    rec = runinfo.record_for(_codex())
    assert rec["argv"] is None
    assert "config.toml cannot be read whole" in rec["error"]


def test_a_busy_agent_keeps_its_previous_line():
    a = _claude()
    first = runinfo.record_for(a)
    a.model = "opus"
    kept = runinfo.record_for(a, busy=True, previous=first)
    assert kept["argv"] == first["argv"]
    assert runinfo.record_for(a)["argv"] != first["argv"]


def test_handed_servers_follow_argvs_own_conditions(monkeypatch):
    a = _claude()
    a.desktop_tools = True
    a.detected_servers = {"github": {"command": "gh"}}
    a.browser_tools = True
    names = [s["name"] for s in a.handed_servers()]
    assert names == ["agentvoice-desktop", "agentvoice-crew", "github", "claude-in-chrome"]
    a.no_tools = True
    assert a.handed_servers() == []


def test_codex_lists_a_config_server_it_starts_switched_off(monkeypatch):
    from adapters import codex
    monkeypatch.setattr(codex, "config_servers", lambda: {"filesystem": {"command": "npx"}})
    a = _codex()
    got = {s["name"]: s["on"] for s in a.handed_servers()}
    assert got == {"agentvoice-crew": True, "filesystem": False}
    assert "mcp_servers.filesystem.enabled=false" in a._argv("", None)


# --- redaction -------------------------------------------------------------------------

@pytest.mark.parametrize("argv,hidden", [
    (["x", "--api-key", "sk-abcdefgh12345678"], "sk-abcdefgh12345678"),
    (["x", "--token=plainvalue"], "plainvalue"),
    (["x", "-c", 'mcp_servers.gh.env.GITHUB_TOKEN="ghp_abcdefgh12345678"'], "ghp_abcdefgh12345678"),
    (["x", "-c", 'mcp_servers.gh.bearer_token="hello"'], "hello"),
    (["x", "-c", 'mcp_servers.gh.env={"A"="valueA"}'], "valueA"),
    (["x", "--header", "Authorization: Bearer xyz.abc"], "xyz.abc"),
    (["x", "https://bob:hunter2@host.example/p?key=abc"], "hunter2"),
    (["x", "https://host.example/p?key=abc123"], "abc123"),
    (["x", '{"command": "run --flag ghp_abcdefgh12345678 done"}'], "ghp_abcdefgh12345678"),
    (["x", "Q2hhbmdlTWVQbGVhc2UxMjM0NTY3"], "Q2hhbmdlTWVQbGVhc2UxMjM0NTY3"),
    (["x", "-e", "TOKEN=abc"], "TOKEN=abc"),
])
def test_a_synthetic_secret_in_a_launch_line_is_redacted(argv, hidden):
    shown = runinfo.redact_argv(argv)
    assert hidden not in "\n".join(shown)
    assert runinfo.MASK in "\n".join(shown)
    assert len(shown) == len(argv)


def test_redaction_keeps_what_is_not_a_secret():
    argv = ["claude", "--no-session-persistence", "--append-system-prompt-file",
            "/run/user/1000/agentvoice/prompts/0123456789abcdef0123.txt",
            "--resume", SID, "-c", 'mcp_servers.agentvoice-crew.env_vars=["XDG_RUNTIME_DIR"]',
            "--settings", '{"skillOverrides": {"sk-reading-list": "off"}}',
            "--plugin-dir", "/home/u/.local/share/agentvoice/agent-plugins/main-abc123"]
    assert runinfo.redact_argv(argv) == argv


def test_a_secret_in_a_real_adapters_line_never_reaches_the_file_or_the_cli(
        monkeypatch, capsys, cfg_factory):
    """End to end: an adapter whose line carries a key (as a hand-written
    `-c` would), published by the daemon's own record_for and write, read
    back by the CLI."""
    secret = "ghp_SYNTHETIC0000000000000000"
    a = _codex()
    real = a._argv
    monkeypatch.setattr(a, "_argv", lambda text, sid: real(text, sid) + [
        "-c", f'mcp_servers.gh.env.GITHUB_TOKEN="{secret}"'])
    runinfo.write({"main": runinfo.record_for(a)})
    assert secret not in runinfo.path().read_text()
    assert oct(runinfo.path().stat().st_mode & 0o777) == "0o600"
    monkeypatch.setattr(runinfo, "_daemon_alive", lambda pid: True)
    import runtime
    monkeypatch.setattr(runtime, "Config", lambda: cfg_factory())
    assert runinfo.cli("main", True) == 0
    out = capsys.readouterr().out
    assert secret not in out
    v = json.loads(out)
    assert v["daemon"] is True and v["line"].startswith("codex exec")
    assert runinfo.cli("main", False) == 0
    assert secret not in capsys.readouterr().out


def test_a_file_left_by_a_dead_daemon_says_nothing(monkeypatch):
    from paths import RUNTIME_DIR
    # A Daemon built by an earlier test leaves a pidfile naming this process.
    (RUNTIME_DIR / "pid").unlink(missing_ok=True)
    runinfo.write({"main": {"program": "claude", "argv": ["claude"]}})
    assert runinfo.read() == {}         # no pidfile at all
    (RUNTIME_DIR / "pid").write_text(str(os.getpid()))
    try:
        assert runinfo.read()["agents"]["main"]["argv"] == ["claude"]
        (RUNTIME_DIR / "pid").write_text("1")
        assert runinfo.read() == {}
    finally:
        (RUNTIME_DIR / "pid").unlink(missing_ok=True)


# --- the hook decides the same when its audit write fails ---------------------------------

def _run_main(monkeypatch, capsys, stdin: str, argv=("permission_hook.py", "claude")) -> tuple[int, str]:
    """main() as Claude Code runs it: the program, and an agent's id or none."""
    monkeypatch.setattr("sys.argv", list(argv))
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    code = hook.main()
    return code, capsys.readouterr().out


#: (payload, level): silence (nobody answers), a level allow, a free tool, a
#: refusal before asking, malformed input, and a payload of the wrong shape.
CASES = [
    (json.dumps({"tool_name": "Bash", "tool_input": {"command": f"echo {CANARY}"}}), "ask"),
    (json.dumps({"tool_name": "Bash", "tool_input": {"command": f"echo {CANARY}"}}), "trusted"),
    (json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}}), "ask"),
    (json.dumps({"tool_name": "mcp__unknown-server__do", "tool_input": {}}), "ask"),
    ("not json at all", "ask"),
    ('{"tool_name": {}, "tool_input": []}', "ask"),
]


def _boom(*a, **k):
    raise RuntimeError("audit disk on fire")


def _exit(*a, **k):
    raise SystemExit("interrupted by signal 15")


@pytest.mark.parametrize("payload,level", CASES)
@pytest.mark.parametrize("failure", [_boom, _exit, KeyboardInterrupt])
def test_the_hook_decides_the_same_when_its_audit_write_raises(
        monkeypatch, capsys, payload, level, failure):
    monkeypatch.setattr(hook, "TIMEOUT", 0.2)
    monkeypatch.setattr(hook, "_settings", lambda: (level, None))
    baseline = _run_main(monkeypatch, capsys, payload)

    def raising(*a, **k):
        if failure is KeyboardInterrupt:
            raise KeyboardInterrupt
        failure()
    monkeypatch.setattr(audit, "record", raising)
    broken = _run_main(monkeypatch, capsys, payload)
    assert broken == baseline
    # One decision on stdout, never a second one from the failure.
    assert broken[1].count("hookSpecificOutput") == 1
    if level == "ask" and "Bash" in payload:
        assert json.loads(broken[1])["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_silence_still_denies_when_the_record_raises(monkeypatch, capsys):
    """The plan's mutation, kept as a test: make the audit write raise, and
    a card nobody answers is still a denial."""
    monkeypatch.setattr(hook, "TIMEOUT", 0.2)
    monkeypatch.setattr(audit, "record", _boom)
    code, out = _run_main(monkeypatch, capsys, json.dumps(
        {"tool_name": "Write", "tool_input": {"file_path": "/tmp/a", "content": "x"}}))
    assert code == 0
    d = json.loads(out)["hookSpecificOutput"]
    assert d["permissionDecision"] == "deny"
    assert "Nobody answered" in d["permissionDecisionReason"]


def test_a_held_audit_lock_costs_half_a_second_and_changes_nothing():
    """In a real hook process, so a lock that blocks is a failure here, not
    a hung suite (an in-process flock on a second descriptor would wait on
    this very test forever)."""
    import subprocess
    import paths
    paths.private_dir(paths.DATA_DIR)
    payload = json.dumps({"tool_name": "mcp__found__x", "tool_input": {}})

    def run():
        t0 = time.monotonic()
        out = subprocess.run([sys.executable, str(ROOT / "daemon/permission_hook.py"), "claude"],
                             input=payload, capture_output=True, text=True, timeout=20,
                             env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        return out.returncode, out.stdout, time.monotonic() - t0

    free = run()
    fd = os.open(paths.DATA_DIR / ".audit.lock", os.O_WRONLY | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        held = run()
    finally:
        os.close(fd)
    assert held[:2] == free[:2]
    assert json.loads(held[1])["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert held[2] < free[2] + 3.0


def test_a_signal_during_the_record_leaves_the_decision_alone(monkeypatch, capsys):
    """Claude Code kills the hook's group when a turn is interrupted; a
    SIGTERM landing while the line is written is a SystemExit there (the
    hook's own handler), swallowed after the decision is out."""
    monkeypatch.setattr(hook, "_settings", lambda: ("trusted", None))

    def interrupted(*a, **k):
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(0.5)
        raise AssertionError("the signal should have ended this")
    monkeypatch.setattr(audit, "record", interrupted)
    saved = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT), \
        signal.getsignal(signal.SIGHUP)
    try:
        code, out = _run_main(monkeypatch, capsys, json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}}))
    finally:
        for sig, h in zip((signal.SIGTERM, signal.SIGINT, signal.SIGHUP), saved):
            signal.signal(sig, h)
    assert code == 0
    assert out.count("hookSpecificOutput") == 1
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "allow"


# --- what a permission line holds --------------------------------------------------------

def _lines():
    return [x for x in audit.read(500) if x.get("kind") == "permission"]


def test_a_decision_is_recorded_without_its_arguments(monkeypatch, capsys):
    monkeypatch.setattr(hook, "_settings", lambda: ("trusted", None))
    before = len(_lines())
    _run_main(monkeypatch, capsys, json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": f"cat /home/u/{CANARY}.txt"}}))
    lines = _lines()
    assert len(lines) == before + 1
    line = lines[-1]
    assert {k: line[k] for k in ("from", "tool", "decision", "how", "level")} == {
        "from": "main", "tool": "Bash", "decision": "allow", "how": "level", "level": "trusted"}
    assert set(line) <= {"at", "kind", "from", "to", "tool", "decision", "how", "level"}
    assert CANARY not in audit.log_path().read_text()
    # An extra agent's hook is started with its id, and the line says so.
    _run_main(monkeypatch, capsys, json.dumps({"tool_name": "Bash", "tool_input": {}}),
              argv=("permission_hook.py", "claude", "sora"))
    assert _lines()[-1]["from"] == "sora"


def test_how_each_decision_was_reached(monkeypatch, capsys, card_desk):
    import cardhelp
    monkeypatch.setattr(hook, "TIMEOUT", 0.3)
    bash = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
    # Asked and answered.
    cardhelp.answer_after(card_desk, 0.0, "allow")
    _run_main(monkeypatch, capsys, bash)
    assert _lines()[-1]["how"] == "asked" and _lines()[-1]["decision"] == "allow"
    cardhelp.answer_after(card_desk, 0.0, "deny")
    _run_main(monkeypatch, capsys, bash)
    assert _lines()[-1]["how"] == "asked" and _lines()[-1]["decision"] == "deny"
    # Nobody answered.
    _run_main(monkeypatch, capsys, bash)
    assert _lines()[-1]["how"] == "unanswered" and _lines()[-1]["decision"] == "deny"
    # Allowed for this chat: the grant the card's "allow all" writes.
    session = "11111111-2222-3333-4444-555555555555"
    assert hook.grant(session)
    try:
        _run_main(monkeypatch, capsys, json.dumps({"tool_name": "Bash", "session_id": session,
                                                   "tool_input": {"command": "ls"}}))
        assert _lines()[-1]["how"] == "chat" and _lines()[-1]["decision"] == "allow"
    finally:
        hook.revoke(session)
    # Refused without asking: a server found on this machine, switched off.
    _run_main(monkeypatch, capsys, json.dumps({"tool_name": "mcp__found__x", "tool_input": {}}))
    assert _lines()[-1]["how"] == "refused"
    # The hook itself failing.
    monkeypatch.setattr(hook, "decide", _boom)
    _run_main(monkeypatch, capsys, bash)
    assert _lines()[-1]["how"] == "failed" and _lines()[-1]["decision"] == "deny"


def test_a_free_tool_leaves_no_line(monkeypatch, capsys):
    before = len(_lines())
    for payload in ({"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}},
                    {"tool_name": "TodoWrite", "tool_input": {}},
                    {"tool_name": "mcp__agentvoice-crew__notes_read", "tool_input": {}}):
        _run_main(monkeypatch, capsys, json.dumps(payload))
    assert len(_lines()) == before


def test_the_fields_are_held_to_their_lists():
    assert audit.record("permission", frm="sora", to="sora", tool="Bash; rm -rf ~",
                        decision="maybe", how="because I said", level="root")
    line = audit.read(1)[-1]
    assert line["tool"] == "?" and line["decision"] == "?"
    assert line["how"] == "?" and line["level"] == "?"


def test_the_hooks_record_call_reads_only_the_tools_name_and_the_outcome():
    """Parsed: in main(), _record_decision is handed three plain names, none
    of them the input or the payload."""
    tree = ast.parse((ROOT / "daemon/permission_hook.py").read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "_record_decision"]
    assert len(calls) == 1
    names = {a.id for a in calls[0].args if isinstance(a, ast.Name)}
    assert names == {"tool_name", "decision", "how"}
    assert len(calls[0].args) == 3 and not calls[0].keywords


def test_how_never_decides_anything():
    """_HOW is written by decide() and _ask(), and read only in main(), after
    the decision is made: a read anywhere else could make the record a part
    of the decision."""
    tree = ast.parse((ROOT / "daemon/permission_hook.py").read_text())
    readers = set()
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for n in ast.walk(fn):
                if isinstance(n, ast.Name) and n.id == "_HOW" and isinstance(n.ctx, ast.Load):
                    readers.add(fn.name)
    assert readers == {"main"}


# --- two agents on one backend --------------------------------------------------------------

def test_two_agents_on_one_backend_are_told_apart(daemon, cfg_factory):
    from crew import Persona
    main = _claude()
    sora = _claude(named="sora")
    sora.cwd = "/srv/sora"
    daemon.agent = main
    p = Persona("sora", {"id": "sora", "name": "sora", "label": "Sora", "agent": "claude"})
    p.agent = sora
    daemon.crew = {"sora": p}
    daemon._main.session_id = SID
    daemon.agent_ring.add("main", "turn", secs=1.0)
    daemon.agent_ring.add("sora", "turn", secs=2.0, error="limit")
    assert daemon.publish_runinfo(daemon.personas())
    agents = json.loads(runinfo.path().read_text())["agents"]
    assert set(agents) == {"main", "sora"}
    hook_main = json.loads(agents["main"]["argv"][agents["main"]["argv"].index("--settings") + 1])
    hook_sora = json.loads(agents["sora"]["argv"][agents["sora"]["argv"].index("--settings") + 1])
    cmd = lambda h: h["hooks"]["PreToolUse"][0]["hooks"][0]["command"]  # noqa: E731
    assert cmd(hook_main).endswith("claude") and cmd(hook_sora).endswith("claude sora")
    assert agents["main"]["cwd"] == "/tmp" and agents["sora"]["cwd"] == "/srv/sora"
    assert agents["main"]["session"]["id"] == SID and agents["sora"]["session"]["id"] is None
    assert [x["text"] for x in agents["main"]["log"]] == ["turn 1.0s"]
    assert [x["text"] for x in agents["sora"]["log"]] == ["turn 2.0s · failed (limit)"]
    # And the decisions, by the id the hook was started with.
    audit.record("permission", frm="sora", to="sora", tool="mcp__only-sora__x",
                 decision="deny", how="unanswered", level="ask")
    assert runinfo.decisions("sora")[0]["tool"] == "mcp__only-sora__x"
    assert all(d["tool"] != "mcp__only-sora__x" for d in runinfo.decisions("main"))


def test_publish_is_quiet_when_nothing_moved(daemon):
    daemon.agent = _claude()
    agents = daemon.personas()
    assert daemon.publish_runinfo(agents, now=1000.0)
    assert not daemon.publish_runinfo(agents, now=1001.0)
    daemon.agent_ring.add("main", "turn", secs=1.0)
    assert daemon.publish_runinfo(agents, now=1002.0)
    # A config.toml or a scan can move under a line with nothing visible
    # changing: rebuilt every RUNINFO_EVERY_S, written only if it differs.
    daemon.agent.model = "opus"
    assert not daemon.publish_runinfo(agents, now=1003.0)
    assert daemon.publish_runinfo(agents, now=1003.0 + daemon.RUNINFO_EVERY_S)


# --- the log ring --------------------------------------------------------------------------

def test_the_ring_takes_no_text():
    ring = runinfo.Ring()
    line = ring.add("sora", "a sentence somebody said", secs="ten seconds",
                    tools=["Bash", "rm -rf ~ please", CANARY + " text"], error="the reply text",
                    changed=["level", "my secret"], start="lukewarm")
    assert line["kind"] == "?"
    assert "secs" not in line
    assert dict(line["tools"]) == {"Bash": 1, "?": 2}
    assert line["error"] == "unknown" and line["start"] == "?"
    assert line["changed"] == ["?", "level"]
    assert "said" not in json.dumps(ring.lines("sora"))
    assert "please" not in json.dumps(ring.lines("sora"))


def test_the_ring_renders_a_turn():
    ring = runinfo.Ring()
    ring.add("main", "turn", secs=12.34, first_ms=820, start="cold",
             tools=["Bash", "Read", "Bash", "Bash"], stopped=True)
    ring.add("main", "rebuilt", changed={"level", "model"}, kept=True)
    ring.add("main", "dropped", error="too_long")
    assert [x["text"] for x in ring.lines("main")] == [
        "turn 12.3s · cold start · first token 820 ms · tools: Bash ×3, Read · stopped",
        "started again for a new level and model · conversation kept",
        "conversation dropped after a failure (too_long)"]


def test_the_ring_is_bounded_and_counts_turns_per_session():
    ring = runinfo.Ring(size=3)
    for i in range(5):
        ring.add("main", "turn", secs=i)
    assert [x["secs"] for x in ring.lines("main")] == [2.0, 3.0, 4.0]
    assert ring.count_turn("main", "a") == 1
    assert ring.count_turn("main", "a") == 2
    assert ring.turns("main", "a") == 2 and ring.turns("main", "b") == 0
    assert ring.count_turn("main", "b") == 1


#: Names a call to agent_ring.add in the daemon may read: numbers, a tool
#: list, failure and session vocabularies, an id. Never a reply, a transcript
#: or an error's text.
RING_SAFE = {"persona", "p", "secs", "ttft", "start", "tools_seen", "kind", "stopped",
             "in_task", "changed", "kept", "had", "sid", "None"}


def test_every_ring_call_reads_only_names_that_hold_no_content():
    tree = ast.parse((ROOT / "daemon/wake_listen.py").read_text())
    calls = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add" and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "agent_ring"):
            continue
        calls += 1
        for arg in list(node.args) + [k.value for k in node.keywords]:
            names = {n.id for n in ast.walk(arg) if isinstance(n, ast.Name)}
            attrs = {n.attr for n in ast.walk(arg) if isinstance(n, ast.Attribute)}
            assert names <= RING_SAFE, f"line {node.lineno} reads {names - RING_SAFE}"
            assert attrs <= {"id"}, f"line {node.lineno} reads .{attrs - {'id'}}"
    assert calls >= 4


def test_a_turn_writes_one_structural_line(daemon):
    """Driven: a real answer() over a fake agent that uses a tool, says a
    sentence holding the canary and fails; the ring has the turn by its
    numbers and kinds, and none of what was said."""
    from adapters.base import Chunk

    class Agent:
        name = "claude"
        last_start = "warm"

        def send(self, text, session_id=None):
            yield Chunk(tool="Bash")
            yield Chunk(text=f"I looked at {CANARY} for you. ", session_id=SID)
            yield Chunk(error="You've hit your usage limit")

        def cancel(self):
            pass
    daemon.agent = Agent()
    daemon.answer(f"please check {CANARY}", {})
    lines = daemon.agent_ring.lines("main")
    assert len(lines) == 1
    assert lines[0]["kind"] == "turn" and lines[0]["error"] == "limit"
    assert lines[0]["tools"] == [("Bash", 1)] and lines[0]["start"] == "warm"
    assert CANARY not in json.dumps(lines)
    assert daemon.agent_ring.turns("main", SID) == 1


# --- the page -----------------------------------------------------------------------------

def test_the_view_keeps_given_apart_from_seen(monkeypatch, cfg_factory):
    import tooldetect
    a = _claude()
    a.detected_servers = {"github": {"command": "gh"}}
    monkeypatch.setattr(runinfo, "read", lambda: {"daemon_pid": 1, "at": 1.0,
                                                  "agents": {"main": runinfo.record_for(a)}})
    monkeypatch.setattr(tooldetect, "read_live", lambda: {"main": {"servers": [
        {"name": "github", "status": "failed"}, {"name": "old-one", "status": "connected"}]}})
    v = runinfo.view("main", cfg_factory())
    rows = {s["name"]: s for s in v["servers"]}
    assert rows["agentvoice-crew"] == {"name": "agentvoice-crew", "source": "agentvoice",
                                       "given": "on", "seen": ""}
    assert rows["github"]["given"] == "on" and rows["github"]["seen"] == "failed"
    assert rows["old-one"]["given"] == "not now" and rows["old-one"]["source"] == "seen"
    assert v["reports_seen"] is True


def test_the_view_refuses_an_agent_that_is_not_there(cfg_factory):
    with pytest.raises(ValueError):
        runinfo.view("nobody", cfg_factory())
    with pytest.raises(ValueError):
        runinfo.view("../etc", cfg_factory())


def test_the_page_draws_everything_as_plain_text_and_writes_nothing():
    """The Advanced tab, read rather than run (CLAUDE.md): every Text in the
    new part is PlainText, it calls only `agents runinfo` and `agents prompt`
    and the log terminal, and writes no setting."""
    src = (ROOT / "pages/AgentDetailsPage.qml").read_text()
    start = src.index("// What is running (phase M16)")
    end = src.index('label: "Id"')
    part = src[start:end]
    assert part.count("Text {") == part.count("textFormat: Text.PlainText")
    assert '"agents", "runinfo"' in part and '"agents", "prompt"' in part
    for writer in ("s.put(", "setAgentField", "setAgentTool", '"bar", "set"'):
        assert writer not in part
    assert "concealed: true" in part
    # The terminal is handed a constant: nothing from settings in it.
    assert '"journalctl --user -u agentvoice -n 300 -f"' in part


def test_the_prompt_preview_conceals_until_asked():
    src = (ROOT / "ui/PromptPreview.qml").read_text()
    assert "property bool concealed: false" in src
    assert "pv.shown(index) ? String(modelData.text)" in src


def test_a_chat_grant_does_not_pay_for_the_level(tmp_path):
    """FINDINGS §50: on an "allow all in this chat" path decide() never loads
    the settings code, and the record must not load it either (~40 ms a
    call); the level is left out there. A fresh interpreter, as Claude Code
    starts the hook. -B as well as the variable: -I ignores PYTHON*, and a
    hook run from the clone must not leave bytecode in it (found by the
    bare-runner check in M16)."""
    import subprocess
    env = {**os.environ, "XDG_DATA_HOME": str(tmp_path / "data"),
           "XDG_CONFIG_HOME": str(tmp_path / "cfg"), "XDG_RUNTIME_DIR": str(tmp_path / "run"),
           "PYTHONDONTWRITEBYTECODE": "1"}
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import permission_hook as h; "
            "sys.argv = ['permission_hook.py', 'claude']; "
            "h._record_decision('Bash', 'allow', 'chat'); print('runtime' in sys.modules)")
    out = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(ROOT / "daemon")],
                         env=env, capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == "False", out.stderr
    line = json.loads((tmp_path / "data/agentvoice/audit.log").read_text().splitlines()[-1])
    assert line["how"] == "chat" and "level" not in line


def test_decisions_come_from_the_end_of_the_log_and_its_archive():
    """The page reads the newest few: from the end of audit.log, then of
    audit.log.1, never a partial first line, never another agent's."""
    import paths
    paths.private_dir(paths.DATA_DIR)
    old = audit.log_path().with_name("audit.log.1")
    keep = [(p, p.read_bytes() if p.exists() else None) for p in (audit.log_path(), old)]
    try:
        filler = json.dumps({"at": 1, "kind": "note_write", "from": "main", "to": "main"}) + "\n"
        archived = json.dumps({"at": 2, "kind": "permission", "from": "zed", "to": "zed",
                               "tool": "Write", "decision": "deny", "how": "asked"}) + "\n"
        old.write_text(filler * 10 + archived)
        newest = json.dumps({"at": 3, "kind": "permission", "from": "zed", "to": "zed",
                             "tool": "Bash", "decision": "allow", "how": "level"}) + "\n"
        audit.log_path().write_text(filler * (runinfo.TAIL_BYTES // len(filler) + 50) + newest)
        got = runinfo.decisions("zed")
        assert [d["tool"] for d in got] == ["Bash", "Write"]
        assert runinfo.decisions("nobody") == []
    finally:
        for p, data in keep:
            if data is None:
                p.unlink(missing_ok=True)
            else:
                p.write_bytes(data)
