"""Speaking speed: one for the main agent, and one per extra agent.

A speed is a number on a loaded voice, not a different model, so changing it
must take effect on the next reply without reloading Piper -- the "plain
attribute after the spec check" rule in CLAUDE.md. And an extra agent with no
speed of its own follows the main agent's, including when that changes.
"""
from __future__ import annotations

import sys
import types

import pytest


# --- the value ----------------------------------------------------------------

@pytest.mark.parametrize("raw, want", [
    (100, 100), (150, 150), ("125", 125), (127.6, 128),
    (10, 50), (900, 200),                 # clamped to what still sounds like speech
    (None, 100), ("fast", 100), (True, 100), (0, 100), (-20, 100),
])
def test_a_speed_is_a_bounded_whole_percent(raw, want):
    from runtime import speed_pct
    assert speed_pct(raw) == want


def test_unset_can_mean_something_else():
    from runtime import speed_pct
    assert speed_pct(None, 0) == 0 and speed_pct(0, 0) == 0


def test_the_main_speed_ships_at_normal(cfg_factory):
    assert cfg_factory()["voiceSpeed"] == 100


class TestAgentSpeed:
    def test_an_agents_own_speed_comes_through(self, cfg_factory):
        cfg = cfg_factory(voiceAgents=[{"name": "friday", "speed": 140}])
        assert cfg.agents()[0]["speed"] == 140

    def test_no_speed_reads_as_same_as_main(self, cfg_factory):
        assert cfg_factory(voiceAgents=[{"name": "friday"}]).agents()[0]["speed"] == 0

    @pytest.mark.parametrize("raw", ["quick", None, [], {}, -5, False])
    def test_a_speed_that_is_not_one_reads_as_unset(self, cfg_factory, raw):
        cfg = cfg_factory(voiceAgents=[{"name": "friday", "speed": raw}])
        assert cfg.agents()[0]["speed"] == 0

    def test_an_extreme_speed_is_clamped(self, cfg_factory):
        cfg = cfg_factory(voiceAgents=[{"name": "friday", "speed": 1000}])
        assert cfg.agents()[0]["speed"] == 200


# --- the speaker ----------------------------------------------------------------

def _bare_speaker():
    import runtime
    return runtime.Speaker.__new__(runtime.Speaker)


def test_normal_speed_leaves_piper_alone():
    sp = _bare_speaker()
    assert sp.speed == 100 and sp.synthesis_config() is None


def test_faster_is_a_shorter_length_scale():
    sp = _bare_speaker()
    sp.speed = 200
    assert sp.length_scale() == pytest.approx(0.5)
    sp.speed = 50
    assert sp.length_scale() == pytest.approx(2.0)


def test_a_voices_own_pace_is_kept_underneath():
    sp = _bare_speaker()
    sp._base_scale = 1.2
    sp.speed = 120
    assert sp.length_scale() == pytest.approx(1.0)


def test_the_speed_reaches_piper(monkeypatch):
    """Through say(), the path that actually runs, not just the helper."""
    import threading

    seen = []

    class Cfg:
        def __init__(self, length_scale=None):
            self.length_scale = length_scale

    fake_piper = types.ModuleType("piper")
    fake_piper.SynthesisConfig = Cfg
    monkeypatch.setitem(sys.modules, "piper", fake_piper)

    class Stream:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def write(self, pcm): pass
        def abort(self): pass

    fake_sd = types.ModuleType("sounddevice")
    fake_sd.OutputStream = lambda **kw: Stream()
    fake_np = types.ModuleType("numpy")
    fake_np.int16 = "int16"
    fake_np.frombuffer = lambda b, dtype=None: memoryview(b).cast("h")
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    monkeypatch.setitem(sys.modules, "numpy", fake_np)

    class Voice:
        def synthesize(self, sentence, syn_config=None):
            seen.append(syn_config)
            yield types.SimpleNamespace(audio_int16_bytes=b"\x00\x01" * 100)

    sp = _bare_speaker()
    sp._voice, sp._rate, sp._stop = Voice(), 22050, threading.Event()
    sp.speed = 150
    sp.say("Hello there.")
    # Not pytest.approx: numpy is faked here, and approx looks for it.
    assert seen and abs(seen[0].length_scale - 100 / 150) < 1e-9

    seen.clear()
    sp.speed = 100
    sp.say("Hello there.")
    assert seen == [None]


# --- the daemon -------------------------------------------------------------------

class Loaded:
    """A voice already in memory. Building another one is what must not happen."""

    def __init__(self, name):
        self.name = self.requested = name
        self.speed = 100
        self.substituted_for = ""

    def superseded(self):
        return False


def test_changing_the_main_speed_does_not_reload_the_voice(daemon):
    daemon.cfg._values["speakReplies"] = True
    voice = Loaded(daemon.cfg.get_str("voice"))
    daemon.speaker = voice
    daemon.cfg._values["voiceSpeed"] = 140
    daemon.reconcile_voice()
    assert daemon.speaker is voice and voice.speed == 140


class TestPersonaSpeed:
    @pytest.fixture
    def recon(self, daemon, monkeypatch):
        import wake_listen

        class Agent:
            name = "claude"
            effort = None
            remembers = True
            levels = ("ask", "edits", "trusted")
            def posture(self, level): return level
            def cancel(self): pass
            def prepare(self, *a, **k): pass

        built = []
        monkeypatch.setattr(wake_listen, "load_adapter", lambda program, **kw: Agent())
        monkeypatch.setattr(wake_listen, "takes_effort", lambda a: False)
        daemon.pipe = type("P", (), {"phrase": "computer", "names": ["friday"],
                                     "unheard": {}})()

        def make(voice):
            built.append(voice)
            return Loaded(voice)

        daemon.make_speaker = make
        daemon.agent = Agent()
        daemon.built = built
        daemon.cfg._values["speakReplies"] = True
        return daemon

    def test_an_agent_with_no_speed_follows_the_main_one(self, recon):
        recon.cfg._values["voiceSpeed"] = 130
        recon.cfg._values["voiceAgents"] = [{"name": "friday"}]
        recon.reconcile_crew()
        p = recon.crew["friday"]
        assert p.speaker.speed == 130
        recon.cfg._values["voiceSpeed"] = 90
        recon.reconcile_crew()
        assert p.speaker.speed == 90 and len(recon.built) == 1

    def test_an_agents_own_speed_wins_and_keeps_its_conversation(self, recon):
        recon.cfg._values["voiceSpeed"] = 130
        recon.cfg._values["voiceAgents"] = [{"name": "friday"}]
        recon.reconcile_crew()
        p = recon.crew["friday"]
        p.session_id = "keep"
        recon.cfg._values["voiceAgents"] = [{"name": "friday", "speed": 175}]
        recon.reconcile_crew()
        assert p.speaker.speed == 175
        assert p.session_id == "keep" and len(recon.built) == 1
