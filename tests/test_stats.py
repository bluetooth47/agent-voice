"""The Overview's numbers (master plan M21): daemon/stats.py, the daemon's
calls into it, the keepStats switch, and `chats last`.

What these hold:

- **never text**: by shape (every recorder refuses or drops what is not an
  id, a word from a fixed list or a number, and a day file holds only
  those) and by an AST walk over every call into stats from the daemon;
- **the numbers are the log lines'**: a turn driven through the real frame
  loop gives stats equal to the structural lines it printed -- the
  "whisper Nms", "heard → spoke" and "wake → spoke" figures;
- **keepStats off writes nothing**, and settings that cannot be read are
  off;
- **a statistic never fails a turn**: a corrupt day file is skipped and
  replaced, a write that raises returns False;
- two agents at once, a duplicate event, midnight, a daemon restart and
  pruning each count what they should.
"""
from __future__ import annotations

import ast
import importlib
import json
import os
import re
import stat
import threading
import time
from pathlib import Path

import pytest

import paths
import stats

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Each test its own data folder: the sandbox's is shared by every test
    that runs a turn."""
    d = tmp_path / "data"
    monkeypatch.setattr(paths, "DATA_DIR", d)
    monkeypatch.setattr(stats, "_pruned_for", "")
    return d


def day_file(now=None) -> Path:
    return stats.stats_dir() / f"{stats.day_of(now)}.json"


def today() -> dict:
    return stats.summary(1)["day"]


T = stats.new_turn_id


# --- recording and reading ------------------------------------------------------------

def test_a_turn_is_counted_with_its_waits():
    assert stats.record_turn("main", "wake", T(), wake_to_reply_ms=4200,
                             transcribe_ms=310, reply_ms=1900)
    d = today()
    assert d["turns"] == {"main": 1} and d["kinds"]["wake"] == 1
    assert d["timings"]["wake_to_reply"] == {"n": 1, "median_ms": 4200, "p95_ms": 4200,
                                             "mean_ms": 4200}
    assert d["timings"]["transcribe"]["median_ms"] == 310
    assert d["timings"]["reply"]["median_ms"] == 1900


def test_a_turn_is_counted_once_by_its_id():
    tid = T()
    assert stats.record_turn("main", "wake", tid, reply_ms=1000)
    assert not stats.record_turn("main", "wake", tid, reply_ms=9000)
    d = today()
    assert d["turn_count"] == 1 and d["timings"]["reply"]["n"] == 1
    assert d["timings"]["reply"]["median_ms"] == 1000


def test_only_a_turn_a_wake_opened_gives_wake_to_first_word():
    """Typed and follow-up turns are counted by kind and left out of the
    wake average, rather than counted as zero."""
    stats.record_turn("main", "followup", T(), wake_to_reply_ms=100, reply_ms=900)
    stats.record_turn("main", "typed", T(), wake_to_reply_ms=100)
    stats.record_turn("main", "wake", T(), wake_to_reply_ms=5000, reply_ms=1100)
    d = today()
    assert d["kinds"] == {"wake": 1, "followup": 1, "talk": 0, "typed": 1, "task": 0}
    assert d["timings"]["wake_to_reply"]["n"] == 1
    assert d["timings"]["wake_to_reply"]["median_ms"] == 5000
    assert d["timings"]["reply"]["n"] == 2


def test_no_samples_is_no_data_never_zero():
    d = today()
    for name in stats.TIMINGS:
        assert d["timings"][name] == {"n": 0, "median_ms": None, "p95_ms": None, "mean_ms": None}
    assert d["turn_count"] == 0 and d["wake_hours"] == [0] * 24


def test_reading_creates_nothing(data_dir):
    stats.summary(7)
    stats.load_day(stats.day_of())
    assert not data_dir.exists()


def test_wakes_rejections_and_limit_hits_by_hour():
    at = time.mktime((2026, 11, 23, 14, 30, 0, 0, 0, -1))
    assert stats.record_wake("spotter", now=at)
    assert stats.record_wake("second-check", now=at)
    assert stats.record_wake("made up", now=at)              # counted as other
    assert stats.record_rejection("second-check", now=at)
    assert stats.record_rejection("confidence", now=at + 3600)
    assert not stats.record_rejection("because", now=at)
    assert stats.record_limit_hit(now=at)
    d = stats.load_day("2026-11-23")
    assert d["wakes"] == {"spotter": 1, "second-check": 1, "other": 1}
    assert d["rejected"] == {"second-check": 1, "confidence": 1}
    assert d["wake_hours"][14] == 3 and d["reject_hours"][14] == 1 and d["reject_hours"][15] == 1
    assert d["limit_hits"] == 1


def test_the_quantiles_come_from_the_buckets_and_stay_inside_what_was_seen():
    h = stats._empty_hist()
    for ms in (900, 1100, 1200, 1300, 1400, 1600, 2100, 2600, 3100, 9000):
        stats._add(h, ms)
    med, p95 = stats.quantile(h, 0.5), stats.quantile(h, 0.95)
    assert 1250 <= med <= 1750          # the true median is 1500: within its bucket
    assert 3100 <= p95 <= 9000
    one = stats._empty_hist()
    stats._add(one, 1234)
    assert stats.quantile(one, 0.5) == 1234 and stats.quantile(one, 0.95) == 1234
    assert stats.quantile(stats._empty_hist(), 0.5) is None


def test_the_files_are_private(data_dir):
    stats.record_turn("main", "wake", T())
    assert stat.S_IMODE(os.stat(stats.stats_dir()).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(day_file()).st_mode) == 0o600
    assert "stats" in paths.PRIVATE_TREES


# --- never text -------------------------------------------------------------------------

CANARY = "the launch code is WALRUS-4471"


def test_a_sentence_has_nowhere_to_go():
    assert not stats.record_turn(CANARY, "wake", T())
    assert not stats.record_turn("main", CANARY, T())
    assert not stats.record_turn("main", "wake", CANARY)
    assert stats.record_turn("main", "wake", T(), wake_to_reply_ms=CANARY,
                             transcribe_ms=[CANARY], reply_ms={"x": CANARY})
    assert stats.record_wake(CANARY)
    assert not stats.record_rejection(CANARY)
    text = day_file().read_text()
    assert "WALRUS" not in text and "launch" not in text
    assert today()["timings"]["reply"]["n"] == 0      # the junk waits were dropped


def _strings(value, keys=True):
    if isinstance(value, dict):
        for k, v in value.items():
            if keys:
                yield k
            yield from _strings(v, keys)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v, keys)
    elif isinstance(value, str):
        yield value


def test_every_string_in_a_day_file_is_an_id_a_date_or_a_fixed_word():
    for kind in stats.TURN_KINDS:
        stats.record_turn("sora", kind, T(), wake_to_reply_ms=1, transcribe_ms=2, reply_ms=3)
    for how in stats.WAKE_HOWS:
        stats.record_wake(how)
    for stage in stats.REJECT_STAGES:
        stats.record_rejection(stage)
    stats.record_limit_hit()
    fixed = (set(stats.TURN_KINDS) | set(stats.WAKE_HOWS) | set(stats.REJECT_STAGES)
             | set(stats.TIMINGS) | {"v", "day", "turns", "wakes", "rejected", "wake_hours",
                                     "reject_hours", "timings", "limit_hits", "ids", "b", "n",
                                     "sum", "min", "max", "sora"})
    for s in _strings(json.loads(day_file().read_text())):
        assert s in fixed or re.fullmatch(r"[0-9a-f]{16}", s) or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", s), s


#: Names a call into stats may read in the daemon. Each holds an id, a word
#: from a fixed list or a number: `clock` is the turn's dict of timestamps
#: (wake_listen's `clock = {...}`), `persona` is read only for its id.
STATS_SAFE = {"persona", "kind", "clock", "heard", "woke", "end", "spoken", "stage", "how",
              "getattr", "stats", "self"}


def _names(node):
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.append(n.id)
    return out


def test_every_call_into_stats_reads_only_names_that_hold_no_content():
    """Parsed, not grepped (CLAUDE.md): every `stats.record_*(...)` and
    every `keep_stat(stats.record_*, ...)` in the daemon, every identifier
    its arguments read, at any depth."""
    calls = 0
    for path in sorted((ROOT / "daemon").rglob("*.py")):
        if path.name == "stats.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            direct = (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                      and f.value.id == "stats" and f.attr.startswith("record_"))
            through = (isinstance(f, ast.Attribute) and f.attr == "keep_stat")
            if not (direct or through):
                continue
            calls += 1
            args = list(node.args) + [k.value for k in node.keywords]
            if through:
                first = args[0] if args else None
                assert (isinstance(first, ast.Attribute) and isinstance(first.value, ast.Name)
                        and first.value.id == "stats" and first.attr.startswith("record_")), \
                    f"{path.name}:{node.lineno} keep_stat must be handed a stats recorder"
            for arg in args:
                bad = set(_names(arg)) - STATS_SAFE
                assert not bad, f"{path.name}:{node.lineno} a stats call reads {bad}"
    assert calls >= 4, "the walk found too few calls to be looking in the right place"


def test_the_clock_handed_to_stats_holds_only_numbers_and_ids():
    """`clock` is on the safe list because of what is put in it: every key
    assigned in wake_listen is a timestamp, a count, the capture's kind or
    the turn's random id."""
    src = (ROOT / "daemon/wake_listen.py").read_text()
    keys = set(re.findall(r'clock\["([a-z_]+)"\]\s*=', src))
    start = src.index('clock = {"voice_end"')
    keys |= set(re.findall(r'"([a-z_]+)":', src[start:src.index("}", start)]))
    assert keys <= {"sent", "first_text", "first_audio", "gaps", "transcribed", "whisper_ms",
                    "woke", "voice_end", "endpoint", "kind", "turn"}, keys


# --- what never fails a turn -------------------------------------------------------------

@pytest.mark.parametrize("junk", [b"{not json", b"\xff\xfe", b"[1, 2, 3]",
                                  b'{"day": "1999-01-01", "turns": {}}', b"x" * 300_000])
def test_a_corrupt_day_file_is_skipped_and_replaced(junk):
    stats.paths.private_dir(stats.stats_dir())
    day_file().write_bytes(junk)
    assert stats.record_turn("main", "wake", T())
    data = json.loads(day_file().read_text())
    assert data["day"] == stats.day_of() and data["turns"] == {"main": {"wake": 1}}


def test_a_damaged_field_is_dropped_and_the_rest_kept():
    stats.record_turn("main", "wake", T(), reply_ms=1500)
    data = json.loads(day_file().read_text())
    data["turns"]["main"]["wake"] = "lots"
    data["turns"]["Not An Id!"] = {"wake": 3}
    data["wakes"] = {"spotter": 2, "hearsay": 9}
    data["wake_hours"] = [1, 2]
    data["timings"]["reply"]["b"][0] = -4
    day_file().write_text(json.dumps(data))
    stats.record_turn("sora", "typed", T())
    d = today()
    assert d["turns"] == {"sora": 1}             # main's count was not a count
    assert d["wakes_by"]["spotter"] == 2 and "hearsay" not in d["wakes_by"]
    assert d["wake_hours"] == [0] * 24
    assert d["timings"]["reply"]["n"] == 1


def test_a_link_at_the_day_file_is_not_followed(tmp_path):
    """Not read through, and not written through: a link there is replaced,
    and whatever it pointed at -- here a plausible day of somebody else's
    counts -- is neither counted nor touched."""
    day = stats.day_of()
    planted = {**stats.empty_day(day), "turns": {"main": {"wake": 5}}}
    target = tmp_path / "somewhere-else.json"
    target.write_text(json.dumps(planted))
    stats.paths.private_dir(stats.stats_dir())
    day_file().symlink_to(target)
    assert stats.record_turn("main", "wake", T())
    assert json.loads(target.read_text()) == planted
    assert not day_file().is_symlink() and today()["turn_count"] == 1


def test_a_write_that_fails_returns_false_and_raises_nothing(monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(stats, "_write", boom)
    assert stats.record_turn("main", "wake", T()) is False
    assert stats.record_wake("spotter") is False
    monkeypatch.setattr(stats, "_Locked", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert stats.record_limit_hit() is False


def test_a_fifo_lock_does_not_hang_a_turn():
    stats.paths.private_dir(stats.stats_dir())
    os.mkfifo(stats.stats_dir() / ".lock")
    assert stats.record_turn("main", "wake", T()) is False


# --- concurrency, days, restarts ---------------------------------------------------------

def test_two_agents_at_once_lose_nothing():
    def work(agent):
        for _ in range(40):
            stats.record_turn(agent, "wake", T(), reply_ms=1000)
            stats.record_wake("spotter")
    threads = [threading.Thread(target=work, args=(a,)) for a in ("main", "sora")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    d = today()
    assert d["turns"] == {"main": 40, "sora": 40}
    assert d["wakes"] == 80 and d["timings"]["reply"]["n"] == 80


def test_two_processes_at_once_lose_nothing(data_dir):
    """The daemon's turn threads and `agentvoice stats clear` are different
    processes: the folder's lock, not only the module's mutex, holds them."""
    import subprocess
    import sys
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import paths, pathlib; "
            "paths.DATA_DIR = pathlib.Path(sys.argv[2]); import stats\n"
            "for _ in range(60): stats.record_turn(sys.argv[3], 'wake', stats.new_turn_id())")
    procs = [subprocess.Popen([sys.executable, "-B", "-c", code, str(ROOT / "daemon"),
                               str(data_dir), agent]) for agent in ("main", "sora", "hazel")]
    for p in procs:
        assert p.wait(timeout=60) == 0
    assert today()["turns"] == {"main": 60, "sora": 60, "hazel": 60}


def test_midnight_splits_the_days():
    midnight = time.mktime((2026, 11, 23, 0, 0, 0, 0, 0, -1))
    stats.record_turn("main", "wake", T(), now=midnight - 0.5)
    stats.record_turn("main", "wake", T(), now=midnight + 0.5)
    stats.record_wake("spotter", now=midnight - 0.5)
    assert stats.load_day("2026-11-22")["turns"] == {"main": {"wake": 1}}
    assert stats.load_day("2026-11-23")["turns"] == {"main": {"wake": 1}}
    assert stats.load_day("2026-11-22")["wake_hours"][23] == 1
    s = stats.summary(2, now=midnight + 10)
    assert s["day"]["turn_count"] == 1 and s["range"]["turn_count"] == 2
    assert [p["day"] for p in s["per_day"]] == ["2026-11-22", "2026-11-23"]


def test_a_daemon_restart_keeps_the_day_and_still_counts_each_turn_once():
    tid = T()
    stats.record_turn("main", "wake", tid)
    importlib.reload(stats)             # a new process: nothing held in memory
    try:
        assert not stats.record_turn("main", "wake", tid)
        assert stats.record_turn("main", "followup", T())
        assert today()["turn_count"] == 2
    finally:
        importlib.reload(stats)


def test_ninety_days_are_kept_and_nothing_else_is_touched():
    stats.paths.private_dir(stats.stats_dir())
    now = time.mktime((2026, 11, 23, 12, 0, 0, 0, 0, -1))
    for back in (0, 1, 89, 90, 120):
        day = time.strftime("%Y-%m-%d", time.localtime(now - back * 86400))
        (stats.stats_dir() / f"{day}.json").write_text(json.dumps(stats.empty_day(day)))
    (stats.stats_dir() / "notes.txt").write_text("mine")
    (stats.stats_dir() / "1999-01-01.json.bak").write_text("mine")
    stats.record_turn("main", "wake", T(), now=now)
    left = sorted(p.name for p in stats.stats_dir().iterdir() if not p.name.startswith("."))
    assert left == ["1999-01-01.json.bak", "2026-08-26.json", "2026-11-22.json",
                    "2026-11-23.json", "notes.txt"]


def test_clear_deletes_the_days_and_nothing_else():
    stats.record_turn("main", "wake", T())
    stats.record_turn("main", "wake", T(), now=time.time() - 86400 * 3)
    (stats.stats_dir() / "notes.txt").write_text("mine")
    assert stats.clear() == 2
    assert sorted(p.name for p in stats.stats_dir().iterdir() if not p.name.startswith(".")) == ["notes.txt"]
    assert stats.clear() == 0


def test_clear_with_nothing_kept_creates_nothing(data_dir):
    assert stats.clear() == 0
    assert not data_dir.exists()


# --- the CLI ---------------------------------------------------------------------------

def test_the_cli(capsys, monkeypatch):
    monkeypatch.setattr(stats, "_keeping", lambda: True)
    stats.record_turn("main", "wake", T(), reply_ms=2000)
    assert stats.main(["--days", "3", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["days"] == 3 and out["keeping"] is True and out["day"]["turn_count"] == 1
    assert out["files"] == 1 and out["bytes"] > 0
    assert stats.main([]) == 0
    assert "1 turns (main 1)" in capsys.readouterr().out
    for bad in (["--days", "0"], ["--days", "91"], ["--days", "x"], ["--nope"]):
        assert stats.main(bad) == 2
    assert stats.main(["clear"]) == 0 and capsys.readouterr().out.strip().endswith("1")


def test_the_cli_says_when_stats_are_off(capsys, monkeypatch):
    monkeypatch.setattr(stats, "_keeping", lambda: False)
    stats.main([])
    assert capsys.readouterr().out.startswith("stats are off")


def test_bin_agentvoice_has_the_verb():
    src = (ROOT / "bin/agentvoice").read_text()
    block = src[src.index("  stats)"):]
    assert 'exec "$PY" "$REPO/daemon/stats.py" "$@"' in block[:800]


# --- the setting ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, want", [(True, True), (False, False), ("true", True), ("on", True),
                                       ("off", False), ("abc", False), (1, False), (0, False),
                                       ([True], False), (None, False), ({}, False)])
def test_keep_stats_is_on_only_for_a_plain_yes(cfg_factory, raw, want):
    assert cfg_factory(keepStats=raw).keep_stats() is want


def test_keep_stats_defaults_on_and_unreadable_settings_are_off(cfg_factory, monkeypatch):
    import runtime
    assert runtime.DEFAULTS["keepStats"] is True
    cfg = cfg_factory()
    assert cfg.keep_stats() is True
    monkeypatch.setattr(type(cfg), "settings_readable", lambda self: False)
    assert cfg.keep_stats() is False


def test_the_setting_is_three_things():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    assert manifest["barWidget"]["defaults"]["keepStats"] is True
    assert any(e["key"] == "keepStats" and e["type"] == "bool"
               for e in manifest["barWidget"]["schema"])
    page = (ROOT / "pages/DisplayPage.qml").read_text()
    assert 'page.s.put("keepStats", !checked)' in page
    import runtime
    assert runtime.TOML_ALIASES["keepStats"] == ("ui", "keep_stats")


# --- the daemon --------------------------------------------------------------------------

class Agent:
    name = "stub"
    last_start = "warm"

    def __init__(self, *parts):
        self.parts = parts

    def send(self, text, session_id=None):
        from adapters.base import Chunk
        for p in self.parts:
            yield Chunk(text=p)

    def cancel(self):
        pass


def _speaker_with_a_clock(daemon, now=time.time):
    real = daemon.speaker.say

    def say(text, watch=None):
        daemon.speaker.first_audio_at = now()       # as runtime.Speaker does
        return real(text, watch)

    daemon.speaker.say = say


def test_keep_stats_off_writes_nothing(daemon, data_dir, cfg_factory):
    daemon.cfg = cfg_factory(echoTailMs=0, keepStats=False)
    daemon.agent.posture = lambda level: level
    daemon.agent = Agent("Hello there. ")
    daemon.agent.posture = lambda level: level
    daemon.pipe = type("P", (), {"max_utterance_ms": 30000})()
    _speaker_with_a_clock(daemon)
    now = time.time()
    daemon.answer("hi", {"transcript": "x"},
                  clock={"voice_end": now - 1, "endpoint": now, "kind": "wake", "woke": now - 3,
                         "turn": T(), "whisper_ms": 200})
    daemon.count_limit_hit()
    daemon.pipe = type("P", (), {"take_rejections": lambda self: ["second-check"],
                                 "wake_how": "spotter", "heard_phrase": "theo"})()
    daemon.note_wake(True)
    assert not data_dir.exists()


def test_a_turn_through_answer_is_counted(daemon):
    daemon.agent = Agent("Hello there. ")
    _speaker_with_a_clock(daemon)
    now = time.time()
    daemon.answer("hi", {"transcript": "x"},
                  clock={"voice_end": now - 1, "endpoint": now, "kind": "wake",
                         "woke": now - 4, "turn": T(), "whisper_ms": 250})
    d = today()
    assert d["turns"] == {"main": 1} and d["kinds"]["wake"] == 1
    assert d["timings"]["transcribe"]["median_ms"] == 250
    assert 4000 <= d["timings"]["wake_to_reply"]["median_ms"] < 4500


def test_a_typed_turn_is_typed_and_gives_no_voice_timings(daemon):
    daemon.agent = Agent("Hello there. ")
    _speaker_with_a_clock(daemon)
    daemon.handle_typed("main", "hello", crew=False)
    d = today()
    assert d["kinds"]["typed"] == 1 and d["turn_count"] == 1
    assert all(d["timings"][n]["n"] == 0 for n in stats.TIMINGS)


def test_a_stat_that_raises_never_reaches_the_turn(daemon, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no")
    monkeypatch.setattr(stats, "record_turn", boom)
    daemon.agent = Agent("Hello there. ")
    _speaker_with_a_clock(daemon)
    last = {"transcript": "x"}
    daemon.answer("hi", last, clock={"voice_end": time.time() - 1, "endpoint": time.time()})
    assert last["reply"].startswith("Hello")
    assert daemon.keep_stat(boom) is False


def test_rejections_are_counted_and_a_wake_test_is_not(daemon):
    class Pipe:
        wake_how, heard_phrase = "second check", "theo"
        queue = ["second-check", "confidence"]

        def take_rejections(self):
            out, self.queue = self.queue, []
            return out
    daemon.pipe = Pipe()
    daemon.note_wake(True)
    d = today()
    assert d["rejected_by"] == {"second-check": 1, "confidence": 1}
    assert d["wakes_by"]["second-check"] == 1
    daemon.pipe.queue = ["second-check"]
    daemon.note_wake(False)
    assert today()["rejected"] == 3 and today()["wakes"] == 1
    # The wake test drains the pipeline's list without counting it.
    src = (ROOT / "daemon/wake_listen.py").read_text()
    body = src[src.index("    def wake_testing"):src.index("    def _write_wake_test")]
    assert "take_rejections" in body and "note_wake" not in body and "stats." not in body


def test_a_full_stop_heard_as_a_keyword_is_not_a_wake(daemon, monkeypatch):
    daemon.pipe = type("P", (), {"wake_how": "spotter", "heard_phrase": "full stop",
                                 "take_rejections": lambda self: []})()
    monkeypatch.setattr(daemon, "heard_full_stop", lambda: True)
    daemon.note_wake(True)
    assert today()["wakes"] == 0


def test_the_pipeline_records_its_rejections_as_codes():
    from wake_listen import Pipeline
    p = Pipeline.__new__(Pipeline)
    p._rejected("second-check")
    p._rejected("confidence")
    assert p.take_rejections() == ["second-check", "confidence"]
    assert p.take_rejections() == []
    src = (ROOT / "daemon/wake_listen.py").read_text()
    assert src.count('self._rejected("confidence")') == 1
    assert src.count('self._rejected("second-check")') == 1


def test_a_limit_hit_is_counted(daemon):
    daemon.pipe = type("P", (), {"max_utterance_ms": 30000})()
    daemon.agent.posture = lambda level: level
    daemon.count_limit_hit()
    assert today()["limit_hits"] == 1


def test_the_service_field_says_uptime_and_both_memories(daemon, monkeypatch):
    calls = []
    monkeypatch.setattr(stats, "memory", lambda: calls.append(1) or
                        {"rss_mb": 900, "agents_mb": 300, "agents_procs": 4})
    f = daemon.service_field(now=1000.0)
    assert f == {"started_at": round(daemon.started_at), "rss_mb": 900, "agents_mb": 300,
                 "agents_procs": 4}
    daemon.service_field(now=1010.0)
    assert len(calls) == 1, "read again inside 30 s"
    daemon.service_field(now=1031.0)
    assert len(calls) == 2
    assert daemon.crew_fields()["service"]["rss_mb"] == 900


def test_memory_reads_this_process_and_its_children():
    import subprocess
    import sys
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        for _ in range(50):
            if stats.rss_kb(child.pid):
                break
            time.sleep(0.02)
        m = stats.memory()
        assert m["rss_mb"] == round(stats.rss_kb(os.getpid()) / 1024)
        assert child.pid in stats.descendants(os.getpid())
        assert m["agents_procs"] >= 1 and m["agents_mb"] >= 0
    finally:
        child.kill()
        child.wait()
    assert stats.rss_kb(999_999_999) is None


def test_state_update_keeps_the_other_sticky_fields():
    from runtime import StateFile
    s = StateFile()
    s.describe(agent="claude", level="ask")
    s.publish("listening")
    s.update(service={"rss_mb": 1})
    written = json.loads(s.path.read_text())
    assert written["agent"] == "claude" and written["service"] == {"rss_mb": 1}


# --- a driven turn gives stats equal to its structural log lines ---------------------------

def test_a_driven_turn_gives_stats_equal_to_its_log_lines(daemon, monkeypatch, capsys):
    """The real frame loop over a scripted microphone (tests/frame_loop.py):
    a wake, a sentence, the endpoint, Whisper, the agent's reply. Every
    figure stats kept is the one the journal line printed, to the line's own
    rounding. (One turn: the reply's echo tail drains whatever the script
    still holds, as deafen() drains a real queue, so a second turn cannot be
    scripted after it; the follow-up kind is held below.)"""
    import frame_loop
    import wake_listen

    clock = frame_loop.Clock()
    daemon.agent = Agent("It is three o'clock. ")
    _speaker_with_a_clock(daemon, now=lambda: wake_listen.time.time())
    pipe = frame_loop.Pipe(feed_wake=frame_loop.wake_on(2))
    pipe.wake_how = "spotter"
    pipe.take_rejections = lambda: []
    items = [frame_loop.QUIET] * 2 + [frame_loop.LOUD] * 5 + [frame_loop.QUIET] * 8
    frame_loop.drive(daemon, monkeypatch, items, pipe=pipe, clock=clock)
    out = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)

    whisper = [int(m) for m in re.findall(r"whisper (\d+)ms", out)]
    heard = [float(m) for m in re.findall(r"heard → spoke in (\d+\.\d)s", out)]
    woke = [float(m) for m in re.findall(r"wake → spoke in (\d+\.\d)s", out)]
    assert len(whisper) == 1 and len(heard) == 1 and len(woke) == 1, out
    assert "● wake" in out

    d = today()
    assert d["turns"] == {"main": 1} and d["kinds"]["wake"] == 1
    assert d["wakes"] == 1 and d["wakes_by"]["spotter"] == 1
    t = d["timings"]
    assert t["transcribe"] == {"n": 1, "median_ms": whisper[0], "p95_ms": whisper[0],
                               "mean_ms": whisper[0]}
    assert t["reply"]["n"] == 1 and t["wake_to_reply"]["n"] == 1
    assert abs(t["reply"]["median_ms"] / 1000 - heard[0]) <= 0.05 + 1e-9
    assert abs(t["wake_to_reply"]["median_ms"] / 1000 - woke[0]) <= 0.05 + 1e-9
    assert woke[0] > heard[0], "the wake figure includes the sentence itself"


@pytest.mark.parametrize("opened, kind", [("wake", "wake"), ("talk", "talk"),
                                          ("followup", "followup"), ("open", "followup"),
                                          ("barge", "followup"), ("", "followup")])
def test_how_a_capture_opened_is_the_turns_kind(daemon, opened, kind):
    """A follow-up window, the open microphone and a barge-in had no wake
    word: counted as follow-ups, and never in the wake average."""
    now = time.time()
    clock = {"kind": opened, "turn": T(), "voice_end": now - 1, "first_audio": now,
             "woke": now - 3, "whisper_ms": 100}
    daemon.count_turn(daemon._main, clock, typed=False)
    d = today()
    assert d["kinds"][kind] == 1
    assert d["timings"]["wake_to_reply"]["n"] == (1 if kind == "wake" else 0)
    assert d["timings"]["reply"]["n"] == 1


# --- chats last -------------------------------------------------------------------------------

def test_chats_last_names_each_agents_newest_real_chat(tmp_path):
    from chats import ChatStore
    store = ChatStore(tmp_path / "chats")

    def rec(agent, at):
        return store.record(chat_id=None, agent_id=agent, agent_label=agent or "Theo",
                            backend="claude", session_id=None, project_dir="/tmp",
                            exchange={"transcript": "q", "reply": "a", "at": at}, now=at)
    old = rec("", 1000.0)
    store.set_current("", None)
    new = rec("", 2000.0)
    store.set_current("", None)
    sora = rec("sora", 1500.0)
    assert store.last_by_owner() == {"main": new, "sora": sora}
    (tmp_path / "chats" / f"{new}.json").unlink()
    assert store.last_by_owner()["main"] == old
    assert ChatStore(tmp_path / "none").last_by_owner() == {}
    assert not (tmp_path / "none").exists()


def test_chats_last_cli_prints_ids_only(tmp_path, capsys, monkeypatch):
    import chats
    monkeypatch.setattr(chats, "CHATS_DIR", tmp_path / "chats")
    store = chats.ChatStore(tmp_path / "chats")
    store.record(chat_id=None, agent_id="", agent_label="Theo", backend="claude",
                 session_id=None, project_dir="/tmp",
                 exchange={"transcript": CANARY, "reply": CANARY, "at": 1.0})
    assert chats.main(["last", "--json"]) == 0
    out = capsys.readouterr().out
    assert "WALRUS" not in out and list(json.loads(out)) == ["main"]


def test_work_for_another_agent_is_a_task_turn(daemon):
    daemon._main.task = object()
    try:
        daemon.count_turn(daemon._main, {"kind": "wake", "turn": T(), "whisper_ms": 9}, typed=False)
    finally:
        daemon._main.task = None
    d = today()
    assert d["kinds"]["task"] == 1 and d["timings"]["transcribe"]["n"] == 0
