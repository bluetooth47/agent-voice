"""The adaptive microphone gate (plan item 10).

What has to hold:

- it follows the room: floor plus margin, after a warm-up on the fixed gate;
- speech in the room does not drag it up (a low percentile sits in the gaps);
- it rises slowly and falls faster, and never leaves its hard limits;
- with it off nothing changes, and switching it off forgets the room;
- the setting is in all three places and on one page.
"""
from __future__ import annotations

import pytest

import noise_floor
from noise_floor import NoiseFloor

FRAME_MS = 200
PER_S = 1000 // FRAME_MS


def fed(nf, level, seconds):
    for _ in range(int(seconds * PER_S)):
        nf.feed(level)
    return nf


def test_the_fixed_gate_holds_until_it_has_heard_the_room():
    nf = NoiseFloor(FRAME_MS)
    fed(nf, -60, noise_floor.WARMUP_S - 0.2)
    assert not nf.ready and nf.gate(-38) == -38
    fed(nf, -60, 0.2)
    assert nf.ready and nf.gate(-38) == -50


def test_a_quiet_room_puts_the_gate_a_margin_above_it():
    nf = fed(NoiseFloor(FRAME_MS, margin_db=12), -52, 5)
    assert nf.gate(-38) == pytest.approx(-40)


def test_a_wake_word_now_and_then_does_not_drag_it_up():
    """Speech at -20 for 40% of the wake phase, the room at -55 for the rest:
    far more talk than a wake phase holds, and the floor is still the room."""
    nf = NoiseFloor(FRAME_MS)
    for i in range(int(30 * PER_S)):
        nf.feed(-20 if i % 5 < 2 else -55)
    assert nf.floor_db == pytest.approx(-55)


def test_a_tv_with_gaps_is_part_of_the_room():
    """Its gaps are not the floor: a gate under the TV holds turns open."""
    nf = NoiseFloor(FRAME_MS)
    for i in range(int(60 * PER_S)):
        nf.feed(-42 if i % 10 < 7 else -60)
    assert nf.floor_db == pytest.approx(-42)


def test_it_rises_slowly_and_falls_faster():
    nf = fed(NoiseFloor(FRAME_MS), -60, noise_floor.WINDOW_S)
    # A fan comes on. The floor holds until the fan is most of what the
    # window remembers, then climbs no faster than RISE_DB_PER_S.
    fed(nf, -40, noise_floor.WINDOW_S * 0.4)
    assert nf.floor_db == pytest.approx(-60), "moved before the room changed"
    fed(nf, -40, noise_floor.WINDOW_S * 0.2)
    before = nf.floor_db
    fed(nf, -40, 4)
    assert 0 < nf.floor_db - before <= noise_floor.RISE_DB_PER_S * 4 + 0.01
    fed(nf, -40, 60)
    assert nf.floor_db == pytest.approx(-40)
    fed(nf, -60, 30)          # the fan goes off
    assert nf.floor_db == pytest.approx(-60), "fell back within the window"
    # And falling is faster per second than rising.
    assert noise_floor.FALL_DB_PER_S > noise_floor.RISE_DB_PER_S


def test_one_loud_frame_moves_nothing():
    nf = fed(NoiseFloor(FRAME_MS), -55, 10)
    before = nf.gate(-38)
    nf.feed(-5)
    assert nf.gate(-38) == before


def test_the_gate_never_leaves_its_limits():
    loud = fed(NoiseFloor(FRAME_MS), -10, 200)
    assert loud.gate(-38) == noise_floor.GATE_MAX_DB
    silent = fed(NoiseFloor(FRAME_MS, margin_db=3), -99, 5)
    assert silent.gate(-38) == noise_floor.GATE_MIN_DB


# --- in the pipeline ------------------------------------------------------------

def test_off_it_changes_nothing(monkeypatch):
    import wake_listen
    pipe = object.__new__(wake_listen.Pipeline)
    pipe.adaptive_gate, pipe.threshold_db = False, -38.0
    for _ in range(100):
        assert pipe.learn_room(-60) is False
    assert pipe.threshold_db == -38.0 and pipe.floor_db is None


def test_on_it_moves_the_gate_the_wake_word_and_endpoint_read(monkeypatch):
    import wake_listen
    pipe = object.__new__(wake_listen.Pipeline)
    pipe.adaptive_gate, pipe.fixed_db, pipe.threshold_db = True, -38.0, -38.0
    pipe._floor = NoiseFloor(FRAME_MS, margin_db=10)
    moved = [pipe.learn_room(-58) for _ in range(5 * PER_S)]
    assert any(moved) and pipe.threshold_db == -48.0 and pipe.floor_db == -58.0


def test_apply_reads_the_settings_and_switching_off_forgets_the_room():
    """Through the real apply(), on a pipeline whose models already match."""
    import test_wake_reconcile as twr
    pipe, cfg, _ = twr._settled(None, 50)
    cfg["adaptiveGate"], cfg["gateMarginDb"] = True, 8
    pipe.apply(cfg)
    assert pipe.adaptive_gate and pipe._floor.margin_db == 8
    for _ in range(5 * PER_S):
        pipe.learn_room(-60)
    assert pipe.threshold_db == -52.0
    cfg["gateMarginDb"] = 99                  # out of range: clamped
    pipe.apply(cfg)
    assert pipe._floor.margin_db == noise_floor.MARGIN_MAX
    cfg["adaptiveGate"] = False
    pipe.apply(cfg)
    assert pipe.threshold_db == -40.0 and not pipe._floor.ready


def test_the_settings_exist_in_all_three_places_and_one_page():
    import json

    from conftest import ROOT
    from qml_sources import page
    from runtime import DEFAULTS, TOML_ALIASES
    man = json.loads((ROOT / "manifest.json").read_text())
    keys = {e["key"] for e in man["barWidget"]["schema"]}
    for key in ("adaptiveGate", "gateMarginDb"):
        assert key in keys and key in man["barWidget"]["defaults"]
        assert key in DEFAULTS and key in TOML_ALIASES
        assert f'page.s.put("{key}"' in page("Listening")
    assert DEFAULTS["adaptiveGate"] is False, "off until it is live-tested"


def test_the_wake_word_hears_a_little_below_the_turn_gate():
    """Fixed: one gate. Following the room: the wake word's checks sit
    WAKE_SLACK_DB lower, never under the hard minimum, so a short name's
    quiet syllables still reach the second check (FINDINGS §27)."""
    nf = NoiseFloor(FRAME_MS)
    assert nf.wake_gate(-38) == -38, "warming up: the fixed gate for both"
    fed(nf, -45, 5)
    assert nf.gate(-38) == -35 and nf.wake_gate(-38) == -35 - noise_floor.WAKE_SLACK_DB
    quiet = fed(NoiseFloor(FRAME_MS, margin_db=3), -99, 5)
    assert quiet.wake_gate(-38) == noise_floor.GATE_MIN_DB


def test_the_pipeline_uses_the_wake_gate_where_the_wake_word_is_judged():
    import wake_listen
    pipe = object.__new__(wake_listen.Pipeline)
    pipe.adaptive_gate, pipe.fixed_db, pipe.threshold_db = True, -38.0, -38.0
    pipe._floor = NoiseFloor(FRAME_MS)
    for _ in range(5 * PER_S):
        pipe.learn_room(-45)
    assert pipe.threshold_db == -35 and pipe.wake_gate_db == -41
    from conftest import ROOT
    src = (ROOT / "daemon" / "wake_listen.py").read_text()
    assert "self._burst_cutter().feed(pcm, level_db >= self.wake_gate_db)" in src
    assert "if level_db < self.wake_gate_db:" in src
