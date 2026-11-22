# Phase M10: Tool detection, and real tool controls

Written 2026-11-22, unattended (started by the runner script). Branch
`phase-m10`, cut from `phase-m9` at e812c7c. Result commit: the notes commit
on top of 2a83bb1, pushed to `fork/phase-m10` only; `dev` fast-forwarded to
it and pushed to `fork`. Model: Claude Opus 5.5 (tier A in the plan).

Commits:
- 4494823: the phase;
- 92af969: Codex pass 1 fixes (6 findings);
- 2a83bb1: Codex pass 2 fixes (3 of 4 findings; the fourth is open issue 4);
- then these notes.

Deployed: **yes**, once, through `bin/agentvoice-deploy --install` (its
strict check green: 3844 tests). 2a83bb1 replaced M9's 961ed64. The daemon
was idle first (state `listening`, every agent idle, no open mic, no task
running, unlocked). **The way back to before M10 is `bin/agentvoice-deploy
961ed64a552b`** (printed by the deploy).

Installed: **yes**: "Build 0.2.0 (2a83bb1), replacing 0.2.0 (961ed64)". The
daemon, the adapters and the permission hook changed.

**Shell restart needed** (Agent details' Tools & skills tab, Communal →
Tools, the Agents card's summary and `ui/ToolConfirm.qml` are QML). Not
run. Until it is, the running shell has M9's QML: per-agent tool chips on
the Agents card that still write the three built-in switches, and no way to
switch a found tool on from the UI (see open issue 1).

A copy of `shell.json` was taken before the deploy
(`~/agentvoice-notes/shell.json.before-M10`, mode 0600); afterwards, and at
the end of the live checks, `shell.json` was byte-identical to it. No live
check wrote any setting (one was refused: see Not verified).

`./bin/agentvoice-check`: green on 2a83bb1.
- **3844 tests** (was 3715; +129), 14 of 14 static checks, "the check wrote
  nothing in the tree: ok".
- The bare-runner variant (`AGENTVOICE_STRICT=1`, a venv with only
  requirements-dev): **green** on 2a83bb1 (3828 passed, 9 skipped: the
  existing numpy-only skips).
- Box: not run (`install.sh` did not change).

## The spike (plan: "spike first, one real turn each")

Recorded into FINDINGS §44 and `tests/fixtures/tools/` (replayed by
`test_tool_controls.py`). Stub MCP servers and a stub CLI left marker files,
so "loaded" and "ran" are files, not a model's say-so.

- **Claude, without `--strict-mcp-config`** (Agent Voice's argv until now):
  the init event listed the user's `desktop-control` (`~/.claude.json`), a
  project `.mcp.json` server **never approved**, and the dynamic one; all
  three started. A `--plugin-dir` plugin's server loads too.
- **With `--strict-mcp-config --mcp-config <0600 file>`**: only the file's
  server; the others never started, a plugin's included. `--mcp-config`
  takes a path, so the config moves out of argv.
- **claude.ai connectors**: none appeared in a `-p` turn on this machine,
  either way.
- **Skills** (for M11): `--settings '{"skillOverrides":{"x":"off"}}'` leaves
  exactly that skill out, merged with the user's own overrides.
- **`permissions.deny`** holds even when the hook answers allow (every
  level's mechanism), for `gh`, a path to it and a `&&` chain -- but
  **`sh -c 'gh'` ran**. So a CLI switch is **told, not enforced**, on every
  backend, Claude included. `Bash(name)` + `Bash(name *)` alone deny the
  plain forms; no `:*` rule (it could catch a longer name).
- **Codex**: `-c mcp_servers.<name>.enabled=false` stops a server (stub
  started without it, not with it); naming a server not in config.toml
  stops Codex starting ("invalid transport"); a quoted key is refused too;
  `-c mcp_servers={}` merges. Below Trusted an MCP call **fails** ("requires
  approval, but approval policy is never"); at Trusted it runs unasked.

What the page calls enforced follows these: an MCP server is enforced
(Claude: strict list; Codex: disabled per server); a CLI is "told, not
enforced" everywhere.

## What was built

**Detector** (new `daemon/tooldetect.py`):
- MCP servers from `~/.claude.json` (`mcpServers`, and `projects[<dir>]` for
  each agent's project: the local scope), each agent's project `.mcp.json`,
  enabled Claude Code plugins (`installed_plugins.json` + `enabledPlugins`,
  `${CLAUDE_PLUGIN_ROOT}` filled in), and `~/.codex/config.toml`
  (`CLAUDE_CONFIG_DIR` / `CODEX_HOME` honoured);
- CLIs from a curated list of 23 that reach an account or a service (`gh`,
  `aws`, `docker`, `stripe`, `op`, ...), plus any added by name (a `cli:`
  key in any tools map), with `shutil.which`; a CLI's place is its PATH
  entry, not its resolved target, so a version manager's upgrade does not
  turn it "changed";
- **reads only** (a test makes every process-starting call fail during a
  scan); bounded (16 MB for `.claude.json`, 512 KB others, 200 servers, 64
  plugins); regular files only; **a project's or a plugin's files are opened
  beneath their root with no link followed at any level** (pass 1);
- **nothing secret in what it returns**: env and header values never;
  values after secret-named, header and env flags, arguments naming a
  secret, key-shaped words and a URL's query and password masked
  (`shown_command`); the scan cache in `$RUNDIR/tools/scan.json` (0600) holds
  the same;
- a **fingerprint** per tool: an HMAC (key `DATA_DIR/tool-key`, 0600) over
  every definition of it, so the approval stored in the 0644 shell.json says
  nothing about what it covers; a changed command, argument, environment
  value, or a project's copy appearing moves it;
- `rows()` (one agent's view), `delivery()` (what each backend gets),
  `switched_on_keys()` (the hook's settings-only view), `notice()` /
  `dismiss()`, `scan_cached()` (stat calls only while nothing moved);
- `agentvoice tools scan [--json] [--rescan]`, `agentvoice tools dismiss
  AGENT`.

**Settings** (three parts each; the check holds them):
- `sharedTools`: manifest defaults `{}` (defaults-only: a map),
  `runtime.DEFAULTS` `{}`, control on Communal → Tools. Values
  `"on:<fingerprint>"` / `"off"`; `{}` is everything found off.
- Per agent: `mcp:<server>` / `cli:<name>` in `mainTools` and
  `voiceAgents[i].tools`, beside the three built-in switches: missing =
  follow `sharedTools`, then off; anything unreadable is off; an agent the
  settings do not have, unreadable settings, or a map over 256 entries
  switch nothing on (pass 1). `runtime.detected_choices`,
  `Config.tool_switches`.

**Delivery**:
- **Claude**: `--strict-mcp-config` on every turn; Agent Voice's servers and
  the found ones switched on for this agent (the definition Claude itself
  would pick for its project) in **one 0600 file with a random name**
  (`base.private_config_file`; a content hash in argv could be guessed back
  from a short secret); a CLI switched off gets the two deny rules; at
  Trusted the hook's matcher adds the found servers; the init event's server
  list kept as `live_servers`, written by the idle poll to
  `$RUNDIR/tools/live.json`.
- **Codex**: every config.toml server not switched on gets
  `enabled=false`, the file read at the turn; the daemon hands the digest
  of each approved definition and a rewritten one is disabled (pass 1); a
  file that cannot be read whole, or an unapproved server whose name `-c`
  cannot carry, **stops the turn** with the reason (passes 1 and 2).
- **CLIs**: one preamble line for every backend that runs commands
  ("you may use gh; docker, tailscale are switched off for you in Agent
  Voice: do not run them; …"). Never an endpoint.
- A change lets the idle process go (`apply_extras`), as for the browser.

**The hook** (`permission_hook.detected_refusal`): a call to an MCP server
that is not Agent Voice's own (or Claude in Chrome) is refused unless this
agent's switch for it is on now, read fresh, **before** any "allow all in
this chat" grant; any failure, unreadable settings, an agent not configured
or now on another program: refused. Server keys never hold `__` and the key
is read exactly (pass 1); a key is on only when no switch naming it says off
(pass 2). One that is on is asked below Trusted, as before.

**Taint**: an agent with a found MCP server switched on writes notes marked
as possibly outside text, and its answers and results are marked, like the
browser (`crew_mcp.could_browse`, `collab._could_browse`; wording now "web
pages or a tool server's output"). The Agents page's Rule of Two warning
counts a found server too.

**Pages**:
- **Agent details → Tools & skills** is now the home of an agent's own tool
  switches, through the one overlay function `s.setAgentTool(id, key,
  value)` (Settings.qml; it refuses anything but a tool switch and a valid
  value, keeps every other field and agent byte for byte):
  - *Built in*: desktop tools, browser, Omarchy commands as As every agent /
    On / Off; notes and collaboration summarised with a link to the Agents
    card (their home is unchanged);
  - *Found on this machine*: one row per tool with its source, masked
    command, status ("On, as for every agent", "Off, its own switch",
    "Changed since you turned it on", why it cannot be used, "running in its
    last session"), whether it asks at this agent's level (⚠ at Trusted),
    "Told, not enforced" for a CLI, and As every agent / On / Off. **On, or
    following every agent while that is on, opens a `ui/ToolConfirm`**
    (what it runs, where it is defined, who gets it, the Trusted and
    outside-text warnings); the approval is written only from its
    `onConfirmed`. Off is written at once. Rescan;
  - the one-time **"Off since this version"** notice: what this agent could
    use that nobody switched either way, each with Turn on, and Dismiss (a
    state file, `$XDG_STATE_HOME/agentvoice/tools-notice.json`, never
    shell.json);
  - a Gemini, Antigravity or Copilot agent's tab says those still start the
    MCP servers in their own settings.
- **Communal → Tools**: the three switches for every agent, plus each found
  tool "on for every agent" through the same confirm (into `sharedTools`),
  Rescan, and "Add a command-line tool by name".
- **Agents → Tools card**: read only: what it has and where from, how many
  found tools are switched on, links to Agent details and Communal.
- `ui/ToolConfirm.qml`: inline, no timer, Cancel focused, Escape cancels;
  the only element besides `DangerButton` allowed an `onConfirmed`, and only
  for a tool switch (`test_confirms.py`).

**Preview**: `preview.sh`'s `agents` and `tools` routes now see a synthetic
machine (three Claude servers, one Codex server, a PATH of two fake CLIs:
never the person's own). Target `tools` rewritten for the new home.

**Bench**: `start_bench.py` variants `loose`, `strict`, `strict3`;
`bench/stub_mcp.py`.

**Docs**: CODEBASE (tooldetect, the adapters, the hook, the pages, the
settings, the CLI, RUNDIR files, the preview), README ("Tools found on this
machine"), CLAUDE.md (a ninth fail-open rule: a switch that says off has to
be off where the CLI looks), FINDINGS §44.

## What was proven, and how

- **The spike** (above): 9 Claude turns (Haiku) and 5 Codex turns
  (gpt-5.6-luna, low), each recorded.
- **Claude's resume fixture re-recorded** with the new flag: three real
  turns, Ask/Haiku → Trusted/Sonnet resuming → Ask/Haiku resuming; the
  marker (`PELICAN-4356`) recalled both ways. The fixture test demands a new
  recording when the flags change, and they did.
- **`tools` preview: 29 of 29 PASS** on the final QML: the catalog lists the
  synthetic machine only; everything off; the notice lists the five Sora
  could use, not Codex's; the built-in chip writes `tools.desktop`; github
  picked On asks, shows the command and the key's *name*, never its value
  (`PREVIEWFAKE` absent), says "Sora only", writes nothing before the
  answer; Cancel writes nothing; Turn on writes `"on:<fp>"` matching the
  catalog; gh likewise; Off written at once; Dismiss; Hazel's reasons and
  ⚠; the Agents card counts one found tool and has no writing chips; its
  link opens the tab; Communal turns linear on for every agent through the
  confirm (URL shown, header value not) and adds a CLI by name. The writes
  log holds exactly the six writes expected.
- **Screenshots**: Sora's tab narrow (520×720) dark and flexoki-light, four
  shots each; Theo's wide; Communal → Tools wide; Sora's Agents card wide.
  One fix from them: the card's subtitle was clipped.
- **Tests** (`test_tooldetect.py`, `test_tool_controls.py`, +129 overall):
  parsing every source; malformed, huge, oversized, linked (final and
  intermediate), FIFO configs; no subprocess; secrets absent from the scan,
  the cache and the CLI's output, and argv; fingerprints; CLIs; the inherit
  chain; garbage values and oversized maps off; unreadable settings off; a
  changed fingerprint off; what each program can use; delivery; the Codex
  argv (disables, bounds, digests, odd names); the hook (off refused before
  a grant, on asked at Ask, exact keys, failures refuse, end to end through
  `main()`); the daemon (a switch alone lets the warm process go, a failed
  scan hands nothing, the journal names no tool); live status; taint;
  `setAgentTool` run in node; nothing turns a found tool on outside a
  confirm (structural); the catalog.
- **Mutations: 46, 45 red.** 30 on the phase (28 first time; the two
  survivors got isolating tests and went red), 11 on pass 1's fixes (9
  first time; one got a test and went red; **one survives: the hook's exact
  key read reverted to prefix matching. It is an equivalent mutant now**:
  keys never hold `__`, so a prefix and an exact read agree on every name
  the key rule allows; the key rule itself is tested red), 5 on pass 2's.
  All run in scratch copies under /tmp, never in the clone.
- **Live, on the installed daemon** (typed, synthetic):
  - Theo's process after a typed turn started only `agentvoice-crew` and
    `agentvoice-desktop` (`live.json`): the user's `desktop-control`, which
    every Claude agent loaded before M10, no longer does;
  - the installed catalog for Sora and Hazel: everything off; Codex's
    `node_repl` Hazel's only; ⚠ at Trusted; the notice; scan 3 files, 8 ms;
  - asked which CLIs are switched off, Theo said "gh, docker and tailscale"
    and declined to run `gh --version` because it is off (the told line,
    live). The deny rule itself was not reached by that turn.

## Shared files touched, and where

- `daemon/wake_listen.py` (big shared, +~70): `detected_for`, the M10 block
  in `apply_extras` (and its counts-only journal line),
  `publish_live_tools` from `reconcile_extras`. Nothing in the turn loop.
- `daemon/agentfs.py` (big shared, +~30): `catalog` gains `detected`,
  `scan`, `notice`, `detected_note`; `UNMANAGED_MCP`.
- `daemon/collab.py` (big shared, +~10): `_could_browse`, `tainted_words`.
- `daemon/permission_hook.py` (security-critical, +~50):
  `detected_refusal`, its call before the grant.
- `daemon/runtime.py`: `sharedTools`, `detected_choices`, the spec's
  `detected`, `Config.tool_switches`.
- `daemon/adapters/claude_code.py`, `codex.py`, `base.py`;
  `daemon/crew_mcp.py` (taint); `bin/agentvoice` (`tools`).
- `Settings.qml` (big shared, +~50): `setAgentTool` only.
- `pages/AgentDetailsPage.qml` (big shared, ~1650 → ~1960),
  `pages/AgentsPage.qml` (big shared; the tool writers removed, the Rule of
  Two extended), `pages/CommunalPage.qml`, `ui/ToolSwitches.qml`, new
  `ui/ToolConfirm.qml`, `ui/qmldir`, `manifest.json`.
- Tests: `test_settings_pages.py` (`OVERLAY_HOMES`: `mainTools` and the
  `tools` field's home is `setAgentTool`, called from Agent details only),
  `test_agents_page.py`, `test_confirms.py`, and the argv readers in
  `test_desktop_tools.py`, `test_notes.py`, `test_try_it.py`; `conftest.py`
  points `CLAUDE_CONFIG_DIR`, `CODEX_HOME` and the detector's PATH at empty
  scratch places for every test.

## Measured

On this machine (i7-1185G7, 8 threads), FINDINGS §44:
- **Scan**: 3 files read of 4 tried; full scan median **9.1 ms** (max 14.0,
  n=25); cached in the process 0.22 ms, from the cache file 0.54 ms.
- **S on Sora** (Claude Haiku, Ask; 20 runs each, interleaved):

  | | loose (before M10) | strict (none on) | strict + 3 on |
  |---|---|---|---|
  | cold median / p95 | 3.06 / 4.41s | 2.49 / 3.60s | 2.81 / 4.61s |
  | warm median / p95 | 1.47 / 2.42s | 1.41 / 2.27s | 1.75 / 2.47s |

  Strict mode is 0.57s *faster* cold (the user's server is no longer
  started); three switched-on servers cost about 0.3s. Raw:
  `bench/baselines/m10-strict-mcp.json`.
- Tests 3715 → 3844; the check's test run about 4 min 20 s.

## Different from the plan, and why

- **CLIs are told, not enforced, on Claude too.** The plan expected Claude's
  deny rules might hold; the spike showed `sh -c` gets past them. Claude
  still gets the deny rules for a CLI that is off, as a speed bump the page
  never calls enforcement.
- **"Off" for a CLI tells the agent not to run it** (one preamble line
  naming the on and the off ones), rather than saying nothing: with nothing
  said, the off switch would change nothing. This is a behaviour change for
  every agent with `gh`, `docker` or `tailscale` installed (open issue 2).
- **`sharedTools` values carry the fingerprint** (`"on:<fp>"` / `"off"`),
  not booleans as the plan's table says, so a changed definition turns off
  the switch for every agent too.
- **The fingerprint covers environment values as well as the command and
  arguments**, through an HMAC so the stored value leaks nothing; rotating a
  server's key asks again.
- **Codex below Trusted refuses MCP calls itself** (recorded), so "asks
  first" there reads "Codex refuses its calls below Trusted: it has no way
  to ask".
- **Codex stops the turn** when its config.toml cannot be read whole, or
  holds an unapproved server whose name `-c` cannot carry (Codex review):
  fail closed, with the reason, rather than start servers nobody switched
  on.
- **The live MCP check used the catalog and Theo's default view**, not a
  server switched on (refused by the permission layer; see Not verified).
  Had it been allowed, it would have used Sora (Ask: every call asks)
  rather than Theo (Trusted) as the plan says, to keep a real desktop
  server from acting unasked.
- **Codex reviewed the daemon, `bin` and `Settings.qml` diff** (1,792
  lines), not the pages, the tests or the docs, to save credits; pass 2
  reviewed pass 1's daemon fix diff (511 lines). Low effort both times.
- **The notice lists every tool this agent could use that nobody switched
  either way**, not a snapshot of "loaded before this version": a server
  added later shows there too, which is still true ("off until you turn it
  on").
- **Gemini, Antigravity and Copilot** still start the MCP servers in their
  own settings; the detector does not read those, and their tab says so.

## Codex review

**Pass 1** (6 findings, all fixed in 92af969):
1. A config.toml too large or with too many servers named none of them, so
   Codex started them with every switch off. Fixed: such a file (and one
   that is not TOML) stops the turn; bounds 4 MB and 1000 servers.
2. An approved Codex server rewritten under the same name between the scan
   and the turn would start. Fixed: digests checked at the turn.
3. Prefix matching let a revoked `docs__admin` pass as `docs`. Fixed: keys
   never hold `__`, the hook reads them exactly, clashing keys are given to
   nobody.
4. `--header "Authorization: Bearer …"` was shown. Fixed: wider masking.
5. A tools map over 256 entries lost an explicit off past the cut. Fixed:
   oversized is unreadable, its owner gets nothing.
6. A plugin manifest could name `../servers.json`; a linked folder inside a
   plugin was followed. Fixed: a plain name beside the manifest only, and
   opens beneath the root with no link followed at any level.

**Pass 2** (4 findings on pass 1's fixes; 3 fixed in 2a83bb1):
1. A Codex server whose name `-c` cannot carry still started with its
   switch off. Fixed: unless switched on, it stops the turn (quoting a key
   was tried and is refused by Codex too).
2. Codex reads config.toml again after the adapter checked it: a rewrite in
   that window (milliseconds) could add or replace a server. **Not fixed**:
   open issue 4.
3. Two ids with one key: a stale approval of one vouched for the other.
   Fixed: a key is on only when no switch naming it says off.
4. A key ending in base64 padding showed its body. Fixed: key-shaped words
   masked whole.

**Pass 2's fixes were not reviewed by Codex** (credits).

Codex ran on the read-only copy both times (`codex sandbox linux -- true`
still panics: "Failed to execvp linux"). The clone's HEAD and status were
unchanged after both passes; each copy was deleted straight after.

## Found along the way

- `_Reader.json(..., limit=MAX_FILE)` bound the size limit when the module
  loaded, so changing the bound did nothing; found by a test.
- A CLI's place was first its resolved target, which a version manager
  moves on every upgrade (mise: `…/installs/gh/2.104.0/…`): every upgrade
  would have turned `gh` "changed". Now its PATH entry.
- The overlay and the daemon look CLIs up on their own PATH; here they are
  the same (checked), but a different PATH would make an approval made on
  the page never match in the daemon (open issue 5).
- Earlier conversation in Theo's history shows him reading this clone's git
  state during the phase (M0 open issue 3: Theo and the runner share the
  clone). Nothing he did reached a commit; the check's "wrote nothing in the
  tree" stayed green.

## Not verified

- **The pages in the real shell.** They need `omarchy-restart-shell` (next
  stop point, after M15). Seen only in `preview.sh` (screenshots and the
  `tools` drive above). Real pointer and keyboard on the new tab, the
  confirm's focus and Escape, and the notice scrolling its confirm into
  view: synthetic events only, or not driven at all (the scroll).
- **A found MCP server switched on for an agent and shown "running"**, and
  **`gh` on for Sora only, used only by Sora** (the plan's typed live
  checks). Writing the real `shell.json` to switch a tool on was refused by
  the permission layer this run; it widens what a real agent can do, so it
  waits for the user at the stop point: switch `gh` on for Sora on her Tools
  & skills tab, ask Sora and Theo which CLIs they may use, and switch a
  found server on for Sora and look for "running in its last session".
- **The deny rule on the installed daemon**: Theo declined to run `gh`
  because he was told it is off, so the rule was not reached live. It is
  proven only by the spike's recordings.
- **A real installed Claude Code plugin's servers** (none is installed
  here): detection and delivery are tested against the `installed_plugins.json`
  format as written down, not a real one.
- **Codex with a server switched on, live** (enabled stays on, the digest
  matches a real file): tested with fixtures only.
- **A turn refused for an unreadable config.toml or an odd server name,
  spoken on the HUD**: tested at the adapter only.
- **Pass 2's fixes were not reviewed by Codex.**
- **The installer box** (`install.sh` did not change).

## Going back

`bin/agentvoice-deploy 961ed64a552b` from the clone, `./install.sh --yes`
once the daemon is idle, then `omarchy-restart-shell`. **That is fail-open**
(plan section 7.7): M9 has no strict mode, so every Claude agent loads every
user MCP server, every project's `.mcp.json` and every plugin's again, Codex
starts every config.toml server, and the `mcp:` / `cli:` entries and
`sharedTools` are ignored (they stay in shell.json, unread). The tool-key,
the scan cache, `live.json` and the notice file are left behind and read by
nothing. Before going back, take the servers you do not want loaded out of
the CLIs' own settings.

## Open issues, for the next phase

1. **Question 3 taken by default: every found tool starts off**, with the
   one-time notice and Turn on. On this machine that means, from the
   install on: no Claude agent loads `desktop-control`; no Codex agent
   starts `node_repl`; every agent is told `gh`, `docker` and `tailscale`
   are switched off (and Claude refuses their plain forms). **Until the
   shell restarts there is no page to switch them back on**; meanwhile
   `omarchy bar set` with an `"on:<fingerprint>"` from `agentvoice tools
   scan --json` is the only way. Acceptable until stop 3, or should the
   runner approve today's servers and CLIs for the agents that had them?
2. **"Off" for a CLI tells the agent not to run it.** The alternative (say
   nothing when off, told only when on) changes nothing for an off switch.
   Keep, or soften to "told only when on"?
3. **The 23 curated CLIs** are a judgement (ones that reach an account or a
   service). Add or drop any? `git`, `curl` and the like are deliberately
   not listed.
4. **Codex's config.toml race** (pass 2 finding 2): Codex reads the file
   again after the adapter checked it; a rewrite in those milliseconds could
   add or replace a server. Closing it needs Codex to read a snapshot (a
   private `CODEX_HOME` holding a copy of config.toml and a link to the
   auth) or `--ignore-user-config` with everything passed by `-c`. Worth it?
5. **The overlay's and the daemon's PATH** must agree for a CLI approval
   made on the page to hold in the daemon (they do here). The daemon could
   publish its own scan for the page to read instead.
6. **A rotated API key in a server's environment turns the server off**
   until approved again (the fingerprint covers env values). Safer; noisier.
   Keep?
7. **A Codex server whose name has a dot stops Codex** for an agent until
   it is switched on or renamed. Strict, and stated on its row and in the
   turn's error; none exists on this machine.
8. **The equivalent mutant** (exact key read vs prefix) is left as is; the
   key rule carries the guarantee.
9. **Codex credits**: 17.04 this phase; **18.83 left for M11–M29**, about
   1 a phase: less than one low-effort pass (a pass costs 4–11). M17, M20,
   M22 and M27 are Tier A. The runner needs a decision.
10. **Carried, still open**: M9's 2–7; M8's 2–11; M7's 2–7; M6's 1, 3, 4;
    M5's 1, 4–6; M4's 4–13; the Voice library trash icon (M25); M0's small
    test and bench fixes; agy's `carries_session_across`; the runner's
    sandbox test command (`codex sandbox linux -- true` still panics).

## Codex credits used

**17.04**. The balance went from 35.87 at the end of M9 to 18.83, read from
the session logs' `rate_limits.credits.balance`:
- **Spike: 1.65** (35.87 → 34.22, read at pass 1's first call): five
  `codex exec` turns (gpt-5.6-luna, low, `--ephemeral`, so no session log of
  their own) and `codex mcp list` checks.
- **Pass 1: 9.11** (34.22 → 25.11). `gpt-6.2-astra`, **low** effort,
  sub-agents disabled, the read-only copy, the daemon + `bin` +
  `Settings.qml` diff (1,792 lines), at most 6 findings. 209,171 tokens
  (166,400 cached).
- **Between the passes: 1.89** (25.11 → 23.22, no session logged in
  between; most likely pass 1 settling late, as in M3).
- **Pass 2: 4.40** (23.22 → 18.83). Low effort, pass 1's daemon fix diff
  (511 lines), at most 4 findings.

**18.83 left** for M11–M29.

## Live checklist: what was done, what happened

Nothing was said into the microphone. Two typed turns to Theo, spoken
aloud by the daemon as any typed turn is.
- Before the deploy: state `listening`, every agent idle, no open mic, no
  task running, unlocked; `shell.json` copied (0600).
- After the install: the service active; the plugin link pointing at the
  deploy checkout at 2a83bb1; `shell.json` byte-identical to the copy.
- Typed "Reply with just the word ready." to Theo: "ready". His process's
  servers (`live.json`): `agentvoice-crew`, `agentvoice-desktop`; no
  `desktop-control`.
- `agentvoice agents catalog sora|jarvis-ajc --json`: as in "What was
  proven".
- Switching `gh` and `desktop-control` on for Sora through `omarchy bar
  set`: **refused by the permission layer** before it ran; nothing written.
- Typed the tools question to Theo: "I'm told gh, docker and tailscale are
  switched off for me. I didn't run gh --version, because a switched-off
  tool stays off even for a test."
- At the end: `shell.json` byte-identical to the copy. No shell restart.
