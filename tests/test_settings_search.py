"""Settings search cannot drift from the settings (master plan M28).

ui/SettingsIndex.js says where every setting lives: the page, the agent, the
tab and the control (an objectName on that page). An index written by hand
goes stale the first time a control moves, so this holds it to the code:

- every manifest key and every defaults-only key has an entry, and so does
  every voiceAgents field that has a page;
- an entry's page is a page the sidebar has, and the page that *writes* the
  key (the one-page tests' own reading), so search lands where the setting
  really is;
- its control exists on that page, once, by that name -- inside an agent's
  card when it is one agent's setting;
- the tabs it names are tabs that page opens;
- old deep links still resolve: the page ids, the `display` alias, a
  `history` summons, the tab and focus fields.

What search does with the index (ranking, opening, unfolding, focusing) is
driven in bench/preview/targets/search.qml, because it runs in QML.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from test_settings_pages import (FIELD_HOMES, ROOT, _declared, _defaults_only,
                                 _key_writers)

INDEX = ROOT / "ui" / "SettingsIndex.js"
SETTINGS = ROOT / "Settings.qml"


def _entries(text: str | None = None) -> list[dict]:
    text = INDEX.read_text() if text is None else text
    m = re.search(r"// BEGIN ENTRIES\nvar ENTRIES = (\[.*?\n\]);\n// END ENTRIES", text, re.S)
    assert m, "the ENTRIES block is missing its markers"
    return json.loads(m.group(1))


def _page_ids() -> list[str]:
    s = SETTINGS.read_text()
    block = s[s.index("readonly property var pages: ["):]
    block = block[:block.index("\n  ]")]
    return re.findall(r'\{ id: "(\w+)"', block)


def _page_files() -> dict[str, Path]:
    """Page id -> its file, read from the overlay's own Loader and
    Components rather than listed here."""
    s = SETTINGS.read_text()
    comp = dict(re.findall(r"Component \{ id: (\w+);\s*(\w+) \{ s: root \}", s))
    loader = s[s.index("sourceComponent: root.page ==="):]
    loader = loader[:loader.index("}")]
    out = {pid: ROOT / "pages" / f"{comp[c]}.qml"
           for pid, c in re.findall(r'root\.page === "(\w+)" \? (\w+)', loader)}
    fallback = re.search(r":\s*(\w+)\s*$", loader.strip())
    out["overview"] = ROOT / "pages" / f"{comp[fallback.group(1)]}.qml"
    return out


def _anchor_lines(path: Path, anchor: str) -> list[str]:
    """Lines setting `objectName` to this name, plainly or as one side of a
    condition (`objectName: blk.isMain ? "agent-speed" : ""`)."""
    pat = re.compile(r'^\s*objectName:.*"' + re.escape(anchor) + r'".*$', re.M)
    return [m.group(0) for m in pat.finditer(path.read_text())]


def _agent_block(path: Path) -> str:
    s = path.read_text()
    start = s.index("component AgentBlock: HeaderStrip {")
    end = s.index("\n  AgentBlock { pg: page }", start)
    return s[start:end]


ENTRIES = _entries()
PAGES = _page_ids()
FILES = _page_files()
TABS = {"agentdetails": {"prompt", "tools", "notes", "chats", "advanced"},
        "communal": {"rules", "who", "preview", "tools", "skills", "notes", "chats"}}


def test_the_index_is_read_and_the_pages_are_found():
    assert len(ENTRIES) > 90
    assert len(PAGES) == 11 and PAGES[0] == "overview" and "about" in PAGES
    assert set(FILES) == set(PAGES), set(FILES) ^ set(PAGES)
    assert all(p.exists() for p in FILES.values())


def test_every_entry_has_the_fields_search_needs():
    for e in ENTRIES:
        kinds = [k for k in ("key", "field", "action") if k in e]
        assert kinds in (["key"], ["key", "field"], ["field"], ["action"]), e
        assert isinstance(e.get("label"), str) and e["label"].strip(), e
        assert isinstance(e.get("anchor"), str) and re.fullmatch(r"[A-Za-z][\w-]*", e["anchor"]), e
        assert isinstance(e.get("words", ""), str), e
        assert set(e) <= {"key", "field", "action", "label", "page", "agent", "tab",
                          "anchor", "words", "when", "advanced"}, e


def test_every_manifest_key_and_every_defaults_only_key_has_an_entry():
    keyed = [e["key"] for e in ENTRIES if "key" in e]
    assert len(keyed) == len(set(keyed)), "a key with two entries"
    missing = (_declared() | _defaults_only()) - set(keyed)
    assert missing == set(), f"no search entry for {sorted(missing)}"
    unknown = set(keyed) - (_declared() | _defaults_only())
    assert unknown == set(), f"entries for keys that do not exist: {sorted(unknown)}"


def test_every_agent_field_with_a_page_has_an_entry():
    fields = [e["field"] for e in ENTRIES if "field" in e]
    assert len(fields) == len(set(fields)), "a field with two entries"
    homed = {f for f, (page, _) in FIELD_HOMES.items() if page}
    assert homed - set(fields) == set(), sorted(homed - set(fields))
    assert set(fields) - set(FIELD_HOMES) == set()


def test_every_entry_opens_a_page_the_sidebar_has():
    for e in ENTRIES:
        assert e["page"] in PAGES, e
        if "tab" in e:
            assert e["tab"] in TABS.get(e["page"], set()), e
        if "agent" in e:
            assert e["agent"] == "main" and e["page"] == "agents", e


def test_a_key_is_found_on_the_page_that_writes_it():
    """Search lands where the setting is changed: the page the one-page
    tests say writes it. A key moved to another page fails here until the
    index moves with it."""
    by_file = {path.name: pid for pid, path in FILES.items()}
    wrong = {}
    for e in ENTRIES:
        if "key" not in e:
            continue
        writers = [by_file[w] for w in _key_writers(e["key"]) if w in by_file]
        if writers != [e["page"]]:
            wrong[e["key"]] = (e["page"], writers)
    assert wrong == {}, wrong


def test_an_agent_field_is_found_on_its_home_page_beside_its_twin():
    for e in ENTRIES:
        if "field" not in e:
            continue
        page, twin = FIELD_HOMES[e["field"]]
        assert FILES[e["page"]].name == page, e
        if "key" in e:
            # key + field: the main agent's key is the field's twin.
            assert e["key"] == twin, (e, twin)
        else:
            # A field alone: its twin, if any, is written on another page
            # (narration: the Conversation page), so it has its own entry.
            assert twin is None or FILES[e["page"]].name not in _key_writers(twin), (e, twin)


def test_every_anchor_is_on_its_page_once():
    """findNamed() takes the first control by that name, so a second one on
    the same page (or in the same agent's card) would be found instead."""
    for e in ENTRIES:
        path = FILES[e["page"]]
        lines = _anchor_lines(path, e["anchor"])
        assert lines, f"{e['anchor']} is not an objectName on {path.name}"
        if len(lines) > 1:
            # Allowed only as the two sides of one condition, so that one
            # agent's card has it on exactly one control.
            assert len(lines) == 2 and all("isMain ?" in ln for ln in lines), (e["anchor"], lines)
            assert ('"' + e["anchor"] + '" : ""' in lines[0]) != ('"' + e["anchor"] + '" : ""' in lines[1])


def test_one_agents_setting_is_inside_the_agent_card():
    """On the Agents page an agent's setting is looked for inside that
    agent's card (objectName "agent-<id>"), so its control must be in the
    card's component, and the card must carry the name."""
    path = FILES["agents"]
    block = _agent_block(path)
    assert re.search(r'objectName: "agent-" \+ agentId', block)
    for e in ENTRIES:
        if e["page"] != "agents":
            continue
        scoped = "field" in e or e.get("agent") == "main"
        inside = re.search(r'objectName:.*"' + re.escape(e["anchor"]) + '"', block) is not None
        assert inside == scoped, (e["anchor"], "scoped" if scoped else "page-wide")


def test_settings_search_finds_the_pause_setting():
    """The feedback's own example ("where is the pause setting?") is in the
    index under the label it is shown with, folded under Advanced on the
    Conversation page."""
    e = next(e for e in ENTRIES if e.get("key") == "trailingSilenceMs")
    assert e["page"] == "conversation" and e["advanced"] and e["label"].startswith("Pause")
    assert "pause" in e["words"].split()


def test_the_index_rejects_a_missing_key(tmp_path):
    """Mutation: the index with one entry dropped fails the coverage rule."""
    text = INDEX.read_text()
    line = next(ln for ln in text.splitlines() if '"key": "echoTailMs"' in ln)
    mutant = _entries(text.replace(line + "\n", ""))
    keyed = {e["key"] for e in mutant if "key" in e}
    assert "echoTailMs" in (_declared() | _defaults_only()) - keyed


def test_the_index_rejects_a_wrong_page():
    """Mutation: an entry pointing at a page other than its key's writer."""
    by_file = {path.name: pid for pid, path in FILES.items()}
    e = dict(next(e for e in ENTRIES if e.get("key") == "hud"))
    e["page"] = "voice"
    writers = [by_file[w] for w in _key_writers(e["key"]) if w in by_file]
    assert writers != [e["page"]]


# --- old deep links ------------------------------------------------------------

def _body(src: str, name: str) -> str:
    start = src.index(f"function {name}(")
    return src[start:src.index("\n  }", start)]


def test_old_deep_links_still_resolve():
    """Payloads written before M28 keep working: a page id, the `display`
    alias (M26), a `history` summons (M18), an agent with a tab, a focus."""
    s = SETTINGS.read_text()
    goto = _body(s, "goTo")
    assert 'if (pageId === "display") pageId = "other"' in goto
    opener = _body(s, "open")
    assert 'if (p.mode === "history") p.page = "chats"' in opener
    tab_re = re.search(r"\^\(([a-z|]+)\)\$/\.test\(String\(p\.tab", opener).group(1).split("|")
    # Every tab goTo() opens, Communal's included (M15's "who" and
    # "preview" were missing until M28, so a link to them landed on Rules).
    assert set(tab_re) >= TABS["agentdetails"] | TABS["communal"]
    assert "focusKey = String(p.focus)" in opener
    # And the new summons does not take a deep link over: setup only takes
    # a summons that asked for nothing in particular.
    assert "plainOpen = mode === \"settings\" && !p.page && !p.focus && !p.chat && !p.id" in opener


def test_every_tab_the_index_names_is_one_go_to_opens():
    goto = _body(SETTINGS.read_text(), "goTo")
    details = set(re.search(r'agentdetails.*?\^\(([a-z|]+)\)\$', goto, re.S).group(1).split("|"))
    communal = set(re.search(r'communal" && /\^\(([a-z|]+)\)\$', goto).group(1).split("|"))
    for e in ENTRIES:
        if e.get("tab"):
            assert e["tab"] in (details if e["page"] == "agentdetails" else communal), e


# --- the search piece and the overlay --------------------------------------------

def test_the_search_box_is_in_the_sidebar_and_ctrl_f_reaches_it():
    s = SETTINGS.read_text()
    assert re.search(r"SettingsSearch \{\s*id: settingsSearch", s)
    assert "onChosen: function(r) { root.reveal(r) }" in s
    keys = s[s.index("Keys.onPressed: function(e) {"):]
    keys = keys[:keys.index("\n      }")]
    assert "Qt.Key_F" in keys and "settingsSearch.focusField()" in keys
    assert "SettingsSearch 1.0 SettingsSearch.qml" in (ROOT / "ui" / "qmldir").read_text()


def test_what_search_shows_is_plain_text():
    """A result's label and path come from the index and from agents' names,
    which a person typed: shown as plain text, like every other name."""
    src = (ROOT / "ui" / "SettingsSearch.qml").read_text()
    texts = re.findall(r"Text \{(.*?)\n\s*\}", src, re.S)
    assert texts and all("textFormat: Text.PlainText" in t for t in texts if "text:" in t)


def test_reveal_walks_only_the_page_it_opened():
    """reveal() never looks outside the page loader: an objectName in the
    sidebar or the permission card is never found and focused instead, and
    a page left meanwhile drops the search rather than finishing it."""
    body = _body(SETTINGS.read_text(), "revealStep")
    assert "var top = pageLoader.item" in body
    assert "a !== pageLoader" in body
    assert "page !== String(r.page)" in body
