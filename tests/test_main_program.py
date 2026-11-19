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


import pytest  # noqa: E402


@pytest.mark.parametrize("program", ["codex", "gemini"])
@pytest.mark.parametrize("level", ["ask", "trusted"])
def test_a_refresh_with_nothing_changed_keeps_the_main_agent_and_its_session(
        daemon, cfg_factory, monkeypatch, program, level):
    """Phase 9, check A9-0. `reconcile_agent` keeps the adapter only when its
    `ask_permission` matches the level; Codex and Gemini never set one, so
    every idle refresh built a new adapter and dropped the conversation.
    Nobody noticed because the main agent here is Claude -- it was found
    reading the code for the Phase 8 backend matrix."""
    import wake_listen
    from adapters.codex import Codex
    from adapters.gemini import Gemini
    cls = {"codex": Codex, "gemini": Gemini}[program]
    built = []

    def load(name=None, ask_permission=True, cwd=None, model=None, **kw):
        agent = cls(model=model, cwd=cwd, ask_permission=ask_permission)
        built.append(agent)
        return agent

    monkeypatch.setattr(wake_listen, "load_adapter", load)
    daemon.cfg = cfg_factory(echoTailMs=0, mainProgram=program,
                             permissions={program: level})
    daemon.agent = None
    daemon.reconcile_agent()
    assert len(built) == 1
    daemon.session_id = "a-conversation"
    daemon.reconcile_agent()
    daemon.reconcile_agent()
    assert len(built) == 1, "an idle refresh rebuilt the main agent"
    assert daemon.agent is built[0]
    assert daemon.session_id == "a-conversation"
