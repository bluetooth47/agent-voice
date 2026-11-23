"""The audit log: who changed what between agents, and when (merged plan,
section 3.7, Phase 14).

One JSON line per note write, and from Phase 15 per collaboration task
(from Phase 16 also each call an agent made, refused ones included):
the time, what kind of thing happened, who did it, where, the note's name
or the task's id, and sizes in bytes. **Never the text.** A note is
whatever an agent decided to write down, which may be a file's contents or
something somebody said; the journal-style structural record is what this
keeps, as the daemon's own log lines do (CLAUDE.md, "A check that reads
the code is not a check that the code ran").

That is held two ways, because one of them alone was shown in this project
to miss a leak:

- **by shape**: `record()` takes only named fields, each of a fixed kind --
  an id or a note name matching its pattern, or a whole number. There is
  no field a sentence fits in. A value that does not match is written as
  "?" rather than as itself, so a caller passing the wrong thing cannot
  put it on disk by mistake;
- **by an AST walk** in the tests, over every call to `audit.record` in
  the daemon, that no argument reads a name that holds content.

Written whether or not chats are saved, like the structural log lines:
it is the record of what agents did to each other's notes, and it holds
nothing a chat would. `DATA_DIR/audit.log`, 0600, rotated to
`audit.log.1` at 1 MB (one old file kept).
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths  # noqa: E402

ROTATE_AT = 1024 * 1024

#: What a line may say happened.
KINDS = frozenset({
    "note_write", "note_append", "note_restore", "note_lock", "note_unlock",
    "note_refused",
    # One per collaboration task, when it ends (Phase 15).
    "task_pass", "task_delegate", "task_ask", "task_message",
    # A skill found outside Agent Voice copied into an agent's folder or the
    # communal one, by the person (phase M11): the skill's name and size.
    "skill_import",
    # A skill moved or copied between agents and Communal, or a move, copy or
    # import undone, by the person (phase M12): ids, the name and its size.
    "skill_move", "skill_copy", "skill_undo",
    # A note moved or copied between agents and Communal (with its history
    # and its record entry), several combined into one topic, or a move or
    # copy undone, by the person (phase M13): ids, the name and sizes.
    "note_move", "note_copy", "note_combine", "note_undo",
    # Rules, defaults and skills imported into Communal from a folder, or
    # an import undone, by the person (phase M15): the operation's id and
    # its size; each skill also gets a skill_import line.
    "communal_import", "communal_import_undo",
    # A permission decision the hook made (phase M16): the agent, the tool's
    # name, allow or deny, how it was reached and the level. No argument,
    # no path: the tool's name is all of the call that is kept.
    "permission",
})
#: A permission line's fields, each from a fixed list (phase M16).
DECISIONS = frozenset({"allow", "deny"})
#: How a decision was reached: the person was asked (and answered, or did
#: not), it was refused without asking, the level or an "allow all in this
#: chat" allowed it, or the hook itself failed (a denial).
HOWS = frozenset({"asked", "unanswered", "refused", "level", "chat", "failed"})
LEVELS = frozenset({"ask", "edits", "trusted"})
#: A tool's name as Claude Code sends it ("Bash", "mcp__server__tool").
_TOOL = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
#: How a task ended: collab.DONE, kept here so this file imports nothing.
STATES = frozenset({"completed", "cancelled", "failed", "refused"})
#: An agent's external id ("main", "sora", "jarvis-ajc"), "you", or
#: "communal" for the shared folder.
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
#: A note's name (notes.NAME) or, from Phase 16, a task id.
_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
#: Why a write was refused, from a fixed vocabulary: never the agent's own
#: words, which could carry anything.
REASONS = frozenset({"", "denied", "locked", "stale", "unreadable-record",
                     "too-long", "too-many", "bad-name", "not-configured",
                     # Why a collaboration call an agent made was refused
                     # (Phase 16): collab's codes, never its sentences.
                     "off", "unknown", "self", "disabled", "unreachable", "no-work",
                     "cycle", "depth", "open-tasks", "inbox-full", "rate", "timeout",
                     "declined", "unheard", "stopped", "busy", "failed", "changed",
                     # phase M8 (crew_links.CODES)
                     "no-link", "quarantined", "crew-unreadable"})


def log_path() -> Path:
    return paths.DATA_DIR / "audit.log"


def _id(value) -> str:
    return value if isinstance(value, str) and _ID.fullmatch(value) else "?"


def _name(value) -> str:
    if value in (None, ""):
        return ""
    return value if isinstance(value, str) and _NAME.fullmatch(value) else "?"


def _size(value) -> int | None:
    if value is None or isinstance(value, bool) or not isinstance(value, int):
        return None
    return max(0, value)


def record(kind: str, *, frm: str, to: str, note: str = "", task: str = "",
           before: int | None = None, after: int | None = None,
           reason: str = "", state: str = "", tool: str = "", decision: str = "",
           how: str = "", level: str = "", wait_s: float | None = None) -> bool:
    """Append one line. Returns False when it could not be written; never
    raises, because a log that fails must not fail the write it records
    (the write has already happened by the time this runs).

    `wait_s`: give up on the lock after this long rather than wait for it
    (the permission hook, phase M16, whose whole run is inside Claude Code's
    hook timeout). None waits, as every other caller always has."""
    line = {"at": round(time.time(), 3),
            "kind": kind if kind in KINDS else "?",
            "from": _id(frm), "to": _id(to)}
    if tool:
        line["tool"] = tool if isinstance(tool, str) and _TOOL.fullmatch(tool) else "?"
    if decision:
        line["decision"] = decision if decision in DECISIONS else "?"
    if how:
        line["how"] = how if how in HOWS else "?"
    if level:
        line["level"] = level if level in LEVELS else "?"
    if note:
        line["note"] = _name(note)
    if task:
        line["task"] = _name(task)
    b, a = _size(before), _size(after)
    if b is not None:
        line["bytes_before"] = b
    if a is not None:
        line["bytes_after"] = a
    if reason:
        line["reason"] = reason if reason in REASONS else "?"
    if state:
        line["state"] = state if state in STATES else "?"
    data = (json.dumps(line, separators=(",", ":")) + "\n").encode()
    try:
        paths.private_dir(paths.DATA_DIR)
        path = log_path()
        # One writer at a time from the size check to the append: two that
        # both saw the log full would otherwise both rotate, and the second
        # would replace the archive with the first one's fresh log.
        lock = os.open(paths.DATA_DIR / ".audit.lock", os.O_WRONLY | os.O_CREAT
                       | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(lock).st_mode):
                return False                # a FIFO there must not stall a save
            if not _lock(lock, wait_s):
                return False
            _rotate(path)
            # O_NONBLOCK: a FIFO left at this path must not hang a note
            # write forever; it is then refused as not a regular file.
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW
                         | os.O_CLOEXEC | os.O_NONBLOCK, 0o600)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    return False
                os.write(fd, data)
            finally:
                os.close(fd)
        finally:
            os.close(lock)
        return True
    except OSError:
        return False


def _lock(fd: int, wait_s: float | None) -> bool:
    """Take the lock: blocking when `wait_s` is None, else trying until it
    has gone. False when it was not had in time."""
    if wait_s is None:
        fcntl.flock(fd, fcntl.LOCK_EX)
        return True
    deadline = time.monotonic() + max(0.0, wait_s)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)


def _rotate(path: Path) -> None:
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if st.st_size < ROTATE_AT:
        return
    try:
        os.replace(path, path.with_name(path.name + ".1"))
    except OSError:
        pass


def read(limit: int = 200) -> list[dict]:
    """The newest `limit` lines, oldest first, for the CLI."""
    out = []
    for p in (log_path().with_name("audit.log.1"), log_path()):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                for raw in f:
                    try:
                        out.append(json.loads(raw))
                    except ValueError:
                        continue
        except OSError:
            continue
    return out[-limit:]
