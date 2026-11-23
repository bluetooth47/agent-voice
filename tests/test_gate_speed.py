"""How fast the adaptive gate follows the room (master plan M23).

What has to hold:

- the rise and fall rates are plain attributes on the running noise floor,
  changed in place: a new rate keeps what the floor has learned and never
  rebuilds a model;
- they arrive through runtime.Config.gate_rates(), bounded (0.1-3.0 and
  0.5-10.0 dB/s), and anything unreadable -- a wrong type, a typo, settings
  that cannot be read -- gives the rates the gate always had (0.5 and 3.0);
- the warm-up, the hard limits on the gate and the wake word's slack are the
  same at every speed;
- the gate still never learns while the screen is locked: those frames are
  dropped before the meter or the floor sees them;
- the page's slow / normal / fast are the numbers noise_floor.SPEEDS says,
  and normal is the shipped pair.
"""
from __future__ import annotations

import json
import re

import pytest

import noise_floor
from noise_floor import NoiseFloor

FRAME_MS = 200
PER_S = 1000 // FRAME_MS


def fed(nf, level, seconds):
    for _ in range(int(round(seconds * PER_S))):
        nf.feed(level)
    return nf


# --- the noise floor -------------------------------------------------------------------

def test_by_default_it_moves_at_the_rates_it_always_had():
    nf = NoiseFloor(FRAME_MS)
    assert (nf.rise_db_per_s, nf.fall_db_per_s) == (0.5, 3.0)
    assert (noise_floor.RISE_DB_PER_S, noise_floor.FALL_DB_PER_S) == (0.5, 3.0)


@pytest.mark.parametrize("rise", [0.1, 0.5, 1.5, 3.0])
def test_a_rise_rate_is_the_most_it_climbs_per_second(rise):
    nf = fed(NoiseFloor(FRAME_MS), -60, noise_floor.WINDOW_S)
    nf.set_rates(rise, 3.0)
    # The room gets louder for good; once the median has turned, the floor
    # climbs at exactly the rate set, one frame at a time.
    fed(nf, -30, noise_floor.WINDOW_S * 0.6)
    before = nf.floor_db
    fed(nf, -30, 1)
    assert nf.floor_db - before == pytest.approx(min(rise, -30 - before))


@pytest.mark.parametrize("fall", [0.5, 3.0, 10.0])
def test_a_fall_rate_is_the_most_it_drops_per_second(fall):
    nf = fed(NoiseFloor(FRAME_MS), -30, noise_floor.WINDOW_S)
    nf.set_rates(0.5, fall)
    fed(nf, -55, noise_floor.WINDOW_S * 0.6)
    before = nf.floor_db
    fed(nf, -55, 0.4)
    assert before - nf.floor_db == pytest.approx(min(fall * 0.4, before + 55))


def test_a_new_rate_keeps_what_it_has_learned():
    nf = fed(NoiseFloor(FRAME_MS), -52, 10)
    floor, levels = nf.floor_db, list(nf._levels)
    nf.set_rates(3.0, 10.0)
    assert nf.floor_db == floor and list(nf._levels) == levels and nf.ready


@pytest.mark.parametrize("rise, fall, want", [
    (0.0, 0.0, (0.1, 0.5)),
    (-4, -4, (0.1, 0.5)),
    (99, 99, (3.0, 10.0)),
    (1.2, 7.5, (1.2, 7.5)),
    ("x", None, (0.5, 3.0)),
    (float("nan"), float("inf"), (0.5, 3.0)),
    (float("-inf"), [], (0.5, 3.0)),
])
def test_rates_are_bounded_and_nonsense_is_the_shipped_rate(rise, fall, want):
    nf = NoiseFloor(FRAME_MS)
    nf.set_rates(rise, fall)
    assert (nf.rise_db_per_s, nf.fall_db_per_s) == pytest.approx(want)


@pytest.mark.parametrize("speed", sorted(noise_floor.SPEEDS))
def test_warm_up_and_the_hard_limits_hold_at_every_speed(speed):
    rise, fall = noise_floor.SPEEDS[speed]
    nf = NoiseFloor(FRAME_MS)
    nf.set_rates(rise / 10, fall / 10)
    fed(nf, -99, noise_floor.WARMUP_S - 0.2)
    assert not nf.ready and nf.gate(-38) == -38 and nf.wake_gate(-38) == -38
    fed(nf, -99, 0.2)
    assert nf.gate(-38) == noise_floor.GATE_MIN_DB
    assert nf.wake_gate(-38) == noise_floor.GATE_MIN_DB
    # Long enough to climb the whole way at this speed's rise.
    fed(nf, 0, noise_floor.WINDOW_S + 100 / (rise / 10))
    assert nf.gate(-38) == noise_floor.GATE_MAX_DB
    assert nf.wake_gate(-38) == noise_floor.GATE_MAX_DB - noise_floor.WAKE_SLACK_DB


def test_talk_shorter_than_half_the_window_moves_no_speed():
    """The plan's risk: a fast gate learning speech. The median is the guard,
    not the rate: 14 s of talk at -20 in a -55 room leaves the floor on the
    room at the fastest rates allowed (FINDINGS §56)."""
    nf = NoiseFloor(FRAME_MS)
    nf.set_rates(noise_floor.RISE_BOUNDS[1], noise_floor.FALL_BOUNDS[1])
    fed(nf, -55, noise_floor.WINDOW_S)
    fed(nf, -20, noise_floor.WINDOW_S * 0.45)
    assert nf.floor_db == pytest.approx(-55)


def test_the_speeds_are_inside_the_bounds_and_normal_is_the_shipped_pair():
    from runtime import DEFAULTS
    assert noise_floor.SPEEDS["normal"] == (DEFAULTS["gateRiseTenths"], DEFAULTS["gateFallTenths"])
    assert noise_floor.SPEEDS["normal"] == (noise_floor.RISE_DB_PER_S * 10, noise_floor.FALL_DB_PER_S * 10)
    s, n, f = (noise_floor.SPEEDS[k] for k in ("slow", "normal", "fast"))
    assert s[0] < n[0] < f[0] and s[1] < n[1] < f[1]
    for rise, fall in noise_floor.SPEEDS.values():
        assert noise_floor.RISE_BOUNDS[0] <= rise / 10 <= noise_floor.RISE_BOUNDS[1]
        assert noise_floor.FALL_BOUNDS[0] <= fall / 10 <= noise_floor.FALL_BOUNDS[1]
        assert fall > rise, "falling stays faster: a gate too high cuts words off"


# --- runtime.Config --------------------------------------------------------------------

def test_the_reader_gives_the_shipped_rates_by_default(cfg_factory):
    assert cfg_factory().gate_rates() == (0.5, 3.0)


@pytest.mark.parametrize("rise, fall, want", [
    (12, 75, (1.2, 7.5)),
    (1, 5, (0.1, 0.5)),
    (30, 100, (3.0, 10.0)),
    (0, 0, (0.1, 0.5)),                  # below the bounds: clamped
    (-3, 4, (0.1, 0.5)),
    (31, 101, (3.0, 10.0)),              # above: clamped
    (10**9, 10**9, (3.0, 10.0)),
    ("12", " 75 ", (1.2, 7.5)),          # a hand edit
    (15.0, 80.0, (1.5, 8.0)),            # TOML or JSON may write 15.0
    (True, False, (0.5, 3.0)),           # a bool is not a number of tenths
    (1.5, 7.25, (0.5, 3.0)),             # a fraction of a tenth is a typo
    ("abc", "", (0.5, 3.0)),
    (None, [], (0.5, 3.0)),
    ({"x": 1}, "²", (0.5, 3.0)),
    ("1e3", "0x10", (0.5, 3.0)),
])
def test_the_reader_bounds_and_cleans(cfg_factory, rise, fall, want):
    c = cfg_factory(gateRiseTenths=rise, gateFallTenths=fall)
    assert c.gate_rates() == pytest.approx(want)


def test_unreadable_settings_give_the_shipped_rates(cfg_factory, monkeypatch):
    c = cfg_factory(gateRiseTenths=30, gateFallTenths=100)
    monkeypatch.setattr(type(c), "settings_readable", lambda self: False)
    assert c.gate_rates() == (0.5, 3.0)


def test_a_stand_in_config_or_a_broken_reader_keeps_the_shipped_rates():
    import wake_listen
    assert wake_listen._gate_rates({"gateRiseTenths": 30}) == (0.5, 3.0)

    class Broken:
        def gate_rates(self):
            raise ValueError("no")
    assert wake_listen._gate_rates(Broken()) == (0.5, 3.0)

    class Odd:
        def gate_rates(self):
            return "fast"
    assert wake_listen._gate_rates(Odd()) == (0.5, 3.0)


# --- the pipeline ----------------------------------------------------------------------

def test_a_changed_rate_reaches_the_running_floor_with_no_rebuild(monkeypatch, tmp_path,
                                                                    cfg_factory):
    """Through the real apply() and a real runtime.Config: the rates land on
    the floor already listening, what it learned is kept, and the engine is
    not built again."""
    from test_sherpa_wake import FakeSherpa
    from test_sherpa_wake import _pipe as sherpa_pipe
    pipe, _ = sherpa_pipe(monkeypatch, tmp_path)
    cfg = cfg_factory(engine="sherpa", phrase="computer", fullStopAnytime=False,
                      wakeCrossCheck=False, adaptiveGate=True)
    pipe.apply(cfg)
    assert FakeSherpa.built == 1
    assert (pipe._floor.rise_db_per_s, pipe._floor.fall_db_per_s) == (0.5, 3.0)
    floor = pipe._floor
    for _ in range(5 * PER_S):
        pipe.learn_room(-58)
    learned = pipe.floor_db
    assert learned == -58

    cfg._values.update(gateRiseTenths=15, gateFallTenths=80)
    pipe.apply(cfg)
    assert pipe._floor is floor, "the floor was replaced, and with it the room"
    assert (floor.rise_db_per_s, floor.fall_db_per_s) == (1.5, 8.0)
    assert pipe.floor_db == learned, "a new rate forgot the room"
    assert FakeSherpa.built == 1, "a rate is a number, not a model"

    cfg._values.update(gateRiseTenths="fast", gateFallTenths=None)
    pipe.apply(cfg)
    assert (floor.rise_db_per_s, floor.fall_db_per_s) == (0.5, 3.0)


def test_a_rate_changes_how_soon_the_gate_follows(monkeypatch, tmp_path, cfg_factory):
    """The whole pipeline, slow against fast, after the room gets 10 dB
    louder: the same start, a different gate 25 s on."""
    from test_sherpa_wake import _pipe as sherpa_pipe
    gates = {}
    for speed in ("slow", "fast"):
        rise, fall = noise_floor.SPEEDS[speed]
        pipe, _ = sherpa_pipe(monkeypatch, tmp_path)
        pipe.apply(cfg_factory(engine="sherpa", phrase="computer", fullStopAnytime=False,
                               wakeCrossCheck=False, adaptiveGate=True,
                               gateRiseTenths=rise, gateFallTenths=fall))
        for _ in range(int(noise_floor.WINDOW_S * PER_S)):
            pipe.learn_room(-55)
        assert pipe.threshold_db == -45
        for _ in range(25 * PER_S):
            pipe.learn_room(-45)
        gates[speed] = pipe.threshold_db
    assert gates["slow"] < gates["fast"] - 1


def test_the_journal_says_the_rates(monkeypatch):
    import wake_listen
    src = open(wake_listen.__file__).read()
    assert "rises {p._floor.rise_db_per_s:.1f} dB/s, falls {p._floor.fall_db_per_s:.1f} dB/s" in src


# --- the lock --------------------------------------------------------------------------

def test_frames_are_dropped_on_lock_before_the_meter_and_the_floor(daemon, monkeypatch):
    """The real frame loop over a scripted microphone: while locked, no frame
    reaches learn_room or the published level, whatever the speed."""
    import frame_loop
    from frame_loop import LOUD, QUIET

    class Pipe(frame_loop.Pipe):
        def __init__(self):
            super().__init__()
            self.learned: list[float] = []
            self.threshold_db = -40.0

        def learn_room(self, level):
            self.learned.append(round(level, 1))
            return False

    pipe = Pipe()
    marks: dict[str, int] = {}

    def lock():
        marks["locked_at"] = len(pipe.learned)
        daemon.locked = True

    def unlock():
        marks["unlocked_at"] = len(pipe.learned)
        daemon.locked = False

    items = [QUIET, QUIET, lock, LOUD, LOUD, LOUD, LOUD, unlock, QUIET, QUIET]
    payloads, _ = frame_loop.drive(daemon, monkeypatch, items, pipe=pipe)
    assert marks["unlocked_at"] == marks["locked_at"], \
        f"the floor learned {marks['unlocked_at'] - marks['locked_at']} frames behind a lock"
    loud = round(frame_loop.rms_db(LOUD), 1)
    assert loud not in pipe.learned, "a frame said behind the lock reached the floor"
    assert all(p.get("level_db") != loud for _, p in payloads), \
        "a frame said behind the lock reached the meter"
    assert len(pipe.learned) >= 3, "the frames either side of the lock were learned"


# --- the page and the three places -----------------------------------------------------

def test_the_settings_exist_in_all_three_places_and_on_one_page():
    from conftest import ROOT
    from qml_sources import page
    from runtime import DEFAULTS, TOML_ALIASES
    man = json.loads((ROOT / "manifest.json").read_text())
    schema = {e["key"]: e for e in man["barWidget"]["schema"]}
    for key, lo, hi, default in (("gateRiseTenths", 1, 30, 5), ("gateFallTenths", 5, 100, 30)):
        e = schema[key]
        assert (e["type"], e["min"], e["max"], e["defaultValue"]) == ("integer", lo, hi, default)
        assert man["barWidget"]["defaults"][key] == default == DEFAULTS[key]
        assert TOML_ALIASES[key] == ("audio", key.replace("gate", "gate_").replace("Tenths", "_tenths").lower())
        assert f'page.s.put("{key}"' in page("Listening")
    assert round(noise_floor.RISE_BOUNDS[0] * 10) == schema["gateRiseTenths"]["min"]
    assert round(noise_floor.RISE_BOUNDS[1] * 10) == schema["gateRiseTenths"]["max"]
    assert round(noise_floor.FALL_BOUNDS[0] * 10) == schema["gateFallTenths"]["min"]
    assert round(noise_floor.FALL_BOUNDS[1] * 10) == schema["gateFallTenths"]["max"]


def test_the_page_presets_are_the_daemon_speeds():
    from qml_sources import page
    text = page("Listening")
    m = re.search(r"readonly property var gateSpeeds: \(?(\{[^}]*\})", text)
    assert m, "the presets are one map on the page"
    found = {k: (int(a), int(b)) for k, a, b in
             re.findall(r"(\w+): \[(\d+), (\d+)\]", m.group(1))}
    assert found == noise_floor.SPEEDS


def test_a_speed_writes_both_rates_and_nothing_else():
    from qml_sources import page
    text = page("Listening")
    body = text[text.index("function chooseGateSpeed"):]
    body = body[:body.index("\n  }")]
    assert 's.put("gateRiseTenths"' in body and 's.put("gateFallTenths"' in body
    assert body.count("s.put(") == 2
