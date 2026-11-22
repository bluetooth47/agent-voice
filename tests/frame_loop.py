"""Drive the real frame loop (`Daemon.run`) over a scripted microphone.

Phase M2 needed the loop driven through open-mic windows, wake words heard
while an agent works, the longest-turn limit and the popup's open-mic
switch, with assertions on what was published and when. The existing
driver in test_states.py runs on the wall clock and stops at the first
transcript, which suits the one turn it drives and not a window that waits
minutes. So this one:

- replaces the frame queue `run()` builds with a script: each `get()` hands
  the loop the next 200ms frame and moves a fake clock on by 200ms, so time
  inside the loop is audio time, exactly as on a real microphone, and a
  ten-minute open-mic wait takes milliseconds;
- runs any callable in the script on the loop's own thread just before the
  next frame, the way the CLI drops a command file between two frames;
- records every payload written to the state file with the fake time it was
  written at, so "within one tick" is a number, not a feeling.

Nothing about the loop itself is faked: the levels go through the
standard-library `frame_db` stand-in (asserted equal to numpy's in
test_states.py), endpointing is the loop's own arithmetic, and the commands
go through the real command file. Anything the script does not supply ends
the drive with `Done`.
"""
from __future__ import annotations

import array
import json
import math
import queue as _queue
import sys
import threading
import time as _time

#: 3200 int16 samples: one 200ms frame at 16kHz, what blocksize=CHUNK gives.
LOUD = b"\x00\x40" * 3200            # about -6 dBFS, well over any gate
QUIET = b"\x00\x00" * 3200           # -99 dB
FRAME_S = 0.2


def rms_db(pcm: bytes) -> float:
    """wake_listen.frame_db in the standard library (see test_states.py)."""
    x = array.array("h")
    x.frombytes(pcm)
    if not len(x):
        return -99.0
    mean = sum(float(v) * v for v in x) / len(x)
    return float(20.0 * math.log10(math.sqrt(mean) / 32768.0 + 1e-9))


class Done(Exception):
    """The script ran out, or asked to stop: the drive is over."""


class Clock:
    """The loop's idea of now. Starts at the real time, so anything compared
    with a real timestamp (a file's mtime, a date) still makes sense."""

    def __init__(self) -> None:
        self.now = _time.time()

    def time(self) -> float:
        return self.now


class FakeTime:
    """The `time` module as wake_listen sees it: the fake clock's time(),
    everything else real. Only wake_listen's own name is rebound, so other
    modules and threads keep the real clock."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def time(self) -> float:
        return self._clock.time()

    def __getattr__(self, name):
        return getattr(_time, name)


def wake_on(*frames: int):
    """A feed_wake that fires on the given wake-phase frame numbers (counted
    from 1, over every frame fed to it)."""
    want = set(frames)
    seen = [0]

    def feed(pcm, level):
        seen[0] += 1
        return seen[0] in want
    return feed


class Utterance:
    """eager.Utterance-shaped: the whole transcript at the end."""
    busy_ms, parts = 12.0, 1

    def __init__(self, text: str) -> None:
        self.text = text
        self.abandoned = False
        self.frames = 0

    def add(self, pcm, loud):
        self.frames += 1
        return False

    def tail(self):
        return None

    def finish(self):
        return self.text, 0.0

    def abandon(self):
        self.abandoned = True


class Pipe:
    """The parts of wake_listen.Pipeline the loop reads."""

    phrase = "theo"
    lead_in_ms, trailing_ms = 5000, 600
    max_utterance_ms, min_utterance_ms = 30_000, 100
    threshold_db = -40.0
    detection_threshold = 0.9
    conversation = True
    follow_up_ms = 3000
    floor_db = None
    heard_phrase = "theo"
    names: tuple = ("theo",)
    accurate_partials = False

    def __init__(self, said: str = "what time is it", feed_wake=None):
        self.said = said
        self.feed_wake = feed_wake or (lambda pcm, level: False)
        self.utterances: list[Utterance] = []

    def learn_room(self, level):
        return False

    def new_capture(self):
        return None                         # live partials off

    def new_utterance(self):
        u = Utterance(self.said)
        self.utterances.append(u)
        return u

    def apply(self, cfg):
        pass

    def reconcile_vocab(self):
        pass


class Script:
    """The frames and actions, consumed one `get()` at a time."""

    def __init__(self, items, clock: Clock, loop_thread: threading.Thread):
        self._items = list(items)
        self._clock = clock
        self._loop = loop_thread
        self.frames = 0

    def _next(self):
        while self._items:
            item = self._items.pop(0)
            if callable(item):
                item()
                continue
            self.frames += 1
            self._clock.now += FRAME_S
            return item
        raise Done("script finished")

    def get(self, *a, **k):
        return self._next()

    def get_nowait(self):
        if threading.current_thread() is not self._loop:
            raise _queue.Empty          # side readers (the wake watch) get nothing
        return self._next()

    def put(self, item):
        pass

    def qsize(self):
        return len(self._items)


def drive(daemon, monkeypatch, items, *, pipe=None, clock=None):
    """Run `daemon.run()` over `items` until they run out (or an action
    raises Done). Returns (payloads, clock): every state-file payload as
    (fake time, dict), in order."""
    import wake_listen

    clock = clock or Clock()
    loop_thread = threading.current_thread()
    script = Script(items, clock, loop_thread)

    class FakeQueueModule:
        Queue = staticmethod(lambda *a, **k: script)
        Empty = _queue.Empty

    class Stream:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    fake_sd = type(sys)("sounddevice")
    fake_sd.RawInputStream = lambda **kw: Stream(**kw)
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    monkeypatch.setattr(wake_listen, "queue", FakeQueueModule)
    monkeypatch.setattr(wake_listen, "time", FakeTime(clock))
    monkeypatch.setattr(wake_listen, "frame_db", rms_db)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False, raising=False)

    daemon.pipe = pipe or Pipe()
    daemon.enabled, daemon.locked, daemon.yielded = True, False, False
    for name in ("reconcile_lock", "reconcile_yield"):
        monkeypatch.setattr(daemon, name, lambda *a, **k: None)
    # The settings poll reads files and rebuilds agents; nothing here changes
    # a setting, so only the parts that matter to these tests run.
    monkeypatch.setattr(daemon, "refresh",
                        lambda: daemon.expire_notices() and daemon.publish_agent())
    if getattr(daemon.agent, "name", None) is None:
        daemon.agent.name = "stub"
    daemon.agent.posture = lambda level: f"{level} here"
    if daemon.speaker is not None:
        daemon.speaker.name = "stub-voice"

    payloads: list[tuple[float, dict]] = []
    real_write = daemon.state._write

    def write(state, extra):
        real_write(state, extra)
        # As written: the sticky fields describe() merges in included.
        payloads.append((clock.now, json.loads(json.dumps(daemon.state._last,
                                                          default=str))))
    monkeypatch.setattr(daemon.state, "_write", write)
    try:
        daemon.run(device=None)
    except Done:
        pass
    return payloads, clock


def command(text: str):
    """An action: the CLI dropping `text` in the command file, as
    `agentvoice open-mic off` does."""
    def act():
        from paths import RUNTIME_DIR
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        tmp = RUNTIME_DIR / "command.tmp"
        tmp.write_text(text)
        tmp.replace(RUNTIME_DIR / "command")
    return act


def stop():
    """An action that ends the drive here."""
    def act():
        raise Done("stopped by the script")
    return act
