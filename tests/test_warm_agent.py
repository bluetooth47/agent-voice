"""One Claude Code process per conversation, not one per turn.

Measured against claude 2.1.325 with Haiku on the dev machine: a process
started for the turn reached its first word in 2.3-2.5s, one already running
in 1.3-1.4s. These drive the real adapter against a stand-in `claude` that
speaks the same stream-json protocol, so the subprocess, the pipes and the
signals are all real -- only the model is not.

What they hold it to is mostly about what must *not* survive: an
interrupted process, a process for another conversation, a process nobody
has used for minutes.
"""
from __future__ import annotations

import json
import os
import sys
import time

import pytest

from adapters.claude_code import ClaudeCode

FAKE = r'''#!{python}
import json, os, sys, time
args = sys.argv[1:]
session = args[args.index("--resume") + 1] if "--resume" in args else "s-%d" % os.getpid()
with open(os.environ["FAKE_CLAUDE_LOG"], "a") as log:
    log.write(json.dumps({{"pid": os.getpid(), "argv": args}}) + "\n")

def out(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

for line in sys.stdin:
    text = json.loads(line)["message"]["content"]
    out({{"type": "system", "subtype": "init", "session_id": session}})
    if text == "hang":
        time.sleep(60)
    out({{"type": "stream_event", "event": {{"type": "content_block_delta",
         "delta": {{"type": "text_delta", "text": "pid %d heard %s." % (os.getpid(), text)}}}}}})
    out({{"type": "result", "subtype": "success", "session_id": session}})
'''


@pytest.fixture
def claude(tmp_path, monkeypatch):
    """A stand-in `claude` first on PATH, and the log of every start."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe = bin_dir / "claude"
    exe.write_text(FAKE.format(python=sys.executable))
    exe.chmod(0o755)
    log = tmp_path / "starts.jsonl"
    log.touch()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))

    made = []

    def make(**kw):
        kw.setdefault("cwd", str(tmp_path))
        kw.setdefault("ask_permission", False)
        a = ClaudeCode(**kw)
        made.append(a)
        return a

    def starts():
        return [json.loads(line) for line in log.read_text().splitlines()]

    make.starts = starts
    yield make
    for a in made:
        a.cancel()


def turn(agent, text, session=None):
    chunks = list(agent.send(text, session))
    said = "".join(c.text for c in chunks)
    errors = [c.error for c in chunks if c.error]
    sid = next((c.session_id for c in reversed(chunks) if c.session_id), None)
    return said, sid, errors


def pid_in(said):
    return int(said.split()[1])


def gone(pid, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        # A zombie still answers kill(0); it has exited all the same.
        try:
            with open(f"/proc/{pid}/stat") as f:
                if f.read().split(")")[-1].split()[0] == "Z":
                    return True
        except OSError:
            return True
        time.sleep(0.05)
    return False


def test_two_turns_are_one_process(claude):
    agent = claude()
    first, sid, errors = turn(agent, "one")
    assert not errors and agent.last_start == "cold"
    second, _, errors = turn(agent, "two", sid)
    assert not errors
    assert pid_in(first) == pid_in(second), "the second turn started claude again"
    assert agent.last_start == "warm"
    assert len(claude.starts()) == 1


def test_prepare_makes_even_the_first_turn_warm(claude):
    """Started at the wake word, so the person's own sentence hides it."""
    agent = claude()
    agent.prepare(None)
    _, _, errors = turn(agent, "hello")
    assert not errors and agent.last_start == "warm"
    assert len(claude.starts()) == 1


def test_another_conversation_gets_its_own_process(claude):
    """A process is a conversation. Writing a turn for session B to the one
    carrying session A would answer it with the wrong history."""
    agent = claude()
    first, sid, _ = turn(agent, "one")
    other, _, _ = turn(agent, "two", "someone-elses")
    assert pid_in(first) != pid_in(other)
    assert ["--resume", "someone-elses"] == \
        claude.starts()[-1]["argv"][claude.starts()[-1]["argv"].index("--resume"):][:2]
    assert gone(pid_in(first)), "the old conversation's process was left running"


def test_a_stop_ends_the_process_and_the_next_turn_resumes(claude):
    agent = claude()
    first, sid, _ = turn(agent, "one")
    agent.cancel()
    assert gone(pid_in(first))
    again, _, errors = turn(agent, "two", sid)
    assert not errors and agent.last_start == "cold"
    assert "--resume" in claude.starts()[-1]["argv"]


def test_a_turn_abandoned_midway_does_not_keep_its_process(claude):
    """Stopped while claude was still working: that process would answer the
    old question before the new one, so it is not written to again."""
    agent = claude()
    agent.prepare(None)
    gen = agent.send("hang")
    assert next(gen).session_id                     # it has started the turn
    pid = claude.starts()[-1]["pid"]
    gen.close()
    assert gone(pid), "a process mid-turn was kept for the next one"
    assert agent._proc is None


def test_an_idle_process_is_let_go(claude):
    """~230MB, held only while it is likely to be used."""
    agent = claude(keep_warm_s=0.3)
    said, _, _ = turn(agent, "one")
    assert gone(pid_in(said), timeout=5), "nobody let the idle process go"


def test_a_process_that_died_between_turns_is_replaced(claude):
    agent = claude()
    first, sid, _ = turn(agent, "one")
    os.kill(pid_in(first), 9)
    assert gone(pid_in(first))
    second, _, errors = turn(agent, "two", sid)
    assert not errors, errors
    assert pid_in(second) != pid_in(first)
    assert agent.last_start == "cold"


def test_what_was_said_never_reaches_the_command_line(claude):
    """The process now lives for minutes, so argv being world readable
    through /proc would expose every turn, not just one."""
    agent = claude()
    turn(agent, "my pin is four four two one")
    for start in claude.starts():
        assert not any("four four" in a for a in start["argv"])


def test_a_missing_claude_is_said_not_raised(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    agent = ClaudeCode(cwd=str(tmp_path), ask_permission=False)
    agent.prepare(None)                             # must not raise
    _, _, errors = turn(agent, "hello")
    assert errors and "could not start claude" in errors[0]
