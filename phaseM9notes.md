# Phase M9: Crew map, drawn

Written 2026-11-22, unattended (started by the runner script). Branch
`phase-m9`, cut from `phase-m8` at 0d4272a. Result commit: the notes commit
on top of 961ed64, pushed to `fork/phase-m9` only; `dev` fast-forwarded to
it and pushed to `fork`. Model: Claude Opus 5.5 (tier B in the plan).

Commits:
- 12f21f6: the phase;
- b68fcd1: Codex pass 1 fixes (plus the queue stall found in the preview);
- 961ed64: Codex pass 2 fix;
- then these notes.

Deployed: **yes**, once, through `bin/agentvoice-deploy --install` (its
strict check green: 3715 tests). 961ed64 replaced M8's a64219f. The daemon
was idle first (state `listening`, no task running, no open mic,
unlocked). **The way back to before M9 is `bin/agentvoice-deploy
a64219fe680c`**.

Installed: **yes**: "Build 0.2.0 (961ed64), replacing 0.2.0 (a64219f)".
Only `collab.py` (the new `crew` CLI) and `crew_links.py` changed on the
daemon side; nothing in the call path or the hook.

**Shell restart needed** (the page, the map and `ui/CrewEdge.qml` are QML).
Not run: this is stop 2, and the user runs it. Until then the running shell
has M7's QML (no Crew map page at all, M8's included).

A copy of `shell.json` was taken before the deploy
(`~/agentvoice-notes/shell.json.before-M9`, mode 0600); afterwards
`shell.json` was byte-identical to it. No live check wrote any setting.

`./bin/agentvoice-check`: green on 961ed64.
- **3715 tests** (was 3662; +53), 14 of 14 static checks, "the check wrote
  nothing in the tree: ok".
- The bare-runner variant (`AGENTVOICE_STRICT=1`, requirements-dev only):
  **not run** this phase. The new tests use the standard library, node and
  the daemon modules only (no numpy, piper or onnxruntime).
- Box: not run (`install.sh` did not change).

## What was built

**The map** (`pages/CrewMapPage.qml`, which now opens on it; Map / Table
toggle, the M8 table is the Table):
- each agent a box; boxes drag (`MouseArea` with `preventStealing`, so the
  page does not scroll under the drag, and `drag.smoothed: false`, so the
  box stays under the pointer where it was grabbed);
- **positions** in `$XDG_STATE_HOME/agentvoice/crew-layout.json`
  (`{"version": 1, "spots": {id: {x, y}}}`, fractions of the map, so a
  narrow and a wide window agree), written by the page through a
  `FileView` (folder made on a failed first save), read back through
  `parseLayout` (ids checked, numbers in 0..1, at most 64 KB, anything
  else ignored). **No saved spot: a ring** (an ellipse the shape of the
  space above the zone; two agents side by side). A spot on the wrong side
  of the zone for an agent's quarantine is ignored for the ring. Not in
  `shell.json`, and nothing in `daemon/`, `bin/` or `install.sh` names the
  file (a test);
- **a line per link** (`ui/CrewEdge.qml`, QtQuick.Shapes, curve
  renderer): border to border, an arrowhead at the agent it reaches, a
  two-way pair bowed apart (the same bend sends opposite directions to
  opposite sides), dashed when it carries nothing as things stand;
- **a label on each line**: "A D M P" for what it carries now, "?" when it
  asks first, a dash for nothing. Clicked, or reached with Tab and Enter,
  it opens the inspector. With more than 14 lines (eight agents linked
  everyone-to-everyone are 56) only the selected agent's or link's lines
  keep their labels and full colour; the rest go faint. Without that the
  8-agent map was an unreadable hairball (screenshot);
- **drag from an agent's dot onto another** to link them: the new link
  carries `ask`; dropping on a link already there selects it; dropping on
  the agent itself or on nothing does nothing. A quarantined agent has no
  dot (it starts nothing);
- **the red zone**: dropping an agent in it arms the inspector's
  Quarantine `DangerButton` (the question says what it loses); Confirm
  quarantines, Cancel, Escape, focus leaving or the 6 s timeout put the box
  back where it was. Dragging a quarantined agent out releases it at once
  and gives nothing back (as the M8 Release button did);
- **the inspector**: for a line, its abilities (`ToggleChips`, disabled
  with the reason into or out of quarantine), Ask me first (advisory for a
  Trusted caller, as in M8), the effective line, **Also allow the reverse**
  (same abilities and ask-first; becomes "Go to Sora → Theo" when the
  reverse exists; disabled with the reason when the target is
  quarantined), **Delete line** (`DangerButton`). For an agent: can reach /
  reached by, Link to (dropdown + Add link), Quarantine or Release. The
  table rows and the line inspector are one inline component
  (`LinkEditor`);
- **keyboard**: Tab reaches each box and each line's label; Enter or Space
  opens it; arrow keys move a box (Shift for bigger steps; into the zone
  asks, out of it releases, as a drag does); Delete or Backspace on a label
  arms Delete line. Create: the agent inspector's Link to. Reverse: the
  line inspector's button;
- a line under the map for links that name an agent not here (removed or
  renamed): not drawn, deleted in the table;
- "There is only one agent" when there is nobody to link.

**One function writes, after the daemon's own validator** (the plan's
"both call one page function that writes crewLinks, after `agentvoice crew
check` has validated it"):
- every edit (map, inspector, table, banner buttons) builds both lists and
  calls `commit()`, which trims them to what quarantine lets a link carry
  (no link out of a quarantined agent, only ask/delegate into one; what
  that drops counted for nothing in the daemon already) and queues them;
- the queue is checked one entry at a time by `agentvoice crew check` (one
  JSON line on stdin: both lists plus the pair the page believes is saved;
  JSON on stdout), and only `applyChecked()` writes, quarantine first,
  through `writeQuarantine` / `writeLinks`, only the lists that changed;
- saved only on exit status 0 **and** `{"ok": true}`; anything else is
  "Not saved: why", and every later queued edit (built on the refused one)
  is dropped; a checker that never started says so;
- an edit is applied only while the saved pair is still the one it was
  built on (the page's copy, and the file on disk, checked by the CLI), so
  a change made underneath is not overwritten (pass 1 and 2);
- the next check waits until the store has confirmed the page's own last
  crew write (`store.pending`), so the file and the page agree when the CLI
  compares them;
- the page shows edits at once (the queued state), and falls back to what
  is saved on a refusal. "Checking and saving…" while the queue runs.

**The validator** (`crew_links.check_write`, pure; `collab.cli_crew`;
`bin/agentvoice crew check`; reads settings only, writes nothing, no daemon
needed). Stricter than reading:
- everything `parse_links` / `parse_quarantine` refuse (malformed, unknown
  ability, an ability twice, a pair twice, a self-link, over 128 links or
  64 quarantined, not lists);
- an id that is no configured agent (`Config.all_agents()` plus `main`):
  removed, or renamed (an agent saved without an id takes it from its wake
  phrase, so a rename changes it). A link already saved naming one may stay
  or narrow, never widen (pass 1), so a stale link does not block every
  other edit;
- a link out of a quarantined agent; message or pass into one;
- a quarantine naming an agent twice (pass 1);
- input over 64 KB, not JSON (a `RecursionError` included), not exactly
  the two lists (plus the optional `saved`), settings that cannot be read;
- `saved` not matching the file (key order and JavaScript's `1` for `1.0`
  compared alike).

**Preview**: target `crew` opens on the map. `--arg linked:W:sparse` draws
a few lines (`linked:W:table` the table); `--arg drags` drives the map with
synthetic pointer and key events through every save (the validator is this
checkout's, against the scratch `shell.json`; the layout goes to a scratch
`XDG_STATE_HOME`, copied to `<out>.layout.json`). `clicks` (the table) now
switches to the table first. `preview.sh` gained the `agentvoice crew` stub
route and the scratch `XDG_STATE_HOME`.

**Docs**: CODEBASE (crew_links, the page, CrewEdge, the preview target),
README (the map in "Agents working together, and the Crew map").

**Settings**: none new (as the plan says). The layout file is not a
setting.

## What was proven, and how

- **`drags`: 30 of 30 PASS**, on the final tree, at normal speed and with
  every `bar set` slowed by 0.6 s: a line drawn from Theo's dot onto Sora
  saved one link carrying ask and opened it; a line dropped back on its own
  agent saved nothing; the inspector's delegate chip and Ask me first; Also
  allow the reverse (same abilities, inspector moved to it); Delete line
  Cancel then Confirm; Hazel dragged into the zone (asks, saves nothing),
  confirmed (saved, stays in the zone); Sora dragged in and cancelled (box
  back within 2 px); no dot on a quarantined agent; Hazel dragged out
  (released, no link back); Theo's box moved (layout file, at the expected
  spot); **keyboard**: Space on Add link created Hazel → Theo, Space on
  Also allow the reverse created Theo → Hazel, Delete on the line's label
  armed the confirm, Tab and Space deleted it; a stray link refused by the
  validator ("Not saved: link 3 names nobody-here…") with nothing written;
  the table read the same list; no write counted as "from outside".
- **`clicks` (the table): 19 of 19 PASS** on the final tree.
- **Compared with a daemon decision**: the last list `drags` saved
  (`main → sora` ask+delegate asking first, `hazel → main` ask, nobody
  quarantined) run through `crew_links.Crew` (what `collab.py` decides
  with): main → sora `[ask, delegate]` asks first, hazel → main `[ask]`,
  every other pair `[]`: the map's labels and the table's rows say the same.
  Not a live typed turn (see Not verified).
- **The installed CLI**, after the install: a good list `ok`, a link to an
  agent nobody has refused with the reason, a stale `saved` refused.
- **Tests** (`tests/test_crew_links.py`, +53): validator cases (each
  refusal with its reason, carry-over narrow vs widen, ask-first drop,
  duplicates, oversize, deep nesting), the CLI (verdicts, exit codes,
  usage, `saved` compared with the file, run through `bin/agentvoice` with
  an empty HOME and nothing written), the page's write path held by
  structure (the two writes reachable only from `applyChecked`, that only
  from `checked`, that only from the checker; every edit through
  `commit()`; no control writes), the page's queue **run in node** against
  a fake store (two quick edits in order; printed-yes-and-failed saves
  nothing; a refusal drops the queue; a change underneath is not
  overwritten; quarantine before links, unchanged lists not written; waits
  for its own unconfirmed write; sends what it saw), every page edit from
  four starting lists trimmed and accepted by the validator, the reverse,
  the layout parser, and the daemon never naming the layout file.
- **Mutations: 35, all red at the end.** 21 on the phase: 20 red first
  time; the survivor (the queue not advancing when the checker exits: the
  stall found in the 8-agent preview) got a test. 8 on pass 1's fixes, 6 on
  pass 2's (one rewritten after the `busy` → `pending` change). Run in a
  scratch copy of the tracked files under /tmp, never in the clone.

## Shared files touched, and where

- `daemon/collab.py` (big shared, +~75): `CREW_CHECK_MAX`, `cli_crew`, the
  `crew` branch in `main()`. Nothing in the call path.
- `daemon/crew_links.py` (+~70): `check_write`, `raw_order`.
- `bin/agentvoice`: the `crew` verb and its usage line.
- `pages/CrewMapPage.qml` (~600 → ~1500 lines): the save queue, the map,
  the inspector, `LinkEditor`. The table's Repeaters build only while the
  table is shown (56 rows of chips rebuilt on every save behind the map
  cost seconds with eight agents).
- New `ui/CrewEdge.qml`; `ui/qmldir`.
- `bench/preview/preview.sh`, `bench/preview/targets/crew.qml`.
- Untouched: `Settings.qml`, `wake_listen.py`, `permission_hook.py`,
  `AgentsPage.qml`, `runtime.py`.

## Measured

On this machine (i7-1185G7, 8 threads):
- **`agentvoice crew check`**, wall time per save from the shell: median
  **181 ms**, max 229 ms (n=20), most of it Python starting. A save on the
  map is that plus `omarchy bar set`.
- The 8-agent page before building the table only when shown: the preview's
  1.1 s step timer fell behind by seconds per save; after, on time.
- Tests 3662 → 3715; the check's test run about 3 min 45 s.
- No speed or size claim is made, so nothing went to FINDINGS.

## Different from the plan, and why

- **"Both call one page function that writes crewLinks"**: one function,
  `commit()`, for both lists, because quarantine and links are judged
  together (a link into a quarantined agent depends on both).
- **The validator is in `crew_links.py`**, with only the CLI in
  `collab.py`: the pure rules sit beside the ones the daemon reads with.
- **"Renamed ids"**: an id that is no configured agent is refused whether
  removed or renamed; the validator cannot tell which.
- **Beyond the plan**: carry-over of saved stale links (narrow only);
  links out of quarantine refused; the page trimming for quarantine before
  every save; the "saved underneath" checks (Codex); Shift-arrows; Delete
  on a label; "Go to the reverse"; the crowded-map rule; the one-agent and
  stray-link lines.
- **Drag out of the zone releases with no confirm**, as the plan says and
  as M8's Release button did. It widens what the agent may be asked, but
  gives back no link.
- **The ring is an ellipse** shaped to the space above the zone (a circle
  overlapped boxes at eight agents in the narrow card).
- **Codex reviewed the daemon, `bin` and the page diff** (1,274 lines), not
  `CrewEdge.qml`, the preview target or the tests, to save credits; pass 2
  reviewed pass 1's fix diff (160 lines). Low effort both times.
- **Codex pass 1 finding 2 was not changed**: quarantine and links are two
  writes, quarantine first. Between them the file holds a link out of a
  quarantined agent, which the validator would refuse but the daemon reads
  as nothing (stricter, not looser). If the links write fails the inert
  link stays until the next save trims it.
- **Pass 2's fix leaves a gap** between the CLI reading the file and
  `omarchy bar set` writing it: `shell.json` has no compare-and-set. Open
  issue 3.
- **Pass 2's fix was not reviewed by Codex** (credits).

## Codex review

**Pass 1** (6 findings; 5 fixed in b68fcd1, 1 explained above):
1. A queued edit restored a quarantine released elsewhere meanwhile.
   Fixed: an edit applies only while the saved pair is the one it was
   built on.
2. Quarantine and links are separate writes. Kept, on purpose (above).
3. A checker that printed yes and exited non-zero counted as yes. Fixed.
4. A saved link to an unknown id could be widened. Fixed: narrow only.
5. A quarantine listing an id twice passed. Fixed: refused.
6. Deep nesting could raise `RecursionError`. Fixed: a refusal. (This
   Python's `json` parsed 30,000 levels without one; the test holds the
   refusal either way.)

**Pass 2** (1 finding, fixed in 961ed64): the page's copy of the settings
can lag the file, so a link removed in another window could be put back.
Fixed in the CLI against the file, with the page waiting for its own
writes to be confirmed.

Codex ran on the read-only copy both times (`codex sandbox linux -- true`
still panics: "Failed to execvp linux"). The clone's HEAD and status were
unchanged after both passes; each copy was deleted straight after.

## Found along the way

- **The save queue stalled** with a second quick edit: the next check was
  started from the checker's output handler, while the process was still
  running, so it found it busy and nobody started it later. Found because
  the 8-agent screenshot still said "Checking and saving…" at 10 s. Fixed
  before review (it advances on exit), with a test.
- **Waiting on the store's `busy` refused its own edits** under slow
  writes (`PREVIEW_SET_DELAY=1`): `busy` drops for a moment between two
  queued writes. Waiting on `pending` (kept until `shell.json` agrees) is
  right; found by the slow-write preview, not by any test.
- **The 8-agent page was slow** because the hidden table rebuilt 56 rows
  on every save. Fixed by building the table only while shown.
- My first layout check in `drags` was wrong (it ignored where in the box
  the drag grabbed); the code was right.

## Not verified

- **The map in the real shell.** It needs `omarchy-restart-shell` (stop
  2). Seen only in `preview.sh` (screenshots: 3 agents narrow dark and
  flexoki-light, 8 agents narrow and wide, everyone and sparse, 1 agent;
  and the `drags` and `clicks` runs).
- **Drawing a link, dragging into the zone and the inspector with a real
  pointer**: synthetic events only (QtTest's TestEvent). Real touchpad
  feel (drag threshold, the dot's hit area, the page not scrolling under a
  drag) is unchecked.
- **The keyboard with real keys**: synthetic `keyClick` only. Tab order
  through the map with many agents was not walked end to end.
- **The live typed delegation over a link drawn on the map** (stop 2: the
  user draws one link, a typed delegation proves it). Enforcement itself
  is M8's and unchanged; it was proven live in M8.
- **The layout file on this machine**: written only in previews (scratch
  `XDG_STATE_HOME`). `~/.local/state/agentvoice/` exists here, so the
  folder-making fallback has not run outside a test of its parse.
- **The bare-runner check variant** was not run this phase.
- **Pass 2's fix was not reviewed by Codex.**
- **The installer box** (`install.sh` did not change).

## Going back

`bin/agentvoice-deploy a64219f` from the clone (M8's last deploy, printed
by the deploy as the one replaced), `./install.sh --yes` once the daemon is
idle, then `omarchy-restart-shell`. M8's table comes back; nothing in the
saved settings changes (M9 adds no setting). The layout file is left behind
and read by nothing. Before M8 see M8's notes (fail-open on downgrade).

## Open issues, for the next phase

1. **Stop 2 is now.** After the restart the Crew map page appears for the
   first time in the real shell (M8's and M9's together). No crew links
   are set on this machine yet, so no agent can reach another until the
   user links them (M8 open issue 1, question 2's default).
2. **Drag out of the zone releases without a confirm** (plan as written).
   Confirm instead?
3. **`shell.json` has no compare-and-set**: between `agentvoice crew
   check` reading the file and `omarchy bar set` writing it, a change from
   elsewhere can still be overwritten. Closing it needs the write to go
   through something that can compare (the daemon, or Omarchy).
4. **Quarantine and links are two writes** (Codex pass 1 finding 2):
   between them an inert link out of a quarantined agent is on disk.
   Acceptable as stricter-first, or move both into one write path?
5. **A stale link blocks nothing but cannot be widened**; deleting it is
   the table's job (the map does not draw it). Draw strays somewhere?
6. **The crowded-map rule (over 14 lines) hides labels** of unselected
   lines; the table and the agent inspector still reach every link. Right
   threshold?
7. **Question 2 and 11 defaults carried** from M8; M8 open issues 2–11
   still open (4: tools listed for an agent with no links; 5: quarantine
   drops links; 7: refused deliveries dropped; 8 is answered by the map:
   the 56-row table is now the second view).
8. **Codex credits**: 19.63 this phase; **35.87 left for M10–M29**, about
   1.8 a phase, under one low-effort pass each (a pass costs 8–11). M10,
   M17, M20, M22 and M27 are Tier A. The runner needs a decision: reviews
   for Tier A phases only, one pass each?
9. **Carried, still open**: M7's 2–7; M6's 1, 3, 4; M5's 1, 4–6; M4's
   4–13; the Voice library trash icon (M25); M0's small test and bench
   fixes; agy's `carries_session_across`; the runner's sandbox test
   command (`codex sandbox linux -- true` still panics).

## Codex credits used

**19.63**. The balance went from 55.49 at the end of M8 to 35.87, read from
the session logs' `rate_limits.credits.balance` (55.49 at this phase's
first call).
- **Pass 1: 10.95** (55.49 → 44.54). `gpt-6.2-astra`, **low** effort,
  sub-agents disabled, the read-only copy, the daemon + `bin` + page diff
  (1,274 lines), at most 6 findings. 32,991 tokens.
- **Pass 2: 8.67** (44.54 → 35.87). Low effort, pass 1's fix diff (160
  lines), at most 4 findings.

**35.87 left** for M10–M29.

## Live checklist: what was done, what happened

Nothing was said into the microphone and no agent turn was run.
- Before the deploy: state `listening`, no task running, no open mic,
  unlocked; `shell.json` copied.
- After the install: the service active, `agentvoice locked` "no", the
  plugin link pointing at the deploy checkout at 961ed64, `shell.json`
  byte-identical to the copy.
- `agentvoice crew check` (installed): `main → sora` ask: `ok`; `main →
  nobody`: refused "link 1 names nobody, which is no agent here now
  (removed, or renamed)", exit 1; a `saved` pair unlike the file: refused
  "the crew links changed outside Settings…", exit 1.
- No shell restart. No setting changed.
