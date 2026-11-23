"""Saved conversations (plan item 2).

What has to hold:

- nothing reaches the disk unless saveChats is on, and what does is
  owner-only;
- a new session starts a new chat, a continued one does not, and a chat
  knows its agent by id, so a rename keeps it;
- the daemon appending while the CLI renames or deletes loses neither;
- Continue resumes natively only where the session can really be taken up
  (same backend, one that remembers, same folder), and otherwise replays the
  words once, ahead of the next request;
- "new chat" and "continue the chat about ..." are whole sentences, never
  part of an ordinary request.
"""
from __future__ import annotations

import json
import stat
import threading

import pytest

from chats import RETENTIONS, ChatStore, replay_context, title_from, valid_id
from conftest import ROOT
from speech_text import chat_command

EX = {"transcript": "Make the HUD wider please.", "reply": "Done.", "error": "",
      "stopped": False}


@pytest.fixture
def store(tmp_path):
    return ChatStore(tmp_path / "chats")


def rec(store, chat_id=None, agent_id="", transcript="Make the HUD wider please.",
        now=None, session="s1", backend="claude", project="/p"):
    return store.record(chat_id=chat_id, agent_id=agent_id, agent_label="Theo",
                        backend=backend, session_id=session, project_dir=project,
                        exchange={**EX, "transcript": transcript}, now=now)


# --- the store ---------------------------------------------------------------

class TestStore:
    def test_a_chat_is_one_owner_only_file(self, store):
        cid = rec(store)
        assert valid_id(cid)
        path = store.root / f"{cid}.json"
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(store.root.stat().st_mode) == 0o700
        assert stat.S_IMODE((store.root / "index.json").stat().st_mode) == 0o600
        chat = json.loads(path.read_text())
        assert chat["title"] == "Make the HUD wider please"
        assert chat["session_id"] == "s1" and chat["project_dir"] == "/p"
        assert chat["exchanges"][0]["reply"] == "Done."

    def test_the_same_chat_grows_and_a_new_one_starts_on_none(self, store):
        a = rec(store, now=1)
        assert rec(store, a, transcript="and taller", now=2) == a
        b = rec(store, None, transcript="Something else", now=3)
        assert b != a
        assert store.load(a)["exchanges"][-1]["transcript"] == "and taller"
        assert store.load(a)["title"] == "Make the HUD wider please", "titled by the first"
        assert [c["id"] for c in store.list()] == [b, a], "newest first"

    def test_the_index_says_which_chat_each_agent_is_in(self, store):
        a = rec(store, agent_id="")
        b = rec(store, agent_id="sora-1x")
        index = json.loads((store.root / "index.json").read_text())
        assert index["current"] == {"": a, "sora-1x": b}
        store.set_current("sora-1x", None)
        store.forget_current()
        assert json.loads((store.root / "index.json").read_text())["current"] == {}

    def test_a_vanished_chat_starts_a_new_one(self, store):
        a = rec(store)
        store.delete(a)
        assert rec(store, a) != a

    def test_rename_pin_delete(self, store):
        a = rec(store)
        assert store.rename(a, "  HUD\nsizing ")
        assert store.load(a)["title"] == "HUD sizing"
        assert not store.rename(a, "   ")
        assert store.pin(a) and store.list()[0]["pinned"] is True
        assert store.delete(a) and store.list() == []
        assert json.loads((store.root / "index.json").read_text())["current"] == {}
        assert not store.delete(a)

    @pytest.mark.parametrize("bad", ["../../etc/passwd", "index", "", "ABCDEF0123456789", None])
    def test_an_id_is_never_a_path(self, store, bad):
        rec(store)
        with pytest.raises(ValueError):
            store._path(bad)
        assert store.load(bad) is None if isinstance(bad, str) else True
        assert not store.rename(bad, "x") if isinstance(bad, str) else True

    def test_a_damaged_index_is_rebuilt_from_the_chats(self, store):
        a = rec(store)
        (store.root / "index.json").write_text("{not json")
        assert [c["id"] for c in store.list()] == [a]
        (store.root / "index.json").unlink()
        assert [c["id"] for c in store.list()] == [a]

    def test_a_long_chat_keeps_its_newest_exchanges(self, store, monkeypatch):
        import chats
        monkeypatch.setattr(chats, "EXCHANGES_MAX", 3)
        a = rec(store, transcript="t0")
        for i in range(1, 6):
            rec(store, a, transcript=f"t{i}")
        assert [e["transcript"] for e in store.load(a)["exchanges"]] == ["t3", "t4", "t5"]

    def test_the_daemon_and_the_cli_at_once_lose_nothing(self, store):
        a = rec(store)
        errors = []

        def daemon():
            try:
                for i in range(30):
                    rec(store, a, transcript=f"turn {i}")
            except Exception as e:      # pragma: no cover - reported below
                errors.append(e)

        def cli():
            try:
                for i in range(30):
                    store.rename(a, f"title {i}")
                    store.pin(a, i % 2 == 0)
            except Exception as e:      # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=daemon), threading.Thread(target=cli)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        chat = store.load(a)
        assert len(chat["exchanges"]) == 31
        assert chat["title"] == "title 29"
        assert store.list()[0]["count"] == 31


class TestRetention:
    def test_by_age_keeps_pinned_and_current(self, store):
        day = 86400
        old = rec(store, agent_id="a", now=0)
        pinned = rec(store, agent_id="b", now=0)
        current = rec(store, agent_id="c", now=0)
        recent = rec(store, agent_id="d", now=40 * day)
        store.pin(pinned)
        store.set_current("a", None)
        store.set_current("b", None)
        store.set_current("d", None)
        assert store.prune("30d", now=41 * day) == 1
        left = {c["id"] for c in store.list()}
        assert left == {pinned, current, recent} and old not in left

    def test_by_count(self, store, monkeypatch):
        ids = [rec(store, agent_id=f"a{i}", now=i) for i in range(103)]
        store.forget_current()
        assert store.prune("last100") == 3
        assert {c["id"] for c in store.list()} == set(ids[3:])

    def test_forever_and_nonsense_keep_everything(self, store):
        rec(store, now=0)
        store.forget_current()
        assert store.prune("forever") == 0 and store.prune("7y") == 0
        assert len(store.list()) == 1

    def test_the_options_match_the_manifest(self):
        man = json.loads((ROOT / "manifest.json").read_text())["barWidget"]
        opts = next(e for e in man["schema"] if e["key"] == "chatRetention")["options"]
        assert tuple(opts) == RETENTIONS


class TestFind:
    def test_title_words_count_most_and_filler_counts_nothing(self, store):
        hud = rec(store, transcript="Make the HUD wider", now=1)
        rec(store, None, transcript="Fix the tests", now=2)
        found = store.find("the chat about the hud", "")
        assert found[0]["id"] == hud and len(found) == 1

    def test_words_anywhere_in_the_chat_count(self, store):
        a = rec(store, transcript="Hello there")
        rec(store, a, transcript="now let's talk about gardening")
        assert store.find("gardening", "")[0]["id"] == a

    def test_only_this_agents_chats(self, store):
        rec(store, agent_id="sora-1x", transcript="HUD again")
        assert store.find("hud", "") == []

    def test_nothing_named_is_the_most_recent(self, store):
        rec(store, now=1)
        b = rec(store, None, transcript="Other", now=2)
        assert [c["id"] for c in store.find("", "")] == [b]


class TestExport:
    def test_markdown_with_who_said_what(self, store, tmp_path):
        a = rec(store)
        text = store.export_markdown(a)
        assert text.startswith("# Make the HUD wider please")
        assert "**You**" in text and "**Theo**: Done." in text
        out = tmp_path / "out"
        out.mkdir()
        first = store.export_to(a, out)
        second = store.export_to(a, out)
        assert first != second and first.exists() and second.exists()
        assert stat.S_IMODE(first.stat().st_mode) == 0o600

    def test_replay_keeps_the_newest_when_long(self, store):
        a = rec(store, transcript="first")
        for i in range(50):
            rec(store, a, transcript=f"turn {i} " + "x" * 200)
        text = replay_context(store.load(a), max_chars=1000)
        assert "turn 49" in text and "first" not in text
        assert text.endswith("The user now says:\n")
        assert replay_context({"exchanges": []}) == ""


def test_titles():
    assert title_from("What time is it? And the date.") == "What time is it?"
    long = title_from("word " * 40)
    assert len(long) <= 61 and long.endswith("…")
    assert title_from("") == "Untitled chat"


# --- what is said ------------------------------------------------------------

@pytest.mark.parametrize("text, want", [
    ("New chat.", ("new", "")),
    ("Start a new conversation", ("new", "")),
    ("Continue the chat about the HUD sizing.", ("continue", "the hud sizing")),
    ("Resume our conversation", ("continue", "")),
    ("Go back to the conversation we had about tests", ("continue", "tests")),
    ("Can you continue the work?", ("", "")),
    ("Write a new chat feature for the app", ("", "")),
    ("Tell me about the chat about cats", ("", "")),
    ("continue", ("", "")),
])
def test_what_counts_as_a_chat_command(text, want):
    assert chat_command(text) == want


# --- the daemon --------------------------------------------------------------

class Agent:
    """A backend that remembers, in a folder, and records what it was sent."""

    name = "claude"
    remembers = True
    cwd = "/p"

    def __init__(self):
        self.sent = []
        self.cancelled = 0

    def send(self, text, session_id=None):
        from adapters.base import Chunk
        self.sent.append((text, session_id))
        yield Chunk(text="Sure.", session_id=session_id or "new-session")

    def cancel(self):
        self.cancelled += 1


@pytest.fixture
def d(daemon, tmp_path):
    daemon.chats = ChatStore(tmp_path / "chats")
    daemon.agent = daemon._main.agent = Agent()
    daemon.cfg._values.update(saveChats=True, keepHistory=False)
    daemon._main.label = "Theo"
    return daemon


def turn(d, text):
    d.answer(text, {"transcript": text})


class TestDaemon:
    def test_nothing_is_written_with_saving_off(self, d):
        d.cfg._values["saveChats"] = False
        turn(d, "Hello there")
        assert not d.chats.root.exists()
        d.chats.forget_current()
        assert not d.chats.root.exists(), "startup does not create it either"

    def test_one_session_is_one_chat(self, d):
        turn(d, "Make the HUD wider")
        turn(d, "And taller")
        [chat] = d.chats.list()
        assert chat["count"] == 2 and chat["title"] == "Make the HUD wider"
        assert d.chats.load(chat["id"])["session_id"] == "new-session"
        assert chat["agent_id"] == "" and chat["agent_label"] == "Theo"

    def test_a_new_session_is_a_new_chat(self, d):
        turn(d, "One")
        d.session_id = None
        turn(d, "Two")
        assert len(d.chats.list()) == 2

    def test_new_chat_said_out_loud(self, d):
        turn(d, "One")
        turn(d, "New chat.")
        assert d.session_id is None and d._main.chat_id is None
        assert d.speaker.said[-1] == "Starting a new chat."
        assert len(d.agent.sent) == 1, "not sent to the agent"
        turn(d, "Two")
        assert len(d.chats.list()) == 2

    def test_continue_by_voice_resumes_the_session(self, d):
        turn(d, "Make the HUD wider")
        hud = d._main.chat_id
        turn(d, "New chat.")
        turn(d, "Fix the tests")
        turn(d, "Continue the chat about the HUD.")
        assert d.speaker.said[-1] == "Continuing Make the HUD wider. Go ahead."
        assert d.session_id == "new-session" and d._main.chat_id == hud
        turn(d, "Taller too")
        assert d.agent.sent[-1] == ("Taller too", "new-session")
        assert d.chats.load(hud)["exchanges"][-1]["transcript"] == "Taller too"

    def test_two_close_matches_are_named_not_guessed(self, d):
        turn(d, "HUD colours")
        turn(d, "New chat.")
        turn(d, "HUD size")
        turn(d, "New chat.")
        before = d.session_id
        turn(d, "Continue the chat about the HUD")
        assert d.speaker.said[-1].startswith("Two chats match: ")
        assert d.session_id == before

    def test_nothing_found_or_saving_off_says_so(self, d):
        turn(d, "Continue the chat about gardening")
        assert d.speaker.said[-1] == "I couldn't find a chat about gardening."
        d.cfg._values["saveChats"] = False
        turn(d, "Continue the chat about gardening")
        assert d.speaker.said[-1].startswith("Saved chats are off.")

    def test_another_backend_or_folder_gets_the_words_once(self, d):
        turn(d, "Make the HUD wider")
        chat = d.chats.load(d._main.chat_id)
        d.agent.cwd = "/elsewhere"
        d.session_id = None
        assert d.continue_chat(d._main, chat) == "replayed"
        assert d.session_id is None
        turn(d, "Taller too")
        text, session = d.agent.sent[-1]
        assert session is None and "Make the HUD wider" in text
        assert text.endswith("The user now says:\nTaller too")
        turn(d, "And blue")
        assert d.agent.sent[-1][0] == "And blue", "once, then the session carries it"
        ex = d.chats.load(chat["id"])["exchanges"]
        assert [e["transcript"] for e in ex] == ["Make the HUD wider", "Taller too", "And blue"]

    def test_a_backend_that_forgets_is_replayed(self, d):
        turn(d, "Hello")
        chat = d.chats.load(d._main.chat_id)
        d.agent.remembers = False
        assert d.continue_chat(d._main, chat) == "replayed"

    def test_continue_from_the_conversation_view(self, d):
        turn(d, "Make the HUD wider")
        cid = d._main.chat_id
        d.new_chat(d._main)
        assert d.apply_chat_command(f"chat-continue {cid}")
        assert d._main.chat_id == cid and d.session_id == "new-session"
        assert d.apply_chat_command("chat-new main")
        assert d._main.chat_id is None and d.session_id is None
        assert d.apply_chat_command("chat-continue 0123456789abcdef")
        assert not d.apply_chat_command("talk")

    def test_an_extra_agents_chat_follows_its_id(self, d):
        from crew import Persona
        p = d.crew["s1"] = Persona("sora", {"name": "sora", "id": "s1", "label": "Sora"})
        p.agent = Agent()
        with d._as(p):
            turn(d, "Hello Sora")
        [chat] = d.chats.list()
        assert chat["agent_id"] == "s1"
        d.new_chat(p)
        p.label, p.name = "Researcher", "nova"
        assert d.apply_chat_command(f"chat-continue {chat['id']}")
        assert p.chat_id == chat["id"]

    def test_a_disk_that_refuses_costs_the_record_not_the_turn(self, d, monkeypatch):
        def boom(**kw):
            raise OSError("read-only")
        monkeypatch.setattr(d.chats, "record", boom)
        turn(d, "Hello")
        assert d.speaker.said[-1] == "Sure."


def test_the_settings_are_in_all_three_places():
    import runtime
    man = json.loads((ROOT / "manifest.json").read_text())["barWidget"]
    assert man["defaults"]["saveChats"] is False
    assert man["defaults"]["chatRetention"] == "forever"
    assert runtime.DEFAULTS["saveChats"] is False
    assert runtime.TOML_ALIASES["saveChats"] == ("ui", "save_chats")
    assert runtime.TOML_ALIASES["chatRetention"] == ("ui", "chat_retention")
    # On the Chats page since phase M18 (Display before it).
    page = (ROOT / "pages/ChatsPage.qml").read_text()
    assert 'put("saveChats"' in page and 'put("chatRetention"' in page


def test_the_cli_sends_continue_and_new_to_the_daemon():
    text = (ROOT / "bin/agentvoice").read_text()
    assert 'send_command "chat-continue $3"' in text
    assert 'send_command "chat-new ${3:-main}"' in text
    assert '"$REPO/daemon/chats.py"' in text


def test_the_listing_cannot_drive_the_terminal(tmp_path, monkeypatch, capsys):
    import chats
    store = ChatStore(tmp_path / "chats")
    monkeypatch.setattr(chats, "ChatStore", lambda: store)
    rec(store, transcript="hi \x1b]0;owned\x07 there")
    assert chats.main(["list"]) == 0
    assert "\x1b" not in capsys.readouterr().out
