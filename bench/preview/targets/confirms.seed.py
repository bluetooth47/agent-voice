"""Synthetic saved chats for the `confirms` target (M1): the same three the
`shared` target uses, so its Delete has something harmless to delete."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).with_name("shared.seed.py")), run_name="__main__")
