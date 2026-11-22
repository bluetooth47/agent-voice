"""A display name apart from the wake phrase, and a stable id (plan item 7c).

Every agent has a Name (any text, shown and spoken) and a Wake phrase (one to
three hearable words). Grants, the permission hook, the Agents panel and
saved chats know an agent by an id that neither of those changes, so:

- an agent saved before ids existed gets its wake phrase as its id, which is
  what everything already called it, so the upgrade moves nothing;
- a renamed agent keeps its conversation, its grants and its panel record;
- two agents still cannot share a wake phrase, whatever they are called.
"""
from __future__ import annotations

import json
import sys

import pytest

from conftest import ROOT


# --- Config ------------------------------------------------------------------

class TestIds:
    def test_an_old_agent_gets_its_wake_phrase_as_its_id(self, cfg_factory):
        cfg = cfg_factory(voiceAgents=[{"name": "hey jarvis"}, {"name": "friday"}])
        assert [a["id"] for a in cfg.agents()] == ["hey-jarvis", "friday"]

    def test_the_old_id_is_what_the_panel_already_called_it(self, cfg_factory):
        from agents_panel import slug
        cfg = cfg_factory(voiceAgents=[{"name": "hey jarvis"}])
        assert cfg.agents()[0]["id"] == slug("hey jarvis")

    def test_a_saved_id_is_kept(self, cfg_factory):
        cfg = cfg_factory(voiceAgents=[{"name": "nova", "id": "jarvis-k3f9"}])
        assert cfg.agents()[0]["id"] == "jarvis-k3f9"

    @pytest.mark.parametrize("bad", ["", "  ", "Has Caps", "-lead", "a/b", "x" * 49,
                                     "main", 7, None, ["a"]])
    def test_an_unusable_id_falls_back_to_the_wake_phrase(self, cfg_factory, bad):
        cfg = cfg_factory(voiceAgents=[{"name": "nova", "id": bad}])
        assert cfg.agents()[0]["id"] == "nova"

    def test_an_agent_called_main_does_not_take_the_main_agents_key(self, cfg_factory):
        cfg = cfg_factory(voiceAgents=[{"name": "main"}])
        assert cfg.agents()[0]["id"] == "agent-main"

    def test_a_second_agent_with_the_same_id_is_dropped(self, cfg_factory):
        """It would share the first one's grants, chats and panel record."""
        cfg = cfg_factory(voiceAgents=[{"name": "nova", "id": "a1"},
                                       {"name": "sage", "id": "a1"}])
        assert [a["name"] for a in cfg.agents()] == ["nova"]

    def test_switched_off_agents_are_reported_by_id(self, cfg_factory):
        cfg = cfg_factory(voiceAgents=[{"name": "nova", "id": "a1", "enabled": False}])
        assert cfg.disabled_agents() == {"a1"}

    def test_found_by_id(self, cfg_factory):
        cfg = cfg_factory(voiceAgents=[{"name": "nova", "id": "a1", "level": "edits"}])
        assert cfg.agent_by_id("a1")["level"] == "edits"
        assert cfg.agent_by_id("nova") is None
        assert cfg.agent_by_id("") is None and cfg.agent_by_id(None) is None


class TestNames:
    def test_a_missing_name_is_the_wake_phrase_capitalised(self, cfg_factory):
        cfg = cfg_factory(voiceAgents=[{"name": "hey jarvis"}])
        assert cfg.agents()[0]["label"] == "Hey Jarvis"

    def test_a_name_is_any_text(self, cfg_factory):
        cfg = cfg_factory(voiceAgents=[{"name": "theo", "label": "Théo — the 2nd!"}])
        assert cfg.agents()[0]["label"] == "Théo — the 2nd!"

    def test_a_name_is_one_short_line(self, cfg_factory):
        cfg = cfg_factory(voiceAgents=[
            {"name": "nova", "label": "  a\nb\x1b[31m  c\t" + "x" * 80}])
        label = cfg.agents()[0]["label"]
        assert "\n" not in label and "\x1b" not in label and "\t" not in label
        assert label.startswith("a b[31m c")
        assert len(label) <= 40

    def test_a_name_that_is_not_text_falls_back(self, cfg_factory):
        cfg = cfg_factory(voiceAgents=[{"name": "nova", "label": {"x": 1}}])
        assert cfg.agents()[0]["label"] == "Nova"

    def test_two_agents_cannot_share_a_wake_phrase_even_with_different_names(
            self, cfg_factory):
        cfg = cfg_factory(voiceAgents=[
            {"name": "nova", "label": "Research", "id": "a1"},
            {"name": "Nova", "label": "Writing", "id": "a2"}])
        assert [a["label"] for a in cfg.agents()] == ["Research"]

    def test_two_agents_may_share_a_name(self, cfg_factory):
        """Only the wake phrase has to be told apart by ear."""
        cfg = cfg_factory(voiceAgents=[{"name": "nova", "label": "Helper"},
                                       {"name": "sage", "label": "Helper"}])
        assert len(cfg.agents()) == 2

    def test_the_main_agents_name(self, cfg_factory):
        assert cfg_factory(phrase="hey theo").main_label() == "Hey Theo"
        assert cfg_factory(phrase="theo", mainName=" Theodore ").main_label() == "Theodore"
        assert cfg_factory(mainName="X").main_label("anything") == "X"


def test_main_name_is_in_all_three_places():
    import runtime
    manifest = json.loads((ROOT / "manifest.json").read_text())["barWidget"]
    assert manifest["defaults"]["mainName"] == ""
    assert any(e["key"] == "mainName" for e in manifest["schema"])
    assert runtime.DEFAULTS["mainName"] == ""
    assert runtime.TOML_ALIASES["mainName"] == ("agent", "main_name")
    assert 'put("mainName"' in (ROOT / "pages/AgentsPage.qml").read_text()


# --- the daemon --------------------------------------------------------------

@pytest.fixture
def recon(daemon, monkeypatch):
    import wake_listen
    from test_crew import SlowAgent, Voice
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
    daemon.pipe = type("P", (), {"phrase": "computer", "names": ["jarvis", "nova"],
                                 "unheard": {}})()
    daemon.make_speaker = lambda voice: Voice(voice, [])
    daemon.agent = SlowAgent()
    daemon.built = built
    return daemon


class TestRename:
    def test_a_new_name_and_wake_phrase_keep_the_conversation(self, recon):
        recon.cfg._values["voiceAgents"] = [{"name": "jarvis", "id": "j1"}]
        recon.reconcile_crew()
        p = recon.crew["j1"]
        p.session_id = "keep"
        agent = p.agent
        recon.cfg._values["voiceAgents"] = [
            {"name": "nova", "id": "j1", "label": "Research"}]
        recon.reconcile_crew()
        assert recon.crew["j1"] is p and p.agent is agent
        assert p.session_id == "keep" and len(recon.built) == 1
        assert (p.name, p.label, p.id) == ("nova", "Research", "j1")

    def test_the_hook_is_handed_the_id_not_the_name(self, recon):
        recon.cfg._values["voiceAgents"] = [{"name": "jarvis", "id": "j1"}]
        recon.reconcile_crew()
        assert recon.built[0][1]["named"] == "j1"

    def test_the_new_wake_phrase_wakes_it(self, recon):
        recon.cfg._values["voiceAgents"] = [{"name": "nova", "id": "j1"}]
        recon.reconcile_crew()
        recon.pipe.heard_phrase = "nova"
        assert recon._woken() is recon.crew["j1"]
        recon.pipe.heard_phrase = "computer"
        assert recon._woken() is recon._main

    def test_routing_is_by_wake_phrase_and_speech_by_name(self, recon):
        recon.cfg._values["voiceAgents"] = [
            {"name": "nova", "id": "j1", "label": "Research"}]
        recon.reconcile_crew()
        said = []
        p = recon.crew["j1"]
        recon.dispatch = lambda q, text, last, clock=None: said.append((q, text))
        recon._send(recon._main, "Nova, hello", {}, {})
        assert said and said[0][0] is p

    def test_the_panel_record_follows_the_id(self, recon):
        recon.cfg._values["voiceAgents"] = [{"name": "nova", "id": "j1", "label": "Research"}]
        recon.reconcile_crew()
        recon._mic_shown = ("listening", {})
        rows = {r["key"]: r for r in recon.panel_agents({"state": "listening"})}
        assert rows["j1"]["label"] == "Research" and rows["j1"]["phrase"] == "nova"

    def test_the_main_agents_name_reaches_the_panel_only_when_chosen(self, recon):
        recon.agent = type("A", (), {"name": "claude", "model": "", "effort": None})()
        recon._main.agent = recon.agent
        recon.cfg._values["voiceAgents"] = []
        recon.reconcile_crew()
        recon._mic_shown = ("listening", {})
        assert recon.panel_agents({"state": "listening"})[0]["label"] == "Claude Code"
        recon.cfg._values["mainName"] = "Theo"
        recon.reconcile_crew()
        assert recon._main.label == "Theo"
        assert recon.panel_agents({"state": "listening"})[0]["label"] == "Theo"

    def test_settings_get_the_id_and_the_name(self, recon):
        recon.cfg._values["voiceAgents"] = [{"name": "nova", "id": "j1", "label": "Research"}]
        recon.reconcile_crew()
        [row] = recon.crew_fields()["crew"]
        assert (row["id"], row["name"], row["label"]) == ("j1", "nova", "Research")


# --- the permission hook -----------------------------------------------------

class TestHook:
    @pytest.fixture
    def hook(self, monkeypatch, tmp_path, cfg_factory):
        import permission_hook
        import runtime
        work = tmp_path / "work"
        work.mkdir()
        self.values = {"voiceAgents": [
            {"name": "jarvis", "id": "j1", "agent": "claude", "level": "edits",
             "projectDir": str(work), "label": "Research"}]}
        monkeypatch.setattr(runtime, "Config", lambda: cfg_factory(**self.values))
        monkeypatch.setattr(permission_hook, "GRANTS", tmp_path / "grants")
        monkeypatch.setattr(sys, "argv", ["permission_hook.py", "claude", "j1"])
        return permission_hook

    def test_a_renamed_agent_keeps_its_level(self, hook):
        assert hook._settings()[0] == "edits"
        self.values["voiceAgents"][0].update(name="nova", label="Writer")
        assert hook._settings()[0] == "edits"

    def test_an_id_nobody_has_is_asked_about(self, hook, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["permission_hook.py", "claude", "jarvis"])
        assert hook._settings() == ("ask", None)

    def test_a_grant_survives_a_rename(self, hook):
        sid = "97c52faa-f737-43a3-83db-1ef0a1d86245"
        assert hook.grant(sid)
        self.values["voiceAgents"][0].update(name="nova", label="Writer")
        assert hook.granted(sid)

    def test_the_card_names_the_agent(self, hook, monkeypatch):
        assert hook._label() == "Research"
        monkeypatch.setattr(sys, "argv", ["permission_hook.py", "claude"])
        self.values["phrase"] = "theo"
        assert hook._label() == "Theo"

    def test_a_label_that_cannot_be_read_is_the_id(self, hook, monkeypatch):
        import runtime

        def boom():
            raise RuntimeError("no")
        monkeypatch.setattr(runtime, "Config", boom)
        assert hook._label() == "j1"


# --- the settings page -------------------------------------------------------

def test_the_page_keeps_every_agent_s_id():
    """The upgrade only holds if the page writes the id the daemon derives
    before it changes anything, the wake phrase above all."""
    page = (ROOT / "pages/AgentsPage.qml").read_text()
    s = (ROOT / "Settings.qml").read_text()
    assert "function agentId(" in s
    assert "copy.id = s.agentId(a)" in page
    assert 'updateAgent(index, "label"' in page
