"""The voice agent's effort level: chosen per agent, offered only where it works.

`claude --effort max` is accepted with a model that has no effort parameter
at all and the turn runs, so nothing downstream says the setting did
nothing. Which models take which levels is therefore decided here, and the
settings screen draws the slider only from what the daemon publishes.
"""
from __future__ import annotations

import json

import pytest

import adapters
from adapters import takes_effort
from adapters.claude_code import EFFORTS, ClaudeCode, effort_levels
from adapters.cli_agent import CliAgent
from adapters.openai_compat import OpenAICompatible
from runtime import DEFAULTS, Config


@pytest.fixture
def cfg():
    c = Config.__new__(Config)
    c._values = dict(DEFAULTS)
    c._stamps = ()
    c.source = "test"
    return c


@pytest.fixture
def no_default(monkeypatch, tmp_path):
    """No ANTHROPIC_MODEL and an empty Claude config: the CLI's own default."""
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    return tmp_path


class TestEffortFor:
    def test_unset_is_the_default(self, cfg):
        assert cfg.effort_for("claude") is None

    def test_a_choice_for_one_agent_does_not_reach_another(self, cfg):
        cfg._values["agentEfforts"] = {"claude": "low"}
        assert cfg.effort_for("claude") == "low"
        assert cfg.effort_for("codex") is None

    @pytest.mark.parametrize("level", EFFORTS)
    def test_every_level_passes(self, cfg, level):
        cfg._values["agentEfforts"] = {"claude": level}
        assert cfg.effort_for("claude") == level

    @pytest.mark.parametrize("junk", ["", "LOW", " low", "--verbose", "high --x",
                                      "extreme", None, 3, ["low"]])
    def test_anything_else_reads_as_unset(self, cfg, junk):
        cfg._values["agentEfforts"] = {"claude": junk}
        assert cfg.effort_for("claude") is None

    @pytest.mark.parametrize("raw", ["low", None, [], 3])
    def test_a_malformed_container_reads_as_unset(self, cfg, raw):
        cfg._values["agentEfforts"] = raw
        assert cfg.effort_for("claude") is None


class TestWhichModelsTakeIt:
    @pytest.mark.parametrize("model", [
        "fable", "opus", "sonnet", "haiku", "opusplan", "sonnet[1m]", "Opus",
        "claude-fable-5-2", "claude-mythos-5-1", "claude-opus-5-5",
        "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7",
        "claude-sonnet-5-5", "claude-sonnet-5", "claude-haiku-5-5",
        "us.anthropic.claude-haiku-5-5", "claude-opus-5-5[1m]",
    ])
    def test_current_models_take_all_five(self, model):
        assert effort_levels(model) == EFFORTS

    @pytest.mark.parametrize("model", ["claude-opus-4-6", "claude-sonnet-4-6"])
    def test_four_six_has_no_xhigh(self, model):
        assert effort_levels(model) == ("low", "medium", "high", "max")

    @pytest.mark.parametrize("model", ["claude-opus-4-5",
                                       "claude-opus-4-5-20251101",
                                       "claude-opus-4-5@20251101"])
    def test_opus_four_five_has_three(self, model):
        assert effort_levels(model) == ("low", "medium", "high")

    @pytest.mark.parametrize("model", [
        "claude-haiku-4-5", "claude-sonnet-4-5", "claude-sonnet-4-20250514",
        "claude-opus-4-1", "claude-3-5-sonnet-20241022", "gpt-5.1-codex",
        "llama3.2", "something-new",
    ])
    def test_older_and_unknown_models_get_no_slider(self, model):
        assert effort_levels(model) == ()

    def test_the_default_model_is_a_current_one(self, no_default):
        assert effort_levels(None) == EFFORTS

    def test_the_default_follows_the_environment(self, no_default, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
        assert effort_levels(None) == ()

    def test_the_default_follows_claude_settings(self, no_default):
        (no_default / "settings.json").write_text(
            json.dumps({"model": "claude-opus-4-6"}))
        assert effort_levels(None) == ("low", "medium", "high", "max")

    def test_unreadable_settings_mean_the_cli_default(self, no_default):
        (no_default / "settings.json").write_text("{not json")
        assert effort_levels(None) == EFFORTS


class TestArgv:
    def test_a_level_the_model_takes_reaches_the_argv(self):
        argv = ClaudeCode(model="opus", effort="low")._argv("", None)
        assert argv[argv.index("--effort") + 1] == "low"

    def test_a_level_the_model_lacks_is_not_passed(self):
        argv = ClaudeCode(model="claude-opus-4-6", effort="xhigh")._argv("", None)
        assert "--effort" not in argv

    def test_a_model_with_no_effort_gets_no_flag(self):
        argv = ClaudeCode(model="claude-haiku-4-5", effort="low")._argv("", None)
        assert "--effort" not in argv

    def test_no_effort_means_no_flag(self):
        assert "--effort" not in ClaudeCode(model="opus")._argv("", None)


class TestLoad:
    def test_claude_takes_one(self):
        assert takes_effort(ClaudeCode) and takes_effort(ClaudeCode())

    def test_the_shared_adapter_and_the_endpoint_do_not(self):
        assert not takes_effort(CliAgent)
        assert not takes_effort(OpenAICompatible)
        assert not takes_effort(None)

    def test_load_passes_it_on(self, monkeypatch):
        monkeypatch.setattr(ClaudeCode, "available", lambda self: True)
        agent = adapters.load("claude", model="sonnet", effort="high")
        argv = agent._argv("", None)
        assert argv[argv.index("--effort") + 1] == "high"


class FakeClaude(ClaudeCode):
    """A ClaudeCode that never starts anything, counting what is stopped.

    No __init__ of its own: takes_effort reads the constructor's signature,
    and a `**kw` one would hide the parameter it is looking for.
    """

    cancelled = 0

    def available(self):
        return True

    def cancel(self):
        self.cancelled += 1


class TestReconcile:
    """Effort is a flag on the waiting process, not part of the conversation."""

    @pytest.fixture
    def running(self, daemon, monkeypatch, tmp_path):
        import wake_listen

        monkeypatch.setattr(wake_listen, "omarchy_default", lambda: "claude")
        monkeypatch.setattr(wake_listen, "project_dir", lambda _: tmp_path)
        daemon.cfg._values["agentModels"] = {"claude": "opus"}
        daemon.agent = FakeClaude(model="opus", cwd=str(tmp_path),
                                  ask_permission=True)
        daemon.session_id = "the-conversation"
        built = []
        monkeypatch.setattr(wake_listen, "load_adapter",
                            lambda **kw: built.append(kw) or FakeClaude(**{
                                k: kw[k] for k in ("model", "effort", "cwd",
                                                   "ask_permission")}))
        daemon.built = built
        return daemon

    def test_changing_it_keeps_the_conversation(self, running):
        agent = running.agent
        running.cfg._values["agentEfforts"] = {"claude": "low"}
        running.reconcile_agent()
        assert running.agent is agent, "rebuilt the agent for an effort change"
        assert running.session_id == "the-conversation"
        assert agent.effort == "low"
        assert agent.cancelled == 1, "the waiting claude kept the old effort"
        assert "--effort" in agent._argv("", running.session_id)

    def test_an_unchanged_level_does_not_restart_anything(self, running):
        running.cfg._values["agentEfforts"] = {"claude": "low"}
        running.reconcile_agent()
        running.reconcile_agent()
        assert running.agent.cancelled == 1

    def test_a_level_the_model_lacks_restarts_nothing(self, running):
        running.agent.model = "claude-haiku-4-5"
        running.cfg._values["agentModels"] = {"claude": "claude-haiku-4-5"}
        running.cfg._values["agentEfforts"] = {"claude": "max"}
        running.reconcile_agent()
        assert running.agent.cancelled == 0
        assert running.effort_in_force() is None

    def test_a_new_model_is_built_with_it(self, running):
        running.cfg._values["agentEfforts"] = {"claude": "high"}
        running.cfg._values["agentModels"] = {"claude": "sonnet"}
        running.reconcile_agent()
        assert running.built and running.built[-1]["effort"] == "high"
        assert running.agent.effort == "high"

    def test_the_panel_is_told_the_notches(self, running):
        running.agent.model = "claude-opus-4-6"
        running.cfg._values["agentModels"] = {"claude": "claude-opus-4-6"}
        running.cfg._values["agentEfforts"] = {"claude": "max"}
        running.reconcile_agent()
        ctx = running.state._context
        assert ctx["efforts"] == ["low", "medium", "high", "max"]
        assert ctx["effort"] == "max"
