"""Open conversation (plan item 11) and moving a chat to a terminal (item 3).

The run loop itself is exercised by hand; these pin the phrases, the
decisions the loop asks the daemon to make, and what each command does.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "daemon"))

from adapters.base import Chunk  # noqa: E402
from speech_text import is_handoff, is_stop_command, open_mic_command  # noqa: E402


# --- the phrases ---------------------------------------------------------------

class TestPhrases:
    @pytest.mark.parametrize("text", [
        "Keep listening.", "keep listening", "Let's keep talking!", "Open mic",
        "okay, keep listening", "Stay listening.", "Keep the mic open.",
    ])
    def test_open(self, text):
        assert open_mic_command(text) == "open"

    @pytest.mark.parametrize("text", [
        "Stop listening.", "Okay, stop listening", "close the mic", "go to sleep",
        "Wait for the wake word.",
    ])
    def test_close(self, text):
        assert open_mic_command(text) == "close"

    @pytest.mark.parametrize("text", [
        "keep listening to the radio", "I keep listening to this song",
        "stop", "stop talking", "can you open the mic settings",
    ])
    def test_ordinary_sentences_are_not_commands(self, text):
        assert open_mic_command(text) == ""

    def test_a_plain_stop_leaves_it_open(self):
        # It stops the reply; the open microphone is closed by "stop
        # listening", a goodbye or a full stop.
        assert open_mic_command("stop") == ""
        assert is_stop_command("stop")

    @pytest.mark.parametrize("text", [
        "Move this to a terminal.", "move it to the terminal",
        "Open this in a terminal", "continue in a terminal",
        "Can you move the conversation to my terminal?",
        "take this over to a terminal", "switch to the terminal",
    ])
    def test_handoff(self, text):
        assert is_handoff(text)

    @pytest.mark.parametrize("text", [
        "move the file to a terminal folder", "what is a terminal",
        "open a terminal and run the tests", "move this to the trash",
    ])
    def test_not_a_handoff(self, text):
        assert not is_handoff(text)


# --- the open microphone ----------------------------------------------------------

@pytest.fixture(autouse=True)
def quiet_publish(daemon, monkeypatch):
    """publish_agent asks the real adapter what it can do; the fakes here
    cannot say, and what is published is checked through crew_fields."""
    monkeypatch.setattr(daemon, "publish_agent", lambda: None)


class TestOpenMic:
    def test_keep_listening_opens_it_for_that_agent(self, daemon):
        assert daemon.voice_command(daemon._main, "keep listening")
        assert daemon.open_mic is daemon._main
        left = daemon.open_mic_left_ms()
        assert 9 * 60_000 < left <= 10 * 60_000
        assert daemon.speaker.said[-1].startswith("I'm listening")

    def test_it_is_published_for_the_bar_and_the_hud(self, daemon):
        daemon.start_open_mic(daemon._main, say=False)
        field = daemon.crew_fields()["open_mic"]
        assert field["id"] == "main"
        assert field["until"] == pytest.approx(time.time() + 600, abs=2)
        daemon.end_open_mic("test")
        assert daemon.crew_fields()["open_mic"] == {}

    def test_stop_listening_closes_it(self, daemon):
        daemon.start_open_mic(daemon._main, say=False)
        assert daemon.voice_command(daemon._main, "stop listening")
        assert daemon.open_mic is None

    def test_stop_listening_with_nothing_open_is_still_swallowed(self, daemon):
        assert daemon.voice_command(daemon._main, "stop listening")
        assert daemon.speaker.said == []

    def test_full_stop_closes_it(self, daemon):
        daemon.start_open_mic(daemon._main, say=False)
        daemon.full_stop()
        assert daemon.open_mic is None

    def test_the_idle_time_is_a_setting_and_clamped(self, daemon):
        daemon.cfg._values["openMicIdleMin"] = 3
        assert daemon.open_mic_idle_s() == 180
        daemon.cfg._values["openMicIdleMin"] = 0
        assert daemon.open_mic_idle_s() == 60
        daemon.cfg._values["openMicIdleMin"] = 500
        assert daemon.open_mic_idle_s() == 3600

    def test_saying_something_starts_the_idle_time_again(self, daemon):
        daemon.start_open_mic(daemon._main, say=False)
        daemon.open_mic_until = time.time() + 5
        daemon.touch_open_mic()
        assert daemon.open_mic_left_ms() > 9 * 60_000

    def test_the_loop_listens_while_it_is_open(self, daemon):
        assert not daemon.open_mic_due(crew=False)
        daemon.start_open_mic(daemon._main, say=False)
        assert daemon.open_mic_due(crew=False)

    def test_going_quiet_closes_it(self, daemon):
        daemon.start_open_mic(daemon._main, say=False)
        daemon.open_mic_until = time.time() - 1
        assert not daemon.open_mic_due(crew=False)
        assert daemon.open_mic is None

    def test_a_lock_closes_it(self, daemon):
        daemon.start_open_mic(daemon._main, say=False)
        daemon.locked = True
        assert not daemon.open_mic_due(crew=False)
        assert daemon.open_mic is None

    def test_a_mute_holds_it_rather_than_ending_it(self, daemon):
        daemon.start_open_mic(daemon._main, say=False)
        daemon.enabled = False
        assert not daemon.open_mic_due(crew=False)
        assert daemon.open_mic is daemon._main, "a mute ended the open mic"
        daemon.enabled = True
        assert daemon.open_mic_due(crew=False)

    def test_a_long_mute_still_times_it_out(self, daemon):
        daemon.start_open_mic(daemon._main, say=False)
        daemon.enabled = False
        daemon.open_mic_until = time.time() - 1
        assert not daemon.open_mic_due(crew=False)
        assert daemon.open_mic is None

    def test_a_mute_does_not_stop_the_reply(self, daemon):
        """Muting closes the microphone, not the chat: the reply keeps
        playing and the agent keeps working. A lock still stops speech."""
        cancelled = []
        daemon.silence = lambda: cancelled.append(True)
        daemon._on_toggle()
        assert daemon.enabled is False
        assert cancelled == [], "a mute cancelled the agent's turn"
        assert daemon.may_speak
        daemon.locked = True
        assert not daemon.may_speak

    def test_the_popup_toggle(self, daemon):
        assert daemon.apply_open_mic_command("open-mic on main")
        assert daemon.open_mic is daemon._main
        assert daemon.speaker.said == []        # the click is its own answer
        assert daemon.apply_open_mic_command("open-mic off")
        assert daemon.open_mic is None
        assert not daemon.apply_open_mic_command("chat-new main")


class SeenAgent:
    """Records what it was sent, and answers with `reply`."""

    name = "claude"

    def __init__(self, reply="It is four."):
        self.reply = reply
        self.prompts = []
        self.cancelled = 0

    def send(self, text, session_id=None):
        self.prompts.append(text)
        yield Chunk(session_id="sess-0001")
        yield Chunk(text=self.reply)

    def cancel(self):
        self.cancelled += 1


class TestMeantForYou:
    def test_an_open_turn_carries_the_question(self, daemon):
        daemon.agent = SeenAgent()
        daemon._main.open_turn = True
        daemon.answer("what time is it", {"transcript": "x"})
        assert daemon.agent.prompts[0].startswith("[Heard on an open microphone")
        assert daemon.agent.prompts[0].endswith("what time is it")
        assert daemon.speaker.said == ["It is four."]

    def test_skip_is_never_said_or_kept(self, daemon, tmp_path):
        from runtime import History
        daemon.history = History(tmp_path / "h.jsonl")
        daemon.cfg._values["keepHistory"] = True
        daemon.agent = SeenAgent(reply="SKIP")
        daemon._main.open_turn = True
        daemon.answer("did you see the game last night", {"transcript": "x"})
        assert daemon.speaker.said == []
        assert not daemon.history.path.exists()

    def test_skip_from_a_named_turn_is_said(self, daemon):
        # Only the open microphone asks for SKIP; anything else is an answer.
        daemon.agent = SeenAgent(reply="SKIP")
        daemon.answer("say skip", {"transcript": "x"})
        assert daemon.speaker.said == ["SKIP"]

    def test_with_the_option_off_nothing_is_added(self, daemon):
        daemon.cfg._values["openMicAddressedOnly"] = False
        daemon.agent = SeenAgent()
        daemon._main.open_turn = True
        daemon.answer("what time is it", {"transcript": "x"})
        assert daemon.agent.prompts == ["what time is it"]

    def test_the_flag_lasts_one_turn(self, daemon):
        daemon.agent = SeenAgent()
        daemon._main.open_turn = True
        daemon.answer("one", {"transcript": "x"})
        daemon.answer("two", {"transcript": "x"})
        assert daemon.agent.prompts[1] == "two"


# --- moving a chat to a terminal ----------------------------------------------------

class TestResumeCommand:
    def test_claude_and_codex(self):
        from wake_listen import terminal_resume_argv
        sid = "3f2a9c1e-1111-2222-3333-444455556666"
        assert terminal_resume_argv("claude", sid) == ["claude", "--resume", sid]
        assert terminal_resume_argv("codex", sid) == ["codex", "resume", sid]

    def test_the_rest_cannot(self):
        from wake_listen import terminal_resume_argv
        for program in ("gemini", "agy", "copilot", "endpoint", ""):
            assert terminal_resume_argv(program, "3f2a9c1e-1111") is None

    @pytest.mark.parametrize("sid", [None, "", "short", "abc; rm -rf ~",
                                     "--dangerously-skip-permissions", "a" * 90,
                                     "$(whoami)abcdef"])
    def test_only_a_real_session_id(self, sid):
        from wake_listen import terminal_resume_argv
        assert terminal_resume_argv("claude", sid) is None


class TestHeldElsewhere:
    def make(self, tmp_path, procs):
        for pid, args in procs.items():
            d = tmp_path / str(pid)
            d.mkdir()
            (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in args) + b"\0")
        (tmp_path / "self").mkdir()
        return str(tmp_path)

    def test_found_when_a_process_has_it(self, tmp_path):
        from wake_listen import session_held_elsewhere
        root = self.make(tmp_path, {
            101: ["node", "/x/claude", "--resume", "sess-abcdef12"],
            102: ["bash"]})
        assert session_held_elsewhere("sess-abcdef12", root)
        assert not session_held_elsewhere("sess-other999", root)

    def test_a_part_of_an_argument_is_not_it(self, tmp_path):
        from wake_listen import session_held_elsewhere
        root = self.make(tmp_path, {101: ["grep", "xsess-abcdef12x"]})
        assert not session_held_elsewhere("sess-abcdef12", root)

    def test_our_own_process_does_not_count(self, tmp_path):
        import os

        from wake_listen import session_held_elsewhere
        root = self.make(tmp_path, {os.getpid(): ["python", "sess-abcdef12"]})
        assert not session_held_elsewhere("sess-abcdef12", root)


class TerminalAgent(SeenAgent):
    cwd = "/home/u/code/project"


@pytest.fixture
def launched(monkeypatch):
    import wake_listen
    calls = []
    real = wake_listen.subprocess.Popen

    def fake_popen(argv, **kw):
        # Only the terminal: the lock check spawns its own helper.
        if "xdg-terminal-exec" in argv:
            calls.append(argv)
            return None
        return real(argv, **kw)

    monkeypatch.setattr(wake_listen.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(wake_listen.shutil, "which",
                        lambda name: "/usr/bin/" + name)
    return calls


class TestHandOff:
    def test_it_opens_the_chat_in_a_terminal(self, daemon, launched):
        daemon.agent = TerminalAgent()
        daemon.session_id = "sess-abcdef12"
        assert daemon.voice_command(daemon._main, "move this to a terminal")
        [argv] = launched
        assert argv[:4] == ["setsid", "uwsm-app", "--", "xdg-terminal-exec"]
        assert "--dir=/home/u/code/project" in argv
        assert argv[-3:] == ["claude", "--resume", "sess-abcdef12"]
        assert daemon.speaker.said[-1] == "Moved to a terminal."

    def test_the_warm_process_is_let_go(self, daemon, launched):
        daemon.agent = TerminalAgent()
        daemon.session_id = "sess-abcdef12"
        daemon.hand_off(daemon._main)
        assert daemon.agent.cancelled == 1
        assert daemon._main.terminal == "sess-abcdef12"

    def test_nothing_to_move_yet(self, daemon, launched):
        daemon.agent = TerminalAgent()
        assert not daemon.hand_off(daemon._main)
        assert launched == []
        assert "nothing to move" in daemon.speaker.said[-1]

    def test_a_program_that_cannot_resume_says_so(self, daemon, launched):
        agent = TerminalAgent()
        agent.name = "gemini"
        daemon.agent = agent
        daemon.session_id = "sess-abcdef12"
        assert not daemon.hand_off(daemon._main)
        assert launched == []
        assert "can't carry a chat into a terminal" in daemon.speaker.said[-1]

    def test_it_closes_the_open_mic(self, daemon, launched):
        daemon.agent = TerminalAgent()
        daemon.session_id = "sess-abcdef12"
        daemon.start_open_mic(daemon._main, say=False)
        daemon.hand_off(daemon._main)
        assert daemon.open_mic is None

    def test_a_saved_chat_is_marked(self, daemon, launched, tmp_path):
        from chats import ChatStore
        daemon.chats = ChatStore(tmp_path / "chats")
        cid = daemon.chats.record(chat_id=None, agent_id="", agent_label="Theo",
                                  backend="claude", session_id="sess-abcdef12",
                                  project_dir="", exchange={"transcript": "hi",
                                                            "reply": "hello"})
        daemon.agent = TerminalAgent()
        daemon.session_id = "sess-abcdef12"
        daemon._main.chat_id = cid
        daemon.hand_off(daemon._main)
        assert daemon.chats.load(cid)["terminal"] > 0
        assert [c["terminal"] for c in daemon.chats.list()] != [0]


class TestWhileTheTerminalHasIt:
    def test_voice_stays_out(self, daemon, monkeypatch):
        import wake_listen
        monkeypatch.setattr(wake_listen, "session_held_elsewhere", lambda sid: True)
        daemon.agent = SeenAgent()
        daemon.session_id = "sess-abcdef12"
        daemon._main.terminal = "sess-abcdef12"
        daemon.answer("what next", {"transcript": "x"})
        assert daemon.agent.prompts == []
        assert "open in a terminal" in daemon.speaker.said[-1]

    def test_once_it_is_closed_the_chat_is_back(self, daemon, monkeypatch):
        import wake_listen
        monkeypatch.setattr(wake_listen, "session_held_elsewhere", lambda sid: False)
        daemon.agent = SeenAgent()
        daemon.session_id = "sess-abcdef12"
        daemon._main.terminal = "sess-abcdef12"
        daemon.answer("what next", {"transcript": "x"})
        assert daemon.agent.prompts == ["what next"]
        assert daemon._main.terminal is None

    def test_no_process_is_started_on_it_meanwhile(self, daemon):
        prepared = []

        class Warm(SeenAgent):
            def prepare(self, session_id=None):
                prepared.append(session_id)

        daemon.agent = Warm()
        daemon.session_id = "sess-abcdef12"
        daemon._main.terminal = "sess-abcdef12"
        daemon.prime_agent()
        assert prepared == []
        daemon._main.terminal = None
        daemon.prime_agent()
        assert prepared == ["sess-abcdef12"]

    def test_a_new_chat_lets_go_of_it(self, daemon):
        daemon._main.terminal = "sess-abcdef12"
        daemon.new_chat(daemon._main)
        assert daemon._main.terminal is None


class TestSettings:
    def test_three_places(self):
        from runtime import DEFAULTS, TOML_ALIASES
        manifest = json.loads((ROOT / "manifest.json").read_text())
        defaults = manifest["barWidget"]["defaults"]
        for key in ("openMicIdleMin", "openMicAddressedOnly", "openMicAuto"):
            assert key in DEFAULTS and key in TOML_ALIASES and key in defaults
        assert defaults["openMicAuto"] is False
        assert defaults["openMicAddressedOnly"] is True
