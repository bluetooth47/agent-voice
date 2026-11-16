"""Transcribing while you talk, and ending the turn sooner when you are done.

Measured in the journal before this existed: 82 turns, median 1105ms of
Whisper, every millisecond of it after the person had stopped, and a fixed
1.2-1.6s pause on top. These pin the two behaviours that buy that back and
the one that must never be bought with it -- cutting somebody off.

Nothing here needs numpy or Whisper: the pieces are bytes and the
transcriber is a function, so it all runs on the bare CI runner.
"""
from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor

import pytest

from eager import LEAD_FRAMES, MIN_PIECE_S, PAUSE_FRAMES, Utterance, \
    sounds_finished

FRAME = 6400                     # 200ms of 16kHz int16, as the daemon delivers
BPS = 32000
LOUD, QUIET = b"\x01" * FRAME, b"\x00" * FRAME


class Whisper:
    """Records what it was handed and answers with a label per call."""

    def __init__(self, fail=False):
        self.calls: list[tuple[int, str]] = []
        self.fail = fail

    def __call__(self, pcm: bytes, context: str) -> str:
        if self.fail:
            raise RuntimeError("model fell over")
        self.calls.append((len(pcm), context))
        return f" piece{len(self.calls)}."


class Manual:
    """An executor that runs nothing until told to, in order -- so a test
    can see what is queued before it has run."""

    def __init__(self):
        self.queue: list[tuple[Future, object, tuple]] = []

    def submit(self, fn, *args):
        fut = Future()
        self.queue.append((fut, fn, args))
        return fut

    def run(self):
        while self.queue:
            fut, fn, args = self.queue.pop(0)
            if fut.set_running_or_notify_cancel():
                try:
                    fut.set_result(fn(*args))
                except Exception as e:
                    fut.set_exception(e)


@pytest.fixture
def pool():
    ex = ThreadPoolExecutor(max_workers=1)
    yield ex
    ex.shutdown(wait=True)


def speak(utt, *frames):
    for f in frames:
        utt.add(f, f == LOUD)


def frames(n, kind):
    return [kind] * n


def wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


# --- the transcript is ready when you stop -----------------------------------

def test_a_sentence_is_transcribed_at_its_pause_not_after_the_turn(pool):
    """The whole point: by the time the endpoint has waited out its silence,
    Whisper has already been handed everything that was said."""
    w = Whisper()
    utt = Utterance(w, pool.submit, bytes_per_s=BPS, frame_bytes=FRAME)
    speak(utt, *frames(10, LOUD), *frames(PAUSE_FRAMES, QUIET))
    assert wait_for(lambda: utt.tail() is not None), \
        "nothing was sent to Whisper at the pause"
    text, waited = utt.finish()
    assert text == "piece1."
    assert len(w.calls) == 1, "finish() transcribed it a second time"
    assert utt.parts == 1


def test_finish_without_any_pause_still_hears_everything(pool):
    """Push-to-talk released mid-word: there was no pause to start on."""
    w = Whisper()
    utt = Utterance(w, pool.submit, bytes_per_s=BPS, frame_bytes=FRAME)
    speak(utt, *frames(10, LOUD))
    assert utt.tail() is None
    text, _ = utt.finish()
    assert text == "piece1." and len(w.calls) == 1


def test_the_silence_before_you_start_is_not_sent(pool):
    """A lead-in can hold five seconds of nothing. Whisper gets a little room
    before the first word and none of the rest."""
    w = Whisper()
    utt = Utterance(w, pool.submit, bytes_per_s=BPS, frame_bytes=FRAME)
    speak(utt, *frames(20, QUIET), *frames(5, LOUD),
          *frames(PAUSE_FRAMES, QUIET))
    utt.finish()
    assert w.calls[0][0] == (LEAD_FRAMES + 5 + PAUSE_FRAMES) * FRAME


def test_tail_is_nothing_while_you_are_still_talking(pool):
    w = Whisper()
    utt = Utterance(w, pool.submit, bytes_per_s=BPS, frame_bytes=FRAME)
    speak(utt, *frames(10, LOUD), *frames(PAUSE_FRAMES, QUIET))
    wait_for(lambda: utt.tail() is not None)
    speak(utt, LOUD)
    assert utt.tail() is None, \
        "a transcript from before you carried on talking looked complete"


# --- pauses mid-thought -------------------------------------------------------

def test_a_short_piece_is_heard_again_as_part_of_a_longer_one():
    """A pause after one second of speech is not a place to cut: the piece is
    dropped and the next transcription starts from the same place."""
    w, ex = Whisper(), Manual()
    utt = Utterance(w, ex.submit, bytes_per_s=BPS, frame_bytes=FRAME)
    speak(utt, *frames(5, LOUD), *frames(PAUSE_FRAMES, QUIET))   # 1s, pause
    speak(utt, *frames(5, LOUD), *frames(PAUSE_FRAMES, QUIET))   # resumes
    ex.run()
    text, _ = utt.finish()
    assert utt.parts == 1
    assert len(w.calls) == 1, "the dropped piece was still transcribed"
    # Speech from the first frame, so there is no silence in front to keep.
    whole = (5 + PAUSE_FRAMES + 5 + PAUSE_FRAMES) * FRAME
    assert w.calls[0][0] == whole, "the second piece did not start over"


def test_a_long_piece_is_kept_and_carries_its_words_into_the_next(pool):
    w = Whisper()
    utt = Utterance(w, pool.submit, bytes_per_s=BPS, frame_bytes=FRAME)
    long_enough = int(MIN_PIECE_S * 5) + 1                      # frames of 200ms
    speak(utt, *frames(long_enough, LOUD), *frames(PAUSE_FRAMES, QUIET))
    speak(utt, *frames(5, LOUD), *frames(PAUSE_FRAMES, QUIET))
    text, _ = utt.finish()
    assert text == "piece1. piece2."
    assert utt.parts == 2
    assert w.calls[1][1] == "piece1.", \
        "the second piece was transcribed without what came before it"


# --- throwing a capture away --------------------------------------------------

def test_an_abandoned_capture_transcribes_nothing_more():
    """A lock mid-sentence. Audio recorded before it must not be transcribed
    after it, for a turn that no longer exists."""
    w, ex = Whisper(), Manual()
    utt = Utterance(w, ex.submit, bytes_per_s=BPS, frame_bytes=FRAME)
    speak(utt, *frames(10, LOUD), *frames(PAUSE_FRAMES, QUIET))
    utt.abandon()
    ex.run()
    assert w.calls == []


def test_a_failed_piece_is_reported_at_the_end_not_in_the_frame_loop():
    """tail() runs on every frame of silence. Raising there would end the
    daemon over a transcription that finish() can report in its place."""
    w, ex = Whisper(fail=True), Manual()
    utt = Utterance(w, ex.submit, bytes_per_s=BPS, frame_bytes=FRAME)
    speak(utt, *frames(10, LOUD), *frames(PAUSE_FRAMES, QUIET))
    ex.run()
    assert utt.tail() is None
    with pytest.raises(RuntimeError):
        utt.finish()


# --- what counts as finished ------------------------------------------------

@pytest.mark.parametrize("said", [
    "Open the file.", "Turn the lights on.", "Delete it.", "Do this.",
    "Tell me what it is.", "What is this for?", "Yes.", "Stop.",
    "Thank you.", "Run the tests!",
])
def test_these_end_where_they_should(said):
    assert sounds_finished(said), said


@pytest.mark.parametrize("said", [
    "", "   ", "Open the file and", "Open the file and.", "Open the...",
    "I want to go to the.", "Check my.", "So.", "Okay.", "Um.",
    "Turn it on,", "Move it into", "It is because.", "Put it on the…",
])
def test_these_are_somebody_drawing_breath(said):
    """Each of these taking the quick end would cut a person off, which is
    the failure this program most needs to avoid."""
    assert not sounds_finished(said), said


# --- the endpoint -------------------------------------------------------------

class _Pipe:
    trailing_ms = 1600
    quick_end_ms = 800


class _Utt:
    def __init__(self, tail):
        self._tail = tail

    def tail(self):
        return self._tail


@pytest.mark.parametrize("quiet, tail, quick, ended", [
    (1700, None, 800, True),               # the full pause always ends it
    (900, "Open the file.", 800, True),    # transcribed, finished, quiet enough
    (900, None, 800, False),               # not transcribed yet
    (900, "Open the file and", 800, False),  # drawing breath
    (600, "Open the file.", 800, False),   # finished, but not quiet long enough
    (900, "Open the file.", 0, False),     # 0 turns it off
])
def test_when_the_turn_ends(daemon, quiet, tail, quick, ended):
    daemon.pipe = _Pipe()
    daemon.pipe.quick_end_ms = quick
    assert daemon.turn_ended(quiet, _Utt(tail)) is ended


def test_the_setting_exists_in_all_three_places():
    import json
    from pathlib import Path

    import runtime
    root = Path(__file__).resolve().parent.parent
    manifest = json.loads((root / "manifest.json").read_text())
    keys = {k["key"]: k for k in manifest["barWidget"]["schema"]}
    assert keys["quickEndMs"]["min"] == 0, "0 is how it is turned off"
    assert manifest["barWidget"]["defaults"]["quickEndMs"] == \
        runtime.DEFAULTS["quickEndMs"]
    assert '"quickEndMs"' in (root / "Settings.qml").read_text()
