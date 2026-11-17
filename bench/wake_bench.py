#!/usr/bin/env python3
"""Score wake engines on the corpus bench/wake_clips.py writes.

    # Vosk, through the daemon's real Pipeline.feed_wake (needs the daemon venv)
    ~/.local/share/agentvoice/venv/bin/python bench/wake_bench.py vosk CLIPS

    # sherpa-onnx keyword spotting (needs `pip install sherpa-onnx sentencepiece`)
    PY bench/wake_bench.py sherpa CLIPS --model DIR [--threshold 0.25 --score 1.0]

    # sherpa-onnx through the daemon's Pipeline -- the shipped path, not the
    # prototype above -- with the model at DIR rather than the installed one
    PY bench/wake_bench.py daemon-sherpa CLIPS --model DIR [--threshold 0.25]

    # side by side
    python3 bench/wake_bench.py compare CLIPS/results-*.json

Phrase "computer", one extra agent "sarah", as in FINDINGS §22. Each clip is
fed in 200ms frames from a fresh detector, and its first firing (if any) is
recorded. Writes CLIPS/results-<label>.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RATE, CHUNK = 16_000, 3200
PHRASE, NAMES = "computer", ["sarah"]


def clips(d: Path):
    for m in json.loads((d / "manifest.json").read_text()):
        with wave.open(str(d / m["file"])) as w:
            yield m, w.readframes(w.getnframes())


# --- Vosk: the daemon's own code path --------------------------------------

def run_vosk(d: Path, args) -> tuple[str, list]:
    sys.path.insert(0, str(HERE.parent / "daemon"))
    import vosk
    import wake_listen
    vosk.SetLogLevel(-1)
    pipe = object.__new__(wake_listen.Pipeline)
    pipe._vosk, pipe._model = vosk, None
    pipe.phrase, pipe._oww = PHRASE, None
    pipe._choose_names(NAMES)
    pipe.threshold_db = args.gate
    pipe.min_loud_frames = max(1, 600 // wake_listen.CHUNK_MS)
    pipe.wake_confidence = args.confidence
    pipe.refractory_ms, pipe._log_speech = 2000, False
    out = []
    for m, pcm in clips(d):
        pipe._reset_wake()
        pipe._refractory_until, pipe._loud_frames = 0.0, 0
        hit, at, cpu = "", None, 0.0
        for i in range(0, len(pcm), CHUNK * 2):
            frame = pcm[i:i + CHUNK * 2]
            t0 = time.process_time()
            fired = pipe.feed_wake(frame, wake_listen.frame_db(frame))
            cpu += time.process_time() - t0
            if fired:
                hit, at = pipe.heard_phrase, (i // 2) / RATE
                break
        out.append({**m, "hit": hit, "at": at, "cpu": cpu})
    return f"vosk-c{int(args.confidence * 100)}", out


def run_daemon_sherpa(d: Path, args) -> tuple[str, list]:
    sys.path.insert(0, str(HERE.parent / "daemon"))
    import wake_listen
    wake_listen.sherpa_model = lambda: Path(args.model)

    class Cfg(dict):
        def get_str(self, k): return str(self[k])
        def get_int(self, k): return int(self[k])
        def agents(self): return [{"name": n} for n in NAMES]

    cfg = Cfg(phrase=PHRASE, sherpaThresholdPct=round(args.threshold * 100))
    pipe = object.__new__(wake_listen.Pipeline)
    pipe._oww = pipe._sherpa = pipe._model = None
    pipe._partials = "auto"
    pipe.refractory_ms, pipe._log_speech = 2000, False
    pipe._build_wake(cfg, "sherpa")
    assert pipe._sherpa is not None, "fell back to Vosk"
    out = []
    for m, pcm in clips(d):
        pipe._sherpa.listen_for(pipe._sherpa.phrases, pipe._sherpa.threshold)
        pipe._refractory_until = 0.0
        hit, at, cpu = "", None, 0.0
        for i in range(0, len(pcm), CHUNK * 2):
            frame = pcm[i:i + CHUNK * 2]
            t0 = time.process_time()
            fired = pipe.feed_wake(frame, wake_listen.frame_db(frame))
            cpu += time.process_time() - t0
            if fired:
                hit, at = pipe.heard_phrase, (i // 2) / RATE
                break
        out.append({**m, "hit": hit, "at": at, "cpu": cpu})
    return f"daemon-sherpa-t{round(args.threshold * 100)}", out


# --- sherpa-onnx keyword spotting ------------------------------------------

def keywords_for(model: Path, words: list[str], boost: float, thr: float) -> str:
    """The keywords-file text for `words`, in whichever unit the model uses."""
    lines = []
    if (model / "bpe.model").exists():
        import sentencepiece as spm
        sp = spm.SentencePieceProcessor(model_file=str(model / "bpe.model"))
        for w in words:
            toks = " ".join(sp.encode(w.upper(), out_type=str))
            lines.append(f"{toks} :{boost} #{thr} @{w}")
    else:
        lex = {}
        for line in (model / "en.phone").read_text().splitlines():
            parts = line.split()
            if parts:
                lex.setdefault(parts[0].upper(), parts[1:])
        for w in words:
            phones = [p for word in w.upper().split() for p in lex[word]]
            lines.append(f"{' '.join(phones)} :{boost} #{thr} @{w}")
    return "\n".join(lines)


def run_sherpa(d: Path, args) -> tuple[str, list]:
    import sherpa_onnx
    model = Path(args.model)
    pick = lambda part: str(sorted(model.glob(
        f"{part}-*chunk-{args.chunk}-*{'.int8' if args.int8 else ''}.onnx"))[0])
    kw = keywords_for(model, [PHRASE, *NAMES], args.score, args.threshold)
    kw_file = d / f".kw-{model.name}.txt"
    kw_file.write_text(kw + "\n")
    kws = sherpa_onnx.KeywordSpotter(
        tokens=str(model / "tokens.txt"), encoder=pick("encoder"),
        decoder=str(sorted(model.glob(f"decoder-*chunk-{args.chunk}-*.onnx"))[0]),
        joiner=pick("joiner"), keywords_file=str(kw_file), num_threads=1,
        keywords_score=args.score, keywords_threshold=args.threshold,
        num_trailing_blanks=args.trailing_blanks, max_active_paths=4)
    out = []
    for m, pcm in clips(d):
        s = kws.create_stream()
        hit, at, cpu = "", None, 0.0
        for i in range(0, len(pcm), CHUNK * 2):
            x = np.frombuffer(pcm[i:i + CHUNK * 2], np.int16).astype(np.float32) / 32768
            t0 = time.process_time()
            s.accept_waveform(RATE, x)
            while kws.is_ready(s):
                kws.decode_stream(s)
                r = kws.get_result(s)
                if r and not hit:
                    hit, at = r, (i // 2) / RATE
                    kws.reset_stream(s)
            cpu += time.process_time() - t0
            if hit:
                break
        out.append({**m, "hit": hit, "at": at, "cpu": cpu})
    tag = "gigaspeech" if "gigaspeech" in model.name else "zh-en"
    label = (f"sherpa-{tag}-t{int(args.threshold * 100)}-s{args.score:g}"
             f"-c{args.chunk}{'-int8' if args.int8 else ''}")
    return label, out


# --- comparison ------------------------------------------------------------

def summarise(rows: list) -> dict:
    pos = [r for r in rows if r["want"]]
    neg = [r for r in rows if not r["want"]]
    by_text = {}
    for r in pos:
        k = r["text"]
        ok = r["hit"] == r["want"]
        a, b = by_text.get(k, (0, 0))
        by_text[k] = (a + ok, b + 1)
    false = [r for r in neg if r["hit"]]
    wrong = [r for r in pos if r["hit"] and r["hit"] != r["want"]]
    audio = sum(len_s(r) for r in rows)
    return {"by_text": by_text,
            "hits": sum(r["hit"] == r["want"] for r in pos), "pos": len(pos),
            "false": false, "neg": len(neg), "wrong": wrong,
            "rtf": sum(r["cpu"] for r in rows) / audio,
            "delay": [r["at"] - 0.6 - r["speech_s"] for r in pos
                      if r["hit"] == r["want"] and r["at"] is not None]}


def len_s(r):            # audio fed: lead + speech + tail, or up to the hit
    return (r["at"] + 0.2) if r["at"] is not None else 0.6 + r["speech_s"] + 1.2


def compare(files: list[Path]) -> None:
    res = {json.loads(f.read_text())["label"]: summarise(json.loads(f.read_text())["rows"])
           for f in files}
    labels = list(res)
    texts = list(next(iter(res.values()))["by_text"])
    w = max(len(t) for t in texts) + 2
    print("| clip".ljust(w + 2) + "| " + " | ".join(labels) + " |")
    print("|" + "-" * (w + 1) + "|" + "|".join("-" * (len(l) + 2) for l in labels) + "|")
    for t in texts:
        cells = [f"{res[l]['by_text'][t][0]} / {res[l]['by_text'][t][1]}".ljust(len(l))
                 for l in labels]
        print(f"| {t}".ljust(w + 2) + "| " + " | ".join(cells) + " |")
    row = lambda name, f: print(f"| {name}".ljust(w + 2) + "| "
                                + " | ".join(f(res[l]).ljust(len(l)) for l in labels) + " |")
    row("**detected**", lambda s: f"{s['hits']} / {s['pos']}")
    row("**false wakes**", lambda s: f"{len(s['false'])} / {s['neg']}")
    row("wrong agent", lambda s: f"{len(s['wrong'])}")
    row("median delay after speech", lambda s:
        f"{np.median(s['delay']):.2f}s" if s["delay"] else "-")
    row("CPU (fraction of 1 core)", lambda s: f"{s['rtf'] * 100:.1f}%")
    for l in labels:
        print(f"\n{l} false wakes:")
        for r in res[l]["false"]:
            print(f"  {r['voice']:7} {int(r['level'])} {r['text']!r} -> {r['hit']}")
        for r in res[l]["wrong"]:
            print(f"  WRONG {r['voice']:7} {int(r['level'])} {r['text']!r} -> {r['hit']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("engine", choices=["vosk", "sherpa", "daemon-sherpa", "compare"])
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--gate", type=float, default=-38.0)
    ap.add_argument("--confidence", type=float, default=0.70)
    ap.add_argument("--model")
    ap.add_argument("--threshold", type=float, default=0.25)
    ap.add_argument("--score", type=float, default=1.0)
    ap.add_argument("--chunk", type=int, default=16)
    ap.add_argument("--int8", action="store_true")
    ap.add_argument("--trailing-blanks", type=int, default=1)
    args = ap.parse_args()
    if args.engine == "compare":
        return compare(args.paths)
    d = args.paths[0]
    run = {"vosk": run_vosk, "sherpa": run_sherpa,
           "daemon-sherpa": run_daemon_sherpa}[args.engine]
    label, rows = run(d, args)
    (d / f"results-{label}.json").write_text(json.dumps({"label": label, "rows": rows}))
    s = summarise(rows)
    print(f"{label}: detected {s['hits']}/{s['pos']}, "
          f"false {len(s['false'])}/{s['neg']}, wrong {len(s['wrong'])}, "
          f"cpu {s['rtf'] * 100:.1f}%")


if __name__ == "__main__":
    main()
