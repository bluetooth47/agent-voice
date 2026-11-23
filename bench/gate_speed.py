#!/usr/bin/env python3
"""How fast the adaptive gate follows the room, at slow, normal and fast
(master plan M23).

    ~/.local/share/agentvoice/venv/bin/python bench/gate_speed.py [--seed N]

The daemon's own NoiseFloor, fed 200 ms frames the way the frame loop feeds
it in the wake phase, over synthetic room noise:

- **a 10 dB step**: a fan (pink noise) at -50 dBFS for a minute, then 10 dB
  louder for two minutes, then back. "Settled" is the first moment after
  the step from which the floor stays within 1 dB of the new room's own
  median, and the time is counted from the step;
- **music**, the same step, because music's level swings far more than a
  fan's frame to frame;
- **talk the wake phase let through**: the room at -50 and a burst at a
  speaking level (-26 dBFS) lasting 3, 8 and 14 seconds -- someone else
  talking, a phone call across the room -- with the gate's highest point
  during and after it. This is the plan's risk: a fast gate learning speech.

Synthetic noise, not a recording of a room; the numbers compare the three
speeds with each other, and what they say about the window holds for any
room, because it is arithmetic about a median.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "daemon"))

import noise_floor  # noqa: E402
from noise_floor import NoiseFloor  # noqa: E402

RATE = 16_000
FRAME = 3200
FRAME_MS = 200
FRAME_S = FRAME_MS / 1000
FIXED = -38.0
BASE = -50.0
STEP = 10.0
TOLERANCE_DB = 1.0


def pink(seconds: float, rng) -> np.ndarray:
    n = int(seconds * RATE)
    spec = np.fft.rfft(rng.standard_normal(n))
    hz = np.fft.rfftfreq(n, 1 / RATE)
    # 1/f above 20 Hz. Below it, unfiltered pink noise drifts by several dB
    # from one second to the next, which is no fan: the room's own median
    # then wanders past the tolerance and every speed reads the same.
    shaped = np.where(hz >= 20, spec / np.sqrt(np.maximum(hz, 20)), 0)
    return np.fft.irfft(shaped, n)


def music(seconds: float, rng) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    out = np.zeros(n)
    chords = [(220, 277, 330), (196, 247, 294), (175, 220, 262), (196, 247, 330)]
    for i, start in enumerate(range(0, n, 2 * RATE)):
        seg = slice(start, min(n, start + 2 * RATE))
        env = np.exp(-3 * (t[seg] - t[seg][0])) * 0.7 + 0.3
        for f0 in chords[i % len(chords)]:
            for h, a in ((1, 1.0), (2, 0.4), (3, 0.2)):
                out[seg] += a * env * np.sin(2 * np.pi * f0 * h * t[seg])
    return out + 0.05 * rng.standard_normal(n)


def at(x: np.ndarray, db: float) -> np.ndarray:
    rms = float(np.sqrt((x ** 2).mean())) + 1e-12
    return x * (10 ** (db / 20) / rms)


def frames_db(x: np.ndarray) -> np.ndarray:
    k = len(x) // FRAME
    f = x[:k * FRAME].reshape(k, FRAME)
    return 20 * np.log10(np.sqrt((f ** 2).mean(axis=1)) + 1e-12)


def floor_for(speed: str) -> NoiseFloor:
    nf = NoiseFloor(FRAME_MS)
    rise, fall = noise_floor.SPEEDS[speed]
    nf.set_rates(rise / 10, fall / 10)
    return nf


def settle(levels: np.ndarray, speed: str, step_at: int, target: float) -> float | None:
    """Seconds from frame `step_at` until the floor stays within the
    tolerance of `target`; None if it never does."""
    nf = floor_for(speed)
    trace = []
    for x in levels:
        nf.feed(float(x))
        trace.append(nf.floor_db if nf.floor_db is not None else float("nan"))
    trace = np.array(trace)
    near = np.abs(trace - target) <= TOLERANCE_DB
    last_out = None
    for i in range(len(trace) - 1, step_at - 1, -1):
        if not near[i]:
            last_out = i
            break
    if last_out is None:
        return 0.0
    if last_out == len(trace) - 1:
        return None
    return (last_out + 1 - step_at) * FRAME_S


def step_case(kind: str, rng) -> dict:
    make = pink if kind == "fan" else music
    a = frames_db(at(make(60, rng), BASE))
    b = frames_db(at(make(120, rng), BASE + STEP))
    c = frames_db(at(make(120, rng), BASE))
    up = np.concatenate([a, b])
    down = np.concatenate([a, b, c])
    out = {}
    for speed in noise_floor.SPEEDS:
        out[speed] = (settle(up, speed, len(a), float(np.median(b))),
                      settle(down, speed, len(a) + len(b), float(np.median(c))))
    return out


def burst_case(seconds: float, rng) -> dict:
    room = frames_db(at(pink(90, rng), BASE))
    talk = frames_db(at(pink(seconds, rng), -26.0))
    after = frames_db(at(pink(60, rng), BASE))
    levels = np.concatenate([room, talk, after])
    out = {}
    for speed in noise_floor.SPEEDS:
        nf = floor_for(speed)
        peak = -99.0
        start = None
        for i, x in enumerate(levels):
            nf.feed(float(x))
            if i == len(room) - 1:
                start = nf.gate(FIXED)
            if i >= len(room):
                peak = max(peak, nf.gate(FIXED))
        out[speed] = (start, peak)
    return out


def fmt(x: float | None) -> str:
    return "never" if x is None else f"{x:.1f} s"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=23)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    speeds = list(noise_floor.SPEEDS)
    print(f"window {noise_floor.WINDOW_S:.0f} s (median), warm-up {noise_floor.WARMUP_S:.0f} s, "
          f"frames {FRAME_MS} ms; tolerance {TOLERANCE_DB:.0f} dB")
    print("speeds (rise, fall dB/s): " + ", ".join(
        f"{s} ({noise_floor.SPEEDS[s][0] / 10:.1f}, {noise_floor.SPEEDS[s][1] / 10:.1f})" for s in speeds))
    for kind in ("fan", "music"):
        res = step_case(kind, rng)
        print(f"\n{kind}: a {STEP:.0f} dB step at {BASE:.0f} dBFS, time to settle")
        print("  " + "".join(f"{s:>12}" for s in ["", *speeds]))
        print("  " + f"{'louder':>12}" + "".join(f"{fmt(res[s][0]):>12}" for s in speeds))
        print("  " + f"{'quieter':>12}" + "".join(f"{fmt(res[s][1]):>12}" for s in speeds))
    print(f"\ntalk the wake phase let through: room {BASE:.0f} dBFS, talk -26 dBFS; "
          f"the gate before -> its highest point")
    for seconds in (3, 8, 14):
        res = burst_case(seconds, rng)
        print(f"  {seconds:>2} s of talk: " + "   ".join(
            f"{s} {res[s][0]:.1f} -> {res[s][1]:.1f}" for s in speeds))
    return 0


if __name__ == "__main__":
    sys.exit(main())
