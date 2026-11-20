#!/usr/bin/env python3
"""Ask the desktop before the agent runs anything.

Claude Code runs this as a PreToolUse hook: it receives the pending tool call
as JSON on stdin and answers with a permission decision. That is the supported
mechanism, and it is the one that works -- `--permission-prompt-tool` is
accepted by the CLI, loads the MCP server, and is then never consulted, at
least in 2.1.278.

The hook is spawned by Claude, not by the daemon, so the two talk through
files in the runtime directory: this writes <id>.request and waits for
<id>.response. Nothing polls that directory -- this process summons the
overlay itself and names the id, and the overlay reads the request file.

Silence means no. A request nobody answers is denied when the timeout expires,
because the alternative -- a spoken sentence quietly editing files while
nobody is at the screen -- is the thing this exists to prevent.
"""
from __future__ import annotations

import json
import re
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import AGENTS_DIR, COMMUNAL_DIR, CONFIG_DIR, DATA_DIR, RUNTIME_DIR, scope_root  # noqa: E402

PENDING = RUNTIME_DIR / "permissions"

#: "Allow everything in this chat": one file per conversation that the user
#: allowed wholesale from the prompt. Keyed by Claude Code's session id, which
#: --resume keeps (checked against the real CLI), so it holds across the turns
#: of one conversation and ends with it -- a new conversation is a new id.
#: The daemon empties this directory when it starts.
GRANTS = RUNTIME_DIR / "grants"

#: Claude Code's session ids are UUIDs. Anything else is not one, and gets
#: no grant either way.
_SESSION = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _timeout() -> float:
    """How long to wait for an answer. Garbage reads as the default.

    At import time, because the environment is read once -- but guarded,
    because an unparseable value raising here would abort the hook, and a
    hook that exits non-zero is a *non-blocking* error in Claude Code: the
    tool proceeds. Every failure in this file has to end in a denial.
    """
    try:
        value = float(os.environ.get("AGENTVOICE_PERMISSION_TIMEOUT", "45"))
    except (TypeError, ValueError):
        return 45.0
    return value if value >= 0 else 45.0


TIMEOUT = _timeout()

#: Tools with no effect outside the conversation. Asking about these would
#: train you to say yes, which is the failure mode a prompt has.
#: ToolSearch only loads the schema of a tool Claude Code deferred -- every
#: MCP tool is deferred -- and the tool it loads is still judged here when it
#: is called. Asking about it put a card on screen before every desktop tool
#: (seen in the first real turn through desktop_mcp.py).
NO_EFFECT = {"TodoWrite", "BashOutput", "ExitPlanMode", "ToolSearch"}

#: One of the agent's own skills, as Claude Code names it when the Skill tool
#: loads it from the plugin folder Agent Voice made for this agent (Phase 13).
#: That folder holds only the skills this agent is meant to have, so loading
#: one reads instructions into the conversation, like a Read of its own
#: folder; whatever the skill then has it do is judged call by call. A skill
#: from any other plugin is asked about as before.
OWN_SKILL = re.compile(r"agentvoice:[a-z0-9][a-z0-9-]{0,47}|agentvoice-omarchy:omarchy")

#: Tools that only read. Allowed, but against SECRETS below rather than
#: unconditionally: the attack is not "the agent read a file", it is "a
#: sentence from a podcast told it to read ~/.ssh/id_ed25519 and put it
#: somewhere". A read it cannot act on is still a read it can quote.
READ_ONLY = {"Read", "NotebookRead", "Glob", "Grep"}

#: Agent Voice's own desktop tools (desktop_mcp.py, plan 12a), by the name
#: Claude Code gives them. Kept in step with desktop_mcp's sets by a test.
#: Matched on the whole prefix, so a server of the user's own is never
#: mistaken for this one by a tool name alone.
DESKTOP_PREFIX = "mcp__agentvoice-desktop__"
#: Window lists and workspaces: reads with no effect, allowed at every level.
DESKTOP_READ_ONLY = {"list_windows", "active_window", "list_workspaces"}
#: The clipboard often holds a password: asked below "trusted".
DESKTOP_SENSITIVE_READ = {"clipboard_read"}
#: Asked by the server itself every time, at every level and whatever a chat
#: grant says -- so the hook passing it is not a silent yes, and a trusted
#: agent, which has no hook at all, is still asked.
DESKTOP_SELF_ASKED = {"screenshot"}

#: Agent Voice's notes tools (crew_mcp.py, merged plan Phase 14), by the
#: name Claude Code gives them. Kept in step with crew_mcp's sets by a test.
CREW_PREFIX = "mcp__agentvoice-crew__"
#: Listing and reading notes: allowed at every level, like Read.
CREW_READ_ONLY = {"notes_list", "notes_read"}
#: Writing a note: asked at "ask", silent at "edits" and "trusted". Without
#: this rule "edits" would ask too (only the four file-edit tools are silent
#: there). Deny and a locked note are the notes store's to refuse, at every
#: level; a denied agent is refused here too, so nobody is asked about a
#: write that cannot happen.
CREW_WRITES = {"notes_write", "notes_append"}

#: Claude in Chrome (plan 12d). Its tools act in the person's real browser,
#: signed in as them, so a click can send, buy or post. Those are asked
#: about at every level -- Trusted and "allow all in this chat" included --
#: out loud and on screen. The rest of the browser follows the level.
BROWSER_PREFIX = "mcp__claude-in-chrome__"
#: The hook's matcher for an agent that is otherwise trusted: only the
#: browser, so nothing else pays for a process per tool call.
BROWSER_MATCHER = "mcp__claude-in-chrome__.*"
#: `computer` actions that do something on the page, as opposed to looking.
BROWSER_ACTING = {"left_click", "right_click", "double_click", "triple_click",
                  "type", "key", "left_click_drag"}
#: Words in an action's own summary that mean it has consequences beyond the
#: page. Claude in Chrome asks the model to state the effect of every click,
#: key and form fill in `action_summary` ("Sends the drafted reply to pat").
#: A false match costs a question; a miss costs a purchase, so the list leans
#: wide.
BROWSER_CONSEQUENCE = re.compile(
    r"\b(submit|send|post|publish|buy|purchas|order|pay|checkout|check out|"
    r"place|confirm|delet|remov|transfer|book|reserv|subscrib|sign up|"
    r"signup|register|tweet|repl(y|ies|ied)|comment|share|upload|donat|"
    r"accept|agree|approv|merg|deploy|apply|invit|cancel|withdraw|"
    r"sell|bid|checkin|check in|log ?out|sign ?out|save|archive|forward)\w*",
    re.I)


def browser_consequence(tool_name: str, tool_input: dict) -> str:
    """Why a browser action needs asking whatever the level, or "".

    Reading is never this: tabs, page text, find, screenshots, scrolling,
    hovering, navigating. Running code in the page and uploading a file
    always are. A click, key, typed text or form fill is when its summary
    says it sends, buys, posts or the like -- or when it gives no summary,
    because an action that will not say what it does is not one to wave
    through.
    """
    name = tool_name[len(BROWSER_PREFIX):] if tool_name.startswith(BROWSER_PREFIX) else ""
    if not name:
        return ""
    if name == "javascript_tool":
        return "it runs code in the page, which can do anything the page can"
    if name == "file_upload":
        return "it uploads a file from this machine to the page"
    if name == "browser_batch":
        for item in tool_input.get("actions") or []:
            if not isinstance(item, dict):
                return "a batch with an item that cannot be read"
            inner = item.get("input")
            why = browser_consequence(BROWSER_PREFIX + str(item.get("name") or ""),
                                      inner if isinstance(inner, dict) else {})
            if why:
                return why
        return ""
    acting = name == "form_input" or (
        name == "computer" and tool_input.get("action") in BROWSER_ACTING)
    if not acting:
        return ""
    summary = " ".join(str(tool_input.get("action_summary") or "").split())[:200]
    if not summary:
        return "it does not say what this click or key will do"
    if BROWSER_CONSEQUENCE.search(summary):
        return f"this may send, buy or post: {summary}"
    return ""


#: Everything else is asked about, including every `mcp__*` tool the user has
#: configured, WebSearch, WebFetch, Task and Skill. That is the point of the
#: `.*` matcher in adapters/claude_code.py: before it, those never reached
#: this process and ran under `--permission-mode auto` while the settings
#: screen said "asks before every change".

#: Paths whose contents are a credential, a key, or a history of what you
#: have typed. A read of one of these is asked about at every level below
#: "trusted", wherever it sits.
#:
#: A denylist, which is the weaker shape, and deliberately so: writes are
#: allowlisted to one project directory because an agent that cannot write
#: is useless, while a *read* of an ordinary file outside the project is
#: something an agent legitimately does all day -- a man page, a sibling
#: repository, a config it is being asked about. Prompting on all of those
#: would train the habit this file exists to avoid. So reads are open except
#: where the file is secret by nature. It will not be a complete list; it is
#: the list of things worth a question.
SECRETS = (
    "/.ssh/", "/.gnupg/", "/.aws/", "/.kube/", "/.netrc", "/.pgpass",
    "/.git-credentials", "/.docker/config.json", "/.config/gh/",
    "/.local/share/keyrings/", "/.password-store/", "/.mozilla/",
    "/.claude/.credentials.json", "/.codex/auth.json", "/.gemini/",
    "/.config/agentvoice/", "/.bash_history", "/.zsh_history",
    "/.python_history", "/.sh_history", "/shadow",
)

#: Same, by name rather than by location.
SECRET_NAMES = ("endpoint.key", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
                "credentials", "credentials.json", ".env")
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".kdbx")

#: Tools whose damage is confined to one named file, so a path rule can
#: describe them honestly. Bash is deliberately absent: "cd /; rm -rf ." has
#: no file_path, and no amount of prefix matching makes one safe to infer.
PATH_SCOPED = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

#: Paths that run code, or decide who may run code, on the next turn. A write
#: to one of these is never an "edit" in the sense the setting means, however
#: far inside the project it sits, so it is asked about even at "edits":
#:
#:   .claude/settings.json installs hooks that run unprompted;
#:   .mcp.json and .gemini/settings.json name commands the CLI will spawn;
#:   .git/hooks/* run on the next commit, .envrc on the next cd;
#:   .vscode/tasks.json runs on folder open;
#:   a .joblib is a pickle the daemon itself loads when its mtime changes.
#:
#: Matched as path fragments because the project is an arbitrary directory and
#: these sit at arbitrary depths inside it.
NEVER_SILENT = (
    "/.claude/", "/.mcp.json", "/.envrc", "/.git/hooks/", "/.vscode/tasks.json",
    "/.gemini/", "/.codex/", "/.config/omarchy/", "/.config/systemd/", "/.ssh/",
)

#: Same idea by extension rather than by location.
NEVER_SILENT_SUFFIX = (".joblib",)


def _sensitive(p: Path) -> bool:
    """True when a write to `p` has to be asked about whatever the level.

    "edits" is a statement about source files. These are not source files:
    each of them is a way to make something else run, including this
    daemon's own config and its own pickled verifier, so auto-allowing them
    would let one granted edit become arbitrary code on the next turn.
    """
    text = str(p)
    if any(frag in text + "/" for frag in NEVER_SILENT):
        return True
    if p.suffix in NEVER_SILENT_SUFFIX:
        return True
    try:
        if p == CONFIG_DIR or CONFIG_DIR in p.parents:
            return True
        # What every agent is told on every turn (merged plan, Phase 9): its
        # instructions, the communal rules. An agent that could rewrite them
        # unasked could rewrite its own orders. By resolved location, not by
        # fragment, because these sit under the data folder wherever XDG puts
        # it -- and only a project that contains that folder can reach them
        # here at all, so this is defence in depth below Trusted. At Trusted
        # there is no hook; the saved versions in agentfs make it visible.
        # And the Claude plugin folders made from them (Phase 13), whose
        # skills an agent loads as its own.
        return (_under(p, AGENTS_DIR) or _under(p, COMMUNAL_DIR)
                or _under(p, DATA_DIR / "agent-plugins")
                or _under(p, DATA_DIR / "omarchy-skill"))
    except (OSError, ValueError, RuntimeError):
        return True


def _under(p: Path, base: Path) -> bool:
    """True when the resolved `p` is `base` or inside it, `base` resolved
    too, since the data folder may itself sit behind a link."""
    root = base.resolve()
    return p == root or root in p.parents


def _foreign(path: str) -> bool:
    """True when `path` is in another agent's folder (merged plan, Phase 9).

    An agent may read its own folder and the communal one; another agent's
    instructions, notes and skills are asked about below Trusted, the way a
    credential is. Its own folder is told apart by the id this hook was
    started with (argv[2]; the main agent's is "", its folder `main`).
    Anything directly in agents/ that is not its own -- the trash, another
    id, the folder itself -- counts as another's. Unsure means foreign.
    """
    try:
        p = _resolved(path)
        me = _named() or "main"
        # The Claude plugin folders hold copies of each agent's skills
        # (Phase 13), named "<id>-<hash>": another agent's copy is as
        # private as its folder (Phase 13 review).
        plugins = (DATA_DIR / "agent-plugins").resolve()
        if p == plugins:
            return True
        if plugins in p.parents:
            # Exactly "<its id>-<20 hex>": "sora" must not own "sora-x-…".
            owner, _, digest = p.relative_to(plugins).parts[0].rpartition("-")
            return not (owner == me and len(digest) == 20
                        and all(c in "0123456789abcdef" for c in digest))
        root = AGENTS_DIR.resolve()
        if p == root:
            return True
        if root not in p.parents:
            return False
        return p.relative_to(root).parts[0] != me
    except (OSError, ValueError, RuntimeError):
        return True


def _settings() -> tuple[str, Path | None]:
    """The permission level and project directory, read fresh.

    The hook is a separate process spawned by Claude, so it cannot be handed
    these by the daemon -- it has to read the same config the daemon reads.
    Any failure falls back to the strictest setting: a config this cannot
    parse must not become a reason to stop asking.

    The directory is None when no project is configured, which makes "edits"
    behave as "ask" rather than as "all of home". See `paths.scope_root`.
    """
    try:
        from runtime import Config
        cfg = Config()
        # argv[1] is the agent that installed this hook. Without it the level
        # cannot be resolved, and an unresolved level is "ask" -- a hook that
        # does not know who it is guarding must not stop guarding.
        agent = sys.argv[1] if len(sys.argv) > 1 else ""
        # argv[2], when present, is the stable id of the extra agent this
        # process belongs to, which has a level and a folder of its own. An
        # id, not a name, so renaming the agent or changing its wake phrase
        # leaves this process guarded by the same decision. One that is no longer
        # configured, or that now names a different program, has nobody's
        # decision behind it: "ask", and no folder, so "edits" cannot widen.
        named = _named()
        if named:
            spec = cfg.agent_by_id(named)
            if spec is None or spec.get("agent") != agent:
                return "ask", None
            return spec["level"], scope_root(spec["projectDir"])
        return cfg.level_for(agent), scope_root(cfg.get_str("projectDir"))
    except Exception:
        return "ask", None


NOTES_DENIED = "You aren't allowed to write notes here. You can still read them."


def _may_write_notes() -> bool:
    """The agent's `notesWrite`, read fresh (merged plan, Phase 14). Any
    failure to read it is a no: a deny here only spares a question about a
    write the notes store would refuse anyway."""
    try:
        from runtime import Config
        cfg = Config()
        named = _named()
        if named:
            spec = cfg.agent_by_id(named)
            agent = sys.argv[1] if len(sys.argv) > 1 else ""
            if spec is None or spec.get("agent") != agent:
                return False
        return cfg.notes_write_for(named)
    except Exception:
        return False


def _notes_question(crew: str, tool_input) -> tuple[dict, str, str]:
    """For a notes write about to be asked about: the input as the card
    shows it (only the fields the tool declares, so an extra `command`
    cannot put words on the card that are not what runs), one line saying
    what it writes where, and the refusal when the note is locked (nobody
    is asked about a write the store would refuse). Unsure of the lock is
    not a refusal here: the store checks it again, inside its own lock."""
    raw = tool_input if isinstance(tool_input, dict) else {}
    keep = ("scope", "name", "text") + (("base",) if crew == "notes_write" else ())
    clean = {k: raw[k] for k in keep if k in raw}
    name = raw.get("name")
    name = name if isinstance(name, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", name) else ""
    scope = raw.get("scope")
    where = ("its own notes" if scope == "mine" else
             "the communal notes" if scope == "communal" else "")
    text = raw.get("text")
    size = f"{len(text)} characters" if isinstance(text, str) else "no text"
    verb = "adds to" if crew == "notes_append" else "writes"
    note = (f"this {verb} the note “{name or '?'}” in {where or 'an unknown place'} "
            f"({size})")
    locked = ""
    base = raw.get("base", 0)
    if not name or not where or (crew == "notes_write" and "base" in raw and (
            isinstance(base, bool) or not isinstance(base, int) or base < 0)):
        # The server refuses these before writing anything; nobody is asked.
        return clean, note, ("That note name, scope or base is not valid: a name is 1 to 48 "
                             "characters of a-z, 0-9 and -; scope is mine or communal; base "
                             "is the rev notes_read gave, or left out.")
    if name and where:
        try:
            import notes
            import agentfs
            target = "communal" if scope == "communal" else agentfs.folder_id(_named())
            if notes.is_locked(target, name):
                locked = (f"The note {name} is locked by the person: it is read-only for "
                          f"every agent.")
        except Exception:
            pass
    return clean, note, locked


def _chain() -> str:
    """The chain the asking agent works for, from the origin file the daemon
    writes while it runs a task; "" when there is none or it cannot be read.
    Never raises: this is on the way to a question, and a hook that throws
    is a hook that permitted."""
    try:
        import collab
        chain = collab.read_origin(_named() or "main")
        return collab.chain_text(chain) if chain else ""
    except Exception:
        return ""


def _named() -> str:
    """The id of the extra agent this hook guards, or "" for the main one."""
    return sys.argv[2] if len(sys.argv) > 2 else ""


def _label() -> str:
    """What the person calls the agent asking, for the card on screen. Its
    display name, read fresh; the id when it cannot be read. Never decides
    anything: only `_named()` reaches a grant."""
    named = _named()
    try:
        from runtime import Config
        cfg = Config()
        if not named:
            return cfg.main_label()
        spec = cfg.agent_by_id(named)
        return spec["label"] if spec else named
    except Exception:
        return named


def _inside(path: str, root: Path | None) -> bool:
    """True when `path` resolves to something under `root`.

    Resolved on both sides, because the whole point is to answer "is this in
    the project", and `~/project/../../etc/passwd` is not, however it is
    spelled.

    `resolve()` without `strict` is what does it: it resolves every symlink it
    can and leaves the rest of the path alone, so a file that does not exist
    yet is still judged -- Write creates files -- and so is a *dangling*
    symlink. Testing `exists()` first and resolving only the parent used to
    miss exactly that: `exists()` follows links, so a link whose target was
    not there yet counted as "does not exist", and `notes.txt ->
    ~/.config/systemd/user/evil.service` was judged to be inside the project.
    """
    if not path or root is None:
        return False
    try:
        p = Path(path).expanduser().resolve()
        return p == root or root in p.parents
    except (OSError, RuntimeError, ValueError):
        return False


def _resolved(path: str) -> Path:
    """`path` with symlinks and `..` taken out, or something harmless-looking
    that `_sensitive` will still judge rather than crash on."""
    try:
        return Path(path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return Path("/.ssh/unparseable")


def _edit_target(tool_name: str, tool_input: dict) -> str:
    """The one file an edit tool will write, or "" when that is not plain.

    The tool's own field: `notebook_path` for NotebookEdit, `file_path` for
    the rest. A value that is not a string, or a second path field naming a
    different file, is not plain, and "" sends it to the question -- a
    harmless `file_path` beside the real `notebook_path` used to be the one
    judged, and an integer became a relative name inside the project.
    """
    own = "notebook_path" if tool_name == "NotebookEdit" else "file_path"
    other = "file_path" if own == "notebook_path" else "notebook_path"
    target = tool_input.get(own)
    if not isinstance(target, str) or not target:
        return ""
    second = tool_input.get(other)
    if second is not None and second != target:
        return ""
    return target


def _paths_in(tool_input: dict) -> list[str]:
    """Every value in a tool's input that names a place on disk."""
    keys = ("file_path", "notebook_path", "path", "pattern", "glob")
    return [str(tool_input[k]) for k in keys
            if isinstance(tool_input.get(k), str) and tool_input[k]]


def _is_secret(path: str) -> bool:
    """True when reading `path` is worth a question however read-only it is."""
    p = _resolved(path)
    text = str(p) + "/"
    if any(frag in text for frag in SECRETS):
        return True
    if p.name in SECRET_NAMES or p.suffix in SECRET_SUFFIXES:
        return True
    return p.name.startswith(".env")


#: Tools that return the *contents* of files they were never asked for by
#: name. Glob is deliberately absent: it returns paths, and that
#: `credentials.json` exists is a far smaller thing than what is inside it.
CONTENT_SEARCH = {"Grep"}

#: Caps on the pre-search. A repository with a million files must not hold
#: the hook open, and a search that cannot be enumerated inside them is
#: answered by asking rather than by assuming it is clean.
SEARCH_FILE_CAP = 20_000
#: One budget for the whole question, not one per strategy. Three five second
#: timeouts in a row meant a Grep of $HOME sat for 23 seconds inside a hook
#: that blocks the tool -- measured, and the agent simply looks hung.
SEARCH_BUDGET_S = 2.0


def _searchable(root: str, glob: str | None = None) -> list[str] | None:
    """Every file a content search under `root` would actually read.

    `rg --files` rather than a walk, because it applies the same ignore
    rules the search itself will: a `.env` listed in .gitignore cannot come
    back in results, so asking about it would be a prompt about nothing --
    and a guard that fires when it need not is how people learn to click
    through guards that matter.

    None when the question cannot be answered inside the caps. The caller
    asks in that case; "could not tell" is not "nothing there".

    With the search's own `glob`, the listing ignores the ignore files and
    applies that glob instead: a glob that names a file can outrank the
    .gitignore that hides it, so the ignored `.env` the plain listing leaves
    out is exactly what `glob: ".env"` searches. Over-asking there is the
    safe side. git cannot answer that question, so it is skipped for it.
    """
    deadline = time.time() + SEARCH_BUDGET_S

    def left() -> float:
        return deadline - time.time()

    try:
        # --hidden, because rg skips dotfiles by default and almost everything
        # on the protected list is one: .ssh, .aws, .gnupg, .env. Without it
        # this looked like it worked and saw none of them. Ignore rules still
        # apply with it, so an ignored .env is still not a prompt.
        argv = ["rg", "--files", "--hidden", "--no-messages"]
        if glob:
            argv += ["--no-ignore", "-g", glob]
        proc = subprocess.run(argv + ["--", root],
                              capture_output=True, text=True, timeout=max(left(), 0.1))
        # rg exits 1 for "no files", a real answer, and 2 for trouble.
        if proc.returncode in (0, 1):
            files = proc.stdout.splitlines()
            return None if len(files) > SEARCH_FILE_CAP else files
    except (OSError, subprocess.SubprocessError):
        pass

    if glob:
        return _walk(root, deadline)

    # Second choice, and it answers the same question: tracked files plus
    # untracked ones git is not ignoring, which is the set rg would have
    # searched. Without this the walk below sees everything a .gitignore
    # hides -- and on this repository that is bench/.venv, whose certifi
    # ships a cacert.pem: a public CA bundle matching the `.pem` rule, so
    # every search prompted about a credential that is nothing of the kind.
    try:
        proc = subprocess.run(
            # `-c core.fsmonitor=`: git reads that key from the repository's
            # own .git/config and *executes* it. So enumerating a project was
            # running code the project carried -- as the session user, before
            # anything was asked, at every level including `ask`. The guard
            # whose job is deciding whether something may run, running it.
            #
            # .git/config is not fetched by `git clone`, but it travels in a
            # tarball, a zip, or a copied directory, which is what makes an
            # imported or shared project the case that matters. Reported
            # against a272d79 by a marketplace reviewer as a static trace;
            # reproduced here before fixing, and `git describe` in
            # paths.build_id turned out to have the same shape.
            #
            # `--no-optional-locks` because a guard inspecting a repository
            # has no business writing to its index.
            ["git", "-c", "core.fsmonitor=", "--no-optional-locks",
             "-C", root, "ls-files", "--cached", "--others",
             "--exclude-standard", "-z"],
            capture_output=True, text=True, timeout=max(left(), 0.1))
        if proc.returncode == 0:
            names = [n for n in proc.stdout.split("\0") if n]
            if len(names) > SEARCH_FILE_CAP:
                return None
            return [os.path.join(root, n) for n in names]
    except (OSError, subprocess.SubprocessError):
        pass

    return _walk(root, deadline)


def _walk(root: str, deadline: float) -> list[str] | None:
    """The same question without ripgrep, and answered more cautiously.

    Without rg there is nothing to read .gitignore for us, so this sees
    ignored files too and will ask about an ignored .env that could never
    have come back in results. That is the right way round: the alternative
    was returning "cannot tell" whenever rg was absent, which made every
    single search prompt -- a guard nobody can live with is a guard that
    gets switched off.

    `.git` is skipped. It is large, it is most of the walk on any real
    repository, and the credential files this list names live in $HOME
    rather than inside a checkout's object store.
    """
    out: list[str] = []
    try:
        for here, dirs, names in os.walk(root, onerror=None):
            if ".git" in dirs:
                dirs.remove(".git")
            for n in names:
                out.append(os.path.join(here, n))
                # Checked per file rather than per directory: one directory
                # holding a million entries is the case that blew the budget.
                if len(out) > SEARCH_FILE_CAP or time.time() > deadline:
                    return None
            if time.time() > deadline:
                return None
    except OSError:
        return None
    return out


def _search_would_read(tool_input: dict) -> list[str] | None:
    """Protected files a content search would return the contents of.

    The hole this closes: `_paths_in` judges a tool by its *arguments*, which
    works for a read -- the argument is the file -- and not at all for a
    search, whose arguments are a pattern and a directory while its output is
    whatever lies beneath. So reading credentials.json asked, and grepping
    the folder it sits in did not, for the same bytes. Reported against
    cba1abf by a marketplace reviewer.
    """
    root = tool_input.get("path")
    root = str(root) if isinstance(root, str) and root else os.getcwd()
    # Spelled as the tool will read it. Handed over verbatim, "~/x" was a
    # directory that does not exist to rg and to the walk, so the pre-search
    # found nothing and the search was allowed -- while the tool itself
    # expanded the tilde and searched the real tree.
    root = str(_resolved(root))
    glob = tool_input.get("glob")
    glob = glob if isinstance(glob, str) and glob else None
    # A search rooted at the agent folders or anything above them can
    # return another agent's files whatever its filters say (a glob can
    # outrank an ignore rule), so it is asked about without enumerating.
    # Searches that wide -- home, / -- were past the file cap and asked
    # already; the new case is the data folder itself.
    files = _searchable(root, glob) if glob else _searchable(root)
    if files is None:
        return None
    try:
        agents = AGENTS_DIR.resolve()
        if Path(root) == agents or Path(root) in agents.parents:
            return [str(agents)]
    except (OSError, RuntimeError, ValueError):
        return [root]
    return [f for f in files if _is_secret(f) or _foreign(f)]


def _grant_file(session: str) -> Path:
    """Where the grant for `session` lives, for this agent. Named by a hash of
    who is asking and the session, so two agents never share a grant and the
    id is never trusted as a filename."""
    import hashlib
    agent = sys.argv[1] if len(sys.argv) > 1 else ""
    key = f"{agent}\0{_named()}\0{session}".encode()
    return GRANTS / (hashlib.sha256(key).hexdigest()[:32] + ".grant")


def granted(session: str) -> bool:
    """True only for a grant this user wrote, for exactly this conversation.

    Every way of being unsure is a no: a missing or malformed id, a file that
    is a symlink, belongs to someone else or is writable by anyone else, or
    holds anything but the record `grant()` writes. A no here is not a
    denial -- it just means the question is asked as usual."""
    try:
        if not _SESSION.fullmatch(session or ""):
            return False
        path = _grant_file(session)
        st = os.lstat(path)
        import stat as _stat
        if (not _stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                or st.st_mode & 0o077):
            return False
        record = json.loads(path.read_text())
        return (isinstance(record, dict) and record.get("session") == session
                and record.get("agent") == (sys.argv[1] if len(sys.argv) > 1 else "")
                and record.get("who") == _named())
    except Exception:
        return False


def grant(session: str) -> bool:
    """Remember "allow everything" for this conversation. False if it could not."""
    try:
        if not _SESSION.fullmatch(session or ""):
            return False
        GRANTS.mkdir(parents=True, exist_ok=True, mode=0o700)
        GRANTS.chmod(0o700)
        path = _grant_file(session)
        staged = path.with_suffix(f".{os.getpid()}.staging")
        fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"session": session, "who": _named(),
                       "agent": sys.argv[1] if len(sys.argv) > 1 else "",
                       "at": time.time()}, f)
        os.replace(staged, path)
        return True
    except Exception:
        return False


def decide(tool_name: str, tool_input: dict, session: str = "") -> tuple[str, str]:
    """Return (decision, reason). decision is 'allow' or 'deny'."""
    if tool_name in NO_EFFECT:
        return "allow", ""

    # Before the grant and the level: these are asked about at every level,
    # and "allow all in this chat" is not an answer to "buy this".
    why = browser_consequence(tool_name, tool_input)
    if why:
        return _ask(tool_name, tool_input, note=why, announce=True)

    desktop = tool_name[len(DESKTOP_PREFIX):] if tool_name.startswith(DESKTOP_PREFIX) else ""
    if desktop in DESKTOP_READ_ONLY or desktop in DESKTOP_SELF_ASKED:
        return "allow", ""
    if desktop in DESKTOP_SENSITIVE_READ:
        if granted(session) or _settings()[0] == "trusted":
            return "allow", ""
        return _ask(tool_name, tool_input, note="this reads the clipboard",
                    session=session)

    crew = tool_name[len(CREW_PREFIX):] if tool_name.startswith(CREW_PREFIX) else ""
    if crew in CREW_READ_ONLY:
        return "allow", ""

    # Allowed wholesale for this conversation, from the prompt. Like
    # "trusted", it covers everything, credentials included -- that is what
    # the button says -- but only this agent, only this conversation.
    if granted(session):
        if crew in CREW_WRITES and not _may_write_notes():
            return "deny", NOTES_DENIED
        return "allow", ""

    if crew in CREW_WRITES:
        # After the grant, so "allow all in this chat" covers it as it
        # covers other tools (merged plan, Phase 8 corrections).
        if not _may_write_notes():
            return "deny", NOTES_DENIED
        clean, note, locked = _notes_question(crew, tool_input)
        if locked:
            return "deny", locked
        level, _ = _settings()
        if level in ("edits", "trusted"):
            return "allow", ""
        return _ask(tool_name, clean, note=note, session=session)

    if (tool_name == "Skill" and isinstance(tool_input, dict)
            and isinstance(tool_input.get("skill"), str)
            and OWN_SKILL.fullmatch(tool_input["skill"])):
        return "allow", ""

    # Reads are free unless they are reads of a credential. Checked before
    # the level, because this holds at "ask" and at "edits" alike -- only
    # "trusted" below skips it, which is what "trusted" means.
    if tool_name in READ_ONLY:
        secrets = [p for p in _paths_in(tool_input) if _is_secret(p)]
        note = f"this reads {secrets[0]}" if secrets else ""
        if not secrets:
            secrets = [p for p in _paths_in(tool_input) if _foreign(p)]
            note = (f"this reads another agent's folder ({secrets[0]})"
                    if secrets else "")

        # The level is consulted *before* the pre-search, not after. At
        # "trusted" the answer is allow whatever the tree holds, and paying
        # for an enumeration to then ignore it is pure latency -- 23 seconds
        # of it on $HOME, inside a hook the tool is waiting on.
        if not secrets and tool_name in CONTENT_SEARCH \
                and _settings()[0] != "trusted":
            found = _search_would_read(tool_input)
            if found is None:
                secrets = ["?"]
                note = ("this searches a tree too large to check for "
                        "credentials")
            elif found:
                secrets = found
                note = (f"this search would read {found[0]}"
                        + (f" and {len(found) - 1} more"
                           if len(found) > 1 else ""))

        if not secrets:
            return "allow", ""
        level, _ = _settings()
        if level == "trusted":
            return "allow", ""
        return _ask(tool_name, tool_input, note=note, session=session)

    level, root = _settings()
    if level == "trusted":
        return "allow", ""
    if level == "edits" and tool_name in PATH_SCOPED:
        target = _edit_target(tool_name, tool_input)
        if target and _inside(target, root) and not _sensitive(_resolved(target)):
            return "allow", ""

    return _ask(tool_name, tool_input, session=session)


def _ask(tool_name: str, tool_input: dict, note: str = "",
         session: str = "", announce: bool = False) -> tuple[str, str]:
    """Put the question on screen and wait for an answer.

    Split out of decide() so both the write path and the read-a-secret
    path ask the same way, through the same file protocol and the same
    timeout. `note` is why it is being asked, when that is not obvious
    from the tool and the path.
    """
    # 0o700: the request holds whatever the agent is about to run, and the
    # response is the word "yes". Neither is anyone else's business, and a
    # response another local user could write would be a free allow.
    PENDING.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        PENDING.chmod(0o700)      # mkdir's mode is ignored if it exists
    except OSError:
        pass
    request_id = uuid.uuid4().hex[:12]
    request = PENDING / f"{request_id}.request"
    response = PENDING / f"{request_id}.response"

    # One line the overlay can show without wrapping. The full input goes
    # along too, for anything that wants the detail.
    # A notebook edit writes its notebook_path; with a different file_path
    # beside it, showing that one would be a prompt that lies about its
    # target, so both are shown.
    nb = tool_input.get("notebook_path") if tool_name == "NotebookEdit" else None
    if isinstance(nb, str) and nb:
        other = tool_input.get("file_path")
        nb = nb if other in (None, nb) else f"{nb} (and file_path {other})"
    summary = str(tool_input.get("command")
                  or nb
                  or tool_input.get("file_path")
                  or tool_input.get("path")
                  or tool_input.get("url")
                  or tool_input.get("action_summary")
                  or tool_input.get("pattern")
                  # A note about to be written (Phase 14): the person sees
                  # the words before they land, not "(no detail)".
                  or tool_input.get("text") or "")
    # Truncated, but never silently. `echo ok` followed by 400 spaces and
    # `; rm -rf ~/work` displayed as `echo ok`, which is a prompt that lies
    # about what it is asking for.
    shown, cut = summary[:400], max(0, len(summary) - 400)
    if cut:
        shown += f"… (+{cut} more characters, {summary.count(chr(10)) + 1} lines)"
    # Written to a temporary name and chmod'd before it is given the one the
    # overlay watches, so it is never briefly readable under its real name --
    # the same order the state file uses. `input` is the whole tool call, which
    # for a write is the entire file content, so the directory mode is not the
    # only thing standing in front of it.
    staged = PENDING / f"{request_id}.staging"
    staged.write_text(json.dumps({
        "id": request_id,
        "tool": tool_name,
        # Which agent is asking, when there is more than one: two can be at
        # work at once, and a card that only says "the agent" cannot be
        # answered knowingly.
        "who": _named(),
        "label": _label(),
        # Whom it is working for, while it does a task another agent passed
        # it (Phase 15): "for Theo, for you". Words on the card only; it
        # never changes what is decided.
        "chain": _chain(),
        "summary": shown,
        "note": note,
        "truncated": cut,
        "length": len(summary),
        "input": tool_input,
        "asked_at": time.time(),
        "timeout": TIMEOUT,
        # Whether "allow everything in this chat" can be offered: only when
        # there is a conversation to scope it to.
        "sessionWide": bool(_SESSION.fullmatch(session or "")),
        # Said out loud by the daemon as well as shown (plan 12d): a
        # purchase should not wait on somebody happening to look.
        "announce": bool(announce),
    }))
    staged.chmod(0o600)
    staged.replace(request)

    # Put it on screen. The overlay reads the request file itself, so the
    # payload only has to say which one. Failure here is not fatal: the
    # request still times out into a denial, which is the safe direction.
    try:
        import subprocess
        subprocess.run(["omarchy-shell", "shell", "summon", "duaneoca.agentvoice",
                        json.dumps({"mode": "permission", "id": request_id})],
                       timeout=5, capture_output=True)
    except Exception:
        pass

    deadline = time.time() + TIMEOUT
    try:
        while time.time() < deadline:
            if response.exists():
                try:
                    answer = json.loads(response.read_text())
                except Exception:
                    answer = {}
                if not isinstance(answer, dict):
                    answer = {}
                # `is True`, not truthiness: only the literal yes the overlay
                # writes counts. A response file holding anything else is a
                # response this cannot read, and that is a denial.
                if answer.get("allow") is True:
                    # This one is allowed whatever happens next; the grant
                    # only saves asking again in this conversation.
                    if answer.get("session") is True:
                        grant(session)
                    return "allow", ""
                return "deny", str(answer.get("reason") or "Denied at the desktop.")
            time.sleep(0.1)
        return "deny", f"Nobody answered within {TIMEOUT:.0f} seconds."
    finally:
        # staged is normally gone -- replace() consumed it -- but a chmod that
        # raised would otherwise leave the whole tool call on disk unowned.
        staged.unlink(missing_ok=True)
        request.unlink(missing_ok=True)
        response.unlink(missing_ok=True)


def _die_cleanly() -> None:
    """Turn a kill into a normal unwind, so the request file goes away.

    Claude kills the whole process group when a turn is interrupted. The
    default SIGTERM disposition skips `finally`, which left the .request file
    behind -- and `agentvoice pending` then showed a question nobody was
    waiting for an answer to, forever.
    """
    def raise_it(signum, _frame):
        raise SystemExit(f"interrupted by signal {signum}")

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, raise_it)
        except (OSError, ValueError):
            pass


def _emit(decision: str, reason: str = "") -> int:
    out = {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
    }}
    if reason:
        out["hookSpecificOutput"]["permissionDecisionReason"] = f"agentvoice: {reason}"
    json.dump(out, sys.stdout)
    sys.stdout.write("\n")
    return 0


def main() -> int:
    """Decide, and whatever happens, say so.

    Everything here is inside one catch, because of how Claude Code reads a
    hook: exit 0 with a decision is the decision, exit 2 is a block, and
    *anything else* -- an unhandled traceback, an ImportError, a full disk
    while writing the request file -- is a non-blocking error, which means
    the tool runs. So the failure mode of this file is not "the hook broke",
    it is "the guard was not there". Every path out of here is a denial that
    names itself.
    """
    _die_cleanly()
    try:
        try:
            payload = json.load(sys.stdin)
        except Exception:
            # An unreadable payload must not become an accidental allow.
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        tool = payload.get("tool_name") or "unknown"
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            tool_input = {}

        session = payload.get("session_id")
        decision, reason = decide(str(tool), tool_input,
                                  session if isinstance(session, str) else "")
        return _emit(decision, reason)
    except BaseException as e:                  # noqa: BLE001 -- see docstring
        try:
            return _emit("deny", f"the permission hook failed: "
                                 f"{type(e).__name__}. Nothing was run.")
        except BaseException:
            # Even the denial could not be written. Exit 2, which Claude Code
            # reads as a block in its own right.
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
