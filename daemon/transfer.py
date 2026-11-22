"""Moving and copying a skill between agents and Communal, and undoing it
(master plan, phase M12). Notes reuse the journal since M13: a record whose
`kind` is "note" is written, settled and undone by notemoves.py, and this
module only keeps the journal, recovery's loop and the dispatch.

Only the person moves anything: the pages and `agentvoice skills move|copy|
undo` call this, no agent tool does, and an agent running those commands is
asked at every level (the orders guard's SKILL_WORDS). Agent Voice's own
folders only: a skill found outside it is never moved, only copied in
(agentfs.import_skill), and that copy is recorded here so it can be undone.

**One transfer, under the one lock every folder write takes** (agentfs.
_locked), in this order:

1. anything an earlier transfer left unfinished is settled first (below);
2. the source is read whole, one folder at a time by descriptor with no link
   followed at any level, inside the bounds every skill keeps (64 files,
   2 MiB, 256 KB a file, a 20,000-character SKILL.md that parse_skill
   accepts), and hashed; the destination is checked free of that name;
3. a journal record is written (`begun`), naming the stage and the hidden
   source by the operation's id;
4. the whole folder is written into a stage inside the destination's skills
   folder (`.t-<op>`), through that folder's open descriptor, so a folder
   swapped for a link meanwhile cannot redirect a write;
5. the source is read again, and must hash the same;
6. a move hides the source (renamed to `.t-<op>-gone` beside it, which no
   reader lists) and then publishes the stage under the skill's name by one
   no-replace rename; a copy only publishes. Hidden first, so the moment
   between the two renames shows the skill in neither place, never both;
7. the record says `published`; the history travels (copied, then the
   source's removed for a move), the hidden source is deleted, the record
   says `done`.

**Crash-safe.** A record still open is settled before any new transfer and
when the daemon starts, before any agent is built, so neither side is ever
shown to an adapter half-done: a record that never reached `published`
rolls back (the stage removed, a hidden source renamed back), one that did
rolls forward (step 7). The daemon also settles one on its idle poll, without
waiting on the lock. A record that cannot be settled becomes `stuck`, with
why, and `agentvoice skills history` lists it.

**Undo is tied to the exact revision.** The record keeps the hash of what
was published. Undoing a move moves it back only while the destination
still hashes the same and the source has no skill of that name; undoing a
copy (or an import) removes the copy only while it hashes the same and, for
a copy, while the original still does too, so an undo can never lose the
only copy of something. An undo is itself recorded, and cannot be undone.

Every transfer writes one audit line: ids, the skill's name and its size,
never its text.
"""
from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agentfs  # noqa: E402
import paths  # noqa: E402
from agentfs import COMMUNAL, AgentFsError  # noqa: E402

#: An operation's id: when it began, and four random bytes.
_OP = re.compile(r"\d{19}-[0-9a-f]{8}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
#: What a record may say was done. `remove` is the undo of a copy or import.
ACTIONS = ("move", "copy", "import", "remove")
#: "outside": where an imported skill came from (never a path).
OUTSIDE = "outside"
#: Finished records kept for `history` and for undo.
KEEP = 100
#: Bytes of a record read back; a record is a few hundred.
RECORD_CAP = 8192
OPEN = ".open.json"
DONE = ".json"


class Stuck(AgentFsError):
    """A record that could not be settled."""


#: How deep this process is inside a transfer or a recovery (phase M13).
#: notes._current settles open records before it reads, which must not
#: happen while one is being written or settled here.
_BUSY = 0


@contextlib.contextmanager
def working():
    global _BUSY
    _BUSY += 1
    try:
        yield
    finally:
        _BUSY -= 1


def busy() -> bool:
    return _BUSY > 0


# --- the journal ----------------------------------------------------------------

def journal_dir(create: bool = False) -> Path:
    """agents/.transfers: inside the folder the orders guard covers, so an
    agent cannot leave a record for recovery to act on without being asked."""
    agentfs._no_link(paths.AGENTS_DIR)
    if create:
        paths.private_dir(paths.AGENTS_DIR)
        agentfs._no_link(paths.AGENTS_DIR)
    d = paths.AGENTS_DIR / ".transfers"
    agentfs._no_link(d)
    if create:
        paths.private_dir(d)
        agentfs._no_link(d)
    return d


def _new_op() -> str:
    return f"{time.time_ns():019d}-{os.urandom(4).hex()}"


def _target_ok(t) -> bool:
    return t == COMMUNAL or agentfs._valid_agent(t)


def _valid(rec) -> bool:
    """A record this module wrote, in the shape it writes: anything else is
    never acted on (a record's names become folder names)."""
    if not isinstance(rec, dict):
        return False
    if rec.get("kind") == "note":
        import notemoves
        return notemoves.valid(rec)
    action, frm, to = rec.get("action"), rec.get("from"), rec.get("to")
    if action not in ACTIONS or not isinstance(rec.get("op"), str) or not _OP.fullmatch(rec["op"]):
        return False
    if not agentfs.valid_skill_name(rec.get("name")) or rec.get("kind") != "skill":
        return False
    if not isinstance(rec.get("digest"), str) or not _DIGEST.fullmatch(rec["digest"]):
        return False
    if action == "import":
        ok = frm == OUTSIDE and _target_ok(to)
    elif action == "remove":
        ok = _target_ok(frm) and to == frm
    else:
        ok = _target_ok(frm) and _target_ok(to) and frm != to
    undo_of = rec.get("undo_of", "")
    return ok and isinstance(undo_of, str) and (undo_of == "" or bool(_OP.fullmatch(undo_of)))


def _read_record(path: Path) -> dict | None:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        data = os.read(fd, RECORD_CAP + 1)
    except OSError:
        return None
    finally:
        os.close(fd)
    if len(data) > RECORD_CAP:
        return None
    try:
        rec = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return rec if _valid(rec) else None


def _save(rec: dict) -> None:
    """Write the record: open (`<op>.open.json`) until it is finished, then
    `<op>.json` and the open one removed. A crash between the two leaves
    both, and the finished one wins."""
    d = journal_dir(create=True)
    data = json.dumps(rec, sort_keys=True).encode()
    if rec["state"] in ("begun", "published"):
        agentfs._atomic_write(d / (rec["op"] + OPEN), data)
        return
    agentfs._atomic_write(d / (rec["op"] + DONE), data)
    with contextlib.suppress(FileNotFoundError):
        os.unlink(d / (rec["op"] + OPEN))


def _forget(rec: dict) -> None:
    """A record whose transfer never happened (refused, or rolled back)."""
    with contextlib.suppress(OSError, AgentFsError):
        os.unlink(journal_dir() / (rec["op"] + OPEN))


def _open_names() -> list[str]:
    try:
        return sorted(n for n in os.listdir(journal_dir()) if n.endswith(OPEN))
    except (OSError, AgentFsError):
        return []


def _finished(op: str) -> dict | None:
    try:
        return _read_record(journal_dir() / (op + DONE))
    except AgentFsError:
        return None


def _prune() -> None:
    try:
        d = journal_dir()
        done = sorted((n for n in os.listdir(d) if n.endswith(DONE) and not n.endswith(OPEN)),
                      reverse=True)
    except (OSError, AgentFsError):
        return
    for n in done[KEEP:]:
        with contextlib.suppress(OSError):
            os.unlink(d / n)


# --- reading and writing a skill folder by descriptor ------------------------------

_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _digest(files) -> str:
    """The same digest agentfs._read_skill makes of a folder found outside."""
    h = hashlib.sha256()
    for rel, data, mode in files:
        h.update(f"{rel}\0{mode}\0{len(data)}\0".encode())
        h.update(data)
    return h.hexdigest()


def read_item(parent_fd: int, name: str) -> tuple[list[tuple[str, bytes, int]], str]:
    """Every file of the skill `name` under the open folder `parent_fd`, as
    (path inside it, bytes, 0o700 or 0o600), and their digest. Opened one
    folder at a time with no link followed, the folder itself included.
    FileNotFoundError when it is not there; AgentFsError for anything a
    skill may not hold."""
    try:
        root = os.open(name, _DIR, dir_fd=parent_fd)
    except FileNotFoundError:
        raise
    except OSError as e:
        if e.errno in (errno.ELOOP, errno.ENOTDIR):
            raise AgentFsError(f"{name} is a link or not a folder, which is refused here") from None
        raise AgentFsError(f"{name} cannot be read ({e.strerror})") from None
    files: list[tuple[str, bytes, int]] = []
    total = 0
    stack = [("", root)]
    try:
        while stack:
            rel, fd = stack.pop()
            try:
                for entry in sorted(os.listdir(fd)):
                    sub = f"{rel}/{entry}" if rel else entry
                    st = os.stat(entry, dir_fd=fd, follow_symlinks=False)
                    if stat.S_ISLNK(st.st_mode):
                        raise AgentFsError(f"it holds a link ({sub}), which is refused here")
                    if stat.S_ISDIR(st.st_mode):
                        stack.append((sub, os.open(entry, _DIR, dir_fd=fd)))
                        continue
                    if not stat.S_ISREG(st.st_mode):
                        raise AgentFsError(f"{sub} is not a plain file")
                    if len(files) >= agentfs.SKILL_FILES_MAX:
                        raise AgentFsError(f"it holds more than {agentfs.SKILL_FILES_MAX} files")
                    ffd = os.open(entry, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                                  dir_fd=fd)
                    try:
                        fst = os.fstat(ffd)
                        if not stat.S_ISREG(fst.st_mode):
                            raise AgentFsError(f"{sub} is not a plain file")
                        with os.fdopen(ffd, "rb", closefd=False) as f:
                            data = f.read(agentfs.READ_CAP + 1)
                    finally:
                        os.close(ffd)
                    if len(data) > agentfs.READ_CAP:
                        raise AgentFsError(f"{sub} is larger than {agentfs.READ_CAP // 1024} KB")
                    total += len(data)
                    if total > agentfs.SKILL_BYTES_MAX:
                        raise AgentFsError(f"it holds more than "
                                           f"{agentfs.SKILL_BYTES_MAX // 1024 // 1024} MB")
                    files.append((sub, data, 0o700 if fst.st_mode & stat.S_IXUSR else 0o600))
            finally:
                os.close(fd)
    except OSError as e:
        for _, fd in stack:
            with contextlib.suppress(OSError):
                os.close(fd)
        if e.errno in (errno.ELOOP, errno.ENOTDIR):
            raise AgentFsError("a folder inside it was swapped for a link or a file, "
                               "which is refused here") from None
        raise AgentFsError(f"it cannot be read ({e.strerror})") from None
    except BaseException:
        for _, fd in stack:
            with contextlib.suppress(OSError):
                os.close(fd)
        raise
    files.sort()
    return files, _digest(files)


def skill_text(name: str, files) -> str:
    """The skill's SKILL.md, or AgentFsError when it breaks a rule every
    skill keeps (parse_skill): a skill with a problem is not moved."""
    raw = next((d for rel, d, _ in files if rel == "SKILL.md"), None)
    if raw is None:
        raise AgentFsError(f"{name} has no SKILL.md")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise AgentFsError(f"{name}'s SKILL.md is not UTF-8 text") from None
    _, why = agentfs.parse_skill(name, text)
    if why:
        raise AgentFsError(f"{name} has a problem, so it is not moved until it is fixed: {why}")
    return text


def _present(dir_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def _rename(fd_a: int, a: str, fd_b: int, b: str) -> None:
    """Rename failing rather than replacing anything at `b` (renameat2
    RENAME_NOREPLACE). Where the system has no such rename, nothing moves:
    a check then a plain rename could replace a folder made in between."""
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    fn = getattr(libc, "renameat2", None)
    if fn is None:
        raise AgentFsError("this system cannot rename a folder without risking replacing "
                           "one; nothing was changed")
    if fn(fd_a, a.encode(), fd_b, b.encode(), 1) == 0:
        return
    err = ctypes.get_errno()
    if err == errno.EEXIST:
        raise AgentFsError(f"something named {b} appeared meanwhile; nothing was changed")
    if err in (errno.ENOSYS, errno.EINVAL):
        raise AgentFsError("this filesystem cannot rename a folder without risking replacing "
                           "one; nothing was changed")
    raise OSError(err, os.strerror(err))


def _fsync(fd: int) -> None:
    with contextlib.suppress(OSError):
        os.fsync(fd)


def _rmtree(dir_fd: int, name: str) -> None:
    if _present(dir_fd, name):
        shutil.rmtree(name, dir_fd=dir_fd)


def _skills_fd(target: str) -> int:
    return agentfs._open_skills_dir(target)


def _label(target: str) -> str:
    return "Communal" if target == COMMUNAL else target


# --- history, which travels with the skill ------------------------------------------

def _file(name: str) -> str:
    return f"skills/{name}/SKILL.md"


def _copy_history(frm: str, to: str, name: str) -> None:
    """Every saved version of the skill's SKILL.md in `frm`, into `to`'s
    history (each by its own name, so doing it twice changes nothing)."""
    versions = agentfs._versions(frm, _file(name))
    if not versions:
        return
    dest = agentfs._history_dir(to, _file(name), create=True)
    for v in versions:
        if os.path.lexists(dest / v.name):
            continue
        try:
            fd = os.open(v, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        except OSError:
            continue
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                continue
            data = os.read(fd, agentfs.READ_CAP + 1)
        except OSError:
            continue
        finally:
            os.close(fd)
        if len(data) <= agentfs.READ_CAP:
            agentfs._atomic_write(dest / v.name, data)
    agentfs._prune(to, _file(name))


def _drop_history(target: str, name: str) -> None:
    """The skill's history in `target`, gone with it (a move, an undone copy)."""
    try:
        d = agentfs._history_dir(target, _file(name))
    except AgentFsError:
        return
    skill_hist = d.parent             # .history/skills/<name>
    with contextlib.suppress(AgentFsError):
        agentfs._no_link(skill_hist)
        if os.path.isdir(skill_hist) and not os.path.islink(skill_hist):
            shutil.rmtree(skill_hist)


def _kept(target: str, name: str) -> bool:
    """Whether the skill's SKILL.md is as last kept (not "changed outside")."""
    try:
        return not agentfs.read_file(target, _file(name))["changed_outside"]
    except AgentFsError:
        return False


def _keep_at(target: str, name: str, who: str) -> None:
    """Save the live SKILL.md as kept at `target` if it does not read so
    already: a skill kept where it was is kept where it lands."""
    path, _ = agentfs._resolve(target, _file(name))
    raw = agentfs._raw_text(path)
    if raw is not None and raw != agentfs._newest_saved(target, _file(name)):
        agentfs._save_version(target, _file(name), raw, who)
        agentfs._prune(target, _file(name))


# --- one transfer ---------------------------------------------------------------------

def _finish(rec: dict) -> dict:
    """Step 7, for a published record; run again by recovery, so each part
    is safe to repeat."""
    action, frm, to, name, op = rec["action"], rec["from"], rec["to"], rec["name"], rec["op"]
    if action in ("move", "copy"):
        _copy_history(frm, to, name)
        if rec.get("kept"):
            _keep_at(to, name, action)
    if action in ("move", "remove"):
        _drop_history(frm, name)
        try:
            fd = _skills_fd(frm)
        except AgentFsError:
            fd = None
        if fd is not None:
            try:
                _rmtree(fd, f".t-{op}-gone")
                _fsync(fd)
            finally:
                os.close(fd)
    undo_of = rec.get("undo_of", "")
    if undo_of:
        orig = _finished(undo_of)
        if orig is not None and orig.get("state") == "done":
            orig["state"], orig["undone_by"] = "undone", op
            _save(orig)
    rec["state"] = "done"
    _save(rec)
    _prune()
    return rec


def _transfer_locked(frm: str, name: str, to: str, action: str, undo_of: str = "",
                     expect: str | None = None) -> dict:
    """Move or copy, the lock held. `expect`: the digest the source must
    have (an undo moving back exactly what was moved)."""
    src_fd = _skills_fd(frm)
    try:
        dst_fd = _skills_fd(to)
    except BaseException:
        os.close(src_fd)
        raise
    rec: dict | None = None
    stage = hidden = None
    published = False
    try:
        try:
            files, digest = read_item(src_fd, name)
        except FileNotFoundError:
            raise AgentFsError(f"{_label(frm)} has no skill named {name}") from None
        if expect is not None and digest != expect:
            raise AgentFsError(f"{name} in {_label(frm)} changed since it was moved there; "
                               "Undo is refused so the change is not lost")
        skill_text(name, files)
        if _present(dst_fd, name):
            raise AgentFsError(f"{_label(to)} already has a skill named {name}; "
                               "rename or remove that one first")
        rec = {"v": 1, "op": _new_op(), "kind": "skill", "action": action, "from": frm,
               "to": to, "name": name, "digest": digest, "files": len(files),
               "bytes": sum(len(d) for _, d, _ in files), "kept": _kept(frm, name),
               "undo_of": undo_of, "at": round(time.time(), 3), "state": "begun"}
        _save(rec)
        stage = f".t-{rec['op']}"
        os.mkdir(stage, 0o700, dir_fd=dst_fd)
        stage_fd = os.open(stage, _DIR, dir_fd=dst_fd)
        try:
            for rel, data, mode in files:
                agentfs._write_beneath(stage_fd, rel, data, mode)
            _fsync(stage_fd)
        finally:
            os.close(stage_fd)
        # The source again: moved as it was when it was checked, or not at all.
        try:
            _, again = read_item(src_fd, name)
        except FileNotFoundError:
            again = ""
        if again != digest:
            raise AgentFsError(f"{name} changed while it was being moved; nothing was changed, "
                               "try again")
        if action == "move":
            hidden = f".t-{rec['op']}-gone"
            _rename(src_fd, name, src_fd, hidden)
        try:
            _rename(dst_fd, stage, dst_fd, name)
        except BaseException:
            if hidden is not None:
                with contextlib.suppress(OSError, AgentFsError):
                    _rename(src_fd, hidden, src_fd, name)
                hidden = None
            raise
        published, stage = True, None
        _fsync(dst_fd)
        _fsync(src_fd)
        rec["state"] = "published"
        _save(rec)
    except BaseException as e:
        # Published but not recorded so: left for recovery, which sees the
        # destination in place and finishes it rather than undo half.
        if not published:
            if stage is not None:
                with contextlib.suppress(OSError):
                    _rmtree(dst_fd, stage)
            if hidden is not None:
                with contextlib.suppress(OSError, AgentFsError):
                    _rename(src_fd, hidden, src_fd, name)
            if rec is not None:
                _forget(rec)
        if isinstance(e, OSError):
            done = "moved" if action == "move" else "copied"
            if published:
                raise AgentFsError(f"it was {done}, and recording that failed ({e.strerror}); "
                                   "it is finished on the next try") from None
            if e.errno == errno.ENOSPC:
                raise AgentFsError("the disk is full; nothing was changed") from None
            raise AgentFsError(f"it could not be {done} ({e.strerror}); nothing was "
                               "changed") from None
        raise
    finally:
        os.close(src_fd)
        os.close(dst_fd)
    return _finish_or_say(rec)


def _finish_or_say(rec: dict) -> dict:
    """_finish, for a transfer that has published: one that fails here is
    left recorded as published, for recovery to finish, and says so rather
    than reading as "nothing happened"."""
    try:
        return _finish(rec)
    except (OSError, AgentFsError) as e:
        why = e.strerror if isinstance(e, OSError) else str(e)
        raise AgentFsError(f"{rec['name']} is in {_label(rec['to'])} now, but finishing "
                           f"the {rec['action']} failed ({why}); it is finished on the next "
                           "try") from None


def _remove_locked(target: str, name: str, undo_of: str, expect: str) -> dict:
    """Take back a copy (the undo of a copy or an import), only while it is
    exactly what was copied."""
    fd = _skills_fd(target)
    rec = None
    hidden = None
    try:
        try:
            files, digest = read_item(fd, name)
        except FileNotFoundError:
            raise AgentFsError(f"{_label(target)} has no skill named {name} any more") from None
        if digest != expect:
            raise AgentFsError(f"{name} in {_label(target)} changed since it was copied there; "
                               "Undo is refused so the change is not lost")
        rec = {"v": 1, "op": _new_op(), "kind": "skill", "action": "remove", "from": target,
               "to": target, "name": name, "digest": digest, "files": len(files),
               "bytes": sum(len(d) for _, d, _ in files), "kept": False,
               "undo_of": undo_of, "at": round(time.time(), 3), "state": "begun"}
        _save(rec)
        hidden = f".t-{rec['op']}-gone"
        _rename(fd, name, fd, hidden)
        _fsync(fd)
        rec["state"] = "published"
        _save(rec)
    except BaseException:
        if rec is not None and rec["state"] == "begun":
            if hidden is not None and _present(fd, hidden) and not _present(fd, name):
                with contextlib.suppress(OSError, AgentFsError):
                    _rename(fd, hidden, fd, name)
            _forget(rec)
        raise
    finally:
        os.close(fd)
    return _finish_or_say(rec)


# --- recovery ---------------------------------------------------------------------------

def _settle(rec: dict) -> str:
    """Finish or roll back one record left open by a transfer that did not
    end (the lock held, so its process is gone). Returns what was done."""
    if rec.get("kind") == "note":
        import notemoves
        return notemoves.settle(rec)
    op, action, frm, to, name = rec["op"], rec["action"], rec["from"], rec["to"], rec["name"]
    stage, hidden = f".t-{op}", f".t-{op}-gone"
    if rec["state"] == "published":
        _finish(rec)
        return "finished"
    if action == "remove":
        fd = _skills_fd(frm)
        try:
            hid = _present(fd, hidden) and not _present(fd, name)
        finally:
            os.close(fd)
        if hid:
            rec["state"] = "published"
            _save(rec)
            _finish(rec)
            return "finished"
        _forget(rec)
        return "rolled back"
    src_fd = _skills_fd(frm)
    try:
        dst_fd = _skills_fd(to)
    except AgentFsError:
        # The destination is gone (its agent trashed since): nothing landed
        # there, and the source must not stay hidden for want of it.
        dst_fd = None
    except BaseException:
        os.close(src_fd)
        raise
    try:
        landed = False
        if dst_fd is not None and not _present(dst_fd, stage) and _present(dst_fd, name):
            try:
                landed = read_item(dst_fd, name)[1] == rec["digest"]
            except (OSError, AgentFsError):
                landed = False
        if landed and (action != "move" or _present(src_fd, hidden) or not _present(src_fd, name)):
            rec["state"] = "published"
            _save(rec)
        else:
            if dst_fd is not None:
                _rmtree(dst_fd, stage)
            if action == "move" and _present(src_fd, hidden):
                if _present(src_fd, name):
                    raise Stuck(f"{name} was hidden in {_label(frm)} by a move that did not "
                                f"finish, and a new {name} is there now; the old one is in "
                                f"skills/{hidden}")
                _rename(src_fd, hidden, src_fd, name)
            if dst_fd is not None:
                _fsync(dst_fd)
            _fsync(src_fd)
    finally:
        os.close(src_fd)
        if dst_fd is not None:
            os.close(dst_fd)
    if rec["state"] == "published":
        _finish(rec)
        return "finished"
    _forget(rec)
    return "rolled back"


def _recover_locked() -> list[dict]:
    with working():
        return _recover_open()


def _recover_open() -> list[dict]:
    out = []
    try:
        d = journal_dir()
    except AgentFsError:
        return out
    for n in _open_names():
        op = n[: -len(OPEN)]
        if os.path.lexists(d / (op + DONE)):
            # Finished; the open copy outlived it by a crash.
            with contextlib.suppress(OSError):
                os.unlink(d / n)
            continue
        rec = _read_record(d / n)
        if rec is None or rec.get("op") != op:
            # Not a record this wrote: never acted on, and set aside so it
            # is not looked at on every poll.
            with contextlib.suppress(OSError):
                os.rename(d / n, d / (n + ".bad"))
            out.append({"op": op, "done": "set aside: not a record this wrote"})
            continue
        try:
            done = _settle(rec)
        except (OSError, AgentFsError) as e:
            rec["state"], rec["problem"] = "stuck", str(e)[:300]
            with contextlib.suppress(OSError, AgentFsError):
                _save(rec)
            done = "stuck"
        out.append({"op": op, "name": rec["name"], "action": rec["action"], "done": done})
    return out


def pending() -> bool:
    """Whether a record is open: cheap (one directory listing), for the
    daemon's poll."""
    return bool(_open_names())


def recover(block: bool = True) -> list[dict] | None:
    """Settle every transfer left unfinished. The daemon calls it when it
    starts, before any agent is built, and on its poll with `block` False,
    when it returns None if a transfer holds the lock (it is not
    interrupted, only under way)."""
    if not pending():
        return []
    try:
        with agentfs._locked(block):
            return _recover_locked()
    except BlockingIOError:
        return None


# --- what the person does ----------------------------------------------------------------

def _audit(rec: dict, kind: str, parts_bytes: int | None = None) -> None:
    """One line: ids, the name, its size; for a Combine (M13) the size of
    the notes it was made of too. Never text."""
    try:
        import audit
        frm, to, name, size = rec["from"], rec["to"], rec["name"], rec["bytes"]
        audit.record(kind, frm="you" if frm == OUTSIDE else frm, to=to, note=name,
                     before=parts_bytes, after=size)
    except Exception:           # noqa: BLE001 -- the move is made; a log never undoes it
        pass


def shadows(name: str, to: str) -> list[str]:
    """Who keeps a skill of its own over this one where it lands: for
    Communal, every agent with its own of that name; for an agent, "communal"
    when Communal has one (which this agent's own now hides)."""
    out = []
    for t in agentfs.targets():
        if t == to or (to != COMMUNAL and t != COMMUNAL):
            continue
        with contextlib.suppress(OSError, AgentFsError):
            agentfs._no_link(agentfs._base(t))
            agentfs._no_link(agentfs._base(t) / "skills")
            if os.path.lexists(agentfs._base(t) / "skills" / name):
                out.append(t)
    return out


def _result(rec: dict) -> dict:
    return {"op": rec["op"], "action": rec["action"], "from": rec["from"], "to": rec["to"],
            "name": rec["name"], "files": rec["files"], "bytes": rec["bytes"],
            "undo_of": rec.get("undo_of", ""),
            "shadows": shadows(rec["name"], rec["to"]) if rec["action"] != "remove" else []}


def _check_targets(frm: str, to: str, name: str) -> None:
    for t in (frm, to):
        if not _target_ok(t):
            raise AgentFsError(f"not an agent id or communal: {t!r}")
    if not agentfs.valid_skill_name(name):
        raise AgentFsError(agentfs.parse_skill(name if isinstance(name, str) else "", "")[1])
    if frm == to:
        raise AgentFsError(f"{name} is in {_label(to)} already")


def move(frm: str, name: str, to: str) -> dict:
    """Move the skill `name` from `frm` to `to` (agent folder ids, or
    communal). Returns what was done, its op id among it."""
    return _do(frm, name, to, "move")


def copy(frm: str, name: str, to: str) -> dict:
    return _do(frm, name, to, "copy")


def _do(frm: str, name: str, to: str, action: str) -> dict:
    _check_targets(frm, to, name)
    with agentfs._locked(), working():
        _recover_locked()
        rec = _transfer_locked(frm, name, to, action)
    _audit(rec, f"skill_{action}")
    return _result(rec)


def record_import(target: str, name: str) -> dict | None:
    """Record a skill just imported into `target` (agentfs.import_skill), so
    it can be undone like a copy. None when it cannot be read back."""
    with agentfs._locked(), working():
        try:
            fd = _skills_fd(target)
        except AgentFsError:
            return None
        try:
            files, digest = read_item(fd, name)
        except (OSError, AgentFsError):
            return None
        finally:
            os.close(fd)
        rec = {"v": 1, "op": _new_op(), "kind": "skill", "action": "import", "from": OUTSIDE,
               "to": target, "name": name, "digest": digest, "files": len(files),
               "bytes": sum(len(d) for _, d, _ in files), "kept": True, "undo_of": "",
               "at": round(time.time(), 3), "state": "done"}
        _save(rec)
        _prune()
    return rec


def undo(op: str) -> dict:
    """Undo the transfer `op`, if neither side changed since (see the top)."""
    return _undo(op, "skill")


def _undo(op: str, kind: str) -> dict:
    """Undo the transfer `op` of `kind` (a skill's here, a note's for
    notemoves.undo), the checks every undo shares made first."""
    if not isinstance(op, str) or not _OP.fullmatch(op):
        raise AgentFsError(f"not a transfer id: {op!r}")
    with agentfs._locked(), working():
        _recover_locked()
        rec = _finished(op)
        if rec is None or rec.get("kind") != kind:
            raise AgentFsError(f"no finished {kind} transfer {op} is recorded")
        if rec.get("undo_of"):
            raise AgentFsError("that was an Undo, which cannot itself be undone; move it again")
        if rec.get("state") == "undone":
            raise AgentFsError("that was undone already")
        if rec.get("state") != "done":
            raise AgentFsError(f"that did not finish ({rec.get('state')}); nothing to undo")
        if kind == "note":
            import notemoves
            new = notemoves.undo_locked(rec)
            _audit(new, "note_undo")
            return notemoves.result(new)
        name = rec["name"]
        if rec["action"] == "move":
            new = _transfer_locked(rec["to"], name, rec["from"], "move", undo_of=op,
                                   expect=rec["digest"])
        elif rec["action"] in ("copy", "import"):
            if rec["action"] == "copy":
                # The original must still be exactly what was copied, or
                # taking the copy back could lose the only one there is.
                fd = _skills_fd(rec["from"])
                try:
                    try:
                        same = read_item(fd, name)[1] == rec["digest"]
                    except (OSError, AgentFsError):
                        same = False
                finally:
                    os.close(fd)
                if not same:
                    raise AgentFsError(f"the original {name} in {_label(rec['from'])} changed or "
                                       "is gone since it was copied; Undo is refused, since it "
                                       "would remove the only copy as it was")
            new = _remove_locked(rec["to"], name, undo_of=op, expect=rec["digest"])
        else:
            raise AgentFsError("that cannot be undone")
    _audit(new, "skill_undo")
    return _result(new)


def history(limit: int = 20, kind: str = "skill") -> list[dict]:
    """The transfers of `kind` recorded, newest first, each with whether
    Undo would be offered for it (not whether it would succeed: that is
    checked then)."""
    try:
        d = journal_dir()
        names = sorted((n for n in os.listdir(d) if n.endswith(DONE) or n.endswith(OPEN)),
                       reverse=True)
    except (OSError, AgentFsError):
        return []
    out, seen = [], set()
    for n in names:
        op = n[: -len(OPEN)] if n.endswith(OPEN) else n[: -len(DONE)]
        if op in seen:
            continue
        seen.add(op)
        rec = _read_record(d / n)
        if rec is None or rec.get("kind") != kind:
            continue
        out.append({k: rec.get(k, "") for k in ("op", "kind", "action", "from", "to", "name", "files",
                                                 "bytes", "state", "undo_of", "undone_by",
                                                 "at", "problem")}
                   | {"undoable": bool(rec.get("state") == "done" and not rec.get("undo_of")
                                       and rec["action"] in ("move", "copy", "import"))})
        if len(out) >= limit:
            break
    return out
