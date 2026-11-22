# Phase M5: The Agents page (item 8, bug E)

Written 2026-11-22, unattended (started by the runner script). Branch
`phase-m5`, cut from `phase-m4` at f9b5d01. Result commit: the notes commit
on top of 314d726, pushed to `fork/phase-m5` only; `dev` fast-forwarded to
it and pushed to `fork`. Model: Claude Opus 5.5, high.

Commits: d8f2424 (the phase), 735c1f6 (Codex pass 1 fixes), 314d726 (Codex
pass 2 fixes), then these notes.

Deployed: **yes**, 314d726 through `bin/agentvoice-deploy --no-install` (its
strict check green, 3216 tests). The daemon was idle (state `listening`,
every agent idle). It replaced 72c9589; the way back is
`bin/agentvoice-deploy 72c9589b30af`. Installed: **no**. Nothing under
`daemon/`, `bin/` or `install.sh` changed, so the running daemon is still
the right one. **Shell restart needed** to see the new page (QML only). Not
run: the next stop point is after M9.

A copy of `shell.json` was taken before the deploy
(`~/agentvoice-notes/shell.json.before-M5`, mode 0600). After the deploy it
was byte-identical to the live file.

`./bin/agentvoice-check`: green, **3216 tests** (was 3194; +22), 14 of 14
static checks, "the check wrote nothing in the tree: ok". The bare-runner
variant (`AGENTVOICE_STRICT=1`, a venv with only requirements-dev) was green
on d8f2424: 3194 passed, 9 skipped (the existing numpy skips). Box: not run
(`install.sh` did not change).

## What was built

**One block per agent.** `pages/AgentsPage.qml` used to hold two
hand-written copies of every row, one for the main agent and one for the
extra agents. It now has one inline component, `AgentBlock`. The main agent
is `agentIndex: -1`; the Repeater still builds by count, so a save
rebuilds nothing. The page went from 1384 to 1208 lines, with more in it.

- **Header strip** (`ui/HeaderStrip`): state dot, name, wake phrase and
  state, then pills, most important first: the permission level (toned:
  trusted in the urgent colour, edits in the accent), program · model,
  effort, voice · speed. Pills give way from the least important when the
  strip is narrow. A problem line (urgent) and the Rule of Two warning
  (accent) show under it, folded or open. Click, Enter or Space unfolds it.
- **Cards** (`ui/CardGrid`, two across from 520 px of page, one below):
  - *Identity*: name and wake phrase side by side; runs on; the model and
    its effort as one `ModelPicker`, plus the "Other…" text field.
  - *Endpoint*: endpoint agents only. The `EndpointEditor` and its
    own-machine warning.
  - *Permissions*: level (with the "Trust it / Cancel" step as before) and
    project folder. Only restyled.
  - *Voice*: voice, with **▶ Test**, which plays the voice the agent would
    use at its own speed. Then speed, and "talk while it works" for extra
    agents.
  - *Tools*: the three switches as `ToggleChips` (every agent → on → off),
    one line per tool saying what it has and where that comes from ("on, as
    for every agent", "off, this agent's own", "not available" with the
    reason in the tooltip), and a link to Communal → Tools.
  - *Collaboration & notes*: collaboration (all four values), takes work
    from agents, notes write.
  - *Agent*: on/off (extra agents), the main agent's wake model when
    openWakeWord is the engine, the role/personality/instructions summary
    with "Edit in Agent details →", and Remove.
- **Every write goes through `writeField(index, field, value)`**. It names
  each key (main agent) and each field (`updateAgent(index, "field", …)`),
  so FIELD_HOMES and the key inventory still see where each one is
  written. The main agent's endpoint writes go through `putMainEndpoint`,
  which names its five keys.

**Bug E.** The "ON THE DESKTOP" group is gone from the Agents page. Its
three keys (`desktopTools`, `browserTools`, `omarchySkill`) moved, same
names and same controls, in the same commit, to a new **Communal → Tools**
tab: "For every agent. An agent's own switch beats this…". A deep link with
`tab: "tools"` opens it (`Settings.goTo`).

**Pieces:**
- `ui/ToolSwitches.qml` draws `part: "tools"` or `part: "collab"`. Both
  share the program tables that `test_tools_skills` and `test_notes` hold
  to agentfs. The foldable "Tools & collaboration" group is gone.
- `ui/SegmentedChoice.qml` has an opt-in `wrap: true` (with a width set):
  chips that do not fit wrap onto the next line, with the same keyboard
  behaviour. A transparent, disabled copy of the chips measures the
  one-line width.
- `ui/HeaderStrip.qml` has `controlled`: a click asks through `toggled()`
  and leaves the page's binding alone. It also has the `problem` and
  `warning` lines.
- `ui/ModelPicker.qml` is held to its card's width: the model half elides,
  the effort half stays in reach.
- `ui/AgentCard.qml` is deleted. Nothing used it any more.
- `Settings.playSample(voice, speed)` takes a pace. The playing sample is
  known by voice and pace (`samplePace`).
- `vEffortsKnown`: whether the state file carried an effort list.

**Settings.** None new. **Moved, same names:** `desktopTools`,
`browserTools`, `omarchySkill` → Communal → Tools.

**Tests.** New `tests/test_agents_page.py` (22 tests). It **runs** the
page's write functions in node: they are taken out of AgentsPage.qml as
written and run against a stub overlay. It holds that:
- saving any field of any agent (23 writes × 3 agents) changes that field
  of that agent and nothing else, byte for byte, including unknown fields,
  nested objects, key order, the neighbours and a field named `__proto__`;
- tool chips change one key of one agent's `tools`, and the whole saved
  list is compared;
- an entry from before ids gets its derived id and nothing else;
- each main-agent write is its one key and never `voiceAgents`;
- choosing a voice fetches it for either kind of agent;
- a controlled strip asks rather than assigns;
- the Tools card's "where it comes from" line;
- the Communal tools tab and its deep link;
- Test's pace;
- the delegate's index binding.

It carries an in-suite mutation (a copy that only knows today's fields),
so the guard cannot go vacuous. node is not a project dependency: GitHub's
runners have it, and the tests skip, saying why, where it is missing.

Eight existing tests, in six files, read the old page's text (test_agent_pages,
test_agent_names, test_agentfs_migrate, test_voice_download,
test_no_openwakeword, test_tools_skills). Each was changed to the new
literal and keeps what it held. test_agent_pages' "Communal writes no
setting" became "Communal writes exactly those three".

**Mutations: 28, all red.** 16 on the phase, 7 on pass 1's fixes, 5 on
pass 2's. Of pass 2's five, four are caught by read checks of the QML (the
picker's widths, the effort's "known" rule, the Test button's pace). Only
the preview shows those working.

**Preview.**
- `preview.sh --config FILE`: `--live-config` starting from a synthetic
  shell.json. `bench/preview/configs/agents1.json` and `agents8.json` hold
  the main agent plus seven: a normal Claude agent with a field from a
  newer build, a trusted Codex, an endpoint, a switched-off Gemini,
  Antigravity, Copilot, and a long name. `states/agents.json` is the
  matching daemon state.
- `agents` rewritten for the new structure: **57 of 57**. It checks:
  - a save does not rebuild or shut the open agent;
  - a dropdown stays open through an unrelated save;
  - effort through the picker's menu, speed, a tool chip, the main agent's
    effort per program;
  - the endpoint agent's cards, and its tool chips disabled rather than
    hidden;
  - the tools deep link marks the Tools card, and its link reaches
    Communal → Tools, where the switch writes `desktopTools`;
  - **after all of it, every untouched agent's entry is byte for byte as
    it was**, and the edited one kept every field, the unknown one
    included.
- `agentclicks`: the same 24 actions on the old page (phase-m4, from
  `git archive`) and the new one, from the same config. **The two write
  logs are identical**: same keys, values and order. It was rerun after
  each fix commit and stayed identical.
- `agentshots`: one scene per shot (every agent shut, main open and below,
  an extra agent, the endpoint, switched off, the long name, Communal →
  Tools). Taken wide dark, wide `flexoki-light`, and narrow (the overlay
  drawn 560 px wide, which is the real narrow layout; a crop of a wide
  screen is not). Also the 1-agent config, and a long custom model with a
  stale effort.
- `agentshots --arg '{"keys":true}'`, the keyboard walk, from the main
  strip:
  - Enter opens it;
  - Tab reaches every control in order: name, wake phrase, runs on, model,
    effort, level chips, project folder, voice, Test, speed, tool chips,
    the Communal link, collaboration, takes work, notes, Edit in Agent
    details;
  - then the next strips, the foot link and the sidebar;
  - Space opens sora, and Space on her chips flipped desktop tools and
    wrote it.
- The `tools` (23 of 23), `notes` (20 of 20), `confirms`, `clicks` and
  `folders` (11 of 11) targets were updated for the new structure, or for
  the measuring copy of the chips, and pass.

**Docs.** README ("More than one agent"; "On the desktop" now points to
Communal → Tools). CODEBASE (AgentsPage, CommunalPage, the ui pieces, the
new preview targets and `--config`).

## The key inventory, before and after

`python3 -I bench/key-inventory.py` on f9b5d01 and on 314d726. Every key
and every `voiceAgents` field keeps its page. The only change of page is
the three tool keys moving to Communal:

| Key | Before | After |
|---|---|---|
| `desktopTools` | AgentsPage, ToggleRow | **CommunalPage**, ToggleRow |
| `browserTools` | AgentsPage, ToggleRow | **CommunalPage**, ToggleRow |
| `omarchySkill` | AgentsPage, ToggleRow | **CommunalPage**, ToggleRow |

Every other Agents-page write now reads "Column (function writeField)",
or "putMainEndpoint" for the main agent's endpoint keys, instead of the
control it came from, because the controls call that one function.
`owwModel` is unchanged (its Dropdown, on the Agent card).

## Shared files touched, and where

- `pages/AgentsPage.qml` (big shared): rewritten. The page functions are
  kept (`updateAgent`, `addAgent`, `putMap`, `runOn`, `toolMap`, the
  `putAgent*` helpers, `ruleOfTwo`, `folderSummary`, the open-cards
  logic). Added: `copyEntry`, `writeField`, `writeTool`,
  `putMainEndpoint`, and the `AgentBlock` component.
- `Settings.qml` (big shared):
  - `playSample` (pace), `samplePace`, `sampleNextPace`;
  - `goTo` accepts the communal `tools` tab;
  - `vEffortsKnown`;
  - a comment on `focusTools`.
- `pages/CommunalPage.qml`: the Tools tab.
- `ui/`: ToolSwitches, SegmentedChoice, HeaderStrip, ModelPicker, Pill
  (comment), qmldir; AgentCard deleted.
- `Panel.qml`, `wake_listen.py`: untouched.

## Measured

- Tests 3194 → 3216; the check's test run is about 2 min 42 s, as before.
- AgentsPage.qml 1384 → 1208 lines. ToolSwitches 265 → 280.
- The clicks diff: 24 writes each side, 0 differences.
- No speed or size claim is made, so nothing went to FINDINGS.

## Different from the plan, and why

- **The main agent's wake model is on its Agent card**, as the plan says.
  With openWakeWord live, the Identity card's wake phrase shows the phrase
  read-only and points there.
- **"Talk while it works" for extra agents is on the Voice card.** The
  plan's card list does not place it. The main agent's is still the
  Conversation setting (question 9's per-agent extra was not built).
- **Remove is on the Agent card.** The plan does not say where it goes.
- **The Tools card's chips cycle**: every agent → on → off. That is
  ToggleChips' design from M1, replacing the three-way row. Reaching "off"
  from "every agent" takes two clicks, and each click writes.
- **`SegmentedChoice` gained a wrap mode.** At the overlay's normal size
  (Style.space(880), about 730 px here) each card is about 250 px wide, and
  "Ask first | Edits are fine | Trust everything" ran past the card's edge.
  It is opt-in, so every other page is unchanged.
- **The narrow layout appears only on a screen narrower than the
  overlay.** The plan's "narrow (520×720)" screenshots were crops of a
  wide overlay; here the overlay is drawn 560 px wide instead.
- **"Same as the main agent" no longer says "not on this machine"** in the
  voice hint. That was an old bug (an empty voice was never in the list on
  disk), seen in the screenshots.
- **The idle Remove button says "Remove this agent" for a name over 16
  characters.** The confirmation still names the agent. The button does
  not wrap, and a long name pushed it past the card.
- **Codex ran on the read-only copy both times.** `codex sandbox linux --
  true` still panics ("Failed to execvp linux"). The clone's HEAD and
  status were unchanged after both passes, and both copies were deleted.
  Pass 2 was sent the fix diff only.

## Codex review

- **Pass 1** (6 findings, all fixed in 735c1f6):
  - a `__proto__` field lost when another agent was saved;
  - a stale effort that could not be cleared;
  - a long model name pushing effort out of the card;
  - Test confusing two agents that share a voice at different speeds;
  - the tests not holding the delegate's index binding;
  - the tool test not checking the list's length.
- **Pass 2** (5 findings, all fixed in 314d726):
  - the picker's preferred width fed back from its given width;
  - an effort called stale before the daemon had built the agent;
  - the effort half unbounded;
  - Test's button comparing the raw speed with the pace played;
  - the sample test passing with the pace unrecorded.
- **Pass 2's fixes were not re-reviewed by Codex** (credits, below). They
  have their own tests and five mutations, and the preview checks were
  rerun on them.

## Found along the way

- **A `TestEvent` whose parent is not an item sends keys nowhere.** The
  preview's window is never the compositor's focus window, so keys go to
  the parent item's window. The overlay root is not an item, so the
  keyboard walk creates its TestEvent inside the page.
- **The old `tools` target assumed the real config's main agent inherits
  its browser.** It does not here (`mainTools.browser = "off"`), so two of
  its checks would have failed on the old page too. They now derive the
  expected warning from the agent's state.
- **AgentFolders' `saveAgents` and `Settings.assignVoice` copy entries by
  assignment too**, so a `__proto__` field would be lost there as well.
  Old code, not changed here (open issue 4).

## Not verified

- **The new page in the real shell.** It needs `omarchy-restart-shell`,
  which is held for stop point 2. It was seen only in `preview.sh`: wide,
  narrow, dark and light, the clicks diff, the round trip and the keyboard
  walk.
- **▶ Test playing a voice aloud.** The command it builds is tested; the
  sound was not heard.
- **A real pointer and a real keyboard on the page.** All the clicks and
  keys were synthetic (QtTest's TestEvent).
- **The `voices` preview target** was not rerun. It downloads and deletes
  real voice files. Its one Agents-page step (the "Edit in Agent details"
  link) is held by test_agent_pages and was driven in the round-trip
  target's flow.
- **The upgrade on the real `shell.json`.** The keys are unchanged, so
  nothing migrates. The page has not been opened against the real config
  in the real shell.

## Going back

`bin/agentvoice-deploy 72c9589b30af` from the clone, then
`omarchy-restart-shell` for the QML. No stored data changes: every key
keeps its name and value. An older build draws the tools for every agent
at the foot of its Agents page again.

## Open issues, for the next phase

1. **Question 9 taken by default: no mockup extras** (mic picker,
   per-agent talk while working for the main agent, "ask" for notes,
   per-agent speak replies).
2. **Codex credits overspent again**: 38.44 against about 7.5 (below).
   Pass 1's diff was 5,079 lines, including the tests, the preview harness
   and the docs, even though the prompt asked Codex to skip the last two.
   **149.95 left for M6–M29, about 6.2 per phase.** For the runner:
   - build REVIEW.diff from product code only
     (`git diff … -- '*.qml' daemon bin install.sh`);
   - consider one pass per phase on a large phase, or `low` effort for the
     second pass.
3. **Pass 2's fixes were not reviewed by Codex.**
4. **`AgentFolders.saveAgents` and `Settings.assignVoice`** copy
   `voiceAgents` entries by assignment, so a field named `__proto__` is
   lost when either rewrites the list. Old code, and unlikely in practice.
   The page's `copyEntry` is the fix if wanted.
5. **A very long program · model pill** (a 70-character custom model)
   leaves room for no other pill on the strip. The pill could elide.
6. **The tools chips need two clicks from "every agent" to "off"**, and
   each click writes. Should the cycle be every agent → off → on, or should
   a menu replace it?
7. **Carried, still open:**
   - M4's open issues 4–13 (none touched here);
   - the Voice library trash icon (M25);
   - M0's small test and bench fixes;
   - agy's `carries_session_across`;
   - the runner's sandbox test command (`codex sandbox linux -- true`
     panics).

## Codex credits used

**38.44**. The balance went from 188.39 at the end of M4 to 149.95, read
from the session logs' `rate_limits.credits.balance`. It was still 188.39
at this phase's first call, so nothing came in between.
- **Pass 1: 28.66** (188.39 → 159.73). `gpt-6.2-astra`, medium effort,
  sub-agents disabled, read-only copy, the whole phase diff (5,079 lines):
  77,694 tokens.
- **Pass 2: 9.78** (159.73 → 149.95). The same settings, on pass 1's fix
  diff only (320 lines): 35,877 tokens.

**149.95 left** for M6–M29.

## Live checklist: what was said, what happened

- Before the deploy, `agentvoice status`: state `listening`, every agent
  idle (main, sora, jarvis-ajc).
- After the deploy, `shell.json` was byte-identical to the copy taken
  before.
- Nothing said by voice, no typed turn (the daemon did not change), no
  shell restart, no settings changed.
