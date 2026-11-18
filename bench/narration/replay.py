#!/usr/bin/env python3
"""Replay recorded turns and print what progress talk would have said, and when.

    python bench/narration/replay.py                    # every turn, brief
    python bench/narration/replay.py --level detailed c11 c23
    python bench/narration/replay.py --summary          # the table only

Each recorded line goes through the adapter's own parser (claude_code's
`parse_line`, codex's `activity_chunks`), the agent's words through
`iter_sentences` as they would be spoken, and the activities through
`narration.Narrator` on the recorded clock. Nothing here is audio: speech
lengths are estimated at SPEECH_WPS words a second, so the times of the
agent's own sentences, and so of the gaps between them, are estimates.

The four targets from plan.md are checked on every turn:

- repeats: the same line twice in a turn;
- overlaps: a line still being said when the agent's next sentence is ready
  (it would be cut at the next word break);
- invented: a line made from an activity that had not happened yet;
- secrets: a line that looks like it holds a key, names a secret file, or
  quotes a command line.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "daemon"))

import narration  # noqa: E402
from adapters.claude_code import parse_line  # noqa: E402
from adapters.codex import _NOT_SPEECH, _harvest_text, activity_chunks  # noqa: E402
from adapters.base import Chunk  # noqa: E402
from speech_text import FLUSH, iter_sentences  # noqa: E402

TURNS = HERE / "turns"

#: Piper at speed 1.0, roughly: 165 words a minute, plus a breath.
SPEECH_WPS = 2.75
SPEECH_PAD_S = 0.3
TICK_S = 0.25


def speech_s(text: str) -> float:
    return SPEECH_PAD_S + len(text.split()) / SPEECH_WPS


def load(path: Path):
    lines = path.read_text().splitlines()
    head = json.loads(lines[0])
    return head, [json.loads(x) for x in lines[1:]]


def chunks(head: dict, entries: list[dict]):
    """(seconds, Chunk) for the turn, through the adapters' own parsing."""
    started: set[str] = set()
    for entry in entries:
        t, msg = entry["t"] / 1000.0, entry["msg"]
        if head["backend"] == "claude":
            if msg.get("type") == "result":
                yield t, Chunk(done=True)
                return
            for c in parse_line(msg):
                yield t, c
        else:
            kind = str(msg.get("type", ""))
            if kind.startswith("item."):
                item = msg.get("item") or msg
                for c in activity_chunks(kind, item, started):
                    yield t, c
                itype = str(item.get("type", ""))
                if itype in ("command_execution", "mcp_tool_call") or itype in _NOT_SPEECH:
                    continue
                if kind == "item.completed":
                    found = _harvest_text(item)
                    if found.strip():
                        yield t, Chunk(text=found)
            elif kind == "turn.completed":
                yield t, Chunk(done=True)
                return


class Turn:
    def __init__(self, path: Path, level: str):
        self.head, entries = load(path)
        self.level = level
        self.events: list[tuple[float, str, str]] = []   # (t, who, text)
        self.narrator = narration.Narrator(level)
        self.free_at = 0.0          # when the voice is next free
        self.speaking_line = None   # (line, ends)
        self.cuts = 0
        self.tools = 0
        self.commands: list[str] = []
        self.answer_at = None
        self.end = 0.0
        self._run(entries)

    def _say_due(self, upto: float, now_ref: list) -> None:
        t = now_ref[0]
        while t < upto:
            if t >= self.free_at:
                line = self.narrator.due(t)
                if line is not None:
                    ends = t + speech_s(line.spoken)
                    self.events.append((t, "NARRATE", line.text))
                    self.speaking_line = (line, ends)
                    self.free_at = ends
                    self.narrator.spoke(ends)
            t += TICK_S
        now_ref[0] = max(now_ref[0], upto)

    def _run(self, entries: list[dict]) -> None:
        now = [0.0]
        detailed = self.level == "detailed"
        stream = list(chunks(self.head, entries))

        def deltas():
            for t, c in stream:
                self._say_due(t, now)
                if c.activity:
                    a = c.activity
                    act = narration.describe(a["name"], a["input"],
                                             detailed=detailed, helper=a["helper"])
                    self.narrator.activity(act, t, a["id"])
                    self.tools += 1
                    inp = a["input"] or {}
                    what = inp.get("command") or inp.get("file_path") or \
                        inp.get("pattern") or inp.get("query") or inp.get("url") or \
                        inp.get("description") or ""
                    if inp.get("command"):
                        self.commands.append(str(inp["command"]))
                    tag = "helper" if a["helper"] else "tool"
                    self.events.append((t, tag, f"{a['name']} {str(what)[:70]}"))
                if c.tool:
                    yield FLUSH
                if c.tool_done:
                    self.narrator.finished(c.tool_done)
                if c.text:
                    self.narrator.text()
                    yield c.text
                if c.done:
                    self.end = t

        for sentence in iter_sentences(deltas()):
            t = now[0]
            if self.speaking_line and self.speaking_line[1] > t:
                self.cuts += 1
                self.events.append((t, "CUT", self.speaking_line[0].text))
                self.free_at = t
            self.speaking_line = None
            start = max(t, self.free_at)
            ends = start + speech_s(sentence)
            self.free_at = ends
            self.narrator.agent_said(sentence, ends)
            self.events.append((start, "says", sentence))
        self.end = self.end or now[0]

    # --- the four targets ---------------------------------------------------

    def problems(self) -> dict[str, int]:
        lines = self.narrator.lines
        texts = [x.text for x in lines]
        invented = sum(1 for x in lines if any(a.t > x.t for a in x.sources)
                       or not x.sources)
        secret = 0
        for x in lines:
            if narration.looks_secret(x.text) or narration.looks_secret(x.spoken):
                secret += 1
            elif any(len(cmd) > 8 and cmd in x.text for cmd in self.commands):
                secret += 1
            elif "sk-test" in x.text:
                secret += 1
        return {"repeats": len(texts) - len(set(texts)), "overlaps": self.cuts,
                "invented": invented, "secrets": secret}

    def print(self) -> None:
        h = self.head
        print(f"\n{h['id']}  {h['backend']}  {self.end:.1f}s  {self.tools} tools  "
              f"— {h['prompt']}")
        for t, who, text in sorted(self.events, key=lambda e: e[0]):
            mark = {"NARRATE": ">>", "CUT": "xx"}.get(who, "  ")
            print(f"  {mark} {t:6.1f}  {who:7}  {text}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--level", default="brief", choices=("brief", "detailed"))
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args(argv)
    paths = sorted(TURNS.glob("*.jsonl"))
    if args.ids:
        paths = [p for p in paths if p.stem in args.ids]
    totals = {"repeats": 0, "overlaps": 0, "invented": 0, "secrets": 0}
    rows = []
    said = 0
    for p in paths:
        turn = Turn(p, args.level)
        if not args.summary:
            turn.print()
        probs = turn.problems()
        for k, v in probs.items():
            totals[k] += v
        said += len(turn.narrator.lines)
        rows.append((p.stem, turn.end, turn.tools, len(turn.narrator.lines), probs))
    print(f"\n{'turn':5} {'secs':>6} {'tools':>5} {'lines':>5}  problems")
    for pid, end, tools, n, probs in rows:
        bad = ", ".join(f"{k} {v}" for k, v in probs.items() if v) or "-"
        print(f"{pid:5} {end:6.1f} {tools:5} {n:5}  {bad}")
    print(f"\n{len(rows)} turns, {said} lines ({args.level}); "
          + ", ".join(f"{k} {v}" for k, v in totals.items()))
    return 1 if any(totals.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
