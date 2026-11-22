#!/usr/bin/env python3
"""Approval cards, answered by the person at the screen (phase M7).

Until M7 a card's answer was a file: the hook wrote `<id>.request` under
`$RUNDIR/permissions/`, and whatever wrote `<id>.response` next to it had
answered. Any process running as the desktop user could do that -- including
an agent at Trusted, answering its own card with `agentvoice permit <id>
allow` -- so "ask me first" was a promise nothing kept.

Now the daemon holds every card, and an answer reaches it only over its
socket, from a caller it has checked:

- **Who asks.** The hook, the desktop and crew servers (under `--guard`)
  connect to `$RUNDIR/cards/cards.sock` and post the card. They are
  children of an agent CLI the daemon started, and they check the other end
  is the daemon by the kernel's word (SO_PEERCRED): the listener must be
  their own ancestor, which no other process can make itself. The daemon's
  own collaboration questions post to the same desk in-process
  (`LOCAL_DESK`).
- **Who answers.** `agentvoice pending ID` and `agentvoice permit ID
  VERDICT`, run by the overlay. The daemon reads the caller's pid from the
  kernel and accepts an *allow* only when:
    * the caller's parent is the live Omarchy shell -- an executable called
      quickshell, run with `-p $OMARCHY_PATH/shell` -- which rules out
      everything an agent can start, and everything the shell starts
      detached (Quickshell's execDetached double-forks, so those are
      reparented away from it: measured in M7);
    * that shell does not descend from the daemon, so nothing an agent
      started, a shell included, can stand in for it;
    * the caller's stdout (for `pending`) or stdin (for `permit`) is a pipe
      whose other end the shell holds -- so `exec agentvoice pending ID >
      /tmp/x`, smuggled into a command the shell runs, gets no nonce;
    * the answer carries the card's one-use nonce, which only a checked
      `pending` is given, and the digest of the card it showed;
    * the screen is not locked, and the card is still waiting.
  A deny is accepted from anyone. An allow that fails any check is not
  ignored: the card is **denied**, and the journal says why.
- **Silence, expiry, a stop, the asker going away, a lock** are all no.

What this does not stop, written down because the plan asks for exactly
what was proven (see phaseM7notes.md): a process running as the same user
that sets out to defeat it. It can drop a plugin into the shell's plugins
folder or edit this plugin's QML, which the shell then runs; inject input
through the compositor's virtual keyboard and pointer protocols; race the
overlay for the pipes it holds through /proc/PID/fd; or replace the daemon's
own code. The orders guard asks about the plain forms of those at every
level, and below Trusted every command is a card -- so an agent cannot
become that process without the user approving it. At Trusted it can.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import select
import socket
import struct
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import RUNTIME_DIR  # noqa: E402

SOCKET_DIR = RUNTIME_DIR / "cards"
SOCKET_NAME = "cards.sock"

#: Card ids: twelve hex characters, the form `agentvoice pending` and
#: `permit` have always checked.
CARD_ID = re.compile(r"[0-9a-f]{12}")
NONCE = re.compile(r"[0-9a-f]{32}")
DIGEST = re.compile(r"[0-9a-f]{64}")
VERDICTS = ("allow", "allow-session", "deny")

#: One ask, in bytes. A Write's whole file rides along in `input`, as it did
#: in the request file.
ASK_MAX = 16 * 1024 * 1024
#: One show or answer request.
LINE_MAX = 64 * 1024

#: How long an asker waits beyond the card's own timeout before deciding the
#: daemon will not answer. Small on purpose: Claude Code kills a hook after
#: 60 s and reads that as a non-blocking error, which runs the tool. With the
#: 45 s default the hook is done by 48 s.
GRACE_S = 3.0
#: And never longer than this in all, whatever timeout it was handed: a
#: setting of 90 s would otherwise outlive Claude's 60 (Codex review of M7).
#: The daemon takes the card down when the asker hangs up.
ASK_BUDGET_S = 55.0

DEFAULT_TIMEOUT = 45.0

#: Cards waiting at once. Each holds a thread and a summon; beyond this an
#: agent in a loop is told no at once instead of filling the daemon.
MAX_PENDING = 16

#: The in-process desk, when this module runs inside the daemon. Set by the
#: daemon at start; never in a hook or a server process.
LOCAL_DESK: "Desk | None" = None

# What the asker is told, each of them a denial.
NOBODY = "Agent Voice is not running, so nobody could be asked; nothing was run."
NOT_OURS = ("The card socket did not belong to Agent Voice's daemon, so nobody "
            "was asked; nothing was run.")
UNREADABLE = "Agent Voice's answer could not be read, so this was denied."
LOCKED = "The screen is locked, so nobody could be asked; nothing was run."
LOCKED_SINCE = "The screen locked before anyone answered, so this was denied."
NO_SOCKET = ("Agent Voice could not open the socket its cards are answered "
             "through, so nobody could answer; nothing was run.")
TOO_MANY = "Too many questions are already waiting, so this was denied."
DENIED = {"allow": False, "reason": "Denied at the desktop."}


def socket_path(root: Path | None = None) -> Path:
    return (root or SOCKET_DIR) / SOCKET_NAME


def omarchy_shell_dir() -> Path:
    """Where the Omarchy shell's own QML lives: what the live shell runs."""
    base = os.environ.get("OMARCHY_PATH") or "/usr/share/omarchy"
    return Path(base) / "shell"


# --- the card itself ----------------------------------------------------------------

_STR_LIMITS = {"tool": 200, "who": 64, "label": 200, "chain": 600,
               "summary": 64 * 1024, "note": 2000}


def clean_fields(fields) -> dict:
    """The fields an asker may set, each of its kind: a string cut to its
    limit, a count, a flag. Anything else is dropped, and a value of the
    wrong kind becomes its safe default -- `sessionWide` and `announce` are
    False unless they are literally True."""
    fields = fields if isinstance(fields, dict) else {}
    out: dict = {}
    for key, limit in _STR_LIMITS.items():
        v = fields.get(key)
        out[key] = v[:limit] if isinstance(v, str) else ""
    if not out["tool"]:
        out["tool"] = "unknown"
    for key in ("truncated", "length"):
        v = fields.get(key)
        out[key] = v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0
    for key in ("sessionWide", "announce"):
        out[key] = fields.get(key) is True
    inp = fields.get("input")
    out["input"] = inp if isinstance(inp, dict) else {}
    return out


def canonical(card: dict) -> bytes:
    return json.dumps(card, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def digest_of(card: dict) -> str:
    """The hash of a card exactly as shown: what an answer is bound to."""
    return hashlib.sha256(canonical(card)).hexdigest()


def shown(public: dict) -> dict:
    """What the overlay is handed and draws: the card less `input`, the
    whole tool call -- for a Write the entire file -- which the card never
    shows (its summary does) and which made a reply larger than an ask
    (Codex review of M7). The daemon keeps `input` for itself."""
    return {k: v for k, v in public.items() if k != "input"}


class _Card:
    __slots__ = ("id", "public", "digest", "nonce", "deadline", "done", "answer", "stop")

    def __init__(self, public: dict, deadline: float, stop=None) -> None:
        self.id = public["id"]
        self.public = public
        self.digest = digest_of(shown(public))
        self.nonce = secrets.token_hex(16)
        self.deadline = deadline
        self.done = threading.Event()
        self.answer: dict | None = None
        self.stop = stop


def summon_overlay(card_id: str) -> None:
    """Put the card on screen. The overlay asks for the card itself, by id."""
    import subprocess
    subprocess.run(["omarchy-shell", "shell", "summon", "duaneoca.agentvoice",
                    json.dumps({"mode": "permission", "id": card_id})],
                   timeout=5, capture_output=True)


class Desk:
    """The daemon's cards: posted, shown, answered once, then gone.

    Every resolution goes through `_finish` under one lock, so an answer
    and the timeout cannot both win: whichever is first is the outcome,
    and the other is told the question is no longer waiting."""

    def __init__(self, summon=None, is_locked=None, log=None,
                 clock=time.monotonic, locked_now=None) -> None:
        self._cards: dict[str, _Card] = {}
        self._lock = threading.Lock()
        self.summon = summon if summon is not None else summon_overlay
        self.is_locked = is_locked if is_locked is not None else (lambda: False)
        #: The lock asked afresh, for an allow: `is_locked` is the daemon's
        #: flag, which its 2 s poll can leave behind a lock that just landed
        #: (Codex review of M7). True, False, or None for "cannot tell",
        #: which keeps the flag's answer, as the daemon's own poll does.
        self.locked_now = locked_now
        self.log = log if log is not None else (lambda line: None)
        self.clock = clock
        #: False when the socket could not be opened: nobody could answer,
        #: so a card is refused at once rather than left to time out.
        self.ready = True

    def _locked(self) -> bool:
        try:
            return self.is_locked() is not False
        except Exception:               # noqa: BLE001 -- unsure is locked
            return True

    def _locked_fresh(self) -> bool:
        """For an allow: the flag, then the compositor asked now."""
        if self._locked():
            return True
        if self.locked_now is None:
            return False
        try:
            return self.locked_now() is True
        except Exception:               # noqa: BLE001 -- unsure is locked
            return True

    def _finish(self, card: _Card, answer: dict | None) -> bool:
        """Settle `card` with `answer`, once. True if this call settled it."""
        with self._lock:
            if self._cards.get(card.id) is not card or card.done.is_set():
                return False
            card.answer = answer
            card.done.set()
            del self._cards[card.id]
            return True

    def post(self, fields, timeout: float | None = None, on_posted=None,
             stop=None) -> dict | None:
        """Put one card up and wait for its answer: the answer dict, or None
        when nobody answered in time, `stop()` turned true, or it raised.
        Only `answer.get("allow") is True` is a yes."""
        timeout = DEFAULT_TIMEOUT if timeout is None else float(timeout)
        if not self.ready:
            return {"allow": False, "reason": NO_SOCKET}
        if self._locked():
            return {"allow": False, "reason": LOCKED}
        public = {**clean_fields(fields), "id": uuid.uuid4().hex[:12],
                  "asked_at": time.time(), "timeout": timeout}
        # The deadline is fixed before the summon, which can take seconds:
        # the hook's whole wait has to fit inside Claude Code's 60 s.
        card = _Card(public, self.clock() + timeout, stop)
        with self._lock:
            if len(self._cards) >= MAX_PENDING:
                return {"allow": False, "reason": TOO_MANY}
            self._cards[card.id] = card
        self.log(f"card {card.id} up: {public['tool']} for "
                 f"{public['who'] or 'the main agent'}")
        try:
            try:
                self.summon(card.id)
            except Exception:           # noqa: BLE001 -- times out into a no
                pass
            if on_posted is not None:
                try:
                    on_posted()
                except Exception:       # noqa: BLE001 -- cannot change the answer
                    pass
            while True:
                left = card.deadline - self.clock()
                if left <= 0:
                    break
                if card.done.wait(min(0.1, left)):
                    return card.answer
                if self._locked():
                    self._finish(card, {"allow": False, "reason": LOCKED_SINCE})
                    continue
                if stop is not None:
                    try:
                        gone = bool(stop())
                    except Exception:   # noqa: BLE001
                        gone = True
                    if gone:
                        break
        finally:
            settled = self._finish(card, None)
        if settled:
            self.log(f"card {card.id} down: nobody answered")
            return None
        return card.answer

    def pending(self) -> list[dict]:
        """The cards waiting now, oldest first, as shown (no nonce)."""
        with self._lock:
            cards = sorted(self._cards.values(), key=lambda c: c.public["asked_at"])
        return [dict(c.public) for c in cards]

    def show(self, card_id: str | None, verified: bool, why: str = "") -> dict:
        """One card for the overlay or a terminal: the newest when no id is
        given, `{}` when none is waiting. Only a verified caller is given
        the nonce an allow needs."""
        with self._lock:
            if card_id:
                card = self._cards.get(card_id)
            else:
                card = max(self._cards.values(),
                           key=lambda c: c.public["asked_at"], default=None)
        if card is None:
            return {}
        out = {**shown(card.public), "digest": card.digest, "verified": bool(verified)}
        if verified:
            out["nonce"] = card.nonce
        else:
            out["why"] = why or "this was not asked from the Agent Voice panel"
        return out

    def answer(self, card_id: str, verdict: str, nonce: str = "", digest: str = "",
               verified: bool = False, why: str = "") -> tuple[bool, str]:
        """Answer one card. (accepted, what happened).

        A deny is taken from anyone. An allow must be verified, unlocked,
        for this card's nonce and digest; one that is not settles the card
        as a denial, so trying to answer somebody else's card for them ends
        it."""
        with self._lock:
            card = self._cards.get(card_id) if isinstance(card_id, str) else None
        if card is None:
            return False, f"no question {card_id} is waiting"
        if verdict == "deny":
            if self._finish(card, dict(DENIED)):
                self.log(f"card {card.id}: denied")
                return True, "denied"
            return False, f"no question {card_id} is waiting"
        problem = ""
        if verdict not in ("allow", "allow-session"):
            problem = "the answer was neither allow nor deny"
        elif not verified:
            problem = why or "the answer did not come from the Agent Voice panel"
        elif self.clock() >= card.deadline:
            # post() wakes every 0.1 s; an allow landing in between, after
            # the deadline, was otherwise taken (Codex review of M7).
            problem = "the question had expired"
        elif self._locked_fresh():
            problem = "the screen is locked"
        elif not (isinstance(nonce, str) and NONCE.fullmatch(nonce)
                  and hmac.compare_digest(nonce, card.nonce)):
            problem = "the answer was not for the question on screen"
        elif not (isinstance(digest, str) and DIGEST.fullmatch(digest)
                  and hmac.compare_digest(digest, card.digest)):
            problem = "the question shown was not the question asked"
        elif verdict == "allow-session" and card.public.get("sessionWide") is not True:
            problem = "this question cannot be allowed for the whole chat"
        if not problem and card.stop is not None:
            # The asker's turn was stopped: the question is withdrawn, and an
            # allow must not be reported as taken for a turn that will not
            # act on it (Codex review of M7).
            try:
                withdrawn = bool(card.stop())
            except Exception:           # noqa: BLE001
                withdrawn = True
            if withdrawn:
                self._finish(card, None)
                return False, "the question was withdrawn: the turn that asked it was stopped"
        if problem:
            if self._finish(card, {"allow": False,
                                   "reason": f"An answer that could not be checked was "
                                             f"refused ({problem}), so this was denied."}):
                self.log(f"card {card.id}: an allow was refused ({problem}); denied")
                return False, f"refused, and the question was denied: {problem}"
            return False, f"no question {card_id} is waiting"
        result = {"allow": True}
        if verdict == "allow-session":
            result["session"] = True
        if not self._finish(card, result):
            return False, f"no question {card_id} is waiting"
        self.log(f"card {card.id}: allowed{' for the chat' if verdict == 'allow-session' else ''}")
        return True, "allowed"


# --- processes, read from /proc --------------------------------------------------------

def _stat(pid: int) -> tuple[int, int]:
    """(parent pid, start time in ticks) of a live process."""
    with open(f"/proc/{pid}/stat", "rb") as f:
        stat = f.read().decode("utf-8", "replace")
    # The command name is in brackets and may hold spaces and brackets.
    rest = stat.rsplit(")", 1)[1].split()
    return int(rest[1]), int(rest[19])


def descends(pid: int, ancestor: int) -> bool:
    """Whether `pid` is below `ancestor` (never `ancestor` itself). Unsure
    is no -- callers that use this to *refuse* ask `not descends_or_unsure`."""
    if ancestor <= 1 or pid == ancestor:
        return False
    seen = 0
    try:
        while pid > 1 and seen < 128:
            if pid == ancestor:
                return True
            pid = _stat(pid)[0]
            seen += 1
    except (OSError, ValueError, IndexError):
        return False
    return pid == ancestor


def _clear_of(pid: int, ancestor: int) -> bool:
    """True only when the whole line of `pid`'s ancestors was read and
    `ancestor` is not in it. A line that cannot be read is not clear."""
    seen = 0
    try:
        while pid > 1 and seen < 128:
            if pid == ancestor:
                return False
            pid = _stat(pid)[0]
            seen += 1
    except (OSError, ValueError, IndexError):
        return False
    return pid in (0, 1) and ancestor not in (0, 1)


def is_self_or_ancestor(pid: int) -> bool:
    """Whether `pid` is this process or one of its ancestors."""
    me = os.getpid()
    return pid == me or descends(me, pid)


def _cmdline(pid: int) -> list[str]:
    with open(f"/proc/{pid}/cmdline", "rb") as f:
        return [a.decode("utf-8", "surrogateescape") for a in f.read().split(b"\0") if a]


def config_path(argv: list[str]) -> str | None:
    """The `-p`/`--path` a quickshell was started with, or None."""
    for i, a in enumerate(argv[1:], start=1):
        if a in ("-p", "--path"):
            return argv[i + 1] if i + 1 < len(argv) else None
        if a.startswith("--path="):
            return a[len("--path="):]
        if a.startswith("-p") and not a.startswith("--") and len(a) > 2:
            return a[2:]
    return None


#: SO_PEERPIDFD, where the number is known: asm-generic's 77. Python 3.13
#: does not name it. Anywhere else, no pidfd -- a wrong number would hand
#: back some other option's value as if it were a descriptor.
SO_PEERPIDFD = getattr(socket, "SO_PEERPIDFD", None) or (
    77 if platform.machine() in ("x86_64", "aarch64", "riscv64") else None)


def peer_pidfd(conn) -> int | None:
    """A pidfd for the process at the other end, or None. It pins that
    process, so a pid that died and was given to another is caught."""
    if SO_PEERPIDFD is None:
        return None
    try:
        fd = conn.getsockopt(socket.SOL_SOCKET, SO_PEERPIDFD)
    except OSError:
        return None
    try:
        if os.readlink(f"/proc/self/fd/{fd}") == "anon_inode:[pidfd]":
            return fd
    except OSError:
        return None
    return None                         # not ours to close: not a pidfd


def pidfd_pid(fd: int) -> int:
    """The pid a pidfd refers to now: -1 once that process is gone."""
    try:
        with open(f"/proc/self/fdinfo/{fd}") as f:
            for line in f:
                if line.startswith("Pid:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return -1


class Verifier:
    """Who may ask, and whose allow counts. See the module docstring."""

    def __init__(self, daemon_pid: int | None = None, shell_dir: Path | None = None,
                 shell_exes: tuple[str, ...] = ("quickshell",)) -> None:
        self.daemon_pid = daemon_pid or os.getpid()
        self.shell_dir = shell_dir if shell_dir is not None else omarchy_shell_dir()
        self.shell_exes = tuple(shell_exes)

    def asker(self, pid: int) -> tuple[bool, str]:
        """A card may be posted only by a process the daemon started."""
        if descends(pid, self.daemon_pid):
            return True, ""
        return False, "only an agent Agent Voice started can ask"

    def panel(self, pid: int, fd: int, pidfd: int | None = None) -> tuple[bool, str]:
        """Whether `pid` is the overlay's own `agentvoice pending|permit`.
        `fd` is the descriptor that must be the shell's pipe: 1 for pending,
        0 for permit. (ok, why not)."""
        where = "output" if fd == 1 else "input"
        try:
            ppid, started = _stat(pid)
            if ppid <= 1:
                return False, "it was not started by the Omarchy shell"
            exe = os.readlink(f"/proc/{ppid}/exe").removesuffix(" (deleted)")
            if os.path.basename(exe) not in self.shell_exes:
                return False, "it was not started by the Omarchy shell"
            if os.stat(f"/proc/{ppid}").st_uid != os.getuid():
                return False, "it was started by another user's shell"
            path = config_path(_cmdline(ppid))
            try:
                same = path is not None and Path(path).resolve() == self.shell_dir.resolve()
            except (OSError, RuntimeError):
                same = False
            if not same:
                return False, (f"it was started by a shell that is not running "
                               f"{self.shell_dir}")
            if _stat(ppid)[1] > started:
                return False, "the caller's parent changed while it was checked"
            if not _clear_of(ppid, self.daemon_pid):
                return False, "it was started from inside an agent"
            link = os.readlink(f"/proc/{pid}/fd/{fd}")
            if not link.startswith("pipe:["):
                return False, f"its {where} is not the shell's own pipe"
            held = False
            for name in os.listdir(f"/proc/{ppid}/fd"):
                try:
                    if os.readlink(f"/proc/{ppid}/fd/{name}") == link:
                        held = True
                        break
                except OSError:
                    continue
            if not held:
                return False, f"its {where} is not the shell's own pipe"
            # The same process, under the same parent, from start to end: a
            # pid that died and was reused, or a parent that died and left
            # the caller to be reparented, does not get through.
            if _stat(pid) != (ppid, started):
                return False, "the caller changed while it was checked"
            if pidfd is not None and pidfd_pid(pidfd) != pid:
                return False, "the caller changed while it was checked"
            return True, ""
        except (OSError, ValueError, IndexError):
            return False, "the caller could not be checked"


# --- the socket -------------------------------------------------------------------------

def _strict(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("a key given twice")
        out[k] = v
    return out


def _parse(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_strict)
    except Exception:                   # noqa: BLE001 -- RecursionError too
        return None


def _read_line(conn, limit: int, deadline: float | None = None, stop=None) -> bytes | None:
    """One line, or None: closed, too long, past `deadline`, or `stop()`."""
    buf = b""
    while b"\n" not in buf:
        if len(buf) > limit:
            return None
        if deadline is not None and time.monotonic() > deadline:
            return None
        if stop is not None:
            try:
                if stop():
                    return None
            except Exception:           # noqa: BLE001
                return None
        try:
            chunk = conn.recv(65536)
        except socket.timeout:
            continue
        if not chunk:
            return None
        buf += chunk
    line = buf.split(b"\n", 1)[0]
    return line if len(line) <= limit else None


def _gone(conn) -> bool:
    """Whether the other end has hung up (the hook was killed, the turn
    stopped). Readable with nothing to read is a hang-up."""
    try:
        ready, _, _ = select.select([conn], [], [], 0)
        if not ready:
            return False
        return conn.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT) == b""
    except BlockingIOError:
        return False
    except OSError:
        return True


class Listener:
    """The daemon's end of the card socket: one thread accepting, one short
    reader per connection. A stalled client cannot hold more than its own
    thread; more than READERS reading at once are closed unread."""

    READERS = 32

    def __init__(self, desk: Desk, verifier: Verifier, root: Path | None = None) -> None:
        self.desk = desk
        self.verifier = verifier
        self.root = root
        self.sock = None
        self._readers = threading.BoundedSemaphore(self.READERS)

    def start(self) -> bool:
        path = socket_path(self.root)
        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.parent.chmod(0o700)
            try:
                path.unlink()           # a socket the last daemon left
            except FileNotFoundError:
                pass
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            old = os.umask(0o177)
            try:
                sock.bind(str(path))
            finally:
                os.umask(old)
            os.chmod(path, 0o600)
            sock.listen(16)
        except OSError as e:
            self.desk.ready = False
            self.desk.log(f"approval cards: no socket ({type(e).__name__}); "
                          f"every card is refused")
            return False
        self.sock = sock
        self.desk.ready = True
        threading.Thread(target=self._loop, name="cards", daemon=True).start()
        return True

    def stop(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _loop(self) -> None:
        sock = self.sock
        while sock is not None:
            try:
                conn, _ = sock.accept()
            except OSError:
                if self.sock is None:
                    return
                time.sleep(0.1)
                continue
            if not self._readers.acquire(blocking=False):
                conn.close()
                continue
            try:
                threading.Thread(target=self._one, args=(conn,), daemon=True).start()
            except Exception:           # noqa: BLE001 -- no thread: no card
                self._readers.release()
                conn.close()

    @staticmethod
    def _send(conn, obj) -> None:
        try:
            conn.sendall(json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n")
        except OSError:
            pass

    def _one(self, conn) -> None:
        pidfd = None
        released = False
        try:
            conn.settimeout(1.0)
            creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                    struct.calcsize("3i"))
            pid, uid, _gid = struct.unpack("3i", creds)
            if uid != os.getuid() or pid <= 1:
                return
            pidfd = peer_pidfd(conn)
            raw = _read_line(conn, ASK_MAX, deadline=time.monotonic() + 5.0)
            self._readers.release()
            released = True
            msg = _parse(raw) if raw is not None else None
            if not isinstance(msg, dict):
                return self._send(conn, {"error": "not a request"})
            op = msg.get("op")
            if op == "ask":
                ok, why = self.verifier.asker(pid)
                if not ok:
                    return self._send(conn, {"answer": {"allow": False, "reason": why}})
                timeout = msg.get("timeout")
                if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                        or not 0 <= timeout <= 600):
                    timeout = DEFAULT_TIMEOUT
                answer = self.desk.post(msg.get("card"), timeout,
                                        stop=lambda: _gone(conn))
                return self._send(conn, {"answer": answer})
            if op == "show":
                cid = msg.get("id") or None
                if cid is not None and not (isinstance(cid, str) and CARD_ID.fullmatch(cid)):
                    return self._send(conn, {})
                ok, why = self.verifier.panel(pid, 1, pidfd)
                return self._send(conn, self.desk.show(cid, ok, why))
            if op == "answer":
                cid, verdict = msg.get("id"), msg.get("verdict")
                if not (isinstance(cid, str) and CARD_ID.fullmatch(cid)):
                    return self._send(conn, {"ok": False, "text": "not a question id"})
                ok, why = self.verifier.panel(pid, 0, pidfd)
                done, text = self.desk.answer(cid, verdict if isinstance(verdict, str) else "",
                                              msg.get("nonce", ""), msg.get("digest", ""),
                                              verified=ok, why=why)
                return self._send(conn, {"ok": done, "text": text})
            return self._send(conn, {"error": "not a request"})
        except Exception as e:          # noqa: BLE001 -- never the listener's end
            self.desk.log(f"approval cards: a connection failed ({type(e).__name__})")
        finally:
            if not released:
                self._readers.release()
            if pidfd is not None:
                try:
                    os.close(pidfd)
                except OSError:
                    pass
            try:
                conn.close()
            except OSError:
                pass


def start_desk(is_locked, locked_now=None, log=print, root: Path | None = None) -> Desk:
    """The daemon's desk and its socket, made once at start. Also becomes
    LOCAL_DESK, so the daemon's own questions post to it in-process."""
    global LOCAL_DESK
    desk = Desk(is_locked=is_locked, locked_now=locked_now,
                log=lambda line: log(f"  {line}", flush=True))
    Listener(desk, Verifier(), root).start()
    LOCAL_DESK = desk
    return desk


# --- the clients ------------------------------------------------------------------------

def _connect(root: Path | None = None, timeout: float = 5.0):
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(timeout)
    try:
        conn.connect(str(socket_path(root)))
    except OSError:
        conn.close()
        raise
    return conn


def _peer(conn) -> tuple[int, int]:
    creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    pid, uid, _gid = struct.unpack("3i", creds)
    return pid, uid


def ask(fields: dict, timeout: float, stop=None, root: Path | None = None,
        on_sent=None) -> dict | None:
    """The hook's and the servers' side: post a card and wait for the answer.
    None when nobody answered in time or `stop()` turned true; a denial with
    its reason for everything that went wrong on the way. `on_sent` runs
    once the question is with the daemon. Never raises."""
    try:
        conn = _connect(root)
    except OSError:
        return {"allow": False, "reason": NOBODY}
    try:
        try:
            pid, uid = _peer(conn)
        except OSError:
            return {"allow": False, "reason": NOT_OURS}
        # By the kernel's word, not the socket's name: anything running as
        # this user can bind a socket at that path, but nothing can make
        # itself this process's ancestor.
        if uid != os.getuid() or not is_self_or_ancestor(pid):
            return {"allow": False, "reason": NOT_OURS}
        conn.sendall(json.dumps({"op": "ask", "card": fields, "timeout": timeout},
                                ensure_ascii=False).encode("utf-8") + b"\n")
        if on_sent is not None:
            try:
                on_sent()
            except Exception:           # noqa: BLE001 -- cannot change the answer
                pass
        conn.settimeout(0.1)
        raw = _read_line(conn, LINE_MAX, stop=stop,
                         deadline=time.monotonic() + min(timeout + GRACE_S, ASK_BUDGET_S))
        if raw is None:
            return None
        msg = _parse(raw)
        if not isinstance(msg, dict) or "answer" not in msg:
            return {"allow": False, "reason": UNREADABLE}
        answer = msg["answer"]
        if answer is None:
            return None
        if not isinstance(answer, dict):
            return {"allow": False, "reason": UNREADABLE}
        return answer
    except Exception:                   # noqa: BLE001 -- every failure is a no
        return {"allow": False, "reason": UNREADABLE}
    finally:
        try:
            conn.close()
        except OSError:
            pass


def _request(msg: dict, root: Path | None = None) -> dict | None:
    """One request to the daemon and its one-line reply, or None."""
    try:
        with _connect(root) as conn:
            pid, uid = _peer(conn)
            if uid != os.getuid():
                return None
            conn.sendall(json.dumps(msg).encode("utf-8") + b"\n")
            raw = _read_line(conn, ASK_MAX, deadline=time.monotonic() + 10.0)
    except OSError:
        return None
    reply = _parse(raw) if raw is not None else None
    return reply if isinstance(reply, dict) else None


def _stdin_line(wait: float = 2.0) -> str:
    """One line from stdin when it is a pipe or a file, else ''. A terminal
    is never read: `agentvoice permit ID deny` typed by hand must not hang."""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return ""
        ready, _, _ = select.select([sys.stdin], [], [], wait)
        if not ready:
            return ""
        return sys.stdin.readline(LINE_MAX)
    except (OSError, ValueError):
        return ""


def main(argv: list[str]) -> int:
    """`cards.py show [ID]` and `cards.py answer ID VERDICT` (the nonce and
    digest on stdin, never argv: /proc/PID/cmdline is readable by every
    local account)."""
    if len(argv) >= 1 and argv[0] == "show" and len(argv) <= 2:
        cid = argv[1] if len(argv) == 2 else ""
        if cid and not CARD_ID.fullmatch(cid):
            print("{}")
            return 0
        reply = _request({"op": "show", "id": cid})
        # ASCII, as the request file was: a C1 control character in a card
        # would otherwise reach the terminal of whoever runs `pending`.
        print(json.dumps(reply if reply is not None else {}))
        return 0
    if len(argv) == 3 and argv[0] == "answer":
        from speech_text import safe_for_terminal
        cid, verdict = argv[1], argv[2]
        if not CARD_ID.fullmatch(cid) or verdict not in VERDICTS:
            print("usage: agentvoice permit <id> allow|allow-session|deny", file=sys.stderr)
            return 2
        sent = _parse(_stdin_line().strip().encode("utf-8")) or {}
        if not isinstance(sent, dict):
            sent = {}
        reply = _request({"op": "answer", "id": cid, "verdict": verdict,
                          "nonce": sent.get("nonce", "") if isinstance(sent.get("nonce"), str) else "",
                          "digest": sent.get("digest", "") if isinstance(sent.get("digest"), str) else ""})
        if reply is None:
            out = {"ok": False, "text": "Agent Voice is not running, so nothing was answered"}
        else:
            out = {"ok": reply.get("ok") is True,
                   "text": str(reply.get("text") or "no answer from Agent Voice")}
        print(json.dumps({"ok": out["ok"], "text": safe_for_terminal(out["text"])}))
        if not out["ok"]:
            print(f"agentvoice: {safe_for_terminal(out['text'])}", file=sys.stderr)
        return 0 if out["ok"] else 1
    print("usage: cards.py show [ID] | answer ID allow|allow-session|deny", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
