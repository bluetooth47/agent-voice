# Phase M6: Agent details: agent tabs, personality and instructions (items 9, 10)

Written 2026-11-22, unattended (started by the runner script). Branch
`phase-m6`, cut from `phase-m5` at 6bc943f. Result commit: the notes commit
on top of c4c67f9, pushed to `fork/phase-m6` only; `dev` fast-forwarded to
c4c67f9 and pushed to `fork` (it moves to the notes commit with them).
Model: Claude Opus 5.5, high.

Commits: fa40d42 (the phase), 98953fd (Codex pass 1 fixes), c4c67f9 (Codex
pass 2 fixes), then these notes.

Deployed: **yes**, c4c67f9 through `bin/agentvoice-deploy --install` (its
strict check green, 3312 tests). It replaced 314d726; the way back is
`bin/agentvoice-deploy 314d7264cfe5`. Installed: **yes**. The daemon,
`bin/agentvoice` and the Claude adapter changed, so the running daemon had
to be replaced for Try it to work. Before the deploy every agent was idle
(state `listening`, main, sora and jarvis-ajc idle, no open mic). The
installer reported "Build 0.2.0 (c4c67f9), replacing 0.2.0 (72c9589)".
**Shell restart needed** to see the page (QML). Not run: the next stop point
is after M9.

A copy of `shell.json` was taken before the deploy
(`~/agentvoice-notes/shell.json.before-M6`, mode 0600). After the deploy and
install it was byte-identical to the live file.

`./bin/agentvoice-check`: green on c4c67f9, **3312 tests** (was 3216; +96),
14 of 14 static checks, "the check wrote nothing in the tree: ok". The
bare-runner variant (`AGENTVOICE_STRICT=1`, a venv with only
requirements-dev) was green on fa40d42: 3279 passed, 9 skipped (the existing
numpy skips). It was not rerun on the two fix commits; they add no
dependency. Box: not run (`install.sh` did not change).

## What was built

**Item 9: agent tabs.** `AgentTabs` (from M1) replace the drop-down on Agent
details:
- one tab per agent, main first, each with its state dot and a tooltip;
- keyed by the agent's id, so a rename changes the label and keeps the
  selection (checked in the preview);
- `current` is bound to the page's agent and a pick only asks the overlay,
  so a removed agent's tab can never stay chosen (the Phase 12 drop-down
  bug cannot come back);
- the deep link `{page, agent, tab}` is unchanged.

**Item 10, on the Personality & instructions tab:**

- **Trait chips.** Three rows: tone (warm / dry / playful), length
  (brief / detailed), formality (casual / formal). They write one managed
  line at the top of `personality.md`, `Traits: warm, brief, casual.`, and
  read it back. The new module `daemon/traits.py` does it:
  - pure functions `parse` and `apply`;
  - the line goes after any leading comment. `agentfs.clean` strips a
    comment only while it leads the file, so a line above the template's
    comment would have pushed the comment into what the agent is told;
  - free text comes back byte for byte;
  - unknown hand-typed values are kept exactly as typed, duplicates
    included;
  - a category holds one value;
  - clearing every chip removes the line.

  The page does not write the file itself. It runs `agentvoice agents
  traits apply` on the text in the personality box (JSON on stdin) and saves
  the result through that box's `FileEditor`. So `personality.md` still has
  one writer in the overlay, with its `--base` stamp check, "Keep mine" and
  "Reload". A result for text or a stamp that changed while it ran is
  dropped, not saved. `agents traits get ID` and `agents traits set ID
  [--base STAMP]` exist for scripts and the plan's CLI. `set` writes on the
  stamp it was given, or on the stamp it read.
- **One-line hints.** Each box has a `Hint` (one line, the detail in a
  tooltip). This replaces the SettingRow paragraphs on this tab.
- **Starter templates.** They are offered when a box is read, empty and
  not being typed in:
  - 4 for role, 4 for personality, 3 for instructions, in
    `daemon/templates/{role,personality,instructions}/`. The first line of
    each file is a label comment;
  - `agentfs.starters()` and `agentvoice agents templates` read them, and
    leave out one that is unreadable, unlabelled or over its budget;
  - a starter is put in the box and saved like typing (`FileEditor.fill`).
- **Meters.** A `BudgetMeter` under each box (a thin bar and "used /
  limit": plain, the accent from 85%, urgent past the budget, with how much
  over). It counts what the agent is actually told:
  - `FileEditor.sentChars` is `agentfs.clean` in JavaScript, with Python's
    idea of whitespace;
  - a test runs it in node against `clean()` on a 21-string corpus;
  - the editor's save refuses an over-budget text by the same count. It
    used to count raw characters.
- **Try it** (`agentvoice try AGENT`):
  - The page sends the draft, meaning what is in the personality and
    instructions boxes now, saved or not, on stdin as one JSON line.
    `bin/agentvoice` refuses at once when the service is off or the screen
    is locked, then hands over to `daemon/try_it.py client`. That writes
    the request to `$RUNDIR/try/<id>.req` (0600, in a 0700 folder) and
    waits for `<id>.status`.
  - The daemon reads requests from the run loop between captures
    (`take_try`, `handle_try`). It refuses with the reason when:
    - the screen is locked, or the lock cannot be told;
    - the microphone is lent to a call;
    - the request is stale or the agent is unknown;
    - the agent has no program, or its program cannot start with no tools;
    - any agent is busy;
    - the last try was under 10 s ago.
  - Otherwise it builds a throwaway adapter (`try_adapter`):
    - level ask, with `no_tools`. For Claude Code that is `--tools ""
      --strict-mcp-config`, proven on one recorded real turn
      (`tests/fixtures/try/claude-no-tools.json`: no tools and no MCP
      servers at start, none used when asked to list files);
    - none of the desktop, browser, notes or collaboration tools;
    - no skills, no session kept, and the draft in place of the saved text.
  - It takes the first sentence, asks the lock again, and says the sentence
    in the agent's voice. It speaks while the microphone is muted, as a
    typed turn does, and never while the screen is locked.
  - It is never saved to a chat and never shown on the readout. The journal
    gets the time taken and the length, never the words.
  - The page shows "Said: “…”" or "Not tried: why", and waits 10 s before
    allowing another press. Where Try it cannot run, it says why before the
    press.
- `Adapter.no_tools` (base) is the switch. Only Claude Code reads it.

**Settings.** None.

**Tests.** Two new files:
- `tests/test_personality.py`:
  - the traits round trip on 9 kinds of free text, byte for byte;
  - the line placed after the starter comment, and its fixed order;
  - unknown values kept as typed;
  - a long paragraph starting with "Traits:" is left alone;
  - the budget counts the line;
  - `traits set` on its stamp, refused on a stale stamp after an outside
    write, refused on a write landing between its own read and write,
    refused on a file it could read only in part;
  - a whole read stamped by its own size;
  - bad input gives words, not a traceback;
  - the choices never travel in argv;
  - the starters exist and fit their budgets, and broken ones are left out;
  - the meter in node against `clean()`;
  - the tabs, the chips through the editor, Try it on stdin.
- `tests/test_try_it.py`:
  - every refusal, the lock first;
  - the request cleaned and cut to its budgets;
  - `take` and `answer` (private files, stale requests marked, old answers
    cleared);
  - the first sentence (with "J. Smith", a stall after "Hi! ", a tool);
  - the client against a scripted daemon: said, refused, not picked up,
    bad draft;
  - the CLI's own refusals;
  - the daemon's half with a stub side turn. It says one sentence while
    muted and puts no words in the journal. Locked, lent out, busy, a
    second try within 10 s, unknown or stale: nothing is built or sent. A
    lock or "cannot tell" arriving mid-turn means nothing is said. A
    backend without no-tools is refused. Cancel comes before close;
  - the safe adapter build;
  - Claude's argv with no_tools, the draft absent from it and present in
    the private prompt file;
  - the recorded turn's flags still in today's argv.

Existing tests changed: `test_agent_pages` (the picker is now AgentTabs, and
the save check counts sent characters) and `test_cli` (the usage line names
`try`). The speech audit caught the first version of the try log line, which
read `sentence`, though only for its length. It now reads a local `size`.

**Mutations: 29, all red.** 14 on the phase, 10 on pass 1's fixes, 5 on
pass 2's. One of pass 2's first passed: it deduplicated in `line()`, not
where the bug was. Re-aimed at `parse()`, it went red. They covered:
- each refusal: locked, lock unknown, the rate limit, busy, the backend;
- `no_tools`, `--strict-mcp-config`, the crew tools under no_tools, level
  ask;
- speaking while muted, the held stream, the first-sentence cut;
- the skills index dropped, the traits line placement, unknown values, the
  base stamp, the partial-read guard on both sides, the whole-read stamp,
  the starter budget, the meter's comment loop, the stale chip result.

**Preview.**
- `details`:
  - since M6 it also walks the tabs (main first), a click on a tab, a
    rename that keeps the selection, a starter, Warm, typing free text,
    Brief (only the line changed), clearing Warm, the meter's count, and
    Try it with unsaved instructions;
  - `agentvoice try` is a preview stub. It logs the draft to `<out>.try`
    and answers a fixed line, or refuses under `PREVIEW_TRY=refuse`;
  - it checks that the draft arrived on stdin and that argv named only the
    agent;
  - **58 of 58**, with `--live-config` and with `--config agents1.json`
    plus `PREVIEW_TRY=refuse`, and again after the pass 1 fixes.
- The `details` target's Remove, Undo and "Move to trash" steps had failed
  since M1 made those buttons DangerButtons: 9 failures, and the same 9 on
  `phase-m5`, run from a temporary worktree. They now arm and confirm.
- `detailshots`: under `--config`, sora has two chips chosen. Shots:
  - wide dark and wide `flexoki-light`, for the main agent (over-budget
    role, outside-change notice, unreadable personality) and for sora
    (empty boxes with starters);
  - narrow (the overlay 560 px wide) with Warm and Brief chosen;
  - 9 tabs, so the row scrolls with its edge fade.

**Docs.**
- README: a paragraph on Agent details under "More than one agent".
- CODEBASE: traits.py, try_it.py, the agentfs additions, the new ui pieces,
  the CLI verbs, the preview targets.

## Shared files touched, and where

- `pages/AgentDetailsPage.qml` (big shared):
  - the picker (Dropdown and Binding) replaced by AgentTabs;
  - the three SettingRows on the prompt tab replaced by label, Hint,
    StarterChips and FileEditor;
  - the trait rows, Try it, and their functions and Processes. The other
    tabs are untouched.
- `daemon/wake_listen.py` (big):
  - `take_try`, `try_adapter` and `handle_try`, beside `handle_typed`
    (about 170 lines);
  - one call in the run loop, in `phase == "wake"` after typed messages;
  - `import try_it`.
- `daemon/agentfs.py` (big):
  - `starters()` and `_traits_cli`;
  - the `traits` and `templates` verbs;
  - `read_file` says `partial`;
  - the conflict message no longer assumes `a.file`.
- `ui/FileEditor.qml`: `sentChars`, `current`, `fill`, `partial`, the meter,
  and the save check by sent characters.
- `ui/InstructionsBox.qml`: `showCounter`.
- `ui/`: BudgetMeter and StarterChips are new; qmldir sorted.
- `daemon/adapters/base.py` and `claude_code.py`: `no_tools`.
- `bin/agentvoice`: `try`, and the usage lines.
- `Settings.qml`, `Panel.qml`, `AgentsPage.qml`: untouched.

## Measured

- Tests 3216 → 3312. The check's test run is about 2 min 45 s, as before.
- **Try it on the real daemon** (main agent, Claude Code, Opus at medium
  effort, synthetic draft). The side turn took **5.3 s** the first time and
  **3.6 s** the second (the journal's `try:` lines), before speaking.
- One recorded no-tools Claude turn, with the user's default model, cost
  **$0.074** (its `total_cost_usd`). That is the order of a Try it press.
- No speed or size claim is made, so nothing went to FINDINGS.

## Different from the plan, and why

- **Try it runs only on Claude Code and plain endpoints.** The plan has it
  refused "when the backend is missing". Codex's review pointed out that the
  other backends cannot honestly be called "no tools":
  - Codex `exec` without approval still runs read-only commands;
  - Gemini's plan mode and agy's read-only mode still read files;
  - an agent endpoint runs whatever its own host gives it;
  - agy also keeps a resumable conversation.

  None of them has been shown to start with nothing, so they are refused,
  with the reason on the page before the press (`try_it.backend_refusal`).
  Open issue 1.
- **The chips save through the editor (`traits apply`), not through
  `traits set`.** The plan's `get|set` exist and are tested. The page uses
  the pure `apply` so that `personality.md` keeps its one writer and the
  chips act on the draft in the box, unsaved typing included. That is also
  what Try it speaks from.
- **The CLI is `agents traits get ID`** (action first), not `agents traits
  ID get`, because `apply` takes no id.
- **"Cannot tell whether the screen is locked" refuses Try it.** A reply
  still goes on in that case, as before. Try it is an extra and need not
  (Codex pass 1).
- **The 10 s limit counts from the start of a try.** A try that takes more
  than 10 s with its speech allows the next one as soon as it ends (seen
  live: the second press was accepted).
- **One sentence is cut at its own boundary.** "Hi! How are you?" says
  "Hi!". The shared splitter would merge the two.
- **The meter replaces the box's own counter** in FileEditor, and the
  save's budget check now counts what is told rather than raw characters.
  For text with a leading comment or tabs this allows a little more.
- **Hints replace paragraphs on the prompt tab only.** Item 10 is about
  that tab. The other tabs keep their text until their own phases.
- **No keyboard walk of the new controls** (below).
- **Codex ran on the read-only copy both times.** `codex sandbox linux --
  true` still panics ("Failed to execvp linux"). The clone's HEAD and status
  were unchanged after both passes, and both copies were deleted. Pass 1 was
  sent the product-code diff only (1,772 lines: QML, daemon, bin, without
  templates), with findings capped at 8. Pass 2 was sent pass 1's fix diff
  only (324 lines), at low effort, capped at 5.

## Codex review

- **Pass 1** (8 findings; 7 fixed in 98953fd, 1 not changed):
  - Try it could speak if both lock probes failed. Now the lock is asked
    afresh before accepting and before speaking, and "cannot tell" refuses;
  - `ephemeral` and `no_tools` were not enforced on every backend. Try it
    is now limited to Claude Code and plain endpoints;
  - a chip result could save older text over newer. It is now dropped when
    the text or the stamp changed;
  - `traits set` wrote back a truncated read. It now refuses;
  - the stream was dropped before cancel. It is held, cancelled, then
    closed;
  - unknown trait values with non-ASCII letters were dropped. They are kept
    verbatim;
  - "Hi! How are you?" spoke both sentences. The first is cut at its
    boundary;
  - **not changed:** a chip click on a file whose leading comment is shown
    cleaned drops that comment. Every save from the editor always has: it
    saves what it shows, and a leading comment is never told to the agent.
    Open issue 3.
- **Pass 2** (5 findings; 4 fixed in c4c67f9, 1 recorded):
  - an editor saving a file it could read only in part, via the chips or
    typing. `read_file` now says `partial` and the editor refuses;
  - a whole read was stamped with the file's later size. It is now stamped
    by its own size;
  - "US, us" lost "us" to a case-blind dedupe. Every value is kept;
  - "Hi! " followed by a stall waited for the timeout. The first sentence
    is now returned as its boundary arrives;
  - **recorded, not changed:** when the compositor's lock helper times out,
    `session_locked()` falls back to logind, which can say unlocked under
    an Omarchy lock. That is the lock detection every reply uses. Open
    issue 4.
- **Pass 2's fixes were not reviewed by Codex** (credits, below). They have
  their own tests and five mutations, all red after one was re-aimed.

## Found along the way

- **The `details` preview target had 9 failures since M1**, and nobody saw
  them. They were the same on `phase-m5`. It still clicked Remove the
  pre-DangerButton way. Fixed here.
- **The 8-agent preview config cannot run `details`**: it adds an agent,
  and eight is the maximum. Use `agents1.json` with that target.
- **Claude 2.1.330 still loads its built-in plugins** (agents-md, telemetry,
  privacy, plugin-authoring) under `--tools ""`. The init event lists them
  with no tools and no MCP servers. They add no tool there, but they are
  not "nothing".

## Not verified

- **The page in the real shell.** It needs `omarchy-restart-shell`, which is
  held for stop point 2. Seen only in `preview.sh`: wide and narrow, dark and
  light, the two `details` runs.
- **Hearing Try it.** On the real daemon two synthetic tries reported
  "said", with a sentence that followed the draft ("Ahoy there, Theo here,
  keeping the light on…"), and the speaker path ran. Nobody was at the desk
  to hear it. The plan's stop-2 check stays: change Theo's tone chip, press
  Try it, hear the difference.
- **A real pointer and a real keyboard** on the tabs, the chips, the
  starters and Try it. Every click was synthetic (QtTest's TestEvent). No
  keyboard walk was done for the new controls. AgentTabs, ToggleChips and
  Button each have their keyboard handling from M1 and before, but their
  order on this page was not walked.
- **`agentvoice lock` during a try.** The lock check before speaking is
  tested with a stub. Live, `lock` was used only before a try (refused by
  the CLI).
- **A plain-endpoint agent's Try it**, live. Allowed by `backend_refusal`
  and tested with a stub; there is no endpoint here to run it on.
- **The `voices` and `agentshots` preview targets** were not rerun. Nothing
  they drive changed.

## Going back

`bin/agentvoice-deploy 314d7264cfe5` from the clone, then `./install.sh
--yes` from the plugin folder once the daemon is idle (the daemon changed),
then `omarchy-restart-shell` for the QML. No setting changed.
- An older build reads a `Traits:` line as ordinary personality text, and
  tells it to the agent as such.
- It ignores the starter folders and `$RUNDIR/try/`.
- Its `agentvoice` has no `try` verb.

## Open issues, for the next phase

1. **Try it on Codex, Gemini, agy and Copilot.** Each would need a posture
   proven, by a recorded real turn, to start with no tools. Codex perhaps
   with a sandbox and tool configuration that `exec` honours. Worth doing,
   or keep Try it to Claude Code and plain endpoints?
2. **Who may run `agentvoice try`.** Any process running as the user,
   including an agent at Trusted, can make the daemon speak one sentence
   from a no-tools turn of a Claude agent, on text it supplies. It is rate
   limited, refused while locked, and has no tools. It is not under the
   orders guard. Add it there (the M7 card-answer work is the place), or
   accept it?
3. **Saving from an editor drops a leading comment** (the template's
   explanation), because the box shows and saves the cleaned text. This is
   old behaviour, now also on the chips' path. Keep the comment, or keep
   the cleaned text?
4. **The lock probe's logind fallback after a helper timeout** (Codex pass
   2) applies to every reply, not only Try it. Should a timeout read as
   "cannot tell"?
5. **Codex credits overspent again**: 32.80 against about 6.2 (below).
   Product-code-only diffs and capped findings helped: pass 1 cost 22.64
   against M5's 28.66, on a third of the lines. **117.16 left for M7–M29,
   about 5.1 per phase.** One pass at low effort per phase is about what is
   left.
6. **Pass 2's fixes were not reviewed by Codex.**
7. **Carried, still open:**
   - M5's open issues 1 and 4–6: question 9's default, `__proto__` in
     `saveAgents` and `assignVoice`, the long model pill, the
     two-click tool chips;
   - M4's open issues 4–13;
   - the Voice library trash icon (M25);
   - M0's small test and bench fixes;
   - agy's `carries_session_across`;
   - the runner's sandbox test command (`codex sandbox linux -- true`
     panics).

## Codex credits used

**32.80**. The balance went from 149.95 at the end of M5 to 117.16, read
from the session logs' `rate_limits.credits.balance`. It was still 149.95
at this phase's first call.
- **Pass 1: 22.64** (149.95 → 127.31). `gpt-6.2-astra`, medium effort,
  sub-agents disabled, read-only copy, the product-code diff (1,772 lines),
  at most 8 findings: 71,211 tokens.
- **Pass 2: 10.16** (127.31 → 117.16). Low effort, the same settings
  otherwise, on pass 1's fix diff only (324 lines), at most 5 findings:
  32,121 tokens.

**117.16 left** for M7–M29.

## Live checklist: what was said, what happened

All with synthetic text. Nothing was said by voice into the microphone.
- Before the deploy, `agentvoice status`: state `listening`, every agent
  idle, no open mic.
- After the install: the service was active, `agentvoice locked` said no,
  and the state was `listening`. `shell.json` was byte-identical to the copy
  taken before.
- `agentvoice try main`, with a draft personality ("Traits: playful, brief."
  plus a canary word) and a one-line instruction. It answered "Ahoy there,
  Theo here, keeping the light on and ready whenever you are!" (exit 0).
  The journal: `try: main answered in 5.3s (71 chars)`.
- Again straight after: said a second sentence (3.6 s). The first try had
  taken over 10 s with its speech.
- `agentvoice try jarvis-ajc` (Codex): refused, "Try it runs only where a
  turn can be started with no tools at all, …, not codex" (exit 1).
- `agentvoice try nobody-here`: refused, "that agent is not running here".
- `agentvoice lock`, then `try main`: refused, "the screen is locked".
  Then `agentvoice unlock`: `locked` no, state `listening`.
- The journal since the first try (`-o json`): 8 lines, none holding the
  canary, the draft or the reply. `$RUNDIR/try/` was empty and 0700
  afterwards. No file under `chats/` was written after the tries began.
- No shell restart. No setting changed.
