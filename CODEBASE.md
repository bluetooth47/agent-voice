# Agent Voice: codebase summary for agents

Written 2026-11-21 against branch `orders-guard` at `92c71ff`. Read this
first, then `CLAUDE.md` (the binding rules for working here), then the module
you will touch. Every module in `daemon/` opens with a long docstring
explaining why it exists. Read that docstring before changing the module.
Where a docstring and the code disagree, the code wins. (The `collab.py`
and `crew_mcp.py` docstrings that said crew calls travel as files were
corrected in M8: they use a Unix socket, see 4.4.)

---

## 1. What it is

Agent Voice (`duaneoca.agentvoice`, v0.2.0, MIT) is a hands-free voice front
end for whichever AI coding agent is installed on an **Omarchy** (Arch +
Hyprland + Quickshell) desktop. You say a wake phrase, speak a request, and it
sends the transcript to an agent (Claude Code, Codex, Gemini, Antigravity,
Copilot or any OpenAI-compatible endpoint), then reads the reply aloud one
sentence at a time. Everything runs locally except the agent itself.

Up to 8 extra agents can run beside the main one. Each agent has a folder of
its own (role, personality, instructions, skills, notes) and all share a
communal folder. Claude Code and Codex agents can collaborate: ask each
other questions, delegate tasks, pass the conversation, leave messages.

It has two halves:

| Half | Language | Runs as | Lives in |
|---|---|---|---|
| **Daemon** | Python 3 | systemd user service `agentvoice.service` | `daemon/` |
| **Desktop UI** | QML (Quickshell plugin) | loaded by Omarchy's shell | `*.qml`, `pages/`, `ui/` |

They talk through files in `$XDG_RUNTIME_DIR/agentvoice/`, Unix signals and the
`bin/agentvoice` CLI. There is no socket between the UI and the daemon. The
one socket is `$RUNDIR/crew/calls.sock`, between the crew MCP server (run
inside an agent's CLI) and the daemon.

---

## 2. Where things live on disk

| Path | What |
|---|---|
| `~/Projects/agent-voice/` | **The development clone. Work here.** Remotes: `fork` (push), `upstream` (duaneoca, push disabled). |
| `~/.config/omarchy/plugins/duaneoca.agentvoice` | **The live plugin path: a symlink** to the deploy checkout below (since M0). Never written directly. |
| `~/.local/share/agentvoice-plugin/` | **The deploy checkout** the symlink points at, on a detached HEAD. Changed only by `bin/agentvoice-deploy`. |
| `~/.local/state/agentvoice/deploys.log` | One line per deploy: time, previous commit, new commit, target. |
| `~/.local/share/agentvoice/app/` | **An installed copy** of the daemon. The service runs this copy, not the repo. Update it with `./install.sh --yes`. |
| `~/.local/share/agentvoice/{venv,models,verifiers,wakewords}` | Interpreter, wheels, Vosk/Whisper/Piper/sherpa models, trained verifiers. |
| `~/.local/share/agentvoice/agents/<id>/` | One folder per agent (`main` for the main agent): `role.md`, `personality.md`, `instructions.md`, `skills/<name>/SKILL.md`, `notes/`, `.history/`. See section 6. |
| `~/.local/share/agentvoice/agents/.trash/<id>-<ns>/` | A removed agent's folder plus its `settings.json` entry, for Undo/Restore. |
| `~/.local/share/agentvoice/agents/.state.json` | Migration record (`MIGRATION_VERSION`). |
| `~/.local/share/agentvoice/communal/` | Shared by every agent: `rules.md`, `defaults.md`, `skills/`, `notes/`, `.history/`. |
| `~/.local/share/agentvoice/agent-plugins/` | Per-agent Claude `--plugin-dir` folders built from the Omarchy skill plus the agent's and communal skills. |
| `~/.local/share/agentvoice/omarchy-skill/` | Generated Omarchy skill. |
| `~/.local/share/agentvoice/agentvoice-skill/` | M14: the generated Agent Voice skill (`skills/agentvoice/SKILL.md`, a `stamp` of what it was built from). Written by the daemon; the orders guard covers it like the folders above. Left in place by an uninstall (regenerable, like `agent-plugins/`). |
| `~/.local/share/agentvoice/chats/` | Saved chats (opt-in), 0600, `index.json`. |
| `~/.local/share/agentvoice/stats/YYYY-MM-DD.json` | M21: the Overview's per-day counts and timings (`stats.py`); numbers and ids only, 0600 in a 0700 folder, kept 90 days, nothing written with `keepStats` off. |
| `~/.local/share/agentvoice/audit.log` | One JSON line per note write, collaboration task and agent call; never text. 0600, rotated at 1 MB. Locks: `.agentfs.lock`, `.audit.lock`. |
| `~/.config/omarchy/shell.json` | **Main settings store.** The bar widget writes the keys here (`omarchy bar set`). |
| `~/.config/agentvoice/agentvoice.toml` | Fallback config for machines without Omarchy. |
| `~/.config/agentvoice/endpoint-keys.json` | API keys for endpoints, keyed by host. |
| `~/.config/agentvoice/agent-env.json` | M17: each agent's extra environment variables (`launch_extras.py`), 0600 in a 0700 folder, written atomically under `.agent-env.lock`; never a link, never in shell.json. Values are never printed, logged or published (runinfo, the page and the CLI show names only). A file other accounts can read is not used. Inside the orders guard (`CONFIG_DIR`). |
| `$XDG_RUNTIME_DIR/agentvoice/` | Runtime IPC, see below. |
| `~/.local/state/omarchy/agents/usage/agentvoice-<key>.json` | Records that Omarchy's Agents panel shows. |

Runtime files (`$RUNDIR` = `$XDG_RUNTIME_DIR/agentvoice/`):

| File | What |
|---|---|
| `state` | JSON for the bar: top-level `state` first (the CLI's `vstate` anchors on it), plus `who`, `collab` (one-line collaboration status) and `tasks` (public task board, never a brief). |
| `pid`, `command`, `typed/` | Daemon pid; atomic command file; typed input. |
| `history.jsonl` | This session's conversation, "This session" on the Chats page (tmpfs). |
| `cards/cards.sock` | Unix socket (0600 in 0700): approval cards (M7). Askers post and wait on it; the overlay's `pending`/`permit` show and answer. The daemon holds every card. |
| `permissions/` | Before M7, the hook's `<id>.request` / `.response` files. Nothing reads them now; writes there are still asked about (orders guard). |
| `grants/` | "Allow all in this chat" grants, keyed by session hash; cleared at start. |
| `prompts/` | 0600 instruction files handed to adapters; since M10 also `mcp-<random>.json`, the MCP servers handed to Claude Code by path (a found server's definition can carry a key; argv is world readable). |
| `runinfo.json` | M16: what each agent runs, for Agent details → Advanced, written by the daemon's idle poll (`publish_runinfo`) from the live adapters (`runinfo.record_for`): the next command line (the adapter's own `launch_argv`, i.e. its `_argv`) and the last one it really started, both redacted; session, timeouts, the servers it is given, its structural log ring; the daemon's pid (a file left by a dead daemon is ignored). 0600. |
| `tools/scan.json`, `tools/live.json` | M10: the last scan of the tools found on this machine (nothing secret in it: names, sources, masked commands, fingerprints; 0600 in 0700), and each Claude agent's last init event's server list (name and status), for the Tools & skills tab. |
| `crew/calls.sock` | Unix socket: crew MCP server → daemon calls, caller identified by `SO_PEERCRED`. |
| `crew/origin/<id>.json` | Who an agent is working for during a task (for "Sora, for Theo, for you"). |
| `diffs/` | `show_changes` output from the desktop tools. |
| `wake-test.json`, `wake-auto.json`, `wake-auto.pid` | Wake-word tests. |

The service unit runs `ExecStart=<venv>/python -u <app>/daemon/wake_listen.py`.
Its template is `desktop/agentvoice.service.in`.

`daemon/paths.py` resolves all of these paths (`AGENTS_DIR`, `COMMUNAL_DIR`
are new). Never hard-code a path; add it there instead.

---

## 3. Repository layout

```
manifest.json        plugin manifest: kinds bar-widget + overlay; barWidget.schema/defaults = every setting
Panel.qml            bar icon + its popup: STOP, level meter, agent chips, 5 quick toggles, voice,
                     last heard (no permission picker since M3); passes the readout to the HUD
Hud.qml              layer-shell readout beside the bar during a turn (hidden at once on lock);
                     locked (ui/ReadoutLines, one size) or dynamic (sized to fit), top or bottom;
                     shows the collaboration line ("Theo → Sora: passing")
Settings.qml         the overlay: shared state `s`, SettingsStore, launch functions, permission prompt,
                     send sheet, sidebar frame, Ctrl+1..9/0/PgUp/PgDn page jumps, agentTint (an agent's
                     colour from the theme accent); summon {"mode":"history"} opens the Chats page
AgentFolders.qml     add/remove/restore agent folders for every page (via `agentvoice agents`), so an
                     operation and its Undo outlive the page that started it
Chats.qml            the chats browser (M18: one component, three places): list (search box ->
                     `chats search` on stdin with agent:/before:/after:, agent chips, title / agents /
                     date / turns / duration / summary (M19) or last line),
                     a chat as bubbles (ExchangeItem/ChatBubble), continue, new, share, send, rename
                     (stdin), pin, export, delete; scope all (Chats page) / agent / multi
KnobRow.qml, SettingsGroup.qml   shared slider row / group box
pages/               one file per sidebar page (11), each handed the overlay as `s`
ui/                  building blocks with no setting names (see 5.2)
bin/                 agentvoice (control CLI), agentvoice-check, agentvoice-train-verifier
install.sh           installer/uninstaller (uv, venv, models pinned by models.lock, systemd unit)
models.lock          piper-voices revision + sha256 for every downloadable file
daemon/              the Python daemon (see section 4); daemon/templates/ seeds new folders
tests/               pytest suite: 89 files, about 1840 test functions (about 2790 collected);
                     tests/fixtures/{agents,collab,preamble}
bench/               benchmarks, FINDINGS.md (measured claims, through §53), baselines/phase8.json,
                     preview/ (QML renderer), latency/preamble/roster benches, install-in-a-box
merged-plan.md       the round just built: Phases 8–16 (+ 17, the user's), sections 3.x are the spec
merge-decisions.md   how agents-plan.md and the other plan were merged
plan.md              earlier round (items 1–12, phases A–G)
phase1notes.md … phase16notes.md   per-phase write-ups of what was built, measured, found
testplan.md / testresults.md      manual and automated test plan and its results
latencyplan.md       latency work notes
```

Untracked in the working tree (do not commit blindly): `CODEBASE.md`,
`agents-plan.md` (superseded by merged-plan.md), `bugs-notes.md`,
`voice-commands-notes.md`; `testresults.md` is modified.

---

## 4. The daemon (`daemon/`)

### 4.1 The core loop: `wake_listen.py` (about 5700 lines)

This file is the entry point (`main()`), and its structure is:

- **Wake engines.** Three are selected by the `engine` setting (default
  `vosk`):
  - **Vosk**, restricted to a grammar of the wake phrase;
  - **openWakeWord** (`OwwWake`), optional;
  - **sherpa-onnx keyword spotter** (`SherpaWake`, model
    `sherpa-onnx-kws-zipformer-zh-en-3M`).

  An optional personal **verifier** (`verifier.py`) and a **cross-check**
  (`crosscheck.py`: Vosk + Whisper must both hear the same name) sit on top
  of the engine. Since M22 there are three wake decisions
  (`crosscheck.decision`): **first only** (the spotter alone), **either
  stage** (a spotter hit wakes at once and the second check rescues a short
  burst it missed: the default) and **both must agree** (`wakeBothAgree`: a
  spotter hit is held, `crosscheck.Agreement`, while the second check hears
  the burst up to it, and wakes only on the same name; the frames said
  meanwhile are carried into the capture). When the second stage cannot run
  (`crosscheck.both_blocker`: openWakeWord, Vosk, a sherpa-onnx that fell
  back, the check switched off, a Vosk-only check with no Vosk model) wakes
  are held closed and the state file's `wake_decision` says why; nothing
  falls back to one stage. "Full stop" keeps its immediate path in every
  mode, and a lock or mute drops a held wake (`Pipeline.forget_wake`).
- **`Pipeline`** owns the models: wake engine, Whisper (faster-whisper) for
  transcription, and Vosk partials. `Pipeline.apply()` *reconciles* them
  against config: it compares a spec and rebuilds only when that spec
  changes. Read the reconcile rules in CLAUDE.md before adding any
  model-backed setting. `_release()` frees the replaced model and calls
  `malloc_trim`.
- **`Daemon`** holds all the state:
  - flags: `enabled` (what the user asked for), `locked` (what the session is
    doing), and `listening`, which needs both;
  - the agent and session id, the speaker, interrupt events;
  - the crew of multiple agents (`personas`), follow-up window, open mic,
    barge-in, narration, typed input, chat save/continue, terminal handoff
    (`hand_off`), lock/yield reconciliation, and publishing to the state
    file and the Agents panel;
  - **agent folders:** runs `agentfs.migrate()` at start;
    `reconcile_parts()` / `reconcile_agent_files()` feed each adapter its
    folder pieces (`adapter.parts`) between turns; `tools_for()` and
    `plugin_dir_for()` give each agent its tools and skills;
  - **collaboration:** `self.collab = collab.Runtime(self)`; hooks into the
    loop are marked "collab" (`turn_ended`, `tick`, `stop_from`,
    `stop_all`, `deliveries`, `take_asides`). Voice commands "pass this to
    Sora …" and "Sora, take over" go through `pass_command()`;
    `side_adapter()` runs quiet `ask_agent` turns (ephemeral, nothing kept);
  - **commands inside sentences (M4):** `sentence_command()` is the one
    hook, called after the checks for a command said on its own, from the
    run loop's one-agent chain and from `_send()` (several agents; never
    for a typed message). It refuses while locked, lent out, while another
    program records (`recording_elsewhere()`, pw-dump at that moment) and
    on the agent's own voice (`_said_lately`, filled by `speak()`). The
    open-mic and goodbye commands act there and say their fixed sentence;
    new/continue chat act inside the agent's turn (`answer(command=…)` →
    `chat_in_sentence()`). The rest of the sentence goes to the agent once.
    `take_undo()` puts an open-mic switch back on "no" or "cancel that"
    within `UNDO_S` (3s) of the turn that carried the rest, under the same
    guards, and only if no other switch happened since (`_open_mic_gen`).
    After "…, stop listening" nothing listens without the wake word, so the
    frame loop opens an `undo` capture for those seconds (`undo_due()`)
    that takes nothing but an undo.
- **`Daemon.run()`** is the frame loop. It reads 100ms PipeWire frames via
  `sounddevice` (imported *inside* `run()` so tests can fake it). Each frame
  goes through gate → wake → capture (endpointing) → transcribe →
  `answer()` → `speak()`. `answer()` streams from the adapter, and
  `speech_text` chunks the stream into sentences for Piper.
- **States** (`STATES`): off, locked, yielded, listening, capture,
  transcribing, thinking, speaking, followup. Panel.qml must draw every
  state; check 10b enforces this. Since M2 a `followup` payload says which
  window it is (`window`: `open` for the open microphone, `followup` after a
  reply); a payload naming an agent's state while the microphone is muted
  carries `muted: true`; the sticky fields carry `limit_hits` (`{date,
  today, last}`: turns cut at `maxUtteranceMs` today, kept across a daemon
  restart through the old state file); and when a rebuild ended a
  conversation every publish but a locked one carries `notice` (why; the
  HUD's extra line, until that agent's next turn). Since M22 `notice` also
  carries "NAME: heard, not confirmed" for four seconds when both stages
  must agree and one did not, and the sticky fields carry `wake_decision`
  (`{mode: first | either | both, closed, blocked, why}`: `blocked` is a
  `crosscheck.BLOCKERS` code saying why "both must agree" cannot run now,
  whatever is chosen; `closed` that it is chosen anyway). Since M3 a turn with no
  answer yet carries `last_reply` (the answer before it, for the readout's
  top line), and the Display page's Preview publishes four seconds of a
  sample `speaking` payload with `preview: true` (`agentvoice
  hud-preview`; never mirrored to Omarchy's Agents panel). Both readout
  lines clear together, and stay cleared, on a lock, an agent switch, a
  chat switch from the conversation view and ten idle minutes: see
  `readout.py`.
- **Rebuilds keep the conversation (M2, bug I).** `reconcile_agent` (main)
  and `_rebuild_persona` (extra agents) always build a new adapter when the
  program, folder, endpoint, level or model changes, so no process started
  under old flags survives. `carry_session()` then keeps the session when
  only the level and/or model changed and the adapter's
  `carries_session_across` covers it (`sessions.carry`); a kept session
  loses its "allow all in this chat" grants on any level change, Ask ↔
  Edits included (`permission_hook.revoke`; if one cannot be removed the
  session is dropped instead). `catch_up_flags()` applies a level or folder
  that moved while an agent was busy before its next turn starts
  (`dispatch()`, and the single-agent path before `answer()`), and refuses
  the turn of an agent deleted or switched off meanwhile. `adapter_stale()`
  (also what collaboration calls check) counts a level that moved without
  moving the hook, Ask ↔ Edits.
- **Chimes (M2, bug J).** `chime(name, why)` logs `chime: NAME (why)` for
  every sound played. A wake for the agent the open microphone is already
  listening for re-arms silently (`listening_for`).
- **Longest turn (M2, bug C).** `maxUtteranceMs` counts from the first
  voiced frame of a capture (from the key going down with push-to-talk),
  not from when the window opened; each cut is counted (`count_limit_hit`).
- **Open mic off (M2, bug K).** An open-mic window nobody has started
  speaking into closes on the frame `open_mic` goes `None`.
- **Signals.** `SIGUSR1` toggles the mic and `SIGUSR2` interrupts. `SIGTERM`
  raises SystemExit so `finally` cleans up the pidfile and the panel records.
  Other commands arrive as the atomic file `$RUNDIR/command` (including
  `chat-continue ID [AGENT]`, `chat-new`, `task-cancel ID`), or as files in
  `$RUNDIR/typed/` for typed input.

### 4.2 Supporting modules

| Module | Role |
|---|---|
| `runtime.py` | `Config`: precedence shell.json → TOML → `DEFAULTS`, reloaded by mtime stamp, with per-agent getters `level_for`, `model_for`, `effort_for`, `agents()`, `all_agents()` (switched-off ones too), `tools_for`, `notes_write_for`, `collaboration_for`, `accepts_work_for`. `settings_readable()` is False when the entry is missing, the TOML is broken or shell.json repeats a key; guards then close. Also `StateFile`, `History`, `Speaker` (Piper TTS). Helpers: `agent_id_for`, `display_name`, `instructions_text`, `speed_pct`, `tool_choices`, `notes_choice`, `collab_choice`. |
| `paths.py` | Every path, plus `scope_root` (the project root for permission scoping; returns `None` rather than HOME on purpose). |
| `agentfs.py` | **Owns the agent and communal folders** (Phase 9): fixed file names and budgets (role 300, personality 1500, instructions 2000, rules/defaults 1500, skill 20000 chars), refuses every symlink, reads never fail a turn, every write saved to `.history/` (10 kept) and detects outside edits (Keep = `ack`, Revert). Also create/trash/restore/export, skills parsing + index + `plugin_dir` (Phase 13), `catalog` (which tools a program can use), roster lines, `parts`/`preview` (prompt pieces), and `migrate` (Phase 10). Since M6, `starters()` (the templates offered for an empty box, `templates/{role,personality,instructions}/*.md`, first line a label comment) and the `traits get|set|apply` and `templates` verbs. CLI behind `agentvoice agents`. |
| `traits.py` | M6: the trait chips' one managed line at the top of `personality.md` (`Traits: warm, brief, casual.`), after any leading comment. `parse`, `apply`: free text is returned byte for byte, unknown hand-typed values are kept, a category holds one value. Pure. |
| `try_it.py` | M6: Try it. `refusal()` (locked, lent out, stale, unknown, no program, busy, `MIN_GAP_S` 10 s), the request and status files in `$RUNDIR/try/` (0600 in 0700; the draft on stdin, never argv), `draft_parts`, `first_sentence`, and the CLI's half (`try_it.py client AGENT`). The daemon's half is `Daemon.take_try` / `try_adapter` / `handle_try`: a throwaway adapter at level ask with `no_tools` (Claude: `--tools "" --strict-mcp-config`, recorded in `tests/fixtures/try/`), none of Agent Voice's tools, `ephemeral`; never a chat, never the readout; the journal gets timing and length only. |
| `notes.py` | Notes store (Phase 14) under `agents/<id>/notes/` and `communal/notes/`: `.meta.json` (rev, author, hash, tainted, lock), 20 versions kept, base-rev conflict check, `append` without base, deny/lock checked inside the lock, corrupt meta locks everything, hand edits show as "you". M13: a note is a topic (`topic_label`, `first_line` in every listing, with its saved-version count); `gone` lists names with history and no note (Earlier notes); `_current` settles an open transfer before it reads, so half a move never reads as a note made by hand. |
| `collab.py` | Collaboration (Phases 15–16): `Task` (kinds pass/delegate/ask/message; pending → active → completed/cancelled/failed/refused), the board, checks at request and at turn start, the pass order (tell the user first, then share the chat), per-chat target sessions, `crew/origin` files, the call socket server, limits (`DEPTH_MAX` 3, `OPEN_DELEGATIONS_MAX` 2, `RATE_PER_MIN` 6, `QUESTION_TIMEOUT_S` 120, `CANCEL_WINDOW_S` 3), wrapping of returned text as information. CLI: `collab.py pass|tasks`. M20: `CHAT_TOOLS` (`chats_search`, `chats_read`) travel on the same socket and through the same `_caller` (the kernel's pid, the agent's running turn; a side turn refused), with their own rate (`chat_search.RATE_PER_MIN` 20), then `chat_search.answer`. |
| `crew_mcp.py` | MCP stdio server `agentvoice-crew`, started for every Claude Code and Codex agent regardless of `desktopTools`. 13 tools: `notes_list/read/write/append`, `list_agents`, `ask_agent`, `delegate`, `pass_conversation`, `message_agent`, `task_status`, `cancel_task`, and (M20) `chats_search`, `chats_read`, listed unless the agent's `chatSearch` is off or it is quarantined (`offers_chats`, shared with the daemon's warm-process check), sent to the daemon over the call socket like the collaboration tools, no `--guard` question. Collaboration tools hidden when the agent's `collaboration` is off or it is quarantined (`offers_collab`, shared with the daemon's warm-process check); a quarantined agent writes no communal note. argv `crew_mcp.py <program> [<id>] [--guard]`; `--guard` = Codex below Trusted, which has no hook. |
| `tooldetect.py` | M10: the tools found on this machine. **Reads, never starts anything** (a test makes `subprocess` fail during a scan): MCP servers from `~/.claude.json` (`mcpServers`, and `projects[<dir>]` for each agent's project, the local scope), each project's `.mcp.json`, enabled Claude Code plugins (`installed_plugins.json` + `enabledPlugins`, `${CLAUDE_PLUGIN_ROOT}` filled in), and `~/.codex/config.toml`; CLIs from `CURATED_CLIS` (ones that reach an account or a service) plus any added by name (a `cli:` key in a tools map), with `shutil.which`. Bounded (16 MB for `.claude.json`, 512 KB others, 200 servers, 64 plugins), regular files only, an agent-writable file (a project's `.mcp.json`, a plugin's) never followed through a link. **Nothing secret leaves it**: env and header values never, key-like arguments masked, a URL's query and password dropped (`shown_command`). A tool's **fingerprint** is an HMAC over every definition of it under `DATA_DIR/tool-key` (0600), so the approval stored in the world-readable shell.json says nothing about what it covers; any change to a definition (or a project's copy appearing) moves it. `rows()` joins the scan with `Config.tool_switches` for one agent (own switch → `sharedTools` → off; on only while the approved fingerprint holds; whether its program can use it and why not; whether it asks at its level, from the recordings in `tests/fixtures/tools/`; live status); `delivery()` is what the daemon hands each backend; `switched_on_keys()` is the hook's settings-only view; `notice()`/`dismiss()` the one-time "off since this version" list (`$XDG_STATE_HOME/agentvoice/tools-notice.json`). `scan_cached()` reuses a scan while no file, PATH folder or setting it depends on moved. CLI behind `agentvoice tools`. |
| `skillscan.py` | M11: every skill on this machine and who gets it. **Reads, never starts anything** (tested): the skills Claude Code finds by itself (`~/.claude/skills`, claude.ai's synced ones under `skills/synced/<bucket>/`, each enabled plugin's `skills/`) and Codex does (`~/.codex/skills`, `~/.agents/skills`; Codex's `.system` ones and its plugins' are its own and not switched), as recorded in `tests/fixtures/skills/spike-m11.json`. A skill's own folder may be a link (Omarchy's are) and is followed, as the CLIs do; nothing inside is. Bounded (200 skills, 400 entries a folder, 64 KB of a SKILL.md for its description). Marks what the person already switched off in the CLIs' own settings (`user_off`: Claude's `skillOverrides`, Codex's `[[skills.config]]`). `agent_view()` is one agent's skills (its own, communal, its CLI's) with `on` / `delivered` / `why`; `lanes()` puts every skill in its owner's lane plus Unused (found outside, no agent gets it); `native_off()` is what the daemon switches off where the CLI looks: every name in `skillsOff` plus every Agent Voice skill's name (so the CLI's own of that name is never offered beside it), each with every name it goes by (its folder's and its front matter's, which may differ outside Agent Voice: `alias_map`, kept while no SKILL.md moved), or, with an unreadable list, every name the CLI finds, listed in full (`SkillsUnknown` when a folder cannot be listed, holds more than can be listed, or the plugin list cannot be read). "omarchy" in a list also switches off the bundled Omarchy skill (`Config.tools_for`). `import_skill()` → `agentfs.import_skill`. CLI behind `agentvoice skills`. |
| `notemoves.py` | M13: moving and copying a note between agents and Communal, combining notes of one folder into one topic, and Undo of a move or copy; `agentvoice notes move\|copy\|combine\|undo\|history\|lanes`. A move carries the file, its `.meta.json` entry (rev, author, taint, lock) and its `.history/`; the rev goes on from a destination tombstone if higher, and a destination tombstone's lock is kept. Under agentfs's lock, through transfer.py's journal (`kind: "note"`): both records must be readable (a corrupt one refuses); the text staged as `.t-<op>.md`; the destination's entry written before the file lands; a move hides the source (`.t-<op>-gone.md`) then publishes by one no-replace rename; history copied by version name; the source tombstoned. Recovery rolls back until landed, forward after. Combine keeps the first note named (or a new name), adds each other under a `## Topic` heading, ORs taint and lock, saves each other's last text as a version and tombstones it. Widening (into Communal, out of a quarantined agent or any agent when the list is unreadable, a tainted note) refused without `confirmed`, checked under the lock. Undo tied to digest and rev. One audit line each (`note_move`, `note_copy`, `note_combine`, `note_undo`): ids, name, sizes. Only the person: the orders guard's `NOTE_WORDS`. |
| `communal_import.py` | M15: rules, defaults and skills imported into Communal from a folder laid out as Export writes it, and Undo; `agentvoice agents import communal DIR [--confirm TOKEN]`, `import-undo OP`, `import-history`. `plan()` is a dry run that writes nothing: every file it would write, a diff per text, each skill new/same/clash, the agents reached (those that take Communal), the agents whose own skill hides one, the ignored entries, every problem (a link anywhere, a special file, a text over its budget, a skill over the bounds or with a problem, a reserved name, more than 20 skills, a clash: nothing is replaced), and a token over what was read and what it replaces. `commit()` re-reads under agentfs's lock, checks the token, and runs one record (`kind: "import"`) through transfer.py's journal: old and new bytes of each text in `agents/.transfers/<op>.d/`, skills staged as `.t-<op>-a-<name>` and published by no-replace renames, texts written with a version named for the op. Recovery rolls a `begun` record back (only what still hashes as imported; a hand-edited text leaves it `stuck`) and finishes a `published` one. `undo()` only while every skill and text is as imported; itself one record. Audit: `communal_import`/`communal_import_undo` (op id, size) and one `skill_import` per skill. Only the person: the orders guard's `FOLDER_WORDS`. |
| `transfer.py` | M12: moving and copying a skill between Agent Voice's own folders (agents and Communal), and Undo. Only the person moves anything (the pages and `agentvoice skills move\|copy\|undo`; no agent tool; the orders guard asks an agent that runs them). One transfer under agentfs's lock: anything left unfinished settled first; the source read whole by descriptor with no link followed, within the bounds every skill keeps (64 files, 2 MiB, 256 KB a file, a SKILL.md `parse_skill` accepts) and hashed; a journal record (`agents/.transfers/<op>.open.json`, inside the orders guard); the folder staged in the destination's skills folder (`.t-<op>`) by its descriptor; the source hashed again; a move hides the source (`.t-<op>-gone`) and then publishes by one no-replace rename (never in two places, at worst in neither for a moment); the history travels; the record finished (`<op>.json`, 100 kept). `recover()` finishes a published record and rolls back any other; the daemon calls it at start before any agent is built, and on its poll without waiting for the lock. Undo is tied to the digest: a move goes back only while the destination is unchanged and the source free of that name; a copy or an import is taken back only while it is unchanged and (a copy) the original still is too. One audit line each (`skill_move`, `skill_copy`, `skill_undo`): ids, name, size. Since M13 the journal is shared with notes: a record's `kind` sends it to notemoves.py for validation, settling and undo; `working()`/`busy()` mark a transfer or recovery in progress, so notes' own settle-before-read stays out of it; `history(kind=)`. Since M15 `kind: "import"` goes to communal_import.py the same way. |
| `crew_links.py` | M8: crew links and quarantine, pure. `parse_links`/`parse_quarantine` (unreadable → None and why), `Crew` (`abilities`, `allows`, `asks_first`, `reach`, `reached_by`; none out of quarantine, only ask/delegate into it), `everyone(ids)` for "Link everyone as before", `refusal()` with audit codes `no-link`, `quarantined`, `crew-unreadable`; M20 `search_refusal()`, its form for chat search (no target: unreadable or quarantined only). `QUARANTINE_BRIEF_MAX` 1000. M9: `check_write()`, what the Crew map may save (stricter than reading: no id nobody has unless that link or quarantined id is already saved, nothing out of a quarantined agent, only ask/delegate into one), run by `agentvoice crew check` (`collab.cli_crew`: one JSON line on stdin, JSON verdict on stdout, settings read from disk, nothing written). The Crew map page mirrors it; `test_crew_links.py` runs the page's JS against it in node. |
| `audit.py` | `audit.record()` takes only typed fields (ids, names, integers); a bad value is written as "?". A test AST-walks every call. Since M16 the kind `permission` (written by the hook: tool name by pattern, decision, how, level, each from a fixed list; never an argument or a path) and `wait_s`, which gives up on the lock rather than wait. M20: kinds `chat_search` / `chat_read` with `scope` (off/own/all), `hits` (a count) and `chat` (a 16-hex id); never the query. |
| `launch_extras.py` | M17: an agent's extra flags and environment variables, **checked at launch in the adapter** (`checked`, `checked_env`, `popen_env`), never only on the page. A denylist per program written three ways: exact names read off `claude --help` 2.1.330 and `codex exec --help` 0.171.0, each with its category (`level`, `hooks`, `config`, `mcp`, `tools`, `skills`, `dirs`, `prompt`, `session`, `stream`, `own`, `model`, `writes`, `elsewhere`, `exits`); words that put any flag's name in a category (`permission`, `hook`, `mcp`, `tool`, `dir`, `prompt`, `session`, `format`, `key`, `token`…); and shapes (every element a flag on its own: never a bare word, never `--`, one short flag per element, `--no-X` judged as X, a prefix of a refused name refused). Only Claude Code and Codex are passed any (`PROGRAMS`); a refused one raises `LaunchRefused`, whose words name the flag and never its value (`failure` kind `refused`). Environment names: a denylist of exact names, prefixes and suffixes (PATH, HOME, LD_*, PYTHON*, NODE_*, XDG_*, the proxies, *_BASE_URL and other addresses, CLAUDE_*, CODEX_*, AGENTVOICE_*, BASH_*, GIT_*…). `agentvoice agents flags check PROGRAM` (one JSON line on stdin) and `agentvoice agents env ID list|set NAME|unset NAME|clear` (a value on stdin; names only ever printed). |
| `agent_manage.py` | M17: Duplicate and Reset to defaults, the settings-entry half (agentfs does the folders: `duplicate_folder`, `reset_folder`, `undo_reset`). `duplicate_entry`: a new id and wake phrase, switched off, at Ask, no tool switched on, no extra flag or environment variable, every restriction the original has kept (a tool or skill off, notes denied, collaboration off/ask, work refused); a quarantined agent, or any while the list cannot be read, is not copied. `reset_entry`: id, wake phrase, name and switch kept, everything else a new agent's; the old folder and entry go to the trash first so Restore (or Undo) puts it back. `agentvoice agents duplicate ID | reset ID --line | unreset NAME`. |
| `stats.py` | M21: the Overview's numbers. `record_turn(agent, kind, turn_id, wake_to_reply_ms=, transcribe_ms=, reply_ms=)` (once per random turn id; `kind` from `TURN_KINDS`; the wake figure only for `wake`), `record_wake(how)`, `record_rejection(stage)` (`second-check`: a name heard and turned down; `confidence`), `record_limit_hit()`: each a locked read-modify-write of today's file, atomic, never raising (False instead), a damaged file replaced, a link not followed; pruned past 90 days (day-named regular files only). Waits are fixed-bucket histograms with n/sum/min/max; `quantile` interpolates in the bucket and stays within min..max. `summary(days)` (today and the range, every timing with its count, `None` for no data) for `agentvoice stats`; `clear()`. `memory()`: the daemon's RSS and, apart, the sum over its descendants. The daemon calls it only through `Daemon.keep_stat` (reads `Config.keep_stats()` each time), `note_wake` (after each `feed_wake`), `count_turn` (end of `answer()`, from the turn's clock: `kind`, `woke`, `whisper_ms`, `voice_end`, `first_audio`) and `count_limit_hit`; an AST test holds what those calls read. |
| `runinfo.py` | M16: Agent details → Advanced, read only. `redact_argv` (secret-named, header and environment flags, `-c key=value` whose key names a secret, key-shaped words, known key prefixes anywhere, bearer tokens, a URL's password and query; the session id stays); `Ring`, the daemon's per-agent log ring, whose `add` types every field (kind, seconds, tool names by pattern, `failure.KINDS`, the `sessions` changes) so no text fits; `record_for` (one adapter's record); `write`/`read` of `$RUNDIR/runinfo.json`; `view` (the published record, given vs seen servers from `tools/live.json`, the agent's `permission` audit lines) for `agentvoice agents runinfo ID [--json]`. |
| `speech_text.py` | Markdown → speakable prose, sentence boundaries, code blocks → "Code omitted", `safe_for_terminal`, `as_prompt`; `pass_command` ("pass/send this to NAME …") and `is_take_over`. Since M4 the **command table** (`COMMANDS`: id, phrases, effect, the positions it may sit at, the in-sentence phrases, CLI equivalent, the fixed sentence said when it fires inside a sentence) and **`find_command(text, mode, names)`**: the rules from before M4 first (`exact`), then a command at the start or end (`edges`) or in its own clause (`clause`), with the never-fires rules (an object after it, a negation, quoted or reported speech, a question, two commands). |
| `voice_commands.py` | `agentvoice commands [--json]`: the table plus each enabled agent's wake phrase, from the settings. |
| `cards.py` | **Approval cards** (M7). `Desk`: the daemon's cards, posted, shown, answered once (`_finish` under one lock); silence, expiry, a stop, a hung-up asker or a lock is no. `Listener` on `cards/cards.sock`; `Verifier`: an asker must descend from the daemon; an **allow** counts only from a process whose parent is the live Omarchy shell (exe `quickshell`, `-p $OMARCHY_PATH/shell`, not descended from the daemon), whose stdout (`pending`) or stdin (`permit`) is a pipe that shell holds, carrying the card's one-use nonce and digest, while unlocked. A failed allow **denies** the card. `ask()`: the hook's client, which checks the listener is its own ancestor. CLI `cards.py show [ID]` / `answer ID VERDICT` (nonce on stdin). `LOCAL_DESK` in the daemon. Security-critical. |
| `permission_hook.py` | Claude Code **PreToolUse hook**. Posts the card to the daemon over `cards/cards.sock` (M7; `ask_card` → `cards.ask`, or `LOCAL_DESK` in-process) and waits on the same connection. Levels: `ask` / `edits` / `trusted`. Fails *closed*; hook settings use `onFailure: "block"`. Crew rules: notes reads allowed, notes writes asked at Ask and refused when `notesWrite` is deny; collaboration tools pass (the daemon asks). Loading the agent's own skill is a read. **Found tools** (M10, `detected_refusal`): a call to an MCP server that is not Agent Voice's own is refused unless this agent's switch for it is on now (read fresh; unreadable settings, an agent not configured or on another program, any failure: refused), before any grant; one that is on is asked below Trusted. **Orders guard** (`orders_write`, 92c71ff): see section 8. Since M16 each decision that is not simply a free tool gets one `permission` audit line (`_record_decision`: agent, tool name, allow/deny, how — asked, unanswered, refused, level, chat, failed — and level), written after the decision is on stdout, outside main()'s catch and inside its own, with a half-second lock budget; `_HOW` is set where decide() and _ask() reach a decision and read only by main(). M20: `CREW_CHATS` (`chats_search`, `chats_read`) pass at every level, as reads (the daemon decides which chats); a direct read of the saved-chats folder (`_saved_chat`: Read, Glob, a Grep rooted there or whose pre-search would read a chat file, a link into it) is asked below Trusted, as another agent's folder is. Security-critical. |
| `readout.py` | M3, bug B: the readout's kept reply (`last_reply`), when both lines clear and stay cleared (`gone`: lock, agent or chat switch, `KEEP_S` 600 s idle), and the 4 s preview. Pure, on an injectable clock; `Daemon._compose` calls it for every unlocked payload. |
| `sessions.py` | M2, bug I: the pure rule for whether a conversation survives an adapter rebuild (`carry`, `spec_changes`, `why`). |
| `crew.py` | Multiple agents: `Persona` (own adapter/session/voice, plus `task`, `saved_conversation`, `turn_id`, `answering` for collaboration), `route()` picks who was addressed by wake name. With extra agents, each turn runs on its own thread. |
| `chats.py` | Saved conversations (opt-in `saveChats`), 0600, `index.json`. Shared chats (Phase 15): `owner`, `participants`, `shared_with`, per-speaker `sessions`; `may_replay`, `may_continue`. CLI includes `may-continue`. M18: `delete_all` (only `<id>.json` files and their temporaries directly in the folder; a link removed as a link, never followed or counted; the index rewritten with `purged`), `delete` remembers the id an hour in `deleted`, and `record(began=)` refuses a turn that began before either (the daemon passes the time the turn was sent), so a save in flight never restores deleted history; `stats` (lstat, creates nothing); `search` (the `find` scorer, `score()`, with the last word also a prefix; every chat or one agent's). `rename ID` with no title and `search` read stdin. M19: `instant_title` (the first-sentence title, stored at creation), `renamed` (set by `rename`), `auto_title` / `summary` / `named_for` / `named_at` (`set_name`, which never touches `title` and never recreates a deleted chat); `user_renamed` (the flag, or a title that is not the instant one: a rename from before M19 or by an older build) and `display_title` (rename > written name > first sentence), which is the index's `title`; `score()` counts every name as a title and the summary at 1.5; `parse_query` / `parse_date` / `agent_matches` give `search` its `agent:`, `before:`, `after:` filters (an unreadable one is reported, `left out:` on stderr). M20: `search(may_see=)` judges each chat (index entry, then file) before any filter, score or count; `expired(retention)` is what the next prune would delete (`_doomed`, shared with `prune`). |
| `chat_search.py` | M20: chat search as an agent tool, the daemon's side. `scope()` (settings unreadable → `unreadable`; `crew_links.search_refusal`: crew settings unreadable or quarantined; `off`; else `own`/`all`), `visible()` (the `may_see` for `ChatStore.search`: `own` = `chats.may_replay`, `all` = every chat; never one `ChatStore.expired` lists), `answer()` (no work another agent asked for (`for-agent`); the first check; `saveChats` off = no saved chats; the search or the read; the last check with settings read again, the turn still live, every chat reloaded and judged under both readings; one audit line and one journal line of numbers). What is handed back: `search_text` / `hit_text` (id, title, dates, speakers, summary, a snippet, quarantined speakers marked; `HITS_MAX` 10), `read_text` (fenced, `READ_MAX` 8000, where to go on). `plain()` strips control and format characters. |
| `chat_names.py` | M19: names and summaries. `mode()` (owner only with saving on and readable settings), `due()` / `pick()` (quiet `IDLE_S` 120 s, used within `FRESH_S` a day, `named_for` != `updated`), `Budget` (`PER_HOUR` 10, seeded from the index's `named_at`), `refusal()` (off, locked or undetermined, unreadable crew settings, quarantined owner, owner gone, no program, a different program from the chat's, a backend `try_it.backend_refusal` refuses, busy), `prompt()` (fenced, first exchange plus the newest, `TRANSCRIPT_MAX` 6000), `parse()` / `clean()` (control and format characters out, caps 60 / 160), `make_side()` (level ask, `no_tools`, `ephemeral`, no parts or instructions, not spoken). The daemon's half is `Daemon.name_chats` (the idle poll, below the listening gate, every `LOOK_EVERY_S`) and `_name_one` (a thread; journal gets seconds and lengths). |
| `eager.py` | Transcribes at pauses while the person is still talking. |
| `barge.py`, `headset.py` | Barge-in: VAD plus an echo-calibrated gate; only works on a headset. |
| `crosscheck.py` | Vosk + Whisper must both hear the wake name; M22: the three wake decisions, why "both must agree" cannot run (`BLOCKERS`), and the hold (`Agreement`). |
| `noise_floor.py` | Adaptive gate: room floor median + `gateMarginDb`. M23: `rise_db_per_s` / `fall_db_per_s` on the running floor, set in place by `set_rates()` (bounded by `RISE_BOUNDS`, `FALL_BOUNDS`) from `Config.gate_rates()` (`gateRiseTenths`, `gateFallTenths`; unreadable → 0.5 and 3.0); `SPEEDS` is the page's slow / normal / fast. |
| `narration.py` | "Progress talk": fixed-table sentences from the agent's real tool events. Never model-written. |
| `chimes.py` | wake / heard / done sounds. |
| `failure.py` | Classifies agent errors (limit, auth, network…) without repeating their text. |
| `agents_panel.py` | Writes Omarchy Agents-panel records; "Working for Theo" during a task. |
| `desktop_mcp.py` | Stdlib-only MCP stdio server `agentvoice-desktop`: window/workspace/editor/browser tools via Hyprland. `servers()` returns its entry; `serve(handler=)` is shared with crew_mcp. Enabled per agent by `tools_for`. |
| `omarchy_skill.py` | Generates the Omarchy skill from `omarchy commands --json` + `hyprctl binds -j`. |
| `agentvoice_skill.py` | M14: generates the Agent Voice skill, how Agent Voice itself works, **explain only** (question 7): the command table (`speech_text.table`: every phrase, effect and where it counts, the mode now in force), each agent's wake phrase (as escaped JSON strings; a phrase that is not plain words is left out), every setting with its page (label and first sentence from `manifest.json`, page from the `put("key"` calls in `pages/`), what an agent cannot do itself (a terminal handoff ends the turn it is said in), the `agentvoice` commands to *suggest* (never run), and the files from `paths.py`. **Never teaches** what the orders guard asks about: `forbidden()` matches every fragment the guard matches on a command (card answers, passes, skill and note moves, folder writes, the guarded folders) plus `permit`, `bar set`, `shell.json`, and `build()` writes nothing when the text holds one; a command whose terminal form the guard asks about (`agentvoice pass …`) is not printed as the person's way. At most 20,000 characters (the settings notes are cut shorter before anything is refused). `stale()` is a hash of the generator, `speech_text.py`, `manifest.json`, the page files, the wake phrases and the mode, kept per file while its size and mtime stay. The daemon builds it in `reconcile_extras` (`_refresh_agentvoice_skill`; a refused build is said once and not retried until an input changes). Delivered per agent by `agentfs.plugin_dir` beside `omarchy` (Claude Code, whatever the Omarchy switch says) and as one index line, ≤160 characters, in `skill_text` for the other CLIs; an endpoint gets nothing. `agentvoice` is a reserved skill name. `python daemon/agentvoice_skill.py show|build`. |
| `endpoints.py` | Endpoint helper CLI: clean URL, list models, test, keys, reasoning text. |
| `voices.py` | Voice library: fetch (sha256 vs models.lock), sample, remove. |
| `verifier.py` | Train/load a personal wake verifier. |
| `monitor.py`, `wake_test.py`, `wake_auto.py` | Live wake scores; "say it ten times" test; automatic test with synthesized clips. |
| `templates/agent/{role,personality,instructions}.md`, `templates/communal/{rules,defaults}.md` | Seeds for new folders; a leading `<!-- -->` comment is never sent. |
| `vocab.txt`, `agentvoice.toml` | Default custom vocabulary; fallback config. |

### 4.3 Backend adapters (`daemon/adapters/`)

The contract (`base.py`) is `Adapter.send(text, session_id)`, which streams
`Chunk`s. Each adapter also implements `prepare()`, `cancel()`, `models()`,
`efforts()`, `posture()` / `guards_permissions`, `why_unavailable()`, and
`preamble()`. `feed()` hands the prompt over on **stdin, never argv**.
`Watchdog` kills hung turns (and is poked while a collaboration question
waits).

**What is running** (M16): `launch_argv(session_id)` is the command line
the next turn would start, from the adapter's own `_argv` (Gemini's and the
shared CLI adapter's were split out of `send()` for it; an endpoint has
none; since M17 it holds the extra flags too, or the refusal); every adapter notes the argv it really handed Popen as
`last_launch` (`_launched`), `launch_running()` says whether that process
lives, `handed_servers()` lists the MCP servers its next process is given
by `_argv`'s own conditions, and `prompt_channel` says how the request
reaches it. `runinfo.record_for` reads only these.

**How it is launched** (M17): `extra_args`, `extra_env` and `resume` on the
base, set by the daemon between turns (`Daemon.apply_launch`, from
`Config.launch_for` and the env file), and `idle_timeout_s` (the hung-turn
limit, read by each turn's `Watchdog`; an endpoint keeps its own). Claude
Code appends `_extras_argv()` at the end of its argv and Codex straight
after `exec` (so a flag left wanting a value meets one clap refuses, never
`resume`); both pass `env=_popen_env()` to Popen. Each check raises
`LaunchRefused`, which `prepare()` swallows and `send()` turns into one
error in our own words; no process starts. A changed flag or variable lets
the idle process go, as a tool switch does. Resume off is the daemon's:
every turn is sent with no session, the session is dropped (and its
"allow all in this chat" revoked) when the turn ends, and a continued chat
is replayed rather than resumed.

**Prompt assembly** (`preamble()`, Phase 11), most stable first so prompt
caches survive: spoken style → communal rules → communal defaults → "About
you, NAME:" personality → instructions → skills index (backends without
skill loading) → Omarchy commands → roster of other agents (as information).
Pieces come from `adapter.parts` (built by `agentfs.parts_from`); empty
pieces leave no header, so empty folders give the old preamble byte for
byte.

| Adapter | Notes |
|---|---|
| `claude_code.py` | A warm `claude -p` stream-json process. `--resume` (carried across a level or model change: `carries_session_across`, recorded in `tests/fixtures/resume/`); instructions via `--append-system-prompt-file`; the hook via `--settings` (full matcher below Trusted; at Trusted `TRUSTED_MATCHER`: Bash + edit tools, plus the browser when on); **`--strict-mcp-config` on every turn** (M10: otherwise `claude -p` also starts every server in the user's settings, the project's `.mcp.json` unapproved, and every plugin's; recorded in `tests/fixtures/tools/claude-strict-mcp.json`) and one `--mcp-config <0600 file>` (`base.private_config_file`, a random name) with desktop and crew servers and the found servers switched on for this agent (`detected_servers`); a CLI switched off is refused by `permissions.deny` `Bash(name)` / `Bash(name *)` in the hook settings (plain forms only: `sh -c` gets past, so "told, not enforced"); at Trusted the hook's matcher adds the found servers so a switch turned off reaches a warm process; the init event's `mcp_servers` kept as `live_servers`; the skills switched off for this agent where Claude looks (M11, `skills_off`) as `skillOverrides: {name: "off"}` in the same `--settings` (its Skill tool then refuses them, recorded; a bare name never touches the agent's own `agentvoice:` copy), and `--disable-slash-commands` (no skill at all) when those cannot be named (`skills_unknown`). `--plugin-dir` from `agentfs.plugin_dir`; `--no-session-persistence` for side turns. The only backend that can ask permission. |
| `codex.py` | `codex exec --json`, `thread_id` resume; options before `resume`; carried across a level or model change (recorded; a model change makes Codex emit a warning `error` item, then answer). Crew server via `crew_mcp.codex_config` (`--guard` below Trusted); every server in its own `config.toml` not switched on for this agent gets `-c mcp_servers.<name>.enabled=false` (M10), read from the file at the turn (naming one that is not there stops Codex starting); `mcp_on` holds the digest of each approved definition (`tooldetect.spec_digest`), so one rewritten since the scan is disabled; a file that cannot be read whole (over 4 MB or 1000 servers, not TOML), or an unapproved server whose name `-c` cannot carry (a dot: quoting is refused too), stops the turn with the reason (`ConfigUnaccounted`); the skills switched off for this agent (M11, `skills_off`) as one `-c skills.config=[{name="…",enabled=false},…]`, which Codex merges with config.toml's own (recorded), and no turn when those cannot be named (`skills_unknown`); below Trusted Codex refuses MCP calls itself (recorded); `--ephemeral` side turns. Read-only unless trusted. Keeps `ask_permission` so a refresh no longer rebuilds it (Phase 9 fix). |
| `gemini.py` | Plain text, one-shot, **no memory**; `--approval-mode plan`. |
| `antigravity.py` | `agy`, JSON, `--conversation` resume. Not carried across a level change (no recorded turn: agy was not signed in during M2), so it starts fresh and says why. |
| `cli_agent.py` | Plain-stdout template; only `copilot` remains (no memory). |
| `openai_compat.py` | Any `/chat/completions` endpoint. History replayed, capped by `endpointHistoryTurns`. |
| `__init__.py` | `load()` picks the backend. The main agent follows `omarchy default agent` unless `mainProgram` or an endpoint URL overrides it. |

Rule: a backend is offered only after it has answered **one real turn**.
Notes and collaboration exist only for Claude Code and Codex
(`NOTES_PROGRAMS`, `COLLAB_PROGRAMS` in agentfs).

### 4.4 Collaboration flow

- **User-started** (Phase 15): voice "pass this to Sora, …" / "Sora, take
  over", the Send sheet, or `agentvoice pass TO < brief`. The user is told
  the chat goes with it, then the target is added to `shared_with` and runs
  in its own session for that chat, at its own level.
- **Agent-started** (Phase 16): a crew tool call goes over
  `$RUNDIR/crew/calls.sock`. The daemon identifies the caller by kernel pid
  (must descend from that agent's running turn), checks chain depth, limits
  and `acceptsWork`, then applies the caller's `collaboration`: `off`
  refuses, `ask` shows the card and says it aloud, `announce` speaks one
  line and waits 3 s for "stop", `allow` is quiet. Sending to an endpoint is
  always said aloud with its host.
- Nothing one agent says is the user's approval; returned text is wrapped
  with its source and a web-taint warning when relevant.
- **Crew links and quarantine** (M8, `crew_links.py`, `crewLinks` and
  `crewQuarantine`): an agent-started call from A to B with ability X
  (ask, delegate, message, pass) runs only along a link A → B listing X.
  No link, or an empty list, is refused; an unreadable list refuses every
  agent-started call (and flashes in the HUD). Checked against the
  settings read fresh at the request (`_guard`), after the card or the
  spoken line (`_act`), when queued work starts (`start`, `_ask`) and at
  delivery (the answer in `_ask`, messages and results in `deliveries`);
  `Runtime.sweep` on every poll refuses queued work and cancels running
  work whose link or quarantine changed. `askFirst` makes the effective
  level `ask` (the M7 card) short of `off`. A quarantined agent starts
  nothing (tools hidden and refused), a link into it carries only ask and
  delegate, a delegation into it is the brief alone (capped, never the
  chat, a new session), its answers and results come back marked, and it
  writes no communal note. When one is quarantined the daemon detaches
  its sessions, lets its warm process go and revokes its shares
  (`ChatStore.detach`); release restores nothing. A pass the person starts
  needs no link but is refused into quarantine (voice, sheet, CLI). Each
  agent's prompt roster names only whom it may reach; `list_agents` lists
  only those, with `you_may`.

---

## 5. The desktop UI

- `manifest.json` declares `entryPoints`: barWidget → `Panel.qml`, overlay →
  `Settings.qml`, `keepLoaded: true`.
- The UI shells out to `agentvoice …` for everything. It reads
  `$RUNDIR/state` and `agentvoice is-active`, polled twice a second. Folder
  text goes through `agentvoice agents …` with text on stdin as one JSON line.
- The overlay deep-links with `{page, agent, tab}` (e.g.
  `{"page":"agentdetails","agent":"sora"}`). Ctrl+1..9 jump to pages.
- Read colours as `Commons.Color` (with `import qs.Commons as Commons`),
  never a bare `Color`. Any text from a transcript, a model reply, a folder
  file or an agent name needs `textFormat: Text.PlainText`.
- **QML changes need a shell restart to be seen** (`omarchy-restart-shell`).
  Tell the user first. Verify with a screenshot.
- `bench/preview/preview.sh` renders any surface beside the live shell
  without touching it. Targets: settings, popup, knob, clicks, agents,
  voices, gallery (every ui/ piece; `--arg narrow,long`, `danger`, `keys`),
  confirms (every DangerButton, cancelled then confirmed), details,
  detailshots, folders, notes, shared, tools, persist, and since M5
  agentclicks (the same actions on the old and new Agents page, to diff the
  writes) and agentshots (one scene per shot; `--arg '{"width":560}'` draws
  the narrow layout, `'{"keys":true}'` walks the page by keyboard). Since
  M6 `details` also walks the agent tabs, a rename, a starter, the trait
  chips, the meter and Try it (`agentvoice try` is a stub that logs the
  draft to `<out>.try`; `PREVIEW_TRY=refuse` makes it refuse), and
  `detailshots` with `--config` gives sora two chips chosen. Since M7
  `card` draws the permission card from a synthetic card the stubbed
  `agentvoice pending` serves (`--arg verified|unverified|allow`;
  `PREVIEW_PERMIT=refuse` makes the stubbed `permit` refuse), and checks
  the nonce arrived on stdin, never argv. Since M8 `crew` draws the Crew
  map (`--arg empty|linked|clicks`, `:520` for the narrow card; configs
  `crew3.json` and `agents8.json`); `clicks` drives Link everyone, a chip,
  Ask me first, Delete, Add link, Quarantine and Release through real saves
  and checks each list written. Since M9 it opens on the map: `linked:W:sparse`
  draws a few lines, `linked:W:table` the table, and `drags` drives the map
  with synthetic pointer and key events (draw a line, the inspector's chip
  and Ask me first, the reverse, Delete line, a drop into the zone confirmed
  and one cancelled, a drag out, a box moved, and create / reverse / delete
  from the keyboard), every save through this checkout's `agentvoice crew
  check`; the layout goes to a scratch `XDG_STATE_HOME`, copied to
  `<out>.layout.json`. Options
  include `--state FILE`, `--theme`, `--live-config`, `--config FILE` (a
  synthetic shell.json from `bench/preview/configs/`, so nothing real is
  shown or written) and `--arg '{"page":…}'`. It never moves the real
  pointer. Since M10 the
  `agents` and `tools` routes see a **synthetic machine** (three Claude Code
  servers, one Codex server, a PATH of two fake CLIs: never the person's
  own), and `tools` (with `--config crew3.json`) drives Sora's Tools &
  skills tab: the notice, a built-in chip, github picked On, its confirm
  checked for what it shows (the command and the key's name, never its
  value), cancelled, then turned on, gh likewise, github off, Dismiss;
  Hazel's (Codex) reasons; the Agents card's read-only summary and its
  link; Communal → Tools turning linear on for every agent and adding a
  CLI by name.

### 5.1 Pages (`pages/`)

| Page | What |
|---|---|
| `OverviewPage.qml` | Status and quick links. M21: the numbers (`agentvoice stats --days 7 --json`, read on open, after each turn and every 30 s): tiles for turns per agent, wake to first word, reply after you stop, transcription (each with p95 and its turn count, "no data yet" with none), wakes / turned down (false wakes labelled as the second check's), uptime and memory (the state file's `service`); a Today / 7 days choice (shown only, writes nothing); wakes by hour (`MiniBars`). The microphone card (level, gate, the one Mute) and the agents' cards with **last chat ›** (`agentvoice chats last --json`, only for a chat whose file is there). |
| `AgentsPage.qml` | One `AgentBlock` per agent, the main one included (M5): a `HeaderStrip` (state dot, name, wake phrase, pills for level, program · model, effort, voice · speed) that unfolds into a `CardGrid` of cards: Identity (name and wake phrase, runs on, `ModelPicker`), Endpoint (endpoint agents), Permissions, Voice (▶ Test plays the agent's voice at its speed), Tools (`ToolSwitches` part `tools`: chips with where each value comes from), Collaboration, notes & chats (part `collab`: collaboration, takes work, notes, chat search with its question before "Every chat"), Agent (on/off, wake model, the folder summary linking to Agent details, remove). Every write goes through `writeField(index, field, value)`, which names each key and field; `test_agents_page.py` runs those functions in node. The tools for every agent are on Communal → Tools since M5 (bug E). |
| `AgentDetailsPage.qml` | One agent's folder (Phase 12). Agents picked by `AgentTabs`, keyed by id, main first (M6). Tabs: Personality & instructions (role, personality, instructions editors, each with a one-line `Hint`, starters while empty and a meter; trait chips that rewrite the managed line through `agents traits apply` and save through the personality editor; ▶ Try it, `agentvoice try` with the draft on stdin; the prompt preview), Tools & skills (M10: **the home of an agent's own tool switches**, through `s.setAgentTool`: the built-in desktop/browser/Omarchy chips; notes and collaboration summarised with a link to the Agents card; "Found on this machine" from `agents catalog`'s `detected`, one As every agent / On / Off per tool with its source, masked command, whether it asks and "told, not enforced" for a CLI; On, or following every agent while that is on, first opens a `ui/ToolConfirm` (what it runs, where it is defined, who gets it) and writes `"on:<fingerprint>"` only from its `onConfirmed`; Rescan; the one-time "off since this version" notice with Turn on and Dismiss; since M11 the skills as lanes of `ui/SkillCard`s in `ui/DropLane`s: this agent's (its own and the ones its program finds by itself, each with a switch written through `s.setAgentSkill`), Communal (a switch for this agent), every other agent's (read only), and Unused, each card of which can be given to this agent or Communal as a checked copy through a `ToolConfirm` whose `onConfirmed` runs `agentvoice skills import`; since M12 every card can be dragged to another lane (Ctrl copies) or sent with its Move to…, all through `skillDropped`: an Agent Voice skill moves or copies through `ui/SkillMover`, one found outside is only ever copied, through the one import confirm; a clash or a skill with a problem is refused with why), Notes, Chats, Advanced (M16: what is running, from `agents runinfo` while the tab is open: the next command line and the last one started, the working directory, the conversation, the timeouts, the MCP servers given apart from those the program said it started, the whole prompt from `agents prompt` in a `PromptPreview` with `concealed` (each piece's text only on Show), the agent's recent structural log lines and Open full log, its recent permission decisions; then open/export folder, remove, trash with restore). Writes settings only through `setAgentTool` and `setAgentSkill`; Advanced writes nothing. |
| `CommunalPage.qml` | Tabs: Rules & defaults (each editor with its `FileHistory`, and Import… beside Export: M15), Who gets it (M15: one switch per agent into `communalOff`, Start fresh = `chats new ID`, and why communal notes stay reachable), Preview (M15: one agent's whole prompt from `agents prompt`, its adapter's own builder, with each piece's source, precedence and size and the total), Tools (desktop tools, browser and Omarchy skill for every agent, moved from the Agents page in M5; since M10 the tools found on this machine, each "on for every agent" through a `ToolConfirm` into `sharedTools`, Rescan, and "Add a command-line tool by name"), Skills, Notes, Chats (multi-agent conversations). States plainly that rules are text, not enforcement. Writes only those six settings (M14 added `agentvoiceSkill`, M15 `communalOff`). |
| `CrewMapPage.qml` | M8–M9: who may do what to whom, drawn (Map) or as a table (Table). **Map** (M9): agent boxes that drag (positions in `$XDG_STATE_HOME/agentvoice/crew-layout.json`, fractions of the map, never read by the daemon; none saved: a ring), a `ui/CrewEdge` line per link with an arrow at the agent it reaches (a two-way pair bows apart), a label chip on each line ("A D M P", "?" for ask first; on a crowded map only the selected agent's), drag from an agent's dot onto another to link (allows ask), a red zone to quarantine by dragging into (a `DangerButton` armed by the drop; Cancel puts the box back) and out of to release, and an inspector: a line's abilities, Ask me first, Also allow the reverse, Delete line; an agent's reach, Link to, Quarantine/Release. Keyboard: Tab to boxes and labels, Enter opens, arrows move a box, Delete on a label arms Delete line. **Table** (M8): the "no links yet" banner with **Link everyone as before** (a `DangerButton`), From / To / Allows (`ToggleChips`, disabled with the reason into or out of quarantine) / Ask me first (advisory for Trusted agents) / Delete, Add link, per agent Quarantine (confirm: what it loses) or Release, can reach / reached by, and the effective line. An unreadable list gets a banner and "Start again with no links". **Every edit goes through `commit()`**: trimmed for quarantine, queued, checked by `agentvoice crew check`, and written only by `applyChecked()` (quarantine first) through `writeQuarantine` / `writeLinks`; a refusal empties the queue and says "Not saved: …". "Changed outside Settings at HH:MM" comes from the overlay (`crewOutsideAt`). Its reading of the lists mirrors `crew_links.py`, checked in node. |
| `ListeningPage.qml` | M23: the pipeline, four `ui/StageBlock`s, each with its own `ui/AdvancedSection`: 1 Microphone (meter, gate Fixed / Follows the room, **Adapts** slow / normal / fast writing `gateRiseTenths` and `gateFallTenths` together (`gateSpeeds`, held equal to `noise_floor.SPEEDS`), the fixed level; Advanced: margin and the exact rates), 2 First listener (engine, its threshold, the phrase link; `owwBlock` with Your voice and A phrase of your own, `sherpaBlock` with the boost and Also sounds like, each only for its engine), 3 Second check (who votes, greyed with `secondCheckReason`; Advanced: window, trailing words, Whisper hint), 4 Decision (below, Vosk's confidence, today's line from `agentvoice stats --days 1 --json`); then Test my wake word. M22: **When a wake counts** (First only / Either stage / Both must agree, one control writing `wakeCrossCheck` and `wakeBothAgree`); Both is refused with the reason when the second stage cannot run, and the daemon's `wake_decision.closed` is said under it. |
| `VoicePage.qml` | Voice, speed, voice library. |
| `ChatsPage.qml` | M18: the Chats page. A foldable "Saving and privacy" card (folded once chats are saved, until opened): `saveChats`, `chatRetention`, `keepHistory` (moved from Display, same names), where the chats are and their size (`chats stats --json`, read on open, when the saved count moves and after a delete), and **Delete all saved chats** (a `DangerButton` stating the count and scope; `deleteAllChats()` starts `chats delete --all` from its `onConfirmed` only). M19: **Names and summaries** (`chatSummaries`, Off / By the chat's agent, with the measured cost). Under it `Chats { followSummon: true }`. |
| `ConversationPage.qml` | Turn timing, follow-up, open mic, narration, barge-in. |
| `DisplayPage.qml` | HUD, Agents panel, the "Saved chats → Go to Chats" pointer, logging. M21: `keepStats` and **Clear stats** (a `DangerButton`; `clearStats()` starts `agentvoice stats clear` from its `onConfirmed` only), with how many days are kept and their size. |
| `AboutPage.qml` | Version and links. |

### 5.2 Building blocks (`ui/`)

| Component | What |
|---|---|
| `AdvancedSection.qml` | Collapsed "Advanced (N)" fold for fine-tuning. |
| `AgentTabs.qml` | One tab per agent with a state dot; one row that scrolls at nine. |
| `Card.qml`, `CardGrid.qml` | Titled box (optionally foldable); two across from 520 px of page, one when narrower. |
| `ChatBubble.qml` | One turn as a left or right bubble; plain, selectable text; `stripe` (M18) the speaking agent's colour down its left edge; width from `FontMetrics` (a hidden measuring Text froze the overlay on a 200-exchange session). |
| `CompactSelector.qml` | "Label: value ▾" mini selector; a disabled one says why. |
| `CrewEdge.qml` | M9: one Crew map line (QtQuick.Shapes): border to border between two boxes, a quadratic bend for a two-way pair, an arrowhead, dashed when it carries nothing; exposes the chip point (`midX`, `midY` at `chipT`). |
| `DangerButton.qml` | ⚠ button whose first click arms an inline "Really …? Cancel / Do it" strip; 6 s or Escape disarms; Cancel has focus; the action runs only in `onConfirmed`. |
| `DraggableCard.qml`, `DropLane.qml`, `UndoToast.qml` | Drag moves, Ctrl+drag copies, a "Move to…" menu as the keyboard way; a lane can refuse with a reason; Undo for 10 s. They only ask: the page moves. |
| `HeaderStrip.qml`, `Pill.qml` | Foldable agent header (dot, name, pills, caret, a problem and a warning line shown folded or open); `controlled` makes a click ask through `toggled()` rather than assign, so the caller's binding survives. Small toned label. |
| `Hint.qml`, `Tip.qml` | One plain line with the detail in a tooltip; the shared themed tooltip. |
| `MenuList.qml` | Pick-one popup list with keyboard walking, headings and disabled entries with reasons. |
| `ModelPicker.qml` | Model and effort joined in one control. |
| `StageBlock.qml` | A numbered pipeline stage with a connector line. |
| `StatTile.qml`, `MiniBars.qml` | One Overview number; per-hour bars with a readout line. |
| `SearchField.qml` | Search box (debounced, Escape clears) with filter chips. |
| `ToggleChips.qml` | Row of on/off (optionally inherit) chips; a disabled chip says why. |
| `EndpointEditor.qml` | Endpoint URL/model/key/test editor. |
| `ExchangeItem.qml` | One exchange as bubbles (M18): you on the right, the named agent on the left in its `tint`; thinking folded; failed / stopped under it; agent-to-agent questions folded to one line that opens to both agents' bubbles. |
| `FileEditor.qml` | The one editor for each folder file; Keep/Revert for outside edits, base-stamp conflicts. Since M6: `sentChars` (agentfs.clean's count, checked against it in node), a `BudgetMeter`, `current` (the draft) and `fill(text)` (a starter or the chips' text, saved like typing). |
| `BudgetMeter.qml` | M6: a thin bar and "used / limit", toned from 85% and past the budget. |
| `StarterChips.qml` | M6: "Start from:" and one button per template; hands the text up. |
| `InstructionsBox.qml` | Free-text box that saves on focus loss. |
| `LevelMeter.qml` | Mic level meter. |
| `NotesPanel.qml` | One notes folder: editor, history with View/Restore, lock, Open folder. Since M13 the notes are topic cards (`SkillCard`: topic, first line, rev and author) in `DropLane`s: this folder's first (Open, Lock, and Pick while combining), then every folder's from `agentvoice notes lanes`, whose cards open on their own tab (`openElsewhere`). Every drop and Move to… goes through `noteDropped` (refuses a clash, a note with a problem, an unreadable record, saying why) into `NoteMover`. Combine picks notes in order (the first is kept); Earlier notes puts one back from its newest version. Polls skip a reading that changed nothing and wait while a card is dragged. Names no setting. |
| `NoteMover.qml` | M13: the note move/copy/combine/undo commands, built here only. `request()` runs at once or, when it widens (into Communal, out of a quarantined agent or with an unreadable list, a tainted note), shows a `ToolConfirm` (who can read it, that past versions go too) whose `onConfirmed` alone calls `transferNote()`, the one place `--confirm` is added. Combine always asks (`combineNotes()` only from its confirm). Then an `UndoToast`; failures said. |
| `PageHeader.qml` | Page title row. |
| `PromptPreview.qml` | What an agent is told, piece by piece, each labelled with its source (since M15 optionally with how it stands against the others and its size). Read only. |
| `FileHistory.qml` | M15: a folder file's saved versions beside its editor: when, who, size; View (its text and a diff to now, `agents version`); Restore (`agents revert … --base` the editor's stamp, never while changed outside Settings) and Undo for ten seconds. |
| `CommunalImport.qml` | M15: the import box: Check (the dry run, listed), Import… → a `ToolConfirm` whose `onConfirmed` alone calls `commitImport()` (the only place `--confirm` and the token are built), then Undo for ten seconds. |
| `ReadoutLines.qml` | M3: the locked readout, two fixed-height slots (last answer, dim with an accent bar; what is being said now, bright), each showing the end of its text, PlainText. Used by the HUD and the popup. |
| `SegmentedChoice.qml` | Segmented enum control; `wrap: true` (with a width set) lets the chips wrap in a half-width card. |
| `SendSheet.qml` | "Send to another agent": target, editable brief, what goes with it; sends via `agentvoice pass`. |
| `SettingRow.qml` | One setting on one line. |
| `SettingsStore.qml` | The single copy of the widget's settings; `put()` writes through `omarchy bar set`. |
| `SidebarNav.qml` | The page list down the side. |
| `StatusCard.qml` | Boxed status line with a state chip. |
| `TabStrip.qml` | Tabs across the top of a page. |
| `ToggleRow.qml` | A SettingRow with a switch. |
| `ToolSwitches.qml` | One agent's tools and collaboration, as two cards (`part: "tools"` or `"collab"`): since M10 the tools part is **read only** -- desktop/browser/Omarchy with where each value comes from or why a program cannot use one, how many found tools are switched on, and links to Agent details (`detailsAsked`) and Communal; collaboration, takes work, notes, and (M20) chat search: Off / Its own and shared / Every chat, where "Every chat" only opens a `ToolConfirm` (`pickChatSearch`) and `chatSearchPicked("all")` is emitted from its `onConfirmed` alone; the hint says what the scope does not hold, per program. Holds the program tables test_tools_skills checks against agentfs. |
| `ToolConfirm.qml` | M10: the inline question before a found tool is switched on (title, plain-text lines, a warning, Cancel focused, Escape cancels, no timer). The only element besides `DangerButton` allowed an `onConfirmed` (test_confirms), and only for a tool switch or (M11) giving a copy of a skill found on this machine. |
| `SkillCard.qml` | M11: one skill as a card: name, a line of what it is for, a source pill, an optional switch (emits `toggled(on)`; the page writes), a status line, a details drop-down (description, source path, size, problems, shadowing, who gets it) and room for buttons. Plain text throughout. Since M12 draggable between `DropLane`s (a drag on its header moves, Ctrl copies; `canMove` false offers copying alone) with a Move to… menu (Menu or Ctrl+M from the keyboard); it only emits `moveRequested`. |
| `SkillMover.qml` | M12: the move/copy itself for any page with skill lanes: `request()` runs `agentvoice skills move\|copy` at once, or, when it widens (into Communal; out of a quarantined agent, or any agent when the quarantine list is unreadable), first shows a `ToolConfirm` naming who gets it and who keeps its own, whose `onConfirmed` alone calls `transferSkill()`, the one place `--confirm` is added. Then an `UndoToast` (ten seconds) running `skills undo`; failures said under the lanes. Knows no setting: the page hands it labels and the quarantine list. |
| `VoiceLibraryRow.qml` | One voice in the library. |
| `VoiceSlider.qml` | Snapping slider for a setting. |

---

## 6. Agent folders, skills, notes, chats (data)

- **Settings knobs stay in shell.json; content lives in folders.** The old
  `agentInstructions` setting and `voiceAgents[i].instructions` were
  migrated into `instructions.md` (Phase 10). `agentInstructions` is gone
  from the manifest but kept in `runtime.DEFAULTS` for migration only.
- Folder id is the agent id; the main agent's internal id is `""` and its
  folder/external id is `main`. An agent with id `communal` gets no folder.
- Removing an agent moves its folder plus settings entry to `.trash`;
  Restore puts both back.
- **Skills** (Phase 13): `skills/<name>/SKILL.md` with front matter; own
  skills shadow communal ones of the same name; `omarchy` is reserved.
  Claude gets them as a plugin dir (`agent-plugins/`); other backends get a
  skills index in the preamble. Since M11 a skill switched off for an agent
  (`skillsOff`) is in neither, and the CLIs' own skills are switched off
  where they look (`skillscan.py`). A skill found outside Agent Voice is
  given to an agent or Communal only as a **checked copy**
  (`agentfs.import_skill`: the rules every skill keeps, read beneath its
  folder with no link followed, hashed before and after, staged and
  published inside the skills folder by its open descriptor with a
  no-replace rename, its SKILL.md's version saved first, one `skill_import`
  audit line of name and size); the original is never edited, moved or
  deleted.
- **Notes** (Phase 14): per agent and communal, reached by agents through
  crew tools and by the UI through `agentvoice agents notes`. Notes are
  information, never instructions; returned with author, time and a taint
  warning if the writer could browse.
- **Chats**: shared chats carry `owner`, `shared_with`, `participants`,
  per-agent `sessions`. Only the owner and `shared_with` may be replayed a
  chat.

---

## 7. Settings (the "three places" rule)

A setting is only finished when it exists in all three places:

1. `manifest.json` → `barWidget.schema` + `barWidget.defaults`;
2. `daemon/runtime.py` → `DEFAULTS` (and `TOML_ALIASES` if it belongs in the
   fallback config);
3. exactly **one** page in `pages/`, written with `s.put("key", …)`.
   `test_settings_pages.py` enforces the one page.

Current keys, grouped:

- **Wake/listening:** `engine`, `phrase`, `mainName`, `owwModel`,
  `owwThresholdPct`, `sherpaThresholdPct`, `shortNameBoostPct`,
  `wakeConfidencePct`, `wakeAlsoSounds`, `wakeCrossCheck`, `wakeBothAgree`,
  `crossCheck*`,
  `useVerifier`, `micThresholdDb`, `adaptiveGate`, `gateMarginDb`,
  `gateRiseTenths`, `gateFallTenths`,
  `yieldToRecorders`, `fullStopAnytime`.
- **Turn timing:** `leadInMs`, `minUtteranceMs`, `maxUtteranceMs`,
  `trailingSilenceMs`, `quickEndMs`, `echoTailMs`, `followUpMs`,
  `conversationMode`, `openMicAuto`, `openMicIdleMin`,
  `openMicAddressedOnly`.
- **Speech:** `voice`, `voiceSpeed`, `speakReplies`, `chimes`, `narration`,
  `narrationSilenceS`, `bargeIn`, `bargeOnHeadset`, `bargeFactor`.
- **Agent:** `mainProgram`, `model`, `agentModels`, `agentEfforts`,
  `permissions` (per program), `projectDir`, `voiceAgents` (extra agents,
  max 8), `endpointUrl`, `endpointModel`, `endpointIsAgent`,
  `endpointTimeoutS`, `endpointHistoryTurns`, `desktopTools`,
  `browserTools`, `omarchySkill`, `agentvoiceSkill` (M14: bool, default on;
  the Agent Voice skill, per agent in its tools map beside the other three;
  unreadable reads as off, and so does unreadable settings).
- **Launch (M17):** `mainResume` (bool, default true; only an explicit false is off), `mainIdleTimeoutS` (30–600, default 90, held in bounds; not a number reads 90), `mainExtraArgs` (list, defaults-only, `[]`; not a list of strings reads as none), and `voiceAgents[i].resume` / `.idleTimeoutS` / `.extraArgs`. Settings unreadable: resume, 90, nothing extra. Written only on Agent details → Advanced: the main twins put directly (`putLaunch`), an extra agent's through `Settings.setAgentField`. `Config.launch_for`. The flags are judged by the adapter at launch, whoever wrote them.
- **Skills switched off (M11):** `mainSkillsOff` (list, defaults-only, `[]`) and `voiceAgents[i].skillsOff`: skill names (a folder's, or a plugin's `plugin:name`). One name is one switch: the agent's own copy, the communal one and its CLI's own of that name, together. Missing = every skill it would get (as before M11); anything that is not a list of names, or over 256, is unreadable: no communal skill and none its CLI finds, its own still given. Written only through `Settings.setAgentSkill`, from Agent details; `Config.skills_off_for`.
- **Found tools (M10):** `sharedTools` (map tool id → `"on:<fingerprint>"` / `"off"`, defaults-only, `{}` = everything found off; written on Communal → Tools). An agent's own switches for found tools sit in its tools map beside the built-in three (`mainTools`, `voiceAgents[i].tools`): `mcp:<server>` / `cli:<name>` → `"on:<fingerprint>"` / `"off"`, missing = follow `sharedTools`; anything else reads as off. Written only through `Settings.setAgentTool`, from Agent details. Unreadable settings switch nothing on.
- **Crew (M8):** `crewLinks` (list of `{from, to, allow, askFirst}` by
  stable id; `[]` = nobody linked), `crewQuarantine` (list of ids). Both
  defaults-only in the manifest (lists), written on the Crew map page.
  Unreadable (not a list, a malformed link, `null`, settings unreadable)
  = every agent-started call refused. No TOML alias.
- **Main agent tools and collaboration (new):** `mainTools` (map
  desktop/browser/omarchySkill/agentvoiceSkill → inherit/on/off; in defaults but not in the
  schema list), `mainNotesWrite` (allow/deny, default allow),
  `mainCollaboration` (off/ask/announce/allow, default announce),
  `mainAcceptsWork` (default true), `mainChatSearch` (off/own/all, default
  own; M20; unreadable, an unknown agent or unreadable settings = off).
- **Display/privacy:** `hud`, `hudLingerMs`, `livePartials`, `agentsPanel`,
  `logSpeech` (off by default), `keepStats` (M21, on; anything but a plain true, or unreadable settings, is off).
- **Chats (M18, moved from Display, same names):** `keepHistory`,
  `saveChats`, `chatRetention`. **M19:** `chatSummaries` (off/owner,
  default owner; unreadable, or saving off, is off).
- **Removed:** `agentInstructions` (now `agents/main/instructions.md`).

Per-agent maps (`permissions`, `agentModels`, `agentEfforts`) are keyed **by
program name**. Extra agents carry their own fields inside `voiceAgents[i]`,
each with a stable `id`, now including `tools`, `notesWrite`,
`collaboration`, `acceptsWork` and `chatSearch` (same values as the main ones). Unreadable
values fail safe: a bad `notesWrite` is deny, a bad `collaboration` is ask;
an unknown agent id gets deny / off.

---

## 8. CLI (`bin/agentvoice`)

| Commands | What they do |
|---|---|
| `start` / `stop` / `toggle` | Control the service (the panel switch). Stopping unloads ~600MB. |
| `mic` | Mute or unmute (SIGUSR1); everything stays warm. |
| `interrupt` | Stop the reply in progress (SIGUSR2). |
| `talk` / `talk-end` | Push to talk. |
| `lock` / `unlock` / `locked` | Close the mic for a screen lock, or report whether it is closed. |
| `open-mic on\|off` | Open mic. |
| `commands [--json]` | Every spoken command and each agent's wake phrase (voice_commands.py). |
| `type <agent> <text>` | Typed input to an agent. |
| `wake-test start\|stop\|auto\|auto-stop` | Wake-word tests. |
| `permit <id> allow\|allow-session\|deny`, `pending [<id>]` | Answer or show a permission request, through the daemon (M7). Nonce and digest on stdin. An allow counts only from the overlay; from anywhere else it is refused and the card denied. `pending` gives the nonce only to the overlay's own call. |
| `calibrate` | Check whether the room supports barge-in. |
| `monitor` | Live wake-word scores. |
| `voice fetch\|sample\|remove` | The Voice page's library. |
| `chats list\|show\|rename\|pin\|unpin\|delete\|export\|continue ID [AGENT]\|share ID AGENT\|unshare ID AGENT\|new [AGENT]`, `history` | Saved chats; this session's conversation. M18: `delete --all` (prints the count), `stats [--json]`, `search [--agent ID] [--json]` (words on stdin), `rename ID` (title on stdin). |
| `pass TO [--from ID] [--chat ID] < brief` | Pass the conversation to another agent (collab.py). |
| `tasks [--json]`, `tasks cancel ID` | Collaboration tasks; cancel sends `task-cancel`. |
| `agents list\|show\|create\|trash\|restore\|trash-list\|write\|history\|revert\|ack\|preview\|export\|skills\|catalog\|migrate …` | Agent folders (agentfs.py); text on stdin. |
| `agents runinfo ID [--json]` | M16: `runinfo.view`: the command line ID's next turn starts and the last one it started (redacted; never a prompt), working directory, session, timeouts, the servers it is given and those its program said it started, its recent structural log lines and permission decisions. Says when the service is not running or has not published. |
| `agents duplicate ID`, `agents reset ID --line < entry`, `agents unreset NAME` | M17 (`agent_manage.py`): a copy, switched off, with no grant, secret or session (its entry printed as JSON, for the page to save); a reset (old folder and entry to the trash first; the reset entry printed); putting a reset agent back (the fresh folder goes to the trash as a folder no agent uses). The orders guard asks an agent running any of them at every level. |
| `agents flags check PROGRAM < JSON line`, `agents env ID list [--json] \| set NAME [--line] < value \| unset NAME \| clear` | M17 (`launch_extras.py`): whether each extra flag would be passed, by the launch's own judge; an agent's environment variables, names only ever printed. `env … set/unset/clear` is asked at every level when an agent runs it. |
| `agents prompt ID [--json]` | M15: everything ID's adapter puts ahead of a request, built by `Adapter.preamble_pieces` over what the daemon hands it (parts, instructions, skill text, CLIs, a roster along crew links): each piece's source, precedence and size, the total, and the skills a Claude agent loads beside it. |
| `agents version TARGET FILE VERSION [--json]` | M15: one saved version's text and a diff from it to the file now. Reads only. |
| `agents import communal DIR [--confirm TOKEN] [--json]`, `agents import-undo OP`, `agents import-history [--json]` | M15: `communal_import.py`. Without `--confirm` a dry run that changes nothing and prints the token; with it, exactly that, all or nothing. The orders guard asks an agent running `import` or `import-undo` at every level. |
| `agents traits get ID\|set ID [--base S]\|apply`, `agents templates` | M6: the trait chips' line (choices and text on stdin as JSON); the starters. |
| `try AGENT < draft.json` | M6: Try it. One sentence in AGENT's voice from a no-tools side turn on the draft; refused with the reason. |
| `skills lanes [--json]` | M11: every skill on this machine in its owner's lane, Communal and Unused, with who gets each (`skillscan.py`). Reads files only. |
| `skills import SOURCE_ID\|PATH TO [--confirm]` | M11: give an agent (or `communal`) a checked copy of a skill found outside Agent Voice, by its id from `lanes` or (M12) a folder's path (with a `/`); the original is unchanged. Since M12 recorded, so `undo` takes it back; into Communal needs `--confirm`. The orders guard asks when an agent runs it. |
| `skills move\|copy FROM NAME TO [--confirm]` | M12: between agents' folders and `communal` (`transfer.py`); prints the op as JSON, its `op` id among it. Into Communal, or out of a quarantined agent (or any agent when the quarantine list cannot be read), refused without `--confirm`. |
| `skills undo OP`, `skills history [--json]` | M12: undo a move, copy or import if neither side changed since; the transfers recorded, newest first, stuck ones with why. |
| `tools scan [--json] [--rescan]` | M10: the MCP servers and CLIs found on this machine (`tooldetect.py`). Reads files only; never starts a tool; never prints a secret value. |
| `tools dismiss AGENT` | M10: hide AGENT's "off since this version" notice (a state file, not a setting). |
| `agents notes TARGET list\|show\|write\|lock\|unlock\|history\|version\|restore\|folder` | Notes (notes.py via agentfs). Since M13 an agent running write, lock, unlock or restore here (or `agents write\|revert\|ack\|trash\|restore\|create\|migrate\|traits set`) is asked at every level: through it a write is the person's, past locks and deny (the orders guard's `FOLDER_WORDS`). |
| `notes move\|copy FROM NAME TO [--confirm]` | M13: a note with its history and entry (`notemoves.py`). Into Communal, out of a quarantined agent (or any, list unreadable), or a note that may hold web text: refused without `--confirm`. |
| `notes combine TARGET INTO NAME…` / `notes undo OP` / `notes history [--json]` / `notes lanes [--json]` | M13: one topic from several notes of a folder (the first, or a new name); undo a move or copy while unchanged; the journal's note records; every folder's notes as lanes. |
| `endpoint clean\|models\|test\|key` | The endpoint editor. |
| `stats [--days N] [--json]`, `stats clear` | M21: the Overview's numbers, today and the last N days (default 7, at most 90); `clear` deletes every day file and prints how many. Reads files; no daemon needed. `chats last --json`: each agent's newest saved chat id. |
| `status` (JSON), `is-active` | Status for scripts and the bar. |

Commands that are not signals are written atomically to `$RUNDIR/command`.

---

## 9. Security model (do not weaken)

Summarized from CLAUDE.md and merged-plan.md section 3; read the full text.

- The permission hook **fails closed**: every exit path emits a decision,
  its command is `shlex.quote`d, and Claude's hook entry has
  `onFailure: "block"`.
- Paths are judged with a non-strict `resolve()` (dangling symlinks count).
  `edits` means source files inside the project only. Files that make
  something else run (`.claude/settings.json`, `.mcp.json`, `.envrc`,
  `.git/hooks`) always ask. Bash is never path-scoped.
- **Orders guard** (92c71ff): a write to `agents/`, `communal/`,
  `agent-plugins/`, `omarchy-skill/`, `~/.config/agentvoice/` or
  `shell.json` (or a Bash command mentioning those paths or
  `bar set duaneoca.agentvoice`) is asked about at **every** level,
  Trusted included, with no "allow all in this chat". A trusted Claude
  agent therefore now gets a hook on Bash/Write/Edit/MultiEdit/NotebookEdit.
  Bash matching is on command text: it catches the plain case, not a
  determined one. Trusted Codex has no hook, so for it outside-edit
  detection (Keep/Revert) is the only control.
- **Card answers** (M7, `cards.py`): an allow counts only from the overlay,
  checked by the kernel's word (SO_PEERCRED, a pidfd where the kernel has
  one, /proc): parent is the live Omarchy shell, the pipe is the shell's,
  the nonce and digest match, the screen is unlocked. Anything else denies
  the card. The orders guard's second layer asks at every level about
  `agentvoice permit`, the card socket and the old `permissions/` folder,
  and about writes to what the shell runs (`~/.config/omarchy`, this
  plugin's checkout) and the daemon's installed code (`app/`, `venv/`).
  Not sound against a same-user process set on defeating it (see
  phaseM7notes.md); below Trusted an agent cannot become one unasked.
  Since M8 it also asks about `agentvoice pass`, `collab.py pass`,
  `agentvoice chats share` and anything under `$RUNDIR/crew`: a pass the
  person files is governed only by quarantine, so an agent that filed one
  itself would step round its crew links.
- Notes: `notesWrite` deny and a per-note lock beat every level through the
  crew tools; a corrupt `.meta.json` locks all notes.
- Collaboration: caller identity from `SO_PEERCRED`, never from the call;
  another agent's words are never the user's approval; targets run at their
  own level in their own per-chat session.
- Agent folders refuse every symlink. The audit log never holds text.
- Search tools (`CONTENT_SEARCH`) are judged by what `rg --files` would read.
- **Extra flags and environment variables (M17)** are checked in the
  adapter at launch against a per-program denylist (`launch_extras.py`),
  refused even after a confirm and whoever wrote the setting; a refusal
  starts no process. Variables live in a 0600 file, never in shell.json,
  never printed, logged or published.
- Spoken text and folder text **never go in argv**, because
  `/proc/<pid>/cmdline` is world-readable. Use stdin, prompt files (0600),
  or an HTTPS body.
- Transcripts, replies, folder files and agent names are untrusted in the
  UI: PlainText in QML, `safe_for_terminal` for printing, `shq` for the
  floating-terminal launcher.
- **The mic closes while the screen is locked.** Not a setting. Detection
  uses `omarchy-hyprland-session-locked`; frames are dropped before
  measurement and the HUD hides at once.
- `logSpeech` is off by default; structural log lines are never gated.
- Models are pinned by sha256 in `models.lock`. Python dependencies are
  deliberately not pinned yet.

---

## 10. Development workflow

- **Where:** in the clone, `~/Projects/agent-voice`. The plugin folder
  changes only through `bin/agentvoice-deploy` (see CLAUDE.md, "Where to
  work").
- **Before any commit:** run `./bin/agentvoice-check`: static checks
  (settings ↔ UI, parse, shellcheck-ish, pinned downloads, QML property
  lint, states drawn) then pytest, then a check that the run wrote nothing
  in the tree. `AGENTVOICE_BOX=1` for real installs under
  bubblewrap when `install.sh` changes. CI (`.github/workflows/check.yml`)
  runs `check` and `full` (`AGENTVOICE_NO_SKIPS=1`).
- **Tests** cover `speech_text`, `permission_hook`, `runtime.Config`, the
  adapters (recorded real turns replayed), the frame loop (fake
  `sounddevice` in `test_states.py`; `tests/frame_loop.py` drives it over a
  scripted microphone on a fake clock, 200ms of audio time per frame, and
  records every state payload), and new suites `test_agentfs`,
  `test_agentfs_migrate`, `test_preamble`, `test_agent_pages`,
  `test_tools_skills`, `test_notes`, `test_collab` (replays
  `fixtures/collab/recorded-session.json`), `test_turn_latency`. Do not test
  QML behaviour or the real microphone.
- **Deploying:** `bin/agentvoice-deploy [--install] [COMMIT]` from the
  clone; the way back is the same with an older commit.
- **Installing:** `./install.sh --yes` copies to
  `~/.local/share/agentvoice/app` and restarts the service. **This kills any
  voice turn in progress**, including the one you may be running inside. Do
  it last, or ask the user.
- **Git:**
  - Each phase got its own branch (`phase-8` … `phase-16`), each built on
    the last; `orders-guard` is off `phase-16`. Older: `dev`, `main`,
    `phase-b` … `phase-g`, `latency-2`, `test-fixes`,
    `voice-latency-and-conversation`.
  - **Push only to the `fork` remote (bluetooth47/agent-voice). Never push to
    duaneoca/agent-voice** (`upstream` in the clone; its push URL is
    disabled).
  - The redesign round runs as phases M0–M30 (`notes/master-plan.md`),
    branch `phase-mN`, notes `phaseMNnotes.md`.
  - The user's own uncommitted work may be in the tree, so don't commit
    blindly.
  - End commit messages with the Co-Authored-By line.
- **Claims:** measure before asserting, and record numbers in
  `bench/FINDINGS.md`. Correct wrong claims in place.
- **Phase process:** after each phase, write `phaseNnotes.md`; Codex reviews
  each phase (first and second pass) and fixes land as separate commits.
- **The user is often using the desktop while you work:** never drive the
  real pointer.

---

## 11. Current state and what's next (as of 2026-11-21)

- **Built:** every `plan.md` item (phases A–G) and merged-plan Phases 8–16:
  - 8: spec, baselines, backend matrix, agent fixtures;
  - 9: `agentfs.py` storage, hook rules, Codex session fix;
  - 10: migration of instructions into folders, folder-backed Agents page;
  - 11: prompt assembly from the folders;
  - 12: Agent details and Communal pages;
  - 13: per-agent tool switches and skills;
  - 14: notes, crew MCP server, audit log;
  - 15: user-started collaboration, passing a conversation, shared chats;
  - 16: agent-started collaboration (crew tools, call socket, levels).
- **Installed:** `phase-m2` at a2deeb6 (deployed and installed
  2026-11-21 by the M2 runner; 2918 tests green): the first daemon change
  of the redesign round. Before it, `orders-guard` at 92c71ff. The QML of
  M1 and M2 shows only after an `omarchy-restart-shell` (stop point 1).
- **M0 done (2026-11-21):** the clone, the symlinked plugin path,
  `agentvoice-deploy`, the check writing nothing; `dev` and `main` are at
  `phase-m0` on the fork. Theo's project folder is the clone.
- **Named agents in daily use:** "Theo" (Opus, Piper voice `theo`) is the
  main agent. "Sora" is a Haiku extra agent (its `notesWrite` is deny in
  settings). Theo's browser tools are off.
- **Next:** the redesign round, M1 to M29, run by
  `~/Documents/agent-reconfiguration-plan/phase-runner/master_runner.py`;
  M30 hands off to Phase 17 (the user's own).

---

## 12. Known issues

- ~~The shell reloads when any file in the plugin folder is written~~ (bug
  H): fixed in M0 by the clone, the symlink and `agentvoice-deploy`.
- **Voice commands only fire when said alone** ("stop", "goodbye", "full
  stop", "take over"); inside a longer sentence they go to the agent as
  ordinary text.
- **The popup resizes** as the last-heard line appears and disappears.
- The orders guard matches Bash on command text only.
- Card answers (M7) are checked against what a same-user process can
  forge, not against one that sets out to: a plugin dropped into the
  shell's folder, injected input through the virtual keyboard or pointer,
  or a race on the overlay's pipes through `/proc/PID/fd` all still get a
  yes. Hence "advisory for Trusted agents" (phaseM7notes.md).
