#!/usr/bin/env python3
"""Time to first sound, and silence between sentences, for a voice.

Plays a reply through the real Speaker and real Piper into a silent output
that blocks for as long as the audio would take to play, so the timings are
what you would hear without anything coming out of the speakers. Sentences
arrive the way the agent's stream delivers them: all at once by default, or
`--every` seconds apart.

    ~/.local/share/agentvoice/venv/bin/python bench/ahead_bench.py ryan-high
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "daemon"))

REPLY = [
    "Sure, I looked at the journal for the last hour, and the daemon restarted "
    "twice because the voice setting changed underneath it.",
    "Both restarts were clean, and nothing was lost from the conversation.",
    "If you want, I can pin the voice so a settings change waits for the "
    "current reply to finish, which would stop it happening mid-sentence.",
    "Otherwise there is nothing to fix.",
]


class SilentStream:
    """Blocks for the audio's duration and records when sound starts and
    where it goes quiet."""

    #: When the audio written so far runs out. Shared by every stream, so
    #: silence across a stream being closed and another opened still counts.
    until = 0.0

    def __init__(self, rate, log):
        self.rate = rate
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()

    def start(self):
        pass

    def stop(self):
        time.sleep(max(0.0, self.until - time.time()))

    def close(self):
        pass

    def abort(self):
        pass

    def write(self, pcm):
        now = time.time()
        if now > self.until + 0.02:
            self.log.append(("gap", self.until, now))
        start = max(now, self.until)
        SilentStream.until = start + len(pcm) / self.rate
        # Blocks like PortAudio: until about one slice is left queued.
        time.sleep(max(0.0, self.until - time.time() - 0.05))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("voice")
    ap.add_argument("--every", type=float, default=0.0,
                    help="seconds between sentences arriving from the agent")
    a = ap.parse_args()

    import runtime
    from adapters.base import speech_safe

    sp = runtime.Speaker(a.voice)
    log: list = []
    fake_sd = types.ModuleType("sounddevice")
    fake_sd.OutputStream = lambda **kw: SilentStream(sp._rate, log)
    sys.modules["sounddevice"] = fake_sd
    sp.say("Warm.")                       # load onnxruntime's first-run cost
    log.clear()

    t0 = time.time()

    def agent():
        for i, sentence in enumerate(REPLY):
            if i:
                time.sleep(a.every)
            sp.prefetch(speech_safe(sentence), first=(i == 0))

    threading.Thread(target=agent, daemon=True).start()
    first = None
    with sp.holding():
        for i, sentence in enumerate(REPLY):
            arrives = t0 + i * a.every
            time.sleep(max(0.0, arrives - time.time()))
            sp.say(speech_safe(sentence))
            if first is None:
                first = sp.first_audio_at
    # After the first sound only: the wait before it is reported on its own.
    gaps = [b - a_ for kind, a_, b in log if kind == "gap" and a_ > first]
    print(f"{a.voice}: first sound {first - t0:.2f}s, "
          f"silence between sentences {sum(gaps):.2f}s "
          f"(longest {max(gaps, default=0):.2f}s)")


if __name__ == "__main__":
    main()
