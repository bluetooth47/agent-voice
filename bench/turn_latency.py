#!/usr/bin/env python3
"""Per-agent turn latency, read back out of the journal.

Every voice turn already prints one structural line (`report_latency` in
daemon/wake_listen.py):

    heard → spoke in 4.7s  (pause 1.5s · whisper 0.0s · claude warm 2.4s · ...)

That number is end of speech to first word. ("heard → showed" is the same
line for a reply that was displayed but not spoken; it is a different
measurement and is left out.) It names the *adapter*, not the agent, so the
agent is worked out from the status lines around it, in this order:

1. the `● still listening (Ns for <name> ...)` line the daemon prints when
   the follow-up window opens, within a few seconds *after* the reply: it
   names the agent that just answered;
2. otherwise the agent that started the capture: `● wake <name>`,
   `● <name> stopping it`, `● go on (talked over <name>`;
3. otherwise `?`. A turn whose adapter disagrees with that agent's program
   is `?` too: a follow-up can be taken by another agent named mid-window.

Names are accepted only from the daemon's own start-up lines (the main wake
phrase and each `agent “<label>”` line) plus the old phrases below, matched
against whole status lines. Anything else reads as `?`, so a transcript that
reached the journal with `logSpeech` on can never be echoed as a name.

Two agents answering at once can still be confused when they share an
adapter: the journal has no turn id to join on. Treat a per-agent split
where agents overlapped as approximate.

Wake to first word is not printed anywhere, so it is derived, and only for a
turn a named wake started with nothing in between: the `N.Ns audio, whisper`
line is printed when transcription finished, and the first word came
`total - pause - whisper` after that. It includes the time spent asking.

    python bench/turn_latency.py                       # last 30 days
    python bench/turn_latency.py --build 2eeb919
    python bench/turn_latency.py --json

A `--since` that starts after the service started misses that start's build
line, so those turns have no build and `--build` drops them; widen the window.
Run it with `logSpeech` off (the default) for a baseline: with it on, a
spoken line shaped exactly like a latency line would be counted. Reads
timings and names only, and writes nothing.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys

ANSI = re.compile(r"\x1b\[[0-9;]*m")
BUILD = re.compile(r"\s*knobs: .* build \S+ \(([0-9a-f]+)\)\s*$")
MAIN = re.compile(r'\s*listening for "([^"]+)"')
MAIN_PROGRAM = re.compile(r"\s*agent: (\w+) · voice: ")
CONF = re.compile(r"\s*agent “([^”]+)”: (\w+) ·")
WAKE = re.compile(r"\s*● wake(?: (.*?))?\s{2}(go ahead|stopping)")
STOP = re.compile(r"\s*● (.+?)\s{2}stopping it — go ahead\s*$")
OVER = re.compile(r"\s*● go on\s{2}\(talked over (.+?) — listening\)\s*$")
FOLLOW = re.compile(
    r"\s*● still listening\s{2}\([\d.]+s for (.+?) — or say a name\)\s*$")
STATUS = re.compile(r"\s*● ")
AUDIO = re.compile(r"\s*[\d.]+s audio, whisper \d+ms")
HEARD = re.compile(r"\s*heard → spoke in (\d+(?:\.\d+)?)s\s+\((.*)\)\s*$")
SPAN = re.compile(r"(?:^| · )([a-z][a-z ]*?) (\d+(?:\.\d+)?)s")
ADAPTERS = ("claude", "codex", "gemini", "agy", "copilot", "endpoint")

# Wake phrases this machine has used, mapped to the agent that answered.
# "computer" and "sarah" were Theo's and Sora's earlier phrases; "jarvis" was
# Hazel's (her id is still jarvis-ajc).
ALIASES = {"theo": "Theo", "computer": "Theo", "hey computer": "Theo",
           "sora": "Sora", "sarah": "Sora", "hazel": "Hazel",
           "jarvis": "Hazel"}
MAIN_NAME = "Theo"
FOLLOW_WINDOW_S = 5.0
#: Names are learned only this soon after a service start's build line, where
#: the daemon announces its agents. A reply shaped like an announcement later
#: on (with logSpeech on) cannot add a name; an agent added mid-session reads
#: as "?" until the next start.
ROSTER_WINDOW_S = 30.0


def journal(since: str) -> list[tuple[float, str]]:
    proc = subprocess.run(
        ["journalctl", "--user", "-u", "agentvoice", "--since", since,
         "-o", "json", "--output-fields=MESSAGE,__REALTIME_TIMESTAMP"],
        capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"journalctl failed ({proc.returncode}): "
                         f"{proc.stderr.strip()[:200]}")
    lines = []
    for raw in proc.stdout.splitlines():
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        msg = rec.get("MESSAGE")
        if isinstance(msg, list):  # journald stores non-UTF-8 as bytes
            msg = bytes(msg).decode("utf-8", "replace")
        if not isinstance(msg, str):
            continue
        lines.append((int(rec["__REALTIME_TIMESTAMP"]) / 1e6,
                      ANSI.sub("", msg)))
    return lines


class Roster:
    """The names one service start announced, and each one's program."""

    def __init__(self):
        self.programs: dict[str, str | None] = {}
        self.extras = 0

    @staticmethod
    def _key(raw: str) -> str:
        return " ".join(raw.lower().split())

    def learn(self, raw: str, program: str | None, extra: bool) -> None:
        key = self._key(raw)
        name = ALIASES.get(key, key.title())
        if program or name not in self.programs:
            self.programs[name] = program
        self.extras += extra

    def name(self, raw: str) -> str | None:
        """A name this start announced (or an old alias), else None."""
        key = self._key(raw)
        if key in ALIASES:
            return ALIASES[key]
        return key.title() if key.title() in self.programs else None


def turns(lines):
    """One record per spoken latency line, with the agent it belonged to."""
    roster, build, started = Roster(), None, None
    agent = None            # who the current capture is for
    wake_ts = audio_ts = None
    pending = None          # a turn waiting for its follow-up line

    def flush():
        nonlocal pending
        rec, pending = pending, None
        if rec is not None:
            prog = roster.programs.get(rec["agent"])
            if prog and rec["backend"] and prog != rec["backend"]:
                rec["agent"] = "?"
        return rec

    for ts, msg in lines:
        if pending is not None and ts - pending["ts"] > FOLLOW_WINDOW_S:
            yield flush()
        if m := BUILD.match(msg):
            if pending is not None:
                yield flush()
            roster, build, agent, started = Roster(), m.group(1), None, ts
            wake_ts = audio_ts = None
        elif (started is not None and ts - started <= ROSTER_WINDOW_S
              and (m := MAIN.match(msg))):
            roster.learn(m.group(1), None, extra=False)
            roster.learn(MAIN_NAME, None, extra=False)
        elif (started is not None and ts - started <= ROSTER_WINDOW_S
              and (m := MAIN_PROGRAM.match(msg))):
            roster.programs[MAIN_NAME] = m.group(1)
        elif (started is not None and ts - started <= ROSTER_WINDOW_S
              and (m := CONF.match(msg))):
            roster.learn(m.group(1), m.group(2), extra=True)
        elif m := FOLLOW.match(msg):
            name = roster.name(m.group(1))
            if pending is not None:
                pending["agent"] = name or "?"
                yield flush()
            agent, wake_ts, audio_ts = name, None, None
        elif m := WAKE.match(msg):
            raw = (m.group(1) or "").strip()
            if raw:
                agent = roster.name(raw)
            else:
                # A nameless wake is the main agent's only when there is no
                # other agent it could be.
                agent = MAIN_NAME if roster.extras == 0 else None
            wake_ts = ts if (raw and m.group(2) == "go ahead") else None
            audio_ts = None
        elif (m := STOP.match(msg)) or (m := OVER.match(msg)):
            agent, wake_ts, audio_ts = roster.name(m.group(1)), None, None
        elif (STATUS.match(msg) or "(nothing heard)" in msg
              or msg.strip() == "interrupted"):
            # Any other capture transition (open mic, a stop with no name):
            # the last wake no longer starts the next turn.
            wake_ts = audio_ts = None
        elif AUDIO.match(msg):
            audio_ts = ts
        elif m := HEARD.match(msg):
            if pending is not None:
                yield flush()
            total = float(m.group(1))
            spans = {k.strip(): float(v) for k, v in SPAN.findall(m.group(2))}
            backend = next((k.split()[0] for k in spans
                            if k.split()[0] in ADAPTERS), None)
            wake_to_word = None
            if wake_ts is not None and audio_ts is not None:
                word_ts = (audio_ts + total - spans.get("pause", 0.0)
                           - spans.get("whisper", 0.0))
                wake_to_word = round(word_ts - wake_ts, 2)
            pending = {"agent": agent or "?", "build": build,
                       "backend": backend, "end_to_word": total,
                       "wake_to_word": wake_to_word,
                       "warm": any(k.endswith(" warm") for k in spans),
                       "ts": ts}
            wake_ts = audio_ts = None
    if pending is not None:
        yield flush()


def pct(values, p):
    if not values:
        return None
    s = sorted(values)
    # nearest rank, so p95 of 20 values is the 19th, not an interpolation
    k = max(0, min(len(s) - 1, -(-p * len(s) // 100) - 1))
    return s[int(k)]


def summary(rows):
    out = {}
    for agent in sorted({r["agent"] for r in rows}):
        mine = [r for r in rows if r["agent"] == agent]
        e2w = [r["end_to_word"] for r in mine]
        w2w = [r["wake_to_word"] for r in mine if r["wake_to_word"] is not None]
        out[agent] = {
            "turns": len(mine),
            "backend": sorted({r["backend"] for r in mine if r["backend"]}),
            "end_to_word_median": statistics.median(e2w) if e2w else None,
            "end_to_word_p95": pct(e2w, 95),
            "wake_turns": len(w2w),
            "wake_to_word_median": statistics.median(w2w) if w2w else None,
            "wake_to_word_p95": pct(w2w, 95),
        }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--since", default="-30 days")
    ap.add_argument("--build", help="only turns on this build (short sha)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rows = list(turns(journal(a.since)))
    if a.build:
        rows = [r for r in rows if r["build"] and r["build"].startswith(a.build)]
    s = summary(rows)
    if a.json:
        print(json.dumps(s, indent=2))
        return 0
    print(f"{'agent':8} {'turns':>5}  {'end→word med':>12} {'p95':>6}"
          f"   {'wake turns':>10} {'wake→word med':>13} {'p95':>6}  backend")
    for agent, v in s.items():
        f = lambda x: "-" if x is None else f"{x:.1f}s"  # noqa: E731
        print(f"{agent:8} {v['turns']:>5}  {f(v['end_to_word_median']):>12} "
              f"{f(v['end_to_word_p95']):>6}   {v['wake_turns']:>10} "
              f"{f(v['wake_to_word_median']):>13} {f(v['wake_to_word_p95']):>6}"
              f"  {','.join(v['backend'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
