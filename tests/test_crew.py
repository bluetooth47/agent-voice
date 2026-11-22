"""More than one agent, each woken by its own name, working at the same time.

Asked for in this shape: an agent called "computer", another called something
else, as many as you like, each with its own model -- and more than one of
them able to work at once. Each also has its own voice, permission level and
folder, and its own conversation.

The rules worth holding, because each is a way this goes wrong out loud:

- a name is a word the wake engine can actually hear, or it is refused and
  the settings say why;
- an extra agent's permission level and folder are its own, and an agent the
  hook cannot find is asked about, never trusted;
- two agents can think at once, but only one speaks at a time, nobody is
  talked over, and one reply is never interleaved with another;
- stopping one agent stops that one.

Nothing here needs numpy, Piper, Vosk or a microphone.
"""
from __future__ import annotations

import json
import sys
import threading
import time

import pytest


def _until(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


# --- the setting --------------------------------------------------------------

class TestConfigAgents:
    def test_none_by_default(self, cfg_factory):
        assert cfg_factory().agents() == []

    def test_a_well_formed_agent_comes_through(self, cfg_factory):
        cfg = cfg_factory(voiceAgents=[{
            "name": "Jarvis", "agent": "claude", "model": "sonnet",
            "effort": "high", "voice": "amy-medium", "level": "edits",
            "projectDir": "~/code"}])
        assert cfg.agents() == [{
            "name": "jarvis", "id": "jarvis", "label": "Jarvis", "agent": "claude", "model": "sonnet",
            "effort": "high", "voice": "amy-medium", "speed": 0, "narration": "", "instructions": "", "level": "edits",
            "tools": {"desktop": "inherit", "browser": "inherit", "omarchySkill": "inherit"},
            "detected": {},
            "skillsOff": [],
            "notesWrite": "allow", "collaboration": "announce", "acceptsWork": True,
            "projectDir": "~/code", "endpoint": None}]

    def test_the_program_defaults_to_claude(self, cfg_factory):
        assert cfg_factory(voiceAgents=[{"name": "friday"}]).agents()[0]["agent"] == "claude"

    @pytest.mark.parametrize("name", [
        "", "   ", "r2d2", "jarvis!", "one two three four", "-rf", "ünïcode",
        "a" * 200, None, 7,
    ])
    def test_a_name_that_could_never_be_heard_is_dropped(self, cfg_factory, name):
        assert cfg_factory(voiceAgents=[{"name": name}]).agents() == []

    def test_a_name_taken_twice_keeps_the_first(self, cfg_factory):
        cfg = cfg_factory(voiceAgents=[{"name": "friday", "model": "opus"},
                                       {"name": "Friday", "model": "haiku"}])
        assert [a["model"] for a in cfg.agents()] == ["opus"]

    def test_values_that_would_become_arguments_are_checked(self, cfg_factory):
        """A model or effort ends up after a flag on a CLI that can run
        commands: anything that is not plainly one reads as unset."""
        cfg = cfg_factory(voiceAgents=[{
            "name": "friday", "agent": "claude --dangerously", "model": "--yolo",
            "effort": "ludicrous", "voice": "../../etc/passwd"}])
        a = cfg.agents()[0]
        assert a["agent"] == "" and a["model"] == "" and a["effort"] == ""
        assert a["voice"] == ""

    @pytest.mark.parametrize("level", [None, "", "TRUSTED", "root", 1, True])
    def test_a_level_nobody_chose_is_ask(self, cfg_factory, level):
        cfg = cfg_factory(voiceAgents=[{"name": "friday", "level": level}])
        assert cfg.agents()[0]["level"] == "ask"

    @pytest.mark.parametrize("raw", [None, "jarvis", {"name": "jarvis"}, 3, [None, 4, "x"]])
    def test_a_malformed_list_is_no_agents(self, cfg_factory, raw):
        assert cfg_factory(voiceAgents=raw).agents() == []

    def test_there_is_a_ceiling(self, cfg_factory):
        from runtime import MAX_AGENTS
        names = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot",
                 "golf", "hotel", "india", "juliet"]
        cfg = cfg_factory(voiceAgents=[{"name": n} for n in names])
        assert len(cfg.agents()) == MAX_AGENTS

    def test_an_agent_switched_off_is_left_out(self, cfg_factory):
        cfg = cfg_factory(voiceAgents=[{"name": "friday", "enabled": False},
                                       {"name": "jarvis"}])
        assert [a["name"] for a in cfg.agents()] == ["jarvis"]
        assert cfg.disabled_agents() == {"friday"}
        assert cfg.agent_named("friday") is None

    @pytest.mark.parametrize("value", [True, None, 0, "", "false", "off", []])
    def test_only_an_explicit_false_switches_it_off(self, cfg_factory, value):
        """Missing means on, so a list written before the switch existed
        keeps every agent; a hand-edited oddity is not read as off either."""
        cfg = cfg_factory(voiceAgents=[{"name": "friday", "enabled": value}])
        assert [a["name"] for a in cfg.agents()] == ["friday"]
        assert cfg.disabled_agents() == set()

    def test_an_off_agent_keeps_its_name_taken(self, cfg_factory):
        """Switching it back on must not find a second agent answering to
        the same name."""
        cfg = cfg_factory(voiceAgents=[{"name": "friday", "enabled": False},
                                       {"name": "Friday", "model": "haiku"}])
        assert cfg.agents() == []

    def test_an_off_agent_counts_toward_the_ceiling(self, cfg_factory):
        from runtime import MAX_AGENTS
        names = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot",
                 "golf", "hotel", "india"]
        raw = [{"name": n, "enabled": False} for n in names[:2]]
        raw += [{"name": n} for n in names[2:]]
        cfg = cfg_factory(voiceAgents=raw)
        assert len(cfg.agents()) + len(cfg.disabled_agents()) == MAX_AGENTS

    def test_an_off_agent_is_not_listened_for(self, cfg_factory):
        from wake_listen import wanted_names
        cfg = cfg_factory(voiceAgents=[{"name": "friday", "enabled": False},
                                       {"name": "jarvis"}])
        assert wanted_names(cfg) == ["jarvis"]

    def test_agent_named(self, cfg_factory):
        cfg = cfg_factory(voiceAgents=[{"name": "friday", "level": "trusted"}])
        assert cfg.agent_named("friday")["level"] == "trusted"
        assert cfg.agent_named("jarvis") is None
        assert cfg.agent_named("") is None

    def test_it_is_declared_in_all_the_places_a_setting_lives(self):
        from conftest import ROOT
        from runtime import DEFAULTS, TOML_ALIASES
        manifest = json.loads((ROOT / "manifest.json").read_text())
        assert manifest["barWidget"]["defaults"]["voiceAgents"] == []
        assert DEFAULTS["voiceAgents"] == []
        assert "voiceAgents" in TOML_ALIASES
        from qml_sources import overlay
        assert "voiceAgents" in overlay()


# --- who a sentence is for ----------------------------------------------------

class TestRoute:
    NAMES = ["computer", "jarvis", "mister fox"]

    @pytest.mark.parametrize("text,expect", [
        ("Jarvis, what time is it?", ("jarvis", "what time is it?")),
        ("jarvis what time is it", ("jarvis", "what time is it")),
        ("Hey Jarvis, what time is it?", ("jarvis", "what time is it?")),
        ("Okay, Jarvis. Stop.", ("jarvis", "Stop.")),
        ("Mister Fox, list the files.", ("mister fox", "list the files.")),
        ("Jarvis.", ("jarvis", "")),
        ("Ask Jarvis about it.", ("", "Ask Jarvis about it.")),
        ("Jarvisson, hello", ("", "Jarvisson, hello")),
        ("What time is it?", ("", "What time is it?")),
        ("", ("", "")),
    ])
    def test_route(self, text, expect):
        from crew import route
        assert route(text, self.NAMES) == expect

    def test_a_main_phrase_with_a_greeting_in_it(self):
        from crew import route
        assert route("Hey computer, hi", ["hey computer", "jarvis"]) == \
            ("hey computer", "hi")


# --- the wake engine ----------------------------------------------------------

class FakeModel:
    def __init__(self, known):
        self.known = set(known)

    def vosk_model_find_word(self, word):
        return 1 if word in self.known else -1


def _pipe(known=("computer", "jarvis", "friday", "hey")):
    import wake_listen
    pipe = object.__new__(wake_listen.Pipeline)
    pipe._model = FakeModel(known)
    pipe.phrase = "computer"
    pipe.names, pipe.unheard = [], {}
    return pipe


class TestWakeNames:
    def test_names_the_engine_knows_are_listened_for(self):
        pipe = _pipe()
        pipe._choose_names(["jarvis", "friday"])
        assert pipe.names == ["jarvis", "friday"] and pipe.unheard == {}

    def test_a_word_it_does_not_know_is_refused_and_said(self):
        pipe = _pipe()
        pipe._choose_names(["omarchy", "jarvis"])
        assert pipe.names == ["jarvis"]
        assert "omarchy" in pipe.unheard["omarchy"]

    def test_the_main_phrase_cannot_be_taken(self):
        pipe = _pipe()
        pipe._choose_names(["computer"])
        assert pipe.names == [] and "main agent" in pipe.unheard["computer"]

    def test_a_name_inside_the_main_phrase_cannot_win(self):
        pipe = _pipe()
        pipe.phrase = "hey computer"
        pipe._choose_names(["computer"])
        assert pipe.names == [] and "computer" in pipe.unheard

    def test_which_phrase_was_heard(self):
        pipe = _pipe()
        pipe._choose_names(["jarvis"])
        assert pipe.phrase_in("computer") == "computer"
        assert pipe.phrase_in("[unk] jarvis") == "jarvis"
        assert pipe.phrase_in("[unk]") == ""

    def test_longest_first(self):
        pipe = _pipe()
        pipe.phrase, pipe.names = "hey computer", ["computer two"]
        assert pipe.phrase_in("hey computer") == "hey computer"

    def test_the_grammar_holds_every_name(self, monkeypatch):
        pipe = _pipe()
        pipe._choose_names(["jarvis"])
        seen = {}

        class Rec:
            def __init__(self, model, rate, grammar):
                seen["grammar"] = json.loads(grammar)

            def SetWords(self, on):
                pass

        pipe._vosk = type("V", (), {"KaldiRecognizer": Rec})
        pipe._reset_wake()
        assert seen["grammar"] == ["computer", "jarvis", "[unk]"]

    def test_a_new_name_rebuilds_the_engine(self, cfg_factory, monkeypatch):
        """The names are part of the grammar, so they belong in the wake spec
        -- or adding an agent would do nothing until the service restarted."""
        import wake_listen
        pipe = _pipe()
        pipe._oww, pipe._whisper_size, pipe._whisper_override = None, "tiny.en", None
        pipe._partials = "auto"
        built = []
        pipe._build_wake = lambda cfg, engine: built.append(engine)
        cfg = cfg_factory(engine="vosk", phrase="computer")
        pipe.apply(cfg)
        pipe.apply(cfg)
        assert built == ["vosk"]
        cfg._values["voiceAgents"] = [{"name": "jarvis"}]
        pipe.apply(cfg)
        assert built == ["vosk", "vosk"]
        assert wake_listen.wanted_names(cfg) == ["jarvis"]

    # A short name said on its own, then a pause. Frames under the gate never
    # reach the grammar, so it cannot finish the word by hearing the silence;
    # only the partial path was left, and that wants three loud 200ms frames.
    # "sarah" is two syllables and never woke. Measured on synthesized clips
    # through the real Vosk model: bench/FINDINGS.md.

    def _feeding_pipe(self, final_words, accepts_on_quiet=False):
        import wake_listen
        pipe = _pipe(known=("computer", "sarah"))
        pipe._choose_names(["sarah"])
        pipe._oww, pipe._refractory_until, pipe._loud_frames = None, 0.0, 0
        pipe.threshold_db = pipe.wake_gate_db = -40.0
        pipe.min_loud_frames = 3
        pipe.wake_confidence, pipe.refractory_ms = 0.70, 1500
        pipe._log_speech = False
        calls = []

        class Rec:
            def __init__(self, *a):
                pass

            def SetWords(self, on):
                pass

            def AcceptWaveform(self, pcm):
                calls.append("accept")
                return accepts_on_quiet and pcm == b"quiet"

            def PartialResult(self):
                return json.dumps({"partial": "sarah"})

            def _verdict(self, name):
                calls.append(name)
                return json.dumps({
                    "text": " ".join(w for w, _ in final_words),
                    "result": [{"word": w, "conf": c} for w, c in final_words]})

            def Result(self):
                return self._verdict("result")

            def FinalResult(self):
                return self._verdict("final")

        pipe._vosk = type("V", (), {"KaldiRecognizer": Rec})
        pipe._reset_wake()
        assert wake_listen.CHUNK_MS == 200
        return pipe, calls

    def test_a_short_name_wakes_when_the_speech_stops(self):
        pipe, calls = self._feeding_pipe([("sarah", 0.95)])
        assert pipe.feed_wake(b"loud", -20.0) is False     # one frame: too short
        assert pipe.feed_wake(b"quiet", -60.0) is True     # the pause: verdict
        assert pipe.heard_phrase == "sarah"
        assert calls == ["accept", "accept", "final"]

    def test_the_confidence_bar_still_holds_at_the_end(self):
        pipe, _ = self._feeding_pipe([("sarah", 0.40)])
        pipe.feed_wake(b"loud", -20.0)
        assert pipe.feed_wake(b"quiet", -60.0) is False

    def test_silence_alone_never_asks_for_a_verdict(self):
        pipe, calls = self._feeding_pipe([("sarah", 0.95)])
        for _ in range(5):
            assert pipe.feed_wake(b"quiet", -60.0) is False
        assert calls == []

    def test_a_final_the_grammar_already_had_is_not_lost(self):
        pipe, calls = self._feeding_pipe([("sarah", 0.95)],
                                         accepts_on_quiet=True)
        pipe.feed_wake(b"loud", -20.0)
        assert pipe.feed_wake(b"quiet", -60.0) is True
        assert calls[-1] == "result"

    def test_wanted_names_survives_a_stand_in_config(self):
        import wake_listen
        assert wake_listen.wanted_names({"phrase": "computer"}) == []


# --- the permission hook ------------------------------------------------------

class TestHookForANamedAgent:
    @pytest.fixture
    def settings(self, monkeypatch, cfg_factory, tmp_path):
        import permission_hook
        import runtime
        project = tmp_path / "proj"
        project.mkdir()

        def use(argv, **values):
            cfg = cfg_factory(**values)
            monkeypatch.setattr(runtime, "Config", lambda: cfg)
            monkeypatch.setattr(sys, "argv", ["permission_hook.py", *argv])
            return permission_hook._settings()

        return use, project

    def test_its_own_level_and_folder(self, settings):
        use, project = settings
        level, root = use(["claude", "friday"],
                          permissions={"claude": "ask"}, projectDir="",
                          voiceAgents=[{"name": "friday", "level": "edits",
                                        "projectDir": str(project)}])
        assert level == "edits" and root == project.resolve()

    def test_the_main_agents_trust_does_not_leak_to_it(self, settings):
        use, _ = settings
        level, _ = use(["claude", "friday"],
                       permissions={"claude": "trusted"},
                       voiceAgents=[{"name": "friday"}])
        assert level == "ask"

    def test_an_agent_that_is_no_longer_configured_is_asked_about(self, settings):
        use, _ = settings
        assert use(["claude", "friday"], permissions={"claude": "trusted"},
                   voiceAgents=[]) == ("ask", None)

    def test_an_agent_now_on_a_different_program_is_asked_about(self, settings):
        use, _ = settings
        assert use(["claude", "friday"],
                   voiceAgents=[{"name": "friday", "agent": "codex",
                                 "level": "trusted"}]) == ("ask", None)

    def test_corrupt_settings_still_ask(self, settings):
        use, _ = settings
        assert use(["claude", "friday"], voiceAgents="garbage") == ("ask", None)

    def test_an_agent_switched_off_is_asked_about(self, settings):
        use, _ = settings
        assert use(["claude", "friday"],
                   voiceAgents=[{"name": "friday", "enabled": False,
                                 "level": "trusted"}]) == ("ask", None)

    def test_the_main_agent_is_unchanged(self, settings):
        use, _ = settings
        level, _ = use(["claude"], permissions={"claude": "trusted"},
                       voiceAgents=[{"name": "friday"}])
        assert level == "trusted"

    def test_the_request_says_who_is_asking(self, monkeypatch):
        import permission_hook
        monkeypatch.setattr(sys, "argv", ["permission_hook.py", "claude", "friday"])
        assert permission_hook._named() == "friday"
        monkeypatch.setattr(sys, "argv", ["permission_hook.py", "claude"])
        assert permission_hook._named() == ""

    def test_claude_hands_the_name_to_its_hook_quoted(self):
        import shlex
        from adapters.claude_code import ClaudeCode
        settings = json.loads(ClaudeCode(named="mister fox")._hook_settings("mister fox"))
        command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        assert shlex.split(command)[-2:] == ["claude", "mister fox"]
        argv = ClaudeCode(named="friday", ask_permission=True)._argv("", None)
        hook = json.loads(argv[argv.index("--settings") + 1])
        assert hook["hooks"]["PreToolUse"][0]["hooks"][0]["command"].endswith(" claude friday")

    def test_the_main_agents_hook_names_nobody(self):
        from adapters.claude_code import ClaudeCode
        argv = ClaudeCode(ask_permission=True)._argv("", None)
        command = json.loads(argv[argv.index("--settings") + 1])[
            "hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        assert command.endswith(" claude")


# --- turns side by side -------------------------------------------------------

class SlowAgent:
    """Thinks for `delay`, then answers `sentences`, until cancelled."""

    name = "claude"
    remembers = True

    levels = ("ask", "edits", "trusted")

    def __init__(self, sentences=("One.",), delay=0.0, wait=None, gap=0.0):
        self.sentences = list(sentences)
        self.delay = delay
        self.wait = wait
        self.gap = gap
        self.cancelled = 0
        self.sent: list[str] = []
        self._stop = threading.Event()

    def send(self, text, session_id=None):
        from adapters.base import Chunk
        self.sent.append(text)
        self._stop.clear()
        if self.wait is not None:
            self.wait.wait(3.0)
        if self._stop.wait(self.delay):
            return
        for i, s in enumerate(self.sentences):
            if i and self._stop.wait(self.gap):
                return
            if self._stop.is_set():
                return
            yield Chunk(text=s + " ", session_id=f"s-{id(self)}")

    def posture(self, level):
        return level

    def cancel(self):
        self.cancelled += 1
        self._stop.set()

    def prepare(self, *a, **k):
        pass


class Voice:
    """A speaker that records who said what, in what order, and takes time."""

    def __init__(self, name, log, seconds=0.05):
        self.name = self.requested = name
        self.log, self.seconds = log, seconds
        self.cancelled = 0

    def say(self, text, watch=None):
        self.log.append((self.name, "start", text))
        end = time.time() + self.seconds
        while time.time() < end:
            if watch is not None and watch():
                self.log.append((self.name, "cut", text))
                return
            time.sleep(0.005)
        self.log.append((self.name, "end", text))

    def cancel(self):
        self.cancelled += 1

    def superseded(self):
        return False


@pytest.fixture
def crew(daemon):
    """The main agent plus two extras, built by hand: what reconcile_crew()
    would have made of three names the wake engine can hear."""
    import queue

    from crew import Persona
    log: list = []
    daemon.enabled, daemon.locked, daemon.yielded = True, False, False
    daemon._frames = queue.Queue()
    daemon.pipe = type("P", (), {"conversation": False, "phrase": "computer",
                                 "names": ["jarvis", "friday"], "unheard": {}})()
    daemon._main.name = "computer"
    daemon._main.agent = SlowAgent(["Main one.", "Main two."])
    daemon._main.speaker = Voice("main", log)
    # The settings they were built from: an agent the settings do not have
    # is one that was deleted, and takes no new turn (M2).
    daemon.cfg._values["voiceAgents"] = [{"name": "jarvis"}, {"name": "friday"}]
    for name in ("jarvis", "friday"):
        p = daemon.crew[name] = Persona(name, {"name": name, "id": name,
                                               "label": name.title()})
        p.agent = SlowAgent([f"{name} one.", f"{name} two."])
        p.speaker = Voice(name, log)
    daemon.log = log
    return daemon


def _wait_idle(d, timeout=5.0):
    assert _until(lambda: not any(p.busy for p in d.personas()), timeout), \
        "turns did not finish"


class TestSideBySide:
    def test_one_agent_is_exactly_the_old_daemon(self, daemon):
        assert not daemon.crew_mode
        assert daemon.agent is daemon._main.agent
        daemon.agent = "x"
        assert daemon._main.agent == "x"

    def test_two_agents_think_at_once(self, crew):
        gate = threading.Event()
        crew.crew["jarvis"].agent.wait = gate
        crew.crew["friday"].agent.wait = gate
        assert crew.dispatch(crew.crew["jarvis"], "a", {})
        assert crew.dispatch(crew.crew["friday"], "b", {})
        # Both are inside send() at the same moment, blocked on the gate.
        assert _until(lambda: crew.crew["jarvis"].agent.sent
                      and crew.crew["friday"].agent.sent)
        assert crew.crew["jarvis"].busy and crew.crew["friday"].busy
        gate.set()
        _wait_idle(crew)

    def test_only_one_speaks_at_a_time_and_replies_do_not_interleave(self, crew):
        # Two sentences each, with a pause between them like a real stream:
        # the other agent is ready to speak during that pause, and must wait.
        for name in ("jarvis", "friday"):
            crew.crew[name].agent = SlowAgent(
                [f"This is the first thing {name} has to say.",
                 f"And this is the second thing {name} has to say."], gap=0.15)
        crew.dispatch(crew.crew["jarvis"], "a", {})
        crew.dispatch(crew.crew["friday"], "b", {})
        _wait_idle(crew)
        speaking = 0
        for who, what, _ in crew.log:
            speaking += 1 if what == "start" else -1
            assert speaking <= 1, crew.log
        order = [who for who, what, _ in crew.log if what == "start"]
        assert sorted(order) == ["friday", "friday", "jarvis", "jarvis"]
        # Whoever started first finished before the other began.
        assert order[0] == order[1] and order[2] == order[3], order

    def test_each_agent_speaks_in_its_own_voice_and_keeps_its_own_conversation(self, crew):
        crew.dispatch(crew.crew["jarvis"], "a", {})
        _wait_idle(crew)
        assert {who for who, *_ in crew.log} == {"jarvis"}
        assert crew.crew["jarvis"].session_id == f"s-{id(crew.crew['jarvis'].agent)}"
        assert crew._main.session_id is None and crew.crew["friday"].session_id is None

    def test_nobody_is_talked_over(self, crew):
        crew._hold(True)
        crew.dispatch(crew.crew["jarvis"], "a", {})
        time.sleep(0.3)
        assert crew.log == [], "a reply started while somebody was talking"
        crew._hold(False)
        _wait_idle(crew)
        assert crew.log

    def test_stopping_one_stops_that_one(self, crew):
        gate = threading.Event()
        crew.crew["jarvis"].agent.wait = gate
        crew.crew["friday"].agent.delay = 0.3
        crew.dispatch(crew.crew["jarvis"], "a", {})
        crew.dispatch(crew.crew["friday"], "b", {})
        crew.crew["jarvis"].stop()
        gate.set()
        _wait_idle(crew)
        said = {who for who, what, _ in crew.log if what == "start"}
        assert said == {"friday"}
        assert crew.crew["friday"].agent.cancelled == 0

    def test_silence_from_inside_a_turn_is_about_that_turn(self, crew):
        from crew import Persona  # noqa: F401
        jarvis, friday = crew.crew["jarvis"], crew.crew["friday"]
        with crew._as(jarvis):
            crew._here.turn = True
            try:
                crew.silence()
            finally:
                crew._here.turn = False
        assert jarvis.interrupt.is_set()
        assert not friday.interrupt.is_set() and not crew._main.interrupt.is_set()

    def test_silence_from_the_loop_stops_everyone(self, crew):
        crew.silence()
        assert all(p.interrupt.is_set() for p in crew.personas())
        crew._clear_interrupts()
        assert not any(p.interrupt.is_set() for p in crew.personas())

    def test_the_stop_button_stops_every_busy_agent(self, crew):
        gate = threading.Event()
        for p in crew.crew.values():
            p.agent.wait = gate
        crew.dispatch(crew.crew["jarvis"], "a", {})
        crew.dispatch(crew.crew["friday"], "b", {})
        assert _until(lambda: crew.crew["jarvis"].busy and crew.crew["friday"].busy)
        crew._on_interrupt()
        assert crew.crew["jarvis"].interrupt.is_set()
        assert crew.crew["friday"].interrupt.is_set()
        gate.set()
        _wait_idle(crew)

    def test_a_turn_thread_does_not_eat_push_to_talk(self, crew):
        from runtime import RUNTIME_DIR
        (RUNTIME_DIR / "command").write_text("talk")
        crew._here.turn = True
        try:
            crew.poll_session()
        finally:
            crew._here.turn = False
        assert (RUNTIME_DIR / "command").read_text() == "talk"
        (RUNTIME_DIR / "command").unlink()

    def test_history_names_the_agent_by_its_name(self, crew):
        """By its display name for the screen, and by its id for anything
        that has to find it again after a rename."""
        crew.cfg._values["keepHistory"] = True
        crew.dispatch(crew.crew["friday"], "b", {"transcript": "b"})
        _wait_idle(crew)
        lines = [json.loads(l) for l in crew.history.path.read_text().splitlines()]
        assert lines[-1]["agent"] == "Friday" and lines[-1]["agent_id"] == "friday"


class TestWhoItIsFor:
    def test_a_name_at_the_start_routes_it(self, crew):
        crew._send(crew._main, "Friday, what is up?", {"transcript": "x"}, {})
        _wait_idle(crew)
        assert crew.crew["friday"].agent.sent == ["what is up?"]
        assert crew._main.agent.sent == []

    def test_otherwise_it_goes_to_whoever_was_woken(self, crew):
        crew._send(crew.crew["jarvis"], "what is up?", {}, {})
        _wait_idle(crew)
        assert crew.crew["jarvis"].agent.sent == ["what is up?"]

    def test_a_named_stop_stops_that_agent_and_sends_nothing(self, crew):
        gate = threading.Event()
        crew.crew["friday"].agent.wait = gate
        crew.dispatch(crew.crew["friday"], "long job", {})
        assert _until(lambda: crew.crew["friday"].busy)
        crew._send(crew._main, "Friday, stop.", {}, {})
        assert crew.crew["friday"].interrupt.is_set()
        gate.set()
        _wait_idle(crew)
        assert crew.crew["friday"].agent.sent == ["long job"]
        assert crew._main.agent.sent == []

    def test_full_stop_stops_every_agent_whoever_it_was_said_to(self, crew):
        gates = {}
        for p in crew.personas():
            gates[p.name] = p.agent.wait = threading.Event()
        crew.dispatch(crew._main, "job a", {})
        crew.dispatch(crew.crew["friday"], "job b", {})
        assert _until(lambda: crew._main.busy and crew.crew["friday"].busy)
        crew.crew["jarvis"].follow_up = True
        crew._send(crew.crew["jarvis"], "Jarvis, full stop.", {}, {})
        assert crew._main.interrupt.is_set()
        assert crew.crew["friday"].interrupt.is_set()
        assert not crew.crew["jarvis"].follow_up
        for g in gates.values():
            g.set()
        _wait_idle(crew)
        assert crew.crew["jarvis"].agent.sent == []

    def test_goodbye_closes_that_agents_window_and_sends_nothing(self, crew):
        crew.crew["friday"].follow_up = True
        crew._send(crew.crew["friday"], "Okay, thanks, goodbye.", {}, {})
        _wait_idle(crew)
        assert not crew.crew["friday"].follow_up
        assert crew.crew["friday"].agent.sent == []

    def test_waking_a_busy_agent_stops_it_and_only_it(self, crew):
        gate = threading.Event()
        for p in crew.personas():
            p.agent.wait = gate
        crew.dispatch(crew.crew["jarvis"], "a", {})
        crew.dispatch(crew.crew["friday"], "b", {})
        assert _until(lambda: crew.crew["jarvis"].busy and crew.crew["friday"].busy)
        crew.pipe.heard_phrase = "jarvis"
        assert crew._woken() is crew.crew["jarvis"]
        assert crew.crew["jarvis"].interrupt.is_set()
        assert not crew.crew["friday"].interrupt.is_set()
        gate.set()
        _wait_idle(crew)

    def test_the_main_phrase_wakes_the_main_agent(self, crew):
        crew.pipe.heard_phrase = "computer"
        assert crew._woken() is crew._main

    def test_asking_a_busy_agent_again_replaces_its_turn(self, crew):
        gate = threading.Event()
        jarvis = crew.crew["jarvis"]
        jarvis.agent.wait = gate
        crew.dispatch(jarvis, "first", {})
        assert _until(lambda: jarvis.agent.sent == ["first"])
        jarvis.agent.wait = None
        threading.Timer(0.05, gate.set).start()
        assert crew.dispatch(jarvis, "second", {})
        _wait_idle(crew)
        assert jarvis.agent.sent == ["first", "second"]

    def test_an_agent_that_cannot_answer_says_why(self, crew):
        friday = crew.crew["friday"]
        friday.agent, friday.problem = None, "codex is not installed"
        crew._send(crew._main, "Friday, hello", {}, {})
        _wait_idle(crew)
        said = [text for who, what, text in crew.log if what == "start"]
        assert said and "codex is not installed" in said[0]


class TestReadout:
    def test_the_microphone_wins_while_it_is_doing_something(self, crew):
        gate = threading.Event()
        crew.crew["jarvis"].agent.wait = gate
        crew.dispatch(crew.crew["jarvis"], "a", {"transcript": "a"})
        crew._capture_for = crew.crew["friday"]
        state, extra = crew._compose("capture", {"transcript": ""})
        assert state == "capture" and extra["who"] == "friday"
        assert extra["live"]["jarvis"] == "thinking"
        gate.set()
        _wait_idle(crew)

    def test_an_idle_microphone_shows_the_working_agent(self, crew):
        gate = threading.Event()
        crew.crew["jarvis"].agent.wait = gate
        crew.dispatch(crew.crew["jarvis"], "a", {"transcript": "a"})
        assert _until(lambda: crew.crew["jarvis"].state == "thinking")
        state, extra = crew._compose("listening", {"level_db": -50.0})
        assert state == "thinking" and extra["who"] == "jarvis"
        assert extra["who_label"] == "Jarvis"
        assert extra["transcript"] == "a" and extra["level_db"] == -50.0
        gate.set()
        _wait_idle(crew)

    def test_afterwards_it_keeps_the_last_answer(self, crew):
        crew.dispatch(crew.crew["friday"], "b", {"transcript": "b"})
        _wait_idle(crew)
        state, extra = crew._compose("listening", {})
        assert state == "listening" and extra["who"] == "friday"
        assert "friday one." in extra["reply"]

    def test_with_one_agent_nothing_is_added(self, daemon):
        assert daemon._compose("listening", {"a": 1}) == ("listening", {"a": 1})


class TestReconcile:
    @pytest.fixture
    def recon(self, daemon, monkeypatch):
        import wake_listen
        built = []

        def load(program, **kw):
            built.append((program, kw))
            a = SlowAgent()
            a.name = program
            a.effort = kw.get("effort")
            return a

        monkeypatch.setattr(wake_listen, "load_adapter", load)
        monkeypatch.setattr(wake_listen, "takes_effort", lambda a: True)
        monkeypatch.setattr(wake_listen, "takes_model", lambda a: True)
        daemon.pipe = type("P", (), {"phrase": "computer", "names": ["jarvis"],
                                     "unheard": {"omarchy": "unknown word"}})()
        daemon.make_speaker = lambda voice: Voice(voice, [])
        daemon.agent = SlowAgent()
        daemon.built = built
        return daemon

    def test_builds_what_the_engine_can_hear(self, recon):
        recon.cfg._values["voiceAgents"] = [
            {"name": "jarvis", "agent": "codex", "model": "o3", "level": "edits",
             "voice": "amy-medium"},
            {"name": "omarchy"}]
        recon.reconcile_crew()
        assert list(recon.crew) == ["jarvis"]
        program, kw = recon.built[0]
        assert program == "codex" and kw["named"] == "jarvis"
        assert kw["level"] == "edits" and kw["ask_permission"] is True
        assert kw["model"] == "o3"
        assert recon.crew["jarvis"].speaker.name == "amy-medium"
        assert recon._main.name == "computer"
        fields = {c["name"]: c for c in recon.crew_fields()["crew"]}
        assert fields["omarchy"]["problem"] == "unknown word"
        assert fields["jarvis"]["problem"] == ""

    def test_an_agent_on_its_own_endpoint_gets_one(self, recon, monkeypatch):
        import wake_listen
        monkeypatch.setattr(wake_listen, "endpoint_key", lambda host: "k-" + host)
        recon.cfg._values["voiceAgents"] = [
            {"name": "jarvis", "agent": "endpoint", "endpointUrl": "localhost:11434",
             "endpointModel": "qwen3:4b", "instructions": "be brief"}]
        recon.reconcile_crew()
        program, kw = recon.built[0]
        assert program is None
        assert kw["endpoint"] == {"url": "http://localhost:11434/v1", "model": "qwen3:4b",
                                  "is_agent": False, "timeout_s": 0, "history_turns": 8,
                                  "key": "k-localhost:11434"}
        assert kw["instructions"] == "be brief"
        assert recon.crew["jarvis"].problem == ""

    def test_an_endpoint_with_no_model_says_so(self, recon):
        recon.cfg._values["voiceAgents"] = [
            {"name": "jarvis", "agent": "endpoint", "endpointUrl": "localhost:11434"}]
        recon.reconcile_crew()
        assert recon.built == []
        assert "address and a model" in recon.crew["jarvis"].problem

    def test_an_effort_change_keeps_the_conversation(self, recon):
        recon.cfg._values["voiceAgents"] = [{"name": "jarvis"}]
        recon.reconcile_crew()
        p = recon.crew["jarvis"]
        p.session_id = "keep"
        recon.cfg._values["voiceAgents"] = [{"name": "jarvis", "effort": "low"}]
        recon.reconcile_crew()
        assert p.session_id == "keep" and p.agent.effort == "low"
        assert len(recon.built) == 1

    def test_a_model_change_starts_a_new_one_where_it_cannot_carry(self, recon):
        """SlowAgent claims no `carries_session_across`, so a new model is a
        new conversation for it, and says why (phase M2: a backend shown to
        resume under the new model keeps it -- see test_sessions.py)."""
        recon.cfg._values["voiceAgents"] = [{"name": "jarvis"}]
        recon.reconcile_crew()
        p = recon.crew["jarvis"]
        p.session_id = "old"
        recon.cfg._values["voiceAgents"] = [{"name": "jarvis", "model": "haiku"}]
        recon.reconcile_crew()
        assert p.session_id is None and len(recon.built) == 2
        assert "model change" in recon._compose("listening", {})[1]["notice"]

    def test_a_busy_agent_is_left_alone(self, recon):
        recon.cfg._values["voiceAgents"] = [{"name": "jarvis"}]
        recon.reconcile_crew()
        p = recon.crew["jarvis"]
        gate = threading.Event()
        p.agent.wait = gate
        recon.dispatch(p, "a", {})
        assert _until(lambda: p.busy)
        recon.cfg._values["voiceAgents"] = []
        recon.reconcile_crew()
        assert "jarvis" in recon.crew, "removed mid-turn"
        gate.set()
        _wait_idle(recon)
        recon.reconcile_crew()
        assert "jarvis" not in recon.crew

    def test_switching_an_agent_off_stops_its_turn(self, recon):
        """A deleted agent finishes its turn; one switched off is stopped
        at once, then removed when its thread has ended."""
        recon.cfg._values["voiceAgents"] = [{"name": "jarvis"}]
        recon.reconcile_crew()
        p = recon.crew["jarvis"]
        p.agent.delay = 5.0
        recon.dispatch(p, "a", {})
        # Until the request is with the agent: the stand-in clears its stop
        # flag when send() starts, so a cancel before that would be lost.
        assert _until(lambda: p.busy and p.agent.sent)
        recon.cfg._values["voiceAgents"] = [{"name": "jarvis", "enabled": False}]
        recon.reconcile_crew()
        assert p.interrupt.is_set() and p.agent.cancelled >= 1
        _wait_idle(recon)
        recon.reconcile_crew()
        assert "jarvis" not in recon.crew

    def test_an_agent_switched_back_on_comes_back(self, recon):
        recon.cfg._values["voiceAgents"] = [{"name": "jarvis", "enabled": False}]
        recon.reconcile_crew()
        assert "jarvis" not in recon.crew
        recon.cfg._values["voiceAgents"] = [{"name": "jarvis", "enabled": True}]
        recon.reconcile_crew()
        assert "jarvis" in recon.crew

    def test_the_main_agent_is_not_rebuilt_under_its_own_turn(self, recon):
        recon.cfg._values["voiceAgents"] = [{"name": "jarvis"}]
        recon.reconcile_crew()
        gate = threading.Event()
        recon._main.agent = SlowAgent(wait=gate)
        before = recon._main.agent
        recon.dispatch(recon._main, "a", {})
        assert _until(lambda: recon._main.busy)
        recon.reconcile_agent()
        assert recon._main.agent is before and before.cancelled == 0
        gate.set()
        _wait_idle(recon)


# --- the real frame loop ------------------------------------------------------

def test_the_loop_hands_a_second_agent_work_while_the_first_is_busy(
        crew, monkeypatch):
    """Driven through the real run loop, the way test_states drives one turn:
    a fake sounddevice delivers real-sized frames from its own thread, and
    only the wake engine and Whisper are scripted.

    "jarvis, <first>" -- jarvis starts work and is still working when
    "computer, <second>" reaches the main agent. Nothing about the first
    stops the second, and the second does not stop the first.
    """
    import sys as _sys

    import wake_listen
    from test_states import _rms_db

    loud = b"\x00\x40" * 3200
    quiet = b"\x00\x00" * 3200
    wakes = ["jarvis", "computer"]
    said = ["first request", "second request"]

    class Capture:
        def AcceptWaveform(self, pcm):
            return False

        def PartialResult(self):
            return json.dumps({"partial": ""})

    class Utterance:
        busy_ms, parts = 12.0, 1

        def __init__(self, text):
            self.text = text

        def add(self, pcm, loud):
            pass

        def tail(self):
            return None

        def finish(self):
            return self.text, 0.0

        def abandon(self):
            pass

    class Pipe:
        phrase = "computer"
        names = ["jarvis"]
        unheard: dict = {}
        heard_phrase = ""
        lead_in_ms, trailing_ms, quick_end_ms = 5000, 0, 0
        max_utterance_ms, min_utterance_ms = 10_000, 100
        threshold_db = -40.0
        detection_threshold = 0.9
        conversation = False
        follow_up_ms = 3000
        floor_db = None

        def learn_room(self, level):
            return False

        def feed_wake(self, pcm, level):
            if pcm != loud or not wakes:
                return False
            self.heard_phrase = wakes.pop(0)
            return True

        def new_capture(self):
            return Capture()

        def new_utterance(self):
            return Utterance(said.pop(0))

    class Stream:
        def __init__(self, **kw):
            self.cb = kw["callback"]

        def __enter__(self):
            def feed():
                for burst in range(2):
                    for frame in [loud, loud] + [quiet] * 15:
                        self.cb(frame, len(frame) // 2, None, None)
                        time.sleep(0.01)
                while True:
                    self.cb(quiet, len(quiet) // 2, None, None)
                    time.sleep(0.01)
            threading.Thread(target=feed, daemon=True).start()
            return self

        def __exit__(self, *exc):
            return False

    class Done(Exception):
        pass

    fake_sd = type(_sys)("sounddevice")
    fake_sd.RawInputStream = lambda **kw: Stream(**kw)
    monkeypatch.setitem(_sys.modules, "sounddevice", fake_sd)
    monkeypatch.setattr(wake_listen, "frame_db", _rms_db)
    for name in ("refresh", "reconcile_lock", "reconcile_yield"):
        monkeypatch.setattr(crew, name, lambda *a, **k: None)
    crew.pipe = Pipe()
    gate = threading.Event()
    crew.crew["jarvis"].agent.wait = gate

    sends = []
    real_send = crew._send

    def send(p, text, last, clock, open_turn=False, heard_at=None):
        sends.append((p.name, text))
        real_send(p, text, last, clock, heard_at=heard_at)
        if len(sends) == 2:
            raise Done()

    monkeypatch.setattr(crew, "_send", send)

    def watchdog():
        time.sleep(5)
        crew._next_frame = lambda *a: (_ for _ in ()).throw(
            AssertionError(f"the loop stalled after {sends}"))

    threading.Thread(target=watchdog, daemon=True).start()
    try:
        with pytest.raises(Done):
            crew.run(device=None)
        assert sends == [("jarvis", "first request"), ("computer", "second request")]
        jarvis = crew.crew["jarvis"]
        assert jarvis.busy and jarvis.agent.cancelled == 0, \
            "the second agent's turn stopped the first"
        assert _until(lambda: crew._main.agent.sent == ["second request"])
        assert jarvis.agent.sent == ["first request"]
    finally:
        gate.set()
        _wait_idle(crew)
    said_by = [who for who, what, _ in crew.log if what == "start"]
    assert "main" in said_by and "jarvis" in said_by
