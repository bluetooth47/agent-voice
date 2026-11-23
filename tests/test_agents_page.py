"""The Agents page (master plan M5): one block for every agent, and the
writes it makes.

`voiceAgents` is one setting holding every extra agent, written whole: an
edit to one field of one agent rewrites the list. So the page's save path is
the most fragile thing in the overlay -- a copy that dropped a field it did
not know, or touched a neighbour, would lose settings with nothing on screen
to say so. These tests *run* that path rather than read it: the functions
are taken out of AgentsPage.qml as they are and executed in node, with a
stub for the overlay, and what they would save is compared byte for byte
with what was there.

node is not a dependency of the project. GitHub's runners have it, and so
does any machine with the plugin's development tools; where it is missing
these tests say so and skip (CLAUDE.md: a test that cannot run must be
honest that it is skipping).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from qml_scan import scan

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "pages" / "AgentsPage.qml"

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed, so the page's JavaScript cannot be run")


def function_source(path: Path, name: str, src: str | None = None) -> str:
    """`function name(...) { ... }` as written in a QML file, found with the
    same brace matching the other QML tests use."""
    s = scan(path)
    text = s.src if src is None else src
    m = re.search(r"\bfunction " + re.escape(name) + r"\(", s.clean)
    assert m, f"{path.name} has no function {name}"
    brace = s.clean.index("{", m.end())
    return text[m.start():s.closes[brace] + 1]


def run_js(script: str):
    out = subprocess.run([NODE], input=script, capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


PAGE_FUNCTIONS = ["copyEntry", "mapValue", "putMap", "setLevel", "setModel", "setEffort", "saveAgents",
                  "updateAgent", "putAgentNotes",
                  "putAgentCollab", "putAgentAccepts", "writeField",
                  "putMainEndpoint", "runOn"]


def harness(agents, settings, calls, replace: dict[str, str] | None = None) -> list:
    """Run `calls` (JavaScript statements) against the page's functions, one
    fresh overlay per call, and return what each call wrote."""
    fns = []
    for name in PAGE_FUNCTIONS:
        src = function_source(PAGE, name)
        fns.append((replace or {}).get(name, src))
    agent_id = function_source(ROOT / "Settings.qml", "agentId")
    script = f"""
{agent_id}
{chr(10).join(fns)}
var AGENTS = JSON.parse({json.dumps(json.dumps(agents))});
var SETTINGS = {json.dumps(settings)};
var CALLS = {json.dumps(calls)};
var s, page, results = [];
for (var c = 0; c < CALLS.length; c++) {{
  s = {{
    voiceAgents: JSON.parse(JSON.stringify(AGENTS)),
    puts: [], chose: [],
    put: function(k, v) {{ this.puts.push([k, JSON.parse(JSON.stringify(v === undefined ? null : v))]) }},
    setting: function(k, d) {{ return Object.prototype.hasOwnProperty.call(SETTINGS, k) ? SETTINGS[k] : d }},
    chooseVoice: function(v) {{ this.chose.push(v) }},
    agentId: agentId
  }};
  page = {{ s: s, main: "claude", endpointChosen: false, mainProgram: "" }};
  eval(CALLS[c]);
  results.push({{ puts: s.puts, chose: s.chose, endpointChosen: page.endpointChosen }});
}}
console.log(JSON.stringify(results));
"""
    return run_js(script)


# Three agents with everything a saved entry can hold, and some it cannot
# yet: a field from a newer build, a nested object, unicode, a number.
AGENTS = [
    {"id": "sora", "name": "sora", "label": "Sora ☀", "agent": "claude", "model": "sonnet",
     "effort": "medium", "voice": "amy-medium", "speed": 0, "narration": "", "level": "ask",
     "projectDir": "", "tools": {"desktop": "on"}, "collaboration": "ask", "notesWrite": "deny",
     "acceptsWork": False, "futureField": {"kept": [1, 2.5, None]}},
    {"id": "hazel", "name": "hazel", "label": "Hazel", "agent": "codex", "level": "trusted",
     "projectDir": "~/p/hazel", "speed": 120, "instructions": "old, pre-folder"},
    {"id": "echo-local", "name": "echo", "agent": "endpoint", "endpointUrl": "http://localhost:11434/v1",
     "endpointModel": "llama3.2", "endpointIsAgent": False, "endpointTimeoutS": 0,
     "endpointHistoryTurns": 8, "enabled": False, "level": "ask"},
]

# (call, field, expected value; None means the field is removed)
EXTRA_WRITES = [
    ('writeField(I, "enabled", false)', "enabled", False),
    ('writeField(I, "enabled", true)', "enabled", True),
    ('writeField(I, "label", "Renamed")', "label", "Renamed"),
    ('writeField(I, "name", "zed")', "name", "zed"),
    ('writeField(I, "agent", "gemini")', "agent", "gemini"),
    ('writeField(I, "model", "opus")', "model", "opus"),
    ('writeField(I, "effort", "high")', "effort", "high"),
    ('writeField(I, "level", "edits")', "level", "edits"),
    ('writeField(I, "voice", "joe-medium")', "voice", "joe-medium"),
    ('writeField(I, "speed", 135)', "speed", 135),
    ('writeField(I, "narration", "brief")', "narration", "brief"),
    ('writeField(I, "projectDir", "~/elsewhere")', "projectDir", "~/elsewhere"),
    ('writeField(I, "notesWrite", "deny")', "notesWrite", "deny"),
    ('writeField(I, "notesWrite", "allow")', "notesWrite", None),
    ('writeField(I, "collaboration", "off")', "collaboration", "off"),
    ('writeField(I, "collaboration", "announce")', "collaboration", None),
    ('writeField(I, "acceptsWork", false)', "acceptsWork", False),
    ('writeField(I, "acceptsWork", true)', "acceptsWork", None),
    ('updateAgent(I, "endpointUrl", "https://api.example.com/v1")', "endpointUrl", "https://api.example.com/v1"),
    ('updateAgent(I, "endpointModel", "m")', "endpointModel", "m"),
    ('updateAgent(I, "endpointIsAgent", true)', "endpointIsAgent", True),
    ('updateAgent(I, "endpointTimeoutS", 30)', "endpointTimeoutS", 30),
    ('updateAgent(I, "endpointHistoryTurns", 2)', "endpointHistoryTurns", 2),
]


def _expect_one_field_changed(before: dict, after: dict, field: str, want) -> list[str]:
    wrong = []
    rest_before = [(k, v) for k, v in before.items() if k != field]
    rest_after = [(k, v) for k, v in after.items() if k != field]
    if json.dumps(rest_before) != json.dumps(rest_after):
        wrong.append(f"other fields changed: {rest_before} -> {rest_after}")
    if want is None:
        if field in after:
            wrong.append(f"{field} kept as {after[field]!r}")
    elif json.dumps(after.get(field)) != json.dumps(want):
        wrong.append(f"{field} = {after.get(field)!r}, wanted {want!r}")
    return wrong


def _check_extra_writes(results, calls, agents=None) -> list[str]:
    AGENTS_ = AGENTS if agents is None else agents
    wrong = []
    for (index, (call, field, want)), r in zip(calls, results):
        puts = r["puts"]
        if [k for k, _ in puts] != ["voiceAgents"]:
            wrong.append(f"{call} @ {index}: wrote {[k for k, _ in puts]}")
            continue
        saved = puts[0][1]
        if len(saved) != len(AGENTS_):
            wrong.append(f"{call} @ {index}: {len(saved)} agents saved")
            continue
        for j, (old, new) in enumerate(zip(AGENTS_, saved)):
            if j == index:
                for w in _expect_one_field_changed(old, new, field, want):
                    wrong.append(f"{call} @ {index}: {w}")
            elif json.dumps(old) != json.dumps(new):
                wrong.append(f"{call} @ {index}: agent {j} changed: {old} -> {new}")
    return wrong


def _extra_calls():
    return [(i, w) for i in range(len(AGENTS)) for w in EXTRA_WRITES]


@needs_node
def test_saving_one_field_of_one_agent_leaves_everything_else_byte_identical():
    """The data-loss guard for voiceAgents: every field the page writes, on
    every agent, changes that field of that agent and nothing else --
    unknown fields, nested objects, key order and the neighbours included."""
    calls = _extra_calls()
    results = harness(AGENTS, {}, [c.replace("I", str(i), 1) for i, (c, _, _) in calls])
    assert _check_extra_writes(results, calls) == []


def test_the_page_no_longer_writes_an_agents_tools():
    """Phase M10: an agent's own tool switches have one home, Agent details'
    Tools & skills, through `s.setAgentTool` (test_tool_controls.py runs
    it). The Agents card shows a summary and links there."""
    from qml_scan import scan
    src = scan(PAGE).nocomment
    assert 'put("mainTools"' not in src
    assert not re.search(r'updateAgent\([^)]*"tools"', src)
    assert "setAgentTool" not in src
    assert 'onDetailsAsked: blk.s.goTo("agentdetails", blk.agentId, "tools")' in src


@needs_node
def test_an_entry_from_before_ids_gets_its_derived_id_and_nothing_else():
    old = [{"name": "jarvis ajc", "agent": "claude", "zz": 1}, {"name": "max", "label": "Max"}]
    r = harness(old, {}, ['writeField(1, "level", "edits")'])[0]
    saved = r["puts"][0][1]
    assert saved[0] == {"name": "jarvis ajc", "agent": "claude", "zz": 1, "id": "jarvis-ajc"}
    assert saved[1] == {"name": "max", "label": "Max", "id": "max", "level": "edits"}
    # Key order: everything as it was, the id appended.
    assert list(saved[0]) == ["name", "agent", "zz", "id"]


@needs_node
def test_the_guard_is_not_vacuous():
    """Mutation, inside the suite: an updateAgent that copies only the fields
    this build knows -- the obvious way to write it -- loses `futureField`,
    and the comparison above says so."""
    copy = function_source(PAGE, "copyEntry")
    mutated = ("function copyEntry(a) { var copy = {}; var known = ['id','name','label','agent','model',"
               "'effort','voice','speed','narration','level','projectDir','tools','collaboration','notesWrite',"
               "'acceptsWork','enabled','endpointUrl','endpointModel','endpointIsAgent','endpointTimeoutS',"
               "'endpointHistoryTurns','instructions']; for (var q = 0; q < known.length; q++) "
               "if (known[q] in a) copy[known[q]] = a[known[q]]; return copy }")
    assert "Object.defineProperty" in copy
    src = function_source(PAGE, "updateAgent")
    calls = [(0, EXTRA_WRITES[2])]
    results = harness(AGENTS, {}, ['writeField(0, "label", "Renamed")'], replace={"copyEntry": mutated})
    assert any("other fields changed" in w for w in _check_extra_writes(results, calls))
    # And one that touches the neighbours.
    neighbour = src.replace("if (i === index) {", "if (true) {")
    results = harness(AGENTS, {}, ['writeField(0, "label", "Renamed")'], replace={"updateAgent": neighbour})
    assert any("agent 1 changed" in w for w in _check_extra_writes(results, calls))


MAIN_SETTINGS = {"agentModels": {"claude": "opus", "codex": "gpt-5"},
                 "agentEfforts": {"claude": "high"}, "permissions": {"claude": "ask", "gemini": "edits"},
                 "mainTools": {"browser": "off"}, "endpointUrl": "", "endpointModel": ""}

MAIN_WRITES = [
    ('writeField(-1, "label", "Theodore")', [["mainName", "Theodore"]]),
    ('writeField(-1, "name", "theo")', [["phrase", "theo"]]),
    ('writeField(-1, "model", "sonnet")', [["agentModels", {"claude": "sonnet", "codex": "gpt-5"}]]),
    ('writeField(-1, "model", "")', [["agentModels", {"codex": "gpt-5"}]]),
    ('writeField(-1, "effort", "low")', [["agentEfforts", {"claude": "low"}]]),
    ('writeField(-1, "level", "trusted")', [["permissions", {"claude": "trusted", "gemini": "edits"}]]),
    ('writeField(-1, "voice", "ryan-medium")', [["voice", "ryan-medium"]]),
    ('writeField(-1, "speed", 125)', [["voiceSpeed", 125]]),
    ('writeField(-1, "projectDir", "~/p")', [["projectDir", "~/p"]]),
    ('writeField(-1, "notesWrite", "deny")', [["mainNotesWrite", "deny"]]),
    ('writeField(-1, "collaboration", "allow")', [["mainCollaboration", "allow"]]),
    ('writeField(-1, "acceptsWork", false)', [["mainAcceptsWork", False]]),
    ('writeField(-1, "agent", "codex")', [["mainProgram", "codex"]]),
    ('writeField(-1, "agent", "omarchy")', []),
    ('writeField(-1, "agent", "endpoint")', []),
    ('putMainEndpoint("endpointUrl", "http://x/v1")', [["endpointUrl", "http://x/v1"]]),
    ('putMainEndpoint("endpointHistoryTurns", 3)', [["endpointHistoryTurns", 3]]),
]


@needs_node
def test_each_main_agent_write_is_its_one_key_and_never_the_agent_list():
    results = harness(AGENTS, MAIN_SETTINGS, [c for c, _ in MAIN_WRITES])
    for (call, want), r in zip(MAIN_WRITES, results):
        assert r["puts"] == want, call
    # "endpoint" is chosen on the page until both boxes are filled.
    assert results[[c for c, _ in MAIN_WRITES].index('writeField(-1, "agent", "endpoint")')]["endpointChosen"]


@needs_node
def test_choosing_a_voice_fetches_it_for_either_kind_of_agent():
    r = harness(AGENTS, {}, ['writeField(-1, "voice", "joe-medium")', 'writeField(2, "voice", "kristin-medium")'])
    assert r[0]["chose"] == ["joe-medium"] and r[1]["chose"] == ["kristin-medium"]


# --- the header strip asks rather than assigns ------------------------------------

@needs_node
def test_a_controlled_strip_asks_and_leaves_its_binding_alone():
    """Every save rebuilds nothing, but a click that assigned `expanded`
    would break the page's binding, and a deep link could no longer open the
    agent (the bug the old AgentCard's comment described)."""
    flip = function_source(ROOT / "ui" / "HeaderStrip.qml", "flip")
    script = f"""
var foldable = true, expanded = false, controlled = true, asked = [];
function toggled(v) {{ asked.push(v) }}
{flip}
flip();
var a = {{ expanded: expanded, asked: asked.slice() }};
controlled = false; asked = [];
flip();
console.log(JSON.stringify([a, {{ expanded: expanded, asked: asked }}]))
"""
    controlled, free = run_js(script)
    assert controlled == {"expanded": False, "asked": [True]}
    assert free == {"expanded": True, "asked": [True]}
    assert "controlled: true" in PAGE.read_text()


# --- where a tool's value comes from ------------------------------------------------

@needs_node
@pytest.mark.parametrize("program,choices,globals_,want", [
    ("claude", {}, {"desktop": True, "browser": False, "omarchySkill": True},
     ["on, as for every agent", "off, as for every agent", "on, as for every agent"]),
    ("claude", {"desktop": "off", "browser": "on"}, {"desktop": True},
     ["off, this agent's own", "on, this agent's own", "off, as for every agent"]),
    ("codex", {"browser": "on"}, {"desktop": False, "omarchySkill": False},
     ["off, as for every agent", "not available", "off, as for every agent"]),
    ("endpoint", {"desktop": "on"}, {"desktop": True},
     ["not available", "not available", "not available"]),
])
def test_the_tools_card_says_where_each_value_comes_from(program, choices, globals_, want):
    """An inherited "off" must read as the setting for every agent, not as a
    switch that is missing (the plan's words for the Tools card)."""
    qml = ROOT / "ui" / "ToolSwitches.qml"
    text = qml.read_text()
    tables = "\n".join(f"var {n} = {re.search(n + r':\s*(\[[^\]]*\])', text).group(1)};"
                       for n in ("desktopPrograms", "browserPrograms"))
    fns = "\n".join(function_source(qml, n) for n in ("choice", "whyNot", "source"))
    script = f"""
var program = {json.dumps(program)}, choices = {json.dumps(choices)}, globals = {json.dumps(globals_)};
{tables}
{fns}
console.log(JSON.stringify(["desktop", "browser", "omarchySkill"].map(source)))
"""
    assert run_js(script) == want


# --- bug E: the switches for every agent live on Communal ---------------------------

def test_the_agents_page_no_longer_writes_the_tools_for_every_agent():
    page = scan(PAGE)
    for key in ("desktopTools", "browserTools", "omarchySkill"):
        assert not re.search(r'\bput\("' + key + '"', page.nocomment), key
    assert "ON THE DESKTOP" not in page.src
    assert "SettingsGroup {" not in page.clean
    # The card and the foot of the page say where they went.
    assert page.src.count('goTo("communal", "", "tools")') == 2


def test_communal_draws_them_on_its_own_tools_tab():
    s = scan(ROOT / "pages" / "CommunalPage.qml")
    m = re.search(r'visible: page\.tab === "tools"', s.nocomment)
    assert m, "no tools tab"
    body_start = max(o for o in s.opens if o < m.start())
    body = s.nocomment[body_start:s.closes[body_start]]
    for key in ("desktopTools", "browserTools", "omarchySkill"):
        assert f'page.s.put("{key}", !checked)' in body, key
        assert f'page.s.resetKey("{key}")' in body, key
    assert '{ id: "tools", label: "Tools" }' in s.src
    # M15 added Who gets it and Preview before them.
    assert '["who", "preview", "tools", "skills", "notes", "chats"].includes(s.communalTab)' in s.src


@needs_node
def test_a_deep_link_can_open_communal_on_its_tools_tab():
    go = function_source(ROOT / "Settings.qml", "goTo")
    script = f"""
var pages = [{{id: "overview"}}, {{id: "agents"}}, {{id: "communal"}}, {{id: "agentdetails"}}];
var page = "", communalTab = "rules", focusTools = false, focusAgent = "", mode = "",
    detailsAgent = "", detailsTab = "", pageScroll = null;
var Qt = {{ callLater: function() {{}} }};
{go}
var out = [];
goTo("communal", "", "tools"); out.push([page, communalTab]);
goTo("communal", "", "bogus"); out.push([page, communalTab]);
goTo("agents", "sora", "tools"); out.push([page, focusAgent, focusTools]);
console.log(JSON.stringify(out))
"""
    assert run_js(script) == [["communal", "tools"], ["communal", "tools"], ["agents", "sora", True]]


def test_every_agent_is_drawn_by_the_one_block():
    """The main agent and the extra ones were two copies of every row, and
    drifted (M5). One block now; the Repeater keeps building by count."""
    text = PAGE.read_text()
    assert text.count("component AgentBlock:") == 1
    assert text.count("AgentBlock {") == 2
    assert "model: page.s.voiceAgents.length" in text
    assert "AgentCard {" not in text
    for card in ("Identity", "Endpoint", "Permissions", "Voice", "Tools", "Collaboration, notes & chats", "Agent"):
        assert f'title: "{card}"' in text, card


@needs_node
def test_test_plays_the_voice_at_the_agents_own_pace():
    """▶ Test on an agent's Voice card plays its sample at its own speed;
    anything that is not a speed in range falls back to the main agent's."""
    play = function_source(ROOT / "Settings.qml", "playSample")
    script = f"""
var SETTINGS = {{ voiceSpeed: 110 }};
var root = {{ setting: function(k, d) {{ return k in SETTINGS ? SETTINGS[k] : d }},
             samplePlaying: "", sampleNext: "", sampleNextPace: 0 }};
var sampler = {{ running: false, command: [] }};
{play}
var out = [];
[[ "amy-medium", 135 ], [ "amy-medium", undefined ], [ "amy-medium", 20 ], [ "amy-medium", "x" ],
 [ "x;rm -rf ~", 120 ]].forEach(function(c) {{
  sampler.running = false; sampler.command = [];
  playSample(c[0], c[1]);
  out.push(sampler.command);
}});
console.log(JSON.stringify(out))
"""
    got = run_js(script)
    assert got[0] == ["agentvoice", "voice", "sample", "amy-medium", "135"]
    assert got[1] == got[2] == got[3] == ["agentvoice", "voice", "sample", "amy-medium", "110"]
    assert got[4] == [], "only a real voice name reaches the command"


@needs_node
def test_a_field_named_proto_survives_an_edit_of_another_agent():
    """JSON.parse makes "__proto__" an ordinary field; a copy that assigned
    it would hand it to the prototype setter and the saved list would lose
    it (Codex review, M5). The fixture goes through JSON.parse, as
    shell.json does."""
    agents = [{"id": "a", "name": "a", "__proto__": {"version": 2}, "zz": 1},
              {"id": "b", "name": "b", "label": "B"}]
    calls = [(1, ('writeField(I, "label", "Bee")', "label", "Bee")),
             (0, ('writeField(I, "level", "edits")', "level", "edits"))]
    results = harness(agents, {}, [c.replace("I", str(i), 1) for i, (c, _, _) in calls])
    assert _check_extra_writes(results, calls, agents) == []
    assert results[0]["puts"][0][1][0] == agents[0]


def test_each_extra_agent_writes_through_its_own_index():
    """The tests above call writeField with the index they mean. What hands
    a block that index is the Repeater's delegate, and every write in the
    block goes through it; `agentIndex: 0` there would make editing the
    second agent overwrite the first (Codex review, M5)."""
    s = scan(PAGE)
    text = s.nocomment
    rep = text[text.index("model: page.s.voiceAgents.length"):]
    delegate = rep[:rep.index("\n  }\n")]
    assert re.search(r"delegate: AgentBlock \{\s*required property int index\s*pg: page\s*agentIndex: index\s*\}", delegate)
    assert "function write(field, value) { pg.writeField(agentIndex, field, value) }" in text
    block = text[text.index("component AgentBlock:"):text.index("AgentBlock { pg: page }")]
    for call in re.finditer(r"\b(?:updateAgent|removeAgent|writeTool|writeField)\(([^,)]*)", block):
        assert call.group(1).strip() in ("blk.agentIndex", "agentIndex"), call.group(0)


@needs_node
def test_two_agents_sharing_a_voice_at_different_speeds_each_test_their_own():
    """Each card's Test is its own sample: the player records the pace it
    started at, the other speed is queued rather than taken as a stop, and
    the same voice at the same speed stops (Codex review, M5)."""
    play = function_source(ROOT / "Settings.qml", "playSample")
    script = f"""
var root = {{ setting: function(k, d) {{ return d }}, samplePlaying: "", samplePace: 0,
             sampleNext: "", sampleNextPace: 0 }};
var sampler = {{ running: false, command: [] }};
{play}
var out = [];
playSample("amy-medium", 100);
out.push([root.samplePlaying, root.samplePace, sampler.command[4]]);
sampler.running = true;
playSample("amy-medium", 150);
out.push([root.sampleNext, root.sampleNextPace, sampler.running]);
// The player's onRunningChanged starts the queued one through playSample.
var v = root.sampleNext, p = root.sampleNextPace; root.sampleNext = "";
playSample(v, p);
out.push([root.samplePlaying, root.samplePace, sampler.command[4]]);
sampler.running = true;
playSample("amy-medium", 150);
out.push([root.sampleNext, sampler.running]);
console.log(JSON.stringify(out))
"""
    started, queued, second, stopped = run_js(script)
    assert started == ["amy-medium", 100, "100"]
    assert queued == ["amy-medium", 150, False], "the other speed is queued, not taken as a stop"
    assert second == ["amy-medium", 150, "150"], "and plays at its own pace, recorded"
    assert stopped == ["", False], "the same voice at the same speed stops"


def test_the_test_button_asks_for_and_recognises_the_same_pace():
    """A speed out of range plays at the main agent's; the button must
    compare with that pace, or it says Test while its sample plays."""
    text = scan(PAGE).nocomment
    assert "testPace: speedHeard >= 50 && speedHeard <= 200 ? speedHeard : pg.mainSpeed" in text
    assert "blk.s.samplePace === blk.testPace" in text
    assert "blk.s.playSample(blk.voiceHeard, blk.testPace)" in text


def test_an_effort_is_called_stale_only_on_the_daemons_answer():
    """An extra agent the daemon has not built yet is listed with no efforts;
    that must not offer to clear a valid saved effort (Codex review, M5)."""
    text = scan(PAGE).nocomment
    assert 'Array.isArray(info.efforts) && String(info.posture || "") !== ""' in text
    assert "s.serviceActive && s.vEffortsKnown" in text
    assert 'staleEffort: blk.effort !== "" && blk.effortsKnown &&' in text
    settings = scan(ROOT / "Settings.qml").nocomment
    assert "root.vEffortsKnown = Array.isArray(d.efforts)" in settings


def test_a_stale_effort_can_be_cleared_and_a_long_model_cannot_hide_effort():
    """Read checks for two layout fixes from Codex's review (M5); the preview
    shows them working. The picker is handed the effort as saved, so its
    "Default" commits even when the model in force does not take it, and the
    row has a reset for when the model takes none. The model half of the
    picker is given what is left after effort, so a long name elides."""
    text = scan(PAGE).nocomment
    row = text[text.index('label: "Model"'):text.index("TextField {", text.index('label: "Model"'))]
    assert 'onReset: blk.write("effort", "")' in row and "changed: staleEffort" in row
    assert "effort: blk.effort\n" in row
    assert "width: Math.min(implicitWidth, parent.width)" in row
    picker = scan(ROOT / "ui" / "ModelPicker.qml").nocomment
    assert "picker.width - 2 -" in picker and "effortSel.width + 1" in picker
    # Its own preferred width from natural widths, never from given ones.
    assert "implicitWidth: modelSel.implicitWidth + (effortSel.visible ? effortSel.implicitWidth + 1 : 0) + 2" in picker
    assert "picker.width - 3 - Math.min(modelSel.implicitWidth" in picker
