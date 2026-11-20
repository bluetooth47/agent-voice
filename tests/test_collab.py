"""Collaboration runtime: passing a conversation, shared chats (merged plan,
Phase 15).

What has to hold:

- A15-1: a chat's owner no longer changes when another agent records into
  it, and a chat from before Phase 15 reads exactly as it did;
- A15-2: a pass adds the target to `shared_with`, and gives it a turn, only
  after the person was told the chat goes with it -- the spoken line (with
  "stop" cancelling in the window after it), the CLI's stderr, the sheet's
  text -- and an endpoint target names its host;
- A15-3: a task turn runs in the target's session for that chat, never the
  session of its own conversation, so another conversation's "allow all in
  this chat" does not come with it;
- A15-4: each refusal (self, switched off, unreachable) is said with its
  reason and starts no turn;
- A15-5: with saving off, nothing of the brief or the replay reaches the
  data folder;
- a task's states move only forward, once, and a busy target queues;
- the origin file names the chain, and a missing, corrupt or malformed one
  is no chain at all;
- stop, the global stop and a lock do what section "Stop, lock and state"
  says.
"""
from __future__ import annotations

import io
import json
import os
import threading
import time
from pathlib import Path

import pytest

import chats as chat_schema
import collab
from chats import ChatStore
from collab import Board, Task, check

BRIEF_MARK = "zebracrossing-brief-marker"


def _until(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return bool(cond())


# --- the task model -------------------------------------------------------------

def task(i="a" * 16, frm="main", to="sora", **kw):
    return Task(id=i, kind="pass", frm=frm, to=to, chain=[frm], **kw)


class TestBoard:
    def test_states_move_forward_once_and_late_events_are_ignored(self):
        b = Board()
        t, new = b.add(task())
        assert new and t.state == "pending"
        assert b.move(t.id, "active") and t.started
        assert not b.move(t.id, "pending")
        assert b.move(t.id, "cancelled", "stopped")
        # The turn reporting in after the cancel changes nothing.
        assert not b.move(t.id, "completed")
        assert t.state == "cancelled" and t.reason == "stopped"

    @pytest.mark.parametrize("path", [
        ["active", "completed"], ["active", "failed"], ["active", "cancelled"],
        ["refused"], ["cancelled"], ["failed"]])
    def test_every_allowed_path(self, path):
        b = Board()
        t, _ = b.add(task())
        for state in path:
            assert b.move(t.id, state), state
        for state in collab.STATES:
            assert not b.move(t.id, state), f"{path} then {state}"

    def test_pending_cannot_complete_without_starting(self):
        b = Board()
        t, _ = b.add(task())
        assert not b.move(t.id, "completed")

    def test_one_action_is_one_task(self):
        b = Board()
        first, new = b.add(task(request="one"))
        again, new2 = b.add(task(request="two"))
        assert new and not new2 and again is first and first.request == "one"
        assert len(b.public()) == 1

    def test_a_busy_target_queues_and_one_runs_at_a_time(self):
        b = Board()
        t1, _ = b.add(task("1" * 16))
        t2, _ = b.add(task("2" * 16))
        t2.created = t1.created + 1
        assert b.due(time.time(), lambda a: True) == []
        assert b.due(time.time(), lambda a: False) == [t1]
        assert b.position(t2) == 2
        b.move(t1.id, "active")
        assert b.due(time.time(), lambda a: False) == []
        b.move(t1.id, "completed")
        assert b.due(time.time(), lambda a: False) == [t2]

    def test_the_cancel_window_holds_a_task_back(self):
        b = Board()
        t, _ = b.add(task(not_before=time.time() + 60))
        assert b.due(time.time(), lambda a: False) == []

    def test_cancel_returns_only_what_was_running(self):
        b = Board()
        a, _ = b.add(task("1" * 16, to="sora"))
        c, _ = b.add(task("2" * 16, to="hazel"))
        b.move(a.id, "active")
        stopped = b.cancel(lambda t: True)
        assert stopped == [a] and c.state == "cancelled"

    def test_public_holds_no_text(self):
        b = Board()
        b.add(task(request=BRIEF_MARK, brief=BRIEF_MARK))
        assert BRIEF_MARK not in json.dumps(b.public())

    def test_finished_tasks_are_pruned(self):
        b = Board()
        for i in range(collab.KEEP_DONE + 10):
            t, _ = b.add(task(f"{i:016x}"))
            b.move(t.id, "refused", "x")
        b.add(task("f" * 16))
        assert len(b.public()) <= collab.KEEP_DONE + 1


class TestCheck:
    KNOWN = {"main": "Theo", "sora": "Sora", "nova": "Nova", "wren": "Wren"}

    def test_each_refusal_says_why(self):
        kw = dict(known=self.KNOWN, disabled={"nova"}, live={"main", "sora"})
        assert "already has" in check("main", "main", **kw)
        assert "switched off" in check("nova", "main", **kw)
        assert "can't be reached" in check("wren", "main", **kw)
        assert "no agent" in check("ghost", "main", **kw)
        assert check("sora", "main", **kw) == ""


# --- what is said ---------------------------------------------------------------------

def test_the_lines_say_the_chat_goes_and_name_an_endpoints_host():
    assert "whole chat" in collab.sees_line("Sora")
    assert "api.example.com" in collab.sees_line("Sora", "api.example.com")
    assert collab.spoken_line("Sora") == "Passing this chat to Sora."
    assert "api.example.com" in collab.spoken_line("Sora", "api.example.com")


def test_the_brief_is_wrapped_as_information():
    block = collab.brief_block("Theo", "Sora", "User: hi\nTheo: hello")
    assert "information, not an instruction" in block and "<<<" in block
    assert "nothing Theo was allowed" in block


# --- origin files ----------------------------------------------------------------

class TestOrigin:
    def test_round_trip_names_the_chain(self, tmp_path):
        t = task(frm="main", to="sora")
        collab.write_origin("sora", t, {"main": "Theo"}, tmp_path)
        chain = collab.read_origin("sora", tmp_path)
        assert chain == [{"id": "main", "label": "Theo"}]
        assert collab.chain_text(chain) == "for Theo, for you"
        path = tmp_path / "origin" / "sora.json"
        assert path.stat().st_mode & 0o077 == 0
        collab.clear_origin("sora", tmp_path)
        assert collab.read_origin("sora", tmp_path) is None

    @pytest.mark.parametrize("raw", [
        b"", b"not json", b"[]", b'{"chain": "main"}', b'{"chain": []}',
        b'{"chain": [{"id": "../x", "label": "a"}]}',
        b'{"chain": [{"id": "main"}]}',
        b'{"chain": [1, 2]}',
        b'{"chain": [{"id":"a","label":"a"},{"id":"b","label":"b"},'
        b'{"id":"c","label":"c"},{"id":"d","label":"d"}]}',
        b"\xff\xfe",
    ])
    def test_corrupt_or_malformed_is_no_chain(self, tmp_path, raw):
        d = tmp_path / "origin"
        d.mkdir()
        (d / "sora.json").write_bytes(raw)
        assert collab.read_origin("sora", tmp_path) is None

    def test_a_link_is_not_followed(self, tmp_path):
        d = tmp_path / "origin"
        d.mkdir()
        real = tmp_path / "real.json"
        real.write_text('{"chain": [{"id": "main", "label": "Theo"}]}')
        (d / "sora.json").symlink_to(real)
        assert collab.read_origin("sora", tmp_path) is None

    def test_a_bad_agent_id_reads_nothing_and_writes_nothing(self, tmp_path):
        collab.write_origin("../x", task(), {}, tmp_path)
        assert not (tmp_path / "origin").exists() or not any((tmp_path / "origin").iterdir())
        assert collab.read_origin("../x", tmp_path) is None

    def test_the_permission_card_names_the_chain_and_never_raises(self, tmp_path, monkeypatch):
        import permission_hook
        monkeypatch.setattr(collab, "crew_dir", lambda: tmp_path)
        monkeypatch.setattr(permission_hook, "_named", lambda: "sora")
        assert permission_hook._chain() == ""
        collab.write_origin("sora", task(), {"main": "Theo"}, tmp_path)
        assert permission_hook._chain() == "for Theo, for you"
        (tmp_path / "origin" / "sora.json").write_text("{broken")
        assert permission_hook._chain() == ""

    def test_the_chain_is_on_the_request_card(self):
        import permission_hook
        src = Path(permission_hook.__file__).read_text()
        assert '"chain": _chain()' in src


# --- requests from the CLI and the sheet ----------------------------------------

class TestRequests:
    def test_round_trip(self, tmp_path):
        collab.write_request({"to": "sora", "from": "main", "entry": "sheet",
                              "id": "ab" * 8, "chat": "0" * 16}, "the brief\nline two", tmp_path)
        (req,) = collab.take_requests(tmp_path)
        assert req == {"to": "sora", "from": "main", "entry": "sheet", "id": "ab" * 8,
                       "chat": "0" * 16, "brief": "the brief\nline two"}
        assert collab.take_requests(tmp_path) == []

    @pytest.mark.parametrize("head", [
        "to=../x\n", "to=sora\nfrom=A B\n", "to=sora\nchat=xyz\n", "to=sora\nid=zz\n",
        "to=sora\nentry=voice\n", "garbage\n", "",
    ])
    def test_malformed_requests_are_dropped(self, head):
        assert collab.parse_request(head + "\nbrief") is None

    def test_the_cli_says_the_chat_goes_before_it_sends(self, tmp_path, cfg_factory):
        """A15-2 for the CLI: stderr first, then the request file."""
        cfg = cfg_factory(voiceAgents=[
            {"id": "sora", "name": "sora", "agent": "claude", "level": "ask"},
            {"id": "far", "name": "far", "agent": "endpoint",
             "endpointUrl": "https://api.example.com/v1", "endpointModel": "m"}])
        events = []

        class Err(io.StringIO):
            def write(self, s):
                events.append(("stderr", s, list((tmp_path / "requests").glob("*.req"))
                               if (tmp_path / "requests").exists() else []))
                return super().write(s)
        err = Err()
        brief = io.StringIO(BRIEF_MARK)
        brief.isatty = lambda: False
        assert collab.cli_pass(["sora"], brief, err, cfg=cfg, root=tmp_path) == 0
        said = [e for e in events if "whole chat" in e[1]]
        assert said and said[0][2] == [], "the request existed before stderr said so"
        assert len(list((tmp_path / "requests").glob("*.req"))) == 1
        # An endpoint names its host.
        err2 = io.StringIO()
        brief2 = io.StringIO("x")
        brief2.isatty = lambda: False
        assert collab.cli_pass(["far"], brief2, err2, cfg=cfg, root=tmp_path) == 0
        assert "api.example.com" in err2.getvalue()

    def test_the_cli_refuses_without_sending(self, tmp_path, cfg_factory):
        cfg = cfg_factory(voiceAgents=[
            {"id": "nova", "name": "nova", "agent": "claude", "enabled": False}])
        for args, why in ((["main"], "already has"), (["nova"], "switched off"),
                          (["ghost"], "no agent"), (["../x"], "agent id")):
            err = io.StringIO()
            assert collab.cli_pass(args, io.StringIO(""), err, cfg=cfg, root=tmp_path) != 0
            assert why in err.getvalue(), args
        assert not (tmp_path / "requests").exists()

    def test_the_line_mode_takes_one_json_string(self, tmp_path, cfg_factory):
        cfg = cfg_factory(voiceAgents=[{"id": "sora", "name": "sora", "agent": "claude"}])
        line = io.StringIO(json.dumps("two\nlines") + "\n")
        line.isatty = lambda: False
        assert collab.cli_pass(["sora", "--line"], line, io.StringIO(), cfg=cfg,
                               root=tmp_path) == 0
        (req,) = collab.take_requests(tmp_path)
        assert req["brief"] == "two\nlines"


# --- shared chats: the schema ----------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures" / "agents"


class TestSharedChats:
    def old_store(self, tmp_path):
        store = ChatStore(tmp_path / "chats")
        fx = json.loads((FIXTURES / "saved-chats.json").read_text())
        store.root.mkdir(parents=True)
        for chat in fx["chats"]:
            (store.root / f"{chat['id']}.json").write_text(json.dumps(chat))
        return store, fx

    def test_old_chats_read_unchanged(self, tmp_path):
        """A15-1: a chat written before Phase 15, the main one under
        agent_id "", reads as its owner's with nobody else in it."""
        store, fx = self.old_store(tmp_path)
        main = store.load("0123456789abcdef")
        assert chat_schema.owner_of(main) == "main"
        assert chat_schema.participants_of(main) == ["main"]
        assert chat_schema.shared_with(main) == []
        assert chat_schema.sessions_of(main) == {
            "main": {"backend": "claude", "session_id": "sess-main-1", "project_dir": ""}}
        codex = store.load("fedcba9876543210")
        assert chat_schema.owner_of(codex) == "kestrel-x7q"
        # Loading changed nothing on disk.
        for chat in fx["chats"]:
            assert json.loads((store.root / f"{chat['id']}.json").read_text()) == chat

    def test_the_index_rebuild_carries_the_new_fields(self, tmp_path):
        store, _ = self.old_store(tmp_path)
        listed = {c["id"]: c for c in store.list()}
        assert listed["0123456789abcdef"]["owner"] == "main"
        assert listed["0123456789abcdef"]["participants"] == ["main"]
        assert listed["0123456789abcdef"]["agent_id"] == ""
        assert listed["fedcba9876543210"]["agents"] == ["kestrel-x7q"]

    def test_ownership_no_longer_changes_on_record(self, tmp_path):
        store, _ = self.old_store(tmp_path)
        store.record(chat_id="0123456789abcdef", agent_id="nova", agent_label="Nova",
                     backend="claude", session_id="sess-nova", project_dir="/n",
                     exchange={"transcript": "go on", "reply": "Sure.", "kind": "brief",
                               "for": "main"})
        chat = store.load("0123456789abcdef")
        assert chat["agent_id"] == "" and chat["agent_label"] == "Main"
        assert chat["owner"] == "main"
        assert chat["session_id"] == "sess-main-1" and chat["backend"] == "claude"
        assert chat["participants"] == ["main", "nova"]
        assert chat["sessions"]["nova"]["session_id"] == "sess-nova"
        assert chat["sessions"]["main"]["session_id"] == "sess-main-1"
        last = chat["exchanges"][-1]
        assert (last["agent_id"], last["agent_label"], last["kind"], last["for"]) == \
            ("nova", "Nova", "brief", "main")
        # Having spoken grants nothing: only a share does.
        assert not chat_schema.may_replay(chat, "nova")
        assert chat_schema.may_continue(chat, "nova")      # it has a session there

    def test_the_owner_keeps_its_session_up_to_date(self, tmp_path):
        store = ChatStore(tmp_path / "chats")
        cid = store.record(chat_id=None, agent_id="", agent_label="Theo", backend="claude",
                           session_id="s1", project_dir="/p",
                           exchange={"transcript": "a", "reply": "b"})
        store.record(chat_id=cid, agent_id="", agent_label="Theo", backend="claude",
                     session_id=None, project_dir="/p",
                     exchange={"transcript": "c", "reply": "d"})
        chat = store.load(cid)
        assert chat["session_id"] == "s1" and chat["sessions"]["main"]["session_id"] == "s1"
        assert chat["exchanges"][-1]["agent_id"] == "main"

    def test_share_is_the_only_grant_of_replay(self, tmp_path):
        store, _ = self.old_store(tmp_path)
        cid = "0123456789abcdef"
        assert not chat_schema.may_continue(store.load(cid), "nova")
        assert store.share(cid, "nova")
        assert store.share(cid, "nova")             # twice is once
        assert store.share(cid, "main")             # the owner: no change
        chat = store.load(cid)
        assert chat["shared_with"] == ["nova"]
        assert chat_schema.may_replay(chat, "nova")
        with pytest.raises(ValueError):
            store.share(cid, "../x")
        assert store.unshare(cid, "nova")
        assert chat_schema.shared_with(store.load(cid)) == []

    def test_a_hand_edited_list_holds_only_ids(self, tmp_path):
        chat = {"id": "0" * 16, "agent_id": "", "shared_with": ["sora", "../x", 3, "sora"],
                "participants": "main", "sessions": {"BAD": {}, "sora": "x"}}
        assert chat_schema.shared_with(chat) == ["sora"]
        assert chat_schema.participants_of(chat) == ["main"]
        assert chat_schema.sessions_of(chat) == {}

    def test_replay_labels_each_speaker(self, tmp_path):
        chat = {"agent_label": "Theo", "exchanges": [
            {"transcript": "hi", "reply": "hello", "agent_label": "Theo"},
            {"transcript": "go on", "reply": "on it", "agent_label": "Sora"}]}
        text = chat_schema.replay_context(chat)
        assert "Theo: hello" in text and "Sora: on it" in text

    def test_find_includes_chats_shared_with_the_agent(self, tmp_path):
        store, _ = self.old_store(tmp_path)
        assert store.find("", "nova") == []
        store.share("0123456789abcdef", "nova")
        assert [c["id"] for c in store.find("", "nova")] == ["0123456789abcdef"]

    def test_the_cli_refuses_continuing_an_unshared_chat(self, tmp_path, monkeypatch, capsys):
        store, _ = self.old_store(tmp_path)
        monkeypatch.setattr(chat_schema, "ChatStore", lambda: store)
        assert chat_schema.main(["may-continue", "0123456789abcdef", "nova"]) == 1
        assert "isn't shared with nova" in capsys.readouterr().err
        assert chat_schema.main(["share", "0123456789abcdef", "nova"]) == 0
        assert chat_schema.main(["may-continue", "0123456789abcdef", "nova"]) == 0


# --- the daemon ------------------------------------------------------------------

class SlowAgent:
    name = "claude"
    remembers = True
    cwd = "/p"

    def __init__(self, sentences=("One.",), wait=None):
        self.sentences = list(sentences)
        self.wait = wait
        self.cancelled = 0
        self.sent: list = []
        self._stop = threading.Event()

    def send(self, text, session_id=None):
        from adapters.base import Chunk
        self.sent.append((text, session_id))
        self._stop.clear()
        if self.wait is not None:
            self.wait.wait(3.0)
        for s in self.sentences:
            if self._stop.is_set():
                return
            yield Chunk(text=s + " ", session_id=f"s-{id(self)}-{len(self.sent)}")

    def posture(self, level):
        return level

    def cancel(self):
        self.cancelled += 1
        self._stop.set()

    def prepare(self, *a, **k):
        pass


class Voice:
    def __init__(self, name, log):
        self.name = self.requested = name
        self.log = log
        self.cancelled = 0

    def say(self, text, watch=None):
        self.log.append((self.name, "say", text))

    def cancel(self):
        self.cancelled += 1

    def superseded(self):
        return False


AGENTS = [
    {"id": "sora", "name": "sora", "label": "Sora", "agent": "claude", "level": "ask"},
    {"id": "hazel", "name": "hazel", "label": "Hazel", "agent": "codex", "level": "trusted"},
    {"id": "nova", "name": "nova", "label": "Nova", "agent": "claude", "enabled": False},
    {"id": "wren", "name": "wren", "label": "Wren", "agent": "claude"},
]


@pytest.fixture
def crew(daemon, tmp_path):
    """Theo (main) with Sora and Hazel built; Nova switched off; Wren
    configured but not built (the wake engine cannot hear it)."""
    import queue

    from crew import Persona
    log: list = []
    d = daemon
    d.cfg._values.update(voiceAgents=AGENTS, saveChats=True, mainName="Theo",
                         keepHistory=True)
    d.enabled, d.locked, d.yielded = True, False, False
    d._frames = queue.Queue()
    d.pipe = type("P", (), {"conversation": False, "phrase": "theo",
                            "names": ["sora", "hazel"], "unheard": {}})()
    d._main.name, d._main.label = "theo", "Theo"
    d._main.agent = SlowAgent(["Theo here."])
    d._main.speaker = Voice("main", log)
    for spec in AGENTS[:2]:
        p = d.crew[spec["id"]] = Persona(spec["name"], spec)
        p.agent = SlowAgent([f"{spec['label']} here."])
        p.speaker = Voice(spec["id"], log)
    d.chats = ChatStore(tmp_path / "chats")
    d.collab = collab.Runtime(d, root=tmp_path / "crew")
    d.catch_up_one = lambda p: None
    d.log = log
    d.events = []
    real_share, real_dispatch, real_say = d.chats.share, d.dispatch, d._say_for

    def share(cid, agent):
        d.events.append(("share", agent))
        return real_share(cid, agent)

    def dispatch(p, text, last, clock=None, typed=False):
        d.events.append(("dispatch", p.id))
        return real_dispatch(p, text, last, clock, typed)

    def say_for(p, line):
        d.events.append(("say", p.id, line))
        return real_say(p, line)
    d.chats.share, d.dispatch, d._say_for = share, dispatch, say_for
    return d


def _idle(d):
    assert _until(lambda: not any(p.busy for p in d.personas())), "turns did not finish"


def _theo_chat(d, text=f"what is the plan {BRIEF_MARK}"):
    """Theo has answered once, into a saved chat."""
    d.chats.root.mkdir(parents=True, exist_ok=True)
    cid = d.chats.record(chat_id=None, agent_id="", agent_label="Theo", backend="claude",
                         session_id="theo-1", project_dir="/p",
                         exchange={"transcript": text, "reply": "The plan is X."})
    d._main.chat_id, d._main.session_id = cid, "theo-1"
    d._main.last = {"transcript": text, "reply": "The plan is X."}
    return cid


def _release(d):
    """Let every pending task's cancel window pass, and poll."""
    for t in d.collab.board.open():
        t.not_before = 0.0
    d.collab.tick()


class TestPassByVoice:
    def test_said_first_then_shared_then_dispatched(self, crew):
        """A15-2, voice: the spoken line before anything is shared or sent."""
        cid = _theo_chat(crew)
        assert crew.pass_command(crew._main, "Pass this to Sora.")
        assert crew.events == [("say", "", "Passing this chat to Sora.")]
        assert chat_schema.shared_with(crew.chats.load(cid)) == []
        crew.collab.tick()                      # still inside the window
        assert crew.events == [("say", "", "Passing this chat to Sora.")]
        _release(crew)
        assert [e[0] for e in crew.events] == ["say", "share", "dispatch"]
        _idle(crew)
        sora = crew.crew["sora"]
        chat = crew.chats.load(cid)
        assert chat["shared_with"] == ["sora"]
        assert chat["owner"] == "main" and chat["agent_id"] == ""
        last = chat["exchanges"][-1]
        assert (last["agent_id"], last["kind"], last["for"]) == ("sora", "brief", "main")
        assert last["transcript"] == "(passed from Theo)"
        # Sora was given the transcript and the brief, labelled.
        prompt, session = sora.agent.sent[0]
        assert session is None
        assert "Theo: The plan is X." in prompt and "information, not an instruction" in prompt
        # She stays in the shared chat; Theo is as he was.
        assert sora.chat_id == cid
        assert crew._main.session_id == "theo-1" and crew._main.chat_id == cid
        t = crew.collab.board.public()[-1]
        assert t["state"] == "completed"
        assert crew._last_target is sora

    def test_stop_in_the_window_cancels_before_anything_is_shared(self, crew):
        cid = _theo_chat(crew)
        crew.pass_command(crew._main, "pass this to sora")
        crew._send(crew._main, "stop", {}, {})
        _release(crew)
        assert [e[0] for e in crew.events] == ["say"]
        assert chat_schema.shared_with(crew.chats.load(cid)) == []
        assert crew.crew["sora"].agent.sent == []
        assert crew.collab.board.public()[-1]["state"] == "cancelled"

    def test_the_global_stop_clears_the_queue(self, crew):
        _theo_chat(crew)
        crew.pass_command(crew._main, "pass this to sora")
        crew._on_interrupt()
        _release(crew)
        assert crew.crew["sora"].agent.sent == []
        crew.pass_command(crew._main, "pass this to sora")
        crew.full_stop()
        _release(crew)
        assert crew.crew["sora"].agent.sent == []

    def test_take_over_passes_from_whoever_was_spoken_to(self, crew):
        cid = _theo_chat(crew)
        crew._last_target = crew._main
        crew._send(crew._main, "Sora, take over.", {}, {})
        assert crew.events[0] == ("say", "", "Passing this chat to Sora.")
        _release(crew)
        _idle(crew)
        assert crew.chats.load(cid)["shared_with"] == ["sora"]

    def test_the_request_rides_with_it(self, crew):
        _theo_chat(crew)
        crew.pass_command(crew._main, "pass this to Hazel, and ask her to check it")
        _release(crew)
        _idle(crew)
        prompt, _ = crew.crew["hazel"].agent.sent[0]
        assert prompt.endswith("The user now says:\nask her to check it")

    def test_a_name_that_is_no_agent_is_an_ordinary_request(self, crew):
        assert not crew.pass_command(crew._main, "pass this to the left")
        assert crew.events == []


class TestRefusals:
    @pytest.mark.parametrize("said, why", [
        ("pass this to Theo", "Theo already has this conversation."),
        ("pass this to Nova", "Nova is switched off"),
        ("pass this to Wren", "Wren can't be reached"),
    ])
    def test_each_refusal_is_said_and_starts_no_turn(self, crew, said, why):
        """A15-4."""
        _theo_chat(crew)
        assert crew.pass_command(crew._main, said)
        assert crew.events and crew.events[0][0] == "say" and why in crew.events[0][2]
        _release(crew)
        assert not any(e[0] in ("share", "dispatch") for e in crew.events)
        assert all(not p.agent.sent for p in crew.personas())
        assert crew.collab.board.public()[-1]["state"] == "refused"

    def test_rechecked_when_the_turn_starts(self, crew):
        _theo_chat(crew)
        crew.pass_command(crew._main, "pass this to sora")
        # Switched off during the window.
        crew.cfg._values["voiceAgents"] = [dict(AGENTS[0], enabled=False)] + AGENTS[1:]
        _release(crew)
        assert crew.crew["sora"].agent.sent == []
        assert crew.collab.board.public()[-1]["state"] == "refused"
        assert "switched off" in crew.events[-1][2]

    def test_nothing_to_pass_is_refused(self, crew):
        crew.pass_command(crew._main, "pass this to sora")
        assert "nothing to pass" in crew.events[0][2]


class TestQueue:
    def test_a_busy_target_queues_and_says_so(self, crew):
        _theo_chat(crew)
        gate = threading.Event()
        sora = crew.crew["sora"]
        sora.agent.wait = gate
        crew.dispatch(sora, "her own thing", {})
        assert _until(lambda: sora.agent.sent)
        crew.events.clear()
        crew.pass_command(crew._main, "pass this to sora")
        assert any("is busy" in e[2] for e in crew.events if e[0] == "say")
        _release(crew)
        t = crew.collab.board.public()[-1]
        assert t["state"] == "pending" and t["position"] == 1
        gate.set()
        _idle(crew)
        _release(crew)
        _idle(crew)
        assert len(sora.agent.sent) == 2
        assert crew.collab.board.public()[-1]["state"] == "completed"


class TestSessions:
    def test_a_task_never_runs_in_the_targets_own_session(self, crew):
        """A15-3: Sora's own conversation (and any grant scoped to it) stays
        behind; the task gets a new session for this chat."""
        _theo_chat(crew)
        sora = crew.crew["sora"]
        sora.session_id = "sora-own"
        crew.pass_command(crew._main, "pass this to sora")
        _release(crew)
        _idle(crew)
        assert sora.agent.sent[0][1] is None
        assert sora.session_id != "sora-own"

    def test_her_session_in_this_chat_is_resumed(self, crew):
        cid = _theo_chat(crew)
        crew.chats.record(chat_id=cid, agent_id="sora", agent_label="Sora", backend="claude",
                          session_id="sora-in-chat", project_dir="/p",
                          exchange={"transcript": "x", "reply": "y"})
        crew.crew["sora"].session_id = "sora-own"
        crew.pass_command(crew._main, "pass this to sora")
        _release(crew)
        _idle(crew)
        prompt, session = crew.crew["sora"].agent.sent[0]
        assert session == "sora-in-chat"
        assert "We are continuing" not in prompt      # resumed, not replayed

    def test_a_terminals_session_is_not_touched(self, crew):
        cid = _theo_chat(crew)
        crew.chats.record(chat_id=cid, agent_id="sora", agent_label="Sora", backend="claude",
                          session_id="in-terminal", project_dir="/p",
                          exchange={"transcript": "x", "reply": "y"})
        crew.crew["sora"].terminal = "in-terminal"
        crew.pass_command(crew._main, "pass this to sora")
        _release(crew)
        _idle(crew)
        assert crew.crew["sora"].agent.sent[0][1] is None

    def test_a_delegation_puts_the_target_back(self, crew):
        cid = _theo_chat(crew)
        sora = crew.crew["sora"]
        sora.session_id, sora.chat_id = "sora-own", None
        t = Task(id="d" * 16, kind="delegate", frm="main", to="sora", chain=["main"],
                 brief="do x", chat_id=cid, frm_label="Theo", to_label="Sora")
        crew.collab.board.add(t)
        crew.collab.tick()
        _idle(crew)
        assert sora.session_id == "sora-own" and sora.chat_id is None
        assert t.state == "completed"


class TestSavingOff:
    def test_nothing_of_the_brief_reaches_the_data_folder(self, crew, sandbox):
        """A15-5."""
        import paths
        crew.cfg._values["saveChats"] = False
        crew.chats = ChatStore(paths.DATA_DIR / "chats")
        crew.history.path = Path(os.environ["XDG_RUNTIME_DIR"]) / "agentvoice" / "h.jsonl"
        crew.history.append({"agent_id": "", "transcript": f"remember {BRIEF_MARK}",
                             "reply": "ok", "new": True})
        crew._main.last = {"transcript": f"remember {BRIEF_MARK}", "reply": "ok"}
        crew.pass_command(crew._main, "pass this to sora")
        _release(crew)
        _idle(crew)
        prompt, _ = crew.crew["sora"].agent.sent[0]
        assert BRIEF_MARK in prompt                  # she was given it, in memory
        for root, _dirs, files in os.walk(paths.DATA_DIR):
            for f in files:
                data = (Path(root) / f).read_bytes()
                assert BRIEF_MARK.encode() not in data, f
        assert crew.crew["sora"].chat_id is None


class TestStopAndLock:
    def test_stopping_the_source_stops_its_tasks(self, crew):
        _theo_chat(crew)
        gate = threading.Event()
        sora = crew.crew["sora"]
        sora.agent.wait = gate
        crew.pass_command(crew._main, "pass this to sora")
        _release(crew)
        assert _until(lambda: sora.agent.sent)
        crew._send(crew._main, "stop", {}, {})
        gate.set()
        _idle(crew)
        assert crew.collab.board.public()[-1]["state"] == "cancelled"
        assert sora.agent.cancelled

    def test_cancel_by_id(self, crew):
        _theo_chat(crew)
        crew.pass_command(crew._main, "pass this to sora")
        tid = crew.collab.board.open()[0].id
        assert crew.apply_chat_command(f"task-cancel {tid}")
        _release(crew)
        assert crew.crew["sora"].agent.sent == []

    def test_a_task_keeps_running_behind_a_lock_and_speaks_after(self, crew):
        _theo_chat(crew)
        gate = threading.Event()
        sora = crew.crew["sora"]
        sora.agent.wait = gate
        crew.pass_command(crew._main, "pass this to sora")
        _release(crew)
        assert _until(lambda: sora.agent.sent)
        crew.locked = True
        crew.silence()                          # what reconcile_lock does
        assert not sora.interrupt.is_set() and sora.agent.cancelled == 0
        gate.set()
        _idle(crew)
        assert not any(who == "sora" for who, *_ in crew.log), "spoke over the lock"
        assert crew.collab.board.public()[-1]["state"] == "completed"
        crew.collab.tick()                      # still locked: still waiting
        assert not any(who == "sora" for who, *_ in crew.log)
        crew.locked = False
        crew.collab.tick()
        assert ("sora", "say", "Sora here.") in crew.log

    def test_the_origin_file_exists_only_while_the_task_runs(self, crew, tmp_path):
        _theo_chat(crew)
        gate = threading.Event()
        crew.crew["sora"].agent.wait = gate
        crew.pass_command(crew._main, "pass this to sora")
        _release(crew)
        assert collab.read_origin("sora", tmp_path / "crew") == [{"id": "main", "label": "Theo"}]
        gate.set()
        _idle(crew)
        assert collab.read_origin("sora", tmp_path / "crew") is None


class TestShown:
    def test_hud_line_panel_and_state(self, crew):
        _theo_chat(crew)
        gate = threading.Event()
        sora = crew.crew["sora"]
        sora.agent.wait = gate
        crew.pass_command(crew._main, "pass this to sora")
        assert crew.collab.line() == "Theo → Sora: passing"
        _release(crew)
        assert _until(lambda: sora.agent.sent)
        assert crew.collab.line() == "Sora (for Theo): working"
        panel = {a["key"]: a for a in crew.panel_agents({"state": "listening"})}
        assert panel["sora"]["for"] == "Theo"
        import agents_panel
        assert agents_panel.status(panel["sora"], "listening") == "Working for Theo"
        state, extra = crew._compose("listening", {})
        assert extra["collab"] == "Sora (for Theo): working"
        assert extra["who_label"] == "Sora (for Theo)"
        assert BRIEF_MARK not in json.dumps(extra)
        gate.set()
        _idle(crew)
        assert crew.collab.line() == "Sora finished"

    def test_no_tasks_leaves_the_state_as_it_was(self, crew):
        _state, extra = crew._compose("listening", {})
        assert "tasks" not in extra and "collab" not in extra


class TestAudit:
    def test_one_line_per_task_and_no_content(self, crew):
        import audit
        before = len(audit.read(1000))
        _theo_chat(crew)
        crew.pass_command(crew._main, "pass this to sora")
        _release(crew)
        _idle(crew)
        crew.pass_command(crew._main, "pass this to nova")
        lines = audit.read(1000)[before:]
        assert [(l["kind"], l["state"]) for l in lines] == [
            ("task_pass", "completed"), ("task_pass", "refused")]
        assert lines[0]["from"] == "main" and lines[0]["to"] == "sora"
        assert BRIEF_MARK not in audit.log_path().read_text()


class TestContinueShared:
    def test_continuing_without_a_share_is_refused(self, crew, capsys):
        cid = _theo_chat(crew)
        assert crew.apply_chat_command(f"chat-continue {cid} hazel")
        assert "isn't shared with hazel" in capsys.readouterr().out
        assert crew.crew["hazel"].chat_id is None
        crew.chats.share(cid, "hazel")
        assert crew.apply_chat_command(f"chat-continue {cid} hazel")
        assert crew.crew["hazel"].chat_id == cid
        # Hazel has no session in it: the chat is replayed to her.
        assert "We are continuing" in crew.crew["hazel"].replay


def test_the_sheet_says_what_travels_before_send():
    """A15-2, sheet: the words are on it, and the send goes through the
    one CLI path with the chat and a one-press id."""
    src = (Path(__file__).resolve().parent.parent / "ui" / "SendSheet.qml").read_text()
    assert "will see this whole chat (up to 8000 characters)" in src
    assert "is an endpoint: the chat and the brief are sent to" in src
    assert '"agentvoice", "pass"' in src and '"--id", sheet.taskId' in src
    assert "--line" in src


# --- the spoken commands -----------------------------------------------------------

from speech_text import is_take_over, pass_command  # noqa: E402


@pytest.mark.parametrize("said, want", [
    ("Pass this to Sora.", ("sora", "")),
    ("pass this chat to sora, and ask her about the weather",
     ("sora", "ask her about the weather")),
    ("Please send the conversation to Sora", ("sora", "")),
    ("pass it over to hey jarvis and then summarize it", ("hey jarvis", "summarize it")),
    ("pass to Sora", ("sora", "")),
    ("pass this to the left", ("", "")),
    ("move this to a terminal", ("", "")),
    ("hand this to Sora", ("", "")),         # "hand" is the terminal's word
    ("can you pass the salt to sora", ("", "")),
    ("tell sora to pass this to theo", ("", "")),
])
def test_pass_command(said, want):
    assert pass_command(said, ["sora", "theo", "hey jarvis", "jarvis"]) == want


@pytest.mark.parametrize("said, want", [
    ("Take over.", True), ("you take it from here", True), ("take over please", True),
    ("take over the world", False), ("can you take a look", False)])
def test_take_over(said, want):
    assert is_take_over(said) is want


def test_saying_it_twice_is_one_task(crew):
    _theo_chat(crew)
    crew.pass_command(crew._main, "pass this to sora")
    crew.pass_command(crew._main, "pass this to sora")
    assert len(crew.collab.board.open()) == 1
    _release(crew)
    _idle(crew)
    _release(crew)
    _idle(crew)
    assert len(crew.crew["sora"].agent.sent) == 1


def test_the_finished_line_leaves_the_readout(crew, monkeypatch):
    _theo_chat(crew)
    crew.pass_command(crew._main, "pass this to sora")
    _release(crew)
    _idle(crew)
    assert crew.collab.line() == "Sora finished"
    monkeypatch.setattr(collab, "FLASH_S", 0.0)
    crew.collab._flash = ("Sora finished", 0.0)
    crew.collab.tick()
    assert crew.collab.line() == ""


def test_the_line_is_shown_when_it_cannot_be_heard(crew):
    _theo_chat(crew)
    crew.enabled = False                        # muted: nothing is said aloud
    crew.pass_command(crew._main, "pass this to sora")
    assert crew._main.last["reply"] == "Passing this chat to Sora."
