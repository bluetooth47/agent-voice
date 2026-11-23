"""Phase M17: how an agent is launched -- extra flags, environment variables,
resume, the hung-turn limit -- and Start fresh.

The flags and the environment are a way round every other decision Agent
Voice makes, so the tests that matter most here are the ones that run the
adapter: a refused flag is refused *at launch*, in every spelling, with the
settings written past the page, and no process starts. The page's own check
is the same function (`agents flags check`), so there is one list.
"""
from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import launch_extras
from launch_extras import LaunchRefused

ROOT = Path(__file__).resolve().parent.parent

#: A pid above any pid_max: stop_tree's getpgid() on it fails, so a fake
#: process is never mistaken for a real process group.
NO_PID = 4194304 + 4242

CANARY = "sk-ant-CANARYVALUE0123456789abcdef"


class FakeProc:
    """What Popen hands back, recording what it was given."""

    def __init__(self, argv, env, lines=()):
        self.argv, self.env, self.pid = list(argv), env, NO_PID
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("".join(line + "\n" for line in lines))
        self.stderr = io.StringIO("")

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass

    def terminate(self):
        pass


@pytest.fixture
def popen(monkeypatch):
    """Every Popen an adapter makes, faked and recorded."""
    class Made(list):
        pass
    made = Made()

    def fake(argv, **kw):
        proc = FakeProc(argv, kw.get("env"), fake.lines)
        made.append(proc)
        return proc
    fake.lines = ()
    import adapters.claude_code as cc
    import adapters.codex as cx
    monkeypatch.setattr(cc.subprocess, "Popen", fake)
    monkeypatch.setattr(cx.subprocess, "Popen", fake)
    made.fake = fake
    return made


@pytest.fixture(autouse=True)
def _no_env_file():
    """The env file lives in the sandbox's config folder, shared by every
    test: none before, none after."""
    launch_extras.env_path().unlink(missing_ok=True)
    launch_extras._CACHE.clear()
    yield
    launch_extras.env_path().unlink(missing_ok=True)
    launch_extras._CACHE.clear()


@pytest.fixture
def codex_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    (tmp_path / "codex").mkdir()
    return tmp_path / "codex"


def _claude(**kw):
    from adapters.claude_code import ClaudeCode
    a = ClaudeCode(**kw)
    a.keep_warm_s = 0
    return a


def _codex(**kw):
    from adapters.codex import Codex
    return Codex(**kw)


# --- the denylist, every spelling ---------------------------------------------------------

#: The master plan's list (M17), by program: each must be refused.
PLAN_CLAUDE = ("--permission-mode", "--dangerously-skip-permissions", "--settings",
               "--setting-sources", "--mcp-config", "--strict-mcp-config", "--plugin-dir",
               "--allowedTools", "--add-dir", "--append-system-prompt",
               "--append-system-prompt-file", "--resume", "--output-format")
PLAN_CODEX = ("-c", "--config", "--sandbox", "--full-auto",
              "--dangerously-bypass-approvals-and-sandbox", "--dangerously-bypass-hook-trust")


def _spellings(flag: str) -> list[str]:
    """The ways one refused flag can be written."""
    if not flag.startswith("--"):
        return [flag, flag + "=x", flag.upper() if flag[1:].isalpha() else flag]
    name = flag[2:]
    out = [flag, flag + "=x", flag + "=", "--" + name.upper(), "--" + name.swapcase()]
    if len(name) > 4:
        out.append("--" + name[:-1])            # an abbreviation
    return out


@pytest.mark.parametrize("program,flag", [("claude", f) for f in PLAN_CLAUDE] +
                                         [("codex", f) for f in PLAN_CODEX])
def test_the_plans_flags_are_refused_in_every_spelling(program, flag):
    for spelled in _spellings(flag):
        assert launch_extras.judge(program, spelled) is not None, spelled


@pytest.mark.parametrize("program", ["claude", "codex"])
def test_every_listed_name_is_refused_in_every_spelling(program):
    deny, short, _ = launch_extras._RULES[program]
    for name in deny:
        for spelled in _spellings("--" + name):
            assert launch_extras.judge(program, spelled) is not None, spelled
        assert launch_extras.judge(program, "--no-" + name) is not None, name
    for letter in short:
        for spelled in (f"-{letter}", f"-{letter}=x", f"-{letter.upper()}"):
            assert launch_extras.judge(program, spelled) is not None, spelled


@pytest.mark.parametrize("arg,why", [
    ("mcp", "bare"), ("update", "bare"), ("resume", "bare"), ("exec", "bare"), ("", "bare"),
    ("-", "bare"), ("--", "end"), ("-pc", "cluster"), ("-dangerously-skip-permissions", "cluster"),
    ("-cfoo=1", "cluster"), ("--a b", "shape"), ("---x", "shape"), ("--=x", "shape"),
    ("--dángerous", "shape"), ("--x\nY", "control"), ("--x\x00", "control"),
    ("--name=" + "x" * 300, "long"),
])
def test_shapes_that_could_hide_a_command_are_refused(arg, why):
    """A bare word is a subcommand (`claude mcp add`, `codex exec resume`) or
    the request itself; `--` makes everything after it one; a cluster is
    several flags; and a value goes after =, never in the next element."""
    for program in ("claude", "codex"):
        assert launch_extras.judge(program, arg) == why, (program, arg)


@pytest.mark.parametrize("name", ["permission-foo", "mcp-bar", "foo-hook", "use-sandbox",
                                  "auto-approve", "settings-file", "more-tools", "plugin-x",
                                  "extra-dir", "system-prompt-x", "fork-it", "jsonl",
                                  "remote-x", "api-key", "auth-token", "keep-session",
                                  "env-file", "workspace", "trust-all"])
def test_a_flag_added_next_month_is_refused_by_its_words(name):
    """The words catch what the exact lists cannot know yet."""
    for program in ("claude", "codex"):
        assert launch_extras.judge(program, "--" + name) is not None, (program, name)


@pytest.mark.parametrize("program,flag", [
    ("claude", "--debug"), ("claude", "--debug=api"), ("claude", "--max-budget-usd=2"),
    ("claude", "--fallback-model=haiku"), ("claude", "--betas=x"), ("claude", "--name=x"),
    ("claude", "-n=x"), ("claude", "-d"), ("claude", "--autocompact=auto"),
    ("codex", "--color=never"), ("codex", "--oss"), ("codex", "--local-provider=ollama"),
])
def test_harmless_flags_are_passed(program, flag):
    assert launch_extras.judge(program, flag) is None


def test_no_harmless_name_holds_a_refused_word():
    """Read off --help and let through: none may contain a word that would
    refuse it (the words are checked first, so this holds the list honest)."""
    for program, (deny, _, known) in launch_extras._RULES.items():
        assert not (set(deny) & known), program
        for name in known:
            squashed = name.replace("-", "")
            assert not [w for w, _ in launch_extras._WORDS if w in squashed], (program, name)


def test_another_program_is_passed_none():
    assert launch_extras.judge("gemini", "--debug") == "program"
    assert launch_extras.checked_env("gemini", {"GEMINI_API_KEY": "x"}) == {}


def test_a_refusal_names_the_flag_and_never_its_value():
    why = launch_extras.refusal("claude", ["--debug", f"--api-key={CANARY}"])
    assert "--api-key" in why and CANARY not in why
    with pytest.raises(LaunchRefused) as e:
        launch_extras.checked("claude", [f"--settings={CANARY}"])
    assert "--settings" in str(e.value) and CANARY not in str(e.value)
    assert launch_extras.refusal("claude", ["--debug"] * 17).startswith("it has more than 16")


def test_unreadable_flags_are_none():
    assert launch_extras.args_choice(None) == []
    assert launch_extras.args_choice(["--debug"]) == ["--debug"]
    for bad in ("--debug", {"a": 1}, [1], ["--x", None], ["x"] * 65):
        assert launch_extras.args_choice(bad) is None


# --- refused at launch, in the adapter -------------------------------------------------------

@pytest.mark.parametrize("flag", [*PLAN_CLAUDE, "--bare", "--safe-mode", "--dangerously",
                                  "mcp", "--", "-p", "--no-strict-mcp-config"])
def test_claude_refuses_a_flag_at_launch_and_starts_nothing(flag, popen):
    """Set on the adapter directly, as a setting written past the page
    would reach it: _argv refuses, prepare() starts nothing and says
    nothing, and the turn is one error in our own words."""
    a = _claude()
    a.extra_args = (flag,)
    with pytest.raises(LaunchRefused):
        a._argv("", None)
    a.prepare(None)
    assert popen == []
    chunks = list(a.send("hello", None))
    assert popen == []
    assert len(chunks) == 1 and chunks[0].error.startswith("Agent Voice did not start it")


@pytest.mark.parametrize("flag", [*PLAN_CODEX, "-C", "--cd=/", "--profile=x", "-o=/tmp/x",
                                  "resume", "--ignore-rules", "--trust"])
def test_codex_refuses_a_flag_at_launch_and_starts_nothing(flag, popen, codex_home):
    a = _codex()
    a.extra_args = (flag,)
    with pytest.raises(LaunchRefused):
        a._argv("", None)
    chunks = list(a.send("hello", None))
    assert popen == []
    assert len(chunks) == 1 and chunks[0].error.startswith("Agent Voice did not start it")


def test_runinfo_shows_the_refusal_in_our_words():
    import runinfo
    a = _claude()
    a.extra_args = (f"--settings={CANARY}",)
    rec = runinfo.record_for(a)
    assert rec["argv"] is None and "--settings" in rec["error"] and CANARY not in rec["error"]


def test_a_refused_launch_is_said_as_its_own_kind():
    import failure
    text = "Agent Voice did not start it: its extra flag --bare is never passed: x. Clear it."
    assert failure.classify(text) == "refused"
    said = failure.spoken("refused", "claude")
    assert "Advanced" in said and "--bare" not in said


def test_a_safe_flag_goes_last_for_claude_cold_and_warm(popen):
    """Cold: the process the wake word starts carries the flag, at the end
    of the line. Warm: the next turn is written to that same process. A
    flag changed by the daemon lets the idle process go, and the next one
    carries the new flag."""
    from adapters.base import Chunk  # noqa: F401
    a = _claude()
    a.extra_args = ("--debug", "--max-budget-usd=2")
    a.prepare(None)                                  # cold
    assert len(popen) == 1
    argv = popen[0].argv
    assert argv[-2:] == ["--debug", "--max-budget-usd=2"]
    assert argv[:2] == ["claude", "-p"]
    assert a.last_launch["argv"] == argv
    a.prepare(None)                                  # warm: the same process
    assert len(popen) == 1
    a.cancel()                                       # what apply_launch does on a change
    a.extra_args = ("--fallback-model=haiku",)
    a.prepare(None)
    assert len(popen) == 2 and popen[1].argv[-1] == "--fallback-model=haiku"
    assert "--debug" not in popen[1].argv


def test_a_refused_launch_still_stops_the_process_it_let_go(popen):
    """A warm process for another conversation is let go when a turn needs
    a new one; if the new one is refused (or fails to start) the old one is
    still stopped, never left running unowned."""
    a = _claude()
    a.prepare("other-session")
    old = popen[0]
    stopped = []
    old.terminate = lambda: stopped.append("terminate")
    old.kill = lambda: stopped.append("kill")
    a.extra_args = ("--bare",)
    a.prepare(None)
    assert len(popen) == 1 and stopped and a._proc is None
    stopped.clear()
    a.extra_args = ()
    a.prepare("other-session")
    again = popen[1]
    again.terminate = lambda: stopped.append("terminate")
    a.extra_args = ("--bare",)
    chunks = list(a.send("hi", None))
    assert chunks[0].error.startswith("Agent Voice did not start it") and stopped


def test_a_safe_flag_goes_straight_after_exec_for_codex(popen, codex_home):
    """Before `--json`: a flag left wanting a value meets one clap will not
    take, rather than eating `resume` and making the session id the request."""
    popen.fake.lines = ['{"type": "thread.started", "thread_id": "t1"}',
                        '{"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}']
    a = _codex()
    a.extra_args = ("--color=never",)
    list(a.send("hello", "abc-123"))
    argv = popen[0].argv
    assert argv[:4] == ["codex", "exec", "--color=never", "--json"]
    assert argv[-2:] == ["resume", "abc-123"]
    assert "hello" not in " ".join(argv)


def test_launch_argv_equals_what_popen_got_with_extras(popen, codex_home):
    """M16's promise still holds with extras: the line shown is the line run."""
    a = _codex()
    a.extra_args = ("--oss",)
    shown = a.launch_argv(None)
    popen.fake.lines = ['{"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}']
    list(a.send("hi", None))
    assert popen[0].argv == shown and "--oss" in shown


# --- environment variables ----------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "PATH", "HOME", "LD_PRELOAD", "ld_library_path", "PYTHONPATH", "PYTHONSTARTUP", "NODE_OPTIONS",
    "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR", "HTTP_PROXY", "https_proxy", "ALL_PROXY", "NO_PROXY",
    "ANTHROPIC_BASE_URL", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CLAUDE_CONFIG_DIR", "CODEX_HOME",
    "CLAUDE_CODE_SIMPLE", "CLAUDE_CODE_SAFE_MODE", "CLAUDE_CODE_SHELL_PREFIX",
    "AGENTVOICE_PERMISSION_TIMEOUT", "BASH_ENV", "ENV", "SHELL", "GIT_SSH_COMMAND",
    "SSL_CERT_FILE", "NODE_EXTRA_CA_CERTS", "MISE_DATA_DIR", "DYLD_INSERT_LIBRARIES",
    "SSH_AUTH_SOCK", "WAYLAND_DISPLAY", "ANTHROPIC_MODEL", "MCP_TIMEOUT", "EDITOR",
    "1BAD", "A-B", "", "X" * 65,
])
def test_the_env_denylist(name):
    assert launch_extras.env_judge(name) is not None, name
    with pytest.raises(ValueError):
        launch_extras.set_env("main", name, "x")


@pytest.mark.parametrize("name", ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY",
                                  "OPENAI_ORG_ID", "GITHUB_TOKEN", "AWS_ACCESS_KEY_ID", "LANG", "TZ"])
def test_keys_are_what_it_is_for(name):
    assert launch_extras.env_judge(name) is None


def test_the_env_file_is_0600_and_its_folder_0700():
    launch_extras.set_env("main", "ANTHROPIC_API_KEY", CANARY)
    path = launch_extras.env_path()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) & 0o077 == 0
    assert launch_extras.env_for("main") == ({"ANTHROPIC_API_KEY": CANARY}, "")
    assert launch_extras.env_for("sora-1") == ({}, "")
    assert launch_extras.unset_env("main", "ANTHROPIC_API_KEY") is True
    assert launch_extras.env_for("main") == ({}, "")


def test_a_file_others_can_read_is_not_used_and_the_writer_puts_it_right():
    launch_extras.set_env("main", "ANTHROPIC_API_KEY", CANARY)
    path = launch_extras.env_path()
    os.chmod(path, 0o644)
    launch_extras._CACHE.clear()
    env, problem = launch_extras.env_for("main")
    assert env == {} and "0600" in problem
    names, problem = launch_extras.env_names("main")
    assert names == ["ANTHROPIC_API_KEY"] and problem
    launch_extras.set_env("main", "OPENAI_API_KEY", "x")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert launch_extras.env_for("main")[0] == {"ANTHROPIC_API_KEY": CANARY, "OPENAI_API_KEY": "x"}


def test_a_link_or_a_corrupt_file_is_never_used_nor_overwritten(tmp_path):
    path = launch_extras.env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    real = tmp_path / "elsewhere.json"
    real.write_text(json.dumps({"agents": {"main": {"ANTHROPIC_API_KEY": "x"}}}))
    os.chmod(real, 0o600)
    path.symlink_to(real)
    assert launch_extras.env_for("main") == ({}, "it is a link, which is never followed")
    with pytest.raises(ValueError):
        launch_extras.set_env("main", "OPENAI_API_KEY", "y")
    path.unlink()
    path.write_text("{not json")
    os.chmod(path, 0o600)
    launch_extras._CACHE.clear()
    assert launch_extras.env_for("main")[1] == "it is not JSON"
    with pytest.raises(ValueError):
        launch_extras.set_env("main", "OPENAI_API_KEY", "y")
    assert path.read_text() == "{not json"          # every other agent's keys kept


def test_a_value_is_checked_and_never_printed(capsys, monkeypatch):
    """The CLI prints names only, whatever it is asked."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(CANARY) + "\n"))
    assert launch_extras.env_cli("main", "set", "ANTHROPIC_API_KEY", True, False) == 0
    for action in ("list",):
        launch_extras.env_cli("main", action, None, False, False)
        launch_extras.env_cli("main", action, None, False, True)
    monkeypatch.setattr(sys, "stdin", io.StringIO("bad\x07value"))
    assert launch_extras.env_cli("main", "set", "OPENAI_API_KEY", False, False) == 1
    monkeypatch.setattr(sys, "stdin", io.StringIO("x"))
    assert launch_extras.env_cli("main", "set", "LD_PRELOAD", False, False) == 1
    out = capsys.readouterr()
    assert CANARY not in out.out + out.err
    assert "ANTHROPIC_API_KEY" in out.out and "LD_PRELOAD is never set" in out.err


def test_the_cli_never_prints_a_value_through_agentvoice(tmp_path):
    """End to end, through bin/agentvoice: the value on stdin, never argv;
    neither output stream holds it."""
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "cfg"),
           "XDG_DATA_HOME": str(tmp_path / "data"), "XDG_RUNTIME_DIR": str(tmp_path / "run"),
           "PYTHONDONTWRITEBYTECODE": "1", "AGENTVOICE_PYTHON": sys.executable}
    run = lambda *a, inp="": subprocess.run([str(ROOT / "bin/agentvoice"), "agents", "env", *a],  # noqa: E731
                                            input=inp, capture_output=True, text=True, env=env,
                                            timeout=60)
    got = run("main", "set", "ANTHROPIC_API_KEY", "--line", inp=json.dumps(CANARY) + "\n")
    assert got.returncode == 0, got.stderr
    listed = run("main", "list", "--json")
    assert json.loads(listed.stdout) == {"names": ["ANTHROPIC_API_KEY"], "problem": ""}
    for p in (got, listed):
        assert CANARY not in p.stdout + p.stderr
    f = tmp_path / "cfg" / "agentvoice" / "agent-env.json"
    assert stat.S_IMODE(f.stat().st_mode) == 0o600 and CANARY in f.read_text()


def test_the_environment_reaches_popen_checked(popen, codex_home):
    a = _claude()
    a.extra_env = {"ANTHROPIC_API_KEY": CANARY}
    a.prepare(None)
    assert popen[0].env["ANTHROPIC_API_KEY"] == CANARY
    assert popen[0].env["PATH"] == os.environ["PATH"]       # the daemon's own, beneath
    assert CANARY not in " ".join(popen[0].argv)
    b = _codex()
    b.extra_env = {"OPENAI_API_KEY": CANARY}
    list(b.send("hi", None))
    assert popen[1].env["OPENAI_API_KEY"] == CANARY
    # None at all: inherited exactly as before M17.
    c = _claude()
    c.prepare(None)
    assert popen[2].env is None


def test_a_denied_name_written_past_the_page_is_refused_at_launch(popen):
    a = _claude()
    a.extra_env = {"LD_PRELOAD": "/tmp/x.so"}
    a.prepare(None)
    chunks = list(a.send("hi", None))
    assert popen == [] and "LD_PRELOAD is never set" in chunks[0].error


# --- the daemon: apply_launch, resume, the timeout ------------------------------------------------

class P:
    def __init__(self, pid="", spec=None, main=False, label=""):
        self.id, self.spec, self.main, self.label = pid, spec or {}, main, label or pid or "main"
        self.name = self.label


def _bare_daemon(cfg):
    from wake_listen import Daemon
    d = Daemon.__new__(Daemon)
    d.cfg = cfg
    d._said = {}
    return d


def test_apply_launch_hands_everything_and_logs_counts_only(cfg_factory, capsys):
    launch_extras.set_env("main", "ANTHROPIC_API_KEY", CANARY)
    d = _bare_daemon(cfg_factory(mainExtraArgs=["--debug"], mainResume=False,
                                 mainIdleTimeoutS=240))
    a = _claude()
    cancelled = []
    a.cancel = lambda: cancelled.append(1)
    assert d.apply_launch(a, P(main=True)) is True
    assert a.extra_args == ("--debug",) and a.extra_env == {"ANTHROPIC_API_KEY": CANARY}
    assert a.resume is False and a.idle_timeout_s == 240.0
    out = capsys.readouterr().out
    assert "1 extra flag · 1 environment variable" in out
    assert CANARY not in out and "ANTHROPIC_API_KEY" not in out and "--debug" not in out
    # Nothing moved: no new process, no line.
    assert d.apply_launch(a, P(main=True)) is False
    # Through apply_extras the idle process goes when they move.
    d.cfg = cfg_factory(mainExtraArgs=[])
    assert d.apply_launch(a, P(main=True)) is True and a.extra_args == ()


def test_an_endpoint_keeps_its_own_timeout(cfg_factory):
    from adapters.openai_compat import OpenAICompatible as OpenAICompat
    e = OpenAICompat(base_url="http://localhost:11434/v1", model="m", is_agent=True)
    before = e.idle_timeout_s
    _bare_daemon(cfg_factory(mainIdleTimeoutS=30)).apply_launch(e, P(main=True))
    assert e.idle_timeout_s == before


def test_the_timeout_reaches_the_watchdog(cfg_factory, popen, monkeypatch):
    import adapters.claude_code as cc
    seen = []

    class Dog:
        def __init__(self, proc, idle_s, on_timeout=None):
            seen.append(idle_s)
            self.fired = False

        def poke(self):
            pass

        def stop(self):
            pass
    monkeypatch.setattr(cc, "Watchdog", Dog)
    a = _claude()
    _bare_daemon(cfg_factory(mainIdleTimeoutS=420)).apply_launch(a, P(main=True))
    popen.fake.lines = ['{"type": "result", "subtype": "success", "session_id": "s1"}']
    list(a.send("hi", None))
    assert seen == [420.0]


def test_an_extra_agents_launch_follows_its_own_entry(cfg_factory):
    agents = [{"id": "sora-1", "name": "sora", "agent": "codex", "resume": False,
               "idleTimeoutS": 600, "extraArgs": ["--oss"]},
              {"id": "kit-2", "name": "kit", "idleTimeoutS": "soon", "extraArgs": "--oss",
               "resume": "false"}]
    cfg = cfg_factory(voiceAgents=agents, mainIdleTimeoutS=45)
    assert cfg.launch_for("sora-1") == {"resume": False, "idle_s": 600, "args": ("--oss",)}
    assert cfg.launch_for("kit-2") == {"resume": False, "idle_s": 90, "args": None}
    assert cfg.launch_for("main") == {"resume": True, "idle_s": 45, "args": ()}
    assert cfg.launch_for("nobody") == {"resume": True, "idle_s": 90, "args": ()}


@pytest.mark.parametrize("raw,want", [(5, 30), (9000, 600), (90.7, 90), (True, 90), ("90", 90),
                                      (None, 90), (float("inf"), 90), (300, 300)])
def test_the_timeout_is_held_in_bounds(raw, want):
    from runtime import idle_timeout_choice
    assert idle_timeout_choice(raw) == want


def test_unreadable_settings_launch_with_nothing_extra(cfg_factory):
    cfg = cfg_factory(mainExtraArgs=["--debug"], mainResume=False, mainIdleTimeoutS=300)
    cfg.source, cfg._toml_broken = "real", True
    assert cfg.launch_for("main") == {"resume": True, "idle_s": 90, "args": ()}


def _turns(daemon, resume: bool, n: int = 3):
    """n driven turns over an agent that starts a session each time;
    returns the session each was sent with."""
    from adapters.base import Chunk
    sent = []

    class Agent:
        name = "claude"
        last_start = "warm"
        remembers = True

        def __init__(self):
            self.resume = resume

        def send(self, text, session_id=None):
            sent.append(session_id)
            yield Chunk(text="Done. ", session_id=session_id or f"s{len(sent)}")

        def cancel(self):
            pass
    daemon.agent = Agent()
    for _ in range(n):
        daemon.answer("next", {})
    return sent


def test_resume_on_carries_the_session(daemon):
    assert _turns(daemon, True) == [None, "s1", "s1"]


def test_resume_off_sends_every_turn_with_no_session(daemon, monkeypatch):
    import permission_hook
    revoked = []
    monkeypatch.setattr(permission_hook, "revoke", lambda sid: revoked.append(sid) or True)
    assert _turns(daemon, False) == [None, None, None]
    assert daemon.session_id is None
    # Each turn's "allow all in this chat" ended with it.
    assert revoked == ["s1", "s2", "s3"]


def test_resume_off_drops_a_session_set_before_the_turn(daemon):
    """A session put back since the last turn ended -- a delegated task's,
    a skipped open-mic turn's -- is not carried either."""
    from adapters.base import Chunk
    sent = []

    class Agent:
        name = "claude"
        remembers = True
        resume = False

        def send(self, text, session_id=None):
            sent.append(session_id)
            yield Chunk(text="Done. ")

        def cancel(self):
            pass
    daemon.agent = Agent()
    daemon.session_id = "restored-by-a-task"
    daemon.answer("next", {})
    assert sent == [None]


def test_resume_off_means_no_resume_flag_and_no_warm_reuse(popen):
    """At the adapter: no session asked for means no --resume, and a process
    holding the last turn's session is not written the next one."""
    a = _claude()
    popen.fake.lines = ['{"type": "result", "subtype": "success", "session_id": "s1"}']
    list(a.send("one", None))
    assert "--resume" not in popen[0].argv
    a.prepare(None)                       # what prime_agent asks with resume off
    assert len(popen) == 2 and "--resume" not in popen[1].argv
    a.prepare("s1")
    assert "--resume" in popen[-1].argv   # and with it on, the session is resumed


def test_resume_off_replays_a_continued_chat(daemon):
    """A saved chat continued with resume off is read back to the agent,
    not resumed: its session would be dropped before the turn."""
    from crew import Persona
    p = daemon._main

    class Agent:
        name = "claude"
        remembers = True
        cwd = "/tmp"
        resume = False

        def cancel(self):
            pass
    p.agent = Agent()
    chat = {"id": "c1", "owner": "main", "turns": [{"transcript": "hi", "reply": "hello"}],
            "sessions": {"main": {"session_id": "abc", "backend": "claude", "project_dir": "/tmp"}},
            "session_id": "abc", "backend": "claude", "project_dir": "/tmp"}
    assert isinstance(p, Persona)
    assert daemon.continue_chat(p, chat) == "replayed"
    assert p.session_id is None
    p.agent.resume = True
    assert daemon.continue_chat(p, chat) == "resumed" and p.session_id == "abc"


# --- Start fresh ------------------------------------------------------------------------------

def test_start_fresh_ends_only_that_agents_conversation(daemon, monkeypatch, capsys):
    import permission_hook
    revoked = []
    monkeypatch.setattr(permission_hook, "revoke", lambda sid: revoked.append(sid) or True)
    main = daemon._main
    main.session_id = "s-main"
    cancelled = []

    class Agent:
        def cancel(self):
            cancelled.append(1)
    main.agent = Agent()
    assert daemon.apply_chat_command("chat-new main") is True
    assert main.session_id is None and cancelled == [1] and revoked == ["s-main"]
    assert [x["kind"] for x in daemon.agent_ring.lines("main")] == ["fresh"]
    assert "started fresh" in daemon.agent_ring.lines("main")[0]["text"]
    assert daemon.apply_chat_command("chat-new nobody") is True
    assert "no such agent" in capsys.readouterr().out


def test_start_fresh_says_so_while_it_works(daemon, capsys):
    import threading
    main = daemon._main
    main.session_id = "s-main"
    stop = threading.Event()
    main.thread = threading.Thread(target=stop.wait)
    main.thread.start()
    try:
        daemon.apply_chat_command("chat-new main")
        assert main.session_id == "s-main"
        assert "is working" in capsys.readouterr().out
    finally:
        stop.set()
        main.thread.join()


# --- three places per key -----------------------------------------------------------------------

def test_three_places_per_key():
    from runtime import DEFAULTS
    manifest = json.loads((ROOT / "manifest.json").read_text())["barWidget"]
    schema = {x["key"]: x for x in manifest["schema"]}
    assert DEFAULTS["mainResume"] is True and manifest["defaults"]["mainResume"] is True
    assert schema["mainResume"]["type"] == "bool"
    assert DEFAULTS["mainIdleTimeoutS"] == 90 == manifest["defaults"]["mainIdleTimeoutS"]
    t = schema["mainIdleTimeoutS"]
    assert (t["type"], t["min"], t["max"], t["defaultValue"]) == ("integer", 30, 600, 90)
    assert DEFAULTS["mainExtraArgs"] == [] == manifest["defaults"]["mainExtraArgs"]
    assert "mainExtraArgs" not in schema           # a list: defaults only
    page = (ROOT / "pages/AgentDetailsPage.qml").read_text()
    for key in ("mainResume", "mainIdleTimeoutS", "mainExtraArgs"):
        assert f's.put("{key}"' in page


def test_the_page_checks_flags_with_the_launch_judge_and_keeps_values_off_argv():
    """One list: the page asks `agents flags check`, the adapter's own judge,
    and holds no copy of its own. A value goes on stdin, as one JSON line,
    and is forgotten once written."""
    from qml_scan import scan
    src = scan(ROOT / "pages/AgentDetailsPage.qml").nocomment
    assert '["agentvoice", "agents", "flags", "check", page.program]' in src
    for name in ("dangerously-skip-permissions", "strict-mcp-config", "append-system-prompt"):
        assert name not in src, name
    at = src.index("function setEnv(")
    body = src[at:src.index("\n  }", at)]
    assert '"set", name, "--line"]' in body and "JSON.stringify(value)" in body
    command = body[body.index("["):body.index("]") + 1]
    assert "value" not in command
    assert 'write(envChanger.pending); envChanger.pending = ""' in src
    sub = src[src.index("function submitEnv("):]
    sub = sub[:sub.index("\n  }")]
    assert 'envValueField.text = ""' in sub
    assert "password: true" in src
