"""Agent details' personality tools (master plan M6, item 10).

- **Trait chips** write one managed line at the top of personality.md and
  read it back. Free text is never touched, hand-typed values are kept, and
  a write keeps the `--base` stamp check, against an outside writer too.
- **The budget counts the line**, and the meter counts what is actually
  told: FileEditor.sentChars is run in node against agentfs.clean itself.
- **Starter templates** exist for each box and fit its budget.
- **The page** offers tabs keyed by id, the chips through the one editor,
  and Try it with the draft on stdin.
"""
from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import agentfs
import paths
import traits
from qml_scan import scan

ROOT = Path(__file__).resolve().parent.parent
DAEMON = ROOT / "daemon"
TEMPLATE = (DAEMON / "templates" / "agent" / "personality.md").read_text()
PAGE = (ROOT / "pages" / "AgentDetailsPage.qml").read_text()
EDITOR = ROOT / "ui" / "FileEditor.qml"


@pytest.fixture(autouse=True)
def data(tmp_path, monkeypatch):
    d = tmp_path / "data"
    monkeypatch.setattr(paths, "DATA_DIR", d)
    monkeypatch.setattr(paths, "AGENTS_DIR", d / "agents")
    monkeypatch.setattr(paths, "COMMUNAL_DIR", d / "communal")
    agentfs._LAST_GOOD.clear()
    return d


# --- the managed line ----------------------------------------------------------------

FREE = [
    "",
    "I am Theo. I speak plainly.",
    "First paragraph.\n\nSecond paragraph,\nwith a line break.\n",
    "  indented start\n\ttab inside\n",
    "Ünïcödé ☀ and an emoji 🎙️.\n",
    "Traits are not this line: it says so in the middle.\nTraits: warm.",
    TEMPLATE,
    TEMPLATE + "Free text after the starter comment.\n",
    "<!-- a comment -->\n<!-- and another -->\nThen words.",
]


@pytest.mark.parametrize("free", FREE)
def test_choosing_and_clearing_every_trait_gives_back_the_free_text_byte_for_byte(free):
    text = free
    for cat, values in traits.TRAITS.items():
        for v in values:
            text = traits.apply(text, {cat: v})
            assert traits.parse(text)["traits"][cat] == v
    assert traits.parse(text)["line"]
    back = traits.apply(text, {k: None for k in traits.TRAITS})
    assert back == free
    assert not traits.parse(back)["line"] or free.startswith("Traits")


@pytest.mark.parametrize("free", FREE[1:])
def test_the_free_text_is_never_changed_whatever_the_line_says(free):
    once = traits.apply(free, {"tone": "dry", "length": "brief"})
    twice = traits.apply(once, {"tone": "playful", "formality": "formal"})
    rest = lambda t: t.split("Traits: ", 1)[1].split("\n", 1)[1] if "Traits: " in t else t  # noqa: E731
    head, m = traits._split(twice)
    assert twice[m.end():] == once[traits._split(once)[1].end():]
    assert m.group(0).startswith("Traits: playful, brief, formal.")
    assert rest(once) == rest(twice)


def test_the_line_sits_after_the_starter_comment_so_the_comment_stays_untold():
    text = traits.apply(TEMPLATE, {"tone": "warm"})
    assert text.startswith(TEMPLATE)
    assert agentfs.clean(text) == "Traits: warm."
    # Above the comment, the comment would no longer lead the file and the
    # agent would be told it.
    assert agentfs.clean("Traits: warm.\n" + TEMPLATE) != "Traits: warm."


def test_the_line_is_written_in_a_fixed_order():
    text = traits.apply("", {"formality": "casual", "tone": "warm", "length": "brief"})
    assert text == "Traits: warm, brief, casual.\n"


def test_unknown_hand_typed_values_are_kept_and_a_category_holds_one_value():
    typed = "traits: Warm, Dry, sarcastic , very British.\nRest."
    got = traits.parse(typed)
    assert got["traits"] == {"tone": "warm", "length": None, "formality": None}
    assert got["unknown"] == ["sarcastic", "very british"]
    new = traits.apply(typed, {"tone": "playful"})
    assert new == "Traits: playful, sarcastic, very british.\nRest."
    # Clearing every chip keeps a line while it still holds a typed value.
    assert traits.apply(new, {"tone": None}) == "Traits: sarcastic, very british.\nRest."


def test_a_paragraph_that_merely_starts_with_traits_is_not_the_line():
    long = "Traits: " + "warm and kind, " * 20 + "and more."
    assert not traits.parse(long)["line"]
    assert traits.apply(long, {"tone": "dry"}).endswith("\n\n" + long)
    middle = "Hello.\nTraits: warm."
    assert not traits.parse(middle)["line"]


def test_a_category_or_value_that_is_not_a_trait_is_refused():
    for bad in ({"colour": "red"}, {"tone": "loud"}, {"tone": 3}, ["tone"]):
        with pytest.raises(ValueError):
            traits.apply("x", bad)


# --- the budget, and the CLI on the file ---------------------------------------------------

def test_the_budget_counts_the_managed_line():
    agentfs.write("main", "personality.md", "x" * 1495)
    path, _ = agentfs._resolve("main", "personality.md")
    text = traits.apply(path.read_text(), {"tone": "warm"})
    agentfs.write("main", "personality.md", text)
    got = agentfs.read_file("main", "personality.md")
    assert got["problem"] and len(got["text"]) == 1500
    assert got["text"].startswith("Traits: warm.")
    assert len(agentfs.clean(text)) == len("Traits: warm.\n\n") + 1495


def run(*argv, stdin: str = ""):
    out, err = io.StringIO(), io.StringIO()
    old = sys.stdin, sys.stdout, sys.stderr
    sys.stdin = io.TextIOWrapper(io.BytesIO(stdin.encode()), encoding="utf-8")
    sys.stdout, sys.stderr = out, err
    try:
        code = agentfs.main(list(argv))
    finally:
        sys.stdin, sys.stdout, sys.stderr = old
    return code, out.getvalue(), err.getvalue()


def test_traits_set_writes_on_the_stamp_it_was_given_and_get_reads_it_back():
    agentfs.create("sora")
    code, out, _ = run("traits", "get", "sora", "--json")
    stamp = json.loads(out)["stamp"]
    code, out, err = run("traits", "set", "sora", "--base", stamp,
                         stdin='{"traits": {"tone": "dry", "length": "brief"}}\n')
    assert code == 0, err
    code, out, _ = run("traits", "get", "sora", "--json")
    got = json.loads(out)
    assert got["traits"] == {"tone": "dry", "length": "brief", "formality": None}
    assert got["stamp"] != stamp
    # Through the module that saves versions: Keep/Revert still work on it.
    assert not agentfs.read_file("sora", "personality.md")["changed_outside"]


def test_traits_set_refuses_a_stale_stamp_after_an_outside_write():
    agentfs.create("sora")
    _, out, _ = run("traits", "get", "sora", "--json")
    stamp = json.loads(out)["stamp"]
    path, _ = agentfs._resolve("sora", "personality.md")
    path.write_text("Written by hand, outside Settings.\n")
    code, _, err = run("traits", "set", "sora", "--base", stamp, stdin='{"traits": {"tone": "warm"}}')
    assert code == 3 and err.startswith("conflict: personality.md changed")
    assert path.read_text() == "Written by hand, outside Settings.\n"


def test_traits_set_with_no_base_still_never_overwrites_a_write_in_between(monkeypatch):
    """No --base: the stamp it read is the base, so a hand save between its
    read and its write is refused rather than lost."""
    agentfs.create("sora")
    path, _ = agentfs._resolve("sora", "personality.md")
    real = agentfs.write

    def racing(*a, **k):
        path.write_text("A hand save that landed meanwhile.\n")
        return real(*a, **k)
    monkeypatch.setattr(agentfs, "write", racing)
    code, _, err = run("traits", "set", "sora", stdin='{"traits": {"tone": "warm"}}')
    assert code == 3, err
    assert path.read_text() == "A hand save that landed meanwhile.\n"


def test_traits_apply_is_pure_and_reports_the_count_told():
    code, out, _ = run("traits", "apply", stdin=json.dumps(
        {"text": TEMPLATE + "Hello.", "traits": {"formality": "formal"}}))
    d = json.loads(out)
    assert code == 0 and d["text"] == traits.apply(TEMPLATE + "Hello.", {"formality": "formal"})
    assert d["chars"] == len("Traits: formal.\n\nHello.")
    assert not paths.AGENTS_DIR.exists()       # wrote nothing


def test_traits_refuse_bad_input_with_words_not_a_traceback():
    agentfs.create("sora")
    for argv, stdin in [(("traits", "apply"), "not json"), (("traits", "apply"), "[1]"),
                        (("traits", "apply"), '{"traits": {"tone": "loud"}}'),
                        (("traits", "set", "communal"), "{}"), (("traits", "get"), ""),
                        (("traits", "get", "../x"), "")]:
        code, _, err = run(*argv, stdin=stdin)
        assert code == 1 and err.startswith("agentvoice agents: "), (argv, err)


def test_the_choices_never_travel_in_argv():
    """The page writes them on stdin; the CLI has no argument for them."""
    trait_calls = re.findall(r'"agents",\s*"traits",\s*"(\w+)"[^\]]*\]', PAGE)
    assert trait_calls and set(trait_calls) == {"apply"}
    assert re.search(r'id: traitWriter[\s\S]*?stdinEnabled: true', PAGE)
    assert re.search(r'id: traitReader[\s\S]*?stdinEnabled: true', PAGE)


# --- starter templates ------------------------------------------------------------------------

def test_every_box_has_starters_and_each_fits_its_budget():
    got = agentfs.starters()
    assert set(got) == {"role", "personality", "instructions"}
    for kind, items in got.items():
        assert len(items) >= 3, kind
        files = sorted((DAEMON / "templates" / kind).glob("*.md"))
        assert len(items) == len(files), f"a {kind} starter was left out as broken"
        for x in items:
            assert x["label"] and x["text"] == agentfs.clean(x["text"])
            assert len(x["text"]) <= agentfs.AGENT_FILES[agentfs.STARTER_KINDS[kind]]


def test_a_broken_or_oversize_starter_is_left_out(tmp_path, monkeypatch):
    (tmp_path / "role").mkdir()
    (tmp_path / "role" / "ok.md").write_text("<!-- Fine -->\nShort role.\n")
    (tmp_path / "role" / "long.md").write_text("<!-- Long -->\n" + "x" * 301)
    (tmp_path / "role" / "nolabel.md").write_text("No label line.\n")
    (tmp_path / "role" / "binary.md").write_bytes(b"\xff\xfe")
    monkeypatch.setattr(agentfs, "TEMPLATES", tmp_path)
    got = agentfs.starters()
    assert [x["id"] for x in got["role"]] == ["ok"] and got["personality"] == []


def test_the_page_offers_starters_only_for_an_empty_read_box():
    fn = PAGE[PAGE.index("function offerStarters("):]
    body = fn[:fn.index("\n  }")]
    for cond in ("ed.loaded", "!ed.holding", "!ed.editing", 'ed.current.trim() === ""'):
        assert cond in body
    assert PAGE.count("StarterChips {") == 3
    for ed in ("roleEditor", "personalityEditor", "instructionsEditor"):
        assert f"page.offerStarters({ed})" in PAGE and f"{ed}.fill(t)" in PAGE


# --- the meter counts what is told -------------------------------------------------------------

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed, so the meter's JavaScript cannot be run")

CORPUS = [
    "", "   ", "plain", "  padded  ", "﻿﻿BOMs first", "line\r\nendings\rold mac",
    "tabs\tbecome\tspaces", "controls\x00\x01\x07\x1b[31m gone\x7f", "\u0085next-line ends\u0085",
    "nbsp inside and ", "　ideographic　", "zero​width stays",
    "emoji 🎙️👩‍💻 count as code points", "<!-- c -->after", "  \n<!-- one -->\n<!--two-->\nleft",
    "text <!-- not leading --> kept", "<!-- unclosed comment stays", TEMPLATE,
    TEMPLATE + "Traits: warm.\n\nHello.", "trailing feff﻿", "x" * 1600,
]


@needs_node
def test_the_meter_counts_exactly_what_clean_keeps():
    s = scan(EDITOR)
    m = re.search(r"\bfunction sentChars\(", s.clean)
    brace = s.clean.index("{", m.end())
    fn = s.src[m.start():s.closes[brace] + 1]
    script = f"{fn}\nconsole.log(JSON.stringify(JSON.parse(process.argv[1]).map(sentChars)))"
    out = subprocess.run([NODE, "-e", script, json.dumps(CORPUS)], capture_output=True,
                         text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [len(agentfs.clean(t)) for t in CORPUS]


def test_the_editor_draws_the_meter_and_refuses_a_save_by_the_same_count():
    box = EDITOR.read_text()
    assert "BudgetMeter {" in box and "used: fe.sentChars(box.text)" in box
    assert "showCounter: false" in box
    save = box[box.index("function save("):box.index("function keepMine(")]
    assert "fe.sentChars(t) > fe.limit" in save


# --- the page --------------------------------------------------------------------------------

def test_agent_tabs_replace_the_drop_down_keyed_by_id_main_first():
    assert "Dropdown {" not in PAGE and "agentPicker" in PAGE
    tabs = PAGE[PAGE.index("readonly property var agentTabs:"):]
    tabs = tabs[:tabs.index("\n  }\n")]
    assert tabs.index('id: "main"') < tabs.index("for (var i = 0")
    assert "id: id, label:" in tabs and "s.agentId(a)" in tabs
    block = PAGE[PAGE.index("AgentTabs {"):]
    block = block[:block.index("\n  }\n")]
    assert "current: page.target" in block
    assert "onPicked: function(id) { page.s.detailsAgent = id }" in block


def test_the_deep_link_still_reaches_an_agent_and_a_tab():
    settings = (ROOT / "Settings.qml").read_text()
    go = settings[settings.index("function goTo("):]
    assert 'if (agent) { detailsAgent = agent; detailsTab = validTab ? tab : "prompt" }' in go


def test_the_chips_save_through_the_editor_never_beside_it():
    writer = PAGE[PAGE.index("id: traitWriter"):]
    writer = writer[:writer.index("\n  }\n")]
    assert "personalityEditor.fill(d.text)" in writer
    assert '"agents", "write"' not in PAGE


def test_try_it_sends_the_draft_on_stdin_and_is_rate_limited_on_the_page():
    fn = PAGE[PAGE.index("function tryIt()"):]
    fn = fn[:fn.index("\n  }\n")]
    assert 'tryer.command = ["agentvoice", "try", page.target]' in fn
    assert "personalityEditor.current" in fn and "instructionsEditor.current" in fn
    assert "tryer.pending = JSON.stringify(" in fn and "tryCooldown.restart()" in fn
    proc = PAGE[PAGE.index("id: tryer"):]
    assert "stdinEnabled: true" in proc[:600]
    assert "Timer { id: tryCooldown; interval: 10000 }" in PAGE
    assert "!tryCooldown.running" in PAGE[PAGE.index("id: tryButton"):][:400]


def test_new_text_on_the_page_is_plain():
    for rel in ("ui/BudgetMeter.qml", "ui/StarterChips.qml"):
        body = (ROOT / rel).read_text()
        assert body.count("Text {") == body.count("textFormat: Text.PlainText"), rel
