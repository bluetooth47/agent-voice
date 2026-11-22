#!/usr/bin/env python3
"""Run the command detector over your own saved chats, locally, and print
counts only (phase M4, notes/master-plan.md "Measure").

Every transcript in `~/.local/share/agentvoice/chats/` is run through
`speech_text.find_command` in each `commandsInSentences` mode. What comes
out is how many would fire, per mode, command and place -- never a word of
what was said. Nothing leaves the machine and nothing is written unless
asked for.

    python3 bench/commands_scan.py                 counts per mode
    python3 bench/commands_scan.py --sample FILE   also write each sentence
                                                   holding a command's words
                                                   to FILE (0600, your own
                                                   words), with the modes it
                                                   fires in and an empty
                                                   "meant" to fill in
    python3 bench/commands_scan.py --labels FILE   per mode: how many fired,
                                                   how many of those were not
                                                   meant (the false-trigger
                                                   rate), and how many meant
                                                   ones did not fire

The sample file holds transcripts, so it is created 0600 and refused if it
already exists; put it outside any folder something syncs or watches.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "daemon"))

from chats import CHATS_DIR, ChatStore  # noqa: E402
from runtime import Config  # noqa: E402
import speech_text  # noqa: E402
from speech_text import COMMAND_MODES, find_command  # noqa: E402


def transcripts(root: Path):
    """Each transcript the user said, from every saved chat. Typed ones too:
    the store does not say which were typed, and a sentence is a sentence."""
    store = ChatStore(root)
    for entry in store.list():
        chat = store.load(entry["id"])
        for ex in (chat or {}).get("exchanges", []):
            text = ex.get("transcript")
            if isinstance(text, str) and text.strip() and ex.get("kind") != "brief":
                yield text


def names_from_settings() -> tuple:
    cfg = Config()
    out = [cfg.get_str("phrase"), cfg.main_label()]
    for spec in cfg.agents():
        out += [spec["name"], spec["label"]]
    return tuple(" ".join(str(n).lower().split()) for n in out if n)


def scan(texts, names) -> dict:
    """Counts only: {"transcripts", "exact", "modes": {mode: {"fire",
    "by_command": {id: n}, "by_where": {where: n}}}}, and the rows that
    would fire (kept in memory, for --sample)."""
    counts = {"transcripts": 0, "exact": Counter(), "words": 0,
              "words_by_command": Counter(),
              "modes": {m: {"fire": 0, "by_command": Counter(),
                            "by_where": Counter()} for m in COMMAND_MODES}}
    rows = []
    for text in texts:
        counts["transcripts"] += 1
        # Held a command's words somewhere, whether or not anything fired:
        # the sentences the never-fires rules were deciding about.
        words = [w.lower().replace("'", "").replace("’", "")
                 for w in speech_text._WORD.findall(text)]
        hits = speech_text._hits(words)
        if hits:
            counts["words"] += 1
            for cid in {h[2].id for h in hits}:
                counts["words_by_command"][cid] += 1
        fired = {}
        for mode in COMMAND_MODES:
            found = find_command(text, mode, names)
            if found is None:
                continue
            if found.exact:
                if mode == "alone":
                    counts["exact"][found.command.id] += 1
                continue
            m = counts["modes"][mode]
            m["fire"] += 1
            m["by_command"][found.command.id] += 1
            m["by_where"][found.where] += 1
            fired[mode] = (found.command.id, found.where)
        if fired or hits:
            rows.append({"text": text, "fires": fired, "meant": None})
    return {"counts": counts, "rows": rows}


def print_counts(counts: dict) -> None:
    print(f"transcripts scanned: {counts['transcripts']}")
    exact = sum(counts["exact"].values())
    print(f"commands said on their own (as before M4): {exact}"
          + (f"  {dict(sorted(counts['exact'].items()))}" if exact else ""))
    print(f"held a command's words inside a sentence: {counts['words']}"
          + (f"  {dict(sorted(counts['words_by_command'].items()))}"
             if counts["words"] else ""))
    for mode in COMMAND_MODES:
        m = counts["modes"][mode]
        line = f"{mode:>6}: would fire inside a sentence {m['fire']}"
        if m["fire"]:
            line += (f"  by command {dict(sorted(m['by_command'].items()))}"
                     f"  by place {dict(sorted(m['by_where'].items()))}")
        print(line)


def write_sample(path: Path, rows: list) -> None:
    """Each would-fire sentence, for labelling. 0600, never overwritten."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        for row in rows:
            f.write(json.dumps({"text": row["text"],
                                "fires": {m: list(v) for m, v in row["fires"].items()},
                                "meant": None}) + "\n")


def rates(path: Path) -> dict:
    """{mode: (fired, fired but not meant, meant but did not fire)} from a
    labelled sample. "meant" is whether a command was meant at all."""
    out = {m: [0, 0, 0] for m in COMMAND_MODES}
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("meant") not in (True, False):
            continue
        fires = row.get("fires") or {}
        for mode in COMMAND_MODES:
            if mode in fires:
                out[mode][0] += 1
                out[mode][1] += row["meant"] is False
            elif row["meant"] is True:
                out[mode][2] += 1
    return {m: tuple(v) for m, v in out.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--chats", type=Path, default=CHATS_DIR,
                    help="the saved chats (default: %(default)s)")
    ap.add_argument("--sample", type=Path,
                    help="write the would-fire sentences here, for labelling")
    ap.add_argument("--labels", type=Path,
                    help="print the false-trigger rate from a labelled sample")
    args = ap.parse_args(argv)
    if args.labels:
        for mode, (n, bad, missed) in rates(args.labels).items():
            rate = f"{bad / n:.0%}" if n else "-"
            print(f"{mode:>6}: fired {n}, of them not meant {bad} ({rate}); "
                  f"meant but not fired {missed}")
        return 0
    result = scan(transcripts(args.chats), names_from_settings())
    print_counts(result["counts"])
    if args.sample:
        write_sample(args.sample, result["rows"])
        print(f"sample: {len(result['rows'])} sentences written to {args.sample} "
              "(0600): set each \"meant\" to true if a command was meant, else false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
