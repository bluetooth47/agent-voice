"""Test my wake word (plan item 9): wakes are counted, not answered.

What has to hold:

- a wake during the test opens no turn and is counted with how it woke;
- a burst of speech is an attempt, so the hit rate means something;
- near misses carry reasons only, never words;
- it ends on its own, at ten wakes or 90s, so a forgotten test never
  leaves wakes being swallowed;
- the readout file is owner-only and removed when there is no test.
"""
from __future__ import annotations

import json
import stat

import pytest

import wake_test
from wake_test import WakeTest


def test_ten_wakes_end_it():
    t = WakeTest(now=0.0)
    for i in range(10):
        t.on_attempt()
        t.on_wake("theo", "spotter")
    assert t.status == "done"
    t.on_wake("theo", "spotter")
    snap = t.snapshot(now=1.0)
    assert snap["hits"] == 10 and snap["attempts"] == 10 and snap["rate"] == 1.0
    assert snap["left_s"] == 0


def test_it_times_out():
    t = WakeTest(now=0.0, limit_s=90)
    assert not t.tick(now=89.9)
    assert t.tick(now=90.0) and t.status == "timeout"
    t.on_attempt()
    assert t.attempts == 0, "counting after the end"


def test_a_wake_before_its_burst_ends_never_beats_100_percent():
    t = WakeTest(now=0.0)
    t.on_wake("theo", "second check")
    snap = t.snapshot(now=0.0)
    assert snap["attempts"] == 1 and snap["rate"] == 1.0
    assert snap["by"] == ["theo · second check"]


def test_rate_and_near_misses():
    t = WakeTest(now=0.0)
    for _ in range(4):
        t.on_attempt()
    t.on_wake("theo", "spotter")
    for i in range(20):
        t.on_near(f"second check: vosk only {i}")
    t.on_near("")
    snap = t.snapshot(now=10.0)
    assert snap["rate"] == 0.25
    assert len(snap["near"]) == wake_test.NEAR_MAX
    assert snap["near"][-1] == "second check: vosk only 19"
    assert snap["left_s"] == 80


def test_the_file_is_owner_only_and_never_missing(tmp_path):
    """The page watches this file, and a watcher cannot watch a file that
    does not exist yet: deleting it at daemon start is why the first live
    test showed nothing at all."""
    path = tmp_path / "wake-test.json"
    wake_test.write(path, WakeTest(now=0.0).snapshot(now=0.0))
    assert json.loads(path.read_text())["status"] == "running"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    wake_test.write(path, None)
    assert json.loads(path.read_text()) == {"status": ""}


def test_the_loudest_frame_is_kept_against_the_gate():
    t = WakeTest(now=0.0)
    for db in (-50.0, -31.5, -40.0):
        t.on_level(db, -27.0)
    snap = t.snapshot(now=1.0)
    assert snap["peak_db"] == -31.5 and snap["gate_db"] == -27.0


# --- through the daemon -------------------------------------------------------

class ScriptedPipe:
    """Wakes on the frames it is told to, and turns one down."""
    threshold_db = -40.0

    def __init__(self, wake_on):
        self.wake_on = set(wake_on)
        self.n = 0
        self.heard_phrase = ""
        self.wake_how = ""
        self.near = []

    def feed_wake(self, pcm, level):
        self.n += 1
        if self.n in self.wake_on:
            self.heard_phrase, self.wake_how = "theo", "spotter"
            return True
        if self.n == 2:
            self.near.append("second check: vosk only — whisper disagreed")
        return False

    def take_near_misses(self):
        out, self.near = self.near, []
        return out


@pytest.fixture
def testing(daemon, tmp_path, monkeypatch):
    monkeypatch.setattr(type(daemon), "WAKE_TEST_FILE", tmp_path / "wake-test.json")
    return daemon


def test_without_a_test_frames_go_to_the_wake_word(testing):
    testing.pipe = ScriptedPipe(wake_on={1})
    assert testing.wake_testing(b"\0" * 10, -20.0) is False
    assert testing.pipe.n == 0


def test_a_wake_in_the_test_is_counted_and_not_answered(testing):
    testing.pipe = ScriptedPipe(wake_on={3})
    assert testing.apply_wake_test_command("wake-test-start")
    # Two 200ms frames loud then two quiet: one attempt of 400ms.
    for level in (-20.0, -20.0, -60.0, -60.0):
        assert testing.wake_testing(b"\0" * 6400, level) is True
    snap = json.loads(testing.WAKE_TEST_FILE.read_text())
    assert snap["hits"] == 1 and snap["attempts"] == 1
    assert snap["by"] == ["theo · spotter"]
    assert snap["near"] == ["second check: vosk only — whisper disagreed"]
    assert testing.apply_wake_test_command("wake-test-stop")
    assert json.loads(testing.WAKE_TEST_FILE.read_text())["status"] == "stopped"
    assert testing.wake_testing(b"\0" * 6400, -20.0) is False, \
        "a stopped test still swallows wakes"


def test_other_commands_are_not_its_business(testing):
    assert not testing.apply_wake_test_command("talk")
    assert not testing.apply_wake_test_command(None)


def test_the_run_loop_asks_the_test_before_the_wake_word():
    """The hook has to sit in front of the wake branch, or a wake during the
    test opens a turn. Read from the source, because the run loop needs a
    microphone."""
    from conftest import ROOT
    src = (ROOT / "daemon" / "wake_listen.py").read_text()
    hook = src.index('if phase == "wake" and self.wake_testing(pcm, level):')
    wake = src.index('fired = self.pipe.feed_wake(pcm, level)')
    assert hook < wake
    assert "if self.apply_wake_test_command(cmd):" in src


def test_the_cli_and_the_page_know_it():
    from conftest import ROOT
    from qml_sources import overlay, page
    cli = (ROOT / "bin" / "agentvoice").read_text()
    assert 'send_command "wake-test-${2:-start}"' in cli
    assert "wake-test.json" in overlay()
    assert "page.s.wakeTest(" in page("Listening")


# --- the automatic test -------------------------------------------------------

def test_auto_clips_cover_names_stop_and_distractors():
    import wake_auto
    got = list(wake_auto.clips(["theo", "hey computer"], "full stop"))
    assert ("Theo.", "theo") in got and ("Hey Theo.", "theo") in got
    assert ("Hey Computer.", "hey computer") in got
    assert ("Hey Hey Computer.", "hey computer") not in got
    assert ("Full stop.", "full stop") in got
    assert sum(1 for _, w in got if w == "") == len(wake_auto.DISTRACTORS)
    assert not any(w == "full stop" for _, w in wake_auto.clips(["theo"], ""))


def test_auto_tally():
    import wake_auto
    rows = [
        {"text": "Theo.", "want": "theo", "woke": "theo", "how": "spotter", "voice": "amy"},
        {"text": "Theo.", "want": "theo", "woke": "theo", "how": "second check", "voice": "ryan"},
        {"text": "Theo.", "want": "theo", "woke": "", "how": "", "voice": "alan"},
        {"text": "Theo.", "want": "theo", "woke": "sora", "how": "spotter", "voice": "x"},
        {"text": "Video", "want": "", "woke": "theo", "how": "second check", "voice": "amy"},
        {"text": "Okay", "want": "", "woke": "", "how": "", "voice": "amy"},
    ]
    t = wake_auto.tally(rows, ["theo", "sora"], "")
    assert t["names"]["theo"] == {"tries": 4, "hits": 2, "spotter": 1,
                                  "second check": 1, "confirmed": 0, "other": 0}
    # Master plan M22: a wake both stages agreed on has its own column.
    both = wake_auto.tally([{"text": "Theo.", "want": "theo", "woke": "theo",
                             "how": "confirmed", "voice": "amy"}], ["theo"], "")
    assert both["names"]["theo"]["confirmed"] == 1 and both["names"]["theo"]["other"] == 0
    assert t["names"]["sora"]["tries"] == 0
    assert t["false"] == ["“Video” (amy) woke theo"] and t["distractors"] == 2


def test_auto_is_reachable_from_the_cli_and_the_page():
    from conftest import ROOT
    from qml_sources import overlay, page
    cli = (ROOT / "bin" / "agentvoice").read_text()
    assert 'daemon/wake_auto.py' in cli and "auto-stop)" in cli
    assert "wake-auto.json" in overlay()
    assert "page.s.wakeTestAuto(" in page("Listening")
