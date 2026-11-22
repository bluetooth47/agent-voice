"""Moving and copying a note between agents and Communal, combining notes
into one topic, and undoing a move or a copy (master plan, phase M13).

A note is a topic: one file per subject, `<name>.md`, with its entry in the
folder's `.meta.json` (rev, author, time, hash, taint, lock) and its past
versions under `.history/<name>/` (notes.py). **A move carries all three**:
the file, its entry and its history. The entry travels whole, with one
exception, the rev: a folder that once had a note of that name keeps a
tombstone of its rev, and a note arriving goes on from at least there, so
an agent that read the old one can never write over the new one on a rev it
happens to share (notes.py's rule, kept across a move).

Only the person does any of this: the Notes tabs and `agentvoice notes
move|copy|combine|undo` call it; no crew tool does, and an agent running
those commands is asked at every level (the orders guard's NOTE_WORDS).

**One transfer, under the one lock every note write takes** (agentfs.
_locked), the M12 journal's way (transfer.py):

1. anything an earlier transfer left unfinished is settled first;
2. both records are read; either one unreadable refuses (an unreadable
   record locks every note in its folder, and a move must not wash that
   off); the note is read and must be text; the destination must have no
   note of that name and room for one more;
3. a journal record (`begun`) names the note, its digest, the entry it will
   have where it lands, and the destination's entry it replaces (a
   tombstone, or none);
4. the text is staged in the destination folder (`.t-<op>.md`, which no
   reader lists), and the source read again: it must not have changed;
5. the destination's record gets the entry first, so that even a reader that
   skipped recovery would see the note's taint and lock, never a note "made
   by hand";
6. a move hides the source (`.t-<op>-gone.md`) and then publishes the stage
   by one no-replace rename: between the two the note is in neither place,
   never both; a copy only publishes;
7. `published`; the history is copied over, by each version's own name; a
   move then tombstones the source's entry, drops its history and deletes
   the hidden copy; `done`.

**Crash-safe.** Recovery (transfer.recover, which the daemon runs when it
starts and on its poll, and notes._current before any note is read) rolls a
record back until the note has landed and forward once it has, as M12 does.

**Combine** merges several notes of one folder into one topic note: the
first named is the one kept (or a new name is made); each other note's text
is added under a heading of its topic. The result is tainted if any part
was, and locked if any part was. Each note combined away keeps its whole
history -- its last text saved as a version first -- so the Notes tab's
"Earlier notes" can put it back. Recorded and recovered like a move; it
cannot be undone in one step.

**Undo** of a move or a copy is tied to the exact revision: the note where
it landed must still have the digest and the rev it landed with. A copy is
taken back only while the original is unchanged too.

**Confirm before widening** (section 7.3): into Communal, out of a
quarantined agent (or any agent when the list cannot be read), or a note
that may hold text from web pages. `move()` and `copy()` refuse those
without `confirmed`, checked under the lock, so the page's question is a
question and this still holds.

Every transfer writes one audit line: ids, the note's name and sizes, never
its text.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agentfs  # noqa: E402
import notes  # noqa: E402
import transfer  # noqa: E402
from agentfs import COMMUNAL, MAIN, AgentFsError  # noqa: E402

#: What a note record may say was done. `remove` is the undo of a copy.
ACTIONS = ("move", "copy", "remove", "combine")
#: The most notes one Combine takes.
COMBINE_MAX = 20
_ENTRY_KEYS = {"rev", "author", "at", "hash", "tainted", "locked"}


def _label(target: str) -> str:
    return "Communal" if target == COMMUNAL else target


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- the record's shape ------------------------------------------------------------

def _entry_ok(e, tomb_ok: bool = False) -> bool:
    if not notes._valid_entry(e):
        return False
    return tomb_ok or e["hash"] != ""


def valid(rec) -> bool:
    """A note record in the shape this writes; transfer._valid asks here for
    any record whose kind is "note". Anything else is never acted on."""
    if not isinstance(rec, dict) or rec.get("kind") != "note":
        return False
    action, frm, to, name = rec.get("action"), rec.get("from"), rec.get("to"), rec.get("name")
    if action not in ACTIONS or not isinstance(rec.get("op"), str) \
            or not transfer._OP.fullmatch(rec["op"]):
        return False
    if not notes.valid_name(name) or not transfer._target_ok(frm) or not transfer._target_ok(to):
        return False
    if (action in ("move", "copy")) == (frm == to):
        return False
    if not isinstance(rec.get("digest"), str) or not transfer._DIGEST.fullmatch(rec["digest"]):
        return False
    if not _entry_ok(rec.get("entry")):
        return False
    before = rec.get("before")
    if before is not None and not _entry_ok(before, tomb_ok=True):
        return False
    versions = rec.get("versions", [])
    if not isinstance(versions, list) or len(versions) > 4 * notes.HISTORY_KEEP or \
            not all(isinstance(v, str) and notes._VERSION.fullmatch(v) for v in versions):
        return False
    if action == "combine":
        sources = rec.get("sources")
        if not isinstance(sources, list) or not 1 <= len(sources) < COMBINE_MAX:
            return False
        seen = {name}
        for src in sources:
            if not isinstance(src, dict) or set(src) != {"name", "digest", "entry"} \
                    or not notes.valid_name(src["name"]) or src["name"] in seen \
                    or not isinstance(src["digest"], str) \
                    or not transfer._DIGEST.fullmatch(src["digest"]) \
                    or not _entry_ok(src["entry"]):
                return False
            seen.add(src["name"])
        prior = rec.get("prior", "")
        if not isinstance(prior, str) or not (prior == "" or transfer._DIGEST.fullmatch(prior)):
            return False
    undo_of = rec.get("undo_of", "")
    return isinstance(undo_of, str) and (undo_of == "" or bool(transfer._OP.fullmatch(undo_of)))


# --- the folders, by path, the way notes.py reaches them ------------------------------

def _dir(target: str, create: bool = False) -> Path:
    """`target`'s notes folder, links refused on the way (notes.notes_dir).
    A destination agent's own folder is never made here: a move must not
    bring back an agent that was just moved to the trash."""
    return notes.notes_dir(target, create=create, make_folder=target == MAIN)


def _open(d: Path) -> int:
    return os.open(d, transfer._DIR)


def _bytes(d: Path, file: str) -> bytes | None:
    """A file in the notes folder, None when it is not there."""
    try:
        return notes._read_note_bytes(d / file)
    except notes.NotesError:
        return None


def _tombstone(e: dict, keep_lock: bool) -> dict:
    """What a folder keeps of a note that left: its rev moved on, so a write
    based on the note that was here is refused (notes._seen's rule)."""
    return {"rev": e["rev"] + 1, "author": notes.YOU, "at": time.time(), "hash": "",
            "tainted": False, "locked": bool(keep_lock and e["locked"])}


# --- history, which travels with the note ---------------------------------------------

def _copy_versions(frm_dir: Path, to_dir: Path, name: str, versions: list[str]) -> None:
    """Each saved version named, from `frm_dir`'s history into `to_dir`'s, by
    its own name, so doing it twice changes nothing. Nothing is pruned here:
    the next write keeps the newest twenty, as for any note."""
    if not versions:
        return
    src = notes._history_dir(frm_dir, name)
    dest = notes._history_dir(to_dir, name, create=True)
    for v in versions:
        if os.path.lexists(dest / v):
            continue
        data = _bytes(src, v)
        if data is not None:
            agentfs._atomic_write(dest / v, data)


def _drop_history(d: Path, name: str, only: list[str] | None = None) -> None:
    """The note's history in `d`, gone with it: all of it (a move), or just
    the versions named (the undo of a copy, which leaves whatever was there
    before the copy came)."""
    try:
        hd = notes._history_dir(d, name)
    except AgentFsError:
        return
    if not os.path.isdir(hd) or os.path.islink(hd):
        return
    if only is None:
        shutil.rmtree(hd)
        return
    for v in only:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(hd / v)
    with contextlib.suppress(OSError):
        os.rmdir(hd)


# --- one move or copy -------------------------------------------------------------------

def _why_confirm(cfg, frm: str, to: str, entry: dict | None) -> str:
    """Why a move or copy must be confirmed, or "" (master plan, section
    7.3): into Communal, out of a quarantined agent (any agent when the list
    cannot be read), or a note that may hold text from web pages."""
    if to == COMMUNAL:
        return "every agent will be able to read this note, and its past versions"
    if frm != COMMUNAL:
        q = cfg.quarantined() if cfg is not None else None
        if q is None:
            return "the quarantine list cannot be read, so every agent counts as quarantined"
        if frm in q:
            return f"{frm} is quarantined"
    if entry is not None and entry.get("tainted"):
        return "it may contain text from web pages"
    return ""


def _move_locked(frm: str, name: str, to: str, action: str, *, undo_of: str = "",
                 expect: str | None = None, expect_rev: int | None = None,
                 cfg=None, confirmed: bool = True) -> dict:
    """Move or copy the note, the lock held and the journal settled."""
    sd, smeta, sgot = notes._current(frm)
    if smeta is None:
        raise notes.NotesError(f"the notes record in {_label(frm)} (.meta.json) cannot be read, "
                               "so nothing is moved out of it until it is fixed",
                               "unreadable-record")
    data = sgot.get(name)
    if isinstance(data, notes.NotesError):
        raise notes.NotesError(f"{name} cannot be moved: {data}")
    if data is None:
        raise notes.NotesError(f"{_label(frm)} has no note called {name}")
    try:
        notes._decode(data)
    except notes.NotesError as e:
        raise notes.NotesError(f"{name} cannot be moved: {e}") from None
    e = smeta[name]
    digest = _sha(data)
    if expect is not None and (digest != expect or e["rev"] != expect_rev):
        raise notes.NotesError(f"{name} in {_label(frm)} changed since it was moved there; "
                               "Undo is refused so the change is not lost")
    if not confirmed:
        why = _why_confirm(cfg, frm, to, e)
        if why:
            raise notes.NotesError(f"{why}: run it again with --confirm once you are sure")
    dd = _dir(to, create=True)
    dmeta = notes._load_meta(dd)
    if dmeta is None:
        raise notes.NotesError(f"the notes record in {_label(to)} (.meta.json) cannot be read, "
                               "so nothing is moved into it until it is fixed",
                               "unreadable-record")
    dnames = notes._note_names(dd)
    if name in dnames or os.path.lexists(dd / (name + notes.SUFFIX)):
        raise notes.NotesError(f"{_label(to)} already has a note called {name}; rename or "
                               "combine that one first")
    if len(dnames) >= notes.FOLDER_MAX:
        raise notes.NotesError(f"{_label(to)} already holds {notes.FOLDER_MAX} notes, the most "
                               "a folder can", "too-many")
    before = dmeta.get(name)
    entry = dict(e)
    if before is not None:
        entry["rev"] = max(e["rev"], before["rev"])
        entry["locked"] = bool(e["locked"] or before["locked"])
    versions = [v.name for v in notes._versions(sd, name)]
    rec = {"v": 1, "op": transfer._new_op(), "kind": "note", "action": action, "from": frm,
           "to": to, "name": name, "digest": digest, "files": 1, "bytes": len(data),
           "entry": entry, "before": before, "versions": versions, "undo_of": undo_of,
           "at": round(time.time(), 3), "state": "begun"}
    stage, hidden = f".t-{rec['op']}.md", f".t-{rec['op']}-gone.md"
    staged = published = False
    hid = False
    entered = False
    # Both folders opened before anything is recorded, so a folder that
    # cannot be opened leaves no record behind and no descriptor open.
    dfd = _open(dd)
    try:
        sfd = _open(sd)
    except BaseException:
        os.close(dfd)
        raise
    try:
        transfer._save(rec)
        agentfs._write_beneath(dfd, stage, data, 0o600)
        staged = True
        transfer._fsync(dfd)
        if notes._read_note_bytes(sd / (name + notes.SUFFIX)) != data:
            raise notes.NotesError(f"{name} changed while it was being moved; nothing was "
                                   "changed, try again")
        dmeta[name] = entry
        notes._save_meta(dd, dmeta)
        entered = True
        if action == "move":
            transfer._rename(sfd, name + notes.SUFFIX, sfd, hidden)
            hid = True
        transfer._rename(dfd, stage, dfd, name + notes.SUFFIX)
        published, staged = True, False
        transfer._fsync(dfd)
        transfer._fsync(sfd)
        rec["state"] = "published"
        transfer._save(rec)
    except BaseException as err:
        if not published:
            if staged:
                with contextlib.suppress(OSError):
                    os.unlink(stage, dir_fd=dfd)
            if hid:
                with contextlib.suppress(OSError, AgentFsError):
                    transfer._rename(sfd, hidden, sfd, name + notes.SUFFIX)
            if entered:
                with contextlib.suppress(OSError, AgentFsError):
                    _restore_entry(dd, name, entry, before)
            with contextlib.suppress(OSError, AgentFsError):
                transfer._forget(rec)
        if isinstance(err, OSError):
            done = "moved" if action == "move" else "copied"
            if published:
                raise notes.NotesError(f"it was {done}, and recording that failed "
                                       f"({err.strerror}); it is finished on the next try") from None
            if err.errno == 28:
                raise notes.NotesError("the disk is full; nothing was changed") from None
            raise notes.NotesError(f"it could not be {done} ({err.strerror}); nothing was "
                                   "changed") from None
        raise
    finally:
        os.close(dfd)
        os.close(sfd)
    return _finish_or_say(rec)


def _restore_entry(dd: Path, name: str, entry: dict, before: dict | None) -> None:
    """Put the destination's entry back as it was, if it is still the one a
    transfer wrote and no note of that name is there."""
    meta = notes._load_meta(dd)
    if meta is None or meta.get(name) != entry or os.path.lexists(dd / (name + notes.SUFFIX)):
        return
    if before is None:
        meta.pop(name, None)
    else:
        meta[name] = before
    notes._save_meta(dd, meta)


def _finish(rec: dict) -> dict:
    """Step 7, for a published record; run again by recovery, so each part
    is safe to repeat."""
    action, frm, to, name, op = rec["action"], rec["from"], rec["to"], rec["name"], rec["op"]
    if action == "combine":
        _finish_combine(rec)
    elif action in ("move", "copy"):
        _copy_versions(_dir(frm), _dir(to), name, rec["versions"])
    if action in ("move", "remove"):
        sd = _dir(frm)
        meta = notes._load_meta(sd)
        if meta is None:
            raise notes.NotesError(f"the notes record in {_label(frm)} cannot be read, so the "
                                   f"note's old entry there cannot be closed")
        # The undo of a copy: what that folder had before the copy came (a
        # locked tombstone stays locked), and only the versions it brought.
        orig = (transfer._finished(rec["undo_of"])
                if action == "remove" and rec.get("undo_of") else None)
        held = bool(orig and orig.get("before") and orig["before"]["locked"])
        e = meta.get(name)
        if e is not None and e["hash"] == rec["entry"]["hash"] and \
                not os.path.lexists(sd / (name + notes.SUFFIX)):
            meta[name] = _tombstone({**e, "locked": held}, keep_lock=True)
            notes._save_meta(sd, meta)
        if action == "move":
            _drop_history(sd, name)
        else:
            _drop_history(sd, name, only=orig["versions"] if orig else [])
        with contextlib.suppress(FileNotFoundError):
            os.unlink(sd / f".t-{op}-gone.md")
    undo_of = rec.get("undo_of", "")
    if undo_of:
        orig = transfer._finished(undo_of)
        if orig is not None and orig.get("state") == "done":
            orig["state"], orig["undone_by"] = "undone", op
            transfer._save(orig)
    rec["state"] = "done"
    transfer._save(rec)
    transfer._prune()
    return rec


def _finish_or_say(rec: dict) -> dict:
    try:
        return _finish(rec)
    except (OSError, AgentFsError) as e:
        why = e.strerror if isinstance(e, OSError) else str(e)
        raise notes.NotesError(f"{rec['name']} is in {_label(rec['to'])} now, but finishing "
                               f"the {rec['action']} failed ({why}); it is finished on the "
                               "next try") from None


def _remove_locked(target: str, name: str, *, undo_of: str, expect: str, expect_rev: int,
                   versions: list[str]) -> dict:
    """Take back a copy (the undo of a copy), only while it is exactly the
    revision that landed."""
    d, meta, got = notes._current(target)
    if meta is None:
        raise notes.NotesError(f"the notes record in {_label(target)} cannot be read; Undo is "
                               "refused until it is fixed", "unreadable-record")
    data = got.get(name)
    if not isinstance(data, bytes):
        raise notes.NotesError(f"{_label(target)} has no note called {name} any more")
    e = meta[name]
    if _sha(data) != expect or e["rev"] != expect_rev:
        raise notes.NotesError(f"{name} in {_label(target)} changed since it was copied there; "
                               "Undo is refused so the change is not lost")
    rec = {"v": 1, "op": transfer._new_op(), "kind": "note", "action": "remove", "from": target,
           "to": target, "name": name, "digest": expect, "files": 1, "bytes": len(data),
           "entry": dict(e), "before": None, "versions": list(versions), "undo_of": undo_of,
           "at": round(time.time(), 3), "state": "begun"}
    transfer._save(rec)
    fd = _open(d)
    try:
        transfer._rename(fd, name + notes.SUFFIX, fd, f".t-{rec['op']}-gone.md")
        transfer._fsync(fd)
        rec["state"] = "published"
        transfer._save(rec)
    except BaseException:
        if rec["state"] == "begun":
            if os.path.lexists(d / f".t-{rec['op']}-gone.md") and \
                    not os.path.lexists(d / (name + notes.SUFFIX)):
                with contextlib.suppress(OSError, AgentFsError):
                    transfer._rename(fd, f".t-{rec['op']}-gone.md", fd, name + notes.SUFFIX)
            transfer._forget(rec)
        raise
    finally:
        os.close(fd)
    return _finish_or_say(rec)


# --- combine ---------------------------------------------------------------------------

def _combined_text(into: str, texts: dict[str, str], order: list[str], into_exists: bool) -> str:
    parts = []
    if into_exists:
        parts.append(texts[into].rstrip("\n"))
    for n in order:
        if n == into and into_exists:
            continue
        parts.append(f"## {notes.topic_label(n)}\n\n{texts[n].strip(chr(10))}".rstrip("\n"))
    return "\n\n".join(p for p in parts if p != "") + "\n"


def _combine_locked(target: str, into: str, names: list[str]) -> dict:
    d, meta, got = notes._current(target)
    if meta is None:
        raise notes.NotesError(f"the notes record in {_label(target)} (.meta.json) cannot be "
                               "read, so nothing is combined until it is fixed",
                               "unreadable-record")
    texts, raw = {}, {}
    for n in names:
        data = got.get(n)
        if isinstance(data, notes.NotesError):
            raise notes.NotesError(f"{n} cannot be combined: {data}")
        if data is None:
            raise notes.NotesError(f"{_label(target)} has no note called {n}")
        try:
            texts[n] = notes._decode(data)
        except notes.NotesError as e:
            raise notes.NotesError(f"{n} cannot be combined: {e}") from None
        raw[n] = data
    into_exists = into in names
    if not into_exists and (into in got or os.path.lexists(d / (into + notes.SUFFIX))):
        raise notes.NotesError(f"there is already a note called {into}: pick it among the notes "
                               "to combine, or give the combined note another name")
    text = _combined_text(into, texts, names, into_exists)
    if len(text) > notes.NOTE_MAX:
        raise notes.NotesError(f"combined, they would be {len(text)} characters, and a note holds "
                               f"at most {notes.NOTE_MAX}", "too-long")
    new = text.encode("utf-8")
    before = meta.get(into)
    parts = [meta[n] for n in names]
    entry = {"rev": (before["rev"] if before else 0) + 1, "author": notes.YOU, "at": time.time(),
             "hash": notes._hash(new), "tainted": any(p["tainted"] for p in parts),
             "locked": any(p["locked"] for p in parts) or bool(before and before["locked"])}
    sources = [{"name": n, "digest": _sha(raw[n]), "entry": dict(meta[n])}
               for n in names if n != into]
    rec = {"v": 1, "op": transfer._new_op(), "kind": "note", "action": "combine", "from": target,
           "to": target, "name": into, "digest": _sha(new), "files": len(names),
           "bytes": len(new), "parts_bytes": sum(len(raw[n]) for n in names),
           "entry": entry, "before": before, "versions": [],
           "sources": sources, "prior": _sha(raw[into]) if into_exists else "",
           "undo_of": "", "at": round(time.time(), 3), "state": "begun"}
    transfer._save(rec)
    published = False
    try:
        # Each note combined away keeps its last text as a version, so its
        # whole past is there to restore from Earlier notes.
        for src in sources:
            notes._keep_version(d, src["name"], raw[src["name"]], src["entry"]["author"],
                                src["entry"]["tainted"])
        if into_exists:
            notes._keep_version(d, into, raw[into], before["author"], before["tainted"])
            if notes._read_note_bytes(d / (into + notes.SUFFIX)) != raw[into]:
                raise notes.NotesError(f"{into} changed while it was being combined; nothing "
                                       "was changed, try again")
            agentfs._atomic_write(d / (into + notes.SUFFIX), new)
        else:
            agentfs._atomic_write(d / (into + notes.SUFFIX), new, exclusive=True)
        published = True
        rec["state"] = "published"
        transfer._save(rec)
    except agentfs.Conflict:
        transfer._forget(rec)
        raise notes.NotesError(f"a note called {into} appeared meanwhile; nothing was "
                               "changed") from None
    except BaseException as err:
        if not published:
            transfer._forget(rec)
        if isinstance(err, OSError) and not published:
            raise notes.NotesError(f"they could not be combined ({err.strerror}); nothing was "
                                   "changed") from None
        raise
    return _finish_or_say(rec)


def _finish_combine(rec: dict) -> None:
    """The combined note's entry, each other note's tombstone, and their
    files gone: safe to repeat. A note changed by hand since (a crash, then
    an edit before recovery) is left where it is."""
    d = _dir(rec["to"])
    meta = notes._load_meta(d)
    if meta is None:
        raise notes.NotesError(f"the notes record in {_label(rec['to'])} cannot be read")
    into = rec["name"]
    data = _bytes(d, into + notes.SUFFIX)
    if data is not None and _sha(data) == rec["digest"] and meta.get(into) != rec["entry"]:
        meta[into] = dict(rec["entry"])
    for src in rec["sources"]:
        n = src["name"]
        path = d / (n + notes.SUFFIX)
        cur = _bytes(d, n + notes.SUFFIX)
        if cur is not None and _sha(cur) != src["digest"]:
            continue
        e = meta.get(n)
        if e is not None and e["hash"] != "":
            meta[n] = _tombstone(e, keep_lock=True)
        if cur is not None:
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
    notes._save_meta(d, meta)


# --- recovery ----------------------------------------------------------------------------

def settle(rec: dict) -> str:
    """Finish or roll back one note record left open (transfer._settle sends
    note records here; the lock is held). Returns what was done."""
    if rec["state"] == "published":
        _finish(rec)
        return "finished"
    action, frm, to, name, op = rec["action"], rec["from"], rec["to"], rec["name"], rec["op"]
    stage, hidden, file = f".t-{op}.md", f".t-{op}-gone.md", name + notes.SUFFIX
    if action == "combine":
        d = _dir(to)
        data = _bytes(d, file)
        if data is not None and _sha(data) == rec["digest"]:
            rec["state"] = "published"
            transfer._save(rec)
            _finish(rec)
            return "finished"
        transfer._forget(rec)
        return "rolled back"
    if action == "remove":
        d = _dir(frm)
        if os.path.lexists(d / hidden) and not os.path.lexists(d / file):
            rec["state"] = "published"
            transfer._save(rec)
            _finish(rec)
            return "finished"
        transfer._forget(rec)
        return "rolled back"
    sd = _dir(frm)
    try:
        dd = _dir(to)
        dd_there = dd.is_dir()
    except AgentFsError:
        dd, dd_there = None, False
    landed = False
    if dd_there and not os.path.lexists(dd / stage):
        data = _bytes(dd, file)
        landed = data is not None and _sha(data) == rec["digest"]
    if landed and (action != "move" or os.path.lexists(sd / hidden)
                   or not os.path.lexists(sd / file)):
        rec["state"] = "published"
        transfer._save(rec)
        _finish(rec)
        return "finished"
    if dd_there:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(dd / stage)
        _restore_entry(dd, name, rec["entry"], rec["before"])
    if action == "move" and os.path.lexists(sd / hidden):
        if os.path.lexists(sd / file):
            raise transfer.Stuck(f"{name} was hidden in {_label(frm)} by a move that did not "
                                 f"finish, and a new {name} is there now; the old one is in "
                                 f"notes/{hidden}")
        fd = _open(sd)
        try:
            transfer._rename(fd, hidden, fd, file)
            transfer._fsync(fd)
        finally:
            os.close(fd)
    transfer._forget(rec)
    return "rolled back"


# --- what the person does --------------------------------------------------------------

def result(rec: dict) -> dict:
    out = {"op": rec["op"], "kind": "note", "action": rec["action"], "from": rec["from"],
           "to": rec["to"], "name": rec["name"], "bytes": rec["bytes"],
           "rev": rec["entry"]["rev"], "versions": len(rec.get("versions", [])),
           "undo_of": rec.get("undo_of", "")}
    if rec["action"] == "combine":
        out["combined"] = [s["name"] for s in rec["sources"]]
    return out


def _check(frm: str, to: str, name: str) -> None:
    for t in (frm, to):
        if not transfer._target_ok(t):
            raise notes.NotesError(f"not an agent id or communal: {t!r}")
    notes._check_name(name)
    if frm == to:
        raise notes.NotesError(f"{name} is in {_label(to)} already")


def _do(frm: str, name: str, to: str, action: str, confirmed: bool, cfg) -> dict:
    _check(frm, to, name)
    with agentfs._locked(), transfer.working():
        transfer._recover_locked()
        rec = _move_locked(frm, name, to, action, cfg=cfg, confirmed=confirmed)
        transfer._audit(rec, f"note_{action}")
    return result(rec)


def move(frm: str, name: str, to: str, *, confirmed: bool = False, cfg=None) -> dict:
    """Move the note `name` from `frm` to `to` (agent folder ids, or
    communal), with its history and its entry. A widening move needs
    `confirmed`; `cfg` is read for the quarantine list (a fresh Config when
    None)."""
    return _do(frm, name, to, "move", confirmed, _cfg(cfg))


def copy(frm: str, name: str, to: str, *, confirmed: bool = False, cfg=None) -> dict:
    return _do(frm, name, to, "copy", confirmed, _cfg(cfg))


def _cfg(cfg):
    if cfg is not None:
        return cfg
    from runtime import Config
    return Config()


def combine(target: str, into: str, names: list[str]) -> dict:
    """Combine the notes `names` of `target` into the topic note `into`: one
    of them (kept, the others added under it) or a new name."""
    if not transfer._target_ok(target):
        raise notes.NotesError(f"not an agent id or communal: {target!r}")
    notes._check_name(into)
    if not isinstance(names, list) or len(names) != len(set(names)):
        raise notes.NotesError("name each note to combine once")
    for n in names:
        notes._check_name(n)
    others = [n for n in names if n != into]
    if len(others) < 1 or len(names) < 2 or len(names) > COMBINE_MAX:
        raise notes.NotesError(f"combine takes 2 to {COMBINE_MAX} notes")
    with agentfs._locked(), transfer.working():
        transfer._recover_locked()
        rec = _combine_locked(target, into, names)
        transfer._audit(rec, "note_combine", parts_bytes=rec["parts_bytes"])
    return result(rec)


def undo(op: str) -> dict:
    """Undo the note move or copy `op`, if neither side changed since."""
    return transfer._undo(op, "note")


def undo_locked(rec: dict) -> dict:
    """transfer._undo's note half: the record is a finished, undoable note
    record and the lock is held."""
    name, op = rec["name"], rec["op"]
    if rec["action"] == "move":
        return _move_locked(rec["to"], name, rec["from"], "move", undo_of=op,
                            expect=rec["digest"], expect_rev=rec["entry"]["rev"])
    if rec["action"] == "copy":
        sd = _dir(rec["from"])
        data = _bytes(sd, name + notes.SUFFIX)
        if data is None or _sha(data) != rec["digest"]:
            raise notes.NotesError(f"the original {name} in {_label(rec['from'])} changed or is "
                                   "gone since it was copied; Undo is refused, since it would "
                                   "remove the only copy as it was")
        return _remove_locked(rec["to"], name, undo_of=op, expect=rec["digest"],
                              expect_rev=rec["entry"]["rev"], versions=rec["versions"])
    raise notes.NotesError("that cannot be undone")


def history(limit: int = 20) -> list[dict]:
    return transfer.history(limit, kind="note")


def lanes(cfg) -> dict:
    """Every notes folder as a lane, for the Notes tabs: the main agent's,
    each agent's, and Communal's, each note with its topic label and first
    line. A folder that cannot be read is a lane with its problem."""
    labels = notes.labels(cfg)
    try:
        q = cfg.quarantined()
    except Exception:           # noqa: BLE001 -- unreadable reads as everyone
        q = None
    targets = [MAIN] + [t for t in agentfs.targets() if t not in (COMMUNAL, MAIN)] + [COMMUNAL]
    out = []
    for t in targets:
        lane = {"id": t, "label": "Communal" if t == COMMUNAL else labels.get(t, t),
                "quarantined": t != COMMUNAL and (q is None or t in q),
                "notes": [], "locked_all": False, "problem": ""}
        try:
            got = notes.list_notes(t)
        except (AgentFsError, OSError) as e:
            lane["problem"] = str(e)
            out.append(lane)
            continue
        for n in got["notes"]:
            n["author_label"] = labels.get(n["author"], n["author"])
        lane.update(notes=got["notes"], locked_all=got["locked_all"], problem=got["problem"])
        out.append(lane)
    return {"lanes": out, "quarantine_readable": q is not None}


# --- CLI -----------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agentvoice notes",
                                 description="Moving, copying and combining notes (phase M13). "
                                             "One folder's notes: agentvoice agents notes.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lanes", help="every notes folder, each note with its topic")
    p.add_argument("--json", action="store_true")
    for verb, what in (("move", "move a note, with its history, to another agent or Communal"),
                       ("copy", "copy a note, with its history, to another agent or Communal")):
        p = sub.add_parser(verb, help=what)
        p.add_argument("frm", metavar="FROM", help="an agent's folder id, or communal")
        p.add_argument("name")
        p.add_argument("to", metavar="TO", help="an agent's folder id, or communal")
        p.add_argument("--confirm", action="store_true",
                       help="into Communal, out of a quarantined agent, or a note that may hold "
                            "text from web pages: you were asked")
    p = sub.add_parser("combine", help="combine notes of one folder into one topic note")
    p.add_argument("target", help="an agent's folder id, or communal")
    p.add_argument("into", help="the note kept (one of NAMES), or a new note's name")
    p.add_argument("names", nargs="+", metavar="NAME")
    p = sub.add_parser("undo", help="undo a move or copy, if nothing changed since")
    p.add_argument("op", help="its id, from the move's output or `history`")
    p = sub.add_parser("history", help="the moves, copies and combines recorded")
    p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    from speech_text import safe_for_terminal as safe
    try:
        if a.cmd == "lanes":
            from runtime import Config
            got = lanes(Config())
            if a.json:
                print(json.dumps(got, ensure_ascii=False))
            else:
                for lane in got["lanes"]:
                    print(safe(lane["label"]) + (" (quarantined)" if lane["quarantined"] else ""))
                    for n in lane["notes"]:
                        print(safe(f"  {n['name']}  {n['first_line']}"))
                    if lane["problem"]:
                        print(safe(f"  ! {lane['problem']}"))
            return 0
        if a.cmd == "history":
            got = history()
            if a.json:
                print(json.dumps(got))
            else:
                for r in got:
                    where = (f"{r['from']} → {r['to']}" if r["action"] in ("move", "copy")
                             else f"in {r['from']}")
                    extra = (" (undone)" if r["state"] == "undone" else
                             f" ({r['state']}: {r['problem']})" if r["state"] == "stuck" else
                             " (undo)" if r["undo_of"] else "")
                    print(safe(f"{r['op']}  {r['action']} {r['name']} {where}{extra}"))
            return 0
        if a.cmd == "undo":
            print(json.dumps(undo(a.op)))
            return 0
        if a.cmd == "combine":
            print(json.dumps(combine(a.target, a.into, list(a.names))))
            return 0
        fn = move if a.cmd == "move" else copy
        print(json.dumps(fn(a.frm, a.name, a.to, confirmed=a.confirm)))
        return 0
    except AgentFsError as e:
        print(f"agentvoice notes: {safe(str(e))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
