"""Phase M15: Communal -- who gets it, the whole prompt, import, history.

* `communalOff`: an agent opted out is told no communal rules or defaults
  and given no communal skill, by every path that builds what it gets (the
  prompt parts, the Claude plugin folder, the skills index, the catalog, the
  lanes, the native-skill switch); an unreadable list is nobody opted out;
  the daemon lets a warm process go when it changes.
* `agents prompt`: built by the adapter's own preamble builder, so what the
  page shows is byte for byte what each backend is sent -- checked against
  the daemon's own path for every backend.
* `agents import communal DIR`: a dry run that changes nothing, a commit that
  is all or nothing (real crashes: a forked child dying with os._exit at the
  step named, then recovery), Undo tied to the revision, refusals for links,
  oversize files, clashes and a moved folder, audit lines with no text.
* History: one saved version's text and its diff to now.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import agentfs
import audit
import communal_import
import paths
import permission_hook as hook
import runtime
import skillscan
import transfer
from adapters.antigravity import Antigravity
from adapters.claude_code import ClaudeCode
from adapters.cli_agent import CliAgent
from adapters.codex import Codex
from adapters.gemini import Gemini
from adapters.openai_compat import OpenAICompatible

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def data(tmp_path, monkeypatch):
    monkeypatch.setattr(agentfs, "live_from_state", lambda: None)
    d = tmp_path / "data"
    monkeypatch.setattr(paths, "DATA_DIR", d)
    monkeypatch.setattr(paths, "AGENTS_DIR", d / "agents")
    monkeypatch.setattr(paths, "COMMUNAL_DIR", d / "communal")
    monkeypatch.setattr(hook, "AGENTS_DIR", d / "agents")
    monkeypatch.setattr(hook, "COMMUNAL_DIR", d / "communal")
    monkeypatch.setattr(hook, "DATA_DIR", d)
    agentfs._LAST_GOOD.clear()
    return d


def skill(root: Path, name: str, desc: str = "Does a thing. Use when asked.", body: str = "Steps.") -> Path:
    (root / name).mkdir(parents=True, exist_ok=True)
    (root / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n\n{body}\n")
    return root / name


def communal_skill(name: str, **kw) -> Path:
    paths.COMMUNAL_DIR.mkdir(parents=True, exist_ok=True)
    return skill(paths.COMMUNAL_DIR / "skills", name, **kw)


def tree(root: Path) -> dict[str, str]:
    """Every file under `root` with its hash (links as their target)."""
    out = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root))
        if p.is_symlink():
            out[rel] = "link:" + os.readlink(p)
        elif p.is_file():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        else:
            out[rel] = "dir"
    return out


# --- the setting ------------------------------------------------------------------------

def test_communal_off_reads_as_a_set_of_ids(cfg_factory):
    assert runtime.Config.communal_off(cfg_factory()) == frozenset()
    cfg = cfg_factory(communalOff=["sora", "main"])
    assert cfg.communal_off() == {"sora", "main"}
    assert not cfg.takes_communal("") and not cfg.takes_communal("main")
    assert not cfg.takes_communal("sora") and cfg.takes_communal("hazel")


@pytest.mark.parametrize("raw", ["sora", {"sora": True}, ["Sora"], ["sora", 3], ["../x"],
                                 [f"a{i}" for i in range(65)], 7])
def test_an_unreadable_list_is_nobody_opted_out(cfg_factory, raw):
    """Appendix A: unreadable is [] -- every agent is told the rules, which
    may carry safety text."""
    cfg = cfg_factory(communalOff=raw)
    assert cfg.communal_off() == frozenset() and cfg.takes_communal("sora")


def test_null_is_nobody_and_unreadable_settings_are_nobody(cfg_factory, monkeypatch):
    assert cfg_factory(communalOff=None).communal_off() == frozenset()
    cfg = cfg_factory(communalOff=["sora"])
    monkeypatch.setattr(cfg, "settings_readable", lambda: False)
    assert cfg.takes_communal("sora")


def test_the_setting_has_its_three_parts():
    manifest = json.loads((ROOT / "manifest.json").read_text())["barWidget"]
    assert manifest["defaults"]["communalOff"] == [] == runtime.DEFAULTS["communalOff"]
    page = (ROOT / "pages" / "CommunalPage.qml").read_text()
    assert 's.put("communalOff", list)' in page


# --- what an opted-out agent gets ---------------------------------------------------------

def test_an_opted_out_agent_is_told_no_rules_or_defaults_and_indexed_no_communal_skill():
    agentfs.write("communal", "rules.md", "Never shout.")
    agentfs.write("communal", "defaults.md", "Use metric.")
    communal_skill("weekly")
    texts = agentfs.snapshot()[1]
    me = [{"id": "sora", "label": "Sora", "phrase": "sora"}]
    told = agentfs.parts_from(texts, "sora", "Sora", me)
    assert told["rules"] == "Never shout." and "weekly" in told["skills"]
    off = agentfs.parts_from(texts, "sora", "Sora", me, communal_on=False)
    assert off["rules"] == off["defaults"] == "" and "weekly" not in off["skills"]


MAKERS = {
    "claude": ClaudeCode, "codex": Codex, "gemini": Gemini, "agy": Antigravity,
    "copilot": lambda: CliAgent("copilot"),
    "endpoint-chat": lambda: OpenAICompatible("http://127.0.0.1:9", "m"),
    "endpoint-agent": lambda: OpenAICompatible("http://127.0.0.1:9", "m", is_agent=True),
}


@pytest.mark.parametrize("name", sorted(MAKERS))
def test_opted_out_is_byte_for_byte_an_empty_communal_folder(name):
    """A11-1 still holds: with the communal folder empty the preamble is the
    old one (test_preamble), and an opted-out agent's preamble with a full
    communal folder is that same one."""
    me = [{"id": "sora", "label": "Sora", "phrase": "sora"}]
    agentfs.write("sora", "personality.md", "Dry.")
    empty = MAKERS[name]()
    empty.parts = agentfs.parts_from(agentfs.snapshot()[1], "sora", "Sora", me)
    agentfs.write("communal", "rules.md", "Never shout.")
    agentfs.write("communal", "defaults.md", "Use metric.")
    communal_skill("weekly")
    off = MAKERS[name]()
    off.parts = agentfs.parts_from(agentfs.snapshot()[1], "sora", "Sora", me, communal_on=False)
    assert off.preamble() == empty.preamble()
    on = MAKERS[name]()
    on.parts = agentfs.parts_from(agentfs.snapshot()[1], "sora", "Sora", me)
    assert "Never shout." in on.preamble()


def test_its_plugin_folder_has_no_communal_skill():
    (paths.AGENTS_DIR / "sora").mkdir(parents=True)
    communal_skill("weekly")
    skill(paths.AGENTS_DIR / "sora" / "skills", "mine")
    on = Path(agentfs.plugin_dir("sora", None))
    assert (on / "skills" / "weekly" / "SKILL.md").is_file()
    off = Path(agentfs.plugin_dir("sora", None, communal_on=False))
    assert not (off / "skills" / "weekly").exists() and (off / "skills" / "mine").is_dir()
    # With nothing of its own left and no built-in skill: no folder at all.
    shutil.rmtree(paths.AGENTS_DIR / "sora" / "skills")
    assert agentfs.plugin_dir("sora", None, communal_on=False) is None


def test_each_communal_skill_says_why_it_is_not_given():
    communal_skill("weekly")
    got = agentfs.skill_set([], agentfs.skills("communal"), frozenset(), communal_on=False)
    assert [(s["name"], s["delivered"], s["why"]) for s in got] == \
        [("weekly", False, agentfs.NOT_COMMUNAL)]
    view = skillscan.agent_view("claude", frozenset(), [], agentfs.skills("communal"), [],
                                "plugin", False)
    assert view[0]["why"] == agentfs.NOT_COMMUNAL


def test_an_opted_out_agents_cli_keeps_its_own_copy_of_a_communal_skills_name():
    """native: Agent Voice hides the CLI's own copy of a skill it gives
    instead; it gives an opted-out agent no communal one, so it hides none."""
    communal_skill("weekly")
    ext = [{"name": "weekly", "family": "claude", "folder": "weekly", "source": "claude-user",
            "source_label": "~/.claude/skills", "aliases": []}]
    on = skillscan.agent_view("claude", frozenset(), [], agentfs.skills("communal"), ext, "plugin")
    off = skillscan.agent_view("claude", frozenset(), [], agentfs.skills("communal"), ext,
                               "plugin", False)
    assert [s["delivered"] for s in on if s.get("native")] == [False]
    assert [s["delivered"] for s in off if s.get("native")] == [True]


def test_lanes_and_catalog_say_who_takes_communal(cfg_factory, monkeypatch):
    monkeypatch.setattr(skillscan, "scan", lambda: {"skills": [], "problems": [], "ms": 0})
    communal_skill("weekly")
    cfg = cfg_factory(phrase="theo", mainProgram="claude", communalOff=["sora"],
                      voiceAgents=[{"id": "sora", "name": "sora", "agent": "claude"},
                                   {"id": "wren", "name": "wren", "agent": "claude"}])
    got = skillscan.lanes(cfg)
    takes = {lane["id"]: lane["takes_communal"] for lane in got["lanes"]}
    assert takes == {"main": True, "sora": False, "wren": True}
    assert got["communal"][0]["gets"] == ["Theo", "Wren"]
    monkeypatch.setattr(skillscan, "lanes", lambda c, texts=None: got)
    import tooldetect
    monkeypatch.setattr(tooldetect, "scan_cached", lambda c, force=False, with_defs=False:
                        {"tools": [], "problems": [], "files_read": 0, "ms": 0})
    monkeypatch.setattr(tooldetect, "rows", lambda *a, **k: [])
    cat = agentfs.catalog("sora", cfg)
    assert cat["takes_communal"] is False
    assert [s["why"] for s in cat["skills"] if s["source"] == "communal"] == [agentfs.NOT_COMMUNAL]


def test_the_roster_lists_no_communal_skill_for_an_opted_out_agent(cfg_factory):
    communal_skill("weekly")
    cfg = cfg_factory(phrase="theo", mainProgram="claude", communalOff=["sora"],
                      voiceAgents=[{"id": "sora", "name": "sora", "agent": "claude"}])
    got = {a["id"]: a["skills"] for a in agentfs.roster(cfg)}
    assert got == {"main": ["weekly"], "sora": []}


# --- the daemon ---------------------------------------------------------------------------

class Agent(ClaudeCode):
    def __init__(self):
        super().__init__()
        self.cancelled = 0

    def cancel(self):
        self.cancelled += 1


def crew_daemon(daemon, monkeypatch, entries):
    from crew import Persona
    import crew_links
    daemon.agent = Agent()
    daemon._main.name, daemon._main.label = "theo", "Theo"
    daemon.cfg._values["phrase"] = "theo"
    daemon.cfg._values["voiceAgents"] = [{"id": e["id"], "name": e["name"]} for e in entries]
    daemon.cfg._values["crewLinks"] = crew_links.everyone(["main"] + [e["id"] for e in entries])
    for spec in entries:
        p = Persona(spec["name"], spec)
        p.agent = Agent()
        daemon.crew[spec["id"]] = p
    monkeypatch.setattr(daemon, "publish_agent", lambda: None)


def test_opting_out_reaches_the_next_poll_and_lets_the_idle_process_go(daemon, monkeypatch):
    crew_daemon(daemon, monkeypatch, [{"id": "sora", "name": "sora", "label": "Sora"}])
    agentfs.write("communal", "rules.md", "Never shout.")
    daemon.reconcile_agent_files()
    daemon.reconcile_parts()
    sora = daemon.crew["sora"].agent
    assert sora.parts["rules"] == "Never shout."
    before = sora.cancelled
    daemon.cfg._values["communalOff"] = ["sora"]
    daemon.reconcile_parts()
    assert sora.parts["rules"] == "" and "Never shout." not in sora.preamble()
    assert sora.cancelled == before + 1
    assert daemon._main.agent.parts["rules"] == "Never shout."       # the others keep it
    daemon.cfg._values["communalOff"] = []
    daemon.reconcile_parts()
    assert sora.parts["rules"] == "Never shout." and sora.cancelled == before + 2


def test_the_plugin_folder_follows_the_switch(daemon, monkeypatch):
    crew_daemon(daemon, monkeypatch, [{"id": "sora", "name": "sora", "label": "Sora"}])
    communal_skill("weekly")
    daemon.reconcile_agent_files()
    p = daemon.crew["sora"]
    on = daemon.plugin_dir_for(p, None)
    assert on and (Path(on) / "skills" / "weekly").is_dir()
    daemon.cfg._values["communalOff"] = ["sora"]
    assert daemon.plugin_dir_for(p, None) is None          # nothing else to give it
    daemon.cfg._values["communalOff"] = "garbled"           # unreadable: everyone
    assert daemon.plugin_dir_for(p, None) == on


def test_the_names_its_cli_hides_leave_out_communal_ones(daemon, monkeypatch):
    crew_daemon(daemon, monkeypatch, [{"id": "sora", "name": "sora", "label": "Sora"}])
    communal_skill("weekly")
    daemon.reconcile_agent_files()
    daemon.cfg._values["voiceAgents"] = [{"id": "sora", "name": "sora", "agent": "claude"}]
    p, agent = daemon.crew["sora"], daemon.crew["sora"].agent
    assert "weekly" in daemon.native_skills_off(agent, p)[0]
    daemon.cfg._values["communalOff"] = ["sora"]
    assert "weekly" not in daemon.native_skills_off(agent, p)[0]


# --- the whole prompt, as sent --------------------------------------------------------------

PROGRAMS = {"claude": ClaudeCode, "codex": Codex, "gemini": Gemini, "agy": Antigravity,
            "copilot": lambda: CliAgent("copilot")}


def fixed_tools(monkeypatch):
    import agentvoice_skill
    import omarchy_skill
    import tooldetect
    monkeypatch.setattr(tooldetect, "scan_cached", lambda cfg, force=False, with_defs=False:
                        ({"tools": []}, []) if with_defs else {"tools": []})
    monkeypatch.setattr(tooldetect, "delivery", lambda *a, **k: {
        "servers": {}, "codex_on": {}, "codex_off": [], "clis_on": ["gh"], "clis_off": ["stripe"]})
    monkeypatch.setattr(omarchy_skill, "instructions", lambda root=None: "OMARCHY COMMANDS")
    monkeypatch.setattr(agentvoice_skill, "instructions", lambda root=None: "AGENT VOICE LINE")
    monkeypatch.setattr(agentvoice_skill, "plugin_dir", lambda: None)
    monkeypatch.setattr(omarchy_skill, "plugin_dir", lambda: None)


@pytest.mark.parametrize("program", sorted(PROGRAMS) + ["endpoint-chat", "endpoint-agent"])
@pytest.mark.parametrize("opted_out", [False, True])
def test_the_preview_is_what_the_daemon_sends(daemon, monkeypatch, program, opted_out):
    """The page's numbers and pieces are the adapter's own preamble over
    what the daemon hands it: the same bytes, for every backend, with the
    agent in Communal and opted out of it."""
    fixed_tools(monkeypatch)
    crew_daemon(daemon, monkeypatch, [{"id": "sora", "name": "sora", "label": "Sora"}])
    if program.startswith("endpoint"):
        daemon.cfg._values.update(endpointUrl="http://127.0.0.1:9/v1", endpointModel="m",
                                  endpointIsAgent=program == "endpoint-agent")
        daemon.agent = OpenAICompatible("http://127.0.0.1:9/v1", "m",
                                        is_agent=program == "endpoint-agent")
    else:
        daemon.cfg._values["mainProgram"] = program
        daemon.agent = PROGRAMS[program]()
    if opted_out:
        daemon.cfg._values["communalOff"] = ["main"]
    agentfs.write("communal", "rules.md", "Never shout.")
    agentfs.write("communal", "defaults.md", "Use metric.")
    agentfs.write("main", "personality.md", "Dry humour.")
    agentfs.write("main", "instructions.md", "Be brief.")
    agentfs.write("sora", "role.md", "Quick answers.")
    communal_skill("weekly")
    daemon.reconcile_agent_files()
    daemon.reconcile_parts()
    daemon.apply_extras(daemon.agent, daemon._main)
    daemon.agent.instructions = daemon.instructions_for("", daemon.cfg["agentInstructions"])
    sent = daemon.agent.preamble()
    got = agentfs.prompt("main", daemon.cfg)
    assert "\n\n".join(p["text"] for p in got["pieces"]) == sent
    assert got["total"] == len(sent) == sum(p["chars"] for p in got["pieces"]) + got["separators"]
    assert ("Never shout." in sent) is (not opted_out)
    assert got["takes_communal"] is (not opted_out)
    assert "Quick answers." in sent                       # the roster, along a link


def test_the_preview_names_where_each_piece_comes_from(cfg_factory, monkeypatch):
    fixed_tools(monkeypatch)
    cfg = cfg_factory(phrase="theo", mainProgram="codex")
    agentfs.write("communal", "rules.md", "Never shout.")
    agentfs.write("main", "instructions.md", "Be brief.")
    got = agentfs.prompt("main", cfg)
    keys = [p["key"] for p in got["pieces"]]
    assert keys == ["style", "rules", "instructions", "skill_text", "clis"]
    by = {p["key"]: p for p in got["pieces"]}
    assert by["rules"]["source"] == "communal/rules.md"
    assert by["instructions"]["source"] == "agents/main/instructions.md"
    assert "win over the communal defaults" in by["instructions"]["precedence"]
    assert got["beside"] == []                     # Codex is told its skills inline


def test_a_claude_agent_is_shown_the_skills_it_loads_beside_the_prompt(cfg_factory, monkeypatch):
    fixed_tools(monkeypatch)
    communal_skill("weekly")
    cfg = cfg_factory(phrase="theo", mainProgram="claude")
    got = agentfs.prompt("main", cfg)
    assert "weekly" in got["beside"][0]["note"] and "not counted" in got["beside"][0]["note"]
    off = agentfs.prompt("main", cfg_factory(phrase="theo", mainProgram="claude",
                                             communalOff=["main"]))
    assert "weekly" not in off["beside"][0]["note"]


def test_an_unknown_agent_is_refused(cfg_factory):
    with pytest.raises(agentfs.AgentFsError):
        agentfs.prompt("nobody", cfg_factory())


# --- import -----------------------------------------------------------------------------------

@pytest.fixture
def src(tmp_path):
    d = tmp_path / "export"
    d.mkdir()
    (d / "rules.md").write_text("Ask before deleting anything.\n")
    (d / "defaults.md").write_text("Use metric units.\n")
    skill(d / "skills", "weekly", body="Write the weekly report.")
    skill(d / "skills", "packing", body="Pack the bag.")
    return d


def cfg(cfg_factory, **kw):
    return cfg_factory(phrase="theo", voiceAgents=[{"id": "sora", "name": "sora"}], **kw)


def before_import():
    agentfs.write("communal", "rules.md", "Old rules.")
    return tree(paths.DATA_DIR)


def test_a_dry_run_lists_everything_and_changes_nothing(src, cfg_factory):
    was = before_import()
    (src / "notes.txt").write_text("x")
    p = communal_import.plan(str(src), cfg(cfg_factory, communalOff=["sora"]))
    assert p["problems"] == [] and p["changes"] == 4
    assert p["ignored"] == ["notes.txt"]
    assert p["files"] == ["rules.md", "defaults.md", "skills/packing/SKILL.md",
                          "skills/weekly/SKILL.md"]
    t = {x["file"]: x for x in p["texts"]}
    assert t["rules.md"]["change"] == "replace" and t["defaults.md"]["change"] == "new"
    assert "-Old rules." in t["rules.md"]["diff"] and "+Ask before deleting anything." in t["rules.md"]["diff"]
    assert p["reaches"] == ["Theo"]                       # Sora opted out
    assert len(p["token"]) == 32
    assert tree(paths.DATA_DIR) == was                    # nothing written, no lock, no journal


def test_an_import_commits_all_of_it_and_undo_puts_it_back(src, cfg_factory):
    was = before_import()
    c = cfg(cfg_factory)
    p = communal_import.plan(str(src), c)
    r = communal_import.commit(str(src), p["token"], c)
    assert r["state"] == "done" and r["texts"] == ["rules.md", "defaults.md"]
    assert sorted(r["skills"]) == ["packing", "weekly"]
    assert agentfs.read_file("communal", "rules.md")["text"] == "Ask before deleting anything."
    for f in ("rules.md", "defaults.md", "skills/weekly/SKILL.md"):
        assert not agentfs.read_file("communal", f)["changed_outside"], f
    assert {s["name"] for s in agentfs.skills("communal")} == {"packing", "weekly"}
    assert communal_import.history()[0]["undoable"]
    u = communal_import.undo(r["op"])
    assert u["action"] == "undo" and u["undo_of"] == r["op"]
    assert agentfs.read_file("communal", "rules.md")["text"] == "Old rules."
    assert not agentfs.read_file("communal", "rules.md")["changed_outside"]
    path, _ = agentfs._resolve("communal", "defaults.md")
    assert not path.exists() and not agentfs.read_file("communal", "defaults.md")["changed_outside"]
    assert agentfs.skills("communal") == []
    now = tree(paths.DATA_DIR)
    # The live files are as they were; only history and the journal grew.
    # (an empty skills folder made on the way, and the journal, aside).
    live = lambda t: {k: v for k, v in t.items() if not k.startswith(("agents", ".", "audit"))
                      and "/.history" not in k and k != "communal/skills"}
    assert live(now) == live(was)
    h = communal_import.history()
    assert h[0]["action"] == "undo" and h[1]["state"] == "undone" and not h[1]["undoable"]
    with pytest.raises(agentfs.AgentFsError, match="undone already"):
        communal_import.undo(r["op"])
    with pytest.raises(agentfs.AgentFsError, match="no finished import"):
        communal_import.undo(u["op"])
    # No side copy outlives an import that can no longer be undone.
    assert not [n for n in os.listdir(transfer.journal_dir()) if n.endswith(".d")]


def test_a_text_or_skill_changed_since_refuses_the_undo(src, cfg_factory):
    before_import()
    c = cfg(cfg_factory)
    r = communal_import.commit(str(src), communal_import.plan(str(src), c)["token"], c)
    agentfs.write("communal", "rules.md", "Edited after.")
    with pytest.raises(agentfs.AgentFsError, match="rules.md changed since"):
        communal_import.undo(r["op"])
    agentfs.write("communal", "rules.md", "Ask before deleting anything.\n")
    (paths.COMMUNAL_DIR / "skills" / "weekly" / "SKILL.md").write_text("changed")
    with pytest.raises(agentfs.AgentFsError, match="weekly in Communal changed"):
        communal_import.undo(r["op"])
    assert agentfs.read_file("communal", "rules.md")["text"] == "Ask before deleting anything."


def test_the_token_commits_only_what_the_dry_run_listed(src, cfg_factory):
    was = before_import()
    c = cfg(cfg_factory)
    token = communal_import.plan(str(src), c)["token"]
    (src / "rules.md").write_text("Something else.\n")
    with pytest.raises(agentfs.AgentFsError, match="changed since the dry run"):
        communal_import.commit(str(src), token, c)
    token = communal_import.plan(str(src), c)["token"]
    agentfs.write("communal", "rules.md", "Edited meanwhile.")
    with pytest.raises(agentfs.AgentFsError, match="changed since the dry run"):
        communal_import.commit(str(src), token, c)
    with pytest.raises(agentfs.AgentFsError, match="not a token"):
        communal_import.commit(str(src), "x; rm -rf ~", c)
    assert agentfs.skills("communal") == []
    assert not os.path.exists(paths.AGENTS_DIR / ".transfers") or \
        not [n for n in os.listdir(paths.AGENTS_DIR / ".transfers") if n.endswith(".json")]
    assert was  # (texts above changed by the test itself)


def test_the_commit_writes_the_very_bytes_its_token_was_checked_on(src, cfg_factory, monkeypatch):
    """Found re-reading the diff: commit() checked the token on one read of
    the folder and staged from a second, so a file changed between the two
    would have been committed unseen. One read now."""
    before_import()
    c = cfg(cfg_factory)
    token = communal_import.plan(str(src), c)["token"]
    real, reads = communal_import.read_source, []

    def read_then_change(path):
        got = real(path)
        reads.append(1)
        (src / "rules.md").write_text("Changed after the check.\n")
        return got
    monkeypatch.setattr(communal_import, "read_source", read_then_change)
    communal_import.commit(str(src), token, c)
    assert reads == [1]
    assert agentfs.read_file("communal", "rules.md")["text"] == "Ask before deleting anything."


def refused(src, c, match):
    p = communal_import.plan(str(src), c)
    assert any(match in x for x in p["problems"]), p["problems"]
    with pytest.raises(agentfs.AgentFsError, match="refused"):
        communal_import.commit(str(src), p["token"], c)
    assert agentfs.skills("communal") == []


def test_links_are_refused_wherever_they_are(src, cfg_factory, tmp_path):
    c = cfg(cfg_factory)
    link = tmp_path / "link"
    link.symlink_to(src)
    p = communal_import.plan(str(link), c)
    assert p["problems"] and "link" in p["problems"][0]
    (src / "rules.md").unlink()
    (src / "rules.md").symlink_to(tmp_path / "elsewhere.md")         # dangling
    refused(src, c, "rules.md is a link")
    (src / "rules.md").unlink()
    (src / "skills" / "weekly" / "more.md").symlink_to("/etc/passwd")
    refused(src, c, "skills/weekly: it holds a link")
    (src / "skills" / "weekly" / "more.md").unlink()
    (src / "skills" / "evil").symlink_to(src / "skills" / "weekly")
    refused(src, c, "skills/evil")


def test_special_and_oversize_files_are_refused(src, cfg_factory):
    c = cfg(cfg_factory)
    (src / "rules.md").write_text("x" * 1501)
    refused(src, c, "longer than 1500 characters")
    (src / "rules.md").write_bytes(b"x" * (agentfs.READ_CAP + 1))
    refused(src, c, "larger than")
    (src / "rules.md").unlink()
    os.mkfifo(src / "defaults.md.fifo")
    (src / "defaults.md").unlink()
    os.rename(src / "defaults.md.fifo", src / "defaults.md")
    refused(src, c, "defaults.md is not a plain file")
    (src / "defaults.md").unlink()
    (src / "skills" / "weekly" / "big.bin").write_bytes(b"x" * (agentfs.READ_CAP + 1))
    refused(src, c, "larger than")


def test_bad_skills_reserved_names_and_too_many_are_refused(src, cfg_factory):
    c = cfg(cfg_factory)
    (src / "skills" / "weekly" / "SKILL.md").write_text("no front matter")
    refused(src, c, "skills/weekly")
    shutil.rmtree(src / "skills" / "weekly")
    skill(src / "skills", "agentvoice")
    refused(src, c, "Agent Voice's own")
    shutil.rmtree(src / "skills" / "agentvoice")
    for i in range(communal_import.MAX_SKILLS):
        skill(src / "skills", f"s{i}")
    refused(src, c, f"more than {communal_import.MAX_SKILLS} skills")


def test_a_clash_is_refused_and_the_same_skill_is_left_alone(src, cfg_factory):
    c = cfg(cfg_factory)
    shutil.copytree(src / "skills" / "packing", paths.COMMUNAL_DIR / "skills" / "packing")
    p = communal_import.plan(str(src), c)
    assert {s["name"]: s["change"] for s in p["skills"]} == {"packing": "same", "weekly": "new"}
    assert "skills/packing/SKILL.md" not in p["files"]
    communal_skill("weekly", body="Another weekly.")
    refused_plan = communal_import.plan(str(src), c)
    assert any("already has a skill named weekly" in x for x in refused_plan["problems"])
    with pytest.raises(agentfs.AgentFsError, match="refused"):
        communal_import.commit(str(src), refused_plan["token"], c)
    assert "Another weekly." in (paths.COMMUNAL_DIR / "skills" / "weekly" / "SKILL.md").read_text()


def test_nothing_new_is_refused_and_an_agents_own_skill_is_named(src, cfg_factory):
    c = cfg(cfg_factory)
    skill(paths.AGENTS_DIR / "sora" / "skills", "weekly")
    p = communal_import.plan(str(src), c)
    assert {s["name"]: s["hidden_for"] for s in p["skills"]}["weekly"] == ["Sora"]
    communal_import.commit(str(src), p["token"], c)
    again = communal_import.plan(str(src), c)
    assert again["changes"] == 0 and again["problems"] == []
    with pytest.raises(agentfs.AgentFsError, match="nothing to import"):
        communal_import.commit(str(src), again["token"], c)


def test_an_export_round_trips(cfg_factory, tmp_path):
    """Round-trip a synthetic export: what Export writes, Import reads."""
    c = cfg(cfg_factory)
    agentfs.write("communal", "rules.md", "Be careful.")
    agentfs.write("communal", "defaults.md", "Metric.")
    communal_skill("weekly")
    out = Path(agentfs.export("communal", str(tmp_path)))
    shutil.rmtree(paths.COMMUNAL_DIR)
    agentfs.ensure_communal()
    p = communal_import.plan(str(out), c)
    assert p["problems"] == [], p["problems"]
    communal_import.commit(str(out), p["token"], c)
    assert agentfs.read_file("communal", "rules.md")["text"] == "Be careful."
    assert [s["name"] for s in agentfs.skills("communal")] == ["weekly"]


def test_audit_lines_hold_ids_names_and_sizes_never_text(src, cfg_factory):
    (src / "rules.md").write_text("CANARYWORD rules.\n")
    c = cfg(cfg_factory)
    r = communal_import.commit(str(src), communal_import.plan(str(src), c)["token"], c)
    communal_import.undo(r["op"])
    log = audit.log_path().read_text()
    kinds = [json.loads(line)["kind"] for line in log.splitlines()]
    assert kinds.count("communal_import") == 1 and kinds.count("communal_import_undo") == 1
    assert kinds.count("skill_import") == 2
    assert "CANARYWORD" not in log
    for n in os.listdir(transfer.journal_dir()):
        if n.endswith(".json"):
            assert "CANARYWORD" not in (transfer.journal_dir() / n).read_text()


# --- crashes ---------------------------------------------------------------------------------

def crash(at, fn):
    pid = os.fork()
    if pid == 0:                                    # pragma: no cover - the child
        try:
            at()
            fn()
        finally:
            os._exit(0)
    _, status = os.waitpid(pid, 0)
    assert os.WIFEXITED(status)


def die_when(obj, attr, test, timing="before"):
    real = getattr(obj, attr)
    seen = {"n": 0}

    def wrapper(*a, **k):
        if timing == "before" and test(seen, *a, **k):
            os._exit(0)
        out = real(*a, **k)
        if timing == "after" and test(seen, *a, **k):
            os._exit(0)
        return out
    return lambda: setattr(obj, attr, wrapper)


def nth(n):
    def test(seen, *a, **k):
        seen["n"] += 1
        return seen["n"] == n
    return test


BEGUN = die_when(communal_import, "_apply_locked", lambda seen, *a, **k: True)
STAGED = die_when(agentfs, "_write_beneath", nth(1), "after")
ONE_PUBLISHED = die_when(transfer, "_rename", nth(1), "after")
TEXT_SET = die_when(communal_import, "_set_text", nth(1), "after")
PUBLISHED = die_when(transfer, "_save", lambda seen, rec: rec.get("state") == "published", "after")
HALF_FINISHED = die_when(transfer, "_keep_at", nth(1), "after")


@pytest.mark.parametrize("at,ends", [(BEGUN, "rolled back"), (STAGED, "rolled back"),
                                     (ONE_PUBLISHED, "rolled back"), (TEXT_SET, "rolled back"),
                                     (PUBLISHED, "finished"), (HALF_FINISHED, "finished")])
def test_an_interrupted_import_leaves_both_sides_whole(src, cfg_factory, at, ends):
    was = before_import()
    c = cfg(cfg_factory)
    token = communal_import.plan(str(src), c)["token"]
    crash(at, lambda: communal_import.commit(str(src), token, c))
    assert transfer.pending()
    got = transfer.recover()
    assert [x["done"] for x in got] == [ends]
    assert not transfer.pending()
    names = os.listdir(paths.COMMUNAL_DIR / "skills") if (paths.COMMUNAL_DIR / "skills").exists() else []
    assert not [n for n in names if n.startswith(".t-")]
    if ends == "rolled back":
        assert agentfs.skills("communal") == []
        assert agentfs.read_file("communal", "rules.md")["text"] == "Old rules."
        assert not agentfs.read_file("communal", "rules.md")["changed_outside"]
        live = lambda t: {k: v for k, v in t.items() if k.startswith("communal/")
                          and "/.history" not in k and not k.startswith("communal/.history")}
        assert {k: v for k, v in live(tree(paths.DATA_DIR)).items() if k != "communal/skills"} \
            == live(was)
        assert communal_import.history() == []
    else:
        assert {s["name"] for s in agentfs.skills("communal")} == {"packing", "weekly"}
        assert agentfs.read_file("communal", "defaults.md")["text"] == "Use metric units."
        assert communal_import.history()[0]["state"] == "done"


def test_an_interrupted_undo_leaves_the_import_whole(src, cfg_factory):
    before_import()
    c = cfg(cfg_factory)
    r = communal_import.commit(str(src), communal_import.plan(str(src), c)["token"], c)
    crash(TEXT_SET, lambda: communal_import.undo(r["op"]))
    assert [x["done"] for x in transfer.recover()] == ["rolled back"]
    assert {s["name"] for s in agentfs.skills("communal")} == {"packing", "weekly"}
    assert agentfs.read_file("communal", "rules.md")["text"] == "Ask before deleting anything."
    assert communal_import.history()[0]["undoable"]
    communal_import.undo(r["op"])                         # and it still can be
    assert agentfs.skills("communal") == []


def test_a_text_edited_by_hand_during_an_interrupted_import_is_never_overwritten(src, cfg_factory):
    before_import()
    c = cfg(cfg_factory)
    token = communal_import.plan(str(src), c)["token"]
    crash(TEXT_SET, lambda: communal_import.commit(str(src), token, c))
    path, _ = agentfs._resolve("communal", "rules.md")
    path.write_text("Typed by hand.")
    assert [x["done"] for x in transfer.recover()] == ["stuck"]
    assert path.read_text() == "Typed by hand."
    assert communal_import.history()[0]["state"] == "stuck"


def test_a_forged_import_record_is_never_acted_on(src, cfg_factory):
    d = transfer.journal_dir(create=True)
    op = transfer._new_op()
    (d / f"{op}.open.json").write_text(json.dumps({
        "v": 1, "op": op, "kind": "import", "action": "import", "name": "communal",
        "from": "outside", "to": "communal", "undo_of": "", "state": "begun",
        "texts": [{"file": "../../.bashrc", "old": "", "new": ""}], "skills": []}))
    got = transfer.recover()
    assert got and got[0]["done"].startswith("set aside")


def test_records_this_module_writes_are_valid_and_odd_ones_are_not():
    good = {"v": 1, "op": "1" * 19 + "-deadbeef", "kind": "import", "action": "import",
            "name": "communal", "from": "outside", "to": "communal", "undo_of": "",
            "state": "begun", "texts": [{"file": "rules.md", "old": "", "new": "a" * 64}],
            "skills": [{"name": "weekly", "digest": "b" * 64, "add": True}]}
    assert communal_import.valid(good)
    for bad in ({**good, "action": "move"}, {**good, "undo_of": "1" * 19 + "-deadbeef"},
                {**good, "skills": [{"name": "../x", "digest": "b" * 64, "add": True}]},
                {**good, "texts": [{"file": "instructions.md", "old": "", "new": ""}]},
                {**good, "to": "sora"}, {**good, "state": "whatever"}):
        assert not communal_import.valid(bad), bad


# --- the CLI and the guard -------------------------------------------------------------------

def run_cli(*args, data):
    """`data` is XDG_DATA_HOME/agentvoice; the settings are a scratch folder's
    (none), never the real shell.json."""
    env = {**os.environ, "XDG_DATA_HOME": str(data.parent), "PYTHONDONTWRITEBYTECODE": "1",
           "XDG_CONFIG_HOME": str(data.parent.parent / "config")}
    return subprocess.run([sys.executable, str(ROOT / "daemon" / "agentfs.py"), *args],
                          capture_output=True, text=True, env=env, timeout=60)


def test_the_cli_dry_run_then_confirm(src, tmp_path):
    real = tmp_path / "xdg"
    out = run_cli("import", "communal", str(src), "--json", data=real / "agentvoice")
    assert out.returncode == 0, out.stderr
    plan = json.loads(out.stdout)
    assert plan["changes"] == 4
    out = run_cli("import", "communal", str(src), "--confirm", plan["token"], "--json",
                  data=real / "agentvoice")
    assert out.returncode == 0, out.stderr
    done = json.loads(out.stdout)
    assert (real / "agentvoice" / "communal" / "skills" / "weekly" / "SKILL.md").is_file()
    out = run_cli("import-history", "--json", data=real / "agentvoice")
    assert json.loads(out.stdout)[0]["op"] == done["op"]
    out = run_cli("import", "sora", str(src), data=real / "agentvoice")
    assert out.returncode == 1 and "only communal" in out.stderr


@pytest.mark.parametrize("cmd", [
    "agentvoice agents import communal ~/Downloads/x --confirm 0123456789abcdef0123456789abcdef",
    "agentvoice  agents  import communal /tmp/x",
    "agentvoice agents import-undo 1234567890123456789-deadbeef",
    "python3 ~/.local/share/agentvoice/app/daemon/communal_import.py",
    "python3 daemon/agentfs.py import communal /tmp/x",
])
def test_an_agent_importing_is_asked_at_every_level(cmd, monkeypatch):
    assert hook.orders_write("Bash", {"command": cmd}), cmd
    monkeypatch.setattr(hook, "_ask", lambda *a, **k: ("asked", k.get("note", "")))
    assert hook.decide("Bash", {"command": cmd})[0] == "asked"


@pytest.mark.parametrize("cmd", ["agentvoice agents import-history --json",
                                 "agentvoice agents prompt sora --json",
                                 "agentvoice agents version communal rules.md 1-x.md"])
def test_reading_imports_prompts_and_versions_is_not_asked(cmd):
    assert hook.orders_write("Bash", {"command": cmd}) == "", cmd


# --- history -------------------------------------------------------------------------------------

def test_a_version_shows_its_text_and_the_diff_to_now():
    agentfs.write("communal", "rules.md", "First rule.")
    agentfs.write("communal", "rules.md", "Second rule.")
    old, new = [v["version"] for v in reversed(agentfs.history("communal", "rules.md"))]
    v = agentfs.version("communal", "rules.md", old)
    assert v["text"] == "First rule." and not v["same"]
    assert "-First rule." in v["diff"] and "+Second rule." in v["diff"]
    assert agentfs.version("communal", "rules.md", new)["same"]
    with pytest.raises(agentfs.AgentFsError):
        agentfs.version("communal", "rules.md", "../../etc")
    with pytest.raises(agentfs.AgentFsError):
        agentfs.version("communal", "role.md", old)
    # Restore is the existing revert, on a base; history then holds both.
    stamp = agentfs.read_file("communal", "rules.md")["stamp"]
    agentfs.revert("communal", "rules.md", old, base=stamp)
    assert agentfs.read_file("communal", "rules.md")["text"] == "First rule."
    assert agentfs.version("communal", "rules.md", new)["text"] == "Second rule."


def test_a_long_diff_is_cut_and_counted():
    lines = agentfs.diff_lines("\n".join(map(str, range(1000))), "")
    assert len(lines) == agentfs.DIFF_LINES + 1 and lines[-1].startswith("… and ")


# --- the page (read, not run: CLAUDE.md) ------------------------------------------------------

PAGE = (ROOT / "pages" / "CommunalPage.qml").read_text()
HISTORY = (ROOT / "ui" / "FileHistory.qml").read_text()
IMPORT = (ROOT / "ui" / "CommunalImport.qml").read_text()


def test_history_restores_only_on_the_editors_stamp_and_never_writes():
    assert '"agents", "revert", target, file, v' in HISTORY and '"--base"' in HISTORY
    assert '"agents", "write"' not in HISTORY
    # Restore waits while the file was changed outside Settings.
    assert "enabled: !fh.busy && !fh.outside" in HISTORY
    assert PAGE.count("FileHistory {") == 2


def test_the_import_commits_only_from_its_confirm_with_the_dry_runs_token():
    body = IMPORT[IMPORT.index("function commitImport()"):IMPORT.index("function undoImport()")]
    assert '"--confirm", String(planned.token)' in body and "canImport()" in body
    confirm = IMPORT[IMPORT.index("ToolConfirm {"):]
    assert "onConfirmed: imp.commitImport()" in confirm[:1200]
    # Defined, and called from the confirm alone (the header comment names it).
    assert IMPORT.count("imp.commitImport()") == 1 and IMPORT.count("function commitImport()") == 1


def test_the_who_page_writes_a_clean_list_and_says_what_it_cannot_do():
    fn = PAGE[PAGE.index("function setTakes"):PAGE.index("property string freshNote")]
    assert "known.indexOf(x) >= 0" in fn                   # a removed agent's id is dropped
    assert "communalOffReadable ? page.communalOffRaw : []" in fn
    assert "Communal notes stay reachable" in PAGE and "Start fresh" in PAGE
    assert '["agentvoice", "chats", "new", id]' in PAGE
    # Every one of the new texts is plain.
    for body in (HISTORY, IMPORT):
        assert body.count("Text {") == body.count("textFormat: Text.PlainText")


def test_the_preview_tab_draws_the_real_builders_pieces():
    assert '["agentvoice", "agents", "prompt", page.previewAgent, "--json"]' in PAGE
    assert "how: x.precedence, chars: x.chars" in PAGE


def test_the_preview_stub_routes_chats_new_away_from_the_real_daemon():
    stub = (ROOT / "bench" / "preview" / "preview.sh").read_text()
    assert '"\\${2:-}" = new ]; then printf' in stub
