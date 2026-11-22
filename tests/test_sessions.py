"""A conversation outlives a new permission level or model (phase M2, bug I).

Reported as "open-mic chats lose earlier turns", and traced in the journal
to 2026-11-19 00:20:51: the level went from Trusted to Ask, the main agent
was rebuilt, and the very next turn started with no history -- so the agent
judged it "not meant for it", having no idea what the conversation was.

The rules, each a way this goes wrong:

- the adapter is still rebuilt, so no process started under the old flags
  (a trusted one, or a hooked one) ever takes another turn;
- a new program, endpoint or folder still starts a new conversation;
- a new level or model keeps it only on a backend with a recorded turn
  proving it resumes under the new flags (tests/fixtures/resume/);
- a backend that has to start fresh says why, in the readout;
- a kept conversation loses its "allow all in this chat" grants when the
  level changed: lowering the level is the newer decision.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

import permission_hook as hook
import sessions
from adapters.antigravity import Antigravity
from adapters.claude_code import ClaudeCode

SID = "97c52faa-f737-43a3-83db-1ef0a1d86245"


# --- the rule ------------------------------------------------------------------

class TestCarry:
    CARRIES = frozenset({"level", "model"})

    @pytest.mark.parametrize("changed", [{"level"}, {"model"}, {"level", "model"}])
    def test_a_level_or_model_is_carried_where_proven(self, changed):
        assert sessions.carry(changed, self.CARRIES) == (True, "")

    @pytest.mark.parametrize("end", ["program", "endpoint", "folder", "other"])
    def test_these_always_start_again(self, end):
        keep, why = sessions.carry({end, "level"}, self.CARRIES)
        assert not keep and why == end

    def test_unproven_is_not_carried(self):
        assert sessions.carry({"level"}, frozenset()) == (False, "level")
        assert sessions.carry({"model"}, frozenset({"level"})) == (False, "model")

    def test_spec_fields_map_to_changes_and_unknown_fields_end_it(self):
        before = {"agent": "claude", "model": "", "level": "ask", "projectDir": "",
                  "endpoint": None, "id": "sora"}
        assert sessions.spec_changes(before, {**before, "level": "trusted"}) == {"level"}
        assert sessions.spec_changes(before, {**before, "model": "haiku"}) == {"model"}
        assert sessions.spec_changes(before, {**before, "projectDir": "/x"}) == {"folder"}
        assert sessions.spec_changes(before, {**before, "agent": "codex"}) == {"program"}
        assert sessions.spec_changes(before, {**before, "newField": 1}) == {"other"}

    def test_the_reasons_are_words_not_conversation(self):
        for reason in ("program", "endpoint", "folder", "level", "model", "other"):
            assert sessions.why(reason, "agy").endswith(("now", "changed", "change"))
        assert "agy" in sessions.why("level", "agy")


# --- the backends that claim it ------------------------------------------------

def test_only_the_backends_with_a_recording_claim_it():
    """The same rule as being offered at all: one real turn, recorded."""
    from adapters import REGISTRY
    fixtures = Path(__file__).parent / "fixtures" / "resume"
    for name, cls in REGISTRY.items():
        claims = getattr(cls, "carries_session_across", frozenset())
        if claims:
            assert (fixtures / f"{name}-level-and-model.json").exists(), name
    assert ClaudeCode.carries_session_across == {"level", "model"}
    assert Antigravity.carries_session_across == frozenset(), \
        "agy could not be signed in to record one (phase M2 notes)"


# --- the main agent ------------------------------------------------------------

class FakeClaude(ClaudeCode):
    """Never starts anything; counts what is stopped."""
    cancelled = 0

    def available(self):
        return True

    def cancel(self):
        self.cancelled += 1


class FakeAgy(Antigravity):
    cancelled = 0

    def available(self):
        return True

    def cancel(self):
        self.cancelled += 1


@pytest.fixture
def main(daemon, monkeypatch, tmp_path):
    import wake_listen

    monkeypatch.setattr(wake_listen, "project_dir",
                        lambda d: Path(d) if d else tmp_path)
    built = []

    def load(name=None, **kw):
        cls = {"claude": FakeClaude, "agy": FakeAgy}[name]
        args = {k: kw[k] for k in ("model", "cwd", "ask_permission") if k in kw}
        a = cls(**args)
        if kw.get("level") in a.levels:
            a.level = kw["level"]
        built.append(a)
        return a

    monkeypatch.setattr(wake_listen, "load_adapter", load)
    monkeypatch.setattr(hook, "GRANTS", tmp_path / "grants")
    daemon.cfg._values["mainProgram"] = "claude"
    daemon.cfg._values["permissions"] = {"claude": "ask", "agy": "ask"}
    daemon.cfg._values["agentModels"] = {"claude": "haiku"}
    daemon.agent = None
    daemon.reconcile_agent()
    daemon.session_id = SID
    daemon.built = built
    daemon.tmp = tmp_path
    return daemon


def _grant(monkeypatch, who="claude"):
    monkeypatch.setattr(sys, "argv", ["permission_hook.py", who])
    assert hook.grant(SID)
    assert hook.granted(SID)


class TestMainAgent:
    def test_ask_to_trusted_and_back_keeps_the_conversation(self, main):
        first = main.agent
        main.cfg._values["permissions"] = {"claude": "trusted"}
        main.reconcile_agent()
        trusted = main.agent
        assert trusted is not first, "the adapter was not rebuilt"
        assert first.cancelled == 1, "the hooked process kept running"
        assert trusted.ask_permission is False
        assert main.session_id == SID, "a level change dropped the conversation"
        main.cfg._values["permissions"] = {"claude": "ask"}
        main.reconcile_agent()
        assert main.agent is not trusted and trusted.cancelled == 1, \
            "the trusted process outlived the level"
        assert main.agent.ask_permission is True
        assert main.session_id == SID
        # And the next turn resumes it under the hook.
        argv = main.agent._argv("", main.session_id)
        assert argv[argv.index("--resume") + 1] == SID
        assert '"matcher": ".*"' in argv[argv.index("--settings") + 1]

    def test_a_new_model_keeps_it(self, main):
        main.cfg._values["agentModels"] = {"claude": "sonnet"}
        main.reconcile_agent()
        assert main.agent.model == "sonnet" and main.session_id == SID

    def test_a_new_folder_starts_a_new_one_and_says_why(self, main, capsys):
        other = main.tmp / "elsewhere"
        main.cfg._values["projectDir"] = str(other)
        main.reconcile_agent()
        assert main.agent.cwd == str(other)
        assert main.session_id is None
        assert "project folder changed" in main.state._context["notice"]
        assert "new conversation — its project folder changed" in capsys.readouterr().out

    def test_a_new_program_starts_a_new_one(self, main):
        main.cfg._values["mainProgram"] = "agy"
        main.reconcile_agent()
        assert isinstance(main.agent, FakeAgy) and main.session_id is None
        assert "different program" in main.state._context["notice"]

    def test_a_backend_without_a_recording_starts_fresh_and_says_why(self, main):
        main.cfg._values["mainProgram"] = "agy"
        main.reconcile_agent()
        main.session_id = SID
        main.cfg._values["permissions"] = {"claude": "ask", "agy": "trusted"}
        main.reconcile_agent()
        assert main.agent.level == "trusted" and main.session_id is None
        notice = main.state._context["notice"]
        assert "Antigravity cannot carry a chat across a permission change" in notice

    def test_the_notice_lasts_until_the_agent_has_answered(self, main):
        main.cfg._values["projectDir"] = str(main.tmp / "elsewhere")
        main.reconcile_agent()
        assert main.expire_notices() is False         # nothing answered yet
        main._main.turn_id += 1                       # a turn began...
        main._main.answering = True
        assert main.expire_notices() is False         # ...and is still going
        main._main.answering = False
        assert main.expire_notices() is True
        main.publish_agent()
        assert "notice" not in main.state._context

    def test_a_level_change_withdraws_allow_all_in_this_chat(self, main, monkeypatch):
        _grant(monkeypatch)
        main.cfg._values["permissions"] = {"claude": "trusted"}
        main.reconcile_agent()
        assert main.session_id == SID
        assert not hook.granted(SID), "the grant outlived the level it was made under"

    def test_a_model_change_leaves_the_grant(self, main, monkeypatch):
        _grant(monkeypatch)
        main.cfg._values["agentModels"] = {"claude": "sonnet"}
        main.reconcile_agent()
        assert main.session_id == SID and hook.granted(SID)


# --- revoke() itself: guard code, so it fails toward asking ----------------------

class TestRevoke:
    @pytest.fixture(autouse=True)
    def grants(self, tmp_path, monkeypatch):
        monkeypatch.setattr(hook, "GRANTS", tmp_path / "grants")
        return tmp_path / "grants"

    def test_every_agents_grant_for_that_session_goes(self, monkeypatch):
        _grant(monkeypatch, "claude")
        monkeypatch.setattr(sys, "argv", ["permission_hook.py", "claude", "sora"])
        assert hook.grant(SID)
        assert hook.revoke(SID) == 2
        assert not hook.granted(SID)

    def test_other_sessions_are_kept(self, monkeypatch):
        other = "11111111-2222-3333-4444-555555555555"
        monkeypatch.setattr(sys, "argv", ["permission_hook.py", "claude"])
        assert hook.grant(other)
        assert hook.revoke(SID) == 0
        assert hook.granted(other)

    @pytest.mark.parametrize("bad", ["", "not-a-session", "../../x", None])
    def test_a_malformed_session_touches_nothing(self, monkeypatch, bad):
        _grant(monkeypatch)
        assert hook.revoke(bad) == 0
        assert hook.granted(SID)

    def test_unreadable_files_and_a_missing_folder_never_raise(self, grants, monkeypatch):
        assert hook.revoke(SID) == 0                   # no folder yet
        _grant(monkeypatch)
        (grants / "junk.grant").write_text("{not json")
        (grants / "dir.grant").mkdir()
        assert hook.revoke(SID) == 1
        assert (grants / "junk.grant").exists(), "left alone: granted() rejects it"


# --- an extra agent -------------------------------------------------------------

@pytest.fixture
def crew(daemon, monkeypatch, tmp_path):
    import wake_listen

    def load(program, **kw):
        cls = {"claude": FakeClaude, "agy": FakeAgy}[program]
        a = cls(**{k: kw[k] for k in ("model", "cwd", "ask_permission") if k in kw})
        if kw.get("level") in a.levels:
            a.level = kw["level"]
        return a

    monkeypatch.setattr(wake_listen, "load_adapter", load)
    monkeypatch.setattr(hook, "GRANTS", tmp_path / "grants")
    daemon.pipe = type("P", (), {"phrase": "theo", "names": ["sora"],
                                 "unheard": {}})()
    daemon.make_speaker = lambda voice: None
    daemon.agent.posture = lambda level: level
    daemon.cfg._values["voiceAgents"] = [{"name": "sora", "agent": "claude"}]
    daemon.reconcile_crew()
    daemon.crew["sora"].session_id = SID
    daemon.tmp = tmp_path
    return daemon


class TestExtraAgent:
    def test_a_level_change_keeps_it_and_rebuilds(self, crew):
        p = crew.crew["sora"]
        before = p.agent
        crew.cfg._values["voiceAgents"] = [{"name": "sora", "agent": "claude",
                                            "level": "trusted"}]
        crew.reconcile_crew()
        assert p.agent is not before and before.cancelled == 1
        assert p.agent.ask_permission is False and p.session_id == SID

    def test_ask_to_edits_keeps_it(self, crew):
        """A level that moved no flag at all was a new conversation too."""
        crew.cfg._values["voiceAgents"] = [{"name": "sora", "agent": "claude",
                                            "level": "edits"}]
        crew.reconcile_crew()
        assert crew.crew["sora"].session_id == SID

    def test_a_folder_change_starts_again_and_says_why(self, crew):
        crew.cfg._values["voiceAgents"] = [{"name": "sora", "agent": "claude",
                                            "projectDir": str(crew.tmp)}]
        crew.reconcile_crew()
        assert crew.crew["sora"].session_id is None
        assert "sora: new chat — its project folder changed." in \
            crew.crew_fields()["notice"].lower()

    def test_agy_starts_fresh_on_a_level_change(self, crew):
        crew.cfg._values["voiceAgents"] = [{"name": "sora", "agent": "agy"}]
        crew.reconcile_crew()
        p = crew.crew["sora"]
        p.session_id = SID
        crew.cfg._values["voiceAgents"] = [{"name": "sora", "agent": "agy",
                                            "level": "trusted"}]
        crew.reconcile_crew()
        assert p.session_id is None
        assert "cannot carry a chat across a permission change" in \
            crew.crew_fields()["notice"]

    def test_the_grant_goes_with_the_level(self, crew, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["permission_hook.py", "claude", "sora"])
        assert hook.grant(SID) and hook.granted(SID)
        crew.cfg._values["voiceAgents"] = [{"name": "sora", "agent": "claude",
                                            "level": "trusted"}]
        crew.reconcile_crew()
        assert crew.crew["sora"].session_id == SID and not hook.granted(SID)
