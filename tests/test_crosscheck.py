"""The second check: Vosk and Whisper re-hear short bursts sherpa-onnx let
pass, and both must hear the same name (FINDINGS §24).

What has to hold:

- a name wakes only when both engines agree, or -- for a name Vosk cannot
  hear at all -- when Whisper heard the bare name and nothing else;
- a stand-in spelling votes for a name missing from Vosk's lexicon;
- bursts are cut by level, carry their preroll and quiet tail, and are
  dropped when too short or too long;
- the spotter's own hit wins and clears the half-cut burst;
- Whisper is not asked when every name has a Vosk vote and Vosk heard none;
- the setting exists in all three places.

Nothing here needs a model.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "daemon"))
sys.path.insert(0, str(ROOT / "tests"))

import crosscheck  # noqa: E402
from crosscheck import Bursts, decide, leading_name, vosk_grammar, vosk_heard  # noqa: E402
from qml_sources import page  # noqa: E402

NAMES = ["theo", "sora"]


# --- matching the transcript ---------------------------------------------------

@pytest.mark.parametrize("text,want", [
    ("Theo.", ("theo", 0)),
    ("Hey, Theo.", ("theo", 0)),
    ("Okay hey Sora?", ("sora", 0)),
    ("Theo, what time is it?", ("theo", 4)),
    ("Theo's coming over later.", ("", 0)),
    ("I told Theo.", ("", 0)),
    ("Pluto.", ("", 0)),
    ("", ("", 0)),
])
def test_the_name_must_open_the_transcript(text, want):
    assert leading_name(text, NAMES) == want


def test_the_longest_name_wins():
    assert leading_name("Hey computer, hi", ["computer", "hey computer"]) == ("hey computer", 1)


# --- the rule -------------------------------------------------------------------

def test_both_engines_agreeing_wakes_it():
    assert decide(NAMES, {"theo", "sora"}, "theo", "Theo.")[0] == "theo"
    assert decide(NAMES, {"theo", "sora"}, "sora", "Hey, Sora.")[0] == "sora"


def test_one_engine_alone_does_not():
    # Vosk hears "theo" in "Video" 8/10; Whisper hears "Sora" in "Story" 2/10.
    assert decide(NAMES, {"theo", "sora"}, "theo", "Video.") == ("", "vosk only — whisper disagreed")
    assert decide(NAMES, {"theo", "sora"}, "", "Sora.")[0] == ""
    assert decide(NAMES, {"theo", "sora"}, "sora", "Theo.")[0] == "", "they must agree on WHICH name"


def test_a_long_sentence_after_the_name_does_not():
    assert decide(NAMES, {"theo"}, "theo", "Theo, what time is it?")[0] == ""
    assert decide(NAMES, {"theo"}, "theo", "Theo, you there?")[0] == "theo"


def test_a_name_without_a_vote_needs_the_bare_name():
    assert decide(NAMES, {"theo"}, "", "Sora.")[0] == "sora"
    assert decide(NAMES, {"theo"}, "", "Hey Sora!")[0] == "sora"
    assert decide(NAMES, {"theo"}, "", "Sora, can you help?")[0] == ""


def test_nothing_heard_says_nothing():
    assert decide(NAMES, {"theo", "sora"}, "", "Thank you.") == ("", "")


# --- the Vosk grammar -----------------------------------------------------------

def test_a_stand_in_votes_for_a_name_vosk_lacks():
    knows = {"theo", "zora"}.__contains__
    grammar, means = vosk_grammar(NAMES, knows)
    assert grammar == ["theo", "zora"]
    assert vosk_heard("zora", means) == "sora"
    assert vosk_heard("theo", means) == "theo"
    assert vosk_heard("", means) == ""


def test_a_name_with_no_stand_in_has_no_vote():
    grammar, means = vosk_grammar(["theo", "ziggy"], {"theo"}.__contains__)
    assert grammar == ["theo"] and set(means.values()) == {"theo"}


# --- cutting bursts -------------------------------------------------------------

LOUD, QUIET = b"L" * 4, b"q" * 4


def _run(cutter, pattern):
    out = []
    for c in pattern:
        got = cutter.feed(LOUD if c == "L" else QUIET, c == "L")
        if got is not None:
            out.append(got)
    return out


def test_a_short_burst_comes_back_with_preroll_and_tail():
    got = _run(Bursts(200), "qqLLqq")
    assert got == [QUIET + LOUD + LOUD + QUIET + QUIET]


def test_one_quiet_frame_inside_a_name_does_not_end_it():
    assert len(_run(Bursts(200), "qLLqLLqq")) == 1


def test_a_blip_is_too_short():
    assert _run(Bursts(200), "qLqqq") == []


def test_a_sentence_is_too_long():
    n = crosscheck.MAX_BURST_MS // 200 + 2
    assert _run(Bursts(200), "q" + "L" * n + "qq") == []
    # and the cutter is usable again afterwards
    assert len(_run(Bursts(200), "qLLqq")) == 1


# --- the Pipeline ---------------------------------------------------------------

class FakeSherpa:
    def __init__(self):
        self.heard, self.resets = "", 0

    def feed(self, pcm):
        hit, self.heard = self.heard, ""
        return hit

    def reset(self):
        self.resets += 1


def _pipe(vosk="", has_vote=("theo", "sora"), whisper=""):
    import wake_listen
    pipe = object.__new__(wake_listen.Pipeline)
    pipe._oww, pipe._sherpa = None, FakeSherpa()
    pipe.phrase, pipe.names = "theo", ["sora"]
    pipe.cross_check, pipe._log_speech = True, False
    pipe.threshold_db, pipe.refractory_ms = -40.0, 2000
    pipe._refractory_until = 0.0
    pipe.asked = []
    pipe._vosk_vote = lambda audio, names: (vosk, set(has_vote))
    pipe._whisper_names = lambda audio, names: pipe.asked.append(audio) or whisper
    return pipe


def _say(pipe, pattern):
    fired = []
    for c in pattern:
        if pipe.feed_wake(b"\0" * 8, -20.0 if c == "L" else -70.0):
            fired.append(pipe.heard_phrase)
    return fired


def test_the_pipeline_wakes_on_agreement_and_says_why(capsys):
    pipe = _pipe(vosk="sora", whisper="Sora.")
    assert _say(pipe, "qLLqq") == ["sora"]
    assert "second check: sora by vosk + whisper" in capsys.readouterr().out
    assert pipe._sherpa.resets == 1


def test_a_near_miss_is_logged_without_the_words(capsys):
    pipe = _pipe(vosk="theo", whisper="Video, please")
    assert _say(pipe, "qLLqq") == []
    out = capsys.readouterr().out
    assert "no wake — vosk only" in out
    assert "Video" not in out, "logSpeech is off: the transcript stays out of the journal"


def test_whisper_is_not_asked_when_vosk_heard_nothing():
    pipe = _pipe(vosk="")
    assert _say(pipe, "qLLqq") == []
    assert pipe.asked == []


def test_whisper_is_asked_when_a_name_has_no_vosk_vote():
    pipe = _pipe(vosk="", has_vote=("theo",), whisper="Sora.")
    assert _say(pipe, "qLLqq") == ["sora"]


def test_the_spotter_wins_and_clears_the_burst():
    pipe = _pipe(vosk="theo", whisper="Theo.")
    _say(pipe, "qL")
    pipe._sherpa.heard = "theo"
    assert _say(pipe, "L") == ["theo"]
    pipe._refractory_until = 0.0
    assert _say(pipe, "qq") == [], "the cleared burst must not wake it a second time"


def test_off_means_off():
    pipe = _pipe(vosk="theo", whisper="Theo.")
    pipe.cross_check = False
    assert _say(pipe, "qLLqq") == []


# --- the setting ----------------------------------------------------------------

def test_the_setting_exists_in_all_three_places():
    from runtime import DEFAULTS, TOML_ALIASES
    manifest = json.loads((ROOT / "manifest.json").read_text())["barWidget"]
    assert DEFAULTS["wakeCrossCheck"] is True
    assert manifest["defaults"]["wakeCrossCheck"] is True
    assert TOML_ALIASES["wakeCrossCheck"] == ("wake", "cross_check")
    assert any(e["key"] == "wakeCrossCheck" for e in manifest["schema"])
    assert 's.put("wakeCrossCheck"' in page("Listening")


def test_the_window_is_a_setting_not_a_constant():
    """crossCheckMinMs / crossCheckMaxMs: plain attributes, so a change
    applies to the next burst."""
    cut = Bursts(200, min_ms=600, max_ms=800)
    assert _run(cut, "qLLqq") == [], "400ms is under a 600ms minimum"
    assert len(_run(cut, "qLLLLqq")) == 1
    cut.max_ms = 600
    assert _run(cut, "qLLLLqq") == [], "800ms is over the new maximum"
