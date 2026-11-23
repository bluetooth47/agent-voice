"""The session's conversation, kept for reading back, and a readout that fits it.

Asked for from use: "there isn't a place to see the full chat easily, and if a
response or prompt is too long the popup is too small". Three things answer
it -- a record of the session, a page to read it on, and a HUD that grows to
fit -- and this file holds each of them to what it promises, including the
privacy promise: memory only, the owner only, gone at logout, and off means
deleted.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

import runtime
from adapters.base import Chunk
from runtime import HISTORY_MAX, REPLY_MAX, History

ROOT = Path(__file__).resolve().parent.parent


def _code(path: Path) -> str:
    """QML without its comments, so prose cannot satisfy an assertion."""
    out = []
    for line in path.read_text().splitlines():
        if line.strip().startswith("//"):
            continue
        out.append(line.split("//", 1)[0] if "//" in line and "://" not in line
                   else line)
    return "\n".join(out)


# --- the record -----------------------------------------------------------------

def test_it_lives_beside_the_state_file_in_the_runtime_directory():
    """tmpfs, gone at logout. Never the journal and never the disk."""
    assert History().path.parent == runtime.RUNTIME_DIR
    assert History().path.name == "history.jsonl"


def test_only_the_owner_can_read_it(tmp_path):
    h = History(tmp_path / "history.jsonl")
    h.append({"transcript": "my pin is 4421"})
    assert stat.S_IMODE(h.path.stat().st_mode) == 0o600


def test_a_loose_file_is_tightened_on_the_next_turn(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text("")
    path.chmod(0o644)
    History(path).append({"transcript": "x"})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_turns_are_appended_one_per_line(tmp_path):
    h = History(tmp_path / "history.jsonl")
    h.append({"transcript": "one"})
    h.append({"transcript": "two"})
    rows = [json.loads(l) for l in h.path.read_text().splitlines()]
    assert [r["transcript"] for r in rows] == ["one", "two"]


def test_it_keeps_the_most_recent_turns_and_no_more(tmp_path):
    h = History(tmp_path / "history.jsonl")
    for i in range(HISTORY_MAX + 5):
        h.append({"n": i})
    rows = [json.loads(l) for l in h.path.read_text().splitlines()]
    assert len(rows) == HISTORY_MAX
    assert rows[0]["n"] == 5 and rows[-1]["n"] == HISTORY_MAX + 4
    assert stat.S_IMODE(h.path.stat().st_mode) == 0o600, "the rewrite loosened it"


def test_a_failure_to_write_never_costs_the_turn(tmp_path):
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("")
    History(blocked / "history.jsonl").append({"transcript": "x"})   # no raise


def test_clear_is_idempotent(tmp_path):
    h = History(tmp_path / "history.jsonl")
    h.clear()
    h.append({"transcript": "x"})
    h.clear()
    assert not h.path.exists()


# --- what a turn records ------------------------------------------------------------

class Agent:
    name = "claude"

    def __init__(self, *chunks):
        self.chunks = chunks

    def send(self, text, session_id=None):
        yield from self.chunks

    def cancel(self):
        pass


@pytest.fixture
def recorded(daemon, tmp_path):
    daemon.history = History(tmp_path / "history.jsonl")
    daemon.cfg._values["keepHistory"] = True

    def rows():
        if not daemon.history.path.exists():
            return []
        return [json.loads(l) for l in daemon.history.path.read_text().splitlines()]

    return daemon, rows


def test_a_turn_records_what_was_heard_and_what_was_said(recorded):
    daemon, rows = recorded
    daemon.agent = Agent(Chunk(session_id="s1"), Chunk(text="It is ten past four."))
    daemon.answer("what time is it", {"transcript": "what time is it"})
    [row] = rows()
    assert row["transcript"] == "what time is it"
    assert row["reply"] == "It is ten past four."
    assert row["agent"] == "claude" and row["new"] is True
    assert row["error"] == "" and row["stopped"] is False


def test_a_following_turn_is_part_of_the_same_conversation(recorded):
    daemon, rows = recorded
    daemon.session_id = "s1"
    daemon.agent = Agent(Chunk(text="Yes."))
    daemon.answer("and tomorrow", {"transcript": "x"})
    assert rows()[0]["new"] is False


def test_a_failed_turn_records_why_and_never_the_message(recorded):
    daemon, rows = recorded
    daemon.agent = Agent(Chunk(error="You've hit your limit · resets 7pm "
                                     "while answering: my pin is 4421"))
    daemon.answer("what is my pin", {"transcript": "x"})
    [row] = rows()
    assert row["error"] == "limit"
    assert "4421" not in json.dumps(row), "the error text reached the record"
    assert row["reply"].startswith("Claude has hit its usage limit")


def test_a_long_answer_is_kept_whole(recorded):
    """The readout cut replies at 400 characters, mid-sentence."""
    daemon, rows = recorded
    long = " ".join(f"Sentence number {i} of a long answer." for i in range(40))
    daemon.agent = Agent(Chunk(text=long))
    last = {"transcript": "x"}
    daemon.answer("explain", last)
    assert len(long) > 400
    assert rows()[0]["reply"] == long
    assert last["reply"] == long[:REPLY_MAX], "and the readout gets all of it"


def test_off_records_nothing(recorded):
    daemon, rows = recorded
    daemon.cfg._values["keepHistory"] = False
    daemon.agent = Agent(Chunk(text="Hello."))
    daemon.answer("hi", {"transcript": "x"})
    assert rows() == []


def test_off_deletes_what_was_already_kept(recorded, monkeypatch):
    """Turning it off is saying the words should not be kept -- including the
    ones that already were."""
    daemon, rows = recorded
    daemon.history.append({"transcript": "earlier"})
    daemon.cfg._values["keepHistory"] = False
    for name in ("reconcile_agent", "reconcile_voice"):
        monkeypatch.setattr(daemon, name, lambda *a, **k: None)
    class Pipe:
        def reconcile_vocab(self):
            pass
    daemon.pipe = Pipe()
    monkeypatch.setattr(daemon.cfg, "reload", lambda: False)
    daemon.refresh()
    assert not daemon.history.path.exists()


def test_nothing_about_a_turn_goes_to_the_journal_because_of_this(recorded, capsys):
    daemon, _ = recorded
    daemon.agent = Agent(Chunk(text="The code is 4421."))
    daemon.answer("what is the code", {"transcript": "x"})
    assert "4421" not in capsys.readouterr().out


def test_the_setting_exists_in_all_three_places():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    assert "keepHistory" in {k["key"] for k in manifest["barWidget"]["schema"]}
    assert manifest["barWidget"]["defaults"]["keepHistory"] is \
        runtime.DEFAULTS["keepHistory"]
    from qml_sources import overlay
    assert '"keepHistory"' in overlay()


# --- agentvoice history ------------------------------------------------------------

jq = pytest.mark.skipif(shutil.which("jq") is None,
                        reason="agentvoice history is jq, and jq is not here")


def _cli(rt: Path, *args):
    env = {**os.environ, "XDG_RUNTIME_DIR": str(rt)}
    return subprocess.run([str(ROOT / "bin" / "agentvoice"), "history", *args],
                          capture_output=True, text=True, env=env, timeout=20)


@jq
def test_the_terminal_listing_cannot_carry_escape_sequences(tmp_path):
    """A reply is model output; raw, it could repaint the terminal."""
    (tmp_path / "agentvoice").mkdir()
    (tmp_path / "agentvoice" / "history.jsonl").write_text(
        json.dumps({"at": 1, "agent": "claude", "transcript": "hi",
                    "reply": "ok\u001b]0;pwned\u0007 done", "new": True}) + "\n"
        + "this line is damaged\n"
        + json.dumps({"at": 2, "agent": "claude", "transcript": "again",
                      "reply": "", "error": "limit"}) + "\n")
    out = _cli(tmp_path)
    assert out.returncode == 0, out.stderr
    assert "\u001b" not in out.stdout and "\u0007" not in out.stdout
    assert "you: hi" in out.stdout and "you: again" in out.stdout, \
        "one damaged line took the rest of the listing with it"
    assert "[failed: limit]" in out.stdout


@jq
def test_clear_deletes_it(tmp_path):
    (tmp_path / "agentvoice").mkdir()
    path = tmp_path / "agentvoice" / "history.jsonl"
    path.write_text("{}\n")
    assert _cli(tmp_path, "clear").returncode == 0
    assert not path.exists()


# --- the screens ----------------------------------------------------------------------

HUD = _code(ROOT / "Hud.qml")
SETTINGS = _code(ROOT / "Settings.qml")
PANEL = _code(ROOT / "Panel.qml")


def test_no_qml_reads_a_colour_through_a_bare_color():
    """On Qt 6.12 a bare `Color` is QtQuick's own value-type helper, not the
    theme, so every colour read through it was undefined -- and the QML check
    had been failing on exactly this, 25 times, for a while. Omarchy's own
    files write Commons.Color."""
    files = [*ROOT.glob("*.qml"), *ROOT.glob("ui/*.qml"), *ROOT.glob("pages/*.qml"),
             *ROOT.glob("bench/preview/targets/*.qml")]
    assert len(files) > 5, "found almost no QML -- the glob is wrong, not the code clean"
    for qml in files:
        bare = re.findall(r"(?<![\w.])Color\.\w+", _code(qml))
        assert not bare, f"{qml.relative_to(ROOT)} reads the theme through a bare Color: {bare}"


def test_the_readout_no_longer_cuts_the_text_off():
    """In dynamic mode. Locked mode (phase M3) cuts on purpose, in
    ui/ReadoutLines, and the one-line header elides its status; neither is
    the transcript or the answer of a dynamic readout."""
    dynamic = HUD[HUD.index("ReadoutLines {"):]
    dynamic = dynamic[dynamic.index("\n        }") + 1:]
    assert "maximumLineCount" not in dynamic
    assert "ElideRight" not in dynamic
    header = HUD[HUD.index("id: headerLabel"):HUD.index("id: clickHint")]
    assert HUD.count("maximumLineCount") == header.count("maximumLineCount") == 1


def test_the_readout_scrolls_past_its_limit_and_follows_the_answer():
    assert "Flickable" in HUD
    assert re.search(r"implicitHeight:\s*Math\.min\(maxHeight", HUD), \
        "it must stop growing somewhere"
    assert "following" in HUD and "contentY = contentHeight - height" in HUD


def test_the_readout_widens_to_fit_rather_than_staying_280():
    assert "TextMetrics" in HUD
    assert re.search(r"implicitWidth:\s*textWidth", HUD)


def test_hovering_holds_it_open_but_a_lock_still_does_not_wait():
    assert "HoverHandler" in HUD
    linger = HUD[HUD.index("id: linger"):]
    linger = linger[:linger.index("}")]
    assert "hover.hovered" in linger, "the countdown ignores the pointer"
    lock = HUD[HUD.index("onVStateChanged:"):]
    lock = lock[:lock.index("\n")]
    assert "hover" not in lock, "a hover must not hold it over the lock screen"


def test_a_click_on_the_readout_opens_the_conversation():
    assert "signal openConversation()" in HUD
    assert "hud.openConversation()" in HUD
    block = PANEL[PANEL.index("  Hud {"):]
    block = block[:block.index("\n  }") + 4]
    assert "onOpenConversation: conversation.running = true" in block
    summon = PANEL[PANEL.index("id: conversation"):]
    summon = summon[:summon.index("}")]
    # The Chats page since phase M18 (a "history" mode of the overlay before).
    assert '\\"page\\":\\"chats\\"' in summon


def test_the_conversation_page_reads_the_file_the_daemon_writes():
    assert '"/agentvoice/history.jsonl"' in SETTINGS
    assert 'p.mode === "history"' in SETTINGS


def test_the_conversation_page_closes_when_the_screen_locks():
    """The conversation, and the Overview's last exchange, are on a surface
    that draws over the lock screen, so they go. Since phase M7 a permission
    prompt goes too, as a no: it would show the command over the lock
    screen, and the daemon refuses an allow while locked anyway."""
    handler = SETTINGS[SETTINGS.index("onVStateChanged:"):]
    handler = handler[:handler.index("\n  }\n")]
    assert '"locked"' in handler and "close()" in handler
    assert 'mode === "permission"' in handler and "dismiss()" in handler
    # dismiss() on an unanswered card is a deny, never a hide alone.
    body = SETTINGS[SETTINGS.index("function dismiss()"):]
    body = body[:body.index("\n  }")]
    assert 'answer("deny")' in body


def _blocks(src: str, opener: str) -> list[str]:
    """Each `opener {...}` block, by brace depth."""
    out, at = [], 0
    while (at := src.find(opener, at)) >= 0:
        depth, end = 0, at
        for end in range(src.index("{", at), len(src)):
            depth += {"{": 1, "}": -1}.get(src[end], 0)
            if depth == 0:
                break
        out.append(src[at:end + 1])
        at = end
    return out


def test_what_was_said_is_selectable_and_never_rendered_as_markup():
    """One exchange is drawn by ui/ExchangeItem.qml, for this session's view
    and a saved chat alike (both in Chats.qml, the Chats page since M18), as
    two ui/ChatBubbles: that is where both halves are checked."""
    assert "id: historyPage" not in SETTINGS, "one conversation view, not two"
    assert _code(ROOT / "Chats.qml").count("delegate: ExchangeItem {") == 2
    item = _code(ROOT / "ui/ExchangeItem.qml")
    bubbles = _blocks(item, "ChatBubble {")
    assert len(bubbles) == 2
    assert any("text: turn.heard" in b for b in bubbles)
    assert any("text: turn.answer" in b for b in bubbles)
    edits = _blocks(_code(ROOT / "ui/ChatBubble.qml"), "TextEdit {")
    assert len(edits) == 1
    for block in edits:
        assert "readOnly: true" in block and "selectByMouse: true" in block
        formats = re.findall(r"textFormat:\s*(\S+)", block)
        assert formats == ["TextEdit.PlainText"], \
            f"neither half of the conversation was written by us: {formats}"
    # Everything else ExchangeItem shows of it -- the thinking, an aside's
    # line, who failed -- is plain too.
    for block in _blocks(item, "Text {"):
        if re.search(r"text:[^\n]*turn\.(thinking|aside|who)", block):
            assert "textFormat: Text.PlainText" in block, block[:160]


def test_clearing_takes_two_presses():
    """A DangerButton since M1: the first press arms it, and clearing runs
    only from onConfirmed (tests/test_confirms.py holds that for every
    caller of clearSession)."""
    # On the Chats page's "This session" since phase M18.
    chats = _code(ROOT / "Chats.qml")
    [button] = [b for b in _blocks(chats, "DangerButton {") if 'text: "Clear"' in b]
    assert "onConfirmed: view.s.clearSession()" in button
    assert '["agentvoice", "history", "clear"]' in SETTINGS


def test_a_saved_chat_is_never_rendered_as_markup():
    """Titles come from what was said, names are any text, and a note can
    quote the CLI's error: every Text in the browser that shows one is
    plain."""
    src = _code(ROOT / "Chats.qml")
    risky = re.compile(r"text:[^\n]*(title|agentName|note|preview|\.c\b|chat\.)")
    shown = [b for b in _blocks(src, "Text {") if risky.search(b)]
    assert len(shown) >= 5
    for block in shown:
        assert "textFormat: Text.PlainText" in block, block[:200]
