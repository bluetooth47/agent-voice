# Phase M11: Skills: scan, lanes, assign

Written 2026-11-22, unattended (started by the runner script). Branch
`phase-m11`, cut from `phase-m10` at 04cdc86. Result commit: the notes
commit on top of c912e54, pushed to `fork/phase-m11` only; `dev`
fast-forwarded to it and pushed to `fork`. Model: Claude Opus 5.5 (tier B in
the plan).

Commits:
- 18c91f2: the phase;
- 9d2f825: Codex pass 1 fixes (5 findings, all fixed);
- cc4b7de: Codex pass 2 fixes (3 findings, all fixed);
- c912e54: a fix found by the live check after the install (one name in
  two of Codex's skill folders listed twice); not reviewed by Codex;
- then these notes.

Deployed: **yes**, twice, through `bin/agentvoice-deploy --install` (its
strict check green both times). cc4b7de replaced M10's 2a83bb1, then c912e54
replaced cc4b7de. The daemon was idle both times (state `listening`, every
agent idle, no open mic, no task, unlocked). **The way back to before M11 is
`bin/agentvoice-deploy 2a83bb18e698`.**

Installed: **yes**: "Build 0.2.0 (c912e54), replacing 0.2.0 (cc4b7de)".
The daemon, both adapters, the hook and the CLI changed.

**Shell restart needed** (Agent details' skill lanes, Communal → Skills,
`ui/SkillCard.qml`). Not run. Until it is, the running shell has M10's QML:
the old two-list Skills section with no switches, and Communal → Skills
reading `agents skills communal` (still there, unchanged), so nothing is
broken meanwhile; there is just no way to switch a skill off from the UI.

A copy of `shell.json` was taken before the first deploy
(`~/agentvoice-notes/shell.json.before-M11`, mode 0600); after each deploy
and at the end of the live checks `shell.json` was byte-identical to it. No
live check wrote any setting.

`./bin/agentvoice-check`: green on c912e54.
- **3932 tests** (was 3844; +88), 14 of 14 static checks, "the check wrote
  nothing in the tree: ok".
- The bare-runner variant (`AGENTVOICE_STRICT=1`, a venv with only
  requirements-dev): **green** on c912e54 (3916 passed, 9 skipped: the
  existing numpy-only skips, the same 9 as M10).
- Box: not run (`install.sh` did not change).

## The spike

Recorded in `tests/fixtures/skills/spike-m11.json` (replayed by
`test_skillscan.py`) and FINDINGS §45. Claude: seven Haiku turns with Agent
Voice's argv shape, reading the init event's `skills`, and two asking the
Skill tool to load one. Codex: `codex debug prompt-input`, which renders the
prompt the model would get **without a model call**: no credits, and no
real Codex turn.

- **Claude Code offers every skill in `~/.claude/skills`** (links
  followed), **the claude.ai account's synced skills**
  (`~/.claude/skills/synced/<bucket>/`, as `anthropic-skills:<name>`),
  enabled plugins' skills and its bundled ones, less the person's own
  `skillOverrides`. On this machine: 35, Agent Voice's among them, whatever
  the Tools & skills tab said.
- `--settings '{"skillOverrides":{"minecraft":"off"}}'`: gone from the init
  event, and **the Skill tool refuses it** ("disabled for model invocation
  in skillOverrides settings"). A bare name also hides the synced skill of
  that name, **never the agent's own `agentvoice:` copy**. An unknown name is
  ignored. A `--plugin-dir` skill cannot be switched off this way, so Agent
  Voice leaves its own off skills out of the plugin folder.
- **Codex reads `~/.codex/skills`, its own `.system`, its plugins' and
  `~/.agents/skills`** (Omarchy links its skills into the last two). A name
  in both is listed once, from `~/.codex/skills`.
- `-c skills.config=[{name="x",enabled=false}]` switches one off; a plugin
  skill needs `plugin:name`; a name that says off beats a path that says on;
  **config.toml's own entries are merged, not replaced**; an unknown name is
  ignored.

## What was built

**Scan** (new `daemon/skillscan.py`): every skill Claude Code and Codex
find by themselves, read only (directory listings and SKILL.md heads, no
process: tested), bounded (200 for the pages, 400 entries a folder, 64 KB of
a SKILL.md). Each card: name, description, source and path, size and file
count, its problem, whether it could be copied in and why not, the names it
goes by (folder and front matter), and `user_off` when the person already
switched it off in the CLI's own settings (Claude's `skillOverrides`,
Codex's `[[skills.config]]`).

**Setting, three parts** (the check holds them): `mainSkillsOff` (manifest
default `[]`, defaults-only like the other lists; `runtime.DEFAULTS` `[]`;
TOML alias `agent.main_skills_off`) and `voiceAgents[i].skillsOff`, written
only through the new overlay function `s.setAgentSkill(id, name, on)`,
called from Agent details only (`FIELD_HOMES`, `OUTSIDE_WRITERS`,
`OVERLAY_HOMES`). Names: a folder's or a plugin's `plugin:name`. **One name
is one switch**: the agent's own copy, the communal one, the one its CLI
finds, and (pass 1) the bundled Omarchy skill for `omarchy`. Missing = every
skill it would get, as before M11. **Unreadable** (not a list, a non-name
entry, over 256, unreadable settings, an agent the settings do not have) =
no communal skill and none its CLI finds; its own folder's still given.
`setAgentSkill` leaves an unreadable list alone rather than rewrite it.

**Delivery** (`skillscan.native_off`, `Daemon.native_skills_off` in
`apply_extras`):
- an off skill is left out of the Claude plugin folder (the switch list is
  in `plugin_dir_for`'s cache key) and out of the index other backends are
  told;
- **Claude**: `skillOverrides: {name: "off"}` in the `--settings` already
  passed, at every level, for every name in the list, every name it goes by,
  and every Agent Voice skill's name (so the CLI's own of that name is never
  offered beside it);
- **Codex**: one `-c skills.config=[...]`, each name checked again against
  the pattern before it is written into the TOML value;
- unreadable list: every name the CLI finds, from a full listing; when that
  listing cannot be had (a folder unreadable or too large, the plugin list
  unreadable), **Claude gets no skill at all** (`--disable-slash-commands`)
  and **Codex starts no turn**, said once in the journal;
- a change lets the warm process go, as the tools do.

**Assign = import a checked copy** (`agentfs.import_skill`, `agentvoice
skills import SOURCE_ID TO`): a source is named by its id from a scan made
then, never a path; the rules every skill keeps (`parse_skill`: name, front
matter, no hooks, sizes; `walk_skill`: no link inside, plain files, 64 files,
2 MB, 256 KB a file); read beneath its folder with no link followed at any
level; hashed before and after; staged and published inside the skills folder
by its open descriptor with a no-replace rename (pass 1); its SKILL.md's
version saved first (pass 1), so it reads as kept; one `skill_import` audit
line of name and size. The original is never written. The orders guard asks
when an agent runs `agentvoice skills import` (`SKILL_WORDS`), at every
level.

**Pages**:
- **Agent details → Tools & skills**: lanes of `ui/SkillCard`s in
  `ui/DropLane`s (two across when wide): this agent's (its own and those its
  program finds, each with a switch), Communal (a switch for this agent),
  every other agent's (read only), and Unused (found outside, no agent gets
  it), each Unused card with Give a copy to this agent / to Communal through a
  `ToolConfirm` (where it is copied from, size, who gets it, the warning),
  whose `onConfirmed` alone runs the import (structural test). A card unfolds
  to description, source, size, problems, shadowing and who gets it. The tab
  says what "off" does and does not do, and what its program has that Agent
  Voice does not switch. Dragging between lanes is M12; a lane refuses a drop
  with that reason.
- **Communal → Skills**: reads `agentvoice skills lanes`; one line per
  agent on how it takes skills or why none (endpoint, no program, a program
  Agent Voice cannot run; Codex and the others "told a list"); each skill
  says who gets it and who does not and why (its own / switched off / takes
  none).

**Preview**: `preview.sh` gives its `agentvoice` stub a scratch `HOME` (so
`~/.agents/skills` is never the person's) and synthetic skills in each source,
and routes `skills`; new target `skills` (seed `skills.seed.py`, config
`configs/skills3.json`), with a `shots` mode for screenshots.

**Docs**: CODEBASE (skillscan, both adapters, the pages, SkillCard,
settings, CLI, data), README ("Skills on this machine"), CLAUDE.md (the ninth
rule now covers skills), FINDINGS §45.

## What was proven, and how

- **The spike** (above): Claude turns recorded; Codex rendered prompts.
- **`skills` preview: 18 of 18 PASS** on the final QML: Sora's tab lists
  exactly the synthetic machine's skills (her own, communal, Claude Code's);
  the broken one listed with why; Claude Code's weekly-report hidden by the
  communal one; Unused holds what nobody gets; switching big-guide off
  writes her `skillsOff` and moves it to Unused, where it says it is too long
  to copy; Give a copy asks, names the source and "Sora only", copies nothing
  before the answer or on Cancel, and Give a copy makes it hers, given, not
  "changed outside"; a communal skill switched off and back on for her alone;
  Communal → Skills reads three lanes and says Hazel is told a list. The
  writes log holds exactly three `voiceAgents` writes, Hazel's own list
  untouched.
- **Screenshots** (`/tmp`, not committed): wide 1280×800 dark and
  flexoki-light, seven shots each; narrow 520×720 dark, nine shots. Two text
  fixes from them (the honest "files stay readable" note and the Unused
  subtitle were elided).
- **Tests** (`test_skillscan.py`, 88; plus the shared tables): the setting,
  unreadable cases, `skill_set` with the switch, plugin folder and index,
  the scan per source (links, synced, plugins, `.system` left out), no
  process, malformed and linked skills, bounds, unreadable folders, aliases,
  `user_off`, `native_off` and its fail-closed paths, `agent_view`, lanes,
  duplicates, both adapters (and the recorded shapes replayed), the daemon
  (a switch lets the warm process go, nothing changed lets nothing go, an
  unreadable list, an unlistable folder stopping Codex), the import (whole,
  original unchanged by hash, modes, kept, audit line, each rule refused with
  nothing left, clash, reserved, ids not paths, no folder, changed mid-copy, a
  folder swapped for a link mid-copy, the skills folder swapped after the
  check, a folder appearing before publish, history failures, no
  renameat2), the hook words, the confirm path, `setAgentSkill` in node.
- **Mutations: 37 run, 35 red.** 24 on the phase (19 the first time; three
  more once the tests were tightened; one, the import's own reserved-name
  check, showed the check was redundant with `parse_skill` and the check was
  removed; **one survives as an equivalent mutant**: removing the import's
  first clash check, because the re-check just before the rename still
  refuses); 10 on pass 1's fixes; 3 on pass 2's. All in scratch copies under
  `/tmp`, never in the clone.
- **Live, on the installed daemon** (typed, synthetic):
  - `agentvoice skills lanes` and `agents catalog main`: Theo and Sora get
    minecraft, omarchy-app, workmap-pages and the 14 synced skills;
    diagnose-crash and omarchy are marked "switched off in your own Claude
    Code settings" and sit in Unused; Hazel's lane after the fix in c912e54
    is diagnose-crash, omarchy, omarchy-app, workmap-pages, as Codex lists
    them; scan 33 ms, no problems;
  - typed to Theo, "the names of the skills your Skill tool can load": his
    reply listed minecraft, omarchy-app, workmap-pages, Agent Voice's
    Omarchy skill, Claude Code's bundled ones and the anthropic-skills ones,
    and neither of the two the person switched off: exactly his lane plus
    the bundled ones. **The default is unchanged**;
  - his process's `--settings` held `permissions` and `hooks` and no
    `skillOverrides` (nothing switched off).

## Shared files touched, and where

- `daemon/wake_listen.py` (big shared, +~60): `skills_off_for`,
  `native_skills_off`, the switch list in `plugin_dir_for`'s key, the M11
  block in `apply_extras`, `reconcile_parts` passing the switch list. Nothing
  in the turn loop.
- `daemon/agentfs.py` (big shared, +~330): `walk_skill` (from `_skill_tree`),
  `valid_skill_name`, `skill_set(..., off)`, `plugin_dir(..., off)`,
  `parts_from(..., off)`, the roster and preview, `delivery_of`, the catalog's
  skills view and lanes, `import_skill` and its descriptor helpers.
- `daemon/permission_hook.py` (security-critical, +~10): `SKILL_WORDS` in
  `orders_write`.
- `daemon/runtime.py`: `SKILL_REF`, `skills_off_choice`, `mainSkillsOff`,
  the `skillsOff` field, `Config.skills_off_for`, `tools_for`'s Omarchy rule.
- `daemon/adapters/claude_code.py`, `codex.py`; `daemon/tooldetect.py`
  (`enabled_plugins` factored out, its bound now said); `daemon/audit.py`
  (`skill_import`); `bin/agentvoice` (`skills`).
- `Settings.qml` (big shared, +~50): `setAgentSkill` only.
- `pages/AgentDetailsPage.qml` (big shared, ~1960 → ~2210), 
  `pages/CommunalPage.qml`, new `ui/SkillCard.qml`, `ui/qmldir`,
  `manifest.json`.
- Tests: `test_settings_pages.py` (the new key and field), `test_confirms.py`
  and `test_tool_controls.py` (a second `ToolConfirm`, allowed only to
  import), `test_notes.py` (`copied_bytes` in the audit allow-list),
  `test_crew.py` (the new field), `conftest.py` (`~/.agents/skills` pointed
  at scratch for every test).

## Measured

On this machine (i7-1185G7, 8 threads), FINDINGS §45:
- **Scan**: 26 skills (5 + 14 synced for Claude, 4 + 3 for Codex), median
  **17.4 ms**, max 33 ms (n=25, a test run going).
- **Plugin folder with 20 skills**: **18.0 ms** median to build, 13.9 ms when
  it exists (every file is read to name it).
- **What the idle poll pays per agent for its switches**: 1.29 ms (Claude),
  0.93 ms (Codex).
- S on `sora`: not rerun (the index only shrinks; Claude's `--settings`
  gains one small key).
- Tests 3844 → 3932; the check's test run about 4 min 25 s.

## Different from the plan, and why

- **The skills a CLI finds by itself stay on by default.** The plan's
  "Unused (skills outside Agent Voice that no agent uses)" assumed they were
  unused; the spike showed every Claude agent is offered every one in
  `~/.claude/skills` (Theo uses minecraft), and the setting the plan names
  is an off-list whose empty value is "everything it would get". So they sit
  in the lanes of the agents that get them (as the mockup draws minecraft in
  Theo's lane), with a real off switch where the CLI looks, and Unused holds
  the ones nobody gets. Open issue 1.
- **The plan's honest note ("Claude Code agents can still see these")** is
  not needed: they can be switched off, and are. What the page says instead
  is that "off" takes a skill out of what the CLI offers and an agent that
  reads files can still open the file.
- **`~/.agents/skills` and the claude.ai synced skills are scanned** too:
  the spike found the CLIs read them. Codex's own `.system` skills, Codex
  plugins' and Claude Code's bundled ones are listed on the tab as not
  switched (open issue 4).
- **A skill's own top-level folder may be a link** (Omarchy installs its
  skills as links into `/usr/share`): followed, as the CLIs do; a link inside
  a skill is refused, as the plan says.
- **"omarchy" in a list also switches off Agent Voice's bundled Omarchy
  skill** (Codex pass 1), which the plan did not address.
- **Assign is a "Give a copy" button with a confirm**, not a drag (M12),
  and reuses `ToolConfirm` rather than a new piece.
- **The CLI verb is `agentvoice skills import ID TO`**, by the id a scan
  gives, not a path; M12's `skills import PATH TO` can extend it.
- **Codex reviewed the daemon, `bin` and `Settings.qml` diff** (1,390 lines)
  at low effort, capped at 5 findings; pass 2 the 425-line fix diff, capped
  at 3. Not the pages, tests or docs.
- **A real Codex turn was not used for the spike** (`debug prompt-input`
  only), and Hazel was not asked live, to save credits.

## Codex review

Both passes on the read-only copy (`codex sandbox linux -- true` still
fails: "Failed to execvp linux"), `gpt-6.2-astra`, low effort, sub-agents
disabled. The clone's HEAD and status were unchanged after both; each copy
deleted straight after.

**Pass 1** (5 findings, all fixed in 9d2f825):
1. The import checked the skills folder then wrote by path: a folder
   swapped for a link in between could redirect the copy. Fixed: opened
   component by component with `O_NOFOLLOW`, staged and published by
   descriptor, `renameat2(RENAME_NOREPLACE)`.
2. With an unreadable list, the names switched off natively came from the
   200-skill page view, so some could be missed. Fixed: a full listing,
   closing (SkillsUnknown) when a folder is too large or the plugin list
   unreadable.
3. A skill whose front matter names it otherwise than its folder was
   switched off by one name. Fixed: both names, from a stat-keyed alias map.
4. "omarchy" in the list left the bundled Omarchy skill on. Fixed in
   `Config.tools_for`.
5. The history version was saved after publishing; a failed save left a
   live skill. Fixed: saved first, removed if publishing fails.

**Pass 2** (3 findings on pass 1's fixes, all fixed in cc4b7de):
1. `enabled_plugins` read the first 64 installed plugins (disabled ones
   included) and said nothing past that. Fixed: counts enabled ones, records
   a problem past the bound, which the strict listing turns into a close.
2. The alias map was still built from the 200-skill view. Fixed: the full
   listing, closing when it cannot be had; nothing read with nothing to
   switch.
3. Without `renameat2` the fallback (check, then rename) could replace a
   folder made in between. Fixed: nothing is published there.

**Pass 2's fixes and c912e54 were not reviewed by Codex** (credits).

## Found along the way

- **The person's own `skillOverrides` already switch two skills off**
  (omarchy, diagnose-crash); the first scan reported them as given. Fixed
  before the review (`user_off`), with tests.
- **One name in two of Codex's folders was listed twice** (live, after the
  install). Fixed in c912e54.
- **The preview's stub read Omarchy's default agent from `$HOME`**: with the
  scratch home, Theo had no program in the preview; the skills config names
  `mainProgram` instead, so the preview no longer depends on the person's
  default.
- **The qmllint check reads tracked files only**, so a new QML file is first
  linted after it is committed (it passed on the first run and failed on the
  second for the preview target). Worth knowing for every phase.
- The narrow 520×720 preview crop shows the middle of the screen; the
  overlay itself does not shrink, so the right edge (the switches) is cut
  off in narrow shots. The wide shots show the whole layout.

## Not verified

- **The pages in the real shell.** They need `omarchy-restart-shell` (next
  stop point, after M15). Seen only in `preview.sh`. The keyboard paths on a
  card (Tab to it, Enter unfolds, Space toggles) and the confirm's focus and
  Escape were not driven; toggles and buttons only through synthetic clicks.
- **A skill switched off for a real agent, live** (the plan's typed check
  with a switch). It writes the real `shell.json`; not attempted. At the
  stop point: switch minecraft off for Sora on her Tools & skills tab, ask
  her which skills she can load (it should be gone, and Theo's should not),
  then switch it back on.
- **Hazel (Codex) asked which skills she sees**: not run (Codex credits);
  Codex's behaviour comes from rendered prompts (`debug prompt-input`), not a
  real turn.
- **Give a copy on the installed build**: driven in the preview only (it
  would write into a real agent's folder).
- **A Claude Code plugin's skill switched off by `plugin:name`**: no plugin is
  installed here; the shape is the one Codex accepts and Claude's init event
  uses, not recorded for Claude.
- **The fail-closed paths on a real machine** (an unreadable list with an
  unlistable folder): tested at the adapter and daemon only.
- **Pass 2's fixes and c912e54 were not reviewed by Codex.**
- **The installer box** (`install.sh` did not change).

## Going back

`bin/agentvoice-deploy 2a83bb18e698` from the clone, `./install.sh --yes`
once the daemon is idle, then `omarchy-restart-shell`. **That is fail-open
for anything switched off** (plan section 7.7): M10 has no `skillsOff`, so
every skill an agent's CLI finds, and every communal skill, is given again,
and the bundled Omarchy skill follows `omarchySkill` alone. The lists stay in
shell.json, unread. Copies given from Unused stay in the agents' folders as
plain skills (M10 gives them, like any skill there). Before going back, move
a skill you switched off out of the folders the CLIs read, or switch it off
in the CLI's own settings (`skillOverrides` in `~/.claude/settings.json`,
`[[skills.config]]` in `~/.codex/config.toml`).

## Open issues, for the next phase

1. **Skills the CLIs find by themselves stay on by default** (today's
   behaviour), each with an off switch. Section 11 has no question for it;
   question 3's "off, with the list" was about MCP servers. Chosen because a
   skill is instructions, not a capability, the setting is an off-list, the
   risk table asks new settings to default to today's behaviour, and Theo
   uses minecraft. Should they start off, like MCP servers, with a notice and
   one-click restore?
2. **Unused also holds a skill hidden by an Agent Voice skill of its name**
   (weekly-report in the preview) and **ones the person switched off in the
   CLI's own settings** (omarchy, diagnose-crash here). Correct by "no agent
   gets it", but Give a copy of the first clashes in Communal. Hide those
   from Unused, or label them?
3. **The person's `~/.claude/skills/omarchy` beside Agent Voice's bundled
   Omarchy skill**: when `omarchySkill` is on, Claude would offer both (the
   person's own settings switch the native one off here). Switch the native
   `omarchy` off whenever the bundled one is on?
4. **Codex's own `.system` skills, Codex plugins' skills and Claude Code's
   bundled skills are not switched** (the tab says so). Switching them by
   name works (recorded for `imagegen` and `pdf:pdf`). Add them as cards?
5. **A Claude plugin skill's off key (`plugin:name`)** is unrecorded for
   Claude (none installed). Record one when a plugin is installed.
6. **Codex merges `-c skills.config` with config.toml's** (0.171.0). If a
   later Codex replaces it instead, the person's own disables would be lost
   for Agent Voice's Codex turns. The fixture test would not notice (it
   replays a recording); a CLI upgrade should rerun the spike's last row.
7. **The fail-closed answer when names cannot be listed**: Claude gets no
   skill at all (Agent Voice's own included) and Codex no turn. Strict;
   rare (an unreadable folder in the person's own home with an unreadable
   list). Keep?
8. **Codex credits: 17.81 this phase; 1.02 left for M12–M29.** No later
   phase can have a Codex review; every one will be "review owed" unless
   credits are added. M17, M20, M22 and M27 are Tier A, where the plan makes
   both passes mandatory before the next phase starts. **The runner needs a
   decision before M12** (more credits, a different reviewer, or accept
   "review owed").
9. **Carried, still open**: M10's 1–8; M9's 2–7; M8's 2–11; M7's 2–7; M6's
   1, 3, 4; M5's 1, 4–6; M4's 4–13; the Voice library trash icon (M25); M0's
   small test and bench fixes; agy's `carries_session_across`; the runner's
   sandbox test command (`codex sandbox linux -- true` still fails).

## Codex credits used

**17.81**. The balance went from 18.83 at the end of M10 to 1.02, read from
the session logs' `rate_limits.credits.balance`:
- **Spike: 0.** `codex debug prompt-input` makes no model call; the balance
  was 18.83 before pass 1.
- **Pass 1: 11.16** (18.83 → 7.66). `gpt-6.2-astra`, **low** effort,
  sub-agents disabled, the read-only copy, the daemon + `bin` +
  `Settings.qml` diff (1,390 lines), at most 5 findings.
- **Pass 2: 6.64** (7.66 → 1.02). Low effort, pass 1's fix diff (425 lines),
  at most 3 findings.

**1.02 left** for M12–M29.

## Live checklist: what was done, what happened

Nothing was said into the microphone. One typed turn to Theo, spoken aloud
by the daemon as any typed turn is.
- Before each deploy: state `listening`, every agent idle, no open mic, no
  task, unlocked; `shell.json` copied (0600) before the first.
- After each install: the service active; the plugin link pointing at the
  deploy checkout at the new commit; `shell.json` byte-identical to the copy.
- `agentvoice skills lanes --json` and `agentvoice agents catalog main
  --json`: as in "What was proven". Hazel's duplicate cards found here, fixed
  in c912e54, deployed, read again: one each.
- Typed "Reply with only the names of the skills your Skill tool can load,
  comma separated, no other words." to Theo: the list in "What was proven".
- Theo's `claude` process: `--settings` keys `permissions`, `hooks`; no
  `skillOverrides`.
- At the end: `shell.json` byte-identical to the copy. No shell restart.
