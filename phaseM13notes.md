# Phase M13: Note categories, and moving notes

Written 2026-11-22, unattended (started by the runner script). Branch
`phase-m13`, cut from `phase-m12` at c4ddf14. Result commit: the notes
commit on top of 051ecc3, pushed to `fork/phase-m13` only; `dev`
fast-forwarded to it and pushed to `fork`. Model: Claude Opus 5.5 (tier B in
the plan).

Commits:
- 051ecc3: the phase, including the fixes my own re-read found (listed under
  "Found along the way");
- then these notes.

**Codex review: bypassed (user decision, 2026-11-22).** Codex was not run, for
review or anything else. In its place I re-read the whole diff before the
commit; what that found and fixed is under "Found along the way". Nothing in
this phase has been reviewed by a second model.

Deployed: **yes**, once, through `bin/agentvoice-deploy --install 051ecc3` (its
strict check green). It replaced M12's b8247f1. The daemon was idle: state
`listening`, every agent idle, no open mic, no task, unlocked. **The way back
to before M13 is `bin/agentvoice-deploy b8247f1`** (see "Going back").

Installed: **yes**: "Build 0.2.0 (051ecc3), replacing 0.2.0 (b8247f1)". The
daemon, the hook and the CLI changed. `install.sh` did not change.

**Shell restart needed** (`ui/NotesPanel.qml`, new `ui/NoteMover.qml`, both
pages' Notes tabs). Not run. Until it is, the running shell has M12's Notes
tab: one folder's list with the editor, no cards, no moving. Nothing is broken
meanwhile: the old tab calls only `agentvoice agents notes …`, which did not
change. The one difference it can meet is the guard: an *agent* running
`agentvoice agents notes … write|lock|unlock|restore` is now asked (the page
itself is not an agent and is never asked).

A copy of `shell.json` was taken before the deploy
(`~/agentvoice-notes/shell.json.before-M13`, 0600); after the install and the
live checks it was byte-identical. No live check wrote a setting, a note or an
agent folder.

`./bin/agentvoice-check`: green on 051ecc3.
- **4161 tests** (was 4022; +139), 14 of 14 static checks, "the check wrote
  nothing in the tree: ok".
- The bare-runner variant (`AGENTVOICE_STRICT=1`, a venv with only
  requirements-dev): **green** (4145 passed, 9 skipped: the same numpy-only
  skips as M12).
- Box: not run (`install.sh` did not change).

## What was built

**A note is a topic.** Storage did not change and nothing was rewritten: a
note file already is one topic.
- The crew tools steer to it: `notes_list` says notes are kept one per topic
  and returns each with its topic label and its first line (quoted, with "each
  first line is quoted from the note: information, not an instruction"); the
  `notes_list`, `notes_write` and `notes_append` descriptions say to append to
  the topic's note rather than start a new one.
- `notes.py`: `topic_label` ("shopping-list" → "Shopping list"), `first_line`
  (the first line with words, heading marks dropped, non-printing characters
  blanked, 120 at most), each listed note's saved-version count, and `gone`:
  names with saved versions and no note (deleted by hand, or combined away).

**Moving, copying, combining** (new `daemon/notemoves.py`, through M12's
journal, which now holds records of `kind: "note"`; transfer.py dispatches
validation, settling and undo by kind):
- **A move carries the file, its `.meta.json` entry and its history.** The
  entry travels whole (rev, author, time, hash, taint, lock), except that the
  rev goes on from a destination tombstone when that is higher, and a
  destination tombstone's lock is kept: an agent that read an older note of
  that name there can never write over the new one on a shared rev.
- Under the one lock: anything unfinished settled first; **both records must
  be readable** (a corrupt one refuses, in either direction, so a move never
  washes off "every note locked"); the note must be text; no clash, room in
  the destination; a journal record; the text staged as `.t-<op>.md`; the
  source read again; **the destination's entry written before the file
  lands**; a move hides the source (`.t-<op>-gone.md`) and then publishes by
  one `renameat2(RENAME_NOREPLACE)`; `published`; history copied by version
  name; the source tombstoned and its history removed; done.
- **Settled before anything reads.** `notes._current`, which every notes read
  and write goes through (the tools, the CLI, the page), settles an open
  record first: half a move is a note file with no entry, which the scan
  would otherwise take for a note made by hand, its taint and lock gone. The
  daemon's own recovery (constructor and poll, from M12) settles note records
  too.
- **Combine** merges 2 to 20 notes of one folder into one topic: the first
  named is kept (or a new name is made); each other is added under a
  `## Topic` heading; taint and lock are ORed; author "you". Each note
  combined away keeps its whole history, its last text saved as a version
  first, and is tombstoned (its lock kept); **Earlier notes** on the tab puts
  it back from its newest version. Recorded and recovered like a move; not
  undoable in one step (the confirm says so).
- **Undo** of a move or copy, tied to digest and rev where it landed; a copy
  only while the original is unchanged too. Undoing a copy removes only the
  versions it brought, and leaves a lock the folder's earlier tombstone had.
- **Confirm before widening**, checked inside the lock: into Communal, out of
  a quarantined agent (any agent when the list cannot be read), or a note
  marked as holding web text. `move()`/`copy()` refuse without `confirmed`;
  the CLI's `--confirm` sets it.
- **Audit**: one line each, `note_move`, `note_copy`, `note_combine` (with the
  parts' total size), `note_undo`: ids, the name, sizes. Never text, and the
  journal record holds no text either (tested).
- **CLI**: `agentvoice notes lanes [--json]`, `move|copy FROM NAME TO
  [--confirm]`, `combine TARGET INTO NAME…`, `undo OP`, `history [--json]`.
  `agentvoice skills history` now lists skill records only.

**Only the person.** No crew tool moves, copies, combines or undoes (tested
by name). The orders guard asks an agent running any of those at every level
(`NOTE_WORDS`). And `FOLDER_WORDS` (below, "Found along the way").

**Pages.** `ui/NotesPanel` (one folder, as before, plus):
- its notes as topic cards (`ui/SkillCard`: topic, first line, rev, author,
  size, the web mark, a lock badge; unfolded: name, saved versions, lock,
  taint) in its own `DropLane`, with **Open** (the editor below, unchanged),
  **Lock/Unlock**, and **Pick** while combining;
- every other folder as a lane from `agentvoice notes lanes` (main, each
  agent, Communal; "· quarantined" in the title), whose cards' **Open →**
  goes to that lane's own Notes tab (`openElsewhere`; the pages route it);
- a drag moves, Ctrl+drag copies, **Move to…** (Menu or Ctrl+M) does both;
  every way in goes through `noteDropped`, which refuses with the reason (a
  clash, a note with a problem, an unreadable record on either side) or hands
  it to the new `ui/NoteMover`;
- `ui/NoteMover`: runs a move at once, or asks first when it widens
  ("Move Garden to Communal?", from where, who can read it, "2 saved versions
  go with it", the web-text and quarantine warnings, "its past versions move
  too, so whoever can read it there can read what it said before");
  `--confirm` is added only in `transferNote()`, called only from that
  confirm's `onConfirmed`. Combine always asks (`combineNotes()` only from its
  own confirm). Then an `UndoToast` for ten seconds; failures said.
- **Combine…** / **Earlier notes (N)** with **Put back**.
- The editor closes, saying so, when the open note leaves the folder (moved,
  combined or deleted), rather than offer to save it back.
- Communal → Notes shows the same lanes with Communal as home.

**Preview**: new target `notemoves` (seed `notemoves.seed.py`, writing through
notes.py so every note has its entry and history; config `transfer3.json`,
Hazel quarantined), with a `shots` mode. The Phase 14 `notes` target updated
for the cards. `preview.sh`'s `agentvoice` stub routes `notes` to the scratch
data folder.

**Docs**: CODEBASE (notemoves.py, notes.py, transfer.py, NotesPanel,
NoteMover, the CLI rows), README ("Notes are topics"), FINDINGS §47.

## What was proven, and how

- **Tests** (`test_notemoves.py` 114, `test_notemoves_ui.py` 24, plus the
  shared tables): topic labels and first lines (an escape sequence blanked);
  the listing's topic, first line and version count; `notes_list` steering to
  one note per topic and quoting first lines (a first line cannot close its
  own quotes); **crew tools still scoped to `mine` and `communal`, none
  moves**; **a move keeps rev, history, author, taint and lock** (the entry
  byte-equal); a copy duplicates all three; the tombstone rev rule and its
  lock; **a clash refused**; **a corrupt record on either side refuses** and
  is left as it was; bad names and targets; a binary note; a trashed agent's
  folder never brought back; a full destination; **a full disk** mid-move; a
  hand edit mid-move; a failed publish putting the hidden source back;
  **`notesWrite=deny` and a lock still hold where it lands**, through the
  store and through the tool; taint staying on appends; the four confirm
  reasons for move and copy (and four ordinary moves that need none); the
  CLI reading the quarantine fresh; undo of a move (rev on from the
  tombstone, history back, "undone", no second undo, no undo of an undo);
  undo of a copy taking only its own versions; **stale undos refused** (an
  edit, an edit and back to the same bytes, a new note at the source, the
  original changed, the copy changed); note and skill ops not undoable
  through each other's verb; **Combine keeping every history** (each part's
  last text a version, tombstones, taint and lock ORed) and Put back
  restoring text and taint; Combine into a new name; Combine refusals; the
  size cap; a corrupt record; **audit lines of names and sizes only** (a
  canary absent from the log and the journal); **real crashes** (a forked
  child dying with `os._exit`) at six points of a move (staged, entry
  written, hidden, published, recorded, half finished), three of a copy, two
  of a Combine and one of an undo, each settled by recovery the right way
  with nothing left behind; **a read after a crash settles first** (taint,
  lock and author survive) and, as the second layer, a scan that skipped
  recovery still sees taint and lock because the entry landed first; the
  daemon's recovery settling a note record; a forged record set aside; a
  stuck record when a new note took the hidden one's place; **8 writers
  appending during a move lose nothing** (every line in the moved note or a
  new one at the source); **two movers crossing in opposite directions ten
  times each never deadlock** and lose nothing; two moves of one note at once
  serialised; lanes (order, labels, quarantine, an unreadable list, an
  unreadable record); the CLI round trip and terminal-safe output; the hook
  asking for every moving and folder-writing command through `decide()` and
  not for reading ones. QML: `--confirm` built only in `transferNote`;
  `transferNote` and `combineNotes` reached only from a ToolConfirm's
  `onConfirmed`; note commands built only in the mover; every way a card
  moves going through `noteDropped`; Combine asked through the mover only;
  plain text everywhere; the panel naming no setting; the mover's "when to
  ask" (ten cases) and the lane refusals (six) run in node. `notes combine`
  joined test_confirms' destructive-command table.
- **Mutations: 25 run, 25 red**, all in scratch copies under /tmp (never the
  clone): settle-before-read off; the entry written after the file; taint,
  an unreadable quarantine list and Communal each needing no confirm; lock,
  taint, the tombstone rev and the history each not travelling; Combine
  washing taint, dropping the lock, keeping no last version; an undone copy
  dropping all history; undo ignoring the rev; undoing a copy whose original
  changed; a corrupt destination accepted; a clash overwriting; recovery never
  rolling forward; the note words and the `unlock` folder word gone; the
  panel skipping its refusal; the mover not asking for taint; `--confirm`
  added outside the confirm; Combine from a plain click. One survived the
  first run (the "append rather than start a new one" wording in
  `notes_list`'s description was unpinned); the test was tightened and it
  went red.
- **`notemoves` preview: 28 of 28 PASS** through synthetic mouse events
  (TestEvent; the real pointer never moved), the real CLI and a scratch data
  folder: cards titled by topic with their first line; every other folder a
  lane, Communal last; a drag moves Garden to Theo with its two versions, Undo
  brings it back; Ctrl+drag copies, Undo takes the copy back; Recipes (web
  text) through Move to… asks with the warning and Cancel changes nothing;
  towards Communal it asks (who can read it, "2 saved versions go with it"),
  moves with its versions, Undo brings it back; Birds out of quarantined
  Hazel asks with the warning, then moves; a clash is refused with the reason
  and asks nothing; Combine picks Seeds then Compost in order, asks, leaves
  one note and Compost's last text as a version; Earlier notes' Put back
  brings Compost back; a card's Open → goes to Communal's tab, which shows
  every agent's lane. **Phase 14's `notes` target: 21 of 21. M12's
  `transfer`: 23 of 23; M11's `skills`: 18 of 18.**
- **Screenshots** (`/tmp/m13`, not committed): wide 820×660 dark and
  flexoki-light, narrow 520×720 dark, six each, through the shots mode (the
  confirm for a move into Communal up). All cropped with `--size`.
- **Live, on the installed daemon** (read-only or refused, synthetic): the
  service active, the plugin link at 051ecc3; `agentvoice notes history`
  empty; `notes lanes --json`: four lanes (main, Hazel, Sora, Communal), **no
  real agent has a note yet**, quarantine readable; `notes move main
  no-such-note sora`, `notes combine main a no-such-x no-such-y`, `notes undo
  <unknown>`, `notes move main x main` all refused with the reason; the
  installed hook asks for move, combine, undo, `agents notes … unlock|write`
  and `agents write`, and not for lanes, history, `agents notes … list` or
  `agents trash-list`; no journal folder created; no traceback or transfer
  line in the journal (read with `-o json`); `shell.json` byte-identical.

## Shared files touched, and where

- `daemon/wake_listen.py` (big shared): **not touched**. M12's
  `transfer.recover()` in the constructor and the poll settles note records
  through the dispatch.
- `daemon/agentfs.py` (big shared): **not touched** (the plan lists it for the
  CLI; see "Different from the plan").
- `daemon/permission_hook.py` (security-critical, +27): `NOTE_WORDS`,
  `FOLDER_WORDS` and their messages, after the crew words.
- `daemon/transfer.py` (+66, -8): `working()`/`busy()`, note dispatch in `_valid`,
  `_settle` and undo (`_undo(op, kind)`), `history(kind=)`, `_audit`'s parts
  size.
- `daemon/notes.py` (+75, -3): `_settle_transfers`, `topic_label`, `first_line`,
  `_gone`, the listing's new fields. `daemon/crew_mcp.py`: descriptions and
  the listing line. `daemon/audit.py`: four kinds. `daemon/skillscan.py`:
  `history(kind="skill")`. `bin/agentvoice`: the `notes` verb.
- `pages/AgentDetailsPage.qml` (big shared, 2320 → 2325) and
  `pages/CommunalPage.qml` (941 → 944): `onOpenElsewhere` only.
- `ui/NotesPanel.qml` (841 → 1194); new `ui/NoteMover.qml`; `ui/qmldir`.
- Tests touched: `test_confirms.py` (the `notes combine` verb; a ToolConfirm
  may also `transferNote`/`combineNotes`), `test_transfer_ui.py` (the
  `--confirm` list), `test_notes.py` (`parts_bytes` in the audit allow-list).

## Measured

FINDINGS §47, on the i7-1185G7, a scratch folder on the home disk (btrfs):
moving a one-line note **16.8 ms** median (undo 19.1); a note at the size cap
with 20 saved versions **68.1 ms** (undo 72.3); combining five 1,000-character
notes **25.6 ms**; `lanes` over nine folders of about 20 notes **45.0 ms**;
`list_notes` of 20 notes **3.8 ms**; the `pending()` check before every read
**68 µs**. Tests 4022 → 4161; the check's test run about 4 min 50 s.

## Different from the plan, and why

- **The CLI is `agentvoice notes move|copy|combine|undo|history|lanes`**
  (new `notemoves.py`), not new verbs in `agentfs.py`: M12 put moving skills
  under `agentvoice skills`, one verb per subject, and `agentfs.py` is a big
  shared file. One folder's notes stay `agentvoice agents notes TARGET …`.
- **`--confirm` on the command line** for widening moves, which the plan asks
  of the page only, as M12 did for skills; here it is checked *inside* the
  lock, because the taint it depends on is read there.
- **A tainted note asks for any move or copy**, not only into Communal: the
  plan lists "a tainted note" as its own reason to confirm.
- **The rev travels, except over a tombstone.** The plan says the revision
  travels; a destination that had a note of that name keeps that rev, so the
  arriving note goes on from the higher one (and an undone move comes back
  one rev on, from the tombstone it left). Without that, an agent holding the
  old note's rev could overwrite the arriving one unread.
- **History is merged by version name and not pruned at a move**: a
  destination with saved versions of an earlier note of that name keeps them
  beside the arriving ones (as a note re-created by hand would); the next
  write keeps the newest twenty, as always.
- **Combine stays inside one folder** (move first to combine across), keeps
  the first note picked (a new name only from the CLI), **always asks**
  (it takes notes off the list) and is **not undoable in one step**: each
  part's history stays and Earlier notes puts a part back. The plan asks
  Combine to keep each source's history; Undo was named for moves.
- **Earlier notes** (put back a combined-away or hand-deleted note) is new:
  without it, "each source's history kept" would be on disk and unreachable.
- **Note cards reuse `ui/SkillCard`** (it already had title, subtitle, badge,
  status, details, drag and Move to…), with a `dragKey` of their own.
- **Codex did not review** (bypassed by the user's decision).

## Found along the way

- **A lock bypass through the notes CLI, now closed.** `agentvoice agents
  notes TARGET write|lock|unlock|restore` writes as the person, so an agent
  with a shell could unlock a note the person locked, or write past
  `notesWrite=deny`, and the orders guard asked nothing: it matched paths and
  a few command words, and these commands name no path. The same held for
  `agentvoice agents write|revert|ack|trash|restore|create|migrate` and
  `traits set` (an agent's instructions, through the CLI). `FOLDER_WORDS` now
  asks for all of them at every level; reading verbs are not asked. Still a
  text match, like every Bash rule in the guard: quoting gets past it.
- **My own re-read of the diff before the commit** found and fixed: the
  guard's `trash\b` also matched the read-only `agents trash-list`; the folder
  descriptors were opened after the journal record was written, so a failed
  open would have left a record and a descriptor behind; undoing a copy
  unlocked a name the folder's earlier tombstone had locked (now kept, with a
  test); an unused helper.
- **The Notes tab rebuilt every card on every 4 s poll**, even when nothing
  changed: that would drop a drag out of a person's hand and fold any card
  they had unfolded. A reading is now applied only when it differs, and not
  while a card is being dragged. Found by the preview's first drag failing.
- **A preview drag's first synthetic step must be small**: MouseArea moves
  the ghost from where the drag threshold was crossed, so a 29 px first step
  left the drop point 29 px short of the lane (a hand's first step is a few
  pixels). The target now steps 8 px first.
- **`preview.sh`'s stub had no `notes` case**, so a preview's `agentvoice
  notes …` fell through to the installed CLI. It did nothing (the M12 CLI had
  no `notes` verb, so it printed usage; nothing real changed, checked), but
  with this build installed it would have acted on real notes. Routed to the
  scratch folder now.
- **Editing files while the check runs fails its last line**, rightly; the
  first full run was spent that way (4160 passed, the tree check failed on
  three files edited mid-run). The second run, untouched, was green.

## Not verified

- **The Notes tabs in the real shell.** They need `omarchy-restart-shell`
  (next stop point, after M15). Seen only in `preview.sh` with synthetic mouse
  events: a real pointer's drag, the ghost over the overlay, Ctrl pressed or
  released mid-drag, and Open → switching pages were not seen live.
- **The keyboard paths**: Tab to a card, Ctrl+M or Menu for Move to…,
  Up/Down/Enter in it, Escape and Enter on both confirms, Enter on Undo, and
  Pick/Combine from the keyboard. Key events cannot reach the preview window.
- **The plan's typed live check** (Theo appends to an existing topic note
  instead of starting a new one; move it to Communal and Sora reads it;
  restore an old version): it needs real turns by real agents, and moving a
  note into Communal widens what every real agent reads, the kind of live
  check an unattended run does not make (memory: M10). No real agent has a
  note yet, either. Proven with fixtures instead. At the stop point: ask Theo
  to note something on a topic twice and check `agentvoice agents notes main
  list` shows one note; drag it to Communal and ask Sora what the communal
  notes say; open its History and Restore one.
- **Whether agents really follow "one note per topic"**: the descriptions
  say so; no real turn was run to see an agent append rather than start a
  note.
- **Crash recovery on the real daemon**: tested with real crashes of forked
  children and recovery in tests; the installed daemon was not killed
  mid-move.
- **The Codex review** (bypassed, not owed).
- **The installer box** (`install.sh` did not change).

## Going back

`bin/agentvoice-deploy b8247f1` from the clone, `./install.sh --yes` once the
daemon is idle, then `omarchy-restart-shell`. **First make sure no transfer is
unfinished**: `agentvoice notes history` and `agentvoice skills history` list
none `stuck`, and `~/.local/share/agentvoice/agents/.transfers/` holds no
`*.open.json` (the M13 daemon settles any when it starts, and so does any notes
read). An M12 daemon reads a note record as one it did not write and sets it
aside (`.bad`), never acting on it, so a note move cut short and then
downgraded would stay half done: a `.t-*.md` stage or a hidden source that no
older build lists. Notes sit wherever they were moved; the meta format is
unchanged, so an older build reads them there, with their entries and
history. Combined notes stay combined. An older build's guard does not ask an
agent running `agentvoice agents notes … unlock` or the other folder verbs:
going back reopens that. Plan section 7.7 applies as for M12.

## Open issues, for the next phase

1. **Codex review bypassed** for M13 (user decision, 2026-11-22); M12 stays
   "review owed".
2. **Combine has no Undo** (each part's history stays; Earlier notes puts one
   back). Build a one-step Undo for Combine?
3. **Combine into a new name** is CLI-only (`agentvoice notes combine TARGET
   NEW A B`); the tab keeps the first note picked. Add a name field?
4. **Combining across folders** is refused (move first). Allow it?
5. **A tainted note asks before any move or copy**, not only into Communal
   (the plan lists taint as its own reason). Keep, or ask only when widening
   the audience?
6. **Undo back into Communal asks nothing** (as M12 decided for skills).
7. **History merges by version name** when the destination once had a note of
   that name, and is pruned to twenty on the next write. Keep, or set the old
   versions aside?
8. **A stuck note transfer** is shown only by `agentvoice notes history` and
   recovery's output; no page shows it (as M12's open issue 5 for skills).
9. **`FOLDER_WORDS` is a text match**, like the rest of the Bash guard:
   `agentvoice agents notes main 'unlock' x` with odd quoting or a variable
   gets past it. A real fix is the daemon refusing a person-only write that
   did not come from the shell (as M7 did for cards). Worth a phase?
10. **Carried, still open**: M12's 2–7; M11's 1–7; M10's 1–8; M9's 2–7; M8's
    2–11; M7's 2–7; M6's 1, 3, 4; M5's 1, 4–6; M4's 4–13; the Voice library
    trash icon (M25); M0's small test and bench fixes; agy's
    `carries_session_across`; the runner's sandbox test command.

## Live checklist: what was done, what happened

Nothing was said into the microphone and no turn was typed.
- Before the deploy: state `listening`, every agent idle, no open mic, no
  task, unlocked; `shell.json` copied (0600).
- `bin/agentvoice-deploy --install 051ecc3`: "deployed 051ecc3f9af4. The way
  back: bin/agentvoice-deploy b8247f137c2e"; "QML changed: run
  omarchy-restart-shell? (not run)"; the installer: "Build 0.2.0 (051ecc3),
  replacing 0.2.0 (b8247f1)".
- After: the service active; the plugin link at 051ecc3; `notes history`
  empty; `notes lanes`: four lanes, no notes, quarantine readable; four
  refusals with their reasons; the installed hook asks for the six moving or
  writing commands and not for the four reading ones; no `agents/.transfers`
  created; 27 journal lines since the deploy, none with a traceback;
  `shell.json` byte-identical to the copy. No shell restart.
