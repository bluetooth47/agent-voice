# Phase M14: The Agent Voice skill

Written 2026-11-22, unattended (started by the runner script). Branch
`phase-m14`, cut from `phase-m13` at 7120ef6. Result commit: the notes commit
on top of ed12962, pushed to `fork/phase-m14` only; `dev` fast-forwarded to it
and pushed to `fork`. Model: Claude Sonnet 5.5 (tier C in the plan).

Commits:
- 49e527e: the phase;
- 6a3cd2b: a fix found by the first install (below);
- ed12962: a wording fix found in the preview screenshot;
- then these notes.

**Codex review: bypassed (user decision, 2026-11-22).** Codex was not run, for
review or anything else. In its place I re-read the whole diff before the
first commit; what that and the live checks found is under "Found along the
way". Nothing in this phase has been reviewed by a second model.

Deployed: **yes**, three times through `bin/agentvoice-deploy --install` (its
strict check green each time): 49e527e, then 6a3cd2b, then ed12962. The daemon
was idle each time (state `listening`, no open mic). **The way back to before
M14 is `bin/agentvoice-deploy 051ecc3`** (see "Going back").

Installed: **yes**: "Build 0.2.0 (ed12962), replacing 0.2.0 (6a3cd2b)". The
daemon, the hook and the CLI changed. `install.sh` did not change.

**Shell restart needed** for the two switches (`pages/CommunalPage.qml`,
`pages/AgentDetailsPage.qml`, `ui/ToolSwitches.qml`, `pages/AgentsPage.qml`,
`Settings.qml`). Not run. Until it is, the running shell has M13's QML: no
Agent Voice switch on Communal → Tools, and no "How Agent Voice works" row
on Tools & skills (the row comes from the catalog, so it appears as soon as
the Agent details page is reloaded; the Communal switch needs the restart).
Nothing is broken meanwhile: the skill is on by default and is given.

A copy of `shell.json` was taken before the first deploy
(`~/agentvoice-notes/shell.json.before-M14`, 0600); after the installs and the
live checks it was byte-identical. No live check wrote a setting.

`./bin/agentvoice-check`: green on the final tree (the notes commit), run last.
- **4247 tests** (was 4161; +86), 14 of 14 static checks, "the
  check wrote nothing in the tree: ok".
- Bare-runner variant (`AGENTVOICE_STRICT=1`, a venv with only
  requirements-dev): **not run** this phase. `test_agentvoice_skill.py` uses no
  numpy or other wheel, but I did not run it on a bare venv.
- Box: not run (`install.sh` did not change).

## What was built

**`daemon/agentvoice_skill.py`** writes `skills/agentvoice/SKILL.md` in
`~/.local/share/agentvoice/agentvoice-skill/` (a Claude plugin folder, plus a
`stamp`), modelled on `omarchy_skill.py` and generated from the definitions
the daemon uses:
- what Agent Voice is and how to talk to it (wake phrase, open mic, push to
  talk, mute versus stop, the lock);
- **the command table**, from `speech_text.table()`: each command's label,
  effect, every phrase, the phrases counted inside a sentence, where it may
  appear, the sentence it says, and the mode in force now;
- **the agents' wake phrases**, from the settings (`voice_commands.wake_phrases`),
  each name a JSON string and a phrase that is not plain words left out: this is
  data, not an instruction;
- **every setting with its page**: label, first sentence of the description
  (cut to 90 characters, shorter if the whole would pass 20,000) and default
  from `manifest.json`; the page from the `put("key"` calls in `pages/`, named
  as the sidebar names it (`PAGE_LABELS`, held to `Settings.qml` by a test);
- **the files**, from `paths.py`, only the ones the orders guard does not
  cover (the state file, saved chats, models, voices, the journal command); what
  the agents are told is described, never named by path;
- **what an agent cannot do itself**: a terminal handoff ends the turn it is
  said in, so it gives the person the phrase; it cannot answer a permission
  question; and a section of what is the person's to do (settings, mic, pass,
  new chat);
- **`agentvoice` commands to suggest**, never to run (`SUGGEST`, each a real verb
  of `bin/agentvoice`, tested).

**Explain only** (question 7, the default taken). The text opens with "Explain;
do not act", says "Suggest, do not run", and never offers a command the
guard asks about. `forbidden()` matches every fragment the orders guard matches
on a command (card answers, passes, skill and note moves, folder writes, the
guarded folders by every spelling) plus `permit`, `bar set`, `omarchy bar`,
`shell.json`; `build()` writes **nothing** (and keeps the earlier file) when
the text holds one. A command whose terminal form the guard asks about
(`agentvoice pass …` for "pass" and "take over") is not printed as the
person's way (`teachable`).

**Delivery**, through the Omarchy skill's own machinery:
- **Claude Code**: `agentfs.plugin_dir(…, agentvoice_root)` copies
  `skills/agentvoice/SKILL.md` into each agent's own plugin folder beside
  `omarchy` (one merged folder when it has both or has its own skills; its own
  folder alone when only it is wanted), **whatever the Omarchy switch says**.
- **Other CLIs** (Codex, Gemini, Antigravity, Copilot): one index line, at
  most 160 characters, in `skill_text` after the Omarchy list, naming the file to
  read ("- agentvoice: how Agent Voice works (…); read PATH when asked"), with
  one sentence saying to explain and not run. An empty line when the path is too
  long to fit, never an over-long one.
- **Endpoints**: nothing (`takes_skill_text` is false, the catalog says why).
- **Rebuilt when stale** (`stale()`): a hash of the generator, `speech_text.py`,
  `manifest.json`, the page files, the wake phrases and the commands-in-sentences
  mode, kept per file while size and mtime stay, so the 2 s idle poll reads
  nothing when nothing moved. The daemon builds it in `reconcile_extras`
  (`_refresh_agentvoice_skill`); a refused or failed build is said once and not
  tried again until an input changes. The plugin folder cache is keyed by the
  file's revision, so a rebuilt skill reaches a warm Claude process on its next
  idle poll.
- `agentvoice` is a **reserved skill name** (`agentfs.RESERVED_SKILLS`): a user
  skill by that name is listed with its problem and given to nobody.
- **The orders guard covers the folder** (`permission_hook`: `_sensitive` and
  `_orders_dirs`), as it covers `omarchy-skill`: an agent writing there is asked
  at every level.

**Settings, three parts** (the check holds them):
- `agentvoiceSkill`: manifest schema + default `true`; `runtime.DEFAULTS` and TOML
  alias `agent.agentvoice_skill`; the control on **Communal → Tools** (a
  `ToggleRow`). Unreadable (a value that is not true) reads as **off**, and so
  does any unreadable settings file.
- the per-agent `agentvoiceSkill` in `mainTools` / `voiceAgents[i].tools`:
  inherit / on / off, the fourth built-in switch (`TOOL_GLOBALS`), written only
  through `Settings.setAgentTool` from Agent details → Tools & skills, where the
  catalog adds a "How Agent Voice works" row. Unreadable reads as inherit.
- "agentvoice" in an agent's `skillsOff` switches it off too (one name, one
  switch, as for `omarchy`).

**Also**: the Agent details preview lists "How Agent Voice works" as a built-in
piece; `bench/preamble_size.py` counts it; docs in CODEBASE, README ("Agent
Voice skill") and FINDINGS §48.

## What was proven, and how

- **Tests** (`tests/test_agentvoice_skill.py`, 85, plus the shared tables):
  every phrase, in-sentence phrase, effect, label and fired sentence of every
  command in the text, and per command **exactly the table's phrases and no
  other command's**; a changed table is followed; wake phrases and an escaped
  name, an odd phrase left out; the mode in the text; every setting with its
  page and the page labels equal to the sidebar; what an agent cannot do; "explain,
  do not act"; files from `paths` with no guarded path anywhere in the text; each
  suggested command a real verb and none the guard's; **the text and the live
  build hold nothing forbidden**; `forbidden()` on eight guard-matched commands
  and four words; the guard's own CLI form of "pass" not printed; a refused
  build writes nothing and keeps the earlier file; **size within 20,000** (the
  real one, eight agents with 40-character names, 120 settings with long
  descriptions shortened, 400 refused); the index line within 160 (and empty when
  it cannot fit); `stale()` moving on a wake phrase, the mode, another agent, a
  changed `speech_text.py`, a changed manifest, a plugin folder appearing, and not
  otherwise; the digest kept while a file is unchanged; the reserved name; delivery
  (merged folder, its own folder alone, as before with it off, a missing file is
  no skill); each switch (global, own, own beats global, unreadable per-agent =
  inherit, unreadable global = off, unreadable settings = off, by name in
  `skillsOff`); **only the agents with it on receive it** through the real
  `apply_extras` for Claude and Codex; independent of the Omarchy switch; an
  endpoint given nothing; a switch turned off reaches a warm process and nothing
  moving lets nothing go; a rebuilt file is a new plugin folder; the daemon
  building it once, again on a change, once when refused, and not for an agent
  that does not want it; the guard asking for a write by tool and by Bash
  command; the setting's three parts; the CLI `show` and `build`; **the installed
  layout** (see below). Nine existing tests were updated for the fourth switch
  and the reserved-name message.
- **Mutations: 28 run, 28 red**, in scratch copies under `/tmp`, never in the
  clone: `forbidden()` empty; `teachable` always true; the extra words emptied;
  the guard's words not consulted; `agentvoice` not reserved; the folder missing
  from the guard's two lists (two); the stamp ignoring wake phrases, the mode,
  `speech_text.py` or the manifest (four); the size not checked; the settings
  notes never shortened; the index line unbounded; a wake phrase unfiltered; a
  name unescaped; the plugin folder ignoring the Agent Voice root; "nothing chosen"
  returning the Omarchy folder only; unreadable settings still giving it; the
  by-name switch ignored; the per-agent switch dropped from `TOOL_GLOBALS`;
  `apply_extras` giving it to everyone; the plugin cache ignoring the revision; a
  refused build retried every poll; the daemon never rebuilding; building when no
  agent wants it; a pass CLI printed; the source root ignoring the plugin link.
  Two were first not caught by my own tests (the extra words, and the notes never
  being shortened); the tests were tightened and both went red.
- **Preview** (`preview.sh`, synthetic mouse events, real CLI, scratch data
  folder, the real pointer never moved): the M10 `tools` target **29 of 29
  PASS** with the fourth switch in place; the `skills` target's scrolling
  screenshots (900×700, dark) show the "How Agent Voice works" row with its
  three choices on Sora's Tools & skills tab. Not shot: the Communal switch, a
  light theme, a narrow width (a `ToggleRow` copied from the Omarchy one).
- **Live, on the installed daemon** (typed, synthetic): the skill built by the
  daemon at its first poll; the catalog shows the row (`on`, `can`); the
  Agent details preview lists the built-in piece; **typed to Theo (Claude Code):
  "How do I keep the mic open so I do not have to say the wake phrase each time?
  Answer from your Agent Voice skill, in two sentences."** His reply: say "keep
  listening", which opens the mic until "stop listening" or "goodbye" or ten
  minutes' silence, and a Conversation-page setting called "Open the mic after
  every wake". That label is in the manifest and the skill, nowhere in his prompt,
  so it came from the skill (not proven by a transcript of his tool calls). His
  plugin folder and Sora's were rebuilt with it (`agent-plugins/`); no traceback
  in the journal.

## Shared files touched, and where

- `daemon/wake_listen.py` (big shared, +~45): the import, `_refresh_agentvoice_skill`,
  `plugin_dir_for`'s extra root and revision, and four lines in `apply_extras`.
  Nothing in the turn loop.
- `daemon/agentfs.py` (big shared, +~25): `RESERVED_SKILLS`, `plugin_dir`'s
  fourth argument, `TOOL_ROWS`, the catalog row, `_asks`, one preview piece.
- `daemon/permission_hook.py` (security-critical, +2 lines): the new folder in
  `_sensitive` and `_orders_dirs`.
- `daemon/runtime.py`: the default, the TOML alias, `TOOL_GLOBALS`, the two
  `tools_for` rules. New `daemon/agentvoice_skill.py`.
- `pages/AgentDetailsPage.qml` (big shared, +8): a note for the preview piece
  and the key in the preview's watch list. `pages/CommunalPage.qml` (+19, the
  switch), `pages/AgentsPage.qml`, `ui/ToolSwitches.qml`, `Settings.qml`
  (`setAgentTool`'s list): one entry each. `manifest.json`.
- `bench/preamble_size.py`, `bench/FINDINGS.md` (§48), CODEBASE, README.
- Tests: new `test_agentvoice_skill.py`; `test_tools_skills`, `test_skillscan`,
  `test_agent_pages`, `test_crew`, `test_preamble` for the fourth switch.

## Measured

FINDINGS §48. Codex, Gemini, Antigravity and Copilot preambles grow by **299
characters** (6,837 to 7,138, about 75 tokens); a Claude preamble by nothing
(the skill loads through the CLI; its front matter, 377 characters, is what
Claude lists in its own context, the body only when asked). The real SKILL.md is
**19,501 characters** against a limit of 20,000: close. "S on `sora`" was not
rerun.

## Different from the plan, and why

- **The Settings section reads the manifest and pages from the plugin folder
  when the daemon runs installed** (see below): the plan says "from the manifest
  and the page map" and does not say where an installed daemon finds them.
- **A Codex "index" is not the skills index** (`agentfs.skills_index`, which
  lists a skill's own description and path) but one line in `skill_text`, after
  the Omarchy list, because that index is built from folder skills and this is a
  built-in one. The line says the same thing (name, what it is for, the path).
- **The stamp includes the commands-in-sentences mode** as well as the wake
  phrases, because the text states the mode.
- **Settings notes are one sentence each, cut to 90 characters**, to stay under
  20,000 (the whole manifest's descriptions are about 11,800 characters alone).
- **No CLI verb** (`agentvoice skill …`): `python daemon/agentvoice_skill.py
  show|build` exists; the Agent details preview names the piece. Not asked for.
- **Codex review bypassed** by the user's decision.

## Found along the way

- **The first install built a half-empty skill.** The installed daemon runs from
  `~/.local/share/agentvoice/app/`, which has `daemon/`, `bin/` and `desktop/` and
  neither `manifest.json` nor `pages/`; `paths.ROOT` is `app/`, so the Settings
  section came out empty (10,252 characters instead of 19,355) with no error. No
  test could see it: the suite runs from the checkout. Found by comparing the
  installed file's size with `show`'s. Fixed in 6a3cd2b: `source_root()` falls
  back to `~/.config/omarchy/plugins/duaneoca.agentvoice` (read only: a read
  reloads nothing), the text says so when neither has them, and the stamp moves
  when one appears; three tests lay out an `app/` with an empty ROOT, and a
  mutation (the link ignored) turns one red. Worth remembering for every
  phase that reads a repo file at runtime: `paths.ROOT` is not the repo once
  installed.
- **The new row said "Asks before running a command"** (screenshot): it fell
  through `_asks` to the Omarchy wording. The skill runs nothing. Fixed in
  ed12962 with a test.
- **My own re-read of the diff** found nothing further to change; the live check
  and the screenshot found the two above.
- **A `monkeypatch` of `DATA_DIR` in tests leaks state across tests unless each
  file resets agent folders**: my first run failed in ways that depended on test
  order until the file got the same per-test data fixture `test_tools_skills`
  has.

## Not verified

- **Hazel (Codex) asked "how do I keep the mic open?"**: not run. Codex is not
  to be run in this phase (the user's decision), and a typed Codex turn needs it.
  What Hazel is given is only the rendered text: her preamble grew by one line
  (`bench/preamble_size.py`), and the unit test runs `apply_extras` for a Codex
  adapter. Whether she reads the file when asked is untested.
- **The pages in the real shell**: the Communal switch and the new row need
  `omarchy-restart-shell` (next stop point, after M15). Seen only in `preview.sh`
  (the row, in dark at 900×700). The Communal switch, a light theme, a narrow
  width and keyboard use were not shot or driven.
- **That Theo read the skill, rather than guessing**: his answer carries a label
  found only in the skill, which is evidence, not a transcript of his tool calls.
  One question, once.
- **The skill's accuracy to a person's ear**: the phrases are shown as the
  daemon matches them (lower case, no apostrophes: "thats all", "im done"), so
  an agent saying them aloud says what is matched, not how Whisper writes them.
  Whether that reads oddly was not judged.
- **A warm Claude process picking up a rebuilt skill** after a wake-phrase change
  on the real daemon: tested at the daemon with a fake adapter, not by changing a
  real wake phrase.
- **The bare-runner variant** and **the installer box** (not run).
- **S on `sora`** not rerun (no number claimed).
- **The Codex review** (bypassed, not owed).

## Going back

`bin/agentvoice-deploy 051ecc3` from the clone, `./install.sh --yes` once the
daemon is idle, then `omarchy-restart-shell`. An M13 daemon does not read
`agentvoiceSkill` and does not generate or deliver the skill; the folder
`~/.local/share/agentvoice/agentvoice-skill/` stays on disk, unread and
regenerable (an uninstall does not remove it, like `agent-plugins/`: `rm -rf` it
by hand if wanted). The setting and the per-agent entries stay in `shell.json`,
unread. Plugin dirs rebuild without it. An M13 guard does not ask about the
folder; nothing there is read by an M13 daemon. A user skill named `agentvoice`
that M14 refused is accepted again.

## Open issues, for the next phase

1. **Codex review bypassed** for M14 (user decision, 2026-11-22). M12 stays
   "review owed".
2. **Explain-only (question 7)**: taken as the default. If agents should also
   run read-only commands such as `agentvoice status`, the skill and the guard
   would change together.
3. **The skill is 19,501 of 20,000 characters.** A longer manifest or more
   agents is absorbed by shortening the settings notes (then refused when even
   that is not enough, keeping the old file). Should the settings list move to a
   second file in the skill folder (a skill may hold more than SKILL.md)?
4. **Phrases are shown in the daemon's matching form** ("thats all"). Show
   Whisper-style spellings with punctuation instead?
5. **The Settings section needs the plugin folder when installed.** If the plugin
   is removed while the daemon runs, the text says the list is not available. An
   alternative is `install.sh` copying `manifest.json` and `pages/` into `app/`
   (changes the installer, so it would need the box).
6. **A user's own skill named `agentvoice` is refused** (reserved), and one in
   `~/.claude/skills` by that name is offered beside Agent Voice's as
   `agentvoice` and `agentvoice:agentvoice`. Neither was seen on this machine.
7. **Hazel's one line** is a path to read. A Codex agent below Trusted has no
   hook, so a read is not asked about; for a Claude agent the file is read through
   the Skill tool and never by path.
8. **Carried, still open**: M13's 2–9; M12's 2–7; M11's 1–7; M10's 1–8; M9's 2–7;
   M8's 2–11; M7's 2–7; M6's 1, 3, 4; M5's 1, 4–6; M4's 4–13; the Voice library
   trash icon (M25); M0's small test and bench fixes; agy's
   `carries_session_across`; the runner's sandbox test command.

## Live checklist: what was done, what happened

One typed turn to Theo, spoken aloud by the daemon as any typed turn is. Nothing
was said into the microphone.
- Before each deploy: state `listening`, no open mic; `shell.json` copied (0600)
  before the first.
- `bin/agentvoice-deploy --install 49e527e`: "Build 0.2.0 (49e527e), replacing
  0.2.0 (051ecc3)"; the skill built within seconds; 10,252 characters (the bug
  above). `preamble_size.py`: the line is 299 characters.
- `bin/agentvoice-deploy --install 6a3cd2b`: the skill 19,501 characters, the
  Settings section present; the stamp written.
- The catalog row (`on`, `can`), the preview piece, the typed turn to Theo (above).
- `bin/agentvoice-deploy --install ed12962`: the row's `asks` empty.
- At the end: the service active; `shell.json` byte-identical to the copy. No
  shell restart.
