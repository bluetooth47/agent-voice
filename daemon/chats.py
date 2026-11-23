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

    python chats.py list | show ID | rename ID [TITLE...] | pin ID | unpin ID
                   | delete ID | delete --all | export ID [FOLDER]
                   | prune RETENTION | stats [--json] | last --json
                   | search [--agent ID] [--json]

`rename ID` with no title, and `search`, read their text from stdin (phase
M18): a title is often the first sentence somebody said, and a search is
what they are looking for, and argv is readable by every local account.

Deleting (phase M18): `delete --all` removes every chat file in this folder
and nothing a link points at, and writes `purged` into the index; a single
delete writes the chat's id into `deleted` for an hour. A turn that began
before either and ends after it is not saved (`record(began=...)`), so a
save already in flight never puts back what was just deleted.

Names and summaries (phase M19, chat_names.py) add, all optional:

- `instant_title`: the first-sentence title the chat was made with. `title`
  starts as the same text and is what a rename writes, so an older build
  still shows the right one; `renamed` is set by a rename from here on.
- `auto_title` and `summary`: written by the chat's own agent once the chat
  has gone quiet. `display_title` decides what is shown: **a rename always
  wins**, then the written name, then the first sentence.
- `named_for` / `named_at`: the `updated` the last name was written (or
  tried) for, and when -- at most one side turn per chat per change.

`search` takes filters (`agent:NAME`, `before:DATE`, `after:DATE`) among the
words; see parse_query.
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
#: How long a deleted chat's id is remembered, so a turn that was already
#: running into it is not saved into a new chat (phase M18). Longer than the
#: longest a turn may run (the hung-turn limit is at most 600 s).
DELETED_KEEP_S = 3600
#: A search, read from stdin: longer than anyone types into a box.
QUERY_MAX = 500
#: The names a chat file, and the temporary file it is written through, have
#: in the folder. Nothing else there is a chat, and nothing else is deleted.
_CHAT_FILE = re.compile(r"[0-9a-f]{16}\.json")
_TEMP_FILE = re.compile(r"\.(?:[0-9a-f]{16}|index)\.json\.\d+\.tmp")
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


def _first_transcript(chat: dict) -> str:
    ex = chat.get("exchanges") or []
    first = ex[0] if ex and isinstance(ex[0], dict) else {}
    return str(first.get("transcript", ""))


def instant_title(chat: dict) -> str:
    """The first-sentence title the chat was made with: stored since M19,
    worked out from its first request before that."""
    have = chat.get("instant_title")
    if isinstance(have, str) and have:
        return have
    return title_from(_first_transcript(chat))


def user_renamed(chat: dict) -> bool:
    """Whether the person has named this chat. `renamed` since M19; and a
    title that is not the one the chat was made with was typed by somebody
    -- a rename before M19, or by an older build after it -- so it counts
    too. Unsure means renamed: the person's words are never hidden behind
    a written name."""
    if chat.get("renamed") is True:
        return True
    title = chat.get("title")
    return isinstance(title, str) and bool(title) and title != instant_title(chat)


def display_title(chat: dict) -> str:
    """The title shown and spoken: the person's rename, else the name the
    chat's agent wrote (phase M19), else the first sentence."""
    title = str(chat.get("title") or "")
    if user_renamed(chat):
        return title
    auto = chat.get("auto_title")
    if isinstance(auto, str) and auto.strip():
        return auto
    return title or instant_title(chat) or "Untitled chat"


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", str(text or "").lower().replace("’", "'"))


def clean_title(text) -> str:
    text = " ".join(str(text or "").split())
    return "".join(c for c in text if c.isprintable())[:120].strip()


def _when(meta) -> float:
    """A chat's `updated`, for sorting: a hand-edited index can hold anything
    there, and one bad value must not stop every save (found in M18)."""
    at = meta.get("updated") if isinstance(meta, dict) else None
    return float(at) if isinstance(at, (int, float)) and not isinstance(at, bool) else 0.0


def wanted_words(query: str) -> list[str]:
    """The words of a search that say which chat, filler left out."""
    return [w for w in _words(query) if w not in _FILLER]


def score(chat: dict, want: list[str], prefix_last: bool = False) -> float:
    """How well `chat` matches the words `want`, from 0 to 1: a word in the
    title counts twice what a word anywhere in the chat does. With
    `prefix_last`, the last word also matches the start of a word, for a
    search box being typed into ("wak" finds "wake")."""
    if not want:
        return 0.0
    # Every name the chat has had counts as a title (phase M19): what the
    # person called it, what its agent wrote, and the first sentence.
    auto = chat.get("auto_title") if isinstance(chat.get("auto_title"), str) else ""
    summ = chat.get("summary") if isinstance(chat.get("summary"), str) else ""
    texts = []
    for e in chat.get("exchanges") or []:
        if isinstance(e, dict):
            texts.append(str(e.get("transcript", "")))
            texts.append(str(e.get("reply", "")))
    head = f"{chat.get('title', '')}\n{auto}"
    # One string, one pass (phase M19, measured over 1000 chats): a word
    # that is not even a substring of the chat cannot be one of its words,
    # so most chats are passed over without being split at all.
    body = "\n".join(texts).lower().replace("’", "'")
    names = f"{head}\n{summ}".lower().replace("’", "'")
    if not any(w in body or w in names for w in want):
        return 0.0
    title = set(_words(head))
    summary = set(_words(summ))

    def in_body(w: str, prefix: bool) -> bool:
        # A search, not a split: no list of every word in the chat is built.
        edge = r"(?<![a-z0-9'])" + re.escape(w) + ("" if prefix else r"(?![a-z0-9'])")
        return w in body and re.search(edge, body) is not None

    got = 0.0
    for i, w in enumerate(want):
        if prefix_last and i == len(want) - 1:
            got += (2 if any(t.startswith(w) for t in title)
                    else 1.5 if any(t.startswith(w) for t in summary)
                    else 1 if in_body(w, True) else 0)
        else:
            got += 2 if w in title else 1.5 if w in summary else 1 if in_body(w, False) else 0
    return got / (2 * len(want))


# --- search filters (phase M19) -----------------------------------------------

_FILTER = re.compile(r'(?<!\S)(agent|before|after):(?:"([^"]*)"|(\S*))', re.I)
#: A relative date: 3d, 2w (days or weeks ago).
_AGO = re.compile(r"(\d{1,4})([dw])")


def _day_start(y: int, m: int, d: int) -> float:
    return time.mktime((y, m, d, 0, 0, 0, 0, 0, -1))


def parse_date(value: str, now: float | None = None) -> float | None:
    """The local midnight a search date names, as a timestamp: 2026-11-01,
    2026-11 (its first day), today, yesterday, 3d or 2w (days or weeks ago).
    None when it is none of those."""
    now = time.time() if now is None else now
    v = str(value or "").strip().lower()
    lt = time.localtime(now)
    try:
        if v in ("today", "yesterday"):
            base = _day_start(lt.tm_year, lt.tm_mon, lt.tm_mday)
            return base if v == "today" else _day_start(lt.tm_year, lt.tm_mon, lt.tm_mday - 1)
        m = _AGO.fullmatch(v)
        if m:
            days = int(m.group(1)) * (7 if m.group(2) == "w" else 1)
            return _day_start(lt.tm_year, lt.tm_mon, lt.tm_mday - days)
        m = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-(\d{1,2}))?", v)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
            if 1 <= mo <= 12 and 1 <= d <= 31 and 1970 <= y <= 9999:
                time.strptime(f"{y:04d}-{mo:02d}-{d:02d}", "%Y-%m-%d")   # a real day
                return _day_start(y, mo, d)
    except (ValueError, OverflowError):
        return None
    return None


def parse_query(query: str, now: float | None = None) -> tuple[str, dict, list[str]]:
    """A search split into (the words, the filters, what could not be read).

    Filters: `agent:NAME` (an id or a name, `agent:"Two words"`; more than
    one means any of them), `after:DATE` (used on or after that day) and
    `before:DATE` (started before it); see parse_date. A filter that cannot
    be read is left out and named in the third part, so the list can say so
    rather than quietly widen."""
    filters: dict = {}
    problems: list[str] = []

    def take(m):
        kind, value = m.group(1).lower(), (m.group(2) if m.group(2) is not None else m.group(3))
        value = " ".join(str(value or "").split())
        if kind == "agent":
            if value:
                filters.setdefault("agent", []).append(value)
            else:
                problems.append("agent: needs a name")
        else:
            at = parse_date(value, now)
            if at is None:
                problems.append(f"{kind}: needs a date like 2026-11-01, today or 7d")
            elif kind == "after":
                filters["after"] = max(at, filters.get("after", at))
            else:
                filters["before"] = min(at, filters.get("before", at))
        return " "

    words = _FILTER.sub(take, str(query or ""))
    return " ".join(words.split()), filters, problems


def _norm(name) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).split())


def agent_matches(chat_meta: dict, chat: dict | None, wanted: list[str],
                  names: dict | None = None) -> bool:
    """Whether a chat is one of `wanted`'s: one of them owns it or has spoken
    in it, as the Chats page's agent chips have it. Each name is an agent's
    id, its name now (`names`: normalised name -> id, from the settings) or
    a name it answered under in this chat."""
    ids = {str(chat_meta.get("owner") or "")} | set(chat_meta.get("participants") or [])
    labels = {_norm(chat_meta.get("agent_label"))}
    for e in (chat or {}).get("exchanges") or []:
        if isinstance(e, dict) and e.get("kind") != "aside" and e.get("agent_label"):
            if e.get("agent_id") in ids or not e.get("agent_id"):
                labels.add(_norm(e.get("agent_label")))
    labels.discard("")
    for w in wanted:
        n = _norm(w)
        if not n:
            continue
        if n.replace(" ", "-") in ids or n in labels:
            return True
        if names and names.get(n) in ids:
            return True
    return False


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
            # What is shown (phase M19): a rename, else the written name,
            # else the first sentence. `auto` says the written name is it.
            "title": display_title(chat),
            "auto": not user_renamed(chat) and isinstance(chat.get("auto_title"), str)
                    and bool(chat.get("auto_title", "").strip()),
            "renamed": user_renamed(chat),
            "summary": chat.get("summary", "") if isinstance(chat.get("summary"), str) else "",
            "named_for": chat.get("named_for", 0),
            "named_at": chat.get("named_at", 0),
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
        index["chats"].sort(key=_when, reverse=True)
        self._write_json(self.root / INDEX, index)

    def _deleted_at(self, chat_id: str | None) -> float:
        """When every chat, or `chat_id`, was last deleted; 0 for never.
        Read under the lock. A damaged value counts as never: it can only
        keep a turn from being saved, never put a chat back."""
        try:
            data = json.loads((self.root / INDEX).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0.0
        if not isinstance(data, dict):
            return 0.0
        at = data.get("purged")
        at = float(at) if isinstance(at, (int, float)) else 0.0
        gone = data.get("deleted")
        if valid_id(chat_id) and isinstance(gone, dict):
            one = gone.get(chat_id)
            if isinstance(one, (int, float)):
                at = max(at, float(one))
        return at

    def _upsert(self, index: dict, chat: dict) -> None:
        index["chats"] = [c for c in index["chats"] if c.get("id") != chat["id"]]
        index["chats"].append(self._meta(chat))

    # --- the daemon --------------------------------------------------------

    def record(self, *, chat_id: str | None, agent_id: str, agent_label: str,
               backend: str, session_id: str | None, project_dir: str,
               exchange: dict, now: float | None = None,
               began: float | None = None) -> str | None:
        """Add one exchange: to `chat_id`, or to a new chat when that is None
        or gone. Returns the chat's id, and makes it the agent's current one.

        `agent_id` is the daemon's id of whoever answered ("" for the main
        agent). A new chat is that agent's; in an existing one it is a
        speaker, and the chat's owner, `agent_id`, `agent_label` and
        top-level session stay the owner's (Phase 15: they used to be
        overwritten on every exchange, so a second agent recording into a
        chat would have taken it over). `exchange` may carry `kind` and
        `for` (the agent a passed conversation came from).

        `began`: when the turn started. A turn that began before every chat
        was deleted, or before `chat_id` was, is not saved and None comes
        back (phase M18): its exchange belongs to what was deleted, and
        saving it would start that history again."""
        now = time.time() if now is None else now
        speaker = external(agent_id)
        with self._locked():
            if began is not None and began <= self._deleted_at(chat_id):
                return None
            chat = self.load(chat_id) if valid_id(chat_id) else None
            if chat is None:
                first = title_from(exchange.get("transcript", ""))
                chat = {"id": secrets.token_hex(8), "started": now, "pinned": False,
                        "title": first, "instant_title": first,
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
            # "unprompted" (master plan M27): what an agent said by itself
            # when background work finished; there is no transcript.
            if exchange.get("kind") in ("brief", "aside", "unprompted"):
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

    def detach(self, agent: str) -> int:
        """Phase M8: `agent` (external id) has just been quarantined. Every
        chat it does not own stops being shared with it, and every chat --
        its own included -- forgets its session there, so nothing replays
        or resumes into it what it could see before. Releasing it later
        puts none of this back. Its own chats stay its own; who spoke in a
        chat is history and stays. Returns how many chats changed. Every
        chat file is read, not the index, which is only a listing."""
        agent = str(agent or "")
        if not _AGENT.fullmatch(agent) or not self.root.is_dir():
            return 0
        changed = 0
        with self._locked():
            index = self._read_index()
            for path in sorted(self.root.glob("*.json")):
                if path.name == INDEX:
                    continue
                chat = self.load(path.stem)
                if chat is None:
                    continue
                touched = False
                if agent in shared_with(chat):
                    chat["shared_with"] = [a for a in shared_with(chat) if a != agent]
                    touched = True
                raw = chat.get("sessions")
                if isinstance(raw, dict) and agent in raw:
                    del raw[agent]
                    touched = True
                if owner_of(chat) == agent and chat.get("session_id"):
                    # An older chat keeps its owner's session at the top.
                    chat["session_id"] = ""
                    touched = True
                if touched:
                    self._write_json(path, chat)
                    self._upsert(index, chat)
                    changed += 1
            index["current"].pop(internal(agent), None)
            self._save_index(index)
        return changed

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
        # Phase M19: said so, so the name the chat's agent writes never
        # takes its place, even a rename to the first sentence's words.
        return self._change(chat_id, lambda c: c.update(title=title, renamed=True))

    def set_name(self, chat_id: str, *, for_updated: float, at: float,
                 title: str = "", summary: str = "") -> bool:
        """Phase M19: store what the chat's agent wrote -- `auto_title` and
        `summary`, when there is a title -- and that the chat was named (or
        tried) for the version last changed at `for_updated`. Never touches
        `title`, so a rename stays the person's. False when the chat is gone:
        a name never brings a deleted chat back."""
        from chat_names import SUMMARY_MAX, TITLE_MAX, clean
        title, summary = clean(title, TITLE_MAX), clean(summary, SUMMARY_MAX)

        def put(c):
            c["named_for"], c["named_at"] = for_updated, at
            if title:
                c["auto_title"] = title
                c["summary"] = summary
        return self._change(chat_id, put)

    def pin(self, chat_id: str, on: bool = True) -> bool:
        return self._change(chat_id, lambda c: c.update(pinned=bool(on)))

    def mark_terminal(self, chat_id: str, now: float | None = None) -> bool:
        """Note that the chat went on in a terminal."""
        when = round(time.time() if now is None else now)
        return self._change(chat_id, lambda c: c.update(terminal=when))

    def delete(self, chat_id: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self._locked():
            path = self._path(chat_id)
            try:
                path.unlink()
            except FileNotFoundError:
                return False
            index = self._read_index()
            index["chats"] = [c for c in index["chats"] if c.get("id") != chat_id]
            index["current"] = {k: v for k, v in index["current"].items() if v != chat_id}
            # Phase M18: a turn still running into it is not saved into a
            # new chat (record's `began`). Kept an hour, then forgotten.
            gone = index.get("deleted") if isinstance(index.get("deleted"), dict) else {}
            gone = {k: v for k, v in gone.items()
                    if valid_id(k) and isinstance(v, (int, float)) and v > now - DELETED_KEEP_S}
            # Exact, not rounded: rounded down it could fall below the start
            # of a turn sent within the same millisecond, and miss it.
            gone[chat_id] = now
            index["deleted"] = gone
            self._save_index(index)
            return True

    def delete_all(self, now: float | None = None) -> int:
        """Delete every saved chat (phase M18, "Delete all saved chats").
        Returns how many chat files went.

        Only what this store writes, directly in its folder: `<id>.json`
        files and the temporary files they are written through. A link
        there is removed as a link, never followed, so nothing outside the
        folder is touched and it is not counted; a folder or any other name
        is left alone. The index is rewritten empty with `purged`, under the
        lock the daemon takes, so a save in flight either lands before this
        (and goes with the rest) or is refused after it (record's `began`).
        The folder itself stays, and a missing one is not created."""
        now = time.time() if now is None else now
        if not self.root.is_dir() or self.root.is_symlink():
            return 0
        with self._locked():
            gone = 0
            with os.scandir(self.root) as entries:
                for entry in entries:
                    name = entry.name
                    if not (_CHAT_FILE.fullmatch(name) or _TEMP_FILE.fullmatch(name)):
                        continue
                    if name == INDEX:
                        continue
                    try:
                        if entry.is_symlink():
                            os.unlink(entry.path)        # the link, not its target
                        elif entry.is_file(follow_symlinks=False):
                            os.unlink(entry.path)
                            gone += 1 if _CHAT_FILE.fullmatch(name) else 0
                    except FileNotFoundError:
                        pass
            self._write_json(self.root / INDEX, {"chats": [], "current": {},
                                                 "purged": now})
            return gone

    def stats(self) -> dict:
        """Where the chats are and what they take up, for the Chats page.
        Read without the lock and without creating anything. Only regular
        files count, by lstat: a link is not followed and not counted, so a
        link to something large does not make the chats look large."""
        out = {"dir": str(self.root), "exists": False, "chats": 0, "pinned": 0,
               "bytes": 0}
        if not self.root.is_dir() or self.root.is_symlink():
            return out
        out["exists"] = True
        try:
            with os.scandir(self.root) as entries:
                for entry in entries:
                    try:
                        st = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    out["bytes"] += st.st_size
                    if _CHAT_FILE.fullmatch(entry.name):
                        out["chats"] += 1
        except OSError:
            return out
        try:
            index = json.loads((self.root / INDEX).read_text(encoding="utf-8"))
            out["pinned"] = sum(1 for c in index.get("chats", [])
                                if isinstance(c, dict) and c.get("pinned") is True)
        except (OSError, ValueError, AttributeError):
            pass
        return out

    def last_by_owner(self) -> dict:
        """Master plan M21, the Overview's "last chat →": for each agent, by
        external id, the id of the newest chat it owns -- only one whose
        file is there, so the link never opens nothing. Ids only: a title is
        what somebody said. Read without the lock, creating nothing."""
        out: dict = {}
        if not self.root.is_dir() or self.root.is_symlink():
            return out
        try:
            index = json.loads((self.root / INDEX).read_text(encoding="utf-8"))
            metas = index.get("chats") if isinstance(index, dict) else None
        except (OSError, ValueError):
            metas = None
        if not isinstance(metas, list):
            metas = self._rebuild()["chats"]
        for meta in sorted((m for m in metas if isinstance(m, dict)), key=_when, reverse=True):
            cid, own = meta.get("id"), meta.get("owner") or external(meta.get("agent_id", ""))
            if not (isinstance(cid, str) and valid_id(cid)) or not isinstance(own, str) \
                    or not _AGENT.fullmatch(own) or own in out:
                continue
            try:
                if (self.root / f"{cid}.json").is_file() and not (self.root / f"{cid}.json").is_symlink():
                    out[own] = cid
            except OSError:
                continue
        return out

    def search(self, query: str, agent: str | None = None, limit: int = 200,
               names: dict | None = None, problems: list | None = None,
               now: float | None = None, may_see=None) -> list[dict]:
        """Every saved chat that matches `query`, best first, for the search
        box on the Chats page (phase M18): the scorer `find` uses, with the
        last word also matching the start of a word. `agent` (external id)
        keeps the chats it owns, has spoken in or has been shared; None keeps
        all of them -- the person sees every chat. [{"id", "score"}].

        Phase M19: the query may hold filters (parse_query): `agent:NAME`,
        `before:DATE`, `after:DATE`. With filters and no words, every chat
        that passes them, newest first. A filter that cannot be read is
        described in `problems` and left out. `names` (normalised name ->
        id) may be a function, called only when an `agent:` filter is there.

        Phase M20: `may_see(chat)` -> bool, for an agent's chat search. It is
        asked of the index entry and again of the chat file, and a chat it
        refuses is passed over *before* any filter, score or count reads it,
        so it adds nothing to anything this returns. Both must say yes: the
        index is only a listing, and a stale one can only hide more."""
        text, filters, bad = parse_query(str(query or "")[:QUERY_MAX], now)
        if problems is not None:
            problems.extend(bad)
        want = wanted_words(text)
        # Nothing saved: nothing to find, and no folder made by looking.
        if (not want and not filters) or not self.root.is_dir():
            return []
        # The settings are read for names only when a name is asked for.
        if callable(names):
            names = names() if "agent" in filters else None
        scored = []
        for meta in self.list():
            if not valid_id(meta.get("id")):
                continue
            chat = None
            if may_see is not None:
                # First, before anything else is read out of it (phase M20).
                if not may_see(meta):
                    continue
                chat = self.load(meta["id"])
                if chat is None or not may_see(chat):
                    continue
            if agent is not None:
                people = set(meta.get("participants") or []) | set(meta.get("agents") or [])
                if agent != meta.get("owner") and agent not in people:
                    continue
            if "after" in filters and _when(meta) < filters["after"]:
                continue
            if "before" in filters:
                began = meta.get("started")
                began = float(began) if isinstance(began, (int, float)) \
                    and not isinstance(began, bool) else _when(meta)
                if began >= filters["before"]:
                    continue
            if chat is None:
                chat = self.load(meta["id"])
            if chat is None:
                continue
            if "agent" in filters and not agent_matches(meta, chat, filters["agent"], names):
                continue
            got = score(chat, want, prefix_last=True) if want else 1.0
            if got:
                scored.append((got, _when(meta), meta["id"]))
        scored.sort(reverse=True)
        return [{"id": cid, "score": round(got, 3)} for got, _, cid in scored[:limit]]

    @staticmethod
    def _doomed(index: dict, retention: str, now: float) -> list[dict]:
        """The index entries the retention setting no longer keeps: older
        than its days, or past its count, newest first -- pinned chats and
        every agent's current chat aside. One rule for prune(), which
        deletes them, and expired(), which an agent's chat search reads
        (phase M20): a chat waiting for the next prune is already gone."""
        if retention not in RETENTIONS or retention == "forever":
            return []
        # Strings only: a hand-edited value that is not one must not stop
        # the rule from being worked out (a set of a list would raise).
        current = index.get("current") if isinstance(index.get("current"), dict) else {}
        keep_ids = {v for v in current.values() if isinstance(v, str)}
        ordered = sorted(index["chats"], key=_when, reverse=True)
        doomed = []
        if retention.endswith("d"):
            cutoff = now - int(retention[:-1]) * 86400
            doomed = [c for c in ordered if _when(c) < cutoff]
        elif retention.startswith("last"):
            doomed = ordered[int(retention[4:]):]
        return [c for c in doomed if isinstance(c, dict)
                and not c.get("pinned") and c.get("id") not in keep_ids]

    def expired(self, retention: str, now: float | None = None) -> frozenset:
        """The ids of the chats the next prune would delete (phase M20).
        Creates nothing."""
        now = time.time() if now is None else now
        if retention not in RETENTIONS or retention == "forever" or not self.root.is_dir():
            return frozenset()
        with self._locked():
            return frozenset(str(c.get("id")) for c in self._doomed(self._read_index(),
                                                                     retention, now))

    def prune(self, retention: str, now: float | None = None) -> int:
        """Delete what the retention setting no longer keeps. Pinned chats
        and every agent's current chat stay. Returns how many went."""
        if retention not in RETENTIONS or retention == "forever":
            return 0
        now = time.time() if now is None else now
        with self._locked():
            index = self._read_index()
            gone = 0
            for c in self._doomed(index, retention, now):
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
        want = wanted_words(query)
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
            got = score(chat, want)
            if got:
                scored.append((got, meta))
        scored.sort(key=lambda s: (s[0], _when(s[1])), reverse=True)
        return [dict(meta, score=round(got, 3)) for got, meta in scored]

    def export_markdown(self, chat_id: str) -> str | None:
        chat = self.load(chat_id)
        if chat is None:
            return None
        who = chat.get("agent_label") or "Agent"
        lines = [f"# {display_title(chat) or 'Chat'}", "",
                 f"{who} · {chat.get('backend') or 'agent'} · "
                 f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(chat.get('started', 0)))}",
                 ""]
        if isinstance(chat.get("summary"), str) and chat["summary"].strip():
            lines += [f"_{chat['summary']}_", ""]
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
        slug = re.sub(r"[^a-z0-9]+", "-", display_title(chat).lower()).strip("-")[:40]
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
        turn = f"User: {e.get('transcript', '')}\n{speaker}: {e.get('reply', '')}"
        if len(turn) + 2 > max_chars:
            turn = (f"User: {str(e.get('transcript', ''))[:max_chars // 2]}\n"
                    f"{speaker}: {str(e.get('reply', ''))[:max_chars // 2 - 200]}")
        turns.append(turn)
    body = ""
    for turn in reversed(turns):
        if len(body) + len(turn) + 2 > max_chars:
            break
        body = turn + "\n\n" + body
    if not body:
        return ""
    return ("We are continuing an earlier conversation. Here it is, for "
            "context:\n\n" + body.rstrip() + "\n\n" + tail)


def quarantine_refusal(agent: str) -> str:
    """Why a chat may not be shared with `agent` (external id): it is
    quarantined (phase M8), or the settings cannot say. "" when it may."""
    try:
        from runtime import Config
        q = Config().quarantined()
    except Exception:                   # noqa: BLE001 -- a guard closes
        q = None
    if q is None:
        return ("The crew settings can't be read, so a chat is not shared with any agent "
                "until they can. Check the Crew map.")
    if agent in q:
        return f"{agent} is quarantined. Release it on the Crew map first."
    return ""


def refusal(chat: dict, agent: str) -> str:
    """Why `agent` may not carry `chat` on, in words a person can act on."""
    return (f"That chat isn't shared with {agent}: it has no session in it and "
            f"nobody shared it. Use Share chat with... first, or pass the "
            f"conversation to it.")


def _agent_names() -> dict:
    """Each agent's name now, normalised, to its external id, for
    `agent:NAME` (phase M19). Empty when the settings cannot be read: the
    filter then matches ids and the names saved in each chat."""
    try:
        from runtime import Config
        cfg = Config()
        out = {_norm(cfg.main_label()): "main"}
        for spec in cfg.all_agents():
            for n in (spec.get("label"), spec.get("name")):
                if _norm(n):
                    out.setdefault(_norm(n), spec["id"])
        out.pop("", None)
        return out
    except Exception:                   # noqa: BLE001 -- a convenience only
        return {}


def main(argv: list[str]) -> int:
    store = ChatStore()
    if not argv or argv[0] == "list":
        # Titles come from what was said and names are any text: printed to
        # a terminal, either could carry escape sequences.
        from speech_text import safe_for_terminal
        for c in store.list():
            pin = "*" if c.get("pinned") else " "
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(_when(c)))
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
        elif verb == "rename" and len(rest) == 1:
            # Phase M18: the title on stdin, one line, so what was typed
            # (often the first sentence somebody said) is not in argv.
            ok = store.rename(rest[0], sys.stdin.readline())
        elif verb in ("pin", "unpin") and rest:
            ok = store.pin(rest[0], verb == "pin")
        elif verb == "delete" and rest == ["--all"]:
            # Phase M18, from the Chats page's confirm: how many went.
            print(store.delete_all())
            return 0
        elif verb == "delete" and len(rest) == 1:
            ok = store.delete(rest[0])
        elif verb == "last" and rest == ["--json"]:
            # Master plan M21: each agent's newest saved chat, ids only.
            print(json.dumps(store.last_by_owner()))
            return 0
        elif verb == "stats" and rest in ([], ["--json"]):
            st = store.stats()
            if rest:
                print(json.dumps(st))
            else:
                from speech_text import safe_for_terminal
                print(safe_for_terminal(f"{st['chats']} chats, {st['bytes']} bytes, "
                                        f"in {st['dir']}"))
            return 0
        elif verb == "search":
            # The query on stdin (phase M18), never argv.
            agent, as_json = None, False
            args = list(rest)
            while args:
                a = args.pop(0)
                if a == "--json":
                    as_json = True
                elif a == "--agent" and args and _AGENT.fullmatch(args[0]):
                    agent = args.pop(0)
                else:
                    print("usage: agentvoice chats search [--agent ID] [--json] "
                          "(the words on stdin)", file=sys.stderr)
                    return 2
            # One line: the overlay writes it and keeps the pipe open.
            problems: list[str] = []
            hits = store.search(sys.stdin.readline(QUERY_MAX), agent,
                                names=_agent_names, problems=problems)
            if problems:
                # Said, not swallowed: a filter left out widens the list.
                from speech_text import safe_for_terminal
                print(safe_for_terminal("left out: " + "; ".join(problems)), file=sys.stderr)
            if as_json:
                print(json.dumps(hits))
            else:
                from speech_text import safe_for_terminal
                titles = {c.get("id"): c.get("title", "") for c in store.list()}
                for h in hits:
                    print(f"{h['id']} {h['score']:.3f}  "
                          f"{safe_for_terminal(str(titles.get(h['id'], '')))}")
            return 0
        elif verb in ("share", "unshare") and len(rest) == 2:
            # By external id ("main" for the main agent).
            if verb == "share":
                why = quarantine_refusal(rest[1])
                if why:
                    print(why, file=sys.stderr)
                    return 1
            ok = (store.share if verb == "share" else store.unshare)(rest[0], rest[1])
        elif verb == "may-continue" and len(rest) == 2:
            # Whether AGENT may carry chat ID on; asked by `agentvoice chats
            # continue ID AGENT` before anything is sent to the daemon, so a
            # refusal is said where it was asked for.
            chat = store.load(rest[0])
            if chat is None:
                raise LookupError
            if owner_of(chat) != rest[1]:
                # Phase M8: a quarantined agent carries on only its own.
                why = quarantine_refusal(rest[1])
                if why:
                    print(why, file=sys.stderr)
                    return 1
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
            print("usage: agentvoice chats [list|show ID|rename ID [TITLE]|pin ID|unpin ID|"
                  "delete ID|delete --all|export ID [FOLDER]|share ID AGENT|unshare ID AGENT|"
                  "continue ID [AGENT]|new [AGENT]|stats [--json]|last --json|search [--agent ID] [--json]]",
                  file=sys.stderr)
            return 2
        if not ok:
            raise LookupError
        return 0
    except (LookupError, ValueError):
        print("no such chat", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
