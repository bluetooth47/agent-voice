"""Plan 12a and 12b: desktop tools through MCP, and the Omarchy skill.

The MCP server is driven over its real stdio, with stub `hyprctl`, `grim`
and friends on PATH that record what they were asked to do, so nothing here
touches the real desktop.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import desktop_mcp
import omarchy_skill
import permission_hook as hook

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "daemon/desktop_mcp.py"
P = "mcp__agentvoice-desktop__"


# --- stubs --------------------------------------------------------------------

CLIENTS = [{"address": "0x1a", "class": "firefox", "title": "Docs",
            "workspace": {"id": 2}, "mapped": True},
           {"address": "0x2b", "class": "foot", "title": "shell",
            "workspace": {"id": 1}, "mapped": True}]


@pytest.fixture
def stubs(tmp_path, monkeypatch):
    """A PATH whose desktop commands log their argv to calls.log."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "calls.log"
    script = f"""#!/bin/sh
printf '%s\\n' "$(basename "$0") $*" >> {log}
case "$(basename "$0") $1 $2" in
  "hyprctl -j clients") echo '{json.dumps(CLIENTS)}' ;;
  "hyprctl -j activewindow") echo '{json.dumps(CLIENTS[1])}' ;;
  "hyprctl -j workspaces") echo '[{{"id":1,"windows":1,"monitor":"eDP-1"}}]' ;;
  "hyprctl dispatch"*) echo ok ;;
  "wl-paste"*) printf 'copied text' ;;
  "grim"*) for a; do last=$a; done; printf 'PNGDATA' > "$last" ;;
esac
"""
    for name in ("hyprctl", "notify-send", "wl-copy", "wl-paste", "grim", "wpctl",
                 "uwsm-app", "omarchy-system-lock", "systemctl", "playerctl",
                 "omarchy-audio-output-volume", "omarchy-launch-editor",
                 "xdg-terminal-exec", "omarchy-launch-browser"):
        f = bin_ / name
        f.write_text(script)
        f.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}:/usr/bin:/bin")
    # Spawned commands are detached; wait for them in the tests below.
    return log


def calls(log: Path) -> list[str]:
    import time
    time.sleep(0.15)
    return log.read_text().splitlines() if log.exists() else []


def rpc(*messages, env=None):
    """Send messages to a real server process, return its replies."""
    lines = "".join(json.dumps(m) + "\n" for m in messages)
    out = subprocess.run([sys.executable, str(SERVER), "claude"], input=lines,
                         capture_output=True, text=True, timeout=20,
                         env=env or os.environ.copy())
    return [json.loads(l) for l in out.stdout.splitlines() if l.strip()]


# --- the protocol -------------------------------------------------------------

def test_it_speaks_mcp_over_stdio():
    replies = rpc(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "t", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "nope"})
    assert [r["id"] for r in replies] == [1, 2, 3]      # no reply to a notification
    init = replies[0]["result"]
    assert init["protocolVersion"] == "2025-06-18"
    assert init["serverInfo"]["name"] == "agentvoice-desktop"
    names = {t["name"] for t in replies[1]["result"]["tools"]}
    assert {"open_app", "screenshot", "lock_screen", "list_windows"} <= names
    assert replies[2]["error"]["code"] == -32601


def test_an_unknown_protocol_version_gets_the_newest():
    (r,) = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "1999-01-01"}})
    assert r["result"]["protocolVersion"] == desktop_mcp.PROTOCOLS[0]


def test_garbage_is_a_parse_error_not_a_crash():
    out = subprocess.run([sys.executable, str(SERVER), "claude"],
                         input="{not json\n" + json.dumps(
                             {"jsonrpc": "2.0", "id": 9, "method": "ping"}) + "\n",
                         capture_output=True, text=True, timeout=20)
    replies = [json.loads(l) for l in out.stdout.splitlines()]
    assert replies[0]["error"]["code"] == -32700
    assert replies[1] == {"jsonrpc": "2.0", "id": 9, "result": {}}


def test_every_tool_declares_a_closed_schema():
    for t in desktop_mcp.TOOLS:
        assert t["inputSchema"]["additionalProperties"] is False, t["name"]


# --- the tools, against stubs -------------------------------------------------

def test_windows_are_listed(stubs):
    windows = json.loads(desktop_mcp.call("list_windows", {}))
    assert [w["class"] for w in windows] == ["firefox", "foot"]
    assert [w["focused"] for w in windows] == [False, True]


def test_focus_move_close_and_workspace_use_hyprctl(stubs):
    desktop_mcp.call("focus_window", {"address": "0x1a"})
    desktop_mcp.call("move_window", {"address": "0x1a", "workspace": 3})
    desktop_mcp.call("close_window", {"address": "0x1a"})
    desktop_mcp.call("switch_workspace", {"workspace": 4})
    assert calls(stubs) == [
        "hyprctl dispatch focuswindow address:0x1a",
        "hyprctl dispatch movetoworkspacesilent 3,address:0x1a",
        "hyprctl dispatch closewindow address:0x1a",
        "hyprctl dispatch workspace 4"]


@pytest.mark.parametrize("args", [{"address": "0x1a; rm -rf ~"},
                                  {"address": "firefox"}, {}])
def test_a_window_address_is_only_an_address(stubs, args):
    with pytest.raises(desktop_mcp.ToolError):
        desktop_mcp.call("close_window", args)
    assert calls(stubs) == []


@pytest.mark.parametrize("ws", [0, 100, "two", None])
def test_a_workspace_is_a_number_in_range(stubs, ws):
    with pytest.raises(desktop_mcp.ToolError):
        desktop_mcp.call("switch_workspace", {"workspace": ws})


def _desktop_file(d: Path, name: str, **fields):
    d.mkdir(parents=True, exist_ok=True)
    body = "[Desktop Entry]\nType=Application\n" + "".join(
        f"{k}={v}\n" for k, v in fields.items())
    (d / name).write_text(body)


def test_an_app_is_found_by_its_launcher_name(tmp_path):
    apps = tmp_path / "applications"
    _desktop_file(apps, "org.mozilla.firefox.desktop", Name="Firefox", Exec="firefox")
    _desktop_file(apps, "org.gnome.Nautilus.desktop", Name="Files", Exec="nautilus")
    _desktop_file(apps, "secret.desktop", Name="Firewall", NoDisplay="true")
    assert desktop_mcp.find_app("firefox", [apps]) == "org.mozilla.firefox.desktop"
    assert desktop_mcp.find_app("Files", [apps]) == "org.gnome.Nautilus.desktop"
    assert desktop_mcp.find_app("fire", [apps]) == "org.mozilla.firefox.desktop"
    assert desktop_mcp.find_app("bash -c id", [apps]) is None


def test_open_app_launches_a_desktop_entry_never_a_command(stubs, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "none"))
    _desktop_file(tmp_path / "data/applications", "firefox.desktop", Name="Firefox")
    assert desktop_mcp.call("open_app", {"name": "Firefox"}) == "opened firefox"
    assert calls(stubs) == ["uwsm-app -- firefox.desktop"]
    with pytest.raises(desktop_mcp.ToolError):
        desktop_mcp.call("open_app", {"name": "rm -rf /"})


def test_the_clipboard_round_trips(stubs):
    assert desktop_mcp.call("clipboard_read", {}) == "copied text"
    desktop_mcp.call("clipboard_write", {"text": "hello"})
    assert "wl-copy " in calls(stubs)


def test_volume_is_clamped(stubs):
    assert desktop_mcp.call("volume", {"action": "set", "percent": 150}) == "volume 100%"
    assert "wpctl set-volume @DEFAULT_AUDIO_SINK@ 100%" in calls(stubs)


def test_a_layout_opens_terminal_editor_and_browser(stubs, tmp_path):
    out = desktop_mcp.call("open_project_layout",
                           {"folder": str(tmp_path), "url": "https://example.com"})
    assert out.startswith("opened terminal, editor, browser")
    seen = calls(stubs)
    assert f"uwsm-app -- xdg-terminal-exec --dir={tmp_path}" in seen
    assert f"omarchy-launch-editor {tmp_path}" in seen
    assert "omarchy-launch-browser https://example.com" in seen


def test_a_layout_refuses_a_url_that_is_not_web(stubs, tmp_path):
    with pytest.raises(desktop_mcp.ToolError):
        desktop_mcp.call("open_project_layout", {"folder": str(tmp_path),
                                                 "editor": False, "terminal": False,
                                                 "url": "file:///etc/passwd"})


# --- lock and suspend need the words this turn --------------------------------

def _heard(monkeypatch, text):
    monkeypatch.setattr(desktop_mcp, "heard_this_turn", lambda: text)


@pytest.mark.parametrize("tool, said", [
    ("lock_screen", "theo lock the screen"), ("lock_screen", "Lock my computer"),
    ("suspend", "suspend the laptop"), ("suspend", "put it to sleep")])
def test_lock_and_suspend_follow_what_was_said(stubs, monkeypatch, tool, said):
    _heard(monkeypatch, said)
    desktop_mcp.call(tool, {})
    assert calls(stubs)


@pytest.mark.parametrize("tool, said", [
    ("lock_screen", "what time is it"), ("lock_screen", ""),
    ("suspend", "lock the screen"), ("lock_screen", "unblock the door"),
    ("suspend", "sleepy music please")])
def test_lock_and_suspend_are_refused_otherwise(stubs, monkeypatch, tool, said):
    _heard(monkeypatch, said)
    with pytest.raises(desktop_mcp.ToolError, match="did not ask"):
        desktop_mcp.call(tool, {})
    assert calls(stubs) == []


def test_heard_this_turn_reads_the_state_file(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "RUNTIME_DIR", tmp_path)
    (tmp_path / "state").write_text(json.dumps({"transcript": "lock it"}))
    assert desktop_mcp.heard_this_turn() == "lock it"
    (tmp_path / "state").write_text("garbage")
    assert desktop_mcp.heard_this_turn() == ""


# --- a screenshot is asked about every time -----------------------------------

def test_a_refused_screenshot_takes_nothing(stubs, monkeypatch):
    monkeypatch.setattr(desktop_mcp, "ask_at_the_desktop", lambda t, a: False)
    with pytest.raises(desktop_mcp.ToolError, match="refused"):
        desktop_mcp.call("screenshot", {})
    assert calls(stubs) == []


def test_an_allowed_screenshot_is_an_image_and_leaves_no_file(stubs, monkeypatch, tmp_path):
    monkeypatch.setattr(desktop_mcp, "ask_at_the_desktop", lambda t, a: True)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    kind, data = desktop_mcp.call("screenshot", {"scale": 9})
    assert (kind, data) == ("image", b"PNGDATA")
    assert any(c.startswith("grim -s 1 ") for c in calls(stubs))
    assert not list(tmp_path.glob("agentvoice-shot-*"))


def test_the_screenshot_question_ignores_a_chat_grant(monkeypatch):
    """It goes straight to _ask, never through decide(), so neither
    "trusted" nor "allow all in this chat" can answer it."""
    seen = {}

    def ask(tool, args, note="", session=""):
        seen.update(tool=tool, session=session)
        return "deny", "no"

    monkeypatch.setattr(hook, "_ask", ask)
    monkeypatch.setattr(hook, "granted", lambda s: True)
    monkeypatch.setattr(hook, "_settings", lambda: ("trusted", None))
    assert desktop_mcp.ask_at_the_desktop("screenshot", {}) is False
    assert seen == {"tool": P + "screenshot", "session": ""}


def test_a_screenshot_reply_is_an_mcp_image(monkeypatch):
    monkeypatch.setattr(desktop_mcp, "call", lambda n, a: ("image", b"\x89PNG"))
    r = desktop_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": "screenshot", "arguments": {}}})
    (item,) = r["result"]["content"]
    assert item["type"] == "image" and item["mimeType"] == "image/png"


def test_a_tool_error_is_reported_to_the_agent_not_raised():
    r = desktop_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": "no_such_tool", "arguments": {}}})
    assert r["result"]["isError"] is True


# --- the permission hook ------------------------------------------------------

@pytest.fixture
def asked(monkeypatch):
    seen = []
    monkeypatch.setattr(hook, "_ask", lambda tool, args, note="", session="":
                        (seen.append(tool), ("deny", "asked"))[1])
    monkeypatch.setattr(hook, "granted", lambda s: False)
    return seen


def _at(monkeypatch, level):
    monkeypatch.setattr(hook, "_settings", lambda: (level, None))


@pytest.mark.parametrize("level", ["ask", "edits"])
def test_reading_windows_is_free_and_changes_are_asked(monkeypatch, asked, level):
    _at(monkeypatch, level)
    for tool in ("list_windows", "active_window", "list_workspaces"):
        assert hook.decide(P + tool, {})[0] == "allow"
    for tool in ("open_app", "close_window", "move_window", "switch_workspace",
                 "volume", "media", "notify", "clipboard_write", "lock_screen",
                 "suspend", "open_project_layout", "clipboard_read"):
        assert hook.decide(P + tool, {})[0] == "deny", tool
    assert len(asked) == 12


def test_trusted_lets_changes_through(monkeypatch, asked):
    _at(monkeypatch, "trusted")
    for tool in ("close_window", "clipboard_read", "lock_screen"):
        assert hook.decide(P + tool, {})[0] == "allow"
    assert asked == []


def test_the_hook_leaves_the_screenshot_to_the_server(monkeypatch, asked):
    _at(monkeypatch, "ask")
    assert hook.decide(P + "screenshot", {})[0] == "allow"


def test_another_servers_tool_of_the_same_name_is_asked(monkeypatch, asked):
    _at(monkeypatch, "ask")
    for tool in ("mcp__evil__list_windows", "mcp__agentvoice-desktop2__screenshot",
                 "list_windows", "mcp__agentvoice-desktop_list_windows"):
        assert hook.decide(tool, {})[0] == "deny", tool


def test_the_hook_and_the_server_agree_on_the_lists():
    assert hook.DESKTOP_PREFIX == f"mcp__{desktop_mcp.SERVER}__"
    assert hook.DESKTOP_READ_ONLY == set(desktop_mcp.READ_ONLY)
    assert hook.DESKTOP_SENSITIVE_READ == set(desktop_mcp.SENSITIVE_READ)
    assert hook.DESKTOP_SELF_ASKED == set(desktop_mcp.SELF_ASKED)
    declared = {t["name"] for t in desktop_mcp.TOOLS}
    assert set(desktop_mcp.READ_ONLY) | set(desktop_mcp.SENSITIVE_READ) \
        | set(desktop_mcp.SELF_ASKED) <= declared


# --- the adapter --------------------------------------------------------------

def test_claude_gets_the_server_and_the_skill_only_when_on():
    from adapters.claude_code import ClaudeCode
    a = ClaudeCode(named="nova-k3f")
    argv = a._argv("", None)
    assert "--mcp-config" not in argv and "--plugin-dir" not in argv
    a.desktop_tools, a.skill_dir = True, "/skills/here"
    argv = a._argv("", None)
    config = json.loads(argv[argv.index("--mcp-config") + 1])
    server = config["mcpServers"]["agentvoice-desktop"]
    assert server["args"][1:] == ["claude", "nova-k3f"]
    assert argv[argv.index("--plugin-dir") + 1] == "/skills/here"
    assert "--strict-mcp-config" not in argv      # the user's servers stay


def test_other_backends_get_the_short_list_in_their_instructions():
    from adapters.codex import Codex
    from adapters.openai_compat import OpenAICompatible
    c = Codex()
    c.skill_text = "OMARCHY COMMANDS"
    assert "OMARCHY COMMANDS" in c.preamble()
    e = OpenAICompatible("http://x/v1", "m", is_agent=True)
    e.skill_text = "OMARCHY COMMANDS"
    assert "OMARCHY COMMANDS" not in e.preamble()


def test_the_daemon_applies_both_and_keeps_the_conversation(cfg_factory, tmp_path, monkeypatch):
    from wake_listen import Daemon
    from adapters.claude_code import ClaudeCode
    d = Daemon.__new__(Daemon)
    d.cfg = cfg_factory(desktopTools=True, omarchySkill=True)
    monkeypatch.setattr(omarchy_skill, "plugin_dir", lambda: str(tmp_path))
    a = ClaudeCode()
    cancelled = []
    a.cancel = lambda: cancelled.append(1)
    assert d.apply_extras(a) is True
    assert (a.desktop_tools, a.skill_dir) == (True, str(tmp_path))
    assert cancelled == [1]
    assert d.apply_extras(a) is False            # nothing changed: nothing let go
    d.cfg = cfg_factory(desktopTools=False, omarchySkill=False)
    assert d.apply_extras(a) is True
    assert (a.desktop_tools, a.skill_dir) == (False, None)


# --- the Omarchy skill --------------------------------------------------------

RAW = {"ok": True, "commands": [
    {"route": "omarchy theme set", "group": "theme", "summary": "Apply a theme",
     "args": "<name>", "examples": ["omarchy theme set tokyo-night"],
     "hidden": False, "requires_sudo": False},
    {"route": "omarchy launch browser", "group": "launch",
     "summary": "Launch the default browser", "args": "[url]", "examples": [],
     "hidden": False, "requires_sudo": False},
    {"route": "omarchy update", "group": "update", "summary": "Update everything",
     "hidden": False, "requires_sudo": True},
    {"route": "omarchy theme install", "group": "theme", "summary": "Install a theme",
     "hidden": False, "requires_sudo": False},
    {"route": "omarchy toggle suspend", "group": "toggle", "summary": "x",
     "hidden": False, "requires_sudo": False},
    {"route": "omarchy menu secret", "group": "menu", "summary": "x",
     "hidden": True, "requires_sudo": False},
    "garbage",
]}
BINDS = [
    {"has_description": True, "modmask": 64, "key": "S", "description": "Toggle scratchpad"},
    {"has_description": True, "modmask": 64 | 1, "key": "Return", "description": "Terminal"},
    {"has_description": True, "modmask": 0, "key": "XF86AudioMute", "description": "Mute"},
    {"has_description": False, "modmask": 64, "key": "X", "description": ""},
]


def test_only_everyday_commands_are_kept():
    routes = [c["route"] for c in omarchy_skill.commands(RAW)]
    assert routes == ["omarchy launch browser", "omarchy theme set"]


def test_keybindings_are_written_as_keys():
    assert omarchy_skill.keybindings(BINDS) == [
        ("SUPER + S", "Toggle scratchpad"), ("SUPER + SHIFT + Return", "Terminal")]


def test_the_skill_is_a_plugin_folder_claude_can_load(tmp_path):
    out = omarchy_skill.build(tmp_path, cmds=omarchy_skill.commands(RAW),
                              binds=omarchy_skill.keybindings(BINDS), version="4.5.0")
    assert out["commands"] == 2
    manifest = json.loads((tmp_path / ".claude-plugin/plugin.json").read_text())
    assert manifest["name"] == "agentvoice-omarchy"
    skill = (tmp_path / "skills/omarchy/SKILL.md").read_text()
    head = skill.split("---")[1]
    assert "name: omarchy" in head and "description:" in head
    assert "`omarchy theme set <name>`: Apply a theme" in skill
    assert "togglespecialworkspace scratchpad" in skill
    assert "- SUPER + S: Toggle scratchpad" in skill
    assert "omarchy update" not in skill
    text = omarchy_skill.instructions(tmp_path)
    assert "omarchy theme set <name> : Apply a theme" in text
    assert len(text) <= omarchy_skill.INSTRUCTIONS_MAX


def test_no_commands_leaves_the_old_skill_alone(tmp_path):
    omarchy_skill.build(tmp_path, cmds=omarchy_skill.commands(RAW), binds=[], version="1")
    before = (tmp_path / "skills/omarchy/SKILL.md").read_text()
    assert omarchy_skill.build(tmp_path, cmds=[], binds=[], version="2")["skipped"]
    assert (tmp_path / "skills/omarchy/SKILL.md").read_text() == before


def test_a_new_omarchy_makes_it_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(omarchy_skill, "omarchy_version", lambda: "4.5.0")
    omarchy_skill.build(tmp_path, cmds=omarchy_skill.commands(RAW), binds=[])
    assert not omarchy_skill.stale(tmp_path)
    monkeypatch.setattr(omarchy_skill, "omarchy_version", lambda: "4.6.0")
    assert omarchy_skill.stale(tmp_path)
    assert omarchy_skill.stale(tmp_path / "missing")


def test_install_builds_the_skill():
    assert "omarchy_skill.py" in (ROOT / "install.sh").read_text()


def test_loading_a_deferred_tools_schema_is_not_asked_about(monkeypatch, asked):
    """Every MCP tool is deferred, so ToolSearch comes before each one. It
    runs nothing; the tool it loads is judged when it is called."""
    _at(monkeypatch, "ask")
    assert hook.decide("ToolSearch", {"query": "select:mcp__agentvoice-desktop__notify"})[0] == "allow"
    assert asked == []
