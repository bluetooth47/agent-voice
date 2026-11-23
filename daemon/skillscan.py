"""Skills on this machine, and who gets each one (master plan, phase M11).

Agent Voice has always given an agent the skills in its own folder and the
communal one (agentfs.py, Phase 13). The CLIs it runs also find skills by
themselves, and until M11 nothing said so: a `claude -p` turn lists every
skill in ~/.claude/skills, the claude.ai account's synced skills and every
enabled plugin's, and `codex exec` every skill in ~/.codex/skills and
~/.agents/skills (recorded in tests/fixtures/skills/spike-m11.json). This
module finds those, says which agent sees which, and turns the switch off
where the CLI looks:

- **Claude Code**: `skillOverrides: {name: "off"}` in the `--settings` the
  adapter already passes. Its Skill tool then refuses the skill ("disabled
  for model invocation"), recorded. A bare name also hides the claude.ai
  synced skill of that name, and never the agent's own `agentvoice:` copy.
- **Codex**: `-c skills.config=[{name=..., enabled=false}]`, merged by Codex
  with any in config.toml (recorded). A plugin's skill needs `plugin:name`.

Either way the skill's files stay readable to an agent with file tools:
"off" takes it out of what the CLI offers, it does not hide a file. The
pages say so.

The scan **reads only**: directory listings and SKILL.md files, bounded,
never a subprocess (a test makes every process-starting call fail). The
top-level folder of a skill may be a link -- Omarchy installs its own skills
as links into /usr/share -- and the CLIs follow it, so the scan does too;
inside a skill nothing is followed, and a skill holding a link cannot be
copied in (agentfs.import_skill).

One name is one switch (`skillsOff`): everything of that name an agent would
get -- its own copy, the communal one, the one its CLI finds -- is off
together. An Agent Voice skill (own or communal) of the same name as one the
CLI finds hides the CLI's, so an agent never has two of one name.

    python skillscan.py lanes [AGENT] [--json]
    python skillscan.py import SOURCE_ID|PATH TO [--confirm]   # TO: an agent id or communal
    python skillscan.py move|copy FROM NAME TO [--confirm]      # phase M12, transfer.py
    python skillscan.py undo OP
    python skillscan.py history [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agentfs  # noqa: E402
from runtime import SKILL_REF  # noqa: E402

#: Where each CLI finds skills by itself, as recorded (the fixture above).
#: Claude Code's bundled skills (/loop, /schedule, ...) are part of the
#: program, not files here, and Codex's own (~/.codex/skills/.system) and its
#: plugins' are the same kind of thing: listed in UNMANAGED, not switched.
SOURCES = {
    "claude-user": {"family": "claude", "label": "~/.claude/skills"},
    "claude-synced": {"family": "claude", "label": "claude.ai (synced)"},
    "claude-plugin": {"family": "claude", "label": "a Claude Code plugin"},
    "codex-user": {"family": "codex", "label": "~/.codex/skills"},
    "agents": {"family": "codex", "label": "~/.agents/skills"},
}
#: The programs that find skills by themselves, and which sources they read.
FAMILY = {"claude": "claude", "codex": "codex"}
#: What a program's tab says about the skills Agent Voice does not switch.
UNMANAGED = {
    "claude": "Claude Code also has skills built into it (/loop, /schedule, /code-review…); "
              "Agent Voice does not switch those.",
    "codex": "Codex also has skills of its own (~/.codex/skills/.system) and its plugins'; "
             "Agent Voice does not switch those.",
    "gemini": "Gemini may also load skills from its own settings; Agent Voice does not switch "
              "those.",
    "agy": "Antigravity may also load skills from its own settings; Agent Voice does not switch "
           "those.",
    "copilot": "Copilot may also load skills from its own settings; Agent Voice does not switch "
               "those.",
}
#: Bounds: how many skills the scan lists in all, how many entries it reads
#: from one folder, and how much of a SKILL.md it reads for the description.
MAX_SKILLS = 200
MAX_ENTRIES = 400
HEAD_BYTES = 64 * 1024
#: A plugin skill's name as Claude Code gives it, `plugin:skill`.
_PLUGIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


class SkillsUnknown(Exception):
    """A folder a CLI reads skills from is there and cannot be listed, so
    the skills it holds cannot be named, and so cannot be switched off."""


def roots():
    """Where the CLIs keep their settings (tooldetect's, which honours
    CLAUDE_CONFIG_DIR and CODEX_HOME; the tests point both at scratch)."""
    import tooldetect
    return tooldetect.default_roots()


def _shown(r, path) -> str:
    return r.shown(path)


def agents_dir(r) -> Path:
    """~/.agents/skills, the folder skills shared between coding agents live
    in (Omarchy links its own there); Codex reads it (recorded). A function
    so the tests can point it somewhere else, as they do the CLIs' homes."""
    return r.home / ".agents" / "skills"


def _listing(folder: Path, hidden: bool = False, strict: bool = False) -> list[str]:
    """Entry names in `folder`, sorted, bounded. [] when it is not there;
    SkillsUnknown when it is there and cannot be read -- or, when `strict`,
    when it holds more than MAX_ENTRIES, so a list meant to name every
    skill never names only some. The folder itself may be a link (Omarchy's
    ~/.agents/skills holds links; a person may link the whole folder)."""
    try:
        with os.scandir(folder) as it:
            names = []
            for e in it:
                if not hidden and e.name.startswith("."):
                    continue
                names.append(e.name)
                if len(names) >= MAX_ENTRIES:
                    if strict and next(it, None) is not None:
                        raise SkillsUnknown(f"{folder.name} holds more than {MAX_ENTRIES} entries")
                    break
    except FileNotFoundError:
        return []
    except NotADirectoryError:
        return []
    except OSError as e:
        raise SkillsUnknown(f"{folder.name} cannot be listed ({e.strerror})") from None
    return sorted(names)


def _places(r, strict: bool = False) -> list[tuple[str, str, Path, str]]:
    """Every (source, folder name -- as `plugin:folder` for a plugin's --,
    folder, plugin) the CLIs read a skill from, by listing their folders.
    Raises SkillsUnknown when one is there and cannot be listed. At most
    MAX_SKILLS for the pages; `strict` (what the daemon switches off when a
    list is unreadable) lists every one, and raises rather than name only
    some: a folder too large, or a plugin list that cannot be read (Codex
    review of M11)."""
    out: list[tuple[str, str, Path, str]] = []
    user = r.claude_dir / "skills"
    for n in _listing(user, strict=strict):
        if n == "synced":
            continue                    # the claude.ai buckets, below
        out.append(("claude-user", n, user / n, ""))
    for bucket in _listing(user / "synced", strict=strict):
        for n in _listing(user / "synced" / bucket, strict=strict):
            if (user / "synced" / bucket / n).is_dir():
                out.append(("claude-synced", n, user / "synced" / bucket / n, ""))
    import tooldetect
    reader = tooldetect._Reader()
    try:
        plugins = tooldetect.enabled_plugins(r, reader)
    except Exception:               # noqa: BLE001 -- a plugin list that cannot be read lists none
        plugins, reader.problems = [], ["the plugin list cannot be read"]
    if strict and reader.problems:
        raise SkillsUnknown("Claude Code's plugin list cannot be read")
    for plugin, root in plugins:
        if not _PLUGIN.fullmatch(plugin):
            continue
        for n in _listing(root / "skills", strict=strict):
            out.append(("claude-plugin", f"{plugin}:{n}", root / "skills" / n, plugin))
    for n in _listing(r.codex_home / "skills", strict=strict):
        out.append(("codex-user", n, r.codex_home / "skills" / n, ""))
    shared = agents_dir(r)
    for n in _listing(shared, strict=strict):
        out.append(("agents", n, shared / n, ""))
    return out if strict else out[:MAX_SKILLS]


def _front_name(folder: Path, plugin: str) -> str:
    """The name a skill's own front matter gives it ("" when none can be
    read), as `plugin:name` for a plugin's."""
    head = _head(folder / "SKILL.md")
    if head is None:
        return ""
    front, _ = agentfs._front_matter(head.decode("utf-8", errors="replace"))
    name = str((front or {}).get("name") or "").strip()
    if not name:
        return ""
    return f"{plugin}:{name}" if plugin else name


def _aliases(name: str, folder: Path, plugin: str) -> set[str]:
    """Every name a CLI might know this skill by: its folder's and its front
    matter's, which may differ outside Agent Voice (Codex review of M11).
    Naming both is harmless: a name that names nothing is ignored by both
    CLIs (recorded)."""
    out = {name, _front_name(folder, plugin)}
    return {n for n in out if n and SKILL_REF.fullmatch(n)}


def native_names(program: str) -> list[str]:
    """Every name a program's CLI might know a skill it finds by itself by,
    now: what is switched off when an agent's list cannot be read. Every
    folder is listed in full; SkillsUnknown when one cannot be, or holds
    more than can be listed."""
    family = FAMILY.get(program)
    if family is None:
        return []
    names: set[str] = set()
    for src, name, folder, plugin in _places(roots(), strict=True):
        if SOURCES[src]["family"] == family:
            names |= _aliases(name, folder, plugin)
    return sorted(names)


#: The aliases of each skill a family's CLI finds, kept while nothing in
#: its folders moved (a listing and a stat per skill, no file read), so the
#: idle poll stays cheap: family -> (stamp, {alias: every alias}).
_ALIAS_MEMO: dict = {}


def alias_map(program: str) -> dict[str, set[str]]:
    """{a name: every name that skill goes by} for the skills `program`'s
    CLI finds by itself, from every one of them (the strict listing, not
    the pages' 200: Codex review of M11, pass 2). SkillsUnknown when they
    cannot all be listed: a switch could then miss the name the CLI uses,
    so the caller closes rather than guess."""
    family = FAMILY.get(program)
    if family is None:
        return {}
    places = [p for p in _places(roots(), strict=True) if SOURCES[p[0]]["family"] == family]
    stamp = []
    for _, name, folder, _ in places:
        try:
            st = os.stat(folder / "SKILL.md")
            stamp.append((str(folder), st.st_mtime_ns, st.st_size, st.st_ino))
        except OSError:
            stamp.append((str(folder), 0, -1, 0))
    have = _ALIAS_MEMO.get(family)
    if have is not None and have[0] == stamp:
        return have[1]
    out: dict[str, set[str]] = {}
    for _, name, folder, plugin in places:
        names = _aliases(name, folder, plugin)
        for n in names:
            out.setdefault(n, set()).update(names)
    _ALIAS_MEMO[family] = (stamp, out)
    return out


def _head(path: Path) -> bytes | None:
    """The start of SKILL.md, read without following a link at the file
    itself; None when absent, not a regular file or unreadable."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0) \
        | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        return os.read(fd, HEAD_BYTES)
    except OSError:
        return None
    finally:
        os.close(fd)


def _one(r, src: str, name: str, folder: Path, plugin: str) -> dict:
    """One skill found outside Agent Voice, as the pages show it."""
    bare = name.split(":", 1)[1] if plugin else name
    entry = {"id": f"{src}:{name}", "name": name, "folder": bare, "source": src,
             "aliases": [name] if SKILL_REF.fullmatch(name) else [],
             "family": SOURCES[src]["family"], "source_label": SOURCES[src]["label"],
             "path": _shown(r, folder), "linked": folder.is_symlink(),
             "description": "", "size": 0, "files": 0, "problem": "", "copy_problem": ""}
    if plugin:
        entry["source_label"] = f"the {plugin} plugin"
    try:
        real = folder.resolve(strict=True)
        if not real.is_dir():
            entry["problem"] = "it is not a folder"
            return entry
    except (OSError, RuntimeError):
        entry["problem"] = "it is a link to nothing" if folder.is_symlink() else "it cannot be read"
        return entry
    head = _head(real / "SKILL.md")
    if head is None:
        entry["problem"] = "it has no SKILL.md Agent Voice can read"
        return entry
    text = head.decode("utf-8", errors="replace")
    front, why = agentfs._front_matter(text)
    if front is None:
        entry["problem"] = why
    else:
        entry["description"] = " ".join(str(front.get("description", "")).split())[:400]
        # The name its front matter gives it, when that differs from its
        # folder's: a CLI may know it by either, so both are switched.
        own_name = str(front.get("name") or "").strip()
        known = {name, f"{plugin}:{own_name}" if plugin and own_name else own_name}
        entry["aliases"] = sorted(n for n in known if n and SKILL_REF.fullmatch(n))
        if own_name and own_name != bare:
            entry["front_name"] = own_name[:64]
    tree, why = agentfs.walk_skill(real)
    if tree:
        entry["files"] = len(tree)
        entry["size"] = sum(size for _, _, size in tree)
    # Whether it could be copied into an agent's folder (assign = import a
    # verified copy): the rules every Agent Voice skill keeps.
    if why:
        entry["copy_problem"] = why
    elif not agentfs.valid_skill_name(bare):
        entry["copy_problem"] = agentfs.parse_skill(bare, "")[1]
    else:
        whole = _whole(real / "SKILL.md")
        entry["copy_problem"] = (agentfs.parse_skill(bare, whole)[1] if whole is not None
                                 else "its SKILL.md cannot be read")
    return entry


def _whole(path: Path) -> str | None:
    """SKILL.md in full for the copy check, within the cap a skill keeps."""
    try:
        data, more = agentfs._read_bytes(path)
    except (OSError, agentfs.AgentFsError):
        return None
    if more:
        return "x" * (agentfs.SKILL_MAX + 1)    # longer than any skill may be
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def user_off(r) -> tuple[set[str], set[str], set[str]]:
    """What the person already switched off in the CLIs' own settings, so a
    lane does not say an agent gets what its CLI will not offer: Claude
    Code's `skillOverrides` ("off"), and Codex's `[[skills.config]]` with
    enabled = false, by name or by path. (claude names, codex names, codex
    SKILL.md paths resolved). Read only; anything unreadable is nothing."""
    import tooldetect
    reader = tooldetect._Reader()
    claude: set[str] = set()
    settings = reader.json(r.claude_dir / "settings.json", follow=True)
    overrides = settings.get("skillOverrides") if isinstance(settings, dict) else None
    if isinstance(overrides, dict):
        claude = {k for k, v in overrides.items() if isinstance(k, str) and v == "off"}
    names: set[str] = set()
    places: set[str] = set()
    config = reader.toml(r.codex_home / "config.toml", limit=4 * 1024 * 1024, follow=True)
    entries = ((config or {}).get("skills") or {}).get("config") if isinstance(config, dict) else None
    for e in entries if isinstance(entries, list) else []:
        if not isinstance(e, dict) or e.get("enabled") is not False:
            continue
        if isinstance(e.get("name"), str):
            names.add(e["name"])
        if isinstance(e.get("path"), str):
            try:
                places.add(str(Path(os.path.expanduser(e["path"])).resolve()))
            except (OSError, RuntimeError):
                pass
    return claude, names, places


def scan() -> dict:
    """Every skill the CLIs find outside Agent Voice, now: {"skills": [...],
    "problems": [...], "ms"}. A folder that cannot be listed is a problem,
    not an exception: the page shows what could be read and says what
    could not."""
    t0 = time.monotonic()
    r = roots()
    problems: list[str] = []
    try:
        places = _places(r)
    except SkillsUnknown as e:
        places, problems = [], [str(e)]
    found = [_one(r, *p) for p in places]
    try:
        claude_off, codex_names, codex_paths = user_off(r)
    except Exception:           # noqa: BLE001 -- the CLI's own settings are its business
        claude_off, codex_names, codex_paths = set(), set(), set()
    for s, (_, _, folder, _) in zip(found, places):
        if s["family"] == "claude":
            s["user_off"] = s["name"] in claude_off or s["folder"] in claude_off
        else:
            try:
                where = str((folder / "SKILL.md").resolve())
            except (OSError, RuntimeError):
                where = ""
            s["user_off"] = s["name"] in codex_names or where in codex_paths
    return {"skills": found, "problems": problems,
            "ms": round((time.monotonic() - t0) * 1000, 1)}


# --- who gets what -----------------------------------------------------------------

def native_off(cfg, agent_id: str, program: str, own_names=()) -> list[str]:
    """The names to switch off where `program`'s CLI looks, for one agent:
    every name in its `skillsOff`, and every Agent Voice skill it has (its
    own or communal, present at all) so the CLI's copy of that name is not
    offered beside it. Unknown names are harmless to both CLIs (recorded).

    When its list cannot be read, every skill that CLI finds now: the
    folders are listed, and SkillsUnknown is raised when one cannot be --
    the caller then starts no turn rather than offer what nobody can see."""
    if FAMILY.get(program) is None:
        return []
    off = cfg.skills_off_for(agent_id)
    names = set(own_names)
    if off is None:
        names |= set(native_names(program))
    else:
        names |= set(off)
        # And every other name a skill so named goes by (its folder's, its
        # front matter's), so the switch holds whichever the CLI uses. Not
        # knowing them all raises SkillsUnknown: the caller closes.
        aliases = alias_map(program) if names else {}
        for n in list(names):
            names |= aliases.get(n, set())
    return sorted(n for n in names if isinstance(n, str) and SKILL_REF.fullmatch(n))


def agent_view(program: str, off, own: list[dict], communal: list[dict],
               external: list[dict], delivery: str, communal_on: bool = True) -> list[dict]:
    """One agent's skills, as its Tools & skills tab lists them: its own,
    the communal ones (agentfs.skill_set), then each one its CLI finds by
    itself. Every entry carries `on` (not switched off), `delivered` (it
    really gets it) and `why` (why not, when it does not). `communal_on`
    False: an agent opted out of Communal (phase M15). Pure."""
    entries = agentfs.skill_set(own, communal, off, communal_on)
    if delivery == "none":
        entries = [{**s, "delivered": False,
                    "why": s.get("why") or "its program is given no skills"} for s in entries]
    family = FAMILY.get(program)
    if family is None:
        return entries
    # The names Agent Voice gives it: an opted-out agent's CLI is not told
    # to hide its own copy of a communal skill it is not given (M15).
    ours = {s["name"] for s in entries if communal_on or s["source"] != agentfs.COMMUNAL}
    first: dict[str, dict] = {}
    for s in external:
        if s["family"] != family:
            continue
        names = set(s.get("aliases") or ()) | {s["name"]}
        on = off is not None and not (names & set(off))
        shadowed = bool(names & ours) or s["folder"] in ours
        # One name is offered once: a skill in both ~/.codex/skills and
        # ~/.agents/skills (Omarchy links its own into each) is listed by
        # Codex from ~/.codex/skills only (recorded), and SOURCES' order is
        # that order. claude.ai's synced skills have names of their own.
        key = native_key(s)
        earlier = first.get(key)
        why = ("its switch list cannot be read, so it is off" if off is None
               else "switched off for this agent" if not on
               else "an Agent Voice skill of the same name is given instead" if shadowed
               else f"the one in {earlier['source_label']} is offered instead" if earlier
               else f"switched off in your own {agentfs.PROGRAM_LABELS.get(program, program)} settings"
               if s.get("user_off") else "")
        first.setdefault(key, s)
        entries.append({**s, "native": True, "on": on, "shadowed": shadowed,
                        "duplicate": earlier is not None, "delivered": not why, "why": why})
    return entries


def native_key(s: dict) -> str:
    """What makes two skills a CLI finds the same one to it: its family
    and name, the claude.ai synced ones apart (Claude lists those under a
    name of their own, `anthropic-skills:<name>`)."""
    space = "synced:" if s["source"] == "claude-synced" else ""
    return f"{s['family']}:{space}{s['name']}"


def lanes(cfg, texts=None) -> dict:
    """Every skill on this machine in its owner's lane (master plan, M11):
    one lane per agent (main first) holding its own skills and the ones its
    CLI finds that it gets; Communal; and Unused, the skills found outside
    Agent Voice that no agent gets. Each card says who gets it."""
    scanned = scan()
    external = scanned["skills"]
    communal = agentfs.skills(agentfs.COMMUNAL)
    agents = [{"id": agentfs.MAIN, "agent_id": "", "label": cfg.main_label(
        " ".join(cfg.get_str("phrase").lower().split())), "enabled": True}]
    agents += [{"id": a["id"], "agent_id": a["id"], "label": a["label"],
                "enabled": a.get("enabled", True)} for a in cfg.all_agents()]
    out_lanes = []
    gets: dict[str, list[str]] = {}
    for a in agents:
        program = agentfs.program_of(a["agent_id"] or agentfs.MAIN, cfg)
        delivery = agentfs.delivery_of(program)[0]
        off = cfg.skills_off_for(a["agent_id"])
        own = agentfs.skills(a["id"])
        takes = cfg.takes_communal(a["id"])
        view = agent_view(program, off, own, communal, external, delivery, takes)
        for s in view:
            if s.get("delivered") and a["enabled"]:
                gets.setdefault(_card_id(s), []).append(a["label"])
        out_lanes.append({"id": a["id"], "label": a["label"], "program": program,
                          "program_label": agentfs.PROGRAM_LABELS.get(program, program or "No program"),
                          "enabled": a["enabled"], "delivery": delivery,
                          "takes_communal": takes,
                          "skills": [s for s in view if s["source"] == a["id"]
                                     or (s.get("native") and s.get("delivered"))]})
    for lane in out_lanes:
        lane["skills"] = [{**s, "gets": gets.get(_card_id(s), [])} for s in lane["skills"]]
    shared = [{**s, "gets": gets.get(_card_id(s), [])} for s in communal]
    unused = [{**s, "gets": []} for s in external if not gets.get(_card_id(s))]
    return {"lanes": out_lanes, "communal": shared, "unused": unused,
            "problems": scanned["problems"], "ms": scanned["ms"]}


def _card_id(s: dict) -> str:
    """A card's id across lanes: for a skill a CLI finds by itself, the one
    skill it is to that CLI (native_key, so a second copy of a name is not
    Unused while the first is given); for an Agent Voice skill, where it
    lives and its name."""
    return native_key(s) if "family" in s else f"{s['source']}:{s['name']}"


def find(source_id: str) -> tuple[dict, Path]:
    """The skill found outside Agent Voice with this id, and its folder,
    from a scan made now (never a path from the caller)."""
    if not isinstance(source_id, str) or len(source_id) > 200:
        raise agentfs.AgentFsError("not a skill found on this machine")
    for src, name, folder, plugin in _places(roots()):
        if f"{src}:{name}" == source_id:
            return _one(roots(), src, name, folder, plugin), folder
    raise agentfs.AgentFsError("no skill found on this machine has that id; scan again")


def import_skill(source_id: str, target: str) -> dict:
    """Assign a skill from outside Agent Voice to an agent or Communal: a
    verified copy (agentfs.import_skill). The original is never changed.
    Since M12 the copy is recorded (transfer.record_import), so it can be
    undone like any copy: the result carries its `op`."""
    entry, folder = find(source_id)
    got = agentfs.import_skill(target, entry["folder"], folder)
    return _recorded(got)


def import_path(path: str, target: str) -> dict:
    """The same, from a folder named by its path (master plan M12: `skills
    import PATH TO`). Its name is the folder's; everything import_skill
    checks is checked the same way."""
    if not isinstance(path, str) or not path or "\x00" in path:
        raise agentfs.AgentFsError("not a folder")
    folder = Path(path).expanduser()
    if not folder.is_absolute():
        folder = Path.cwd() / folder
    return _recorded(agentfs.import_skill(target, folder.name, folder))


def _recorded(got: dict) -> dict:
    import transfer
    rec = transfer.record_import(got["target"], got["name"])
    return {**got, "op": rec["op"] if rec else ""}


def needs_confirm(cfg, frm: str, to: str) -> str:
    """Why a move, copy or import must be confirmed, or "" (master plan,
    section 7.3): into Communal (every agent gets it), or out of a
    quarantined agent (what it wrote may not be what you meant to share).
    A quarantine list that cannot be read counts every agent as in it."""
    if to == agentfs.COMMUNAL:
        return "every agent will get this skill"
    if frm and frm not in (agentfs.COMMUNAL, "outside"):
        q = cfg.quarantined()
        if q is None:
            return "the quarantine list cannot be read, so every agent counts as quarantined"
        if frm in q:
            return f"{frm} is quarantined"
    return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agentvoice skills",
                                 description="Skills on this machine, and who gets each.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lanes", help="every skill, in its owner's lane")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("import", help="give an agent or Communal a copy of a skill found here")
    p.add_argument("source", help="its id, from `lanes --json`, or a folder's path (with a /)")
    p.add_argument("to", help="an agent's folder id, or communal")
    p.add_argument("--confirm", action="store_true", help="into Communal: you were asked")
    # Phase M12: between Agent Voice's own folders, and back.
    for verb, what in (("move", "move a skill to another agent or Communal"),
                       ("copy", "copy a skill to another agent or Communal")):
        p = sub.add_parser(verb, help=what)
        p.add_argument("frm", metavar="FROM", help="an agent's folder id, or communal")
        p.add_argument("name")
        p.add_argument("to", metavar="TO", help="an agent's folder id, or communal")
        p.add_argument("--confirm", action="store_true",
                       help="into Communal, or out of a quarantined agent: you were asked")
    p = sub.add_parser("undo", help="undo a move, copy or import, if nothing changed since")
    p.add_argument("op", help="its id, from the move's output or `history`")
    p = sub.add_parser("history", help="the moves, copies and imports recorded")
    p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "lanes":
            from runtime import Config
            got = lanes(Config())
            if a.json:
                print(json.dumps(got))
            else:
                from speech_text import safe_for_terminal as safe
                for lane in got["lanes"]:
                    print(f"{safe(lane['label'])} ({safe(lane['program_label'])})")
                    for s in lane["skills"]:
                        print(f"  {safe(s['name'])}  [{safe(s.get('source_label') or 'own')}]")
                print("Communal")
                for s in got["communal"]:
                    print(f"  {safe(s['name'])}")
                print("Unused")
                for s in got["unused"]:
                    print(f"  {safe(s['name'])}  [{safe(s['source_label'])}]  {safe(s['id'])}")
                for p in got["problems"]:
                    print(f"  ! {safe(p)}")
            return 0
        import transfer
        if a.cmd == "history":
            got = transfer.history(kind="skill")
            if a.json:
                print(json.dumps(got))
            else:
                from speech_text import safe_for_terminal as safe
                for r in got:
                    where = (f"{r['from']} → {r['to']}" if r["action"] != "remove"
                             else f"from {r['from']}")
                    extra = (" (undone)" if r["state"] == "undone" else
                             f" ({r['state']}: {r['problem']})" if r["state"] == "stuck" else
                             " (undo)" if r["undo_of"] else "")
                    print(safe(f"{r['op']}  {r['action']} {r['name']} {where}{extra}"))
            return 0
        if a.cmd == "undo":
            print(json.dumps(transfer.undo(a.op)))
            return 0
        from runtime import Config
        frm = "outside" if a.cmd == "import" else a.frm
        why = needs_confirm(Config(), frm, a.to)
        if why and not a.confirm:
            raise agentfs.AgentFsError(f"{why}: run it again with --confirm once you are sure")
        if a.cmd == "import":
            got = (import_path(a.source, a.to) if "/" in a.source
                   else import_skill(a.source, a.to))
        elif a.cmd == "move":
            got = transfer.move(a.frm, a.name, a.to)
        else:
            got = transfer.copy(a.frm, a.name, a.to)
        print(json.dumps(got))
        return 0
    except (agentfs.AgentFsError, SkillsUnknown) as e:
        from speech_text import safe_for_terminal as safe
        print(f"agentvoice skills: {safe(str(e))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
