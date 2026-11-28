"""Phase M31: Communal as a grouping of skills, and the two screens that
show it (the user's decisions of 2026-11-27, phaseM30notes.md).

- A skill every agent that takes skills already has is communal by itself
  (two agents at least); `communalSkills` adds others ("add") and keeps one
  out of that rule ("remove") until it is added back.
- Communal is a grouping. It copies nothing and gives or withholds nothing:
  an agent whose program lacks a communal skill does not get it, and the
  row names who that is. Each agent's Exclude is its `skillsOff`, as before.
- An agent opted out of Communal (M15) has no "From communal" section; its
  skills are its own. Removing an automatic one switches nothing off.
- The setting's three homes: manifest, runtime.DEFAULTS, Communal → Skills.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import agentfs
import skillscan
from qml_scan import overlay_qml, scan
from test_skillscan import claude_home, codex_home, machine, own, write_skill  # noqa: F401
from test_skillscan import data  # noqa: F401 -- the autouse scratch data folder
from test_tool_controls import function_source
from test_transfer_ui import calls_of

ROOT = Path(__file__).resolve().parent.parent
COMMUNAL = ROOT / "pages" / "CommunalPage.qml"
DETAILS = ROOT / "pages" / "AgentDetailsPage.qml"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


def crew(cfg_factory, main_off=None, sora=None, hazel=None, **kw):
    """Theo (Claude Code), Sora (Claude Code) and Hazel (Codex), as on the
    user's machine when M31 was decided."""
    return cfg_factory(mainProgram="claude", mainName="Theo", mainSkillsOff=main_off or [], voiceAgents=[
        {"name": "sora", "id": "sora", "agent": "claude", **(sora or {})},
        {"name": "hazel", "id": "hazel", "agent": "codex", **(hazel or {})}], **kw)


def everywhere(tmp_path):
    """The synthetic machine, plus one skill both programs have
    (omarchy-app, linked into ~/.claude/skills; a copy in ~/.codex/skills)."""
    machine(tmp_path)
    write_skill(codex_home() / "skills" / "omarchy-app", "omarchy-app", desc="Build an Omarchy app.")


def rows(cfg) -> dict:
    return {r["name"]: r for r in skillscan.grouping(cfg)["rows"]}


# --- the setting -----------------------------------------------------------------

@pytest.mark.parametrize("raw, want", [
    (None, {"add": [], "remove": []}),
    ({}, {"add": [], "remove": []}),
    ({"add": ["weekly"]}, {"add": ["weekly"], "remove": []}),
    ({"add": ["a", "a", "tidy:format"], "remove": ["b"]}, {"add": ["a", "tidy:format"], "remove": ["b"]}),
    ({"add": None, "remove": None}, {"add": [], "remove": []}),
    (["weekly"], None), ("weekly", None), ({"add": "weekly"}, None), ({"keep": []}, None),
    ({"add": ["../x"]}, None), ({"add": [5]}, None), ({"add": ["a"], "remove": ["a"]}, None),
    ({"add": ["x"] * 257}, None), ({"remove": [{"n": 1}]}, None)])
def test_communal_skills_is_two_lists_of_names_or_unreadable(raw, want):
    from runtime import communal_skills_choice
    assert communal_skills_choice(raw) == want


def test_unreadable_settings_read_as_unknown(cfg_factory, monkeypatch):
    cfg = cfg_factory(communalSkills={"add": ["x"]})
    assert cfg.communal_skills() == {"add": ["x"], "remove": []}
    monkeypatch.setattr(type(cfg), "settings_readable", lambda self: False)
    assert cfg.communal_skills() is None


def test_the_setting_has_its_three_homes():
    from runtime import DEFAULTS
    manifest = json.loads((ROOT / "manifest.json").read_text())
    assert manifest["barWidget"]["defaults"]["communalSkills"] == {}
    assert DEFAULTS["communalSkills"] == {}
    # One page writes it, and only from setCommunal.
    writers = [p.name for p in overlay_qml() if 'put("communalSkills"' in scan(p).nocomment]
    assert writers == ["CommunalPage.qml"]
    assert scan(COMMUNAL).nocomment.count('put("communalSkills"') == 1
    assert 'page.s.put("communalSkills", next)' in function_source(COMMUNAL, "setCommunal")


# --- who has what ---------------------------------------------------------------------

def test_a_skill_every_agent_has_is_communal_by_itself(cfg_factory, tmp_path):
    everywhere(tmp_path)
    got = rows(crew(cfg_factory))
    app = got["omarchy-app"]
    assert app["auto"] and app["communal"] and not app["added"]
    assert app["has"] == ["Theo", "Sora", "Hazel"] and app["lacks"] == []
    assert sorted(app["sources"]) == ["~/.claude/skills", "~/.codex/skills"]
    # Only the two Claude agents have weekly: not communal, and Hazel named.
    weekly = got["weekly"]
    assert not weekly["auto"] and not weekly["communal"]
    assert weekly["has"] == ["Theo", "Sora"]
    assert weekly["lacks"] == [{"label": "Hazel", "why": "Codex has no skill of this name"}]


def test_a_communal_folder_skill_is_one_every_agent_has(cfg_factory, tmp_path):
    machine(tmp_path)
    own("communal", "house-style")
    got = rows(crew(cfg_factory))["house-style"]
    assert got["auto"] and got["communal"] and got["folder"] is True
    assert got["sources"] == ["communal folder"]


def test_an_excluded_skill_is_still_had_and_said_to_be_excluded(cfg_factory, tmp_path):
    everywhere(tmp_path)
    got = rows(crew(cfg_factory, sora={"skillsOff": ["omarchy-app"]}))["omarchy-app"]
    assert got["auto"] and got["communal"]
    assert got["excluded"] == ["Sora"] and "Sora" in got["has"]


def test_a_skill_off_in_the_programs_own_settings_is_not_had(cfg_factory, tmp_path):
    everywhere(tmp_path)
    settings = json.loads((claude_home() / "settings.json").read_text())
    settings["skillOverrides"] = {"omarchy-app": "off"}
    (claude_home() / "settings.json").write_text(json.dumps(settings))
    got = rows(crew(cfg_factory))["omarchy-app"]
    assert not got["auto"] and not got["communal"]
    assert got["has"] == ["Hazel"]
    assert {x["why"] for x in got["lacks"]} == {"switched off in your own Claude Code settings"}


def test_a_second_copy_of_a_name_is_one_skill(cfg_factory, tmp_path):
    everywhere(tmp_path)
    # ~/.agents/skills holds a second omarchy-app for Codex (Omarchy links
    # its skills into both): still one row, Hazel counted once.
    write_skill(skillscan.agents_dir(skillscan.roots()) / "omarchy-app", "omarchy-app")
    got = skillscan.grouping(crew(cfg_factory))["rows"]
    assert [r["name"] for r in got].count("omarchy-app") == 1
    assert {r["name"]: r for r in got}["omarchy-app"]["has"] == ["Theo", "Sora", "Hazel"]


def test_an_agent_that_takes_no_skills_is_not_counted(cfg_factory, tmp_path):
    machine(tmp_path)
    got = rows(crew(cfg_factory, hazel={"agent": "endpoint"}))["weekly"]
    # Theo and Sora are the agents that count, and both have it.
    assert got["auto"] and got["communal"]
    assert got["lacks"] == [{"label": "Hazel", "why": "takes no skills"}]


def test_an_opted_out_agent_is_not_counted(cfg_factory, tmp_path):
    machine(tmp_path)
    got = rows(crew(cfg_factory, communalOff=["hazel"]))["weekly"]
    assert got["auto"] and got["communal"]
    assert got["lacks"] == [{"label": "Hazel", "why": "takes nothing from Communal"}]


def test_a_switched_off_agent_still_counts(cfg_factory, tmp_path):
    machine(tmp_path)
    got = rows(crew(cfg_factory, hazel={"enabled": False}))["weekly"]
    assert not got["auto"] and "Hazel" in [x["label"] for x in got["lacks"]]


def test_one_agent_alone_makes_nothing_communal(cfg_factory, tmp_path):
    machine(tmp_path)
    cfg = cfg_factory(mainProgram="claude", voiceAgents=[])
    assert not any(r["communal"] for r in skillscan.grouping(cfg)["rows"])


@pytest.mark.parametrize("have, n_counted, want", [
    ({"a": {"x"}, "b": {"x"}}, 2, True), ({"a": {"x"}, "b": set()}, 2, False),
    ({"a": {"x"}}, 1, False), ({}, 0, False)])
def test_is_auto(have, n_counted, want):
    agents = [{"id": i, "delivery": "plugin", "takes_communal": True} for i in list(have)[:n_counted]]
    holders = {k: {n: {} for n in v} for k, v in have.items()}
    assert skillscan.is_auto("x", holders, agents) is want


# --- add and remove -------------------------------------------------------------------

def test_adding_a_skill_makes_it_communal_and_gives_it_to_nobody_new(cfg_factory, tmp_path):
    machine(tmp_path)
    got = rows(crew(cfg_factory, communalSkills={"add": ["weekly"]}))["weekly"]
    assert got["communal"] and got["added"] and not got["auto"]
    assert got["has"] == ["Theo", "Sora"] and got["lacks"][0]["label"] == "Hazel"


def test_removing_an_automatic_one_keeps_it_out_until_added_back(cfg_factory, tmp_path):
    everywhere(tmp_path)
    got = rows(crew(cfg_factory, communalSkills={"remove": ["omarchy-app"]}))["omarchy-app"]
    assert got["auto"] and got["removed"] and not got["communal"]
    got = rows(crew(cfg_factory, communalSkills={"add": ["omarchy-app"]}))["omarchy-app"]
    assert got["communal"]


def test_a_skill_only_in_one_agents_folder_is_lacked_for_that_reason(cfg_factory, tmp_path):
    machine(tmp_path)
    own("sora", "tea-timer")
    got = rows(crew(cfg_factory))["tea-timer"]
    assert got["has"] == ["Sora"] and got["sources"] == ["Sora's folder"]
    assert got["lacks"] == [{"label": "Theo", "why": "not in its skills folder"},
                            {"label": "Hazel", "why": "not in its skills folder"}]


@needs_node
def test_lacks_are_grouped_by_why():
    fns = function_source(COMMUNAL, "lacksText")
    got = _node(fns, 'lacksText([{label: "Theo", why: "a"}, {label: "Sora", why: "a"}, '
                     '{label: "Hazel", why: "b"}])')
    assert got == "Theo or Sora (a); Hazel (b)"


def test_an_added_name_nobody_has_is_still_listed(cfg_factory, tmp_path):
    machine(tmp_path)
    got = rows(crew(cfg_factory, communalSkills={"add": ["gone-now"]}))["gone-now"]
    assert got["communal"] and got["has"] == [] and len(got["lacks"]) == 3


def test_unreadable_is_the_automatic_rule_alone(cfg_factory, tmp_path):
    everywhere(tmp_path)
    got = skillscan.grouping(crew(cfg_factory, communalSkills={"add": "weekly"}))
    assert got["readable"] is False
    names = {r["name"]: r for r in got["rows"]}
    assert names["omarchy-app"]["communal"] and not names["weekly"]["communal"]


def _delivery(cfg):
    """Everything each agent is actually given: the names switched off
    where its CLI looks, what its tab marks delivered, and for the Claude
    agents the skills in the plugin folder made for it."""
    found = skillscan.scan()["skills"]
    out = {}
    for agent_id, program in (("", "claude"), ("sora", "claude"), ("hazel", "codex")):
        me = agent_id or agentfs.MAIN
        off = cfg.skills_off_for(agent_id)
        view = skillscan.agent_view(program, off, agentfs.skills(me), agentfs.skills(agentfs.COMMUNAL),
                                    found, agentfs.delivery_of(program)[0], cfg.takes_communal(me))
        folder = agentfs.plugin_dir(me, None, off, None, cfg.takes_communal(me)) \
            if program == "claude" else None
        out[me] = (skillscan.native_off(cfg, agent_id, program),
                   sorted((s["name"], s["source"], s["delivered"]) for s in view),
                   sorted(q.name for q in (Path(folder) / "skills").iterdir()) if folder else None)
    return out


@pytest.mark.parametrize("setting", [
    {"add": ["weekly", "deploy", "crash", "nobody-has-it"]},
    {"remove": ["omarchy-app", "house-style"]},
    {"add": "unreadable"}])
def test_communal_is_a_grouping_that_gives_and_withholds_nothing(cfg_factory, tmp_path, setting):
    everywhere(tmp_path)
    own("communal", "house-style")
    own("sora", "tea-timer")
    before = _delivery(crew(cfg_factory, sora={"skillsOff": ["docx"]}))
    after = _delivery(crew(cfg_factory, sora={"skillsOff": ["docx"]}, communalSkills=setting))
    assert before == after


def test_nothing_outside_the_grouping_reads_the_setting():
    """Only the grouping (and the pages through it) reads communalSkills:
    no adapter, prompt builder or plugin folder can be changed by it."""
    readers = []
    for path in sorted((ROOT / "daemon").glob("*.py")):
        src = path.read_text()
        if "communal_skills(" in src or '"communalSkills"' in src:
            readers.append(path.name)
    assert readers == ["runtime.py", "skillscan.py"]


# --- one agent's tab ------------------------------------------------------------------

def test_cards_are_one_per_name_in_two_sections():
    entries = [
        {"name": "weekly", "source": "communal", "delivered": False, "why": "its own of the same name is given instead"},
        {"name": "weekly", "source": "sora", "delivered": True, "why": ""},
        {"name": "app", "source": "codex-user", "native": True, "source_label": "~/.codex/skills",
         "delivered": True, "why": ""},
        {"name": "app", "source": "agents", "native": True, "source_label": "~/.agents/skills",
         "delivered": False, "why": "the one in ~/.codex/skills is offered instead"},
        {"name": "solo", "source": "sora", "delivered": True, "why": ""}]
    got = {c["name"]: c for c in skillscan.cards(entries, {"weekly", "app"}, True)}
    assert list(got) == ["weekly", "app", "solo"]
    assert got["weekly"]["source"] == "sora" and got["weekly"]["section"] == "communal"
    assert got["weekly"]["also"] == [{"where": "communal folder",
                                      "why": "its own of the same name is given instead"}]
    assert got["app"]["source"] == "codex-user" and got["app"]["also"][0]["where"] == "~/.agents/skills"
    assert got["solo"]["section"] == "own"
    # An agent opted out of Communal: every card is its own.
    assert {c["section"] for c in skillscan.cards(entries, {"weekly", "app"}, False)} == {"own"}


def test_the_catalog_puts_communal_skills_first_with_exclude_as_skills_off(cfg_factory, tmp_path):
    everywhere(tmp_path)
    own("sora", "tea-timer")
    cfg = crew(cfg_factory, sora={"skillsOff": ["omarchy-app"]})
    cat = agentfs.catalog("sora", cfg)
    cards = {c["name"]: c for c in cat["skill_cards"]}
    assert cards["omarchy-app"]["section"] == "communal"
    assert cards["omarchy-app"]["on"] is False and cards["omarchy-app"]["delivered"] is False
    assert cards["tea-timer"]["section"] == "own" and cards["weekly"]["section"] == "own"
    assert cat["communal_readable"] is True
    assert "skill_lanes" not in cat              # no other agent's lanes (M31)
    assert len(cards) == len(cat["skill_cards"])


def test_an_opted_out_agents_tab_has_no_communal_section(cfg_factory, tmp_path):
    everywhere(tmp_path)
    cat = agentfs.catalog("sora", crew(cfg_factory, communalOff=["sora"]))
    assert {c["section"] for c in cat["skill_cards"]} == {"own"}
    assert any(c["name"] == "omarchy-app" and c["delivered"] for c in cat["skill_cards"])


def test_removing_an_automatic_one_returns_it_to_each_agents_own_still_on(cfg_factory, tmp_path):
    everywhere(tmp_path)
    for agent in ("main", "sora", "hazel"):
        cfg = crew(cfg_factory, communalSkills={"remove": ["omarchy-app"]})
        card = {c["name"]: c for c in agentfs.catalog(agent, cfg)["skill_cards"]}["omarchy-app"]
        assert card["section"] == "own" and card["on"] is True and card["delivered"] is True, agent


def test_the_cli_reads_the_grouping(cfg_factory, tmp_path, monkeypatch, capsys):
    everywhere(tmp_path)
    import runtime
    monkeypatch.setattr(runtime, "Config", lambda: crew(cfg_factory))
    assert skillscan.main(["communal", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert {r["name"] for r in got["rows"] if r["communal"]} == {"omarchy-app"}
    assert [a["label"] for a in got["agents"]] == ["Theo", "Sora", "Hazel"]
    assert skillscan.main(["communal"]) == 0
    assert "communal  omarchy-app (every agent has it)" in capsys.readouterr().out


def test_reading_the_grouping_is_not_asked():
    import permission_hook as hook
    assert hook.orders_write("Bash", {"command": "agentvoice skills communal --json"}) == ""


# --- the pages ------------------------------------------------------------------------

def test_communal_is_changed_only_from_a_confirm():
    got = calls_of(COMMUNAL, "setCommunal")
    assert got == [("onConfirmed", "ToolConfirm"), ("onConfirmed", "ToolConfirm")], got
    for path in overlay_qml():
        if path != COMMUNAL:
            assert "setCommunal" not in scan(path).nocomment, path.name
    # Remove and the switch only ask.
    asks = {h for h, _ in calls_of(COMMUNAL, "askCommunal")}
    assert asks == {"onClicked", "onToggled"}
    assert "put(" not in function_source(COMMUNAL, "askCommunal")


def test_the_confirms_say_who_has_it_and_that_nothing_is_copied_or_switched_off():
    fn = function_source(COMMUNAL, "confirmLines")
    assert '"Who has it"' in fn and '"Who doesn\'t"' in fn
    assert "No agent is given a copy" in fn and "Nothing is switched off" in fn
    assert "stays out of Communal until you add it back" in fn


def test_exclude_on_agent_details_is_its_skills_off_switch():
    src = scan(DETAILS).nocomment
    assert 'text: modelData.on === true ? "Exclude" : "Include again"' in src
    assert "onClicked: page.switchSkill(modelData.name, modelData.on !== true)" in src
    # Only this agent: its own two sections, nothing of another agent's.
    for gone in ("skill_lanes", "otherLanes", "unused", "Unused"):
        assert gone not in src, gone
    assert 'objectName: "fromCommunal"' in src and 'objectName: "ownSkills"' in src


def test_communal_skills_has_a_search_and_a_switch_per_skill():
    src = scan(COMMUNAL).nocomment
    assert 'placeholder: "Search skills"' in src
    assert "onToggled: function(on) { page.askCommunal(modelData, on, \"all\") }" in src
    assert 'text: "Remove…"' in src


@pytest.mark.parametrize("path", [COMMUNAL, DETAILS])
def test_new_skill_text_is_plain(path):
    """A skill's name and description are whatever its author wrote."""
    src = scan(path).src
    start = src.index("communalRows" if path == COMMUNAL else "Phase M31: only this agent")
    src = src[:src.index("--- Notes (Phase 14)", start)]
    for m in re.finditer(r"\bText \{", src[start:]):
        body = src[start + m.start():start + m.start() + 700]
        assert "textFormat: Text.PlainText" in body or 'text: "' in body.split("\n")[1] \
            or body.split("\n")[3].strip().startswith('text: "'), body[:200]


def _node(fn_src: str, call: str):
    out = subprocess.run([NODE, "-e", fn_src + "\nconsole.log(JSON.stringify(" + call + "));"],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@needs_node
@pytest.mark.parametrize("cur, name, on, auto, want", [
    ({}, "weekly", True, False, {"add": ["weekly"], "remove": []}),
    (None, "weekly", True, False, {"add": ["weekly"], "remove": []}),
    ({"add": ["weekly"]}, "weekly", False, False, {"add": [], "remove": []}),
    ({}, "app", False, True, {"add": [], "remove": ["app"]}),
    ({"remove": ["app"]}, "app", True, True, {"add": [], "remove": []}),
    ({"add": ["app"]}, "app", False, True, {"add": [], "remove": ["app"]}),
    ({"add": ["x"], "remove": ["y"]}, "z", True, False, {"add": ["x", "z"], "remove": ["y"]}),
    ({"add": "weekly"}, "z", True, False, None),
    ({"add": ["a"], "remove": ["a"]}, "z", True, False, None),
    ({"other": []}, "z", True, False, None),
    (["weekly"], "z", True, False, None),
    ({}, "../x", True, False, None),
    ({}, "x", "yes", False, None)])
def test_communal_edited(cur, name, on, auto, want):
    fn = function_source(COMMUNAL, "communalEdited")
    assert _node(fn, f"communalEdited({json.dumps(cur)}, {json.dumps(name)}, {json.dumps(on)}, "
                     f"{json.dumps(auto)})") == want


# --- Codex review, pass 1 ---------------------------------------------------------

def test_a_failed_scan_still_groups_agent_voices_own_skills(cfg_factory, tmp_path, monkeypatch):
    """The catalog's fallback for a scan that raised has no timing in it;
    the grouping of the folders it could read must not fail on that."""
    own("main", "lint")
    own("sora", "lint")
    cfg = crew(cfg_factory, hazel={"agent": "endpoint"})

    def broken():
        raise OSError("no")
    monkeypatch.setattr(skillscan, "scan", broken)
    cat = agentfs.catalog("sora", cfg)
    assert cat["skills_error"].startswith("the skill scan failed")
    assert {c["name"]: c["section"] for c in cat["skill_cards"]}["lint"] == "communal"


def test_a_communal_skill_the_agents_program_switched_off_is_its_own(cfg_factory, tmp_path):
    everywhere(tmp_path)
    settings = json.loads((claude_home() / "settings.json").read_text())
    settings["skillOverrides"] = {"weekly": "off"}
    (claude_home() / "settings.json").write_text(json.dumps(settings))
    cfg = crew(cfg_factory, communalSkills={"add": ["weekly"]})
    assert rows(cfg)["weekly"]["communal"]
    card = {c["name"]: c for c in agentfs.catalog("sora", cfg)["skill_cards"]}["weekly"]
    assert card["section"] == "own" and card["delivered"] is False


def test_keep_comes_from_the_communal_folders_copy(cfg_factory, tmp_path):
    machine(tmp_path)
    own("main", "lint")
    own("communal", "lint")
    got = rows(crew(cfg_factory))["lint"]
    assert got["folder"] is True
    assert got["stamp"] == {s["name"]: s for s in agentfs.skills(agentfs.COMMUNAL)}["lint"]["stamp"]
    assert got["changed_outside"] is True        # written by hand, as a person would


def test_a_name_nobody_has_is_kept_out_of_all_skills():
    src = scan(COMMUNAL).nocomment
    assert "var all = page.heldRows" in src
    assert "(r.has || []).length > 0" in src
    assert "page.heldRows.length" in src


def test_the_confirm_checks_readability_again_when_it_writes():
    fn = function_source(COMMUNAL, "setCommunal")
    assert fn.index("if (!page.skillsReadable)") < fn.index('page.s.put("communalSkills"')
    assert "onSkillsReadableChanged: if (!skillsReadable) skillAsking = \"\"" in scan(COMMUNAL).nocomment
