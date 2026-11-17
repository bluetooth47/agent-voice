#!/usr/bin/env python3
"""Synthesize the wake-word corpus that wake_bench.py scores engines on.

Same recipe as FINDINGS §22, widened: every installed Piper voice, speech
scaled to -20 and -28 dBFS RMS, over -60 dBFS white noise, with 0.6s of
noise before and 1.2s after so an engine hears the pause a person leaves.

    ~/.local/share/agentvoice/venv/bin/python bench/wake_clips.py OUT_DIR

Writes OUT_DIR/*.wav (16 kHz mono int16) and OUT_DIR/manifest.json.
Synthesized speech is not a person in a room: use the numbers to compare
engines with each other, not as detection rates.
"""
from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np

MODELS = Path.home() / ".local/share/agentvoice/models/piper"
RATE = 16_000
LEVELS = (-20.0, -28.0)
NOISE_DB = -60.0
LEAD_S, TAIL_S = 0.6, 1.2

#: (text, which phrase should fire, or "" for none)
TARGETS = [
    ("Computer", "computer"),
    ("Sarah", "sarah"),
    ("Hey Sarah", "sarah"),
    ("Sarah, what time is it", "sarah"),
    ("Computer, open the browser", "computer"),
]

#: The §22 sound-alikes and the words that already false-woke, then more
#: near misses, then ordinary talk.
DISTRACTORS = [
    "Sahara", "Zara", "Commuter", "Sorrow", "Okay", "Sounds good", "Salad",
    "Zero", "Sierra", "Serena", "Sarong", "Seriously", "Cucumber",
    "Computation", "Competitor", "Compute", "Carrot", "Hello there",
    "Thank you",
    "I think we should get lunch at noon and then go back to work.",
    "The weather is supposed to be cold and rainy all week.",
    "Can you send me that file when you get a chance?",
    "She said the meeting moved to Thursday afternoon.",
    "My sister bought a new car last weekend.",
    "We are going to need a bigger table for the party.",
]


def synth(voice, text: str) -> np.ndarray:
    raw = b"".join(getattr(c, "audio_int16_bytes", c)
                   for c in voice.synthesize(text))
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    src = getattr(voice.config, "sample_rate", 22050)
    if src != RATE:
        n = int(round(len(x) * RATE / src))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    return x


def rms_db(x: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-12))


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    from piper import PiperVoice

    rng = np.random.default_rng(22)
    manifest = []
    for onnx in sorted(MODELS.glob("*.onnx")):
        voice = PiperVoice.load(str(onnx))
        vname = onnx.stem.replace("en_US-", "").replace("-medium", "")
        for text, want in [*TARGETS, *((d, "") for d in DISTRACTORS)]:
            speech = synth(voice, text)
            # Trim Piper's own silence so the level is the speech's level.
            loud = np.flatnonzero(np.abs(speech) > 0.01)
            speech = speech[loud[0]:loud[-1] + 1]
            for level in LEVELS:
                s = speech * 10 ** ((level - rms_db(speech)) / 20)
                pad = lambda sec: np.zeros(int(sec * RATE), np.float32)
                x = np.concatenate([pad(LEAD_S), s, pad(TAIL_S)])
                x = x + rng.standard_normal(len(x)) * 10 ** (NOISE_DB / 20)
                pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
                slug = "".join(c if c.isalnum() else "_" for c in text.lower())[:40]
                name = f"{vname}_{int(-level)}_{slug}.wav"
                with wave.open(str(out / name), "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(RATE)
                    w.writeframes(pcm.tobytes())
                manifest.append({"file": name, "text": text, "want": want,
                                 "voice": vname, "level": level,
                                 "speech_s": round(len(s) / RATE, 2)})
        print(f"  {vname}: done")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"{len(manifest)} clips in {out}")


if __name__ == "__main__":
    main()
