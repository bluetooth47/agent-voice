"""Synthetic numbers for the `listening` preview target (master plan M23),
written through the real stats.py into PREVIEW_DATA -- never the real stats
folder -- so the Decision stage's "Today" line has something fixed to say:
7 wakes (2 of them confirmed by the second check), 3 rejected by the second
check, 1 held, then dropped.
"""
import os
import sys
import time
from pathlib import Path

data = Path(os.environ["PREVIEW_DATA"])
sys.path.insert(0, sys.argv[1])
os.environ["XDG_DATA_HOME"] = str(data.parent)

import paths  # noqa: E402

paths.DATA_DIR = data
import stats  # noqa: E402

now = time.time()
lt = time.localtime(now)
morning = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def today_at(k):
    """The k-th event back from now, ten minutes apart, never before
    midnight, so every one lands today whatever time it is run."""
    return max(morning, now - k * 600)


for k in range(5):
    stats.record_wake("spotter", now=today_at(k))
for k in range(2):
    stats.record_wake("confirmed", now=today_at(5 + k))
for k in range(3):
    stats.record_rejection("second-check", now=today_at(k))
stats.record_rejection("held", now=today_at(4))
