# Phase M16: Agent details Advanced: what is running

Written 2026-11-22, unattended (started by the runner script). Branch
`phase-m16`, cut from `phase-m15` at 0274831. Result commit: the notes commit
on top of 0322b00, pushed to `fork/phase-m16` only; `dev` fast-forwarded to it
and pushed to `fork`. Model: Claude Opus 5.5 (tier B in the plan).

Commits:
- cc1845e: the phase;
- ba46488: the chat-grant test left bytecode in the clone (`python -I` ignores
  `PYTHONDONTWRITEBYTECODE`; the bare-runner check's last line caught it);
- 154bcf4: the `advanced` preview target switches agents through `goTo()`
  (the deploy's strict check caught an unresolved `detailsAgent`);
- 0322b00: what each agent runs is published after its prompt parts are
  handed over (found on the installed build, below);
- then these notes.

**Codex review: bypassed (user decision, 2026-11-22).** Codex was not run, for
review or anything else. In its place I re-read the whole diff before the
final commits; what that found is under "Found along the way". Nothing in this
phase has been reviewed by a second model.

Deployed: **yes**, twice, both through `bin/agentvoice-deploy --install` (its
strict check green each time). First 154bcf4, replacing M15's bf3945d, with the
daemon idle (state `off` at the moment of the check, every agent idle, no open
mic, no task). Then 0322b00, replacing 154bcf4, after I waited for three
minutes with no turn in the journal (somebody was using Agent Voice in
between; see Live checklist). **The way back to before M16 is
`bin/agentvoice-deploy bf3945d115f9`** (see "Going back").

Installed: **yes**: "Build 0.2.0 (0322b00), replacing 0.2.0 (154bcf4)". The
daemon, the adapters, the hook and the CLI changed. `install.sh` did not.

**Shell restart needed** (`pages/AgentDetailsPage.qml`, `ui/PromptPreview.qml`).
Not run. Until it is, the running shell has M15's Agent details: its Advanced
tab shows only the id, the folder and the trash. Nothing is broken meanwhile:
the daemon publishes `runinfo.json` and the hook writes its audit lines whether
or not anything reads them.

A copy of `shell.json` was taken before the first deploy
(`~/agentvoice-notes/shell.json.before-M16`, 0600); after both installs and the
live checks it was byte-identical. No live check wrote a setting, a file in an
agent folder, or anything else of the person's.

`./bin/agentvoice-check`: green on the final tree (exit 0, every line ok).
- **4401 tests** (was 4330; +71), 14 of 14 static checks, "the check wrote
  nothing in the tree: ok".
- Bare-runner variant (`AGENTVOICE_STRICT=1`, a venv with only
  requirements-dev): **green** on the final tree, 4385 passed, 9 skipped (the
  same numpy-only skips as M15).
- Box: not run (`install.sh` did not change).
- **Not every intermediate commit was proven green before it was made**, and I
  will not claim it: on cc1845e the check was green before the commit, but it
  lints only tracked QML, so the new preview target was not linted until it was
  committed; and for the two runs after that I read only the last lines of the
  output and not the exit status. The deploy's own strict check then failed on
  that target (nothing was deployed), which is how 154bcf4 came about. From
  154bcf4 on, each run was read in full with its exit status.

## What was built

**Agent details → Advanced: what is running** (read only; the plan's "nothing
here changes anything"). For the agent picked, above the existing id, folder
and trash:
- **Command line**: the exact line its next turn starts and, beside it, the
  last one it really started, with the process id and whether it still runs
  ("with the same line", or the other line drawn too). Built by the adapter's
  own `_argv` (below), so it is what runs. The page says how the request
  reaches the process (stdin), that nothing said is ever in a command line,
  that instructions travel in a private file named by its path, and that
  anything key-shaped is shown as •••. Codex refusing to start (its
  config.toml unreadable, a server `-c` cannot name) is shown in its own words;
  an endpoint says "No process: each turn is an HTTPS request to HOST, model
  M" (the host only: no path, query or password).
- **Working directory**, with "Change on Agents page →".
- **Conversation**: the session id, that its next turn resumes it, and how
  many turns it has had since the service started; or "starts fresh every
  turn"; or, for an endpoint, how many turns it keeps and sends.
- **Timeouts**: the hung-turn limit (90 s) and, for Claude Code, how long its
  process waits between turns (5 minutes), "Fixed in this version" (M17 adds
  the control); an endpoint's links to the Agents page, where it is set.
- **MCP servers**: each server it is *given* (Agent Voice's own, found on this
  machine, Claude in Chrome; Codex's config.toml servers started switched off)
  kept apart from what its program *said it started* (Claude Code's init event,
  M10's `tools/live.json`): "github · found on this machine · given · said it
  started: failed". A server it said it started and is not given now is listed
  too. The page says only Claude Code reports.
- **What it is sent**: the whole prompt from `agents prompt` (M15: the adapter's
  own builder, in send order, each piece with its source, precedence and size),
  in a `PromptPreview` that is now `concealed`: each piece's text is drawn only
  after its own **Show**, or **Show all** (the plan's "full content only on a
  deliberate reveal").
- **Recent log**: the agent's last twelve structural lines, newest first ("turn
  41.0s · warm start · first token 900 ms · tools: Bash ×6, Edit ·
  mcp__github__list_issues", "started again for a new level · conversation
  kept", "conversation dropped after a failure (too_long)"), and **Open full
  log**, which hands Omarchy's floating terminal one constant command,
  `journalctl --user -u agentvoice -n 300 -f`.
- **Recent permission decisions**: time, tool name, allowed or refused, how
  ("you were asked", "nobody answered", "without asking", "by its level", "by
  “allow all in this chat”", "the hook failed") and the level. The page says
  only Claude Code agents run the hook.

The tab reads `agentvoice agents runinfo ID --json` every 5 s and `agents
prompt` on opening and after a change, **only while the overlay is open on that
tab** (each read is a Python process; FINDINGS §50). Every new Text is
`PlainText`; nothing on the tab writes a setting.

**`daemon/runinfo.py`** (new):
- `redact_argv`: the value after a secret-named, header or environment flag; a
  `--flag=value` of one; a `-c key=value` whose key's last part names a secret
  or carries one (`env`, `headers`; not `env_vars`, a list of names); a
  generated-looking word; a known key prefix (ghp_, sk-…, with a digit after)
  anywhere in a word; a bearer token; a URL's password and query. The session
  id is not masked, and a flag right after a flag is never swallowed (so
  `--no-session-persistence` leaves the next flag alone). Leans wide: a masked
  word costs a word.
- `Ring`: the daemon's per-agent log ring (40 lines). `add` types every field
  (a kind from a fixed list; seconds; a tool's name by pattern, else "?"; a
  failure kind from `failure.KINDS`, else "unknown"; the `sessions` change
  vocabulary; booleans), so no sentence fits anywhere, with `logSpeech` on or
  off; `render` builds the words from those fields alone. `count_turn` counts
  turns per session.
- `record_for`: one adapter's record (next line, last line, cwd, session,
  timeouts, endpoint host, servers given, the request channel). A busy agent's
  next line is not rebuilt (its turn's thread owns the adapter; a concurrent
  `_argv` could race the turn's own on the prompt file's temporary name).
- `write`/`read` of `$RUNDIR/runinfo.json` (0600, atomic). A file whose
  daemon pid is not the live pidfile's is ignored: a dead daemon's record says
  nothing true.
- `view`/`cli`: `agentvoice agents runinfo ID [--json]`: the published record,
  given-vs-seen servers, and the agent's permission lines from the **end** of
  the audit log and its archive (256 KB each). It says when the service is not
  running, or running but not publishing (an older build, or starting).

**Adapters** (`daemon/adapters/`): `launch_argv(session_id)` on the base is the
adapter's own `_argv("", session_id)`; Gemini's and the shared CLI adapter's
argv were split out of `send()` into `_argv` for it (the CLI adapter shows
`<the prompt>` where a template would put it; copilot's has no slot). Every
adapter notes the argv it handed Popen (`_launched` → `last_launch`: argv, pid,
time), `launch_running()`, `handed_servers()` (Claude: the same conditions as
`_argv`; Codex: its own, the config.toml servers on as approved, the rest off)
and `prompt_channel`.

**The daemon** (`wake_listen.py`): `agent_ring`; one `turn` line at the end of
each turn (seconds, first token, warm/cold, the tool names the stream named,
the failure kind, stopped, for another agent), `rebuilt` where an adapter is
rebuilt for a changed level/model/program/folder (with whether the
conversation was kept), `dropped` where a failure ends the conversation; turns
counted per session. `publish_runinfo` runs **last in the idle poll** (after
`reconcile_parts`), rebuilds when something visible moved and at most every
10 s otherwise, and writes only when the record changed. Both are inside their
own catch: a page is never worth a turn.

**The hook** (`permission_hook.py`, security-critical): one audit line of the
new kind `permission` per decision that is not simply a free tool: the agent
(`main` or its id), the tool's name, allow or deny, how (`_HOW`, set by
`_by()` where `decide()` allows on the level or a chat grant, and by `_ask()`
on an answer or none; "refused" for a deny reached without asking; "failed"
when the hook itself failed), and the level. Never the arguments, never a path.
Order in `main()`: decide, emit, **flush**, and only then `_record_decision`,
outside the main catch and inside its own (`BaseException`), so nothing in the
record can become a second answer; the lock is given up after 0.5 s; the level
is read only when `decide()` had already loaded the settings code or a person
was asked (on a chat-grant path reading it would cost ~40 ms a call).
`decide()`'s outcomes are unchanged: the only edit to a condition is
`granted(session) or level == "trusted"` for the clipboard read, split into
two ifs with the same result.

**Audit** (`audit.py`): kind `permission`; fields `tool` (by pattern),
`decision`, `how`, `level` (each from a fixed list, else "?"); `wait_s`, which
gives up on the lock instead of waiting (every other caller still waits).

**Preview target** `advanced` (synthetic `advanced.run.json` as the daemon's
published record for a Claude, a Codex and an endpoint agent; `advanced.seed.py`
for folders holding a made-up word and audit lines), and `preview.sh`: a
target's `TARGET.run.json` becomes the scratch runtime folder's `runinfo.json`
and `tools/live.json`, naming the script's own pid as the daemon.

**Docs**: CODEBASE (runinfo.py, the adapter methods, the hook's record,
audit's kind, `runinfo.json`, the page, the CLI row), README ("What is
running"), CLAUDE.md (the first fail-open rule now says the audit line comes
after the decision and inside its own catch), FINDINGS §50.

## What was proven, and how

- **Tests** (`tests/test_runinfo.py`, 71 collected from 37 functions, plus three adjusted elsewhere):
  - **runinfo equals the adapter's argv, with no user text**, for Claude Code,
    Codex, Gemini, Antigravity and Copilot (a canary in the instructions, the
    folder pieces and the request is in no element); for Codex, Gemini,
    Antigravity and Copilot **the very list Popen received** is the recorded
    last launch and equals the next line; Claude's `_spawn` records the line
    it started (with `--resume`); an endpoint has no line and shows its host
    only; Codex's refusal in its own words; a busy agent keeps its line; the
    servers given follow `_argv`'s conditions (Claude, and Codex's switched-off
    config.toml server).
  - **The hook decides the same when its audit write raises**: six payloads
    (silence, a Trusted allow, a free Read, a refusal, malformed input, the
    wrong shape) × three failures (an exception, `SystemExit`,
    `KeyboardInterrupt`): identical exit status and stdout, exactly one
    decision on stdout; **silence still denies** with the record raising; a
    held audit lock (in a real hook process, so a blocking lock fails the test
    rather than hanging it) leaves the decision as it was; a SIGTERM during the
    record leaves the allow on stdout, once.
  - **Permission lines hold no arguments**: a canary in a command is not in the
    log; the line has only `at kind from to tool decision how level`; an
    extra agent's hook records its id; fields outside their lists become "?";
    `_record_decision` is handed exactly three plain names (parsed); `_HOW` is
    read only in `main()` (parsed); the existing AST walk over every
    `audit.record` call (test_notes) covers the new call, with its five names
    added to the safe list; a free tool writes nothing; each "how" is reached
    (asked and allowed, asked and denied, nobody answered, the chat grant,
    refused, the hook failing); a chat grant does not import the settings code
    (a fresh interpreter, as Claude Code starts the hook).
  - **Two agents on one backend are told apart**: a main and an extra Claude
    agent through the daemon's own `publish_runinfo`: separate records, each
    hook command naming its agent, separate working directories, sessions,
    rings and decisions.
  - **A synthetic secret in a launch line is redacted**: eleven shapes, and
    what must stay (session id, `env_vars`, a skill named `sk-…`, prompt-file
    and plugin paths, a flag after `--no-session-persistence`); end to end, a
    key in a real Codex adapter's line is in neither the published file (0600)
    nor the CLI's JSON or text.
  - **The ring takes no text**: a sentence as the kind, tool names with spaces,
    the reply as an error, a made-up change: all refused to "?"/"unknown";
    rendering; bounded; per-session turn counts; every `agent_ring.add` call in
    the daemon reads only names from a safe list (parsed); **a driven turn**
    through the real `answer()` with a tool, a sentence holding the canary and
    a usage-limit failure leaves one line with the numbers and kinds and none
    of the words.
  - The view keeps given apart from seen; a dead daemon's file is ignored;
    decisions come from the end of the log and its archive; an agent that is
    not there is refused; the page's new part is all `PlainText`, calls only
    `agents runinfo`/`agents prompt` and the constant terminal command, writes
    nothing (read, not run); the publish happens after the prompt parts are
    handed over, by order and **driven** (`catch_up()` on a daemon with a
    linked agent: the published line's prompt file is the turn's preamble,
    roster included).
- **Mutations: 27 run, 26 red, 1 survived (equivalent)** (scratch copies under
  /tmp, never the clone): the record unguarded; the record before the decision
  inside the catch; no lock budget (**hung** the first time, because that test
  ran in-process; rewritten to a real hook process, then red); the level always
  read; the chat path unmarked (**survived** the first time: no test reached a
  grant; one added, then red); "asked" unmarked; tool and how unvalidated in
  audit; no key prefixes; `-c` keys not checked; secret flags not hidden; the
  session id masked; the argv unredacted; ring tools, error and kind
  unvalidated; a dead daemon's file believed; given and seen merged; Claude
  recording another line; Codex recording none; main keyed by its empty id; no
  turn line; the reply put into the ring; the busy guard skipped; the publish
  before the parts (both new tests red); and, through the preview, the prompt
  never concealed (two checks red). The survivor: `launch_argv` handing
  `_argv` the instructions as its text, which changes nothing because no
  `_argv` reads its text argument, which is the property itself (the
  first test would fail if one began to).
- **Preview** (`preview.sh`, synthetic mouse events, real CLI, scratch data,
  runtime and settings, the real pointer never moved): **`advanced` 33 of 33
  PASS**: the drawn line is the published one, its session, the last launch
  "still running, with the same line", the conversation, the working
  directory, the timeouts, github given and failed to start, the notes server,
  a log line, a rebuild, three decisions; the prompt read and its made-up word
  **not drawn until Show all**, drawn after, hidden by Hide all, and one
  piece's own Show draws that piece only; Open full log hands the terminal
  journalctl and nothing else; Hazel's line is Codex's, its config.toml server
  started switched off, no "said it started" claimed, its own decision and not
  main's; the endpoint has no process and says where it goes, keeps turns, and
  links its timeout to the Agents page; no setting written. Regressions on the
  same page: **`details` 58 of 58**, **`tools` 29 of 29**.
- **Screenshots** (`/tmp/m16`, not committed): 520×720 dark (the crop cuts the
  overlay's right edge, as for earlier phases), 900×760 dark walked to the
  bottom (log, decisions, folder), 900×760 flexoki-light with Show all.
- **Live, on the installed daemon** (read-only): see the checklist at the end.
  The page's command line for main **equals `/proc/1027841/cmdline` of the
  running `claude` process, element for element (24 elements, the same pid)**;
  after the second install the published next line's prompt file is
  **byte-identical to `agents prompt main`** (1,301 characters, roster
  included); the ring holds the real turns as numbers and tool names.

## Shared files touched, and where

- `daemon/wake_listen.py` (big shared, +87 lines): `import runinfo`; the ring and
  publish state in `__init__`; `rebuilt` lines after `carry_session` in
  `reconcile_agent` and `_rebuild_persona`; `publish_runinfo` /
  `_publish_runinfo` and the call at the end of `catch_up()`; in `answer()`:
  `tools_seen`, the `dropped` line, the `turn` line and count. Nothing else in
  the turn loop changed.
- `pages/AgentDetailsPage.qml` (big shared, 2,330 → 2,832): the Advanced
  sections, their two Processes and timer, `resetRun()` from the page's one
  `onTargetChanged`.
- `daemon/permission_hook.py` (security-critical, +85 lines): `_HOW`/`_by`, the
  marks in `decide()`/`_ask()`, `_record_decision`, `main()`'s order.
- `daemon/agentfs.py` (big shared, +7): the `runinfo` verb.
- `daemon/audit.py`, `daemon/adapters/` (base, claude_code, codex, gemini,
  antigravity, cli_agent), new `daemon/runinfo.py`, `ui/PromptPreview.qml`,
  `bin/agentvoice` (help lines), `bench/preview/preview.sh`, the new target
  files; `tests/test_notes.py` (safe names), `tests/test_voice_download.py`
  (below). `Settings.qml`, `manifest.json` and `runtime.py` were not touched:
  **no new setting** (the plan: "Settings. None").

## Measured

FINDINGS §50, on the i7-1185G7. A recorded decision costs the hook 1.6 ms
median after a level read, about 1 ms on a chat-grant path; a whole hook
process on a refused call went from 142–143 ms (M15) to 146–147 ms; a free
tool pays nothing. A record rebuild for a Claude and a Codex agent: 2.6 ms
median, 3.5 ms p95. `agents runinfo` as a process: 206 ms median with a
published record (293 ms without), read every 5 s only while the tab is
open: about 4% of a core while somebody looks, nothing otherwise. Reading the
decisions from two full 1 MB audit files: 87 ms whole, 1.2 ms from the tails.

## Different from the plan, and why

- **The command line comes from the daemon, not from a CLI that rebuilds the
  adapter.** The plan says runinfo is "built by the same function the adapter
  uses". Rebuilding an adapter in a second process would mean reproducing
  everything the daemon hands it (tools, servers, skills, parts) — a second
  copy of the logic. The daemon instead asks its live adapters for
  `launch_argv()` (their own `_argv`) and publishes the result; the CLI reads
  that. When the service is not running there is no line, and the page says
  so: nothing is launched then.
- **The last launch is shown beside the next one**, the argv Popen really
  received, so the `/proc` check has something exact to compare with.
- **Decisions are recorded for every decision that is not simply free**, not
  for free reads (Read without a secret, TodoWrite, the notes reads, Agent
  Voice's own skill): those are thousands a day and would push the note and
  collaboration lines out of a 1 MB log. Open issue 3.
- **The level is left out on a chat-grant path** (measured cost, above).
- **The prompt comes from `agents prompt`** (M15's builder), not the Phase 12
  `agents preview` the Personality tab still uses (M15 open issue 4).
- **Timeouts are shown, not linked, where nothing can change them yet** ("Fixed
  in this version"); M17 adds the hung-turn control.
- **Two launcher tests were refined**: `test_every_launcher_argument_is_quoted`
  now also accepts a constant command line with no shell metacharacter (Open
  full log's), and the installer-flags test looks only at launcher calls that
  run the installer. Neither loosens what they protect: an interpolated value
  still needs `shq`, and every installer call is still checked.
- **Codex review bypassed** by the user's decision.

## Found along the way

- **On the installed build, the first published line lacked the roster**: the
  record was built in `reconcile_extras`, before `reconcile_parts` gave the
  main agent its parts, and a turn that started then kept that line (a busy
  agent's is not rebuilt). The page showed a 1,048-character prompt file while
  the running process had the 1,301-character one. The publish now runs last
  in `catch_up()`; fixed in 0322b00, re-deployed, and confirmed byte-identical.
- **Recording the level cost an "allow all in this chat" call ~43 ms**
  (importing the settings code, which that path never needs): measured, then
  read only when cheap.
- **Reading the decisions parsed the whole audit log** (87 ms at its rotation
  size, every 5 s): now the tails.
- **My re-read of the hook**: the decision is now flushed before the record, so
  a hook killed outright (SIGKILL, which no handler sees) while writing the line
  has already handed its decision over.
- **My re-read of the daemon**: the turn-end ring calls had no guard of their
  own (now one: a page is never worth a turn); "started again for a new
  settings" when nothing named changed (now "started again"); an unused
  "changed on" table in the view (removed).
- **Two mutations survived or hung** (above): a test added for the chat grant,
  and the lock test moved into a real hook process.
- **A second `onTargetChanged` on the page** ("Property value set multiple
  times", the whole overlay failed to load) was found by the first preview run,
  not by the check: qmllint does not report it. Merged into the page's one
  handler.
- **`publish_runinfo` assumed real Persona objects**: test_agentvoice_skill's
  stand-ins have no `session_id`. It now reads with defaults and is inside its
  own catch.
- **The hook's `_named()` reads `sys.argv[2]`**, which under pytest is pytest's
  own argument: the tests set the hook's argv as Claude Code does.
- **A Daemon built by an earlier test leaves a pidfile naming the test
  process**, which made one test's first assertion order-dependent.
- **`python -I` ignores `PYTHONDONTWRITEBYTECODE`**: the chat-grant test wrote
  `daemon/__pycache__`; the bare-runner check's last line caught it (`-B`).
- **The check's qmllint step lints tracked files only**, so a new QML file is
  not linted until committed; the deploy's strict check caught
  `overlay.detailsAgent` in the new target. Worth knowing for every phase that
  adds a target.
- **My nested helper named `main`** inside `_publish_runinfo` broke a test that
  finds the daemon's `def main(` by text; renamed `is_main`.

## Not verified

- **The tab in the real shell.** It needs `omarchy-restart-shell` (not run).
  Seen only in `preview.sh` with synthetic mouse events: a real pointer, the
  keyboard (Tab to Show, Show all, Open full log, Change on Agents page), and
  the 5 s refresh over a long session were not driven.
- **Open full log opening a real terminal**: only logged by the preview's stub.
- **The plan's typed live check, as written** ("sample `/proc/<pid>/cmdline`
  during a turn; it equals the shown line and holds no user text"): **done for
  a running process, not during a turn I typed.** No turn was typed (as in
  every earlier phase). The process sampled was main's warm `claude`, started
  by the daemon for somebody's own turn (they were using it); its cmdline
  equalled the shown last line exactly, and holds only flags, paths and Agent
  Voice's settings JSON. That no request text is in it rests on the tests (a
  canary through every adapter, and Popen's own argv recorded) and on the
  design (stdin since the marketplace review), not on a canary said live.
- **Codex, Gemini, Antigravity and Copilot lines against a real process**: only
  Claude's was compared live (no other agent ran a turn while I watched).
  Hazel's (Codex) next line was read live and looked right.
- **A permission line from a real decision**: none was written while I
  watched. Main is at Trusted, where the hook runs only for Bash, edits and the
  browser, and the turns seen used ToolSearch and the crew tools. At the next
  stop point: let an agent below Trusted run a command, answer the card, and
  look at Recent permission decisions.
- **The endpoint variant on a real endpoint** (preview only).
- **The installer box** (`install.sh` did not change).
- **The Codex review** (bypassed, not owed).

## Going back

`bin/agentvoice-deploy bf3945d115f9` from the clone, `./install.sh --yes` once
the daemon is idle, then `omarchy-restart-shell`. An M15 build **ignores the
`permission` audit kind**: its hook writes none, and nothing it has reads them;
the lines already in `audit.log` stay (each is about 130 bytes, and the log
rotates at 1 MB as before). `$RUNDIR/runinfo.json` is left behind unread (tmpfs:
gone at logout). An M15 page's Advanced tab is the id, folder and trash again.
Nothing to undo in the settings: M16 added none.

## Open issues, for the next phase

1. **Codex review bypassed** for M16 (user decision, 2026-11-22). M12 stays
   "review owed".
2. **The deploy script's idle test** (`state` in listening/off/locked, every
   agent idle, no running task) does not consider a follow-up window or a
   conversation in progress: an install between two turns of somebody's
   conversation would restart the daemon under them. I waited for three
   minutes with no turn in the journal before the second install. Should
   `agentvoice-deploy` wait for quiet itself (no turn for N seconds, no open
   mic)?
3. **Free tools are not recorded** (reads, TodoWrite, the notes reads). Should
   the list show them too, perhaps counted rather than listed?
4. **Only Claude Code's hook records decisions.** Codex's desktop and notes
   servers ask cards through their own `--guard` and write no `permission`
   line. Record those too?
5. **The level is omitted on a chat-grant line** (40 ms otherwise). Enough?
6. **The tab polls a Python process every 5 s while open** (~0.2 s CPU each).
   The daemon could push the record through the state file instead. Worth it?
7. **The Personality tab's preview is still Phase 12's `agents preview`**,
   whose roster ignores the crew links; Advanced uses `agents prompt`. M15's
   open issue 4, still open.
8. **The ring lives in the daemon's memory**: a restart (every install) empties
   it. The journal keeps the same lines. Persist it?
9. **The check now takes five to six minutes** on this machine (CLAUDE.md still
   says about two and a half). Not changed here.
10. **Carried, still open**: M15's 2–8; M14's 2–7; M13's 2–9; M12's 2–7; M11's
    1–7; M10's 1–8; M9's 2–7; M8's 2–11; M7's 2–7; M6's 1, 3, 4; M5's 1, 4–6;
    M4's 4–13; the Voice library trash icon (M25); M0's small test and bench
    fixes; agy's `carries_session_across`; the runner's sandbox test command.

## Live checklist: what was done, what happened

Nothing was said into the microphone and no turn was typed.
- Before the first deploy: state `off`, every agent idle, no open mic, no task;
  `shell.json` copied (0600).
- `bin/agentvoice-deploy --install 154bcf4`: the first attempt (ba46488)
  stopped at its strict check (the preview target's `detailsAgent`), "nothing
  was deployed". Then: "deployed 154bcf4def30. The way back:
  bin/agentvoice-deploy bf3945d115f9"; "QML changed: run
  omarchy-restart-shell? (not run)"; "Build 0.2.0 (154bcf4), replacing 0.2.0
  (bf3945d)". The service came back active and wrote `runinfo.json` (0600).
- Somebody then used Agent Voice (turns in the journal; states capture,
  thinking, speaking). From then on I only read: `agents runinfo` for main,
  sora and jarvis-ajc; main's `/proc/1027841/cmdline` against the shown last
  line (equal, 24 elements); the published next line's prompt file against the
  running one's (1,048 against 1,301 characters, by piece header only: the
  roster was missing, the bug fixed in 0322b00); the audit log's permission
  lines by shape (none yet); the ring (five real turns, numbers and tool names
  only).
- Waited until three minutes passed with no turn in the journal, state
  `listening`, every agent idle, no open mic. `bin/agentvoice-deploy --install
  --wait 60 0322b00`: "deployed 0322b00c59f2. The way back:
  bin/agentvoice-deploy 154bcf4def30"; "Build 0.2.0 (0322b00), replacing 0.2.0
  (154bcf4)".
- After: the service active; main's published next line's prompt file
  byte-identical to `agents prompt main` (1,301 characters: style, CLIs,
  roster); Sora's and Hazel's lines readable, nothing masked in either (no
  secret in them); `shell.json` byte-identical to the copy; 27 journal lines
  since the restart, none with a traceback (read with `-o json`). No shell
  restart.
