"""The Chats page (phase M18): what the daemon and the CLI do for it.

What has to hold:

- `delete --all` removes only chat files in the chats folder -- never what a
  link there points at, never another name, never a folder -- creates
  nothing when there is no folder, and says how many went;
- a save already in flight when chats are deleted does not put them back:
  a turn that began before the delete is not saved, one that began after is,
  and the next turn starts a fresh chat;
- the search box's words arrive on stdin, never argv, and so does a new
  title; the search ranks with the scorer "continue the chat about" uses;
- `stats` reads sizes without following a link and without creating the
  folder;
- the page is in the sidebar, the three privacy settings have moved there
  with their names, and the delete runs only from a confirmation (the last
  is tests/test_confirms.py's table).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

import chats
from chats import ChatStore, score, wanted_words
from conftest import ROOT

EX = {"transcript": "Make the HUD wider please.", "reply": "Done.", "error": "",
      "stopped": False}


@pytest.fixture
def store(tmp_path):
    return ChatStore(tmp_path / "chats")


def rec(store, chat_id=None, agent_id="", transcript="Make the HUD wider please.",
        reply="Done.", now=None, began=None, label="Theo"):
    return store.record(chat_id=chat_id, agent_id=agent_id, agent_label=label,
                        backend="claude", session_id="s1", project_dir="/p",
                        exchange={**EX, "transcript": transcript, "reply": reply},
                        now=now, began=began)


# --- delete --all --------------------------------------------------------------

class TestDeleteAll:
    def test_every_chat_goes_and_the_count_is_said(self, store):
        ids = [rec(store, transcript=f"chat {i}", now=100 + i) for i in range(3)]
        store.pin(ids[0])
        assert store.delete_all(now=200) == 3
        assert store.list() == []
        assert not any((store.root / f"{i}.json").exists() for i in ids)
        index = json.loads((store.root / "index.json").read_text())
        assert index == {"chats": [], "current": {}, "purged": 200}
        assert store.root.is_dir(), "the folder itself stays"

    def test_a_link_is_removed_as_a_link_and_its_target_is_untouched(self, store, tmp_path):
        rec(store)
        outside = tmp_path / "precious.json"
        outside.write_text('{"id": "0123456789abcdef", "keep": true}')
        link = store.root / "0123456789abcdef.json"
        link.symlink_to(outside)
        dangling = store.root / "fedcba9876543210.json"
        dangling.symlink_to(tmp_path / "nowhere.json")
        assert store.delete_all() == 1, "a link is not a chat, and is not counted"
        assert outside.read_text() == '{"id": "0123456789abcdef", "keep": true}'
        assert not os.path.lexists(link) and not os.path.lexists(dangling)

    def test_nothing_but_chat_files_and_their_temporaries_goes(self, store):
        rec(store)
        keep = {"notes.txt": "x", "README.json": "{}", "0123.json": "{}",
                "ABCDEF0123456789.json": "{}"}
        for name, text in keep.items():
            (store.root / name).write_text(text)
        (store.root / "sub").mkdir()
        (store.root / "sub" / "0123456789abcdef.json").write_text("{}")
        temp = store.root / ".0123456789abcdef.json.4242.tmp"
        temp.write_text("half a chat")
        store.delete_all()
        for name, text in keep.items():
            assert (store.root / name).read_text() == text, name
        assert (store.root / "sub" / "0123456789abcdef.json").exists(), "nothing below the folder"
        assert not temp.exists(), "a half-written chat is chat content too"
        assert (store.root / ".lock").exists()

    def test_no_folder_is_created_and_none_is_counted(self, store):
        assert store.delete_all() == 0
        assert not store.root.exists()

    def test_a_chats_folder_that_is_a_link_is_not_followed(self, tmp_path):
        real = ChatStore(tmp_path / "real")
        cid = rec(real)
        (tmp_path / "linked").symlink_to(tmp_path / "real")
        assert ChatStore(tmp_path / "linked").delete_all() == 0
        assert real.load(cid) is not None

    def test_the_index_keeps_nothing_of_what_went(self, store):
        rec(store, transcript="a secret plan")
        store.delete_all()
        assert "secret" not in (store.root / "index.json").read_text()


# --- a save in flight -----------------------------------------------------------

class TestInFlight:
    def test_a_turn_that_began_before_delete_all_is_not_saved(self, store):
        a = rec(store, now=100)
        store.delete_all(now=200)
        assert rec(store, a, transcript="said before", now=210, began=190) is None
        assert rec(store, None, transcript="a new chat begun before", now=211, began=199) is None
        assert store.list() == []
        assert list(store.root.glob("*.json")) == [store.root / "index.json"]

    def test_a_turn_that_began_after_is_saved_into_a_new_chat(self, store):
        a = rec(store, now=100)
        store.delete_all(now=200)
        b = rec(store, a, transcript="said after", now=220, began=201)
        assert b is not None and b != a
        assert store.load(b)["exchanges"][0]["transcript"] == "said after"

    def test_one_deleted_chat_holds_off_only_its_own_late_turn(self, store):
        a = rec(store, now=100)
        other = rec(store, transcript="other", now=101)
        assert store.delete(a, now=200)
        assert rec(store, a, transcript="late", now=210, began=150) is None
        assert rec(store, other, transcript="unrelated", now=211, began=150) == other
        assert rec(store, a, transcript="later", now=212, began=205) not in (None, a)

    def test_a_deleted_id_is_forgotten_after_an_hour(self, store):
        a = rec(store, now=100)
        store.delete(a, now=200)
        b = rec(store, transcript="x", now=300)
        store.delete(b, now=200 + chats.DELETED_KEEP_S + 1)
        index = json.loads((store.root / "index.json").read_text())
        assert a not in index["deleted"] and b in index["deleted"]

    def test_without_a_start_time_it_saves_as_before(self, store):
        a = rec(store)
        store.delete(a)
        assert rec(store, a) not in (None, a)

    def test_a_damaged_marker_never_stops_a_save(self, store):
        rec(store, now=100)
        index = json.loads((store.root / "index.json").read_text())
        index.update(purged="soon", deleted=["x"])
        (store.root / "index.json").write_text(json.dumps(index))
        assert rec(store, None, now=300, began=250) is not None


class Agent:
    """A backend whose turn takes long enough for the person to press
    Delete all while it runs."""

    name = "claude"
    remembers = True
    cwd = "/p"

    def __init__(self, during=None):
        self.during = during
        self.cancelled = 0

    def send(self, text, session_id=None):
        from adapters.base import Chunk
        if self.during:
            self.during()
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


class TestDaemon:
    def test_delete_all_during_a_turn_is_not_undone_by_its_save(self, d, capsys):
        d.answer("Make the HUD wider", {"transcript": "Make the HUD wider"})
        [first] = d.chats.list()
        d.agent.during = d.chats.delete_all
        d.answer("And taller", {"transcript": "And taller"})
        assert d.chats.list() == [], "the turn in flight did not bring the chat back"
        assert d._main.chat_id is None
        assert "chat not saved: deleted while the turn ran" in capsys.readouterr().out
        d.agent.during = None
        d.answer("Something new", {"transcript": "Something new"})
        [fresh] = d.chats.list()
        assert fresh["id"] != first["id"] and fresh["count"] == 1
        assert fresh["title"] == "Something new"

    def test_one_chat_deleted_during_a_turn_stays_deleted(self, d):
        d.answer("Make the HUD wider", {"transcript": "Make the HUD wider"})
        [first] = d.chats.list()
        d.agent.during = lambda: d.chats.delete(first["id"])
        d.answer("And taller", {"transcript": "And taller"})
        assert d.chats.list() == []


# --- search ---------------------------------------------------------------------

class TestSearch:
    def test_best_first_with_the_voice_scorer(self, store):
        a = rec(store, transcript="Tune the wake word threshold", now=1)
        b = rec(store, transcript="Lunch plans", reply="The wake word is fine", now=2)
        rec(store, transcript="Something else", now=3)
        hits = store.search("wake word")
        assert [h["id"] for h in hits] == [a, b]
        assert hits[0]["score"] == 1.0 and hits[1]["score"] == 0.5
        assert store.find("wake word", "")[0]["id"] == a
        assert score(store.load(a), wanted_words("wake word")) == 1.0

    def test_the_last_word_matches_as_it_is_typed(self, store):
        a = rec(store, transcript="Tune the wake word threshold")
        assert [h["id"] for h in store.search("wak")] == [a]
        assert store.search("wak zzz") == [], "only the last word is a prefix"
        assert store.find("wak", "") == [], "the spoken search is unchanged"

    def test_filler_alone_finds_nothing(self, store):
        rec(store)
        assert store.search("the chat about") == []
        assert store.search("") == []

    def test_every_agents_chats_unless_one_is_asked_for(self, store):
        mine = rec(store, transcript="garden plan", agent_id="")
        sora = rec(store, transcript="garden hose", agent_id="sora")
        assert {h["id"] for h in store.search("garden")} == {mine, sora}
        assert [h["id"] for h in store.search("garden", agent="sora")] == [sora]
        store.share(mine, "sora")
        assert {h["id"] for h in store.search("garden", agent="sora")} == {mine, sora}

    def test_nothing_saved_finds_nothing_and_makes_no_folder(self, store):
        assert store.search("garden") == []
        assert not store.root.exists()

    def test_a_damaged_date_does_not_stop_the_search(self, store):
        a = rec(store, transcript="garden plan")
        index = json.loads((store.root / "index.json").read_text())
        index["chats"][0]["updated"] = "yesterday"
        (store.root / "index.json").write_text(json.dumps(index))
        rec(store, transcript="garden hose")
        assert a in [h["id"] for h in store.search("garden")]

    def test_a_long_query_is_cut(self, store):
        rec(store)
        assert store.search("x " * 10_000) == []


def cli(args, stdin="", env_home=None):
    env = dict(os.environ, XDG_DATA_HOME=str(env_home), PYTHONDONTWRITEBYTECODE="1",
               AGENTVOICE_PYTHON=sys.executable)
    return subprocess.run([str(ROOT / "bin" / "agentvoice"), "chats", *args],
                          input=stdin, capture_output=True, text=True, env=env, timeout=30)


class TestCli:
    @pytest.fixture
    def home(self, tmp_path):
        store = ChatStore(tmp_path / "agentvoice" / "chats")
        self.a = rec(store, transcript="Tune the wake word threshold")
        self.b = rec(store, transcript="Lunch plans")
        self.store = store
        return tmp_path

    def test_search_takes_its_words_on_stdin(self, home):
        r = cli(["search", "--json"], "wake\n", home)
        assert r.returncode == 0, r.stderr
        assert [h["id"] for h in json.loads(r.stdout)] == [self.a]

    def test_search_refuses_words_in_argv(self, home):
        r = cli(["search", "wake"], "", home)
        assert r.returncode == 2 and "stdin" in r.stderr and r.stdout == ""

    def test_search_for_one_agent(self, home):
        r = cli(["search", "--agent", "sora", "--json"], "wake\n", home)
        assert json.loads(r.stdout) == []

    def test_the_plain_search_cannot_drive_the_terminal(self, home):
        self.store.rename(self.a, "wake \x1b]0;owned\x07 word")
        r = cli(["search"], "wake\n", home)
        assert self.a in r.stdout and "\x1b" not in r.stdout

    def test_rename_takes_the_title_on_stdin(self, home):
        r = cli(["rename", self.a], "Wake word tuning\nignored second line\n", home)
        assert r.returncode == 0, r.stderr
        assert self.store.load(self.a)["title"] == "Wake word tuning"
        assert cli(["rename", self.a], "   \n", home).returncode == 1

    def test_delete_all_says_how_many(self, home):
        r = cli(["delete", "--all"], "", home)
        assert (r.returncode, r.stdout.strip()) == (0, "2")
        assert self.store.list() == []
        assert cli(["delete", "--all", "extra"], "", home).returncode == 2

    def test_stats(self, home):
        r = cli(["stats", "--json"], "", home)
        st = json.loads(r.stdout)
        assert st["chats"] == 2 and st["exists"] and st["bytes"] > 0
        assert st["dir"].endswith("agentvoice/chats")


class TestStats:
    def test_nothing_is_created(self, store):
        assert store.stats() == {"dir": str(store.root), "exists": False, "chats": 0,
                                 "pinned": 0, "bytes": 0}
        assert not store.root.exists()

    def test_a_link_is_not_followed_or_counted(self, store, tmp_path):
        rec(store)
        big = tmp_path / "big"
        big.write_bytes(b"x" * 100_000)
        (store.root / "0123456789abcdef.json").symlink_to(big)
        st = store.stats()
        assert st["chats"] == 1 and st["bytes"] < 100_000

    def test_pinned_are_counted(self, store):
        store.pin(rec(store))
        rec(store, transcript="two")
        assert store.stats()["pinned"] == 1


# --- the page -------------------------------------------------------------------

SETTINGS = (ROOT / "Settings.qml").read_text()
PAGE = (ROOT / "pages" / "ChatsPage.qml").read_text()
CHATS = (ROOT / "Chats.qml").read_text()


def test_chats_is_a_sidebar_page_and_the_top_row_button_is_gone():
    assert '{ id: "chats",        label: "Chats"' in SETTINGS
    assert 'root.page === "chats" ? chatsPage' in SETTINGS
    assert "ChatsPage 1.0 ChatsPage.qml" in (ROOT / "pages" / "qmldir").read_text()
    assert "id: switcher" not in SETTINGS
    assert 'root.mode === "history"' not in SETTINGS, "no second mode of the overlay"
    # An older bar or HUD still summons {"mode":"history"}: it opens the page.
    assert 'if (p.mode === "history") p.page = "chats"' in SETTINGS


def test_every_way_in_reaches_the_page():
    panel = (ROOT / "Panel.qml").read_text()
    assert '\\"page\\":\\"chats\\"' in panel
    assert 'text: "Chats"' in panel
    assert 'showChat("")' in (ROOT / "pages" / "OverviewPage.qml").read_text()
    for page in ("DisplayPage", "AgentDetailsPage", "CommunalPage"):
        src = (ROOT / "pages" / f"{page}.qml").read_text()
        assert 'goTo("chats", "")' in src, page
        assert 'showPage("history")' not in src and 'goTo("display"' not in src, page


def test_the_three_privacy_settings_moved_with_their_names():
    display = (ROOT / "pages" / "DisplayPage.qml").read_text()
    for key in ("saveChats", "chatRetention", "keepHistory"):
        assert f'page.s.put("{key}"' in PAGE, key
        assert f'"{key}"' not in display, key


def test_one_browser_in_three_places():
    agent = (ROOT / "pages" / "AgentDetailsPage.qml").read_text()
    communal = (ROOT / "pages" / "CommunalPage.qml").read_text()
    assert "Chats {" in PAGE and "followSummon: true" in PAGE
    assert re.search(r'Chats \{[^}]*scope: "agent"[^}]*scopeAgent: page\.target', agent)
    assert re.search(r'Chats \{[^}]*scope: "multi"', communal)
    assert "followSummon" not in agent + communal, "an embedded browser leaves the page's chat alone"


def test_search_and_rename_go_on_stdin():
    search = CHATS[CHATS.index("id: searcher"):]
    search = search[:search.index("\n  }\n")]
    assert 'command = ["agentvoice", "chats", "search", "--json"]' in search
    assert "write(pending)" in search and "stdinEnabled: true" in search
    rename = CHATS[CHATS.index("function rename("):]
    rename = rename[:rename.index("\n  }")]
    assert 'view.run("rename", [id], ' in rename
    assert 'run("rename", [view.chat.id, t])' not in CHATS, "no title in argv"


def test_delete_all_states_the_count_and_scope():
    button = PAGE[PAGE.index("id: purgeButton"):]
    button = button[:button.index("\n      }")]
    assert "page.chatCount" in button and "every agent's, pinned too" in button
    assert "onConfirmed: page.deleteAllChats()" in button
    assert '["agentvoice", "chats", "delete", "--all"]' in PAGE


def test_the_skill_names_the_page():
    import agentvoice_skill
    assert agentvoice_skill.PAGE_LABELS["ChatsPage"] == "Chats"
    assert agentvoice_skill.page_of_keys()["saveChats"] == "Chats"
