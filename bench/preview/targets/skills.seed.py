"""Synthetic skill folders for the `skills` preview target (phase M11):
Theo has one of his own; Sora has one of her own and one that is broken
(listed, given to nobody); Communal has two. Plain files written into
PREVIEW_DATA, as a person would make them; every word is made up."""
import os
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
base = Path(os.environ["PREVIEW_DATA"])


def skill(where: Path, name: str, desc: str | None, extra: str = "") -> None:
    d = where / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    head = f"---\nname: {name}\n" + (f"description: {desc}\n" if desc else "") + "---\n"
    (d / "SKILL.md").write_text(head + "\nSteps for the preview.\n" + extra)


skill(base / "agents" / "main", "packing-list", "Make a packing list for a trip. Use when asked to pack.")
skill(base / "agents" / "sora", "tea-timer", "Time a pot of tea. Use when asked about brewing.")
skill(base / "agents" / "sora", "half-done", None)
skill(base / "communal", "house-style", "How replies are worded here. Use for every written reply.")
skill(base / "communal", "weekly-report", "The communal way to write the weekly report.")
