"""The wait you actually sit through, measured and said every turn.

Before this the journal had "agent 37.0s, first token 3133ms", and the first
token is the model's own figure, counted from the moment the request left.
It leaves out the pause the endpoint waits through, Whisper, and starting the
agent -- most of the silence after you stop talking -- so the number that
decides how this feels was the one nothing recorded.
"""
from __future__ import annotations

import re
import time

from adapters.base import Chunk


class Agent:
    name = "stub"
    last_start = "warm"

    def __init__(self, *parts):
        self.parts = parts

    def send(self, text, session_id=None):
        for p in self.parts:
            time.sleep(0.01)
            yield Chunk(text=p)

    def cancel(self):
        pass


def _speaker_with_a_clock(daemon):
    """The fake speaker, recording when its first sound went out the way
    runtime.Speaker does."""
    real = daemon.speaker.say

    def say(text, watch=None):
        daemon.speaker.first_audio_at = time.time()
        return real(text, watch)

    daemon.speaker.say = say


def test_a_turn_says_how_long_you_waited_and_where_it_went(daemon, capsys):
    daemon.agent = Agent("Hello there. ", "Second sentence.")
    _speaker_with_a_clock(daemon)
    now = time.time()
    clock = {"voice_end": now - 2.0, "endpoint": now - 0.4,
             "transcribed": now - 0.1}
    last = {"transcript": "x"}
    daemon.answer("a private question", last, clock=clock)

    out = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
    line = next((l for l in out.splitlines() if "heard →" in l), "")
    assert line, f"no latency line: {out!r}"
    assert "spoke in" in line
    for part in ("pause 1.6s", "whisper 0.3s", "stub warm", "voice"):
        assert part in line, f"{part!r} missing from {line!r}"
    assert last["latency_ms"] >= 2000, "and the panel gets the number"


def test_the_latency_line_carries_no_words(daemon, capsys):
    """Structural, never gated -- so it must hold nothing anybody said."""
    daemon.agent = Agent("The account number is four eight one five. ")
    _speaker_with_a_clock(daemon)
    now = time.time()
    daemon.answer("what is my account number", {"transcript": "x"},
                  clock={"voice_end": now - 1, "endpoint": now})
    out = capsys.readouterr().out
    assert "heard →" in out
    assert "four eight" not in out and "account number" not in out


def test_without_a_voice_it_counts_to_the_words_on_screen(daemon, capsys):
    daemon.agent = Agent("Hello there. ")
    daemon.speaker = None
    now = time.time()
    daemon.answer("hi", {"transcript": "x"},
                  clock={"voice_end": now - 1, "endpoint": now})
    assert "heard → showed in" in capsys.readouterr().out


def test_a_turn_with_no_clock_still_runs(daemon, capsys):
    """The echo path and every caller that predates the clock."""
    daemon.agent = Agent("Hello there. ")
    daemon.answer("hi", {"transcript": "x"})
    assert "heard →" not in capsys.readouterr().out
    assert daemon.speaker.said


def test_a_new_turn_clears_the_last_ones_number():
    """The panel keeps a value until it is told otherwise."""
    import wake_listen
    assert wake_listen._empty_turn()["latency_ms"] == 0
