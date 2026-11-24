# Phase M28: Settings search, and first-run setup

Written 2026-11-23, unattended (started by the runner script). Branch
`phase-m28`, cut from `phase-m27` at dfddc1a. Result commit: the notes commit
on top of 8efa5e0, pushed to `fork/phase-m28` only; `dev` fast-forwarded to it
and pushed to `fork`. Model: Claude Opus 5.5 (high).

Commits:
- 8efa5e0: the phase;
- then these notes.

**Codex review: bypassed (user decision, 2026-11-22).** Codex was not run, for
review or anything else. In its place I re-read the whole diff before the
commit and ran 17 mutations of the new code against the new tests and
preview targets (all 17 red); what the re-read found is under "Found along
the way". Nothing in this phase has been reviewed by a second model.

Deployed: **yes**, `bin/agentvoice-deploy --no-install 8efa5e0` with the
daemon idle (state `listening`, open mic empty, every agent idle), its strict
check green (5327 passed): "deployed 8efa5e012cc0. The way back:
bin/agentvoice-deploy ca3a9a4adbf9".

Installed: **no, on purpose.** No daemon file changed (`git diff --name-only
ca3a9a4 8efa5e0 -- daemon bin desktop install.sh requirements*.txt
models.lock` is empty), so the installed service is current: `agentvoice
about` says "different builds, but no daemon file differs between them, so
the service is current".

**No setting was written and no turn was run.** `shell.json` was not touched
(mtime Nov 22); no setup marker exists in `~/.local/state/agentvoice/` (only
`crew-layout.json` and `deploys.log`). Every preview used scratch config,
state, runtime and data folders.

**Shell restart needed** (`Settings.qml`, `Setup.qml`, `ui/SettingsSearch.qml`,
`ui/SettingsIndex.js`, `ui/SearchField.qml`, `ui/AgentTabs.qml`, every page).
Not run. Until it is, the running shell has no search box and no setup.

`./bin/agentvoice-check`: green on the final tree (exit 0, every line ok).
- **5327 tests** (+21: `tests/test_settings_search.py` 17, four more in
  `test_settings_pages.py`), 14 of 14 static checks, "the check wrote nothing
  in the tree: ok". 6 min 17 s.
- The first full run of the phase (before the re-read fixes) was green too:
  5326.
- Box not run: `install.sh` did not change.
- Bare runner not run: the new tests read files only (json, re, the existing
  `qml_scan`), no wheel.

## What was built

**Settings search** (feedback item 22, "where is the pause setting?").

- `ui/SettingsSearch.qml`: a box at the top of the sidebar, above the page
  list; **Ctrl+F** from anywhere in the overlay (`Settings.qml`'s key
  handler). Typing searches (120 ms debounce); up to twelve results drawn
  over the page, each with its path ("Conversation › Advanced", "Agents ›
  Sora", "Agent details › Hazel › Advanced") and, for a control hidden for
  the current choice, "shown when …". Up/Down move, Enter opens, Escape
  clears (an empty box lets Escape close the overlay as before).
- `ui/SettingsIndex.js`: 107 entries, plain JSON between `BEGIN/END ENTRIES`:
  every manifest key (77) and every defaults-only key (12), every
  voiceAgents field with a page (as `key + field`, one result per agent, or
  `field` alone: two), and 16 actions (Mute mic, the service switch, Test my wake
  word, Pace, Voice commands, Voice library, Delete all saved chats, Preview
  the readout, Clear stats, Keys, Repair, Remove, Environment variables,
  Copy diagnostics, Check for updates, Run setup again). Each page is a
  result by its own name. Ranking: a label word, then a synonym, then the
  key, the agent and the page; every query word must fit; a label starting
  with the whole query first. "pause" gives the pause that ends a turn, then
  the shorter pause, then Mute mic.
- `Settings.reveal()`: `goTo(page, agent, tab)`, then finds the control by
  objectName (inside `agent-<id>` on the Agents page), retried every 120 ms
  for about two seconds while the page builds; `flip()`s every folded
  ancestor (`AdvancedSection`, a foldable `Card`, an agent's controlled
  `HeaderStrip`); scrolls to it; outlines it for 2.6 s (`flashBox`, placed
  again every 150 ms while it shows, in the scroller's content); focuses the
  first thing under it that takes Tab focus, else the card (so Escape still
  works). A control not on screen (an openWakeWord threshold while Vosk
  listens) outlines the nearest thing that is and says why under the box. A
  page change clears the outline and the note.
- **Anchors**: 84 `objectName` lines added across the pages (`set-<key>` on the
  row, `agent-<field>` inside an agent's card, which is `agent-" + agentId`;
  `agent-speed` is conditional on `isMain` on its two controls, because a
  card has one of them visible), alongside the ones that existed
  (`pauseKnob`, `gateRiseKnob`, `commandsRow`, `crewMap`, …): 98 distinct
  anchors in the index. Names only: no control's
  behaviour changed.

**First-run setup** (`Setup.qml`, root level).

- Drawn in place of the sidebar and page while the overlay's `mode` is
  `"setup"` (title "Set up Agent Voice"); built each time it is shown, so
  each step starts from what is set now.
- **1 Microphone**: the meter with the gate line, Fixed / Follows the room,
  the gate level; **Start Agent Voice** while the service is known to be off
  (the overlay's own `toggleService()`, with its guards). **2 Wake word**:
  the engine (one not installed is not written: its installer is offered
  instead, which closes setup), the phrase (a box plus the nine suggestions,
  checked as the Agents page checks it; openWakeWord's model on that
  engine), and **Try it**: the daemon's own `wake-test`, stopped by setup
  after three tries, "N of 3 tries woke it" with the gate advice when you
  never reached it. **3 Your agent**: the programs found
  (`agentvoice about backends --json`, M26) plus Omarchy's default, the ones
  not found named, "installed is not signed in"; the name; the wake phrase
  shown with a Change link back to step 2. **4 Done**: what was chosen, and
  Ctrl+F.
- **Writes**: only `adaptiveGate`, `micThresholdDb`, `engine`, `phrase`,
  `owwModel`, `mainProgram`, `mainName`, through `s.put`, each only when it
  differs from what is set. Never an agent folder, another agent, an
  endpoint, a permission level or a voice. **Skip setup** writes the marker
  and nothing else.
- **When it shows by itself**: once, for a summons that asked for nothing (no
  page, focus, chat or card id), when every one of these has answered and
  says fresh: no marker; settings and the manifest's defaults loaded; none of
  `mainName`, `mainProgram`, `phrase`, `engine`, `owwModel` changed; no
  `voiceAgents`; agent folders read and none but `communal` (the daemon makes
  `agents/main` the first time it starts); the engine installed;
  `agentvoice is-active` has answered, and said no. `install.sh` never starts
  the service, so a real first install meets all of them.
- **The marker** (`$XDG_STATE_HOME/agentvoice/setup.json`, `{version,
  status: open|skipped|done|dismissed, step, at}`), written by `FileView`,
  with a `mkdir -p` and one retry when the folder is missing. Written the
  moment setup is shown, so Escape mid-way never brings it back by itself.
- **The way back in**: About → **Run setup again** (from step 1), the
  Overview's **Setup is not finished** line while the marker says open or
  skipped (from the step it was left at), with **Not now** (marker
  `dismissed`), and the summons `{"mode":"setup","step":"wake"}`.

**Also**: `ui/SearchField.qml` gains `submitted`, `stepped` and `stepsList`
(off by default, so the Chats page's box passes Up/Down on as before) and
`focusField()` selects the text; `tests/qml_scan.py` lists `Setup.qml` in
`overlay_qml()`, so every QML rule (plain text, colours, confirms) covers it.

**Preview**: targets `search` (38 checks) and `setup` (`fresh` 12,
`configured` 6, `reminder` 7, `walk` 24; or one step by name); both take
`,narrow` (the card drawn 500 px). `preview.sh --service-off` (a scratch
runtime folder with no state file and `is-active` answering no) and
`<out>.setup.json`; `configs/fresh.json` (the widget entry and nothing else).

**Docs**: README (setup and Ctrl+F under Install; the layout), CODEBASE (both
features, the anchor rule, the targets), CHANGELOG (M28).

## What was proven, and how

- **Tests** (`tests/test_settings_search.py`): every manifest and
  defaults-only key has exactly one entry; every voiceAgents field with a
  page has one; every entry's page is in the sidebar and its tab is one
  `goTo` opens; **a key's entry names the page that writes it**
  (`_key_writers`, the one-page tests' own reading); an agent field's page is
  its `FIELD_HOMES` home and its key its twin; every anchor is an objectName
  on its page exactly once (or the two sides of one `isMain` condition);
  agent-scoped anchors are inside `AgentBlock` and nothing else is; the pause
  entry; old deep links (`display`, `history`, every tab, `focus`) in
  `open()`/`goTo()`; Ctrl+F wired; results drawn as plain text; reveal walks
  only the page loader. `test_settings_pages.py`: Setup writes exactly
  `SETUP_KEYS` (both ways, including a computed key and `omarchy bar set`),
  reaches no agent list, folder, tool, skill or launch function and runs no
  process but `about backends`; a mutated copy with one more put is caught;
  `setupFresh` holds all fifteen guards and the marker is written on show.
- **Mutations: 17 run, 17 red** (scratch copies in /tmp, never the clone): an
  entry dropped; an entry on the wrong page; an anchor renamed on its page;
  an anchor duplicated; an agent entry pointing outside the card; the card's
  name dropped; Setup writing `voice`; Setup running `agents create`; the
  `display` alias gone; `who` dropped from `open()`'s tabs; `setupFresh`
  without the folders; without the defaults; setup taking deep links; the
  marker not written on show; Ctrl+F not focusing; results as AutoText; and
  (preview) setup's stale-test guard removed, which the `walk` target catches
  twice.
- **Preview `search`, 38 of 38** (crew3 config, showcase state, the pointer
  never moved, keys through QtTest's TestEvent): a plain summons of a
  configured install opens the Overview; Ctrl+F from the card focuses the
  box; "pause" (typed key by key) puts the pause first, Mute mic below, path
  "Conversation › Advanced"; Down/Up; Enter opens Conversation, unfolds the
  timings, outlines `pauseKnob`, puts the keyboard on its slider, scrolls,
  clears the box; "model" gives Theo's, Sora's and Hazel's, and Sora's opens
  her card with the model row outlined inside it; Hazel's Extra flags opens
  her Advanced tab; Browser opens Communal → Tools; the openWakeWord threshold
  under Vosk opens Listening and says why it is not there; About by name;
  the note clears; nonsense matches nothing; the five old deep links; **the
  write log empty at the end**.
- **Preview `setup`**: `fresh` (fresh config, `--service-off`, the state
  folder removed first): setup opens by itself at step 1 with the start
  button and the empty meter's reason; no setting written; marker `open`
  (folder made on the first save); Start logs `agentvoice toggle`; Skip
  goes to the Overview with the reminder, no setting, marker `skipped`/mic;
  summoned again, setup does not come back. `configured` (crew3,
  `--service-off`): service known off, folders read, not called fresh, no
  marker, no reminder. `reminder` (a marker left at step 2): not opened,
  "Left at step 2 of 4", Not now hides it and writes `dismissed`, no
  setting; About's Run setup again opens step 1. `walk` (fresh config,
  showcase state): About → Run setup again; the meter live; Follows the
  room; the phrase chip; an earlier test's "done" left in the file is not
  shown and counts for nothing after Start; the fake test's tries counted
  and stopped at three ("2 of 3 tries woke it", Try again), `wake-test start`
  and `stop` logged; Claude Code and Codex offered (preview.sh's fakes), the
  rest named as not found; Codex; the name typed; Done says "ada, on Codex"
  and the gate; Open the settings → Overview with no reminder; **the write
  log holds exactly `adaptiveGate`, `phrase`, `mainProgram`, `mainName`**, all
  on the widget's entry; marker `done`.
- **Existing targets after the change**: `conversation` 35/35 (its own
  focus deep link still works beside search's), `other` 26/26, `about`
  29/29 (after the fix below), `chats drive` 32/32 (the sidebar keys, its own
  search box), `confirms` ran its whole sequence with the same writes M26
  recorded.
- **Screenshots** (`/tmp/m28/shots`, not committed): setup steps 1–4 at
  1100×760 dark, step 2 in flexoki-light, steps 1 and 3 narrow (card 500 px)
  in flexoki-light; search results dark and narrow light; the landed knob in
  light (the slider's focus ring visible; the outline had faded by the shot).

## Shared files touched, and where

- `Settings.qml` (big shared): `serviceKnown` in the probe; `open()` (the
  setup summons, `plainOpen`, the tab list fix, `offerSetup()`); `goTo()`
  (clears the outline and note); new sections "first-run setup" and
  "settings search"; Ctrl+F; the card's width and title for setup; the search
  box above `SidebarNav`; the hint line; `flashBox` in the scroller; the setup
  Loader.
- `pages/AgentsPage.qml` (big shared): `objectName`s only (the card, 15
  controls, Add an agent).
- `pages/AgentDetailsPage.qml` (big shared): six `objectName`s.
- `pages/OverviewPage.qml`: the setup reminder, two `objectName`s.
- `pages/AboutPage.qml`: Run setup again.
- Other pages: `objectName`s only. `ui/AgentTabs.qml` (a guard),
  `ui/SearchField.qml`, `ui/qmldir`, `tests/qml_scan.py`,
  `tests/test_settings_pages.py`, `bench/preview/preview.sh`,
  `bench/preview/targets/about.qml`.
- New: `Setup.qml`, `ui/SettingsSearch.qml`, `ui/SettingsIndex.js`,
  `tests/test_settings_search.py`, two targets, `configs/fresh.json`.
- Not touched: anything in `daemon/`, `bin/`, `install.sh`, `manifest.json`,
  `runtime.py`, `Panel.qml`, `Hud.qml`.

## Measured

Nothing. No speed or size claim is made.

## Different from the plan, and why

- **The wake phrase is on step 2, not step 3.** The plan lists it under
  "first agent"; it is one key (`phrase`), and step 2's test needs it, so
  step 3 shows it with a Change link back. One writer in setup, not two.
- **"Say it three times"** is the daemon's existing ten-try `wake-test`,
  stopped by setup after three tries. No daemon change, so no install.
- **Setup does not install engines in place.** Choosing one not installed
  writes nothing and offers its installer, which closes the overlay (as the
  Listening page's does); the Overview offers to finish afterwards. The plan
  says nothing either way; writing an engine the daemon would fall back from
  is the "control that silently does nothing" CLAUDE.md forbids.
- **Not an endpoint in setup.** The agent step offers the programs found;
  an endpoint is set on the Agents page (setup says so when one is set).
- **The search index has actions too** (Mute mic, Copy diagnostics, …): a
  person searching "mute" or "uninstall" means a control, setting or not.
- **"Focuses the control"** lands on the first thing under it that takes Tab
  focus; a `ToggleRow`'s switch takes none today, so for a switch the card
  takes the focus and the outline marks the switch (open issue 2).
- **`preview.sh` gained `--service-off`**, the targets `,narrow`: the plan's
  "fresh state" needs a service that has never run, and the M18–M26 narrow
  shots only cropped a wide card.

## Found along the way

- **Pre-existing: a deep link to Communal's "Who gets it" or "Preview" tab
  opened Rules.** `open()`'s tab list predated M15's two tabs, though
  `goTo()` knew them. Fixed, with its test; found by the `search` target's
  old-deep-link checks.
- **Pre-existing: the `about` target expected "M26" as the newest changelog
  entry**, so it has failed one check since M27 added its entry. It now
  checks the entry's shape.
- **`AgentTabs.reveal()`'s delayed call ran on a destroyed page** (a
  TypeError in the log) when an agent's tab was opened and left within a
  frame, which search does. Guarded.
- **My re-read of the diff** found three things, each fixed before the
  commit with a check that fails without it: setup's wake test would have
  taken a previous test's result left in `wake-test.json` (the Listening
  page's, say) for its own, and could have stopped its own test at once on
  it, because the overlay re-reads the file every second; `setupFresh`
  trusted `changed()`, which reads every key as unchanged until the
  manifest's defaults have loaded; and the new Up/Down handlers would have
  swallowed those keys in the Chats page's search box too.
- **The Done step showed what the daemon runs this second** (the state
  file), not the program just chosen; the `walk` target caught it.
- **Index labels drifted from the page labels** in 16 places ("Discard
  shorter than" for "Ignore a turn shorter than"); aligned, the old words
  kept as synonyms. The rest differ on purpose (the index adds context:
  "Readout size" for the page's "Size").
- **Binding-loop warnings in `StatusCard.qml:132` and `SettingRow.qml:160`**
  appear in preview logs; the M27 build logs the same, so pre-existing. Not
  touched.

## Not verified

- **Both features in the real shell.** Needs `omarchy-restart-shell` (not
  run). Seen only in `preview.sh`.
- **The plan's keyboard check, "find pause and land on the control", in the
  real shell.** Done in the preview with synthetic keys (Ctrl+F, typing,
  Enter); the real-shell walk is the user's.
- **Setup on a real fresh install**: by design it does not appear on this
  machine (agent folders exist). Driven in the preview with `--service-off`
  and an empty scratch data folder only. The box was not run (`install.sh`
  unchanged).
- **Setup's wake test with a real voice**: driven with a fake
  `wake-test.json`; the daemon's side is M22's unchanged code.
- **Start Agent Voice from setup, and an engine's installer from setup**,
  on the real desktop: logged by the preview stubs only.
- **Screen-reader names** of the search results and setup controls (set,
  not heard).
- **The Codex review** (bypassed, not owed).

## Going back

`bin/agentvoice-deploy ca3a9a4adbf9` from the clone, then
`omarchy-restart-shell`. No install needed either way (no daemon file
changed). Nothing stored changes: no setting was added, moved or renamed. An
older build does not read `~/.local/state/agentvoice/setup.json`; delete it
to have setup offered again (it is offered only on a fresh install anyway).

## Open issues, for the next phase

1. **Codex review bypassed** for M28 (user decision, 2026-11-22). M12 stays
   "review owed".
2. **A switch found by search does not get the keyboard**: `ToggleRow`'s
   `ToggleSwitch` takes no Tab focus, so the card does and the outline marks
   it. Left for M29's keyboard pass.
3. **Setup's Start button toggles** (the overlay's one start path, with its
   guards), offered only while `is-active` has said no. A service started
   elsewhere in the two seconds before the next poll would be stopped by a
   click. Default: kept (a fresh install's service is never running). A
   `start` verb would close it.
4. **The reminder after "Run setup again"**: running it on a configured
   install and closing it with Escape leaves "Setup is not finished" on the
   Overview until finished or Not now. Default: as built (it was started).
5. **Index labels are kept by hand.** The tests hold coverage, pages and
   anchors, not that a label matches the text on screen. Default: as built;
   a label check could read each anchor's `label:`.
6. **Setup offers no endpoint and no extra agents.** Default: as built (the
   Agents page has both; Done points there).
7. **Carried, still open**: M27's 2–9; M26's 2–6; M25's 2–5; M24's 2–6;
   M23's 2–7; M22's 2–7; M21's 2–7; M20's 2–8; M19's 3–6; M18's 2–6; M17's
   2–7; M16's 2–9; M15's 2–8; M14's 2–7; M13's 2–9; M12's 2–7; M11's 1–7;
   M10's 1–8; M9's 2–7; M8's 2–11; M7's 2–7; M6's 1, 3, 4; M5's 1, 4–6; M4's
   4–13; M0's small test and bench fixes; agy's `carries_session_across`; the
   runner's sandbox test command.
