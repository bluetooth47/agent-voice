"""Synthetic numbers for the `overview` preview target (master plan M21),
written through the real stats.py into PREVIEW_DATA -- never the real
stats folder -- and, with --state, the service's start time and memory
into the scratch state file.

PREVIEW_ARG picks the day:
- `idle` (the default): one agent, a quiet day so far;
- `several`: three agents (Theo, Sora, Hazel), a busy day;
- `week`: `several`, plus six earlier days, for the 7 days view;
- `empty`: nothing kept at all -- a new install;
- `off`: `several`, with keepStats off in the config the target is given.

Every number is fixed, so the target can check what each tile says:
`several` today is 9 turns (Theo 5, Sora 3, Hazel 1), each wake to first
word 3.2 s, transcription 0.3 s, reply after you stop 1.8 s, 7 wakes and 2
turned down by the second check. `week` adds 4 turns, 2 wakes and 1
rejection on each of the six days before. A saved chat for Theo gives his
card a "last chat ›".
"""
import json
import os
import sys
import time
from pathlib import Path

mode = (os.environ.get("PREVIEW_ARG", "") or "idle").split("-")[0]
data = Path(os.environ["PREVIEW_DATA"])
sys.path.insert(0, sys.argv[1])
os.environ["XDG_DATA_HOME"] = str(data.parent)

import paths  # noqa: E402

paths.DATA_DIR = data
import stats  # noqa: E402
from chats import ChatStore  # noqa: E402

now = time.time()
DAY = 86400.0
# Morning of today, so every turn lands today whatever time it is run.
lt = time.localtime(now)
morning = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def today_at(k):
    """The k-th event back from now, 25 minutes apart, never before
    midnight: today's bars fill the last few hours whatever time it is."""
    return max(morning, now - k * 1500)


def turns(plan, start=None):
    for k, (agent, kind, hour) in enumerate(plan):
        typed = kind in ("typed", "task")
        stats.record_turn(agent, kind, stats.new_turn_id(),
                          wake_to_reply_ms=3200, transcribe_ms=None if typed else 300,
                          reply_ms=None if typed else 1800,
                          now=today_at(k) if start is None else start + hour * 3600)


if mode != "empty":
    if mode == "idle":
        turns([("main", "wake", 0), ("main", "followup", 0)])
        stats.record_wake("spotter", now=today_at(0))
    else:
        turns([("main", "wake", 0), ("main", "wake", 0), ("main", "followup", 0),
                ("main", "typed", 0), ("main", "wake", 0),
                ("sora", "wake", 0), ("sora", "wake", 0), ("sora", "talk", 0),
                ("hazel", "task", 0)])
        for k in range(7):
            stats.record_wake("spotter", now=today_at(k * 2))
        stats.record_rejection("second-check", now=today_at(1))
        stats.record_rejection("second-check", now=today_at(5))
    if mode == "week":
        for back in range(1, 7):
            start = morning - back * DAY
            turns([("main", "wake", 9), ("main", "wake", 13), ("sora", "wake", 17),
                   ("hazel", "typed", 20)], start)
            stats.record_wake("spotter", now=start + 9 * 3600)
            stats.record_wake("vosk", now=start + 17 * 3600)
            stats.record_rejection("second-check", now=start + 22 * 3600)

    # Theo's last chat, so his card offers "last chat ›".
    store = ChatStore(data / "chats")
    store.record(chat_id=None, agent_id="", agent_label="Theo", backend="claude",
                 session_id="s-preview", project_dir="/tmp",
                 exchange={"transcript": "What is on the calendar this afternoon?",
                           "reply": "The design review at two.", "at": now})

run = os.environ.get("PREVIEW_RUN", "")
if run and (Path(run) / "state").is_file():
    state = json.loads((Path(run) / "state").read_text())
    state["service"] = {"started_at": round(now - (2 * 3600 + 14 * 60)), "rss_mb": 1160,
                        "agents_mb": 412, "agents_procs": 6}
    (Path(run) / "state").write_text(json.dumps(state))
