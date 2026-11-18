"""Progress talk: short, true sentences about what an agent is doing.

During a long turn the room is otherwise silent between the agent's opening
sentence and its answer. This turns the agent's own tool events into a line
now and then -- "I'm reading noise_floor.py.", "Running the tests." -- and
nothing else. No model writes these: every sentence comes from an event the
agent really emitted, through a fixed table, so it can never describe
something that did not happen.

Three parts, each testable alone:

- `describe(name, args)` turns one tool call into an `Activity`, or None for
  a tool that has nothing to say (a to-do list, a tool search).
- `Narrator` decides *when* to speak and *what*: it waits for silence, spaces
  its lines further apart as a turn goes on, groups bursts ("I've looked
  through six files."), never repeats itself, and never starts once the
  agent has begun to talk.
- The privacy filter: a secret file is "a config file", a command line is
  never read out, and a finished sentence that still looks like it holds a
  key is dropped rather than said.

Every line has two forms: `text` for the screen, which shows the real file
name, and `spoken` for the voice, which says it the way a person would.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from urllib.parse import urlsplit

LEVELS = ("off", "brief", "detailed")

#: Seconds with nothing said before the first line.
SILENCE_S = 7.0
#: Seconds from one line to the next, growing so a long task doesn't chatter.
GAPS_S = (10.0, 15.0, 25.0)
#: A burst still arriving is waited for, so six reads become one line...
SETTLE_S = 1.5
#: ...but not for ever.
SETTLE_MAX_S = 3.0

#: Tools that do nothing a listener would want to hear about.
SILENT_TOOLS = frozenset({
    "TodoWrite", "TodoRead", "ToolSearch", "TaskList", "TaskGet",
    "TaskUpdate", "TaskCreate", "TaskOutput", "BashOutput", "KillShell",
    "KillBash", "ExitPlanMode", "EnterPlanMode", "AskUserQuestion",
    "SendFeedback", "ListAgents", "ScheduleWakeup",
})

_NUMBERS = ("no", "one", "two", "three", "four", "five", "six", "seven",
            "eight", "nine", "ten", "eleven", "twelve")


def number(n: int) -> str:
    return _NUMBERS[n] if 0 <= n < len(_NUMBERS) else str(n)


# --- privacy ---------------------------------------------------------------

#: A path that is never named: keys, tokens, the files that hold them.
_SECRET_PATH = re.compile(
    r"(^|[/\\])(\.env(\.[\w.-]*)?|\.netrc|\.npmrc|\.pypirc|\.pgpass|"
    r"id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|auth\.json|credentials(\.\w+)?|"
    r"secrets?(\.\w+)?|[\w.-]*token[\w.-]*|[\w.-]*password[\w.-]*|"
    r"endpoint\.key)$"
    r"|[/\\]\.(ssh|gnupg|aws|kube|docker|password-store)([/\\]|$)"
    r"|\.(pem|key|p12|pfx|kdbx|gpg|asc)$",
    re.IGNORECASE)

#: Something in a finished sentence that looks like a key. A line that
#: matches is dropped, not edited: half a sentence is no use, and a filter
#: that edits can be talked round.
_SECRET_TEXT = re.compile(
    r"sk-[A-Za-z0-9_-]{6,}|gh[pousr]_[A-Za-z0-9]{10,}|AKIA[0-9A-Z]{12,}"
    r"|xox[abpr]-[A-Za-z0-9-]{8,}|AIza[0-9A-Za-z_-]{20,}"
    r"|\b[A-Za-z0-9+/_-]{32,}\b|\b[0-9a-f]{24,}\b"
    r"|\.env\b|\.ssh\b|\.gnupg\b|\bid_(rsa|ed25519)\b"
    r"|\b(api[_ ]?key|password|passwd|secret|token|bearer)\b",
    re.IGNORECASE)

#: A command that sets, sends or reads something private. Its description is
#: not used either, because the model may have quoted the value in it.
_SECRET_COMMAND = re.compile(
    r"\b[A-Z][A-Z0-9_]*(KEY|TOKEN|SECRET|PASSWORD|PASS)[A-Z0-9_]*=|"
    r"authorization:|bearer\s|--password|--token|-p\s*\S+@|"
    r"\b(pass|gpg|secret-tool|keyring|ssh-add|ssh-keygen)\b",
    re.IGNORECASE)


def secret_path(path: str) -> bool:
    return bool(path) and bool(_SECRET_PATH.search(path.strip()))


def looks_secret(text: str) -> bool:
    return bool(_SECRET_TEXT.search(text or ""))


# --- how a file name is said ----------------------------------------------

_EXT_SPOKEN = {
    "py": "dot py", "qml": "dot Q M L", "md": "dot M D", "json": "dot JSON",
    "toml": "dot toml", "sh": "dot S H", "txt": "dot text", "js": "dot J S",
    "ts": "dot T S", "yaml": "dot yaml", "yml": "dot yaml", "html": "dot HTML",
    "css": "dot CSS", "rs": "dot R S", "go": "dot go", "c": "dot C",
    "cpp": "dot C P P", "h": "dot H", "jsonl": "dot JSON L", "lock": "dot lock",
    "ini": "dot ini", "conf": "dot conf", "cfg": "dot config",
}


def base_name(path: str) -> str:
    path = (path or "").rstrip("/\\")
    return re.split(r"[/\\]", path)[-1] if path else ""


def spoken_file(name: str) -> str:
    """"noise_floor.py" -> "noise floor dot py"; "README.md" -> "README dot M D"."""
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        stem, ext = name, ""
    words = re.sub(r"[_\-]+", " ", stem).strip()
    if ext:
        words += " " + _EXT_SPOKEN.get(ext.lower(), "dot " + " ".join(ext.upper()))
    return words


def _speakable_name(name: str) -> bool:
    """Short and wordlike enough to be worth saying aloud."""
    return 0 < len(name) <= 40 and not looks_secret(name) and \
        bool(re.fullmatch(r"[\w.\- ]+", name))


# --- one tool call -> one activity ----------------------------------------

@dataclass
class Activity:
    """One thing the agent did, in words.

    `kind` groups activities for bursts and for the "something new" rule.
    `item` is what it was done to, as shown on screen (a file name, a
    query, a host, the spoken name of a command); `item_spoken` is the same
    for the voice. Either may be empty, and then only the kind is told.
    """
    kind: str
    item: str = ""
    item_spoken: str = ""
    helper: bool = False
    long: bool = False
    t: float = 0.0
    done: bool = False
    tool_id: str = ""
    #: `item` is the agent's own description of a command, not a phrase
    #: from the table.
    described: bool = False


def _file_activity(kind: str, path: str) -> Activity:
    if secret_path(path):
        return Activity(kind, "a config file", "a config file")
    name = base_name(path)
    if not _speakable_name(name):
        return Activity(kind)
    return Activity(kind, name, spoken_file(name))


#: Commands that are said by what they are for, never by what they are.
#: (program, first argument or None) -> (words, takes a while)
_COMMANDS: dict[tuple[str, str | None], tuple[str, bool]] = {
    ("agentvoice-check", None): ("running the checks", True),
    ("pytest", None): ("running the tests", True),
    ("tox", None): ("running the tests", True),
    ("npm", "test"): ("running the tests", True),
    ("cargo", "test"): ("running the tests", True),
    ("go", "test"): ("running the tests", True),
    ("make", "test"): ("running the tests", True),
    ("make", "check"): ("running the checks", True),
    ("git", "status"): ("checking what has changed", False),
    ("git", "diff"): ("looking at the changes", False),
    ("git", "log"): ("looking at the history", False),
    ("git", "show"): ("looking at a commit", False),
    ("git", "blame"): ("looking at the history", False),
    ("git", "commit"): ("committing", False),
    ("git", "push"): ("pushing", True),
    ("git", "pull"): ("pulling the latest changes", True),
    ("git", "fetch"): ("fetching the latest changes", True),
    ("git", "clone"): ("cloning a repository", True),
    ("git", "checkout"): ("switching branches", False),
    ("git", "switch"): ("switching branches", False),
    ("git", "branch"): ("looking at the branches", False),
    ("git", "stash"): ("stashing changes", False),
    ("git", "add"): ("staging changes", False),
    ("git", None): ("using git", False),
    ("gh", None): ("checking GitHub", True),
    ("ls", None): ("looking through the folders", False),
    ("tree", None): ("looking through the folders", False),
    ("find", None): ("looking for files", False),
    ("fd", None): ("looking for files", False),
    ("wc", None): ("counting lines", False),
    ("grep", None): ("searching the code", False),
    ("rg", None): ("searching the code", False),
    ("ag", None): ("searching the code", False),
    ("du", None): ("checking disk usage", False),
    ("df", None): ("checking disk space", False),
    ("pip", "install"): ("installing packages", True),
    ("pip3", "install"): ("installing packages", True),
    ("uv", "pip"): ("installing packages", True),
    ("uv", "sync"): ("installing packages", True),
    ("uv", "add"): ("installing packages", True),
    ("npm", "install"): ("installing packages", True),
    ("npm", "ci"): ("installing packages", True),
    ("npm", "run"): ("running a script", True),
    ("pnpm", "install"): ("installing packages", True),
    ("pnpm", "add"): ("installing packages", True),
    ("yarn", None): ("installing packages", True),
    ("pacman", None): ("installing packages", True),
    ("yay", None): ("installing packages", True),
    ("paru", None): ("installing packages", True),
    ("cargo", "build"): ("building it", True),
    ("cargo", "run"): ("building and running it", True),
    ("make", None): ("building it", True),
    ("cmake", None): ("building it", True),
    ("ninja", None): ("building it", True),
    ("qmake6", None): ("building it", True),
    ("go", "build"): ("building it", True),
    ("curl", None): ("fetching something from the web", False),
    ("wget", None): ("downloading something", True),
    ("journalctl", None): ("reading the logs", False),
    ("systemctl", None): ("checking the service", False),
    ("docker", None): ("using Docker", True),
    ("podman", None): ("using Podman", True),
    ("mkdir", None): ("making a folder", False),
    ("cp", None): ("copying files", False),
    ("mv", None): ("moving files", False),
    ("rm", None): ("deleting files", False),
    ("chmod", None): ("changing file permissions", False),
    ("tar", None): ("unpacking an archive", False),
    ("unzip", None): ("unpacking an archive", False),
    ("qmllint", None): ("checking the QML", False),
    ("ruff", None): ("checking the code style", False),
    ("mypy", None): ("checking the types", True),
    ("shellcheck", None): ("checking the shell scripts", False),
    ("hyprctl", None): ("asking Hyprland", False),
    ("omarchy", None): ("running an Omarchy command", False),
    ("agentvoice", None): ("using agentvoice", False),
}

#: Programs that read a file, so the command is told as reading it.
_READERS = frozenset({"cat", "head", "tail", "less", "more", "bat", "nl"})
#: Programs not worth a word on their own.
_NOTHING = frozenset({"echo", "printf", "true", "false", "sleep", "cd",
                      "pwd", "date", "which", "type", "command", "test", "["})
_INTERPRETERS = frozenset({"python", "python3", "node", "bash", "sh", "zsh",
                           "ruby", "perl", "deno", "bun"})


def _words(command: str) -> list[list[str]]:
    """The command's simple commands, each as words, wrappers taken off."""
    out = []
    for part in re.split(r"&&|\|\||;|\||\n", command):
        try:
            words = shlex.split(part, comments=True)
        except ValueError:
            words = part.split()
        while words and (re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0])
                         or words[0] in ("sudo", "env", "time", "nice",
                                         "timeout", "xargs", "exec", "nohup")):
            words = words[1:]
            if words and re.fullmatch(r"-?\d+[smh]?|-\w+", words[0]):
                words = words[1:]
        if words:
            words[0] = base_name(words[0])
            out.append(words)
    return out


def _command_activity(command: str, description: str, detailed: bool) -> Activity | None:
    if _SECRET_COMMAND.search(command):
        return Activity("run", "a command", "a command")
    simple = [w for w in _words(command) if w[0] not in _NOTHING]
    if any(secret_path(w) for w in re.split(r"[\s'\"=<>]+", command) if w):
        # Reading one is a config file, like the Read tool; anything else
        # done to one is just a command.
        if len(simple) == 1 and simple[0][0] in _READERS:
            return Activity("read", "a config file", "a config file")
        return Activity("run", "a command", "a command")
    if not simple:
        return None
    for words in simple:
        prog = words[0]
        arg = next((w for w in words[1:] if not w.startswith("-")), None)
        if prog in ("python", "python3") and len(words) > 2 and words[1] == "-m":
            if words[2] == "pytest":
                return Activity("run", "running the tests", long=True)
            if words[2] == "pip" and "install" in words:
                return Activity("run", "installing packages", long=True)
        if (prog in _READERS and arg) or (prog == "sed" and "-n" in words):
            target = words[-1]
            return _file_activity("read", target)
        hit = _COMMANDS.get((prog, arg)) or _COMMANDS.get((prog, None))
        if hit:
            return Activity("run", hit[0], hit[0], long=hit[1])
        if prog in _INTERPRETERS:
            script = next((w for w in words[1:] if not w.startswith("-")), "")
            if "-c" in words or not script:
                return Activity("run", "running a short script", long=False)
            name = base_name(script)
            if _speakable_name(name):
                return Activity("run", f"running {name}",
                                f"running {spoken_file(name)}", long=True)
            return Activity("run", "running a script", long=True)
    # Unknown: the agent's own one-line description, when it is safe to say.
    desc = re.sub(r"\s+", " ", description or "").strip().rstrip(".")
    if detailed and desc and len(desc) <= 70 and not looks_secret(desc):
        desc = desc[0].lower() + desc[1:]
        return Activity("run", desc, desc, described=True)
    return Activity("run")


def _host(url: str) -> str:
    try:
        host = urlsplit(url if "//" in url else "//" + url).hostname or ""
    except ValueError:
        return ""
    host = host[4:] if host.startswith("www.") else host
    return host if _speakable_name(host) else ""


def _query(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    # A long query is a mouthful that runs into the answer; the short form
    # ("I'm searching the web.") says as much.
    if not text or len(text) > 60 or len(text.split()) > 6 or looks_secret(text):
        return ""
    return text


def _pattern(text: str) -> str:
    """A search pattern worth saying: words, not a regular expression."""
    text = (text or "").strip()
    if (not text or len(text) > 30 or looks_secret(text)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_ .-]*", text)):
        return ""
    return text


def describe(name: str, args: dict | None, *, detailed: bool = True,
             helper: bool = False) -> Activity | None:
    """What a tool call is, in words, or None when it is not worth any."""
    args = args if isinstance(args, dict) else {}
    act = _describe(name or "", args, detailed)
    if act is not None:
        act.helper = helper
    return act


def _describe(name: str, args: dict, detailed: bool) -> Activity | None:
    if name in SILENT_TOOLS:
        return None
    if name in ("Read", "NotebookRead", "read_file", "view"):
        return _file_activity("read", args.get("file_path") or args.get("path") or "")
    if name in ("Edit", "MultiEdit", "NotebookEdit", "edit_file", "replace"):
        return _file_activity("edit", args.get("file_path") or
                              args.get("notebook_path") or args.get("path") or "")
    if name in ("Write", "write_file", "create_file"):
        return _file_activity("write", args.get("file_path") or args.get("path") or "")
    if name in ("Grep", "search_file_content", "grep"):
        pattern = _pattern(args.get("pattern", ""))
        return Activity("search", pattern, pattern)
    if name in ("Glob", "glob", "list_directory", "LS"):
        literal = base_name(args.get("pattern", ""))
        if "*" in literal or "?" in literal or not _speakable_name(literal):
            literal = ""
        return Activity("find", literal, spoken_file(literal) if literal else "")
    if name in ("Bash", "run_shell_command", "shell", "command_execution"):
        return _command_activity(str(args.get("command", "")),
                                 str(args.get("description", "")), detailed)
    if name in ("WebSearch", "web_search", "google_web_search"):
        q = _query(args.get("query", ""))
        return Activity("web_search", q, q)
    if name in ("WebFetch", "web_fetch"):
        host = _host(str(args.get("url", "")))
        return Activity("web_fetch", host, " dot ".join(host.split(".")) if host else "")
    if name in ("Task", "Agent"):
        desc = re.sub(r"\s+", " ", str(args.get("description", ""))).strip().rstrip(".")
        if not desc or len(desc) > 60 or looks_secret(desc):
            desc = ""
        else:
            desc = desc[0].lower() + desc[1:]
        return Activity("helper", desc, desc, long=True)
    if name == "Skill":
        skill = str(args.get("skill", "")).split(":")[-1].replace("-", " ")
        return Activity("skill", skill if _speakable_name(skill) else "",
                        skill if _speakable_name(skill) else "")
    if name == "file_change":
        changes = args.get("changes") or []
        paths = [c.get("path", "") for c in changes if isinstance(c, dict)]
        if len(paths) == 1:
            return _file_activity("edit", paths[0])
        return Activity("edit", "", "")
    if name.startswith("mcp__"):
        server = name.split("__")[1] if name.count("__") >= 2 else ""
        if "chrome" in server or "browser" in server:
            return Activity("tool", "the browser", "the browser")
        server = re.sub(r"[_\-]+", " ", server).strip()
        return Activity("tool", server if _speakable_name(server) else "",
                        server if _speakable_name(server) else "")
    if name == "mcp_tool_call":
        server = re.sub(r"[_\-]+", " ", str(args.get("server", ""))).strip()
        return Activity("tool", server if _speakable_name(server) else "",
                        server if _speakable_name(server) else "")
    return Activity("tool")


# --- activities -> a sentence ----------------------------------------------

@dataclass
class Line:
    text: str
    spoken: str
    kinds: frozenset = field(default_factory=frozenset)
    t: float = 0.0
    #: The activities it was made from, so a check can prove every line
    #: came from something that had already happened.
    sources: tuple = ()


def _one(act: Activity, detailed: bool) -> tuple[str, str]:
    """A sentence about a single activity: (screen, voice)."""
    item = act.item if detailed else ""
    said = (act.item_spoken or act.item) if detailed else ""
    who = "My helper is" if act.helper else "I'm"
    k = act.kind
    if k == "read":
        if act.item == "a config file":
            return f"{who} reading a config file.", f"{who} reading a config file."
        if item:
            return f"{who} reading {item}.", f"{who} reading {said}."
        return f"{who} reading through the files.", f"{who} reading through the files."
    if k == "edit":
        if act.item == "a config file":
            return f"{who} editing a config file.", f"{who} editing a config file."
        if item:
            return f"{who} editing {item}.", f"{who} editing {said}."
        return f"{who} making changes.", f"{who} making changes."
    if k == "write":
        if item and act.item != "a config file":
            return f"{who} writing {item}.", f"{who} writing {said}."
        return f"{who} writing a new file.", f"{who} writing a new file."
    if k == "search":
        if item:
            return f"{who} searching the code for {item}.", f"{who} searching the code for {said}."
        return f"{who} searching the code.", f"{who} searching the code."
    if k == "find":
        if item:
            return f"{who} looking for {item}.", f"{who} looking for {said}."
        return f"{who} looking for files.", f"{who} looking for files."
    if k == "run":
        # Known commands keep their name in brief too: "running the tests"
        # names a stage, not a detail. A description or a script name is a
        # detail.
        spoken = act.item_spoken or act.item
        if act.item == "a command" or not act.item:
            return f"{who} running a command.", f"{who} running a command."
        if act.described:
            if detailed:
                return (f"{who} running a command to {act.item}.",
                        f"{who} running a command to {spoken}.")
            return f"{who} running a command.", f"{who} running a command."
        # A script's name is a detail; brief says only that one is running.
        if not detailed and act.item.startswith("running ") and \
                act.item not in ("running the tests", "running the checks"):
            return f"{who} running a script.", f"{who} running a script."
        return f"{who} {act.item}.", f"{who} {spoken}."
        return f"{who} running a command.", f"{who} running a command."
    if k == "web_search":
        if item:
            return f"{who} searching the web for {item}.", f"{who} searching the web for {said}."
        return f"{who} searching the web.", f"{who} searching the web."
    if k == "web_fetch":
        if item:
            return f"{who} reading a page on {item}.", f"{who} reading a page on {said}."
        return f"{who} reading a web page.", f"{who} reading a web page."
    if k == "helper":
        if item:
            return (f"I've started a helper to {item}.",
                    f"I've started a helper to {said}.")
        return "I've started a helper on part of this.", "I've started a helper on part of this."
    if k == "skill":
        if item:
            return f"{who} using the {item} skill.", f"{who} using the {said} skill."
        return f"{who} using a skill.", f"{who} using a skill."
    if k == "tool":
        if item:
            return f"{who} using {item}.", f"{who} using {said}."
        return f"{who} using a tool.", f"{who} using a tool."
    return f"{who} working on it.", f"{who} working on it."


def _count(n: int, one: str, many: str) -> str:
    return f"{number(n)} {one if n == 1 else many}"


def _times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(n, "several times" if n > 3 else f"{number(n)} times")


def _many(kind: str, acts: list[Activity]) -> str:
    """A phrase for several of one kind, past tense: "looked through six files"."""
    n = len(acts)
    files = len({a.item for a in acts if a.item}) or n
    if kind == "read":
        return f"looked through {_count(files, 'file', 'files')}"
    if kind == "edit":
        return f"changed {_count(files, 'file', 'files')}"
    if kind == "write":
        return f"written {_count(files, 'file', 'files')}"
    if kind == "search":
        return f"searched the code {_times(n)}"
    if kind == "find":
        return f"looked for files {_times(n)}"
    if kind == "run":
        return f"run {_count(n, 'command', 'commands')}"
    if kind == "web_search":
        return f"searched the web {_times(n)}"
    if kind == "web_fetch":
        return f"read {_count(n, 'web page', 'web pages')}"
    if kind == "helper":
        return f"started {_count(n, 'helper', 'helpers')}"
    return f"used {_count(n, 'tool', 'tools')}"


def compose(acts: list[Activity], detailed: bool) -> Line | None:
    """One line for the activities since the last one, or None.

    A single activity, or one still running, is told as it is ("I'm reading
    Panel.qml."). Several are summed up by kind, at most two kinds, in the
    order they happened ("I've looked through six files and run two
    commands.").
    """
    if not acts:
        return None
    # A helper's work is told as the helper's. Starting it is only news when
    # it is all there is; once it is working, what it does says more.
    if any(a.helper for a in acts):
        acts = [a for a in acts if a.kind != "helper" or a.helper]
    running = [a for a in acts if not a.done and (a.long or a is acts[-1])]
    if len(acts) == 1 or (running and running[-1] is acts[-1] and acts[-1].long):
        act = running[-1] if running else acts[0]
        text, spoken = _one(act, detailed)
        return Line(text, spoken, frozenset({act.kind}))
    order: list[str] = []
    groups: dict[str, list[Activity]] = {}
    for a in acts:
        if a.kind not in groups:
            order.append(a.kind)
            groups[a.kind] = []
        groups[a.kind].append(a)
    if len(order) == 1 and len(groups[order[0]]) == 1:
        text, spoken = _one(acts[-1], detailed)
        return Line(text, spoken, frozenset(order))
    top = sorted(order, key=lambda k: -len(groups[k]))[:2]
    top = [k for k in order if k in top]
    helper = all(a.helper for a in acts)
    who = "My helper has" if helper else "I've"
    if len(top) == 1:
        phrase = _many(top[0], groups[top[0]])
    else:
        phrase = f"{_many(top[0], groups[top[0]])} and {_many(top[1], groups[top[1]])}"
    text = f"{who} {phrase}."
    return Line(text, text, frozenset(top))


# --- when to speak ---------------------------------------------------------

_STEM = re.compile(r"(?:'s|ing|es|ed|s)$")
_FILLER = frozenset({"i'm", "im", "i've", "ive", "the", "a", "an", "and",
                     "to", "of", "for", "on", "in", "my", "now", "it",
                     "this", "that", "through", "some", "let", "me", "i'll",
                     "going", "will", "with"})


def _stems(text: str) -> set[str]:
    words = re.findall(r"[a-z][a-z']*", text.lower())
    return {_STEM.sub("", w) for w in words if w not in _FILLER and len(w) > 2}


class Narrator:
    """Decides when a line is due, for one turn.

    Fed with the turn's events as they happen (`activity`, `finished`,
    `text`, `spoke`), and asked `due(now)` whenever the caller has a moment.
    Times are seconds on whatever clock the caller uses; the replay tool
    feeds recorded ones.

    The rules, from plan.md, plus two the recorded turns asked for:

    - nothing until `silence_s` has passed with nothing said, by the agent or
      by this;
    - then at least `gaps_s[0]` between lines, growing to `gaps_s[1]`, then
      `gaps_s[2]` for every line after;
    - only about activity not yet told, of a kind the last line did not
      cover, and never the same sentence twice;
    - never while the agent is writing words: text blocks narration until
      it starts another tool, so a line never starts once the answer has;
    - only while a tool is running. Between tools the model is writing, and
      what it writes next may be the answer: a line started then was cut
      off by it in the recordings;
    - not when the agent has just said the same thing itself ("Running the
      check script now." makes "I'm running the checks." redundant).
    """

    def __init__(self, level: str = "brief", *, silence_s: float = SILENCE_S,
                 gaps_s: tuple[float, ...] = GAPS_S, start: float = 0.0) -> None:
        self.level = level if level in LEVELS else "brief"
        self.silence_s = silence_s
        self.gaps_s = tuple(gaps_s) or GAPS_S
        self.quiet_since = start        # the last moment anything was said
        self.pending: list[Activity] = []   # happened, not yet told
        self.running: dict[str, Activity] = {}
        self.lines: list[Line] = []
        self.said: set[str] = set()
        self.last_kinds: frozenset = frozenset()
        self.talking = False            # the agent is writing words
        self._agent_words: set[str] = set()

    @property
    def detailed(self) -> bool:
        return self.level == "detailed"

    def activity(self, act: Activity | None, now: float, tool_id: str = "") -> None:
        """The agent started something. `act` None is a tool not worth a
        word, which still means the agent is working, not talking."""
        self.talking = False
        if act is None:
            act = Activity("", t=now)
            act.done = True
        act.t = now
        act.tool_id = tool_id or act.tool_id
        if act.kind:
            self.pending.append(act)
        if act.tool_id and not act.done:
            self.running[act.tool_id] = act

    def finished(self, tool_id: str) -> None:
        """A tool returned."""
        act = self.running.pop(tool_id, None)
        if act is not None:
            act.done = True

    def text(self) -> None:
        """The agent is writing words: its plan sentence, or its answer."""
        self.talking = True

    def agent_said(self, sentence: str, until: float) -> None:
        """The agent said `sentence` aloud, ending at `until`."""
        self._agent_words = _stems(sentence)
        self.spoke(until)

    def spoke(self, until: float) -> None:
        """Something was said aloud, ending at `until`."""
        self.quiet_since = max(self.quiet_since, until)

    def next_allowed(self) -> float:
        wait = self.quiet_since + self.silence_s
        if self.lines:
            gap = self.gaps_s[min(len(self.lines) - 1, len(self.gaps_s) - 1)]
            wait = max(wait, self.lines[-1].t + gap)
        return wait

    def due(self, now: float) -> Line | None:
        """The line to say now, if one is due. Saying it is the caller's job,
        and so is calling `spoke()` when it ends."""
        if (self.level == "off" or self.talking or not self.pending
                or not self.running or now < self.next_allowed()):
            return None
        last = self.pending[-1]
        # A burst still arriving: wait for it, so it is told as one line.
        same = sum(1 for a in self.pending if a.kind == last.kind)
        if same > 1 and now - last.t < SETTLE_S and \
                now - self.pending[0].t < SETTLE_MAX_S + SETTLE_S:
            return None
        line = compose(self.pending, self.detailed)
        told = self.pending
        self.pending = []
        if line is None or line.text in self.said \
                or not (line.kinds - self.last_kinds):
            return None
        if looks_secret(line.text) or looks_secret(line.spoken):
            return None
        mine = _stems(line.spoken)
        if mine and mine <= self._agent_words:
            return None
        line.t = now
        line.sources = tuple(told)
        self.lines.append(line)
        self.said.add(line.text)
        self.last_kinds = line.kinds
        return line
