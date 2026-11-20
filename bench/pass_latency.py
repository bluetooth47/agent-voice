#!/usr/bin/env python3
"""A pass against a direct turn to the same target, on the running daemon
(merged plan, Phase 15, A15-6).

For each round, interleaved so drift cancels:

- **direct**: `agentvoice type TARGET` with a synthetic one-line question;
- **pass**: `agentvoice pass TARGET --from SOURCE` with the same question as
  the brief (the CLI entry, which has no cancel window: a spoken pass adds
  the 3s window and the spoken line on top of this, by design).

Each is timed from the command returning to the moment the state file shows
the target's reply text (`who` is the target and `reply` is non-empty), so
both include the daemon's poll and the target's own start. Prints timings
only; costs one short model call per turn. With saveChats on, every turn here
lands in saved chats: delete them afterwards (`agentvoice chats list`).

    python bench/pass_latency.py --target sora --source main --rounds 5

Not a voiced measurement: the plan's A15-6 asks for voiced passes, which
need a person. This isolates the part a pass adds, from dispatch on.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

STATE = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "agentvoice" / "state"


def state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def wait_reply(target: str, timeout: float) -> float | None:
    start = time.monotonic()
    want = "" if target == "main" else target
    while time.monotonic() - start < timeout:
        s = state()
        if s.get("who") == want and s.get("reply"):
            return time.monotonic() - start
        time.sleep(0.05)
    return None


def wait_idle(timeout: float = 120.0) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        live = state().get("live") or {}
        if all(v == "idle" for v in live.values()):
            return
        time.sleep(0.2)


def run(cmd: list[str], text: str) -> None:
    subprocess.run(cmd, input=text, text=True, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="sora")
    ap.add_argument("--source", default="main")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--timeout", type=float, default=90.0)
    a = ap.parse_args()
    q = "Synthetic timing check: reply with the single word ready."
    times = {"direct": [], "pass": []}
    for i in range(a.rounds):
        for kind in (("direct", "pass") if i % 2 == 0 else ("pass", "direct")):
            wait_idle()
            time.sleep(1.0)
            if kind == "direct":
                run(["agentvoice", "type", a.target], q)
            else:
                run(["agentvoice", "pass", a.target, "--from", a.source], q)
            t = wait_reply(a.target, a.timeout)
            print(f"round {i + 1} {kind:6s} {'timeout' if t is None else f'{t:.2f}s'}",
                  flush=True)
            if t is not None:
                times[kind].append(t)
    for kind, xs in times.items():
        if xs:
            print(f"{kind:6s} n={len(xs)} median {statistics.median(xs):.2f}s "
                  f"min {min(xs):.2f}s max {max(xs):.2f}s")
    if times["direct"] and times["pass"]:
        print(f"pass - direct (medians): "
              f"{statistics.median(times['pass']) - statistics.median(times['direct']):+.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
