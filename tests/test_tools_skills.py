"""Tools and skills per agent (merged plan, Phase 13).

A13-1: the tool switches resolve inherit / on / off per agent, the main one
included, and a switch turned off reaches a warm process on its next turn.
A13-2: a skill reaches only the agents meant to have it, and a malformed one
is listed with its problem and given to nobody. A13-3: Codex is given the
index (its skills load only from its own home or the project, so there is no
per-process way to hand it a folder). Every test has its own data folder.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import agentfs
import omarchy_skill
import paths
import permission_hook as hook

ROOT = Path(__file__).resolve().parent.parent

GOOD = "---\nname: {n}\ndescription: {d}\n---\n\n{body}\n"


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
    return d


def skill(target, name, desc="Does a thing. Use when asked.", body="Steps.", text=None,
          extra=None):
    base = paths.COMMUNAL_DIR if target == "communal" else paths.AGENTS_DIR / target
    d = base / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(text if text is not None else GOOD.format(n=name, d=desc, body=body))
    for rel, content in (extra or {}).items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(content)
    return d


def omarchy_root(tmp_path) -> str:
    root = tmp_path / "omarchy-skill"
    (root / "skills/omarchy").mkdir(parents=True)
    (root / "skills/omarchy/SKILL.md").write_text("---\nname: omarchy\ndescription: x\n---\nOMARCHY\n")
    return str(root)


def tree(root) -> dict[str, str]:
    root = Path(root)
    return {p.relative_to(root).as_posix(): p.read_text()
            for p in sorted(root.rglob("*")) if p.is_file()}


# --- A13-1: the switches ---------------------------------------------------------

def test_inherit_follows_the_global_setting_for_every_agent(cfg_factory):
    cfg = cfg_factory(desktopTools=True, browserTools=False, omarchySkill=True,
                      voiceAgents=[{"name": "sora", "id": "sora"}])
    want = {"desktop": True, "browser": False, "omarchySkill": True}
    assert cfg.tools_for("") == want
    assert cfg.tools_for("main") == want
    assert cfg.tools_for("sora") == want


def test_an_agents_own_switch_beats_the_global_one(cfg_factory):
    cfg = cfg_factory(desktopTools=True, browserTools=True, omarchySkill=False,
                      mainTools={"browser": "off"},
                      voiceAgents=[{"name": "sora", "id": "sora",
                                    "tools": {"desktop": "off", "omarchySkill": "on"}}])
    assert cfg.tools_for("") == {"desktop": True, "browser": False, "omarchySkill": False}
    assert cfg.tools_for("sora") == {"desktop": False, "browser": True, "omarchySkill": True}


def test_a_switched_off_agent_keeps_its_switches(cfg_factory):
    cfg = cfg_factory(browserTools=True, voiceAgents=[
        {"name": "sora", "id": "sora", "enabled": False, "tools": {"browser": "off"}}])
    assert cfg.tools_for("sora")["browser"] is False


@pytest.mark.parametrize("raw", ["off", ["off"], 3, None, {"browser": "OFF"},
                                 {"browser": True}, {"browser": ""}, {"browser": None}])
def test_an_unreadable_switch_reads_as_inherit(cfg_factory, raw):
    cfg = cfg_factory(browserTools=True, mainTools=raw,
                      voiceAgents=[{"name": "sora", "id": "sora", "tools": raw}])
    assert cfg.tools_for("")["browser"] is True
    assert cfg.tools_for("sora")["browser"] is True


def test_an_unknown_agent_follows_the_globals(cfg_factory):
    cfg = cfg_factory(browserTools=True)
    assert cfg.tools_for("nobody")["browser"] is True


def test_the_main_switches_are_a_shipped_default():
    import runtime
    assert runtime.DEFAULTS["mainTools"] == {}
    manifest = json.loads((ROOT / "manifest.json").read_text())
    assert manifest["barWidget"]["defaults"]["mainTools"] == {}


def _daemon(cfg, monkeypatch, root):
    from wake_listen import Daemon
    d = Daemon.__new__(Daemon)
    d.cfg = cfg
    monkeypatch.setattr(omarchy_skill, "plugin_dir", lambda: root)
    return d


class P:
    def __init__(self, pid):
        self.id = pid


def test_a_switch_turned_off_reaches_a_warm_process(cfg_factory, monkeypatch, tmp_path):
    from adapters.claude_code import ClaudeCode
    root = omarchy_root(tmp_path)
    on = [{"name": "sora", "id": "sora", "agent": "claude"}]
    d = _daemon(cfg_factory(browserTools=True, voiceAgents=on), monkeypatch, root)
    a = ClaudeCode(named="sora")
    cancelled = []
    a.cancel = lambda: cancelled.append(1)
    assert d.apply_extras(a, P("sora")) is True
    assert a.browser_tools is True and "--chrome" in a._argv("", None)
    cancelled.clear()
    off = [{**on[0], "tools": {"browser": "off"}}]
    d.cfg = cfg_factory(browserTools=True, voiceAgents=off)
    assert d.apply_extras(a, P("sora")) is True
    # The warm process is let go; the next turn starts without Chrome.
    assert cancelled == [1]
    assert a.browser_tools is False
    argv = a._argv("", None)
    assert "--no-chrome" in argv and "--chrome" not in argv


def test_one_agents_switch_leaves_the_others_alone(cfg_factory, monkeypatch, tmp_path):
    from adapters.claude_code import ClaudeCode
    agents = [{"name": "sora", "id": "sora", "agent": "claude", "tools": {"desktop": "off"}}]
    d = _daemon(cfg_factory(desktopTools=True, voiceAgents=agents), monkeypatch,
                omarchy_root(tmp_path))
    main, sora = ClaudeCode(), ClaudeCode(named="sora")
    main.cancel = sora.cancel = lambda: None
    d.apply_extras(main, P(""))
    d.apply_extras(sora, P("sora"))
    assert (main.desktop_tools, sora.desktop_tools) == (True, False)


def test_the_omarchy_switch_per_agent(cfg_factory, monkeypatch, tmp_path):
    from adapters.claude_code import ClaudeCode
    from adapters.codex import Codex
    root = omarchy_root(tmp_path)
    monkeypatch.setattr(omarchy_skill, "instructions", lambda: "OMARCHY LIST")
    agents = [{"name": "hazel", "id": "hazel", "agent": "codex", "tools": {"omarchySkill": "off"}}]
    d = _daemon(cfg_factory(omarchySkill=True, voiceAgents=agents), monkeypatch, root)
    main, hazel = ClaudeCode(), Codex(named="hazel")
    main.cancel = hazel.cancel = lambda: None
    d.apply_extras(main, P(""))
    d.apply_extras(hazel, P("hazel"))
    assert main.skill_dir == root
    assert hazel.skill_text == ""


def test_changing_switches_keeps_the_conversation(cfg_factory, monkeypatch):
    """The switches are handed over between turns; they are not a new agent."""
    from wake_listen import Daemon, Persona
    d = Daemon.__new__(Daemon)
    built = []
    monkeypatch.setattr(Daemon, "_build_persona", lambda self, p, spec: built.append(spec))
    cfg = cfg_factory(voiceAgents=[{"name": "sora", "id": "sora"}])
    spec = cfg.agents()[0]
    p = Persona("sora", spec)
    p.spec, p.agent, p.id, p.label = spec, object(), "sora", "Sora"
    new = cfg_factory(voiceAgents=[{"name": "sora", "id": "sora",
                                    "tools": {"browser": "off"}}]).agents()[0]
    d._rebuild_persona(p, new)
    assert built == [] and p.spec == new


def test_the_plugin_folder_is_built_once_per_change(cfg_factory, monkeypatch, tmp_path):
    root = omarchy_root(tmp_path)
    d = _daemon(cfg_factory(), monkeypatch, root)
    calls = []
    real = agentfs.plugin_dir
    monkeypatch.setattr(agentfs, "plugin_dir", lambda *a: calls.append(a) or real(*a))
    d._agentfs_stamp = ("one",)
    d.plugin_dir_for(P(""), root)
    d.plugin_dir_for(P(""), root)
    assert len(calls) == 1
    d._agentfs_stamp = ("two",)
    d.plugin_dir_for(P(""), root)
    assert len(calls) == 2


def test_a_failed_build_keeps_the_omarchy_skill(cfg_factory, monkeypatch, tmp_path):
    root = omarchy_root(tmp_path)
    d = _daemon(cfg_factory(), monkeypatch, root)
    d.say_once = lambda key, line: True

    def boom(*a):
        raise OSError("disk full")
    monkeypatch.setattr(agentfs, "plugin_dir", boom)
    d._agentfs_stamp = ("x",)
    assert d.plugin_dir_for(P(""), root) == root


# --- skills: what counts as one ---------------------------------------------------

def test_a_well_formed_skill_passes():
    assert agentfs.parse_skill("weekly", GOOD.format(n="weekly", d="Write it.", body="x")) == ("Write it.", "")


def test_a_folded_or_quoted_description_is_read():
    text = "---\nname: w\ndescription: >\n  One line\n  and the next.\nother: 1\n---\nbody"
    assert agentfs.parse_skill("w", text) == ("One line and the next.", "")
    assert agentfs.parse_skill("w", '---\nname: "w"\ndescription: \'Quoted.\'\n---\n')[0] == "Quoted."


@pytest.mark.parametrize("folder,text,why", [
    ("w", "no front matter", "no front matter"),
    ("w", "---\nname: w\ndescription: x\n", "not closed"),
    ("w", "---\ndescription: x\n---\n", "no name"),
    ("w", "---\nname: other\ndescription: x\n---\n", "must match"),
    ("w", "---\nname: w\n---\n", "no description"),
    ("w", "---\nname: w\ndescription: " + "d" * 301 + "\n---\n", "longer than 300"),
    ("w", "---\nname: w\ndescription: x\n---\n" + "y" * 20_001, "longer than 20000"),
    ("w", "", "empty"),
    ("omarchy", "---\nname: omarchy\ndescription: x\n---\n", "built-in Omarchy"),
    ("Bad_Name", "---\nname: Bad_Name\ndescription: x\n---\n", "folder name"),
])
def test_a_malformed_skill_names_its_problem(folder, text, why):
    desc, problem = agentfs.parse_skill(folder, text)
    assert why in problem and desc == ""


def test_skills_lists_every_folder_with_its_problem():
    skill("sora", "good")
    skill("sora", "nameless", text="---\ndescription: x\n---\n")
    (paths.AGENTS_DIR / "sora/skills/empty-dir").mkdir()
    (paths.AGENTS_DIR / "sora/skills/Bad Name").mkdir()
    got = {s["name"]: s["problem"] for s in agentfs.skills("sora")}
    assert got["good"] == ""
    assert "no name" in got["nameless"]
    assert "no SKILL.md" in got["empty-dir"]
    assert "folder name" in got["Bad Name"]


def test_a_link_inside_a_skill_is_refused(tmp_path):
    d = skill("sora", "linked")
    (tmp_path / "outside.sh").write_text("echo hi")
    os.symlink(tmp_path / "outside.sh", d / "run.sh")
    [s] = agentfs.skills("sora")
    assert "link" in s["problem"]


def test_too_many_files_is_a_problem():
    skill("sora", "big", extra={f"f{i}.txt": "x" for i in range(agentfs.SKILL_FILES_MAX)})
    [s] = agentfs.skills("sora")
    assert "more than" in s["problem"]


def test_an_own_skill_hides_the_communal_one_of_the_same_name():
    skill("communal", "report", desc="Communal way.")
    skill("communal", "shared", desc="Everyone.")
    skill("sora", "report", desc="Sora's way.")
    got = agentfs.skill_set(agentfs.skills("sora"), agentfs.skills("communal"))
    by = {(s["source"], s["name"]): s for s in got}
    assert by[("sora", "report")]["delivered"] is True
    assert by[("communal", "report")]["shadowed"] is True
    assert by[("communal", "report")]["delivered"] is False
    assert by[("communal", "shared")]["delivered"] is True


def test_a_broken_own_skill_still_hides_the_communal_one():
    skill("communal", "report")
    skill("sora", "report", text="broken")
    got = agentfs.skill_set(agentfs.skills("sora"), agentfs.skills("communal"))
    assert not any(s["delivered"] for s in got)


# --- A13-2: delivery ----------------------------------------------------------------

def test_with_no_skills_the_plugin_folder_is_the_omarchy_one_as_before(tmp_path):
    root = omarchy_root(tmp_path)
    assert agentfs.plugin_dir("main", root) == root
    assert agentfs.plugin_dir("main", None) is None
    assert not agentfs.plugins_dir().exists()


def test_the_plugin_folder_holds_exactly_what_this_agent_is_meant_to_have(tmp_path):
    root = omarchy_root(tmp_path)
    skill("sora", "pirate", body="Say ahoy.", extra={"scripts/run.sh": "echo ahoy"})
    skill("main", "theo-only", body="Theo's.")
    skill("communal", "shared", body="For all.")
    skill("communal", "pirate", body="Communal pirate.")
    skill("sora", "broken", text="no front matter")
    got = agentfs.plugin_dir("sora", root)
    assert Path(got).parent == agentfs.plugins_dir()
    files = tree(got)
    assert set(files) == {".claude-plugin/plugin.json", "skills/omarchy/SKILL.md",
                          "skills/pirate/SKILL.md", "skills/pirate/scripts/run.sh",
                          "skills/shared/SKILL.md"}
    assert "Say ahoy." in files["skills/pirate/SKILL.md"]       # its own, not communal
    assert json.loads(files[".claude-plugin/plugin.json"])["name"] == "agentvoice"
    theo = tree(agentfs.plugin_dir("main", root))
    assert "skills/theo-only/SKILL.md" in theo and "skills/pirate/SKILL.md" in theo
    assert "Communal pirate." in theo["skills/pirate/SKILL.md"]


def test_the_omarchy_skill_is_left_out_when_switched_off(tmp_path):
    skill("sora", "pirate")
    files = tree(agentfs.plugin_dir("sora", None))
    assert "skills/omarchy/SKILL.md" not in files and "skills/pirate/SKILL.md" in files


def test_plugin_folders_are_named_by_content_and_never_rewritten(tmp_path):
    root = omarchy_root(tmp_path)
    d = skill("sora", "pirate", body="one")
    first = agentfs.plugin_dir("sora", root)
    assert agentfs.plugin_dir("sora", root) == first
    before = tree(first)
    (d / "SKILL.md").write_text(GOOD.format(n="pirate", d="Does a thing. Use when asked.", body="two"))
    second = agentfs.plugin_dir("sora", root)
    assert second != first
    assert tree(first) == before                      # a running process keeps its files
    assert "two" in tree(second)["skills/pirate/SKILL.md"]


def test_a_script_keeps_its_executable_bit_and_files_are_private(tmp_path):
    d = skill("sora", "pirate", extra={"run.sh": "echo"})
    os.chmod(d / "run.sh", 0o755)
    got = Path(agentfs.plugin_dir("sora", None))
    assert os.stat(got / "skills/pirate/run.sh").st_mode & 0o777 == 0o700
    assert os.stat(got / "skills/pirate/SKILL.md").st_mode & 0o777 == 0o600
    assert os.stat(got).st_mode & 0o077 == 0


def test_prune_removes_every_folder_but_the_ones_kept(tmp_path):
    skill("sora", "a")
    keep = agentfs.plugin_dir("sora", None)
    skill("sora", "b")
    other = agentfs.plugin_dir("sora", None)
    (agentfs.plugins_dir() / ".stage-x").mkdir()
    assert agentfs.prune_plugins([keep]) == 2
    assert Path(keep).is_dir() and not Path(other).exists()


def test_the_claude_argv_carries_the_plugin_folder(tmp_path):
    from adapters.claude_code import ClaudeCode
    skill("sora", "pirate")
    a = ClaudeCode(named="sora")
    a.skill_dir = agentfs.plugin_dir("sora", None)
    argv = a._argv("", None)
    assert argv[argv.index("--plugin-dir") + 1] == a.skill_dir


# --- the index, for a backend with no skills of its own --------------------------------

def test_the_index_is_told_to_codex_and_not_to_claude_or_an_endpoint():
    from adapters.claude_code import ClaudeCode
    from adapters.codex import Codex
    from adapters.openai_compat import OpenAICompatible
    from adapters.base import SKILLS_HEAD
    skill("sora", "pirate", desc="Talk like a pirate.")
    parts = agentfs.parts_from(agentfs.snapshot()[1], "sora", "Sora", [])
    assert "- pirate: Talk like a pirate. (" in parts["skills"]
    codex, claude = Codex(), ClaudeCode()
    endpoint = OpenAICompatible("http://x/v1", "m", is_agent=True)
    for a in (codex, claude, endpoint):
        a.parts = parts
    assert SKILLS_HEAD in codex.preamble()
    assert str(paths.AGENTS_DIR / "sora/skills/pirate/SKILL.md") in codex.preamble()
    assert "pirate" not in claude.preamble()
    assert "pirate" not in endpoint.preamble()


def test_the_index_comes_before_the_omarchy_commands():
    from adapters.codex import Codex
    skill("communal", "shared")
    c = Codex()
    c.parts = agentfs.parts_from(agentfs.snapshot()[1], "main", "Theo", [])
    c.skill_text = "OMARCHY COMMANDS"
    text = c.preamble()
    assert text.index("shared") < text.index("OMARCHY COMMANDS")


def test_no_skills_leaves_no_header():
    from adapters.codex import Codex
    from adapters.base import SKILLS_HEAD
    c = Codex()
    c.parts = agentfs.parts_from(agentfs.snapshot()[1], "main", "Theo", [])
    assert c.parts["skills"] == "" and SKILLS_HEAD not in c.preamble()


def test_the_index_keeps_to_its_budgets():
    entries = [{"name": f"s{i:02d}", "description": "d" * 300, "path": "/p/" + "x" * 50,
                "delivered": True} for i in range(30)]
    text = agentfs.skills_index(entries)
    lines = text.split("\n")
    assert all(len(line) <= agentfs.SKILL_INDEX_LINE for line in lines)
    assert len(text) <= agentfs.SKILL_INDEX_MAX + 40
    assert lines[-1].startswith("- and ") and "more" in lines[-1]


def test_a_malformed_skill_is_not_in_the_index():
    skill("sora", "broken", text="nothing")
    skill("sora", "good")
    parts = agentfs.parts_from(agentfs.snapshot()[1], "sora", "Sora", [])
    assert "good" in parts["skills"] and "broken" not in parts["skills"]


def test_the_snapshot_holds_a_skill_whole_or_not_at_all(tmp_path):
    skill("sora", "long", body="z" * 25_000)
    d = skill("sora", "linked")
    (tmp_path / "x").write_text("x")
    os.symlink(tmp_path / "x", d / "x")
    texts = agentfs.snapshot()[1]["sora"]
    assert len(texts["skills/long/SKILL.md"]) > agentfs.SKILL_MAX   # for parse_skill to refuse
    assert "skills/linked/SKILL.md" not in texts


def test_editing_a_script_moves_the_stamp():
    d = skill("sora", "pirate", extra={"run.sh": "one"})
    before = agentfs.stamp()
    (d / "run.sh").write_text("two, longer")
    assert agentfs.stamp() != before


# --- what each program can use ----------------------------------------------------------

def test_the_program_table_matches_the_adapters():
    """DESKTOP_PROGRAMS and the rest are what the adapters actually take."""
    from adapters import REGISTRY
    for name, cls in REGISTRY.items():
        a = cls()
        assert hasattr(a, "desktop_tools") == (name in agentfs.DESKTOP_PROGRAMS), name
        assert hasattr(a, "browser_tools") == (name in agentfs.BROWSER_PROGRAMS), name
        assert hasattr(a, "skill_dir") == (name in agentfs.PLUGIN_PROGRAMS), name
        assert a.takes_skill_text == (name not in agentfs.PLUGIN_PROGRAMS), name


@pytest.mark.parametrize("program,desktop,browser,delivery", [
    ("claude", True, True, "plugin"),
    ("codex", True, False, "index"),
    ("gemini", False, False, "index"),
    ("endpoint", False, False, "none"),
])
def test_a_tool_a_program_cannot_use_says_why(cfg_factory, program, desktop, browser, delivery):
    entry = {"name": "sora", "id": "sora", "agent": program}
    if program == "endpoint":
        entry.update(endpointUrl="http://x/v1", endpointModel="m")
    cfg = cfg_factory(desktopTools=True, browserTools=True, voiceAgents=[entry])
    c = agentfs.catalog("sora", cfg)
    rows = {t["key"]: t for t in c["tools"]}
    assert rows["desktop"]["can"] is desktop and rows["browser"]["can"] is browser
    for t in rows.values():
        assert t["can"] or t["why_not"]          # a control that does nothing says why
        assert t["on"] is True                   # switched on is a separate fact
    assert c["delivery"] == delivery and c["delivery_how"]


def test_the_catalog_says_whether_it_asks_at_this_level(cfg_factory):
    agents = [{"name": "sora", "id": "sora", "agent": "claude", "level": "ask"},
              {"name": "hazel", "id": "hazel", "agent": "codex", "level": "trusted"}]
    cfg = cfg_factory(desktopTools=True, browserTools=True, voiceAgents=agents)
    sora = {t["key"]: t["asks"] for t in agentfs.catalog("sora", cfg)["tools"]}
    hazel = {t["key"]: t["asks"] for t in agentfs.catalog("hazel", cfg)["tools"]}
    assert sora["omarchySkill"].startswith("Asks")
    assert hazel["omarchySkill"].startswith("Runs commands without asking")
    assert "screenshot" in hazel["desktop"]
    assert hazel["browser"] == ""                # it cannot use it, so nothing to ask


def test_the_catalog_shows_its_own_switch_and_the_global(cfg_factory):
    cfg = cfg_factory(browserTools=True, mainProgram="claude", mainTools={"browser": "off"})
    row = next(t for t in agentfs.catalog("main", cfg)["tools"] if t["key"] == "browser")
    assert (row["choice"], row["global"], row["on"]) == ("off", True, False)


def test_an_endpoint_main_agent_gets_nothing(cfg_factory):
    skill("communal", "shared")
    cfg = cfg_factory(endpointUrl="http://x/v1", endpointModel="m")
    c = agentfs.catalog("main", cfg)
    assert c["program"] == "endpoint" and not any(s["delivered"] for s in c["skills"])


# --- the generated description ------------------------------------------------------------

def test_the_roster_says_what_each_agent_can_use_and_follows_a_switch(cfg_factory):
    skill("sora", "pirate")
    skill("communal", "shared")
    agents = [{"name": "sora", "id": "sora", "agent": "claude"},
              {"name": "hazel", "id": "hazel", "agent": "codex"}]
    cfg = cfg_factory(browserTools=True, desktopTools=True, mainProgram="claude",
                      voiceAgents=agents)
    by = {a["id"]: a for a in agentfs.roster(cfg, live_ids={"main", "sora", "hazel"})}
    assert by["sora"]["tools"] == ["desktop", "browser", "omarchySkill"]
    assert by["hazel"]["tools"] == ["desktop", "omarchySkill"]     # no Chrome for Codex
    assert by["sora"]["skills"] == ["pirate", "shared"]
    assert by["main"]["skills"] == ["shared"]                      # not Sora's
    agents[0]["tools"] = {"browser": "off"}
    cfg = cfg_factory(browserTools=True, desktopTools=True, voiceAgents=agents)
    by = {a["id"]: a for a in agentfs.roster(cfg, live_ids={"sora"})}
    assert "browser" not in by["sora"]["tools"]


def test_the_preview_names_the_skills_by_program(cfg_factory):
    skill("communal", "shared", desc="For all.")
    claude = cfg_factory(mainProgram="claude")
    [item] = [x for x in agentfs.preview("main", claude, live_ids={"main"}) if x["label"] == "Skills"]
    assert item["text"] == "" and "shared" in item["note"]
    codex = cfg_factory(mainProgram="codex")
    [item] = [x for x in agentfs.preview("main", codex, live_ids={"main"}) if x["label"] == "Skills"]
    assert "shared: For all." in item["text"]
    endpoint = cfg_factory(endpointUrl="http://x/v1", endpointModel="m")
    assert not [x for x in agentfs.preview("main", endpoint, live_ids={"main"})
                if x["label"] == "Skills"]


def test_the_preview_follows_the_agents_own_omarchy_switch(cfg_factory):
    cfg = cfg_factory(omarchySkill=True, voiceAgents=[
        {"name": "sora", "id": "sora", "agent": "claude", "tools": {"omarchySkill": "off"}}])
    labels = [x["label"] for x in agentfs.preview("sora", cfg, live_ids={"main", "sora"})]
    assert "Omarchy commands and keybindings" not in labels


# --- the hook and the CLI --------------------------------------------------------------------

def test_a_write_into_a_plugin_folder_is_asked_about(data):
    assert hook._sensitive(data / "agent-plugins" / "abc" / "skills/x/SKILL.md")
    assert hook._sensitive(data / "omarchy-skill" / "skills/omarchy/SKILL.md")
    assert not hook._sensitive(data / "chats" / "x.json")


def cli(*args, env=None):
    return subprocess.run([sys.executable, str(ROOT / "daemon/agentfs.py"), *args],
                          capture_output=True, text=True, env=env)


def test_the_cli_lists_skills_and_makes_the_folder(tmp_path):
    env = {**os.environ, "XDG_DATA_HOME": str(tmp_path / "xdg")}
    made = cli("skills-folder", "sora", env=env)
    assert made.returncode == 0
    folder = Path(made.stdout.strip())
    assert folder == tmp_path / "xdg/agentvoice/agents/sora/skills" and folder.is_dir()
    assert os.stat(folder).st_mode & 0o077 == 0
    (folder / "pirate").mkdir()
    (folder / "pirate/SKILL.md").write_text(GOOD.format(n="pirate", d="Arr.", body=""))
    (folder / "broken").mkdir()
    (folder / "broken/SKILL.md").write_text("x")
    got = json.loads(cli("skills", "sora", "--json", env=env).stdout)
    assert [(s["name"], bool(s["problem"])) for s in got] == [("broken", True), ("pirate", False)]
    assert cli("skills-folder", "../x", env=env).returncode == 1


def test_the_cli_catalog_is_json(tmp_path):
    env = {**os.environ, "XDG_DATA_HOME": str(tmp_path / "xdg"),
           "XDG_CONFIG_HOME": str(tmp_path / "cfg")}
    out = cli("catalog", "main", "--json", env=env)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert [t["key"] for t in got["tools"]] == ["desktop", "browser", "omarchySkill"]


def test_the_cards_copy_of_the_program_table_matches_agentfs():
    """ToolSwitches.qml decides on the card whether to offer a switch or say
    why not; it must agree with agentfs, which decides what is given."""
    import re
    qml = (ROOT / "ui/ToolSwitches.qml").read_text()

    def listed(name):
        m = re.search(name + r':\s*\[([^\]]*)\]', qml)
        return tuple(re.findall(r'"([a-z-]+)"', m.group(1)))
    assert listed("desktopPrograms") == agentfs.DESKTOP_PROGRAMS
    assert listed("browserPrograms") == agentfs.BROWSER_PROGRAMS
