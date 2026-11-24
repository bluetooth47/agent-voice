"""The Conversation page (master plan M24): the same settings, compact.

What has to hold:

- every setting the old page changed is changed by this one, once, and the
  six timings are folded together; the pace presets are the four timings they
  always were;
- **the page holds no command phrase written by hand**: what you can say comes
  from `agentvoice commands --json`, so the page cannot drift from what the
  daemon matches (a phrase put in quotes is a failure; a setting's or a
  feature's name is not a phrase to say);
- a timing stored as a string ("90000") is read the way the daemon reads it
  (`Config.get_int`), on the page and in the turn drawn from it;
- the open mic's button has one entry point that checks the service, and the
  one process that changes the open mic is built there;
- the deep link: a focus is a setting's key and nothing else, goTo clears it,
  and the page only acts on the six timings it holds;
- the table the page reads says which positions each mode allows.
"""
from __future__ import annotations

import json
import re

import pytest

from conftest import ROOT
from qml_scan import scan
from qml_sources import page as page_src

PAGE = ROOT / "pages" / "ConversationPage.qml"
TIMELINE = ROOT / "ui" / "TurnTimeline.qml"

#: Everything the Conversation page changed before M24 (bench/key-inventory.py
#: at M23): none may move, none may be lost.
KEYS = {
    "leadInMs", "trailingSilenceMs", "quickEndMs", "minUtteranceMs", "maxUtteranceMs",
    "echoTailMs", "conversationMode", "followUpMs", "narration", "narrationSilenceS",
    "openMicIdleMin", "openMicAddressedOnly", "openMicAuto", "commandsInSentences",
    "fullStopAnytime", "bargeOnHeadset", "bargeIn", "bargeFactor",
}
TIMINGS = ["leadInMs", "trailingSilenceMs", "quickEndMs", "minUtteranceMs",
           "maxUtteranceMs", "echoTailMs"]


def src() -> str:
    return PAGE.read_text()


def written() -> list[str]:
    return re.findall(r'\bput\("([A-Za-z]+)"', src())


# --- the keys ------------------------------------------------------------------------

def test_every_setting_the_page_had_is_still_changed_here():
    assert set(written()) == KEYS


def test_no_setting_is_changed_in_two_places_on_the_page():
    """A control per key: the preset's own writes go through applyPreset, so
    `put(k, ...)` with a variable is not counted, and each literal key once."""
    keys = written()
    assert len(keys) == len(set(keys)), sorted(k for k in set(keys) if keys.count(k) > 1)


def test_the_page_adds_no_setting():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    declared = {e["key"] for e in manifest["barWidget"]["schema"]}
    assert KEYS <= declared
    assert "focusKey" not in declared and "openMic" not in declared


def test_the_six_timings_are_folded_together_in_one_advanced():
    s = src()
    sec = s[s.index('objectName: "timingsAdvanced"'):s.index('objectName: "commandsCard"')]
    assert "count: 6" in sec
    got = re.findall(r'flashed: page\.flash === "([A-Za-z]+)"', sec)
    assert got == TIMINGS
    # Each marked row writes the key it is marked with, and no other.
    for key in TIMINGS:
        block = sec[sec.index(f'flashed: page.flash === "{key}"'):]
        nxt = block.find("Marked {")
        block = block if nxt < 0 else block[:nxt]
        assert re.findall(r'\bput\("([A-Za-z]+)"', block) == [key], key


def test_the_deep_link_acts_on_those_six_and_only_those():
    s = src()
    m = re.search(r'timingKeys: \[([^\]]*)\]', s, re.S)
    assert m
    assert re.findall(r'"([A-Za-z]+)"', m.group(1)) == TIMINGS
    # Each has a knob the scroll can find.
    fn = s[s.index("function knobFor(key)"):s.index("Timer {\n    id: scrollTimer")]
    for key in TIMINGS:
        assert f'key === "{key}"' in fn


# --- the pace presets --------------------------------------------------------------------

def test_the_presets_are_the_four_timings_they_always_were():
    s = src()
    block = s[s.index("readonly property var presets"):s.index("// A timing never written")]
    got = {name: {k: int(v) for k, v in re.findall(r'(\w+): (\d+)', body)}
           for name, body in re.findall(r'"(\w+)":\s*\{([^}]*)\}', block)}
    assert got == {
        "patient": {"leadInMs": 8000, "trailingSilenceMs": 2000, "quickEndMs": 1200, "followUpMs": 12000},
        "balanced": {"leadInMs": 5000, "trailingSilenceMs": 1200, "quickEndMs": 800, "followUpMs": 7000},
        "snappy": {"leadInMs": 3500, "trailingSilenceMs": 800, "quickEndMs": 500, "followUpMs": 5000},
    }


def test_balanced_is_what_ships():
    """So a fresh install reads Balanced, not Custom: the page falls back to
    the shipped value for a timing never written, as the daemon does."""
    from runtime import DEFAULTS
    for key, want in {"leadInMs": 5000, "trailingSilenceMs": 1200, "quickEndMs": 800,
                      "followUpMs": 7000}.items():
        assert DEFAULTS[key] == want
    assert "paceValue(key) { return num(key, isNaN(dflt(key)) ? -1 : dflt(key)) }" in src()


# --- no phrase written by hand ----------------------------------------------------------------

def _literals(text: str) -> list[str]:
    """Every string literal in `text` (comments already out)."""
    return [m.group(1) for m in re.finditer(r'"((?:[^"\\\n]|\\.)*)"', text)]


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", "", text.lower().replace("’", "").replace("'", "")).split())


def _phrases() -> set[str]:
    from speech_text import COMMANDS, _UNDO
    out = set(_UNDO)
    for c in COMMANDS:
        out |= {_norm(p) for p in c.phrases}
        out |= {_norm(p) for p in c.in_sentence}
    return {p for p in out if p}


def test_the_page_holds_no_command_phrase_of_its_own():
    phrases = _phrases()
    assert len(phrases) > 50 and "keep listening" in phrases and "no" in phrases
    found = []
    for lit in _literals(scan(PAGE).nocomment):
        # A phrase in quotes, whatever its length: "stop", \"keep listening\".
        # Not a bare mention: "Keep listening after a reply" is a setting's
        # name, and "open mic" the feature's.
        for quoted in re.findall(r'\\"([^"]*)\\"|“([^”]*)”', lit):
            q = _norm(quoted[0] or quoted[1])
            if q in phrases:
                found.append(q)
    # The narration examples are what the agent says, not what you say.
    found = [f for f in found if f not in {"running the tests", "reading panelqml"}]
    assert sorted(set(found)) == []


def test_the_page_says_what_it_reads_from():
    s = src()
    assert 'command: ["agentvoice", "commands", "--json"]' in s
    # Built from the table: the open mic's note and the example.
    assert 'phraseOf("open_mic")' in s and 'phraseOf("close_mic")' in s


# --- a timing stored as a string ---------------------------------------------------------------

@pytest.mark.parametrize("raw, want", [("90000", 90000), (90000, 90000), (" 90000 ", 90000),
                                       ("-1", -1), (90000.9, 90000)])
def test_the_daemon_reads_a_stored_string_timing(cfg_factory, raw, want):
    assert cfg_factory(maxUtteranceMs=raw).get_int("maxUtteranceMs") == want


@pytest.mark.parametrize("raw", ["", "abc", "9e4", "90000ms", None, [], {}])
def test_an_unreadable_timing_is_the_shipped_one(cfg_factory, raw):
    assert cfg_factory(maxUtteranceMs=raw).get_int("maxUtteranceMs") == 30000


def test_the_page_reads_every_number_through_num():
    """A KnobRow given the string "90000" cannot take it; every number the
    page shows or draws goes through num(), which mirrors get_int."""
    s = scan(PAGE).nocomment
    assert re.findall(r'page\.s\.setting\("(\w+)", \d', s) == [], "a numeric setting read bare"
    fn = s[s.index("function num(key, fallback)"):s.index("function dflt(key)")]
    assert "[+-]?[0-9]+" in fn and "parseInt" in fn and "Math.trunc" in fn
    for key in TIMINGS + ["followUpMs", "openMicIdleMin", "narrationSilenceS", "bargeFactor"]:
        assert f'page.num("{key}"' in s, key


# --- the open mic -------------------------------------------------------------------------------

def test_the_open_mic_has_one_way_in_and_it_checks_the_service():
    s = scan(PAGE).nocomment
    callers = [m.start() for m in re.finditer(r'\btoggleOpenMic\(\)', s)]
    defn = s.index("function toggleOpenMic()")
    outside = [c for c in callers if c != defn + len("function ")]
    assert len(outside) == 1, "one control calls it"
    body = s[defn:s.index("Process {", defn)]
    assert "s.serviceActive" in body and body.index("s.serviceActive") < body.index("openMicProc.running = true")
    # The process is built and started only there.
    assert s.count("openMicProc.running = true") == 1
    assert s.count("openMicProc.command =") == 1
    assert '"open-mic", page.openMicOn ? "off" : "on"' in body


def test_a_press_that_cannot_work_says_why():
    s = src()
    why = s[s.index("readonly property string openMicWhy"):s.index("// The only way in")]
    assert "Start the service first" in why
    # A spawn that never started is caught by `running` going false.
    assert "onRunningChanged: if (!running && !began)" in s
    # `exitCode` is not a property of a Quickshell Process (found in M24).
    assert "exitCode" not in scan(PAGE).nocomment


def test_the_state_the_card_reads_is_the_one_the_daemon_writes():
    settings = (ROOT / "Settings.qml").read_text()
    assert 'root.vOpenMic = (d.open_mic && typeof d.open_mic === "object") ? d.open_mic : ({})' in settings
    daemon = (ROOT / "daemon" / "wake_listen.py").read_text()
    at = daemon.index("def open_mic_field")
    body = daemon[at:at + 500]
    assert '"who"' in body and '"until"' in body
    page = scan(PAGE).nocomment
    assert "s.vOpenMic.until" in page and "s.vOpenMic.who" in page


# --- the deep link -------------------------------------------------------------------------------

def test_a_focus_is_a_setting_key_and_goto_clears_it():
    settings = (ROOT / "Settings.qml").read_text()
    assert "property string focusKey" in settings
    assert 'if (/^[A-Za-z]{1,40}$/.test(String(p.focus || ""))) focusKey = String(p.focus)' in settings
    goto = settings[settings.index("function goTo("):settings.index("// Into the settings, from open()")]
    assert 'focusKey = ""' in goto
    # Set after goTo, which clears it.
    summon = settings[settings.index('A deep link: {"page": "agents"'):]
    assert summon.index("goTo(") < summon.index("focusKey = String(p.focus)")


def test_the_page_takes_the_focus_so_asking_again_is_a_change():
    s = scan(PAGE).nocomment
    fn = s[s.index("function showFocus()"):s.index("Connections {\n    target: page.s\n    function onFocusKeyChanged")]
    assert 'timingKeys.indexOf(key) < 0' in fn
    assert 's.focusKey = ""' in fn
    assert "timings.expanded = true" in fn


def test_the_limit_note_links_to_the_longest_turn():
    s = src()
    # click, Return, Enter, Space, and a screen reader's press (M29)
    assert s.count('page.s.focusKey = "maxUtteranceMs"') == 5
    assert 'text: "Raise it →"' in s
    assert 'hit the limit' in s


# --- the table the page reads ------------------------------------------------------------------------

def test_the_table_says_which_positions_each_mode_allows():
    from speech_text import COMMAND_MODES, POSITIONS, table
    mp = table()["mode_positions"]
    assert list(mp) == list(COMMAND_MODES)
    assert mp["alone"] == ["alone"]
    assert mp["edges"] == ["alone", "start", "end"]
    assert mp["clause"] == list(POSITIONS)
    # Every position the page words is one the table has.
    words = re.search(r'whereWords: \(\{(.*?)\}\)', src(), re.S).group(1)
    assert re.findall(r'"(\w+)":', words) == list(POSITIONS)


def test_the_page_reads_only_fields_the_table_has():
    from speech_text import table
    data = table()
    cmd = data["commands"][0]
    s = scan(PAGE).nocomment
    s = s[s.index('objectName: "command-" + modelData.id'):]  # the list's own delegate
    fn = scan(PAGE).nocomment
    fn = fn[fn.index("function liveWhere(c)"):fn.index("PageHeader {")]
    for field in sorted(set(re.findall(r'modelData\.(\w+)', s)) | set(re.findall(r'\bc\.(\w+)', fn))):
        assert field in cmd, field
    for field in ("mode_positions", "positions", "undo", "commands"):
        assert field in data


# --- text -----------------------------------------------------------------------------------------------

def test_every_text_on_the_page_and_the_timeline_is_plain():
    """What a model or a settings file wrote (an agent's name, a phrase) is
    drawn as plain text: `AutoText` renders anything that looks like HTML."""
    for path in (PAGE, TIMELINE):
        sc = scan(path)
        for m in re.finditer(r'\bText \{', sc.clean):
            end = sc.closes[m.end() - 1]
            block = sc.nocomment[m.start():end]
            # The block's own properties, not a nested element's.
            assert "textFormat: Text.PlainText" in block, f"{path.name}:{sc.lineno(m.start())}"


# --- the timeline ----------------------------------------------------------------------------------------

def test_the_timeline_is_drawn_from_the_settings_and_registered():
    qmldir = (ROOT / "ui" / "qmldir").read_text()
    assert "TurnTimeline 1.0 TurnTimeline.qml" in qmldir
    s = scan(PAGE).nocomment
    block = s[s.index("TurnTimeline {"):]
    block = block[:block.index("\n    }\n")]
    assert 'leadInMs: page.num("leadInMs"' in block
    assert 'talkMs: page.num("maxUtteranceMs"' in block
    assert 'pauseMs: page.num("trailingSilenceMs"' in block
    assert 'quickMs: page.num("quickEndMs"' in block
    assert 'page.num("followUpMs"' in block
    assert "limitHits: page.limitToday" in block
    # Follow-up is left out when following on is off.
    assert 'conversationMode", true) === true ? page.num("followUpMs", 7000) : 0' in block


def test_the_page_is_still_in_the_sidebar_and_scrolls_to_nothing_else():
    assert 'ConversationPage { s: root }' in (ROOT / "Settings.qml").read_text()
    assert page_src("Conversation") == src()
