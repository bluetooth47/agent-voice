"""Master plan M21: what keeping the Overview's numbers costs.

- the stats write at the end of a turn (stats.record_turn, with all three
  waits), in microseconds, median and p95 over N turns into one day;
- a wake and a rejection write, the same way;
- the day file's size after 200 turns (three agents), 60 wakes and 15
  rejections;
- summary(7) over a full week, the read the Overview makes.

Runs against a scratch data folder; nothing real is read or written.
    python3 -B bench/stats_cost.py [N]
"""
import os
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path

here = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("AGENTVOICE_DAEMON") or str(here.parent / "daemon"))
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
import paths  # noqa: E402

paths.DATA_DIR = Path(tempfile.mkdtemp(prefix="agentvoice-stats-bench-"))
import stats  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
rnd = random.Random(21)
agents = ["main", "sora", "hazel"]
kinds = ["wake", "wake", "followup", "typed", "talk"]


def timed(fn, *a, **k):
    t0 = time.perf_counter()
    ok = fn(*a, **k)
    assert ok
    return (time.perf_counter() - t0) * 1e6


turn_us = [timed(stats.record_turn, rnd.choice(agents), rnd.choice(kinds), stats.new_turn_id(),
                 wake_to_reply_ms=rnd.uniform(2000, 9000), transcribe_ms=rnd.uniform(100, 900),
                 reply_ms=rnd.uniform(800, 4000)) for _ in range(N)]
wake_us = [timed(stats.record_wake, "spotter") for _ in range(60)]
rej_us = [timed(stats.record_rejection, "second-check") for _ in range(15)]
size = (stats.stats_dir() / f"{stats.day_of()}.json").stat().st_size


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


# A full week for the read.
now = time.time()
for back in range(1, 7):
    for _ in range(N):
        stats.record_turn(rnd.choice(agents), rnd.choice(kinds), stats.new_turn_id(),
                          reply_ms=rnd.uniform(800, 4000), now=now - back * 86400)
read_us = []
for _ in range(50):
    t0 = time.perf_counter()
    stats.summary(7)
    read_us.append((time.perf_counter() - t0) * 1e6)

print(f"record_turn x{N}: median {statistics.median(turn_us):.0f} us, p95 {q(turn_us, .95):.0f} us")
print(f"record_wake x60: median {statistics.median(wake_us):.0f} us, p95 {q(wake_us, .95):.0f} us")
print(f"record_rejection x15: median {statistics.median(rej_us):.0f} us")
print(f"day file after {N} turns, 60 wakes, 15 rejections: {size} bytes")
print(f"summary(7) over 7 days of {N} turns: median {statistics.median(read_us) / 1000:.1f} ms, "
      f"p95 {q(read_us, .95) / 1000:.1f} ms")
