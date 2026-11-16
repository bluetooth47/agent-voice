"""The short sounds: what they are, when they play, and what they must not do.

What they must not do is the larger half. A chime the microphone hears is a
chime that counts as the person talking; a chime under the first word of a
reply is noise; a chime on a locked machine is the machine announcing a
turn to whoever is standing there.
"""
from __future__ import annotations

import array
import time

import pytest

import chimes
from adapters.base import Chunk


# --- the sounds ----------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(chimes.TONES))
def test_each_sound_starts_and_ends_silent(name):
    """A note that starts or stops away from zero clicks."""
    notes = chimes.TONES[name]
    pcm = array.array("h")
    pcm.frombytes(chimes.synth(notes, chimes.LEVEL[name]))
    at = 0
    for _freq, ms in notes:
        n = int(chimes.RATE * ms / 1000)
        assert pcm[at] == 0 and pcm[at + n - 1] == 0, f"{name} clicks"
        at += n
    assert at == len(pcm)


@pytest.mark.parametrize("name", sorted(chimes.TONES))
def test_each_sound_is_quiet_and_short(name):
    pcm = array.array("h")
    pcm.frombytes(chimes.synth(chimes.TONES[name], chimes.LEVEL[name]))
    assert max(abs(s) for s in pcm) <= 32767 * chimes.LEVEL[name] + 1
    assert len(pcm) / chimes.RATE < 0.35, "punctuation, not an announcement"


def test_the_three_are_told_apart_by_shape_not_only_pitch():
    lengths = {len(chimes.TONES[n]) for n in chimes.TONES}
    assert lengths == {1, 2, 3}


def test_heard_is_the_quietest_because_it_plays_every_turn():
    assert chimes.LEVEL["heard"] == min(chimes.LEVEL.values())


# --- when they play --------------------------------------------------------------

class FakeChimes:
    def __init__(self, length=0.2, fail=False):
        self.played: list[str] = []
        self.settled = 0
        self.length = length
        self.fail = fail

    def play(self, name):
        if self.fail:
            raise OSError("no output device")
        self.played.append(name)
        return self.length

    def settle(self):
        self.settled += 1


def test_a_chime_is_not_taken_for_the_person_talking(daemon):
    daemon.chimes = FakeChimes(length=0.2)
    daemon.cfg._values["chimes"] = True
    before = time.time()
    daemon.chime("wake")
    assert daemon.chimes.played == ["wake"]
    assert daemon._chime_until >= before + 0.2, \
        "our own chime would be heard as the person starting to talk"


def test_while_a_chime_sounds_loudness_is_not_speech(daemon):
    class Pipe:
        threshold_db = -40.0
    daemon.pipe = Pipe()
    daemon.chimes = FakeChimes(length=0.5)
    daemon.cfg._values["chimes"] = True
    assert daemon.voiced(-10.0)
    daemon.chime("wake")
    assert not daemon.voiced(-10.0), "our own chime counted as the person"
    daemon._chime_until = 0.0
    assert daemon.voiced(-10.0) and not daemon.voiced(-60.0)


def test_a_chime_does_not_throw_away_what_was_said_under_it(daemon):
    """Deafness drops frames whole. The frame after a wake word can hold the
    start of the request, so the chime masks loudness and keeps the audio."""
    daemon.chimes = FakeChimes(length=0.2)
    daemon.cfg._values["chimes"] = True
    daemon._deaf_until = 0.0
    daemon.chime("wake")
    assert daemon._deaf_until == 0.0


def test_switched_off_means_silent(daemon):
    daemon.chimes = FakeChimes()
    daemon.cfg._values["chimes"] = False
    daemon.chime("wake")
    assert daemon.chimes.played == []


@pytest.mark.parametrize("flag", ["locked", "yielded"])
def test_nothing_chimes_when_it_is_not_listening(daemon, flag):
    daemon.chimes = FakeChimes()
    daemon.cfg._values["chimes"] = True
    setattr(daemon, flag, True)
    daemon.chime("done")
    assert daemon.chimes.played == []


def test_a_missing_output_device_costs_nothing_but_a_line(daemon, capsys):
    daemon.chimes = FakeChimes(fail=True)
    daemon.cfg._values["chimes"] = True
    daemon.chime("wake")                         # must not raise
    daemon.chime("wake")
    out = capsys.readouterr().out
    assert out.count("cannot play sounds") == 1, "said once, not every wake"


def test_speech_waits_for_a_chime_to_finish(daemon):
    daemon.chimes = FakeChimes()
    daemon.speak("Hello there.", 0)
    assert daemon.chimes.settled == 1 and daemon.speaker.said


# --- the long-task chime --------------------------------------------------------

class Agent:
    name = "stub"

    def __init__(self, *chunks):
        self.chunks = chunks

    def send(self, text, session_id=None):
        yield from self.chunks

    def cancel(self):
        pass


def test_a_long_task_ends_with_the_done_chime(daemon, monkeypatch):
    import wake_listen
    monkeypatch.setattr(wake_listen, "LONG_TURN_S", 0.0)
    daemon.chimes = FakeChimes(length=0.0)
    daemon.cfg._values["chimes"] = True
    daemon.agent = Agent(Chunk(text="All done here."))
    daemon.answer("do the thing", {"transcript": "x"})
    assert daemon.chimes.played == ["done"]


def test_a_short_answer_does_not(daemon):
    daemon.chimes = FakeChimes(length=0.0)
    daemon.cfg._values["chimes"] = True
    daemon.agent = Agent(Chunk(text="Four."))
    daemon.answer("two plus two", {"transcript": "x"})
    assert daemon.chimes.played == []


def test_a_failed_task_says_why_instead_of_chiming(daemon, monkeypatch):
    import wake_listen
    monkeypatch.setattr(wake_listen, "LONG_TURN_S", 0.0)
    daemon.chimes = FakeChimes(length=0.0)
    daemon.cfg._values["chimes"] = True
    daemon.agent = Agent(Chunk(error="API Error: Connection error."))
    daemon.answer("do the thing", {"transcript": "x"})
    assert daemon.chimes.played == []
    assert "could not reach" in daemon.speaker.said[0]


def test_the_setting_exists_in_all_three_places():
    import json
    from pathlib import Path

    import runtime
    root = Path(__file__).resolve().parent.parent
    manifest = json.loads((root / "manifest.json").read_text())
    assert "chimes" in {k["key"] for k in manifest["barWidget"]["schema"]}
    assert manifest["barWidget"]["defaults"]["chimes"] is runtime.DEFAULTS["chimes"]
    assert '"chimes"' in (root / "Settings.qml").read_text()
