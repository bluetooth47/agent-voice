"""Short sounds that say what the daemon heard, so nobody has to look.

A voice interface is meant to be used without watching it, and until these
existed the only sign that the wake word had landed, or that the turn had
ended and the agent was now working, was the icon in the bar. Measured in
this machine's journal: 3-8s between the end of what you said and the first
word back, with nothing to tell "heard you, thinking" from "missed it".

Three sounds, kept few and short on purpose:

    wake    two rising notes   -- listening; go ahead
    heard   one soft note      -- got it; the agent is working on it
    done    three-note chime   -- a task that took a while has finished

They play in the background: PortAudio pulls them from a callback on its
own thread, the way the microphone already delivers frames. A blocking
write would hold the frame loop -- and the `heard` sound sits between the
end of your sentence and the agent being asked, where every millisecond is
the wait people notice. Speech still waits for a sound to finish (settle()),
so the two never play over each other.

Synthesised here, with the standard library: nothing to download, nothing to
pin, and the CI runner -- which has no numpy -- can test the waveforms.
"""
from __future__ import annotations

import array
import math
import time

RATE = 24_000

#: Notes as (frequency Hz, duration ms), played back to back.
TONES: dict[str, tuple[tuple[int, int], ...]] = {
    "wake": ((660, 70), (880, 90)),                  # E5 -> A5, rising
    "heard": ((587, 60),),                           # D5, once
    "done": ((523, 80), (659, 80), (784, 130)),      # C E G, a major chord
}

#: Peak level as a fraction of full scale. Quiet on purpose: these are
#: punctuation, not announcements, and `heard` the quietest of all because it
#: plays after every single turn.
LEVEL = {"wake": 0.22, "heard": 0.13, "done": 0.20}

#: Shaping, in seconds. A note that starts or stops at a non-zero sample
#: clicks; 4ms of attack and 6ms of release are below what reads as a fade.
ATTACK_S, RELEASE_S = 0.004, 0.006


def synth(notes, level: float) -> bytes:
    """16-bit mono PCM at RATE. A soft bell rather than a beep: a fast
    attack, an exponential decay, and a quarter of the octave above for
    warmth -- a pure sine at these levels sounds like a smoke alarm."""
    out = array.array("h")
    attack = max(1, int(RATE * ATTACK_S))
    release = max(1, int(RATE * RELEASE_S))
    for freq, ms in notes:
        n = int(RATE * ms / 1000)
        w = 2 * math.pi * freq / RATE
        for i in range(n):
            env = min(1.0, i / attack, (n - 1 - i) / release)
            env *= math.exp(-3.0 * i / n)
            s = (math.sin(w * i) + 0.25 * math.sin(2 * w * i)) / 1.25
            out.append(int(32767 * level * env * s))
    return out.tobytes()


class Chimes:
    """The three sounds, rendered once, played without blocking."""

    def __init__(self) -> None:
        self._pcm = {name: synth(notes, LEVEL[name])
                     for name, notes in TONES.items()}
        self._stream = None

    def length_s(self, name: str) -> float:
        return len(self._pcm[name]) / 2 / RATE

    def play(self, name: str) -> float:
        """Start a sound and return at once. Returns its length in seconds."""
        import sounddevice as sd

        self.settle()
        data = self._pcm[name]
        pos = 0

        def feed(outdata, _frames, _time, _status):
            nonlocal pos
            want = len(outdata)
            piece = data[pos:pos + want]
            pos += want
            outdata[:len(piece)] = piece
            if len(piece) < want:
                outdata[len(piece):] = b"\x00" * (want - len(piece))
                raise sd.CallbackStop

        stream = sd.RawOutputStream(samplerate=RATE, channels=1,
                                    dtype="int16", callback=feed)
        stream.start()
        self._stream = stream
        return self.length_s(name)

    def settle(self, timeout: float = 1.0) -> None:
        """Wait for a sound still playing to end, and close its stream.

        Called before anything else makes a noise. Cheap in practice: the
        longest sound is 290ms and the agent takes a second or more to say
        anything, so by the time speech wants the device this returns at once.
        """
        stream, self._stream = self._stream, None
        if stream is None:
            return
        end = time.monotonic() + timeout
        try:
            while stream.active and time.monotonic() < end:
                time.sleep(0.005)
            stream.close()
        except Exception:
            pass
