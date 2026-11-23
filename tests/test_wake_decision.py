"""Which stages must agree before a wake counts (master plan M22).

Three choices, all real:

- first only: the spotter alone (wakeCrossCheck off);
- either stage: a spotter hit wakes at once and the second check rescues a
  short burst the spotter missed (the default, unchanged -- the existing
  tests in test_crosscheck.py and test_sherpa_wake.py hold it);
- both must agree (wakeBothAgree): a spotter hit is held until the second
  check names the same agent, within a window.

What has to hold, besides the three working:

- a missing second stage holds wakes closed and says why; it never wakes on
  one stage (openWakeWord, Vosk, a sherpa-onnx that fell back, the second
  check switched off, a Vosk-only check with no Vosk model);
- "full stop" keeps its immediate path in every mode;
- what was said while a hit was held reaches the capture it opens;
- a lock or a mute drops a held hit, so a name said before the lock is never
  joined to speech after it;
- a name heard and not confirmed is counted ("held") and said on the HUD,
  never as what was said, and never over a lock screen;
- the setting is three things and one control, and reads false when it
  cannot be read.

Nothing here needs a model: the engines are stood in for, and the frame loop
is the real one over a scripted microphone (tests/frame_loop.py).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "daemon"))
sys.path.insert(0, str(ROOT / "tests"))

import crosscheck  # noqa: E402
from crosscheck import Agreement, Bursts, both_blocker, decision  # noqa: E402
from qml_sources import overlay, page  # noqa: E402

LOUD, QUIET = b"\x00\x40" * 3200, b"\x00\x00" * 3200


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Each test its own stats folder, as in test_stats.py: the frame-loop
    tests count wakes too."""
    import paths
    import stats
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(stats, "_pruned_for", "")


# --- the three choices, pure ---------------------------------------------------------

@pytest.mark.parametrize("cross, both, want", [
    (False, False, "first"), (True, False, "either"),
    (True, True, "both"),
    # Both asked for with the second check off is not "first": it is both,
    # which cannot run, so wakes are held closed (below).
    (False, True, "both"),
])
def test_two_settings_make_three_decisions(cross, both, want):
    assert decision(cross, both) == want
    assert want in crosscheck.DECISIONS


@pytest.mark.parametrize("engine, cross, engines, vosk, sherpa, code", [
    ("sherpa", True, "both", True, True, ""),
    ("sherpa", True, "whisper", False, True, ""),     # Whisper alone needs no Vosk
    ("sherpa", True, "both", False, True, ""),        # Whisper still votes alone
    ("sherpa", True, "vosk", False, True, "no-vosk"),
    ("sherpa", False, "both", True, True, "off"),
    ("openwakeword", True, "both", True, False, "oww"),
    ("vosk", True, "both", True, False, "vosk"),
    ("vosk", True, "both", True, True, "fallback"),   # sherpa-onnx chosen, fell back
])
def test_when_both_cannot_run_it_says_which_way(engine, cross, engines, vosk, sherpa, code):
    assert both_blocker(engine, cross, engines, vosk, sherpa) == code
    if code:
        why = crosscheck.BLOCKERS[code]
        assert why and "{" not in why, "a fixed sentence, nothing interpolated"


def test_the_agreement_holds_a_spotter_hit_for_its_tail():
    a = Agreement(tail=2, window=3)
    a.hold("spotter", "theo")
    assert a.waiting_on_check()
    assert a.frame(b"1") == ""
    assert a.frame(b"2") == "due"
    held = a.take()
    assert held["name"] == "theo" and held["frames"] == [b"1", b"2"]
    assert a.pending is None


def test_a_second_check_vote_waits_its_window_then_expires():
    a = Agreement(tail=2, window=3)
    a.hold("check", "sora")
    assert not a.waiting_on_check()
    assert a.check_vote("sora") == "sora" and a.check_vote("theo") == ""
    assert [a.frame(b"x") for _ in range(3)] == ["", "", "expired"]


def test_a_burst_can_be_taken_before_it_ends():
    cut = Bursts(200)
    for pcm, loud in [(b"q", False), (b"L", True), (b"L", True)]:
        assert cut.feed(pcm, loud) is None
    assert cut.take() == b"qLL", "the preroll and the speech so far"
    assert cut.take() is None, "and the cutter starts again"


def test_a_taken_burst_keeps_the_window():
    short = Bursts(200)
    short.feed(b"q", False)
    short.feed(b"L", True)
    assert short.take() is None, "200ms is a click, not a name"
    long = Bursts(200, max_ms=600)
    for _ in range(6):
        long.feed(b"L", True)
    assert long.take() is None, "past the maximum: a sentence with a name in it"
    none = Bursts(200)
    none.feed(b"q", False)
    assert none.take() is None, "nothing over the gate: nothing to judge"


# --- the Pipeline, engines stood in for ----------------------------------------------

class Spotter:
    """sherpa-onnx's place: `script` is what each feed() hears, in order."""

    def __init__(self, script=()):
        self.script = list(script)
        self.resets = 0

    def feed(self, pcm):
        return self.script.pop(0) if self.script else ""

    def reset(self):
        self.resets += 1


def _pipe(spotter=(), vosk="", whisper="", has_vote=("theo", "sora"), mode="both",
          engines="both", tail=2):
    import wake_listen
    pipe = object.__new__(wake_listen.Pipeline)
    pipe._oww, pipe._sherpa = None, Spotter(spotter)
    pipe.phrase, pipe.names = "theo", ["sora"]
    pipe.engine, pipe._chosen_engine = "sherpa", "sherpa"
    pipe.cross_check = mode != "first"
    pipe.decision = mode
    pipe.cc_engines, pipe.cc_trailing, pipe.cc_hint = engines, 3, True
    pipe._log_speech = False
    pipe.threshold_db = pipe.wake_gate_db = -40.0
    pipe.refractory_ms = 2000
    pipe._refractory_until = 0.0
    pipe.asked = []
    pipe._vosk_vote = lambda audio, names: (vosk, set(has_vote))

    def whisper_names(audio, names):
        pipe.asked.append(audio)
        if isinstance(whisper, Exception):
            raise whisper
        return whisper
    pipe._whisper_names = whisper_names
    pipe._agreement().tail = tail
    pipe.reconcile_decision()
    return pipe


def _feed(pipe, frames):
    """[(pcm, loud)] -> the names woken, in order."""
    out = []
    for pcm, loud in frames:
        if pipe.feed_wake(pcm, -20.0 if loud else -70.0):
            out.append(pipe.heard_phrase)
    return out


def F(tag: bytes, loud: bool):
    """A frame that can be told apart from the others."""
    return (tag * 4, loud)


def test_both_agree_wakes_and_says_so(capsys):
    pipe = _pipe(spotter=["", "", "theo"], vosk="theo", whisper="Theo.")
    woke = _feed(pipe, [F(b"q", False), F(b"a", True), F(b"b", True), F(b"c", False),
                        F(b"d", False)])
    assert woke == ["theo"]
    assert pipe.wake_how == "confirmed"
    assert "both agree: theo" in capsys.readouterr().out
    assert pipe.take_rejections() == []


def test_the_second_check_hears_the_burst_up_to_the_hit():
    pipe = _pipe(spotter=["", "", "theo"], vosk="theo", whisper="Theo.", tail=1)
    _feed(pipe, [F(b"q", False), F(b"a", True), F(b"b", True), F(b"c", True)])
    assert pipe.asked == [b"qqqq" + b"aaaa" + b"bbbb" + b"cccc"], \
        "preroll, the name, and one frame of tail -- not a burst's end"


def test_with_the_shipped_tail_a_hit_is_judged_on_its_own_frame():
    """FINDINGS §55: a tail of 0 caught the most real wakes, the most
    one-breath requests and no more false ones, with the least delay."""
    assert crosscheck.CONFIRM_TAIL_FRAMES == 0
    import wake_listen
    pipe = object.__new__(wake_listen.Pipeline)
    assert pipe._agreement().tail == 0
    pipe = _pipe(spotter=["", "", "theo"], vosk="theo", whisper="Theo, what",
                 tail=crosscheck.CONFIRM_TAIL_FRAMES)
    frames = [F(b"q", False), F(b"a", True), F(b"b", True)]
    assert _feed(pipe, frames) == ["theo"], "woken on the frame the spotter fired"
    assert pipe.asked == [b"qqqq" + b"aaaa" + b"bbbb"]
    assert pipe.take_carried() == [], "nothing was held, so nothing is carried"


def test_what_was_said_while_held_is_carried_to_the_capture():
    pipe = _pipe(spotter=["", "", "theo"], vosk="theo", whisper="Theo, what", tail=2)
    frames = [F(b"q", False), F(b"a", True), F(b"a", True), F(b"w", True), F(b"x", True)]
    assert _feed(pipe, frames) == ["theo"]
    assert pipe.take_carried() == [b"wwww", b"xxxx"], \
        "the frames after the hit, as the spotter alone would have captured them"
    assert pipe.take_carried() == [], "once"


def test_first_hit_and_second_miss_is_held_then_dropped(capsys):
    pipe = _pipe(spotter=["", "", "theo"], vosk="theo", whisper="Video.")
    assert _feed(pipe, [F(b"q", False), F(b"a", True), F(b"a", True), F(b"b", False),
                        F(b"c", False)]) == []
    assert pipe.take_rejections() == ["held"]
    assert pipe.take_held() == ["theo"]
    out = capsys.readouterr().out
    assert "heard theo, not confirmed — the second check did not hear it (vosk only" in out
    assert "Video" not in out, "logSpeech is off"
    assert len(pipe.asked) == 1, "the second check was asked"
    assert any(m.startswith("not confirmed:") for m in pipe.take_near_misses())


def test_the_two_stages_naming_different_agents_wakes_nobody():
    pipe = _pipe(spotter=["", "", "theo"], vosk="sora", whisper="Sora.")
    assert _feed(pipe, [F(b"q", False), F(b"a", True), F(b"a", True), F(b"b", False),
                        F(b"c", False)]) == []
    assert pipe.take_rejections() == ["held"]
    assert "the second check heard another name" in pipe.take_near_misses()[-1]


def test_a_miss_the_second_check_would_rescue_is_not_a_wake_on_its_own():
    """Either stage rescues it; both must agree holds it for the spotter,
    which never comes."""
    pipe = _pipe(spotter=[], vosk="theo", whisper="Theo.")
    assert _feed(pipe, [F(b"q", False), F(b"a", True), F(b"b", True),
                        F(b"c", False), F(b"d", False)]) == []
    assert pipe._agree.pending and pipe._agree.pending["stage"] == "check"
    assert _feed(pipe, [F(b"e", False)] * 3) == []
    assert pipe.take_rejections() == ["held"], "the vote ran out: held, then dropped"

    either = _pipe(spotter=[], vosk="theo", whisper="Theo.", mode="either")
    assert _feed(either, [F(b"q", False), F(b"a", True), F(b"b", True),
                          F(b"c", False), F(b"d", False)]) == ["theo"]


def test_a_late_spotter_inside_the_window_agrees():
    pipe = _pipe(spotter=["", "", "", "", "", "theo"], vosk="theo", whisper="Theo.")
    woke = _feed(pipe, [F(b"q", False), F(b"a", True), F(b"b", True), F(b"c", False),
                        F(b"d", False), F(b"e", False)])
    assert woke == ["theo"] and pipe.wake_how == "confirmed"
    assert pipe.take_carried() == [b"eeee"], "what came after the burst it confirmed"


def test_a_vote_outside_the_window_does_not():
    window = crosscheck.AGREE_WINDOW_MS // 200
    pipe = _pipe(spotter=[""] * (5 + window) + ["theo"], vosk="theo", whisper="Theo.")
    frames = [F(b"q", False), F(b"a", True), F(b"b", True), F(b"c", False), F(b"d", False)]
    frames += [F(b"e", False)] * (window + 1)
    assert _feed(pipe, frames) == []
    assert "held" in pipe.take_rejections()


def test_a_name_inside_a_sentence_is_turned_down():
    """The spotter fires on "Theo" in "I was telling Theo": the burst up to
    it does not open with the name."""
    pipe = _pipe(spotter=["", "", "", "theo"], vosk="theo", whisper="I was telling Theo",
                 tail=0)
    assert _feed(pipe, [F(b"q", False), F(b"i", True), F(b"w", True), F(b"t", True)]) == []
    assert pipe.take_rejections() == ["held"]


def test_a_name_below_the_gate_is_too_quiet_to_confirm():
    pipe = _pipe(spotter=["theo"], vosk="theo", whisper="Theo.", tail=0)
    assert _feed(pipe, [F(b"q", False)]) == []
    assert pipe.asked == [], "nothing was asked about no speech"
    assert pipe.take_rejections() == ["held"]


def test_a_second_check_that_fails_wakes_nobody(capsys):
    pipe = _pipe(spotter=["", "", "theo"], vosk="theo", whisper=RuntimeError("boom"))
    assert _feed(pipe, [F(b"q", False), F(b"a", True), F(b"a", True), F(b"b", False),
                        F(b"c", False)]) == []
    assert "second check failed" in capsys.readouterr().out
    assert pipe.take_rejections() == ["held"]


def test_a_stale_hold_is_dropped_not_decided(monkeypatch):
    import wake_listen
    pipe = _pipe(spotter=["", "", "theo"], vosk="theo", whisper="Theo.", tail=3)
    _feed(pipe, [F(b"q", False), F(b"a", True), F(b"a", True)])
    assert pipe._agree.waiting_on_check()
    later = wake_listen.time.time() + wake_listen.HOLD_STALE_S + 1
    monkeypatch.setattr(wake_listen.time, "time", lambda: later)
    assert _feed(pipe, [F(b"b", False), F(b"c", False)]) == []
    assert "held" in pipe.take_rejections()


def test_forgetting_drops_the_hold_and_the_burst():
    pipe = _pipe(spotter=["", "", "theo"], vosk="theo", whisper="Theo.", tail=2)
    _feed(pipe, [F(b"q", False), F(b"a", True), F(b"a", True)])
    assert pipe._agree.pending is not None
    pipe.forget_wake()
    assert pipe._agree.pending is None and pipe._burst_cutter().take() is None
    assert _feed(pipe, [F(b"b", False), F(b"c", False)]) == [], \
        "the name before the lock is not joined to what comes after it"


def test_with_both_off_a_spotter_hit_still_wakes_at_once():
    pipe = _pipe(spotter=["theo"], mode="either")
    assert _feed(pipe, [F(b"a", True)]) == ["theo"] and pipe.wake_how == "spotter"
    first = _pipe(spotter=["theo"], mode="first")
    assert _feed(first, [F(b"a", True)]) == ["theo"]


# --- held closed when the second stage cannot run -------------------------------------

def test_the_second_check_switched_off_holds_wakes_closed(capsys):
    pipe = _pipe(spotter=["theo"], vosk="theo", whisper="Theo.", mode="both")
    pipe.cross_check = False
    assert pipe.reconcile_decision()
    assert pipe.decision_field() == {"mode": "both", "closed": True, "blocked": "off",
                                     "why": crosscheck.BLOCKERS["off"]}
    assert "wakes held closed" in capsys.readouterr().out
    assert _feed(pipe, [F(b"a", True)]) == []
    assert pipe.asked == [] and pipe.take_rejections() == ["held"]
    assert pipe.take_held() == ["theo"]


def test_a_vosk_only_check_with_no_vosk_model_holds_wakes_closed(monkeypatch):
    import wake_listen
    monkeypatch.setattr(wake_listen, "vosk_model", lambda: None)
    pipe = _pipe(spotter=["theo"], engines="vosk")
    assert pipe.decision_field()["blocked"] == "no-vosk"
    assert _feed(pipe, [F(b"a", True)]) == []
    monkeypatch.setattr(wake_listen, "vosk_model", lambda: Path("/models/vosk"))
    assert pipe.reconcile_decision(), "a model arriving on disk changes the answer"
    assert pipe.decision_field()["closed"] is False


def test_openwakeword_has_no_second_check_so_both_holds_it_closed():
    import wake_listen

    class Oww:
        def feed(self, pcm):
            return True
    pipe = object.__new__(wake_listen.Pipeline)
    pipe._sherpa, pipe._oww = None, Oww()
    pipe.phrase, pipe.names, pipe.engine, pipe._chosen_engine = "hey jarvis", [], \
        "openwakeword", "openwakeword"
    pipe.cross_check, pipe.decision, pipe.cc_engines = True, "both", "both"
    pipe.refractory_ms, pipe._refractory_until = 2000, 0.0
    pipe.reconcile_decision()
    assert pipe.decision_field()["closed"] is True
    assert pipe.feed_wake(b"\0" * 8, -20.0) is False
    assert pipe.take_rejections() == ["held"]
    assert pipe.feed_wake(b"\0" * 8, -20.0) is False
    assert pipe.take_rejections() == [], "one phrase is counted once (the refractory)"
    pipe.decision = "either"
    pipe._refractory_until = 0.0
    assert pipe.feed_wake(b"\0" * 8, -20.0) is True, "either stage: as before"


def test_a_vosk_grammar_match_is_held_closed_too():
    src = (ROOT / "daemon/wake_listen.py").read_text()
    body = src[src.index("    def feed_wake"):src.index("    def learn_room")]
    tail = body[body.index("self.heard_phrase = matched") - 400:]
    assert 'if getattr(self, "decision", "") == "both":' in tail
    assert "self._held(matched" in tail
    assert tail.index("self._held(matched") < tail.index("self.heard_phrase = matched")


@pytest.mark.parametrize("mode, closed", [("first", False), ("either", False),
                                          ("both", False), ("both", True)])
def test_full_stop_keeps_its_own_path_in_every_mode(mode, closed):
    import wake_listen
    pipe = _pipe(spotter=[wake_listen.STOP_PHRASE], mode=mode)
    if closed:
        pipe.cross_check = False
        pipe.reconcile_decision()
        assert pipe.decision_field()["closed"]
    assert pipe.feed_wake(b"\0" * 8, -70.0) is True
    assert pipe.heard_phrase == wake_listen.STOP_PHRASE
    assert pipe.asked == [], "nothing was asked first"


def test_full_stop_drops_a_held_name():
    import wake_listen
    pipe = _pipe(spotter=["", "theo", wake_listen.STOP_PHRASE], vosk="theo",
                 whisper="Theo.", tail=3)
    assert _feed(pipe, [F(b"q", False), F(b"a", True), F(b"b", False)]) == \
        [wake_listen.STOP_PHRASE]
    assert pipe._agree.pending is None


# --- the setting -------------------------------------------------------------------------

def test_the_setting_exists_in_all_three_places():
    from runtime import DEFAULTS, TOML_ALIASES
    manifest = json.loads((ROOT / "manifest.json").read_text())["barWidget"]
    assert DEFAULTS["wakeBothAgree"] is False
    assert manifest["defaults"]["wakeBothAgree"] is False
    assert TOML_ALIASES["wakeBothAgree"] == ("wake", "both_agree")
    entry = next(e for e in manifest["schema"] if e["key"] == "wakeBothAgree")
    assert entry["type"] == "bool" and entry["defaultValue"] is False
    assert 's.put("wakeBothAgree"' in page("Listening")


@pytest.mark.parametrize("raw, want", [
    (True, True), (False, False), ("true", True), ("on", True), ("1", True),
    ("yes", True), ("no", False), ("", False), (1, False), (0, False),
    ([True], False), ({"x": 1}, False), (None, False), ("tru", False),
])
def test_only_a_plain_yes_turns_it_on(cfg_factory, raw, want):
    assert cfg_factory(wakeBothAgree=raw).wake_both_agree() is want


def test_by_default_it_is_off(cfg_factory):
    assert cfg_factory().wake_both_agree() is False


def test_unreadable_settings_read_it_off(cfg_factory, monkeypatch):
    c = cfg_factory(wakeBothAgree=True)
    monkeypatch.setattr(c, "settings_readable", lambda: False)
    assert c.wake_both_agree() is False


def test_apply_takes_the_decision_with_no_rebuild(monkeypatch, tmp_path):
    from test_sherpa_wake import FakeSherpa
    from test_sherpa_wake import _pipe as sherpa_pipe
    pipe, cfg = sherpa_pipe(monkeypatch, tmp_path)
    pipe.apply(cfg)
    assert pipe.decision == "either" and FakeSherpa.built == 1
    cfg["wakeBothAgree"] = True
    pipe._agreement().hold("check", "sarah")
    pipe.apply(cfg)
    assert pipe.decision == "both"
    assert FakeSherpa.built == 1, "a rule is a number, not a model"
    assert pipe._agree.pending is None, "a hold under the old rule is not one under the new"
    assert pipe.decision_field() == {"mode": "both", "closed": False, "blocked": "", "why": ""}
    cfg["wakeCrossCheck"] = False
    pipe.apply(cfg)
    assert pipe.decision_field()["closed"] is True


def test_a_stand_in_config_without_the_method_reads_off():
    import wake_listen
    assert wake_listen._both_agree({"wakeBothAgree": True}) is False
    assert wake_listen._both_agree(type("C", (), {"get_bool": lambda s, k: True})()) is True

    class Broken:
        def wake_both_agree(self):
            raise ValueError("no")
    assert wake_listen._both_agree(Broken()) is False


# --- the daemon: carried frames, the lock, the HUD, the state file, stats -------------

def _frame_loop_pipe(spotter, said="what time is it", vosk="theo", whisper="Theo.",
                     tail=2):
    import frame_loop
    import wake_listen

    class P(wake_listen.Pipeline):
        lead_in_ms, trailing_ms = 5000, 600
        max_utterance_ms, min_utterance_ms = 30_000, 100
        detection_threshold, conversation, follow_up_ms = 0.9, True, 3000
        floor_db, accurate_partials = None, False

        def __init__(self):
            pass

        def learn_room(self, level):
            return False

        def new_capture(self):
            return None

        def new_utterance(self):
            u = frame_loop.Utterance(self.said)
            u.got = []
            real_add = u.add
            u.add = lambda pcm, loud: (u.got.append(pcm), real_add(pcm, loud))[1]
            self.utterances.append(u)
            return u

        def apply(self, cfg):
            pass

        def reconcile_vocab(self):
            pass

    p = P()
    p.said, p.utterances = said, []
    p._oww, p._sherpa = None, Spotter(spotter)
    p.phrase, p.names = "theo", ["sora"]
    p.engine = p._chosen_engine = "sherpa"
    p.cross_check, p.decision = True, "both"
    p.cc_engines, p.cc_trailing, p.cc_hint = "both", 3, True
    p._log_speech = False
    p.threshold_db = p.wake_gate_db = -40.0
    p.refractory_ms, p._refractory_until = 2000, 0.0
    p.heard_phrase = ""
    p._vosk_vote = lambda audio, names: (vosk, {"theo", "sora"})
    p._whisper_names = lambda audio, names: whisper
    p._agreement().tail = tail
    p.reconcile_decision()
    return p


A = b"\x00\x41" * 3200          # loud, and told apart from LOUD
B = b"\x00\x42" * 3200


def test_the_real_frame_loop_opens_the_capture_with_the_held_frames(daemon, monkeypatch):
    import frame_loop
    pipe = _frame_loop_pipe(spotter=["", "", "theo"])
    items = [QUIET, LOUD, LOUD, A, B, LOUD, frame_loop.stop()]
    frame_loop.drive(daemon, monkeypatch, items, pipe=pipe)
    assert pipe.wake_how == "confirmed"
    [u] = pipe.utterances
    assert u.got[:2] == [A, B], "the two frames said while both stages were asked"
    assert u.got[2:] == [LOUD], "then the capture's own"


def test_with_either_stage_the_loop_carries_nothing(daemon, monkeypatch):
    import frame_loop
    pipe = _frame_loop_pipe(spotter=["", "", "theo"])
    pipe.decision = "either"
    items = [QUIET, LOUD, LOUD, A, B, frame_loop.stop()]
    frame_loop.drive(daemon, monkeypatch, items, pipe=pipe)
    [u] = pipe.utterances
    assert u.got == [A, B], "the frames after the hit, captured as they come"


def test_a_lock_in_the_middle_of_a_hold_drops_it(daemon, monkeypatch):
    import frame_loop
    pipe = _frame_loop_pipe(spotter=["", "", "theo"], tail=3)

    def lock():
        daemon.locked = True

    def unlock():
        daemon.locked = False
    items = [QUIET, LOUD, LOUD, lock, QUIET, QUIET, unlock, QUIET, QUIET, QUIET,
             frame_loop.stop()]
    frame_loop.drive(daemon, monkeypatch, items, pipe=pipe)
    assert pipe.utterances == [], "nothing woke"
    assert pipe._agree.pending is None


def test_carried_frames_are_judged_against_the_gate_not_the_chime(daemon, monkeypatch):
    import frame_loop
    import wake_listen
    # The standard-library RMS (asserted equal to numpy's in test_states.py),
    # so this runs on the bare runner too.
    monkeypatch.setattr(wake_listen, "frame_db", frame_loop.rms_db)

    class Utt:
        def __init__(self):
            self.got = []

        def add(self, pcm, loud):
            self.got.append(loud)
            return False
    daemon.pipe = type("P", (), {"threshold_db": -40.0})()
    daemon._chime_until = wake_listen.time.time() + 60     # a chime "sounding"
    u = Utt()
    buf, heard = daemon.carry_into([LOUD, QUIET], b"", None, u)
    assert heard is True and u.got == [True, False]
    assert buf == LOUD + QUIET
    assert daemon.carry_into([], b"", None, u) == (b"", False)


def test_the_wake_watch_carries_them_too():
    """The wake word heard while the agent works opens the next capture in
    the run loop's `woke` branch; what a held wake kept goes with it."""
    src = (ROOT / "daemon/wake_listen.py").read_text()
    watch = src[src.index("    def _wake_watch_until"):src.index("    def limit_field")]
    assert watch.index("self._woke_carried = self.take_carried()") < watch.index("self._woke = True")
    branch = src[src.index("                if woke:"):]
    branch = branch[:branch.index("continue")]
    assert "carry_into(carried" in branch and "self._woke_carried" in branch


def test_a_name_not_confirmed_is_said_on_the_hud_for_a_moment(daemon, monkeypatch):
    import wake_listen
    daemon.state.publish("listening")
    pipe = _pipe(spotter=["", "", "theo"], vosk="", whisper="")
    daemon.pipe = pipe
    _feed(pipe, [F(b"q", False), F(b"a", True), F(b"a", True), F(b"b", False),
                 F(b"c", False)])
    daemon.note_wake(False)
    written = json.loads(daemon.state.path.read_text())
    assert written["notice"].endswith("heard, not confirmed")
    assert "theo" in written["notice"].lower()
    later = wake_listen.time.time() + wake_listen.WAKE_NOTE_S + 1
    monkeypatch.setattr(wake_listen.time, "time", lambda: later)
    assert daemon.expire_wake_note()
    daemon._recompose()
    assert "notice" not in json.loads(daemon.state.path.read_text())


def test_the_note_is_never_shown_over_a_lock_screen(daemon):
    daemon.state.publish("listening")
    daemon.pipe = _pipe()
    daemon.note_held("theo")
    assert "notice" in json.loads(daemon.state.path.read_text())
    daemon.locked = True
    daemon.state.publish("locked")
    written = json.loads(daemon.state.path.read_text())
    assert written["state"] == "locked" and "notice" not in written


def test_the_wake_test_drains_held_names_and_counts_nothing():
    src = (ROOT / "daemon/wake_listen.py").read_text()
    body = src[src.index("    def wake_testing"):src.index("    def _write_wake_test")]
    assert '"take_held"' in body and "note_held" not in body and "note_wake" not in body


def test_the_state_file_says_the_decision(daemon):
    daemon.pipe = _pipe(mode="both")
    assert daemon.crew_fields()["wake_decision"] == {
        "mode": "both", "closed": False, "blocked": "", "why": ""}
    daemon.pipe = object()
    assert daemon.crew_fields()["wake_decision"] == {}, "a pipeline that does not say"


def test_a_changed_decision_is_published_once(daemon, monkeypatch):
    calls = []
    monkeypatch.setattr(daemon, "publish_agent",
                        lambda: calls.append(daemon.crew_fields()["wake_decision"]))
    daemon.pipe = _pipe(mode="either")
    daemon.reconcile_decision()
    daemon.reconcile_decision()
    assert len(calls) == 1
    daemon.pipe.decision = "both"
    daemon.pipe.cross_check = False
    daemon.reconcile_decision()
    daemon.reconcile_decision()
    assert len(calls) == 2 and calls[-1]["closed"] is True
    daemon.pipe = object()
    daemon.reconcile_decision()
    assert len(calls) == 2, "a pipeline that says nothing publishes nothing"


def test_the_note_expires_above_the_listening_gate():
    """With the readout's expiry, for the readout's reason: refresh() is
    below the gate a muted microphone stops at."""
    src = (ROOT / "daemon" / "wake_listen.py").read_text()
    poll = src[src.index("if time.time() - last_lock_poll > 2.0:"):]
    poll = poll[:poll.index("if crew:")]
    assert "self.expire_wake_note()" in poll


def test_stats_count_confirmed_and_held(daemon):
    import stats
    today = lambda: stats.summary(1)["day"]  # noqa: E731 -- as test_stats reads it
    name = [F(b"q", False), F(b"a", True), F(b"a", True), F(b"b", False), F(b"c", False)]
    pipe = _pipe(spotter=["", "", "theo"], vosk="theo", whisper="Theo.")
    daemon.pipe = pipe
    fired = _feed(pipe, name)
    assert fired == ["theo"]
    daemon.note_wake(True)
    pipe2 = _pipe(spotter=["", "", "theo"], vosk="", whisper="")
    daemon.pipe = pipe2
    _feed(pipe2, name)
    daemon.note_wake(False)
    d = today()
    assert d["wakes_by"]["confirmed"] == 1
    assert d["rejected_by"]["held"] == 1


# --- the page, the overlay, monitor ------------------------------------------------------

def test_the_selector_writes_both_keys_and_refuses_what_cannot_run():
    text = page("Listening")
    assert 'objectName: "decisionChoice"' in text
    body = text[text.index("function chooseDecision"):]
    body = body[:body.index("readonly property string decisionHint")]
    assert 'v === "both" && bothBlocker !== ""' in body
    assert "decisionChoice.holding = false" in body, "a refused pick drops the chip's hold"
    assert body.index("return") < body.index('s.put("wakeBothAgree", true)'), \
        "refused before anything is written"
    assert 's.put("wakeCrossCheck", v === "either")' in body


def test_the_old_second_check_switch_is_gone():
    text = page("Listening")
    assert 'label: "Second check for short names"' not in text
    assert len(re.findall(r'put\("wakeCrossCheck"', text)) == 2


def test_the_reasons_are_plain_text():
    text = page("Listening")
    for name in ("decisionRefused", "decisionClosed"):
        block = text[text.index(f'objectName: "{name}"'):]
        block = block[:block.index("}")]
        assert "textFormat: Text.PlainText" in block, name


def test_the_overlay_reads_the_field_and_lists_closed_wakes():
    text = overlay()
    assert "root.vWakeDecision = (d.wake_decision" in text
    assert "vWakeDecision.closed === true" in text
    problems = text[text.index("readonly property var problems"):]
    assert "Wakes are held closed" in problems[:problems.index("return out")]


def test_the_page_knows_every_blocker_the_daemon_can_name():
    """The page decides on the code; every code it names must exist."""
    text = page("Listening")
    for code in re.findall(r'd\.blocked === "([a-z-]+)"', text):
        assert code in crosscheck.BLOCKERS, code


def test_monitor_says_the_mode(cfg_factory, monkeypatch):
    import monitor
    monkeypatch.setattr(monitor, "vosk_model", lambda: None)
    monkeypatch.setattr(monitor, "sherpa_model", lambda: Path("/models/kws"))
    mode, line = monitor.decision_line(cfg_factory(wakeBothAgree=True), "sherpa")
    assert mode == "both" and "both stages must agree" in line and "closed" not in line
    mode, line = monitor.decision_line(cfg_factory(wakeBothAgree=True), "openwakeword")
    assert "held closed" in line and "openWakeWord has no second check" in line
    mode, line = monitor.decision_line(cfg_factory(wakeCrossCheck=False), "sherpa")
    assert mode == "first"
    mode, line = monitor.decision_line(cfg_factory(), "sherpa")
    assert mode == "either"
    monkeypatch.setattr(monitor, "sherpa_model", lambda: None)
    mode, line = monitor.decision_line(cfg_factory(wakeBothAgree=True), "sherpa")
    assert "held closed" in line and "sherpa-onnx is not running" in line, \
        "no model: the daemon falls back to Vosk, which has no second check"
