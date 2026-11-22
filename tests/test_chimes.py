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
    from qml_sources import overlay
    assert '"chimes"' in overlay()


# --- which chime, and why (phase M2, bug J) ----------------------------------------

def test_every_chime_that_plays_says_which_and_why(daemon, capsys):
    """"A random be-deep" could not be traced: the journal said what the loop
    did and never what it played. A fixed phrase, never anything said."""
    daemon.chimes = FakeChimes(length=0.0)
    daemon.cfg._values["chimes"] = True
    daemon.chime("wake", "wake word")
    daemon.chime("heard", "end of what was said")
    out = capsys.readouterr().out
    assert "chime: wake (wake word)" in out
    assert "chime: heard (end of what was said)" in out


def test_a_chime_that_does_not_play_says_nothing(daemon, capsys):
    daemon.chimes = FakeChimes()
    daemon.cfg._values["chimes"] = False
    daemon.chime("wake", "wake word")
    assert "chime:" not in capsys.readouterr().out


def test_every_call_names_its_reason():
    """Parsed: a chime() with no reason is a sound the journal cannot place."""
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "daemon" / "wake_listen.py").read_text()
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "chime"]
    assert len(calls) == 4, "a chime site was added or lost: give it a reason"
    for call in calls:
        assert len(call.args) == 2, f"chime() at line {call.lineno} has no reason"


def _crew_with_theo_busy(daemon, monkeypatch):
    """Theo (the main agent) working, Sora beside him: the open microphone's
    stretch between turns, when the loop is waiting for a wake word."""
    import threading

    import wake_listen
    from conftest import FakeAgent
    from crew import Persona

    monkeypatch.setattr(wake_listen, "CHIME_TAIL_S", 0.0)
    monkeypatch.setattr(daemon, "publish_agent", lambda: None)
    daemon.chimes = FakeChimes(length=0.0)
    daemon.cfg._values["chimes"] = True
    sora = Persona("sora", {"id": "sora", "name": "sora", "label": "Sora"})
    sora.agent = FakeAgent()
    daemon.crew = {"sora": sora}
    daemon._main.name, daemon._main.label = "theo", "Theo"
    gate = threading.Event()
    daemon._main.thread = threading.Thread(target=gate.wait, args=(5,), daemon=True)
    daemon._main.thread.start()
    return gate


@pytest.mark.parametrize("heard, open_mic, chimed", [
    ("theo", True, False),      # its own name inside its own open microphone
    ("sora", True, True),       # somebody else woken: a real wake
    ("theo", False, True),      # no open microphone: a real wake
])
def test_a_wake_inside_the_open_mic_is_silent(daemon, monkeypatch, capsys,
                                               heard, open_mic, chimed):
    """The be-deep: in open mic, the agent's name heard while it worked
    stopped it and played "listening, go ahead" over a microphone that was
    listening already (2026-11-19 and 11-21, every open-mic wake). The wake
    still stops the turn; it just does not announce what was already so."""
    import frame_loop

    gate = _crew_with_theo_busy(daemon, monkeypatch)
    pipe = frame_loop.Pipe(feed_wake=frame_loop.wake_on(2))
    pipe.heard_phrase = heard
    items = [lambda: daemon.start_open_mic(daemon._main, say=False)] if open_mic else []
    items += [frame_loop.QUIET] * 4
    try:
        frame_loop.drive(daemon, monkeypatch, items, pipe=pipe)
    finally:
        gate.set()
    out = capsys.readouterr().out
    assert ("wake" in daemon.chimes.played) is chimed, daemon.chimes.played
    if not chimed:
        assert "chime: wake not played (open mic was already listening)" in out
    if heard == "theo":
        assert "stopping it" in out, "the wake no longer stops the turn"


@pytest.mark.parametrize("open_mic, played", [
    (True, ["heard"]),
    (False, ["wake", "heard", "wake"]),
])
def test_the_rearm_after_a_wake_stopped_the_reply(daemon, monkeypatch, open_mic, played):
    """With one agent, the wake word heard during a reply re-arms with the
    wake chime -- inside the open microphone, silently."""
    import frame_loop
    import wake_listen

    monkeypatch.setattr(wake_listen, "CHIME_TAIL_S", 0.0)
    monkeypatch.setattr(daemon, "publish_agent", lambda: None)
    daemon.chimes = FakeChimes(length=0.0)
    daemon.cfg._values["chimes"] = True
    turns = []

    def answer(text, last, clock=None):
        turns.append(text)
        if len(turns) > 1:
            raise frame_loop.Done()
        daemon._woke = True                 # the wake word stopped this reply
    monkeypatch.setattr(daemon, "answer", answer)
    pipe = frame_loop.Pipe(feed_wake=frame_loop.wake_on(1) if not open_mic else None)
    items = [lambda: daemon.start_open_mic(daemon._main, say=False)] if open_mic else []
    items += [frame_loop.LOUD] * 3 + [frame_loop.QUIET] * 5 + [frame_loop.stop()]
    frame_loop.drive(daemon, monkeypatch, items, pipe=pipe)
    assert len(turns) == 1
    assert daemon.chimes.played == played
