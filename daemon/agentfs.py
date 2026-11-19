"""Agent folders and the communal folder (merged plan, Phase 9).

Each agent has a folder of its own, and every agent shares one communal
folder. This module owns them: where they are, which names may be read or
written in them, how a read survives a bad file, how a write never loses
another, and the saved versions that make a change from outside Settings
visible. Nothing else touches these files directly; the settings pages and
the daemon go through here, the pages by way of the CLI at the bottom.

    ~/.local/share/agentvoice/
      communal/rules.md, defaults.md, skills/<name>/SKILL.md, .history/
      agents/<id>/role.md, personality.md, instructions.md,
                  skills/<name>/SKILL.md, .history/
      agents/.trash/<id>-<ns>/   a removed agent, with its settings.json

`target` is an agent's folder id (`main` for the main agent, whose internal
id is "") or `communal`. `file` is one of a fixed set of names, or
`skills/<name>/SKILL.md`; never a path. An id is never a path either: it is
checked against the same pattern the settings use for agent ids.

**A symlink anywhere under these folders is refused**, wherever it points.
The folders hold what every agent is told on every turn, so a link that
leads out of them (to a file another program writes, or one that does not
exist yet) would let something outside decide what an agent reads. Refusing
all of them is simpler to reason about than judging where each one goes.

**Reading never fails a turn.** A missing file reads as empty. An oversize
one is cut to its budget and the problem published. One that cannot be read
(binary, broken UTF-8, a symlink) keeps the last good text this process saw
and says so; after a restart with no good copy it reads as empty.

**Every write through here is saved** in `.history/<file>/` (newest ten
kept). When a file's content no longer matches its newest saved version it
was changed outside Settings: the change applies -- hand editing is a
feature -- and `read()` reports it, so the page can offer Keep (`ack`) and
Revert. For an agent that runs with no permission hook (Trusted Claude,
Trusted Codex) this visibility is the only thing standing in for
enforcement; see merged-plan.md section 3.5.

    python agentfs.py list|show|create|trash|restore|trash-list|write|
                      history|revert|ack|stamp ...   (see --help)
"""
from __future__ import annotations

import argparse
import codecs
import contextlib
import fcntl
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

import paths  # noqa: E402
from runtime import _AGENT_ID  # noqa: E402

TEMPLATES = Path(__file__).resolve().parent / "templates"

#: The files an agent's folder holds, and each one's budget in characters,
#: counted after cleaning (merged plan, section 3.6).
AGENT_FILES = {"role.md": 300, "personality.md": 1500, "instructions.md": 2000}
COMMUNAL_FILES = {"rules.md": 1500, "defaults.md": 1500}
#: A skill's whole file. Its front matter is checked in Phase 13.
SKILL_MAX = 20_000
_SKILL = re.compile(r"skills/([a-z0-9][a-z0-9-]{0,47})/SKILL\.md")

COMMUNAL = "communal"
MAIN = "main"
HISTORY_KEEP = 10
#: Bytes read from one file. Far past every budget, so an oversize file is
#: still cut at its budget and reported, not refused, while a 2GB file
#: cannot make the idle poll read 2GB.
READ_CAP = 256 * 1024
#: Bytes accepted by one write. The page saves what is in its editor, which
#: may be over budget (the counter says so); this only stops a runaway.
WRITE_CAP = 256 * 1024
SETTINGS_CAP = 64 * 1024

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_LEADING_COMMENT = re.compile(r"\A\s*<!--.*?-->", re.S)
_WHO = re.compile(r"[a-z0-9][a-z0-9-]{0,23}")
_VERSION = re.compile(r"(\d{19})-([a-z0-9][a-z0-9-]{0,23})(?:-\d+)?\.md")
_TRASHED = re.compile(r"([a-z0-9][a-z0-9-]{0,47})-(\d{19})")

#: The last text each file read well, in this process. Held so a file broken
#: by a bad save keeps telling its agent what it said before, rather than
#: silently dropping the communal rules for a turn.
_LAST_GOOD: dict[str, str] = {}


class AgentFsError(Exception):
    """Something the caller asked for that cannot be done, in words that can
    be shown. Never a crash: the CLI prints it and exits 1."""


class Conflict(AgentFsError):
    """The file changed after the caller read it. Carries the current stamp,
    so the page can offer "reload / keep mine" with the right base."""

    def __init__(self, current: str):
        super().__init__("changed since it was read")
        self.current = current


# --- names ------------------------------------------------------------------

def folder_id(persona_id: str) -> str:
    """The folder of an agent known inside the daemon by `persona_id`. The
    main agent's internal id is "", and its folder is `main`; that is the one
    translation, so old chats, grants and the hook are left as they are."""
    return persona_id or MAIN


def _valid_agent(agent_id: str) -> bool:
    # "communal" passes the settings' id pattern, and an existing agent may
    # have it; it is refused a folder here rather than re-keyed there.
    return (isinstance(agent_id, str) and bool(_AGENT_ID.fullmatch(agent_id))
            and agent_id != COMMUNAL)


def _base(target: str) -> Path:
    if target == COMMUNAL:
        return paths.COMMUNAL_DIR
    if not _valid_agent(target):
        raise AgentFsError(f"not an agent id: {target!r}")
    return paths.AGENTS_DIR / target


def _limit(target: str, file: str) -> int:
    """The budget for `file` in `target`, or AgentFsError for a name that is
    not one of the fixed set. This is what keeps `file` from being a path."""
    fixed = COMMUNAL_FILES if target == COMMUNAL else AGENT_FILES
    if file in fixed:
        return fixed[file]
    if isinstance(file, str) and _SKILL.fullmatch(file):
        return SKILL_MAX
    raise AgentFsError(f"not a file this folder holds: {file!r}")


def _no_link(path: Path) -> None:
    """Refuse `path` if it is a symlink (dangling ones included). Missing,
    or under something that is not a directory, is fine: nothing is there.
    Any other failure to look is a refusal, not a crash."""
    try:
        if stat.S_ISLNK(os.lstat(path).st_mode):
            raise AgentFsError(f"{path.name} is a symlink, which is refused here")
    except (FileNotFoundError, NotADirectoryError):
        pass
    except OSError as e:
        raise AgentFsError(f"{path.name} cannot be checked ({e.strerror})") from None


def _resolve(target: str, file: str, create: bool = False) -> tuple[Path, int]:
    """The path of `file` in `target`, with every directory on the way
    checked for symlinks, and made (0700) when `create`."""
    limit = _limit(target, file)
    base = _base(target)
    # From agents/ (or communal/) down. The data folder above them is the
    # user's to arrange, and may itself be a link to another disk.
    chain = [base] if target == COMMUNAL else [paths.AGENTS_DIR, base]
    rel = Path(file)
    for part in rel.parts[:-1]:
        chain.append(chain[-1] / part)
    for d in chain:
        _no_link(d)
        if create:
            paths.private_dir(d)
            _no_link(d)
    path = base / rel
    _no_link(path)
    return path, limit


def _key(target: str, file: str) -> str:
    return f"{target}/{file}"


# --- reading -----------------------------------------------------------------

def clean(text: str) -> str:
    """Text as an agent is told it and a counter counts it: the same rules
    as runtime.instructions_text, plus the starter comment taken off."""
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text.replace("\t", " "))
    while True:
        m = _LEADING_COMMENT.match(text)
        if not m:
            break
        text = text[m.end():]
    return text.strip()


def _read_bytes(path: Path) -> tuple[bytes, bool]:
    """At most READ_CAP bytes of a regular file, and whether there was more.
    Opened without following a symlink."""
    # O_NONBLOCK so a FIFO dropped in place of a file cannot hold the idle
    # poll forever waiting for a writer; it is refused by the type check.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise AgentFsError(f"{path.name} is not a regular file")
        with os.fdopen(fd, "rb", closefd=False) as f:
            data = f.read(READ_CAP + 1)
    finally:
        os.close(fd)
    return data[:READ_CAP], len(data) > READ_CAP


def _decode(data: bytes, more: bool) -> str:
    """UTF-8 or AgentFsError. A file cut at READ_CAP may end inside a
    character; that tail is dropped rather than read as corruption."""
    if b"\x00" in data:
        raise AgentFsError("it holds binary data")
    try:
        if more:
            return codecs.getincrementaldecoder("utf-8")().decode(data, final=False)
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise AgentFsError("it is not UTF-8 text") from None


def _bytes_or_none(path: Path) -> tuple[bytes, bool] | None:
    try:
        return _read_bytes(path)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as e:
        if e.errno == 40:  # ELOOP: O_NOFOLLOW met a symlink
            raise AgentFsError(f"{path.name} is a symlink, which is refused here") from None
        raise AgentFsError(f"{path.name} could not be opened ({e.strerror})") from None


def _raw_text(path: Path) -> str | None:
    """The file's text as written (uncleaned), None when it is missing."""
    got = _bytes_or_none(path)
    return None if got is None else _decode(*got)


def _stamp_of(path: Path) -> str:
    """The revision token a read hands out and a write's `base` is checked
    against: the content's hash and its size, from the bytes, so it is the
    same whether or not the file can be read as text, and two large files
    that share their first READ_CAP bytes still differ. "missing" when
    there is no file."""
    got = _bytes_or_none(path)
    return "missing" if got is None else _stamp_from(got[0], path)


def _stamp_from(data: bytes, path: Path | None = None, size: int | None = None) -> str:
    if size is None:
        try:
            size = os.lstat(path).st_size if path is not None else len(data)
        except OSError:
            size = len(data)
    return f"{hashlib.sha256(data[:READ_CAP]).hexdigest()[:16]}-{size}"


def read_file(target: str, file: str) -> dict:
    """One file as an agent would be told it. Never raises for a bad file:
    the problem is in `problem`, and `text` is what to use."""
    out = {"name": file, "limit": 0, "text": "", "chars": 0, "exists": False,
           "problem": "", "changed_outside": False, "stamp": "missing"}
    out["limit"] = _limit(target, file)
    key = _key(target, file)
    try:
        path, limit = _resolve(target, file)
        got = _bytes_or_none(path)
        if got is not None:
            # From the very bytes the text comes from, so a save between
            # reading and stamping cannot pair this text with that stamp.
            out["stamp"] = _stamp_from(got[0], path)
        raw = None if got is None else _decode(*got)
    except AgentFsError as e:
        good = _LAST_GOOD.get(key)
        out.update(exists=True, text=good or "", chars=len(good or ""),
                   changed_outside=True,
                   problem=f"{file} could not be read: {e}; "
                           + ("using the last good copy" if good is not None
                              else "it is ignored"))
        return out
    if raw is None:
        _LAST_GOOD.pop(key, None)
        newest = _newest_saved(target, file)
        out["changed_outside"] = bool(newest)   # deleted by hand
        return out
    text = clean(raw)
    if len(text) > limit:
        out["problem"] = (f"{file} is longer than {limit} characters; "
                          f"the end is ignored")
        text = text[:limit].rstrip()
    _LAST_GOOD[key] = text
    out.update(exists=True, text=text, chars=len(text),
               changed_outside=raw != _newest_saved(target, file))
    return out


def _skill_files(target: str) -> list[str]:
    base = _base(target) / "skills"
    try:
        _no_link(_base(target))
        _no_link(base)
        names = sorted(e.name for e in os.scandir(base) if e.is_dir(follow_symlinks=False))
    except (OSError, AgentFsError):
        return []
    return [f"skills/{n}/SKILL.md" for n in names
            if _SKILL.fullmatch(f"skills/{n}/SKILL.md")]


def read(target: str) -> dict:
    """Everything in one folder: each file as read_file gives it, the skills
    present, the problems and the files changed outside Settings."""
    base = _base(target)
    fixed = COMMUNAL_FILES if target == COMMUNAL else AGENT_FILES
    files = {}
    for name in [*fixed, *_skill_files(target)]:
        files[name] = read_file(target, name)
    exists = False
    try:
        exists = stat.S_ISDIR(os.lstat(base).st_mode)
    except OSError:
        pass
    return {
        "target": target,
        "exists": exists,
        "path": str(base),
        "files": files,
        "skills": [n.split("/")[1] for n in files if n.startswith("skills/")],
        "problems": [f["problem"] for f in files.values() if f["problem"]],
        "changed_outside": [n for n, f in files.items() if f["changed_outside"]],
    }


def targets() -> list[str]:
    """Every folder present: communal first, then the agents by id."""
    out = []
    try:
        if stat.S_ISDIR(os.lstat(paths.COMMUNAL_DIR).st_mode):
            out.append(COMMUNAL)
    except OSError:
        pass
    try:
        _no_link(paths.AGENTS_DIR)
        out += sorted(e.name for e in os.scandir(paths.AGENTS_DIR)
                      if e.is_dir(follow_symlinks=False) and _valid_agent(e.name))
    except (OSError, AgentFsError):
        pass
    return out


def summary() -> dict:
    """What the daemon publishes and logs: sizes, problems and notices per
    folder. Sizes only, never the text. One folder that cannot be read is
    reported as its problem; it does not take the others with it."""
    out = {}
    for t in targets():
        try:
            r = read(t)
        except (OSError, AgentFsError) as e:
            out[t] = {"files": {}, "problems": [f"{t} cannot be read: {e}"],
                      "changed_outside": []}
            continue
        out[t] = {
            "files": {n: {"chars": f["chars"], "limit": f["limit"],
                          "exists": f["exists"]} for n, f in r["files"].items()},
            "problems": r["problems"],
            "changed_outside": r["changed_outside"],
        }
    return out


def stamp() -> tuple:
    """Every tracked file's and history folder's (path, mtime, size, inode),
    for the daemon to notice a hand edit without reading any text."""
    seen = []
    for t in targets():
        base = _base(t)
        fixed = COMMUNAL_FILES if t == COMMUNAL else AGENT_FILES
        for name in [*fixed, *_skill_files(t)]:
            for p in (base / name, base / ".history" / name):
                try:
                    st = os.lstat(p)
                    seen.append((str(p), st.st_mtime_ns, st.st_size, st.st_ino))
                except OSError:
                    seen.append((str(p), 0, -1, 0))
    return tuple(seen)


def file_stamp(target: str, file: str) -> str:
    """The stamp a write's `base` is compared with (see _stamp_of)."""
    path, _ = _resolve(target, file)
    return _stamp_of(path)


# --- writing -----------------------------------------------------------------

@contextlib.contextmanager
def _locked():
    """One lock for every folder, the pattern chats.py uses: writes are
    rare and small, and one lock cannot be taken in the wrong order."""
    paths.private_dir(paths.DATA_DIR)
    try:
        fd = os.open(paths.DATA_DIR / ".agentfs.lock",
                     os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW
                     | os.O_NONBLOCK, 0o600)
    except OSError as e:
        raise AgentFsError(f"the lock file cannot be opened ({e.strerror})") from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise AgentFsError("the lock file is not a regular file")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _atomic_write(path: Path, data: bytes) -> None:
    """Into place by rename, so a reader never sees half a file; fsynced, so
    a crash leaves the old file or the new one."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                 | os.O_CLOEXEC, 0o600)
    try:
        try:
            with os.fdopen(fd, "wb", closefd=False) as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    # The rename itself, made durable: without it a crash can lose a save
    # the caller was told succeeded.
    with contextlib.suppress(OSError):
        dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)


def _history_dir(target: str, file: str, create: bool = False) -> Path:
    _limit(target, file)                 # a name from the fixed set, never a path
    base = _base(target)
    d = base / ".history" / file
    chain = ([] if target == COMMUNAL else [paths.AGENTS_DIR]) + [base, base / ".history"]
    for part in Path(file).parts:
        chain.append(chain[-1] / part)
    for c in chain:
        _no_link(c)
        if create:
            paths.private_dir(c)
    return d


def _versions(target: str, file: str) -> list[Path]:
    """Saved versions, newest first."""
    try:
        d = _history_dir(target, file)
        found = [Path(e.path) for e in os.scandir(d)
                 if e.is_file(follow_symlinks=False) and _VERSION.fullmatch(e.name)]
    except (OSError, AgentFsError):
        return []
    return sorted(found, key=lambda p: p.name, reverse=True)


def _newest_saved(target: str, file: str) -> str | None:
    for v in _versions(target, file):
        try:
            return _decode(*_read_bytes(v))
        except (OSError, AgentFsError):
            continue
    return None


def _save_version(target: str, file: str, text: str, who: str) -> Path:
    """Save `text` as the newest version and return its path. Pruning is
    left to _prune, after the live file is in place, so a failed save can
    take its version back out without having lost an older one."""
    d = _history_dir(target, file, create=True)
    name = f"{time.time_ns():019d}-{who}.md"
    n = 1
    while os.path.lexists(d / name):
        name = f"{time.time_ns():019d}-{who}-{n}.md"
        n += 1
    _atomic_write(d / name, text.encode("utf-8"))
    return d / name


def _prune(target: str, file: str) -> None:
    for old in _versions(target, file)[HISTORY_KEEP:]:
        with contextlib.suppress(OSError):
            old.unlink()


def write(target: str, file: str, text: str, base: str | None = None,
          who: str = "settings") -> str:
    """Write `file` in `target` and save the version. Returns the new stamp.

    With `base`, the write happens only if the file still has that stamp;
    otherwise Conflict, carrying the current one. Without it the last write
    wins, and the one it replaced is still in the history."""
    with _locked():
        return _write_locked(target, file, text, base, who)


def _write_locked(target: str, file: str, text: str, base: str | None,
                  who: str) -> str:
    """write(), with the lock already held.

    The version is saved first and the live file second; if the live write
    fails, the version is taken back out. Either both change or neither
    does, so a failed save never shows as "changed outside Settings"."""
    if not isinstance(text, str):
        raise AgentFsError("text must be a string")
    if "\x00" in text:
        raise AgentFsError("text holds a NUL character")
    data = text.encode("utf-8")
    if len(data) > WRITE_CAP:
        raise AgentFsError(f"{file} is larger than {WRITE_CAP // 1024} KB")
    if not _WHO.fullmatch(who):
        raise AgentFsError(f"not a name for who wrote it: {who!r}")
    path, _ = _resolve(target, file, create=True)
    current = _stamp_of(path)
    if base is not None and base != current:
        raise Conflict(current)
    version = _save_version(target, file, text, who)
    try:
        _atomic_write(path, data)
    except BaseException:
        with contextlib.suppress(OSError):
            version.unlink()
        raise
    _prune(target, file)
    return _stamp_from(data, size=len(data))


def history(target: str, file: str) -> list[dict]:
    _limit(target, file)       # raised here: _versions() swallows errors
    out = []
    for v in _versions(target, file):
        m = _VERSION.fullmatch(v.name)
        try:
            chars = len(clean(_decode(*_read_bytes(v))))
        except (OSError, AgentFsError):
            chars = -1
        out.append({"version": v.name, "at": int(m.group(1)) / 1e9,
                    "who": m.group(2), "chars": chars})
    return out


def revert(target: str, file: str, version: str | None = None,
           base: str | None = None) -> str:
    """Put a saved version back (the newest when none is named): the undo
    for a change made outside Settings. Returns the new stamp."""
    _limit(target, file)
    if version is not None and not _VERSION.fullmatch(version or ""):
        raise AgentFsError(f"not a version: {version!r}")
    # Chosen under the lock, so a save or a prune between choosing and
    # writing cannot change what "the newest" means.
    with _locked():
        versions = _versions(target, file)
        if version is None:
            if not versions:
                raise AgentFsError(f"{file} has no saved version to go back to")
            chosen = versions[0]
        else:
            chosen = next((v for v in versions if v.name == version), None)
            if chosen is None:
                raise AgentFsError(f"{file} has no version {version}")
        try:
            text = _decode(*_read_bytes(chosen))
        except OSError as e:
            raise AgentFsError(f"that version cannot be read ({e.strerror})") from None
        # With `base`, only if the file is still what the person looked at
        # when they chose Revert.
        return _write_locked(target, file, text, base, "revert")


def ack(target: str, file: str, base: str | None = None) -> None:
    """Keep a change made outside Settings: save what is there now as the
    newest version, so it no longer reads as changed outside. With `base`,
    only if the file is still the one the person was shown; keeping a
    deletion saves an empty version."""
    with _locked():
        path, _ = _resolve(target, file)
        if base is not None and _stamp_of(path) != base:
            raise Conflict(_stamp_of(path))
        raw = _raw_text(path)
        _save_version(target, file, raw or "", "you")
        _prune(target, file)


# --- folders -----------------------------------------------------------------

def _templates(kind: str) -> dict[str, str]:
    d = TEMPLATES / kind
    names = AGENT_FILES if kind == "agent" else COMMUNAL_FILES
    out = {}
    for name in names:
        try:
            out[name] = (d / name).read_text(encoding="utf-8")
        except OSError:
            out[name] = ""
    return out


def create(agent_id: str) -> list[str]:
    """A new agent's folder from the template. Refused when it exists."""
    if agent_id == COMMUNAL:
        raise AgentFsError("an agent whose id is 'communal' cannot have a folder: "
                           "that name is the shared folder's; give it another id")
    base = _base(agent_id)
    made = []
    with _locked():
        _no_link(paths.AGENTS_DIR)
        if os.path.lexists(base):
            raise AgentFsError(f"a folder for {agent_id} already exists")
        for name, text in _templates("agent").items():
            _write_locked(agent_id, name, text, None, "template")
            made.append(name)
    return made


def ensure_communal() -> list[str]:
    """The communal folder's files from the template, each only if missing.
    Safe to call on every start (Phase 10 does)."""
    made = []
    with _locked():
        for name, text in _templates("communal").items():
            path, _ = _resolve(COMMUNAL, name)
            if not os.path.lexists(path):
                _write_locked(COMMUNAL, name, text, "missing", "template")
                made.append(name)
    return made


def _trash_dir(create: bool = False) -> Path:
    """agents/.trash, checked for links before anything is made or chmod'd
    through it."""
    _no_link(paths.AGENTS_DIR)
    if create:
        paths.private_dir(paths.AGENTS_DIR)
        _no_link(paths.AGENTS_DIR)
    d = paths.AGENTS_DIR / ".trash"
    _no_link(d)
    if create:
        paths.private_dir(d)
    return d


def _sidecar(tdir: Path, name: str) -> Path:
    """Where a trashed agent's settings entry is kept: beside its folder,
    never inside it, so nothing the folder held is overwritten."""
    return tdir / f"{name}.settings.json"


def trash(agent_id: str, settings_json: str) -> str:
    """Move an agent's folder to the trash with its settings entry beside
    it, so `restore` can put the agent back whole. Returns the trash name.
    Works with no folder too: the settings entry alone is worth keeping.

    The entry is written first and the folder moved second; if the move
    fails the entry is taken back out, so the trash never holds half."""
    if not _valid_agent(agent_id) or agent_id == MAIN:
        raise AgentFsError(f"{agent_id!r} cannot be moved to the trash")
    if len(settings_json.encode("utf-8")) > SETTINGS_CAP:
        raise AgentFsError("the settings entry is too large")
    try:
        entry = json.loads(settings_json) if settings_json.strip() else {}
    except ValueError:
        raise AgentFsError("the settings entry is not JSON") from None
    if not isinstance(entry, dict):
        raise AgentFsError("the settings entry must be a JSON object")
    with _locked():
        tdir = _trash_dir(create=True)
        name = f"{agent_id}-{time.time_ns():019d}"
        dest = tdir / name
        side = _sidecar(tdir, name)
        if os.path.lexists(dest) or os.path.lexists(side):
            raise AgentFsError("a trash entry with that name exists; try again")
        src = _base(agent_id)
        _no_link(src)
        _atomic_write(side, json.dumps(entry, ensure_ascii=False).encode("utf-8"))
        try:
            if os.path.lexists(src):
                os.rename(src, dest)
            else:
                paths.private_dir(dest)
        except BaseException:
            with contextlib.suppress(OSError):
                side.unlink()
            raise
    return name


def restore(name: str) -> dict:
    """Put a trashed agent's folder back and return its settings entry.

    An entry whose settings cannot be read is left in the trash, untouched,
    rather than restored as an agent with no settings: try again after
    fixing the file, or remove it by hand."""
    m = _TRASHED.fullmatch(name or "")
    if not m or not _valid_agent(m.group(1)):
        raise AgentFsError(f"not a trash entry: {name!r}")
    agent_id = m.group(1)
    with _locked():
        tdir = _trash_dir()
        src = tdir / name
        _no_link(src)
        if not os.path.isdir(src):
            raise AgentFsError(f"nothing in the trash called {name}")
        dest = _base(agent_id)
        _no_link(paths.AGENTS_DIR)
        if os.path.lexists(dest):
            raise AgentFsError(f"an agent folder {agent_id} exists already")
        side = _sidecar(tdir, name)
        try:
            entry = json.loads(_decode(*_read_bytes(side)))
        except (OSError, ValueError, AgentFsError):
            raise AgentFsError(f"the settings saved with {name} cannot be read; "
                               f"it is left in the trash") from None
        if not isinstance(entry, dict):
            raise AgentFsError(f"the settings saved with {name} are not an object; "
                               f"it is left in the trash")
        os.rename(src, dest)
        with contextlib.suppress(OSError):
            side.unlink()
    return entry


def trash_list() -> list[dict]:
    out = []
    try:
        d = _trash_dir()
        entries = [e for e in os.scandir(d) if e.is_dir(follow_symlinks=False)]
    except (OSError, AgentFsError):
        return []
    for e in entries:
        m = _TRASHED.fullmatch(e.name)
        if not m:
            continue
        label, problem = "", ""
        try:
            entry = json.loads(_decode(*_read_bytes(_sidecar(d, e.name))))
            if isinstance(entry, dict):
                label = str(entry.get("label") or entry.get("name") or "")[:64]
        except (OSError, ValueError, AgentFsError):
            problem = "its settings cannot be read"
        out.append({"name": e.name, "id": m.group(1),
                    "at": int(m.group(2)) / 1e9, "label": label,
                    "problem": problem})
    return sorted(out, key=lambda t: t["at"], reverse=True)


# --- CLI ---------------------------------------------------------------------

def _print(obj, as_json: bool, text: str) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1) if as_json else text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agentvoice agents",
                                 description="Agent folders and the communal folder.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="every folder, with sizes and problems")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("show", help="one folder, text included")
    p.add_argument("target")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("create", help="a new agent's folder from the template")
    p.add_argument("id")
    p = sub.add_parser("trash", help="move to the trash; settings entry on stdin")
    p.add_argument("id")
    p = sub.add_parser("restore", help="put back from the trash; prints its settings entry")
    p.add_argument("name")
    p = sub.add_parser("trash-list")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("write", help="text on stdin, never as an argument")
    p.add_argument("target")
    p.add_argument("file")
    p.add_argument("--base", help="only if the file still has this stamp")
    p = sub.add_parser("history")
    p.add_argument("target")
    p.add_argument("file")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("revert", help="the newest saved version, or VERSION")
    p.add_argument("target")
    p.add_argument("file")
    p.add_argument("version", nargs="?")
    p.add_argument("--base", help="only if the file still has this stamp")
    p = sub.add_parser("ack", help="keep a change made outside Settings")
    p.add_argument("target")
    p.add_argument("file")
    p.add_argument("--base", help="only if the file still has this stamp")
    sub.add_parser("ensure-communal")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "list":
            s = summary()
            lines = []
            for t, v in s.items():
                sizes = " · ".join(f"{n} {f['chars']}/{f['limit']}"
                                   for n, f in v["files"].items())
                extra = (f"  [changed outside: {', '.join(v['changed_outside'])}]"
                         if v["changed_outside"] else "")
                lines.append(f"{t}: {sizes}{extra}")
                lines += [f"  ! {pr}" for pr in v["problems"]]
            _print(s, a.json, "\n".join(lines) or "no agent folders yet")
        elif a.cmd == "show":
            r = read(a.target)
            text = "\n\n".join(f"== {n} ({f['chars']}/{f['limit']})\n{f['text']}"
                               for n, f in r["files"].items())
            _print(r, a.json, text)
        elif a.cmd == "create":
            print("\n".join(create(a.id)))
        elif a.cmd == "trash":
            print(trash(a.id, sys.stdin.read(SETTINGS_CAP + 1)))
        elif a.cmd == "restore":
            print(json.dumps(restore(a.name), ensure_ascii=False))
        elif a.cmd == "trash-list":
            t = trash_list()
            _print(t, a.json, "\n".join(f"{e['name']}  {e['label']}" for e in t)
                   or "the trash is empty")
        elif a.cmd == "write":
            data = sys.stdin.buffer.read(WRITE_CAP + 1)
            if len(data) > WRITE_CAP:
                raise AgentFsError(f"{a.file} is larger than {WRITE_CAP // 1024} KB")
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                raise AgentFsError("the text is not UTF-8") from None
            print(write(a.target, a.file, text, base=a.base))
        elif a.cmd == "history":
            h = history(a.target, a.file)
            _print(h, a.json, "\n".join(
                f"{v['version']}  {v['who']}  {v['chars']} chars" for v in h)
                or "no saved versions")
        elif a.cmd == "revert":
            print(revert(a.target, a.file, a.version, base=a.base))
        elif a.cmd == "ack":
            ack(a.target, a.file, base=a.base)
        elif a.cmd == "ensure-communal":
            print("\n".join(ensure_communal()))
    except Conflict as e:
        print(f"conflict: {a.file} changed since it was read; current stamp {e.current}",
              file=sys.stderr)
        return 3
    except AgentFsError as e:
        print(f"agentvoice agents: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
