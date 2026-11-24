"""The keyboard pass and the consistency audit (master plan M29).

Every page is built from the same pieces, and every action on one can be
reached without a pointer and is named for a screen reader. These hold it
by reading the QML (CLAUDE.md: the QML's behaviour is not tested, its
structure is); `bench/preview/targets/keys.qml` drives the real overlay
with Tab and checks the same thing from the other side.
"""
from __future__ import annotations

import re
from pathlib import Path

from qml_scan import ROOT, scan

# The settings overlay: what a person reaches from the bar's Settings. The bar
# popup (Panel.qml) and the readout (Hud.qml) are not pages and keep a
# keyboard model of their own (Omarchy's panel cursor), so they are not here.
OVERLAY = sorted([ROOT / "Settings.qml", ROOT / "Setup.qml", ROOT / "Chats.qml"]
                 + list((ROOT / "pages").glob("*.qml")) + list((ROOT / "ui").glob("*.qml")))


def _rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def _element_braces(sc, pos):
    """The "{" of each QML element `pos` is inside, innermost first, with its
    type name (`ActionButton`, `component LastChatLink: TextLink` -> TextLink)."""
    out = []
    for brace in sc.enclosing(pos):
        m = re.fullmatch(r"(?:component\s+\w+\s*:\s*|\w+\s*:\s*)?([A-Z][\w.]*)", sc.header(brace))
        if m:
            out.append((brace, m.group(1)))
    return out


def _own(sc, brace) -> str:
    """The cleaned body of the element at `brace`, with every nested block
    blanked: what is set on the element itself."""
    end = sc.closes[brace]
    body = list(sc.nocomment[brace + 1:end])
    for o in sc.opens:
        if brace < o < end:
            c = sc.closes[o]
            # Only the outermost nested blocks matter; blanking a block twice
            # is harmless.
            for i in range(o - brace, c - brace - 1):
                if body[i] != "\n":
                    body[i] = " "
    return "".join(body)


# --- 1. the old pieces are gone ------------------------------------------------------

def test_no_page_uses_the_old_settingsgroup_or_knobrow():
    """The plan's static test. SettingsGroup put a capitalised heading above
    a box while every redesigned page put the title inside a Card; KnobRow
    drew its own header beside SettingRow's and the two had drifted (markup
    in a label, a "?" and "reset" the keyboard could not reach). Both files
    are gone, so a new use cannot even load."""
    for name in ("KnobRow", "SettingsGroup"):
        assert not (ROOT / f"{name}.qml").exists(), name
        for p in OVERLAY + [ROOT / "Panel.qml", ROOT / "Hud.qml"]:
            sc = scan(p)
            assert not re.search(r"\b" + name + r"\s*\{", sc.clean), f"{_rel(p)} uses {name}"


def test_no_capitalised_section_headings_are_left():
    """A Card's title is in sentence case. A heading in capitals is the old
    SettingsGroup look coming back by hand."""
    for p in OVERLAY:
        sc = scan(p)
        for m in re.finditer(r'\btitle:\s*"([^"]*)"', sc.nocomment):
            t = m.group(1)
            assert not (len(t) > 3 and t.isupper()), f"{_rel(p)}:{sc.lineno(m.start())} {t!r}"
        assert "font.letterSpacing" not in sc.clean, _rel(p)


# --- 2. every button is reachable and named --------------------------------------

# Chips inside a control that keeps its own keyboard cursor: the control is
# the Tab stop, the arrows walk the chips.
CURSOR_CONTROLS = {"ui/SegmentedChoice.qml", "ui/TabStrip.qml", "ui/ToggleChips.qml", "ui/AgentTabs.qml"}
# The permission card's two allows stay pointer-only, so a keypress meant for
# something else can never approve a card; Deny is reachable. phaseM29notes.md
# records it as an open issue.
POINTER_ONLY_ALLOWS = {('Settings.qml', '"Allow once"'), ('Settings.qml', '"Allow all in this chat"')}


def test_every_button_is_an_actionbutton():
    """Omarchy's Button is `focusable: false` unless told, so 29 buttons were
    pointer-only. ActionButton sets it once, with the accessible name."""
    found_allows = set()
    for p in OVERLAY:
        rel = _rel(p)
        if rel in CURSOR_CONTROLS or rel == "ui/ActionButton.qml":
            continue
        sc = scan(p)
        for m in re.finditer(r"(?<![\w.])Button\s*\{", sc.clean):
            body = sc.nocomment[m.end():sc.closes[m.end() - 1]]
            text = re.search(r'\btext:\s*("[^"]*")', body)
            key = (rel, text.group(1) if text else "")
            if key in POINTER_ONLY_ALLOWS:
                found_allows.add(key)
                continue
            raise AssertionError(f"{rel}:{sc.lineno(m.start())}: a bare Button; use ActionButton")
    assert found_allows == POINTER_ONLY_ALLOWS, "the exemption names a button that is gone"


def test_actionbutton_takes_the_focus_and_has_a_name():
    sc = scan(ROOT / "ui" / "ActionButton.qml")
    own = _own(sc, sc.opens[0])
    assert re.search(r"^\s*focusable:\s*true\s*$", own, re.M)
    assert "Accessible.name:" in own and "Accessible.onPressAction:" in own


def test_every_switch_takes_the_focus():
    """Omarchy's ToggleSwitch has no focus of its own; FocusSwitch gives it
    one. M28's search could only outline a switch it landed on."""
    for p in OVERLAY:
        if p.name == "FocusSwitch.qml":
            continue
        sc = scan(p)
        assert not re.search(r"(?<![\w.])ToggleSwitch\s*\{", sc.clean), f"{_rel(p)}: use FocusSwitch"
    sw = scan(ROOT / "ui" / "FocusSwitch.qml")
    own = _own(sw, sw.opens[0])
    for need in ("activeFocusOnTab:", "hasCursor: activeFocus", "Keys.onSpacePressed:",
                 "Accessible.role: Accessible.CheckBox", "Accessible.name:"):
        assert need in own, need
    row = scan(ROOT / "ui" / "ToggleRow.qml")
    assert "FocusSwitch {" in row.clean and "accessibleName: row.label" in row.src


def test_help_and_reset_are_reachable_on_every_setting_row():
    for name in ("SettingRow", "SliderRow"):
        sc = scan(ROOT / "ui" / f"{name}.qml")
        links = [m.start() for m in re.finditer(r"\bTextLink\s*\{", sc.clean)]
        assert len(links) == 2, name
        assert "MouseArea" not in sc.clean[links[0]:sc.closes[sc.clean.index("{", links[1])]], name
    link = scan(ROOT / "ui" / "TextLink.qml")
    own = _own(link, link.opens[0])
    for need in ("activeFocusOnTab:", "Keys.onReturnPressed:", "Keys.onSpacePressed:",
                 "Accessible.name:", "visible: link.activeFocus"):
        assert need in link.clean or need in own, need


def test_a_slider_number_can_be_typed_from_the_keyboard():
    slider = scan(ROOT / "ui" / "VoiceSlider.qml").clean
    assert "signal typeWanted()" in slider and "slider.typeWanted()" in slider
    row = scan(ROOT / "ui" / "SliderRow.qml").clean
    assert "onTypeWanted: knob.startTyping()" in row
    # And the keyboard comes back to the slider either way out of the box.
    assert row.count("slider.forceActiveFocus()") == 2


# --- 3. whatever takes the focus has a name ---------------------------------------

def test_everything_that_takes_tab_focus_has_an_accessible_name():
    missing = []
    for p in OVERLAY:
        sc = scan(p)
        for m in re.finditer(r"\bactiveFocusOnTab\s*:", sc.clean):
            els = _element_braces(sc, m.start())
            if not els:
                continue
            brace, typ = els[0]
            own = _own(sc, brace)
            if not re.search(r"\bactiveFocusOnTab\s*:\s*false\b", own) and "Accessible.name:" not in own:
                missing.append(f"{_rel(p)}:{sc.lineno(m.start())} {typ}")
    assert not missing, "\n".join(missing)


# --- 4. nothing clickable is pointer-only ---------------------------------------------

# A MouseArea whose action the keyboard reaches some other way, and how.
KEYBOARD_ELSEWHERE = {
    ("Settings.qml", "root.dismiss()"): "Escape closes the overlay",
    ("pages/CrewMapPage.qml", "page.select(null)"): "Escape clears the selection",
    ("pages/CrewMapPage.qml", 'page.select({ kind: "link"'): "the link's chip takes Tab and Enter",
    ("pages/CrewMapPage.qml", "body.before"): "a node moves with the arrow keys",
    ("pages/CrewMapPage.qml", "function(m)"): "a node moves with the arrow keys",
    ("ui/DraggableCard.qml", "function(mouse)"): "Enter opens Move to…",
    ("ui/SkillCard.qml", "function(mouse)"): "Ctrl+M opens Move to…",
    ("ui/VoiceSlider.qml", "function(m)"): "the arrow keys, PgUp/PgDn, Home/End",
    ("ui/SliderRow.qml", "knob.startTyping()"): "Enter on the slider",
    ("ui/MenuList.qml", "menu.choose(entry.index)"): "Up/Down/j/k and Enter",
    ("ui/SettingsSearch.qml", "search.choose(row.index)"): "Up/Down and Enter in the box",
    ("ui/SidebarNav.qml", "nav.picked(entry.modelData.id)"): "Up/Down/j/k on the list",
    ("ui/SearchField.qml", "search.clear()"): "Escape clears the box",
    ("ui/CompactSelector.qml", "sel.open()"): "Enter, Space or Down on the selector",
}


def test_no_click_is_pointer_only():
    """A MouseArea that does something sits in an element that takes Tab
    (a TextLink, a focusable row), or its action has a keyboard way named
    above. A new one fails until it has either."""
    seen = set()
    bad = []
    for p in OVERLAY:
        rel = _rel(p)
        sc = scan(p)
        for m in re.finditer(r"\bMouseArea\s*\{", sc.clean):
            brace = m.end() - 1
            body = sc.nocomment[brace + 1:sc.closes[brace]]
            act = re.search(r"\bon(Clicked|Pressed|DoubleClicked)\s*:\s*([^\n]*)", body)
            if not act:
                continue
            handler = act.group(2)
            hit = [k for k in KEYBOARD_ELSEWHERE if k[0] == rel and k[1] in handler]
            if hit:
                seen.update(hit)
                continue
            # enclosing() excludes the MouseArea itself: [0] is its parent.
            parents = _element_braces(sc, brace)[:2]
            if any(t == "TextLink" or re.search(r"\bactiveFocusOnTab\s*:(?!\s*false\b)", _own(sc, b))
                   for b, t in parents):
                continue
            bad.append(f"{rel}:{sc.lineno(m.start())} {handler.strip()[:60]}")
    assert not bad, "pointer-only:\n" + "\n".join(bad)
    assert seen == set(KEYBOARD_ELSEWHERE), f"stale entries: {set(KEYBOARD_ELSEWHERE) - seen}"


def test_every_text_says_its_size():
    """A Text with no font size is drawn in Qt's default, larger than every
    label and heading here: Communal's "No shared skills yet." and five
    status lines on the Agents and Agent details pages read like headings
    nobody wrote (found by the M29 sheet)."""
    bad = []
    for p in OVERLAY:
        sc = scan(p)
        for m in re.finditer(r"(?<![\w.])Text\s*\{", sc.clean):
            own = _own(sc, m.end() - 1)
            if not re.search(r"\bfont\.(pixelSize|pointSize)\s*:|\bfont\s*:", own):
                bad.append(f"{_rel(p)}:{sc.lineno(m.start())}")
    assert not bad, "no font size:\n" + "\n".join(bad)
