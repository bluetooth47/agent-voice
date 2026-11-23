"""Duplicate an agent, or reset one to its defaults (phase M17).

Both live on Agent details → Advanced, beside Export and Remove. The folder
work is agentfs's (duplicate_folder, reset_folder, undo_reset), under its
lock and its rule against links; this module decides what the settings
entry of the result holds, because that is where a copy could carry more
than it should.

**Duplicate** makes a new agent: a new stable id, a wake phrase of its own,
switched off until the person turns it on (a phrase picked here may not be
one a wake engine hears well, and a second agent answering the moment it is
made would be a surprise). It gets the original's program, model, effort,
voice, folder and launch timings, and a copy of its role, personality,
instructions and skills. It gets **no grant**: the permission level is Ask,
no tool is switched on for it, no crew link names it, no chat is shared
with it and no session is its. Restrictions the original carries do come
with it -- a tool switched off, a skill switched off, notes denied,
collaboration off or ask, work refused -- so a copy never has more than
either the original or a new agent would. Not copied at all: its extra
flags (each one was confirmed for that agent) and its environment
variables (secrets stay with the agent they were given to). A quarantined
agent is not copied: the copy would carry its folder out of quarantine.

**Reset** keeps who the agent is -- its id, name, wake phrase, whether it
is switched on, its chats and crew links -- and puts everything else back
as a new agent has it: the starting templates in its folder, and in its
settings Claude Code, no model or effort of its own, the main agent's
voice, Ask, no tool or skill switched, the default collaboration, no
extra flags. Its folder and settings go to the trash first, so Restore (or
the Undo) puts it back whole; its environment variables are not touched
(they are not in the trash, so nothing could bring them back).
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agentfs  # noqa: E402
from runtime import (  # noqa: E402
    MAX_AGENTS, accepts_choice, agent_id_for, collab_choice, display_name, notes_choice,
)

#: What a new agent's entry holds, as the Agents page's Add writes it.
NEW_AGENT = {"agent": "claude", "model": "", "effort": "", "voice": "", "speed": 0,
             "narration": "", "level": "ask", "projectDir": ""}

#: Taken from the original as they are: what it runs and how it sounds,
#: none of them a grant.
COPIED = ("agent", "model", "effort", "voice", "speed", "narration", "projectDir",
          "endpointUrl", "endpointModel", "endpointIsAgent", "endpointTimeoutS",
          "endpointHistoryTurns", "resume", "idleTimeoutS")

#: Words for a copy's wake phrase after the original's last word.
_COPY_WORDS = ("copy", "second copy", "third copy", "fourth copy", "fifth copy",
               "sixth copy", "seventh copy", "eighth copy", "ninth copy")

_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")


class Refused(Exception):
    """Why this agent cannot be duplicated or reset, in words."""


def duplicate_entry(source: dict, new_id: str, name: str, label: str) -> dict:
    """The settings entry for a copy of `source` (an entry as saved), under
    `new_id`, woken by `name`, called `label`: switched off, its grants at a
    new agent's, and every restriction the original carries kept."""
    out = {"id": new_id, "name": name, "label": label, "enabled": False, **NEW_AGENT}
    for key in COPIED:
        if key in source:
            out[key] = source[key]
    # Never more than a new agent may: Ask, whatever the original had.
    out["level"] = "ask"
    tools = source.get("tools")
    if isinstance(tools, dict):
        # A switch saying off stays off; one saying on is not copied, so the
        # copy follows the settings for every agent, as a new one does.
        off = {k: "off" for k, v in tools.items() if isinstance(k, str) and v == "off"}
        if off:
            out["tools"] = off
    if "skillsOff" in source:
        # As written, even when it cannot be read: an unreadable list
        # withholds skills, and a copy keeps that rather than lifting it.
        out["skillsOff"] = source["skillsOff"]
    if notes_choice(source, "notesWrite") == "deny":
        out["notesWrite"] = "deny"
    collab = collab_choice(source, "collaboration")
    if collab in ("off", "ask"):
        out["collaboration"] = collab
    if not accepts_choice(source, "acceptsWork"):
        out["acceptsWork"] = False
    return out


def reset_entry(entry: dict) -> dict:
    """`entry` back to a new agent's settings, keeping its id, wake phrase,
    name and on/off switch."""
    out = {"id": entry.get("id"), "name": entry.get("name", ""), "label": entry.get("label", ""),
           **NEW_AGENT}
    if entry.get("enabled") is False:
        out["enabled"] = False
    return out


def main_entry(cfg) -> dict:
    """The main agent's settings in the shape of an extra agent's entry, for
    a copy of it. Its program as the main agent runs it now (its own
    setting, else Omarchy's default), or its endpoint."""
    from adapters import main_program
    out: dict = {"name": cfg.get_str("phrase"), "label": cfg.get_str("mainName")}
    endpoint = cfg.main_endpoint()
    if endpoint:
        out.update(agent="endpoint", endpointUrl=endpoint["url"], endpointModel=endpoint["model"],
                   endpointIsAgent=endpoint["is_agent"], endpointTimeoutS=endpoint["timeout_s"],
                   endpointHistoryTurns=endpoint["history_turns"])
    else:
        program = main_program(cfg.get_str("mainProgram")) or "claude"
        out.update(agent=program, model=cfg.model_for(program) or "",
                   effort=cfg.effort_for(program) or "")
    out.update(voice=cfg.get_str("voice"), projectDir=cfg.get_str("projectDir"))
    raw = cfg._values
    for key, field in (("mainTools", "tools"), ("mainSkillsOff", "skillsOff"),
                       ("mainNotesWrite", "notesWrite"), ("mainCollaboration", "collaboration"),
                       ("mainAcceptsWork", "acceptsWork"), ("mainResume", "resume"),
                       ("mainIdleTimeoutS", "idleTimeoutS")):
        if key in raw:
            out[field] = raw[key]
    return out


def _raw_entries(cfg) -> list[dict]:
    raw = cfg["voiceAgents"]
    return [e for e in raw if isinstance(e, dict)] if isinstance(raw, list) else []


def _entry_id(entry: dict) -> str:
    raw = entry.get("id")
    raw = raw.strip() if isinstance(raw, str) else ""
    if _ID.fullmatch(raw) and raw != "main":
        return raw
    return agent_id_for(" ".join(str(entry.get("name") or "").lower().split()))


def source_entry(agent_id: str, cfg) -> dict:
    """The entry an agent's copy is made from: an extra agent's as saved,
    or the main agent's as main_entry() puts it."""
    if agent_id in ("", "main"):
        return main_entry(cfg)
    for entry in _raw_entries(cfg):
        if _entry_id(entry) == agent_id:
            return entry
    raise Refused(f"there is no agent {agent_id!r} in the settings")


def copy_name(source_name: str, taken: set[str]) -> str:
    """A wake phrase for a copy: the original's last word and "copy" (one to
    three plain words, as every wake phrase), the first not `taken`."""
    words = [w for w in re.sub(r"[^a-z ]", " ", str(source_name or "").lower()).split() if w]
    last = (words[-1] if words else "agent")[:18]
    for tail in _COPY_WORDS:
        name = f"{last} {tail}"
        if name not in taken:
            return name
    raise Refused("every name for a copy is taken; rename one of the copies first")


def new_id(name: str, taken: set[str]) -> str:
    """A fresh id: the name and a few random letters, as the Agents page
    makes one, so a copy never inherits anything keyed by an old id."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "agent"
    while True:
        out = f"{base}-{secrets.randbelow(46656):x}"
        if out not in taken and not os.path.lexists(agentfs._base(out)):
            return out


def duplicate(agent_id: str, cfg) -> dict:
    """Copy agent `agent_id` ("main" for the main agent): its folder (agentfs
    .duplicate_folder) and the entry for the settings, which the caller
    saves. Returns {"entry", "skills", "left"}. Refused for a quarantined
    agent, while the quarantine list cannot be read, with no room for one
    more agent, or when settings cannot be read."""
    if not cfg.settings_readable():
        raise Refused("the settings cannot be read, so nothing can be copied from them")
    quarantined = cfg.quarantined()
    if quarantined is None:
        raise Refused("the quarantine list cannot be read, so no agent is copied until it can")
    if (agent_id or "main") in quarantined:
        raise Refused("it is quarantined: a copy would carry its folder out of quarantine. "
                      "Release it on the Crew map first")
    entries = _raw_entries(cfg)
    if len(entries) >= MAX_AGENTS:
        raise Refused(f"there are already {MAX_AGENTS} agents; remove one first")
    source = source_entry(agent_id, cfg)
    taken = {" ".join(str(e.get("name") or "").lower().split()) for e in entries}
    taken.add(" ".join(cfg.get_str("phrase").lower().split()))
    name = copy_name(source.get("name") or "", taken)
    ids = {_entry_id(e) for e in entries} | {"main", agentfs.COMMUNAL}
    fresh = new_id(name, ids)
    label = display_name(source.get("label"), source.get("name") or name)
    label = (label[:35].rstrip() + " copy") if label else ""
    entry = duplicate_entry(source, fresh, name, label)
    folder = agentfs.duplicate_folder("main" if agent_id in ("", "main") else agent_id, fresh)
    return {"entry": entry, "skills": folder["skills"], "left": folder["left"]}


def reset(agent_id: str, settings_json: str) -> dict:
    """Reset an extra agent: its folder and its saved entry (`settings_json`,
    as the page holds it) to the trash, a fresh folder in its place, and the
    entry for the settings, which the caller saves. {"trash", "entry"}."""
    if agent_id in ("", "main"):
        raise Refused("the main agent cannot be reset here: it cannot go to the trash, "
                      "so nothing could undo it")
    try:
        entry = json.loads(settings_json) if settings_json.strip() else None
    except ValueError:
        entry = None
    if not isinstance(entry, dict) or not str(entry.get("name") or "").strip():
        raise Refused("its settings entry did not arrive, so it was not reset")
    if _entry_id(entry) != agent_id:
        raise Refused("the settings entry is another agent's, so nothing was reset")
    done = agentfs.reset_folder(agent_id, settings_json)
    return {"trash": done["trash"], "entry": reset_entry({**entry, "id": agent_id})}


def cli(a) -> int:
    """`agentvoice agents duplicate ID | reset ID [--line] | unreset NAME`."""
    try:
        if a.cmd == "duplicate":
            from runtime import Config
            print(json.dumps(duplicate(a.id, Config()), ensure_ascii=False))
        elif a.cmd == "reset":
            raw = (sys.stdin.readline(agentfs.SETTINGS_CAP + 1) if a.line
                   else sys.stdin.read(agentfs.SETTINGS_CAP + 1))
            print(json.dumps(reset(a.id, raw), ensure_ascii=False))
        elif a.cmd == "unreset":
            print(json.dumps(agentfs.undo_reset(a.name), ensure_ascii=False))
    except Refused as e:
        print(f"agentvoice agents: {e}", file=sys.stderr)
        return 1
    except agentfs.AgentFsError as e:
        print(f"agentvoice agents: {e}", file=sys.stderr)
        return 1
    return 0
