# Phase 9: Storage foundation (`daemon/agentfs.py`)

Written 2026-11-19. Branch `phase-9`, cut from `phase-8` at ecbaffe, pushed
to `fork/phase-9` only (the hash is in `git log`). Installed: yes, and the
live check below ran on the installed build. Tested on: i7-1185G7, `claude`
2.1.328, `codex-cli` 0.170.0.

`./bin/agentvoice-check`: green, 1934 tests (was 1819). The new and changed
test files also pass on the bare runner (`AGENTVOICE_STRICT=1`). Box: not
run (`install.sh` did not change; the templates sit under `daemon/`, which
it already copies, and the installed copy was checked to have them).

Codex reviewed the phase twice before it was pushed; what that changed is
under "Found along the way".

## What was built

- **A9-0, the Codex session fix, first** (moved here by the user from
  Phase 8). `Codex` and `Gemini` now keep `ask_permission`, so
  `reconcile_agent` keeps a Codex or Gemini main agent and its session
  across an idle refresh. The test failed before the fix (it reproduced the
  bug) and fails again if either attribute is removed.
- **`daemon/agentfs.py`**, which owns the agent folders and the communal
  folder:
  - folder ids checked against the settings' id pattern; `main` is the main
    agent's folder (`folder_id("")`); file names only from a fixed set
    (`role.md`, `personality.md`, `instructions.md`; `rules.md`,
    `defaults.md`; `skills/<name>/SKILL.md`), so neither is ever a path;
  - **any symlink under the folders is refused**, wherever it points,
    dangling ones included;
  - **reading never fails**: a missing file is empty; an oversize one is cut
    to its budget with a problem published; a binary, non-UTF-8, symlinked
    or non-regular file (a FIFO included, opened non-blocking) keeps the
    last good text this process saw, or reads as empty with none. The
    starter `<!-- ... -->` comment, a BOM and control characters are
    stripped before anything is counted or told;
  - **writes** go version first, live file second (atomic, fsynced, an
    exclusive temporary name, the directory fsynced), under one `fcntl`
    lock; a failed live write takes its version back out. A `base` stamp
    that no longer matches is a conflict (CLI exit 3) carrying the current
    stamp. Stamps are a hash of the bytes plus the size, the same for a
    read and a write;
  - **saved versions**, newest ten, for every file including skills. A file
    whose content differs from its newest version was changed outside
    Settings: it applies, and `read()` reports it. **Keep** (`ack`) and
    **Revert** (newest, or a named version) both accept a `base`, so they
    act only on the file the person was shown;
  - `create` from `daemon/templates/agent/`, `ensure_communal` from
    `daemon/templates/communal/` (each file with a starter comment saying
    what it is for and its limit; no persona, no provider);
  - **trash and restore**: the folder moves to `agents/.trash/<id>-<ns>/`
    with its settings entry in a sidecar beside it, written first; restore
    puts both back and refuses, leaving the entry, if the sidecar cannot be
    read. An agent with no folder can still be trashed for its settings;
  - the CLI from section 3.7 for this phase (`list`, `show`, `create`,
    `trash`, `restore`, `trash-list`, `write`, `history`, `revert`, `ack`,
    `ensure-communal`), as `agentvoice agents …`, text always on stdin.
- **The daemon notices hand edits** (`Daemon.reconcile_agent_files`, called
  from `refresh()` outside the config guard). It compares file stamps on
  every idle poll and re-reads only on a change; it logs one structural
  line of sizes and flags, never text, and publishes per-folder sizes,
  problems and files changed outside Settings as `agent_files` in the state.
  With no folders it says and publishes nothing. A failed read is retried on
  the next poll, and a failed publish does not stop the poll.
- **The permission hook**:
  - a raw write into `agents/` or `communal/`, by resolved location, is
    never silent below Trusted (`_sensitive`);
  - a raw read of another agent's folder asks below Trusted, the way a
    credential read does (`_foreign`); its own folder and the communal one
    are free. A content search rooted at or above `agents/` asks;
  - edit tools are judged by their own field (`notebook_path` for
    NotebookEdit), and a non-string path or a second path field naming a
    different file goes to the question; a notebook question shows the
    notebook path.

## Shared files touched, and where

- `daemon/wake_listen.py`: one call in `refresh()`, the new
  `reconcile_agent_files` method beside it, and `agent_files` added to
  `crew_fields()`.
- `daemon/permission_hook.py`: `_sensitive`, the new `_under`, `_foreign`
  and `_edit_target`, the read branch of `decide`, the edits rule,
  `_searchable` (a `glob` argument) and `_search_would_read`, and the
  summary line in `_ask`.
- `daemon/paths.py`: `AGENTS_DIR`, `COMMUNAL_DIR`.
- `daemon/adapters/codex.py`, `gemini.py`: one attribute each.
- `bin/agentvoice`: the `agents` subcommand.

## Measured (numbers, against the baseline)

- Idle-poll cost (FINDINGS §34): `stamp()` median 1.48ms, max 2.15ms with
  eight agents, the communal folder and a skill each; `summary()` 10.0ms,
  only on a change.
- Hand edit to journal line on the real daemon: 1.75s (the poll is 2s).
- No prompt or turn path changed, so the Phase 8 latency baselines do not
  apply until Phase 11.

## Different from the plan, and why

- **Every symlink is refused**, not only one that leads out of the folder.
  Simpler to reason about, and stricter.
- **An agent whose id is `communal` keeps its id and gets no folder**, with
  a reason. The settings accept that id; reserving it in `runtime.py` (the
  first attempt) would have silently re-keyed an existing agent's chats and
  grants, which Codex's second review caught. Phase 10 reports it.
- The plan's stamp was unspecified; it is a content hash plus size, so two
  saves in the same second are still told apart.
- Keep and Revert take a `base` as well as Save does.

## Found along the way (bugs, surprises)

- **Codex's first review** found, and this phase fixed before pushing:
  - **a Grep whose path started with `~` was never checked**: the pre-search
    handed `~/x` to rg and the walk verbatim, found no such folder, and the
    search was allowed while the tool searched the real tree. This was a
    pre-existing fail-open in the credential check too, now closed for both;
  - `history()` skipped the file-name check and could list version-shaped
    files anywhere;
  - a FIFO in place of a file would have hung the daemon's idle poll;
  - a failed save could leave the live file changed with no version, and a
    failed trash could leave half an entry;
  - `NotebookEdit` with a harmless `file_path` beside the real
    `notebook_path` was judged by the wrong one, and an integer path became
    a relative name inside the project (both pre-existing);
  - one folder that could not be read took the whole summary down, and the
    stamp was committed before the read succeeded;
  - `trash()` could chmod through a symlinked `agents/` before refusing it;
  - several tests passed for the wrong reason (listed in the review).
- **Codex's second review** found, and this phase fixed: a Grep `glob` can
  bring in a file the .gitignore hides, so with a glob the listing now
  ignores the ignore files (also pre-existing for credentials); the
  `communal` re-keying above; a publish error could still stop the poll;
  read text and stamp came from two reads; Keep and Revert acted on a file
  the person had not seen; failed writes left temporary files.
- **My own mutation script** failed to restore four mutations on its first
  run (the replacement text was not unique), which left `return False` in
  the two hook rules for one test run. Caught immediately, fixed by hand,
  and every mutation rerun with a backup copy instead.
- The concurrent-writer test did not catch a missing lock until the writers
  were made to start at the same instant.

**Mutations**: each of 26 guards was removed in turn and a test went red
for every one (the hook's write rule, read rule, search filter, ancestor
rule, tilde expansion, glob listing, edit field and second-field checks,
the notebook prompt; agentfs's symlink refusal, base check, notice, lock,
file-name set, history name check, FIFO open, save rollback, NUL refusal,
stamp size, trash rollback, temp cleanup, ack and revert bases; and A9-0 on
both adapters).

## Not verified (what was skipped, and why)

- A hand edit reaching an agent's *prompt*: nothing is sent to agents until
  Phase 11. The live check proves the daemon sees and publishes it.
- The box (`install.sh` unchanged).
- Accepted and written down, not fixed (Codex flagged them; each needs a
  process already running as the user, or is a rare edge): a directory
  swapped for a link between the check and the open (section 3.5 now says
  so); history ordered by wall clock; an edit with the same size and a
  restored mtime is not noticed until something else changes; a broken or
  removed folder can hide its notices; the hook still runs its pre-search
  in its own working folder, not the session's `cwd` from the hook input,
  and reads rg's newline-separated list (pre-existing); a malformed `Read`
  with no path is allowed, as before; "allow everything in this chat"
  covers the new rules, by design.

## Going back (what an older build sees after this phase)

An older build ignores `agents/` and `communal/` entirely, and nothing in
shell.json changed. The live check's throwaway folder was removed
afterwards, so this machine has no agent folders yet: Phase 10 creates them.

## Open issues, for the next phase

- Phase 10 creates the folders, migrates the instructions, and reports an
  agent whose id is `communal`.
- The Agents page's add and remove should call `agents create` and
  `agents trash` (Phase 10).
- Consider passing the hook input's `cwd` to the Grep pre-search (a
  pre-existing gap, found here).

## Live checklist: what was said, what happened

No voice was involved; this phase has no spoken behaviour. On the installed
build: `agentvoice agents create phase9-check` → the journal printed
`agent files: phase9-check: role 0 personality 0 instructions 0` on the next
poll. A shell write of one synthetic sentence into `personality.md` → 1.75s
later `… personality 33 … · 1 changed outside`, `agents list` showed the
notice, and `agentvoice status` carried it in `agent_files`. `agents ack` →
the notice cleared on the next poll. The folder was then removed and the
journal printed `agent files: none`.
