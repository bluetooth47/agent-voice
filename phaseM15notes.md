# Phase M15: Communal: who gets it, preview, import, history

Written 2026-11-22, unattended (started by the runner script). Branch
`phase-m15`, cut from `phase-m14` at 2cd2bcd. Result commit: the notes commit
on top of bf3945d, pushed to `fork/phase-m15` only; `dev` fast-forwarded to it
and pushed to `fork`. Model: Claude Opus 5.5 (tier B in the plan). **This is
stop point 3.**

Commits:
- bf3945d: the phase, including the fixes my own re-read and the preview
  found (listed under "Found along the way");
- then these notes.

**Codex review: bypassed (user decision, 2026-11-22).** Codex was not run, for
review or anything else. In its place I re-read the whole diff before the
commit; what that found and fixed is under "Found along the way". Nothing in
this phase has been reviewed by a second model.

Deployed: **yes**, once, through `bin/agentvoice-deploy --install bf3945d` (its
strict check green). It replaced M14's ed12962. The daemon was idle: state
`listening`, no open mic, every agent idle, no task. **The way back to before
M15 is `bin/agentvoice-deploy ed12962`** (see "Going back").

Installed: **yes**: "Build 0.2.0 (bf3945d), replacing 0.2.0 (ed12962)". The
daemon, the hook and the CLI changed. `install.sh` did not change.

**Shell restart needed** (`pages/CommunalPage.qml`, new `ui/FileHistory.qml`
and `ui/CommunalImport.qml`, `ui/PromptPreview.qml`, `Settings.qml`'s
`goTo`). Not run. Until it is, the running shell has M14's Communal page: no
Who gets it or Preview tab, no History, no Import. Nothing is broken
meanwhile: `communalOff` is `[]`, so every agent takes Communal as before, and
the old page calls nothing that changed.

A copy of `shell.json` was taken before the deploy
(`~/agentvoice-notes/shell.json.before-M15`, 0600); after the install and the
live checks it was byte-identical. No live check wrote a setting, a communal
file or an agent folder.

`./bin/agentvoice-check`: green on bf3945d, and again on the final tree.
- **4330 tests** (was 4247; +83), 14 of 14 static checks, "the check wrote
  nothing in the tree: ok".
- Bare-runner variant (`AGENTVOICE_STRICT=1`, a venv with only
  requirements-dev): **green**, 4314 passed, 9 skipped (the same numpy-only
  skips as M13).
- Box: not run (`install.sh` did not change).

## What was built

**Who gets Communal: `communalOff`** (three parts: manifest default `[]`
(defaults-only, a list, like `crewQuarantine`), `runtime.DEFAULTS`, and the
switches on Communal → **Who gets it**, its one writing page). Ids are `main`
or an agent's id.
- An opted-out agent is told **no communal rules or defaults** and given **no
  communal skill**, through every path that builds what it gets:
  `agentfs.parts_from` (its prompt pieces and the skills index),
  `agentfs.plugin_dir` (a Claude agent's plugin folder; the communal folder is
  not even read), `skill_set` (each communal skill listed with why: "it takes
  nothing from Communal"), `catalog`, `roster`, `skillscan.lanes` and
  `agent_view` (Communal → Skills says "(takes nothing from Communal)"), and
  the daemon's native-skill switch (its CLI's own copy of a communal skill's
  name is no longer hidden, since Agent Voice gives it none).
- **Unreadable is everyone** (`Config.communal_off`: not a list, a bad id,
  more than 64, or settings that cannot be read), as Appendix A says: the
  rules may carry safety text.
- The daemon reads it fresh (`Daemon.takes_communal`) in `reconcile_parts` and
  in the plugin-folder cache key, so a switch reaches the next idle poll and a
  **warm process is let go** (the preamble or plugin folder changed).
- **Communal notes stay reachable** through the notes tools, and the page says
  why (they are looked up, not told); quarantine is what stops writing them.
- **Start fresh**, under each opted-out agent: `agentvoice chats new ID`, "Its
  current conversation may still hold what it was told before."
- The page writes a clean list: the ids of agents that still exist, so a
  removed agent's id never opts out a new one that takes it.

**Preview: the whole prompt, as sent** (`agentvoice agents prompt ID
[--json]`, Communal → **Preview** with one tab per agent).
- `Adapter.preamble()` is now `preamble_pieces()` joined: the one builder.
  `agentfs.prompt()` runs it over exactly what the daemon hands the adapter
  (parts, instructions, the Omarchy and Agent Voice skill lines, the found
  CLIs, a roster of the agents the crew links let it reach), with the adapter
  class's own `takes_skill_text` and `has_tools`.
- Each piece: label, source (`communal/rules.md`, `agents/sora/instructions.md`,
  …), a line on how it stands against the others (taken from what its header
  tells the model, nothing stronger: "Told that its own standing instructions
  win where the two differ"), its size; the total in characters and about how
  many tokens; for Claude, the skills it loads beside the prompt (not counted).

**Import** (`agentvoice agents import communal DIR [--confirm TOKEN]`,
`import-undo OP`, `import-history`; new `daemon/communal_import.py`; the page's
**Import…** beside Export, `ui/CommunalImport.qml`).
- DIR as Export writes it: `rules.md`, `defaults.md`, `skills/`. Anything else
  is listed as ignored and never read.
- **A dry run first**, writing nothing (no lock file, no journal): each file it
  would write, a diff for each text, each skill new / the same (left alone) /
  a clash, the agents it reaches (those that take Communal), the agents whose
  own skill of that name hides one, the problems, and a **token**. A problem
  refuses the whole import: a **link anywhere** (the folder itself, a text, a
  skill, inside a skill, dangling or not), a special file, a text over its
  1,500-character budget or over 256 KB, a skill over the bounds every skill
  keeps or with a problem of its own, a reserved name, more than 20 skills, a
  **clash** (nothing is ever replaced).
- **One all-or-nothing commit through M12's journal** (`kind: "import"`; the
  lock, the records and recovery are transfer.py's): the folder read once more
  under the lock and the token checked against that very read; old and new
  bytes of each text kept in `agents/.transfers/<op>.d/` (inside the orders
  guard); skills staged as `.t-<op>-a-<name>` and published by no-replace
  renames; texts written with a version named for the operation, so nothing
  reads "changed outside Settings". Recovery rolls back a record that never
  reached `published` (only what still hashes as imported) and finishes one
  that did; a text edited by hand in between is never overwritten (the record
  goes `stuck`, saying why).
- **Undo** for ten seconds on the page and `import-undo OP` at any time: only
  while every skill and text is exactly as imported; itself one record, not
  undoable. Side copies go once nothing can be undone.
- The commit is reached only from the import's `ToolConfirm` ("Import into
  Communal?", the files, who it reaches, what it replaces and that History
  keeps it); `--confirm` and the token are built in `commitImport()` alone
  (`test_confirms`' table has "agents import").
- **Audit**: `communal_import` / `communal_import_undo` (the op id and size)
  and one `skill_import` per skill (name and size). Never text.
- **Only the person**: the orders guard asks an agent running `agents import`
  or `import-undo` (and `communal_import.py`) at every level; `import-history`,
  `prompt` and `version` are reads and are not asked.

**History and Undo beside the Rules and Defaults editors** (`ui/FileHistory.qml`,
new `agentvoice agents version TARGET FILE VERSION [--json]`): when, who
(saved here, restored, kept, imported…), size; **View** shows the version and a
diff from it to now; **Restore** is the existing `agents revert … --base` the
editor's stamp, disabled while the file was changed outside Settings (that text
is in no version yet); **Undo** for ten seconds restores the version that was
newest before.

**Communal → Chats** stays as it was (a filtered view).

**Preview target** `communal` (seed `communal.seed.py`, config
`transfer3.json`), with a `shots:TAB` mode. `preview.sh`'s stub now logs
`chats new` rather than reach the real daemon, and no longer lets a preview
write `__pycache__` into the clone (below).

**Docs**: CODEBASE (communal_import.py, transfer.py, CommunalPage, the two new
pieces, the CLI rows), README ("Who takes Communal", "History and Import"),
FINDINGS §49.

## What was proven, and how

- **Tests** (`tests/test_communal.py`, 81, plus the shared tables): the setting
  read as ids, every unreadable shape (seven) read as nobody, unreadable
  settings as nobody, its three parts; an opted-out agent's parts with no rules,
  defaults or communal index entry; **an opted-out preamble byte for byte equal
  to an empty communal folder's, for all seven backends** (A11-1 itself still
  passes unchanged in test_preamble); its plugin folder without the communal
  skill (and none at all when nothing else is left); each communal skill's
  reason; its CLI's own copy no longer hidden; lanes, catalog and roster; the
  daemon: opting out reaches the next poll and lets the idle process go, and
  back; the plugin folder follows the switch, unreadable included; the native
  names. **The preview equals what the daemon sends, for Claude, Codex, Gemini,
  Antigravity, Copilot and both endpoint kinds, opted in and out** (the
  daemon's own `reconcile_parts` and `apply_extras` against `agents prompt`,
  same bytes, total = pieces + separators); sources and precedence; Claude's
  skills beside. Import: **a dry run changes nothing** (every file under the
  data folder hashed before and after); commit and undo round trip (live files
  back as they were, nothing "changed outside", no side copy left); undo refused
  after a text or a skill changed, twice, or of an undo; the token refused after
  the folder or Communal moved and for a malformed one; **the commit stages the
  very bytes its token was checked on**; links (the folder, a dangling text, a
  link inside a skill, a skill that is a link), oversize texts and files, a
  FIFO, a bad skill, a reserved name, 21 skills, a clash, nothing new; an export
  round trip; audit lines with no text (a canary absent from the log and the
  journal records); **real crashes** (a forked child dying with `os._exit`) at
  six points of a commit (begun, staged, one skill published, one text set,
  published, half finished) and one of an undo, each settled the right way with
  no `.t-` left; a hand edit during an interrupted import left alone (`stuck`);
  a forged record set aside; record validation; the CLI round trip; the guard
  asking for five import commands through `decide()` and not for three reads.
  History: a version's text and diff, bad names refused, restore round trip, a
  long diff cut and counted. QML (read, not run): History restores on the
  editor's stamp, never `agents write`, waits while changed outside; the import
  commits only from its confirm with the token; the Who page's clean list;
  plain text everywhere new; the preview stub's `chats new`. Eight existing
  tests updated for the new key, tabs, a second `file:` naming (FileHistory)
  and the new audit call.
- **Mutations: 29 run, 26 red, 1 hang, 2 removed, 1 survived** (scratch copies
  under /tmp, never the clone): parts_from, plugin_dir, the index, skill_set,
  takes_communal inverted, unreadable-opts-everyone-out, the daemon's parts,
  the plugin cache key, the native names, agent_view, lanes, the token, a link
  followed, the budget, a clash replaced, rollback leaving texts / the version /
  published skills, a hand edit overwritten, undo ignoring a changed text, no
  version saved, record validation, the guard's import words, the prompt not
  the builder's, the Who page keeping stale ids: all red. "The dry run takes
  the lock" **hung** the suite (the commit holds the lock and calls the dry run:
  a self-deadlock), which a person would see as never finishing, not as a pass.
  Two survived because the checks they removed were duplicates (a text link is
  refused by `O_NOFOLLOW` too; a reserved name by `parse_skill` too): I removed
  the duplicates. "Audit carries text" survived because `audit.record` itself
  maps any reason outside its fixed list to "?", so the module's own allow-list
  is what holds (and test_notes' AST check of every audit call).
- **Preview** (`preview.sh`, synthetic mouse events, real CLI, scratch data
  folder and shell.json, the real pointer never moved): **`communal` 24 of 24
  PASS** (a switch per agent; Sora's writes `communalOff ["sora"]`; Start fresh
  logged; Theo's prompt has the rules, the total adds up; Sora's says she takes
  nothing from Communal, has no rules or defaults and keeps her own
  instructions; History lists two versions, View diffs, Restore, Undo; Check
  lists two changes, the ignored README, reaches Theo and Hazel only, changes
  nothing; Import asks listing the files, commits, Undo takes it back).
  Regressions: M10 `tools` **29 of 29**, M11 `skills` **18 of 18**.
- **Screenshots** (`/tmp/m15`, not committed): Who gets it narrow 520×720 dark
  and 900×760 flexoki-light; Preview 900×760 dark; Rules with History open and
  the import's dry run, 900×760 dark and flexoki-light.
- **Live, on the installed daemon** (read-only, synthetic): `agents prompt` for
  main, sora and jarvis-ajc gives **1,301, 1,346 and 7,330 characters, the same
  numbers the daemon logged** for those agents after the restart; a dry run of a
  synthetic export against the real Communal folder listed its diff and token
  and **left the data folder byte-identical**; `import-history` empty; the
  installed hook asks for `import` (with and without `--confirm`) and
  `import-undo`, not for `import-history`, `prompt` or `version`; 29 journal
  lines since the restart, none with a traceback (read with `-o json`);
  `shell.json` byte-identical.

## Shared files touched, and where

- `daemon/wake_listen.py` (big shared, +22): `takes_communal()`, its use in
  `reconcile_parts`, in `plugin_dir_for`'s key and call, and in
  `native_skills_off`. Nothing in the turn loop.
- `daemon/agentfs.py` (big shared, +265): `NOT_COMMUNAL` and `skill_set`'s
  `communal_on`; `plugin_dir`, `parts_from`, `parts`, `preview`, `roster`,
  `catalog` honour it; `diff_lines`, `version`; `PIECES` and `prompt()`; the
  CLI verbs `version`, `prompt`, `import`, `import-undo`, `import-history`.
- `daemon/permission_hook.py` (security-critical, +6): `FOLDER_WORDS` gains
  `import`, `import-undo` and `communal_import.py`.
- `daemon/adapters/base.py`: `preamble_pieces()`; `preamble()` joins it
  (byte-identical: the golden file still passes).
- `daemon/transfer.py` (+11): `kind: "import"` dispatched in `_valid` and
  `_settle`. `daemon/runtime.py`: `communal_off_choice`, the default,
  `communal_off()`, `takes_communal()`. `daemon/skillscan.py`, `daemon/audit.py`
  (two kinds). New `daemon/communal_import.py`.
- `pages/CommunalPage.qml` (963 → 1,295): the two tabs, History, Import,
  the told count, the skills reason. `Settings.qml` (big shared, one line: the
  two tabs in `goTo`). `ui/PromptPreview.qml` (`how`, `chars`), new
  `ui/FileHistory.qml`, `ui/CommunalImport.qml`, `ui/qmldir`. `manifest.json`.
- `bench/preview/preview.sh`, new target and seed; CODEBASE, README, FINDINGS.

## Measured

FINDINGS §49, on the i7-1185G7, a scratch folder on the home disk (btrfs).
Opting out removes the communal pieces only: with 1,500-character rules and
defaults and three skills, a Claude Code main agent's preamble goes from 3,941
to 856 characters, Codex's and Gemini's from 4,506 to 856. It can only shrink;
confirmed. An import of two texts and one skill: dry run 1.2 ms, commit 32.7 ms,
undo 30.3 ms (medians); two texts and 20 skills: 5.0 ms, 151.3 ms, 48.5 ms.
`agents prompt` in-process: 3.1 ms. **"S on `sora`" was not rerun**: the real
Communal folder is empty, so opting Sora out changes nothing she is sent today
(1,346 characters either way, live).

## Different from the plan, and why

- **`communalOff` holds ids, `main` included**, as `crewQuarantine` does; the
  page drops ids of agents that no longer exist when it writes.
- **The preview is a new verb, `agents prompt`, not `agents preview`**: the
  Phase 12 preview (Agent details) lists pieces by their source text and
  builds its roster from every switched-on agent; the new one runs the
  adapter's own builder and follows the crew links like the daemon. The Agent
  details preview was left as it is (see open issue 4).
- **Import is into Communal only.** The plan's verb names Communal; an agent's
  own skills come in through `agentvoice skills import` (M11/M12). Asked for
  another target, the command says so.
- **A clash refuses the whole import** rather than replace a skill: the plan
  says "name clashes" are listed; replacing would need its own Undo of an
  overwritten skill. A skill identical to Communal's is "the same" and left
  alone.
- **The dry run's token** ties the confirm to exactly what was listed: the plan
  says "a dry-run list … then a confirm"; without a token the folder could
  change between the two.
- **The import is a new journal kind in transfer.py, not a call of M12's
  skill transfer**: one record covers texts and several skills, so it commits
  and rolls back as one (the plan's "one all-or-nothing commit"), using M12's
  lock, records, recovery loop and folder readers.
- **Start fresh is `chats new ID`**, which exists since Phase 15; the page
  offers it under each opted-out agent, always, since it cannot know whether
  the current conversation saw the rules.
- **History lists, views, diffs and restores; Undo after a restore** is a
  restore of the version that was newest before, on the stamp the restore
  returned.
- **Codex review bypassed** by the user's decision.

## Found along the way

- **My re-read of the diff found a check-then-use gap in the commit**:
  `commit()` checked the token against one read of the person's folder and
  then staged from a second read, so a file changed between the two would have
  been committed without being shown. One read now; a test changes the file
  right after the read and proves the old bytes are what land.
- **The History link was drawn over the editor** (the first light screenshot):
  a `SettingRow` lays out a single child. Each editor and its History are now
  one Column.
- **A preview run beside the check left `daemon/__pycache__` in the clone**,
  which failed the check's last line: the stub runs this checkout's CLI, and a
  target's seed imports this checkout's modules, both without
  `PYTHONDONTWRITEBYTECODE`. Both set it now. Earlier phases never ran a
  preview during a check, so it had not shown.
- **Two duplicate checks** in the import (a text link, a reserved name) were
  found by mutations that survived; removed, with a comment naming what holds.
- **The audit call first read `rec[...]` directly**, which test_notes' AST
  check of every `audit.record` refuses; it now passes plain names (op, name,
  byte counts), and `op` joined that test's safe list.
- **The Phase 12 preview's roster ignores the crew links** (it lists every
  switched-on agent; the daemon, since M8, only the linked ones). Found while
  making `agents prompt` match the daemon; not changed here (open issue 4).

## Not verified

- **The page in the real shell.** It needs `omarchy-restart-shell` (this stop
  point). Seen only in `preview.sh` with synthetic mouse events: a real
  pointer, the keyboard (Tab through the new tabs and toggles, Enter on
  History's header, Escape on the import confirm), and the Preview's agent
  tabs scrolling with many agents were not driven.
- **The plan's typed live check**: opt Sora out and she no longer follows a
  communal rule; opt her back in. It needs a communal rule written into the
  real Communal folder (which widens what every real agent is told) and a real
  settings write, the kind of live check an unattended run does not make
  (memory: M10). The real Communal folder is empty, so there is no rule to stop
  following today. Proven with the daemon in tests and with `agents prompt`
  live instead. At the stop point: put a harmless rule in Communal (say "End
  every answer with the word mango"), ask Sora something, switch her off on Who
  gets it, ask again (the next answer should not say mango; if the old
  conversation still does, Start fresh), switch her back on.
- **A real import into the real Communal folder**, and its Undo: only the dry
  run was run live. At the stop point: Export Communal, then Import that folder
  back (Check should say everything is the same), or import a one-skill folder
  and Undo it.
- **Start fresh on the real daemon** (logged in the preview, not run).
- **A warm Claude process let go by the switch on the real daemon**: tested
  with the daemon and a fake adapter, not by switching a real agent.
- **Crash recovery on the real daemon** (tested with real crashes of forked
  children; the installed daemon was not killed mid-import).
- **The installer box** (`install.sh` did not change).
- **The Codex review** (bypassed, not owed).

## Going back

`bin/agentvoice-deploy ed12962` from the clone, `./install.sh --yes` once the
daemon is idle, then `omarchy-restart-shell`. **First make sure no import is
unfinished**: `agentvoice agents import-history` lists none `begun`, `published`
or `stuck`, and `~/.local/share/agentvoice/agents/.transfers/` holds no
`*.open.json` (the M15 daemon settles any when it starts). An M14 daemon
**ignores `communalOff`**, so every opted-out agent is told the communal rules
and given the communal skills again (plan section 7.7: keep such an agent
stopped while the older build runs, or move what it should not get out of the
communal folder first). An M14 daemon reads an import record as one it did not
write and sets it aside (`.bad`), never acting on it, so an import cut short and
then downgraded would stay half done: a `.t-<op>-a-*` stage in
`communal/skills/` that no build lists, or a text the record would have put
back. Imported rules, defaults and skills stay where they landed; their History
holds the earlier texts, and an M14 page can Revert the newest. The side copies
in `agents/.transfers/*.d/` stay, unread. An M14 guard does not ask an agent
running `agents import` (the verb does not exist there).

## Open issues, for the next phase

1. **Codex review bypassed** for M15 (user decision, 2026-11-22). M12 stays
   "review owed".
2. **A clash refuses the whole import.** Should Import offer "replace
   Communal's" (with the replaced skill kept for Undo), or skip the clashing
   skill and import the rest?
3. **Import into an agent's own folder** (rules do not apply there, but its
   instructions and skills could) is not offered. Wanted?
4. **The Agent details preview (Phase 12, `agents preview`) lists every
   switched-on agent in the roster**, ignoring the crew links the daemon has
   honoured since M8; `agents prompt` (Communal → Preview) follows them. Point
   the Agent details tab at `agents prompt` too, and retire `agents preview`?
5. **`communalOff` is all or nothing.** An agent that wants the rules but not
   the defaults, or the rules but not a communal skill (that one has its own
   switch already), has no setting. Enough?
6. **Start fresh is offered under every opted-out agent**, whether or not its
   current conversation ever saw the rules (the page cannot tell).
7. **The import is a text-and-skill folder only**: notes and chats are not
   imported (the plan names rules, defaults and skills).
8. **The dry run is asked about by the guard** when an agent runs it (only its
   token separates it from the commit). Allow agents the dry run?
9. **Carried, still open**: M14's 2–7; M13's 2–9; M12's 2–7; M11's 1–7; M10's
   1–8; M9's 2–7; M8's 2–11; M7's 2–7; M6's 1, 3, 4; M5's 1, 4–6; M4's 4–13;
   the Voice library trash icon (M25); M0's small test and bench fixes; agy's
   `carries_session_across`; the runner's sandbox test command.

## Live checklist: what was done, what happened

Nothing was said into the microphone and no turn was typed.
- Before the deploy: state `listening`, no open mic, every agent idle, no task;
  `shell.json` copied (0600).
- `bin/agentvoice-deploy --install bf3945d`: "deployed bf3945d115f9. The way
  back: bin/agentvoice-deploy ed12962efc80"; "QML changed: run
  omarchy-restart-shell? (not run)"; the installer: "Build 0.2.0 (bf3945d),
  replacing 0.2.0 (ed12962)". The daemon came back to `listening`.
- After: `agents prompt` for three agents equal to the daemon's logged sizes; a
  dry run of `/tmp/m15live/exp` against the real Communal folder, data folder
  byte-identical; `import-history` empty; the installed hook asks for the three
  writing commands and not the three reading ones; no traceback in the journal;
  `shell.json` byte-identical to the copy. No shell restart.
