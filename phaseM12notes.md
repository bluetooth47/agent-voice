# Phase M12: Skills: move, copy, undo

Written 2026-11-22, unattended (started by the runner script). Branch
`phase-m12`, cut from `phase-m11` at a15e78a. Result commit: the notes
commit on top of b8247f1, pushed to `fork/phase-m12` only; `dev`
fast-forwarded to it and pushed to `fork`. Model: Claude Opus 5.5 (tier B in
the plan).

Commits:
- cfe69f7: the phase;
- b8247f1: a fix found re-reading `transfer.py` after Codex refused the
  review (below); not reviewed by Codex;
- then these notes.

**Codex review: owed, both passes.** Codex answered "You've hit your usage
limit … try again at Nov 25th, 2026 2:53 PM" to pass 1, and the balance now
reads 0. Nothing in this phase has been reviewed by a second model.

Deployed: **yes**, once, through `bin/agentvoice-deploy --install` (its
strict check green). b8247f1 replaced M11's c912e54. The daemon was idle
(state `listening`, every agent idle, no open mic, no task, unlocked).
**The way back to before M12 is `bin/agentvoice-deploy c912e54`** (see
"Going back").

Installed: **yes**: "Build 0.2.0 (b8247f1), replacing 0.2.0 (c912e54)". The
daemon, the hook and the CLI changed.

**Shell restart needed** (Agent details' and Communal's skill lanes,
`ui/SkillCard.qml`, new `ui/SkillMover.qml`). Not run. Until it is, the
running shell has M11's QML: lanes with switches and Give a copy, no
dragging, and the Unused confirm per card. Nothing is broken meanwhile: one
thing differs, M11's Give a copy **to Communal** now fails with "every agent
will get this skill: run it again with --confirm" (the M11 page does not
pass `--confirm`), said under the lanes. Giving a copy to an agent works.

A copy of `shell.json` was taken before the deploy
(`~/agentvoice-notes/shell.json.before-M12`, 0600); after the install and
the live checks it was byte-identical. No live check wrote a setting or an
agent folder.

`./bin/agentvoice-check`: green on b8247f1.
- **4022 tests** (was 3932; +90), 14 of 14 static checks, "the check wrote
  nothing in the tree: ok".
- The bare-runner variant (`AGENTVOICE_STRICT=1`, a venv with only
  requirements-dev): **green** on b8247f1 (4006 passed, 9 skipped: the same
  numpy-only skips as M11).
- Box: not run (`install.sh` did not change).

## What was built

**One transfer helper**, new `daemon/transfer.py`, for Agent Voice's own
folders (agents and Communal); M13 reuses its journal for notes. Under the
one folder lock every write takes (`agentfs._locked`, which gained a
non-blocking form):

1. anything an earlier transfer left unfinished is settled first;
2. the source is read whole, one folder at a time **by descriptor with no
   link followed at any level** (its own folder included), within the bounds
   every skill keeps (64 files, 2 MiB, 256 KB a file, a 20,000-character
   SKILL.md that `parse_skill` accepts: no hooks, name = folder), and
   hashed; the destination is checked free of that name;
3. a journal record, `agents/.transfers/<op>.open.json` (inside the folder
   the orders guard covers, so an agent cannot plant one for recovery to act
   on without being asked);
4. the folder is staged in the destination's skills folder (`.t-<op>`)
   through that folder's open descriptor;
5. the source is read again and must hash the same;
6. a move **hides the source first** (`.t-<op>-gone`, which no reader lists)
   and then publishes by one `renameat2(RENAME_NOREPLACE)`, so between the
   two renames the skill is in neither place, never both; a copy only
   publishes;
7. the record says `published`; the SKILL.md history travels (copied; the
   source's removed on a move); "kept" travels (a skill kept where it was is
   kept where it lands, one changed outside Settings stays so); the hidden
   source is deleted; the record is finished (`<op>.json`, 100 kept).

**Crash-safe.** `recover()` rolls back a record that never reached
`published` (stage removed, hidden source renamed back) and rolls forward one
that did. The daemon calls it in its constructor, **before any agent is
built** and before the plugin folders are pruned, and on its idle poll
(`reconcile_agent_files`) without waiting on the lock: a held lock is a
transfer under way, not a crash. A record not in the shape this writes is
set aside (`.bad`), never acted on; one that cannot be settled becomes
`stuck` with why. b8247f1: a move cut short whose destination agent was
trashed before recovery now rolls back instead of sticking with the skill
hidden.

**Undo is tied to the exact revision** (the digest of what was published).
A move goes back only while the destination still hashes the same and the
source has no skill of that name; a copy (or, since M12, an import, which is
now recorded) is taken back only while it is unchanged and, for a copy,
while the original still is too, so an undo never removes the only copy as
it was. An undo is recorded, marks the original `undone`, and cannot itself
be undone; undoing twice is refused.

**Audit**: one line per transfer (`skill_move`, `skill_copy`, `skill_undo`):
ids, the skill's name, its size. Never text (the AST audit test holds it).

**CLI** (`agentvoice skills`, M11's verb): `move|copy FROM NAME TO
[--confirm]`, `undo OP`, `history [--json]`, and `import ID|PATH TO
[--confirm]` (a path when it holds a `/`). **Into Communal, or out of a
quarantined agent (or out of any agent when the quarantine list cannot be
read), the command refuses without `--confirm`**, read from a fresh Config;
so the page's question is a question, and the daemon side still holds. The
orders guard asks an agent that runs move, copy, undo or `transfer.py`, at
every level (`SKILL_WORDS`); reading the history is not asked. No crew tool
or MCP server names a transfer (tested).

**Pages.**
- `ui/SkillCard` is now draggable between `ui/DropLane`s: a drag on its
  header moves it, Ctrl held copies; a **Move to…** button (also Menu or
  Ctrl+M) lists every other lane under Move to / Copy to. `canMove` false
  (a skill found outside Agent Voice) offers copying alone. It only emits.
- New `ui/SkillMover`: `request()` runs the move at once, or, when it
  widens, shows a `ToolConfirm` ("Move tea-timer to Communal?", from where,
  "Every agent will get this skill…", who keeps its own, and for a
  quarantined source "it may have written this skill itself. Read it before
  you share it", and that past versions go with it). `--confirm` is added
  only in `transferSkill()`, called only from that confirm's `onConfirmed`
  (structural test). Then an `UndoToast` for ten seconds; failures are said
  under the lanes.
- **Agent details → Tools & skills**: every lane takes drops; every card has
  Move to…; all of it goes through `skillDropped`, which refuses (and says
  why: a clash, a skill with a problem, Unused as a destination) or hands it
  on. A skill found outside (a card its program finds, an Unused one) is only
  ever copied, through **one** import confirm for every way in (the Unused
  buttons, a drag, a card's Copy to…); a finished import offers Undo too.
- **Communal → Skills**: the shared skills and each agent's own as lanes,
  the same moves, the same confirm and Undo; the per-agent "how it takes
  skills" lines stay.

**Preview**: new target `transfer` (seed `transfer.seed.py`, config
`configs/transfer3.json` with Hazel quarantined), and a `shots` mode. M11's
`skills` target updated for the one import confirm.

**Docs**: CODEBASE (transfer.py, the CLI rows, the pages, SkillCard,
SkillMover), README ("Moving a skill"), FINDINGS §46.

## What was proven, and how

- **Tests** (`test_transfer.py` 74, `test_transfer_ui.py` 16; plus the shared
  tables): move, copy and undo round trips, each recorded in the journal,
  with history travelling and "kept" kept; refusals leaving nothing (no
  stage, no hidden folder, no open record, no audit line); a clash; bad
  ids and names; every bound (65 files, over 2 MiB, a 256 KB+ file, a
  20,001-character SKILL.md, a link, a dangling link, a FIFO, hooks, no
  SKILL.md) and the bounds themselves allowed (64 files, 20,000 characters);
  the skill folder itself a link; a **full disk** mid-copy; a folder inside
  the source **swapped for a link** mid-move; the destination's skills
  folder swapped for a link mid-move (the copy lands in the folder that was
  checked, nothing in the link's target); the source edited mid-move; no
  `renameat2`; a publish that fails putting the hidden source back;
  shadowing reported and holding both ways; **both plugin folders rebuilt**
  (the skill gone from the source agent's, there in the destination's, and
  back after Undo; into Communal every agent's); a **stale Undo** refused
  (destination edited, the name taken again at the source, the copy
  edited, the original edited or deleted); unrecorded ids; **real crashes**:
  a forked child that dies with `os._exit` at five points of a move (mid
  stage, after hiding, after publishing, after recording, mid finish), three
  of a copy and one of an undo, never leaving a skill in two places, each
  settled by `recover()` (and a second recovery finding nothing); a new
  transfer settling an old one first; **the daemon's constructor settling
  one** before it builds anything; the poll leaving a held lock alone and
  settling once it is free; a forged and a corrupt record set aside; a stuck
  record; **two moves at once serialised** (one lands whole, the other is
  told the skill is gone) and two different moves both landing; an import
  by path recorded and undone; the CLI's `--confirm` for Communal, for a
  quarantined source, for an unreadable quarantine list, and for an import
  into Communal; the hook words; the journal under the orders guard, 0700;
  the audit lines names and sizes only. QML: `--confirm` built in exactly
  the two confirmed functions; `transferSkill` reached only from a
  ToolConfirm's `onConfirmed`; move/copy/undo commands built only in the
  mover; every way a card moves going through `skillDropped`; the mover's
  "when to ask" run in node over eight cases; plain text.
- **Mutations: 24 run, 24 red.** 23 on the phase, all in scratch copies
  under /tmp (never the clone): 22 red the first time; the survivor
  (recovery never rolling forward a *published* move) was nearly equivalent,
  since the begun path also sees a landed move, but differs when the
  destination was edited before recovery (it would put the hidden source
  back beside it), so a test for that was added and it went red. Plus the
  b8247f1 test, red against cfe69f7's `transfer.py`.
- **`transfer` preview: 23 of 23 PASS** on the final QML, through
  synthetic mouse events (TestEvent; the real pointer never moved), the real
  CLI and a scratch data folder: a drag moves (Theo → Hazel), Undo moves it
  back; Ctrl+drag copies, Undo takes the copy back and leaves the original;
  Move to… opens and lists every other lane to move or copy; towards
  Communal it asks, naming who gets it, nothing moves before the answer,
  Cancel closes it, the confirm moves it, Undo brings it back; out of
  quarantined Hazel it asks with the warning, nothing moves first, then it
  moves; a clash through the menu is refused with the reason, asks nothing,
  changes nothing; an Unused card dropped on Hazel asks the import's
  question; on Communal → Skills a move into Communal asks and moves, and
  one out to Theo moves at once with Undo offered. **M11's `skills`
  target: still 18 of 18.**
- **Screenshots** (`/tmp`, not committed): wide 820×660 dark and
  flexoki-light, nine shots each; narrow 520×720 dark, nine. (A first wide
  run without `--size` grabbed the whole screen, other windows included; it
  was deleted at once and retaken cropped to the overlay.)
- **Live, on the installed daemon** (read-only or refused, synthetic): the
  service active, the plugin link at b8247f1; `agentvoice skills history`
  empty; `skills move main no-such-skill sora` refused ("main has no skill
  named no-such-skill"); `skills move main x communal` refused for want of
  `--confirm` before anything was looked up; the installed hook asks for
  `skills move … --confirm` and `skills undo …` and not for `skills
  history`; no transfer line or traceback in the journal; no journal folder
  created.

## Shared files touched, and where

- `daemon/wake_listen.py` (big shared, +~20): `transfer.recover()` in the
  constructor before `prune_plugins`; `transfer.pending()` /
  `recover(block=False)` at the top of `reconcile_agent_files`. Nothing in
  the turn loop.
- `daemon/agentfs.py` (big shared, +3): `_locked(block=True)`.
- `daemon/permission_hook.py` (security-critical, +5): `SKILL_WORDS` and the
  message.
- `daemon/skillscan.py`: `import_path`, `_recorded`, `needs_confirm`, the
  CLI verbs. `daemon/audit.py`: three kinds.
- `pages/AgentDetailsPage.qml` (big shared, 2202 → 2320): the drop and
  menu wiring, one import confirm, the mover. `pages/CommunalPage.qml`: the
  lanes. `ui/SkillCard.qml`: drag and menu. New `ui/SkillMover.qml`;
  `ui/qmldir`.
- Tests: `test_confirms.py` (a ToolConfirm may also `transferSkill`),
  `test_notes.py` (`size`, `OUTSIDE` in the audit allow-list),
  `test_skillscan.py` (an import's result carries its `op`).

## Measured

FINDINGS §46, on the i7-1185G7, a scratch folder on the home disk (btrfs):
a move of a 2-file skill **17.1 ms** median (undo 19.7), of a skill at the
bound (64 files, about 2 MB) **114.5 ms** (undo 116.5); the poll's
`pending()` check **72 µs**. Tests 3932 → 4022; the check's test run about
4 min 40 s.

## Different from the plan, and why

- **The CLI is `agentvoice skills move|copy|undo|history`**, not `agentvoice
  agents skills …`: M11 put skills under `agentvoice skills`, and one verb
  for one subject is easier to find. `skills import PATH TO` extends M11's
  `import ID TO` (a path holds a `/`).
- **`--confirm` on the command line** for every widening transfer, which the
  plan asks of the page only: the daemon side then holds too, and the pages
  pass it only from the confirm.
- **A skill with a problem is not moved** (fix it first), and Unused is not a
  destination (switching a skill off is how it stops being given).
- **Undo needs no confirm**, even when it puts a skill back into Communal:
  it restores what the person had a moment ago.
- **Imports are recorded and can be undone** like a copy (the plan names
  undo for moves and copies; an import is a copy from outside).
- **The plan's ".history" for each round trip** is the transfer journal
  (`agents/.transfers`, listed by `skills history`), plus the skill's own
  SKILL.md history travelling with it.
- **Keyboard**: Move to… is a focusable button, and Menu or Ctrl+M on a card
  opens it; the menu walks with Up/Down and picks with Enter (MenuList).
  Not driven: see Not verified.
- **Codex did not review** (out of quota).

## Found along the way

- **Synthetic key events do not reach the preview window** (it never takes
  the keyboard, by design), so no preview can drive a keyboard path; and the
  overlay's page view there is about 530×510, so a drag works only between
  lanes on screen together (neighbours). There is no auto-scroll while
  dragging near the edge: in a small window, Move to… is the way to a far
  lane (as DraggableCard's comment says it must always be).
- **A preview without `--size` screenshots every monitor**, the person's
  other windows included. Worth a guard in `preview.sh` (open issue 6).
- **A `pgrep -f` wait loop matches itself** (again; it is in the memory
  notes); two hung waiters were stopped.

## Not verified

- **The pages in the real shell.** They need `omarchy-restart-shell` (next
  stop point, after M15). Seen only in `preview.sh`, with synthetic mouse
  events. A real pointer's drag in Quickshell, the drag ghost over the
  overlay, and Ctrl pressed or released mid-drag were not seen.
- **The keyboard paths**: Tab to a card, Ctrl+M or Menu to open Move to…,
  Up/Down/Enter in it, Escape and Enter on the confirm, Enter on the toast's
  Undo. Key events cannot reach the preview window. At the stop point: do a
  move, a copy and an undo with the keyboard alone.
- **The plan's typed live check** (move a skill from Theo to Communal and
  Sora can use it; undo and she cannot): it moves a real skill into what
  every real agent gets, the kind of widening an unattended run is refused
  (memory: M10). Proven with fixtures instead (both plugin folders rebuilt;
  into Communal every agent's). At the stop point: make a throwaway skill in
  Theo's folder, drag it to Communal, ask Sora to list her skills, Undo, ask
  again.
- **Crash recovery on the real daemon**: tested by constructing the Daemon
  in a test after a real crash of a forked child; the installed daemon was
  not killed mid-transfer.
- **Give a copy to Communal in the old (M11) QML** now needs `--confirm`
  and fails until the shell restarts (said on the page).
- **The Codex review, both passes** (owed).
- **The installer box** (`install.sh` did not change).

## Going back

`bin/agentvoice-deploy c912e54` from the clone, `./install.sh --yes` once the
daemon is idle, then `omarchy-restart-shell`. **First make sure no transfer
is unfinished**: `agentvoice skills history` lists none `stuck`, and
`~/.local/share/agentvoice/agents/.transfers/` holds no `*.open.json` (the
M12 daemon finishes or rolls back any when it starts, so starting it once is
enough). An older build lists no `.t-*` folder, so a skill hidden by a move
cut short would be invisible to it. Skills sit wherever they were moved;
an older build gives them from there, as any skill. The journal folder is
ignored by older builds (no agent id starts with a dot). Plan section 7.7
applies as for M11 (`skillsOff` unread before M11).

## Open issues, for the next phase

1. **Codex review owed for M12, both passes**, and for every later phase
   until credits are added (balance 0; the limit resets 2026-11-25 14:53
   per Codex's message). M17, M20, M22 and M27 are Tier A, where the plan
   makes both reviews mandatory before the next phase. The runner needs a
   decision (wait for the reset, more credits, another reviewer, or accept
   "review owed").
2. **Auto-scroll while dragging near the edge of a lane list**: not built;
   Move to… covers it. Build it?
3. **A skill with a problem cannot be moved** (only fixed in place). Allow
   moving a broken skill (it stays undelivered wherever it goes)?
4. **Undo back into Communal asks nothing.** Should it ask, like the move?
5. **A stuck transfer** is shown only by `agentvoice skills history` and the
   journal line; no page shows it. Add a notice under the lanes?
6. **`preview.sh` without `--size` grabs every monitor**: make a crop the
   default, or refuse to shoot without one?
7. **Moving history**: a move takes the SKILL.md versions along and removes
   them at the source; a copy duplicates them. The plan says past versions
   move with notes (M13); for skills this is the same choice. Keep?
8. **Carried, still open**: M11's 1–7; M10's 1–8; M9's 2–7; M8's 2–11; M7's
   2–7; M6's 1, 3, 4; M5's 1, 4–6; M4's 4–13; the Voice library trash icon
   (M25); M0's small test and bench fixes; agy's `carries_session_across`;
   the runner's sandbox test command (`codex sandbox linux -- true` still
   fails: "Failed to execvp linux").

## Codex credits used

**At most 1.02; no review was produced.** The balance was 1.02 at the start
(the last M11 session log); pass 1 (`gpt-6.2-astra`, low effort, sub-agents
disabled, the read-only copy, the daemon + `ui/SkillMover.qml` diff of 1,279
lines, at most 3 findings) was refused at once with the usage-limit message,
and the balance then read 0. Pass 2 was not attempted. The clone's HEAD and
status were unchanged after the attempt and the copy was deleted straight
after. **0 left** for M13–M29.

## Live checklist: what was done, what happened

Nothing was said into the microphone and no turn was typed.
- Before the deploy: state `listening`, every agent idle, no open mic, no
  task, unlocked; `shell.json` copied (0600).
- After the install: the service active; the plugin link at b8247f1;
  `shell.json` byte-identical to the copy.
- `agentvoice skills history`: empty. `skills move main no-such-skill sora`:
  refused. `skills move main x communal`: refused for want of `--confirm`.
  The installed hook: asks for move and undo, not for history. Journal: no
  transfer line, no traceback; `agents/.transfers` not created.
- At the end: `shell.json` byte-identical to the copy. No shell restart.
