#!/usr/bin/env python3
"""The accurate live transcript against the real Vosk and Whisper (item 6).

    ~/.local/share/agentvoice/venv/bin/python bench/live_text_bench.py

Piper says requests with pauses in them; the frames go through the daemon's
own `hear()` at real time (200ms a frame), with the real Vosk recogniser and
the real Whisper worker, exactly as a capture would. For each request:

- updates: how often the text on screen changed;
- swaps: how often Whisper's part grew (rough text replaced);
- fallbacks: how often Whisper's part shrank back to Vosk's -- the flicker
  the plan warned about. Must be 0;
- pause to swap: from the end of a pause-starting frame to Whisper's text
  appearing, in seconds;
- the last text shown against the transcript that is actually sent.

Synthesized voices: these say whether the swaps behave, not how accurate
Whisper is on you.
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "daemon"))

import wake_auto  # noqa: E402
from runtime import Config  # noqa: E402

RATE, FRAME = 16_000, 3200
PAUSE_S = 0.7

REQUESTS = [
    ["Can you open the settings page,", "and then turn the gate up a little?"],
    ["I want to rename the main agent.", "Call it Theo,", "and keep the wake word."],
    ["Check whether the tests pass.", "If any fail,", "tell me which ones."],
    ["Search the project for the word gate,", "then list the files."],
    ["What's the weather like tomorrow?"],
    ["Write a short note to the team.", "Say the build is green,", "and that I'll merge it tonight."],
]


class Self:
    """Just enough of the daemon for Daemon.hear."""

    def __init__(self, pipe):
        self.pipe = pipe


def main() -> int:
    from piper import PiperVoice

    import wake_listen
    cfg = Config()
    pipe = wake_listen.Pipeline(cfg)
    pipe._partials = "accurate"
    me = Self(pipe)
    hear = wake_listen.Daemon.hear
    voices = [(p.stem.split("-", 1)[-1], PiperVoice.load(str(p)))
              for p in sorted(wake_auto.PIPER.glob("*.onnx"))][:2]
    rng = np.random.default_rng(5)
    rows = []
    for vname, voice in voices:
        for parts in REQUESTS:
            chunks = [np.zeros(int(0.4 * RATE))]
            for j, p in enumerate(parts):
                if j:
                    chunks.append(np.zeros(int(PAUSE_S * RATE)))
                chunks.append(wake_auto.synth(voice, p))
            chunks.append(np.zeros(int(1.6 * RATE)))
            x = np.concatenate(chunks)
            x = x * (10 ** (-24 / 20) / (np.sqrt((x[x != 0] ** 2).mean()) + 1e-12))
            x = x + rng.standard_normal(len(x)) * 10 ** (-60 / 20)
            pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()
            frames = [pcm[i:i + FRAME * 2] for i in range(0, len(pcm) - FRAME * 2 + 1, FRAME * 2)]

            cap, utt = pipe.new_capture(), pipe.new_utterance()
            shown, updates, swaps, fallbacks = "", 0, 0, 0
            covered, cut_at, lags = 0, [], []
            t0 = time.time()
            for i, f in enumerate(frames):
                voiced = wake_listen.frame_db(f) >= pipe.threshold_db
                text = hear(me, cap, utt, f, voiced)
                _, cov = utt.whisper_so_far()
                if utt._sent and len(cut_at) < len(utt._sent):
                    cut_at.append(time.time())
                if cov > covered:
                    swaps += 1
                    if cut_at:
                        lags.append(time.time() - cut_at[-1])
                elif cov < covered:
                    fallbacks += 1
                covered = cov
                if text and text != shown:
                    updates += 1
                    shown = text
                # Real time: the next frame arrives 200ms after this one did.
                time.sleep(max(0.0, t0 + (i + 1) * 0.2 - time.time()))
            final, _ = utt.finish()
            rows.append({"voice": vname, "parts": len(parts), "updates": updates,
                         "swaps": swaps, "fallbacks": fallbacks, "lags": lags,
                         "same": shown.strip() == final.strip(),
                         "shown": shown, "final": final})
            print(f"{vname:14} parts {len(parts)}  updates {updates:3}  swaps {swaps}  "
                  f"fallbacks {fallbacks}  same {rows[-1]['same']!s:5}  "
                  f"lag {', '.join(f'{v:.2f}' for v in lags) or '-'}", flush=True)
            if not rows[-1]["same"]:
                print(f"    shown: {shown}\n    sent:  {final}")
    lags = [v for r in rows for v in r["lags"]]
    print(f"\n{len(rows)} requests · fallbacks {sum(r['fallbacks'] for r in rows)} · "
          f"last text = sent {sum(r['same'] for r in rows)}/{len(rows)} · "
          f"pause→swap median {statistics.median(lags):.2f}s, max {max(lags):.2f}s · "
          f"updates median {statistics.median(r['updates'] for r in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
