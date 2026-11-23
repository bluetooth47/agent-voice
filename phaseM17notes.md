# Phase M17: Advanced: controls and agent management

Written 2026-11-22, unattended (started by the runner script). Branch
`phase-m17`, cut from `phase-m16` at f6c4f7e. Result commit: the notes commit
on top of d7c3918, pushed to `fork/phase-m17` only; `dev` fast-forwarded to it
and pushed to `fork`. Model: Claude Opus 5.5 (tier A in the plan: launch flags
are a security boundary).

Commits:
- d7c3918: the phase;
- then these notes.

**Codex review: bypassed (user decision, 2026-11-22).** Codex was not run, for
review or anything else. In its place I re-read the whole diff before the
commit; what that found is under "Found along the way". Nothing in this phase
has been reviewed by a second model, and it is a Tier A phase: the plan's
safety net for those was both Codex passes.

Deployed: **yes**, once, through `bin/agentvoice-deploy --install --wait 120
d7c3918` (its strict check green), with the daemon idle (state `listening`,
every agent idle, no open mic, no task, no turn in the journal for the five
minutes before). "deployed d7c3918c2528. The way back: bin/agentvoice-deploy
0322b00c59f2". **The way back to before M17 is `bin/agentvoice-deploy
0322b00c59f2`** (see "Going back").

Installed: **yes**: "Build 0.2.0 (d7c3918), replacing 0.2.0 (0322b00)". The
daemon, the adapters, the hook, the CLI and the manifest changed. `install.sh`
did not.

**Shell restart needed** (`pages/AgentDetailsPage.qml`, `AgentFolders.qml`,
`Settings.qml`). Not run. Until it is, the running shell has M16's Advanced
tab (read only): none of the new controls are drawn, and nothing is broken
meanwhile -- the new settings are at their defaults (resume on, 90 s, no extra
flag), which is exactly what every agent did before M17.

A copy of `shell.json` was taken before the deploy
(`~/agentvoice-notes/shell.json.before-M17`, 0600); after the install and the
live checks it was byte-identical. No live check wrote a setting, a file in a
real agent folder, or the real environment file.

`./bin/agentvoice-check`: green on the final tree (exit 0, every line ok).
- **4629 tests** (was 4401; +228), 14 of 14 static checks, "the check wrote
  nothing in the tree: ok".
- Bare-runner variant (`AGENTVOICE_STRICT=1`, a venv with only
  requirements-dev): **green**, 4613 passed, 9 skipped (the same numpy-only
  skips as M16).
- Box: not run (`install.sh` did not change).
- The one commit before these notes was made on a check read in full with its
  exit status (the first full run had found one failure, below, fixed before
  the commit).

## What was built

**Agent details → Advanced: how it is launched.** The tab that M16 made read
only now also changes how the agent's program starts, from its next turn. The
intro says so ("A change applies from its next turn; the risky ones ask
first"). Below the command line:

- **Extra flags** (Claude Code and Codex; `mainExtraArgs` /
  `voiceAgents[i].extraArgs`). Each saved flag is listed with its verdict
  ("⚠ passed", or "refused: <why>") and a Remove. Typing one asks
  `agentvoice agents flags check PROGRAM` (250 ms after the last keystroke) --
  the very judge the adapter runs at launch, so the page holds no copy of the
  list. A refused flag shows "Refused, and not saved: <why>" and Add cannot be
  pressed; a harmless one shows the ⚠ warning, and Add is a DangerButton
  ("Pass --debug to Theo's program on every turn?"). The verdict is tied to
  the exact text it judged, so an edit after a check can never ride an older
  "ok". Clear all, one click, and the note "Its last turn failed (KIND). If
  that began when a flag was added, clear them" from the log ring (the plan's
  "last error shown, one-click clear"). The row says a command line is
  readable by every account through /proc, so a key belongs in an
  environment variable. Another program (Gemini, Antigravity, Copilot) is
  passed none, and the row says why.
- **Environment variables** (Claude Code and Codex). Names only, each with a
  Remove that asks first ("Its value is kept nowhere else"); a NAME field, a
  password field and Set. The value goes to `agents env ID set NAME --line`
  on stdin and leaves the field as it is handed over, set or not. A refused
  name comes back with the reason.
- **Resume its conversation** (`mainResume` / `.resume`), a switch, disabled
  with the reason for a program that keeps no conversation; **Start fresh**,
  a DangerButton running `agentvoice chats new ID`.
- **Stop a turn after** (`mainIdleTimeoutS` / `.idleTimeoutS`), a slider
  30–600 s, default 90; an endpoint keeps its own timeout on the Agents page.
  The Timeouts row now says only the keep-warm time is fixed.
- In the Folder row, beside Open folder, Export and Remove: **Duplicate**
  (plain: it widens nothing) and **Reset to defaults** (a DangerButton,
  extra agents only), each with a paragraph saying exactly what is copied or
  reset, and after a reset an Undo bar like the removal's.

**`daemon/launch_extras.py`** (new): the flag judge and the environment file.
- `judge(program, arg)` → a category or None. Exact names read off `claude
  --help` (2.1.330) and `codex exec --help` (0.171.0), each with its category
  (level, hooks, config, mcp, tools, skills, dirs, prompt, session, stream,
  own, model, writes, elsewhere, exits); category **words** anywhere in a
  name (permission, dangerous, sandbox, approv, trust, hook, setting, config,
  profile, env, mcp, tool, allow, deny, plugin, skill, agent, dir, worktree,
  prompt, resume, session, fork, thread, format, stream, json, output,
  remote, cloud, background, key, token, secret, auth…), so a flag added next
  month is refused unread; **shapes**: every element a flag on its own (a
  bare word is a subcommand -- `claude mcp add`, `codex exec resume` -- or the
  request), never `--`, one short flag per element, `--no-X` judged as X, a
  prefix of a refused name refused (some parsers take abbreviations),
  ASCII names only, no control character, 200 characters, 16 flags. Read off
  `--help` and let through after a confirm: Claude's `--debug`,
  `--max-budget-usd`, `--fallback-model`, `--betas`, `--name`,
  `--autocompact`, `--ax-screen-reader`, `--max-turns`; Codex's `--color`,
  `--oss`, `--local-provider`.
- `checked()` raises `LaunchRefused` with our own sentence, which names the
  flag and never its value (a value may be a key); `failure` classifies it as
  the new kind `refused` ("Claude was not started: one of its launch settings
  is never passed. Agent details, Advanced, says which.").
- Environment: `env_judge` (exact names, prefixes, suffixes: PATH, HOME,
  USER, TMPDIR, SHELL, ENV, IFS, EDITOR, PAGER, DISPLAY, SSH_AUTH_SOCK,
  NODE_OPTIONS, CA files, `LD_*`, `PYTHON*`, `NODE_*`, `XDG_*`, `MISE_*`,
  `CLAUDE_*`, `CODEX_*`, `AGENTVOICE_*`, `OMARCHY_*`, `MCP_*`, `BASH_*`,
  `GIT_*`, `SSL_*`, `*_PROXY`, `*_BASE_URL`, `*_API_BASE`, `*_URL`,
  `*_ENDPOINT`, `*_HOST`…; case-folded). The file
  `~/.config/agentvoice/agent-env.json`: 0600 from its first byte, written
  atomically under its own lock, in a folder made 0700; never followed
  through a link; never used when another account can read it (the writer
  puts the mode right); a file that cannot be read is never overwritten (it
  holds every other agent's keys). Read by stat, so the idle poll may ask
  every time. `agents env ID list|set|unset|clear` prints names only.

**Adapters**: `extra_args`, `extra_env`, `resume` on the base, with
`_extras_argv()` and `_popen_env()`. Claude Code appends the extras at the
end of its argv (a value-flag left wanting a value takes none of ours:
claude says "argument missing" and does not start, checked against the real
CLI); Codex puts them straight after `exec` (one left wanting a value meets
`--json`, which clap refuses -- checked against the real CLI -- where before
`resume` it would eat `resume` and make the session id the request). Both
pass `env=` to Popen (None when there are no variables: inherited exactly as
before). A refusal starts no process: `prepare()` swallows it, `send()` turns
it into one error in our words, `launch_argv()` raises it so the Advanced tab
shows it where the command line would be (`runinfo._own_error`).

**The daemon** (`wake_listen.py`): `apply_launch` from `apply_extras` hands
each idle adapter its flags, its environment (read from the file), resume and
the hung-turn limit (`idle_timeout_s`, read by each turn's Watchdog); a
changed flag or variable lets the idle process go, as a tool switch does, and
logs counts only ("launch for “Sora”: 1 extra flag · 1 environment
variable"). Resume off: `answer()` sends the turn with no session (also one
put back since the last turn, by a task or a skipped open-mic turn), drops
the session when the turn ends and revokes its "allow all in this chat"; a
continued chat is replayed, not resumed. `chat-new` (Start fresh) now also
lets the agent's idle process go, revokes the old session's chat grants,
writes a `fresh` line in the log ring, and says when the agent is busy or
does not exist instead of dropping the command. `_rebuild_persona` keeps the
three new fields with the running adapter (they are not a rebuild).

**`daemon/agent_manage.py`** (new) and `agentfs.py`: Duplicate and Reset.
- `duplicate(ID)`: a new id (`<name>-<hex>`), a wake phrase `<last word>
  copy` (or second copy…), the label `<label> copy`, **switched off**;
  program, model, effort, voice, speed, narration, folder, endpoint fields,
  resume and limit copied; **level Ask, no tool switched on, no extra flag,
  no environment variable, no session, chat or replay right** (all keyed by
  the old id); every restriction kept (a tool or a skill off, notes denied,
  collaboration off or ask, work refused). `agentfs.duplicate_folder` copies
  role, personality and instructions, and each skill through `import_skill`
  (checked, beneath its folder, no link followed; one that breaks a rule is
  left out and named) -- not notes, not saved versions. Refused for a
  quarantined agent, while the quarantine list cannot be read, at eight
  agents, or with settings that cannot be read. The main agent can be copied.
- `reset(ID)`: the folder and the settings entry (as the page holds it) go
  to the trash (`agentfs.reset_folder`: trash, then a fresh folder from the
  templates; the old one put back if that fails); the entry is a new agent's
  with id, wake phrase, name and switch kept. `agentfs.undo_reset(NAME)` puts
  it back and moves the fresh folder to the trash as a folder no agent uses.
  The main agent is not reset here (it cannot go to the trash). Environment
  variables are kept: they are not in the trash, so nothing could bring them
  back.
- `AgentFolders.qml`: `duplicate`, `resetAgent`, `undoReset`, with the same
  save-then-rollback rule as remove/restore (a duplicate whose list save
  fails trashes its folder; a reset puts the old one back; an undo resets
  again); after a reset's save lands, `chats new ID` ends its conversation;
  the trash list's Restore of a reset agent goes through `unreset`.

**The orders guard** (`permission_hook.FOLDER_WORDS`): `agents duplicate`,
`reset`, `unreset` and `agents env ID set|unset|clear` are asked at every
level, Trusted included. The env file itself was already under the guard
(`CONFIG_DIR`). `agents env ID list` and `flags check` read and are not
asked. The hook's decision code is otherwise unchanged.

**Settings** (three places each): `mainResume` (bool, schema + defaults),
`mainIdleTimeoutS` (integer 30–600 step 10, schema + defaults), `mainExtraArgs`
(list, defaults only); the `voiceAgents[i]` fields `resume`, `idleTimeoutS`,
`extraArgs` read by `Config._agents()`; `Config.launch_for`. Written only on
Agent details → Advanced: the main twins by the page's `putLaunch`, an extra
agent's through the new `Settings.setAgentField` (FIELD_HOMES, OVERLAY_HOMES,
OUTSIDE_WRITERS updated). Unreadable: resume on, 90 s, no flag (settings that
cannot be read pass nothing extra).

**Preview target** `launch` (new, with `launch.seed.py`), and
`preview.sh`: `agentvoice agents env` always runs against a scratch config
folder, so no preview writes, or reads back, a real key.

**Docs**: CODEBASE (the env file, the two modules, the adapters' launch
paragraph, the settings, the CLI rows, the security list), README ("How it is
launched"), CLAUDE.md (a tenth fail-open rule: "A flag the person adds is
still a flag"), FINDINGS §51, `bin/agentvoice` help lines.

## What was proven, and how

- **Tests** (`tests/test_launch_extras.py`, 41 functions, 188 collected;
  `tests/test_agent_manage.py`, 19 functions, 34 collected; plus six
  adjusted elsewhere):
  - **Denied flags are refused at launch in every form**: the plan's list
    (`--permission-mode`, `--dangerously-skip-permissions`, `--settings`,
    `--setting-sources`, `--mcp-config`, `--strict-mcp-config`,
    `--plugin-dir`, `--allowedTools`, `--add-dir`, `--append-system-prompt*`,
    `--resume`, `--output-format`; Codex's `-c`, `--sandbox`, `--full-auto`,
    the bypass flags) and every listed name, each as `--x`, `--x=v`,
    `--x=`, upper case, swapped case, abbreviated, `--no-x`, and every short
    flag as `-x`, `-x=v`, `-X`; shapes (bare words `mcp`, `update`,
    `resume`, `exec`; `--`; clusters; spaces; Unicode; control characters;
    too long); next month's names by their words. **In the adapter**:
    `extra_args` set directly (as a setting written past the page would
    arrive), `_argv` raises, `prepare()` starts nothing, `send()` is one
    error in our words, Popen never called -- for Claude Code and Codex.
  - A **cold and a warm launch with a safe flag**: Claude's flag last on the
    line the wake word starts; the next turn writes to the same process; a
    change (what apply_launch does) lets it go and the next one carries the
    new flag. Codex's straight after `exec`, `resume ID` still last, the
    request not in argv; `launch_argv` equals what Popen got.
  - **The env denylist** (39 names refused, keys allowed); **the file is
    0600** in a private folder; a file others can read is not used and the
    writer fixes it; a link or a corrupt file is neither used nor
    overwritten; **a value is never printed** (the CLI in process and through
    `bin/agentvoice`, both streams, a canary); the environment reaches Popen
    on top of the daemon's, checked, and a denied name written past the page
    is refused at launch.
  - **Duplicate copies no grants, sessions or secrets**: the entry rules
    field by field; end to end (folder copied without notes, skill scripts
    copied, the env file has nothing for the copy, the daemon reads it as
    switched off at Ask with nothing switched on); no chat replay right or
    session; the main agent copied; a quarantined agent and an unreadable
    list refused; eight agents and unreadable settings refused; a broken
    skill left out and named; a link in the source refused.
  - **Reset round-trips with Restore**: the fresh folder, the trash entry,
    the undo bringing folder, notes, skills and the whole entry back, and the
    fresh folder in the trash as an orphan; the main agent and a wrong entry
    refused; a failed fresh folder puts the old one back; an unreadable trash
    entry is left as it is; the CLI round trip through `bin/agentvoice`.
  - **Resume off means no `--resume`**: driven turns through the real
    `answer()` (on: `[None, s1, s1]`; off: `[None, None, None]` with each
    session's grants revoked); a session set before the turn dropped; the
    Claude adapter asks no `--resume` and does not reuse the warm process;
    a continued chat replayed with resume off and resumed with it on.
  - **The timeout reaches the Watchdog** (420 s configured → the watchdog
    built with 420); an endpoint keeps its own.
  - **Three places per key**; `Config.launch_for` precedence, an extra
    agent's own entry, odd values, unreadable settings; the timeout's bounds.
  - **Start fresh** ends only that agent's conversation, lets its process
    go, revokes its grants and writes the ring line; busy and unknown are
    said.
  - The page asks the launch's judge and holds no list of its own; a value
    goes on stdin as one JSON line and is forgotten; the orders guard asks
    an agent running the new verbs at Ask and at Trusted, and not the
    reading ones; the env file is under the guard.
  - Settings homes (`test_settings_pages`), the confirm table
    (`test_confirms`: "agents reset", "agents env unset", "agents env clear"
    run only from a DangerButton's onConfirmed), and the M16 page test, now:
    the read-only rows still write nothing, and the whole tab puts settings
    only through `putLaunch`, for exactly the three keys.
- **Mutations: 29 run, 29 red, none survived** (scratch copies under /tmp,
  never the clone): the launch check skipped; Claude passing no extras;
  Codex's extras at the end; no abbreviation rule; no `--no-` rule; bare
  words passed; no category words; clusters passed; the env file's mode not
  checked; env names not checked at launch; env names not checked at set;
  the CLI printing a value; a copy keeping the level, every tool, the flags;
  a quarantined agent copied; no reset rollback; undo-reset not moving the
  fresh folder; resume's end-of-turn clear gone; its start-of-turn clear gone
  (survived the first time: no test reached it; one added, then red);
  continue resuming with resume off; the timeout not handed; Start fresh
  keeping grants, keeping the process; the orders guard missing `env`;
  runinfo hiding our words; the environment not passed to Popen; and the two
  stale-process leaks fixed in this phase.
- **Preview** (`preview.sh`, synthetic mouse events, scratch data, config and
  environment folders, the real pointer never moved): **`launch` 43 of 43
  PASS** -- a refused flag says why and cannot be added (`--dangerously-skip-
  permissions`, `--bare`); a harmless one asks, **Cancel writes nothing**,
  confirmed it is one write of `mainExtraArgs`, listed as passed, removed;
  a denied variable refused with the reason and its value out of the field;
  a key set, listed by name, drawn nowhere, in no field, not in the settings;
  **its Remove cancelled keeps it, confirmed removes it**; resume and the
  limit write the main twins; **Start fresh cancelled runs nothing,
  confirmed runs `chats new main` only**; on Sora resume and a flag go into
  her entry through setAgentField with every other field kept and the main
  twins untouched; **Duplicate** adds "Sora copy", switched off, at Ask, no
  flag, with her model, resume and restrictions (her `tools: {desktop: on}`
  not copied); **Reset cancelled resets nothing, confirmed** writes a new
  agent's entry with her name and phrase kept and runs `chats new sora`;
  **Undo** puts her back exactly; Nova (Gemini) is passed no flag and says
  why. Regressions on the same page: **`advanced` 33 of 33**, **`details` 58
  of 58**, **`tools` 29 of 29**, **`confirms`** as before (each confirm
  after a cancel; Agent details' Remove still writes only when confirmed).
- **Screenshots** (`/tmp/m17`, not committed): 520×720 dark (the crop cuts
  the overlay's right edge, as for earlier phases), 900×760 dark during the
  driven run, 900×760 flexoki-light walked down Sora's tab.
- **Live, on the installed build** (see the checklist at the end): the
  journal after the restart has no traceback; the installed `flags check`
  gives the expected verdicts for both programs; `runinfo` publishes resume
  on and 90 s for main, Sora and Jarvis; a **real `claude` process** started
  through the installed adapter code (scratch runtime folder, no daemon, no
  setting, no prompt) had `/proc/<pid>/cmdline` ending in the extra flag and
  equal to `launch_argv`, the probe variable in `/proc/<pid>/environ` and not
  in the command line; `--bare` started no process and the turn said why;
  the installed CLI's Duplicate → Reset → Undo round trip on a scratch data
  and config folder held.

## Shared files touched, and where

- `daemon/wake_listen.py` (big shared, +115): `import launch_extras`;
  `apply_extras` calls `apply_launch` (new, with `launch_for`) and lets the
  idle process go when it moved; `_rebuild_persona`'s kept fields; in
  `answer()` the start and end of a turn with resume off; `continue_chat`'s
  resume condition; the `chat-new` handler. Nothing else in the turn loop
  changed.
- `pages/AgentDetailsPage.qml` (big shared, 2,832 → 3,544): the state,
  processes and functions after M16's block; the Extra flags and Environment
  variables rows; the Conversation row, Resume, Start fresh, the limit; the
  Folder row's Duplicate and Reset with their paragraphs; the reset Undo bar;
  `resetRun` and the one `onAdvancedOpenChanged` extended.
- `daemon/agentfs.py` (big shared, +138): `duplicate_folder`, `reset_folder`,
  `undo_reset`, and the `duplicate`, `reset`, `unreset`, `flags`, `env` verbs.
- `Settings.qml` (big shared, +42): `setAgentField`.
- `daemon/permission_hook.py` (security-critical, +11): `FOLDER_WORDS` only.
- `daemon/runtime.py`, `manifest.json`, `daemon/adapters/{base,claude_code,
  codex}.py`, `daemon/runinfo.py`, `daemon/failure.py`, `AgentFolders.qml`,
  `bin/agentvoice`, `bench/preview/preview.sh`; new `daemon/launch_extras.py`,
  `daemon/agent_manage.py`, the `launch` target; tests as above.

## Measured

FINDINGS §51, on the i7-1185G7. The launch check costs 23 µs for four flags
(88 µs for sixteen) when a process starts, and the environment 221 µs; an
agent with neither pays nothing (Popen gets `env=None` as before). On the idle
poll the env file costs 23 µs from its stat cache (36 µs re-read). The page's
two CLI calls are Python processes of 243 ms median each, run only while the
tab is open and something was typed, saved or opened.

## Different from the plan, and why

- **Extra flags and environment variables are passed to Claude Code and Codex
  only.** The plan's denylist is per program and names only those two; Gemini
  is not installed here (its `--help` could not be read), and agy's and
  copilot's were not read for this list. A program without a written list is
  passed nothing, and the page says so. Open issue 2.
- **A refused flag saved past the page refuses the turn** rather than being
  dropped quietly: a control that does nothing must say why, and the spoken
  line and the Advanced tab both name it. The page itself never saves one.
- **The environment denylist is longer than the plan's** (it adds
  `CLAUDE_*` -- `CLAUDE_CODE_SIMPLE=1` is `--bare`, which skips the hook --
  `AGENTVOICE_*`, `CODEX_*`, `BASH_*`, `GIT_*`, `NODE_*`, `MISE_*`, the CA
  files, display and agent sockets, and every `*_URL`-like address), because
  each of those reaches the hook, its code or where the key goes.
- **Model and effort flags are refused** (`--model`, `--effort`, `-m`) with
  "chosen on the Agents page": not a permission boundary, but a second
  control that would make the first untrue. So are the flags Agent Voice
  passes itself (`-p`, `--verbose`, `--json`, `--approve-for-me`…).
- **Duplicate starts the copy at Ask and switched off**, with a picked wake
  phrase, and copies restrictions but no grant ("safe defaults" read as the
  stricter of the original and a new agent). Notes are not copied.
- **Reset is offered for extra agents only**: the main agent cannot go to the
  trash, so nothing could undo it. Environment variables survive a reset.
- **Start fresh reuses `chats new`**, so it is not a new destructive verb in
  `test_confirms` (the conversation view's New chat and Communal's Start
  fresh run it from a plain button); on this tab it is a DangerButton as the
  plan asks.
- **The hung-turn slider is set in the preview by emitting its `committed`
  signal**, not by a synthetic drag (the `knob` target covers dragging the
  same KnobRow).
- **The Set button has no tooltip**: the preview found that it was drawn over
  the Remove button of the variable just above.
- **Codex review bypassed** by the user's decision.

## Found along the way

- **My re-read of the Claude adapter**: when a new process could not be
  started -- now also because a launch setting was refused, before M17
  because Popen failed -- the warm process it had just let go of was never
  stopped: `prepare()` returned early past the `stop_tree`, and `_take()`
  raised past it, leaving a `claude` running unowned. Both now stop it; a
  test and two mutations hold it.
- **My re-read of the daemon**: the new "no agent to start fresh" line echoed
  an id read from the command file; it no longer echoes it (the first fix,
  through `safe_for_terminal`, was itself flagged by the speech-print audit,
  which treats that call as a sign of speech).
- **A second `onAdvancedOpenChanged`** on the page would have stopped the
  whole overlay loading (M16 hit the same with `onTargetChanged`); merged into
  the one handler before the first run.
- **qmllint reports `id.text = …` assignments made inside a Button's own
  handler** as a missing property (reads and page-level functions pass, as in
  CommunalPage); those assignments moved into page functions.
- **The first full check** found `test_crew`'s expected agent spec without
  the three new fields; updated.
- **The DangerButton's idle text is "⚠ " + its text**, which the first
  preview run's lookups missed (38 failures, all lookups).
- **The resume start-of-turn clear survived its mutation** the first time:
  the end-of-turn clear masked it. A test with a session put back before the
  turn now holds it.
- The real CLIs fail closed for a flag left wanting a value, in the places
  the extras go: `codex exec --color --json` → "a value is required for
  '--color'", `claude -p --verbose --max-budget-usd` → "argument missing".

## Not verified

- **The tab in the real shell.** It needs `omarchy-restart-shell` (not run).
  Seen only in `preview.sh` with synthetic mouse events: a real pointer, the
  keyboard (Tab through Add, Remove, Start fresh, Reset; Escape on an armed
  confirm), the slider dragged by hand, and the real overlay's store writing
  `shell.json` were not driven.
- **The plan's typed live checks, as written**, on the real daemon: "add a
  harmless flag and see it in /proc; add a denied flag and see it refused;
  reset a scratch agent, then Restore". Each writes the person's settings
  (and the denied flag would stop a real agent's turns), so none was done on
  a real agent unattended, as for M10's widening checks. Done instead: the
  `/proc` check on a real `claude` process started through the installed
  adapter code outside the daemon; the denied flag refused by that same code;
  the reset round trip with the installed CLI on scratch folders. At the next
  stop point: add `--debug` to a scratch agent on the tab, run a turn, compare
  `/proc/<pid>/cmdline` with the tab's line; add `--bare` (refused on the
  page) and, by hand in shell.json, see the turn refused and spoken; set an
  environment variable and see it in `/proc/<pid>/environ` (as the user);
  Reset a scratch agent and Restore it from the trash list.
- **Resume off and Start fresh on a real conversation**, by voice or typed.
- **Duplicate and Reset through the real overlay** (preview only).
- **Codex with extras against a real turn** (fixtures, and `codex exec
  --help` parsing only: a real Codex turn would cost a turn of the person's
  quota).
- **The installer box** (`install.sh` did not change).
- **The Codex review** (bypassed, not owed).

## Going back

`bin/agentvoice-deploy 0322b00c59f2` from the clone, `./install.sh --yes` once
the daemon is idle, then `omarchy-restart-shell`. An M16 build **ignores
`mainResume`, `mainIdleTimeoutS`, `mainExtraArgs` and the three voiceAgents
fields** (agents then run without extras, always resume and stop after 90 s)
and never reads `~/.config/agentvoice/agent-env.json` (agents run without
their variables; the file stays, 0600, holding the keys -- delete it if they
should not outlive the build). **An agent that had resume off resumes again
under M16**: if a conversation must not be carried, Start fresh it before
going back. A duplicated agent stays (an ordinary entry); a reset agent's old
self stays in the trash, where an M16 build can restore it only after the
reset one is removed (M16 has no `unreset`).

## Open issues, for the next phase

1. **Codex review bypassed** for M17 (user decision, 2026-11-22) -- a Tier A
   phase, where the plan made both passes mandatory. M12 stays "review owed".
2. **Extras for Gemini, Antigravity and Copilot?** Each needs its own list,
   read off its own `--help` (Gemini is not installed here). Default taken:
   passed none, and the page says so.
3. **Question 12, revisited**: the denylist (the default) admits any flag not
   named, worded or shaped as refused -- including flags a CLI adds tomorrow
   with an innocuous name. An allowlist of the handful read as harmless
   (`--debug`, `--max-budget-usd`, `--fallback-model`, `--betas`, `--name`,
   `--color`, `--oss`…) would be stricter. Keep the denylist?
4. **Duplicate's choices**: it starts at Ask (not the original's level),
   switched off, with a picked wake phrase, and without notes. Should a copy
   keep the original's level, or its notes (with their taint)?
5. **Reset keeps environment variables** (they are not in the trash, so
   nothing could bring them back) and is not offered for the main agent.
   Should reset clear them, and should the main agent have a folder-only
   reset (its files' saved versions undo it)?
6. **A flag in settings that the page would refuse refuses every turn** of
   that agent until removed. Dropping the bad flag and running would keep the
   agent working, quietly differently from its settings. Keep refusing?
7. **The 16-flag and 32-variable caps, 200 and 8,192 characters**: chosen,
   not asked.
8. **Carried, still open**: M16's 2–9; M15's 2–8; M14's 2–7; M13's 2–9;
   M12's 2–7; M11's 1–7; M10's 1–8; M9's 2–7; M8's 2–11; M7's 2–7; M6's 1, 3,
   4; M5's 1, 4–6; M4's 4–13; the Voice library trash icon (M25); M0's small
   test and bench fixes; agy's `carries_session_across`; the runner's sandbox
   test command.

## Live checklist: what was done, what happened

Nothing was said into the microphone and no turn was typed.
- Before the deploy: state `listening`, every agent idle, no open mic, no
  task, no turn in the journal for five minutes; `shell.json` copied (0600).
- `bin/agentvoice-deploy --install --wait 120 d7c3918`: strict check green;
  "deployed d7c3918c2528. The way back: bin/agentvoice-deploy 0322b00c59f2";
  "QML changed: run omarchy-restart-shell? (not run)"; "Build 0.2.0
  (d7c3918), replacing 0.2.0 (0322b00)". Service active.
- After: 30 journal lines since the restart, none with a traceback or an
  error (read with `-o json`); no "launch for" or environment line (no agent
  has extras, and the env file does not exist). `agents flags check claude`
  with `--debug --bare --settings={} mcp --max-budget-usd=1`: passed,
  refused (hooks), refused (config), refused (bare), passed; `codex` with
  `--color=never -c --sandbox=…`: passed, refused, refused. `agents env main
  list --json`: no names, no problem. `agents runinfo main|sora`: published,
  `resume: true`, `idle_s: 90`, no extra flag in the line, no error.
- A real `claude` (haiku) started by the installed `ClaudeCode` adapter with
  `extra_args=("--max-budget-usd=0.01",)` and a probe variable, in a scratch
  `XDG_RUNTIME_DIR`, outside the daemon, with no prompt: process running;
  `/proc/<pid>/cmdline` ended with the flag and equalled `launch_argv`; the
  probe in `/proc/<pid>/environ`, not in the command line; stopped by
  `cancel()` (gone a few seconds later; no process left). `--bare`: no
  process; the turn's error "Agent Voice did not start it: its extra flag
  --bare is never passed: it changes or skips hooks…".
- The installed CLI on scratch folders (`agents8.json` as settings): a copy
  of Sora at Ask, switched off, no tools, no flags; Reset gave a new agent's
  entry and an empty role; `unreset` gave back her model, notes switch and
  unknown field, and her role text; the fresh folder in the trash as an
  orphan.
- `shell.json` byte-identical to the copy afterwards. No shell restart.
