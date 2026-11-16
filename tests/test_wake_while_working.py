"""The wake word stops a turn that is still working.

Reported from use: talking while the agent was thinking or running tools did
nothing until the reply started, and then stopped it. Nothing read the
microphone while the agent worked, so what was said waited in the queue and
the first thing to read it was the barge watch inside the first sentence.

Asked for in this shape: while it works, only the wake word stops it --
ordinary talk does not, since it may be meant for someone else in the room --
and while it is speaking, talking over it on a headset still does.

Nothing here needs numpy or a microphone: the wake word is a stub that fires
on a chosen frame, and the agent is one that works until it is cancelled.
"""
from __future__ import annotations

import queue
import threading
import time
import types

import pytest


def frame(n: int) -> bytes:
    return bytes([n]) * 6400


class StubWake:
    """Pipeline-shaped where the watch touches it: fires on chosen frames."""

    conversation = False

    def __init__(self, fire_on=()):
        self.fire_on = set(fire_on)
        self.fed: list[bytes] = []

    def feed_wake(self, pcm, level):
        self.fed.append(pcm)
        return pcm in self.fire_on


class WorkingAgent:
    """Busy until cancelled, like a turn running a long tool."""

    name = "stub"

    def __init__(self, then=()):
        self.cancelled = False
        self._stop = threading.Event()
        self.then = list(then)

    def send(self, text, session_id=None):
        from adapters.base import Chunk
        for t in self.then:
            yield Chunk(text=t, session_id="s1")
        # Bounded, so a watch that never fires fails the test, not the run.
        self._stop.wait(3.0)
        return

    def cancel(self) -> None:
        self.cancelled = True
        self._stop.set()

    def prepare(self, *a, **k):
        pass


@pytest.fixture
def working(daemon, monkeypatch):
    # The level goes through frame_db, which needs numpy; the bare runner has
    # none, and the watch would stop at the first frame. The stdlib twin is
    # asserted equal to it in test_states wherever numpy exists.
    import wake_listen
    from test_states import _rms_db
    monkeypatch.setattr(wake_listen, "frame_db", _rms_db)
    daemon.enabled, daemon.locked, daemon.yielded = True, False, False
    daemon._frames = queue.Queue()
    daemon.poll_session = lambda: None
    return daemon


def _until(cond, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


class TestWhileItWorks:
    def test_the_wake_word_stops_it_and_keeps_what_follows(self, working):
        for n in range(1, 6):
            working._frames.put(frame(n))
        working.pipe = StubWake(fire_on={frame(3)})
        working.agent = WorkingAgent()

        t0 = time.time()
        working.answer("refactor the whole thing", {})

        assert time.time() - t0 < 2.0, "the turn ran to its end regardless"
        assert working.agent.cancelled, "the agent went on working"
        assert working.pipe.fed == [frame(1), frame(2), frame(3)]
        assert [working._frames.get_nowait() for _ in range(2)] == \
            [frame(4), frame(5)], "what was said after the wake word was lost"
        assert working.take_wake() is True
        assert working.take_wake() is False, "taken once"
        assert not working.arm_follow_up()

    def test_ordinary_talk_does_not(self, working):
        for n in range(1, 4):
            working._frames.put(frame(n))
        working.pipe = StubWake(fire_on=())
        agent = WorkingAgent()
        working.agent = agent

        done = threading.Thread(target=working.answer, args=("hi", {}))
        done.start()
        assert _until(lambda: len(working.pipe.fed) == 3), \
            "the wake word was not listened for while it worked"
        assert not agent.cancelled
        agent.cancel()
        done.join(2.0)
        assert working.take_wake() is False

    def test_not_while_it_is_speaking(self, working):
        """Then the microphone holds our own voice, and on a headset it is
        barge-in's to read."""
        working.pipe = StubWake(fire_on={frame(9)})
        seen_during: list[int] = []

        class Speaker:
            name = "stub"

            def say(self, text, watch=None):
                working._frames.put(frame(9))
                time.sleep(0.2)                 # four of the watch's polls
                seen_during.append(working._frames.qsize())

            def cancel(self):
                pass

        working.speaker = Speaker()
        working.agent = WorkingAgent(then=["Here is a sentence. "])
        threading.Timer(0.6, working.agent.cancel).start()

        working.answer("talk to me", {})

        assert seen_during == [1], "the wake watch read the speaker's frame"
        assert frame(9) not in working.pipe.fed
        assert working.take_wake() is False

    def test_not_in_the_deaf_tail_after_a_sentence(self, working):
        working._deaf_until = time.time() + 30
        working._frames.put(frame(9))
        working.pipe = StubWake(fire_on={frame(9)})
        working.agent = WorkingAgent()
        threading.Timer(0.3, working.agent.cancel).start()

        working.answer("hi", {})

        assert working.pipe.fed == [], "reverb of our own voice was fed"
        assert working.take_wake() is False

    def test_not_after_barge_in_has_stopped_it(self, working):
        """The rest of what they said over the reply belongs to the run
        loop; the watch must not swallow it."""
        working.pipe = StubWake()
        stop = threading.Event()
        working._interrupt.set()
        working._frames.put(frame(1))
        t = threading.Thread(target=working._wake_watch_until, args=(stop,))
        t.start()
        time.sleep(0.2)
        stop.set()
        t.join(1.0)
        assert working._frames.qsize() == 1
        assert working.pipe.fed == []

    def test_a_lock_drops_it(self, working):
        working._woke = True
        working._frames.put(frame(2))
        working.locked = True
        working.deafen(0)
        assert working._frames.qsize() == 0
        assert working.take_wake() is False, \
            "words from before a lock were carried into a turn after it"

    def test_deafen_keeps_the_queue_after_it(self, working):
        working._woke = True
        working._frames.put(frame(2))
        working.deafen(350)
        assert working._frames.qsize() == 1
        assert working._deaf_until == 0.0

    def test_a_new_turn_forgets_a_stale_one(self, working):
        working._woke = True
        working.agent = None
        working.speaker = None
        working.answer("hello", {})
        assert working._woke is False

    def test_no_microphone_no_thread(self, working):
        working._frames = None
        working.pipe = types.SimpleNamespace(conversation=False)
        before = threading.active_count()
        with working._hearing_wake():
            assert threading.active_count() == before


def test_the_run_loop_opens_the_next_turn(daemon, monkeypatch):
    """Driven through the real frame loop. The fake wake word fires once
    only, so a second turn reaching the agent can only have come from the
    capture the mid-turn wake opened."""
    from test_states import _drive_one_turn

    loud = b"\x00\x40" * 3200

    def on_answer(n, text):
        if n == 1:
            # What the wake watch does when it fires, then what the person
            # says after "computer".
            daemon._woke = True
            daemon._interrupt.set()
            while True:
                try:
                    daemon._frames.get_nowait()
                except queue.Empty:
                    break
            daemon._frames.put(loud)
            daemon._frames.put(loud)
            return False
        return True

    sent = _drive_one_turn(daemon, monkeypatch, "actually make it Tuesday",
                           on_answer=on_answer)
    assert sent == ["actually make it Tuesday"] * 2
