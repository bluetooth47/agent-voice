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
| `~/.local/share/agentvoice/chats/` | Saved chats (opt-in), 0600, `index.json`. |
| `~/.local/share/agentvoice/audit.log` | One JSON line per note write, collaboration task and agent call; never text. 0600, rotated at 1 MB. Locks: `.agentfs.lock`, `.audit.lock`. |
| `~/.config/omarchy/shell.json` | **Main settings store.** The bar widget writes the keys here (`omarchy bar set`). |
| `~/.config/agentvoice/agentvoice.toml` | Fallback config for machines without Omarchy. |
| `~/.config/agentvoice/endpoint-keys.json` | API keys for endpoints, keyed by host. |
| `$XDG_RUNTIME_DIR/agentvoice/` | Runtime IPC, see below. |
| `~/.local/state/omarchy/agents/usage/agentvoice-<key>.json` | Records that Omarchy's Agents panel shows. |

Runtime files (`$RUNDIR` = `$XDG_RUNTIME_DIR/agentvoice/`):

| File | What |
|---|---|
| `state` | JSON for the bar: top-level `state` first (the CLI's `vstate` anchors on it), plus `who`, `collab` (one-line collaboration status) and `tasks` (public task board, never a brief). |
| `pid`, `command`, `typed/` | Daemon pid; atomic command file; typed input. |
| `history.jsonl` | The conversation view (tmpfs). |
| `cards/cards.sock` | Unix socket (0600 in 0700): approval cards (M7). Askers post and wait on it; the overlay's `pending`/`permit` show and answer. The daemon holds every card. |
| `permissions/` | Before M7, the hook's `<id>.request` / `.response` files. Nothing reads them now; writes there are still asked about (orders guard). |
| `grants/` | "Allow all in this chat" grants, keyed by session hash; cleared at start. |
| `prompts/` | 0600 instruction files handed to adapters. |
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
Settings.qml         the overlay: shared state `s`, SettingsStore, launch functions, conversation view,
                     permission prompt, send sheet, sidebar frame, Ctrl+1..9 page jumps (1850 lines)
AgentFolders.qml     add/remove/restore agent folders for every page (via `agentvoice agents`), so an
                     operation and its Undo outlive the page that started it
Chats.qml            saved-chats browser: filter by agent / multi-agent, continue, share, send to agent
KnobRow.qml, SettingsGroup.qml   shared slider row / group box
pages/               one file per sidebar page (9), each handed the overlay as `s`
ui/                  building blocks with no setting names (see 5.2)
bin/                 agentvoice (control CLI), agentvoice-check, agentvoice-train-verifier
install.sh           installer/uninstaller (uv, venv, models pinned by models.lock, systemd unit)
models.lock          piper-voices revision + sha256 for every downloadable file
daemon/              the Python daemon (see section 4); daemon/templates/ seeds new folders
tests/               pytest suite: 89 files, about 1840 test functions (about 2790 collected);
                     tests/fixtures/{agents,collab,preamble}
bench/               benchmarks, FINDINGS.md (measured claims, through §39), baselines/phase8.json,
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
  of the engine.
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
  HUD's extra line, until that agent's next turn). Since M3 a turn with no
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
| `notes.py` | Notes store (Phase 14) under `agents/<id>/notes/` and `communal/notes/`: `.meta.json` (rev, author, hash, tainted, lock), 20 versions kept, base-rev conflict check, `append` without base, deny/lock checked inside the lock, corrupt meta locks everything, hand edits show as "you". |
| `collab.py` | Collaboration (Phases 15–16): `Task` (kinds pass/delegate/ask/message; pending → active → completed/cancelled/failed/refused), the board, checks at request and at turn start, the pass order (tell the user first, then share the chat), per-chat target sessions, `crew/origin` files, the call socket server, limits (`DEPTH_MAX` 3, `OPEN_DELEGATIONS_MAX` 2, `RATE_PER_MIN` 6, `QUESTION_TIMEOUT_S` 120, `CANCEL_WINDOW_S` 3), wrapping of returned text as information. CLI: `collab.py pass|tasks`. |
| `crew_mcp.py` | MCP stdio server `agentvoice-crew`, started for every Claude Code and Codex agent regardless of `desktopTools`. 11 tools: `notes_list/read/write/append`, `list_agents`, `ask_agent`, `delegate`, `pass_conversation`, `message_agent`, `task_status`, `cancel_task`. Collaboration tools hidden when the agent's `collaboration` is off or it is quarantined (`offers_collab`, shared with the daemon's warm-process check); a quarantined agent writes no communal note. argv `crew_mcp.py <program> [<id>] [--guard]`; `--guard` = Codex below Trusted, which has no hook. |
| `crew_links.py` | M8: crew links and quarantine, pure. `parse_links`/`parse_quarantine` (unreadable → None and why), `Crew` (`abilities`, `allows`, `asks_first`, `reach`, `reached_by`; none out of quarantine, only ask/delegate into it), `everyone(ids)` for "Link everyone as before", `refusal()` with audit codes `no-link`, `quarantined`, `crew-unreadable`. `QUARANTINE_BRIEF_MAX` 1000. The Crew map page mirrors it; `test_crew_links.py` runs the page's JS against it in node. |
| `audit.py` | `audit.record()` takes only typed fields (ids, names, integers); a bad value is written as "?". A test AST-walks every call. |
| `speech_text.py` | Markdown → speakable prose, sentence boundaries, code blocks → "Code omitted", `safe_for_terminal`, `as_prompt`; `pass_command` ("pass/send this to NAME …") and `is_take_over`. Since M4 the **command table** (`COMMANDS`: id, phrases, effect, the positions it may sit at, the in-sentence phrases, CLI equivalent, the fixed sentence said when it fires inside a sentence) and **`find_command(text, mode, names)`**: the rules from before M4 first (`exact`), then a command at the start or end (`edges`) or in its own clause (`clause`), with the never-fires rules (an object after it, a negation, quoted or reported speech, a question, two commands). |
| `voice_commands.py` | `agentvoice commands [--json]`: the table plus each enabled agent's wake phrase, from the settings. |
| `cards.py` | **Approval cards** (M7). `Desk`: the daemon's cards, posted, shown, answered once (`_finish` under one lock); silence, expiry, a stop, a hung-up asker or a lock is no. `Listener` on `cards/cards.sock`; `Verifier`: an asker must descend from the daemon; an **allow** counts only from a process whose parent is the live Omarchy shell (exe `quickshell`, `-p $OMARCHY_PATH/shell`, not descended from the daemon), whose stdout (`pending`) or stdin (`permit`) is a pipe that shell holds, carrying the card's one-use nonce and digest, while unlocked. A failed allow **denies** the card. `ask()`: the hook's client, which checks the listener is its own ancestor. CLI `cards.py show [ID]` / `answer ID VERDICT` (nonce on stdin). `LOCAL_DESK` in the daemon. Security-critical. |
| `permission_hook.py` | Claude Code **PreToolUse hook**. Posts the card to the daemon over `cards/cards.sock` (M7; `ask_card` → `cards.ask`, or `LOCAL_DESK` in-process) and waits on the same connection. Levels: `ask` / `edits` / `trusted`. Fails *closed*; hook settings use `onFailure: "block"`. Crew rules: notes reads allowed, notes writes asked at Ask and refused when `notesWrite` is deny; collaboration tools pass (the daemon asks). Loading the agent's own skill is a read. **Orders guard** (`orders_write`, 92c71ff): see section 8. Security-critical. |
| `readout.py` | M3, bug B: the readout's kept reply (`last_reply`), when both lines clear and stay cleared (`gone`: lock, agent or chat switch, `KEEP_S` 600 s idle), and the 4 s preview. Pure, on an injectable clock; `Daemon._compose` calls it for every unlocked payload. |
| `sessions.py` | M2, bug I: the pure rule for whether a conversation survives an adapter rebuild (`carry`, `spec_changes`, `why`). |
| `crew.py` | Multiple agents: `Persona` (own adapter/session/voice, plus `task`, `saved_conversation`, `turn_id`, `answering` for collaboration), `route()` picks who was addressed by wake name. With extra agents, each turn runs on its own thread. |
| `chats.py` | Saved conversations (opt-in `saveChats`), 0600, `index.json`. Shared chats (Phase 15): `owner`, `participants`, `shared_with`, per-speaker `sessions`; `may_replay`, `may_continue`. CLI includes `may-continue`. |
| `eager.py` | Transcribes at pauses while the person is still talking. |
| `barge.py`, `headset.py` | Barge-in: VAD plus an echo-calibrated gate; only works on a headset. |
| `crosscheck.py` | Vosk + Whisper must both hear the wake name. |
| `noise_floor.py` | Adaptive gate: room floor median + `gateMarginDb`. |
| `narration.py` | "Progress talk": fixed-table sentences from the agent's real tool events. Never model-written. |
| `chimes.py` | wake / heard / done sounds. |
| `failure.py` | Classifies agent errors (limit, auth, network…) without repeating their text. |
| `agents_panel.py` | Writes Omarchy Agents-panel records; "Working for Theo" during a task. |
| `desktop_mcp.py` | Stdlib-only MCP stdio server `agentvoice-desktop`: window/workspace/editor/browser tools via Hyprland. `servers()` returns its entry; `serve(handler=)` is shared with crew_mcp. Enabled per agent by `tools_for`. |
| `omarchy_skill.py` | Generates the Omarchy skill from `omarchy commands --json` + `hyprctl binds -j`. |
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

**Prompt assembly** (`preamble()`, Phase 11), most stable first so prompt
caches survive: spoken style → communal rules → communal defaults → "About
you, NAME:" personality → instructions → skills index (backends without
skill loading) → Omarchy commands → roster of other agents (as information).
Pieces come from `adapter.parts` (built by `agentfs.parts_from`); empty
pieces leave no header, so empty folders give the old preamble byte for
byte.

| Adapter | Notes |
|---|---|
| `claude_code.py` | A warm `claude -p` stream-json process. `--resume` (carried across a level or model change: `carries_session_across`, recorded in `tests/fixtures/resume/`); instructions via `--append-system-prompt-file`; the hook via `--settings` (full matcher below Trusted; at Trusted `TRUSTED_MATCHER`: Bash + edit tools, plus the browser when on); one `--mcp-config` with desktop and crew servers; `--plugin-dir` from `agentfs.plugin_dir`; `--no-session-persistence` for side turns. The only backend that can ask permission. |
| `codex.py` | `codex exec --json`, `thread_id` resume; options before `resume`; carried across a level or model change (recorded; a model change makes Codex emit a warning `error` item, then answer). Crew server via `crew_mcp.codex_config` (`--guard` below Trusted); `--ephemeral` side turns. Read-only unless trusted. Keeps `ask_permission` so a refresh no longer rebuilds it (Phase 9 fix). |
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
  and checks each list written. Options
  include `--state FILE`, `--theme`, `--live-config`, `--config FILE` (a
  synthetic shell.json from `bench/preview/configs/`, so nothing real is
  shown or written) and `--arg '{"page":…}'`. It never moves the real
  pointer.

### 5.1 Pages (`pages/`)

| Page | What |
|---|---|
| `OverviewPage.qml` | Status and quick links. |
| `AgentsPage.qml` | One `AgentBlock` per agent, the main one included (M5): a `HeaderStrip` (state dot, name, wake phrase, pills for level, program · model, effort, voice · speed) that unfolds into a `CardGrid` of cards: Identity (name and wake phrase, runs on, `ModelPicker`), Endpoint (endpoint agents), Permissions, Voice (▶ Test plays the agent's voice at its speed), Tools (`ToolSwitches` part `tools`: chips with where each value comes from), Collaboration & notes (part `collab`), Agent (on/off, wake model, the folder summary linking to Agent details, remove). Every write goes through `writeField(index, field, value)`, which names each key and field; `test_agents_page.py` runs those functions in node. The tools for every agent are on Communal → Tools since M5 (bug E). |
| `AgentDetailsPage.qml` | One agent's folder (Phase 12). Agents picked by `AgentTabs`, keyed by id, main first (M6). Tabs: Personality & instructions (role, personality, instructions editors, each with a one-line `Hint`, starters while empty and a meter; trait chips that rewrite the managed line through `agents traits apply` and save through the personality editor; ▶ Try it, `agentvoice try` with the draft on stdin; the prompt preview), Tools & skills, Notes, Chats, Advanced (open/export folder, remove, trash with restore). Writes no settings. |
| `CommunalPage.qml` | Tabs: Rules & defaults, Tools (desktop tools, browser and Omarchy skill for every agent; moved from the Agents page in M5), Skills, Notes, Chats (multi-agent conversations). States plainly that rules are text, not enforcement. Writes only those three settings. |
| `CrewMapPage.qml` | M8: who may do what to whom, as a table (M9 draws the map). The "no links yet" banner with **Link everyone as before** (a `DangerButton`), From / To / Allows (`ToggleChips`, ask delegate message pass; disabled with the reason into or out of quarantine) / Ask me first (advisory for Trusted agents) / Delete, Add link (allows ask), per agent Quarantine (confirm: what it loses) or Release, can reach / reached by, and the effective line ("Theo → Sora: delegate · asks you first (link) · announces (Theo's level)"). An unreadable list gets a banner and "Start again with no links". Writes `crewLinks` only in `writeLinks` and `crewQuarantine` only in `writeQuarantine`; quarantine is written before the links it trims. "Changed outside Settings at HH:MM" comes from the overlay (`crewOutsideAt`). Its reading of the lists mirrors `crew_links.py`, checked in node. |
| `ListeningPage.qml` | Wake engine, thresholds, gate, Advanced wake tab. |
| `VoicePage.qml` | Voice, speed, voice library. |
| `ConversationPage.qml` | Turn timing, follow-up, open mic, narration, barge-in. |
| `DisplayPage.qml` | HUD, history, saved chats, Agents panel, logging. |
| `AboutPage.qml` | Version and links. |

### 5.2 Building blocks (`ui/`)

| Component | What |
|---|---|
| `AdvancedSection.qml` | Collapsed "Advanced (N)" fold for fine-tuning. |
| `AgentTabs.qml` | One tab per agent with a state dot; one row that scrolls at nine. |
| `Card.qml`, `CardGrid.qml` | Titled box (optionally foldable); two across from 520 px of page, one when narrower. |
| `ChatBubble.qml` | One turn as a left or right bubble; plain, selectable text. |
| `CompactSelector.qml` | "Label: value ▾" mini selector; a disabled one says why. |
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
| `ExchangeItem.qml` | One exchange in the conversation view; agent-to-agent questions folded to one line. |
| `FileEditor.qml` | The one editor for each folder file; Keep/Revert for outside edits, base-stamp conflicts. Since M6: `sentChars` (agentfs.clean's count, checked against it in node), a `BudgetMeter`, `current` (the draft) and `fill(text)` (a starter or the chips' text, saved like typing). |
| `BudgetMeter.qml` | M6: a thin bar and "used / limit", toned from 85% and past the budget. |
| `StarterChips.qml` | M6: "Start from:" and one button per template; hands the text up. |
| `InstructionsBox.qml` | Free-text box that saves on focus loss. |
| `LevelMeter.qml` | Mic level meter. |
| `NotesPanel.qml` | One notes folder: list, editor, history with View/Restore, lock, Open folder. |
| `PageHeader.qml` | Page title row. |
| `PromptPreview.qml` | What an agent is told, piece by piece, each labelled with its source. Read only. |
| `ReadoutLines.qml` | M3: the locked readout, two fixed-height slots (last answer, dim with an accent bar; what is being said now, bright), each showing the end of its text, PlainText. Used by the HUD and the popup. |
| `SegmentedChoice.qml` | Segmented enum control; `wrap: true` (with a width set) lets the chips wrap in a half-width card. |
| `SendSheet.qml` | "Send to another agent": target, editable brief, what goes with it; sends via `agentvoice pass`. |
| `SettingRow.qml` | One setting on one line. |
| `SettingsStore.qml` | The single copy of the widget's settings; `put()` writes through `omarchy bar set`. |
| `SidebarNav.qml` | The page list down the side. |
| `StatusCard.qml` | Boxed status line with a state chip. |
| `TabStrip.qml` | Tabs across the top of a page. |
| `ToggleRow.qml` | A SettingRow with a switch. |
| `ToolSwitches.qml` | One agent's tools and collaboration, as two cards (`part: "tools"` or `"collab"`): desktop/browser/Omarchy chips (every agent/on/off) with where each value comes from, or why a program cannot use one; collaboration, takes work, notes. Holds the program tables test_tools_skills checks against agentfs. |
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
  skills index in the preamble.
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
  `wakeConfidencePct`, `wakeAlsoSounds`, `wakeCrossCheck`, `crossCheck*`,
  `useVerifier`, `micThresholdDb`, `adaptiveGate`, `gateMarginDb`,
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
  `browserTools`, `omarchySkill`.
- **Crew (M8):** `crewLinks` (list of `{from, to, allow, askFirst}` by
  stable id; `[]` = nobody linked), `crewQuarantine` (list of ids). Both
  defaults-only in the manifest (lists), written on the Crew map page.
  Unreadable (not a list, a malformed link, `null`, settings unreadable)
  = every agent-started call refused. No TOML alias.
- **Main agent tools and collaboration (new):** `mainTools` (map
  desktop/browser/omarchySkill → inherit/on/off; in defaults but not in the
  schema list), `mainNotesWrite` (allow/deny, default allow),
  `mainCollaboration` (off/ask/announce/allow, default announce),
  `mainAcceptsWork` (default true).
- **Display/privacy:** `hud`, `hudLingerMs`, `livePartials`, `keepHistory`,
  `saveChats`, `chatRetention`, `agentsPanel`, `logSpeech` (off by
  default).
- **Removed:** `agentInstructions` (now `agents/main/instructions.md`).

Per-agent maps (`permissions`, `agentModels`, `agentEfforts`) are keyed **by
program name**. Extra agents carry their own fields inside `voiceAgents[i]`,
each with a stable `id`, now including `tools`, `notesWrite`,
`collaboration` and `acceptsWork` (same values as the main ones). Unreadable
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
| `chats list\|show\|rename\|pin\|unpin\|delete\|export\|continue ID [AGENT]\|share ID AGENT\|unshare ID AGENT\|new [AGENT]`, `history` | Saved chats; the conversation view. |
| `pass TO [--from ID] [--chat ID] < brief` | Pass the conversation to another agent (collab.py). |
| `tasks [--json]`, `tasks cancel ID` | Collaboration tasks; cancel sends `task-cancel`. |
| `agents list\|show\|create\|trash\|restore\|trash-list\|write\|history\|revert\|ack\|preview\|export\|skills\|catalog\|migrate …` | Agent folders (agentfs.py); text on stdin. |
| `agents traits get ID\|set ID [--base S]\|apply`, `agents templates` | M6: the trait chips' line (choices and text on stdin as JSON); the starters. |
| `try AGENT < draft.json` | M6: Try it. One sentence in AGENT's voice from a no-tools side turn on the draft; refused with the reason. |
| `agents notes TARGET list\|show\|write\|lock\|unlock\|history\|version\|restore\|folder` | Notes (notes.py via agentfs). |
| `endpoint clean\|models\|test\|key` | The endpoint editor. |
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
- Notes: `notesWrite` deny and a per-note lock beat every level through the
  crew tools; a corrupt `.meta.json` locks all notes.
- Collaboration: caller identity from `SO_PEERCRED`, never from the call;
  another agent's words are never the user's approval; targets run at their
  own level in their own per-chat session.
- Agent folders refuse every symlink. The audit log never holds text.
- Search tools (`CONTENT_SEARCH`) are judged by what `rg --files` would read.
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
