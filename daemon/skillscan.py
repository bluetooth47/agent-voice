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
    python skillscan.py import SOURCE_ID TO      # TO: an agent id or communal
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


def _listing(folder: Path, hidden: bool = False) -> list[str]:
    """Entry names in `folder`, sorted, bounded. [] when it is not there;
    SkillsUnknown when it is there and cannot be read. The folder itself
    may be a link (Omarchy's ~/.agents/skills holds links; a person may link
    the whole folder)."""
    try:
        with os.scandir(folder) as it:
            names = []
            for e in it:
                if not hidden and e.name.startswith("."):
                    continue
                names.append(e.name)
                if len(names) >= MAX_ENTRIES:
                    break
    except FileNotFoundError:
        return []
    except NotADirectoryError:
        return []
    except OSError as e:
        raise SkillsUnknown(f"{folder.name} cannot be listed ({e.strerror})") from None
    return sorted(names)


def _places(r) -> list[tuple[str, str, Path, str]]:
    """Every (source, name the CLI knows it by, folder, plugin) the CLIs read
    a skill from, by listing their folders. Raises SkillsUnknown when one is
    there and cannot be listed."""
    out: list[tuple[str, str, Path, str]] = []
    user = r.claude_dir / "skills"
    for n in _listing(user):
        if n == "synced":
            continue                    # the claude.ai buckets, below
        out.append(("claude-user", n, user / n, ""))
    for bucket in _listing(user / "synced"):
        for n in _listing(user / "synced" / bucket):
            if (user / "synced" / bucket / n).is_dir():
                out.append(("claude-synced", n, user / "synced" / bucket / n, ""))
    try:
        import tooldetect
        plugins = tooldetect.enabled_plugins(r, tooldetect._Reader())
    except Exception:               # noqa: BLE001 -- a plugin list that cannot be read lists none
        plugins = []
    for plugin, root in plugins:
        if not _PLUGIN.fullmatch(plugin):
            continue
        for n in _listing(root / "skills"):
            out.append(("claude-plugin", f"{plugin}:{n}", root / "skills" / n, plugin))
    for n in _listing(r.codex_home / "skills"):
        out.append(("codex-user", n, r.codex_home / "skills" / n, ""))
    shared = agents_dir(r)
    for n in _listing(shared):
        out.append(("agents", n, shared / n, ""))
    return out[:MAX_SKILLS]


def native_names(program: str) -> list[str]:
    """The names a program's CLI finds by itself now, from folder listings
    only (no file is read): what is switched off when an agent's list cannot
    be read. Raises SkillsUnknown when a folder cannot be listed."""
    family = FAMILY.get(program)
    if family is None:
        return []
    names = {name for src, name, _, _ in _places(roots())
             if SOURCES[src]["family"] == family and SKILL_REF.fullmatch(name)}
    return sorted(names)


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
    return sorted(n for n in names if isinstance(n, str) and SKILL_REF.fullmatch(n))


def agent_view(program: str, off, own: list[dict], communal: list[dict],
               external: list[dict], delivery: str) -> list[dict]:
    """One agent's skills, as its Tools & skills tab lists them: its own,
    the communal ones (agentfs.skill_set), then each one its CLI finds by
    itself. Every entry carries `on` (not switched off), `delivered` (it
    really gets it) and `why` (why not, when it does not). Pure."""
    entries = agentfs.skill_set(own, communal, off)
    if delivery == "none":
        entries = [{**s, "delivered": False,
                    "why": s.get("why") or "its program is given no skills"} for s in entries]
    family = FAMILY.get(program)
    if family is None:
        return entries
    ours = {s["name"] for s in entries}
    for s in external:
        if s["family"] != family:
            continue
        on = off is not None and s["name"] not in off
        shadowed = s["folder"] in ours or s["name"] in ours
        why = ("its switch list cannot be read, so it is off" if off is None
               else "switched off for this agent" if not on
               else "an Agent Voice skill of the same name is given instead" if shadowed
               else f"switched off in your own {agentfs.PROGRAM_LABELS.get(program, program)} settings"
               if s.get("user_off") else "")
        entries.append({**s, "native": True, "on": on, "shadowed": shadowed,
                        "delivered": not why, "why": why})
    return entries


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
        view = agent_view(program, off, own, communal, external, delivery)
        for s in view:
            if s.get("delivered") and a["enabled"]:
                gets.setdefault(_card_id(s), []).append(a["label"])
        out_lanes.append({"id": a["id"], "label": a["label"], "program": program,
                          "program_label": agentfs.PROGRAM_LABELS.get(program, program or "No program"),
                          "enabled": a["enabled"], "delivery": delivery,
                          "skills": [s for s in view if s["source"] == a["id"]
                                     or (s.get("native") and s.get("delivered"))]})
    for lane in out_lanes:
        lane["skills"] = [{**s, "gets": gets.get(_card_id(s), [])} for s in lane["skills"]]
    shared = [{**s, "gets": gets.get(_card_id(s), [])} for s in communal]
    unused = [{**s, "gets": []} for s in external if not gets.get(_card_id(s))]
    return {"lanes": out_lanes, "communal": shared, "unused": unused,
            "problems": scanned["problems"], "ms": scanned["ms"]}


def _card_id(s: dict) -> str:
    """A card's id across lanes: an external skill's own id, or where an
    Agent Voice skill lives and its name."""
    return s["id"] if "id" in s else f"{s['source']}:{s['name']}"


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
    verified copy (agentfs.import_skill). The original is never changed."""
    entry, folder = find(source_id)
    return agentfs.import_skill(target, entry["folder"], folder)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agentvoice skills",
                                 description="Skills on this machine, and who gets each.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lanes", help="every skill, in its owner's lane")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("import", help="give an agent or Communal a copy of a skill found here")
    p.add_argument("source", help="its id, from `lanes --json`")
    p.add_argument("to", help="an agent's folder id, or communal")
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
        got = import_skill(a.source, a.to)
        print(json.dumps(got))
        return 0
    except (agentfs.AgentFsError, SkillsUnknown) as e:
        from speech_text import safe_for_terminal as safe
        print(f"agentvoice skills: {safe(str(e))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
