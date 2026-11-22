"""`agentvoice commands [--json]`: every spoken command, and what wakes whom.

The table lives in speech_text.py (phase M4) and this only prints it, with
the agents' wake phrases read from the settings as they are now -- so the
list a page, a skill or a person reads cannot drift from what the daemon
matches. Standard library only, and reads nothing but the settings: no
daemon needs to be running.

The JSON is for the pages and the skill that list commands (M14, M24, M26):
`mode` is the `commandsInSentences` in force, `commands` the table (see
`speech_text.Command.as_dict`), `wake_phrases` one entry per agent that is
switched on: its id ("main" for the main one), display name and phrase.
"""
from __future__ import annotations

import json
import sys

from runtime import Config
from speech_text import POSITIONS, safe_for_terminal, table


def wake_phrases(cfg: Config) -> list[dict]:
    """[{"id", "label", "phrase"}] for the main agent and every extra agent
    that is switched on, in the order the settings give them."""
    out = []
    phrase = cfg.get_str("phrase").strip()
    if phrase:
        out.append({"id": "main", "label": cfg.main_label(phrase),
                    "phrase": phrase})
    for spec in cfg.agents():
        out.append({"id": spec["id"], "label": spec["label"],
                    "phrase": spec["name"]})
    return out


_WHERE = {"alone": "on its own", "start": "at the start", "end": "at the end",
          "clause": "in its own clause"}


def as_text(data: dict) -> str:
    """The table for a person at a terminal. Names and phrases come from
    the settings, which anyone can edit, so they go through
    safe_for_terminal like anything else printed."""
    lines = [f"Commands inside a sentence: {data['mode']}", ""]
    for c in data["commands"]:
        where = ", ".join(_WHERE[p] for p in POSITIONS if p in c["where"])
        lines.append(f"{c['label']}  ({where})")
        lines.append(f"  {c['effect']}")
        said = sorted(c["phrases"])
        lines.append("  Say: " + "; ".join(f'"{p}"' for p in said))
        if c["in_sentence"]:
            lines.append("  Inside a sentence: "
                         + "; ".join(f'"{p}"' for p in c["in_sentence"]))
        if c["said"]:
            lines.append(f"  When it fires inside a sentence it says: \"{c['said']}\"")
        if not c["needs_wake"]:
            lines.append("  Works without the wake word on the sherpa-onnx engine.")
        if c["cli"]:
            lines.append(f"  From a terminal: {c['cli']}")
        lines.append("")
    undo = data["undo"]
    lines.append(f"Undo: within {undo['seconds']:g}s of an open-mic switch made inside "
                 "a sentence, say " + " or ".join(f'"{p}"' for p in ("no", "cancel that"))
                 + ".")
    lines.append("")
    lines.append("Wake phrases:")
    for w in data["wake_phrases"] or []:
        lines.append(f"  {safe_for_terminal(w['label'])}: "
                     f"\"{safe_for_terminal(w['phrase'])}\"")
    if not data["wake_phrases"]:
        lines.append("  (none set)")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if argv and argv[0] not in ("--json",):
        print("usage: agentvoice commands [--json]", file=sys.stderr)
        return 2
    cfg = Config()
    data = table(wake_phrases(cfg), cfg.commands_in_sentences())
    if argv and argv[0] == "--json":
        print(json.dumps(data, indent=2))
    else:
        print(as_text(data))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
