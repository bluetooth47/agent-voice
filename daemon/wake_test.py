"""Test my wake word: say the name ten times, see how many woke it.

Started from the Listening page (`agentvoice wake-test start`). While it
runs, a wake is counted instead of opening a turn, every burst of speech is
counted as an attempt, and what the engines rejected is kept as near
misses, so a hit rate can be read off the screen instead of guessed from the
journal.

An attempt is a burst of speech between 0.2s and 4s: wider than the second
check's window, because the point is to count what the person said, not
what the check would look at. Talking about something else while it runs
counts as attempts too, so the screen says "say only the name".

Pure: the daemon feeds it events and writes `snapshot()` to a file in the
runtime directory (tmpfs, 0600), which the settings page watches. That file
always exists while the daemon runs (IDLE when there is no test). Nothing
said is stored, only names the engines produced and their reasons.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

#: How many times the page asks for the name.
TARGET = 10
#: The test ends by itself after this long, so a forgotten one never leaves
#: wakes being swallowed.
LIMIT_S = 90.0
#: The attempt window, in ms. See the module docstring.
MIN_ATTEMPT_MS = 200
MAX_ATTEMPT_MS = 4000
#: Near misses kept for the screen.
NEAR_MAX = 12


class WakeTest:
    def __init__(self, now: float | None = None, target: int = TARGET,
                 limit_s: float = LIMIT_S) -> None:
        self.started = time.time() if now is None else now
        self.ends = self.started + limit_s
        self.target = target
        self.attempts = 0
        self.hits: list[dict] = []
        self.near: list[str] = []
        #: "running", then "done" (target reached), "timeout" or "stopped".
        self.status = "running"
        #: The loudest frame heard, and the gate it had to clear to count as
        #: a try: the answer to "0 of 0" is usually that one was under the
        #: other.
        self.peak_db = -99.0
        self.gate_db = 0.0

    @property
    def running(self) -> bool:
        return self.status == "running"

    def on_attempt(self) -> None:
        if self.running:
            self.attempts += 1

    def on_level(self, level_db: float, gate_db: float) -> None:
        if self.running:
            self.peak_db = max(self.peak_db, level_db)
            self.gate_db = gate_db

    def on_wake(self, name: str, how: str) -> None:
        if not self.running:
            return
        self.hits.append({"name": name, "how": how})
        if len(self.hits) >= self.target:
            self.status = "done"

    def on_near(self, why: str) -> None:
        if self.running and why:
            self.near = (self.near + [why])[-NEAR_MAX:]

    def tick(self, now: float | None = None) -> bool:
        """End it on time. True when this call ended it."""
        if self.running and (time.time() if now is None else now) >= self.ends:
            self.status = "timeout"
            return True
        return False

    def stop(self) -> None:
        if self.running:
            self.status = "stopped"

    def snapshot(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        # A wake lands during its burst and the burst is counted when it
        # ends, so for a moment there can be a hit with no attempt yet.
        tries = max(self.attempts, len(self.hits))
        return {
            "mode": "manual",
            "status": self.status,
            "target": self.target,
            "hits": len(self.hits),
            "attempts": tries,
            "rate": round(len(self.hits) / tries, 2) if tries else 0.0,
            "by": [h["name"] + " · " + h["how"] for h in self.hits],
            "near": list(self.near),
            "left_s": max(0, int(self.ends - now)) if self.running else 0,
            "peak_db": round(self.peak_db, 1),
            "gate_db": round(self.gate_db, 1),
        }


#: What "no test" is written as. Never a missing file: the page's watcher
#: cannot watch a file that does not exist yet, so a test that created it
#: was never seen -- the button stayed "Start test" and nothing showed.
IDLE = {"status": ""}


def write(path: Path, snap: dict | None) -> None:
    """The snapshot for the page; None writes IDLE."""
    if snap is None:
        snap = IDLE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(snap, f)
        tmp.replace(path)
    except OSError as e:     # a readout must never stop the daemon
        print(f"wake test: {type(e).__name__}: {e}", flush=True)
