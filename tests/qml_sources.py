"""Where the QML for each surface lives, for the tests that read it.

The settings overlay was one 2,500-line Settings.qml. It is now that file --
what every page shares, the conversation view and the permission prompt --
plus one file per settings page in pages/. A test asking "is this setting
drawn" or "does this control fetch what it picks" reads them together, so it
keeps passing when a control moves between pages and fails when it is lost.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def overlay() -> str:
    """Settings.qml followed by every page it shows."""
    files = [ROOT / "Settings.qml", *sorted((ROOT / "pages").glob("*.qml"))]
    return "\n".join(p.read_text() for p in files)


def page(name: str) -> str:
    """One settings page, e.g. page("Listening") for pages/ListeningPage.qml."""
    return (ROOT / "pages" / f"{name}Page.qml").read_text()


def overlay_files() -> list[str]:
    """Repo-relative paths of every overlay file, for per-file checks."""
    return ["Settings.qml"] + [f"pages/{p.name}" for p in
                               sorted((ROOT / "pages").glob("*.qml"))]
