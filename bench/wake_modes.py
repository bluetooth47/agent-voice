#!/usr/bin/env python3
"""The three wake decisions on one fixed clip set (master plan M22).

    ~/.local/share/agentvoice/venv/bin/python -I bench/wake_modes.py OUT.json
        [--whisper base.en] [--modes first,either,both,both-t0,both-t1]

Every installed Piper voice says each clip below, at two loudnesses over
room noise (wake_auto.frames: -16 and -24 dBFS speech, -60 dBFS noise, 0.6s
before and 1.4s after). Each clip is fed, 200ms a frame, through the
daemon's own Pipeline -- the real sherpa-onnx spotter, Vosk, Whisper and
feed_wake -- once per decision:

  first    the spotter alone (wakeCrossCheck off)
  either   a spotter hit wakes at once; the second check rescues (default)
  both     a spotter hit is held until the second check names the same
           agent (wakeBothAgree), with the shipped tail
  both-tN  the same with the hit's tail set to N frames, to choose it

The settings are fixed here (phrase "theo", agents "sora" and "hazel", every
other value the shipped default), not read from shell.json, so the numbers
are the same on any machine with the same models.

What is reported per decision: true accepts per name, distractor accepts,
rejections by stage, the delay each wake landed after the speech ended (and
the delay added over `either` on the same clip), and CPU. The frame loop is
simulated in real time: a frame arrives every 200ms and waits for the one
before it to be processed, so a slow second check delays the wake by what it
costs, as it does in the daemon.

Synthesized speech is not a person in a room: compare the decisions with
each other, not with the rate you will get.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "daemon"))

PHRASE, NAMES = "theo", ["sora", "hazel"]

#: (text, the name it must wake, or "" for none).
TARGETS = [
    ("Theo.", "theo"), ("Hey Theo.", "theo"), ("Sora.", "sora"),
    ("Hey Sora.", "sora"), ("Hazel.", "hazel"),
    ("Theo, you there?", "theo"),
    # One breath, no pause after the name: what a wake word is mostly used
    # for, and what the second check's burst rules were not built around.
    ("Theo, what time is it?", "theo"),
    ("Sora, open the browser please.", "sora"),
]
DISTRACTORS = [
    # Sound-alikes that woke Theo or Sora in FINDINGS §22-24.
    "Video", "Cleo", "Leo", "Neo", "Story", "Sorry", "Rodeo", "Thank you", "Okay",
    # Words that start like a name: a spotter can fire before the word ends.
    "Theodore", "Theology", "Hazelnut",
    # A name inside a sentence: someone talking about the agent.
    "I was telling Theo about it yesterday.",
    "Did Sora finish the report?",
    "Ask Hazel when she gets back.",
    # Ordinary talk.
    "Can you send me that file when you get a chance?",
    "The weather is supposed to be cold and rainy all week.",
]

FRAME_S = 0.2


class Cfg(dict):
    """The shipped defaults, with this bench's values on top."""

    def _v(self, k):
        from runtime import DEFAULTS
        return self[k] if k in self else DEFAULTS[k]

    def __getitem__(self, k):
        return self._v(k) if k not in self.keys() else dict.__getitem__(self, k)

    def get_str(self, k): return str(self._v(k))
    def get_int(self, k): return int(self._v(k))
    def get_bool(self, k): return self._v(k) is True or str(self._v(k)).lower() == "true"

    def agents(self):
        return [{"name": n} for n in NAMES]

    def wake_tuning(self):
        from runtime import Config
        return Config.wake_tuning(self)

    def wake_both_agree(self):
        return self.get_bool("wakeBothAgree")


def settings_for(mode: str, whisper: str) -> tuple[Cfg, int | None]:
    base = {"engine": "sherpa", "phrase": PHRASE, "model": whisper,
            "fullStopAnytime": False, "logSpeech": False, "livePartials": "off"}
    tail = None
    if mode == "first":
        base.update(wakeCrossCheck=False, wakeBothAgree=False)
    elif mode == "either":
        base.update(wakeCrossCheck=True, wakeBothAgree=False)
    elif mode.startswith("both"):
        base.update(wakeCrossCheck=True, wakeBothAgree=True)
        if mode.startswith("both-t"):
            tail = int(mode[len("both-t"):])
    else:
        raise SystemExit(f"unknown mode {mode}")
    return Cfg(base), tail


def fresh(pipe, cfg) -> None:
    """Nothing carried over from the clip before: a new spotter stream (a
    reset one still differs with what it heard last), an empty cutter, no
    hold."""
    pipe._refractory_until = 0.0
    pipe._sherpa_spec = None
    pipe._sherpa_listen(cfg)
    pipe._burst_cutter().clear()
    pipe.forget_wake()
    pipe.take_near_misses()
    pipe.take_rejections()
    pipe.take_held()


def run_clip(pipe, cfg, chunks, speech_end: float) -> dict:
    from wake_listen import frame_db
    fresh(pipe, cfg)
    finish = 0.0
    out = {"woke": "", "how": "", "at": None, "after_speech": None}
    for i, pcm in enumerate(chunks):
        arrive = (i + 1) * FRAME_S
        start = max(arrive, finish)
        t0 = time.perf_counter()
        fired = pipe.feed_wake(pcm, frame_db(pcm))
        finish = start + (time.perf_counter() - t0)
        if fired:
            out.update(woke=pipe.heard_phrase, how=getattr(pipe, "wake_how", ""),
                       at=round(finish, 3), after_speech=round(finish - speech_end, 3))
            break
    out["rejected"] = pipe.take_rejections()
    out["why"] = pipe.take_near_misses()
    return out


def pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 3)


def summarise(rows: list[dict], ref: dict) -> dict:
    per = {}
    for name in [PHRASE, *NAMES]:
        mine = [r for r in rows if r["want"] == name]
        per[name] = f"{sum(r['woke'] == name for r in mine)}/{len(mine)}"
    targets = [r for r in rows if r["want"]]
    distract = [r for r in rows if not r["want"]]
    false = [f"{r['text']} ({r['voice']}, {r['level']}) woke {r['woke']}"
             for r in distract if r["woke"]]
    wrong = [f"{r['text']} ({r['voice']}, {r['level']}) woke {r['woke']}"
             for r in targets if r["woke"] and r["woke"] != r["want"]]
    bare = [r["after_speech"] for r in targets
            if r["woke"] == r["want"] and "," not in r["text"]]
    added = []
    for r in targets:
        other = ref.get((r["text"], r["voice"], r["level"]))
        if other and r["woke"] == r["want"] and other["woke"] == r["want"]:
            added.append(r["at"] - other["at"])
    stages: dict[str, int] = {}
    for r in rows:
        for s in r["rejected"]:
            stages[s] = stages.get(s, 0) + 1
    how: dict[str, int] = {}
    for r in targets:
        if r["woke"] == r["want"]:
            how[r["how"]] = how.get(r["how"], 0) + 1
    return {
        "true_accepts": f"{sum(r['woke'] == r['want'] for r in targets)}/{len(targets)}",
        "per_name": per,
        "one_breath": f"{sum(r['woke'] == r['want'] for r in targets if r['text'].count(' ') >= 3)}"
                      f"/{sum(1 for r in targets if r['text'].count(' ') >= 3)}",
        "distractor_accepts": f"{len(false)}/{len(distract)}",
        "false_wakes": false, "wrong_agent": wrong,
        "rejected": stages, "woke_by": how,
        "bare_name_wake_after_speech_s": {"median": pct(bare, 0.5), "p95": pct(bare, 0.95),
                                          "n": len(bare)},
        "added_over_either_s": {"median": pct(added, 0.5), "p95": pct(added, 0.95),
                                "max": round(max(added), 3) if added else None, "n": len(added)},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out")
    ap.add_argument("--whisper", default="base.en")
    ap.add_argument("--modes", default="first,either,both,both-t0,both-t1")
    ap.add_argument("--voices", type=int, default=0, help="only the first N voices (0 = all)")
    args = ap.parse_args()

    import numpy as np
    from piper import PiperVoice

    import wake_auto
    import wake_listen

    voices = [(p.stem.split("-", 1)[-1], PiperVoice.load(str(p)))
              for p in sorted(wake_auto.PIPER.glob("*.onnx"))]
    if args.voices:
        voices = voices[:args.voices]
    if not voices:
        print("no Piper voice installed")
        return 1
    plan = [(text, want) for text, want in TARGETS] + [(t, "") for t in DISTRACTORS]
    speech = {}
    for text, _ in plan:
        for vname, voice in voices:
            speech[(vname, text)] = wake_auto.synth(voice, text)

    modes = args.modes.split(",")
    cfg, _ = settings_for("either", args.whisper)
    pipe = wake_listen.Pipeline(cfg)
    assert pipe.engine == "sherpa", "sherpa-onnx is not installed here"
    results: dict[str, list] = {}
    cpu: dict[str, float] = {}
    for mode in modes:
        cfg, tail = settings_for(mode, args.whisper)
        pipe.apply(cfg)
        pipe._agreement().tail = crosscheck_tail() if tail is None else tail
        rng = np.random.default_rng(22)
        rows = []
        c0 = time.process_time()
        for text, want in plan:
            for vname, _ in voices:
                for level in wake_auto.LEVELS:
                    s = speech[(vname, text)]
                    chunks = wake_auto.frames(s, level, rng)
                    end = wake_auto.LEAD_S + len(s) / wake_auto.RATE
                    r = run_clip(pipe, cfg, chunks, end)
                    rows.append({"text": text, "want": want, "voice": vname,
                                 "level": level, **r})
        cpu[mode] = time.process_time() - c0
        results[mode] = rows
        print(f"{mode}: done, {len(rows)} clips, {cpu[mode]:.1f}s CPU", flush=True)

    ref = {(r["text"], r["voice"], r["level"]): r for r in results.get("either", [])}
    report = {"hardware": "see FINDINGS", "whisper": args.whisper,
              "phrase": PHRASE, "names": NAMES, "voices": [v for v, _ in voices],
              "levels": list(wake_auto.LEVELS), "modes": {}}
    for mode, rows in results.items():
        s = summarise(rows, ref)
        s["cpu_s"] = round(cpu[mode], 1)
        s["cpu_ms_per_clip"] = round(1000 * cpu[mode] / len(rows), 1)
        report["modes"][mode] = s
    Path(args.out).write_text(json.dumps({"report": report, "rows": results}, indent=1))
    print(json.dumps(report, indent=1))
    return 0


def crosscheck_tail() -> int:
    import crosscheck
    return crosscheck.CONFIRM_TAIL_FRAMES


if __name__ == "__main__":
    raise SystemExit(main())
