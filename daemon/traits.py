"""The trait chips on Agent details (phase M6, feedback item 10).

Three choices about how an agent sounds -- tone, length and formality --
kept as one managed line at the top of its personality.md:

    Traits: warm, brief, casual.

The line is ordinary personality text: the daemon tells it to the agent with
the rest of the file, an older build reads it the same way, and somebody may
type it by hand. So this module only ever reads and rewrites that one line.

- **Free text is never touched.** Everything but the managed line comes back
  byte for byte, the starter comment included.
- **The line sits after any leading comment.** `agentfs.clean` strips a
  comment only while it leads the file; a line put above the template's
  comment would push that comment into what the agent is told.
- **Unknown values are kept, as typed.** "Traits: warm, très calme." keeps
  "très calme" when tone changes; it is only dropped by editing the line by
  hand. Only the trait words are matched without regard to case.
- **A category holds one value.** Choosing one replaces whatever that
  category had, including a second value somebody typed in it.
- **No choices and no unknown values: no line.** Clearing the last chip
  takes the line out, with the blank line that followed it.

Pure functions, so the chips, the CLI and the tests share one reading. The
page calls `agentvoice agents traits apply`, which runs `apply()` on the text
in its editor and hands the result back for the editor to save on its own
stamp; `agents traits ID get|set` read and write the file for scripts.
"""
from __future__ import annotations

import re

#: The chips, in the order they are shown and written.
TRAITS: dict[str, tuple[str, ...]] = {
    "tone": ("warm", "dry", "playful"),
    "length": ("brief", "detailed"),
    "formality": ("casual", "formal"),
}
CATEGORY_OF = {v: k for k, vals in TRAITS.items() for v in vals}

#: The longest line read as the managed one. Past this it is somebody's
#: paragraph that happens to start with "Traits:", and it is left alone.
LINE_MAX = 200

_LEADING = re.compile(r"\A\ufeff?(?:\s*<!--.*?-->)*(?:[ \t]*\r?\n)*", re.S)
_LINE = re.compile(r"[ \t]*traits[ \t]*:[ \t]*(?P<body>[^\n]*?)[ \t]*(?:\r?\n|\Z)", re.I)


def _split(text: str) -> tuple[str, re.Match | None]:
    """The leading comments (as written) and the managed line's match, if
    the first thing after them is one."""
    head = _LEADING.match(text)
    at = head.end() if head else 0
    m = _LINE.match(text, at)
    if m is not None and len(m.group(0)) > LINE_MAX:
        m = None
    return text[:at], m


def parse(text: str) -> dict:
    """What the managed line says.

    {"traits": {"tone": "warm" | None, ...}, "unknown": [...], "line": bool}.
    A category typed twice reads as its first value. Any other value is kept
    in "unknown" exactly as typed, trimmed (Codex review of M6: a filter on
    the letters dropped "très calme" when a chip was clicked)."""
    text = text if isinstance(text, str) else ""
    _, m = _split(text)
    out = {"traits": {k: None for k in TRAITS}, "unknown": [], "line": m is not None}
    if m is None:
        return out
    for raw in m.group("body").rstrip(".").split(","):
        tok = raw.strip()
        if not tok:
            continue
        cat = CATEGORY_OF.get(tok.lower())
        if cat is not None:
            if out["traits"][cat] is None:
                out["traits"][cat] = tok.lower()
        else:
            # Every one, in order, duplicates too: "US, us" is two values to
            # whoever typed them (Codex review of M6, pass 2).
            out["unknown"].append(tok)
    return out


def line(traits: dict, unknown: list) -> str:
    """The managed line for these choices, or "" when there is nothing."""
    values = [traits.get(k) for k in TRAITS if traits.get(k)]
    values += list(unknown)
    return f"Traits: {', '.join(values)}." if values else ""


def check(choices) -> dict:
    """`choices` as {category: value | None}, or ValueError. Only the
    categories present change; a value must be one of its category's."""
    if not isinstance(choices, dict):
        raise ValueError("traits must be an object")
    out = {}
    for k, v in choices.items():
        if k not in TRAITS:
            raise ValueError(f"not a trait: {k!r}")
        if v is not None and v not in TRAITS[k]:
            raise ValueError(f"not a {k}: {v!r}")
        out[k] = v
    return out


def apply(text: str, choices: dict) -> str:
    """`text` with its managed line set to `choices` on top of what it had.

    Everything outside the line is returned exactly as it was."""
    text = text if isinstance(text, str) else ""
    choices = check(choices)
    now = parse(text)
    traits = {**now["traits"], **choices}
    new = line(traits, now["unknown"])
    head, m = _split(text)
    if m is not None:
        rest = text[m.end():]
        if not new:
            # The blank line that separated it from the free text goes too.
            rest = re.sub(r"\A[ \t]*\r?\n", "", rest)
            return head + rest
        ending = "\n" if m.group(0).endswith("\n") or rest else ""
        return head + new + ending + rest
    if not new:
        return text
    rest = text[len(head):]
    if head and not head.endswith("\n"):
        head += "\n"
    if rest.strip():
        return head + new + "\n\n" + rest
    return head + new + "\n"
