# Phase M29: Consistency audit, keyboard and light theme

Written 2026-11-23, unattended (started by the runner script). Branch
`phase-m29`, cut from `phase-m28` at 7cd1529. Result commit: the notes commit
on top of 137f775, pushed to `fork/phase-m29` only; `dev` fast-forwarded to it
and pushed to `fork`. Model: Claude Opus 5.5 (high).

Commits:
- 6d453d3: the phase;
- 137f775: fix, `bin/agentvoice-check` restored (below);
- then these notes, with the screenshot sheets.

**Codex review: bypassed (user decision, 2026-11-22).** Codex was not run, for
review or anything else. In its place I re-read the whole diff before the
commit, ran 12 mutations of the new tests (all red; two of them first came
back green and exposed test bugs, fixed, below), and re-ran 23 existing
preview targets against the change. What the re-read found is under "Found
along the way". Nothing in this phase has been reviewed by a second model.

Deployed: **yes**, twice, each with the daemon idle (state `listening`, open
mic empty, every agent idle) and its strict check green (5337 passed):
`bin/agentvoice-deploy --no-install 6d453d3` ("The way back:
bin/agentvoice-deploy 8efa5e012cc0"), then `--no-install 137f775` ("The way
back: bin/agentvoice-deploy 6d453d384bc0").

Installed: **no, on purpose.** No daemon file differs from the installed
build (`git diff --stat ca3a9a4 137f775 -- daemon bin desktop install.sh
requirements*.txt models.lock` is empty): `agentvoice about` says "different
builds, but no daemon file differs between them, so the service is current".

**No setting was written and no turn was run.** `shell.json` was not touched;
every preview used scratch config, state, runtime and data folders, and every
sheet and walk run checked its write log empty.

**Shell restart needed** (every page, most of `ui/`, `Settings.qml`,
`Setup.qml`, `Chats.qml`). Not run. Until it is, the running shell draws the
M28 overlay.

`./bin/agentvoice-check`: green on the final tree (exit 0, every line ok).
- **5337 tests** (+10: `tests/test_keyboard.py`), 14 of 14 static checks,
  "the check wrote nothing in the tree: ok". 6 min 41 s.
- Green before each commit (three runs, plus the two deploys' strict runs).
  The first full run of the phase had one red test, an exact count my change
  moved (`test_the_limit_note_links_to_the_longest_turn`, below).
- Box not run: `install.sh` did not change.
- Bare runner not run: the new tests read files only (`re` and the
  existing `qml_scan`), no wheel.

## What was built

**1. The old pieces are gone from every page** (plan: "no page still uses the
old `SettingsGroup` / `KnobRow`").

- `ui/SliderRow.qml` replaces the root-level `KnobRow.qml` (28 uses on seven
  pages, Setup and the endpoint editor). Same API and behaviour (VoiceSlider,
  commit on release, typed number, `labels`, `displayDivisor`), but
  SettingRow's shape: `hint` under the slider (was `description`), a
  `disabledReason` that dims the row, disables the slider and says why, the
  label as plain text, "?" and "reset" reachable by keyboard. The four sliders
  that dimmed themselves by hand (`followUpMs`, `bargeFactor`,
  `narrationSilenceS`, `hudLingerMs`) now use `disabledReason`;
  `narrationSilenceS` gains its reason ("Only while it talks while it
  works."), which it never had.
- Every `SettingsGroup` (16 on Overview, Voice, Other settings, About and
  Listening) is a `Card`, with the title inside the box in sentence case like
  every page built since M5. The Overview's "TODAY" heading is a card title's
  weight and case ("Today", "The last 7 days").
- `KnobRow.qml` and `SettingsGroup.qml` are deleted, so a new use cannot load.
  The two preview targets that used KnobRow (`knob`, `gallery`) use SliderRow.
- Wake test card on Listening: its first row repeated the card's title ("Test
  my wake word" twice); the row is "How it is tested".
- Communal → Skills: a "No shared skills yet." line in Qt's default size (the
  largest text on any page) above a lane saying the same is gone; five status
  lines on Agents and Agent details that had no size are body text.
- Setting labels wrap to two lines before they are cut: in the narrow layout
  a label beside its switch read "Show what it heard and what it …".

**2. The keyboard pass.**

- `ui/ActionButton.qml`: Omarchy's Button with `focusable: true` and an
  accessible name (its text, else its tooltip). Omarchy's Button is
  unfocusable unless told, and 29 buttons on the pages could be pressed only
  with a pointer (all eight on Listening, the Agents cards' Test, every voice
  library row, the endpoint editor's four, Overview's Mute mic and Stop, Open
  mic's Turn on, …). Every Button in `pages/`, `ui/`, `Setup.qml` and
  `Chats.qml` is one now (146 replaced; the ones that already had `focusable:
  true` keep it, harmlessly). Exceptions, held by the test: the chips inside
  SegmentedChoice, TabStrip, ToggleChips and AgentTabs (the control is one
  Tab stop and the arrows walk it), and the permission card's **Allow once**
  and **Allow all in this chat**, which stay pointer-only (open issue 2).
  **Deny** is reachable.
- `ui/FocusSwitch.qml`: Omarchy's ToggleSwitch with Tab focus, Space/Enter,
  an accent outline and a named check box. No switch could be reached by
  keyboard before; `ToggleRow` uses it (named after the row's label), as do
  the Overview's service switch, the Crew map's Ask me first and SkillCard.
  This closes M28's open issue 2: search landing on a switch now puts the
  keyboard on it.
- `ui/TextLink.qml`: "?", "reset", "Listening settings ›", "last chat ›" and
  the undo toast's ×, which were a Text with a MouseArea: Tab, Enter/Space,
  an accent outline, a name ("Reset Follow-up window", "Explain Level").
- Enter on a slider opens its number for typing (the pointer clicks it);
  Enter or Escape gives the keyboard back to the slider.
- The Overview's agent cards (`StatusCard` when clickable) and a conversation's
  two folds (`ExchangeItem`: the question between agents, what it thought)
  take Tab and Enter.
- **The page follows the focus** (`Settings.qml`, `followFocus`): Tab moved
  the focus down a long page and left the page where it was. It scrolls only
  when the focused thing's middle is out of view, so a click (always on
  something in view) never moves the page under the pointer.
- **Accessible names** on every composite that takes Tab: SegmentedChoice
  (both its one-line and wrapped forms), TabStrip, ToggleChips,
  CompactSelector, AdvancedSection, HeaderStrip, a foldable Card's head,
  SidebarNav, AgentTabs, MiniBars, FileHistory, DraggableCard, SkillCard, the
  Chats list rows, the Conversation page's "Raise it". A control with no name
  of its own inside a `SettingRow` (chips with no label, Omarchy's Dropdown,
  which this project cannot edit) is given the row's label (`lendName`); a
  button's own text is never replaced.

**3. The inventory compared** (plan: "every key from the start still has
exactly one working home, and no setting was removed"). `bench/key-inventory.py`
against the M1 snapshot in `phaseM1notes.md`:

- **Keys**: 68 at M1, 89 now; none of the 68 gone; every one of the 89 has
  exactly one page. The 11 that moved, moved on purpose and with their names:
  `keepHistory`, `saveChats`, `chatRetention` to Chats (M18); `hud`,
  `hudLingerMs`, `yieldToRecorders`, `logSpeech`, `agentsPanel` to Other
  settings (M26, the Display page renamed); `desktopTools`, `browserTools`,
  `omarchySkill` to Communal (M5, bug E).
- **voiceAgents fields**: 20 at M1, 26 now; none gone; each on one page.
- **Manifest** (schema + defaults): 68 keys at `phase-m0`, 89 now, none
  removed. **`runtime.DEFAULTS`**: 71 then, 92 now, none removed.
- The script printed `mainTools` and `mainSkillsOff` as having **no** home,
  and dropped the `tools` field: since M10/M11 they are written through
  overlay functions (`setAgentTool`, `setAgentSkill`, M17's `setAgentField`),
  which the test's `OVERLAY_HOMES` knew and the script did not. It now reads
  `OVERLAY_HOMES` from the test (with `ast`, not an import), so its table and
  the test agree. A reporting gap, not a lost setting: `FIELD_HOMES` held all
  of them throughout.

**4. Tools.** `bench/preview/sheet.sh`: the settings target over every page
and tab (21: 11 pages, Agent details' 5 tabs, Communal's 7), wide (1100 px)
and narrow (the card drawn 500 px: `"narrow": true` in the settings target's
payload), dark (the current theme) and `flexoki-light`, a fresh install
(`fresh.json`, `--service-off`) and eight agents (`agents8.json`, the
showcase state), every page shot a screenful at a time and tiled into one
contact sheet per variant; a run that writes anything is reported.
`bench/preview/targets/keys.qml`: the keyboard walk (below).

## What was proven, and how

- **`tests/test_keyboard.py`** (10 tests, the plan's static test among them):
  `KnobRow` and `SettingsGroup` gone and used nowhere; no capitalised card
  title or letter-spaced heading; no bare Button outside the named
  exceptions, and the exception list names buttons that exist; ActionButton
  focusable and named; no bare ToggleSwitch, FocusSwitch focusable, keyed,
  named, ToggleRow naming it; SettingRow and SliderRow use two TextLinks and
  no MouseArea for them; Enter on a slider types; **everything with
  `activeFocusOnTab` sets `Accessible.name`**; **no MouseArea that does
  something sits outside a Tab-reachable element** unless its keyboard way is
  written in `KEYBOARD_ELSEWHERE` (14 entries: Escape closes, Up/Down in a
  list, Move to… for a drag, …), with stale entries failing; every Text says
  its size.
- **Mutations: 12 run, 12 red** (scratch copies under /tmp, never the
  clone): a bare Button on Listening; a bare ToggleSwitch on the Overview;
  TabStrip's name removed; ActionButton not focusable; a capital title back;
  KnobRow back; StatusCard's Tab focus removed; ExchangeItem's fold focus
  removed; a foldable Card head set `activeFocusOnTab: false`; Enter-to-type
  unwired; SettingRow's "?" back to a Text; an unsized status Text. (Two came
  back green first; see "Found along the way".)
- **Preview `keys`** (the pointer never moved; keys through QtTest's
  TestEvent): every page and tab is walked with Tab until the focus comes
  round, then walked again with every fold opened (Agents' 8 cards,
  Conversation's 3 Advanced sections, Voice's 1). Each page checks: Tab comes
  back round; every shown, enabled control that says it takes Tab was
  reached; every stop has a name; every stop on the page was scrolled into
  view; the search box is in the order; and the write log is empty at the
  end. **Eight agents: 121 of 121** (Agents unfolded: 240 stops). **Fresh
  install: 116 of 116.** Before the fixes the walk found the unnamed chip
  groups, the unnamed Dropdowns, the MiniBars and the crew view choice.
- **The sheet**: 8 variants, 21 pages each, 54 shots per variant; every run's
  write log empty (`sheet.sh` exit 0). Saved with these notes, downscaled to
  half the sheets' size (each tile a quarter of the shot):
  `notes/m29-sheets/sheet-<state>-<size>-<theme>.jpg`, rendered on the final
  code.
- **Existing preview targets after the change**, same counts as before:
  `search` 38/38, `setup` fresh 12/12 and walk 24/24, `listening` 24/24 (and
  `sherpa`), `conversation` 35/35, `other` 26/26, `about` 29/29, `chats
  drive` 32/32, `crew clicks` 19/19, `tools` 29/29, `skills` 18/18,
  `communal` 24/24, `advanced` 33/33, `notemoves` 28/28, `transfer` 23/23,
  `voicepage` 32/32, `launch` 25/25, `overview several` 11/11 (after the fix
  below). The log-only targets diffed against the same targets run from the
  M28 tree: `confirms` and `agentclicks` write the same lines; `knob` logs the
  same; `gallery keys` the same but for `Button` → `ActionButton` in the
  focus names.
- **Focus visible**: screenshots of a focused switch, dark and light
  (`keys --arg shot`); the accent outline was added after the first pair
  showed Omarchy's own ring faint on both.

## Shared files touched, and where

- `Settings.qml` (big shared): Deny is an ActionButton; `followFocus` on the
  page scroller. Nothing else.
- `pages/AgentsPage.qml`, `pages/AgentDetailsPage.qml` (big shared):
  Button → ActionButton, KnobRow → SliderRow, the personality chips' names,
  five status texts sized.
- Every other page: the same substitutions; SettingsGroup → Card on Overview,
  Voice, Other, About, Listening; the four dimmed sliders' `disabledReason`;
  Overview's links and heading; Communal's duplicate line.
- `ui/`: new `ActionButton`, `FocusSwitch`, `SliderRow`, `TextLink`; `qmldir`;
  `SettingRow` (TextLinks, label wrap, `lendName`), `ToggleRow`,
  `VoiceSlider` (Enter, accessibility), `StatusCard`, `ExchangeItem`,
  `UndoToast`, and accessible names in 13 more.
- `Setup.qml`, `Chats.qml`: ActionButton, SliderRow, accessible names on
  the chats rows.
- Deleted: `KnobRow.qml`, `SettingsGroup.qml`.
- Tests: new `tests/test_keyboard.py`; `test_hud`, `test_other_about_pages`,
  `test_no_openwakeword`, `test_states`, `test_voice_page` read Cards and
  sentence-case titles; `test_conversation_page` counts the screen reader's
  press; `qml_scan.overlay_qml()` drops the two files.
- Bench: `sheet.sh`, `targets/keys.qml` new; `targets/settings.qml` (narrow);
  `knob`, `gallery`, `launch` targets; `preview.sh` (the stats seed fix);
  `key-inventory.py` (overlay homes).
- `notes/m29-sheets/`: the eight contact sheets, JPEG at half the sheets'
  size (2.0 MB together).
- Docs: CLAUDE.md (the keyboard rule, beside the DangerButton one),
  CODEBASE.md (the pieces, the target, the script), CHANGELOG (M29), README
  (KnobRow out of the layout).
- Not touched: anything in `daemon/`, `bin/agentvoice`, `install.sh`,
  `manifest.json`, `runtime.py`, `Panel.qml`, `Hud.qml`, `bin/` (one comment
  in `bin/agentvoice-check` was edited and then restored, below).

## Measured

Nothing. No speed or size claim is made. The counts above are counts.

## Different from the plan, and why

- **"Accessible names" includes the pieces this project cannot edit**:
  Omarchy's Dropdown and ButtonGroup are named from outside (the row lends
  its label; SegmentedChoice names its ButtonGroup).
- **The permission card is not fully keyboard-reachable**: Allow stays
  pointer-only on purpose (open issue 2). The card is not a page, so the
  plan's "every page" does not strictly cover it; it is said here anyway.
- **"Page not in stage order"**: none found. Listening reads mic → first
  listener → second check → decision (M23's StageBlocks, kept: a pipeline is
  what that page is, and a StageBlock is not an old-style row); every other
  page reads top to bottom in the order its subject happens.
- **Not every polish found was done** (the plan: "fix what breaks
  consistency, list the rest"); the rest is in open issue 8.

## Found along the way

- **Pre-existing: the `overview` preview target has failed one check since
  M26.** M26's synthetic About install writes a stats file with 12 turns into
  the same scratch folder `overview.seed.py` seeds with 9, so the target read
  21. Synthetic numbers only, nothing real. `preview.sh` skips its file for a
  target that seeds its own; the target is 11/11 again and About 29/29.
- **Pre-existing: `bench/key-inventory.py` reported two keys with no home**
  (above).
- **Pre-existing: Tab moved the focus off screen** on every long page (above).
- **My re-read of the diff and the mutations** found: the "is it reachable"
  rule took its parents one level too high (`enclosing()` excludes the
  MouseArea itself), so it judged the wrong element and flagged four
  reachable links; a lookahead `\s*(?!false)` accepted
  `activeFocusOnTab: false` (the space before `false` satisfied it), caught
  when the Card mutation came back green; seven `KEYBOARD_ELSEWHERE` entries
  claimed "takes Tab" for things the structural rule can prove, so a
  mutation removing StatusCard's focus passed (they were removed and the
  mutation is red); the changelog and a comment said 47 unreachable buttons,
  a count I had not made (it is 29, counted on the M28 tree); a leftover
  invisible MouseArea in the undo toast; dead lines in `lendName`.
- **A comment edit in `bin/agentvoice-check` made the deployed build "differ"
  from the installed service.** About counts `bin/` as daemon code, so after
  the first deploy it said the service was from a different build and
  offered Repair, for one word in a comment. Restored in 137f775 and deployed
  again; About says the service is current.
- **`test_the_limit_note_links_to_the_longest_turn` counted four writers of
  the "Raise it" focus**; the screen reader's press makes five. The count is
  updated with the reason.
- **One full keyboard walk lost the focus** after Agent details → Advanced
  and every later page read 0 stops. Not reproduced in five later full walks
  (two configs) or in that page alone, sequence included. Recorded as open
  issue 6.
- **Binding-loop warnings** in `StatusCard.qml:145` and `SettingRow.qml:153`
  are the ones M28 recorded (line numbers moved); not touched.

## Not verified

- **All of it in the real shell.** Needs `omarchy-restart-shell` (not run).
  Seen only in `preview.sh`.
- **The real-shell keyboard walk** (the plan gives it to the user, at M30):
  Tab through each page with the real keyboard focus, which the preview
  never takes (its Exclusive focus is rewritten to None).
- **Any screen reader.** The names are set and read back by the walk
  (`item.Accessible.name`); nobody has heard them, and whether the shell
  exposes them to AT-SPI at all is unknown.
- **Text fields' names** come from their placeholder text in the walk's
  reading; whether a screen reader uses the placeholder is not known.
- **The Crew map's Table view** was not walked (the map is its default and
  the walk opens pages by deep link). The table's switches are FocusSwitches
  and its buttons ActionButtons, so the static tests cover it.
- **The Codex review** (bypassed, not owed).

## Going back

`bin/agentvoice-deploy 7cd1529` from the clone (the M28 notes commit; or
`8efa5e012cc0`, the M28 build), then `omarchy-restart-shell`. No install
needed either way (no daemon file changed). Nothing stored changes: no setting
was added, moved, renamed or removed, and nothing new is written anywhere.

## Open issues, for the next phase

1. **Codex review bypassed** for M29 (user decision, 2026-11-22). M12 stays
   "review owed".
2. **Allow on a permission card is pointer-only** (Deny is reachable). A
   keyboard-only user cannot approve a card. Default: kept, fail-closed: a
   keypress meant for something else must never approve anything, and M7's
   answer path trusts the shell, not where its input came from. Question for
   the user: reachable (Tab, then Enter), or as is?
3. **The "?" beside a setting is a Tab stop** (so is "reset" while shown):
   the Agents page with every card open is 240 stops. Default: kept (the
   explanation is the only way to read it without a pointer). An alternative
   is a key on the focused control (F1) instead of a stop.
4. **A switch's label is not clickable** (Omarchy's Toggle row made the whole
   row the target; SettingRow never did). Unchanged. Polish for Phase 17.
5. **`lendName` runs once**, when the row is made: a control a Loader adds
   inside a row later gets no lent name. The walk found none unnamed.
6. **One walk lost the focus once** (above). If it is real, it is in the
   preview's focus handling or in Advanced; the real-shell walk at M30 is
   where it would show.
7. **Two-column cards read left column, then right**, so Tab goes back up
   the page between cards (Agents unfolded: 24 jumps, three per agent; the
   Crew map's nodes: 2). As designed; logged by the walk.
8. **Polish left for Phase 17** (seen in the sheet, not consistency faults):
   a wrapped label's "?" sits at the right edge of the label's box rather
   than after its last word; the Chats page's card is wider than the others
   (M18, on purpose); the narrow layout elides some pill text on agent
   strips; the Agent details tab chips scroll at eight agents (M1's design).
9. **Carried, still open**: M28's 3–6; M27's 2–9; M26's 2–6; M25's 2–5;
   M24's 2–6; M23's 2–7; M22's 2–7; M21's 2–7; M20's 2–8; M19's 3–6; M18's
   2–6; M17's 2–7; M16's 2–9; M15's 2–8; M14's 2–7; M13's 2–9; M12's 2–7;
   M11's 1–7; M10's 1–8; M9's 2–7; M8's 2–11; M7's 2–7; M6's 1, 3, 4; M5's 1,
   4–6; M4's 4–13; M0's small test and bench fixes; agy's
   `carries_session_across`; the runner's sandbox test command. M28's 2 is
   closed (above).
