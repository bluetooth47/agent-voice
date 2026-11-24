"""What a warm `claude -p` says between turns (master plan M27, tier 2).

The spike, recorded in tests/fixtures/background/ against Claude Code
2.1.330: a background command (`sleep 20; echo done-alpha`) and a background
sub-agent, each started by a turn that then ended. When each finished, the
process wrote `task_notification` and then took a whole turn by itself --
`init`, its own words, its own `result` -- with nothing written to stdin.
And when a turn was written the moment a notification arrived, the CLI
answered the notification first and the turn after it, two results in that
order (claude-race.json).

Before M27 nothing read stdout between turns, so that unprompted turn sat in
the pipe and the next turn's reading took its `result` for its own: the
person heard "the background command finished" as the answer to whatever
they asked next, and the real answer one turn late. These replay the
recordings through the real adapter (its pump thread, its turn queue, the
echo `--replay-user-messages` gives each turn) and pin both halves: every
turn gets its own reply, and each finished task is handed to the daemon
exactly once, with the words the CLI wrote -- and nothing else is.
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

import pytest

import adapters.claude_code as cc
from adapters.claude_code import Between, ClaudeCode, Pump, is_echo

FIX = Path(__file__).parent / "fixtures" / "background"


def fixture(name):
    return json.loads((FIX / f"claude-{name}.json").read_text())


def _until(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


# --- a claude whose stdout the test writes, line by line ---------------------

class Out:
    """stdout: readline blocks until the test pushes a line; None ends it."""

    def __init__(self):
        self.q: queue.Queue = queue.Queue()

    def readline(self):
        try:
            got = self.q.get(timeout=10)
        except queue.Empty:
            return ""
        return "" if got is None else got

    def push(self, lines):
        for line in lines:
            self.q.put(json.dumps(line) + "\n")

    def close(self):
        self.q.put(None)


class In:
    def __init__(self, on_write):
        self.on_write, self.writes = on_write, []

    def write(self, s):
        self.writes.append(s)
        self.on_write(len(self.writes))

    def flush(self):
        pass


class Proc:
    """A claude that writes `script[n]` when it is handed its n-th turn."""

    def __init__(self, script=None):
        self.script = script or {}
        self.stdout = Out()
        self.stdin = In(lambda n: self.stdout.push(self.script.get(n, [])))
        self.stderr = None
        self.pid = 2 ** 22 + 7          # nobody's: stop_tree's kill finds no one
        self.code = None

    def poll(self):
        return self.code

    def wait(self, timeout=None):
        return self.code or 0


@pytest.fixture
def make(monkeypatch):
    """A ClaudeCode whose every spawn is the given Proc, and what it hands
    the daemon."""
    monkeypatch.setattr(cc, "Drain", lambda *a, **k: None)
    made = []

    def build(proc, **kw):
        monkeypatch.setattr(cc.subprocess, "Popen", lambda *a, **k: proc)
        kw.setdefault("cwd", "/tmp")
        kw.setdefault("keep_warm_s", 0)
        a = ClaudeCode(**kw)
        a._launched = lambda *x: None
        a.handed = []
        a.on_unprompted = a.handed.append
        made.append((a, proc))
        return a
    yield build
    for a, proc in made:
        a._forget()
        proc.stdout.close()


def turn(agent, text, session=None):
    chunks = list(agent.send(text, session))
    said = "".join(c.text for c in chunks).strip()
    sid = next((c.session_id for c in reversed(chunks) if c.session_id), None)
    errors = [c.error for c in chunks if c.error]
    return said, sid, errors


def phases(name):
    lines = fixture(name)["lines"]
    get = lambda ph: [r["line"] for r in lines if r["phase"] == ph and r["line"]["type"] != "WROTE"]
    return get("turn1"), get("between"), get("turn2")


# --- the recordings themselves -------------------------------------------------

@pytest.mark.parametrize("name", ["bash", "agent"])
def test_the_recording_shows_a_turn_taken_by_itself(name):
    """What the design rests on, read straight off the recording: after the
    first turn's result, with nothing written, a finish and then a whole
    turn of the CLI's own."""
    _, between, _ = phases(name)
    kinds = [(l["type"], l.get("subtype")) for l in between]
    note = kinds.index(("system", "task_notification"))
    assert ("system", "init") in kinds[note:]
    assert ("result", "success") in kinds[note:]
    assert not any(is_echo(l) for l in between), "nobody wrote to it"


def test_the_race_was_answered_notification_first():
    """Written the moment the notification was read, the turn came second:
    the first result after the write is the CLI's own turn, not ours."""
    lines = fixture("race")["lines"]
    wrote = next(i for i, r in enumerate(lines) if r["line"]["type"] == "WROTE"
                 and r["line"]["subtype"] == "race")
    after = [r["line"] for r in lines[wrote + 1:]]
    results = [l for l in after if l["type"] == "result"]
    assert len(results) == 2
    echo = next(i for i, l in enumerate(after) if is_echo(l))
    first = after.index(results[0])
    assert first < echo, "the unprompted turn ended before ours began"
    assert results[1]["result"] == "NEXT"


def test_the_flags_ask_for_the_echo_every_turn_and_the_recording_has_it():
    argv = ClaudeCode(ask_permission=True)._argv("", None)
    assert "--replay-user-messages" in argv
    assert "--replay-user-messages" in fixture("race")["argv"]
    turn1, _, _ = phases("race")
    echo = [l for l in turn1 if is_echo(l)]
    assert len(echo) == 1 and isinstance(echo[0]["message"]["content"], str)


# --- replayed through the adapter --------------------------------------------------

@pytest.mark.parametrize("name, task, words", [
    ("bash", "bxadt98tg", "The background command finished"),
    ("agent", "ae09ac1d04145970a", "The background sub-agent finished"),
])
def test_each_turn_gets_its_own_reply_and_the_finish_is_handed_on_once(make, name, task, words):
    turn1, between, turn2 = phases(name)
    proc = Proc({1: turn1, 2: turn2})
    a = make(proc)
    said, sid, errors = turn(a, "start it")
    assert (said, errors) == ("STARTED", [])
    assert a.background_running(), "a background task is still running"
    proc.stdout.push(between)
    assert _until(lambda: a.handed)
    said2, _, errors = turn(a, "next", sid)
    assert (said2, errors) == ("NEXT", []), "the next turn got the background report"
    assert len(a.handed) == 1
    got = a.handed[0]
    assert got.tasks == ((task, "completed"),) and not got.failed
    assert got.text.startswith(words)
    assert got.session == sid
    assert not a.background_running()


def test_the_next_turn_is_its_own_even_when_the_report_waited_in_the_pipe(make):
    """The bug M27 found: everything the CLI wrote between the turns is
    already there when the next turn is written -- as it was, unread, before
    M27 -- and the next turn still answers with its own words."""
    turn1, between, turn2 = phases("bash")
    proc = Proc({1: turn1, 2: between + turn2})
    a = make(proc)
    _, sid, _ = turn(a, "start it")
    said, _, errors = turn(a, "next", sid)
    assert (said, errors) == ("NEXT", [])
    assert _until(lambda: a.handed)
    assert a.handed[0].text.startswith("The background command finished")


@pytest.mark.parametrize("pump_saw_the_notification", [False, True])
def test_the_race_gives_each_turn_its_own_result(make, pump_saw_the_notification):
    """A turn written as a finish arrives: the CLI's own turn comes first,
    and this turn's reading must neither stop at its result nor say it."""
    turn1, between, _ = phases("race")
    note = next(i for i, l in enumerate(between) if l.get("subtype") == "task_notification") + 1
    early, rest = (between[:note], between[note:]) if pump_saw_the_notification else ([], between)
    proc = Proc({1: turn1, 2: rest})
    a = make(proc)
    _, sid, _ = turn(a, "start it")
    proc.stdout.push(early)
    if early:
        assert _until(lambda: a._bg.finished)
    said, _, errors = turn(a, "Reply with the single word NEXT.", sid)
    assert (said, errors) == ("NEXT", [])
    assert _until(lambda: a.handed)
    assert len(a.handed) == 1
    assert a.handed[0].text.startswith("The background command (`sleep 15; echo done-charlie`)")
    assert "NEXT" not in a.handed[0].text


def test_a_turn_the_cli_takes_with_no_finish_before_it_is_not_handed_on(make):
    """A model writing "done" is text, not an event: an unprompted turn with
    no task_notification of ours before it is read off the stream (so it
    never lands in a reply) and dropped."""
    turn1, between, turn2 = phases("bash")
    note = next(i for i, l in enumerate(between) if l.get("subtype") == "task_notification")
    forged = [l for l in between[note + 1:]
              if l.get("subtype") not in ("background_tasks_changed",)]
    proc = Proc({1: turn1, 2: turn2})
    a = make(proc)
    _, sid, _ = turn(a, "start it")
    proc.stdout.push(forged)
    time.sleep(0.3)
    said, _, _ = turn(a, "next", sid)
    assert said == "NEXT"
    assert a.handed == []


def test_a_notification_for_a_task_it_never_started_is_not_a_finish():
    bg = Between()
    bg.track({"type": "system", "subtype": "task_notification", "task_id": "zzz",
              "status": "completed"})
    assert not bg.finished and not bg.foreign


def test_a_helpers_own_command_finishing_is_not_a_finish():
    """In the sub-agent recording the helper ran its own (foreground) Bash,
    which has a notification of its own: only the helper's finish counts."""
    _, between, _ = phases("agent")
    turn1, _, _ = phases("agent")
    bg = Between()
    for line in turn1:
        bg.track(line)
    notes = []
    for line in between:
        bg.track(line)
        if line.get("subtype") == "task_notification":
            notes.append(list(bg.finished))
    assert len(notes) == 2
    assert notes[0] == [], "the helper's own command"
    assert [f[0] for f in notes[1]] == ["ae09ac1d04145970a"]


def test_the_same_finish_reported_twice_is_one_finish():
    bg = Between()
    start = {"type": "system", "subtype": "task_started", "task_id": "b1",
             "is_backgrounded": True}
    done = {"type": "system", "subtype": "task_notification", "task_id": "b1",
            "status": "completed"}
    for line in (start, done, done):
        bg.track(line)
    assert len(bg.finished) == 1


@pytest.mark.parametrize("status, finished", [("completed", 1), ("failed", 1),
                                              ("killed", 0), ("stopped", 0)])
def test_only_a_completion_or_a_failure_is_announced(status, finished):
    bg = Between()
    bg.track({"type": "system", "subtype": "task_started", "task_id": "b1",
              "is_backgrounded": True})
    bg.track({"type": "system", "subtype": "task_notification", "task_id": "b1",
              "status": status})
    assert len(bg.finished) == finished
    assert not bg.outstanding


def test_a_foreground_command_is_not_background_work():
    bg = Between()
    bg.track({"type": "system", "subtype": "task_started", "task_id": "f1",
              "is_backgrounded": False})
    bg.track({"type": "system", "subtype": "task_started", "task_id": "h1",
              "is_backgrounded": True, "owned_by_subagent": True})
    assert not bg.outstanding


def test_a_command_moved_to_the_background_later_counts():
    bg = Between()
    bg.track({"type": "system", "subtype": "task_started", "task_id": "f1",
              "is_backgrounded": False})
    bg.track({"type": "system", "subtype": "task_updated", "task_id": "f1",
              "patch": {"is_backgrounded": True}})
    assert bg.outstanding


def test_only_top_level_words_are_kept_and_thinking_never():
    bg = Between()
    bg.track({"type": "system", "subtype": "task_started", "task_id": "b1", "is_backgrounded": True})
    bg.track({"type": "system", "subtype": "task_notification", "task_id": "b1", "status": "completed"})
    for line in ({"type": "system", "subtype": "init"},
                 {"type": "assistant", "parent_tool_use_id": "toolu_x",
                  "message": {"content": [{"type": "text", "text": "HELPER"}]}},
                 {"type": "assistant", "message": {"content": [
                     {"type": "thinking", "thinking": "THOUGHT"},
                     {"type": "text", "text": "Done, all good."}]}}):
        assert bg.feed(line) is None
    got = bg.feed({"type": "result", "subtype": "success", "session_id": "s"})
    assert got.text == "Done, all good." and got.tasks == (("b1", "completed"),)


def test_a_failed_unprompted_turn_is_a_failure():
    bg = Between()
    bg.track({"type": "system", "subtype": "task_started", "task_id": "b1", "is_backgrounded": True})
    bg.track({"type": "system", "subtype": "task_notification", "task_id": "b1", "status": "completed"})
    got = bg.feed({"type": "result", "subtype": "error_during_execution", "is_error": True})
    assert got.failed


# --- the grace: a finish whose own turn never comes --------------------------------

def _finished(bg, during_turn):
    bg.track({"type": "system", "subtype": "task_started", "task_id": "b1", "is_backgrounded": True})
    bg.track({"type": "system", "subtype": "task_notification", "task_id": "b1", "status": "completed"})
    if during_turn:
        bg.turn_began()


def test_a_finish_read_between_turns_with_no_turn_after_it_is_said_without_words():
    bg = Between()
    _finished(bg, during_turn=False)
    at = bg.finished[0][2]
    assert bg.settle(at + 1.0) is None                      # still within the grace
    got = bg.settle(at + cc.UNPROMPTED_GRACE_S)
    assert got is not None and got.text == "" and got.tasks == (("b1", "completed"),)
    assert not bg.finished


def test_a_finish_a_turn_of_ours_began_on_was_answered_there():
    bg = Between()
    _finished(bg, during_turn=True)
    assert bg.settle(bg.finished[0][2] + cc.UNPROMPTED_GRACE_S) is None
    assert not bg.finished


def test_a_new_turn_forgets_finishes_an_earlier_turn_answered():
    bg = Between()
    _finished(bg, during_turn=True)
    pump = Pump(Proc(), bg, lambda u: None)
    pump.thread = threading.current_thread()        # never start a reader here
    pump.begin()
    assert not bg.finished and not bg.foreign


def test_settle_waits_while_a_turn_is_registered():
    handed = []
    bg = Between()
    _finished(bg, during_turn=False)
    pump = Pump(Proc(), bg, handed.append)
    pump.turn = queue.Queue()
    pump.settle(now=time.time() + 60)
    assert handed == [] and bg.finished


# --- the process, kept for its work ---------------------------------------------------

def test_background_work_keeps_the_idle_process_past_the_warm_time(make, monkeypatch):
    turn1, _, _ = phases("bash")
    proc = Proc({1: turn1})
    a = make(proc, keep_warm_s=300)
    turn(a, "start it")
    assert a._bg.outstanding
    stopped = []
    monkeypatch.setattr(cc, "stop_tree", lambda p, sig=None: stopped.append(p))
    a._expire(proc)
    assert a._proc is proc and not stopped, "letting it go would kill the work"
    a._idle_since -= cc.BACKGROUND_KEEP_S + 1
    a._expire(proc)
    assert a._proc is None and stopped == [proc], "but not for ever"


def test_without_background_work_the_warm_time_is_as_before(make, monkeypatch):
    _, _, turn2 = phases("bash")
    proc = Proc({1: turn2})
    a = make(proc, keep_warm_s=300)
    turn(a, "hello")
    assert not a._bg.outstanding and not a.background_running()
    monkeypatch.setattr(cc, "stop_tree", lambda p, sig=None: None)
    a._expire(proc)
    assert a._proc is None


def test_nothing_is_handed_on_with_nobody_listening(make):
    turn1, between, turn2 = phases("bash")
    proc = Proc({1: turn1, 2: turn2})
    a = make(proc)
    a.on_unprompted = None
    _, sid, _ = turn(a, "start it")
    proc.stdout.push(between)
    time.sleep(0.2)
    assert turn(a, "next", sid)[0] == "NEXT"


# --- a real process and real pipes ---------------------------------------------------

FAKE = r'''#!{python}
import json, sys, threading, time
args = sys.argv[1:]
echo = "--replay-user-messages" in args
lock = threading.Lock()

def out(obj):
    with lock:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()

def finish_later(tid):
    time.sleep(0.4)
    out({{"type": "system", "subtype": "task_notification", "task_id": tid, "status": "completed"}})
    out({{"type": "system", "subtype": "background_tasks_changed", "tasks": []}})
    out({{"type": "system", "subtype": "init", "session_id": "s1"}})
    out({{"type": "assistant", "message": {{"content": [{{"type": "text",
         "text": "Your background job finished."}}]}}}})
    out({{"type": "result", "subtype": "success", "session_id": "s1"}})

for line in sys.stdin:
    text = json.loads(line)["message"]["content"]
    out({{"type": "system", "subtype": "init", "session_id": "s1"}})
    if echo:
        out({{"type": "user", "isReplay": True, "message": {{"role": "user", "content": text}}}})
    if text == "background":
        out({{"type": "system", "subtype": "task_started", "task_id": "bj1", "is_backgrounded": True}})
        out({{"type": "system", "subtype": "background_tasks_changed", "tasks": [{{"task_id": "bj1"}}]}})
        threading.Thread(target=finish_later, args=("bj1",)).start()
    out({{"type": "stream_event", "event": {{"type": "content_block_delta",
         "delta": {{"type": "text_delta", "text": "heard " + text}}}}}})
    out({{"type": "result", "subtype": "success", "session_id": "s1"}})
'''


@pytest.fixture
def real_claude(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe = bin_dir / "claude"
    exe.write_text(FAKE.format(python=sys.executable))
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    made = []

    def build():
        a = ClaudeCode(cwd=str(tmp_path), ask_permission=False)
        a.handed = []
        a.on_unprompted = a.handed.append
        made.append(a)
        return a
    yield build
    for a in made:
        a.cancel()


def test_a_real_process_says_its_finish_between_turns(real_claude):
    a = real_claude()
    said, sid, errors = turn(a, "background")
    assert (said, errors) == ("heard background", [])
    assert a.background_running()
    assert _until(lambda: a.handed, timeout=5.0)
    assert a.handed[0].text == "Your background job finished."
    assert a.handed[0].tasks == (("bj1", "completed"),)
    said, _, errors = turn(a, "again", sid)
    assert (said, errors) == ("heard again", [])
    assert len(a.handed) == 1


def test_a_real_process_written_to_mid_finish_still_answers_in_order(real_claude):
    """Written while the unprompted turn may be under way: whichever comes
    first, the reply is this turn's and the finish is handed on once."""
    a = real_claude()
    _, sid, _ = turn(a, "background")
    time.sleep(0.4)
    said, _, errors = turn(a, "now", sid)
    assert (said, errors) == ("heard now", [])
    assert _until(lambda: a.handed, timeout=5.0)
    assert len(a.handed) == 1


def _bg_lines(tid="b9"):
    start = [{"type": "system", "subtype": "task_started", "task_id": tid, "is_backgrounded": True},
             {"type": "system", "subtype": "background_tasks_changed", "tasks": [{"task_id": tid}]}]
    note = [{"type": "system", "subtype": "task_notification", "task_id": tid, "status": "completed"},
            {"type": "system", "subtype": "background_tasks_changed", "tasks": []}]
    return start, note


def _turn_lines(text, echo=None, sid="s9"):
    out = [{"type": "system", "subtype": "init", "session_id": sid}]
    if echo is not None:
        out.append({"type": "user", "isReplay": True, "message": {"role": "user", "content": echo}})
    out += [{"type": "stream_event", "event": {"type": "content_block_delta",
             "delta": {"type": "text_delta", "text": text}}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}},
            {"type": "result", "subtype": "success", "session_id": sid}]
    return out


def test_a_finish_the_cli_folds_into_our_turn_is_ours(make):
    """A finish read between turns, and then the CLI answers it inside our
    turn rather than in one of its own: only the echo says these lines are
    ours. Without it this turn would be taken for the unprompted one, its
    reply handed on, and the turn left waiting for a result never coming."""
    start, note = _bg_lines()
    first = _turn_lines("STARTED", echo="go")
    first[1:1] = start
    proc = Proc({1: first, 2: _turn_lines("NEXT, and the job finished.", echo="next")})
    a = make(proc)
    _, sid, _ = turn(a, "go")
    proc.stdout.push(note)
    assert _until(lambda: a._bg.finished)
    said, _, errors = turn(a, "next", sid)
    assert (said, errors) == ("NEXT, and the job finished.", [])
    assert a.handed == [], "our own reply is not an announcement"
    # And its own turn never comes: the turn that began on it answered it.
    a._pump.settle(now=time.time() + cc.UNPROMPTED_GRACE_S + 1)
    assert a.handed == []


def test_a_turn_the_cli_takes_right_behind_ours_is_handed_on(make):
    """Its lines are already queued for our turn when our result is read:
    the pump takes them back, in order, and they are announced."""
    start, note = _bg_lines()
    first = _turn_lines("STARTED", echo="go")
    first[1:1] = start
    behind = note + _turn_lines("The job is done.")
    proc = Proc({1: first + behind, 2: _turn_lines("NEXT", echo="next")})
    a = make(proc)
    said, sid, _ = turn(a, "go")
    assert said == "STARTED"
    assert _until(lambda: a.handed)
    assert a.handed[0].text == "The job is done."
    assert turn(a, "next", sid)[0] == "NEXT"


# --- found live: the seconds between a finish and what the CLI then says --------

def test_a_finish_still_to_be_said_counts_as_background_work(make):
    """Found by the live lock check: after the finish was read nothing was
    "outstanding", so a lock in the two seconds the CLI took to say it
    stopped the process and the finish was never announced, not even as a
    notification. Until that turn's result, the process is still busy."""
    turn1, between, turn2 = phases("bash")
    proc = Proc({1: turn1, 2: turn2})
    a = make(proc)
    _, sid, _ = turn(a, "start it")
    note = next(i for i, l in enumerate(between) if l.get("subtype") == "task_notification")
    result = next(i for i, l in enumerate(between) if l["type"] == "result")
    proc.stdout.push(between[:note + 3])            # the finish and the turn's init
    assert _until(lambda: a._bg.finished and a._bg.auto)
    assert not a._bg.outstanding
    assert a.background_running(), "a lock now would lose what it is about to say"
    proc.stdout.push(between[note + 3:result + 1])
    assert _until(lambda: a.handed)
    assert not a.background_running()


def test_the_let_go_waits_for_a_finish_still_to_be_said(make, monkeypatch):
    turn1, between, _ = phases("bash")
    proc = Proc({1: turn1})
    a = make(proc, keep_warm_s=300)
    turn(a, "start it")
    note = next(i for i, l in enumerate(between) if l.get("subtype") == "task_notification")
    proc.stdout.push(between[:note + 3])
    assert _until(lambda: a._bg.auto)
    stopped = []
    monkeypatch.setattr(cc, "stop_tree", lambda p, sig=None: stopped.append(p))
    a._expire(proc)
    assert a._proc is proc and not stopped
