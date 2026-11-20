# Phase 10: Migration, and the main agent as a folder

Written 2026-11-19. Branch `phase-10`, cut from `phase-9` at f76c9e1, pushed
to `fork/phase-10` only (the hash is in `git log`). Installed: yes, and every
live check below ran on the installed build. Tested on: i7-1185G7, `claude`
2.1.328, `codex-cli` 0.170.0.

`./bin/agentvoice-check`: green, 1984 tests (was 1934). Box: not run
(`install.sh` did not change). Preview: `voices` 21/21 and the new `folders`
target 11/11, both against a scratch data folder.

**Codex did not review this phase.** Its usage limit was reached partway
through the first review (it resets at 19:13 today), so the review below is
my own, plus mutation testing. A Codex review is owed and its findings go in
a follow-up commit on this branch.

## What was built

- **`agentfs.migrate(cfg, dry_run=False, settings_read=True)`**, run by the
  daemon on every start before any agent is built, and by
  `agentvoice agents migrate [--dry-run] [--json]`:
  - makes `communal/` from its template, `agents/main/`, and one folder per
    stable id the settings accept, switched off agents included (new
    `Config.all_agents()`); an entry the settings drop gets none and is
    counted in the report, and an agent whose id is `communal` is reported
    by name and gets none;
  - writes each file **only when it does not exist**, under the lock with a
    base of `missing`, so a second run, a run after a kill, or a run over a
    file the person already has changes nothing that exists;
  - `instructions.md` gets the old setting (`agentInstructions`, or the
    entry's `instructions`, cleaned as the daemon always cleaned them) when
    it has text, else the template; every write is a saved version
    (`migration`), so a migrated file never reads as changed outside;
  - **never writes shell.json**;
  - records `{"migrated": 1}` in `agents/.state.json` last, and only when
    every folder was done;
  - logs, on the first start only, one line per folder made: names, ids,
    file names and character counts, never instruction text.
- **Which source wins** (`agentfs.instructions_for`, and the daemon's cached
  copy of it, `Daemon.instructions_for`): the folder's `instructions.md`
  whenever it exists, **even empty**; the old setting only while the file is
  missing. The main agent (startup and `reconcile_agent`) and every extra
  agent (`reconcile_crew`, by putting the file's text in the spec it
  compares) are told the file. An instruction change keeps the conversation,
  as before.
- **The daemon reads the folders first.** `reconcile_agent_files` now runs
  at the top of `refresh()` and keeps each folder's instructions from the
  same read as the sizes it publishes (`agentfs.snapshot()`), so a hand edit
  or a save reaches the agent on the same poll, and an edit that keeps every
  size still counts. A failed read keeps the instructions it had.
- **A typed turn catches up first** (`handle_typed` calls `refresh()`): see
  "Found along the way".
- **The Agents page** (looks the same until Phase 12):
  - both instructions boxes are a new `ui/FolderInstructionsBox.qml`, which
    reads and writes `instructions.md` through `agentvoice agents`, the text
    as one JSON line on stdin (`write --line`), with the stamp it read as the
    base. A refused save keeps the typed text in the box, says why, and on a
    conflict offers "Replace it with mine" and "Show the other version".
    Until the folder exists it shows, and first saves over, the old setting;
  - **adding an agent** runs `agents create <id>`; **removing one** runs
    `agents trash <id> --line` with its settings entry, and takes it off the
    list only once the folder is in the trash, then shows "Moved … to the
    trash" with **Undo** (`agents restore`, back at its old place). A failed
    trash removes nothing and says why;
  - removing persists every other entry's derived id, as adding and editing
    already did, so an entry with no stored id keeps its folder's name;
  - the new agent's entry no longer carries `instructions`.
- **`agentInstructions` retired**: gone from `manifest.json` (schema and
  defaults), no page writes it, kept in `runtime.DEFAULTS` as the legacy
  read for one release. Confirmed first that `agentvoice-check` only fails
  on a manifest key missing from `DEFAULTS`, not the other way round.
- **The preview harness never writes real agent folders**: `agentvoice
  agents …` in a preview runs this checkout's `agentfs.py` against a scratch
  `XDG_DATA_HOME`, in every mode.
- `bench/preamble_size.py` and `bench/start_bench.py` read instructions
  where the daemon now does.

## Shared files touched, and where

- `daemon/wake_listen.py`: `refresh()` (order), `reconcile_agent_files`
  (snapshot, instructions cache), new `instructions_for`, one line in
  `reconcile_agent`, the spec comprehension in `reconcile_crew`, the top of
  `handle_typed`, and the migration plus the main agent's instructions in
  `main()`.
- `daemon/runtime.py`: `all_agents()`, `_agents()` returns a third list; a
  comment on `agentInstructions` in `DEFAULTS`.
- `daemon/agentfs.py`: `snapshot`, `instructions_for`, `settings_were_read`,
  `migrate`, `migration_state`, `migration_lines`, CLI `migrate`, `--line`.
- `pages/AgentsPage.qml`: add, remove, Undo, the two boxes.
- `Settings.qml`: `vAgentFiles` from the state.
- `manifest.json`: `agentInstructions` removed.
- `bench/preview/preview.sh`, `bench/preview/targets/voices.qml`, new
  `bench/preview/targets/folders.qml`.

## Measured (numbers, against the baseline)

- Preamble, from `bench/preamble_size.py` on the migrated data: main 856,
  sora 957, jarvis-ajc 6,837 characters, identical to Phase 8. Sora's
  system-prompt file is content-named, and her first turn after migration
  reused the same 957-byte file her turns before it had written.
- No prompt or turn path changed beyond where the instructions come from, so
  the latency gate is Phase 11's.

## Different from the plan, and why

- **Migration runs on every start**, not only until `.state.json` says it
  ran: it costs a few `lstat`s, and it gives a folder to an agent added
  meanwhile from an older build. The state still records a whole pass.
- **No folder is made when shell.json was not read.** If the file is
  missing, mid-write or broken at start, `Config` falls back to defaults,
  and copying their empty instructions would make an `instructions.md` that
  hides the real setting for good. Only `communal/` is made, the report says
  why, and nothing is recorded.
- **A failed removal keeps the agent**, rather than removing it and losing
  the folder's link to its settings.
- **Instructions starting with an HTML comment**: the folder reader strips a
  leading `<!-- … -->` (the starter comment), so such text would lose that
  comment where the old setting kept it. Not seen on any machine; written
  down rather than handled.
- The page's boxes take `--line` (one JSON line) rather than closing stdin,
  so they do not depend on how Quickshell closes it.

## Found along the way (bugs, surprises)

- **A typed turn was told stale instructions** (found live, pre-existing for
  settings too). The idle poll that re-reads settings and folders is below
  the listening gate, so with the microphone muted nothing was re-read;
  Sora, asked by typing after her file was changed, answered from her old
  instructions. With the microphone on, a turn typed straight after the save
  still beat the 2s poll. `handle_typed` now calls `refresh()` first; on the
  next install she answered the new instruction on the very next turn.
- **An instructions box drawn before its folder existed** (found by the new
  `folders` preview): a new card appears before `agents create` finishes, so
  its first save went in with base `missing` and was refused. The page now
  re-reads its boxes after every folder operation.
- My own review before the live run found: migration would have copied the
  defaults' empty instructions when shell.json could not be read; a read
  that started before a save and finished after it would put the old text
  and stamp back in the box; and removing one of two entries sharing an id
  (a hand edit) would have removed both. All fixed and tested.
- **Mutations**: each of 13 guards was removed in turn and a test went red
  for every one: never overwrite, an emptied file stays empty, the
  settings-read guard, record only when complete, snapshot only existing
  files, the cache filled before the size comparison, the main agent told
  its file, the extra agents told theirs, refresh order, `all_agents` keeps
  the switched off, the startup guard, the JSON line must be a string, and
  the typed-turn refresh. One survived the first round (the snapshot guard)
  and got its own test.

## Not verified (what was skipped, and why)

- **A spoken check with Sora.** The checks were typed turns on the real
  daemon: she answered in four sentences to "Explain how a refrigerator
  works" under her migrated instruction, and in one word ("Compression.")
  with her file briefly changed to ask for one word, which proves she is
  told the file. Her original text was put back with `agents revert` (the
  stamp is the original's), and the three test chats were deleted. Asking
  her out loud is left for you.
- **Theo's and Hazel's replies "unchanged"** were not compared turn by turn;
  their folders exist, their preambles are byte-for-byte the Phase 8 sizes,
  and their instructions are empty in both places.
- **Codex review**: not run (usage limit), as above.
- The box (`install.sh` unchanged).

## Going back (what an older build sees after this phase)

Checked live (A10-4): `dev` at 2eeb919 was installed over the migrated
data. It started cleanly, ignored the folders, and Phase 8's
`preamble_size.py` against its code gave Sora 957 characters: shell.json
still holds every instruction as it was at the upgrade. **An instruction
changed on this build is not seen by an older one** (it lives in the file),
and an agent added on this build has no `instructions` in its entry. Phase
10 was installed again afterwards.

## Open issues, for the next phase

- Codex review of this phase (after its limit resets).
- `voiceAgents[i].instructions` is still in saved entries; strip it one
  release after this.
- Sora's instructions history holds three test versions from the live check
  (a one-word instruction, each reverted); harmless, and visible once Phase
  12 shows history.
- The plan's `agentvoice agents export` is not built (Phase 12 or later).

## Live checklist: what was said, what happened

No voice from me. On the installed build, with everything idle:

- `agentvoice agents migrate --dry-run` (from the checkout, read only):
  would make communal and three folders; Sora's 24 characters copied.
- Install → the journal printed the four `agent folders: … made …` lines
  and one `agent files:` line; `agents list` shows main, sora and
  jarvis-ajc, Sora's instructions 24/2000, nothing changed outside;
  `.state.json` says `migrated: 1`; folders 0700, files 0600; shell.json's
  hash and mtime unchanged.
- The file's text equals the old setting for all three (compared in
  process, not printed).
- Typed to Sora (mic off, then on): see "Not verified" above.
- `dev` 2eeb919 installed over the data and back: see "Going back".
- Shell restarted so the new Agents page is the live one.
