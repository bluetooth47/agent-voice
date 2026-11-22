"""The command table, and commands inside sentences (phase M4).

`speech_text.find_command` decides; `Daemon.sentence_command` is the one
place the daemon acts on what it decided. The rules here, in the order the
plan gives them: the table holds every phrase there was before; `alone` is
exactly the behaviour before M4; each row of the policy table fires where it
says and nowhere else; each never-fires case stays silent; a command that
fires inside a sentence is said once, from the table, and the rest of the
sentence reaches the agent once; and "no" undoes an open-mic switch for a
moment.
"""
from __future__ import annotations

import ast
import io
import json
import os
import subprocess
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "daemon"))

import speech_text  # noqa: E402
from speech_text import (  # noqa: E402
    COMMAND_MODES, COMMANDS, POSITIONS, UNDO_S, chat_command, command,
    command_mode, find_command, heard_back, is_full_stop, is_goodbye,
    is_handoff, is_stop_command, is_take_over, is_undo, open_mic_command,
    pass_command,
)
import wake_listen  # noqa: E402

#: Kept before the autouse fixture in conftest replaces it.
REAL_RECORDING_ELSEWHERE = wake_listen.Daemon.__dict__["recording_elsewhere"]

FIXTURES = ROOT / "tests" / "fixtures" / "commands"
NAMES = ("sora", "theo", "hey jarvis", "jarvis")


# --- the table -----------------------------------------------------------------

#: The phrase sets as they were before M4, copied here rather than read from
#: the module, so that a phrase lost from the table -- or added without
#: anyone deciding to -- is a failure rather than a silent change.
BEFORE_M4 = {
    "stop": {"stop", "stop talking", "stop it", "cancel", "cancel that",
             "never mind", "nevermind", "be quiet", "shut up", "thats all",
             "forget it", "abort"},
    "goodbye": {"goodbye", "good bye", "bye", "bye bye", "bye for now", "see you",
                "see you later", "see ya", "talk to you later", "talk later",
                "thats all", "thats it", "im done", "were done", "good night",
                "goodnight"},
    "full_stop": {"full stop", "stop everything", "everybody stop", "everyone stop",
                  "stop all", "stop all of it", "emergency stop", "all stop"},
    "new_chat": {"new chat", "a new chat", "start a new chat", "new conversation",
                 "start a new conversation", "fresh chat", "start a fresh chat",
                 "start a fresh conversation", "lets start a new chat",
                 "lets start a new conversation"},
    "open_mic": {"keep listening", "keep on listening", "stay listening",
                 "lets keep talking", "keep talking with me", "lets talk", "open mic",
                 "open the mic", "keep the mic open", "leave the mic open",
                 "listen to me", "start listening", "dont stop listening",
                 "lets have a conversation"},
    "close_mic": {"stop listening", "close the mic", "close mic", "mic off",
                  "turn the mic off", "stop the open mic", "end the open mic",
                  "wait for your name", "wait for the wake word", "go back to sleep",
                  "go to sleep"},
    "take_over": {"take over", "take it over", "take this over", "you take over",
                  "take over from here", "you take it from here", "take it from here",
                  "please take over", "can you take over", "take over please"},
}


class TestTable:
    def test_the_phrases_are_the_ones_from_before(self):
        for cid, phrases in BEFORE_M4.items():
            assert set(command(cid).phrases) == phrases, cid

    def test_the_patterns_are_the_ones_the_matchers_use(self):
        assert command("continue_chat").pattern == speech_text._CONTINUE.pattern
        assert command("handoff").pattern == speech_text._HANDOFF.pattern
        assert command("pass").pattern == speech_text._PASS.pattern

    def test_every_command_from_before_is_in_it_once(self):
        ids = [c.id for c in COMMANDS]
        assert len(ids) == len(set(ids))
        assert set(ids) == {"full_stop", "goodbye", "stop", "open_mic", "close_mic",
                            "handoff", "pass", "take_over", "new_chat",
                            "continue_chat"}

    def test_the_policy_table(self):
        """The plan's table, row for row (notes/master-plan.md, M4)."""
        want = {
            "open_mic": {"alone", "start", "end", "clause"},
            "close_mic": {"alone", "start", "end"},
            "goodbye": {"alone", "end"},
            "new_chat": {"alone", "start"},
            "continue_chat": {"alone", "start"},
            "pass": {"alone", "start"},
            "full_stop": {"alone"},
            "stop": {"alone"},
            "handoff": {"alone"},
            "take_over": {"alone"},
        }
        assert {c.id: set(c.where) for c in COMMANDS} == want

    def test_what_fires_inside_a_sentence_has_words_and_a_sentence_for_it(self):
        for c in COMMANDS:
            assert set(c.where) <= set(POSITIONS)
            inside = set(c.where) - {"alone"}
            if not inside or c.id == "pass":
                # pass's "start" is the request after the name, as before.
                assert not c.in_sentence and not c.said, c.id
                continue
            if c.id != "continue_chat":
                assert c.in_sentence, c.id
                assert set(c.in_sentence) <= set(c.phrases), c.id
            assert c.said and c.said.endswith("."), c.id

    def test_only_full_stop_works_without_the_wake_word(self):
        assert [c.id for c in COMMANDS if not c.needs_wake] == ["full_stop"]

    def test_the_closing_commands_end_the_conversation(self):
        assert {c.id for c in COMMANDS if c.ends} == {"goodbye", "close_mic"}

    def test_as_data(self):
        data = speech_text.table([{"id": "main", "label": "Theo", "phrase": "theo"}],
                                 "clause")
        assert data["mode"] == "clause" and data["modes"] == list(COMMAND_MODES)
        assert [c["id"] for c in data["commands"]] == [c.id for c in COMMANDS]
        assert data["wake_phrases"][0]["phrase"] == "theo"
        assert data["undo"]["seconds"] == UNDO_S
        json.dumps(data)                    # it is JSON, all of it


# --- alone mode is the behaviour before M4 ------------------------------------

def _old(text: str, names=NAMES):
    """What the matchers before M4 said `text` was, in the run loop's order."""
    if is_full_stop(text):
        return "full_stop"
    if is_goodbye(text):
        return "goodbye"
    if is_stop_command(text):
        return "stop"
    mic = open_mic_command(text)
    if mic:
        return "open_mic" if mic == "open" else "close_mic"
    if is_handoff(text):
        return "handoff"
    if pass_command(text, names)[0]:
        return "pass"
    if is_take_over(text):
        return "take_over"
    kind, _ = chat_command(text)
    if kind:
        return "new_chat" if kind == "new" else "continue_chat"
    return None


def _corpus():
    """Every input the existing speech_text, open-mic, chat and collab tests
    use, the fixtures, and each phrase as said."""
    out = set()
    for name in ("test_speech_text.py", "test_open_mic.py", "test_chats.py",
                 "test_collab.py", "test_interrupt.py"):
        tree = ast.parse((ROOT / "tests" / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and 0 < len(node.value) < 120 and "\n" not in node.value:
                out.add(node.value)
    for line in (FIXTURES / "fire.txt").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            out.add(line.split("|")[-1].strip())
    for line in (FIXTURES / "nofire.txt").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            out.add(line.strip())
    for c in COMMANDS:
        for p in c.phrases:
            out |= {p, p.capitalize() + ".", f"Okay, {p}!", f"please {p}"}
    return sorted(out)


def test_alone_gives_what_the_old_matchers_gave_for_every_input():
    """Byte for byte: the same command, the same arguments, and nothing that
    was not a command before."""
    corpus = _corpus()
    assert len(corpus) > 400
    for text in corpus:
        found = find_command(text, "alone", NAMES)
        want = _old(text)
        assert (found.command.id if found else None) == want, text
        if found is not None:
            assert found.exact, text
            if want == "pass":
                assert (found.arg, found.rest) == pass_command(text, NAMES)
            if want == "continue_chat":
                assert found.arg == chat_command(text)[1]


@pytest.mark.parametrize("mode", ["edges", "clause"])
def test_every_mode_keeps_every_command_said_on_its_own(mode):
    """A wider mode adds places a command may be; it takes none away. The one
    difference is "continue the chat about X. <question>", which a mode that
    reads sentences splits where the sentence ends."""
    for text in _corpus():
        want = _old(text)
        if want is None:
            continue
        found = find_command(text, mode, NAMES)
        assert found is not None and found.command.id == want, text
        if want != "continue_chat":
            assert found.exact, text


# --- the corpus, per mode --------------------------------------------------------

def _fire_rows():
    rows = []
    for line in (FIXTURES / "fire.txt").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        least, cid, where, rest, text = [p.strip() for p in line.split("|")]
        rows.append((least, cid, where, "" if rest == "-" else rest, text))
    return rows


@pytest.mark.parametrize("least,cid,where,rest,text", _fire_rows())
def test_it_fires_where_the_corpus_says(least, cid, where, rest, text):
    for mode in COMMAND_MODES:
        found = find_command(text, mode, NAMES)
        fires = found is not None and not found.exact
        if COMMAND_MODES.index(mode) < COMMAND_MODES.index(least):
            assert not fires, (mode, text)
            continue
        assert fires, (mode, text)
        assert found.command.id == cid, (mode, text)
        assert found.where == where, (mode, text)
        assert found.rest == rest, (mode, text)


def _nofire_rows():
    return [line.strip() for line in (FIXTURES / "nofire.txt").read_text().splitlines()
            if line.strip() and not line.startswith("#")]


@pytest.mark.parametrize("text", _nofire_rows())
def test_it_never_fires_on_the_negative_corpus(text):
    found = find_command(text, "clause", NAMES)
    assert found is None or found.exact, (found, text)


def test_the_corpora_are_not_trivial():
    assert len(_fire_rows()) >= 30 and len(_nofire_rows()) >= 50


# --- each never-fires rule, one at a time ------------------------------------------

@pytest.mark.parametrize("text,then", [
    # each pair: the command fires; one change and it does not.
    ("Take notes, and keep listening.", "Take notes, and keep listening to me."),
    ("Take notes, and keep listening.", "Take notes, and don't keep listening."),
    ("Take notes, and keep listening.", "He said, keep listening."),
    ("Take notes, and keep listening.", 'Take notes, and "keep listening".'),
    ("Take notes, and keep listening.", "Take notes, and keep listening? No."),
    ("Take notes, and keep listening.", "New chat, take notes, and keep listening."),
    ("New chat. What's the weather?", "Don't start a new chat. What's the weather?"),
    ("Email Sarah, goodbye.", "Email Sarah, I said goodbye."),
])
def test_one_word_turns_a_command_into_a_sentence(text, then):
    assert find_command(text, "edges", NAMES) is not None
    assert find_command(then, "clause", NAMES) is None


def test_a_mode_that_does_not_allow_the_place_does_not_fire():
    clause = "Take notes, and keep listening, because I might pause."
    assert find_command(clause, "edges") is None
    assert find_command(clause, "clause").where == "clause"
    # "stop listening" has no clause row: close the mic only at an edge.
    assert find_command("Read it, stop listening, then save it.", "clause") is None
    # a goodbye only ends what was said; a new chat only starts it.
    assert find_command("Goodbye, and email Sarah.", "clause") is None
    assert find_command("Email Sarah, new chat.", "clause") is None


def test_what_is_left_is_the_request_and_nothing_else():
    found = find_command("Okay, I'm going to take notes, and keep listening, "
                         "because I might pause.", "clause")
    assert found.rest == "Okay, I'm going to take notes, because I might pause."
    found = find_command("Hey Jarvis, keep listening.", "edges", ("hey jarvis",))
    assert found.rest == ""                 # a name and a greeting say nothing
    found = find_command("No, keep listening.", "edges")
    assert found.rest == "No"               # an answer is not filler


@pytest.mark.parametrize("value", [None, "", "Edges", "both", 3, ["edges"], {"a": 1}])
def test_an_unreadable_mode_is_alone(value):
    assert command_mode(value) == "alone"
    assert find_command("Take notes, and keep listening.", value) is None


def test_undo_words():
    for t in ("No.", "no no", "Cancel that.", "Undo that!", "Nope."):
        assert is_undo(t), t
    for t in ("no thanks, I'm fine", "not now", "cancel the meeting", "yes"):
        assert not is_undo(t), t


def test_heard_back():
    assert heard_back("keep listening", "I'm listening. Say keep listening to stay.")
    assert not heard_back("keep listening", "I keep on listening.")
    assert not heard_back("", "anything")


# --- the setting -----------------------------------------------------------------

class TestSetting:
    def test_three_places(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        bar = manifest["barWidget"]
        assert bar["defaults"]["commandsInSentences"] == "edges"
        entry = next(e for e in bar["schema"] if e["key"] == "commandsInSentences")
        assert entry["options"] == list(COMMAND_MODES)
        assert entry["defaultValue"] == "edges"
        from runtime import DEFAULTS, TOML_ALIASES
        assert DEFAULTS["commandsInSentences"] == "edges"
        assert TOML_ALIASES["commandsInSentences"] == ("wake", "commands_in_sentences")
        page = (ROOT / "pages" / "ConversationPage.qml").read_text()
        assert 'page.s.put("commandsInSentences", v)' in page
        for mode in COMMAND_MODES:
            assert f'value: "{mode}"' in page

    def test_the_page_reads_an_unreadable_value_as_alone(self):
        page = (ROOT / "pages" / "ConversationPage.qml").read_text()
        at = page.index('setting("commandsInSentences"')
        assert ': "alone"' in page[at:at + 200]

    def test_default_and_fallbacks(self, cfg_factory):
        assert cfg_factory().commands_in_sentences() == "edges"
        for mode in COMMAND_MODES:
            assert cfg_factory(commandsInSentences=mode).commands_in_sentences() == mode
        for bad in ("", "EDGES", "always", 1, None, [], {}):
            assert cfg_factory(commandsInSentences=bad).commands_in_sentences() == "alone"

    def test_settings_that_cannot_be_read_are_alone(self, cfg_factory, monkeypatch):
        cfg = cfg_factory(commandsInSentences="clause")
        monkeypatch.setattr(type(cfg), "settings_readable", lambda self: False)
        assert cfg.commands_in_sentences() == "alone"

    def test_read_from_shell_json_and_reloaded(self, sandbox, monkeypatch):
        import runtime
        path = sandbox / "shell-m4.json"
        monkeypatch.setattr(runtime, "SHELL_JSON", path)

        def write(mode):
            entry = {"id": runtime.PLUGIN_ID, "commandsInSentences": mode}
            path.write_text(json.dumps({"bar": {"layout": {"right": [entry]}}}))
            st = path.stat()
            os.utime(path, (st.st_atime, st.st_mtime + 5))

        write("clause")
        cfg = runtime.Config()
        assert cfg.commands_in_sentences() == "clause"
        write("alone")
        assert cfg.reload()
        assert cfg.commands_in_sentences() == "alone"
        path.write_text("{ not json")
        st = path.stat()
        os.utime(path, (st.st_atime, st.st_mtime + 10))
        cfg.reload()
        assert cfg.commands_in_sentences() == "alone", "a broken file must not be edges"


# --- the daemon: the one hook ---------------------------------------------------

def _src():
    return (ROOT / "daemon" / "wake_listen.py").read_text()


def test_find_command_is_called_in_one_place_and_that_place_from_two():
    """The hook, and its two callers: the run loop's own chain (one agent)
    and `_send` (several). Partial text is published from the frame loop and
    reaches neither; a typed message is refused inside `_send`. A third
    caller is a reason to re-read this, not to loosen it."""
    tree = ast.parse(_src())
    finds, hooks = [], []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name == "find_command":
                    finds.append(fn.name)
                if name == "sentence_command":
                    hooks.append(fn.name)
    assert finds == ["sentence_command"]
    assert sorted(hooks) == ["_send", "run"]


def test_the_partial_path_never_reaches_a_command():
    src = _src()
    at = src.index("partial = self.hear(cap, utt, pcm, voiced)")
    block = src[at:src.index("now = time.time()", at)]
    assert "command" not in block


def test_typed_messages_are_not_read_for_commands_inside_sentences():
    src = _src()
    body = src[src.index("    def _send("):src.index("    def dispatch(")]
    assert "None if typed else self.sentence_command(" in body


@pytest.fixture
def quiet_publish(daemon, monkeypatch):
    monkeypatch.setattr(daemon, "publish_agent", lambda: None)
    return daemon


def _sent_to(daemon, monkeypatch):
    sent = []
    monkeypatch.setattr(daemon, "answer",
                        lambda text, last, clock=None, command=None:
                        sent.append((text, command.command.id if command else None)))
    return sent


class TestHook:
    def test_alone_mode_does_nothing_at_all(self, quiet_publish):
        d = quiet_publish
        d.cfg._values["commandsInSentences"] = "alone"
        assert d.sentence_command(d._main, "Take notes, and keep listening.", {}) is None
        assert d.open_mic is None and d.speaker.said == []

    def test_a_command_said_on_its_own_is_left_to_the_checks_before_it(self, quiet_publish):
        d = quiet_publish
        assert d.sentence_command(d._main, "keep listening", {}) is None
        assert d.open_mic is None and d.speaker.said == []

    def test_keep_listening_at_the_end(self, quiet_publish):
        d = quiet_publish
        found = d.sentence_command(d._main, "Take notes, and keep listening.",
                                   {"transcript": "Take notes, and keep listening."},
                                   heard_at=time.time())
        assert found.rest == "Take notes"
        assert d.open_mic is d._main
        assert d.speaker.said == ["Open mic on."], "said once, from the table"
        assert d.state._last.get("reply") == "Open mic on."

    def test_the_sentence_said_is_the_tables(self, quiet_publish, monkeypatch):
        """Change the table and what is said changes: nothing else writes it."""
        d = quiet_publish
        original = command("open_mic")
        swapped = type(original)(**{**original.__dict__, "said": "Mic open, boss."})
        monkeypatch.setitem(speech_text._BY_ID, "open_mic", swapped)
        monkeypatch.setattr(speech_text, "COMMANDS",
                            tuple(swapped if c.id == "open_mic" else c
                                  for c in speech_text.COMMANDS))
        monkeypatch.setattr(speech_text, "_PHRASES", speech_text._phrase_table())
        d.sentence_command(d._main, "Take notes, and keep listening.", {})
        assert d.speaker.said == ["Mic open, boss."]

    def test_stop_listening_closes_it_and_says_so(self, quiet_publish):
        d = quiet_publish
        d.start_open_mic(d._main, say=False)
        found = d.sentence_command(d._main, "Remind me at five, and stop listening.", {})
        assert found.rest == "Remind me at five" and found.command.ends
        assert d.open_mic is None
        assert d.speaker.said == ["Open mic off."]

    def test_a_chat_command_waits_for_the_agents_turn(self, quiet_publish):
        d = quiet_publish
        found = d.sentence_command(d._main, "New chat. What's the weather?", {})
        assert found.command.id == "new_chat" and found.rest == "What's the weather?"
        assert d.speaker.said == [], "said in the turn, where the chat is"

    @pytest.mark.parametrize("context", ["locked", "yielded", "dictating", "own voice"])
    def test_never_in_these_contexts(self, quiet_publish, monkeypatch, context):
        d = quiet_publish
        heard_at = time.time()
        if context == "locked":
            d.locked = True
        elif context == "yielded":
            d.yielded = True
        elif context == "dictating":
            monkeypatch.setattr(type(d), "recording_elsewhere", lambda self: True)
        else:
            d.note_said(heard_at - 3.0, "Say keep listening to talk without the wake word.")
        out = io.StringIO()
        with redirect_stdout(out):
            assert d.sentence_command(d._main, "Take notes, and keep listening.", {},
                                      heard_at=heard_at) is None
        assert d.open_mic is None and d.speaker.said == []
        assert "command not taken: open_mic" in out.getvalue()

    def test_its_own_voice_from_long_ago_is_not_its_own_voice(self, quiet_publish):
        d = quiet_publish
        now = time.time()
        d.note_said(now - 30.0, "Say keep listening to talk without the wake word.")
        d._said_lately[-1] = (now - 30.0, now - 25.0, d._said_lately[-1][2])
        assert d.sentence_command(d._main, "Take notes, and keep listening.", {},
                                  heard_at=now) is not None

    def test_speak_remembers_what_it_said(self, quiet_publish):
        d = quiet_publish
        d.speak("Say keep listening, and I will.", 0)
        began, ended, said = d._said_lately[-1]
        assert began <= ended and "keep listening" in said

    def test_the_journal_line_names_the_command_never_the_words(self, quiet_publish):
        d = quiet_publish
        out = io.StringIO()
        with redirect_stdout(out):
            d.sentence_command(d._main, "Email the quarterly figures, goodbye.", {})
        printed = out.getvalue()
        assert "command: goodbye" in printed and "edges, end" in printed
        assert "quarterly" not in printed and "figures" not in printed

    def test_dictation_is_asked_at_the_moment_it_would_fire(self, quiet_publish,
                                                             monkeypatch):
        d = quiet_publish
        monkeypatch.setattr(type(d), "recording_elsewhere", REAL_RECORDING_ELSEWHERE)
        asked = []
        monkeypatch.setattr(wake_listen, "other_recorders",
                            lambda pid: asked.append(pid) or ["PipeWire ALSA [voxtype]"])
        assert d.sentence_command(d._main, "Take notes, and keep listening.", {}) is None
        assert asked == [os.getpid()]
        monkeypatch.setattr(wake_listen, "other_recorders", lambda pid: [])
        assert d.sentence_command(d._main, "Take notes, and keep listening.", {}) is not None
        # Cannot tell (no pw-dump): as for lending the microphone, not dictation.
        d.end_open_mic("test")
        monkeypatch.setattr(wake_listen, "other_recorders", lambda pid: None)
        assert d.sentence_command(d._main, "Take notes, and keep listening.", {}) is not None


class TestCrewPath:
    def test_send_takes_the_command_out_and_dispatches_the_rest_once(self, quiet_publish,
                                                                     monkeypatch):
        d = quiet_publish
        sent = []
        monkeypatch.setattr(d, "dispatch",
                            lambda p, text, last, clock=None, typed=False, command=None:
                            sent.append((p, text, last["transcript"],
                                         command.command.id if command else None)))
        d._send(d._main, "Take notes, and keep listening.",
                {"transcript": "Take notes, and keep listening."}, {}, heard_at=time.time())
        assert sent == [(d._main, "Take notes", "Take notes", "open_mic")]
        assert d.open_mic is d._main and d.speaker.said == ["Open mic on."]

    def test_nothing_left_sends_nothing(self, quiet_publish, monkeypatch):
        d = quiet_publish
        sent = []
        monkeypatch.setattr(d, "dispatch", lambda *a, **k: sent.append(a))
        d._send(d._main, "Alright then, keep listening.", {"transcript": ""}, {},
                heard_at=time.time())
        assert sent == [] and d.open_mic is d._main

    def test_a_typed_sentence_is_a_request(self, quiet_publish, monkeypatch):
        d = quiet_publish
        sent = []
        monkeypatch.setattr(d, "dispatch",
                            lambda p, text, last, clock=None, typed=False, command=None:
                            sent.append((text, typed, command)))
        d._send(d._main, "Take notes, and keep listening.", {"transcript": ""}, {},
                typed=True)
        assert sent == [("Take notes, and keep listening.", True, None)]
        assert d.open_mic is None and d.speaker.said == []

    def test_the_turn_after_a_goodbye_keeps_no_window(self, quiet_publish, monkeypatch):
        d = quiet_publish
        found = find_command("Email Sarah the notes, goodbye.", "edges")
        monkeypatch.setattr(d, "answer", lambda *a, **k: None)
        monkeypatch.setattr(d, "arm_follow_up", lambda: True)
        d._turn(d._main, "Email Sarah the notes", {}, None, command=found)
        assert d._main.follow_up is False
        d._turn(d._main, "Email Sarah the notes", {}, None)
        assert d._main.follow_up is True


class TestInTheTurn:
    def test_new_chat_then_the_request_once(self, quiet_publish, monkeypatch):
        d = quiet_publish
        found = find_command("New chat. Reply with OK.", "edges")
        sent = []
        d.agent.send = lambda text, session_id=None: sent.append(text) or iter(())
        d._main.session_id, d._main.chat_id = "old-session", "old-chat"
        d.answer(found.rest, {"transcript": found.rest}, command=found)
        assert d._main.chat_id is None
        assert d.speaker.said[0] == "New chat."
        assert "Starting a new chat." not in d.speaker.said
        assert len(sent) == 1 and sent[0].endswith("Reply with OK.")

    def test_a_chat_that_cannot_be_continued_keeps_the_question_back(self, quiet_publish):
        d = quiet_publish
        d.cfg._values["saveChats"] = False
        found = find_command("Continue the chat about the HUD. What colour did we pick?",
                             "edges")
        sent = []
        d.agent.send = lambda text, session_id=None: sent.append(text) or iter(())
        d.answer(found.rest, {"transcript": found.rest}, command=found)
        assert sent == []
        assert d.speaker.said == ["Saved chats are off. Turn on Save conversations in "
                                  "the Display settings."]

    def test_the_rest_is_not_read_for_a_command_again(self, quiet_publish, monkeypatch):
        """What was left is the request. An exact chat command in it would be
        a second command, which find_command already refuses; answer() must
        not look again either."""
        d = quiet_publish
        found = find_command("Take notes, and keep listening.", "edges")
        called = []
        monkeypatch.setattr(d, "chat_turn", lambda *a: called.append(a) or True)
        d.agent.send = lambda text, session_id=None: iter(())
        d.answer("new chat", {"transcript": "new chat"}, command=found)
        assert called == []


class TestUndo:
    def _fire(self, d, text="Take notes, and keep listening."):
        found = d.sentence_command(d._main, text, {}, heard_at=time.time())
        d.undo_clock(found)
        return found

    def test_no_straight_after_puts_the_mic_back(self, quiet_publish):
        d = quiet_publish
        self._fire(d)
        assert d.open_mic is d._main
        assert d.take_undo("No.", time.time()) is True
        assert d.open_mic is None
        assert d.speaker.said == ["Open mic on.", "Open mic off."]

    def test_too_late_is_a_request(self, quiet_publish):
        d = quiet_publish
        self._fire(d)
        assert d.take_undo("No.", time.time() + UNDO_S + 0.5) is False
        assert d.open_mic is d._main

    def test_the_chance_is_used_up_by_whatever_comes_next(self, quiet_publish):
        d = quiet_publish
        self._fire(d)
        assert d.take_undo("What time is it?", time.time()) is False
        assert d.take_undo("No.", time.time()) is False
        assert d.open_mic is d._main

    def test_cancel_that_undoes_and_still_stops(self, quiet_publish):
        d = quiet_publish
        self._fire(d)
        assert d.take_undo("Cancel that.", time.time()) is False
        assert d.open_mic is None, "undone; the stop is the caller's next check"

    def test_closing_is_undone_by_opening_again(self, quiet_publish):
        d = quiet_publish
        d.start_open_mic(d._main, say=False)
        self._fire(d, "That's everything. Mic off.")
        assert d.open_mic is None
        assert d.take_undo("no", time.time()) is True
        assert d.open_mic is d._main

    def test_the_clock_waits_for_the_turn_carrying_the_rest(self, quiet_publish):
        d = quiet_publish
        found = d.sentence_command(d._main, "Take notes, and keep listening.", {},
                                   heard_at=time.time())
        assert d._undo["until"] is None, "open while the agent works on the rest"
        d.undo_clock(found)
        assert d._undo["until"] == pytest.approx(time.time() + UNDO_S, abs=0.5)

    def test_nothing_to_undo_when_nothing_changed(self, quiet_publish):
        d = quiet_publish
        d.sentence_command(d._main, "Remind me at five, and stop listening.", {})
        assert d._undo is None

    def test_a_turn_that_never_ran_does_not_hold_it_open(self, quiet_publish):
        """The rest was to go to the agent, and its turn never started (it
        would not stop, or was switched off): the window is the one after
        the command, not open until something happens to close it."""
        d = quiet_publish
        d.sentence_command(d._main, "Take notes, and keep listening.", {},
                           heard_at=time.time())
        assert d._undo["until"] is None and not d._main.busy
        assert d.take_undo("No.", time.time() + UNDO_S + 1) is False
        assert d.open_mic is d._main

    def test_not_while_locked(self, quiet_publish):
        d = quiet_publish
        self._fire(d)
        d.locked = True
        assert d.take_undo("No.", time.time()) is False


# --- the real frame loop -------------------------------------------------------

def test_the_frame_loop_opens_the_mic_and_sends_the_rest_once(daemon, monkeypatch):
    """Driven through `Daemon.run`: a wake, "Take notes, and keep listening.",
    then the open microphone hears "No." straight after the reply."""
    import frame_loop

    monkeypatch.setattr(daemon, "publish_agent", lambda: None)
    sent = []

    def answer(text, last, clock=None, command=None):
        sent.append((text, command.command.id if command else None))

    monkeypatch.setattr(daemon, "answer", answer)

    class Pipe(frame_loop.Pipe):
        said_list = ["Take notes, and keep listening.", "No."]

        def new_utterance(self):
            u = frame_loop.Utterance(self.said_list[len(self.utterances)])
            self.utterances.append(u)
            return u

    # Speaking drains the queue as echo, which is right for a microphone and
    # would swallow the rest of this script: the frames after the reply are
    # the person, so here the queue is kept.
    monkeypatch.setattr(daemon, "deafen", lambda tail_ms: None)
    pipe = Pipe(feed_wake=frame_loop.wake_on(1))
    items = [frame_loop.LOUD] * 4 + [frame_loop.QUIET] * 5      # the first turn
    items += [frame_loop.LOUD] * 2 + [frame_loop.QUIET] * 10    # "No."
    items += [frame_loop.stop()]
    out = io.StringIO()
    with redirect_stdout(out):
        frame_loop.drive(daemon, monkeypatch, items, pipe=pipe)
    assert sent == [("Take notes", "open_mic")], "the rest, once; the 'no' is not sent"
    assert daemon.speaker.said == ["Open mic on.", "Open mic off."]
    assert daemon.open_mic is None
    printed = out.getvalue()
    assert "command: open_mic" in printed and "command undone: open_mic" in printed
    assert "Take notes" not in printed, "the journal never holds the words"


def test_the_frame_loop_keeps_no_window_after_a_goodbye_in_a_sentence(daemon,
                                                                       monkeypatch):
    """One agent, so the run loop's own chain: the request goes, once, and
    then it waits for the wake word -- no follow-up window."""
    import frame_loop

    monkeypatch.setattr(daemon, "publish_agent", lambda: None)
    monkeypatch.setattr(daemon, "deafen", lambda tail_ms: None)
    sent = []
    monkeypatch.setattr(daemon, "answer", lambda text, last, clock=None, command=None:
                        sent.append(text))
    pipe = frame_loop.Pipe(said="Email Sarah the notes, goodbye.",
                           feed_wake=frame_loop.wake_on(1))
    items = [frame_loop.LOUD] * 4 + [frame_loop.QUIET] * 8 + [frame_loop.stop()]
    payloads, _ = frame_loop.drive(daemon, monkeypatch, items, pipe=pipe)
    assert sent == ["Email Sarah the notes"]
    assert daemon.speaker.said == ["Goodbye."]
    assert not [d for _t, d in payloads if d["state"] == "followup"]
    # Without the goodbye the same turn opens one.
    daemon.speaker.said.clear()
    pipe = frame_loop.Pipe(said="Email Sarah the notes.", feed_wake=frame_loop.wake_on(1))
    items = [frame_loop.LOUD] * 4 + [frame_loop.QUIET] * 8 + [frame_loop.stop()]
    payloads, _ = frame_loop.drive(daemon, monkeypatch, items, pipe=pipe)
    assert [d for _t, d in payloads if d["state"] == "followup"]


def test_the_frame_loop_in_alone_mode_sends_the_sentence_as_before(daemon, monkeypatch):
    import frame_loop

    monkeypatch.setattr(daemon, "publish_agent", lambda: None)
    daemon.cfg._values["commandsInSentences"] = "alone"
    sent = []
    monkeypatch.setattr(daemon, "answer", lambda text, last, clock=None:
                        sent.append(text))
    pipe = frame_loop.Pipe(said="Take notes, and keep listening.",
                           feed_wake=frame_loop.wake_on(1))
    items = [frame_loop.LOUD] * 4 + [frame_loop.QUIET] * 5 + [frame_loop.stop()]
    frame_loop.drive(daemon, monkeypatch, items, pipe=pipe)
    assert sent == ["Take notes, and keep listening."]
    assert daemon.open_mic is None and daemon.speaker.said == []


# --- agentvoice commands -----------------------------------------------------------

def _cli(args, sandbox, env_extra=None):
    env = {**os.environ, "AGENTVOICE_PYTHON": sys.executable,
           "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(sandbox),
           "XDG_CONFIG_HOME": str(sandbox / "xdg_config_home"),
           **(env_extra or {})}
    return subprocess.run([str(ROOT / "bin" / "agentvoice"), "commands", *args],
                          capture_output=True, text=True, env=env, timeout=30)


def test_the_cli_prints_the_table_and_the_wake_phrases(sandbox):
    shell = sandbox / "xdg_config_home" / "omarchy" / "shell.json"
    shell.parent.mkdir(parents=True, exist_ok=True)
    entry = {"id": "duaneoca.agentvoice", "phrase": "theo", "mainName": "Theo\x1b]52;c;x\x07",
             "commandsInSentences": "clause",
             "voiceAgents": [{"name": "sora", "label": "Sora"},
                             {"name": "hazel", "enabled": False}]}
    shell.write_text(json.dumps({"bar": {"layout": {"right": [entry]}}}))
    try:
        got = _cli(["--json"], sandbox)
        assert got.returncode == 0, got.stderr
        data = json.loads(got.stdout)
        assert data["mode"] == "clause"
        assert [c["id"] for c in data["commands"]] == [c.id for c in COMMANDS]
        assert [(w["id"], w["phrase"]) for w in data["wake_phrases"]] == \
            [("main", "theo"), ("sora", "sora")], "an agent switched off wakes nobody"
        text = _cli([], sandbox)
        assert text.returncode == 0
        assert "Open mic" in text.stdout and "\x1b" not in text.stdout
        assert _cli(["--yaml"], sandbox).returncode == 2
    finally:
        shell.unlink()


# --- bench/commands_scan.py ------------------------------------------------------

def test_the_scan_prints_counts_and_never_a_word(sandbox, tmp_path):
    """It runs over somebody's own saved chats, so nothing it prints may
    carry what they said; the sample file, which does, is theirs to ask
    for, 0600 and never written over."""
    from chats import ChatStore
    store = ChatStore(tmp_path / "chats")
    cid = None
    for said in ("Take notes about the zeppelin, and keep listening.",
                 "There's an open mic night at the zeppelin bar.",
                 "What is the capital of Peru?"):
        cid = store.record(chat_id=cid, agent_id="", agent_label="Theo",
                           backend="claude", session_id="s", project_dir="",
                           exchange={"at": time.time(), "transcript": said,
                                     "reply": "ok"})
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(sandbox)}
    script = str(ROOT / "bench" / "commands_scan.py")
    got = subprocess.run([sys.executable, script, "--chats", str(tmp_path / "chats")],
                         capture_output=True, text=True, env=env, timeout=60)
    assert got.returncode == 0, got.stderr
    assert "transcripts scanned: 3" in got.stdout
    assert "held a command's words inside a sentence: 2" in got.stdout
    assert " edges: would fire inside a sentence 1" in got.stdout
    assert "zeppelin" not in got.stdout + got.stderr
    sample = tmp_path / "sample.jsonl"
    got = subprocess.run([sys.executable, script, "--chats", str(tmp_path / "chats"),
                          "--sample", str(sample)],
                         capture_output=True, text=True, env=env, timeout=60)
    assert got.returncode == 0 and "zeppelin" not in got.stdout
    assert sample.stat().st_mode & 0o777 == 0o600
    rows = [json.loads(line) for line in sample.read_text().splitlines()]
    assert len(rows) == 2 and all(r["meant"] is None for r in rows)
    again = subprocess.run([sys.executable, script, "--chats", str(tmp_path / "chats"),
                            "--sample", str(sample)],
                           capture_output=True, text=True, env=env, timeout=60)
    assert again.returncode != 0, "a sample already there is not written over"
