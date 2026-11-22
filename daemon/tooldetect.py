"""Tools found on this machine (master plan, phase M10).

What this finds, and how:

* **MCP servers**, from the files the CLIs themselves read: the user's
  `~/.claude.json` (`mcpServers`, and `projects[<dir>].mcpServers` for each
  agent's project folder, the "local" scope), each project folder's
  `.mcp.json`, the MCP servers of every enabled Claude Code plugin, and
  Codex's `~/.codex/config.toml` (`[mcp_servers]`).
* **Command-line tools**, from a short curated list of CLIs that reach an
  account or a service (`gh`, `aws`, `docker`, ...) plus any the person added
  by name, each looked up on PATH with `shutil.which`.

It **reads** and never starts anything: no subprocess, no server, no CLI
asked for its version (a test makes `subprocess` fail during a scan). Every
file is read bounded, and only a regular file; the agent-controlled ones (a
project's `.mcp.json`, a plugin's files) are not followed through a link.

**Nothing secret leaves this module.** A server's definition can hold an API
key in `env`, `headers`, its URL or an argument. What a scan returns names
environment variables and headers but never their values, masks anything in
the arguments that looks like a key, and drops a URL's query and password.
The whole definition is handed only to `deliverable()`, whose caller writes
it into a 0600 file for Claude Code (adapters/claude_code.py).

**A fingerprint** of each tool's definitions (an HMAC under a key kept in
`DATA_DIR/tool-key`, 0600, so the value stored in the world-readable
shell.json says nothing about what it covers) is what a switch approves:
`"on:<fingerprint>"`. When a definition changes -- its command, arguments,
environment, a project's copy appearing -- the fingerprint moves and the
tool is off again for everyone who approved the old one, until it is
approved again ("changed since you turned it on").

Which agent has what is runtime.Config's (settings only) joined with this
module's scan in `rows()`; the delivery to each backend is in the adapters.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path

#: CLIs worth a switch: each reaches an account or a service, so whether an
#: agent should use it is a real question. Ordinary tools (git, ls, curl) are
#: not listed: switching those off would only break agents. Label = what it
#: is, for the row.
CURATED_CLIS = {
    "gh": "GitHub CLI",
    "glab": "GitLab CLI",
    "aws": "AWS CLI",
    "gcloud": "Google Cloud CLI",
    "az": "Azure CLI",
    "kubectl": "Kubernetes",
    "docker": "Docker",
    "podman": "Podman",
    "terraform": "Terraform",
    "flyctl": "Fly.io",
    "vercel": "Vercel",
    "netlify": "Netlify",
    "heroku": "Heroku",
    "doctl": "DigitalOcean",
    "hcloud": "Hetzner Cloud",
    "wrangler": "Cloudflare",
    "supabase": "Supabase",
    "firebase": "Firebase",
    "stripe": "Stripe",
    "op": "1Password",
    "bw": "Bitwarden",
    "rclone": "rclone (cloud storage)",
    "tailscale": "Tailscale",
}

#: Bounds. ~/.claude.json carries Claude Code's whole project history and
#: grows; past this it is not read, and its servers are not found (off).
MAX_CLAUDE_JSON = 16 * 1024 * 1024
MAX_FILE = 512 * 1024
MAX_PLUGINS = 64
MAX_SERVERS = 200
MAX_PROJECTS = 16
MAX_EXTRA_CLIS = 32
#: One server's definition, as JSON. A command line longer than this is not
#: a definition anyone typed.
MAX_SPEC = 16 * 1024

#: A tool id: "mcp:<server name>" or "cli:<name>". Claude Code names a
#: plugin's server "plugin:<plugin>:<server>", so ":" is allowed after the
#: prefix.
TOOL_ID = re.compile(r"(?:mcp:[A-Za-z0-9][A-Za-z0-9._:@+-]{0,95}|cli:[a-z0-9][a-z0-9._+-]{0,31})")
CLI_NAME = re.compile(r"[a-z0-9][a-z0-9._+-]{0,31}")
#: A name Codex's `-c mcp_servers.<name>.enabled=false` can carry: a dotted
#: path segment with nothing to quote.
CODEX_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")
#: Server names Agent Voice gives its own servers, which a detected one may
#: not take: the permission hook trusts these prefixes.
RESERVED = {"agentvoice-desktop", "agentvoice-crew", "claude-in-chrome"}

#: How a scope is spoken of, and Claude Code's precedence among them: a
#: local server beats a project's, which beats the user's.
SCOPE_WORDS = {"local": "your Claude Code settings for this folder",
               "project": "the project's .mcp.json",
               "user": "your Claude Code settings",
               "plugin": "a Claude Code plugin",
               "codex": "Codex's config.toml"}
_PRECEDENCE = {"local": 0, "project": 1, "user": 2, "plugin": 3}

_SECRET_WORD = r"(?:key|token|secret|passw(?:or)?d|auth|credential|bearer|cookie|session|signature)"
#: Flags whose value is masked: anything named like a secret, and the ones
#: that carry a header or an environment variable, whatever it is called
#: (`--header "Authorization: Bearer …"`, `-e TOKEN=…`).
_CARRIER = r"(?:header|headers|env|environment|cred|credentials)"
_SECRET_FLAG_EQ = re.compile(r"(?i)^(--?[a-z0-9_.-]*(?:" + _SECRET_WORD + "|" + _CARRIER +
                             r")[a-z0-9_.-]*=)(.+)$")
_SECRET_FLAG = re.compile(r"(?i)^(?:--?[a-z0-9_.-]*(?:" + _SECRET_WORD + "|" + _CARRIER +
                          r")[a-z0-9_.-]*|-H|-e)$")
_SECRET_VALUE = re.compile(r"^(?:gh[pousr]_|github_pat_|sk-|xox[abprs]-|AKIA|glpat-|AIza)\S{8,}")
#: A word that looks generated: long, letters and digits mixed, no path.
_TOKENISH = re.compile(r"^(?=.*[0-9])(?=.*[A-Za-z])[A-Za-z0-9_+=-]{20,}$")


@dataclass
class Roots:
    """Where the CLIs keep their settings. Claude Code moves everything under
    CLAUDE_CONFIG_DIR when it is set, its `.claude.json` included; Codex
    under CODEX_HOME."""
    claude_json: Path
    claude_dir: Path
    codex_home: Path
    home: Path

    def shown(self, path: Path | str) -> str:
        """A path as the row shows it, home folded to ~."""
        text = str(path)
        home = str(self.home).rstrip("/")
        if home and (text == home or text.startswith(home + "/")):
            return "~" + text[len(home):]
        return text


def default_roots() -> Roots:
    """The real ones, read from the environment now (tests replace this)."""
    home = Path(os.environ.get("HOME") or Path.home())
    conf = os.environ.get("CLAUDE_CONFIG_DIR")
    if conf:
        claude_dir = Path(conf)
        claude_json = claude_dir / ".claude.json"
    else:
        claude_dir = home / ".claude"
        claude_json = home / ".claude.json"
    codex = Path(os.environ.get("CODEX_HOME") or home / ".codex")
    return Roots(claude_json=claude_json, claude_dir=claude_dir, codex_home=codex, home=home)


def default_path() -> str:
    """The PATH the CLIs are looked up on (tests replace this)."""
    return os.environ.get("PATH", "")


# --- reading -------------------------------------------------------------------

@dataclass
class _Reader:
    """Every file one scan tried, for the cache stamp, and what went wrong."""
    tried: list = field(default_factory=list)
    read: int = 0
    problems: list = field(default_factory=list)

    def raw(self, path: Path, limit: int, follow: bool,
            beneath: Path | None = None) -> bytes | None:
        """The file's bytes: a regular file at most `limit` bytes, opened
        without following a final link unless `follow`. With `beneath`, the
        path is opened one component at a time from that folder, following
        no link at any level (a project's or a plugin's files: an agent can
        put a link at any depth, not only at the end). None if absent or
        refused (refusals are noted)."""
        self.tried.append(str(path))
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        if not follow:
            flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = _open_beneath(beneath, path, flags) if beneath is not None else os.open(path, flags)
        except FileNotFoundError:
            return None
        except OSError as e:
            if not follow and _has_link(path, beneath):
                self.problems.append(f"{path.name}: a link, not followed")
            else:
                self.problems.append(f"{path.name}: cannot be read ({type(e).__name__})")
            return None
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                self.problems.append(f"{path.name}: not a regular file")
                return None
            if st.st_size > limit:
                self.problems.append(f"{path.name}: larger than {limit // 1024} KB, not read")
                return None
            data = os.read(fd, limit + 1)
            if len(data) > limit:
                self.problems.append(f"{path.name}: larger than {limit // 1024} KB, not read")
                return None
            self.read += 1
            return data
        except OSError as e:
            self.problems.append(f"{path.name}: cannot be read ({type(e).__name__})")
            return None
        finally:
            os.close(fd)

    def json(self, path: Path, limit: int | None = None, follow: bool = False,
             beneath: Path | None = None):
        data = self.raw(path, MAX_FILE if limit is None else limit, follow, beneath)
        if data is None:
            return None
        try:
            return json.loads(data)
        except (ValueError, RecursionError):
            self.problems.append(f"{path.name}: not valid JSON")
            return None

    def toml(self, path: Path, limit: int | None = None, follow: bool = False):
        data = self.raw(path, MAX_FILE if limit is None else limit, follow)
        if data is None:
            return None
        try:
            import tomllib
            return tomllib.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, RecursionError):
            self.problems.append(f"{path.name}: not valid TOML")
            return None


def _open_beneath(root: Path, path: Path, flags: int) -> int:
    """os.open(path) where path is inside `root`, walking from root by
    directory descriptors with O_NOFOLLOW at every step. The root itself
    is followed: it is a folder the person configured (a project) or Claude
    Code recorded (a plugin's install path)."""
    import errno
    rel = Path(path).relative_to(root).parts
    if not rel or any(part in ("", ".", "..") for part in rel):
        raise OSError(errno.EINVAL, "not beneath its root")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    dfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | cloexec)
    try:
        for part in rel[:-1]:
            nfd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | nofollow | cloexec, dir_fd=dfd)
            os.close(dfd)
            dfd = nfd
        return os.open(rel[-1], flags | nofollow, dir_fd=dfd)
    finally:
        os.close(dfd)


def _has_link(path: Path, beneath: Path | None) -> bool:
    """Whether `path`, or any folder between it and `beneath`, is a link."""
    p = Path(path)
    if os.path.islink(p):
        return True
    if beneath is None:
        return False
    for parent in p.parents:
        if parent == Path(beneath) or len(parent.parts) <= len(Path(beneath).parts):
            break
        if os.path.islink(parent):
            return True
    return False


#: A plugin manifest's own name for its MCP config: a file beside it, by a
#: plain name, never a path out of the plugin.
_PLUGIN_REF = re.compile(r"(?:\./)?[A-Za-z0-9][A-Za-z0-9._-]*\.json")


# --- definitions -----------------------------------------------------------------

def _valid_spec(spec) -> bool:
    """A server definition worth listing: a table with a command or a URL of
    the right types, small enough to be one somebody wrote."""
    if not isinstance(spec, dict):
        return False
    try:
        if len(json.dumps(spec)) > MAX_SPEC:
            return False
    except (TypeError, ValueError, RecursionError):
        return False
    command, url = spec.get("command"), spec.get("url")
    if not ((isinstance(command, str) and command.strip()) or (isinstance(url, str) and url.strip())):
        return False
    args = spec.get("args", [])
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return False
    for key in ("env", "headers"):
        table = spec.get(key, {})
        if not isinstance(table, dict) or not all(isinstance(k, str) for k in table):
            return False
    return True


def _servers_in(table, reader: _Reader, where: Path) -> dict:
    """`mcpServers` as written, keeping only valid names and definitions."""
    if not isinstance(table, dict):
        return {}
    out = {}
    for name, spec in table.items():
        if not isinstance(name, str) or not TOOL_ID.fullmatch("mcp:" + name):
            reader.problems.append(f"{where.name}: a server name Agent Voice does not accept")
            continue
        if not _valid_spec(spec):
            reader.problems.append(f"{where.name}: “{name}” has no usable command or URL")
            continue
        out[name] = spec
    return out


def _substitute(value, root: str):
    """${CLAUDE_PLUGIN_ROOT} as Claude Code expands it in a plugin's files."""
    if isinstance(value, str):
        return value.replace("${CLAUDE_PLUGIN_ROOT}", root)
    if isinstance(value, list):
        return [_substitute(v, root) for v in value]
    if isinstance(value, dict):
        return {k: _substitute(v, root) for k, v in value.items()}
    return value


def _plugin_servers(roots: Roots, reader: _Reader) -> list[dict]:
    """The MCP servers of each enabled Claude Code plugin."""
    settings = reader.json(roots.claude_dir / "settings.json", follow=True)
    enabled = (settings or {}).get("enabledPlugins") if isinstance(settings, dict) else None
    if not isinstance(enabled, dict):
        return []
    installed = reader.json(roots.claude_dir / "plugins" / "installed_plugins.json", follow=True)
    plugins = (installed or {}).get("plugins") if isinstance(installed, dict) else None
    if not isinstance(plugins, dict):
        return []
    out = []
    for key in sorted(plugins)[:MAX_PLUGINS]:
        if enabled.get(key) is not True or not isinstance(key, str):
            continue
        entries = plugins[key]
        entries = entries if isinstance(entries, list) else [entries]
        entry = next((e for e in entries if isinstance(e, dict)
                      and isinstance(e.get("installPath"), str)), None)
        if entry is None:
            continue
        root = Path(entry["installPath"])
        plugin = key.split("@", 1)[0]
        table = {}
        mcp = reader.json(root / ".mcp.json", beneath=root)
        if isinstance(mcp, dict):
            table.update(mcp.get("mcpServers") if isinstance(mcp.get("mcpServers"), dict) else mcp)
        manifest = reader.json(root / ".claude-plugin" / "plugin.json", beneath=root)
        inline = (manifest or {}).get("mcpServers") if isinstance(manifest, dict) else None
        if isinstance(inline, dict):
            table.update(inline)
        elif isinstance(inline, str) and _PLUGIN_REF.fullmatch(inline) and ".." not in inline:
            more = reader.json(root / inline.removeprefix("./"), beneath=root)
            if isinstance(more, dict):
                table.update(more.get("mcpServers") if isinstance(more.get("mcpServers"), dict) else more)
        for name, spec in _servers_in(table, reader, root / ".mcp.json").items():
            out.append({"name": f"plugin:{plugin}:{name}", "backend": "claude", "scope": "plugin",
                        "source": roots.shown(root), "project": "",
                        "spec": _substitute(spec, str(root))})
    return out


def definitions(roots: Roots, project_dirs=(), reader: _Reader | None = None) -> list[dict]:
    """Every MCP server definition the CLIs would read: one dict per place it
    is defined, with the full definition under "spec". Never shown as it is:
    see `scan()` for what leaves this module."""
    reader = reader or _Reader()
    out: list[dict] = []
    projects = []
    for d in project_dirs:
        if isinstance(d, str) and d.strip():
            p = os.path.abspath(os.path.expanduser(d.strip()))
            if p not in projects:
                projects.append(p)
    projects = projects[:MAX_PROJECTS]

    claude = reader.json(roots.claude_json, limit=MAX_CLAUDE_JSON, follow=True)
    if isinstance(claude, dict):
        for name, spec in _servers_in(claude.get("mcpServers"), reader, roots.claude_json).items():
            out.append({"name": name, "backend": "claude", "scope": "user",
                        "source": roots.shown(roots.claude_json), "project": "", "spec": spec})
        per = claude.get("projects")
        if isinstance(per, dict):
            for proj in projects:
                entry = per.get(proj)
                if not isinstance(entry, dict):
                    continue
                for name, spec in _servers_in(entry.get("mcpServers"), reader,
                                              roots.claude_json).items():
                    out.append({"name": name, "backend": "claude", "scope": "local",
                                "source": roots.shown(roots.claude_json),
                                "project": roots.shown(proj), "spec": spec})
    for proj in projects:
        path = Path(proj) / ".mcp.json"
        mcp = reader.json(path, beneath=Path(proj))
        if isinstance(mcp, dict):
            for name, spec in _servers_in(mcp.get("mcpServers"), reader, path).items():
                out.append({"name": name, "backend": "claude", "scope": "project",
                            "source": roots.shown(path), "project": roots.shown(proj), "spec": spec})
    out += _plugin_servers(roots, reader)

    codex_cfg = roots.codex_home / "config.toml"
    codex = reader.toml(codex_cfg, follow=True)
    if isinstance(codex, dict):
        for name, spec in _servers_in(codex.get("mcp_servers"), reader, codex_cfg).items():
            out.append({"name": name, "backend": "codex", "scope": "codex",
                        "source": roots.shown(codex_cfg), "project": "", "spec": spec})
    return out[:MAX_SERVERS]


# --- fingerprints ----------------------------------------------------------------

def _key_path() -> Path:
    from paths import DATA_DIR
    return DATA_DIR / "tool-key"


def tool_key() -> bytes | None:
    """The HMAC key fingerprints are made with: 32 random bytes, made once,
    0600. None when it cannot be read or made, which leaves every detected
    tool off (nothing can match an empty fingerprint)."""
    path = _key_path()
    for _ in range(2):
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            try:
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                             0o600)
            except FileExistsError:
                continue                # made by someone else meanwhile: read it
            except OSError:
                return None
            try:
                os.write(fd, secrets.token_bytes(32))
            finally:
                os.close(fd)
            continue
        except OSError:
            return None
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077 or st.st_uid != os.getuid():
                return None
            data = os.read(fd, 64)
        except OSError:
            return None
        finally:
            os.close(fd)
        return data if len(data) == 32 else None
    return None


def fingerprint(parts, key: bytes | None) -> str:
    """32 hex digits over `parts` (any JSON value), "" without a key."""
    if not key:
        return ""
    body = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


# --- showing a definition --------------------------------------------------------

def _mask_args(args: list[str]) -> list[str]:
    """Arguments as the confirm shows them. A display, so it leans wide: a
    value after a secret-named, header or environment flag, a flag=value of
    one, any argument with a secret's name in it, anything shaped like a
    generated key, and a URL's query and password. A package that merely
    has "key" in its name is masked too; that costs a word, a miss costs a
    key on screen."""
    out, hide_next = [], False
    for a in args:
        if hide_next:
            out.append("•••")
            hide_next = False
            continue
        m = _SECRET_FLAG_EQ.match(a)
        if m:
            out.append(m.group(1) + "•••")
            continue
        if _SECRET_FLAG.match(a):
            hide_next = True
            out.append(a)
            continue
        if "://" in a:
            out.append(_shown_url(a))
            continue
        if _SECRET_VALUE.match(a) or _TOKENISH.match(a):
            out.append("•••")               # a key on its own: none of it shown
            continue
        if re.search(_SECRET_WORD, a, re.I):
            eq = a.find("=")
            out.append(a[:eq + 1] + "•••" if 0 < eq < 40 and re.fullmatch(r"[A-Za-z0-9_.-]+", a[:eq]) else "•••")
            continue
        out.append(a)
    return out


def _shown_url(url: str) -> str:
    """A URL without its query, fragment or password."""
    from urllib.parse import urlsplit
    try:
        u = urlsplit(url.strip())
    except ValueError:
        return "(a URL that cannot be read)"
    host = u.hostname or ""
    if u.port:
        host += f":{u.port}"
    tail = "?•••" if u.query else ""
    return f"{u.scheme}://{host}{u.path}{tail}" if u.scheme else "(a URL that cannot be read)"


def shown_command(spec: dict) -> str:
    """What the confirm shows as "the command it will run": the command and
    its arguments with anything key-like masked, or the URL it connects to,
    and the names (never values) of the environment variables it is given."""
    import shlex
    if isinstance(spec.get("command"), str) and spec["command"].strip():
        words = [spec["command"]] + _mask_args(list(spec.get("args") or []))
        text = " ".join(w if "•••" in w else shlex.quote(w) for w in words)
    else:
        text = "connects to " + _shown_url(str(spec.get("url") or ""))
    env = spec.get("env") or {}
    if isinstance(env, dict) and env:
        names = sorted(k for k in env if isinstance(k, str))[:12]
        text += " · environment: " + ", ".join(names) + (" …" if len(env) > 12 else "")
    headers = spec.get("headers") or {}
    if isinstance(headers, dict) and headers:
        text += " · headers: " + ", ".join(sorted(k for k in headers if isinstance(k, str))[:8])
    if len(text) > 600:
        text = text[:600] + "…"
    return text




# --- the scan --------------------------------------------------------------------

def _which(name: str, path: str) -> str:
    """Where `name` is found on PATH, as PATH has it: not resolved through
    links, so a version manager's shim or wrapper (mise, asdf) keeps one
    place across upgrades, while a different `gh` earlier on PATH -- the
    change worth a second look -- moves it."""
    found = shutil.which(name, path=path) if path else None
    return os.path.abspath(found) if found else ""


def _order(d: dict) -> tuple:
    return (d["backend"], _PRECEDENCE.get(d["scope"], 9), d["project"], d["source"])


def _fp_of(defs: list[dict], key: bytes | None) -> str:
    """One fingerprint over every definition of one tool, wherever it is."""
    return fingerprint([[d["backend"], d["scope"], d["source"], d["project"], d["spec"]]
                        for d in sorted(defs, key=_order)], key)


#: Every program that runs commands on this machine, and so can use a CLI.
CLI_PROGRAMS = ("claude", "codex", "gemini", "agy", "copilot")


def _scan(roots: Roots, project_dirs, extra_clis, path: str, key: bytes | None):
    """scan(), plus every file it tried (for the cache stamp) and the
    definitions whole (kept in this process only, for delivery)."""
    start = time.monotonic()
    reader = _Reader()
    defs = definitions(roots, project_dirs, reader)
    by_id: dict[str, list] = {}
    for d in defs:
        by_id.setdefault("mcp:" + d["name"], []).append(d)
    tools = []
    for tid in sorted(by_id):
        ds = sorted(by_id[tid], key=_order)
        tools.append({
            "id": tid, "kind": "mcp", "name": tid[4:], "label": tid[4:],
            "backends": sorted({d["backend"] for d in ds}),
            "defs": [{"backend": d["backend"], "scope": d["scope"],
                      "where": SCOPE_WORDS.get(d["scope"], d["scope"]),
                      "source": d["source"], "project": d["project"],
                      "command": shown_command(d["spec"])} for d in ds],
            "fp": _fp_of(ds, key),
            "found": True, "added": False,
        })
    names = []
    for n in list(CURATED_CLIS) + sorted({n for n in extra_clis if isinstance(n, str)}):
        if CLI_NAME.fullmatch(n) and n not in names:
            names.append(n)
    names = names[:len(CURATED_CLIS) + MAX_EXTRA_CLIS]
    for n in names:
        where = _which(n, path)
        curated = n in CURATED_CLIS
        if curated and not where:
            continue                    # not installed: nothing to switch
        tools.append({
            "id": "cli:" + n, "kind": "cli", "name": n,
            "label": CURATED_CLIS.get(n, n),
            "backends": list(CLI_PROGRAMS) if where else [],
            "defs": [{"backend": "", "scope": "path",
                      "where": "on PATH" if where else "not found on PATH",
                      "source": roots.shown(where) if where else "", "project": "",
                      "command": n}],
            "fp": fingerprint(["cli", n, where], key) if where else "",
            "found": bool(where), "added": not curated,
        })
    result = {"tools": tools, "problems": sorted(set(reader.problems))[:20],
              "files_read": reader.read, "files_tried": len(reader.tried),
              "ms": round((time.monotonic() - start) * 1000, 1), "keyed": bool(key)}
    return result, reader.tried, defs


def scan(roots: Roots | None = None, project_dirs=(), extra_clis=(), path: str | None = None,
         key: bytes | None = None) -> dict:
    """What is on this machine, as the pages and `agentvoice tools scan`
    show it. Nothing secret: see the module docstring.

    {"tools": [{"id", "kind", "name", "label", "backends", "defs": [{"backend",
    "scope", "where", "source", "project", "command"}], "fp", "found",
    "added"}], "problems": [...], "files_read", "files_tried", "ms", "keyed"}
    """
    roots = roots or default_roots()
    path = default_path() if path is None else path
    key = tool_key() if key is None else key
    return _scan(roots, project_dirs, extra_clis, path, key)[0]


def server_key(name: str) -> str:
    """The name a detected server gets in the config Agent Voice writes for
    Claude Code, and so in its tools' names (`mcp__<key>__<tool>`): the
    server's own name with anything but letters, digits, - and _ made _,
    never two _ in a row and none at either end -- so the first "__" after
    "mcp__" in a tool's name always ends the key, and the permission hook
    reads the key exactly rather than by prefix (Codex review of M10: with
    prefixes, approving "docs" let "docs__admin" through)."""
    key = re.sub(r"_{2,}", "_", re.sub(r"[^A-Za-z0-9_-]", "_", name)).strip("_")[:64].rstrip("_")
    return key or "server"


def tool_server_key(tool_name: str) -> str:
    """The server key in a Claude Code tool name `mcp__<key>__<tool>`, ""
    when it is not one. Exact: keys never hold "__" (server_key)."""
    if not tool_name.startswith("mcp__"):
        return ""
    return tool_name[5:].split("__", 1)[0]


def spec_digest(spec) -> str:
    """A plain digest of one definition as written, for a backend that reads
    the user's own file at its turn (Codex): the daemon hands it the digest
    of what was approved, and the adapter compares it with the file then, so
    a definition changed since the scan is not started (Codex review)."""
    body = json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# --- the cache -------------------------------------------------------------------

def _stamp_of(tried: list[str], path: str) -> list:
    out = []
    for p in tried:
        try:
            st = os.stat(p)
            out.append([p, st.st_mtime_ns, st.st_size, st.st_ino])
        except OSError:
            out.append([p, None])
    for d in path.split(os.pathsep)[:64]:
        if d:
            try:
                out.append([d, os.stat(d).st_mtime_ns])
            except OSError:
                out.append([d, None])
    return out


#: The last scan in this process, with the definitions whole (never written).
_MEMO: dict = {}


def cache_path() -> Path:
    from paths import RUNTIME_DIR
    return RUNTIME_DIR / "tools" / "scan.json"


def settings_inputs(cfg) -> tuple[list[str], list[str]]:
    """What a scan depends on in the settings: the project folders, and the
    CLI names somebody added by name (a `cli:` key in any tools map)."""
    dirs: list[str] = []
    names: set[str] = set()
    try:
        main_dir = cfg.get_str("projectDir")
        if main_dir:
            dirs.append(main_dir)
        agents = cfg.all_agents()
        for a in agents:
            if a.get("projectDir"):
                dirs.append(a["projectDir"])
        from runtime import detected_choices
        for m in [cfg["sharedTools"], cfg["mainTools"]] + [a.get("detected") for a in agents]:
            for k in detected_choices(m) or {}:
                if k.startswith("cli:"):
                    names.add(k[4:])
    except Exception:
        pass
    return dirs, sorted(names)[:MAX_EXTRA_CLIS]


def scan_cached(cfg, force: bool = False, with_defs: bool = False):
    """`scan()` for the settings in `cfg`, reused while no file it read, no
    PATH folder and no setting it depends on has moved: the idle poll and
    the pages pay a handful of stat calls, not a parse. Kept in this process
    and in `$RUNDIR/tools/scan.json` (0600; nothing secret in it).

    `with_defs` returns (result, definitions) with the definitions whole,
    read fresh unless this process already holds them for the same stamp;
    they are never written anywhere by this module."""
    dirs, extra = settings_inputs(cfg)
    roots = default_roots()
    path = default_path()
    inputs = [str(roots.claude_json), str(roots.claude_dir), str(roots.codex_home), dirs, extra, path]
    key = tool_key()
    if not force:
        memo = _MEMO.get("last")
        if memo and memo["inputs"] == inputs and memo["stamp"] == _stamp_of(memo["tried"], path) \
                and memo["result"].get("keyed") == bool(key):
            return (memo["result"], memo["defs"]) if with_defs else memo["result"]
        if not with_defs:
            disk = _read_cache()
            if disk and disk.get("inputs") == inputs and isinstance(disk.get("tried"), list) \
                    and disk.get("stamp") == _stamp_of(disk["tried"], path) \
                    and isinstance(disk.get("result"), dict) \
                    and disk["result"].get("keyed") == bool(key):
                return disk["result"]
    result, tried, defs = _scan(roots, dirs, extra, path, key)
    stamp = _stamp_of(tried, path)
    _MEMO["last"] = {"inputs": inputs, "tried": tried, "stamp": stamp, "result": result,
                     "defs": defs}
    _write_cache({"inputs": inputs, "tried": tried, "stamp": stamp, "result": result})
    return (result, defs) if with_defs else result


def _read_cache() -> dict | None:
    try:
        fd = os.open(cache_path(), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_size > 4 * 1024 * 1024:
            return None
        memo = json.loads(os.read(fd, st.st_size + 1))
        return memo if isinstance(memo, dict) else None
    except (OSError, ValueError, RecursionError):
        return None
    finally:
        os.close(fd)


def _write_cache(memo: dict) -> None:
    path = cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = path.with_name(f".scan.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(memo, f)
        os.replace(tmp, path)
    except OSError:
        pass


# --- live status -------------------------------------------------------------------

def live_path() -> Path:
    from paths import RUNTIME_DIR
    return RUNTIME_DIR / "tools" / "live.json"


def write_live(live: dict) -> None:
    """{agent id: {"servers": [{"name", "status"}], "at": epoch}}: what each
    agent's Claude Code said it started, from its last init event. Written
    by the daemon; read by the pages (and M16)."""
    path = live_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = path.with_name(f".live.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(live, f)
        os.replace(tmp, path)
    except OSError:
        pass


def read_live() -> dict:
    try:
        fd = os.open(live_path(), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return {}
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > 256 * 1024:
            return {}
        data = json.loads(os.read(fd, st.st_size + 1))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, RecursionError):
        return {}
    finally:
        os.close(fd)


def live_servers(init_servers) -> list[dict]:
    """The `mcp_servers` of a Claude Code init event, as kept: name and
    status only, bounded."""
    out = []
    if isinstance(init_servers, list):
        for s in init_servers[:64]:
            if isinstance(s, dict) and isinstance(s.get("name"), str):
                out.append({"name": s["name"][:96], "status": str(s.get("status") or "")[:24]})
    return out


# --- an agent's view ---------------------------------------------------------------

def _asks(kind: str, program: str, level: str) -> str:
    """Whether using the tool asks first, at this agent's level, as the
    recordings in tests/fixtures/tools/ show it."""
    if level == "trusted":
        return "⚠ Runs without asking at Trusted."
    if kind == "mcp":
        if program == "claude":
            return "Asks before each call."
        if program == "codex":
            return "Codex refuses its calls below Trusted: it has no way to ask."
        return ""
    if program == "claude":
        return "Asks before each command."
    if program == "codex":
        return "Runs read-only below Trusted: a command that changes something is refused."
    return f"Held in {_backend_label(program)}'s safest mode, which cannot ask."


def _backend_label(backend: str) -> str:
    return {"claude": "Claude Code", "codex": "Codex", "gemini": "Gemini", "agy": "Antigravity",
            "copilot": "Copilot", "endpoint": "an endpoint"}.get(backend, backend or "no program")


def _usable(tool: dict, program: str, project: str, roots: Roots | None = None) -> tuple[bool, str]:
    """Whether `program` can use `tool` at all, and why not."""
    if program == "endpoint":
        return False, "An endpoint runs nothing on this machine."
    if not program:
        return False, "No program is chosen for it."
    if tool["kind"] == "cli":
        if not tool["found"]:
            return False, f"{tool['name']} is not on PATH."
        return True, ""
    if program not in ("claude", "codex"):
        return False, f"{_backend_label(program)} is not given MCP servers by Agent Voice."
    mine = [d for d in tool["defs"] if d["backend"] == program]
    if not mine:
        other = _backend_label(tool["backends"][0]) if tool["backends"] else "another program"
        return False, f"It is in {other}'s settings, not {_backend_label(program)}'s."
    if program == "claude":
        shown = ""
        if project:
            r = roots or default_roots()
            shown = r.shown(os.path.abspath(os.path.expanduser(project)))
        if not any(d["scope"] in ("user", "plugin") or (shown and d["project"] == shown)
                   for d in mine):
            return False, "It belongs to another project folder than this agent's."
        if server_key(tool["name"]) in RESERVED:
            return False, "Its name is one Agent Voice uses for its own tools."
    return True, ""


def rows(cfg, agent_id: str, program: str, level: str, project: str, scanned: dict,
         live: dict | None = None) -> list[dict]:
    """Each detected tool as one agent has it (the Tools & skills tab):
    its own switch (inherit / on / off), the switch for every agent, whether
    the fingerprint it was approved under still holds, whether its program
    can use it and why not, whether it asks first, and, for a Claude agent,
    whether its last process said the server was running."""
    own, shared = cfg.tool_switches(agent_id)
    keys: dict[str, int] = {}
    for t in scanned.get("tools") or []:
        if t["kind"] == "mcp":
            keys[server_key(t["name"])] = keys.get(server_key(t["name"]), 0) + 1
    mine_live = {}
    for s in ((live or {}).get(agent_id or "main") or {}).get("servers") or []:
        mine_live[s.get("name")] = s.get("status")
    out = []
    for t in scanned.get("tools") or []:
        tid = t["id"]
        o, sh = own.get(tid), shared.get(tid)
        approval = o if o is not None else (sh or "off")
        fp = t.get("fp") or ""
        approved = bool(fp) and approval == "on:" + fp
        changed = approval.startswith("on:") and not approved
        can, why = _usable(t, program, project)
        if can and t["kind"] == "mcp" and program == "claude" and keys.get(server_key(t["name"]), 0) > 1:
            can, why = False, (f"Another server's name comes out the same once made safe for "
                               f"Claude Code ({server_key(t['name'])}); rename one of them.")
        note = ""
        if can and t["kind"] == "mcp" and program == "codex" and not CODEX_NAME.fullmatch(t["name"]):
            note = ("Its name cannot be switched off for Codex, so while it is off Codex does not "
                    "start for this agent. Turn it on, or rename it in Codex's config.toml.")
        status = ""
        if t["kind"] == "mcp" and program == "claude":
            status = mine_live.get(server_key(t["name"])) or ""
        out.append({
            "id": tid, "kind": t["kind"], "name": t["name"], "label": t["label"],
            "choice": "inherit" if o is None else ("off" if o == "off" else "on"),
            "shared": "on" if (sh or "").startswith("on:") else "off",
            "shared_set": sh is not None,
            "shared_changed": bool(sh and sh.startswith("on:") and sh != "on:" + fp),
            "on": approved and can, "approved": approved, "changed": changed,
            "can": can, "why_not": why,
            "asks": _asks(t["kind"], program, level) if can else "",
            "enforced": t["kind"] == "mcp",
            "live": status, "fp": fp, "defs": t["defs"], "found": t["found"], "note": note,
            "added": t.get("added", False),
        })
    return out


def delivery(cfg, agent_id: str, program: str, project: str, scanned: dict, defs: list[dict]) -> dict:
    """What this agent's program is handed, from its approved tools:

    * "servers": {key: definition} for Claude Code, the definition Claude
      itself would pick for this project, only for a tool whose fingerprint
      matches the one approved now;
    * "codex_off": names in Codex's config.toml to start with enabled=false
      (every one not approved);
    * "clis_on" / "clis_off": the CLIs it is told it may use, and the
      detected ones it is told are switched off.
    Settings that cannot be read approve nothing."""
    out = {"servers": {}, "codex_off": [], "codex_on": {}, "clis_on": [], "clis_off": []}
    the_rows = rows(cfg, agent_id, program, "", project, scanned)
    approved = {r["id"] for r in the_rows if r["on"]}
    for r in the_rows:
        if r["kind"] == "cli" and r["can"]:
            (out["clis_on"] if r["id"] in approved else out["clis_off"]).append(r["name"])
    if program == "claude":
        roots = default_roots()
        shown = roots.shown(os.path.abspath(os.path.expanduser(project))) if project else ""
        for tid in sorted(approved):
            if not tid.startswith("mcp:"):
                continue
            name = tid[4:]
            mine = sorted((d for d in defs if d["name"] == name and d["backend"] == "claude"
                           and (d["scope"] in ("user", "plugin") or (shown and d["project"] == shown))),
                          key=lambda d: _PRECEDENCE.get(d["scope"], 9))
            key = server_key(name)
            if mine and key not in RESERVED and key not in out["servers"]:
                out["servers"][key] = mine[0]["spec"]
    elif program == "codex":
        names = sorted({d["name"] for d in defs if d["backend"] == "codex"})
        out["codex_off"] = [n for n in names if CODEX_NAME.fullmatch(n) and "mcp:" + n not in approved]
        # What each approved one was, so the adapter can tell at the turn
        # whether the file still says the same.
        out["codex_on"] = {d["name"]: spec_digest(d["spec"]) for d in defs
                           if d["backend"] == "codex" and "mcp:" + d["name"] in approved}
    return out


def switched_on_keys(cfg, agent_id: str) -> set[str]:
    """The server keys this agent's settings switch on now, fingerprints not
    checked: for the permission hook, which judges a call made by a process
    started with only approved definitions, so it needs only to know whether
    the switch is still on. Unreadable settings switch nothing on."""
    own, shared = cfg.tool_switches(agent_id)
    on: set[str] = set()
    off: set[str] = set()
    for tid in set(own) | set(shared):
        if not tid.startswith("mcp:"):
            continue
        value = own.get(tid, shared.get(tid))
        key = server_key(tid[4:])
        (on if isinstance(value, str) and value.startswith("on:") else off).add(key)
    # Two ids can come out as one key ("docs.api", "docs_api"): a key is on
    # only when no switch naming it says off (Codex review of M10, pass 2),
    # so a stale approval of one cannot vouch for the other one running.
    return on - off


# --- the one-time notice -------------------------------------------------------------

def _notice_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "agentvoice" / "tools-notice.json"


def _dismissed() -> dict:
    try:
        fd = os.open(_notice_path(), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return {}
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > 256 * 1024:
            return {}
        data = json.loads(os.read(fd, st.st_size + 1))
        d = data.get("dismissed") if isinstance(data, dict) else None
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError, RecursionError):
        return {}
    finally:
        os.close(fd)


def notice(agent_id: str, the_rows: list[dict]) -> list[dict]:
    """Since phase M10 an agent is started with only the tools switched on
    for it, where before Claude Code also loaded every server in the user's
    own settings (and Codex every server in its config.toml, and a shell
    every CLI on PATH). This is the list the Tools & skills tab shows once,
    each with "Turn on": tools this agent could use, that nobody has switched
    either way -- not for it, not for every agent -- and that the person has
    not dismissed. Nothing here writes shell.json."""
    gone = set(_dismissed().get(agent_id or "main") or [])
    return [{"id": r["id"], "name": r["name"], "kind": r["kind"], "label": r["label"]}
            for r in the_rows
            if r["can"] and not r["on"] and r["choice"] == "inherit" and not r.get("shared_set")
            and r["id"] not in gone]


def dismiss(agent_id: str, ids) -> None:
    """Hide the notice's current entries for this agent (a state file, not
    a setting)."""
    path = _notice_path()
    data = _dismissed()
    key = agent_id or "main"
    have = [i for i in (data.get(key) or []) if isinstance(i, str)]
    for i in ids:
        if isinstance(i, str) and TOOL_ID.fullmatch(i) and i not in have:
            have.append(i)
    data[key] = have[:512]
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f".tools-notice.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"version": 1, "dismissed": data}, f)
    os.replace(tmp, path)


# --- the command line ----------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """agentvoice tools scan [--json] [--rescan]
       agentvoice tools dismiss AGENT     hide AGENT's "now off" notice

    Reads files and settings; never starts a tool, never prints a secret."""
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    usage = "usage: agentvoice tools scan [--json] [--rescan] | dismiss AGENT"
    if not args:
        print(usage, file=sys.stderr)
        return 2
    from runtime import Config
    cfg = Config()
    if args[0] == "scan" and set(args[1:]) <= {"--json", "--rescan"}:
        result = scan_cached(cfg, force="--rescan" in args)
        if "--json" in args:
            json.dump(result, sys.stdout)
            sys.stdout.write("\n")
            return 0
        from speech_text import safe_for_terminal
        for t in result["tools"]:
            where = "; ".join(f"{d['where']}{' (' + d['source'] + ')' if d['source'] else ''}"
                              for d in t["defs"])
            print(safe_for_terminal(f"{t['kind']:4} {t['name']:24} {where}"))
        if not result["tools"]:
            print("nothing found")
        for p in result["problems"]:
            print(safe_for_terminal(f"note: {p}"))
        print(f"{result['files_read']} files read in {result['ms']} ms")
        return 0
    if args[0] == "dismiss" and len(args) == 2 and re.fullmatch(r"main|[a-z0-9][a-z0-9-]{0,47}", args[1]):
        import agentfs
        cat = agentfs.catalog(args[1], cfg)
        dismiss(args[1] if args[1] != "main" else "", [n["id"] for n in cat.get("notice") or []])
        return 0
    print(usage, file=sys.stderr)
    return 2


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
