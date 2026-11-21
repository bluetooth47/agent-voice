"""Saved conversations: save, browse, continue (plan item 2).

Off unless `saveChats` is switched on. The session's conversation view has
always been memory-only (runtime.History, tmpfs, gone at logout), and that was
a deliberate privacy line, so keeping chats on disk is the user's choice and
never a default.

On disk: `~/.local/share/agentvoice/chats/`, 0700, one file per chat, 0600:

    {"id", "agent_id", "agent_label", "backend", "session_id",
     "project_dir", "title", "started", "updated", "pinned",
     "exchanges": [{"at", "transcript", "reply", "error", "stopped"}]}

Shared chats (merged plan, Phase 15) add, all optional so an older chat
reads exactly as before:

- `owner`: the agent that started it, by external id ("main" for the main
  agent), fixed when the chat is made. `agent_id` stays in step with it,
  still "" for the main agent, for older readers; record() no longer
  overwrites either when another agent speaks.
- each exchange's `agent_id` and `agent_label` (who answered), and
  optionally `kind` ("brief" for a passed conversation's first turn) and
  `for` (the agent it was passed from);
- `sessions`: {agent: {backend, session_id, project_dir}} per speaker. The
  top-level `session_id`, `backend` and `project_dir` remain the owner's.
- `participants`: who has spoken in it. For display; it grants nothing.
- `shared_with`: the agents that may be replayed the transcript besides its
  owner -- those it was shared with, and those it was passed to. The only
  grant of replay.

and `index.json` beside them: every chat without its exchanges, plus which
chat each agent is in right now (`current`), for the conversation view to
watch. A chat knows its agent by the stable id (plan 7c), so renaming an
agent or changing its wake phrase keeps its chats.

The daemon appends as turns end and the CLI renames, pins, deletes and
exports, possibly at the same moment, so every read-modify-write holds an
exclusive lock on `.lock`. Writes go to a temporary file that is renamed
into place, so a reader never sees half a chat.

    python chats.py list | show ID | rename ID TITLE... | pin ID | unpin ID
                   | delete ID | export ID [FOLDER] | prune RETENTION
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paths import DATA_DIR, private_dir  # noqa: E402

CHATS_DIR = DATA_DIR / "chats"
INDEX = "index.json"
#: How long chats are kept. Pinned chats are never pruned.
RETENTIONS = ("forever", "90d", "30d", "last100")
#: A chat's id: random, so it says nothing and cannot be a path.
_CHAT_ID = re.compile(r"[0-9a-f]{16}")
TITLE_MAX = 60
#: A chat that has grown past this keeps its newest exchanges. Several
#: hundred spoken turns is far more than a day of talking to one agent.
EXCHANGES_MAX = 2000
#: How much of a chat is replayed to a backend that cannot resume it.
REPLAY_MAX = 8000
#: Words that say how to find a chat, not which one.
_FILLER = frozenset({
    "the", "a", "an", "about", "on", "of", "our", "my", "that", "this", "chat",
    "conversation", "one", "with", "from", "we", "had", "where", "when", "it",
    "to", "and", "for", "in", "was", "were", "is",
})


#: An agent's external id: "main", or an extra agent's id.
_AGENT = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")


def valid_id(chat_id) -> bool:
    return isinstance(chat_id, str) and bool(_CHAT_ID.fullmatch(chat_id))


def external(agent_id) -> str:
    """The id written into the new fields: "" (the main agent inside the
    daemon) is "main", as agentfs.folder_id has it."""
    return str(agent_id or "") or "main"


def internal(agent_id) -> str:
    """The daemon's id for an external one: "main" is ""."""
    agent_id = str(agent_id or "")
    return "" if agent_id == "main" else agent_id


def _ids(value) -> list[str]:
    """A list of agent ids read from a chat, keeping only well-formed ones,
    each once, in order: a hand-edited chat cannot put anything else here."""
    out = []
    for v in value if isinstance(value, list) else []:
        if isinstance(v, str) and _AGENT.fullmatch(v) and v not in out:
            out.append(v)
    return out


def owner_of(chat: dict) -> str:
    """Who owns `chat`, by external id. A chat from before Phase 15 has no
    `owner`: its `agent_id` is the owner, as it always was."""
    own = chat.get("owner")
    if isinstance(own, str) and _AGENT.fullmatch(own):
        return own
    return external(chat.get("agent_id", ""))


def participants_of(chat: dict) -> list[str]:
    """Who has spoken in `chat`. An older chat has only its owner."""
    found = _ids(chat.get("participants"))
    return found or [owner_of(chat)]


def shared_with(chat: dict) -> list[str]:
    return [a for a in _ids(chat.get("shared_with")) if a != owner_of(chat)]


def sessions_of(chat: dict) -> dict:
    """Each speaker's session in `chat`. An older chat's top-level session
    is its owner's."""
    out = {}
    raw = chat.get("sessions")
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(k, str) and _AGENT.fullmatch(k) and isinstance(v, dict):
                out[k] = {"backend": str(v.get("backend") or ""),
                          "session_id": str(v.get("session_id") or ""),
                          "project_dir": str(v.get("project_dir") or "")}
    own = owner_of(chat)
    if own not in out and chat.get("session_id"):
        out[own] = {"backend": str(chat.get("backend") or ""),
                    "session_id": str(chat.get("session_id") or ""),
                    "project_dir": str(chat.get("project_dir") or "")}
    return out


def may_replay(chat: dict, agent: str) -> bool:
    """Whether `agent` (external id) may be given this chat's transcript:
    its owner and the agents in `shared_with`, and nobody else. Having
    spoken in it grants nothing."""
    return agent == owner_of(chat) or agent in shared_with(chat)


def may_continue(chat: dict, agent: str) -> bool:
    """Whether `agent` may carry this chat on: it may be replayed it, or it
    already has a session in it."""
    return may_replay(chat, agent) or agent in sessions_of(chat)


def who_may_continue(chat: dict) -> list[str]:
    out = [owner_of(chat)]
    for a in shared_with(chat) + list(sessions_of(chat)):
        if a not in out:
            out.append(a)
    return out


def title_from(text: str) -> str:
    """A title from the first request: its first sentence, cut at a word
    boundary to TITLE_MAX characters."""
    text = " ".join(str(text or "").split())
    first = re.split(r"(?<=[.?!])\s", text, maxsplit=1)[0].strip()
    if len(first) <= TITLE_MAX:
        return first.rstrip(".") or "Untitled chat"
    cut = first[:TITLE_MAX].rsplit(" ", 1)[0]
    return (cut or first[:TITLE_MAX]).rstrip(",;:.") + "…"


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", str(text or "").lower().replace("’", "'"))


def clean_title(text) -> str:
    text = " ".join(str(text or "").split())
    return "".join(c for c in text if c.isprintable())[:120].strip()


class ChatStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else CHATS_DIR

    # --- files -------------------------------------------------------------

    @contextlib.contextmanager
    def _locked(self):
        private_dir(self.root)
        fd = os.open(self.root / ".lock", os.O_WRONLY | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _path(self, chat_id: str) -> Path:
        if not valid_id(chat_id):
            raise ValueError("not a chat id")
        return self.root / f"{chat_id}.json"

    def _write_json(self, path: Path, data) -> None:
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)

    def load(self, chat_id: str) -> dict | None:
        try:
            data = json.loads(self._path(chat_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) and data.get("id") == chat_id else None

    @staticmethod
    def _meta(chat: dict) -> dict:
        ex = chat.get("exchanges") or []
        return {
            "id": chat["id"],
            "agent_id": chat.get("agent_id", ""),
            "agent_label": chat.get("agent_label", ""),
            "backend": chat.get("backend", ""),
            "title": chat.get("title", ""),
            "started": chat.get("started", 0),
            "updated": chat.get("updated", 0),
            "pinned": bool(chat.get("pinned")),
            # When it was last moved to a terminal, so the view can say the
            # transcript here stops where the typing began.
            "terminal": chat.get("terminal", 0),
            "count": len(ex),
            # Shared chats (Phase 15): the owner by external id, who has
            # spoken, and who may carry it on, for the filters and the
            # "Agent conversations" list. An older chat has only its owner.
            "owner": owner_of(chat),
            "participants": participants_of(chat),
            "shared_with": shared_with(chat),
            "agents": who_may_continue(chat),
            # For search in the list: the words, not the whole chat.
            "preview": str(ex[-1].get("transcript", ""))[:160] if ex else "",
        }

    def _read_index(self) -> dict:
        try:
            data = json.loads((self.root / INDEX).read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("chats"), list):
                data.setdefault("current", {})
                return data
        except (OSError, ValueError):
            pass
        return self._rebuild()

    def _rebuild(self) -> dict:
        """The index from the chat files themselves, when it is missing or
        damaged: the chats are the record, the index only a listing."""
        chats = []
        for path in self.root.glob("*.json"):
            if path.name == INDEX:
                continue
            chat = self.load(path.stem)
            if chat is not None:
                chats.append(self._meta(chat))
        return {"chats": chats, "current": {}}

    def _save_index(self, index: dict) -> None:
        index["chats"].sort(key=lambda c: c.get("updated", 0), reverse=True)
        self._write_json(self.root / INDEX, index)

    def _upsert(self, index: dict, chat: dict) -> None:
        index["chats"] = [c for c in index["chats"] if c.get("id") != chat["id"]]
        index["chats"].append(self._meta(chat))

    # --- the daemon --------------------------------------------------------

    def record(self, *, chat_id: str | None, agent_id: str, agent_label: str,
               backend: str, session_id: str | None, project_dir: str,
               exchange: dict, now: float | None = None) -> str:
        """Add one exchange: to `chat_id`, or to a new chat when that is None
        or gone. Returns the chat's id, and makes it the agent's current one.

        `agent_id` is the daemon's id of whoever answered ("" for the main
        agent). A new chat is that agent's; in an existing one it is a
        speaker, and the chat's owner, `agent_id`, `agent_label` and
        top-level session stay the owner's (Phase 15: they used to be
        overwritten on every exchange, so a second agent recording into a
        chat would have taken it over). `exchange` may carry `kind` and
        `for` (the agent a passed conversation came from)."""
        now = time.time() if now is None else now
        speaker = external(agent_id)
        with self._locked():
            chat = self.load(chat_id) if valid_id(chat_id) else None
            if chat is None:
                chat = {"id": secrets.token_hex(8), "started": now, "pinned": False,
                        "title": title_from(exchange.get("transcript", "")),
                        "agent_id": agent_id, "agent_label": agent_label,
                        "backend": backend, "project_dir": project_dir,
                        "exchanges": []}
            own = owner_of(chat)
            sessions = sessions_of(chat)
            people = participants_of(chat)
            mine = sessions.get(speaker, {})
            sessions[speaker] = {
                "backend": backend,
                # The previous session is kept when a turn reports none, as
                # the top-level one always was.
                "session_id": str(session_id or mine.get("session_id") or ""),
                "project_dir": project_dir}
            if speaker not in people:
                people.append(speaker)
            chat.update({"owner": own, "sessions": sessions,
                         "participants": people, "updated": now})
            if speaker == own:
                chat.update({"agent_id": agent_id, "agent_label": agent_label,
                             "backend": backend, "project_dir": project_dir})
                if session_id:
                    chat["session_id"] = session_id
            extra = {}
            if exchange.get("kind") in ("brief", "aside"):
                extra["kind"] = exchange["kind"]
            if isinstance(exchange.get("for"), str) and _AGENT.fullmatch(exchange["for"]):
                extra["for"] = exchange["for"]
            if exchange.get("kind") == "aside":
                # A question this speaker asked another agent (Phase 16): who
                # was asked. Grants nothing: the asked agent is no speaker.
                if isinstance(exchange.get("asked"), str) and _AGENT.fullmatch(exchange["asked"]):
                    extra["asked"] = exchange["asked"]
                extra["asked_label"] = str(exchange.get("asked_label") or "")[:80]
            chat["exchanges"] = (chat.get("exchanges") or [])[-(EXCHANGES_MAX - 1):] + [{
                "at": round(now, 1),
                "transcript": str(exchange.get("transcript", "")),
                "reply": str(exchange.get("reply", "")),
                "error": str(exchange.get("error", "")),
                "stopped": bool(exchange.get("stopped")),
                # Who answered (Phase 15), so one transcript can hold several
                # agents' replies, each labelled.
                "agent_id": speaker,
                "agent_label": str(agent_label or ""),
                **extra,
                # A reasoning model's thinking, shown greyed; only when there
                # was some, so chats from other backends are unchanged.
                **({"thinking": str(exchange["thinking"])[:8000]}
                   if exchange.get("thinking") else {}),
            }]
            self._write_json(self._path(chat["id"]), chat)
            index = self._read_index()
            self._upsert(index, chat)
            index["current"][agent_id] = chat["id"]
            self._save_index(index)
            return chat["id"]

    def share(self, chat_id: str, agent: str) -> bool:
        """Let `agent` (external id) be replayed this chat: "Share chat
        with...", and what a pass does to its target. The owner already may;
        sharing with it changes nothing and is not an error."""
        agent = str(agent or "")
        if not _AGENT.fullmatch(agent):
            raise ValueError("not an agent id")

        def add(chat):
            if agent == owner_of(chat):
                return
            have = shared_with(chat)
            if agent not in have:
                chat["shared_with"] = have + [agent]
        return self._change(chat_id, add)

    def unshare(self, chat_id: str, agent: str) -> bool:
        agent = str(agent or "")
        return self._change(chat_id, lambda c: c.update(
            shared_with=[a for a in shared_with(c) if a != agent]))

    def set_current(self, agent_id: str, chat_id: str | None) -> None:
        with self._locked():
            index = self._read_index()
            if chat_id:
                index["current"][agent_id] = chat_id
            else:
                index["current"].pop(agent_id, None)
            self._save_index(index)

    def forget_current(self) -> None:
        """Nobody is in any chat: the daemon has just started, and every
        agent's conversation with it."""
        if not self.root.is_dir():
            return
        with self._locked():
            index = self._read_index()
            if index["current"]:
                index["current"] = {}
                self._save_index(index)

    # --- the conversation view and the CLI ----------------------------------

    def list(self) -> list[dict]:
        with self._locked():
            return list(self._read_index()["chats"])

    def _change(self, chat_id: str, fn) -> bool:
        with self._locked():
            chat = self.load(chat_id)
            if chat is None:
                return False
            fn(chat)
            self._write_json(self._path(chat_id), chat)
            index = self._read_index()
            self._upsert(index, chat)
            self._save_index(index)
            return True

    def rename(self, chat_id: str, title: str) -> bool:
        title = clean_title(title)
        if not title:
            return False
        return self._change(chat_id, lambda c: c.update(title=title))

    def pin(self, chat_id: str, on: bool = True) -> bool:
        return self._change(chat_id, lambda c: c.update(pinned=bool(on)))

    def mark_terminal(self, chat_id: str, now: float | None = None) -> bool:
        """Note that the chat went on in a terminal."""
        when = round(time.time() if now is None else now)
        return self._change(chat_id, lambda c: c.update(terminal=when))

    def delete(self, chat_id: str) -> bool:
        with self._locked():
            path = self._path(chat_id)
            try:
                path.unlink()
            except FileNotFoundError:
                return False
            index = self._read_index()
            index["chats"] = [c for c in index["chats"] if c.get("id") != chat_id]
            index["current"] = {k: v for k, v in index["current"].items() if v != chat_id}
            self._save_index(index)
            return True

    def prune(self, retention: str, now: float | None = None) -> int:
        """Delete what the retention setting no longer keeps. Pinned chats
        and every agent's current chat stay. Returns how many went."""
        if retention not in RETENTIONS or retention == "forever":
            return 0
        now = time.time() if now is None else now
        with self._locked():
            index = self._read_index()
            keep_ids = set(index["current"].values())
            ordered = sorted(index["chats"], key=lambda c: c.get("updated", 0), reverse=True)
            doomed = []
            if retention.endswith("d"):
                cutoff = now - int(retention[:-1]) * 86400
                doomed = [c for c in ordered if c.get("updated", 0) < cutoff]
            elif retention.startswith("last"):
                doomed = ordered[int(retention[4:]):]
            gone = 0
            for c in doomed:
                if c.get("pinned") or c.get("id") in keep_ids:
                    continue
                try:
                    self._path(c["id"]).unlink()
                except (OSError, ValueError, KeyError):
                    pass
                index["chats"] = [x for x in index["chats"] if x.get("id") != c.get("id")]
                gone += 1
            if gone:
                self._save_index(index)
            return gone

    def find(self, query: str, agent_id: str, exclude: str | None = None) -> list[dict]:
        """This agent's chats that match what was said, best first.

        Words in the title count twice what words anywhere in the chat do,
        and filler ("the chat about our...") counts for nothing. An empty
        query is the most recent chat."""
        want = [w for w in _words(query) if w not in _FILLER]
        me = external(agent_id)
        # Its own, and those shared with it or passed to it (Phase 15).
        chats = [c for c in self.list()
                 if c.get("id") != exclude
                 and (c.get("agent_id") == agent_id
                      or me in (c.get("agents") if isinstance(c.get("agents"), list) else []))]
        if not want:
            return chats[:1]
        scored = []
        for meta in chats:
            chat = self.load(meta["id"])
            if chat is None:
                continue
            title = set(_words(chat.get("title", "")))
            body = set()
            for e in chat.get("exchanges") or []:
                body.update(_words(e.get("transcript", "")))
                body.update(_words(e.get("reply", "")))
            score = sum(2 if w in title else 1 if w in body else 0 for w in want)
            if score:
                scored.append((score / (2 * len(want)), meta))
        scored.sort(key=lambda s: (s[0], s[1].get("updated", 0)), reverse=True)
        return [dict(meta, score=round(score, 3)) for score, meta in scored]

    def export_markdown(self, chat_id: str) -> str | None:
        chat = self.load(chat_id)
        if chat is None:
            return None
        who = chat.get("agent_label") or "Agent"
        lines = [f"# {chat.get('title') or 'Chat'}", "",
                 f"{who} · {chat.get('backend') or 'agent'} · "
                 f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(chat.get('started', 0)))}",
                 ""]
        for e in chat.get("exchanges") or []:
            when = time.strftime("%H:%M", time.localtime(e.get("at", 0)))
            if e.get("kind") == "aside":
                asked = e.get("asked_label") or e.get("asked") or "another agent"
                lines += [f"_{e.get('agent_label') or who} asked {asked}_ ({when}): "
                          f"{e.get('transcript', '')}", "",
                          f"**{asked}**: {e.get('reply', '')}", ""]
                continue
            lines += [f"**You** ({when}): {e.get('transcript', '')}", ""]
            reply = e.get("reply", "")
            if reply:
                lines += [f"**{e.get('agent_label') or who}**: {reply}", ""]
            if e.get("error"):
                lines += [f"_failed: {e['error']}_", ""]
            elif e.get("stopped"):
                lines += ["_stopped part-way_", ""]
        return "\n".join(lines)

    def export_to(self, chat_id: str, folder: Path | None = None) -> Path | None:
        """Write the chat as Markdown into `folder` (Documents, else home),
        never over an existing file. Returns where it went."""
        text = self.export_markdown(chat_id)
        if text is None:
            return None
        chat = self.load(chat_id) or {}
        if folder is None:
            docs = Path.home() / "Documents"
            folder = docs if docs.is_dir() else Path.home()
        slug = re.sub(r"[^a-z0-9]+", "-", str(chat.get("title", "")).lower()).strip("-")[:40]
        day = time.strftime("%Y-%m-%d", time.localtime(chat.get("started", 0)))
        base = f"agentvoice-{day}-{slug or 'chat'}"
        path = Path(folder) / f"{base}.md"
        n = 2
        while path.exists():
            path = Path(folder) / f"{base}-{n}.md"
            n += 1
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        return path


def replay_context(chat: dict, max_chars: int = REPLAY_MAX,
                   tail: str = "The user now says:\n") -> str:
    """The chat as text to put ahead of the next request, for a backend
    that cannot resume it natively. The newest exchanges win when it is long.
    Each reply is labelled with the agent that gave it, so a chat several
    agents have spoken in reads as it happened."""
    who = chat.get("agent_label") or "You (the assistant)"
    turns = []
    for e in chat.get("exchanges") or []:
        speaker = e.get('agent_label') or who
        if e.get("kind") == "aside":
            # A question one agent asked another (Phase 16): both halves are
            # agents' words, fenced, so neither can pass for a "User:" line.
            asked = e.get("asked_label") or e.get("asked") or "another agent"
            q = str(e.get("transcript", "")).replace(">>>", "> > >")[:max_chars // 4]
            a = str(e.get("reply", "")).replace(">>>", "> > >")[:max_chars // 4]
            turns.append(f"({speaker} asked {asked} a question; not the user's words:)\n"
                         f"<<<\n{q}\n>>>\n({asked} answered:)\n<<<\n{a}\n>>>")
            continue
        # One exchange longer than the whole budget would otherwise leave
        # nothing at all to replay (Codex review): cut it, keep the rest.
        turns.append(f"User: {str(e.get('transcript', ''))[:max_chars // 2]}\n"
                     f"{speaker}: {str(e.get('reply', ''))[:max_chars // 2]}")
    body = ""
    for turn in reversed(turns):
        if len(body) + len(turn) + 2 > max_chars:
            break
        body = turn + "\n\n" + body
    if not body:
        return ""
    return ("We are continuing an earlier conversation. Here it is, for "
            "context:\n\n" + body.rstrip() + "\n\n" + tail)


def refusal(chat: dict, agent: str) -> str:
    """Why `agent` may not carry `chat` on, in words a person can act on."""
    return (f"That chat isn't shared with {agent}: it has no session in it and "
            f"nobody shared it. Use Share chat with... first, or pass the "
            f"conversation to it.")


def main(argv: list[str]) -> int:
    store = ChatStore()
    if not argv or argv[0] == "list":
        # Titles come from what was said and names are any text: printed to
        # a terminal, either could carry escape sequences.
        from speech_text import safe_for_terminal
        for c in store.list():
            pin = "*" if c.get("pinned") else " "
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(c.get("updated", 0)))
            line = f"{c.get('agent_label', '')}: {c.get('title', '')}"
            print(f"{c['id']} {pin} {when}  {safe_for_terminal(line)}")
        return 0
    verb, rest = argv[0], argv[1:]
    try:
        if verb == "show" and rest:
            text = store.export_markdown(rest[0])
            if text is None:
                raise LookupError
            from speech_text import safe_for_terminal
            print(safe_for_terminal(text))
            return 0
        if verb == "rename" and len(rest) >= 2:
            ok = store.rename(rest[0], " ".join(rest[1:]))
        elif verb in ("pin", "unpin") and rest:
            ok = store.pin(rest[0], verb == "pin")
        elif verb == "delete" and rest:
            ok = store.delete(rest[0])
        elif verb in ("share", "unshare") and len(rest) == 2:
            # By external id ("main" for the main agent).
            ok = (store.share if verb == "share" else store.unshare)(rest[0], rest[1])
        elif verb == "may-continue" and len(rest) == 2:
            # Whether AGENT may carry chat ID on; asked by `agentvoice chats
            # continue ID AGENT` before anything is sent to the daemon, so a
            # refusal is said where it was asked for.
            chat = store.load(rest[0])
            if chat is None:
                raise LookupError
            if may_continue(chat, rest[1]):
                return 0
            print(refusal(chat, rest[1]), file=sys.stderr)
            return 1
        elif verb == "export" and rest:
            where = store.export_to(rest[0], Path(rest[1]).expanduser() if len(rest) > 1 else None)
            if where is None:
                raise LookupError
            print(where)
            return 0
        elif verb == "prune" and rest:
            print(store.prune(rest[0]))
            return 0
        else:
            print("usage: agentvoice chats [list|show ID|rename ID TITLE|pin ID|unpin ID|"
                  "delete ID|export ID [FOLDER]|share ID AGENT|unshare ID AGENT|"
                  "continue ID [AGENT]|new [AGENT]]", file=sys.stderr)
            return 2
        if not ok:
            raise LookupError
        return 0
    except (LookupError, ValueError):
        print("no such chat", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
