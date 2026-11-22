"""Synthetic skill folders for the `transfer` preview target (phase M12):
Sora has tea-timer, a broken one and her own house-style (so the
communal house-style dropped on her is refused); Theo has packing-list and his own
house-style (so a communal house-style dropped on him is refused); Hazel,
quarantined in configs/transfer3.json, has bird-notes; Communal has
house-style. Plain files in PREVIEW_DATA; every word is made up."""
import os
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
base = Path(os.environ["PREVIEW_DATA"])


def skill(where: Path, name: str, desc: str | None) -> None:
    d = where / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    head = f"---\nname: {name}\n" + (f"description: {desc}\n" if desc else "") + "---\n"
    (d / "SKILL.md").write_text(head + "\nSteps for the preview.\n")


skill(base / "agents" / "main", "packing-list", "Make a packing list for a trip. Use when asked to pack.")
skill(base / "agents" / "sora", "tea-timer", "Time a pot of tea. Use when asked about brewing.")
skill(base / "agents" / "sora", "half-done", None)
skill(base / "agents" / "sora", "house-style", "Sora's own way of wording replies.")
skill(base / "agents" / "hazel", "bird-notes", "Write up the morning's bird count.")
skill(base / "communal", "house-style", "How replies are worded here. Use for every written reply.")
