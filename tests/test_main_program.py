"""The main agent's own program (`mainProgram`), instead of always
Omarchy's default: extra agents could pick any program and the main one
could not."""
from __future__ import annotations


def test_a_known_program_is_used_and_anything_else_falls_back(monkeypatch):
    import adapters
    monkeypatch.setattr(adapters, "omarchy_default", lambda: "claude")
    assert adapters.main_program("codex") == "codex"
    assert adapters.main_program("copilot") == "copilot"
    assert adapters.main_program("") == "claude"
    assert adapters.main_program("--rm -rf") == "claude"


def test_the_daemon_builds_the_main_agent_from_it(daemon, cfg_factory, monkeypatch):
    import wake_listen
    built = []

    def load(name=None, **kw):
        built.append(name)
        return None

    monkeypatch.setattr(wake_listen, "load_adapter", load)
    monkeypatch.setattr(wake_listen, "omarchy_default", lambda: "claude")
    daemon.cfg = cfg_factory(echoTailMs=0, mainProgram="codex")
    daemon.agent = None
    daemon.reconcile_agent()
    assert built == ["codex"]
