# Phase 13: Tools and skills

Written 2026-11-19. Branch `phase-13`, cut from `phase-12` at 0a8944e,
pushed to `fork/phase-13` only (the hashes are in `git log`). Installed:
yes. Tested on: i7-1185G7, Quickshell under Omarchy's shell, `claude`
2.1.328, `codex-cli` 0.171.0.

`./bin/agentvoice-check`: green, 2346 tests (was 2245), qmllint
clean. Box: not run (`install.sh` did not change). Preview: the new `tools`
target 24/24, `details` 40/40 (one check added), `folders` 11/11, all against a scratch data
folder and a scratch shell.json.

**The first commit (6f03e29) went in with the check stale**: I edited
`bench/start_bench.py` after the last check run and committed without
running it again, and that edit broke the bench's baseline (below). The
same mistake as Phase 12's first commit, made a different way: the check
was green, but on an older tree. Codex's review found it; the fix commit
has the check green on the tree it commits.

## What was built

- **Per-agent tool switches** (section 3.4): each Agents card has a
  **Tools & collaboration** group, shut until clicked, with Desktop tools,
  Browser and Omarchy commands, each **Same as every agent / On / Off**.
  Stored as `mainTools` (new top-level key, `{}` by default) and
  `voiceAgents[i].tools`; "same as every agent" removes the key, so an entry
  nobody changed is written as it was. `runtime.Config.tools_for(id)`
  resolves them: the agent's own on or off, else the global setting; a
  missing or unreadable value is inherit. The global switches stay at the
  foot of the Agents page, now headed "For every agent, unless its card's
  Tools & collaboration says otherwise". The group's header shows what the
  agent has while it is shut ("Tools & collaboration · desktop, browser,
  Omarchy commands").
- **A tool the agent's program cannot use says why instead of offering a
  switch** ("Only Claude Code can use Claude in Chrome."; an endpoint "runs
  nothing on this machine"; a program Agent Voice cannot run is named).
- **The daemon resolves them per agent** (`apply_extras(agent, persona)`),
  between turns, and lets an idle process go on a change; the conversation
  is kept (`tools` is one of the spec keys `_rebuild_persona` keeps). A turn
  that replaces a running one is caught up too (`catch_up_one`). A change is
  logged as one structural line: `tools for “Sora”: desktop · omarchy ·
  plugins sora-38e0…`.
- **Skills** (`daemon/agentfs.py`): a folder under `skills/` holding
  `SKILL.md`, whose front matter has a `name` matching the folder and a
  `description` of at most 300 characters; at most 20,000 characters, 64
  files and 2 MB in the folder, no file over 256 KB, no links anywhere in
  it, and no `hooks` in its front matter (Claude Code would run them as
  commands outside the agent's permission level). A skill that fails
  is listed with its problem and given to no agent. `omarchy` is the
  built-in skill's name and is refused for a folder skill. An agent's own
  skill hides a communal one of the same name (even a broken one: the
  person meant this agent to have its own), and the pages say so.
- **Delivery**:
  - Claude: a plugin folder built for the agent in
    `~/.local/share/agentvoice/agent-plugins/<id>-<content hash>/` (the
    Omarchy skill when its switch is on, its own skills, the communal
    ones), passed with `--plugin-dir`. Named by content, so a change makes
    a new folder and never rewrites one a running process has open; the
    daemon prunes them all when it starts. With no folder skills the agent
    gets the Omarchy skill's own folder exactly as before, so its argv is
    unchanged. Built again only when the folders' stamp moves (which now
    covers every file in `skills/`, scripts included) or the Omarchy skill
    moves; a failed build keeps the Omarchy skill and is tried again after
    30s.
  - Codex, Gemini, Antigravity, Copilot: an index in the preamble, after the
    standing instructions and before the Omarchy commands (`Skills:
    instructions for particular tasks…` then `- name: description
    (path)`), each line at most 160 characters and all of it at most 1500,
    with "and N more" when some do not fit. Empty when there are none, so
    the preamble is unchanged.
  - Endpoint: none, and the pages say so.
- **The permission hook**: writing into `agent-plugins/` or `omarchy-skill/`
  asks at every level below Trusted (they become what agents are told);
  reading another agent's plugin copy asks, as reading its folder does
  (A9-5); loading one of the agent's **own** skills with the Skill tool
  (`agentvoice:<name>`, or the Omarchy skill) is allowed as a read, and any
  other skill or malformed input is asked about as before.
- **`agentvoice agents catalog ID [--json]`**: every tool with whether it
  is switched on (its own switch or the setting for every agent), whether
  the program can use it and why not, and whether it asks first at the
  agent's level; then every skill with its problem, shadowing and how it is
  given. `agents skills TARGET [--json]` and `agents skills-folder TARGET`
  (makes `skills/`, 0700, and prints it) too. `roster()` now reports each
  agent's program, usable tools and skills, from the same resolution, for
  `list_agents` in Phase 16. `agents preview` shows the skills as the agent
  gets them (names for Claude, the index for the others).
- **Agent details → Tools & skills** reads `agents catalog`: each tool on
  or off and whose switch, "Cannot use" with the reason, and what it asks;
  then its own skills and the communal ones, each given, hidden by its own,
  or not given with the problem in the urgent colour; how its program gets
  skills and what a skill's scripts do at its level; **Open <name>'s skills
  folder**; **Change on <name>'s Agents card →**, which opens that card's
  group (`goTo("agents", id, "tools")`).
- **Communal** now has tabs: **Rules & defaults** (as before) and
  **Skills** (the shared skills with their problems, who does not get one
  because it has its own, the format in one paragraph, Open the skills
  folder). `{"page":"communal","tab":"skills"}` opens it.
- **A skill made or changed by hand reads as changed outside Settings**
  (every skill is made by hand), with **Keep** (`agents ack … --base`) on
  both pages; the Agents card says "a skill added or changed outside
  Settings (Tools & skills)" rather than calling it a changed file.
- **The Rule of Two warning**: an agent whose browser is on, at Trust
  everything, and not denied notes writes (the key arrives in Phase 14)
  shows under its card's header: "It reads web pages, acts without asking,
  and can change what the other agents are told (the communal rules and
  skills)…". Theo shows it today. Notes join the sentence in Phase 14.
- `bench/start_bench.py` hands each agent its own switches and plugin
  folder, as the daemon does, and has a `skills` variant (three synthetic
  communal skills in a scratch data folder).

## Shared files touched, and where

- `daemon/runtime.py`: `TOOL_GLOBALS`, `TOOL_CHOICES`, `tool_choices()`,
  `DEFAULTS["mainTools"]` and its TOML alias, `tools` in each cleaned agent
  entry, `Config.tools_for()`. `manifest.json`: `mainTools` default.
- `daemon/wake_listen.py`: `tools_for`, `plugin_dir_for`, `apply_extras(agent,
  p)` and its log line, `reconcile_extras` (the Omarchy rebuild check asks
  every agent's switch), `catch_up_one` (switches too), `_rebuild_persona`
  (`tools` kept), the prune at start.
- `daemon/adapters/base.py`: `SKILLS_HEAD`, the index in `preamble()`.
- `daemon/permission_hook.py`: `OWN_SKILL`, the Skill rule, the plugin
  folders in `_sensitive` and `_foreign`.
- `daemon/agentfs.py`: the skills section, `catalog`, `program_of`,
  `level_of`, `roster`, `preview`, `snapshot` (skills whole or not at all),
  `stamp` (all of `skills/`), the CLI.
- `Settings.qml` (`focusTools`, `communalTab`, `goTo`'s tab for those two
  pages, details tab validated), `pages/AgentsPage.qml`,
  `pages/AgentDetailsPage.qml` (the picker's re-bind is now a `Binding`
  element: see below), `pages/CommunalPage.qml`, `ui/AgentCard.qml`
  (`warning`), new `ui/ToolSwitches.qml`, `ui/qmldir`.
- Tests: new `tests/test_tools_skills.py`; `test_crew.py` (the cleaned entry
  has `tools`), `test_agent_pages.py` (the picker binding). Preview: new
  `tools` target, `details` (the picker after a removal).

## Measured (numbers, against the baseline)

FINDINGS §36. Prompts unchanged on this machine, which has no skills: main
1109, sora 1210, jarvis-ajc 7088 characters (the daemon's log after
install, and `preamble_size.py`). **A13-4, the gate with three skills**:
on Sora, quiet runs, cold median +0.06s over 50 pooled runs (+0.18s in one
20-run round, +0.03s in the 30-run round after it), warm +0.07s, p95 lower
or level: inside the gate. Main +0.22s cold, +0.15s warm, inside an Opus
median's ±0.48s noise. Codex not run (quota; its prompt is unchanged here).

## Different from the plan, and why

- **Codex is given the index, not its own skills** (A13-3). Codex 0.171
  finds skills only in `$CODEX_HOME/skills`, `~/.agents/skills`, the
  project's `.agents/skills` and its plugin cache (read from the binary's
  discovery strings, with `skills.config`, which only switches discovered
  skills on and off). Every one of those is shared with the person's own
  Codex sessions or is the project, which the agent folders must never
  write into. So there is no per-process way to hand Codex one agent's
  skills, and no real turn was spent proving one: the index is used and
  the matrix row stays "not run".
- **No separate "communal skills" tool switch.** The plan's catalog lists
  communal and own skills as rows; they are listed (with their problems),
  but they have no switch: a skill is given by being in the folder. A
  per-skill switch would be a second place to say the same thing.
- **"Tools & collaboration" holds only the three tool switches now**; notes
  write arrives with Phase 14 and collaboration with Phase 16. The group's
  name is the plan's, so later phases add rows to it.
- **The Rule of Two reads `notesWrite` already** (absent, so allowed), and
  its wording says why it matters today: a Trusted agent can already
  rewrite the communal rules with a shell command.
- **A program Agent Voice cannot run** (an Omarchy default it has no
  adapter for) is described as answering nothing, rather than as taking an
  index.

## Found along the way (bugs, surprises)

- **qmllint stopped resolving the agent picker's type** once the details
  page grew: `agentPicker.value = Qt.binding(...)` (Phase 12's fix) failed
  the check with `Member "value" not found on type`, though nothing about
  the picker changed and each addition alone linted clean. The re-bind is
  now a `Binding { target: agentPicker; property: "value"; value:
  page.target }`, which does the same job without naming the member; a new
  `details` preview check (the picker names the main agent after a
  removal) goes red when the Binding is taken out.
- **Changing an agent's tool switch would have dropped its conversation**:
  `_rebuild_persona` compares the cleaned entry, and `tools` was not among
  the keys it keeps. Found while wiring it, before any test.
- **At Ask, using one of its own skills asked on screen** (found in the
  live check): Claude Code loads a skill with the Skill tool, which the
  hook had no rule for. The question timed out unanswered (I did not answer
  a permission prompt on the person's behalf); the hook now treats loading
  its own skill as a read.
- **Hand-made skills read as "changed outside Settings" for ever**: Phase
  9's notice applies to every file in the folder, and a skill has no other
  way to be made. Keep now clears it.
- **Mutations**: 7 new guards in the first commit (the own switch, shadowing,
  a malformed skill given, the daemon reading the global browser switch,
  the index for every backend, a link inside a skill, the plugin folders
  not sensitive), 4 in the review fixes (catch-up, the failure retry, the
  plugin copies as foreign, the long-path line), the Skill rule, 4 in the
  second pass (hooks refused, the catch-up on every dispatch, a file over
  256 KB, a broken own folder still hiding the communal skill), and the
  picker Binding in preview: each removed in turn, each turned a test red.

### Codex's review, and what was done

Codex reviewed in two passes. The first, on 6f03e29, **hit its usage
limit before writing its report**; its findings come from the checks it had
run and printed (its log shows each probe and result), each verified here
and fixed in 96a998a. The second, after the limit reset at 00:20, reviewed
everything to 95ff7c8: 2 high, 7 medium, 2 low, fixed in e260dda but one.
Every finding was checked against the code before it was acted on.

Fixed, each with a test:

- **The bench's baseline dropped the folder pieces** (high): adding the
  `skills` variant split an if/elif chain, so `folders` assigned the parts
  and then set them to None. The latency run in progress was stopped and
  run again after the fix; nothing measured with the broken bench is
  reported.
- **A turn that replaced a running one kept the old tool switches** (high
  for A13-1): `dispatch()` stops the busy agent and catches up its prompt,
  but not its switches; `catch_up_one` now applies them.
- **A failed plugin build was cached** until the folders changed; it is
  tried again after 30s.
- **The skills index could exceed its budgets** (176-character line, 1530
  total): a line whose path leaves no room is counted in "and N more", and
  room is kept for that line.
- **`description: null`** read as the word; YAML's null (`null`, `~`) is
  now no description.
- **A main agent on a program Agent Voice cannot run** was described as
  taking a skills index; it is given nothing and the pages say why.
- **Another agent's skills could be read through its plugin copy without
  asking** (the copy sat outside `agents/`): plugin folders are named
  `<id>-<hash>` and the hook treats another agent's as it treats that
  agent's folder; "sora" does not own "sora-x-…".

Second pass, fixed, each with a test (the two navigation fixes also in the
`tools` preview):

- **A skill could declare its own hooks** (high): Claude Code runs a
  skill's front-matter `hooks` as commands while the skill is in use,
  outside the agent's level and this app's hook, and loading an own skill
  had just become silent at Ask. Such a skill is now refused, listed with
  why. (`allowed-tools` is left alone: below Trusted the hook answers
  before Claude Code's own allow rules.)
- **A spoken replacement could still keep the old switches** (medium): a
  turn stopped by a wake word can end during the next capture, so
  `dispatch()` saw the agent idle and skipped the catch-up, and no poll
  runs during a capture. Every turn is now caught up before it starts.
- **A plugin folder could be published incomplete** (medium): a file over
  256 KB passed the check and was dropped from the copy, and a failed
  rename returned the folder anyway. A skill with such a file is refused; a
  failed copy or rename raises (and is retried); the cache key holds the
  Omarchy skill's file revision, which Omarchy updates in place.
- **Codex's index and the pages disagreed** (medium) about an own skill
  folder that cannot be given: it hid the communal skill for Claude and on
  the pages, not in the index. The snapshot keeps such a folder (as no
  text), so it hides it everywhere. Communal named a removed agent's
  leftover folder; it names only agents that exist.
- **Agent details could show a switch's old value** (medium): the catalog
  is read from shell.json, which the store writes after the page changes.
  It is read again when a save lands, and an older reading is labelled
  when a new one fails.
- **The Rule of Two disappeared on a notes deny** (medium), though a Trusted
  Claude agent can still rewrite the communal rules and skills: it no
  longer reads notes write at all (a change from the plan's wording).
- **Keep could save an edit nobody saw** (medium): `ack` compared the stamp
  and then read the file again. One read now does both.
- **The bench's `skills` variant replaced the agent's own skills** (medium)
  rather than adding to them (no effect on this machine, which has none);
  it now copies them into its scratch folder first.
- A card or tool group shut by a click could not be reopened by a deep
  link (the click assigned `expanded`, cutting its binding); both now ask
  the page instead. A details link with a tab and no agent applies the tab.
  `description: null # x` is no description. Skill group titles are plain
  text.

Not changed:

- **The hook can fail open before Python answers** (high, pre-existing):
  if the hook script is missing or Claude Code's hook timeout expires,
  Claude Code falls back to its own permission flow. Not new in this phase
  and not specific to it; changing how the hook is launched (an
  `onFailure: "block"` setting, where the installed Claude Code supports
  it) needs its own check against a real turn. Under Open issues.
- An invalid supporting file (a link added beside a SKILL.md) changes what
  is delivered without moving what the pages watch; the daemon notices
  (its stamp covers every file in `skills/`), and the page shows it on its
  next read. Under Open issues.
- A TOML `[agent] main_tools` table is replaced whole by shell.json's
  `mainTools` (Codex's probe): that is how every map setting merges
  (`permissions`, `agentModels`), and shell.json always has the key.

## Not verified (what was skipped, and why)

- **Codex's S run** (A13-4 for jarvis-ajc): its quota was spent; its prompt
  is unchanged on this machine.
- **The keyboard walk of the new group and tabs in the real shell**: the
  preview never takes keyboard focus, and `ydotoold` is not running here, so
  nothing could type into the real shell. The controls are Omarchy's
  Buttons and ButtonGroups (`focusable`), driven by synthetic clicks.
- **A real Codex turn using the index**: the index is tested as text; no
  Codex turn read a SKILL.md through it (quota).
- **A skill's scripts**: copied with their executable bit (tested); no live
  turn ran one.
- A spoken (voice) turn: the live checks used typed turns, which take the
  same path from dispatch on.

## Going back (what an older build sees after this phase)

- `mainTools` and `voiceAgents[i].tools` are ignored by an older build;
  every agent follows the global switches again.
- Skill folders are ignored by an older build (Phase 12 lists them on the
  Tools tab as "not given to agents yet"). `agent-plugins/` is left on disk
  until a Phase 13 daemon starts again and prunes it.
- An older hook asks before the Skill tool loads a skill, as before.

## Open issues, for the next phase

- **The permission hook fails open if its script is missing or times out**
  (pre-existing, Codex's second pass): consider Claude Code's
  `onFailure: "block"`, checked against a real turn, before Phase 14 puts
  the notes tools behind the same hook.
- The pages watch each SKILL.md's stamp, not the other files in a skill;
  a change to those shows on the page's next read.

- Phase 14 adds `notesWrite` / `mainNotesWrite` to the card's group (the
  Rule of Two already reads them) and the Notes tabs.
- If the person has a Claude plugin of their own named `agentvoice`, its
  skills would be loaded without asking at Ask (the hook matches the
  name). Unlikely; noted.
- Whether a skill should be creatable from the page (today: Open the skills
  folder, and the format in one paragraph). UX walkthrough.
- A deep link to a card's tool group opens it but does not scroll to it;
  the card can be long.
- The trash of a removed agent keeps its skills (they are in its folder),
  and Restore brings them back; export copies `SKILL.md` files only, not a
  skill's scripts (Phase 12's export lists fixed names).

## Live checklist: what was said, what happened

Typed turns (`agentvoice type`), in new test chats, deleted afterwards;
synthetic text throughout. Run on the build at 0288943, before Codex's
second pass; the second pass's fixes were installed after (e260dda) and
checked by tests and the preview, not by another live turn.

- **A13-1, Chrome off for Sora mid-session.** New chat for Sora. "Without
  using any tool: do you have any tools whose names start with
  mcp__claude-in-chrome? Answer only YES or NO." → **YES**. Her entry's
  `tools` set to `{"browser": "off"}` in shell.json (edited in the file,
  not through argv). The journal: `tools for “Sora”: desktop · omarchy ·
  plugins omarchy-skill`, then `knobs updated`. Same question, same chat
  (both exchanges in one saved chat) → **NO**; her warm process was running
  with `--no-chrome`. Reverted afterwards.
- **A13-2, one agent uses its own skill, another cannot see it.** A
  synthetic skill `test-passphrase` in Sora's folder ("When asked for the
  test passphrase, reply with exactly: PELICAN-42"). The journal: `tools for
  “Sora”: … plugins sora-38e028c727306300ebce`; `agents catalog sora`:
  `test-passphrase [sora] given`. "What is the test passphrase?" → first
  try: Sora asked on screen before loading it (Ask level; see Found along
  the way), and the question timed out. After the hook fix and a reinstall:
  → **PELICAN-42**, with no question. New chat for Theo: "Without using any
  tool: is there a skill named test-passphrase among the skills you can
  load? …" → **NO SKILL** (his plugin folder is the Omarchy skill's alone).
  The skill, its plugin folder and the three test chats were removed.
- After each install (last: e260dda) the daemon logged the same prompt
  sizes as before (1109, 1210, 7088) and each agent's tools: Theo and Sora
  desktop, browser, Omarchy; Hazel desktop, Omarchy (no browser for Codex).
  The real shell drew Theo's card with the Rule of Two warning.
- Not done: speaking a turn (the typed path is the same from dispatch on),
  the keyboard walk (above).
