"""Codex's models and reasoning levels, read from Codex itself.

Its model names change with every release, so a list typed into the
settings goes stale; Codex caches the list for this account in
models_cache.json, and that is what the settings offer.
"""
from __future__ import annotations

import json


def _home(tmp_path, monkeypatch, default="gpt-b"):
    home = tmp_path / "codex"
    home.mkdir()
    levels = [{"effort": e, "description": ""} for e in ("low", "medium", "high")]
    (home / "models_cache.json").write_text(json.dumps({"models": [
        {"slug": "gpt-b", "display_name": "GPT B", "description": "Fast.",
         "visibility": "list", "priority": 2, "supported_reasoning_levels": levels},
        {"slug": "gpt-a", "display_name": "GPT A", "description": "Most capable.",
         "visibility": "list", "priority": 1, "supported_reasoning_levels": levels[:2]},
        {"slug": "review", "display_name": "Review", "visibility": "hide", "priority": 0},
    ]}))
    (home / "config.toml").write_text(f'model = "{default}"\n')
    monkeypatch.setenv("CODEX_HOME", str(home))
    return home


def test_the_list_is_codexs_own_best_first_without_hidden_ones(tmp_path, monkeypatch):
    from adapters.codex import Codex
    _home(tmp_path, monkeypatch)
    listed = Codex.models()
    assert [m["value"] for m in listed] == ["gpt-a", "gpt-b"]
    assert listed[0]["label"] == "GPT A — Most capable"


def test_the_settings_are_given_the_list(tmp_path, monkeypatch):
    from adapters import model_lists
    _home(tmp_path, monkeypatch)
    assert [m["value"] for m in model_lists()["codex"]] == ["gpt-a", "gpt-b"]


def test_no_cache_means_no_list_and_no_error(tmp_path, monkeypatch):
    from adapters.codex import Codex
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "nowhere"))
    assert Codex.models() == []
    assert Codex().efforts() == ()


def test_the_levels_are_the_chosen_models_or_the_defaults(tmp_path, monkeypatch):
    from adapters.codex import Codex
    _home(tmp_path, monkeypatch)
    assert Codex(model="gpt-a").efforts() == ("low", "medium")
    assert Codex().efforts() == ("low", "medium", "high")     # config's gpt-b
    assert Codex(model="unknown").efforts() == ()


def test_an_effort_is_passed_only_when_the_model_takes_it(tmp_path, monkeypatch):
    from adapters.codex import Codex
    _home(tmp_path, monkeypatch)
    argv = Codex(model="gpt-b", effort="high")._argv("", None)
    assert argv[argv.index("-c") + 1] == 'model_reasoning_effort="high"'
    # The notes server (Phase 14) adds -c options of its own.
    assert not any(a.startswith("model_reasoning_effort")
                   for a in Codex(model="gpt-a", effort="high")._argv("", None))
