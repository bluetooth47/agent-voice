#!/usr/bin/env python3
"""Fixed gate against the adaptive gate, in six kinds of room (plan item 10).

    ~/.local/share/agentvoice/venv/bin/python bench/gate_bench.py [--quick]

Each room is a synthetic noise bed: a quiet room, a fan, a loud fan, music,
a TV and people talking (the last two are Piper voices, low-passed and
quieter, so they sound like speech from across the room). Into each go, at
a normal speaking level:

- requests, some with a pause mid-sentence, opened as a capture is: what is
  measured is whether the turn ends when the person stops (within a second of
  the configured pause), is held open by the room, or cuts them off;
- wake names and sound-alikes, through the real wake engine as configured
  (sherpa-onnx, the second check, whichever is chosen), with the gate the
  daemon would be using at that moment.

The adaptive gate learns as the daemon does: from every frame outside a
capture, and never from the capture itself.

Synthetic rooms and voices, not recordings of a real one: compare the two
gates with this, and use the live test for the real numbers.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "daemon"))

import wake_auto  # noqa: E402
from noise_floor import NoiseFloor  # noqa: E402
from runtime import Config  # noqa: E402

RATE = 16_000
FRAME = 3200                      # 200ms, as the daemon reads
FRAME_MS = 200
SPEECH_DB = -26.0                 # a person at a desk microphone
WARM_S = 40.0                     # bed alone before anything is said
GAP_S = 4.0                       # bed between events

ROOMS = {
    # name: (kind, level dBFS)
    "quiet room": ("white", -62.0),
    "fan": ("pink", -46.0),
    "loud fan": ("pink", -36.0),
    "music": ("music", -42.0),
    "TV": ("tv", -42.0),
    "people talking": ("babble", -40.0),
}

REQUESTS = [
    ("What's on my calendar today?",),
    ("Can you check whether the tests pass,", "and then tell me what failed?"),
    ("Turn the volume down a little.",),
    ("Open the settings for the bar,", "the one at the top."),
    ("Read me the last message from the build.",),
]
MID_PAUSE_S = 0.5

TV_LINES = [
    "And now the weather for the weekend.", "Scattered showers in the north.",
    "Back to you in the studio.", "Our top story tonight.",
    "Prices rose again this month.", "The match ended in a draw.",
    "Stay with us after the break.", "A new study suggests otherwise.",
]


def rms_db(x: np.ndarray) -> float:
    return 20 * np.log10(float(np.sqrt((x ** 2).mean())) + 1e-12)


def at(x: np.ndarray, db: float) -> np.ndarray:
    return x * (10 ** (db / 20) / (10 ** (rms_db(x) / 20)))


def lowpass(x: np.ndarray, taps: int = 9) -> np.ndarray:
    return np.convolve(x, np.ones(taps) / taps, mode="same")


def bed(kind: str, seconds: float, rng, voices) -> np.ndarray:
    n = int(seconds * RATE)
    if kind == "white":
        return rng.standard_normal(n)
    if kind == "pink":
        spec = np.fft.rfft(rng.standard_normal(n))
        f = np.arange(len(spec)); f[0] = 1
        return np.fft.irfft(spec / np.sqrt(f), n)
    if kind == "music":
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
    if kind in ("tv", "babble"):
        streams = 1 if kind == "tv" else 3
        out = np.zeros(n)
        for s in range(streams):
            _, voice = voices[(s + 1) % len(voices)]
            pos, line = int(rng.uniform(0, 1) * RATE), s
            while pos < n:
                clip = lowpass(wake_auto.synth(voice, TV_LINES[line % len(TV_LINES)]))
                clip = at(clip, -20)
                end = min(n, pos + len(clip))
                out[pos:end] += clip[:end - pos]
                pos = end + int(rng.uniform(0.15, 0.6) * RATE)
                line += streams
        return out + 0.01 * rng.standard_normal(n)
    raise ValueError(kind)


def frames_db(x: np.ndarray) -> np.ndarray:
    k = len(x) // FRAME
    f = x[:k * FRAME].reshape(k, FRAME)
    return 20 * np.log10(np.sqrt((f ** 2).mean(axis=1)) + 1e-12)


def to_pcm(x: np.ndarray) -> list[bytes]:
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()
    return [pcm[i:i + FRAME * 2] for i in range(0, len(pcm) - FRAME * 2 + 1, FRAME * 2)]


class Gate:
    """The gate the daemon would use: fixed, or learning outside captures."""

    def __init__(self, cfg, adaptive: bool):
        self.fixed = float(cfg["micThresholdDb"])
        self.floor = NoiseFloor(FRAME_MS, cfg.get_int("gateMarginDb")) if adaptive else None

    def learn(self, level: float) -> None:
        if self.floor is not None:
            self.floor.feed(level)

    @property
    def db(self) -> float:
        return self.floor.gate(self.fixed) if self.floor is not None else self.fixed

    @property
    def wake(self) -> float:
        return self.floor.wake_gate(self.fixed) if self.floor is not None else self.fixed


def endpoint(levels: np.ndarray, gate: float, speech_end: int, trailing_ms: int,
             lead_in_ms: int, max_ms: int) -> tuple[str, float]:
    """The run loop's energy endpointing over one capture.

    `levels` starts where the capture opened; `speech_end` is the frame the
    person stopped on. Returns (outcome, seconds after they stopped)."""
    heard, last_voice = False, 0
    for i, lv in enumerate(levels):
        t_ms = (i + 1) * FRAME_MS
        if lv >= gate:
            heard, last_voice = True, i
        if not heard:
            if t_ms > lead_in_ms:
                return "nothing heard", 0.0
            continue
        quiet_ms = (i - last_voice) * FRAME_MS
        if quiet_ms > trailing_ms or t_ms >= max_ms:
            late = (i - speech_end) * FRAME_MS / 1000
            if i < speech_end - 1:
                return "cut off", late
            if t_ms >= max_ms:
                return "held open", late
            return ("on time" if late <= trailing_ms / 1000 + 1.0 else "late"), late
    return "held open", (len(levels) - speech_end) * FRAME_MS / 1000


def run_room(name, kind, level, cfg, pipe, voices, quick, rng):
    names = [pipe.phrase, *getattr(pipe, "names", [])]
    vs = voices[:2] if quick else voices[:3]
    events = []                      # (kind, audio, want, text, voice)
    for vname, voice in vs:
        for parts in REQUESTS[:3] if quick else REQUESTS:
            chunks = []
            for j, p in enumerate(parts):
                if j:
                    chunks.append(np.zeros(int(MID_PAUSE_S * RATE)))
                chunks.append(at(wake_auto.synth(voice, p), SPEECH_DB))
            events.append(("request", np.concatenate(chunks), "", " ".join(parts), vname))
        for text, want in wake_auto.clips(names, ""):
            if not want:
                continue                 # its sound-alikes are added below
            events.append(("wake", at(wake_auto.synth(voice, text), SPEECH_DB), want, text, vname))
        for text in wake_auto.DISTRACTORS[:6]:
            events.append(("wake", at(wake_auto.synth(voice, text), SPEECH_DB), "", text, vname))
    rng.shuffle(events)

    total_s = WARM_S + sum(len(a) / RATE + GAP_S for _, a, *_ in events) + 15
    noise = at(bed(kind, total_s, rng, voices), level)
    results = {}
    for mode in ("fixed", "adaptive"):
        gate = Gate(cfg, mode == "adaptive")
        x = noise.copy()
        pos = int(WARM_S * RATE)
        marks = []
        for ev in events:
            a = ev[1]
            x[pos:pos + len(a)] += a
            marks.append((pos // FRAME, (pos + len(a)) // FRAME, ev))
            pos += len(a) + int(GAP_S * RATE)
        lv = frames_db(x)
        pcm = to_pcm(x)
        out = {"requests": {}, "hits": 0, "tries": 0, "false": 0, "distract": 0,
               "gates": []}
        f = 0
        for start, end, ev in marks:
            kind_ev, _, want, text, vname = ev
            if kind_ev == "request":
                open_at = max(f, start - 2)      # the capture opens just before
                while f < open_at:
                    gate.learn(lv[f]); f += 1
                g = gate.db
                out["gates"].append(g)
                res, late = endpoint(lv[open_at:], g, end - open_at, cfg.get_int("trailingSilenceMs"),
                                     cfg.get_int("leadInMs"), min(cfg.get_int("maxUtteranceMs"), 15_000))
                out["requests"][res] = out["requests"].get(res, 0) + 1
                # The capture's frames are not learned; skip past its end.
                f = max(f, end + int((late if res != "nothing heard" else 5) * 5) + 1)
            else:
                clip_from, clip_to = max(f, start - 3), end + 7
                while f < clip_from:
                    gate.learn(lv[f]); f += 1
                pipe.threshold_db, pipe.wake_gate_db = gate.db, gate.wake
                woke, _ = wake_auto.first_wake(pipe, pcm[clip_from:clip_to])
                for i in range(clip_from, clip_to):   # the wake phase learns these
                    gate.learn(lv[i])
                f = clip_to
                if want:
                    out["tries"] += 1
                    out["hits"] += woke == want
                else:
                    out["distract"] += 1
                    out["false"] += bool(woke)
        out["gate"] = round(float(np.median(out["gates"])), 1) if out["gates"] else None
        del out["gates"]
        results[mode] = out
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="two voices, three requests")
    ap.add_argument("--fixed", type=float, default=-38.0,
                    help="the fixed gate to compare with (default: the shipped -38)")
    ap.add_argument("--percentile", type=float, help="override noise_floor.PERCENTILE")
    ap.add_argument("--rooms", help="comma-separated subset of rooms")
    ap.add_argument("--slack", type=float, help="override noise_floor.WAKE_SLACK_DB")
    args = ap.parse_args()
    import noise_floor
    if args.slack is not None:
        noise_floor.WAKE_SLACK_DB = args.slack
    if args.percentile is not None:
        noise_floor.PERCENTILE = args.percentile
    rooms = ROOMS if not args.rooms else {k: v for k, v in ROOMS.items()
                                          if k in args.rooms.split(",")}
    from piper import PiperVoice

    import wake_listen
    cfg = Config()
    cfg_fixed = args.fixed
    cfg.__class__ = type("BenchConfig", (type(cfg),), {
        "__getitem__": lambda self, k, _g=type(cfg).__getitem__:
            cfg_fixed if k == "micThresholdDb" else _g(self, k)})
    pipe = wake_listen.Pipeline(cfg)
    voices = [(p.stem.split("-", 1)[-1], PiperVoice.load(str(p)))
              for p in sorted(wake_auto.PIPER.glob("*.onnx"))]
    rng = np.random.default_rng(23)
    print(f"floor percentile {noise_floor.PERCENTILE} · wake slack "
          f"{noise_floor.WAKE_SLACK_DB} dB · engine {pipe.engine} · fixed gate {cfg['micThresholdDb']} dBFS · margin "
          f"{cfg.get_int('gateMarginDb')} dB · speech {SPEECH_DB} dBFS · "
          f"{len(voices[:2] if args.quick else voices[:3])} voices\n")
    print(f"{'room':16} {'gate':9} {'gate dB':>8}  {'requests (on time/late/held/cut/missed)':40} "
          f"{'wakes':>7} {'false':>6}")
    t0 = time.time()
    for name, (kind, level) in rooms.items():
        res = run_room(name, kind, level, cfg, pipe, voices, args.quick, rng)
        for mode, r in res.items():
            q = r["requests"]
            req = (f"{q.get('on time', 0)}/{q.get('late', 0)}/{q.get('held open', 0)}/"
                   f"{q.get('cut off', 0)}/{q.get('nothing heard', 0)}")
            print(f"{name if mode == 'fixed' else '':16} {mode:9} {r['gate']!s:>8}  {req:40} "
                  f"{r['hits']:>3}/{r['tries']:<3} {r['false']:>2}/{r['distract']}")
        sys.stdout.flush()
    print(f"\n{time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
