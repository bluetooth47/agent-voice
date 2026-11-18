#!/usr/bin/env python3
"""The automatic wake test: synthesized names through the real engines.

`agentvoice wake-test auto` runs this beside the daemon. It reads the same
settings, builds the same wake engine (sherpa-onnx and the second check, or
whichever is chosen) in its own process, and feeds it clips made with every
installed Piper voice:

- each wake name, alone and after "hey", at two loudnesses;
- "full stop", when that keyword is on;
- sound-alikes and ordinary talk that must wake nothing.

Nothing goes near the microphone or the speakers, so it can run with the
daemon listening. Progress and the result go to wake-auto.json in the
runtime directory (0600), which the Listening page watches.

Synthesized speech is not a person in a room: use the numbers to compare one
setting with another, not as the rate you will get. That is what the manual
test is for.
"""
from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wake_test  # noqa: E402
from runtime import RUNTIME_DIR, Config  # noqa: E402

OUT = RUNTIME_DIR / "wake-auto.json"
PID = RUNTIME_DIR / "wake-auto.pid"
PIPER = Path.home() / ".local/share/agentvoice/models/piper"
RATE = 16_000
#: Speech RMS, dBFS. Both clear the default gate; the quieter one is close.
LEVELS = (-16.0, -24.0)
NOISE_DB = -60.0
LEAD_S, TAIL_S = 0.6, 1.4

#: Must wake nothing. The first row is what woke Theo, Sora or Sarah in
#: FINDINGS §22-24, the second is near "full stop", the rest is ordinary talk.
DISTRACTORS = (
    "Video", "Leo", "Cleo", "Story", "Sorry", "Okay", "Thank you", "Rodeo",
    "Bus stop", "I'm full", "Pull up",
    "Hello there", "Can you send me that file when you get a chance?",
)

NOTE = ("Synthesized voices, not you: compare settings with it, and use the "
        "manual test for your real rate.")


def clips(names: list[str], stop: str):
    """(text, wanted name or "") for every clip, in order."""
    for name in names:
        yield name.title() + ".", name
        if not name.startswith(("hey ", "okay ", "ok ")):
            yield "Hey " + name.title() + ".", name
    if stop:
        yield "Full stop.", stop
    for text in DISTRACTORS:
        yield text, ""


def tally(results: list[dict], names: list[str], stop: str) -> dict:
    """Per name: tries, hits, which path caught each; and false wakes."""
    per = {n: {"tries": 0, "hits": 0, "spotter": 0, "second check": 0, "other": 0}
           for n in [*names, *([stop] if stop else [])]}
    false = []
    distract = 0
    for r in results:
        if r["want"]:
            row = per[r["want"]]
            row["tries"] += 1
            if r["woke"] == r["want"]:
                row["hits"] += 1
                key = r["how"] if r["how"] in ("spotter", "second check") else "other"
                row[key] += 1
        else:
            distract += 1
            if r["woke"]:
                false.append(f"“{r['text']}” ({r['voice']}) woke {r['woke']}")
    return {"names": per, "false": false, "distractors": distract}


def synth(voice, text: str):
    import numpy as np
    raw = b"".join(getattr(c, "audio_int16_bytes", c) for c in voice.synthesize(text))
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    src = getattr(voice.config, "sample_rate", 22050)
    if src != RATE:
        n = int(round(len(x) * RATE / src))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    loud = np.flatnonzero(np.abs(x) > 0.01)
    return x[loud[0]:loud[-1] + 1] if len(loud) else x


def frames(speech, level: float, rng):
    import numpy as np

    from wake_listen import CHUNK
    rms = float(np.sqrt((speech ** 2).mean())) + 1e-12
    s = speech * (10 ** (level / 20) / rms)
    x = np.concatenate([np.zeros(int(LEAD_S * RATE)), s, np.zeros(int(TAIL_S * RATE))])
    x = x + rng.standard_normal(len(x)) * 10 ** (NOISE_DB / 20)
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()
    step = CHUNK * 2
    return [pcm[i:i + step] for i in range(0, len(pcm) - step + 1, step)]


def first_wake(pipe, chunks) -> tuple[str, str]:
    """Fresh engine state, then the clip; the first thing that woke it."""
    from wake_listen import frame_db
    pipe._refractory_until = 0.0
    if getattr(pipe, "_sherpa", None) is not None:
        pipe._sherpa.reset()
    pipe._burst_cutter().clear()
    pipe.take_near_misses()
    for pcm in chunks:
        if pipe.feed_wake(pcm, frame_db(pcm)):
            return pipe.heard_phrase, getattr(pipe, "wake_how", "") or "?"
    return "", ""


def main() -> int:
    import numpy as np
    from piper import PiperVoice

    import wake_listen

    started = time.time()
    snap = {"mode": "auto", "status": "loading", "done": 0, "total": 0,
            "note": NOTE, "started": int(started)}
    wake_test.write(OUT, snap)

    stopped = False

    def stop(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop)

    cfg = Config()
    pipe = wake_listen.Pipeline(cfg)
    names = [pipe.phrase, *getattr(pipe, "names", [])]
    stop_phrase = (wake_listen.STOP_PHRASE
                   if getattr(pipe, "_sherpa", None) is not None
                   and getattr(pipe, "stop_keyword", False) else "")
    voices = [(p.stem.split("-", 1)[-1], PiperVoice.load(str(p)))
              for p in sorted(PIPER.glob("*.onnx"))]
    if not voices:
        wake_test.write(OUT, {**snap, "status": "failed",
                              "error": "no Piper voice installed"})
        return 1
    plan = [(text, want, v, lvl)
            for text, want in clips(names, stop_phrase)
            for v in voices
            for lvl in (LEVELS if want else LEVELS[:1])]
    snap.update(status="running", total=len(plan), engine=pipe.engine,
                settings=_settings(cfg))
    rng = np.random.default_rng(17)
    results: list[dict] = []
    cache: dict = {}
    for i, (text, want, (vname, voice), level) in enumerate(plan):
        if stopped:
            break
        key = (vname, text)
        if key not in cache:
            cache[key] = synth(voice, text)
        woke, how = first_wake(pipe, frames(cache[key], level, rng))
        results.append({"text": text, "want": want, "woke": woke, "how": how,
                        "voice": vname, "level": level})
        snap.update(done=i + 1, **tally(results, names, stop_phrase))
        wake_test.write(OUT, snap)
    snap.update(status="stopped" if stopped else "done",
                seconds=int(time.time() - started), **tally(results, names, stop_phrase))
    wake_test.write(OUT, snap)
    return 0


def _settings(cfg) -> str:
    t = cfg.wake_tuning()
    return (f"threshold {cfg.get_int('sherpaThresholdPct')}% · boost "
            f"{int(t['short_boost'] * 100)}% · second check "
            f"{'on, ' + t['engines'] if cfg.get_bool('wakeCrossCheck') else 'off'}")


if __name__ == "__main__":
    PID.parent.mkdir(parents=True, exist_ok=True)
    PID.write_text(str(os.getpid()))
    try:
        code = main()
    except Exception as e:
        wake_test.write(OUT, {"mode": "auto", "status": "failed",
                              "error": f"{type(e).__name__}: {e}", "note": NOTE})
        code = 1
    finally:
        PID.unlink(missing_ok=True)
    raise SystemExit(code)
