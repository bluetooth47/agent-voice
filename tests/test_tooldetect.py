"""The detector of tools found on this machine (master plan, phase M10).

What it must hold: it finds the MCP servers each CLI would read (Claude
Code's user and local scopes, a project's .mcp.json, enabled plugins, Codex's
config.toml) and the curated CLIs on PATH; it reads only, bounded, and never
starts anything; nothing secret in a definition leaves it; a changed
definition has a new fingerprint; and every tool is off until a switch
approves its fingerprint.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import runtime
import tooldetect

ROOT = Path(__file__).resolve().parent.parent
KEY = b"k" * 32
SECRETS = ("ghp_SECRETTOKEN1234567890", "hunter2-PASSWORD", "sk-LIVEKEY987654321",
           "Bearer-HEADER-VALUE", "QUERYSECRET", "URLPASSWORD")


def roots_in(tmp_path) -> tooldetect.Roots:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".codex").mkdir(parents=True, exist_ok=True)
    return tooldetect.Roots(claude_json=home / ".claude.json", claude_dir=home / ".claude",
                            codex_home=home / ".codex", home=home)


def write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


GITHUB = {"type": "stdio", "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-github", "--token", SECRETS[0]],
          "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": SECRETS[0], "DB_PASSWORD": SECRETS[1]}}
REMOTE = {"type": "http", "url": f"https://user:{SECRETS[5]}@api.example.com/mcp?key={SECRETS[4]}",
          "headers": {"Authorization": SECRETS[3]}}


def machine(tmp_path, project=True):
    """A home with one server in each place a CLI looks, secrets in each."""
    r = roots_in(tmp_path)
    proj = tmp_path / "proj"
    proj.mkdir(exist_ok=True)
    write_json(r.claude_json, {
        "mcpServers": {"github": GITHUB, "remote": REMOTE},
        "projects": {str(proj): {"mcpServers": {"localdb": {"command": "pg-mcp",
                                                            "args": [f"--api-key={SECRETS[2]}"]}}}},
        "numStartups": 12})
    if project:
        write_json(proj / ".mcp.json", {"mcpServers": {"github": {"command": "gh-mcp"},
                                                       "notes": {"command": "notes-mcp"}}})
    (r.codex_home / "config.toml").write_text(
        'model = "x"\n[mcp_servers.node_repl]\ncommand = "/usr/bin/node_repl"\n'
        f'[mcp_servers.node_repl.env]\nTOKEN = "{SECRETS[0]}"\n')
    return r, proj


def by_id(result):
    return {t["id"]: t for t in result["tools"]}


# --- finding ---------------------------------------------------------------------

def test_every_place_a_cli_reads_servers_from_is_found(tmp_path):
    r, proj = machine(tmp_path)
    got = by_id(tooldetect.scan(r, [str(proj)], path="", key=KEY))
    assert set(got) == {"mcp:github", "mcp:remote", "mcp:localdb", "mcp:notes", "mcp:node_repl"}
    scopes = {d["scope"] for d in got["mcp:github"]["defs"]}
    assert scopes == {"user", "project"}          # one id, both definitions
    assert got["mcp:localdb"]["defs"][0]["scope"] == "local"
    assert got["mcp:localdb"]["defs"][0]["project"] == str(proj)
    assert got["mcp:node_repl"]["backends"] == ["codex"]
    assert got["mcp:github"]["backends"] == ["claude"]
    user = next(d for d in got["mcp:github"]["defs"] if d["scope"] == "user")
    assert user["source"] == "~/.claude.json"
    # Claude Code's precedence: the project's before the user's.
    assert [d["scope"] for d in got["mcp:github"]["defs"]] == ["project", "user"]


def test_an_enabled_plugins_servers_are_found_with_its_root_filled_in(tmp_path):
    r = roots_in(tmp_path)
    plug = tmp_path / "plugins" / "cache" / "mkt" / "deploy" / "1.0"
    write_json(plug / ".mcp.json", {"mcpServers": {"api": {
        "command": "${CLAUDE_PLUGIN_ROOT}/bin/server", "args": ["--config", "${CLAUDE_PLUGIN_ROOT}/c.json"]}}})
    write_json(r.claude_dir / "plugins" / "installed_plugins.json", {"version": 2, "plugins": {
        "deploy@mkt": [{"scope": "user", "installPath": str(plug)}],
        "idle@mkt": [{"scope": "user", "installPath": str(plug)}]}})
    write_json(r.claude_dir / "settings.json", {"enabledPlugins": {"deploy@mkt": True, "idle@mkt": False}})
    defs = tooldetect.definitions(r)
    assert [d["name"] for d in defs] == ["plugin:deploy:api"]     # idle is installed, not enabled
    assert defs[0]["spec"]["command"] == f"{plug}/bin/server"
    assert defs[0]["spec"]["args"] == ["--config", f"{plug}/c.json"]
    assert defs[0]["scope"] == "plugin"


def test_claude_config_dir_moves_everything(tmp_path, monkeypatch):
    conf = tmp_path / "conf"
    write_json(conf / ".claude.json", {"mcpServers": {"x": {"command": "y"}}})
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(conf))
    r = tooldetect.default_roots()
    assert r.claude_json == conf / ".claude.json" and r.claude_dir == conf
    assert [d["name"] for d in tooldetect.definitions(r)] == ["x"]


# --- reading only, and bounded ---------------------------------------------------

@pytest.mark.parametrize("text", ["{ not json", "[1, 2", "\x00\x01", "[" * 100000])
def test_a_malformed_config_is_a_problem_not_a_crash(tmp_path, text):
    r = roots_in(tmp_path)
    r.claude_json.write_text(text)
    (r.codex_home / "config.toml").write_text("[[[ not toml")
    result = tooldetect.scan(r, path="", key=KEY)
    assert result["tools"] == []
    assert any("not valid" in p for p in result["problems"])


def test_a_huge_file_is_not_read(tmp_path, monkeypatch):
    r, proj = machine(tmp_path)
    monkeypatch.setattr(tooldetect, "MAX_FILE", 64)
    result = tooldetect.scan(r, [str(proj)], path="", key=KEY)
    ids = set(by_id(result))
    assert "mcp:notes" not in ids and "mcp:node_repl" not in ids
    assert any("larger than" in p for p in result["problems"])


def test_definitions_too_big_or_too_many_are_dropped(tmp_path, monkeypatch):
    r = roots_in(tmp_path)
    servers = {f"s{i}": {"command": "c"} for i in range(30)}
    servers["fat"] = {"command": "c", "args": ["x" * (tooldetect.MAX_SPEC + 1)]}
    servers["bad"] = {"command": 7}
    servers["noargs"] = {"command": "c", "args": "not a list"}
    write_json(r.claude_json, {"mcpServers": servers})
    monkeypatch.setattr(tooldetect, "MAX_SERVERS", 10)
    defs = tooldetect.definitions(r)
    assert len(defs) == 10
    assert not {"fat", "bad", "noargs"} & {d["name"] for d in defs}


def test_a_projects_mcp_json_is_not_followed_through_a_link(tmp_path):
    """A project folder is the agent's to write; a link there must not lead
    the scan elsewhere (the hook asks about writing .mcp.json, but a link
    is made as easily as a file)."""
    r, proj = machine(tmp_path, project=False)
    target = write_json(tmp_path / "elsewhere.json", {"mcpServers": {"sneaky": {"command": "x"}}})
    (proj / ".mcp.json").symlink_to(target)
    result = tooldetect.scan(r, [str(proj)], path="", key=KEY)
    assert "mcp:sneaky" not in by_id(result)
    assert any("a link" in p for p in result["problems"])


def test_the_users_own_files_may_be_links(tmp_path):
    """~/.claude.json kept in a dotfiles repository is a link, and is the
    user's own file: followed."""
    r = roots_in(tmp_path)
    real = write_json(tmp_path / "dotfiles" / "claude.json", {"mcpServers": {"kept": {"command": "x"}}})
    r.claude_json.symlink_to(real)
    assert "mcp:kept" in by_id(tooldetect.scan(r, path="", key=KEY))


def test_a_special_file_is_not_read(tmp_path):
    r, proj = machine(tmp_path, project=False)
    os.mkfifo(proj / ".mcp.json")
    result = tooldetect.scan(r, [str(proj)], path="", key=KEY)      # would block on a read
    assert any("not a regular file" in p for p in result["problems"])


def test_a_scan_starts_nothing(tmp_path, monkeypatch):
    """Detection reads files; it never asks a server or a CLI anything."""
    r, proj = machine(tmp_path)
    exe = tmp_path / "bin" / "gh"
    exe.parent.mkdir()
    exe.write_text("#!/bin/sh\ntouch " + str(tmp_path / "RAN") + "\n")
    exe.chmod(0o755)

    def refuse(*a, **k):
        raise AssertionError("a scan started a process")
    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, refuse)
    monkeypatch.setattr(os, "system", refuse)
    monkeypatch.setattr(os, "execv", refuse)
    for name in ("posix_spawn", "posix_spawnp", "fork"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, refuse)
    result = tooldetect.scan(r, [str(proj)], path=str(exe.parent), key=KEY)
    assert "cli:gh" in by_id(result)
    assert not (tmp_path / "RAN").exists()


# --- nothing secret leaves it ---------------------------------------------------

def test_no_secret_value_is_in_what_a_scan_returns(tmp_path):
    r, proj = machine(tmp_path)
    result = tooldetect.scan(r, [str(proj)], path="", key=KEY)
    text = json.dumps(result)
    for secret in SECRETS:
        assert secret not in text, secret
    github = by_id(result)["mcp:github"]["defs"]
    user = next(d for d in github if d["scope"] == "user")
    # The names are there (the confirm says what it is given), the values not.
    assert "GITHUB_PERSONAL_ACCESS_TOKEN" in user["command"] and "--token •••" in user["command"]
    remote = by_id(result)["mcp:remote"]["defs"][0]["command"]
    assert remote == "connects to https://api.example.com/mcp?••• · headers: Authorization"
    assert "--api-key=•••" in by_id(result)["mcp:localdb"]["defs"][0]["command"]


@pytest.mark.parametrize("args,shown", [
    (["--token", "abc"], "--token •••"),
    (["--api-key=abc"], "--api-key=•••"),
    (["API_TOKEN=abc"], "API_TOKEN=•••"),
    (["github_pat_ABCDEFGHIJKLMNOP"], "•••"),
    (["--port", "8080", "--verbose"], "--port 8080 --verbose"),
    # Codex review of M10: a header or environment value, whatever it is called.
    (["--header", "Authorization: Bearer PRIVATE"], "--header •••"),
    (["-H", "X-Custom: PRIVATE"], "-H •••"),
    (["-e", "ANYTHING=PRIVATE"], "-e •••"),
    (["--env=FOO=PRIVATE"], "--env=•••"),
    (["https://u:PRIVATE@h.example/x?k=PRIVATE"], "https://h.example/x?•••"),
    (["Qx7dPRIVATE9a8b7c6d5e4f3"], "•••"),
])
def test_arguments_that_look_like_keys_are_masked(args, shown):
    assert tooldetect.shown_command({"command": "srv", "args": args}) == "srv " + shown


def test_the_cache_holds_nothing_secret_and_is_private(tmp_path, monkeypatch, cfg_factory):
    r, proj = machine(tmp_path)
    monkeypatch.setattr(tooldetect, "default_roots", lambda: r)
    cfg = cfg_factory(projectDir=str(proj))
    tooldetect.scan_cached(cfg, force=True)
    path = tooldetect.cache_path()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    text = path.read_text()
    for secret in SECRETS:
        assert secret not in text


def test_the_cli_prints_no_secret_and_writes_nothing_in_the_tree(tmp_path):
    r, proj = machine(tmp_path)
    env = {**os.environ, "HOME": str(r.home), "XDG_RUNTIME_DIR": str(tmp_path / "run"),
           "XDG_DATA_HOME": str(tmp_path / "data"), "XDG_CONFIG_HOME": str(tmp_path / "config"),
           "XDG_STATE_HOME": str(tmp_path / "state"), "PYTHONDONTWRITEBYTECODE": "1",
           "AGENTVOICE_PYTHON": sys.executable}
    env.pop("CLAUDE_CONFIG_DIR", None)
    env.pop("CODEX_HOME", None)
    before = subprocess.run(["git", "status", "--porcelain", "--ignored"], cwd=ROOT,
                            capture_output=True, text=True).stdout
    for args in (["scan"], ["scan", "--json"], ["scan", "--json", "--rescan"]):
        p = subprocess.run([str(ROOT / "bin" / "agentvoice"), "tools", *args], capture_output=True,
                           text=True, env=env, timeout=60)
        assert p.returncode == 0, p.stderr
        for secret in SECRETS:
            assert secret not in p.stdout + p.stderr
    assert "github" in p.stdout and "node_repl" in p.stdout
    bad = subprocess.run([str(ROOT / "bin" / "agentvoice"), "tools", "frob"], capture_output=True,
                         text=True, env=env, timeout=60)
    assert bad.returncode == 2 and "usage" in bad.stderr
    after = subprocess.run(["git", "status", "--porcelain", "--ignored"], cwd=ROOT,
                           capture_output=True, text=True).stdout
    assert after == before


# --- fingerprints ---------------------------------------------------------------

def test_a_changed_definition_has_a_new_fingerprint(tmp_path):
    r, proj = machine(tmp_path)
    first = by_id(tooldetect.scan(r, [str(proj)], path="", key=KEY))
    again = by_id(tooldetect.scan(r, [str(proj)], path="", key=KEY))
    assert {k: v["fp"] for k, v in first.items()} == {k: v["fp"] for k, v in again.items()}
    data = json.loads(r.claude_json.read_text())
    data["mcpServers"]["github"]["env"]["DB_PASSWORD"] = "rotated"     # a value only
    data["numStartups"] = 13                                           # not a definition
    r.claude_json.write_text(json.dumps(data))
    after = by_id(tooldetect.scan(r, [str(proj)], path="", key=KEY))
    assert after["mcp:github"]["fp"] != first["mcp:github"]["fp"]
    assert after["mcp:remote"]["fp"] == first["mcp:remote"]["fp"]
    # A project's copy appearing is a change to that tool too.
    (proj / ".mcp.json").write_text(json.dumps({"mcpServers": {"remote": {"command": "evil"}}}))
    later = by_id(tooldetect.scan(r, [str(proj)], path="", key=KEY))
    assert later["mcp:remote"]["fp"] != first["mcp:remote"]["fp"]


def test_without_a_key_nothing_has_a_fingerprint(tmp_path):
    r, proj = machine(tmp_path)
    result = tooldetect.scan(r, [str(proj)], path="", key=b"")
    assert all(t["fp"] == "" for t in result["tools"]) and result["keyed"] is False


def test_the_key_is_made_once_private_and_refused_when_not(tmp_path, monkeypatch):
    path = tmp_path / "data" / "tool-key"
    monkeypatch.setattr(tooldetect, "_key_path", lambda: path)
    k = tooldetect.tool_key()
    assert len(k) == 32 and tooldetect.tool_key() == k
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    path.chmod(0o644)
    assert tooldetect.tool_key() is None          # readable by others: not trusted
    path.chmod(0o600)
    path.write_bytes(b"short")
    assert tooldetect.tool_key() is None


# --- CLIs ------------------------------------------------------------------------

def make_exe(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / name
    p.write_text("#!/bin/sh\nexit 0\n")
    p.chmod(0o755)
    return p


def test_curated_clis_on_path_are_found_and_others_are_not_listed(tmp_path):
    r = roots_in(tmp_path)
    bin_ = tmp_path / "bin"
    make_exe(bin_, "gh")
    make_exe(bin_, "git")                     # not curated: nothing to switch
    got = by_id(tooldetect.scan(r, path=str(bin_), key=KEY))
    assert set(got) == {"cli:gh"}
    assert got["cli:gh"]["label"] == "GitHub CLI" and got["cli:gh"]["found"]
    assert got["cli:gh"]["fp"]


def test_a_cli_added_by_name_is_listed_found_or_not(tmp_path):
    r = roots_in(tmp_path)
    bin_ = tmp_path / "bin"
    make_exe(bin_, "rclone2")
    got = by_id(tooldetect.scan(r, extra_clis=["rclone2", "nowhere", "../evil", "a b"],
                                path=str(bin_), key=KEY))
    assert set(got) == {"cli:rclone2", "cli:nowhere"}
    assert got["cli:rclone2"]["found"] and got["cli:rclone2"]["added"]
    assert not got["cli:nowhere"]["found"] and got["cli:nowhere"]["fp"] == ""


def test_a_cli_moved_on_path_is_a_changed_definition(tmp_path):
    r = roots_in(tmp_path)
    make_exe(tmp_path / "a", "gh")
    make_exe(tmp_path / "b", "gh")
    one = by_id(tooldetect.scan(r, path=str(tmp_path / "a"), key=KEY))["cli:gh"]["fp"]
    two = by_id(tooldetect.scan(r, path=str(tmp_path / "b"), key=KEY))["cli:gh"]["fp"]
    assert one and two and one != two


# --- off until switched on -------------------------------------------------------

def rows_for(cfg, scanned, agent="", program="claude", level="ask", project=""):
    return {r["id"]: r for r in tooldetect.rows(cfg, agent, program, level, project, scanned)}


@pytest.fixture
def scanned(tmp_path):
    r, proj = machine(tmp_path)
    make_exe(tmp_path / "bin", "gh")
    return tooldetect.scan(r, [str(proj)], path=str(tmp_path / "bin"), key=KEY), proj, r


def test_everything_found_is_off_by_default(cfg_factory, scanned):
    result, proj, _ = scanned
    for program in ("claude", "codex", "gemini"):
        got = rows_for(cfg_factory(), result, program=program, project=str(proj))
        assert got and not any(r["on"] for r in got.values()), program
    assert runtime.DEFAULTS["sharedTools"] == {}
    manifest = json.loads((ROOT / "manifest.json").read_text())["barWidget"]["defaults"]
    assert manifest["sharedTools"] == {}


def test_the_inherit_chain(cfg_factory, scanned):
    result, proj, _ = scanned
    fp = {t["id"]: t["fp"] for t in result["tools"]}
    on = lambda i: "on:" + fp[i]
    cfg = cfg_factory(sharedTools={"mcp:github": on("mcp:github"), "cli:gh": on("cli:gh")},
                      mainTools={"cli:gh": "off", "mcp:remote": on("mcp:remote")})
    got = rows_for(cfg, result, project=str(proj))
    assert got["mcp:github"]["on"] and got["mcp:github"]["choice"] == "inherit"
    assert not got["cli:gh"]["on"] and got["cli:gh"]["choice"] == "off"     # a personal off wins
    assert got["mcp:remote"]["on"] and got["mcp:remote"]["choice"] == "on"   # its own on
    assert not got["mcp:notes"]["on"]                                        # nobody said
    # An extra agent follows the same chain from its own entry.
    agents = [{"id": "sora", "name": "sora", "agent": "claude", "tools": {"mcp:notes": on("mcp:notes")}}]
    got = rows_for(cfg_factory(voiceAgents=agents, sharedTools={"cli:gh": on("cli:gh")}),
                   result, agent="sora", project=str(proj))
    assert got["mcp:notes"]["on"] and got["cli:gh"]["on"] and not got["mcp:github"]["on"]


@pytest.mark.parametrize("value", ["on", True, 1, "on:xyz", "ON:" + "a" * 32, None, {"on": 1}])
def test_a_switch_that_cannot_be_read_is_off(cfg_factory, scanned, value):
    result, proj, _ = scanned
    got = rows_for(cfg_factory(mainTools={"mcp:github": value}, sharedTools={"mcp:github": value}),
                   result, project=str(proj))
    assert not got["mcp:github"]["on"]
    assert runtime.detected_choices({"mcp:github": value}) == {"mcp:github": "off"}


def test_unreadable_settings_switch_nothing_on(cfg_factory, scanned, monkeypatch):
    result, proj, _ = scanned
    fp = {t["id"]: t["fp"] for t in result["tools"]}
    cfg = cfg_factory(sharedTools={"mcp:github": "on:" + fp["mcp:github"]})
    monkeypatch.setattr(type(cfg), "settings_readable", lambda self: False)
    assert not any(r["on"] for r in rows_for(cfg, result, project=str(proj)).values())
    assert tooldetect.switched_on_keys(cfg, "") == set()


def test_an_agent_the_settings_do_not_have_gets_nothing(cfg_factory, scanned):
    result, proj, _ = scanned
    fp = {t["id"]: t["fp"] for t in result["tools"]}
    cfg = cfg_factory(sharedTools={"mcp:github": "on:" + fp["mcp:github"]})
    assert not any(r["on"] for r in rows_for(cfg, result, agent="ghost").values())


def test_a_changed_fingerprint_turns_it_off_and_says_so(cfg_factory, scanned):
    result, proj, r = scanned
    old = {t["id"]: t["fp"] for t in result["tools"]}["mcp:github"]
    cfg = cfg_factory(mainTools={"mcp:github": "on:" + old})
    assert rows_for(cfg, result, project=str(proj))["mcp:github"]["on"]
    data = json.loads(r.claude_json.read_text())
    data["mcpServers"]["github"]["args"].append("--write-everything")
    r.claude_json.write_text(json.dumps(data))
    rescanned = tooldetect.scan(r, [str(proj)], path="", key=KEY)
    row = rows_for(cfg, rescanned, project=str(proj))["mcp:github"]
    assert not row["on"] and row["changed"] and row["choice"] == "on"


def test_what_a_program_can_use(cfg_factory, scanned):
    result, proj, _ = scanned
    claude = rows_for(cfg_factory(), result, program="claude", project=str(proj))
    codex = rows_for(cfg_factory(), result, program="codex", project=str(proj))
    endpoint = rows_for(cfg_factory(), result, program="endpoint")
    elsewhere = rows_for(cfg_factory(), result, program="claude", project="/somewhere/else")
    assert claude["mcp:github"]["can"] and not claude["mcp:node_repl"]["can"]
    assert codex["mcp:node_repl"]["can"] and not codex["mcp:github"]["can"]
    assert "Claude Code's settings" in codex["mcp:github"]["why_not"]
    assert not endpoint["cli:gh"]["can"] and not endpoint["mcp:github"]["can"]
    assert not elsewhere["mcp:localdb"]["can"] and "another project" in elsewhere["mcp:localdb"]["why_not"]
    assert claude["cli:gh"]["can"] and codex["cli:gh"]["can"]


@pytest.mark.parametrize("program,level,kind,want", [
    ("claude", "ask", "mcp", "Asks before each call."),
    ("claude", "trusted", "mcp", "⚠ Runs without asking at Trusted."),
    ("codex", "ask", "mcp", "Codex refuses its calls below Trusted"),
    ("codex", "trusted", "mcp", "⚠ Runs without asking at Trusted."),
    ("claude", "edits", "cli", "Asks before each command."),
    ("codex", "edits", "cli", "Runs read-only below Trusted"),
])
def test_whether_it_asks_follows_the_recordings(program, level, kind, want):
    assert tooldetect._asks(kind, program, level).startswith(want)


# --- delivery --------------------------------------------------------------------

def test_claude_gets_the_approved_definition_its_own_cli_would_pick(cfg_factory, scanned, monkeypatch):
    result, proj, r = scanned
    monkeypatch.setattr(tooldetect, "default_roots", lambda: r)
    defs = tooldetect.definitions(r, [str(proj)])
    fp = {t["id"]: t["fp"] for t in result["tools"]}
    cfg = cfg_factory(mainTools={"mcp:github": "on:" + fp["mcp:github"], "mcp:remote": "off",
                                 "cli:gh": "on:" + fp["cli:gh"]})
    got = tooldetect.delivery(cfg, "", "claude", str(proj), result, defs)
    # The project's github beats the user's, as in Claude Code.
    assert got["servers"] == {"github": {"command": "gh-mcp"}}
    assert got["clis_on"] == ["gh"] and got["clis_off"] == []
    # Elsewhere, the user's (with its secrets: this goes to a 0600 file).
    away = tooldetect.delivery(cfg, "", "claude", "", result, defs)
    assert away["servers"]["github"]["env"]["DB_PASSWORD"] == SECRETS[1]


def test_codex_is_told_to_leave_off_every_config_server_not_approved(cfg_factory, scanned):
    result, proj, r = scanned
    defs = tooldetect.definitions(r, [str(proj)])
    fp = {t["id"]: t["fp"] for t in result["tools"]}
    off = tooldetect.delivery(cfg_factory(), "", "codex", "", result, defs)
    assert off["codex_off"] == ["node_repl"] and off["servers"] == {}
    on = tooldetect.delivery(cfg_factory(mainTools={"mcp:node_repl": "on:" + fp["mcp:node_repl"]}),
                             "", "codex", "", result, defs)
    assert on["codex_off"] == []


def test_a_name_agent_voice_uses_is_never_delivered(cfg_factory, tmp_path):
    r = roots_in(tmp_path)
    write_json(r.claude_json, {"mcpServers": {"agentvoice-crew": {"command": "impostor"}}})
    result = tooldetect.scan(r, path="", key=KEY)
    fp = result["tools"][0]["fp"]
    cfg = cfg_factory(mainTools={"mcp:agentvoice-crew": "on:" + fp})
    row = rows_for(cfg, result)["mcp:agentvoice-crew"]
    assert not row["can"] and not row["on"]
    got = tooldetect.delivery(cfg, "", "claude", "", result, tooldetect.definitions(r))
    assert got["servers"] == {}


# --- the cache -------------------------------------------------------------------

def test_the_cache_reads_nothing_until_something_moves(tmp_path, monkeypatch, cfg_factory):
    r, proj = machine(tmp_path)
    monkeypatch.setattr(tooldetect, "default_roots", lambda: r)
    cfg = cfg_factory(projectDir=str(proj))
    first = tooldetect.scan_cached(cfg, force=True)
    reads = []
    real = tooldetect._Reader.raw
    monkeypatch.setattr(tooldetect._Reader, "raw",
                        lambda self, *a, **k: reads.append(a[0]) or real(self, *a, **k))
    assert tooldetect.scan_cached(cfg) == first and reads == []
    tooldetect._MEMO.clear()                      # another process: the file cache
    assert tooldetect.scan_cached(cfg) == first and reads == []
    (proj / ".mcp.json").write_text(json.dumps({"mcpServers": {"new": {"command": "n"}}}))
    after = tooldetect.scan_cached(cfg)
    assert reads and "mcp:new" in by_id(after)


def test_a_cli_added_by_name_is_looked_for(tmp_path, monkeypatch, cfg_factory):
    r = roots_in(tmp_path)
    make_exe(tmp_path / "bin", "mytool")
    monkeypatch.setattr(tooldetect, "default_roots", lambda: r)
    monkeypatch.setattr(tooldetect, "default_path", lambda: str(tmp_path / "bin"))
    assert "cli:mytool" not in by_id(tooldetect.scan_cached(cfg_factory()))
    got = by_id(tooldetect.scan_cached(cfg_factory(sharedTools={"cli:mytool": "off"})))
    assert got["cli:mytool"]["found"]


# --- the notice ------------------------------------------------------------------

def test_the_notice_lists_what_nobody_switched_and_goes_when_dismissed(cfg_factory, scanned,
                                                                       monkeypatch, tmp_path):
    result, proj, _ = scanned
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    fp = {t["id"]: t["fp"] for t in result["tools"]}
    cfg = cfg_factory(sharedTools={"cli:gh": "off"}, mainTools={"mcp:remote": "on:" + fp["mcp:remote"]})
    the_rows = tooldetect.rows(cfg, "", "claude", "ask", str(proj), result)
    listed = {n["id"] for n in tooldetect.notice("main", the_rows)}
    # gh: switched off for everyone; remote: on; node_repl: Codex's, not Claude's.
    assert listed == {"mcp:github", "mcp:localdb", "mcp:notes"}
    tooldetect.dismiss("", sorted(listed))
    assert tooldetect.notice("main", the_rows) == []
    state = tmp_path / "state" / "agentvoice" / "tools-notice.json"
    assert stat.S_IMODE(state.stat().st_mode) == 0o600


def test_a_codex_server_whose_name_cannot_be_switched_off_says_it_loads_anyway(cfg_factory, tmp_path):
    """Codex's -c takes a dotted path; a name with a dot in it cannot be
    named there, so Codex starts it whatever the switch says. The row must
    not offer a switch that does nothing (CLAUDE.md: a control that does
    nothing must say why)."""
    r = roots_in(tmp_path)
    (r.codex_home / "config.toml").write_text('[mcp_servers."my.server"]\ncommand = "x"\n')
    result = tooldetect.scan(r, path="", key=KEY)
    row = rows_for(cfg_factory(), result, program="codex")["mcp:my.server"]
    assert not row["can"] and "whatever this says" in row["why_not"]
    assert tooldetect.delivery(cfg_factory(), "", "codex", "", result,
                               tooldetect.definitions(r))["codex_off"] == []


def test_a_cli_behind_a_link_keeps_its_place_across_upgrades(tmp_path):
    """A version manager's shim is a link into a versioned folder; an
    upgrade moves the target, not the place on PATH, and is no reason to
    ask again."""
    r = roots_in(tmp_path)
    v1 = make_exe(tmp_path / "installs" / "1.0", "gh")
    v2 = make_exe(tmp_path / "installs" / "2.0", "gh")
    shims = tmp_path / "shims"
    shims.mkdir()
    (shims / "gh").symlink_to(v1)
    one = by_id(tooldetect.scan(r, path=str(shims), key=KEY))["cli:gh"]["fp"]
    (shims / "gh").unlink()
    (shims / "gh").symlink_to(v2)
    assert by_id(tooldetect.scan(r, path=str(shims), key=KEY))["cli:gh"]["fp"] == one


def test_delivery_never_hands_over_a_name_of_ours_even_if_a_row_said_it_could(
        cfg_factory, tmp_path, monkeypatch):
    """Two layers: the row says it cannot be used, and delivery refuses the
    name on its own as well (the adapter keeps ours a third time)."""
    r = roots_in(tmp_path)
    write_json(r.claude_json, {"mcpServers": {"agentvoice-crew": {"command": "impostor"}}})
    result = tooldetect.scan(r, path="", key=KEY)
    cfg = cfg_factory(mainTools={"mcp:agentvoice-crew": "on:" + result["tools"][0]["fp"]})
    monkeypatch.setattr(tooldetect, "_usable", lambda *a, **k: (True, ""))
    got = tooldetect.delivery(cfg, "", "claude", "", result, tooldetect.definitions(r))
    assert got["servers"] == {}


def test_a_plugin_cannot_point_outside_itself(tmp_path):
    """Codex review of M10: "../servers.json" passed the old check, and a
    linked .claude-plugin folder redirected the manifest read."""
    r = roots_in(tmp_path)
    plug = tmp_path / "plug"
    write_json(tmp_path / "servers.json", {"mcpServers": {"outside": {"command": "x"}}})
    write_json(plug / ".claude-plugin" / "plugin.json", {"name": "p", "mcpServers": "../servers.json"})
    write_json(r.claude_dir / "plugins" / "installed_plugins.json",
               {"version": 2, "plugins": {"p@m": [{"installPath": str(plug)}]}})
    write_json(r.claude_dir / "settings.json", {"enabledPlugins": {"p@m": True}})
    first = tooldetect._Reader()
    assert tooldetect.definitions(r, reader=first) == []
    assert not any(".." in t for t in first.tried), first.tried      # never even tried
    # A plain name beside the manifest is fine...
    write_json(plug / "servers.json", {"mcpServers": {"inside": {"command": "x"}}})
    write_json(plug / ".claude-plugin" / "plugin.json", {"name": "p", "mcpServers": "./servers.json"})
    assert [d["name"] for d in tooldetect.definitions(r)] == ["plugin:p:inside"]
    # ...but not through a linked folder.
    elsewhere = tmp_path / "elsewhere"
    write_json(elsewhere / "plugin.json", {"name": "p", "mcpServers": {"sneaky": {"command": "x"}}})
    import shutil as _sh
    _sh.rmtree(plug / ".claude-plugin")
    (plug / ".claude-plugin").symlink_to(elsewhere)
    (plug / "servers.json").unlink()
    reader = tooldetect._Reader()
    assert tooldetect.definitions(r, reader=reader) == []
    assert any("a link" in p for p in reader.problems)


def test_an_oversized_tools_map_switches_nothing_on(cfg_factory, scanned):
    """Codex review of M10: read only so far, an explicit off past the cut
    was lost and the switch for every agent turned the tool on."""
    result, proj, _ = scanned
    fp = {t["id"]: t["fp"] for t in result["tools"]}
    big = {f"cli:t{i}": "off" for i in range(runtime.MAX_DETECTED)}
    big["mcp:github"] = "off"
    cfg = cfg_factory(mainTools=big, sharedTools={"mcp:github": "on:" + fp["mcp:github"]})
    assert runtime.detected_choices(big) is None
    assert not rows_for(cfg, result, project=str(proj))["mcp:github"]["on"]
    agents = [{"id": "sora", "name": "sora", "agent": "claude", "tools": big}]
    cfg = cfg_factory(voiceAgents=agents, sharedTools={"mcp:github": "on:" + fp["mcp:github"]})
    assert not rows_for(cfg, result, agent="sora", project=str(proj))["mcp:github"]["on"]
    # sharedTools oversized: nothing for every agent.
    shared = {f"cli:t{i}": "off" for i in range(runtime.MAX_DETECTED)}
    shared["mcp:github"] = "on:" + fp["mcp:github"]
    assert not rows_for(cfg_factory(sharedTools=shared), result, project=str(proj))["mcp:github"]["on"]


def test_two_servers_whose_safe_names_clash_are_not_given(cfg_factory, tmp_path):
    r = roots_in(tmp_path)
    write_json(r.claude_json, {"mcpServers": {"a__b": {"command": "x"}, "a_b": {"command": "y"}}})
    result = tooldetect.scan(r, path="", key=KEY)
    rows = rows_for(cfg_factory(), result)
    assert not rows["mcp:a__b"]["can"] and not rows["mcp:a_b"]["can"]
    assert "comes out the same" in rows["mcp:a_b"]["why_not"]


@pytest.mark.parametrize("ref,ok", [("servers.json", True), ("./mcp.json", True), ("../servers.json", False),
                                    ("/etc/x.json", False), ("a/b.json", False), ("x.txt", False),
                                    (".hidden.json", False)])
def test_a_plugin_manifest_may_name_only_a_file_beside_it(ref, ok):
    """The first of two layers (the open beneath the plugin's root is the
    second): checked on its own, so neither stands in for the other."""
    assert bool(tooldetect._PLUGIN_REF.fullmatch(ref) and ".." not in ref) is ok
