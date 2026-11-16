"""The voice agent's model is chosen per agent and only ever one argument.

A model name typed into the settings screen ends up after `--model` in the
argv of a CLI that can run commands, so a value that looks like a flag must
read as unset rather than be passed on.
"""
from __future__ import annotations

import pytest

import adapters
from adapters import takes_model
from adapters.claude_code import ClaudeCode
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


class TestModelFor:
    def test_unset_is_the_cli_default(self, cfg):
        assert cfg.model_for("claude") is None

    def test_a_choice_for_one_agent_does_not_reach_another(self, cfg):
        cfg._values["agentModels"] = {"claude": "sonnet"}
        assert cfg.model_for("claude") == "sonnet"
        assert cfg.model_for("codex") is None

    @pytest.mark.parametrize("ok", ["sonnet", "claude-opus-5-5",
                                    "gpt-5.1-codex", "sonnet[1m]",
                                    "us.anthropic.claude-haiku-5-5"])
    def test_real_names_pass(self, cfg, ok):
        cfg._values["agentModels"] = {"claude": f"  {ok} "}
        assert cfg.model_for("claude") == ok

    @pytest.mark.parametrize("junk", ["", "   ", "--dangerously-skip-permissions",
                                      "-p", "sonnet --verbose", "a\nb", None, 3,
                                      ["sonnet"], "x" * 200])
    def test_anything_else_reads_as_unset(self, cfg, junk):
        cfg._values["agentModels"] = {"claude": junk}
        assert cfg.model_for("claude") is None

    @pytest.mark.parametrize("raw", ["sonnet", None, [], 3])
    def test_a_malformed_container_reads_as_unset(self, cfg, raw):
        cfg._values["agentModels"] = raw
        assert cfg.model_for("claude") is None


class TestTakesModel:
    def test_claude_takes_one(self):
        assert takes_model(ClaudeCode) and takes_model(ClaudeCode())

    def test_the_shared_adapter_and_the_endpoint_do_not(self):
        assert not takes_model(CliAgent)
        assert not takes_model(OpenAICompatible)
        assert not takes_model(None)


class TestLoadPassesIt:
    def test_the_model_reaches_the_argv(self, monkeypatch):
        monkeypatch.setattr(ClaudeCode, "available", lambda self: True)
        agent = adapters.load("claude", model="haiku")
        argv = agent._argv("hello", None)
        assert argv[argv.index("--model") + 1] == "haiku"

    def test_no_model_means_no_flag(self, monkeypatch):
        monkeypatch.setattr(ClaudeCode, "available", lambda self: True)
        assert "--model" not in adapters.load("claude")._argv("hello", None)
