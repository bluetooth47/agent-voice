# Phase M1: Shared UI pieces, and the key inventory

Written 2026-11-21, unattended (started by the runner script). Branch
`phase-m1`, cut from `phase-m0` at 9e2f94c. Result commit: the notes commit on
top of 1034393, pushed to `fork/phase-m1` only. Model: Claude Opus 5.5, high.

Deployed: **yes**, 1034393 through `bin/agentvoice-deploy --no-install` (its
strict check green, 2843 tests), daemon idle. Installed: **no**: nothing under
`daemon/`, `bin/` or `install.sh` changed, so the running daemon is unchanged.
**Shell restart needed** to see the converted buttons in the real shell (not
run: stop point 1).

`./bin/agentvoice-check`: green, **2843 tests** (was 2824; +19), 14 of 14
static checks, "the check wrote nothing in the tree: ok". Box: not run
(`install.sh` did not change).

## What was built

**New building blocks in `ui/`** (none knows a setting by name; all text is
`Text.PlainText`; all use `Commons.Color`):

| Piece | What |
|---|---|
| `Card`, `CardGrid` | Titled box, optionally foldable; two across from 520 px of grid width (what the overlay leaves beside the sidebar at about 760 px), one when narrower. Children get the column width as a binding. |
| `HeaderStrip`, `Pill` | Foldable agent header: tone dot, name, status, pills (most important first; the last pills give way when narrow), caret. Toned pill with tooltip. |
| `CompactSelector`, `ModelPicker` | "Label: value ▾" mini selector with a hold like SegmentedChoice; a disabled one shows its reason on click. Model and effort joined in one bordered control; `effortReason` keeps effort shown and says why it cannot change. |
| `ToggleChips` | On/off chips with optional inherit (inherit → on → off); a missing state reads off unless inherit is allowed; a disabled chip stays focusable and says why under the row. |
| `Hint`, `Tip` | One plain line with the detail (and any truncated text) in a tooltip; the shared themed tooltip. |
| `DangerButton` | "⚠ Text"; first click arms an inline strip "Really …? Cancel / Confirm"; disarms after 6 s, on Escape, on Cancel, when disabled, hidden, or when focus leaves; Cancel has the focus; the strip wraps at `maxWidth`; action only in `onConfirmed`. Never a modal. |
| `AdvancedSection` | "Advanced (N) ▸", shut by default, optional summary when shut. |
| `StageBlock` | Numbered stage ring (toned) with a connector to the next. |
| `StatTile`, `MiniBars` | One number with label and caption; per-hour bars with a readout line (pointer or Left/Right), an honest "Nothing yet" for all zeros. |
| `DraggableCard`, `DropLane`, `UndoToast` | Drag moves, Ctrl+drag copies (only if `allowCopy`); "Move to… / Copy to…" menu as the keyboard path; a lane can refuse with a reason (shown while hovering, said after a refused drop); Undo for 10 s of real time (hover pauses), re-checked at the click. They only ask; the page moves. |
| `AgentTabs` | One tab per agent with a toned dot; one row that scrolls (with edge fades) at nine or whenever it does not fit; chosen tab kept in view; Left/Right/h/l/Home/End. |
| `SearchField` | Search box, debounced (250 ms), Enter searches at once, Escape clears (and passes through when empty), filter chips. |
| `ChatBubble` | Left/right bubble, plain selectable text, a quieter "note" kind. |
| `MenuList` | The pick-one popup the selectors and cards share: headings, disabled entries with reasons, j/k/Up/Down/Enter/Escape. |

**Risky buttons converted to `DangerButton`:** remove an agent (Agents card
and Agent details → Advanced), move an orphan folder to the trash, delete a
saved chat, clear the session's conversation (conversation view, both with
and without saved chats), remove Agent Voice. The three hand-rolled
"click again" flags and 4 s timers are gone (`confirmRemove` ×2,
`confirmDelete`, `confirmClear`).

**Tests:**
- `tests/test_confirms.py`: a table of each destructive command (`agents
  trash`, `chats delete`, `--uninstall`, `history clear`), where it is built
  (exact functions, checked), and the calls that reach it (regexes, any
  quotes and spacing; Process starts count). Every call in every overlay QML
  file must sit in `onConfirmed` or in a wrapper named by file and function.
  `onConfirmed` only on a DangerButton. DangerButton emits `confirmed()` only
  from `confirm()`, which refuses unless armed. The string `delete` in
  Chats.qml only as `run()`'s first argument. No `put("key"` in `ui/`.
- `FIELD_HOMES` in `tests/test_settings_pages.py`: every `voiceAgents[i]`
  field (read out of `runtime.Config._agents()` with an AST walk, so a new
  daemon field fails until it has a home), its `main*` twin, and the six
  defaults-only keys, each written on exactly one page; writes outside the
  pages only in the named overlay functions (`assignVoice`, `trainVerifier`,
  `AgentFolders.saveAgents`, the popup's documented exception); ui/ pieces
  scanned as writers of their own.
- `tests/qml_scan.py`: blanks comments, strings and regex literals (template
  `${…}` kept as code, cleaned recursively), matches braces, and answers
  "which handler / element is this call in". Shared by both tests and by
  `bench/key-inventory.py`.
- Mutations, each turned the suite red: `onConfirmed` → `onClicked` on the
  About page, the Agents card, the session Clear and the orphan trash; the
  DangerButton's armed guard removed; a stray `updateAgent(0, "narration")`
  plus `put("mainTools")` on the Conversation page; and in-test mutations for
  other quotes, spacing, `${…}`, a brace inside a string in `${…}`, and
  same-line handlers.

**Preview:**
- `gallery` rewritten: every piece (plus the pre-M1 ones), `--arg narrow`,
  `long` (long labels), `armed`, `danger` (scripted run) and `keys`
  (keyboard walk). Screenshots taken narrow (560×780) and wide (960×780),
  dark and `flexoki-light`, with long labels.
- New `confirms` target: drives every converted DangerButton in the real
  overlay, cancelled then confirmed, and logs the writes.
- `preview.sh` now stubs the floating-terminal launcher (logs, never runs:
  Repair, Install, Remove Agent Voice), `agentvoice history clear`, and
  `agentvoice chats delete` when not `--scratch-data`. Before this, a preview
  click on Remove Agent Voice would have opened a real terminal running
  `install.sh --uninstall`.

**Docs:** CLAUDE.md (FIELD_HOMES, key-inventory, the DangerButton rule and
its table), CODEBASE.md (the new pieces, the new preview targets).

## The key inventory (snapshot before anything moves)

Generated by `python3 -I bench/key-inventory.py` on 1034393. "Column
(function X)" means the write is in page function X, called from the
controls that use it.

| Key | Kind | Page | Control (handler) |
|---|---|---|---|
| `phrase` | schema | AgentsPage | TextField (onEditingFinished) |
| `micThresholdDb` | schema | ListeningPage | KnobRow (onCommitted) |
| `adaptiveGate` | schema | ListeningPage | ToggleRow (onToggled) |
| `gateMarginDb` | schema | ListeningPage | KnobRow (onCommitted) |
| `wakeConfidencePct` | schema | ListeningPage | KnobRow (onCommitted) |
| `leadInMs` | schema | ConversationPage | KnobRow (onCommitted) |
| `trailingSilenceMs` | schema | ConversationPage | KnobRow (onCommitted) |
| `quickEndMs` | schema | ConversationPage | KnobRow (onCommitted) |
| `minUtteranceMs` | schema | ConversationPage | KnobRow (onCommitted) |
| `maxUtteranceMs` | schema | ConversationPage | KnobRow (onCommitted) |
| `model` | schema | VoicePage | SegmentedChoice (onCommitted) |
| `speakReplies` | schema | VoicePage | ToggleRow (onToggled) |
| `chimes` | schema | VoicePage | ToggleRow (onToggled) |
| `keepHistory` | schema | DisplayPage | ToggleRow (onToggled) |
| `saveChats` | schema | DisplayPage | ToggleRow (onToggled) |
| `chatRetention` | schema | DisplayPage | SegmentedChoice (onCommitted) |
| `voice` | schema | AgentsPage | Dropdown (onChanged) |
| `voiceSpeed` | schema | AgentsPage | KnobRow (onCommitted) |
| `echoTailMs` | schema | ConversationPage | KnobRow (onCommitted) |
| `engine` | schema | ListeningPage | SegmentedChoice (onCommitted) |
| `owwModel` | schema | AgentsPage | Dropdown (onChanged) |
| `owwThresholdPct` | schema | ListeningPage | KnobRow (onCommitted) |
| `sherpaThresholdPct` | schema | ListeningPage | KnobRow (onCommitted) |
| `wakeCrossCheck` | schema | ListeningPage | ToggleRow (onToggled) |
| `shortNameBoostPct` | schema | ListeningPage | KnobRow (onCommitted) |
| `crossCheckMinMs` | schema | ListeningPage | KnobRow (onCommitted) |
| `crossCheckMaxMs` | schema | ListeningPage | KnobRow (onCommitted) |
| `crossCheckEngines` | schema | ListeningPage | SegmentedChoice (onCommitted) |
| `crossCheckTrailingWords` | schema | ListeningPage | KnobRow (onCommitted) |
| `crossCheckWhisperHint` | schema | ListeningPage | ToggleRow (onToggled) |
| `conversationMode` | schema | ConversationPage | ToggleRow (onToggled) |
| `yieldToRecorders` | schema | DisplayPage | ToggleRow (onToggled) |
| `logSpeech` | schema | DisplayPage | ToggleRow (onToggled) |
| `agentsPanel` | schema | DisplayPage | ToggleRow (onToggled) |
| `followUpMs` | schema | ConversationPage | KnobRow (onCommitted) |
| `narration` | schema | ConversationPage | SegmentedChoice (onCommitted) |
| `narrationSilenceS` | schema | ConversationPage | KnobRow (onCommitted) |
| `openMicIdleMin` | schema | ConversationPage | KnobRow (onCommitted) |
| `openMicAddressedOnly` | schema | ConversationPage | ToggleRow (onToggled) |
| `openMicAuto` | schema | ConversationPage | ToggleRow (onToggled) |
| `fullStopAnytime` | schema | ConversationPage | ToggleRow (onToggled) |
| `livePartials` | schema | VoicePage | SegmentedChoice (onCommitted) |
| `mainName` | schema | AgentsPage | TextField (onEditingFinished) |
| `mainProgram` | schema | AgentsPage | Column (function runOn) |
| `projectDir` | schema | AgentsPage | TextField (onEditingFinished) |
| `endpointUrl` | schema | AgentsPage | Column (function runOn) |
| `endpointUrl` | schema | AgentsPage | EndpointEditor (onEdited) |
| `endpointModel` | schema | AgentsPage | Column (function runOn) |
| `endpointModel` | schema | AgentsPage | EndpointEditor (onEdited) |
| `endpointIsAgent` | schema | AgentsPage | EndpointEditor (onEdited) |
| `endpointTimeoutS` | schema | AgentsPage | EndpointEditor (onEdited) |
| `endpointHistoryTurns` | schema | AgentsPage | EndpointEditor (onEdited) |
| `desktopTools` | schema | AgentsPage | ToggleRow (onToggled) |
| `browserTools` | schema | AgentsPage | ToggleRow (onToggled) |
| `omarchySkill` | schema | AgentsPage | ToggleRow (onToggled) |
| `mainNotesWrite` | schema | AgentsPage | ToolSwitches (onNotesPicked) |
| `mainCollaboration` | schema | AgentsPage | ToolSwitches (onCollaborationPicked) |
| `mainAcceptsWork` | schema | AgentsPage | ToolSwitches (onAcceptsWorkPicked) |
| `bargeOnHeadset` | schema | ConversationPage | ToggleRow (onToggled) |
| `bargeIn` | schema | ConversationPage | ToggleRow (onToggled) |
| `bargeFactor` | schema | ConversationPage | KnobRow (onCommitted) |
| `hud` | schema | DisplayPage | ToggleRow (onToggled) |
| `hudLingerMs` | schema | DisplayPage | KnobRow (onCommitted) |
| `useVerifier` | schema | ListeningPage | ToggleRow (onToggled) |
| `agentEfforts` | defaults only | AgentsPage | Column (function setEffort) |
| `agentModels` | defaults only | AgentsPage | Column (function setModel) |
| `mainTools` | defaults only | AgentsPage | Column (function putMainTool) |
| `permissions` | defaults only | AgentsPage | Column (function setLevel) |
| `voiceAgents` | defaults only | AgentsPage | Column (function saveAgents) |
| `wakeAlsoSounds` | defaults only | ListeningPage | Column (function setAlso) |

| voiceAgents[i] field | Page | Control (handler) |
|---|---|---|
| `acceptsWork` | AgentsPage | Column (function putAgentAccepts) |
| `agent` | AgentsPage | Dropdown (onChanged) |
| `agent` | AgentsPage | SettingRow (onReset) |
| `collaboration` | AgentsPage | Column (function putAgentCollab) |
| `effort` | AgentsPage | SegmentedChoice (onCommitted) |
| `effort` | AgentsPage | SettingRow (onReset) |
| `enabled` | AgentsPage | ToggleRow (onToggled) |
| `endpointHistoryTurns` | AgentsPage | EndpointEditor → KnobRow (onCommitted) |
| `endpointIsAgent` | AgentsPage | EndpointEditor → ToggleRow (onToggled) |
| `endpointModel` | AgentsPage | EndpointEditor → Dropdown (onChanged) |
| `endpointModel` | AgentsPage | EndpointEditor → TextField (onEditingFinished) |
| `endpointTimeoutS` | AgentsPage | EndpointEditor → KnobRow (onCommitted) |
| `endpointUrl` | AgentsPage | EndpointEditor → SegmentedChoice (onCommitted) |
| `endpointUrl` | AgentsPage | EndpointEditor → TextField (onEditingFinished) |
| `label` | AgentsPage | SettingRow (onReset) |
| `label` | AgentsPage | TextField (onEditingFinished) |
| `level` | AgentsPage | Button (onClicked) |
| `level` | AgentsPage | SegmentedChoice (onCommitted) |
| `model` | AgentsPage | Dropdown (onChanged) |
| `model` | AgentsPage | SettingRow (onReset) |
| `model` | AgentsPage | TextField (onEditingFinished) |
| `name` | AgentsPage | TextField (onEditingFinished) |
| `narration` | AgentsPage | SegmentedChoice (onCommitted) |
| `narration` | AgentsPage | SettingRow (onReset) |
| `notesWrite` | AgentsPage | Column (function putAgentNotes) |
| `projectDir` | AgentsPage | SettingRow (onReset) |
| `projectDir` | AgentsPage | TextField (onEditingFinished) |
| `speed` | AgentsPage | KnobRow (onCommitted) |
| `speed` | AgentsPage | SegmentedChoice (onCommitted) |
| `speed` | AgentsPage | SettingRow (onReset) |
| `tools` | AgentsPage | Column (function putAgentTool) |
| `voice` | AgentsPage | Dropdown (onChanged) |
| `voice` | AgentsPage | SettingRow (onReset) |

`id` (filled in by the list functions) and `instructions` (the pre-folder
field, read as a fallback, migrated into the folder in Phase 10) have no
writing control, on purpose. The `voice` field also has the Voice library's
shortcut through `Settings.assignVoice`. Outside the pages: `permissions` and
`voice` are written by the popup (Panel.qml; M3 removes the level),
`engine` by `Settings.trainVerifier`, `voiceAgents` by
`AgentFolders.saveAgents` (remove, restore, undo).

## Shared files touched, and where

- `Settings.qml` (big shared): the conversation view's Clear button became a
  DangerButton (~line 1800); `confirmClear` and its Timer removed (~line 968).
  Nothing else.
- `pages/AgentsPage.qml` (big shared): the card's Remove button (~line 1236)
  and its `confirmRemove`/Timer.
- `pages/AgentDetailsPage.qml` (big shared): Remove (Advanced) and the
  orphan "Move to trash"; `onTargetChanged` disarms instead of resetting a
  flag.
- `Chats.qml`: Delete and the session Clear; `confirmDelete` and its Timer.
- `pages/AboutPage.qml`: Remove Agent Voice.
- `bench/preview/preview.sh`: three new stubs. `tests/test_history.py`: the
  clear test follows the DangerButton.
- New: 21 files in `ui/`, `tests/qml_scan.py`, `tests/test_confirms.py`,
  `bench/key-inventory.py`, `bench/preview/targets/confirms.qml` and
  `confirms.seed.py`.

## Measured

No speed or size claims in this phase. Counts:

- Tests 2824 → 2843. Check run ~2 min 25 s for the tests, as before.
- `danger` run (gallery, synthetic events): arm → Cancel: cancelled; arm →
  Reset: confirmed; arm → Escape: cancelled; arm → Enter (focus on Cancel):
  cancelled; arm, untouched 6.3 s: cancelled. Every step logged.
- `keys` run: every piece reached by Tab from the agent tabs (header 1 press,
  model picker 1, chips 4, compact selector 2, Advanced 2, danger 1, bars 1,
  first card 2, Undo 17, search 0 after Undo hands focus on); each answered
  its keys (tab picked, header folded and opened, model picked from its menu,
  chip flipped, disabled chip said "github (MCP): Found in ~/.claude.json;
  approve it on the Communal page first.", Advanced opened, danger armed,
  Escape and tabbing away each disarmed it, bars read "22:00 · 0 turns", a
  card moved by its menu, Undo undid it, search typed and cleared).
- `confirms` run (`--live-config --scratch-data`): Remove Agent Voice, the
  Agents card, Agent details and a saved chat each: armed → Cancel wrote
  nothing; armed → confirm wrote exactly one thing (`floating-terminal
  …/install.sh --uninstall --with-widget` to the stub's log; `bar set
  voiceAgents` without that agent, twice; saved chats 3 → 2 in the scratch
  folder). The target checks the launcher is the stub before confirming.

## Different from the plan, and why

- **More buttons converted than listed**: the second remove-agent site
  (the Agents card), the orphan folder trash (same `agents trash` command),
  and the session Clear in both places (`history clear`, no undo). The
  test's rule is per command, so every path to each had to be confirmed.
- **Not converted**: the Voice library's trash icon (`agentvoice voice
  remove`): open issue 1.
- **Two extra pieces**, `Tip` and `MenuList`, which the others share.
- **"Scrolls at 9"** read as: at nine tabs (the most there can be, main plus
  eight) or whenever they do not fit, the row scrolls sideways rather than
  wrapping.
- **CardGrid's threshold** is on the grid's own width (520 px), since a piece
  cannot see the overlay's width; that is about 760 px of overlay.
- **Codex ran in its own sandbox in the clone** (`-s read-only`), not on a
  throwaway copy: `codex sandbox -- touch ~/x` now fails with "Read-only
  file system" and prints no bwrap error (`codex sandbox linux` is not a
  subcommand in this Codex; the runner prompt's test command panics with
  "Failed to execvp linux"). HEAD and status were the same before and after
  both passes.
- **Reviews were given the diff inline**, told not to explore, to save
  credits. Pass 1: DangerButton, the conversions, both tests, the scanner,
  preview.sh. Pass 2: pass 1's fixes plus MenuList, CompactSelector,
  ToggleChips, DraggableCard, DropLane, UndoToast, AgentTabs, SearchField,
  HeaderStrip, CardGrid. Not sent to Codex: Card, StageBlock, StatTile,
  MiniBars, Hint, Pill, Tip, ModelPicker, AdvancedSection, ChatBubble, the
  preview targets, key-inventory, docs. Pass 2's fixes were not re-reviewed.

## Codex review

- **Pass 1** (6 findings, all accepted, fixed in ec8372b): the armed strip
  could push its buttons off the page with a long name; Escape after tabbing
  away left it armed; wrapper functions allowed by name in any file;
  exact-substring matching missed `run('delete', …)`; template `${…}` hidden
  from the scanner; ui/ skipped by FIELD_HOMES.
- **Pass 2** (12 findings, 11 accepted, fixed in 1034393): Undo could fire
  past its deadline with a stalled event loop; Ctrl-drag copied a
  move-only card; a brace in a string inside `${…}` ended the scan; a stale
  "Move to…" menu could emit a since-disabled move; the drag hotspot was
  fixed at the card's left; UndoToast's width fed on itself; focus left on
  hidden content after a fold or a toast expiring; popups pulled focus back
  after a click elsewhere; a lane's refusal did not follow Ctrl mid-hover;
  ToggleChips' cursor survived a shorter list; AgentTabs did not reveal the
  chosen tab on list changes and ignored the tone. The 12th (a same-line
  handler credited to a later `onConfirmed`) misread `line_of`, which only
  reads up to the call; the rule was tightened anyway (last handler started
  after a brace or semicolon) and a regression case added.

## Found along the way

- **The gallery's keyboard walk found a real DangerButton bug**: after
  Escape the focus stayed on the hidden Cancel button, so the next Tab went
  nowhere. Fixed (focus returns to the idle button), and the walk now checks
  it.
- **Previews could run real destructive commands.** The floating-terminal
  launcher, `agentvoice history clear` and (without `--scratch-data`)
  `agentvoice chats delete` all passed through to the real ones. Stubbed.
- `ToggleChips` first had a `states` property, which shadows `Item.states`,
  and `MenuList` had `background` and `dim`, which shadow Popup's final
  members; qmllint's property-override warnings caught all three (that
  category is not gated by the check).
- **qmllint was not repeatable once**: one check run reported
  `SearchField.qml:42 field.text` as a missing property, after earlier runs
  passed with the same line; the line now goes through a local alias.
- TestEvent key events reach a preview window whose layer surface has no
  keyboard focus, once an item has been given focus with
  `forceActiveFocus()`; Tab from nothing does nothing.

## Not verified

- **The converted buttons in the real shell** (needs `omarchy-restart-shell`;
  stop point 1): arm, Cancel, confirm, Escape and the 6 s timeout on each of
  the six sites, by the user.
- **Real drag and drop with a real pointer**, including Ctrl+drag copy and a
  refused drop. Only the "Move to…" menu path was driven (by keyboard); the
  drag path never ran.
- **Tooltips** (Tip, Hint detail, disabled chips, truncated text): not seen
  in any screenshot.
- **Keyboard focus in the real overlay** (Exclusive focus there; the preview
  ran with none and synthetic events).
- The session Clear buttons were not driven in a preview (they need live
  session history); the test covers their wiring, and the stub now logs the
  command.
- No voice, mic or live-turn check applies to this phase.

## Going back

UI only; nothing stored, no setting added or renamed. `bin/agentvoice-deploy
9e2f94c23d03` (printed by the deploy) puts M0's QML back; then
`omarchy-restart-shell`. An older build has the two-click buttons and no new
pieces.

## Open issues, for the next phase

1. **The Voice library's trash icon** (`removeVoice` → `agentvoice voice
   remove`) is still one click. The voice is re-downloadable (pinned and
   hashed), so it was left for M25's Voice page; adding it to
   `DESTRUCTIVE` then is one line.
2. **Codex review coverage** (above): pieces no page uses yet were not all
   reviewed, and pass 2's fixes were not re-reviewed. Each will be read again
   by the phase whose page first uses it.
3. **M0's open issue 5 is not done** (small test and bench fixes:
   `test_tools_skills`' TMPDIR-length dependence, `test_permission_hook`'s
   cwd sensitivity and its cleanup of the *live* permissions folder,
   `turn_latency.py --build` with `-dirty`). Carried to M2.
4. No section 11 question applied to M1; none was taken by default.
5. The runner prompt's Codex test command (`codex sandbox linux -- true`)
   does not exist in this Codex version; `codex sandbox -- true` is the one
   that works (above).

## Codex credits used

**12.13** (balance 443.73 → 437.15 after pass 1, → 431.60 after pass 2, read
from the session logs' `rate_limits.credits.balance`): pass 1 31,982 tokens,
pass 2 37,111, both `gpt-6.2-astra` at medium reasoning. **431.60 left**
for M2–M29, about 15.4 per phase.

## Live checklist: what was said, what happened

Nothing live in this phase: no voice, no typed turn, no shell restart.
