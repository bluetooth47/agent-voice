"""Phase M11: skills on this machine, lanes, and a real switch per skill.

What the CLIs find by themselves (~/.claude/skills, claude.ai's synced
skills, a plugin's, ~/.codex/skills, ~/.agents/skills) is read, never run;
each agent's `skillsOff` switches a skill off where its CLI looks (Claude
Code's skillOverrides, Codex's skills.config), and out of the plugin folder
and the index Agent Voice builds; an unreadable list closes; and assigning a
skill from outside is a checked copy that leaves the original as it was.
The CLI behaviour all of this rests on is recorded in
tests/fixtures/skills/spike-m11.json and replayed here.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import agentfs
import audit
import omarchy_skill
import paths
import permission_hook as hook
import skillscan

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = json.loads((ROOT / "tests/fixtures/skills/spike-m11.json").read_text())
GOOD = "---\nname: {n}\ndescription: {d}\n---\n\n{body}\n"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


@pytest.fixture(autouse=True)
def data(tmp_path, monkeypatch):
    d = tmp_path / "data"
    monkeypatch.setattr(paths, "DATA_DIR", d)
    monkeypatch.setattr(paths, "AGENTS_DIR", d / "agents")
    monkeypatch.setattr(paths, "COMMUNAL_DIR", d / "communal")
    monkeypatch.setattr(hook, "AGENTS_DIR", d / "agents")
    monkeypatch.setattr(hook, "COMMUNAL_DIR", d / "communal")
    monkeypatch.setattr(hook, "DATA_DIR", d)
    agentfs._LAST_GOOD.clear()
    for t in ("main", "sora"):
        (d / "agents" / t).mkdir(parents=True)
    (d / "communal").mkdir(parents=True)
    return d


def write_skill(folder: Path, name: str, desc="Does a thing. Use when asked.", text=None, extra=None):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(text if text is not None else GOOD.format(n=name, d=desc, body="Steps."))
    for rel, content in (extra or {}).items():
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_text(content)
    return folder


def own(target, name, **kw):
    base = paths.COMMUNAL_DIR if target == "communal" else paths.AGENTS_DIR / target
    return write_skill(base / "skills" / name, name, **kw)


def claude_home() -> Path:
    return Path(os.environ["CLAUDE_CONFIG_DIR"])


def codex_home() -> Path:
    return Path(os.environ["CODEX_HOME"])


def shared_home() -> Path:
    return skillscan.agents_dir(skillscan.roots())


def machine(tmp_path) -> dict:
    """A synthetic machine: two user skills for Claude (one a link, as
    Omarchy installs them), a synced one, a plugin's, one for Codex and one
    in ~/.agents/skills."""
    ext = tmp_path / "usr-share" / "omarchy-app"
    write_skill(ext, "omarchy-app", desc="Build an Omarchy app.")
    (claude_home() / "skills").mkdir(parents=True, exist_ok=True)
    os.symlink(ext, claude_home() / "skills" / "omarchy-app")
    write_skill(claude_home() / "skills" / "weekly", "weekly", desc="Write the weekly report.",
                extra={"run.sh": "echo hi\n"})
    write_skill(claude_home() / "skills" / "synced" / "bucket-1" / "docx", "docx", desc="Word files.")
    plug = tmp_path / "plugins" / "tidy"
    write_skill(plug / "skills" / "format", "format", desc="Format code.")
    (claude_home() / "settings.json").write_text(json.dumps({"enabledPlugins": {"tidy@market": True}}))
    (claude_home() / "plugins").mkdir(exist_ok=True)
    (claude_home() / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"plugins": {"tidy@market": [{"installPath": str(plug)}]}}))
    write_skill(codex_home() / "skills" / "deploy", "deploy", desc="Deploy the site.")
    (codex_home() / "skills" / ".system" / "imagegen").mkdir(parents=True)
    write_skill(shared_home() / "crash", "crash", desc="Diagnose a crash.")
    return {"ext": ext, "plug": plug}


def by_id(result) -> dict:
    return {s["id"]: s for s in result["skills"]}


def digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
            h.update(oct(p.stat().st_mode).encode())
    return h.hexdigest()


# --- the setting -----------------------------------------------------------------

@pytest.mark.parametrize("raw, want", [
    (None, []), ([], []), (["weekly"], ["weekly"]), (["a", "a", "tidy:format"], ["a", "tidy:format"]),
    ("weekly", None), ({"weekly": True}, None), (["ok", 5], None), (["../x"], None),
    (["a b"], None), (["x"] * 257, None), (["-bad"], None)])
def test_skills_off_is_a_list_of_names_or_unreadable(raw, want):
    from runtime import skills_off_choice
    assert skills_off_choice(raw) == want


def test_skills_off_for_reads_each_agent_fresh(cfg_factory):
    cfg = cfg_factory(mainSkillsOff=["weekly"], voiceAgents=[
        {"name": "sora", "id": "sora", "skillsOff": ["deploy"]},
        {"name": "hazel", "id": "hazel", "skillsOff": "nope"},
        {"name": "ivy", "id": "ivy"}])
    assert cfg.skills_off_for("") == frozenset({"weekly"})
    assert cfg.skills_off_for("main") == frozenset({"weekly"})
    assert cfg.skills_off_for("sora") == frozenset({"deploy"})
    assert cfg.skills_off_for("hazel") is None          # unreadable
    assert cfg.skills_off_for("ivy") == frozenset()      # missing: today's behaviour
    assert cfg.skills_off_for("nobody") is None          # nobody's decision


def test_unreadable_settings_switch_every_shared_skill_off(cfg_factory, monkeypatch):
    cfg = cfg_factory()
    monkeypatch.setattr(type(cfg), "settings_readable", lambda self: False)
    assert cfg.skills_off_for("") is None


def test_the_default_is_a_shipped_empty_list():
    from runtime import DEFAULTS
    manifest = json.loads((ROOT / "manifest.json").read_text())
    assert DEFAULTS["mainSkillsOff"] == [] == manifest["barWidget"]["defaults"]["mainSkillsOff"]


# --- skill_set honours the switch ------------------------------------------------------

def test_an_off_skill_is_not_delivered_wherever_it_lives():
    own("main", "mine")
    own("communal", "shared")
    own("communal", "other")
    got = {s["name"]: s for s in agentfs.skill_set(agentfs.skills("main"), agentfs.skills("communal"),
                                                     frozenset({"mine", "shared"}))}
    assert got["mine"]["delivered"] is False and got["mine"]["on"] is False
    assert got["shared"]["delivered"] is False and "switched off" in got["shared"]["why"]
    assert got["other"]["delivered"] is True and got["other"]["on"] is True


def test_an_unreadable_list_keeps_its_own_and_drops_every_communal_one():
    own("main", "mine")
    own("communal", "shared")
    got = {s["name"]: s for s in agentfs.skill_set(agentfs.skills("main"), agentfs.skills("communal"), None)}
    assert got["mine"]["delivered"] is True
    assert got["shared"]["delivered"] is False and "cannot be read" in got["shared"]["why"]
    assert got["shared"]["on"] is False


def test_an_off_skill_is_absent_from_the_plugin_folder_and_the_index(tmp_path):
    own("sora", "mine")
    own("communal", "shared")
    folder = agentfs.plugin_dir("sora", None, frozenset({"shared"}))
    names = sorted(p.name for p in (Path(folder) / "skills").iterdir())
    assert names == ["mine"]
    texts = agentfs.snapshot()[1]
    index = agentfs.parts_from(texts, "sora", "Sora", [], frozenset({"shared"}))["skills"]
    assert "mine" in index and "shared" not in index
    both = agentfs.parts_from(texts, "sora", "Sora", [], frozenset())["skills"]
    assert "shared" in both
    # Unreadable: the communal one is out of both, its own stays.
    folder = agentfs.plugin_dir("sora", None, None)
    assert sorted(p.name for p in (Path(folder) / "skills").iterdir()) == ["mine"]
    assert "shared" not in agentfs.parts_from(texts, "sora", "Sora", [], None)["skills"]


def test_switching_every_skill_off_leaves_the_omarchy_folder_as_before(tmp_path):
    root = tmp_path / "omarchy-skill"
    (root / "skills/omarchy").mkdir(parents=True)
    (root / "skills/omarchy/SKILL.md").write_text("---\nname: omarchy\ndescription: x\n---\nX\n")
    own("sora", "mine")
    assert agentfs.plugin_dir("sora", str(root), frozenset({"mine"})) == str(root)


# --- the scan ------------------------------------------------------------------------

def test_the_scan_finds_every_source_and_says_where_each_is(tmp_path):
    machine(tmp_path)
    got = by_id(skillscan.scan())
    assert set(got) == {"claude-user:omarchy-app", "claude-user:weekly", "claude-synced:docx",
                        "claude-plugin:tidy:format", "codex-user:deploy", "agents:crash"}
    assert got["claude-user:omarchy-app"]["linked"] is True
    assert got["claude-user:omarchy-app"]["description"] == "Build an Omarchy app."
    assert got["claude-user:weekly"]["files"] == 2 and got["claude-user:weekly"]["size"] > 0
    assert got["claude-plugin:tidy:format"]["name"] == "tidy:format"
    assert got["claude-plugin:tidy:format"]["source_label"] == "the tidy plugin"
    assert got["codex-user:deploy"]["family"] == "codex" and got["agents:crash"]["family"] == "codex"
    assert all(s["copy_problem"] == "" for s in got.values())
    # Codex's own (.system) and the claude.ai bucket folder are not skills here.
    assert not any("imagegen" in i or i.endswith(":synced") for i in got)


def test_the_scan_starts_no_process(tmp_path, monkeypatch):
    machine(tmp_path)

    def refuse(*a, **k):
        raise AssertionError("a skill scan started a process")
    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, refuse)
    monkeypatch.setattr(os, "system", refuse)
    monkeypatch.setattr(os, "execv", refuse)
    for name in ("posix_spawn", "posix_spawnp", "fork"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, refuse)
    assert len(skillscan.scan()["skills"]) == 6


@pytest.mark.parametrize("text, words", [
    ("no front matter\n", "no front matter"),
    ("---\nname: bad\ndescription: x\nhooks:\n  PreToolUse: []\n---\nx\n", "hooks"),
    ("---\nname: other\ndescription: x\n---\nx\n", "must match"),
    ("---\nname: bad\n---\nx\n", "no description"),
])
def test_a_malformed_skill_is_listed_with_why_it_cannot_be_copied(tmp_path, text, words):
    write_skill(claude_home() / "skills" / "bad", "bad", text=text)
    got = by_id(skillscan.scan())["claude-user:bad"]
    assert words in got["copy_problem"]


def test_a_skill_with_a_link_inside_cannot_be_copied(tmp_path):
    d = write_skill(claude_home() / "skills" / "linky", "linky")
    os.symlink("/etc/passwd", d / "passwd")
    got = by_id(skillscan.scan())["claude-user:linky"]
    assert "link" in got["copy_problem"]


def test_a_dangling_top_level_link_is_listed_not_followed(tmp_path):
    (claude_home() / "skills").mkdir(parents=True)
    os.symlink(tmp_path / "gone", claude_home() / "skills" / "ghost")
    got = by_id(skillscan.scan())["claude-user:ghost"]
    assert got["problem"] == "it is a link to nothing"


def test_the_scan_is_bounded(tmp_path):
    for i in range(skillscan.MAX_SKILLS + 20):
        (claude_home() / "skills" / f"s{i:03d}").mkdir(parents=True)
    assert len(skillscan.scan()["skills"]) == skillscan.MAX_SKILLS


def test_an_unreadable_folder_is_a_problem_not_a_crash(tmp_path, monkeypatch):
    machine(tmp_path)
    real = os.scandir

    def deny(path):
        if str(path).endswith(os.path.join("codex", "skills")):
            raise PermissionError(13, "Permission denied")
        return real(path)
    monkeypatch.setattr(os, "scandir", deny)
    got = skillscan.scan()
    assert got["skills"] == [] and "cannot be listed" in got["problems"][0]
    with pytest.raises(skillscan.SkillsUnknown):
        skillscan.native_names("codex")


# --- who gets what -------------------------------------------------------------------

def test_native_off_names_its_list_and_every_agent_voice_skill(cfg_factory, tmp_path):
    machine(tmp_path)
    cfg = cfg_factory(mainSkillsOff=["weekly", "tidy:format"])
    assert skillscan.native_off(cfg, "", "claude", {"mine"}) == ["mine", "tidy:format", "weekly"]
    # A program that finds no skills by itself is told nothing.
    assert skillscan.native_off(cfg, "", "gemini", {"mine"}) == []
    assert skillscan.native_off(cfg, "", "endpoint", set()) == []


def test_native_off_with_an_unreadable_list_names_every_skill_the_cli_finds(cfg_factory, tmp_path):
    machine(tmp_path)
    cfg = cfg_factory(mainSkillsOff="garbage")
    assert skillscan.native_off(cfg, "", "claude", set()) == [
        "docx", "omarchy-app", "tidy:format", "weekly"]
    assert skillscan.native_off(cfg, "", "codex", set()) == ["crash", "deploy"]


def test_agent_view_marks_each_native_skill(tmp_path):
    machine(tmp_path)
    own("main", "weekly")                 # an Agent Voice skill of the same name
    ext = skillscan.scan()["skills"]
    view = {(s["source"], s["name"]): s for s in skillscan.agent_view(
        "claude", frozenset({"docx"}), agentfs.skills("main"), [], ext, "plugin")}
    assert view[("claude-user", "omarchy-app")]["delivered"] is True
    assert view[("claude-synced", "docx")]["delivered"] is False
    assert view[("claude-synced", "docx")]["why"] == "switched off for this agent"
    assert view[("claude-user", "weekly")]["shadowed"] is True
    assert view[("claude-user", "weekly")]["delivered"] is False
    assert view[("main", "weekly")]["delivered"] is True
    # Codex's are not a Claude agent's.
    assert not any(src in ("codex-user", "agents") for src, _ in view)
    # Unreadable: every native one off.
    view = skillscan.agent_view("claude", None, [], [], ext, "plugin")
    assert all(not s["delivered"] for s in view)


def test_lanes_put_each_skill_with_its_owner_and_the_rest_in_unused(cfg_factory, tmp_path):
    machine(tmp_path)
    own("main", "mine")
    own("communal", "shared")
    cfg = cfg_factory(mainProgram="claude", mainSkillsOff=["weekly"], voiceAgents=[
        {"name": "sora", "id": "sora", "agent": "claude", "skillsOff": ["shared", "weekly"]},
        {"name": "hazel", "id": "hazel", "agent": "gemini"}])
    got = skillscan.lanes(cfg)
    lanes = {lane["id"]: lane for lane in got["lanes"]}
    assert list(lanes) == ["main", "sora", "hazel"]
    main_names = {s["name"] for s in lanes["main"]["skills"]}
    assert "mine" in main_names and "omarchy-app" in main_names and "weekly" not in main_names
    shared = {s["name"]: s for s in got["communal"]}["shared"]
    assert "Sora" not in shared["gets"] and len(shared["gets"]) == 2      # main and Hazel (index)
    unused = {s["id"] for s in got["unused"]}
    # weekly is off for both Claude agents; Codex's have no Codex agent.
    assert unused == {"claude-user:weekly", "codex-user:deploy", "agents:crash"}


# --- delivery: Claude Code -----------------------------------------------------------

def _settings(argv) -> dict:
    return json.loads(argv[argv.index("--settings") + 1])


@pytest.mark.parametrize("ask", [True, False])
def test_claude_gets_skill_overrides_at_every_level(ask):
    from adapters.claude_code import ClaudeCode
    a = ClaudeCode(named="sora", ask_permission=ask)
    assert "skillOverrides" not in _settings(a._argv("", None))
    a.skills_off = ("weekly", "tidy:format")
    got = _settings(a._argv("", None))
    assert got["skillOverrides"] == {"tidy:format": "off", "weekly": "off"}
    assert got["hooks"]["PreToolUse"][0]["hooks"][0]["onFailure"] == "block"
    assert "--disable-slash-commands" not in a._argv("", None)


def test_try_it_carries_no_overrides():
    from adapters.claude_code import ClaudeCode
    a = ClaudeCode(named="sora")
    a.skills_off = ("weekly",)
    a.no_tools = True
    assert "skillOverrides" not in _settings(a._argv("", None))


def test_claude_with_names_unknown_gets_no_skill_at_all():
    from adapters.claude_code import ClaudeCode
    a = ClaudeCode(named="sora")
    a.skills_unknown = "Agent Voice could not tell which skills to switch off (x)."
    assert "--disable-slash-commands" in a._argv("", None)


def test_the_override_is_the_shape_that_was_recorded_switching_a_skill_off():
    """Replays the spike: the settings Agent Voice writes for "minecraft"
    are exactly the ones whose turn left minecraft out and kept the
    agent's own agentvoice:minecraft."""
    from adapters.claude_code import ClaudeCode
    rec = next(o for o in FIXTURE["claude"]["overrides"] if o.get("plugin_dir_also_holds"))
    ours = json.loads(ClaudeCode._hook_settings("sora", skills_off=("minecraft",)))
    assert {"skillOverrides": ours["skillOverrides"]} == rec["settings"]
    assert rec["gone"] == ["minecraft"] and rec["kept"] == ["agentvoice:minecraft"]
    refused = FIXTURE["claude"]["skill_tool"][0]
    assert "disabled for model invocation" in refused["tool_result"]
    # A name that names nothing is not an error.
    assert any(o.get("error") is False for o in FIXTURE["claude"]["overrides"])


# --- delivery: Codex -----------------------------------------------------------------

def _skill_flag(argv):
    return [argv[i + 1] for i, w in enumerate(argv) if w == "-c" and argv[i + 1].startswith("skills.config")]


def test_codex_gets_one_skills_config_with_each_name_off():
    from adapters.codex import Codex
    a = Codex(named="hazel")
    assert _skill_flag(a._argv("", None)) == []
    a.skills_off = ("omarchy-app", "pdf:pdf")
    assert _skill_flag(a._argv("", None)) == [
        'skills.config=[{name="omarchy-app",enabled=false},{name="pdf:pdf",enabled=false}]']
    argv = a._argv("", "thread-1")
    assert argv.index(_skill_flag(argv)[0]) < argv.index("resume")


def test_codex_never_writes_a_name_that_could_end_the_string():
    from adapters.codex import Codex
    a = Codex(named="hazel")
    a.skills_off = ('x",enabled=true},{name="y', "ok")
    assert _skill_flag(a._argv("", None)) == ['skills.config=[{name="ok",enabled=false}]']


def test_codex_with_names_unknown_starts_no_turn():
    from adapters.codex import Codex
    a = Codex(named="hazel")
    a.skills_unknown = "Agent Voice could not tell which skills to switch off (x)."
    chunks = list(a.send("hello"))
    assert len(chunks) == 1 and "Codex was not started" in chunks[0].error


def test_the_codex_flag_is_the_shape_that_was_recorded():
    from adapters.codex import Codex
    a = Codex(named="hazel")
    a.skills_off = ("omarchy-app",)
    rec = FIXTURE["codex"]["overrides"][0]
    assert _skill_flag(a._argv("", None)) == [rec["c"]] and rec["gone"] == ["omarchy-app"]
    merged = FIXTURE["codex"]["overrides"][-1]
    assert set(merged["gone"]) == {"aaa-one", "bbb-two"}     # config.toml's kept beside ours


# --- the daemon -----------------------------------------------------------------------

class P:
    def __init__(self, pid):
        self.id = pid
        self.label = pid


def _daemon(cfg, monkeypatch, tmp_path):
    from wake_listen import Daemon
    d = Daemon.__new__(Daemon)
    d.cfg = cfg
    d._folder_texts = agentfs.snapshot()[1]
    # As the daemon's poll sets it, so the plugin folder cache is used.
    d._agentfs_stamp = agentfs.stamp()
    monkeypatch.setattr(omarchy_skill, "plugin_dir", lambda: None)
    return d


def test_a_switch_reaches_a_warm_process_and_lets_it_go(cfg_factory, monkeypatch, tmp_path):
    from adapters.claude_code import ClaudeCode
    machine(tmp_path)
    own("communal", "shared")
    on = [{"name": "sora", "id": "sora", "agent": "claude"}]
    d = _daemon(cfg_factory(voiceAgents=on), monkeypatch, tmp_path)
    a = ClaudeCode(named="sora")
    cancelled = []
    a.cancel = lambda: cancelled.append(1)
    d.apply_extras(a, P("sora"))
    # Its Agent Voice skill's name is switched off where Claude looks, so a
    # same-named one of the CLI's is never offered beside it.
    assert a.skills_off == ("shared",)
    first_dir = a.skill_dir
    assert (Path(first_dir) / "skills" / "shared").is_dir()
    cancelled.clear()
    d.cfg = cfg_factory(voiceAgents=[{**on[0], "skillsOff": ["shared", "weekly"]}])
    assert d.apply_extras(a, P("sora")) is True
    assert cancelled == [1]
    assert a.skills_off == ("shared", "weekly")
    assert a.skill_dir != first_dir and a.skill_dir is None      # nothing of its own left
    assert _settings(a._argv("", None))["skillOverrides"] == {"shared": "off", "weekly": "off"}
    # Nothing changed: nothing let go.
    cancelled.clear()
    assert d.apply_extras(a, P("sora")) is False and cancelled == []


def test_an_unreadable_list_switches_off_every_native_skill_in_the_daemon(cfg_factory, monkeypatch, tmp_path):
    from adapters.codex import Codex
    machine(tmp_path)
    d = _daemon(cfg_factory(voiceAgents=[{"name": "hazel", "id": "hazel", "agent": "codex",
                                          "skillsOff": {"no": 1}}]), monkeypatch, tmp_path)
    a = Codex(named="hazel")
    a.cancel = lambda: None
    d.apply_extras(a, P("hazel"))
    assert a.skills_off == ("crash", "deploy") and a.skills_unknown == ""


def test_a_folder_nobody_can_list_stops_the_codex_turn(cfg_factory, monkeypatch, tmp_path):
    from adapters.codex import Codex
    machine(tmp_path)
    d = _daemon(cfg_factory(voiceAgents=[{"name": "hazel", "id": "hazel", "agent": "codex",
                                          "skillsOff": "?"}]), monkeypatch, tmp_path)
    d.say_once = lambda key, line: None
    monkeypatch.setattr(skillscan, "native_names", lambda program: (_ for _ in ()).throw(
        skillscan.SkillsUnknown("skills cannot be listed (Permission denied)")))
    a = Codex(named="hazel")
    a.cancel = lambda: None
    d.apply_extras(a, P("hazel"))
    assert a.skills_unknown and "Permission denied" in a.skills_unknown
    assert "Codex was not started" in list(a.send("hi"))[0].error


# --- importing -----------------------------------------------------------------------

def test_a_skill_is_copied_in_whole_and_the_original_is_unchanged(tmp_path, monkeypatch):
    m = machine(tmp_path)
    src = claude_home() / "skills" / "weekly"
    (src / "run.sh").chmod(0o755)
    before = digest(src)
    got = skillscan.import_skill("claude-user:weekly", "sora")
    # Since M12 the copy is recorded, so it can be undone: its op id.
    assert got.pop("op")
    assert got == {"target": "sora", "name": "weekly", "files": 2,
                   "bytes": sum(p.stat().st_size for p in src.iterdir())}
    assert digest(src) == before
    dest = paths.AGENTS_DIR / "sora" / "skills" / "weekly"
    assert (dest / "SKILL.md").read_text() == (src / "SKILL.md").read_text()
    assert os.stat(dest / "run.sh").st_mode & 0o777 == 0o700
    assert os.stat(dest / "SKILL.md").st_mode & 0o777 == 0o600
    # Kept, not "changed outside Settings", and given to Sora.
    entry = next(s for s in agentfs.skills("sora") if s["name"] == "weekly")
    assert entry["changed_outside"] is False and entry["problem"] == ""
    assert not list((paths.AGENTS_DIR / "sora" / "skills").glob(".import-*"))
    # A top-level link is followed (Omarchy's own skills are links).
    skillscan.import_skill("claude-user:omarchy-app", "communal")
    assert (paths.COMMUNAL_DIR / "skills" / "omarchy-app" / "SKILL.md").is_file()
    assert digest(m["ext"]) == digest(m["ext"])


def test_the_import_writes_one_audit_line_of_names_and_sizes(tmp_path):
    machine(tmp_path)
    skillscan.import_skill("codex-user:deploy", "sora")
    lines = [json.loads(x) for x in audit.log_path().read_text().splitlines()]
    assert len(lines) == 1
    line = lines[0]
    assert {k: line[k] for k in ("kind", "from", "to", "note")} == {
        "kind": "skill_import", "from": "you", "to": "sora", "note": "deploy"}
    assert line["bytes_after"] > 0
    assert "Deploy the site" not in audit.log_path().read_text()


@pytest.mark.parametrize("make, words", [
    (lambda d: os.symlink("/etc/hostname", d / "host"), "link"),
    (lambda d: (d / "big.bin").write_bytes(b"x" * (agentfs.READ_CAP + 1)), "larger than"),
    (lambda d: [(d / f"f{i}.md").write_text("x") for i in range(agentfs.SKILL_FILES_MAX + 1)], "files"),
    (lambda d: (d / "SKILL.md").write_text("---\nname: bad\ndescription: x\nhooks:\n  a: b\n---\n"), "hooks"),
    (lambda d: (d / "SKILL.md").write_text("x" * (agentfs.SKILL_MAX + 1)), "longer than"),
    (lambda d: (d / "SKILL.md").write_text("no front matter"), "front matter"),
    (lambda d: os.mkfifo(d / "pipe"), "not a plain file"),
])
def test_a_skill_breaking_a_rule_is_refused_and_leaves_nothing(tmp_path, make, words):
    d = write_skill(claude_home() / "skills" / "bad", "bad")
    make(d)
    with pytest.raises(agentfs.AgentFsError, match=words):
        skillscan.import_skill("claude-user:bad", "sora")
    assert not (paths.AGENTS_DIR / "sora" / "skills" / "bad").exists()
    assert not list((paths.AGENTS_DIR / "sora").rglob(".import-*"))


def test_a_name_clash_and_a_reserved_name_are_refused(tmp_path):
    machine(tmp_path)
    own("sora", "weekly", desc="Sora's own.")
    with pytest.raises(agentfs.AgentFsError, match="already has a skill named weekly"):
        skillscan.import_skill("claude-user:weekly", "sora")
    assert "Sora's own" in (paths.AGENTS_DIR / "sora/skills/weekly/SKILL.md").read_text()
    write_skill(claude_home() / "skills" / "omarchy", "omarchy")
    with pytest.raises(agentfs.AgentFsError, match="own built-in skills"):
        skillscan.import_skill("claude-user:omarchy", "sora")


def test_an_import_names_a_found_skill_never_a_path(tmp_path):
    machine(tmp_path)
    for bad in ("claude-user:../../etc", "/etc/passwd", "claude-user:nope", "x" * 300, ""):
        with pytest.raises(agentfs.AgentFsError):
            skillscan.import_skill(bad, "sora")
    for target in ("../x", "Sora", "", "communal/x"):
        with pytest.raises(agentfs.AgentFsError):
            skillscan.import_skill("claude-user:weekly", target)


def test_an_agent_with_no_folder_is_refused(tmp_path):
    machine(tmp_path)
    with pytest.raises(agentfs.AgentFsError, match="has no folder"):
        skillscan.import_skill("claude-user:weekly", "ghost")
    assert not (paths.AGENTS_DIR / "ghost").exists()


def test_a_skill_that_changes_while_it_is_copied_is_not_copied(tmp_path, monkeypatch):
    machine(tmp_path)
    real = agentfs._read_skill
    calls = []

    def changing(root):
        files, dg = real(root)
        calls.append(1)
        return files, dg if len(calls) == 1 else "different"
    monkeypatch.setattr(agentfs, "_read_skill", changing)
    with pytest.raises(agentfs.AgentFsError, match="changed while it was copied"):
        skillscan.import_skill("claude-user:weekly", "sora")
    assert not (paths.AGENTS_DIR / "sora" / "skills" / "weekly").exists()
    assert not list((paths.AGENTS_DIR / "sora" / "skills").glob(".import-*"))


def test_a_folder_swapped_for_a_link_mid_copy_is_not_followed(tmp_path, monkeypatch):
    """walk_skill saw a plain folder; by the time a file is opened the
    folder is a link elsewhere. The read is beneath the root with no link
    followed at any level, so it is refused rather than copied."""
    src = write_skill(claude_home() / "skills" / "swap", "swap", extra={"ref/a.md": "A"})
    real_walk = agentfs.walk_skill
    seen = []

    def walk_then_swap(root):
        # The walk sees a plain folder every time (the link is hidden from
        # it), so only the read beneath the root can refuse it.
        if not seen:
            seen.append(real_walk(root))
            shutil.rmtree(Path(root) / "ref")
            elsewhere = tmp_path / "elsewhere"
            elsewhere.mkdir(exist_ok=True)
            (elsewhere / "a.md").write_text("SECRET")
            os.symlink(elsewhere, Path(root) / "ref")
        return seen[0]
    monkeypatch.setattr(agentfs, "walk_skill", walk_then_swap)
    with pytest.raises(agentfs.AgentFsError):
        skillscan.import_skill("claude-user:swap", "sora")
    assert not (paths.AGENTS_DIR / "sora" / "skills" / "swap").exists()
    assert src.exists()


# --- only the person gives a skill ---------------------------------------------------------

@pytest.mark.parametrize("cmd", ["agentvoice skills import claude-user:x sora",
                                 "agentvoice  skills   import a communal",
                                 "python3 daemon/skillscan.py import a b"])
def test_an_agent_running_the_import_is_asked_at_every_level(cmd):
    assert "only you do" in hook.orders_write("Bash", {"command": cmd})


def test_reading_the_lanes_is_not_asked():
    assert hook.orders_write("Bash", {"command": "agentvoice skills lanes --json"}) == ""


def test_the_import_stays_a_cli_verb_and_no_page_reaches_it():
    """Phase M31 took Give a copy off Agent details (the user's decision,
    2026-11-27); `agentvoice skills import` stays, refusing a copy into
    Communal without --confirm (tested above), until the delegation flow
    decides how it comes back. No page builds it."""
    from qml_scan import overlay_qml, scan
    for path in overlay_qml():
        assert '"skills", "import"' not in scan(path).nocomment, path.name
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()) as out, pytest.raises(SystemExit):
        skillscan.main(["import", "--help"])
    assert "--confirm" in out.getvalue()


# --- the overlay function ------------------------------------------------------------------

AGENTS = [{"name": "sora", "id": "sora", "skillsOff": ["a"], "voice": "x"},
          {"name": "hazel bee", "tools": {"desktop": "on"}}]


def run_set_agent_skill(calls, main_off=None, agents=None):
    from test_tool_controls import function_source
    fn = function_source(ROOT / "Settings.qml", "setAgentSkill")
    agent_id = function_source(ROOT / "Settings.qml", "agentId")
    script = f"""
{agent_id}
var AGENTS = JSON.parse({json.dumps(json.dumps(agents if agents is not None else AGENTS))});
var MAIN = {json.dumps(main_off if main_off is not None else ["x"])};
var CALLS = {json.dumps(calls)};
var out = [];
for (var c = 0; c < CALLS.length; c++) {{
  var root = {{ voiceAgents: JSON.parse(JSON.stringify(AGENTS)), puts: [],
    put: function(k, v) {{ this.puts.push([k, JSON.parse(JSON.stringify(v))]) }},
    setting: function(k, d) {{ return k === "mainSkillsOff" ? JSON.parse(JSON.stringify(MAIN)) : d }},
    agentId: agentId }};
  {fn.replace("function setAgentSkill", "root.setAgentSkill = function")}
  var ok = eval(CALLS[c]);
  out.push({{ ok: ok, puts: root.puts }});
}}
console.log(JSON.stringify(out));
"""
    p = subprocess.run([NODE], input=script, capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


@needs_node
def test_set_agent_skill_changes_one_agents_list_and_nothing_else():
    r = run_set_agent_skill(['root.setAgentSkill("sora", "b", false)',
                             'root.setAgentSkill("sora", "a", true)',
                             'root.setAgentSkill("hazel-bee", "tidy:format", false)'])
    for result, (index, want) in zip(r, [(0, ["a", "b"]), (0, []), (1, ["tidy:format"])]):
        assert result["ok"] is True and [k for k, _ in result["puts"]] == ["voiceAgents"]
        expect = json.loads(json.dumps(AGENTS))
        expect[1]["id"] = "hazel-bee"
        expect[index]["skillsOff"] = want
        assert json.dumps(result["puts"][0][1]) == json.dumps(expect)


@needs_node
def test_set_agent_skill_for_the_main_agent_writes_its_list_only():
    r = run_set_agent_skill(['root.setAgentSkill("", "y", false)', 'root.setAgentSkill("main", "x", true)',
                             'root.setAgentSkill("main", "y", false)'], main_off=["x"])
    assert r[0]["puts"] == [["mainSkillsOff", ["x", "y"]]]
    assert r[1]["puts"] == [["mainSkillsOff", []]]


@needs_node
@pytest.mark.parametrize("call, main_off", [
    ('root.setAgentSkill("sora", "../x", false)', None),
    ('root.setAgentSkill("sora", "a", "off")', None),
    ('root.setAgentSkill("nobody", "a", false)', None),
    # A list that cannot be read is left alone, not rewritten.
    ('root.setAgentSkill("main", "a", true)', "not-a-list"),
    ('root.setAgentSkill("main", "a", true)', ["ok", 5]),
])
def test_set_agent_skill_refuses_what_it_cannot_write(call, main_off):
    r = run_set_agent_skill([call], main_off=main_off)[0]
    assert r == {"ok": False, "puts": []}


# --- what the person already switched off in the CLIs' own settings -------------------------

def test_a_skill_off_in_the_clis_own_settings_is_not_said_to_be_given(tmp_path):
    machine(tmp_path)
    settings = json.loads((claude_home() / "settings.json").read_text())
    settings["skillOverrides"] = {"weekly": "off", "docx": "on"}
    (claude_home() / "settings.json").write_text(json.dumps(settings))
    (codex_home() / "config.toml").write_text(
        '[[skills.config]]\nname = "deploy"\nenabled = false\n'
        f'[[skills.config]]\npath = "{shared_home() / "crash" / "SKILL.md"}"\nenabled = false\n')
    got = by_id(skillscan.scan())
    assert got["claude-user:weekly"]["user_off"] is True
    assert got["claude-synced:docx"]["user_off"] is False
    assert got["codex-user:deploy"]["user_off"] is True and got["agents:crash"]["user_off"] is True
    view = {s["name"]: s for s in skillscan.agent_view("claude", frozenset(), [], [],
                                                         list(got.values()), "plugin")}
    assert view["weekly"]["delivered"] is False
    assert view["weekly"]["why"] == "switched off in your own Claude Code settings"
    assert view["docx"]["delivered"] is True


def test_unreadable_cli_settings_mark_nothing_off(tmp_path):
    machine(tmp_path)
    (claude_home() / "settings.json").write_text("{not json")
    (codex_home() / "config.toml").write_text("[[[nope")
    assert not any(s["user_off"] for s in skillscan.scan()["skills"])


# --- Codex review of M11, pass 1 ------------------------------------------------------------

def test_a_skills_folder_swapped_for_a_link_after_the_check_is_not_written_through(tmp_path, monkeypatch):
    """1: the copy is staged and published by the skills folder's open
    descriptor. Swapping the folder for a link once that is open leaves
    the write in the folder that was checked, never the link's target."""
    machine(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    real = agentfs._open_skills_dir

    def open_then_swap(target):
        fd = real(target)
        skills = paths.AGENTS_DIR / target / "skills"
        os.rename(skills, paths.AGENTS_DIR / target / "skills-real")
        os.symlink(elsewhere, skills)
        return fd
    monkeypatch.setattr(agentfs, "_open_skills_dir", open_then_swap)
    skillscan.import_skill("codex-user:deploy", "sora")
    assert list(elsewhere.iterdir()) == []
    assert (paths.AGENTS_DIR / "sora" / "skills-real" / "deploy" / "SKILL.md").is_file()


def test_a_skills_folder_that_is_a_link_is_refused(tmp_path):
    machine(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(elsewhere, paths.AGENTS_DIR / "sora" / "skills")
    with pytest.raises(agentfs.AgentFsError, match="symlink"):
        skillscan.import_skill("codex-user:deploy", "sora")
    assert list(elsewhere.iterdir()) == []


def test_a_name_that_appears_mid_copy_is_never_replaced(tmp_path, monkeypatch):
    machine(tmp_path)
    real = agentfs._read_skill
    calls = []

    def second_read_makes_one(root):
        got = real(root)
        calls.append(1)
        if len(calls) == 2:      # the check after staging: somebody makes an empty one
            (paths.AGENTS_DIR / "sora" / "skills" / "deploy").mkdir()
        return got
    monkeypatch.setattr(agentfs, "_read_skill", second_read_makes_one)
    with pytest.raises(agentfs.AgentFsError, match="appeared"):
        skillscan.import_skill("codex-user:deploy", "sora")
    assert list((paths.AGENTS_DIR / "sora" / "skills" / "deploy").iterdir()) == []
    assert not list((paths.AGENTS_DIR / "sora" / "skills").glob(".import-*"))


def test_a_history_that_cannot_be_written_leaves_no_live_skill(tmp_path, monkeypatch):
    """5: the saved version comes first; when it fails nothing is published."""
    machine(tmp_path)

    def no_history(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(agentfs, "_save_version", no_history)
    with pytest.raises(OSError):
        skillscan.import_skill("codex-user:deploy", "sora")
    assert not (paths.AGENTS_DIR / "sora" / "skills" / "deploy").exists()
    assert not list((paths.AGENTS_DIR / "sora" / "skills").glob(".import-*"))


def test_a_failed_publish_takes_its_saved_version_back(tmp_path, monkeypatch):
    machine(tmp_path)
    monkeypatch.setattr(agentfs, "_rename_noreplace", lambda *a: (_ for _ in ()).throw(OSError(5, "EIO")))
    with pytest.raises(OSError):
        skillscan.import_skill("codex-user:deploy", "sora")
    assert agentfs.history("sora", "skills/deploy/SKILL.md") == []


def test_an_unreadable_list_names_every_skill_however_many(cfg_factory, tmp_path):
    """2: the fail-closed list is not the pages' 200-skill view."""
    for i in range(skillscan.MAX_SKILLS + 5):
        write_skill(claude_home() / "skills" / f"c{i:03d}", f"c{i:03d}")
    write_skill(codex_home() / "skills" / "deploy", "deploy")
    cfg = cfg_factory(mainSkillsOff="?")
    assert "deploy" in skillscan.native_off(cfg, "", "codex", set())
    assert len(skillscan.native_off(cfg, "", "claude", set())) == skillscan.MAX_SKILLS + 5


def test_a_folder_too_large_to_list_whole_closes_rather_than_names_some(cfg_factory, tmp_path, monkeypatch):
    monkeypatch.setattr(skillscan, "MAX_ENTRIES", 3)
    for i in range(5):
        write_skill(codex_home() / "skills" / f"s{i}", f"s{i}")
    cfg = cfg_factory(mainSkillsOff="?")
    with pytest.raises(skillscan.SkillsUnknown):
        skillscan.native_off(cfg, "", "codex", set())
    # The pages still show what fits.
    assert len(skillscan.scan()["skills"]) == 3


def test_an_unreadable_plugin_list_closes_the_fail_closed_list(cfg_factory, tmp_path):
    (claude_home() / "settings.json").write_text(json.dumps({"enabledPlugins": {"x@y": True}}))
    (claude_home() / "plugins").mkdir()
    (claude_home() / "plugins" / "installed_plugins.json").write_text("{broken")
    cfg = cfg_factory(mainSkillsOff="?")
    with pytest.raises(skillscan.SkillsUnknown):
        skillscan.native_off(cfg, "", "claude", set())


def test_a_skill_whose_front_matter_names_it_otherwise_is_off_by_both_names(cfg_factory, tmp_path):
    """3: ~/.codex/skills/release-tools whose front matter says deploy."""
    write_skill(codex_home() / "skills" / "release-tools", "deploy",
                text="---\nname: deploy\ndescription: Ship it.\n---\nx\n")
    got = by_id(skillscan.scan())["codex-user:release-tools"]
    assert got["aliases"] == ["deploy", "release-tools"] and got["front_name"] == "deploy"
    for switched in ("deploy", "release-tools"):
        cfg = cfg_factory(mainSkillsOff=[switched])
        assert skillscan.native_off(cfg, "", "codex", set()) == ["deploy", "release-tools"]
        view = skillscan.agent_view("codex", frozenset({switched}), [], [], [got], "index")
        assert view[0]["delivered"] is False
    cfg = cfg_factory(mainSkillsOff="?")
    assert skillscan.native_off(cfg, "", "codex", set()) == ["deploy", "release-tools"]
    # An Agent Voice skill of either name hides it.
    view = skillscan.agent_view("codex", frozenset(), [{"name": "deploy", "problem": "", "source": "main"}],
                                [], [got], "index")
    assert next(s for s in view if s.get("native"))["shadowed"] is True


def test_the_alias_map_is_kept_while_nothing_moved(tmp_path, monkeypatch):
    write_skill(codex_home() / "skills" / "release-tools", "deploy",
                text="---\nname: deploy\ndescription: Ship it.\n---\nx\n")
    skillscan._ALIAS_MEMO.clear()
    assert skillscan.alias_map("codex")["release-tools"] == {"deploy", "release-tools"}
    reads = []
    real = skillscan._head
    monkeypatch.setattr(skillscan, "_head", lambda p: reads.append(p) or real(p))
    skillscan.alias_map("codex")
    assert reads == []                                   # nothing moved: no file read
    (codex_home() / "skills" / "release-tools" / "SKILL.md").write_text(
        "---\nname: ship\ndescription: Ship it.\n---\nxy\n")
    assert skillscan.alias_map("codex")["release-tools"] == {"ship", "release-tools"}


def test_switching_off_omarchy_switches_off_the_bundled_omarchy_skill(cfg_factory):
    """4: one name, one switch -- Agent Voice's own Omarchy skill too."""
    cfg = cfg_factory(omarchySkill=True, mainSkillsOff=["omarchy"], voiceAgents=[
        {"name": "sora", "id": "sora", "agent": "claude"}])
    assert cfg.tools_for("")["omarchySkill"] is False
    assert cfg.tools_for("sora")["omarchySkill"] is True
    # An unreadable list leaves the built-in switch to its own setting.
    assert cfg_factory(omarchySkill=True, mainSkillsOff="?").tools_for("")["omarchySkill"] is True


# --- Codex review of M11, pass 2 ------------------------------------------------------------

def test_more_enabled_plugins_than_are_read_closes_the_fail_closed_list(cfg_factory, tmp_path, monkeypatch):
    import tooldetect
    monkeypatch.setattr(tooldetect, "MAX_PLUGINS", 2)
    plugins, enabled = {}, {}
    for i in range(3):
        root = tmp_path / f"p{i}"
        write_skill(root / "skills" / f"s{i}", f"s{i}")
        plugins[f"p{i}@m"] = [{"installPath": str(root)}]
        enabled[f"p{i}@m"] = True
    # A disabled plugin sorted first does not use up the room.
    plugins["a-off@m"] = [{"installPath": str(tmp_path / "off")}]
    (claude_home() / "settings.json").write_text(json.dumps({"enabledPlugins": enabled}))
    (claude_home() / "plugins").mkdir()
    (claude_home() / "plugins" / "installed_plugins.json").write_text(json.dumps({"plugins": plugins}))
    cfg = cfg_factory(mainSkillsOff="?")
    with pytest.raises(skillscan.SkillsUnknown):
        skillscan.native_off(cfg, "", "claude", set())
    monkeypatch.setattr(tooldetect, "MAX_PLUGINS", 3)
    assert skillscan.native_off(cfg, "", "claude", set()) == ["p0:s0", "p1:s1", "p2:s2"]


def test_the_alias_map_reads_every_skill_not_the_pages_view(cfg_factory, tmp_path):
    for i in range(skillscan.MAX_SKILLS + 5):
        (claude_home() / "skills" / f"c{i:03d}").mkdir(parents=True)
    write_skill(codex_home() / "skills" / "release-tools", "deploy",
                text="---\nname: deploy\ndescription: Ship it.\n---\nx\n")
    skillscan._ALIAS_MEMO.clear()
    cfg = cfg_factory(mainSkillsOff=["release-tools"])
    assert skillscan.native_off(cfg, "", "codex", set()) == ["deploy", "release-tools"]


def test_an_alias_inventory_that_cannot_be_read_closes(cfg_factory, tmp_path, monkeypatch):
    monkeypatch.setattr(skillscan, "MAX_ENTRIES", 2)
    for i in range(4):
        write_skill(codex_home() / "skills" / f"s{i}", f"s{i}")
    skillscan._ALIAS_MEMO.clear()
    with pytest.raises(skillscan.SkillsUnknown):
        skillscan.native_off(cfg_factory(mainSkillsOff=["s0"]), "", "codex", set())
    # With nothing to switch off there is nothing to alias, and nothing to read.
    assert skillscan.native_off(cfg_factory(), "", "codex", set()) == []


def test_without_an_atomic_no_replace_nothing_is_published(tmp_path, monkeypatch):
    import ctypes
    machine(tmp_path)

    class NoRenameat2:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, name):
            raise AttributeError(name)
    monkeypatch.setattr(ctypes, "CDLL", NoRenameat2)
    with pytest.raises(agentfs.AgentFsError, match="cannot publish"):
        skillscan.import_skill("codex-user:deploy", "sora")
    assert not (paths.AGENTS_DIR / "sora" / "skills" / "deploy").exists()
    assert agentfs.history("sora", "skills/deploy/SKILL.md") == []
    assert not list((paths.AGENTS_DIR / "sora" / "skills").glob(".import-*"))


def test_a_name_in_two_of_codexs_folders_is_one_skill(cfg_factory, tmp_path):
    """Found live after the install: Omarchy links its skills into both
    ~/.codex/skills and ~/.agents/skills, and Codex offers each name once,
    from ~/.codex/skills (recorded). One card in the agent's lane; the
    second copy neither listed as given nor as Unused."""
    write_skill(codex_home() / "skills" / "crash", "crash", desc="Diagnose a crash.")
    write_skill(shared_home() / "crash", "crash", desc="Diagnose a crash.")
    rec = FIXTURE["codex"]["baseline_skills"]["duplicates"]
    assert "listed once, from ~/.codex/skills" in rec
    ext = skillscan.scan()["skills"]
    view = [s for s in skillscan.agent_view("codex", frozenset(), [], [], ext, "index") if s.get("native")]
    assert [(s["source"], s["delivered"]) for s in view] == [("codex-user", True), ("agents", False)]
    assert view[1]["why"] == "the one in ~/.codex/skills is offered instead"
    cfg = cfg_factory(mainProgram="codex")
    got = skillscan.lanes(cfg)
    assert [s["source"] for s in got["lanes"][0]["skills"]] == ["codex-user"]
    assert got["unused"] == []
