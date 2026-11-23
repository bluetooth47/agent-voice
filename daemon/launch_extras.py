"""Extra flags and environment variables for an agent's program (phase M17).

Agent details → Advanced lets the person add flags to the command line an
agent's program starts with, and environment variables to its process. Both
are a way round everything else Agent Voice decides: one flag switches off
the permission hook (`--bare`, `--dangerously-skip-permissions`), one
environment variable loads code into the hook itself (`PYTHONPATH`) or sends
the agent's key to another host (`ANTHROPIC_BASE_URL`). So both are checked
here, against a list per program of what is never passed, **at launch, in
the adapter** -- not only on the page. What the page refuses the daemon
refuses too, whoever wrote the setting, and a refusal stops the turn with
the reason rather than quietly dropping the flag: a control that does
nothing must say why.

A denylist, not an allowlist (the user's answer to question 12 of the
master plan): the CLIs add flags every month and most are harmless; the
categories that are not can be named. To keep a denylist honest it is
written three ways at once:

- **exact names**, read off each CLI's `--help` (claude 2.1.330, codex
  0.171.0), each with the category it falls in;
- **words** that put a flag in a refused category whatever it is called, so
  a flag added next month as `--permission-foo` or `--mcp-bar` is refused
  before anyone has read about it;
- **shapes**: every element is a flag on its own -- `--name`,
  `--name=value`, `-x` or `-x=value` -- never a bare word (a bare word is a
  subcommand, `claude mcp add` or `codex exec resume`, or the request
  itself), never `--` (everything after it is a bare word), one short flag
  per element (`-abc` is three), and a name that begins a refused one is
  refused (`--dangerously`), since some parsers take an abbreviation.
  `--no-X` is judged as X too.

Extra flags and environment are offered for Claude Code and Codex only: the
two whose flags were read for this list, and the two that answer turns in
daily use. Another program is passed none of them, and the page says so.

The environment lives in `~/.config/agentvoice/agent-env.json`, 0600, never
in shell.json (0644, readable by every account): a key belongs there and
not in a flag, which `/proc/<pid>/cmdline` shows to anyone. Its values are
never printed, logged, published in runinfo or shown on the page; only the
names are.
"""
from __future__ import annotations

import contextlib
import errno
import json
import os
import re
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

#: The programs extra flags and environment are passed to.
PROGRAMS = ("claude", "codex")

#: At most this many flags, each at most this long. Past either, the launch
#: is refused with the reason; a list longer than READ_MAX is not read at all.
MAX_ARGS = 16
ARG_MAX = 200
READ_MAX = 64


class LaunchRefused(Exception):
    """The agent's extra flags or environment include something Agent Voice
    never passes. The message is ours and names the flag by its name only
    (never a value: a value may be a key), so it is safe to show and say."""


#: What each category of refused flag would do, in words for the page and
#: for the turn that was refused.
WHY = {
    "level": "it changes what the agent may do without asking, which its permission level decides",
    "hooks": "it changes or skips hooks, and the permission check is a hook",
    "config": "it loads settings or configuration that Agent Voice has not read",
    "mcp": "it changes the agent's MCP servers, which are switched on Tools & skills",
    "tools": "it changes which tools the agent has, which is Tools & skills",
    "skills": "it changes the skills, plugins or helper agents it loads, which are on Tools & skills",
    "dirs": "it widens or moves the folders the agent works in; its project folder is set on the Agents page",
    "prompt": "it changes what the agent is told, which is Personality & instructions",
    "session": "it changes which conversation is resumed or kept, which Agent Voice decides",
    "stream": "it changes the output Agent Voice reads, so the reply could not be understood or spoken",
    "own": "Agent Voice passes this itself",
    "model": "the model and effort are chosen on the Agents page",
    "writes": "it writes files, outside what the permission level allows",
    "elsewhere": "it runs the agent somewhere other than here, or in the background",
    "exits": "it prints something and exits, so no turn could run",
    "secret": ("it carries a secret, and a command line can be read by every account on this "
               "computer: put a key in an environment variable instead"),
    "bare": ("not a flag: every element starts with -, and a value goes after = (--flag=value), "
             "so nothing can be read as a command or as the request"),
    "end": "-- ends the flags, so everything after it would be read as a command or as the request",
    "cluster": "one short flag per element (-abc is three flags): write them separately",
    "shape": "not a flag name Agent Voice can check",
    "control": "it holds a control character",
    "long": f"longer than {ARG_MAX} characters",
    "many": f"more than {MAX_ARGS} extra flags",
    "program": "extra flags are passed to Claude Code and Codex only",
}

# --- Claude Code (claude --help, 2.1.330) -------------------------------------------

_CLAUDE_DENY = {
    # What it may do without asking.
    "permission-mode": "level", "dangerously-skip-permissions": "level",
    "allow-dangerously-skip-permissions": "level", "permission-prompt-tool": "level",
    "permission-prompts": "level", "restricted": "level",
    # Hooks are how it asks: --bare and --safe-mode start without them.
    "bare": "hooks", "safe-mode": "hooks", "include-hook-events": "stream",
    "settings": "config", "setting-sources": "config",
    "mcp-config": "mcp", "strict-mcp-config": "mcp", "ide": "mcp",
    "allowedtools": "tools", "allowed-tools": "tools", "disallowedtools": "tools",
    "disallowed-tools": "tools", "tools": "tools", "brief": "tools",
    "chrome": "own", "no-chrome": "own",
    "plugin-dir": "skills", "plugin-url": "skills", "disable-slash-commands": "skills",
    "agents": "skills", "agent": "skills",
    "add-dir": "dirs", "worktree": "dirs", "tmux": "dirs",
    "system-prompt": "prompt", "system-prompt-file": "prompt",
    "append-system-prompt": "prompt", "append-system-prompt-file": "prompt",
    "system-prompt-snapshot": "prompt", "exclude-dynamic-system-prompt-sections": "prompt",
    "resume": "session", "continue": "session", "fork-session": "session",
    "session-id": "session", "no-session-persistence": "session", "from-pr": "session",
    "teleport": "session",
    "print": "own", "input-format": "stream", "output-format": "stream",
    "include-partial-messages": "stream", "verbose": "own", "replay-user-messages": "stream",
    "forward-subagent-text": "stream", "prompt-suggestions": "stream", "json-schema": "stream",
    "model": "model", "effort": "model",
    "debug-file": "writes", "file": "writes",
    "bg": "elsewhere", "background": "elsewhere", "cloud": "elsewhere",
    "environment": "elsewhere", "remote-control": "elsewhere",
    "remote-control-session-name-prefix": "elsewhere", "desktop": "elsewhere",
    "help": "exits", "version": "exits",
}
#: Its short flags, each with what it stands for.
_CLAUDE_SHORT = {"p": "own", "c": "session", "r": "session", "w": "dirs",
                 "h": "exits", "v": "exits"}
#: Read in its --help and found harmless: passed after a confirm. Listed so a
#: name here is never refused for beginning a longer refused one
#: (`--debug` and `--debug-file`).
_CLAUDE_KNOWN = {"autocompact", "ax-screen-reader", "betas", "debug", "fallback-model",
                 "max-budget-usd", "name", "max-turns"}

# --- Codex (codex exec --help, 0.171.0) ----------------------------------------------

_CODEX_DENY = {
    "config": "config", "enable": "config", "disable": "config", "profile": "config",
    "strict-config": "config", "ignore-user-config": "config",
    "sandbox": "level", "approve-for-me": "own", "full-auto": "level", "yolo": "level",
    "ask-for-approval": "level", "dangerously-bypass-approvals-and-sandbox": "level",
    "dangerously-bypass-hook-trust": "hooks", "trust": "level", "ignore-rules": "level",
    "cyber-access-program": "level",
    "cd": "dirs", "add-dir": "dirs", "worktree": "dirs", "skip-git-repo-check": "own",
    "ephemeral": "own", "thread-source": "session", "last": "session",
    "json": "own", "output-schema": "stream", "experimental-json": "stream",
    "output-last-message": "writes",
    "image": "prompt",
    "model": "model",
    "remote": "elsewhere", "remote-auth-token-env": "elsewhere",
    "help": "exits", "version": "exits",
}
#: Case-folded: -c is --config and -C is --cd, both refused; -V is --version.
_CODEX_SHORT = {"c": "config", "p": "config", "s": "level", "a": "level", "i": "prompt",
                "o": "writes", "m": "model", "h": "exits", "v": "exits"}
_CODEX_KNOWN = {"color", "oss", "local-provider"}

_RULES = {
    "claude": (_CLAUDE_DENY, _CLAUDE_SHORT, _CLAUDE_KNOWN),
    "codex": (_CODEX_DENY, _CODEX_SHORT, _CODEX_KNOWN),
}

#: A word anywhere in a flag's name (dashes and underscores taken out) that
#: puts it in a refused category, whatever program and whatever it is
#: called. Checked after the exact names and before the harmless ones, so a
#: name read as harmless that holds one of these is still refused (a test
#: holds that none does).
_WORDS = (
    ("permission", "level"), ("dangerous", "level"), ("bypass", "level"),
    ("sandbox", "level"), ("approv", "level"), ("yolo", "level"), ("trust", "level"),
    ("hook", "hooks"),
    ("setting", "config"), ("config", "config"), ("profile", "config"), ("env", "config"),
    ("mcp", "mcp"),
    ("tool", "tools"), ("allow", "tools"), ("deny", "tools"),
    ("plugin", "skills"), ("skill", "skills"), ("agent", "skills"), ("extension", "skills"),
    ("dir", "dirs"), ("worktree", "dirs"), ("workspace", "dirs"), ("cwd", "dirs"),
    ("prompt", "prompt"), ("instruction", "prompt"),
    ("resume", "session"), ("continue", "session"), ("session", "session"),
    ("fork", "session"), ("conversation", "session"), ("thread", "session"),
    ("ephemeral", "session"), ("persist", "session"),
    ("format", "stream"), ("stream", "stream"), ("json", "stream"), ("schema", "stream"),
    ("output", "stream"), ("replay", "stream"), ("partial", "stream"),
    ("remote", "elsewhere"), ("cloud", "elsewhere"), ("background", "elsewhere"),
    ("teleport", "elsewhere"), ("detach", "elsewhere"), ("server", "elsewhere"),
    ("key", "secret"), ("token", "secret"), ("secret", "secret"), ("passw", "secret"),
    ("auth", "secret"), ("credential", "secret"), ("cookie", "secret"),
)

_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def args_choice(raw) -> list[str] | None:
    """`extraArgs` as written: a list of strings, read as it is (every
    element is judged at launch, loudly). None when it is not a list of
    strings, or longer than READ_MAX: unreadable, and nothing is passed."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > READ_MAX:
        return None
    if not all(isinstance(x, str) for x in raw):
        return None
    return list(raw)


def _shown(arg: str) -> str:
    """How a flag is named in a refusal: its name, never its value (a value
    may be a key), cut short, with control characters out."""
    head = arg.split("=", 1)[0]
    head = _CONTROL.sub("", head)
    return head[:48] + ("…" if len(head) > 48 else "")


def _judge_name(name: str, deny: dict, known: set) -> str | None:
    """The category a long flag's name falls in, or None to pass it."""
    for n in (name, name[3:] if name.startswith("no-") and len(name) > 3 else None):
        if n is None:
            continue
        if n in deny:
            return deny[n]
    squashed = name.replace("-", "").replace("_", "")
    for word, why in _WORDS:
        if word in squashed:
            return why
    # Read in the CLI's help and found harmless: never refused as the
    # beginning of a longer refused name (`--debug`, `--debug-file`).
    if name in known:
        return None
    # An abbreviation of a refused name, for a parser that takes one.
    for n in (name, name[3:] if name.startswith("no-") else None):
        if n and any(d.startswith(n) and d != n for d in deny):
            return next(deny[d] for d in sorted(deny) if d.startswith(n) and d != n)
    return None


def judge(program: str, arg) -> str | None:
    """Why `arg` is never passed to `program`, as a key of WHY, or None."""
    if program not in _RULES:
        return "program"
    deny, short, known = _RULES[program]
    if not isinstance(arg, str):
        return "shape"
    if _CONTROL.search(arg):
        return "control"
    if len(arg) > ARG_MAX:
        return "long"
    if arg == "--":
        return "end"
    if not arg.startswith("-") or arg == "-":
        return "bare"
    if arg.startswith("--"):
        name = arg[2:].split("=", 1)[0]
        if not name.isascii() or not _NAME.fullmatch(name.lower()):
            return "shape"
        return _judge_name(name.lower(), deny, known)
    # A short flag: exactly one letter, alone or with =value.
    letters = arg[1:].split("=", 1)[0]
    if len(letters) != 1:
        return "cluster"
    if not letters.isascii() or not letters.isalnum():
        return "shape"
    return short.get(letters.lower())


def check(program: str, args) -> list[dict]:
    """Each extra flag with its verdict, for the page: {"arg": its name
    (never a value), "ok", "why" (words, "" when it is passed)}. The same
    judge() the launch uses."""
    out = []
    items = list(args) if isinstance(args, (list, tuple)) else []
    for i, arg in enumerate(items):
        key = "many" if i >= MAX_ARGS else judge(program, arg)
        out.append({"arg": _shown(arg) if isinstance(arg, str) else "?",
                    "ok": key is None, "why": WHY[key] if key else ""})
    return out


def refusal(program: str, args) -> str | None:
    """The first reason `args` cannot be passed to `program`, in a sentence,
    or None when every one can."""
    if not args:
        return None
    if not isinstance(args, (list, tuple)):
        return "its extra flags cannot be read"
    if len(args) > MAX_ARGS:
        return f"it has {WHY['many']}"
    for arg in args:
        key = judge(program, arg)
        if key is not None:
            shown = _shown(arg) if isinstance(arg, str) else "one of them"
            return f"its extra flag {shown} is never passed: {WHY[key]}"
    return None


def checked(program: str, args) -> list[str]:
    """`args`, when every one may be passed to `program`; LaunchRefused
    otherwise. Called by the adapter as it builds the command line, so a
    setting written past the page is refused at the moment it would run."""
    if not args:
        return []
    why = refusal(program, args)
    if why is not None:
        raise LaunchRefused(f"Agent Voice did not start it: {why}. Clear it on Agent details, "
                            f"Advanced.")
    return list(args)


# --- environment variables ------------------------------------------------------------

#: A name a shell would accept.
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
ENV_VALUE_MAX = 8192
#: Per agent.
ENV_MAX = 32
#: The whole file, read.
ENV_FILE_MAX = 256 * 1024

ENV_WHY = {
    "loader": "it changes which code a program loads, the permission hook's included",
    "paths": "it changes where programs and Agent Voice's own files are found",
    "network": "it sends the agent's traffic, and its key, somewhere else",
    "program": ("it changes how the agent's program or Agent Voice runs, in ways the page "
                "cannot show (some switch the permission hook off)"),
    "shell": "it changes what a shell command runs",
    "desktop": "it points the agent at another display, keyring or login",
    "model": "the model is chosen on the Agents page",
    "shape": "not a name a shell accepts (letters, digits and _, not starting with a digit)",
}
_ENV_EXACT = {
    "PATH": "paths", "HOME": "paths", "USER": "paths", "LOGNAME": "paths", "TMPDIR": "paths",
    "SHELL": "shell", "ENV": "shell", "IFS": "shell", "CDPATH": "shell", "PS4": "shell",
    "PROMPT_COMMAND": "shell", "SHELLOPTS": "shell", "ZDOTDIR": "shell", "EDITOR": "shell",
    "VISUAL": "shell", "PAGER": "shell", "MANPAGER": "shell", "BROWSER": "shell",
    "LESSOPEN": "shell", "LESSCLOSE": "shell", "SUDO_ASKPASS": "shell", "SSH_ASKPASS": "shell",
    "DISPLAY": "desktop", "WAYLAND_DISPLAY": "desktop", "DBUS_SESSION_BUS_ADDRESS": "desktop",
    "SSH_AUTH_SOCK": "desktop", "SSH_AGENT_PID": "desktop", "GPG_AGENT_INFO": "desktop",
    "GNUPGHOME": "desktop", "KRB5CCNAME": "desktop", "HYPRLAND_INSTANCE_SIGNATURE": "desktop",
    "NODE_OPTIONS": "loader", "JAVA_TOOL_OPTIONS": "loader", "_JAVA_OPTIONS": "loader",
    "JDK_JAVA_OPTIONS": "loader", "PERL5OPT": "loader", "PERL5LIB": "loader",
    "RUBYOPT": "loader", "RUBYLIB": "loader", "VIRTUAL_ENV": "loader",
    "SSL_CERT_FILE": "network", "SSL_CERT_DIR": "network", "REQUESTS_CA_BUNDLE": "network",
    "CURL_CA_BUNDLE": "network", "NODE_EXTRA_CA_CERTS": "network", "OPENSSL_CONF": "network",
    "CLAUDECODE": "program",
    "ANTHROPIC_MODEL": "model", "ANTHROPIC_SMALL_FAST_MODEL": "model",
}
_ENV_PREFIX = (
    ("LD_", "loader"), ("DYLD_", "loader"), ("PYTHON", "loader"), ("NODE_", "loader"),
    ("NPM_", "loader"), ("BUN_", "loader"), ("DENO_", "loader"), ("GCONV", "loader"),
    ("GLIBC_", "loader"), ("MALLOC_", "loader"), ("CONDA_", "loader"), ("UV_", "loader"),
    ("PIP_", "loader"), ("GEM_", "loader"),
    ("XDG_", "paths"), ("MISE_", "paths"), ("ASDF_", "paths"), ("RTX_", "paths"),
    ("CLAUDE_", "program"), ("CODEX_", "program"), ("AGENTVOICE_", "program"),
    ("OMARCHY_", "program"), ("MCP_", "program"), ("ANTHROPIC_DEFAULT_", "model"),
    ("BASH_", "shell"), ("GIT_", "shell"), ("SSL_", "network"),
)
_ENV_SUFFIX = (
    ("_PROXY", "network"), ("_BASE_URL", "network"), ("_API_BASE", "network"),
    ("_BASE", "network"), ("_URL", "network"), ("_ENDPOINT", "network"), ("_HOST", "network"),
    ("_CA_BUNDLE", "network"), ("_CA_CERTS", "network"),
)


def env_judge(name) -> str | None:
    """Why the variable `name` is never set for an agent, as a key of
    ENV_WHY, or None. Case-folded: `http_proxy` is HTTP_PROXY."""
    if not isinstance(name, str) or not ENV_NAME.fullmatch(name):
        return "shape"
    up = name.upper()
    if up in _ENV_EXACT:
        return _ENV_EXACT[up]
    for prefix, why in _ENV_PREFIX:
        if up.startswith(prefix):
            return why
    for suffix, why in _ENV_SUFFIX:
        if up.endswith(suffix):
            return why
    return None


def env_refusal(name) -> str | None:
    """Why `name` is never set, in a sentence, or None."""
    key = env_judge(name)
    if key is None:
        return None
    shown = _CONTROL.sub("", str(name))[:64] if isinstance(name, str) else "?"
    return f"{shown} is never set for an agent: {ENV_WHY[key]}"


def checked_env(program: str, env) -> dict:
    """`env` when every name may be set for `program`; LaunchRefused
    otherwise. {} for a program extras are not passed to, and for none."""
    if not env or program not in PROGRAMS:
        return {}
    if not isinstance(env, dict) or len(env) > ENV_MAX:
        raise LaunchRefused("Agent Voice did not start it: its environment variables cannot be "
                            "read. Clear them on Agent details, Advanced.")
    for name, value in env.items():
        why = env_refusal(name)
        if why is None and (not isinstance(value, str) or "\x00" in value
                            or len(value) > ENV_VALUE_MAX):
            why = f"{name} has a value that cannot be passed"
        if why is not None:
            raise LaunchRefused(f"Agent Voice did not start it: {why}. Remove it on Agent "
                                f"details, Advanced.")
    return dict(env)


def popen_env(program: str, env) -> dict | None:
    """The environment for Popen: None (inherit as before) with nothing
    extra; else the daemon's own with `env` on top, checked."""
    extra = checked_env(program, env)
    if not extra:
        return None
    return {**os.environ, **extra}


def env_path() -> Path:
    from paths import CONFIG_DIR
    return CONFIG_DIR / "agent-env.json"


_AGENT = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
_CACHE: dict = {}


def _read_raw(strict: bool = True) -> tuple[dict | None, str]:
    """(every agent's variables, "") or (None, why it cannot be read). No
    file is ({}, ""). `strict`: a file other accounts can read is not used
    (a launch); the writer reads it anyway, to put it right."""
    path = env_path()
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    except FileNotFoundError:
        return {}, ""
    except OSError as e:
        return None, ("it is a link, which is never followed" if e.errno == errno.ELOOP
                      else f"it cannot be opened ({e.strerror})")
    with os.fdopen(fd, "rb") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode):
            return None, "it is not a plain file"
        if st.st_uid != os.getuid():
            return None, "it belongs to another account"
        if strict and st.st_mode & 0o077:
            return None, "other accounts can read it (it must be 0600)"
        key = (st.st_ino, st.st_mtime_ns, st.st_size, strict)
        if _CACHE.get("key") == key:
            return _CACHE["value"]
        data = f.read(ENV_FILE_MAX + 1)
    got = _parse(data)
    _CACHE.update(key=key, value=got)
    return got


def _parse(data: bytes) -> tuple[dict | None, str]:
    if len(data) > ENV_FILE_MAX:
        return None, "it is too large"
    try:
        doc = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, "it is not JSON"
    agents = doc.get("agents") if isinstance(doc, dict) else None
    if not isinstance(agents, dict):
        return None, "it has no list of agents"
    out = {}
    for agent, env in agents.items():
        if not isinstance(agent, str) or not _AGENT.fullmatch(agent) or not isinstance(env, dict) \
                or len(env) > ENV_MAX:
            return None, "an entry in it cannot be read"
        for name, value in env.items():
            if not isinstance(name, str) or not ENV_NAME.fullmatch(name) \
                    or not isinstance(value, str) or len(value) > ENV_VALUE_MAX:
                return None, "an entry in it cannot be read"
        out[agent] = dict(env)
    return out, ""


def env_for(agent_id: str) -> tuple[dict, str]:
    """(the variables set for `agent_id` -- "main" for the main agent -- and
    "") or ({}, why the file cannot be used). Read when it changed (its
    stat), so the daemon's idle poll may ask every time."""
    every, problem = _read_raw(strict=True)
    if every is None:
        return {}, problem
    return dict(every.get(agent_id or "main") or {}), ""


def env_names(agent_id: str) -> tuple[list[str], str]:
    """The names set for `agent_id`, sorted, never a value; and the file's
    problem, if it has one."""
    every, problem = _read_raw(strict=False)
    if every is None:
        return [], problem
    names = sorted((every.get(agent_id or "main") or {}).keys())
    if not problem:
        _, problem = _read_raw(strict=True)
    return names, problem


@contextlib.contextmanager
def _locked():
    import fcntl
    from paths import CONFIG_DIR
    _private_dir(CONFIG_DIR)
    lock = CONFIG_DIR / ".agent-env.lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | os.O_CLOEXEC, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _private_dir(d: Path) -> None:
    if d.is_symlink():
        raise ValueError(f"{d} is a link, which is never followed")
    import paths
    paths.private_dir(d)            # 0700 even when it was made with a wider mode


def _write(every: dict) -> None:
    """The whole file, replaced atomically, 0600 from its first byte."""
    path = env_path()
    body = json.dumps({"version": 1, "agents": {a: dict(sorted(e.items()))
                                                for a, e in sorted(every.items()) if e}},
                      indent=1, ensure_ascii=False).encode("utf-8")
    tmp = path.with_name(f".agent-env.{os.getpid()}.tmp")
    with contextlib.suppress(FileNotFoundError):
        tmp.unlink()
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                 | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    _CACHE.clear()


def _agent_ok(agent_id: str) -> str:
    agent = agent_id or "main"
    if not _AGENT.fullmatch(agent) or agent == "communal":
        raise ValueError(f"{agent_id!r} is not an agent id")
    return agent


def _editable() -> dict:
    """Every agent's variables, for a change. A file that cannot be read is
    never overwritten: that would lose every other agent's keys."""
    every, problem = _read_raw(strict=False)
    if every is None:
        raise ValueError(f"{env_path()} cannot be read ({problem}); fix or remove it first")
    # A copy: the parsed file is cached, and a change that fails to write
    # must leave the cache as the file is.
    return {a: dict(e) for a, e in every.items()}


def set_env(agent_id: str, name: str, value: str) -> None:
    """Set one variable for one agent. Refused for a name on the list
    (env_refusal), a value that cannot be passed, or one too many."""
    agent = _agent_ok(agent_id)
    why = env_refusal(name)
    if why is not None:
        raise ValueError(why)
    if not isinstance(value, str) or len(value) > ENV_VALUE_MAX:
        raise ValueError(f"the value is longer than {ENV_VALUE_MAX} characters")
    if _CONTROL.search(value):
        raise ValueError("the value holds a control character (a line break, a tab)")
    with _locked():
        every = _editable()
        mine = dict(every.get(agent) or {})
        if name not in mine and len(mine) >= ENV_MAX:
            raise ValueError(f"an agent has at most {ENV_MAX} environment variables")
        mine[name] = value
        every[agent] = mine
        _write(every)


def unset_env(agent_id: str, name: str) -> bool:
    """Remove one variable; True if it was set."""
    agent = _agent_ok(agent_id)
    with _locked():
        every = _editable()
        mine = dict(every.get(agent) or {})
        if name not in mine:
            return False
        del mine[name]
        every[agent] = mine
        _write(every)
        return True


def clear_env(agent_id: str) -> int:
    """Remove every variable set for one agent; how many there were."""
    agent = _agent_ok(agent_id)
    with _locked():
        every = _editable()
        n = len(every.get(agent) or {})
        if n:
            every.pop(agent, None)
            _write(every)
        return n


# --- the CLI: agentvoice agents flags | env --------------------------------------------

def flags_cli(program: str) -> int:
    """`agentvoice agents flags check PROGRAM` < one line holding a JSON list:
    each flag's verdict as JSON, the same judge() the launch uses. One line,
    so a caller that cannot close stdin (the overlay's Process) still ends it."""
    raw = sys.stdin.readline(64 * 1024)
    try:
        args = json.loads(raw) if raw.strip() else []
    except ValueError:
        print("agentvoice agents: the flags are not a JSON list", file=sys.stderr)
        return 1
    if args_choice(args) is None:
        print("agentvoice agents: the flags are not a list of strings", file=sys.stderr)
        return 1
    offered = program in PROGRAMS
    print(json.dumps({"program": program, "offered": offered,
                      "flags": check(program, args),
                      "refusal": refusal(program, args) if offered and args else None}))
    return 0


def env_cli(agent_id: str, action: str, name: str | None, line: bool, as_json: bool) -> int:
    """`agentvoice agents env ID list|set NAME|unset NAME|clear`. A value
    comes on stdin (with --line, one line holding a JSON string), never as
    an argument; nothing here ever prints one."""
    def fail(msg: str) -> int:
        print(f"agentvoice agents: {msg}", file=sys.stderr)
        return 1
    try:
        _agent_ok(agent_id)
        if action == "list":
            names, problem = env_names(agent_id)
            if as_json:
                print(json.dumps({"names": names, "problem": problem}))
            else:
                print("\n".join(names) or "none set")
                if problem:
                    print(f"! {env_path()}: {problem}", file=sys.stderr)
            return 0
        if action in ("set", "unset") and not name:
            return fail(f"env {action} needs a NAME")
        if action == "set":
            raw = sys.stdin.readline(6 * ENV_VALUE_MAX + 4) if line \
                else sys.stdin.read(ENV_VALUE_MAX + 2)
            if line:
                try:
                    value = json.loads(raw)
                except ValueError:
                    return fail("the value is not one line of JSON")
                if not isinstance(value, str):
                    return fail("the JSON line must hold a string")
            else:
                value = raw[:-1] if raw.endswith("\n") else raw
            set_env(agent_id, name, value)
            print(name)
            return 0
        if action == "unset":
            print(name if unset_env(agent_id, name) else "")
            return 0
        if action == "clear":
            print(clear_env(agent_id))
            return 0
    except ValueError as e:
        return fail(str(e))
    except OSError as e:
        return fail(f"{env_path()} could not be written ({e.strerror})")
    return fail(f"unknown action {action}")
