"""Try it: hear an agent's personality before keeping it (phase M6, item 10).

`agentvoice try AGENT` takes the draft from the Agent details page -- its
personality and standing instructions as they stand in the boxes, saved or
not -- and the daemon speaks one sentence in that agent's voice, from a quiet
side turn that runs on the draft.

What keeps it small and safe, and where each rule lives:

- **The draft travels on stdin and then in a private file**, never in argv:
  the CLI writes `$RUNDIR/try/<id>.req` (0600, in a 0700 folder) and renames
  it into place; the daemon reads and deletes it. The status comes back the
  same way, in `<id>.status`.
- **No tools, nothing kept.** The side turn is built at the lowest level the
  backend has, with no desktop, browser, notes or collaboration tools and no
  skills, and `no_tools` set (Claude Code: `--tools ""` and
  `--strict-mcp-config`). Claude and Codex keep no session file
  (`ephemeral`). It is never written to a chat and never published to the
  readout. Nothing of the draft or the reply goes to the journal.
- **Refused, with the reason**, when the service is off, the screen is
  locked, the microphone is lent out, the agent is unknown or has no program
  to run on, an agent is busy, or the last try was under MIN_GAP_S ago.
  `refusal()` is the one decision; the CLI checks the first two itself too,
  so the page hears at once, and the daemon checks all of them again.
- **One sentence**, the first the reply makes, cut at SENTENCE_MAX.

    python try_it.py client AGENT  < {"personality": "...", "instructions": "..."}
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths  # noqa: E402

#: At most one try per this many seconds, whichever agent it is for.
MIN_GAP_S = 10.0
#: How long the side turn may take to produce its sentence.
TURN_TIMEOUT_S = 30.0
#: How long the CLI waits for the daemon to pick the request up. The daemon
#: reads requests between turns only, so a longer wait means it is busy.
PICKUP_S = 5.0
#: How long the CLI waits after that for the sentence to be said.
FINISH_S = TURN_TIMEOUT_S + 30.0
#: A request older than this when the daemon finds it is refused as stale.
STALE_S = 15.0
SENTENCE_MAX = 300
REQUEST_MAX = 64 * 1024
#: The budgets the files have (agentfs.AGENT_FILES), applied to the draft
#: the same way a read applies them to the file.
PERSONALITY_MAX = 1500
INSTRUCTIONS_MAX = 2000

#: What the side turn is asked. A constant: nothing the user typed is in it.
PROMPT = ("The user is trying out how you sound. Say one short sentence to them, the way "
          "you would greet them at the start of a conversation, in your own manner. Do not "
          "mention this request, tools or instructions. One sentence only.")

_ID = re.compile(r"(\d{19})-(\d{1,10})")
_AGENT = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")


def folder() -> Path:
    return paths.RUNTIME_DIR / "try"


# --- what the daemon decides ---------------------------------------------------

def refusal(*, locked: bool | None, yielded: bool, known: bool, label: str, has_program: bool,
            problem: str = "", target_busy: bool, other_busy: bool,
            since_last: float, stale: bool = False) -> str:
    """Why a try is refused, in words for the page; "" when it may run.
    In order of what the person can do least about.

    `locked` None is "cannot tell". A reply goes on in that case (the
    daemon says so in the journal), but Try it is an extra and need not:
    it is refused rather than risk speaking over a lock screen (Codex
    review of M6)."""
    if locked is None:
        return "cannot tell whether the screen is locked, so it will not speak"
    if locked:
        return "the screen is locked"
    if yielded:
        return "the microphone is lent to a call"
    if stale:
        return "the request waited too long; press Try it again"
    if not known:
        return "that agent is not running here"
    if not has_program:
        return f"{label} has no program to run on" + (f": {problem}" if problem else "")
    if target_busy:
        return f"{label} is busy; try again when it has finished"
    if other_busy:
        return "another agent is answering; try again when it has finished"
    if since_last < MIN_GAP_S:
        wait = max(1, int(MIN_GAP_S - since_last + 0.999))
        return f"one try every {MIN_GAP_S:.0f} seconds; wait {wait} more"
    return ""


def _clean_cut(text, limit: int) -> str | None:
    """The draft as an agent would be told it: cleaned and cut to its
    budget, the way agentfs.read_file treats the file. None when absent."""
    if not isinstance(text, str):
        return None
    from agentfs import clean
    return clean(text)[:limit].rstrip()


def parse_request(raw: bytes) -> dict | None:
    """{"agent", "personality" | None, "instructions" | None} from a
    request file, or None when it is not one."""
    try:
        d = json.loads(raw[:REQUEST_MAX].decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    agent = d.get("agent")
    if not isinstance(agent, str) or not _AGENT.fullmatch(agent):
        return None
    return {"agent": agent,
            "personality": _clean_cut(d.get("personality"), PERSONALITY_MAX),
            "instructions": _clean_cut(d.get("instructions"), INSTRUCTIONS_MAX)}


def draft_parts(parts: dict | None, personality: str | None) -> dict:
    """The agent's prompt parts with the draft personality in place, and no
    skills index: the side turn has no tools to use a skill with."""
    out = dict(parts or {})
    if personality is not None:
        out["personality"] = personality
    out["skills"] = ""
    return out


def backend_refusal(program: str, endpoint: bool, endpoint_is_agent: bool) -> str:
    """Why Try it cannot run on this backend; "" when it can. Only where
    "no tools" is enforced, not just asked for (Codex review of M6):

    - Claude Code: `--tools ""` and `--strict-mcp-config`, recorded on a real
      turn (tests/fixtures/try/claude-no-tools.json);
    - an endpoint that is a plain model: it has no tools to use.

    Codex in `exec` can still run read-only commands, Gemini's plan mode and
    agy's read-only mode still read files, an agent endpoint runs whatever
    its own host gives it, and none of them has been shown to start with
    nothing. They are refused, saying so, until one has."""
    if endpoint:
        return ("its endpoint is an agent with tools of its own, which cannot be switched off "
                "from here" if endpoint_is_agent else "")
    if program == "claude":
        return ""
    return (f"Try it runs only where a turn can be started with no tools at all, which so far "
            f"is Claude Code and plain endpoints, not {program or 'this program'}")


def first_sentence(chunks) -> str:
    """The first sentence of a reply stream (adapters' Chunks), cut at
    SENTENCE_MAX. The shared splitter merges a short sentence into the next
    so speech does not sound choppy; here one is wanted, so the first piece
    is cut again at its own first boundary ("Hi! How are you?" says "Hi!")."""
    from adapters.base import sentences
    from speech_text import _next_boundary
    for s in sentences(chunks):
        s = " ".join(str(s).split())
        if not s:
            continue
        m = _next_boundary(s)
        if m is not None and s[:m.end()].strip():
            s = s[:m.end()].strip()
        return s[:SENTENCE_MAX]
    return ""


def take(now: float | None = None) -> tuple[str, dict | None] | None:
    """The oldest request as (id, request), deleting it; request None when
    the file was not a valid one or is stale (the caller refuses it).
    Clears status files nobody collected."""
    now = time.time() if now is None else now
    d = folder()
    try:
        names = sorted(e.name for e in os.scandir(d) if e.is_file(follow_symlinks=False))
    except OSError:
        return None
    for name in names:
        if name.endswith(".status"):
            try:
                if now - os.lstat(d / name).st_mtime > 300:
                    os.unlink(d / name)
            except OSError:
                pass
    for name in names:
        if not name.endswith(".req"):
            continue
        rid = name[:-4]
        path = d / name
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
            try:
                raw = os.read(fd, REQUEST_MAX + 1)
            finally:
                os.close(fd)
            os.unlink(path)
        except OSError:
            continue
        m = _ID.fullmatch(rid)
        if m is None:
            continue
        req = parse_request(raw)
        if req is not None:
            req["stale"] = now - int(m.group(1)) / 1e9 > STALE_S
        return rid, req
    return None


def answer(rid: str, state: str, why: str = "", text: str = "") -> None:
    """Write the status the CLI waits for: refused, accepted, said, failed."""
    if not _ID.fullmatch(rid):
        return
    d = paths.private_dir(folder())
    tmp = d / f".{rid}.tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"state": state, "why": why, "text": text}, f, ensure_ascii=False)
        os.replace(tmp, d / f"{rid}.status")
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# --- the CLI's half ---------------------------------------------------------------

def _read_status(path: Path) -> dict | None:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def client(agent: str, stdin=None, out=None, err=None, sleep=time.sleep,
           clock=time.monotonic) -> int:
    """Send the draft on stdin to the daemon and wait for it to be said.
    Prints the sentence on stdout (0), or why not on stderr (1)."""
    from speech_text import safe_for_terminal
    stdin = stdin or sys.stdin.buffer
    out, err = out or sys.stdout, err or sys.stderr
    if not _AGENT.fullmatch(agent or ""):
        print("usage: agentvoice try AGENT < draft.json", file=err)
        return 2
    raw = stdin.readline(REQUEST_MAX + 1)
    try:
        d = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        print("the draft is not one line of JSON", file=err)
        return 2
    if not isinstance(d, dict):
        print("the draft must be a JSON object", file=err)
        return 2
    body = {"agent": agent}
    for key in ("personality", "instructions"):
        if isinstance(d.get(key), str):
            body[key] = d[key]
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    if len(data) > REQUEST_MAX:
        print("the draft is too long", file=err)
        return 2
    folder_ = paths.private_dir(folder())
    rid = f"{time.time_ns()}-{os.getpid()}"
    tmp, req, status = folder_ / f".{rid}.tmp", folder_ / f"{rid}.req", folder_ / f"{rid}.status"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, req)

    def wait(seconds: float, done) -> dict | None:
        end = clock() + seconds
        while True:
            s = _read_status(status)
            if s is not None and done(s):
                return s
            if clock() >= end:
                return s
            sleep(0.1)

    first = wait(PICKUP_S, lambda s: True)
    if first is None:
        try:
            os.unlink(req)          # not picked up: take it back
            print("Agent Voice did not pick it up; it may be in the middle of a turn", file=err)
            return 1
        except FileNotFoundError:
            first = wait(PICKUP_S, lambda s: True)   # taken just now
    final = first
    if first is not None and first.get("state") == "accepted":
        final = wait(FINISH_S, lambda s: s.get("state") != "accepted")
    try:
        os.unlink(status)
    except OSError:
        pass
    state = (final or {}).get("state")
    if state == "said":
        print(safe_for_terminal(str(final.get("text", ""))), file=out)
        return 0
    why = str((final or {}).get("why", "")) or (
        "it took too long" if state == "accepted" else "Agent Voice did not answer")
    print(safe_for_terminal(why), file=err)
    return 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 2 and argv[0] == "client":
        return client(argv[1])
    print("usage: try_it.py client AGENT < draft.json", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
