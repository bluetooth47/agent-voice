"""Try it (master plan M6, item 10): one sentence in an agent's voice from a
quiet side turn on the draft personality.

What is held here:

- refused with the reason while locked, lent out, busy, unknown, with no
  program, or inside 10 s of the last try -- and nothing is built or sent;
- the side turn is the safe one: lowest level, no tools Agent Voice adds,
  `no_tools`, no session kept, the draft in place of the saved text;
- the draft and the reply never reach argv or the journal;
- the CLI and the daemon agree on the files between them.
"""
from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import threading
import time
from pathlib import Path

import pytest

import try_it
from adapters.base import Chunk
from adapters.claude_code import ClaudeCode

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "bin/agentvoice"

DRAFT = "Personality canary: QUOKKA-7731 speaks like a lighthouse keeper."
INSTR = "Instructions canary: WOMBAT-2209 always counts in base twelve."


@pytest.fixture(autouse=True)
def unlocked(monkeypatch):
    """The lock asked afresh by handle_try: unlocked unless a test says."""
    import wake_listen
    state = {"now": False}
    monkeypatch.setattr(wake_listen, "session_locked", lambda: state["now"])
    return state


@pytest.fixture
def rundir(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "RUNTIME_DIR", tmp_path / "agentvoice")
    return tmp_path / "agentvoice"


def ok(**kw):
    base = dict(locked=False, yielded=False, known=True, label="Sora", has_program=True,
                target_busy=False, other_busy=False, since_last=1e9)
    return try_it.refusal(**{**base, **kw})


# --- the decision ---------------------------------------------------------------------

def test_a_free_agent_may_try():
    assert ok() == ""


@pytest.mark.parametrize("kw,words", [
    ({"locked": True}, "the screen is locked"),
    ({"yielded": True}, "lent to a call"),
    ({"stale": True}, "waited too long"),
    ({"known": False}, "not running here"),
    ({"has_program": False, "problem": "codex is not installed"}, "no program to run on: codex is not installed"),
    ({"target_busy": True}, "Sora is busy"),
    ({"other_busy": True}, "another agent is answering"),
    ({"since_last": 3.2}, "wait 7 more"),
])
def test_each_refusal_says_why(kw, words):
    assert words in ok(**kw)


def test_cannot_tell_whether_locked_is_a_refusal():
    assert "cannot tell whether the screen is locked" in ok(locked=None)


def test_a_lock_outranks_everything_else():
    assert ok(locked=True, target_busy=True, since_last=0, known=False) == "the screen is locked"


def test_the_limit_is_ten_seconds():
    assert try_it.MIN_GAP_S == 10.0
    assert ok(since_last=9.99) != "" and ok(since_last=10.0) == ""


# --- the request -----------------------------------------------------------------------

def test_a_request_is_cleaned_and_cut_to_the_files_budgets():
    raw = json.dumps({"agent": "sora", "personality": "<!-- c -->\n" + "p" * 1600,
                      "instructions": "\ti" * 1500}).encode()
    req = try_it.parse_request(raw)
    assert req["agent"] == "sora"
    assert req["personality"] == "p" * 1500
    assert 1999 <= len(req["instructions"]) <= 2000 and "\t" not in req["instructions"]


def test_absent_draft_fields_mean_the_saved_text():
    assert try_it.parse_request(b'{"agent": "main"}') == {
        "agent": "main", "personality": None, "instructions": None}


@pytest.mark.parametrize("raw", [b"", b"not json", b"[1]", b'{"agent": "../x"}', b'{"agent": 3}',
                                 b"\xff\xfe"])
def test_a_bad_request_is_none(raw):
    assert try_it.parse_request(raw) is None


def test_take_reads_deletes_and_marks_a_stale_request(rundir):
    folder = rundir / "try"
    folder.mkdir(parents=True)
    now = time.time()
    fresh = f"{int(now * 1e9)}-1"
    old = f"{int((now - 60) * 1e9)}-2"
    (folder / f"{old}.req").write_text('{"agent": "main"}')
    (folder / f"{fresh}.req").write_text('{"agent": "sora"}')
    (folder / "junk.req").write_text('{"agent": "main"}')
    rid, req = try_it.take(now)
    assert rid == old and req["stale"] is True
    rid, req = try_it.take(now)
    assert rid == fresh and req["stale"] is False and req["agent"] == "sora"
    assert try_it.take(now) is None
    assert sorted(p.name for p in folder.iterdir()) == []


def test_answers_are_private_and_old_ones_are_cleared(rundir):
    try_it.answer("1700000000000000000-1", "refused", "why")
    path = rundir / "try" / "1700000000000000000-1.status"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert json.loads(path.read_text()) == {"state": "refused", "why": "why", "text": ""}
    os.utime(path, (time.time() - 400, time.time() - 400))
    try_it.take()
    assert not path.exists()
    try_it.answer("../../etc/x", "said")            # not an id: nothing written
    assert [p.name for p in (rundir / "try").iterdir()] == []


def test_first_sentence_stops_at_the_first_and_caps_it():
    chunks = iter([Chunk(text="Hello there, I am Sora. "), Chunk(text="And this is more.")])
    assert try_it.first_sentence(chunks) == "Hello there, I am Sora."
    # The shared splitter merges short sentences; one is wanted here.
    assert try_it.first_sentence(iter([Chunk(text="Hi! How are you? Fine.")])) == "Hi!"
    assert try_it.first_sentence(iter([Chunk(text="Meet J. Smith, the keeper.")])) == \
        "Meet J. Smith, the keeper."
    assert len(try_it.first_sentence(iter([Chunk(text="x" * 900)]))) == try_it.SENTENCE_MAX
    assert try_it.first_sentence(iter([Chunk(error="boom")])) == ""


# --- the CLI's half --------------------------------------------------------------------

def _client(stdin: bytes, daemon_side, rundir):
    out, err = io.StringIO(), io.StringIO()
    t = threading.Thread(target=daemon_side, daemon=True)
    t.start()
    code = try_it.client("sora", stdin=io.BytesIO(stdin), out=out, err=err)
    t.join(5)
    return code, out.getvalue(), err.getvalue()


def _serve(rundir, *states):
    def side():
        for _ in range(100):
            got = try_it.take()
            if got:
                rid, req = got
                assert req["personality"] == DRAFT
                for st in states:
                    try_it.answer(rid, *st)
                    time.sleep(0.15)
                return
            time.sleep(0.05)
    return side


def test_the_client_hands_the_draft_over_and_prints_what_was_said(rundir):
    code, out, err = _client(json.dumps({"personality": DRAFT}).encode() + b"\n",
                             _serve(rundir, ("accepted",), ("said", "", "Ahoy, keeper here.")), rundir)
    assert (code, out.strip(), err) == (0, "Ahoy, keeper here.", "")
    assert list((rundir / "try").iterdir()) == [], "the client cleans up after itself"


def test_the_client_says_why_it_was_refused(rundir):
    code, out, err = _client(json.dumps({"personality": DRAFT}).encode(),
                             _serve(rundir, ("refused", "Sora is busy; try again")), rundir)
    assert code == 1 and out == "" and "Sora is busy" in err


def test_a_request_nobody_picks_up_is_taken_back(rundir, monkeypatch):
    monkeypatch.setattr(try_it, "PICKUP_S", 0.3)
    code, _, err = _client(b'{"personality": "x"}', lambda: None, rundir)
    assert code == 1 and "did not pick it up" in err
    assert list((rundir / "try").iterdir()) == []


def test_the_client_refuses_a_bad_draft_without_writing(rundir):
    for raw in (b"nope", b"[1]"):
        code, _, err = _client(raw, lambda: None, rundir)
        assert code == 2 and err
    assert not (rundir / "try").exists()


def test_the_cli_refuses_when_the_service_is_off_or_locked(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "systemctl").write_text("#!/bin/sh\nexit 3\n")
    (bin_dir / "systemctl").chmod(0o755)
    env = {**os.environ, "XDG_RUNTIME_DIR": str(tmp_path), "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    run = lambda *a: subprocess.run(["bash", str(CLI), "try", *a], input="{}", capture_output=True,  # noqa: E731
                                    text=True, env=env, timeout=20)
    off = run("sora")
    assert off.returncode == 1 and "Agent Voice is off" in off.stderr
    assert run("../x").returncode == 2
    (bin_dir / "systemctl").write_text("#!/bin/sh\nexit 0\n")
    (tmp_path / "agentvoice").mkdir()
    (tmp_path / "agentvoice" / "state").write_text('{"state": "locked"}')
    locked = run("sora")
    assert locked.returncode == 1 and "locked" in locked.stderr
    assert not (tmp_path / "agentvoice" / "try").exists()


# --- the daemon's half -----------------------------------------------------------------

def test_first_sentence_is_returned_as_soon_as_it_ends():
    """Codex review of M6, pass 2: "Hi! " then a stall was held for a second
    sentence until the turn timed out."""
    pulled = []

    def stream():
        yield Chunk(text="Hi! ")
        pulled.append("more")               # must never be reached
        yield Chunk(text="How are you?")
    assert try_it.first_sentence(stream()) == "Hi!"
    assert pulled == []
    assert try_it.first_sentence(iter([Chunk(text="Let me look"), Chunk(tool="Read"),
                                       Chunk(text=" at that.")])) == "Let me look"


@pytest.mark.parametrize("program,endpoint,agent,ok_", [
    ("claude", False, False, True), ("", True, False, True), ("", True, True, False),
    ("codex", False, False, False), ("gemini", False, False, False),
    ("antigravity", False, False, False), ("copilot", False, False, False),
])
def test_only_backends_that_can_start_with_no_tools_may_try(program, endpoint, agent, ok_):
    assert (try_it.backend_refusal(program, endpoint, agent) == "") is ok_


class Side:
    """A side turn that records what it was given and answers."""

    name = "claude"

    def __init__(self, reply="Ahoy there, I keep the lighthouse and I will keep you right. "
                             "More words after."):
        self.reply, self.sent, self.cancelled = reply, [], 0

    def send(self, text, session_id=None):
        self.sent.append((text, session_id))
        yield Chunk(text=self.reply)

    def cancel(self):
        self.cancelled += 1


def _answers(rundir, rid):
    p = rundir / "try" / f"{rid}.status"
    return json.loads(p.read_text()) if p.exists() else None


RID = "1700000000000000000-1"


def _req(**kw):
    return {"agent": "main", "personality": DRAFT, "instructions": INSTR, "stale": False, **kw}


def test_a_try_runs_the_side_turn_and_says_one_sentence(daemon, rundir, monkeypatch, capsys):
    side = Side()
    built = []
    monkeypatch.setattr(daemon, "try_adapter", lambda p, req: built.append(req) or side)
    daemon.enabled = False                       # muted: Try it still speaks
    daemon.handle_try(RID, _req())
    assert built and side.sent == [(try_it.PROMPT, None)]
    assert side.cancelled >= 1, "thrown away afterwards"
    said = "Ahoy there, I keep the lighthouse and I will keep you right."
    assert daemon.speaker.said == [said]
    assert _answers(rundir, RID) == {"state": "said", "why": "", "text": said}
    out = capsys.readouterr()
    for secret in ("Ahoy", "QUOKKA", "WOMBAT"):
        assert secret not in out.out + out.err, "the journal gets no words"


def _working(d):
    """The main agent mid-turn: a live turn thread is what `busy` reads."""
    d._stop_work = threading.Event()
    d._main.thread = threading.Thread(target=d._stop_work.wait, daemon=True)
    d._main.thread.start()


@pytest.mark.parametrize("setup,words", [
    (lambda d: setattr(d, "locked", True), "locked"),
    (lambda d: setattr(d, "yielded", True), "lent"),
    (_working, "busy"),
])
def test_a_refused_try_builds_and_sends_nothing(daemon, rundir, monkeypatch, setup, words):
    built = []
    monkeypatch.setattr(daemon, "try_adapter", lambda p, req: built.append(1) or Side())
    setup(daemon)
    try:
        daemon.handle_try(RID, _req())
    finally:
        daemon.locked = daemon.yielded = False
        if getattr(daemon, "_stop_work", None):
            daemon._stop_work.set()
            daemon._main.thread.join(2)
    assert built == [] and daemon.speaker.said == []
    got = _answers(rundir, RID)
    assert got["state"] == "refused" and words in got["why"]


def test_a_second_try_inside_ten_seconds_is_refused(daemon, rundir, monkeypatch):
    monkeypatch.setattr(daemon, "try_adapter", lambda p, req: Side())
    daemon.handle_try(RID, _req())
    daemon.handle_try("1700000000000000000-2", _req())
    assert _answers(rundir, "1700000000000000000-2")["state"] == "refused"
    assert "one try every 10 seconds" in _answers(rundir, "1700000000000000000-2")["why"]
    assert len(daemon.speaker.said) == 1


def test_an_unknown_agent_and_a_stale_request_are_refused(daemon, rundir):
    daemon.handle_try(RID, _req(agent="nobody"))
    assert "not running here" in _answers(rundir, RID)["why"]
    daemon.handle_try(RID, _req(stale=True))
    assert "waited too long" in _answers(rundir, RID)["why"]
    daemon.handle_try(RID, None)
    assert _answers(rundir, RID)["state"] == "refused"


def test_a_lock_landing_before_the_sentence_stops_it(daemon, rundir, monkeypatch):
    class Locking(Side):
        def send(self, text, session_id=None):
            daemon.locked = True                # the screen locked mid-turn
            yield Chunk(text="This must not be heard. ")
    monkeypatch.setattr(daemon, "try_adapter", lambda p, req: Locking())
    monkeypatch.setattr(daemon, "reconcile_lock", lambda: None)
    try:
        daemon.handle_try(RID, _req())
    finally:
        daemon.locked = False
    assert daemon.speaker.said == []
    assert _answers(rundir, RID) == {"state": "failed", "why": "the screen locked", "text": ""}


def test_a_lock_that_cannot_be_told_refuses_before_and_stays_silent_after(daemon, rundir, monkeypatch,
                                                                         unlocked):
    built = []
    monkeypatch.setattr(daemon, "try_adapter", lambda p, req: built.append(1) or Side())
    unlocked["now"] = None
    daemon.handle_try(RID, _req())
    assert built == [] and "cannot tell" in _answers(rundir, RID)["why"]

    class Unsure(Side):
        def send(self, text, session_id=None):
            unlocked["now"] = None              # the probe stops answering mid-turn
            yield Chunk(text="This must not be heard either, not even once. ")
    unlocked["now"] = False
    monkeypatch.setattr(daemon, "try_adapter", lambda p, req: Unsure())
    daemon.handle_try(RID, _req())
    assert daemon.speaker.said == [] and _answers(rundir, RID)["state"] == "failed"


def test_a_backend_that_cannot_start_with_no_tools_is_refused(daemon, rundir, monkeypatch):
    class Codex(Side):
        name = "codex"
    side = Codex()
    monkeypatch.setattr(daemon, "try_adapter", lambda p, req: side)
    daemon.handle_try(RID, _req())
    got = _answers(rundir, RID)
    assert got["state"] == "refused" and "Claude Code" in got["why"]
    assert side.sent == [] and daemon.speaker.said == []


def test_the_process_is_cancelled_before_the_stream_is_closed(daemon, rundir, monkeypatch):
    """Codex review of M6: a stream dropped as soon as the first sentence
    was out ran its own cleanup first, before cancel() could reach the
    process it held."""
    order = []

    class Held(Side):
        def send(self, text, session_id=None):
            try:
                yield Chunk(text="A first sentence that is long enough. ")
                yield Chunk(text="And a second one, never read.")
            finally:
                order.append("closed")

        def cancel(self):
            order.append("cancelled")
    monkeypatch.setattr(daemon, "try_adapter", lambda p, req: Held())
    daemon.handle_try(RID, _req())
    assert order[:2] == ["cancelled", "closed"]


def test_no_answer_is_a_failure_not_a_silence(daemon, rundir, monkeypatch):
    monkeypatch.setattr(daemon, "try_adapter", lambda p, req: Side(reply=""))
    daemon.handle_try(RID, _req())
    assert _answers(rundir, RID)["state"] == "failed" and daemon.speaker.said == []


def test_the_side_adapter_is_built_safe_with_the_draft(daemon, monkeypatch):
    import wake_listen
    got = {}

    def fake_load(**kw):
        got.update(kw)
        a = ClaudeCode(ask_permission=kw["ask_permission"], named=kw.get("named", ""))
        a.instructions = kw["instructions"]
        return a
    monkeypatch.setattr(wake_listen, "load_adapter", fake_load)
    have = daemon._main.agent
    have.name = "claude"
    have.instructions = "SAVED instructions"
    have.parts = {"personality": "SAVED personality", "rules": "r", "skills": "an index", "roster": []}
    side = daemon.try_adapter(daemon._main, _req())
    assert got["level"] == "ask" and got["ask_permission"] is True and got["spoken"] is True
    assert side.no_tools and side.ephemeral
    assert not side.desktop_tools and not side.browser_tools and not side.crew_tools
    assert side.skill_dir is None and side.skill_text == ""
    assert side.parts["personality"] == DRAFT and side.parts["skills"] == ""
    assert side.instructions == INSTR and side.parts["rules"] == "r"
    # Absent from the request: the saved text.
    side = daemon.try_adapter(daemon._main, _req(personality=None, instructions=None))
    assert side.parts["personality"] == "SAVED personality" and side.instructions == "SAVED instructions"


def test_claude_with_no_tools_gets_none_and_the_draft_stays_out_of_argv(rundir):
    side = ClaudeCode(ask_permission=True)
    side.no_tools = side.ephemeral = True
    side.desktop_tools = side.crew_tools = side.browser_tools = True     # even if left on
    side.skill_dir = "/somewhere"
    side.parts = {"personality": DRAFT}
    side.instructions = INSTR
    argv = side._argv(try_it.PROMPT, None)
    i = argv.index("--tools")
    assert argv[i + 1] == "" and "--strict-mcp-config" in argv
    assert "--mcp-config" not in argv and "--plugin-dir" not in argv
    assert "--no-chrome" in argv and "--chrome" not in argv
    assert "--no-session-persistence" in argv
    joined = "\0".join(argv)
    for secret in ("QUOKKA", "WOMBAT", try_it.PROMPT):
        assert secret not in joined
    # The draft is in the private prompt file instead.
    path = Path(argv[argv.index("--append-system-prompt-file") + 1])
    assert "QUOKKA" in path.read_text() and "WOMBAT" in path.read_text()


def test_an_ordinary_claude_turn_is_unchanged_by_no_tools():
    argv = ClaudeCode(ask_permission=True)._argv("x", None)
    assert "--tools" not in argv and "--strict-mcp-config" not in argv


def test_the_run_loop_takes_a_try_only_between_captures():
    src = (ROOT / "daemon" / "wake_listen.py").read_text()
    loop = src[src.index("def run(self, device"):]
    wake = loop[loop.index('if phase == "wake":'):]
    wake = wake[:wake.index("self.collab.tick()")]
    assert "trial = self.take_try()" in wake and "self.handle_try(*trial)" in wake


def test_a_recorded_real_turn_proves_the_no_tools_flags():
    """Flags read off --help are a hypothesis (CLAUDE.md). One real turn
    with these flags was recorded: Claude reported no tools and no MCP
    servers at start, and asked to list files with a tool, used none. The
    argv built today must still carry every flag that turn ran with."""
    rec = json.loads((ROOT / "tests" / "fixtures" / "try" / "claude-no-tools.json").read_text())
    assert rec["init"]["tools"] == [] and rec["init"]["mcp_servers"] == []
    assert rec["tool_uses"] == [] and rec["result"]["is_error"] is False
    side = ClaudeCode(ask_permission=True)
    side.no_tools = side.ephemeral = True
    argv = side._argv("", None)
    flags = rec["flags"]
    i = argv.index(flags[0])
    assert argv[i:i + 3] == flags[:3]
    for f in flags[3:]:
        assert f in argv
