"""Every setting has one home.

The settings page was scattered: agent settings in three boxes, the wake word
in four. Splitting it into pages fixes that only while each setting stays on
the page it belongs to, so this holds it: every key the manifest declares is
*changed* on exactly one settings page. A key read elsewhere (the Overview
shows the gate, the Agents card names the voice) is fine; a second control
for it is the scattering coming back.

The popup's five quick toggles, voice and permission level are the deliberate
exception, and live in Panel.qml, not in pages/.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = sorted((ROOT / "pages").glob("*.qml"))


def _declared() -> set[str]:
    manifest = json.loads((ROOT / "manifest.json").read_text())
    return {k["key"] for k in manifest["barWidget"]["schema"]}


def _writers(key: str) -> list[str]:
    # `s.put("key", ...)`, or a page helper that writes one key of a per-agent
    # map, `putMap("key", ...)`.
    pattern = re.compile(r'\b(?:put|putMap)\("' + re.escape(key) + r'"')
    return [p.name for p in PAGES if pattern.search(p.read_text())]


def test_there_are_pages_to_check():
    assert len(PAGES) >= 7, [p.name for p in PAGES]


def test_every_setting_is_changed_on_exactly_one_page():
    wrong = {k: _writers(k) for k in sorted(_declared()) if len(_writers(k)) != 1}
    assert wrong == {}, wrong


def test_a_reset_goes_back_to_the_manifest_default():
    """`reset` links call resetKey, which needs the defaults the manifest
    declares; the overlay reads them from the file rather than relying on the
    shell to pass the manifest in."""
    settings = (ROOT / "Settings.qml").read_text()
    assert 'Qt.resolvedUrl("manifest.json")' in settings
    assert "m.barWidget.defaults" in settings


def test_every_page_is_reachable_from_the_sidebar():
    settings = (ROOT / "Settings.qml").read_text()
    for p in PAGES:
        assert f"{p.stem} {{ s: root }}" in settings, f"{p.name} is never shown"
