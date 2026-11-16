"""Talking over a reply on a headset, and being heard to the end.

Two halves. Whether the sound is going into somebody's ears decides whether
barge-in runs at all, because through laptop speakers it cannot work (our
own voice reaches the microphone as loudly as theirs) and on a headset it
measured clean. And once it has stopped a reply, what the person said has to
survive: it used to be fed to the detector and dropped as echo, so stopping
was all that talking over it could do, and the request had to be repeated
after the wake word.

Nothing here needs numpy or a microphone. The detector is replaced by a stub
that fires on a chosen frame; the detector itself is test_barge's business.
"""
from __future__ import annotations

import json
import queue
import subprocess
import types

import pytest

import headset
from headset import default_output as REAL_DEFAULT_OUTPUT  # before conftest stubs it
from headset import is_headset


# What `pactl -f json list sinks` printed on the development machine, cut to
# the fields that matter. Shokz over HFP, and the laptop's own card.
SHOKZ = {
    "name": "bluez_output.A0_0C_E2_42_92_D2.1",
    "active_port": "headset-hf-output",
    "ports": [{"name": "headset-hf-output", "type": "Headset"}],
    "properties": {"device.form_factor": "headset",
                   "device.description": "OpenRun Pro 2 by Shokz",
                   "device.api": "bluez5"},
}
LAPTOP = {
    "name": "alsa_output.pci-0000_00_1f.3.analog-stereo",
    "active_port": "analog-output-speaker",
    "ports": [{"name": "analog-output-speaker", "type": "Speaker"},
              {"name": "analog-output-headphones", "type": "Headphones"}],
    "properties": {"device.form_factor": "internal",
                   "device.description": "Built-in Audio"},
}


class TestWhatCountsAsAHeadset:
    def test_a_bluetooth_headset(self):
        assert is_headset(SHOKZ)

    def test_laptop_speakers_are_not(self):
        assert not is_headset(LAPTOP)

    def test_wired_headphones_on_the_laptops_own_card(self):
        """The card says "internal" whatever is plugged in; the port is what
        changes when a 3.5mm jack goes in."""
        wired = {**LAPTOP, "active_port": "analog-output-headphones"}
        assert is_headset(wired)

    def test_an_older_pactl_with_no_port_type(self):
        wired = {**LAPTOP, "active_port": "analog-output-headphones",
                 "ports": [{"name": "analog-output-headphones"}]}
        assert is_headset(wired)

    def test_a_bluetooth_speaker_is_not(self):
        """A2DP to a speaker on the desk is the laptop's problem again, only
        louder."""
        speaker = {"name": "bluez_output.x", "active_port": "speaker-output",
                   "ports": [{"name": "speaker-output", "type": "Speaker"}],
                   "properties": {"device.form_factor": "speaker"}}
        assert not is_headset(speaker)

    @pytest.mark.parametrize("sink", [
        {}, {"properties": None}, {"properties": "headset"},
        {"active_port": None, "ports": None},
        {"active_port": "x", "ports": ["not a dict"]},
    ])
    def test_odd_shapes_are_not_a_headset(self, sink):
        assert not is_headset(sink)


class TestAskingTheSoundServer:
    def _pactl(self, monkeypatch, default, sinks):
        def run(argv, **kw):
            if argv[:2] == ["pactl", "get-default-sink"]:
                out = default
            else:
                out = sinks if isinstance(sinks, str) else json.dumps(sinks)
            return types.SimpleNamespace(stdout=out, returncode=0)
        monkeypatch.setattr(headset.subprocess, "run", run)

    def test_the_default_sink_is_the_one_judged(self, monkeypatch):
        self._pactl(monkeypatch, SHOKZ["name"] + "\n", [LAPTOP, SHOKZ])
        assert REAL_DEFAULT_OUTPUT() == (True, "OpenRun Pro 2 by Shokz")
        self._pactl(monkeypatch, LAPTOP["name"], [LAPTOP, SHOKZ])
        assert REAL_DEFAULT_OUTPUT() == (False, "Built-in Audio")

    @pytest.mark.parametrize("default, sinks", [
        ("", [SHOKZ]),                      # no default sink
        ("nowhere", [SHOKZ]),               # a default that is not listed
        (SHOKZ["name"], "Unknown option -f"),  # pactl too old for JSON
        (SHOKZ["name"], {"not": "a list"}),
    ])
    def test_cannot_tell_is_none(self, monkeypatch, default, sinks):
        self._pactl(monkeypatch, default, sinks)
        assert REAL_DEFAULT_OUTPUT() is None

    @pytest.mark.parametrize("exc", [
        FileNotFoundError("pactl"), subprocess.TimeoutExpired("pactl", 2)])
    def test_no_pactl_is_none(self, monkeypatch, exc):
        def run(*a, **k):
            raise exc
        monkeypatch.setattr(headset.subprocess, "run", run)
        assert REAL_DEFAULT_OUTPUT() is None


class TestWhenItListens:
    def _output(self, monkeypatch, answer):
        calls = []

        def ask():
            calls.append(1)
            return answer
        monkeypatch.setattr(headset, "default_output", ask)
        return calls

    def test_on_a_headset_by_default(self, daemon, monkeypatch):
        self._output(monkeypatch, (True, "Shokz"))
        assert daemon.cfg.get_bool("bargeOnHeadset"), "the default changed"
        assert not daemon.cfg.get_bool("bargeIn"), "the default changed"
        assert daemon.barge_wanted()

    @pytest.mark.parametrize("answer", [(False, "Built-in Audio"), None])
    def test_not_through_speakers_or_when_it_cannot_tell(
            self, daemon, monkeypatch, answer):
        self._output(monkeypatch, answer)
        assert not daemon.barge_wanted()

    def test_the_setting_turns_it_off(self, daemon, monkeypatch):
        calls = self._output(monkeypatch, (True, "Shokz"))
        daemon.cfg._values["bargeOnHeadset"] = False
        assert not daemon.barge_wanted()
        assert not calls, "asked the sound server for a setting that is off"

    def test_barge_in_everywhere_does_not_need_to_ask(self, daemon, monkeypatch):
        calls = self._output(monkeypatch, (False, "Built-in Audio"))
        daemon.cfg._values["bargeIn"] = True
        assert daemon.barge_wanted()
        assert not calls

    def test_asked_on_the_idle_poll_not_per_sentence(self, daemon, monkeypatch):
        """23ms of pactl in front of every sentence is latency somebody
        spent a day removing. The idle poll keeps the answer fresh."""
        calls = self._output(monkeypatch, (True, "Shokz"))
        daemon.reconcile_output()
        for _ in range(5):
            assert daemon.barge_wanted()
        assert len(calls) == 1

    def test_headphones_coming_off_are_noticed(self, daemon, monkeypatch):
        self._output(monkeypatch, (True, "Shokz"))
        assert daemon.reconcile_output()
        self._output(monkeypatch, (False, "Built-in Audio"))
        daemon._output_at = 0.0               # the TTL has passed
        assert not daemon.reconcile_output()
        assert not daemon.barge_wanted()

    def test_refresh_reconciles_it(self, daemon, monkeypatch):
        """Outside the config guard: headphones going on changes no setting."""
        calls = self._output(monkeypatch, (True, "Shokz"))
        daemon.pipe = types.SimpleNamespace(reconcile_vocab=lambda: None)
        monkeypatch.setattr(daemon, "reconcile_agent", lambda: None)
        monkeypatch.setattr(daemon, "reconcile_voice", lambda: None)
        monkeypatch.setattr(daemon.cfg, "reload", lambda: False, raising=False)
        daemon.refresh()
        assert calls, "the idle poll never asked where the sound goes"


class StubBarge:
    """BargeIn-shaped: fires on the `fire_on`th frame it is fed."""

    def __init__(self, fire_on):
        self.fire_on, self.fed, self.factor = fire_on, 0, 1.5

    def reset(self):
        self.fed = 0

    def feed(self, pcm):
        self.fed += 1
        return self.fed == self.fire_on


def frame(n: int) -> bytes:
    return bytes([n]) * 6400


@pytest.fixture
def barging(daemon):
    """A daemon listening on a headset, with a microphone queue."""
    daemon.cfg._values["bargeIn"] = True
    daemon.enabled, daemon.locked, daemon.yielded = True, False, False
    daemon._frames = queue.Queue()
    return daemon


class TestWhatTheySaidIsKept:
    def test_the_start_of_it_is_kept_and_the_rest_left_queued(self, barging):
        for n in range(1, 7):
            barging._frames.put(frame(n))
        barging._barge = StubBarge(fire_on=4)

        watch = barging._barge_watch()
        assert watch() is True, "the detector fired and the reply went on"

        assert barging._barged == [frame(2), frame(3), frame(4)], \
            "the frames before the one that fired hold their first word"
        assert [barging._frames.get_nowait() for _ in range(2)] == \
            [frame(5), frame(6)]
        assert barging._interrupt.is_set()
        assert barging.agent.cancelled, "the agent went on working"

    def test_deafen_keeps_the_rest_of_their_sentence(self, barging):
        """speak() deafens after every sentence, and answer() again after an
        interrupt: both used to drop the queue, which was the person
        mid-sentence."""
        barging._barged = [frame(1)]
        barging._frames.put(frame(2))
        barging.deafen(350)
        assert barging._frames.qsize() == 1
        assert barging._deaf_until == 0.0, "the deaf window would drop it next"

    def test_a_lock_still_drops_it(self, barging):
        barging._barged = [frame(1)]
        barging._frames.put(frame(2))
        barging.locked = True
        barging.deafen(0)
        assert barging._frames.qsize() == 0
        assert barging.take_barge() is None, \
            "words from before a lock were carried into a turn after it"

    def test_taken_once(self, barging):
        barging._barged = [frame(1)]
        assert barging.take_barge() == [frame(1)]
        assert barging.take_barge() is None

    def test_a_new_turn_forgets_a_stale_one(self, barging):
        barging._barged = [frame(1)]
        barging.agent = None
        barging.speaker = None
        barging.answer("hello", {})
        assert barging._barged is None

    def test_through_a_whole_reply(self, barging):
        """Driven through answer(): the speaker's own watch is what fires,
        the rest of the reply is not spoken, no follow-up window opens, and
        what was said is waiting for the run loop."""
        from test_interrupt import FakeAgent

        class Speaker:
            name = "stub"
            said: list[str] = []

            def say(self, text, watch=None):
                self.said.append(text)
                barging._frames.put(frame(9))
                if watch is not None:
                    watch()

            def cancel(self):
                pass

        barging.speaker = Speaker()
        barging.agent = FakeAgent(["First sentence here. ", "Second one. ",
                                   "Third one. "])
        barging.poll_session = lambda: None
        barging._barge = StubBarge(fire_on=1)
        barging.pipe = types.SimpleNamespace(conversation=True)

        barging.answer("tell me three things", {})

        assert len(barging.speaker.said) == 1, barging.speaker.said
        assert not barging.arm_follow_up()
        assert barging.take_barge() == [frame(9)]

    def test_no_voice_interrupt_without_barge_in(self, barging, monkeypatch):
        """The keybind and the stop button interrupt too, and those mean
        stop: they must not open a capture."""
        barging.cfg._values["bargeIn"] = False
        barging.cfg._values["bargeOnHeadset"] = False
        assert barging._barge_watch() is None
        barging.state.publish("speaking")
        barging._on_interrupt()
        assert barging.take_barge() is None


def test_the_run_loop_hears_the_rest_without_the_wake_word(daemon, monkeypatch):
    """The point of all of it, driven through the real frame loop. The fake
    wake word fires once only, so a second turn reaching the agent can only
    have come from the capture barge-in opened."""
    from test_states import _drive_one_turn

    loud = b"\x00\x40" * 3200

    def on_answer(n, text):
        if n == 1:
            # What the reply's watch does when it fires.
            daemon._barged = [loud]
            daemon._interrupt.set()
            return False
        return True

    sent = _drive_one_turn(daemon, monkeypatch, "actually make it Tuesday",
                           on_answer=on_answer)
    assert sent == ["actually make it Tuesday"] * 2


def test_the_setting_exists_in_all_three_places():
    from pathlib import Path

    from runtime import DEFAULTS, TOML_ALIASES

    root = Path(__file__).resolve().parent.parent
    manifest = json.loads((root / "manifest.json").read_text())
    widget = manifest["barWidget"]
    assert widget["defaults"]["bargeOnHeadset"] is True
    assert any(s["key"] == "bargeOnHeadset" for s in widget["schema"])
    assert DEFAULTS["bargeOnHeadset"] is True
    assert "bargeOnHeadset" in TOML_ALIASES
    assert 'root.setting("bargeOnHeadset"' in (root / "Settings.qml").read_text()
