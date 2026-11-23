"""Importing rules, defaults and skills into Communal from a folder, and
undoing it (master plan, phase M15).

    agentvoice agents import communal DIR [--json]        # a dry run: changes nothing
    agentvoice agents import communal DIR --confirm TOKEN # commits exactly that
    agentvoice agents import-undo OP
    agentvoice agents import-history [--json]

DIR is laid out as `agentvoice agents export communal` writes it: `rules.md`,
`defaults.md` and `skills/<name>/...`. Anything else in it is listed as
ignored and never read.

**Only the person imports.** No agent tool does, and an agent running these
commands is asked at every level (the orders guard's FOLDER_WORDS): an
import changes what every agent that takes Communal is told.

**A dry run first** (`plan`): every file it would write, a diff for each text,
each skill new or the same, the agents it reaches (those that take Communal:
`communalOff`), the agents whose own skill of that name hides one, and every
problem. A problem refuses the whole import -- a link anywhere (the folder
itself, a file, inside a skill, dangling or not), a special file, a rules or
defaults file over its budget, a skill over the bounds every skill keeps or
with a problem of its own, a reserved name, more than MAX_SKILLS skills, and
a skill whose name Communal already has with different contents (a clash:
nothing is replaced). The dry run ends in a token: a digest over what was
read and over the Communal files it would replace, so `--confirm TOKEN`
commits exactly what was listed, or nothing when either side moved since.

**One commit, all or nothing, through M12's journal** (transfer.py: its lock,
its records, its recovery). Under the one lock: unfinished transfers settled;
the folder read again and the token checked; a record (`kind: "import"`)
with the old and new text of each file kept beside it in
`agents/.transfers/<op>.d/` (inside the folder the orders guard covers);
each skill staged as `communal/skills/.t-<op>-a-<name>`; then published --
each skill by a no-replace rename, each text with a saved version named for
the operation; then `published`, and the record finished. A record that
never reached `published` is rolled back by recovery, before any adapter is
shown either side: staged and published skills taken out (only while they
hash as imported), each text put back while it still holds the imported
bytes. One that did is finished. A text changed by hand in between is never
overwritten: the record is then `stuck`, and says why.

**Undo is tied to the exact revision.** An import is undone only while every
skill it added hashes the same and every text holds the bytes it wrote; the
undo is itself one recorded operation of the same kind (each added skill
hidden then removed, each text put back), and cannot be undone. The audit
log gets one line per import or undo -- the operation's id and its size --
and one `skill_import` line per skill, its name and size. Never text.
"""
from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import os
import re
import stat
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agentfs  # noqa: E402
import transfer  # noqa: E402
from agentfs import COMMUNAL, AgentFsError  # noqa: E402

#: The texts an import may carry: the communal folder's own files.
TEXTS = tuple(agentfs.COMMUNAL_FILES)
#: Skills in one import at most (each is a few hundred bytes of its record).
MAX_SKILLS = 20
#: Entries looked at in the folder before it is refused as not an export.
MAX_ENTRIES = 200
_SHA = re.compile(r"[0-9a-f]{64}")
_TOKEN = re.compile(r"[0-9a-f]{32}")
ACTIONS = ("import", "undo")
STATES = ("begun", "published", "done", "undone", "stuck")
_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _sha(data: bytes | None) -> str:
    return "" if data is None else hashlib.sha256(data).hexdigest()


# --- reading the folder ----------------------------------------------------------

def _read_file(dir_fd: int, name: str) -> bytes:
    """One file under `dir_fd`, no link followed, at most READ_CAP bytes."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     dir_fd=dir_fd)
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise AgentFsError(f"{name} is a link, which is refused here") from None
        raise AgentFsError(f"{name} cannot be read ({e.strerror})") from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise AgentFsError(f"{name} is not a plain file")
        with os.fdopen(fd, "rb", closefd=False) as f:
            data = f.read(agentfs.READ_CAP + 1)
    finally:
        os.close(fd)
    if len(data) > agentfs.READ_CAP:
        raise AgentFsError(f"{name} is larger than {agentfs.READ_CAP // 1024} KB")
    return data


def _text_problem(name: str, data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return f"{name} is not UTF-8 text"
    if "\x00" in text:
        return f"{name} holds a NUL character"
    limit = agentfs.COMMUNAL_FILES[name]
    if len(agentfs.clean(text)) > limit:
        return (f"{name} is longer than {limit} characters, which every agent would be "
                "told only the start of; shorten it first")
    return ""


def read_source(path: str) -> dict:
    """Everything an import of `path` would bring: {"texts": {name: bytes},
    "skills": {name: (files, digest)}, "ignored": [...], "problems": [...]}.
    Reads only, one folder at a time with no link followed at any level."""
    out = {"texts": {}, "skills": {}, "ignored": [], "problems": []}
    root = Path(str(path)).expanduser()
    try:
        fd = os.open(root, _DIR)
    except OSError as e:
        if e.errno in (errno.ELOOP, errno.ENOTDIR):
            out["problems"].append(f"{root} is a link or not a folder, which is refused here")
        else:
            out["problems"].append(f"{root} cannot be opened ({e.strerror})")
        return out
    try:
        try:
            entries = sorted(os.listdir(fd))
        except OSError as e:
            out["problems"].append(f"{root} cannot be listed ({e.strerror})")
            return out
        if len(entries) > MAX_ENTRIES:
            out["problems"].append(f"{root} holds more than {MAX_ENTRIES} entries; "
                                   "it does not look like an export")
            return out
        for name in entries:
            try:
                st = os.stat(name, dir_fd=fd, follow_symlinks=False)
            except OSError as e:
                out["problems"].append(f"{name} cannot be read ({e.strerror})")
                continue
            if name in TEXTS:
                try:                    # O_NOFOLLOW: a link, dangling or not, is refused
                    data = _read_file(fd, name)
                except AgentFsError as e:
                    out["problems"].append(str(e))
                    continue
                why = _text_problem(name, data)
                if why:
                    out["problems"].append(why)
                else:
                    out["texts"][name] = data
            elif name == "skills":
                if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                    out["problems"].append("skills is a link or not a folder, which is refused here")
                    continue
                _read_skills(fd, out)
            else:
                out["ignored"].append(name + ("/" if stat.S_ISDIR(st.st_mode) else ""))
    finally:
        os.close(fd)
    if len(out["skills"]) > MAX_SKILLS:
        out["problems"].append(f"more than {MAX_SKILLS} skills in one import; "
                               "import them in parts")
    return out


def _read_skills(parent: int, out: dict) -> None:
    try:
        sfd = os.open("skills", _DIR, dir_fd=parent)
    except OSError as e:
        out["problems"].append(f"skills cannot be opened ({e.strerror})")
        return
    try:
        names = sorted(os.listdir(sfd))
        if len(names) > MAX_ENTRIES:
            out["problems"].append(f"skills holds more than {MAX_ENTRIES} entries")
            return
        for name in names:
            if name.startswith("."):
                out["ignored"].append(f"skills/{name}")
                continue
            if not agentfs.valid_skill_name(name):
                out["problems"].append(f"skills/{name}: {agentfs.parse_skill(name, '')[1]}")
                continue
            try:                        # parse_skill refuses a reserved name too
                files, digest = transfer.read_item(sfd, name)
                transfer.skill_text(name, files)
            except FileNotFoundError:
                out["problems"].append(f"skills/{name} went away while it was read")
                continue
            except AgentFsError as e:
                out["problems"].append(f"skills/{name}: {e}")
                continue
            out["skills"][name] = (files, digest)
    except OSError as e:
        out["problems"].append(f"skills cannot be read ({e.strerror})")
    finally:
        os.close(sfd)


# --- what Communal has now --------------------------------------------------------

def _communal_text(name: str) -> bytes | None:
    """The communal file's bytes now, None when it is not there."""
    path, _ = agentfs._resolve(COMMUNAL, name)
    got = agentfs._bytes_or_none(path)
    if got is None:
        return None
    if got[1]:
        raise AgentFsError(f"communal {name} is larger than {agentfs.READ_CAP // 1024} KB, "
                           "so it cannot be kept to put back; shorten it first")
    return got[0]


def _communal_skills_dir() -> int | None:
    """Communal's skills folder opened with no link followed, or None when
    there is none yet. Never made here: a dry run writes nothing."""
    try:
        agentfs._no_link(paths_communal())
        agentfs._no_link(paths_communal() / "skills")
    except AgentFsError:
        raise AgentFsError("the communal folder or its skills folder is a link, "
                           "which is refused here") from None
    try:
        return os.open(paths_communal() / "skills", _DIR)
    except FileNotFoundError:
        return None
    except OSError as e:
        raise AgentFsError(f"the communal skills folder cannot be opened ({e.strerror})") from None


def paths_communal() -> Path:
    import paths
    return paths.COMMUNAL_DIR


def _existing(names) -> dict[str, str]:
    """For each of `names` Communal has: its digest ("?" when it cannot be
    read, which counts as different)."""
    out = {}
    fd = _communal_skills_dir()
    if fd is None:
        return out
    try:
        for n in names:
            try:
                out[n] = transfer.read_item(fd, n)[1]
            except FileNotFoundError:
                continue
            except (OSError, AgentFsError):
                out[n] = "?"
    finally:
        os.close(fd)
    return out


# --- the dry run --------------------------------------------------------------------

def _agents(cfg) -> list[dict]:
    phrase = " ".join(cfg.get_str("phrase").lower().split())
    out = [{"id": agentfs.MAIN, "label": cfg.main_label(phrase), "enabled": True}]
    out += [{"id": a["id"], "label": a["label"], "enabled": a.get("enabled", True)}
            for a in cfg.all_agents()]
    for a in out:
        a["takes"] = cfg.takes_communal(a["id"])
    return out


def plan(path: str, cfg) -> dict:
    """The dry run: what importing `path` would do, and the token that
    commits exactly that. Writes nothing anywhere."""
    return _plan(path, cfg)[0]


def _plan(path: str, cfg) -> tuple[dict, dict]:
    """plan(), and the very bytes it was made from: commit() stages those,
    so the token it checked and what it writes come from one read."""
    src = read_source(path)
    problems = list(src["problems"])
    texts, skills, files = [], [], []
    current: dict[str, str] = {}
    for name in TEXTS:
        if name not in src["texts"]:
            continue
        new = src["texts"][name]
        try:
            old = _communal_text(name)
        except AgentFsError as e:
            problems.append(str(e))
            continue
        current[name] = _sha(old)
        same = old == new
        old_text = "" if old is None else old.decode("utf-8", "replace")
        new_text = new.decode("utf-8")
        texts.append({"file": name, "change": "same" if same else "new" if old is None else "replace",
                      "chars": len(agentfs.clean(new_text)), "limit": agentfs.COMMUNAL_FILES[name],
                      "diff": [] if same else agentfs.diff_lines(
                          old_text, new_text, f"communal/{name} now", f"{name} imported")})
        if not same:
            files.append(name)
    try:
        have = _existing(src["skills"])
    except AgentFsError as e:
        problems.append(str(e))
        have = {}
    owners = {}
    for t in agentfs.targets():
        if t == COMMUNAL:
            continue
        for s in agentfs.skills(t):
            owners.setdefault(s["name"], []).append(t)
    labels = {a["id"]: a["label"] for a in _agents(cfg)}
    for name, (fs, digest) in sorted(src["skills"].items()):
        there = have.get(name)
        change = "new" if there is None else "same" if there == digest else "clash"
        if change == "clash":
            problems.append(f"Communal already has a skill named {name}, with other contents; "
                            "rename or remove one of them first (nothing is replaced)")
        text = next(d for rel, d, _ in fs if rel == "SKILL.md").decode("utf-8")
        desc, _ = agentfs.parse_skill(name, text)
        skills.append({"name": name, "change": change, "files": len(fs),
                       "bytes": sum(len(d) for _, d, _ in fs), "description": desc,
                       "hidden_for": [labels.get(t, t) for t in owners.get(name, [])]})
        if change == "new":
            files += [f"skills/{name}/{rel}" for rel, _, _ in fs]
    agents = _agents(cfg)
    token_src = {"texts": {n: _sha(d) for n, d in src["texts"].items()},
                 "skills": {n: d for n, (_, d) in src["skills"].items()},
                 "current": current, "have": have, "problems": problems}
    token = hashlib.sha256(json.dumps(token_src, sort_keys=True).encode()).hexdigest()[:32]
    return {"dir": str(Path(str(path)).expanduser()), "token": token, "problems": problems,
            "ignored": src["ignored"], "texts": texts, "skills": skills, "files": files,
            "changes": len([t for t in texts if t["change"] != "same"])
                       + len([s for s in skills if s["change"] == "new"]),
            "agents": [{"id": a["id"], "label": a["label"], "takes": a["takes"],
                        "enabled": a["enabled"]} for a in agents],
            "reaches": [a["label"] for a in agents if a["takes"] and a["enabled"]]}, src


# --- the journal's side folder ------------------------------------------------------

def side_dir(op: str, create: bool = False) -> Path:
    """agents/.transfers/<op>.d: the old and new bytes of each text an
    operation changes, kept for recovery and for Undo."""
    d = transfer.journal_dir(create=create) / f"{op}.d"
    agentfs._no_link(d)
    if create:
        import paths
        paths.private_dir(d)
        agentfs._no_link(d)
    return d


def _side_read(op: str, name: str) -> bytes | None:
    path = side_dir(op) / name
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as e:
        raise AgentFsError(f"the copy kept for {name} cannot be read ({e.strerror})") from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise AgentFsError(f"the copy kept for {name} is not a plain file")
        data = os.read(fd, agentfs.READ_CAP + 1)
    finally:
        os.close(fd)
    return data


def _side_text(op: str, which: str, entry: dict) -> bytes | None:
    """The old or new bytes of a text step, checked against the record's
    digest: None for "absent"; AgentFsError when the copy does not match."""
    want = entry[which]
    if want == "":
        return None
    data = _side_read(op, f"{which}-{entry['file']}")
    if data is None or _sha(data) != want:
        raise AgentFsError(f"the copy kept of {entry['file']} is missing or changed")
    return data


def _prune_sides() -> None:
    """Side folders whose record has gone (transfer._prune keeps 100)."""
    import shutil
    try:
        d = transfer.journal_dir()
        names = os.listdir(d)
    except (OSError, AgentFsError):
        return
    have = {n[: -len(transfer.OPEN)] if n.endswith(transfer.OPEN) else n[: -len(transfer.DONE)]
            for n in names if n.endswith(transfer.DONE)}     # OPEN ends in DONE too
    for n in names:
        if n.endswith(".d") and n[:-2] not in have and not os.path.islink(d / n):
            shutil.rmtree(d / n, ignore_errors=True)


# --- records ----------------------------------------------------------------------------

def valid(rec) -> bool:
    """A record this module wrote, in its shape (transfer._valid hands
    `kind: "import"` here): anything else is never acted on."""
    if not isinstance(rec, dict) or rec.get("kind") != "import":
        return False
    if rec.get("action") not in ACTIONS or rec.get("state") not in STATES:
        return False
    if not isinstance(rec.get("op"), str) or not transfer._OP.fullmatch(rec["op"]):
        return False
    undo_of = rec.get("undo_of", "")
    if not isinstance(undo_of, str):
        return False
    if (rec["action"] == "undo") != bool(undo_of) or (undo_of and not transfer._OP.fullmatch(undo_of)):
        return False
    skills, texts = rec.get("skills"), rec.get("texts")
    if not isinstance(skills, list) or not isinstance(texts, list) or len(skills) > MAX_SKILLS:
        return False
    seen = set()
    for s in skills:
        if not isinstance(s, dict) or not agentfs.valid_skill_name(s.get("name")) \
                or s["name"] in seen or not isinstance(s.get("digest"), str) \
                or not _SHA.fullmatch(s["digest"]) or not isinstance(s.get("add"), bool):
            return False
        seen.add(s["name"])
    files = set()
    for t in texts:
        if not isinstance(t, dict) or t.get("file") not in TEXTS or t["file"] in files:
            return False
        for k in ("old", "new"):
            if not isinstance(t.get(k), str) or (t[k] and not _SHA.fullmatch(t[k])):
                return False
        files.add(t["file"])
    return rec.get("name") == "communal" and rec.get("from") == transfer.OUTSIDE \
        and rec.get("to") == COMMUNAL


def _version_name(op: str, who: str) -> str:
    return f"{op[:19]}-{who}.md"


def _who(rec: dict) -> str:
    return "import" if rec["action"] == "import" else "undo"


def _stage(rec: dict, name: str) -> str:
    return f".t-{rec['op']}-a-{name}"


def _hidden(rec: dict, name: str) -> str:
    return f".t-{rec['op']}-r-{name}"


def _live(name: str) -> bytes | None:
    path, _ = agentfs._resolve(COMMUNAL, name, create=False)
    got = agentfs._bytes_or_none(path)
    return None if got is None else got[0]


def _set_text(rec: dict, entry: dict, data: bytes | None) -> None:
    """Put `data` (None: no file) in place of the communal text, with a
    saved version named for the operation so it never reads as changed
    outside Settings (an absent file: an empty version, as Keep saves)."""
    path, _ = agentfs._resolve(COMMUNAL, entry["file"], create=True)
    hist = agentfs._history_dir(COMMUNAL, entry["file"], create=True)
    version = hist / _version_name(rec["op"], _who(rec))
    agentfs._atomic_write(version, data or b"")
    if data is None:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(path)
    else:
        agentfs._atomic_write(path, data)


def _unset_text(rec: dict, entry: dict, old: bytes | None) -> None:
    """Put the text back as it was before the operation, and take its
    version out again: the history reads as if it never happened."""
    path, _ = agentfs._resolve(COMMUNAL, entry["file"], create=True)
    if old is None:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(path)
    else:
        agentfs._atomic_write(path, old)
    with contextlib.suppress(OSError, AgentFsError):
        os.unlink(agentfs._history_dir(COMMUNAL, entry["file"]) / _version_name(rec["op"], _who(rec)))


def _apply_locked(rec: dict, staged: dict[str, list] | None = None) -> None:
    """Carry out a `begun` record: stage what it adds, check every text is
    still as the record says it was, publish, and record `published`.
    Anything raised before that is rolled back by the caller."""
    import paths
    agentfs._no_link(paths.COMMUNAL_DIR)
    paths.private_dir(paths.COMMUNAL_DIR)
    fd = agentfs._open_skills_dir(COMMUNAL)
    try:
        for s in rec["skills"]:
            if not s["add"]:
                continue
            files = (staged or {}).get(s["name"])
            if files is None:
                raise AgentFsError(f"{s['name']} has nothing staged")
            stage = _stage(rec, s["name"])
            os.mkdir(stage, 0o700, dir_fd=fd)
            sfd = os.open(stage, _DIR, dir_fd=fd)
            try:
                for rel, data, mode in files:
                    agentfs._write_beneath(sfd, rel, data, mode)
                transfer._fsync(sfd)
            finally:
                os.close(sfd)
            if transfer.read_item(fd, stage)[1] != s["digest"]:
                raise AgentFsError(f"{s['name']} did not stage as it was read")
        for t in rec["texts"]:
            if _sha(_live(t["file"])) != t["old"]:
                raise AgentFsError(f"communal {t['file']} changed meanwhile; nothing was changed")
        for s in rec["skills"]:
            if s["add"]:
                transfer._rename(fd, _stage(rec, s["name"]), fd, s["name"])
            else:
                try:
                    same = transfer.read_item(fd, s["name"])[1] == s["digest"]
                except FileNotFoundError:
                    same = False
                if not same:
                    raise AgentFsError(f"{s['name']} in Communal changed or is gone since it was "
                                       "imported; Undo is refused so the change is not lost")
                transfer._rename(fd, s["name"], fd, _hidden(rec, s["name"]))
        transfer._fsync(fd)
        for t in rec["texts"]:
            _set_text(rec, t, _side_text(rec["op"], "new", t))
        rec["state"] = "published"
        transfer._save(rec)
    finally:
        os.close(fd)


def _rollback_locked(rec: dict) -> None:
    """Undo whatever a `begun` record got done: texts that hold its new
    bytes get their old ones back, skills it added come out (only while
    they hash as recorded), skills it hid go back. Stuck when something it
    would put back over has changed by hand."""
    import shutil
    for t in rec["texts"]:
        live = _live(t["file"])
        if _sha(live) == t["new"] and t["new"] != t["old"]:
            _unset_text(rec, t, _side_text(rec["op"], "old", t))
        elif _sha(live) != t["old"]:
            raise transfer.Stuck(f"communal {t['file']} was changed by hand during an "
                                 "interrupted import; it was left as it is")
    try:
        fd = agentfs._open_skills_dir(COMMUNAL)
    except AgentFsError:
        fd = None
    if fd is not None:
        try:
            for s in rec["skills"]:
                stage, hidden, name = _stage(rec, s["name"]), _hidden(rec, s["name"]), s["name"]
                if s["add"]:
                    transfer._rmtree(fd, stage)
                    if transfer._present(fd, name):
                        try:
                            ours = transfer.read_item(fd, name)[1] == s["digest"]
                        except (OSError, AgentFsError):
                            ours = False
                        if ours:
                            shutil.rmtree(name, dir_fd=fd)
                elif transfer._present(fd, hidden):
                    if transfer._present(fd, name):
                        raise transfer.Stuck(f"{name} was hidden by an Undo that did not finish, "
                                             f"and a new {name} is there now; the old one is in "
                                             f"skills/{hidden}")
                    transfer._rename(fd, hidden, fd, name)
            transfer._fsync(fd)
        finally:
            os.close(fd)
    transfer._forget(rec)
    with contextlib.suppress(OSError, AgentFsError):
        shutil.rmtree(side_dir(rec["op"]))


def _finish(rec: dict) -> dict:
    """A `published` record, finished: each added skill kept as it landed,
    each hidden one removed with its history, an undone import marked so.
    Safe to repeat (recovery runs it again)."""
    fd = agentfs._open_skills_dir(COMMUNAL)
    try:
        for s in rec["skills"]:
            if s["add"]:
                if transfer._present(fd, s["name"]):
                    transfer._keep_at(COMMUNAL, s["name"], _who(rec))
            else:
                transfer._rmtree(fd, _hidden(rec, s["name"]))
                transfer._drop_history(COMMUNAL, s["name"])
        transfer._fsync(fd)
    finally:
        os.close(fd)
    if rec.get("undo_of"):
        orig = transfer._finished(rec["undo_of"])
        if orig is not None and orig.get("kind") == "import" and orig.get("state") == "done":
            orig["state"], orig["undone_by"] = "undone", rec["op"]
            transfer._save(orig)
    rec["state"] = "done"
    transfer._save(rec)
    if rec.get("undo_of"):
        # Nothing can be undone any more: neither copy is needed.
        import shutil
        for op in (rec["op"], rec["undo_of"]):
            with contextlib.suppress(OSError, AgentFsError):
                shutil.rmtree(side_dir(op))
    transfer._prune()
    _prune_sides()
    return rec


def settle(rec: dict) -> str:
    """Recovery's way in (transfer._settle, the lock held)."""
    if rec["state"] == "published":
        _finish(rec)
        return "finished"
    _rollback_locked(rec)
    return "rolled back"


def _run(rec: dict, old: dict[str, bytes | None], new: dict[str, bytes | None],
         staged: dict[str, list] | None) -> dict:
    """Write the side copies, the record, then carry it out; rolled back on
    anything raised before `published`. The lock is held."""
    side = side_dir(rec["op"], create=True)
    for t in rec["texts"]:
        for which, data in (("old", old[t["file"]]), ("new", new[t["file"]])):
            if data is not None:
                agentfs._atomic_write(side / f"{which}-{t['file']}", data)
    rec["state"] = "begun"
    transfer._save(rec)
    try:
        _apply_locked(rec, staged)
    except BaseException as e:
        if rec["state"] != "published":
            try:
                _rollback_locked(rec)
            except (OSError, AgentFsError) as e2:
                rec["state"], rec["problem"] = "stuck", str(e2)[:300]
                with contextlib.suppress(OSError, AgentFsError):
                    transfer._save(rec)
                raise AgentFsError(f"it failed and could not be put back: {e2}") from None
        if isinstance(e, OSError):
            if e.errno == errno.ENOSPC:
                raise AgentFsError("the disk is full; nothing was changed") from None
            raise AgentFsError(f"it could not be done ({e.strerror}); nothing was changed") from None
        raise
    try:
        return _finish(rec)
    except (OSError, AgentFsError) as e:
        why = e.strerror if isinstance(e, OSError) else str(e)
        raise AgentFsError(f"it is in place, but finishing it failed ({why}); it is finished "
                           "on the next try") from None


def _audit(rec: dict) -> None:
    try:
        import audit
        # Only plain names reach audit.record (the AST check in test_notes):
        # the operation's id, a skill's name, byte counts.
        size = sum(s["bytes"] for s in rec["skills"]) + rec.get("text_bytes", 0)
        kind = "communal_import" if rec["action"] == "import" else "communal_import_undo"
        op = rec["op"]
        audit.record(kind, frm="you", to=COMMUNAL, note=op, after=size)
        if rec["action"] == "import":
            for name, copied_bytes in [(s["name"], s["bytes"]) for s in rec["skills"]]:
                audit.record("skill_import", frm="you", to=COMMUNAL, note=name,
                             after=copied_bytes)
    except Exception:           # noqa: BLE001 -- it is done; a log never undoes it
        pass


# --- what the person does ---------------------------------------------------------------

def commit(path: str, token: str, cfg) -> dict:
    """Import `path` into Communal, exactly as the dry run that gave `token`
    listed it, or refuse and change nothing."""
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        raise AgentFsError("not a token from a dry run; run the import without --confirm first")
    with agentfs._locked(), transfer.working():
        transfer._recover_locked()
        p, src = _plan(path, cfg)
        if p["problems"]:
            raise AgentFsError("refused: " + "; ".join(p["problems"][:3]))
        if p["token"] != token:
            raise AgentFsError("the folder or Communal changed since the dry run; nothing was "
                               "changed, look at it again")
        if not p["changes"]:
            raise AgentFsError("nothing to import: Communal has all of it already")
        old, new, texts = {}, {}, []
        for t in p["texts"]:
            if t["change"] == "same":
                continue
            name = t["file"]
            old[name], new[name] = _communal_text(name), src["texts"][name]
            texts.append({"file": name, "old": _sha(old[name]), "new": _sha(new[name])})
        staged = {s["name"]: src["skills"][s["name"]][0] for s in p["skills"] if s["change"] == "new"}
        skills = [{"name": s["name"], "digest": src["skills"][s["name"]][1], "add": True,
                   "files": s["files"], "bytes": s["bytes"]} for s in p["skills"] if s["change"] == "new"]
        rec = {"v": 1, "op": transfer._new_op(), "kind": "import", "action": "import",
               "name": "communal", "from": transfer.OUTSIDE, "to": COMMUNAL, "undo_of": "",
               "texts": texts, "skills": skills,
               "text_bytes": sum(len(new[t["file"]] or b"") for t in texts),
               "at": round(time.time(), 3), "state": "begun"}
        done = _run(rec, old, new, staged)
    _audit(done)
    return result(done)


def undo(op: str) -> dict:
    """Take the import `op` back, only while nothing it wrote has changed."""
    if not isinstance(op, str) or not transfer._OP.fullmatch(op):
        raise AgentFsError(f"not an import id: {op!r}")
    with agentfs._locked(), transfer.working():
        transfer._recover_locked()
        orig = transfer._finished(op)
        if orig is None or orig.get("kind") != "import" or orig.get("action") != "import":
            raise AgentFsError(f"no finished import {op} is recorded")
        if orig.get("state") == "undone":
            raise AgentFsError("that was undone already")
        if orig.get("state") != "done":
            raise AgentFsError(f"that did not finish ({orig.get('state')}); nothing to undo")
        old, new, texts = {}, {}, []
        for t in orig["texts"]:
            if _sha(_live(t["file"])) != t["new"]:
                raise AgentFsError(f"communal {t['file']} changed since the import; Undo is "
                                   "refused so the change is not lost (its History can still "
                                   "put an earlier version back)")
            # The undo writes the import's old bytes back over its new ones.
            old[t["file"]] = _side_text(op, "new", t)
            new[t["file"]] = _side_text(op, "old", t)
            texts.append({"file": t["file"], "old": t["new"], "new": t["old"]})
        fd = agentfs._open_skills_dir(COMMUNAL)
        try:
            for s in orig["skills"]:
                try:
                    same = transfer.read_item(fd, s["name"])[1] == s["digest"]
                except (FileNotFoundError, AgentFsError):
                    same = False
                if not same:
                    raise AgentFsError(f"{s['name']} in Communal changed or is gone since the "
                                       "import; Undo is refused so the change is not lost")
        finally:
            os.close(fd)
        rec = {"v": 1, "op": transfer._new_op(), "kind": "import", "action": "undo",
               "name": "communal", "from": transfer.OUTSIDE, "to": COMMUNAL, "undo_of": op,
               "texts": texts,
               "skills": [{**s, "add": False} for s in orig["skills"]],
               "text_bytes": sum(len(new[t["file"]] or b"") for t in texts),
               "at": round(time.time(), 3), "state": "begun"}
        done = _run(rec, old, new, None)
    _audit(done)
    return result(done)


def result(rec: dict) -> dict:
    return {"op": rec["op"], "action": rec["action"], "state": rec["state"],
            "undo_of": rec.get("undo_of", ""), "texts": [t["file"] for t in rec["texts"]],
            "skills": [s["name"] for s in rec["skills"]],
            "bytes": sum(s["bytes"] for s in rec["skills"]) + rec.get("text_bytes", 0)}


def history(limit: int = 20) -> list[dict]:
    """The imports and their undos recorded, newest first, each with
    whether Undo would be offered."""
    try:
        d = transfer.journal_dir()
        names = sorted((n for n in os.listdir(d)
                        if n.endswith(transfer.DONE) or n.endswith(transfer.OPEN)), reverse=True)
    except (OSError, AgentFsError):
        return []
    out, seen = [], set()
    for n in names:
        op = n[: -len(transfer.OPEN)] if n.endswith(transfer.OPEN) else n[: -len(transfer.DONE)]
        if op in seen:
            continue
        seen.add(op)
        rec = transfer._read_record(d / n)
        if rec is None or rec.get("kind") != "import":
            continue
        out.append({**result(rec), "at": rec.get("at", 0), "undone_by": rec.get("undone_by", ""),
                    "problem": rec.get("problem", ""),
                    "undoable": rec["action"] == "import" and rec["state"] == "done"})
        if len(out) >= limit:
            break
    return out


# --- CLI (through agentfs.main) ---------------------------------------------------------

def cli(a) -> int:
    from runtime import Config
    from speech_text import safe_for_terminal as safe
    if a.cmd == "import-history":
        h = history()
        agentfs._print(h, a.json, "\n".join(
            f"{x['op']}  {x['action']}  {x['state']}  texts: {', '.join(x['texts']) or '-'}  "
            f"skills: {', '.join(x['skills']) or '-'}" for x in h) or "no imports")
        return 0
    if a.cmd == "import-undo":
        r = undo(a.op)
        agentfs._print(r, a.json, f"undone: {r['undo_of']} (as {r['op']})")
        return 0
    if a.target != COMMUNAL:
        raise AgentFsError("only communal can be imported into (an agent's own skills come "
                           "in through agentvoice skills import)")
    cfg = Config()
    if a.confirm:
        r = commit(a.dir, a.confirm, cfg)
        agentfs._print(r, a.json, f"imported as {r['op']}: texts {', '.join(r['texts']) or '-'}; "
                                  f"skills {', '.join(r['skills']) or '-'}")
        return 0
    p = plan(a.dir, cfg)
    lines = [f"from {safe(p['dir'])}"]
    for t in p["texts"]:
        lines.append(f"{t['file']}: {t['change']} ({t['chars']}/{t['limit']} characters)")
        lines += [f"  {safe(x)}" for x in t["diff"]]
    for s in p["skills"]:
        lines.append(f"skill {s['name']}: {s['change']} ({s['files']} files, {s['bytes']} bytes)"
                     + (f"; hidden for {', '.join(s['hidden_for'])} by its own"
                        if s["hidden_for"] else ""))
    lines += [f"ignored: {safe(x)}" for x in p["ignored"]]
    lines.append("reaches: " + (", ".join(p["reaches"]) or "no agent"))
    lines += [f"! {safe(x)}" for x in p["problems"]]
    lines.append(f"token: {p['token']}" if not p["problems"] and p["changes"]
                 else "nothing to import" if not p["problems"] else "refused")
    agentfs._print(p, a.json, "\n".join(lines))
    return 1 if p["problems"] else 0
