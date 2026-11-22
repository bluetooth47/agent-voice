"""Synthetic notes for the `notemoves` preview target (phase M13), written
through notes.py itself so each has its record entry and history: Sora has
garden (three revs), seeds, compost, packing and recipes (marked as holding
text from web pages); Theo has packing (so Sora's packing dropped on him is
refused); Hazel, quarantined in configs/transfer3.json, has birds; Communal
has house-rules. Every word is made up."""
import os
import sys
from pathlib import Path

base = Path(os.environ["PREVIEW_DATA"])
os.environ["XDG_DATA_HOME"] = str(base.parent)
sys.path.insert(0, sys.argv[1])

import notes  # noqa: E402
import paths  # noqa: E402

for t in ("main", "sora", "hazel"):
    paths.private_dir(paths.AGENTS_DIR / t)
notes.write("sora", "garden", "# Garden plans\nBeans by the fence.", author="sora")
notes.append("sora", "garden", "Water on Tuesdays.", author="sora")
notes.append("sora", "garden", "Net the strawberries.", author="sora")
notes.write("sora", "seeds", "Seeds to order\nRunner beans, basil.", author="sora")
notes.write("sora", "compost", "Turn the heap weekly.", author="sora")
notes.write("sora", "packing", "Sora's packing list: tent, stove.", author="sora")
notes.write("sora", "recipes", "Recipes found online\nLentil soup.", author="sora", tainted=True)
notes.write("main", "packing", "Theo's packing list: passport.", author="main")
notes.write("hazel", "birds", "Morning count\nTwo wrens.", author="hazel")
notes.write("communal", "house-rules", "# House rules\nQuiet after ten.")
