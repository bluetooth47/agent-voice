"""Codex: options before `resume`, and the desktop tools through `-c`.

Two bugs seen live on 2026-11-18 with a Codex agent:

- trusted, every turn after the first failed at once, because the resume
  subcommand rejects --approve-for-me placed after it;
- the desktop tools were never handed to Codex at all, and once they were,
  Codex refused every change in `exec` ("requires approval, but approval
  policy is never") and stripped HYPRLAND_INSTANCE_SIGNATURE from the server.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import desktop_mcp
from adapters.codex import Codex

SERVER = Path(desktop_mcp.__file__).resolve()


def _configs(argv: list[str]) -> dict[str, str]:
    out = {}
    for flag, value in zip(argv, argv[1:]):
        if flag == "-c":
            key, _, val = value.partition("=")
            out[key] = val
    return out


@pytest.mark.parametrize("trusted", [True, False])
def test_every_option_comes_before_resume(trusted):
    a = Codex(model="gpt-x", ask_permission=not trusted)
    a.desktop_tools = True
    argv = a._argv("hi", "thread-1")
    assert argv[-2:] == ["resume", "thread-1"]
    assert ("--approve-for-me" in argv) is trusted


def test_no_desktop_tools_unless_switched_on():
    argv = Codex()._argv("hi", None)
    assert not any(k.startswith("mcp_servers.") for k in _configs(argv))


def test_desktop_tools_start_our_server_as_this_agent():
    a = Codex(ask_permission=True, named="hazel")
    a.desktop_tools = True
    c = _configs(a._argv("hi", None))
    key = "mcp_servers.agentvoice-desktop"
    assert json.loads(c[f"{key}.command"]) == sys.executable
    assert json.loads(c[f"{key}.args"]) == [str(SERVER), "codex", "hazel", "--guard"]
    assert "HYPRLAND_INSTANCE_SIGNATURE" in json.loads(c[f"{key}.env_vars"])
    assert c[f"{key}.default_tools_approval_mode"] == '"approve"'


def test_a_trusted_codex_is_not_guarded():
    a = Codex(ask_permission=False)
    a.desktop_tools = True
    args = json.loads(_configs(a._argv("hi", None))["mcp_servers.agentvoice-desktop.args"])
    assert "--guard" not in args


def test_the_config_values_are_valid_toml():
    import tomllib
    for value in _configs(desktop_mcp.codex_config("codex", "a b\"c")).values():
        tomllib.loads(f"v = {value}")


def test_the_guard_asks_before_a_change(monkeypatch):
    import permission_hook
    asked = []
    monkeypatch.setattr(permission_hook, "decide",
                        lambda tool, args, session="": (asked.append(tool) or ("deny", "no")))
    monkeypatch.setattr(desktop_mcp, "GUARD", True)
    with pytest.raises(desktop_mcp.ToolError, match="no"):
        desktop_mcp.call("notify", {"title": "t", "body": "b"})
    assert asked == ["mcp__agentvoice-desktop__notify"]


def test_the_guard_fails_closed_when_the_check_breaks(monkeypatch):
    import permission_hook

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(permission_hook, "decide", boom)
    monkeypatch.setattr(desktop_mcp, "GUARD", True)
    with pytest.raises(desktop_mcp.ToolError, match="not allowed"):
        desktop_mcp.call("clipboard_write", {"text": "x"})


def test_without_guard_the_hook_is_not_consulted(monkeypatch):
    import permission_hook
    monkeypatch.setattr(permission_hook, "decide",
                        lambda *a, **k: pytest.fail("asked twice"))
    monkeypatch.setattr(desktop_mcp, "GUARD", False)
    desktop_mcp.guarded("notify", {})


def test_guard_flag_is_taken_off_argv_before_the_server_reads_it():
    """permission_hook reads the agent id at argv[2]; --guard must not land there."""
    msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    out = subprocess.run([sys.executable, str(SERVER), "codex", "--guard"],
                         input=json.dumps(msg) + "\n", capture_output=True,
                         text=True, timeout=20, env=os.environ.copy())
    assert json.loads(out.stdout.splitlines()[0])["result"]["tools"]
