# Phase M31: Skills redesign, the M30 release blocker

Written 2026-11-27 to 2026-11-28, interactively, with the user at the desk.
Branch `phase-m31`, cut from `phase-m30` at 477c7c0. Model: Claude Opus 5.5.
M31 has no section in the master plan: its scope is the user's decisions of
2026-11-27 in phaseM30notes.md ("M31, as the user decided"), plus the four
answers below, plus one fix the user asked for during the live check (the
tool rows).

**Result: done.** Both screens rebuilt as decided, deployed, installed and
seen by the user in the real shell ("perfect"). The M30 release candidate
reruns on top of this (not started here).

Commits:
- 720f047: the phase;
- 0d55a84: Codex pass 1 fixes (5 findings, all fixed);
- b227e04: Codex pass 2 fix (3 findings: 1 fixed, 2 answered below);
- 8f8db88: one line per tool on Agent details, asked for by the user
  during the live check; **not reviewed by Codex**;
- then these notes.

Pushed: `phase-m31` to `fork` only. `dev` and `main` not moved (both still
963e738): fast-forwarding them is the M30 rerun's step 3, or the user's
call.

**Codex review: both passes run** (credits below).

Deployed: **yes, twice**, through `bin/agentvoice-deploy` (its strict check
green both times):
- `--install b227e04` at 2026-11-28 00:02:39, replacing 963e738. The daemon
  was idle (`listening`, every agent idle). "Build 0.2.0 (b227e04),
  replacing 0.2.0 (963e738)"; service restarted 00:02:42.
- `--no-install 8f8db88` at 00:57:17, replacing b227e04 (QML only;
  `agentvoice about`: "no daemon file differs between them, so the service
  is current").

**Shell restarted twice, with the user's approval**: 00:03:10 (quickshell
PID 1333 → 222062) and 00:57:46 (222062 → 334189). This run was in its own
systemd scope (`app.slice/m31-terminal-*.scope`), so the service restart
could not kill it (the first M30 run's lesson).

`shell.json` was copied before the deploy
(`~/agentvoice-notes/shell.json.before-M31`, 0600). At the end it differs
only by the user's own changes during the live check: `communalSkills`
`{"add": ["docs", "docx", "omarchy", "pdf"], "remove": []}` (written through
the new confirm), `crossCheckMinMs` 200 → 300 and `sherpaThresholdPct`
10 → 20. Nothing this run executed writes a setting.

`./bin/agentvoice-check`: green before every commit and on the final tree.
- **5395 tests** (M30: 5337; +58), 14 of 14 static checks, "the check wrote
  nothing in the tree: ok".
- Bare-runner variant (`AGENTVOICE_STRICT=1`, a venv with only
  requirements-dev), on b227e04: **green**, 5378 passed, 9 skipped (the same
  numpy-only skips as before).
- Box: not run (`install.sh` did not change).

## The decisions

From phaseM30notes.md (2026-11-27), built as written:

- Agent details → Tools & skills: only the selected agent, "From communal"
  (each with Exclude, its `skillsOff`) and its own skills (on/off). No other
  agents' lanes, no Unused.
- Communal → Skills: the communal skills at the top, each with Remove behind
  a confirmation; below, every available skill with a search field and a
  toggle each.
- A skill every agent already has is communal automatically.
- Communal is a grouping: no copies, and the list names who lacks a skill.
- Removing an automatically communal skill returns it to each agent's own
  skills, still on, and keeps it out of the automatic rule until added back.
- Adding to Communal keeps its confirm.

Asked at the start of this run (2026-11-27), each answered with the
recommended option:

1. **The M15 opt-out (`communalOff`) and the grouping**: grouping only. The
   opt-out keeps covering rules, defaults and communal-folder skills; an
   opted-out agent has no "From communal" section, all its skills are its
   own and it keeps them.
2. **Who counts as "every agent"**: every agent whose program takes skills
   (not an endpoint or no program) and that takes Communal, switched on or
   not. An agent's Exclude does not stop it "having" a skill; a skill
   switched off in the program's own settings (Claude Code's
   `skillOverrides`, Codex's `[[skills.config]]`) does.
3. **M12's drag, Move to…, Undo and M11's Give a copy**: dropped from the
   pages. The CLI keeps `agentvoice skills move|copy|import|undo|history`,
   their `--confirm` and journal, unchanged. The delegation flow (later)
   decides how they come back.
4. **The built-in Omarchy and Agent Voice skills**: left under Tools (one
   control each), not in the skill lists.

Decided here, not covered by the notes (told to the user with the first
screenshots):

- **At least two counted agents** before anything is communal
  automatically: with one, every skill it has would be "communal".
- A skill kept only in one agent's Agent Voice folder is lacked by the
  others "not in its skills folder", not "Claude Code has no skill of this
  name".

Asked later: finding (i) (the intermittent `test_history` failure, and the
check printing a failing test's traceback) **stays with the M30 rerun**
(user, 2026-11-27).

## What was built

**Setting `communalSkills`**, three homes (the check holds them): manifest
default `{}` (defaults-only, a map, like `mainTools`), `runtime.DEFAULTS`
`{}` (no TOML alias: the fallback config has no Communal page), and
Communal → Skills, its one writing page (`test_settings_pages`' table, the
settings search index). `runtime.communal_skills_choice`: `{"add": [...],
"remove": [...]}`, skill names (`SKILL_REF`), at most 256 each, no name in
both. Missing or null is neither. Anything else is **unreadable**, read as
the automatic rule alone; the page then refuses to write over it and says
why. `Config.communal_skills()` reads it fresh. **No delivery path reads
it** (a test lists the readers: `runtime.py` and `skillscan.py` only).

**`skillscan.grouping(cfg, scanned)`**, read by `agentvoice skills communal
[--json]` (not asked by the orders guard: a read): every skill any agent
has, by name. An agent *has* a skill when it is in its own folder, in the
communal folder (when it takes Communal), or found by its CLI and offered
(not a second copy of a name, not switched off in the CLI's own settings).
Each row: who has it, who excluded it (`skillsOff`), who lacks it and why
(takes no skills / takes nothing from Communal / switched off in your own
Claude Code settings / Codex has no skill of this name / not in its skills
folder), its sources, `auto` (every counted agent has it, at least two),
`added`, `removed`, `communal` = (auto and not removed) or added. An added
name nobody has now stays listed, so it can be removed. Keep data and path
come from the communal folder's own copy when it has one.

**`skillscan.cards(entries, communal, takes_communal, agent_id)`**: one
agent's tab, one card per name; the given copy is the card and the others of
that name go in `also` with why; `section` "communal" when the name is
communal, the agent has it and takes Communal, else "own".
`agentfs.catalog` now returns `skill_cards` and `communal_readable`, and no
longer `skill_lanes` (one scan per read instead of two).

**Agent details → Tools & skills** (`pages/AgentDetailsPage.qml`): two
`ui/Card`s. **From communal** (`objectName: fromCommunal`): each card with
**Exclude** / **Include again** (`switchSkill`, i.e. `setAgentSkill`, the
existing writer of `skillsOff`; no confirm, as M11's switch never had one)
and Keep when changed outside. **<Name>'s own skills** (`ownSkills`): a
switch each. An opted-out agent's From communal says why it is empty. The
lane, mover, import and drop code is gone (−~300 lines).

**Communal → Skills** (`pages/CommunalPage.qml`): an intro (a grouping,
nothing copied, the automatic rule, Exclude on each agent's tab); one line
for each agent that cannot take part (takes no skills, or opted out);
**Communal skills** (`communalList`), each with **Remove…**; **All skills**
(`allSkills`), a `SearchField` over name and description, a switch per
skill. Remove… and the switch only *ask* (`askCommunal`); an inline
`ToolConfirm` under that card says who has it, who does not and why, and
that no copy is made (adding), or that it goes back to each agent's own
skills still on, nothing switched off, and stays out until added back
(removing). `setCommunal` is reached only from those confirms' `onConfirmed`
and writes through `communalEdited`, which refuses an unreadable value.
Lacks are grouped by reason ("Not Theo or Sora (Claude Code has no skill of
this name)"); a multi-source badge reads "~/.claude/skills +1".

**The tool rows (asked by the user during the live check, 8f8db88)**: each
built-in and found tool on Agent details is one line, the name with As
every agent / On / Off on its right. Under it only why it cannot be used, a
change since it was turned on, or a ⚠ warning (`toolAlert`). The status in
words, what it asks and a CLI's "told, not enforced" fold behind the row's
"?" (`toolHelp`). The definition paths are gone from the row; the confirm
before a tool is turned on still shows what it runs and where it is
defined. Too narrow for one line (under 560 px), the buttons go underneath.

**Removed**: `ui/SkillMover.qml` (no caller left) and the `transfer` preview
target (`transfer.qml`, `transfer.seed.py`); `configs/transfer3.json` stays
(the communal and notemoves targets use it). `ui/SkillCard` says "Ctrl+M
opens Move to" to a screen reader only when draggable.

**Preview**: the `skills` target rewritten for the new screens (26 checks),
with shot modes `shots`, `shots-tools`, `shots-communal`, each `:WIDTH` to
draw the card at that width. `preview.sh`'s synthetic machine gains
`screen-notes` in both Claude Code's and Codex's folders, so one native
skill is communal by itself.

**Docs**: CODEBASE (skillscan, both pages, the CLI table, SkillMover's row
removed), README ("Skills on this machine" rewritten; "Moving a skill"
replaced by the CLI paragraph), FINDINGS §58.

## What was proven, and how

- **Tests**: new `tests/test_communal_skills.py` (69): the setting's shapes
  (14 cases), unreadable settings, three homes; who has what (auto, the
  communal folder, excluded still had, CLI-switched-off not had, one name
  once, endpoint and opted-out agents not counted, a switched-off agent
  counted, one agent alone, `is_auto`); add, remove, added back, a name
  nobody has, unreadable = automatic only; **the grouping gives and
  withholds nothing**: for three settings (four adds, two removes, an
  unreadable value), every agent's `native_off`, its tab's delivered flags
  and its Claude plugin folder are identical before and after; nothing
  outside runtime and skillscan reads it; cards (one per name, sections,
  `also`, opted out); the catalog; removing an automatic one returns it to
  every agent's own, still on and given; the CLI; the guard does not ask;
  the pages: `setCommunal` only from the two confirms, Remove and the
  switch only ask, the confirm texts, Exclude is `skillsOff`, no other
  agent's skills, search and switch present, plain text; `communalEdited`
  in node (13 cases); lack grouping in node; the five pass 1 fixes and the
  pass 2 fix. Rewritten: `test_transfer_ui.py` (no page builds `skills
  move|copy|import|undo` or adds `--confirm` for them, no drag left, SkillMover
  gone). Updated: `test_confirms` (setCommunal allowed on a ToolConfirm),
  `test_settings_pages` (the defaults-only key), `test_agent_pages` (Communal
  writes seven keys), `test_skillscan` (the import stays a CLI verb),
  `test_tool_controls` (one ToolConfirm on Agent details; one-line tool rows,
  `toolAlert` in node).
- **Mutations: 14 run, all caught** (scratch copy under /tmp, never the
  clone): cards ignoring the agent's own holdings, Keep from the first copy,
  one agent counting as "every", user-off counted as had, `remove` ignored,
  opted-out agents counted, the "not in its folder" reason, the opt-out
  section rule, the confirm's readability check removed, both `communalEdited`
  branches, the runtime's add/remove overlap check: 12 red at once. The
  scan-failure `ms` fix survived alone, because the catalog's fallback was
  fixed too (either holds); with both reverted the test goes red.
- **`skills` preview: 26 of 26 PASS** on the final QML (real CLI, scratch
  data, synthetic pointer events, the real pointer never moved): Sora's two
  sections and nothing of another agent's; one weekly-report card with
  Claude Code's copy under Also in; Exclude and Include again write her
  `skillsOff`; her own switch writes the same list; Communal skills lists
  the three every agent has; All skills lists the 10 skills agents have, and
  deploy-site says why Theo and Sora lack it; the search finds tea-timer
  alone; adding docx asks, names who has it and that Hazel does not, writes
  nothing before the answer or on Cancel, then writes `communalSkills.add`;
  Remove… on screen-notes asks, says nothing is switched off and it stays
  out until added back, writes `.remove`; back on Sora's tab docx is From
  communal and screen-notes her own, still on and given. The writes log
  holds exactly those six writes.
- **`tools` preview (M10's): 29 of 29** after the tool-row change.
- **Screenshots** (`/tmp/m31-shots`, not committed): narrow 520 and wide 880,
  dark, both screens; flexoki-light narrow, both screens; the tool rows wide
  and narrow. No shots run wrote anything.
- **Live, in the real shell, by the user** (8f8db88 deployed, after the two
  shell restarts): both skills screens looked at with the real agents
  ("Screens are fine", then "perfect"); on this machine omarchy-app and
  workmap-pages are communal by themselves, as the M30 notes predicted; the
  user added docs, docx, omarchy and pdf to Communal through the confirm
  (seen in shell.json); the tool rows were asked for, rebuilt, deployed and
  seen.

## Shared files touched, and where

- `pages/AgentDetailsPage.qml` (big shared, 3452 → 3252): the skills
  section, its helpers, the tool rows.
- `pages/CommunalPage.qml` (1217 → 1334): the Skills tab and its helpers.
- `daemon/skillscan.py`: `grouping`, `cards`, `has_names`, `is_auto`, the
  `communal` verb. `daemon/agentfs.py` (big shared, +~15): `catalog` only.
  `daemon/runtime.py`: the reader, `DEFAULTS`, `Config.communal_skills`.
- `manifest.json` (one default), `ui/SettingsIndex.js` (one entry),
  `ui/SkillCard.qml` (one line), `ui/qmldir`.
- Nothing in the daemon's turn loop, the adapters or the permission hook.

## Measured

FINDINGS §58 (i7-1185G7, load 1.3 to 1.8, the real machine's 37 skills):
`agents catalog main` median **0.441 s** at M31 against **0.525 s** at
963e738 (7 alternated runs; one scan per read instead of two);
`skills communal` scan 29.8 to 33.4 ms. Tests 5337 → 5395; the check's test
run about 6 min 30 s. (The RC's baseline, which M30 reserved §58 for, goes
in §59.)

## Different from the plan, and why

- **No master plan section**: the scope is the user's decisions (above).
- **The tool rows** were outside the decided scope; the user asked for them
  during the live check ("one quick fix"), so they are in this phase, as
  their own commit, not reviewed by Codex.
- **Remove… uses an inline ToolConfirm, not a DangerButton**: removing from a
  grouping destroys nothing (CLAUDE.md keeps DangerButton for that), and the
  confirm has room to say what happens to each agent. Adding uses the same.
- **Exclude asks nothing**, like M11's switch: it narrows one agent.
- **`skill_lanes` left the catalog** and `skills lanes` has no page reader;
  the verb stays for the CLI.
- **Codex read the diff from its prompt** instead of from the read-only copy
  (below), so it could not open other files for context.

## Found along the way

- **Codex's own sandbox does not work here**: `codex exec --sandbox
  read-only` fails every command with "bwrap: Can't open source /: Function
  not implemented" (the first pass 1 attempt reviewed nothing, 12,621
  tokens). Running without its sandbox on the read-only copy was refused by
  this session's permission system. What worked: keep `--sandbox read-only`,
  put the diff in the prompt, and tell Codex not to run commands.
- **The preview's crop follows the focused monitor**: one run shot the
  wallpaper because focus had moved to the other monitor while the user
  worked; retaken.
- **`SearchField` fires `searched` only on a real edit** (`onTextEdited`),
  and key events never reach the preview window (M12), so the target sets
  the text and sends the signal itself. Typing in the field was seen only in
  the real shell, by the user.
- **The daemon's memory** (M30 finding d) read 1598 MB before the install
  restarted it; not investigated (Phase 17).

## Not verified

- **The keyboard on the two changed screens in the real shell**: Tab to
  Exclude, Include again, Remove…, each switch and the search; Space/Enter
  on them; Escape and Enter on the inline confirm. The preview cannot send
  keys; the structural keyboard tests pass.
- **Exclude / Include again and Remove… in the real shell with the real
  agents**: the user's shell.json shows only adds; whether the others were
  tried is not recorded. Preview-driven only.
- **That an excluded or removed skill changes what a real agent is
  offered**: by design Remove changes nothing and Exclude is M11's
  `skillsOff`, proven by fixtures; no typed turn asked an agent for its
  skills (widening checks on real agents stay refused unattended; this run
  wrote no setting).
- **The light theme and a screen reader in the real shell** for both
  screens (preview light shots only).
- **Codex review of 8f8db88** (the tool rows).
- **The installer box** (`install.sh` did not change).

## Open issues

1. M12's page-only open issues (auto-scroll while dragging, moving a broken
   skill, Undo into Communal asking, a stuck transfer notice) are moot on the
   pages now; the CLI behaviour is unchanged.
2. The delegation flow for skills and tools as a whole, and the cramped
   window: out of scope by the user's decision, for later. Moving a skill
   between agents, and importing one from outside, are CLI-only until then.
3. A skill that the program's own settings switch off (`omarchy`,
   `diagnose-crash` for the Claude agents here) shows under the agent's own
   skills with a switch that cannot turn it on; the card says why. Hide the
   switch?
4. Everything carried in phaseM30notes.md's "Found along the way" and
   "Known limits", including finding (i), stays with the M30 rerun.

## What the M30 rerun must redo because M31 touched it

- **Step 3** to the M31 result (`phase-m31`), not 963e738: `dev` and `main`
  are still 963e738.
- **Steps 4 and 5**: 8f8db88 is deployed and b227e04 installed, so a rerun
  that deploys the notes commit changes no file the service runs; step 5's
  proof must be redone against the new commit (hashes, `agentvoice about`).
- **Step 7**: the S, prompt-size and memory pairs against the M31 build
  (M31 does not touch a turn, so no change is expected); FINDINGS §59.
- **Live checks to redo**: S2 (a skill off for one agent, now from its own
  switch or Exclude), S3 (the communal opt-out: an opted-out agent shows
  everything as its own and keeps it), the skills part of bug G, and S1 (a
  found tool on for one agent) because the tool rows changed; the keyboard
  walk on Agent details → Tools & skills and Communal → Skills; light theme
  on both.
- **The mapping table**: item 11 and item 15's skills part are delivered by
  720f047, 0d55a84, b227e04 (and 8f8db88 for the tool rows); item 11's
  "draggable skill cards" (M12) is now CLI-only by the user's decision.
- **Codex**: M31 is reviewed (both passes); a15e78a..963e738 is still owed
  (the guard-set review the M30 notes moved to the rerun).
- The M30 notes' "Not done" list is otherwise unchanged by M31.

## Going back

To before M31: `bin/agentvoice-deploy --install 963e738` from the clone (the
installer, once the daemon is idle), then `omarchy-restart-shell`. To before
the tool rows only: `bin/agentvoice-deploy b227e04` and a shell restart
(QML only). An older build ignores `communalSkills`, which gives and
withholds nothing anyway, so going back changes no agent's skills; it
brings back M12's lanes and moves. Nothing to finish first: M31 started no
transfer and wrote no agent folder.

## Codex credits

Read from `rate_limits` in the newest `~/.codex/sessions/**/*.jsonl`:

| When | balance | 5 h used | 7 d used |
|---|---|---|---|
| before pass 1 (last session, 2026-11-25) | "0" (`has_credits` false) | 0.0 % | 0.0 % |
| after pass 1 (both attempts) | "0" | 3.0 % | 1.0 % |
| after pass 2 | "0" | 8.0 % | 1.0 % |

Plan `plus`; both passes ran on plan quota, no credits. Every pass:
`gpt-6.2-astra`, `-c model_reasoning_effort='"medium"' --disable
multi_agent --disable multi_agent_v2`, `--sandbox read-only`, on a
read-only copy (`git archive` of HEAD, `chmod -R a-w`) with the diff in
REVIEW.diff and in the prompt.
- Pass 1 attempt 1: the sandbox failure above, nothing reviewed, 12,621
  tokens.
- Pass 1: the product diff (`daemon pages ui manifest.json`, 1,688 lines),
  at most 8 findings: **5** (an open confirm writing after the setting turned
  unreadable; a failed scan breaking the grouping; a CLI-switched-off skill
  under From communal; Keep from the wrong copy; a name nobody has in All
  skills). All fixed in 0d55a84. 33,426 tokens.
- Pass 2: the fix diff (146 lines), at most 5: **3**. Fixed: the row's
  Where pointing at an agent's copy while Keep acts on the communal one
  (b227e04). Answered, not changed: (a) "the confirm could write over an
  unreadable file": the store reads an unparseable shell.json as empty, but
  `omarchy bar set` cannot write an unparseable file either, and a readable
  one gives `communalEdited` exactly the value it validates, the posture of
  every setting writer; (b) "mark the grouping unreadable when it raises":
  that would show "communalSkills cannot be read", blaming the wrong thing;
  the failure is reported through `skills_error`. 13,739 tokens.

The clone's HEAD and status were unchanged after each pass, and each copy
was deleted straight after.
