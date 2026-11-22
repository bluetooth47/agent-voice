"""Read QML structurally enough to ask "what is this line inside?".

The tests that hold where a setting is written, and that a destructive
command is reached only from a confirmation, need more than a grep: a
`folders.remove(` on a page is fine inside `onConfirmed:` and a bug inside
`onClicked:`, and the two differ only in a header several lines up. A grep
for the call would pass both (CLAUDE.md: parse it, never grep it).

So this blanks comments and string contents (keeping every offset and line
break, so positions still map back to the source), then matches braces. A
JavaScript regex literal is blanked too, because `/^[a-z]+( [a-z]+){0,2}$/`
has braces in it that are not blocks. Anything it cannot balance raises,
rather than answering a question about a file it misread.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A `/` starts a regex literal, not a division, after one of these (or at
# the start of an expression). Good enough for this codebase; `balanced()`
# catches the day it is not.
_REGEX_AFTER = set("(,=:[!&|?{};+-*%~^<>") | {""}


def blank(src: str, strings: bool = True) -> str:
    """`src` with comments, string contents and regex literals replaced by
    spaces. Quotes stay, so `"delete"` becomes `"      "` -- callers that
    need the literal look it up in the original at the same offset. With
    `strings=False` only comments are blanked."""
    out = list(src)
    i, n = 0, len(src)
    last = ""  # last significant character outside strings and comments
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        if c == "/" and nxt == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if src[k] != "\n":
                    out[k] = " "
            i = j
            continue
        if c in "\"'`":
            j = i + 1
            # A template literal's `${...}` is code, and is left as code:
            # `${page.s.clearSession()}` runs (Codex review, M1).
            keep: list[tuple[int, int]] = []
            while j < n and src[j] != c:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "\n" and c != "`":
                    break
                if c == "`" and src.startswith("${", j):
                    # Braces inside a string in the expression do not count:
                    # `${"}" + clearSession()}` (Codex review, M1).
                    depth, k = 1, j + 2
                    while k < n and depth:
                        if src[k] in "\"'":
                            q, k = src[k], k + 1
                            while k < n and src[k] != q:
                                k += 2 if src[k] == "\\" else 1
                        else:
                            depth += {"{": 1, "}": -1}.get(src[k], 0)
                        k += 1
                    keep.append((j + 2, k - 1))
                    j = k
                    continue
                j += 1
            if strings:
                for k in range(i + 1, min(j, n)):
                    if src[k] != "\n" and not any(a <= k < b for a, b in keep):
                        out[k] = " "
                # The expression itself is cleaned the same way, so a string
                # in it hides its braces and a comment its words.
                for a, b in keep:
                    out[a:b] = list(blank(src[a:b], strings))
            i = j + 1
            last = c
            continue
        if c == "/" and last in _REGEX_AFTER:
            j = i + 1
            in_class = False
            while j < n and src[j] != "\n":
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "[":
                    in_class = True
                elif src[j] == "]":
                    in_class = False
                elif src[j] == "/" and not in_class:
                    break
                j += 1
            if strings:
                for k in range(i + 1, min(j, n)):
                    out[k] = " "
            i = j + 1
            last = "/"
            continue
        if not c.isspace():
            last = c
        i += 1
    return "".join(out)


@dataclass
class Scanned:
    path: Path
    src: str
    clean: str              # comments, strings and regexes blanked
    nocomment: str          # comments blanked, strings kept
    opens: list[int]        # offset of each "{"
    closes: dict[int, int]  # open offset -> matching close offset

    def enclosing(self, pos: int) -> list[int]:
        """Offsets of the "{" of every block containing `pos`, innermost first."""
        return sorted((o for o in self.opens if o < pos <= self.closes[o]), reverse=True)

    def header(self, brace: int) -> str:
        """What stands before a "{" on its line: `onConfirmed: function()`,
        `function removeAgent(index)`, `DangerButton`. Read from the cleaned
        text, so a comment on that line is not part of it."""
        start = self.clean.rfind("\n", 0, brace) + 1
        return self.clean[start:brace].strip()

    def line_of(self, pos: int) -> str:
        """The cleaned line holding `pos`, from its start up to `pos`."""
        start = self.clean.rfind("\n", 0, pos) + 1
        return self.clean[start:pos]

    def lineno(self, pos: int) -> int:
        return self.src.count("\n", 0, pos) + 1

    def calls(self, needle) -> list[int]:
        """Offsets where `needle` (a string, or a compiled pattern) occurs as
        code: not in a comment, not inside a string, and not as the
        definition (`function removeAgent(`). It may hold a string literal
        (`run("delete"`) as long as it starts with code."""
        out = []
        pattern = needle if isinstance(needle, re.Pattern) else re.compile(re.escape(needle))
        for m in pattern.finditer(self.nocomment):
            p = m.start()
            if self.clean[p] != self.src[p]:
                continue
            if re.search(r"\bfunction\s+$", self.nocomment[max(0, p - 20):p]):
                continue
            out.append(p)
        return out

    def literals(self, needle: str) -> list[int]:
        """Offsets where `needle` occurs inside a string literal in code (a
        command's argv, `" --uninstall"`), never in a comment."""
        return [m.start() for m in re.finditer(re.escape(needle), self.nocomment)
                if self.clean[m.start()] != self.src[m.start()]]

    def handler_of(self, pos: int) -> str:
        """The QML signal handler (`onConfirmed`, `onClicked`, ...) or JS
        function `pos` is inside: the innermost block header naming one, or
        a single-line handler on the same line. "" if neither."""
        # A handler written on the call's own line before it: `onClicked:
        # x()`, `Button { onClicked: x() }`, `DangerButton { id: d;
        # onConfirmed: x() }`. Only the text before the call is read, and
        # the last handler started there (after a brace, a semicolon or the
        # line's start) is the one it belongs to.
        own = re.findall(r"(?:^|[{;])\s*(on[A-Z]\w*)\s*:", self.line_of(pos))
        if own:
            return own[-1]
        for brace in self.enclosing(pos):
            h = self.header(brace)
            m = re.search(r"\b(on[A-Z]\w*)\s*:\s*(?:function\s*\([^)]*\)\s*)?$", h)
            if m:
                return m.group(1)
            m = re.search(r"\bfunction\s+(\w+)\s*\([^)]*\)\s*$", h)
            if m:
                return "function " + m.group(1)
        return ""

    def element_of(self, pos: int) -> str:
        """The innermost QML element `pos` is inside (`ToggleRow`, `Button`)."""
        for brace in self.enclosing(pos):
            m = re.fullmatch(r"(?:\w+\s*:\s*)?([A-Z][\w.]*)", self.header(brace))
            if m:
                return m.group(1)
        return ""


def scan(path: Path) -> Scanned:
    src = path.read_text()
    clean = blank(src)
    stack: list[int] = []
    opens: list[int] = []
    closes: dict[int, int] = {}
    for i, c in enumerate(clean):
        if c == "{":
            stack.append(i)
            opens.append(i)
        elif c == "}":
            if not stack:
                raise ValueError(f"{path.name}:{src.count(chr(10), 0, i) + 1}: unbalanced }}")
            closes[stack.pop()] = i
    if stack:
        raise ValueError(f"{path.name}:{src.count(chr(10), 0, stack[-1]) + 1}: unclosed {{")
    return Scanned(path, src, clean, blank(src, strings=False), opens, closes)


def overlay_qml() -> list[Path]:
    """Every QML file the settings overlay and the bar widget are made of."""
    top = [ROOT / n for n in ("Settings.qml", "Chats.qml", "Panel.qml", "Hud.qml",
                              "AgentFolders.qml", "KnobRow.qml", "SettingsGroup.qml")]
    return ([p for p in top if p.exists()] + sorted((ROOT / "pages").glob("*.qml"))
            + sorted((ROOT / "ui").glob("*.qml")))
