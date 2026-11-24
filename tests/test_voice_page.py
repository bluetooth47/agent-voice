"""The Voice page (master plan M25): quick settings, each agent's voice inline,
a library that lines up, transcription under Advanced.

What has to hold:

- the page changes the four settings it always changed and no other; the
  per-agent rows and the library write **nothing themselves**: a voice reaches
  `voice` / `voiceAgents` only through the overlay's `assignVoice` (the Agents
  card stays the voice's and the speed's home) and a row opens that card with
  `goTo`, which is a link, not a write;
- **the library's columns line up (bug F)**: the trash cell comes first, is
  always there whether or not the row can be removed, and every column but the
  name has a fixed width, so the name and the Test column start at the same x
  on every row;
- the library opens on Downloaded, with one search box and one filter in place
  of the row of buttons, and a voice is found by any word of its name,
  accent, gender or quality;
- "Used for <names>" is drawn from `voiceUsers`, with the agents' display
  names, as plain text;
- **no model is offered that the daemon would not load**: transcription models
  are fetched by name with no hash today, so none is added (the plan's
  question 10 says "if it fits the session, else deferred"); the page offers
  exactly the manifest's list.
"""
from __future__ import annotations

import json
import re

from conftest import ROOT
from qml_scan import scan

PAGE = ROOT / "pages" / "VoicePage.qml"
LIBRARY_ROW = ROOT / "ui" / "VoiceLibraryRow.qml"
AGENT_ROW = ROOT / "ui" / "VoiceAgentRow.qml"

#: The four settings the Voice page has always held.
KEYS = {"speakReplies", "chimes", "model", "livePartials"}


def src() -> str:
    return scan(PAGE).nocomment


def written() -> list[str]:
    return re.findall(r'\bput\("([A-Za-z]+)"', src())


def element(text: str, header: str) -> str:
    """The braces-balanced body of the first element starting with `header`."""
    sc = scan(PAGE)
    start = sc.nocomment.index(header)
    return sc.nocomment[start:sc.closes[sc.nocomment.index("{", start)]]


# --- what the page writes -----------------------------------------------------------------

def test_the_page_changes_the_same_four_settings_it_always_did():
    assert set(written()) == KEYS


def test_each_setting_is_changed_in_one_place():
    keys = written()
    assert len(keys) == len(set(keys))


def test_the_page_adds_no_setting():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    declared = {e["key"] for e in manifest["barWidget"]["schema"]}
    assert KEYS <= declared


def test_the_rows_write_nothing():
    """A row is a view of a setting that lives on the Agents card: no `put`,
    no `setAgentField`, and a link is `goTo`."""
    for path in (LIBRARY_ROW, AGENT_ROW):
        text = scan(path).nocomment
        assert not re.search(r'\bput\(|setAgentField|saveAgents|resetKey', text), path.name
    page = src()
    assert not re.search(r'\bput\("(voice|voiceAgents|voiceSpeed)"', page)
    assert 's.goTo("agents", modelData.id)' in page
    assert "s.assignVoice(who, modelData.value)" in page


def test_each_agent_row_hears_what_the_agents_card_plays():
    """▶ Test plays the voice the agent really speaks in (its own, else the
    main agent's) at the pace it really has: the Agents card's rule, so the
    two cannot play different things."""
    page = src()
    assert "s.playSample(modelData.voice, modelData.speed)" in page
    body = page[page.index("readonly property var agentRows"):page.index("PageHeader {")]
    assert 'v !== "" ? v : page.mainVoice' in body
    assert "sp > 0 ? sp : page.mainSpeed" in body
    assert "n >= 50 && n <= 200 ? n : page.mainSpeed" in page


def test_a_test_that_cannot_play_says_why():
    page = src()
    assert "canTest: page.speaks && !page.s.voiceMissing(modelData.voice)" in page
    assert '"Replies are not spoken."' in page and '"Not on this machine yet."' in page


# --- bug F: the columns --------------------------------------------------------------------------

def cell(text: str, name: str) -> str:
    sc = scan(LIBRARY_ROW)
    start = sc.nocomment.index(f'id: {name}')
    # The Item that owns the id.
    open_ = sc.nocomment.rindex("Item {", 0, start)
    return sc.nocomment[open_:sc.closes[sc.nocomment.index("{", open_)]]


def test_the_trash_cell_is_first_and_is_always_there():
    text = scan(LIBRARY_ROW).nocomment
    trash = cell(text, "trashCell")
    # Anchored at the left edge, ahead of the name.
    assert "anchors.left: parent.left" in trash
    assert "anchors.left: trashCell.right" in text
    # The cell itself has no `visible` and no `enabled`: only what is in it does.
    own = re.sub(r'Button \{.*?\n    \}\n', "", trash, flags=re.S)
    own = re.sub(r'Text \{.*?\n    \}\n', "", own, flags=re.S)
    assert "visible" not in own.split("Button {")[0]
    assert "width: row.trashWidth" in trash
    # The trash button is shown only for a voice that can go...
    assert re.search(r'visible: row\.onDisk && row\.removable\s+iconText', trash)
    # ...and something stands where it is otherwise.
    assert "visible: !(row.onDisk && row.removable)" in trash


def test_every_column_but_the_name_has_a_fixed_width():
    text = scan(LIBRARY_ROW).nocomment
    assert "width: row.trashWidth" in cell(text, "trashCell")
    assert "width: row.testWidth" in cell(text, "testCell")
    assert "width: row.useWidth" in cell(text, "useCell")
    # The cells are anchored to the row, not to each other's content: the Test
    # cell hangs off the Use cell, which hangs off the right edge.
    assert "anchors.right: useCell.left" in cell(text, "testCell")
    assert "anchors.right: parent.right" in cell(text, "useCell")
    # The name takes what is between, so it starts where the trash ends.
    assert "anchors.right: testCell.left" in text


def test_a_missing_voice_and_an_installed_one_share_the_test_column():
    """Download and Test are in the same cell, both as wide as it is, so the
    column does not depend on which one a row shows."""
    text = scan(LIBRARY_ROW).nocomment
    test = cell(text, "testCell")
    assert test.count("width: parent.width") == 2
    assert "visible: row.onDisk" in test and "visible: !row.onDisk" in test


def test_the_agent_rows_use_fixed_cells_too():
    text = scan(AGENT_ROW).nocomment
    assert "width: row.cell" in text and "width: row.linkCell" in text
    assert "anchors.right: linkCell.left" in text and "anchors.right: parent.right" in text


# --- the library ----------------------------------------------------------------------------------

def test_the_library_opens_on_downloaded():
    assert 'property string filter: "here"' in src()


def test_a_voice_being_fetched_stays_in_the_downloaded_list():
    """Otherwise choosing a voice for an agent would make its row, and its
    progress bar, vanish from the view the page opens on."""
    page = src()
    body = page[page.index("readonly property var shown"):page.index("readonly property string mainVoice")]
    assert 's.fetching !== v.value && s.fetchQueue.indexOf(v.value) < 0' in body


def test_one_search_box_and_one_filter_replace_the_row_of_buttons():
    page = src()
    assert page.count("SearchField {") == 1 and page.count("CompactSelector {") == 1
    assert "SegmentedChoice" in page            # still used for the Advanced controls
    lib = page[page.index('title: "Voices"'):page.index("Advanced: hearing you")]
    assert "SegmentedChoice" not in lib
    opts = re.findall(r'value: "([A-Za-z]+)", label: "([^"]+)"', page[:page.index("function matches")])
    assert [v for v, _ in opts] == ["here", "all", "female", "male", "US", "GB"]


def test_a_voice_is_found_by_any_word_of_its_description():
    """`matches` reimplemented in Python over the real list in Settings.qml, so
    the rule on the page and the list it runs over are both read, not assumed."""
    text = (ROOT / "Settings.qml").read_text()
    voices = re.findall(
        r'\{ label: "([^"]+)", value: "([^"]+)", gender: "([a-z]*)", accent: "(US|GB)", quality: "(\w+)"', text)
    assert len(voices) >= 29

    def matches(v, q):
        label, value, gender, accent, quality = v
        hay = f"{label} {value} {gender} {'british' if accent == 'GB' else 'american'} {quality}".lower()
        return all(w in hay for w in q.lower().split() if w)

    assert [v[1] for v in voices if matches(v, "british female")] == [
        "en_GB-alba-medium", "en_GB-cori-medium", "en_GB-cori-high",
        "en_GB-jenny_dioco-medium", "en_GB-southern_english_female-low"]
    assert matches(voices[0], "") and not matches(voices[0], "zzz")
    # The page's own copy has the same shape.
    page = src()
    body = page[page.index("function matches"):page.index("readonly property var shown")]
    assert 'v.accent === "GB" ? "british" : "american"' in body
    assert "hay.indexOf(words[i]) < 0" in body


def test_the_library_says_what_an_empty_list_means():
    page = src()
    assert "No voice matches" in page and "Show All voices" in page


def test_used_for_is_the_agents_display_names():
    settings = (ROOT / "Settings.qml").read_text()
    fn = settings[settings.index("function voiceUsers(v)"):]
    fn = fn[:fn.index("\n  }\n")]
    assert "out.push(root.mainLabel)" in fn and 'out.push("main")' not in fn
    assert "root.agentLabel(a)" in fn
    row = scan(LIBRARY_ROW).nocomment
    assert '"Used for " + row.users' in row


def test_every_text_on_the_page_and_the_rows_is_plain():
    """An agent's name is whatever the person typed; `AutoText` would render
    anything in it that looks like HTML."""
    for path in (PAGE, LIBRARY_ROW, AGENT_ROW):
        sc = scan(path)
        for m in re.finditer(r'\bText \{', sc.clean):
            end = sc.closes[m.end() - 1]
            block = sc.nocomment[m.start():end]
            assert "textFormat: Text.PlainText" in block, f"{path.name}:{sc.lineno(m.start())}"


# --- hearing you -----------------------------------------------------------------------------------

def test_transcription_is_folded_under_advanced_with_one_line_on_what_it_does():
    page = src()
    sec = page[page.index("AdvancedSection {"):]
    assert 'title: "Advanced: hearing you"' in sec and "count: 2" in sec
    assert re.findall(r'\bput\("([A-Za-z]+)"', sec) == ["model", "livePartials"]
    assert "into text on this machine, before anything is sent to an agent" in sec


def test_the_models_offered_are_the_ones_the_manifest_declares():
    """Whisper is fetched by name with no hash, so no model is added until it
    is pinned (open question 10 of the plan); the page lists what it did."""
    page = src()
    sec = page[page.index('label: "Transcription model"'):page.index('label: "Live transcript')]
    offered = re.findall(r'\{ value: "([a-z.]+)", label:', sec)
    manifest = json.loads((ROOT / "manifest.json").read_text())
    entry = next(e for e in manifest["barWidget"]["schema"] if e["key"] == "model")
    assert offered == entry["options"] == ["tiny.en", "base.en", "small.en"]


# --- the preview ------------------------------------------------------------------------------------

def test_the_preview_stub_never_runs_the_real_voice_command():
    sh = (ROOT / "bench" / "preview" / "preview.sh").read_text()
    case = sh[sh.index("  voice)"):sh.index("  crew)")]
    assert 'if [ "\\${PREVIEW_REAL_VOICE:-}" != 1 ]; then printf' in case
    assert ">> '$out.writes'; exit 0; fi" in case


def test_the_agent_row_is_registered():
    q = (ROOT / "ui" / "qmldir").read_text()
    assert "VoiceAgentRow 1.0 VoiceAgentRow.qml" in q
