"""Numbers for the Overview (master plan M21, feedback items 7 and 20).

Per-day counters in `DATA_DIR/stats/YYYY-MM-DD.json` (0600, in a 0700
folder): turns per agent and per kind, wakes accepted (by which engine) and
rejected (by which stage), when in the day they came, how long the waits
were as fixed-bucket histograms, and turns cut at the longest-turn limit.
Kept 90 days. `agentvoice stats [--days N] [--json]` reads them; `agentvoice
stats clear` deletes them (the Clear stats button on Display → Privacy).

**Never text.** What somebody said, what an agent answered, a chat's title,
a tool's arguments: none of it has a field here. That is held the way the
audit log holds it (audit.py), two ways, because one of them alone was shown
in this project to miss a leak:

- **by shape**: every public function takes named arguments of a fixed
  kind -- an agent id matching its pattern, a word from a fixed list, a
  random turn id, a number. A value that does not match is dropped or
  counted under "?" rather than written as itself;
- **by an AST walk** in the tests, over every call into this module from the
  daemon, that no argument reads a name that could hold content.

The definitions, fixed here so each number means one thing:

- **wake to first word** (`wake_to_reply`): from the accepted wake to the
  first sound of the reply. Only for turns a wake word opened: a follow-up,
  the open microphone, push-to-talk and a typed message have no wake, and
  are left out of it rather than counted as zero;
- **transcription** (`transcribe`): Whisper's own working time on what was
  said, start to final text -- the "whisper Nms" of the turn's log line;
- **reply** (`reply`): from the end of what was said (or the key coming
  up) to the first sound of the reply -- the "heard → spoke" log line;
- **a turn** is counted once, by an opaque random id, on the day it ended.
  Typed, follow-up, push-to-talk and task turns are counted under their own
  kind;
- **false wakes** (`rejected["second-check"]`) are bursts the second check
  heard a name in and turned down -- exactly that, not every wake that did
  not happen. `rejected["confidence"]` is the grammar engine matching the
  phrase below the confidence bar;
- **confirmed by the second check** (`wakes["confirmed"]`, master plan M22)
  are wakes both stages agreed on, with "both must agree" chosen; **held,
  then dropped** (`rejected["held"]`) are names one stage heard and the
  other did not confirm -- including every name heard while wakes are held
  closed because the second stage cannot run.

Nothing here may fail a turn: every writer catches everything and returns
False, and an unreadable day file is set aside and started again.
"""
from __future__ import annotations

import datetime
import fcntl
import json
import math
import os
import re
import secrets
import stat
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths  # noqa: E402

#: How long a day's file is kept.
KEEP_DAYS = 90
#: Bigger than any real day file (200 turns is about 6 KB); a larger one is
#: not ours, and is read as unreadable rather than parsed.
MAX_FILE_BYTES = 256 * 1024
#: Turn ids remembered per day, for counting each turn once.
MAX_IDS = 5000
#: Agents counted per day. More than anyone runs; past it, a new id is not
#: counted rather than growing the file without bound.
MAX_AGENTS = 64

#: What opened a turn. A follow-up window, the open microphone and a
#: barge-in are all "followup": no wake word was said for them.
TURN_KINDS = ("wake", "followup", "talk", "typed", "task")
#: Which engine accepted a wake (Pipeline.wake_how).
#: "confirmed" is a wake both stages agreed on (wakeBothAgree, master plan M22).
WAKE_HOWS = ("spotter", "openwakeword", "vosk", "second-check", "confirmed", "other")
#: Which stage turned a wake down.
#: "held" is a name one stage heard and the other did not confirm in time
#: (wakeBothAgree, master plan M22): held, then dropped.
REJECT_STAGES = ("second-check", "confidence", "held")
#: The waits, each a histogram in milliseconds.
TIMINGS = ("wake_to_reply", "transcribe", "reply")
#: Bucket edges in ms: bucket 0 is [0, 50), bucket i is [EDGES[i-1],
#: EDGES[i]), the last is EDGES[-1] and over. Finer where the waits are.
EDGES_MS = (50, 100, 150, 200, 300, 400, 500, 600, 800, 1000, 1250, 1500,
            1750, 2000, 2500, 3000, 3500, 4000, 5000, 6000, 7000, 8000,
            10000, 12000, 15000, 20000, 30000, 45000, 60000, 120000)
#: The longest wait taken as a wait: an hour. Past it, a clock jumped.
MAX_MS = 3_600_000

_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
_TURN = re.compile(r"[0-9a-f]{16}")
_DAY_FILE = re.compile(r"(\d{4}-\d{2}-\d{2})\.json")

_mutex = threading.Lock()
_pruned_for = ""


def stats_dir() -> Path:
    """Read at each call, so a test (or an install) that moves DATA_DIR
    moves this with it."""
    return paths.DATA_DIR / "stats"


def new_turn_id() -> str:
    """An opaque id for one turn: random, so it says nothing about it."""
    return secrets.token_hex(8)


def day_of(now: float | None = None) -> str:
    """The local date `now` falls on: a turn ending at 23:59:59 is that
    day's, one a second later the next day's."""
    return time.strftime("%Y-%m-%d", time.localtime(time.time() if now is None else now))


def _hour(now: float) -> int:
    return time.localtime(now).tm_hour


# --- the shape of a day ---------------------------------------------------------------

def empty_day(day: str) -> dict:
    return {"v": 1, "day": day, "turns": {}, "wakes": {}, "rejected": {},
            "wake_hours": [0] * 24, "reject_hours": [0] * 24,
            "timings": {}, "limit_hits": 0, "ids": []}


def _count(value) -> int:
    """A whole, non-negative count, else 0."""
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, value)


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return float(min(value, MAX_MS))


def _empty_hist() -> dict:
    return {"b": [0] * (len(EDGES_MS) + 1), "n": 0, "sum": 0.0,
            "min": None, "max": None}


def _clean_hist(raw) -> dict:
    h = _empty_hist()
    if not isinstance(raw, dict):
        return h
    b = raw.get("b")
    if isinstance(b, list) and len(b) == len(h["b"]):
        h["b"] = [_count(x) for x in b]
    h["n"] = sum(h["b"])
    # Unclamped: many samples add up past MAX_MS. A damaged sum becomes the
    # buckets' midpoints, so a mean is still about right rather than zero.
    s = raw.get("sum")
    if isinstance(s, (int, float)) and not isinstance(s, bool) and math.isfinite(s) and s >= 0:
        h["sum"] = float(s) if h["n"] else 0.0
    else:
        lows, highs = [0] + list(EDGES_MS), list(EDGES_MS) + [EDGES_MS[-1]]
        h["sum"] = float(sum(c * (lows[i] + highs[i]) / 2 for i, c in enumerate(h["b"])))
    lo, hi = _number(raw.get("min")), _number(raw.get("max"))
    if h["n"] and lo is not None and hi is not None and lo <= hi:
        h["min"], h["max"] = lo, hi
    elif h["n"]:
        # Counts with no bounds: the bounds of the buckets they are in.
        filled = [i for i, c in enumerate(h["b"]) if c]
        h["min"] = float(([0] + list(EDGES_MS))[filled[0]])
        h["max"] = float((list(EDGES_MS) + [MAX_MS])[filled[-1]])
    return h


def _clean_counts(raw, allowed) -> dict:
    if not isinstance(raw, dict):
        return {}
    return {k: _count(v) for k, v in raw.items() if k in allowed and _count(v)}


def _clean_hours(raw) -> list:
    if isinstance(raw, list) and len(raw) == 24:
        return [_count(x) for x in raw]
    return [0] * 24


def clean_day(raw, day: str) -> dict | None:
    """A day as written, every field checked against its kind: what does not
    fit is dropped, never kept as found. None when it is not a day at all
    (the wrong date, not an object), which the writer then replaces."""
    if not isinstance(raw, dict) or raw.get("day") != day:
        return None
    out = empty_day(day)
    turns = raw.get("turns")
    if isinstance(turns, dict):
        for agent, kinds in list(turns.items())[:MAX_AGENTS]:
            if isinstance(agent, str) and _ID.fullmatch(agent):
                counts = _clean_counts(kinds, TURN_KINDS)
                if counts:
                    out["turns"][agent] = counts
    out["wakes"] = _clean_counts(raw.get("wakes"), WAKE_HOWS)
    out["rejected"] = _clean_counts(raw.get("rejected"), REJECT_STAGES)
    out["wake_hours"] = _clean_hours(raw.get("wake_hours"))
    out["reject_hours"] = _clean_hours(raw.get("reject_hours"))
    timings = raw.get("timings")
    if isinstance(timings, dict):
        for name in TIMINGS:
            if name in timings:
                h = _clean_hist(timings[name])
                if h["n"]:
                    out["timings"][name] = h
    out["limit_hits"] = _count(raw.get("limit_hits"))
    ids = raw.get("ids")
    if isinstance(ids, list):
        out["ids"] = [i for i in ids if isinstance(i, str) and _TURN.fullmatch(i)][-MAX_IDS:]
    return out


# --- files ----------------------------------------------------------------------------

def _path(day: str) -> Path:
    return stats_dir() / f"{day}.json"


def _read_file(path: Path) -> dict | None | bool:
    """The file's JSON; None when there is none; False when it is there and
    cannot be read as ours (a link, a FIFO, too big, not JSON)."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError:
        return False
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_FILE_BYTES:
            return False
        with os.fdopen(fd, "rb", closefd=False) as f:
            data = f.read(MAX_FILE_BYTES + 1)
    except OSError:
        return False
    finally:
        os.close(fd)
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return False


def load_day(day: str) -> dict:
    """A day's counts, or an empty day: for readers, which change nothing."""
    raw = _read_file(_path(day))
    return (clean_day(raw, day) if isinstance(raw, dict) else None) or empty_day(day)


def _write(path: Path, data: dict) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class _Locked:
    """The folder's lock, across threads and processes: the daemon's turn
    threads, the frame loop and `agentvoice stats clear` all write here."""

    def __enter__(self):
        _mutex.acquire()
        try:
            paths.private_dir(stats_dir())
            self.fd = os.open(stats_dir() / ".lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
                              | os.O_CLOEXEC | os.O_NONBLOCK, 0o600)
            if not stat.S_ISREG(os.fstat(self.fd).st_mode):
                os.close(self.fd)
                raise OSError("the stats lock is not a regular file")
            fcntl.flock(self.fd, fcntl.LOCK_EX)
        except BaseException:
            _mutex.release()
            raise
        return self

    def __exit__(self, *exc):
        try:
            os.close(self.fd)
        finally:
            _mutex.release()
        return False


def _update(now: float | None, change) -> bool:
    """Read today's file, apply `change` to it, write it back: atomically,
    under the lock. False, never an exception, when anything fails -- this
    runs at the end of a turn and in the frame loop, and a statistic is
    never worth either."""
    try:
        now = time.time() if now is None else float(now)
        day = day_of(now)
        with _Locked():
            path = _path(day)
            raw = _read_file(path)
            data = clean_day(raw, day) if isinstance(raw, dict) else None
            # Unreadable, damaged or another day's: skipped and replaced.
            if data is None:
                data = empty_day(day)
            if change(data, now) is False:
                return False
            _write(path, data)
            _prune_once(day)
        return True
    except Exception:       # noqa: BLE001 -- see the docstring
        return False


# --- what the daemon records ----------------------------------------------------------

def record_turn(agent: str, kind: str, turn_id: str, *, wake_to_reply_ms=None,
                transcribe_ms=None, reply_ms=None, now: float | None = None) -> bool:
    """One turn, at its end. Counted once per `turn_id`: a second call with
    the same id (a retry, a duplicate event) changes nothing."""
    if not (isinstance(agent, str) and _ID.fullmatch(agent)):
        return False
    if kind not in TURN_KINDS or not (isinstance(turn_id, str) and _TURN.fullmatch(turn_id)):
        return False
    waits = {"wake_to_reply": _number(wake_to_reply_ms) if kind == "wake" else None,
             "transcribe": _number(transcribe_ms),
             "reply": _number(reply_ms)}

    def change(data, _now):
        if turn_id in data["ids"]:
            return False
        if agent not in data["turns"] and len(data["turns"]) >= MAX_AGENTS:
            return False
        data["ids"] = (data["ids"] + [turn_id])[-MAX_IDS:]
        kinds = data["turns"].setdefault(agent, {})
        kinds[kind] = kinds.get(kind, 0) + 1
        for name, ms in waits.items():
            if ms is not None:
                _add(data["timings"].setdefault(name, _empty_hist()), ms)
        return True

    return _update(now, change)


def record_wake(how: str, now: float | None = None) -> bool:
    """A wake accepted, by the engine that accepted it."""
    how = how if how in WAKE_HOWS else "other"

    def change(data, at):
        data["wakes"][how] = data["wakes"].get(how, 0) + 1
        data["wake_hours"][_hour(at)] += 1
        return True

    return _update(now, change)


def record_rejection(stage: str, now: float | None = None) -> bool:
    """A wake turned down, by the stage that turned it down."""
    if stage not in REJECT_STAGES:
        return False

    def change(data, at):
        data["rejected"][stage] = data["rejected"].get(stage, 0) + 1
        data["reject_hours"][_hour(at)] += 1
        return True

    return _update(now, change)


def record_limit_hit(now: float | None = None) -> bool:
    """A turn cut at the longest-turn limit (phase M2, bug C)."""
    def change(data, _at):
        data["limit_hits"] += 1
        return True

    return _update(now, change)


# --- histograms -----------------------------------------------------------------------

def _bucket(ms: float) -> int:
    for i, edge in enumerate(EDGES_MS):
        if ms < edge:
            return i
    return len(EDGES_MS)


def _add(h: dict, ms: float) -> None:
    h["b"][_bucket(ms)] += 1
    h["n"] += 1
    h["sum"] = float(h["sum"]) + ms
    h["min"] = ms if h["min"] is None else min(h["min"], ms)
    h["max"] = ms if h["max"] is None else max(h["max"], ms)


def merge(hists) -> dict:
    out = _empty_hist()
    for h in hists:
        if not h or not h.get("n"):
            continue
        out["b"] = [a + b for a, b in zip(out["b"], h["b"])]
        out["n"] += h["n"]
        out["sum"] += h["sum"]
        out["min"] = h["min"] if out["min"] is None else min(out["min"], h["min"])
        out["max"] = h["max"] if out["max"] is None else max(out["max"], h["max"])
    return out


def quantile(h: dict, q: float) -> float | None:
    """The q-th quantile from the buckets: linear inside the bucket it falls
    in, and never outside the smallest and largest value seen -- so one
    sample, or every sample the same, gives that value exactly. None with no
    samples: "no data", never a zero."""
    n = h.get("n", 0) if h else 0
    if not n:
        return None
    rank = q * n
    lows = [0.0] + [float(e) for e in EDGES_MS]
    highs = [float(e) for e in EDGES_MS] + [float(h["max"])]
    seen = 0
    for i, count in enumerate(h["b"]):
        if not count:
            continue
        if seen + count >= rank:
            lo, hi = lows[i], max(lows[i], highs[i])
            value = lo + (hi - lo) * max(0.0, rank - seen) / count
            return min(max(value, h["min"]), h["max"])
        seen += count
    return float(h["max"])


def timing_summary(h: dict) -> dict:
    """What a tile shows: the sample count beside every figure, and None for
    each figure when there are no samples."""
    n = h.get("n", 0) if h else 0
    med, p95 = quantile(h, 0.5), quantile(h, 0.95)
    return {"n": n,
            "median_ms": None if med is None else round(med),
            "p95_ms": None if p95 is None else round(p95),
            "mean_ms": round(h["sum"] / n) if n else None}


# --- reading --------------------------------------------------------------------------

def _days_back(today: str, n: int) -> list[str]:
    d = datetime.date.fromisoformat(today)
    return [(d - datetime.timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def _fold(days: list[dict]) -> dict:
    turns: dict = {}
    kinds = {k: 0 for k in TURN_KINDS}
    wakes = {k: 0 for k in WAKE_HOWS}
    rejected = {k: 0 for k in REJECT_STAGES}
    wake_hours, reject_hours = [0] * 24, [0] * 24
    limit = 0
    for d in days:
        for agent, ks in d["turns"].items():
            turns[agent] = turns.get(agent, 0) + sum(ks.values())
            for k, v in ks.items():
                kinds[k] += v
        for k, v in d["wakes"].items():
            wakes[k] += v
        for k, v in d["rejected"].items():
            rejected[k] += v
        wake_hours = [a + b for a, b in zip(wake_hours, d["wake_hours"])]
        reject_hours = [a + b for a, b in zip(reject_hours, d["reject_hours"])]
        limit += d["limit_hits"]
    return {"turns": turns, "turn_count": sum(turns.values()), "kinds": kinds,
            "wakes": sum(wakes.values()), "wakes_by": wakes,
            "rejected": sum(rejected.values()), "rejected_by": rejected,
            "wake_hours": wake_hours, "reject_hours": reject_hours,
            "timings": {name: timing_summary(merge(d["timings"].get(name) for d in days))
                        for name in TIMINGS},
            "limit_hits": limit}


def summary(days: int = 7, now: float | None = None) -> dict:
    """Today, and the last `days` days (today included), for the Overview
    and `agentvoice stats --json`. Reads only; creates nothing."""
    days = max(1, min(KEEP_DAYS, int(days)))
    today = day_of(now)
    span = [load_day(d) for d in _days_back(today, days)]
    files, size = 0, 0
    folder = stats_dir()
    try:
        with os.scandir(folder) as entries:
            for e in entries:
                if _DAY_FILE.fullmatch(e.name) and e.is_file(follow_symlinks=False):
                    files += 1
                    size += e.stat(follow_symlinks=False).st_size
    except OSError:
        pass
    return {"today": today, "days": days,
            "day": _fold(span[-1:]), "range": _fold(span),
            "per_day": [{"day": d["day"],
                         "turns": sum(sum(k.values()) for k in d["turns"].values()),
                         "wakes": sum(d["wakes"].values()),
                         "rejected": sum(d["rejected"].values())} for d in span],
            "files": files, "bytes": size, "keep_days": KEEP_DAYS,
            "edges_ms": list(EDGES_MS)}


# --- keeping and clearing -------------------------------------------------------------

def _day_files() -> list[tuple[str, Path]]:
    out = []
    try:
        with os.scandir(stats_dir()) as entries:
            for e in entries:
                m = _DAY_FILE.fullmatch(e.name)
                if m and e.is_file(follow_symlinks=False):
                    out.append((m.group(1), Path(e.path)))
    except OSError:
        pass
    return out


def prune(today: str | None = None) -> int:
    """Delete day files older than KEEP_DAYS. Only files named as a day and
    regular: nothing else in the folder is touched. Call under the lock."""
    today = today or day_of()
    try:
        cutoff = (datetime.date.fromisoformat(today)
                  - datetime.timedelta(days=KEEP_DAYS - 1)).isoformat()
    except ValueError:
        return 0
    gone = 0
    for day, path in _day_files():
        try:
            datetime.date.fromisoformat(day)
        except ValueError:
            continue
        if day < cutoff:
            try:
                path.unlink()
                gone += 1
            except OSError:
                pass
    return gone


def _prune_once(day: str) -> None:
    global _pruned_for
    if _pruned_for != day:
        prune(day)
        _pruned_for = day


def clear() -> int:
    """Delete every day file: the Clear stats button. How many went."""
    if not stats_dir().is_dir():
        return 0
    gone = 0
    with _Locked():
        for _day, path in _day_files():
            try:
                path.unlink()
                gone += 1
            except OSError:
                pass
    return gone


# --- live figures: memory (for the state file, not the day files) --------------------

def rss_kb(pid: int) -> int | None:
    """A process's resident memory in kB (VmRSS), or None when it cannot be
    read: gone, another account's, a kernel thread."""
    try:
        with open(f"/proc/{int(pid)}/status", encoding="ascii", errors="replace") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _parents() -> dict[int, int]:
    """pid -> parent pid, for every process this account can see."""
    out = {}
    try:
        names = os.listdir("/proc")
    except OSError:
        return out
    for name in names:
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", encoding="ascii", errors="replace") as f:
                raw = f.read()
            # The command name sits in parentheses and may hold spaces or
            # ")": the fields after its last ")" are fixed.
            out[int(name)] = int(raw[raw.rindex(")") + 2:].split()[1])
        except (OSError, ValueError, IndexError):
            continue
    return out


def descendants(root: int) -> list[int]:
    """Every process below `root`: the agents' CLIs it started, their crew
    and notes servers, whatever those run."""
    kids: dict[int, list[int]] = {}
    for pid, ppid in _parents().items():
        kids.setdefault(ppid, []).append(pid)
    out, todo = [], list(kids.get(root, []))
    while todo:
        pid = todo.pop()
        out.append(pid)
        todo.extend(kids.get(pid, []))
    return out


def memory(root: int | None = None) -> dict:
    """The daemon's own resident memory and, apart from it, its agents':
    the sum over every process below it, in whole MB. Resident memory
    counts a shared library in each process that maps it, so the agents'
    figure leans high; `ps -o rss` shows the same numbers."""
    root = os.getpid() if root is None else root
    own = rss_kb(root)
    procs = descendants(root)
    total = sum(kb for kb in (rss_kb(p) for p in procs) if kb)
    return {"rss_mb": None if own is None else round(own / 1024),
            "agents_mb": round(total / 1024), "agents_procs": len(procs)}


# --- the CLI --------------------------------------------------------------------------

def _keeping() -> bool | None:
    try:
        import runtime
        return runtime.Config().keep_stats()
    except Exception:       # noqa: BLE001 -- a reading, not a guard
        return None


def _seconds(ms) -> str:
    return "no data" if ms is None else f"{ms / 1000:.1f}s"


def text(s: dict) -> str:
    lines = []
    for label, part in (("today", s["day"]), (f"last {s['days']} days", s["range"])):
        t = part["timings"]
        lines.append(f"{label}: {part['turn_count']} turns"
                     + (" (" + ", ".join(f"{a} {n}" for a, n in sorted(part["turns"].items())) + ")"
                        if part["turns"] else ""))
        lines.append(f"  wakes {part['wakes']} (confirmed by the second check "
                     f"{part['wakes_by']['confirmed']}), turned down {part['rejected']} "
                     f"(second check {part['rejected_by']['second-check']}, "
                     f"confidence {part['rejected_by']['confidence']}, "
                     f"held, then dropped {part['rejected_by']['held']}), "
                     f"cut at the limit {part['limit_hits']}")
        for name, label2 in (("wake_to_reply", "wake to first word"),
                             ("transcribe", "transcription"), ("reply", "reply after you stop")):
            x = t[name]
            lines.append(f"  {label2}: median {_seconds(x['median_ms'])}, "
                         f"p95 {_seconds(x['p95_ms'])} ({x['n']} turns)")
    lines.append(f"{s['files']} day files, {s['bytes']} bytes, kept {s['keep_days']} days")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    usage = "usage: agentvoice stats [--days N] [--json] | stats clear"
    if argv == ["clear"]:
        print(clear())
        return 0
    days, as_json, rest = 7, False, list(argv)
    while rest:
        a = rest.pop(0)
        if a == "--json":
            as_json = True
        elif a == "--days" and rest and rest[0].isdigit() and 1 <= int(rest[0]) <= KEEP_DAYS:
            days = int(rest.pop(0))
        else:
            print(usage, file=sys.stderr)
            return 2
    s = summary(days)
    s["keeping"] = _keeping()
    if as_json:
        print(json.dumps(s))
    else:
        if s["keeping"] is False:
            print("stats are off (keepStats): nothing new is counted")
        print(text(s))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
