"""Notes: what agents write down for themselves and for each other (merged
plan, Phase 14).

Each agent has a notes folder of its own and every agent shares the
communal one:

    ~/.local/share/agentvoice/
      agents/<id>/notes/<name>.md, .meta.json, .history/<name>/<ns>-<who>.md
      communal/notes/  (the same shape)

The agents reach them through `crew_mcp.py`'s four tools; the settings
pages through `agentvoice agents notes …`. Nothing else writes here.

**Every write**, under the one lock agentfs uses for every folder: check
the record can be read → check the writer is allowed and the note is not
locked → check `base` → the previous version into `.history/` (twenty
kept) → the new text into place by rename → `.meta.json` updated (rev,
author, time, hash, tainted) → one `audit.log` line, which never holds the
text. `append` needs no `base`: it is how two agents add to one note
without either having to read it first.

**Who may write.** Deny (`notesWrite`, read fresh by the caller on every
call) and a per-note lock (set by the person, in `.meta.json`) are checked
here, inside the lock, before anything else about the write, and they beat
every permission level -- *through these tools*. An agent with a shell and
no hook (Trusted) can still change the files themselves; merged-plan.md
section 3.5 says so, and the Notes tab says it too. The person's own edits
from Settings are not subject to either: a lock is theirs.

**A record that cannot be read locks everything.** A `.meta.json` that is
corrupt, is a link, or is not the shape this writes reads as every note
locked (fail closed), and nothing rewrites it: replacing it would be the
one way to unlock every note at once. A *missing* record is a fresh start.

**A hand edit is the person's.** A note whose bytes no longer match the
hash in its record was changed outside these tools: the next read moves its
rev on and shows it as last written by "you", so a write based on the old
rev is refused. Its taint mark is kept: a change made outside cannot be
told apart from an agent's shell write, so it does not wash a note clean.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agentfs  # noqa: E402
import audit  # noqa: E402
import paths  # noqa: E402
from agentfs import AgentFsError  # noqa: E402

NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
NOTE_MAX = 20_000
FOLDER_MAX = 200
HISTORY_KEEP = 20
SUFFIX = ".md"
META = ".meta.json"
#: Who wrote a note: an agent's external id, or "you" for the person.
YOU = "you"
#: A saved version: `<ns>-<who>[-<n>][.t].md`, `.t` when the text it holds
#: was tainted, so restoring it brings the mark back (Phase 14 review).
_VERSION = re.compile(r"(\d{19})-([a-z0-9][a-z0-9-]{0,47}?)(?:-(\d+))?(\.t)?\.md")
_HASH = re.compile(r"[0-9a-f]{16}")
_META_VERSION = 1


class NotesError(AgentFsError):
    """A refusal in words an agent can say aloud. `reason` is the audit
    log's word for it, from audit.REASONS."""

    def __init__(self, message: str, reason: str = ""):
        super().__init__(message)
        self.reason = reason


class Stale(NotesError):
    """The note changed after the caller read it. Carries the current rev."""

    def __init__(self, current: int):
        super().__init__(f"this note has changed since it was read; it is now at rev "
                         f"{current}. Read it again, then write.", "stale")
        self.current = current


# --- where --------------------------------------------------------------------

def valid_name(name) -> bool:
    return isinstance(name, str) and bool(NAME.fullmatch(name))


def _check_name(name) -> str:
    if not valid_name(name):
        raise NotesError("a note's name is 1 to 48 characters of a-z, 0-9 and -, "
                         "starting with a letter or digit", "bad-name")
    return name


def notes_dir(target: str, create: bool = False) -> Path:
    """`target`'s notes folder, every directory on the way checked for
    links (agentfs refuses all of them), and made 0700 when `create`."""
    base = agentfs._base(target)
    chain = ([] if target == agentfs.COMMUNAL else [paths.AGENTS_DIR]) + [base, base / "notes"]
    for d in chain:
        agentfs._no_link(d)
        if create:
            paths.private_dir(d)
            agentfs._no_link(d)
    return base / "notes"


def _note_path(d: Path, name: str) -> Path:
    p = d / (name + SUFFIX)
    agentfs._no_link(p)
    return p


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


# --- the record ---------------------------------------------------------------

def _valid_entry(e) -> bool:
    def whole(v):
        return isinstance(v, int) and not isinstance(v, bool) and v >= 0
    at = e.get("at") if isinstance(e, dict) else None
    return (isinstance(e, dict) and set(e) == {"rev", "author", "at", "hash", "tainted", "locked"}
            and whole(e["rev"])
            and isinstance(e["author"], str) and bool(NAME.fullmatch(e["author"]))
            and isinstance(at, (int, float)) and not isinstance(at, bool)
            and at == at and 0 <= at < 1e11
            and isinstance(e["hash"], str) and (e["hash"] == "" or bool(_HASH.fullmatch(e["hash"])))
            and isinstance(e["tainted"], bool) and isinstance(e["locked"], bool))


def _no_duplicates(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        # `{"locked": true, "locked": false}` parses as unlocked: a record
        # that says two things is not trusted (Phase 14 review).
        raise ValueError("duplicate key")
    return dict(pairs)


def _load_meta(d: Path) -> dict | None:
    """The record, or None when it cannot be trusted (fail closed: every
    note reads as locked). Missing is an empty record, not an unreadable one.
    Trusted only exactly as this module writes it: version 1, no duplicate
    keys, every entry every field of the right shape."""
    path = d / META
    try:
        data, more = agentfs._read_bytes(path)
    except (FileNotFoundError, NotADirectoryError):
        return {}
    except (OSError, AgentFsError):
        return None
    if more:
        return None
    try:
        raw = json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    if (not isinstance(raw, dict) or set(raw) != {"version", "notes"}
            or raw.get("version") != _META_VERSION or isinstance(raw.get("version"), bool)
            or not isinstance(raw.get("notes"), dict)):
        return None
    out = {}
    for name, e in raw["notes"].items():
        if not valid_name(name) or not _valid_entry(e):
            return None
        out[name] = dict(e)
    return out


def _save_meta(d: Path, meta: dict) -> None:
    data = json.dumps({"version": _META_VERSION, "notes": meta}, indent=1,
                      sort_keys=True).encode()
    agentfs._no_link(d / META)
    agentfs._atomic_write(d / META, data)


def _note_names(d: Path) -> list[str]:
    try:
        entries = list(os.scandir(d))
    except (FileNotFoundError, NotADirectoryError):
        return []
    except OSError as e:
        raise NotesError(f"the notes folder cannot be read ({e.strerror})") from None
    out = []
    for e in entries:
        if not e.name.endswith(SUFFIX) or not e.is_file(follow_symlinks=False):
            continue
        name = e.name[:-len(SUFFIX)]
        if valid_name(name):
            out.append(name)
    return sorted(out)


def _read_note_bytes(path: Path) -> bytes | None:
    """The note's bytes, None when it is missing. A note too large to be
    one, a link or something that is not a file is an error, not a crash."""
    try:
        data, more = agentfs._read_bytes(path)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as e:
        if e.errno == 40:
            raise NotesError(f"{path.name} is a symlink, which is refused here") from None
        raise NotesError(f"{path.name} could not be opened ({e.strerror})") from None
    if more:
        raise NotesError(f"{path.name} is far larger than a note can be")
    return data


def _decode(data: bytes) -> str:
    if b"\x00" in data:
        raise NotesError("it holds binary data")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise NotesError("it is not UTF-8 text") from None


def _mtime(path: Path) -> float:
    try:
        return os.lstat(path).st_mtime
    except OSError:
        return time.time()


def _seen(meta: dict, name: str, data: bytes | None, path: Path) -> bool:
    """Record what is on disk for one note now: a note made or changed by
    hand is the person's, at a new rev; one deleted by hand leaves a
    tombstone (its rev, and its lock), so a note made again under that name
    goes on from that rev and a write based on the deleted one's rev is
    refused (Phase 14 review). True when the record changed."""
    e = meta.get(name)
    if data is None:
        if e is not None and e["hash"] != "":
            e.update(hash="", rev=e["rev"] + 1, author=YOU, at=time.time())
            return True
        return False
    h = _hash(data)
    if e is None:
        meta[name] = {"rev": 1, "author": YOU, "at": _mtime(path), "hash": h,
                      "tainted": False, "locked": False}
        return True
    if e["hash"] != h:
        e.update(rev=e["rev"] + 1, author=YOU, at=_mtime(path), hash=h)
        return True
    return False


def _current(target: str, create: bool = False) -> tuple[Path, dict | None, dict]:
    """With the lock held: the folder, its record brought up to date (and
    saved when it moved and can be trusted), and each note's bytes as they
    were read for that, so what is returned and what was hashed are the
    same bytes. A note that cannot be read maps to its NotesError."""
    d = notes_dir(target, create=create)
    names = _note_names(d)
    meta = _load_meta(d)
    got: dict = {}
    for name in names:
        try:
            got[name] = _read_note_bytes(_note_path(d, name))
        except NotesError as e:
            got[name] = e
    if meta is not None:
        changed = False
        for name, data in got.items():
            if isinstance(data, (bytes, type(None))):
                changed |= _seen(meta, name, data, d / (name + SUFFIX))
        for name in list(meta):
            if name not in got:
                changed |= _seen(meta, name, None, d / (name + SUFFIX))
        if changed and d.is_dir():
            _save_meta(d, meta)
    return d, meta, got


# --- reading ------------------------------------------------------------------

def _entry_out(name: str, e: dict | None, locked_all: bool) -> dict:
    e = e or {"rev": 0, "author": YOU, "at": 0, "tainted": False, "locked": False}
    return {"name": name, "rev": e["rev"], "author": e["author"], "at": e["at"],
            "tainted": e["tainted"], "locked": locked_all or e["locked"]}


def list_notes(target: str) -> dict:
    """Every note with its record, the other files in the folder (which the
    page opens with xdg-open), and the folder's problem if any. Under the
    lock, so a record and the note it describes are read together."""
    with agentfs._locked():
        d, meta, got = _current(target)
    locked_all = meta is None
    notes = []
    for name, data in sorted(got.items()):
        out = _entry_out(name, (meta or {}).get(name), locked_all)
        try:
            if isinstance(data, NotesError):
                raise data
            out["chars"] = len(_decode(data or b""))
            out["problem"] = ""
        except NotesError as e:
            out["chars"] = 0
            out["problem"] = str(e)
        notes.append(out)
    files = []
    try:
        for e in sorted(os.scandir(d), key=lambda e: e.name):
            if e.name.startswith("."):
                continue
            if e.name.endswith(SUFFIX) and valid_name(e.name[:-len(SUFFIX)]) \
                    and e.is_file(follow_symlinks=False):
                continue
            kind = ("link" if e.is_symlink() else "folder" if e.is_dir(follow_symlinks=False)
                    else "file")
            files.append({"name": e.name, "kind": kind})
    except OSError:
        pass
    return {"target": target, "folder": str(d), "notes": notes, "files": files,
            "locked_all": locked_all, "max": FOLDER_MAX, "note_max": NOTE_MAX,
            "problem": ("The notes record (.meta.json) cannot be read, so every note is "
                        "treated as locked. Fix the file or remove it; removing it "
                        "unlocks every note." if locked_all else "")}


def read_note(target: str, name: str) -> dict:
    """One note: its text and its record, read together under the lock.
    NotesError when there is none."""
    _check_name(name)
    with agentfs._locked():
        d, meta, got = _current(target)
    data = got.get(name)
    if isinstance(data, NotesError):
        raise data
    if data is None:
        raise NotesError(f"there is no note called {name}")
    out = _entry_out(name, (meta or {}).get(name), meta is None)
    out["text"] = _decode(data)
    out["chars"] = len(out["text"])
    return out


# --- writing ------------------------------------------------------------------

def _clean(text) -> str:
    if not isinstance(text, str):
        raise NotesError("the text must be a string")
    if "\x00" in text:
        raise NotesError("the text holds a NUL character")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _history_dir(d: Path, name: str, create: bool = False) -> Path:
    h = d / ".history"
    for p in (h, h / name):
        agentfs._no_link(p)
        if create:
            paths.private_dir(p)
            agentfs._no_link(p)
    return h / name


def _versions(d: Path, name: str) -> list[Path]:
    try:
        hd = _history_dir(d, name)
        found = [Path(e.path) for e in os.scandir(hd)
                 if e.is_file(follow_symlinks=False) and _VERSION.fullmatch(e.name)]
    except (OSError, AgentFsError):
        return []
    return sorted(found, key=lambda p: p.name, reverse=True)


def _keep_version(d: Path, name: str, data: bytes, who: str, tainted: bool) -> None:
    """The text being replaced, saved under who wrote it and with its taint
    mark. Twenty kept."""
    hd = _history_dir(d, name, create=True)
    who = who if NAME.fullmatch(who or "") else YOU
    mark = ".t" if tainted else ""
    stamp = f"{time.time_ns():019d}"
    fname = f"{stamp}-{who}{mark}.md"
    n = 1
    while os.path.lexists(hd / fname):
        fname = f"{stamp}-{who}-{n}{mark}.md"
        n += 1
    agentfs._atomic_write(hd / fname, data)
    for old in _versions(d, name)[HISTORY_KEEP:]:
        with contextlib.suppress(OSError):
            old.unlink()


def _refuse(message: str, reason: str, *, author: str, target: str, name: str) -> NotesError:
    """A refusal, written to the audit log when an agent was refused (worth
    seeing), and returned for the caller to raise."""
    if author != YOU:
        audit.record("note_refused", frm=author, to=target, note=name if valid_name(name) else "",
                     reason=reason)
    return NotesError(message, reason)


def _write(target: str, name: str, produce, *, author: str, allowed, base, kind: str,
           check_base: bool) -> dict:
    """The one write path, under the lock. `produce(old_text, entry)` gives
    the new text and whether it is tainted (old_text is None when there is
    no note; entry is its record, or None).
    `allowed` is None for the person's own writes, else a function, read
    here inside the lock, saying whether this agent may write notes at all.
    `check_base`: a replacing write must name the rev it was based on."""
    if not isinstance(author, str) or not NAME.fullmatch(author):
        raise NotesError(f"not a name for who wrote it: {author!r}")
    if allowed is not None and author == YOU:
        # "you" is the person. An agent known by that id would be written
        # down as them, and its refusals left out of the audit log.
        raise NotesError("an agent whose id is 'you' cannot write notes: that name is the "
                         "person's; give it another id", "not-configured")
    if not valid_name(name):
        raise _refuse("a note's name is 1 to 48 characters of a-z, 0-9 and -, starting "
                      "with a letter or digit", "bad-name", author=author, target=target, name="")
    with agentfs._locked():
        d, meta, got = _current(target, create=True)
        if meta is None:
            raise _refuse("the notes record here cannot be read, so every note is locked "
                          "until the person fixes it", "unreadable-record",
                          author=author, target=target, name=name)
        if allowed is not None:
            try:
                ok = bool(allowed())
            except Exception:           # noqa: BLE001 -- a check that fails denies
                ok = False
            if not ok:
                raise _refuse("You aren't allowed to write notes here. You can still read "
                              "them.", "denied", author=author, target=target, name=name)
        e = meta.get(name)
        if allowed is not None and e is not None and e["locked"]:
            raise _refuse(f"The note {name} is locked by the person: it is read-only for "
                          f"every agent.", "locked", author=author, target=target, name=name)
        path = _note_path(d, name)
        old = got.get(name)
        if isinstance(old, NotesError):
            raise old
        exists = old is not None
        rev = e["rev"] if e else 0
        if check_base:
            if exists and (base is None or isinstance(base, bool) or not isinstance(base, int)):
                raise _refuse(f"the note {name} already exists: read it first and pass its rev "
                              f"as base (it is at rev {rev}), or append to it", "stale",
                              author=author, target=target, name=name)
            if (exists and base != rev) or (not exists and base not in (None, 0, rev)):
                if author != YOU:
                    audit.record("note_refused", frm=author, to=target, note=name,
                                 reason="stale")
                raise Stale(rev)
        text, tainted = produce(None if old is None else _decode(old), e)
        text = _clean(text)
        if len(text) > NOTE_MAX:
            raise _refuse(f"a note holds at most {NOTE_MAX} characters, and this would be "
                          f"{len(text)}", "too-long", author=author, target=target, name=name)
        if not exists and sum(1 for v in got.values() if v is not None) >= FOLDER_MAX:
            raise _refuse(f"this notes folder already holds {FOLDER_MAX} notes, the most it "
                          f"can; append to one or ask the person to clear some out",
                          "too-many", author=author, target=target, name=name)
        data = text.encode("utf-8")
        if exists:
            _keep_version(d, name, old, e["author"] if e else YOU, bool(e and e["tainted"]))
        try:
            # A new note is published only if nothing appeared there since
            # the folder was read: a hand-made file, or a FIFO the scan
            # skipped, is never replaced unseen.
            agentfs._atomic_write(path, data, exclusive=not exists)
        except agentfs.Conflict:
            raise Stale(rev) from None
        previous = dict(e) if e else None
        meta[name] = {"rev": rev + 1, "author": author, "at": time.time(), "hash": _hash(data),
                      "tainted": bool(tainted), "locked": bool(e and e["locked"])}
        try:
            _save_meta(d, meta)
        except BaseException:
            # The text landed and its record did not: put the text back, so a
            # failed write leaves nothing behind and a retry adds nothing twice.
            with contextlib.suppress(OSError, AgentFsError):
                if exists:
                    agentfs._atomic_write(path, old)
                else:
                    path.unlink()
            if previous is None:
                meta.pop(name, None)
            else:
                meta[name] = previous
            raise
    old_size = len(old) if old is not None else None
    audit.record(kind, frm=author, to=target, note=name, before=old_size, after=len(data))
    return {"name": name, "rev": rev + 1, "chars": len(text), "created": not exists}


def write(target: str, name: str, text: str, base: int | None = None, *,
          author: str = YOU, tainted: bool = False, allowed=None) -> dict:
    """Replace (or create) a note. Replacing needs the rev it was read at.
    Its taint is the writer's: the text is all theirs now."""
    return _write(target, name, lambda _old, _e: (text, tainted), author=author, allowed=allowed,
                  base=base, kind="note_write", check_base=True)


def append(target: str, name: str, text: str, *, author: str = YOU,
           tainted: bool = False, allowed=None) -> dict:
    """Add `text` on a line of its own at the end of a note, making the note
    when there is none. Needs no rev, so two agents can both add to one.
    A tainted note stays tainted."""
    if not isinstance(text, str) or not text.strip():
        raise NotesError("there is nothing to append")
    add = _clean(text).strip("\n")

    def produce(old, e):
        joined = add if not old else old.rstrip("\n") + "\n" + add
        return joined, bool(tainted) or bool(e and e["tainted"] and old is not None)
    return _write(target, name, produce, author=author, allowed=allowed, base=None,
                  kind="note_append", check_base=False)


def set_locked(target: str, name: str, locked: bool) -> dict:
    """The person's lock: a locked note is read-only for every agent. Only
    the CLI (the Notes tab) calls this; no tool offers it."""
    _check_name(name)
    with agentfs._locked():
        d, meta, got = _current(target)
        if meta is None:
            raise NotesError("the notes record (.meta.json) cannot be read; fix or remove "
                             "it first", "unreadable-record")
        e = meta.get(name)
        if e is None or got.get(name) is None:
            raise NotesError(f"there is no note called {name}")
        e["locked"] = bool(locked)
        _save_meta(d, meta)
    audit.record("note_lock" if locked else "note_unlock", frm=YOU, to=target, note=name)
    return {"name": name, "locked": bool(locked)}


def is_locked(target: str, name: str) -> bool:
    """Whether an agent's write to this note would meet a lock, without the
    lock: only to spare a question about a write that cannot happen. The
    write itself checks again. Unsure is locked."""
    try:
        meta = _load_meta(notes_dir(target))
    except (OSError, AgentFsError):
        return True
    if meta is None:
        return True
    return bool(meta.get(name, {}).get("locked"))


def history(target: str, name: str) -> list[dict]:
    """Saved versions of a note, newest first: who wrote each, its size and
    whether it was tainted."""
    _check_name(name)
    d = notes_dir(target)
    out = []
    for v in _versions(d, name):
        m = _VERSION.fullmatch(v.name)
        try:
            chars = len(_decode(_read_note_bytes(v) or b""))
        except NotesError:
            chars = -1
        out.append({"version": v.name, "at": int(m.group(1)) / 1e9, "who": m.group(2),
                    "chars": chars, "tainted": bool(m.group(4))})
    return out


def _version_file(d: Path, name: str, version: str) -> Path:
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise NotesError(f"not a version: {version!r}")
    chosen = next((v for v in _versions(d, name) if v.name == version), None)
    if chosen is None:
        raise NotesError(f"{name} has no version {version}")
    return chosen


def version_text(target: str, name: str, version: str) -> str:
    _check_name(name)
    chosen = _version_file(notes_dir(target), name, version)
    data = _read_note_bytes(chosen)
    if data is None:
        raise NotesError(f"{name} has no version {version}")
    return _decode(data)


def restore(target: str, name: str, version: str, base: int | None = None) -> dict:
    """Put a saved version back, as the person, with the taint it had. The
    text it replaces is saved in turn, so a restore can itself be undone.
    The version is found and read inside the write's lock, so a prune in
    between cannot make it read as empty."""
    _check_name(name)

    def produce(_old, _e):
        chosen = _version_file(notes_dir(target), name, version)
        data = _read_note_bytes(chosen)
        if data is None:
            raise NotesError(f"{name} has no version {version}")
        return _decode(data), bool(_VERSION.fullmatch(chosen.name).group(4))
    return _write(target, name, produce, author=YOU, allowed=None, base=base,
                  kind="note_restore", check_base=True)


def folder(target: str) -> str:
    """Make the notes folder if it is missing (for Open folder); its path."""
    return str(notes_dir(target, create=True))


# --- who is who ---------------------------------------------------------------

def labels(cfg) -> dict[str, str]:
    """External id -> display name, for "last written by"."""
    out = {YOU: "you"}
    try:
        out["main"] = cfg.main_label()
        for a in cfg.all_agents():
            out[a["id"]] = a["label"]
    except Exception:                   # noqa: BLE001 -- names are decoration
        pass
    return out
