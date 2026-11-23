"""Other settings and About, as pages (master plan M26).

What these hold, read from the QML (the behaviour is driven in the preview
targets `other` and `about`, and the daemon side in test_diagnostics.py):

- the rename kept every key: Other settings writes exactly what Display did,
  and no key moved anywhere else;
- the old page id still opens the page, and every place that linked to About
  for an install now links where Install is;
- the keys are read live and opened read only, never written;
- About writes no setting and starts nothing that reaches out except from a
  click: the update check and the local probe are started by their buttons,
  never when the page opens;
- every Text on both pages that shows something read from outside is plain
  text, and a document opens in a pager with LESSSECURE, never an editor.
"""
from __future__ import annotations

import re
from pathlib import Path

from qml_scan import scan

ROOT = Path(__file__).resolve().parent.parent
OTHER = (ROOT / "pages" / "OtherSettingsPage.qml").read_text()
ABOUT = (ROOT / "pages" / "AboutPage.qml").read_text()
SETTINGS = (ROOT / "Settings.qml").read_text()

#: What Display wrote before M26, and Other settings writes now: nothing
#: added, nothing lost.
KEYS = {"hud", "hudLingerMs", "hudSize", "hudKeepReply", "hudPosition", "hudTextSize",
        "agentsPanel", "yieldToRecorders", "logSpeech", "keepStats"}


def _puts(src):
    return set(re.findall(r'\.put\(\s*"(\w+)"', src))


def test_other_settings_writes_what_display_did():
    assert _puts(OTHER) == KEYS
    for key in KEYS:
        assert f'resetKey("{key}")' in OTHER, key
    assert _puts(ABOUT) == set()


def test_the_page_is_renamed_and_the_old_id_still_opens_it():
    assert '{ id: "other",        label: "Other settings"' in SETTINGS
    assert 'id: "display"' not in SETTINGS
    go = SETTINGS[SETTINGS.index("function goTo("):SETTINGS.index("function showPage(")]
    assert 'if (pageId === "display") pageId = "other"' in go
    # Before the "known" test, or the alias would fall through to Overview.
    assert go.index('pageId = "other"') < go.index("var known")
    assert 'root.page === "other" ? otherPage' in SETTINGS
    assert "OtherSettingsPage { s: root }" in SETTINGS
    assert "OtherSettingsPage 1.0 OtherSettingsPage.qml" in (ROOT / "pages/qmldir").read_text()
    assert not (ROOT / "pages" / "DisplayPage.qml").exists()


def test_the_install_problem_links_to_where_install_now_is():
    assert '"The voice engine is not installed yet.", page: "other"' in SETTINGS
    assert re.search(r'page:\s*"about"', SETTINGS) is None


def test_the_readout_group_holds_the_four_m3_keys_preview_and_the_agents_panel():
    start = OTHER.index('title: "ON-SCREEN READOUT"')
    group = OTHER[start:OTHER.index("SettingsGroup {", start)]
    for key in ("hud", "hudLingerMs", "hudSize", "hudKeepReply", "hudPosition", "hudTextSize",
                "agentsPanel"):
        assert f'put("{key}"' in group, key
    assert "previewHud()" in group


def test_privacy_holds_its_keys_the_chats_pointer_and_the_lock_line():
    start = OTHER.index('title: "PRIVACY"')
    group = OTHER[start:OTHER.index("SettingsGroup {", start)]
    for key in ("yieldToRecorders", "logSpeech", "keepStats"):
        assert f'put("{key}"' in group, key
    assert 'goTo("chats", "")' in group and "clearStats()" in group
    assert "The mic always closes while the screen is locked" in group


def test_the_keys_are_read_live_and_never_written():
    assert 'command: ["agentvoice", "keys", "--json"]' in OTHER
    start = OTHER.index('title: "KEYS"')
    group = OTHER[start:OTHER.index("SettingsGroup {", start)]
    assert "page.keysInfo.rows" in group
    # No fixed list of Hyprland keys left on the page: only the bar icon's
    # own clicks, which are the widget's.
    for fixed in ('"Hold F8"', '"Super+Ctrl+Space"', '"Super+Alt+Space"'):
        assert fixed not in OTHER, fixed
    # The file opens through one checked function, as one argv element.
    assert 'bindingsOpener.command = ["omarchy-launch-editor", f]' in OTHER
    s = scan(ROOT / "pages" / "OtherSettingsPage.qml")
    starts = [m.start() for m in re.finditer(r"bindingsOpener\.running\s*=", s.nocomment)]
    assert {s.handler_of(p) for p in starts} == {"function openBindings"}
    body = OTHER[OTHER.index("function bindingsPath()"):OTHER.index("Process { id: bindingsOpener }")]
    assert "hypr" in body and "bindings" in body and '"/../"' in body


def test_maintenance_is_on_other_settings():
    start = OTHER.index('title: "MAINTENANCE"')
    group = OTHER[start:]
    assert "fetchNow([])" in group and 'fetchNow(["--oww"])' in group and 'fetchNow(["--sherpa"])' in group
    assert "DangerButton {" in group and "onConfirmed: page.s.removeEverything()" in group
    assert group.index("fetchNow([])") < group.index("removeEverything"), "Remove stays last"
    assert 'title: "MAINTENANCE"' not in ABOUT and 'title: "REMOVE"' not in ABOUT


def test_about_reaches_out_only_from_a_click():
    """The update check asks a remote and the probe opens sockets: each is
    started by its function, and each function only by its button."""
    s = scan(ROOT / "pages" / "AboutPage.qml")
    for proc, fn in (("updater", "checkUpdates"), ("prober", "probeLocal"), ("copier", "copyDiagnostics")):
        starts = [m.start() for m in re.finditer(proc + r"\.running\s*=\s*true", s.nocomment)]
        assert starts and {s.handler_of(p) for p in starts} == {"function " + fn}, proc
        calls = [p for p in s.calls(re.compile(r"\b" + fn + r"\s*\("))]
        assert calls and {s.handler_of(p) for p in calls} == {"onClicked"}, fn
    opened = ABOUT[ABOUT.index("Component.onCompleted: {"):]
    opened = opened[:opened.index("}")]
    assert "updater" not in opened and "prober" not in opened and "copier" not in opened


def test_about_passes_its_own_folder_and_never_anything_said():
    for verb in ('["agentvoice", "about", "--json", "--plugin", page.pluginDir]',
                 '["agentvoice", "diagnostics", "copy", "--plugin", page.pluginDir]',
                 '["agentvoice", "about", "updates", "--json", "--plugin", page.pluginDir]',
                 '["agentvoice", "about", "backends", "--json"]',
                 '["agentvoice", "endpoint", "probe-local"]',
                 '["agentvoice", "commands", "--json"]'):
        assert verb in ABOUT, verb


def test_a_document_opens_read_only_and_only_the_three():
    body = ABOUT[ABOUT.index("function openDoc(name)"):]
    body = body[:body.index("\n  }")]
    assert r"/^(CHANGELOG\.md|LICENSE|README\.md)$/.test(name)" in body
    assert '"env", "LESSSECURE=1", "less", "--"' in body
    assert "omarchy-launch-editor" not in ABOUT


def test_every_text_on_both_pages_is_plain_text():
    """A remote's URL, an agent's name, a model's, a journal line and the
    report are all outside text: AutoText would render one that looks like
    HTML (CLAUDE.md). The fixed labels are held to it too, so a new Text
    showing a value cannot slip through by sitting among them."""
    for path in (ROOT / "pages" / "AboutPage.qml", ROOT / "ui" / "InfoRow.qml"):
        src = path.read_text()
        blocks = re.findall(r"\bText \{(.*?)\n\s*\}", src, re.S)
        assert blocks
        for b in blocks:
            assert "textFormat: Text.PlainText" in b, (path.name, b[:120])
    # On Other settings, every Text that shows something read in.
    for needle in ("text: page.keysError", "text: modelData.keys", "text: modelData.what + ",
                   "text: page.statsNote"):
        at = OTHER.index(needle)
        block = OTHER[OTHER.rfind("Text {", 0, at):at + 400]
        assert "textFormat: Text.PlainText" in block, needle


def test_the_commands_are_the_daemons_never_a_copy():
    """No command phrase is written on the About page: the list is the
    table `agentvoice commands --json` prints (as on Conversation, M24)."""
    import speech_text
    phrases = {p for c in speech_text.COMMANDS for p in c.phrases}
    quoted = set(re.findall(r'"([a-z][a-z ]{2,40})"', ABOUT))
    assert not (quoted & phrases), quoted & phrases


def test_found_is_never_called_connected():
    assert "connected" not in ABOUT.replace("not the same as an agent using it", "").lower()
    assert "Installed means its program was found; it does not mean it is signed in." in ABOUT


def test_info_row_is_a_building_block_with_no_setting_in_it():
    src = (ROOT / "ui" / "InfoRow.qml").read_text()
    assert "put(" not in src and "setting(" not in src
    assert "InfoRow 1.0 InfoRow.qml" in (ROOT / "ui" / "qmldir").read_text()


def test_the_preview_stub_reaches_out_to_nothing():
    """Copy, Check for updates, the probe and the launchers are logged in a
    preview, never run: the real clipboard, a remote, a socket, an editor."""
    sh = (ROOT / "bench" / "preview" / "preview.sh").read_text()
    stub = sh[sh.index("  about|diagnostics)"):sh.index("  start|stop|restart|toggle")]
    assert 'if [ "\\${2:-}" = updates ]; then' in stub
    assert 'if [ "\\$1" = diagnostics ] && [ "\\${2:-}" = copy ]; then' in stub
    assert 'if [ "\\${2:-}" = probe-local ]; then' in stub
    assert "for launcher in omarchy-launch-editor omarchy-launch-tui; do" in sh
    # The synthetic journal holds a transcript line the report must drop.
    assert "PREVIEW-TRANSCRIPT" in sh
