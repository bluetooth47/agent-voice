# Agent Voice build plan

Start from the installed orders-guard build at `92c71ff`. First make it possible to save a file without dismissing the desktop. Build the shared controls and stabilize live conversations, then test each new permission and storage operation at the daemon before exposing it on a page. The sequence below ends with one installed candidate for the user's Phase 17 verification sweep. Numbers in this document identify **redesign sessions**. For example, 6b has its own branch, check, and notes. The dated feedback sets the acceptance criteria and the clickable sketch sets the layout.

## Phase 0 — Make the desktop safe to develop on

**Delivers item 4, the early fix in 22, and bug H.** This is an implementation gate. Finish the save/reload test before branch housekeeping or feature work.

1. **Establish what resets.** At an agreed quiet moment, record the running shell version, PID/start time, open panel state and reload messages. The installed `shell/services/PluginRegistry.qml` watches the plugin tree recursively for writes, creation, deletion and moves. It filters some paths, including `.git` and `__pycache__`, but accepts Markdown and editor saves. Its signal reaches `shell.qml::reloadPlugins()`, which unloads panels, services and widgets. Count both process restarts and panel reloads. Reproduce once with a disposable fixture. Use an outside checkout for checks until the gate passes.
2. **Fix the watched-path boundary.** First test a user-owned checkout outside the watched tree, exposed at the original plugin ID by a directory symlink. The adjacent Voxtype plugin has this shape. Trial it with a disposable plugin and a fresh watcher before touching the real checkout. Verify plugin discovery, overlay, popup, installer root, update and removal behavior. For the cutover, preserve the complete checkout, index, untracked files, remotes and modes. In particular preserve the staged planning documents, `voice-commands-notes.md` and the `testresults.md` bug #10 row. Keep a recoverable copy outside the watched tree. If writes through the original plugin path still trigger a reload, the trial failed. Fix the host watcher in a maintained Omarchy checkout/package with a per-plugin explicit-reload option, deploy it and repeat the same test. Keep packaged `/usr/share/omarchy` files pristine and preserve normal discovery/reload for other plugins.
3. **Prove H closed.** Through the original plugin pathname, exercise Markdown, Python, a harmless QML edit, atomic editor save, cache creation/removal, a Git operation and the check suite. Repeat after a deliberate shell restart. Require **zero unexpected panel reloads, zero PID changes and a continuously open settings window** during those operations. Then use an explicit shell restart and verify the QML edit appears. Restore the fixture. Check an unrelated plugin still loads. Record event counts, the selected fix and its reversal. Passing requires the original plugin pathname to survive the test.
4. **Align branches without touching someone else's index.** The 01:05 report placed `dev` 32 and `main` 39 commits behind. A later read-only inspection found local `dev` already at `92c71ff`, with staged documents, cached `fork/dev` still 32 behind, and `main` at `e331d31` tracking `origin/main`. Re-read status, confirm the push URL for **fork** is the user’s bluetooth47/agent-voice repository, fetch **fork**, compare local and remote tips and verify ancestry with `git merge-base --is-ancestor`. Use a clean checkout/worktree for outstanding `--ff-only` operations. Keep any verified descendant tip and its work. Publish the outstanding fast-forwards with explicit refspecs to `fork`, never force. Set local `main` to track `fork/main`, keep `dev` tracking `fork/dev`, and set repo-local `remote.pushDefault=fork`. Compare both local tips with `git ls-remote fork` and inspect tracking. Preserve divergence for resolution if the ancestry check fails.
5. **Retire the finished runner.** Confirm its state says finished. Run `systemctl --user disable --now agentvoice-phase-runner.service`. Verify disabled and inactive, logs/state retained and the actual `agentvoice.service` still in its prior running state. Check for an unwanted completion notification at the next ordinary login. After H passes, capture the §33 latency/prompt baseline on the existing build and current hardware, with the setup recorded for the paired RC run in 16.

**Files and settings.** Expect a local plugin deployment change, Git config/refs and runner enablement. A host-side fix, if needed, has its own revision. No new Agent Voice setting.

**Verification and going back.** Run `./bin/agentvoice-check`, capture the preview popup, restart the shell deliberately for the QML probe, and make one synthetic wake/reply after cutover. The status report recorded 14 green static checks and 2,790 passing tests on the baseline. Preserve the old directory layout and runner enablement for explicit restoration. The historic branch tips remain recoverable by SHA. Write `redesign/phase0notes.md` under the notes directory.

### Working agreement for every session below

- Branch `redesign-0` from the verified orders-guard baseline, then branch `redesign-<N>` from the previous session's reviewed tip. Record exact base and result SHAs even for a deployment-only session with identical tips. Use small commented integration points in **`daemon/wake_listen.py`, `Settings.qml` and `pages/AgentsPage.qml`**. Put policy, storage and rendering in their owning modules. Bare Python module names refer to daemon/ and bare test names to tests/.
- **Every Verify paragraph includes this closeout.** Measure the starting behavior, run **`./bin/agentvoice-check` before every commit** and again on the final tree, resolve both Codex review passes, commit review fixes separately with the project's co-author trailer, and push branches explicitly to **`fork` only**. Install last with `./install.sh --yes` after warning the user that it interrupts a voice turn. If an installed live check reveals a defect, fix, recheck and reinstall before recording the result. Deploy the matching manifest/QML tree from that exact worktree to the original plugin path and retain the previous verified target. The installer copies the daemon payload separately. QML changes require a deliberate **`omarchy restart shell`** to see them live.
- **Screenshots come from `bench/preview/preview.sh`.** For example, use `--size 520x720 --shots 8 --arg '{"page":"agents","agent":"main"}' settings`, then a wide size and `--theme flexoki-light`. Use synthetic state and scratch data, stub side effects, and use `clicks` for write traces. Save evidence under `~/agentvoice-notes/redesign/`. Exercise the installed shell for live acceptance after the preview. No real pointer automation. Use the mockup's order, responsive groups and interactions. Its numbers, paths and engine labels are examples.
- A new setting below lists its **key, default and sole owning page**. Each such entry means **`manifest.json → barWidget.schema + barWidget.defaults`, `daemon/runtime.py → DEFAULTS` plus a validated getter and applicable `TOML_ALIASES`, and an actual owning page control using `s.put("key", …)`**. Test shell.json → TOML → defaults, live reload, corrupt input and prior-state behavior. Use typed bounds with the expected schema min/max/step. Validate structured lists/maps in both directions, including main's internal empty ID ↔ external `main`. Preserve unknown fields when editing. Where the host needs a serialized control value, round-trip the actual schema and `omarchy bar set … --json` before adopting it. Keep `pages/qmldir` and `ui/qmldir` current. Other pages can display a value, deep-link or delegate a shortcut to the same owner. Each declared key must still have exactly one writing page.
- Capture the current key → owner → control inventory in Phase 1 and compare it at every page move. Preserve all existing values and controls, including global defaults, fallbacks, main and extra agents, advanced timings and endpoint fields. Reuse existing keys wherever possible. Proposed names below can change before the owning phase lands. Keep transient view state, generated content and diagnostics out of settings.
- Test pure decisions and the real paths that consume them. For `speech_text.py`, test utterances. For `runtime.Config`, test precedence/reload. For a permission-hook change, test silence, failure, malformed data and exceptions deny. For adapter changes, test the streaming contract, cold stub, permission checks on/off and replay a trace from a real turn before claiming support. Bare CI uses `AGENTVOICE_STRICT=1` with the dev-only Python environment. Full CI uses `AGENTVOICE_NO_SKIPS=1` with the real stack. Run both. Keep microphone and QML behavior checks manual. Use existing fake-device/state fixtures for daemon transitions and qmllint for QML references. Installer changes require `AGENTVOICE_BOX=1 ./bin/agentvoice-check` and verification of the actual installed files in the eight box cases.
- End every session with **`~/agentvoice-notes/redesign/phase<N>notes.md`**. Begin with the date, branch/base/result SHA, fork ref, installed revision, hardware/audio, green check, before/after counts and box result, following the template in `merged-plan.md`. Its sections cover what was built, shared files and locations, measured values/baseline, deviations, findings, unverified cases with reasons, going back, open issues and the live checklist of what was said and happened. Use synthetic content. Put measured performance claims and corrections in `bench/FINDINGS.md`. Record missing hardware, credentials or quota as **not verified**.

## Phase 1 — Shared settings controls

**Goal · 17, foundation for 14 and 22.** Build a responsive card, compact selector, toggle chip, one-line hint with tooltip, warning icon with confirmation, and a draggable card with keyboard Move/Copy actions. Extend `ui/AgentCard.qml`, `SegmentedChoice.qml`, `TabStrip.qml` and the existing shared rows where they fit. Add a collapsed Advanced group and a fixture gallery showing one and two columns. Use `Commons.Color`, plain text, clear focus, accessible names and a visible reason for disabled actions. Cancel is the safe default for destructive actions. Keep setting names out of `ui/`.

**Files and settings.** `ui/`, `ui/qmldir`, `bench/preview/targets/gallery.qml`, `tests/test_settings_pages.py`. No new setting.

**Verify.** Run the common closeout. Preview the gallery narrow/wide, dark/light, keyboard-only and with long labels. Exercise cancel and single-confirm in the preview. Restart the shell for installed QML.

**Risk and going back.** Small screens can hide actions. Check every action fits or scrolls into view. The old build reads the same settings.

## Phase 2 — Open-mic continuity, chimes and status

**Goal · bugs I, J, K.** Reproduce before changing behavior. Run a chat with a synthetic marker, flip Ask → Trusted and back, and follow the same chat through open-mic turns. Correlate backend session, chat and turn identifiers with adapter rebuilds. Preserve authorized history on a compatible resume while dropping old permission grants/processes. Show the reason if a backend has to start fresh. Trace wake/heard/done chimes alongside rejected, empty and accepted captures. Fix the event that gives a misleading cue or resets the chat. On open-mic off, publish that change immediately and distinguish any ordinary follow-up timer from an open mic.

**Files and settings.** `daemon/wake_listen.py` at reconciliation and open-mic transitions, `crew.py`, affected adapters, `chimes.py`, `Panel.qml`/`Hud.qml` for stale state. No new keys.

**Verify.** Extend `test_open_mic.py`, `test_chimes.py`, `test_warm_agent.py` and state/adapter fixtures on demonstrated paths. Preview status transitions, restart the shell for QML, then repeat the spoken sequence and timed stop on the installed build. Record actual cue source, session continuity and off-to-clear ms. If an intermittent report cannot be reproduced, record its matrix and an explicit open disposition for the gate.

**Risk and going back.** A stale privileged process is worse than a cold resume. Old builds retain their transition and display behavior with the same data.

## Phase 3a — Commands in a spoken sentence

**Goal · 1, 22, bug A.** Extend the current exact-match grammar in an addressed chat. Match whole command clauses before punctuation is discarded. Accept a clear leading/trailing command or an explicitly delimited imperative such as “take notes, and keep listening, because I might pause.” Preserve meaningful remaining text for the intended turn once. Stop/cancel ends the interrupted work. Ambiguous multiple commands, quotes, negation, examples, and commands with ordinary objects stay conversational. Where ASR drops punctuation, use tested word boundaries and explicit clause cues. Keep exact commands and the immediate “full stop” emergency path. Acknowledge each command once with a short spoken result when speech is allowed. Keep permission answers in their own card flow.

**Files and settings.** `daemon/speech_text.py`, a small routing change in `wake_listen.py`, `tests/test_speech_text.py`, `test_interrupt.py`, `test_open_mic.py`. No setting.

**Verify.** Table-test aliases, overlapping long/short forms, residual text, and every input context. Say the approved example and “stop listening to that song”, “keep listening to me explain”, “don't start a new chat” and a quoted command. Check effect, acknowledgement count and what reaches the agent. Test lock, dictation, partial transcripts and speech from a model. Measure false triggers over the named negative set.

**Risk and going back.** Treat any unintended action as a blocker. Old builds return to whole-utterance matching.

## Phase 3b — One command reference for people and agents

**Goal · 11, 13, 21.** Give each built-in a command ID, actual phrases/patterns, context, effect and supported CLI equivalent. Generate the Agent Voice skill, compact backend fallback and page data from the matcher definitions. Derive wake phrases from the current enabled roster. Include stop/full stop, goodbye, new/continue, both mic modes, crew pass/takeover and terminal handoff. Check name routing, dictation and yes/no against actual handlers. Distinguish a button-only collaboration answer from a spoken command. Document settings, locations and in-turn limits, particularly handoff ending the running turn.

**Files and settings.** `speech_text.py`, `daemon/omarchy_skill.py`, `agentfs.py`, `adapters/base.py`, `bin/agentvoice`, `README.md`. Reserve the generated `skills/agentvoice/SKILL.md` name. Load it through the existing per-agent plugin builder independently of the Omarchy skill switch. Rebuild on phrase, roster, generator or CLI-contract changes. Use the skill-assignment control in 6c for individual opt-out. No new setting in 3b.

**Verify.** Compare generated inventories and runtime routes, change a wake phrase and check staleness. Ask a supported native-skill agent and a fallback agent how to hand off. Check the preamble-size delta and that a lookup starts no action.

**Risk and going back.** Advice can become stale or appear to confer permission. Older builds can regenerate their prior private plugin cache.

## Phase 4a — Human approval for a crew request

**Goal · prerequisite for 16.** The current collaboration card accepts a response file that another process running as the desktop user can write. Before adding “ask me first” to a link, bind the decision to the human-facing overlay, a live request, its exact payload, and a one-use nonce. Reuse the current daemon socket identity checks where appropriate. Authenticate the connecting overlay process against the live shell and reject agent descendants and legacy file responses for these cards. Keep any unauthenticated or unanswered request denied. Preserve the existing spoken announcement and visible cancel.

**Files and settings.** `daemon/collab.py`, `Settings.qml` permission-card handler, `bin/agentvoice` if a client helper is required. No new setting.

**Verify.** Drive real IPC with synthetic clients for an accepted UI decision, wrong caller, expired request, payload change, double submit, timeout and stop. Preview the pending and denied card, restart the shell and have the user accept one harmless ask and deny another.

**Risk and going back.** Same-user process authentication has limits on an unsandboxed desktop. Document exactly what was verified. Older builds use the old card path, so disable interactions that depend on verified consent before downgrade.

## Phase 4b — Directed crew permissions and their table editor

**Goal · 16.** Implement the policy first, then a keyboard-editable table as its first client. A record names a stable source ID, target ID, allowed subset of ask/delegate/message/pass-chat, and “ask me first”. Missing link or ability means denied. Fresh installs and upgrades start with an empty list. Let the user deliberately add links. Start with an explanation for previously working unlinked pairs. Enforce in the daemon at request, approval, dispatch and delivery, including agent MCP, voice, Send and CLI routes. Preserve actor provenance. Reject queued work if its link or quarantine status changes, cancel affected active work and clear pending disclosures. A pass may grant replay only after the existing informed transfer sequence.

**Files and settings.** `daemon/collab.py`, `crew_mcp.py`, `runtime.py`, small hooks in `wake_listen.py`, `ui/SendSheet.qml`, new `pages/CrewPage.qml`, `Settings.qml` routing. New `crewPolicy` → Crew table and quarantine switches. Its default contains an empty plain `links` list, empty `quarantinedAgents` list and revision zero. Commit both lists together against the last read revision. Reject stale edits. Missing or corrupt policy denies collaboration. Reject partial records and duplicate identities. Quarantine wins regardless of edge cleanup.

Quarantine forbids outbound calls, including reverse paths. Only explicitly allowed inbound ask/delegate may run, with a bounded brief and a fresh isolated context. At the transition, detach old native sessions and block history/replay via direct share/continue, Send, CLI and pending deliveries. Exclude chat-search access that would reintroduce that history. Approvals apply 4a and the stricter of the link and existing agent/target rules. Confirm changes that expand the audience for a chat.

**Verify.** Extend `test_collab.py`, `test_crew.py`, `test_chat_grant.py` and config tests. Matrix both directions × four abilities × absent/invalid/revoked/confirmed × quarantine. Exercise direct calls, a warm MCP client, a queued job, interrupted update, stale confirmation and a previously resumable session. Preview the table and denied Send state, restart the shell, and try one allowed and one denied spoken pass.

**Risk and going back.** An older daemon ignores this policy. Use the restricted downgrade procedure in Security below before starting it.

## Phase 4c — The graphical Crew map

**Goal · 16, 17.** Draw the same directed records as arrows between movable agent boxes. Drag from a port to create a link. Selecting an agent shows incoming/outgoing neighbors. Selecting a line exposes abilities, ask-first, add reverse and confirmed delete. Drag an agent into the red fenced zone to quarantine it, or use its switch. Preview the consequences and confirm changes to the boundary. Remove forbidden abilities. If an edge becomes empty, drop it. Leaving quarantine grants nothing automatically.

**Files and settings.** `pages/CrewPage.qml`, new map/inspector pieces in `ui/`, preview target and `qmldir`. Reuse the 4b writer. Node positions are presentation state only.

**Verify.** Compare serialized policy and actual daemon decisions after editing from map, table, drag-to-quarantine and the switch. Test stale parallel edits, renamed/disabled agents and keyboard focus. Preview 1 and 8 agents in both themes, restart the shell, and repeat create/reverse/delete from the keyboard.

**Risk and going back.** A dropped or invented grant can look plausible on a diagram. The table and 4b daemon still operate without the map. Pre-4b rollback needs the restriction procedure.

## Phase 5a — Agents and the home of existing controls

**Goal · 8, 17, bug E.** Use foldable header strips with name, model, effort, voice and trust. Fit Identity, Model, Voice, Permissions and Tools cards two across when wide. Put effort beside the model, keep project folders and guard levels prominent, retain enabled/speech/progress, wake-model and endpoint-specific controls. Keep collaboration/accepts-work and notes-write available per agent. Remove duplicate footer sections. Relocate the existing global `desktopTools`, `browserTools`, `omarchySkill` inheritance defaults to a working Communal Tools tab in the same change.

**Files and settings.** Main edit to **`pages/AgentsPage.qml`**, plus `CommunalPage.qml`, `ui/AgentCard.qml`, `ToolSwitches.qml`, `EndpointEditor.qml` and the shared navigation/actions in `Settings.qml`. No new keys. Retain inheritance and main/extra storage. Keep a single owner for each existing key while later detail cards invoke the same per-agent action.

**Verify.** Run owner/reset checks and `persist`/`clicks` previews for main, extra, disabled and endpoint agents after a store reload. Compare the before/after key inventory, preview narrow/wide, restart the shell and change effort by keyboard.

**Risk and going back.** An inherited “off” can be mistaken for a missing control. Show both effective value and source. Old pages see the same saved settings.

## Phase 5b — Agent tabs and personality

**Goal · 9, 10.** Replace the agent dropdown with stable-ID tabs, with overflow on small screens. Preserve deep links and the selected subject when agents are renamed. Add tone, length and formality chips that edit a clearly delimited part of `personality.md`. Keep arbitrary free text, templates only for empty fields, one-line hints/tooltips, and meters for role/personality/instructions. “Try it” uses the current draft, actual agent personality and voice in a one-off no-tools sample. It must not alter the current chat.

**Files and settings.** `pages/AgentDetailsPage.qml`, `AgentFolders.qml`, `ui/FileEditor.qml`, `TabStrip.qml`, `daemon/agentfs.py`, sample adapter invocation if needed. Existing file limits 300/1,500/2,000 characters. No new knob.

**Verify.** Test restart-safe edits with an external writer, boundary lengths, and preservation of user prose after chip edits. Preview empty/full tabs, restart the shell, type and undo by keyboard, and hear a synthetic sample from the chosen agent.

**Risk and going back.** Concurrent edits can overwrite prose. Use existing base stamps/history. Old builds read the resulting Markdown.

## Phase 6a — Communal inheritance and shared tools

**Goal · 15.** Add “Who gets communal” and a preview for the selected agent using the actual prompt builder. Show provenance and precedence for rules, defaults and personal instructions. Keep the existing rules/defaults editors and expose saved history, a diff and stale-aware Undo directly beside each editor. Apply opt-out consistently to communal rules/defaults, skills, notes through the tools, and inherited communal tool grants. Saved-chat access still comes from its own explicit grants. Render the effective result, including unsupported, on both agent and Communal views. A global tool toggle supplies a default for all eligible agents. A personal deny wins.

**Files and settings.** `pages/CommunalPage.qml`, `ui/PromptPreview.qml`, `daemon/agentfs.py`, `runtime.py`, `crew_mcp.py`, `adapters/base.py`, warm adapter reconciliation in `wake_listen.py`. New `communalOptOut=[]` → per-agent inclusion switches on Communal. Existing installs keep their current communal content. Reject unknown identities and malformed access configuration at the tool boundary.

**Verify.** Test inclusion/exclusion for native skills, fallback prompt, notes read/list/write and inherited tool launch. Compare preview with what each adapter actually receives. Preview both agents, restart the shell, and change inclusion during a warm session.

**Risk and going back.** Stale prompts or plugins can keep shared material. Remove stale capabilities, detach resumable sessions containing the old communal material and verify a fresh turn uses only the newly authorized context. Previously delivered text cannot be recalled. An older build reapplies communal content. Use the restricted downgrade procedure.

## Phase 6b — Discover tools and authorize them per agent

**Goal · 11, 15, tool half of bug G.** Inventory installed MCP definitions, registered plugins and recognizable CLIs using bounded, read-only metadata scans. Show source, executable identity, availability, supported backend and failure reason. Keep the built-in desktop, browser, Omarchy and crew controls. Every usable row gets a real switch. For a tool lacking a safe integration, show what is missing. Implement the MCP, CLI and plugin integration paths with validated arguments and bounded results. Put a daemon broker or equivalent guarded adapter in the invocation path. Require a warning and confirmation showing source, capabilities and audience for new or shared grants. Discovered tools start off. Offer a communal default and a personal on/off/inherit choice.

**Files and settings.** New discovery module under `daemon/`, `agentfs.catalog`, `runtime.py`, supported `adapters/`, `permission_hook.py`, `pages/AgentDetailsPage.qml` and `CommunalPage.qml`. `agentToolGrants={}` → Agent details, `communalToolGrants={}` → Communal. Both maps start empty. Reuse existing built-in settings and their single writer from 5a. Validate a stable tool identity and reviewed definition fingerprint. A changed definition needs approval again.

**Verify.** Test passive discovery with inert fixtures, first sight off, changed executable/config, unsupported backend, explicit deny vs shared enable, two agents, loss of config and revocation during a turn. Test the hook's failure modes and a working MCP, CLI and plugin integration using innocuous operations and their actual outputs. Record any unsupported integration individually with its missing capability. Preview `tools` and Communal, restart the shell and call one tool before/after its switch. Measure scan time, file count and cold-start delta.

**Risk and going back.** A discovered server or CLI can run code as the user. Start only a granted integration with the right scope. Retire its warm processes on revocation or rollback and rebuild private generated configs. Old builds offer their existing tools.

## Phase 6c — Discover and assign skills

**Goal · 11, 15, skill half of bug G.** Enumerate Agent Voice agent folders, Communal and locally installed skill roots for the supported backends, including Claude Code. Show source, details, effective status, shadowed names and errors on expandable cards. Add an **Unused** lane for unassigned external and managed skills. Distinguish native skill loading, a text index and unsupported operations using the actual capability matrix. Every usable skill can be enabled/disabled for the selected agent, including an inherited skill. Keep provider-managed originals read-only. Assignment from an external root imports a verified copy.

**Files and settings.** `daemon/agentfs.py`, discovery module from 6b, `paths.py`, `runtime.py`, `pages/AgentDetailsPage.qml`, `CommunalPage.qml`, `AgentFolders.qml`, generated plugin/preamble path. New `skillOverrides={}` → Agent details. Absence preserves previously assigned managed skills. Discovered external skills stay unused until assigned.

**Verify.** Extend `test_tools_skills.py` and preamble/adapter fixtures for duplicates, reserved names, opt-out, bad trees, changed files and warm refresh. Preview disabled/Unused/native/index-only cards, restart the shell, and ask each available backend which assigned skill it can see.

**Risk and going back.** A regenerated old plugin may reload a disabled skill. Use the restricted downgrade procedure, including safe physical skill placement.

## Phase 6d — Move and copy skills

**Goal · 11, 15.** Drag between agent, Communal and Unused lanes. Drag moves a managed skill folder, Ctrl-drag copies, and keyboard actions do both. Preview destination and newly exposed audience before sharing. Show an Undo action tied to the exact revision. Implement a single user-initiated operation in the storage layer that also handles multi-file skills. Revalidate source/destination under lock, stage completely, publish once, and recover after interruption before exposing either scope to adapters. An external skill is imported as described in 6c.

**Files and settings.** `daemon/agentfs.py` and a transfer helper, `bin/agentvoice`, `AgentFolders.qml`, shared draggable card, Details and Communal pages. No setting.

**Verify.** Test conflict, same-name shadowing, link substitution, oversize folder, disk-full, interrupted move, simultaneous edit and stale Undo. Compare resulting byte sets and effective skill lists for both agents. Preview drag/Ctrl-copy, restart the shell and complete the move/copy/undo by keyboard too.

**Risk and going back.** Revoke access at the source on move and update both plugin caches. Old builds see complete managed folders at their committed locations. Finish recovery or undo and retire private caches before downgrade.

## Phase 6e — Note categories

**Goal · 12, 15.** Reuse existing `notes/<slug>.md` files as categories. Existing notes are individually visible by name immediately. Use a friendly topic label and the same card lanes, move/copy/undo and audience confirmation as skills. Carry author, taint, revision, lock and permitted history with each category. Keep editing, version view/restore and outside-change detection.

**Files and settings.** `daemon/notes.py`, `agentfs.py`, `crew_mcp.py`, `AgentFolders.qml`, `ui/NotesPanel.qml`, Details/Communal pages. No new setting or bulk rewrite.

**Verify.** Test malformed meta, locked notes, `notesWrite=deny`, revision conflicts, author/taint preservation, crash/retry, collisions and undo. Compare audiences before/after using the agent tools. Preview the category cards, restart the shell, and find and restore a synthetic version.

**Risk and going back.** A move can disclose a note's historic versions alongside its current text. Include version history in the audience confirmation. Old builds read the same Markdown, metadata and versions. Finish pending transfers before downgrade.

## Phase 6f — Import shared rules and skills

**Goal · 15.** Let the user import communal rules and skills from a folder. Show the exact incoming files, diff, affected agents and name conflicts before committing the batch. Keep export and the Chats tab. Recognize the supported export layout and import only the selected, validated rules and skill trees. Use 6d's storage transaction and 6a's history for an all-or-nothing commit and Undo.

**Files and settings.** `daemon/agentfs.py`, `AgentFolders.qml`, `pages/CommunalPage.qml`, `ui/FileEditor.qml`. No new setting.

**Verify.** Round-trip a synthetic export, inject an interrupted import and compare both scopes and histories. Test symlink rejection, unresolved conflicts, cancel and stale Undo. Preview the diff, restart the shell and confirm a selected import changes only the agreed files.

**Risk and going back.** Import can change instructions for every participating agent. Keep an export and use the reviewed revisions to revert. Older builds can read the resulting managed files.

## Phase 7a — Chat titles, summaries and user search

**Goal · 6, data for 7, 15 and 20.** Extend `ChatStore`, which already supports rename, index, replay grants and a text search for continuation. Add a local, bounded topic-title and summary generator, using subject words and representative sentences from the exchange. Use no network by default. Preserve a user's chosen title across regeneration. Show participants, date, turn count and duration when known. Add a common search API for words and agent/date filters. Index old chats lazily or rebuild in bounded batches. Keep canonical chat files readable if an index write fails.

**Files and settings.** `daemon/chats.py`, `paths.py`, `bin/agentvoice`, `tests/test_chats.py`. Existing `saveChats`, `chatRetention` and `keepHistory`. No new setting. Treat derived titles, snippets and indexes as private chat content. Build only for retained saved chats and remove derived rows on delete, expiry and bulk purge.

**Verify.** Use legacy, renamed, multi-speaker, corrupt, interrupted and saving-off fixtures. Judge titles/summaries on synthetic conversations with identical openings and different subjects. Benchmark index size and query latency at named chat/turn counts.

**Risk and going back.** Privacy loss or a broken index can outlive the source. Use 0700/0600 permissions and atomic, rebuildable derived data. Old builds can still open and rename the canonical chats. Rebuild derived metadata after an old-version edit.

## Phase 7b — Chat search as an agent tool

**Goal · 6, 11.** Register a bounded, read-only chat search with the catalog and crew MCP on backends that can enforce it. The user grants it through 6b. The daemon binds the caller to the running turn and authorizes each canonical chat with `may_replay` **before** matching, counting, ranking or quoting it. Owner or explicit `shared_with` permits replay. A participant, an old per-speaker session, a crew edge and `may_continue` can each exist without that grant. Recheck before emitting results or opening a hit. Return attributed excerpts as untrusted information.

**Files and settings.** `chats.py`, `crew_mcp.py`, `collab.py` caller identity, `permission_hook.py`, catalog, `test_chat_grant.py`. Register a new tool ID with 6b's empty-default grants. No new key.

**Verify.** Use the same rare word in permitted, private, unshared and expired chats. Check titles, counts, snippets and IDs, including revocation mid-query, quarantine, session-only records, unknown caller and save-off behavior. Run an allowed and denied live query as two agents. Inspect process arguments and both output streams with synthetic canaries.

**Risk and going back.** An index row cannot authorize a disclosure. Old builds have no agent search tool. Stop new MCP children and discard private derived caches during downgrade.

## Phase 7c — Chats sidebar and conversation reader

**Goal · 5, 6, 15 and chat privacy in 20.** Add **Chats** to the sidebar, remove the title-row Conversations button, keep **Conversation** for listening/timing preferences. Use one chat reader from the sidebar, Agent details, Communal and Overview deep links. Agent details filters to that agent and Communal opens shared chats. Keep current-session history and existing continue, new, rename, pin, export, share/unshare and send actions. Search by terms, participant and before/after dates. Show title, summary, agent, date and length. Put the user's bubbles right, agent's left, with themed shading, visible speaker attribution and folded tool events.

**Files and settings.** `Chats.qml`, `ui/ExchangeItem.qml`, new `pages/ChatsPage.qml`, `Settings.qml` navigation, Details/Communal/`DisplayPage.qml`. Move sole writers for `saveChats`, `chatRetention` and `keepHistory` to Chats. Show storage path and measured usage. Delete all requires warning, exact scope and confirm. Delete canonical and derived data and prevent an in-flight save from recreating deleted history. No new key.

**Verify.** Extend purge and navigation/owner contracts. Preview `shared` and Chats in empty/long/renamed-agent states, restart the shell and walk search → open → continue and cancelled deletion by keyboard.

**Risk and going back.** Use stable IDs and preserve owner/share semantics. Old builds use their former reader and privacy controls. Confirmed deletions remain deleted.

## Phase 8a — Agent details, Advanced inspection

**Goal · 14.** Show the actual assembled prompt in send order, with provenance and effective communal choices. Preview full content locally on deliberate reveal. Show the actual launch argument structure with secrets redacted, working directory, timeout, current session ID, resume support, retained turns, connected MCP/tools and running/failed/off status. Distinguish capability from observed status. Add agent-filtered recent logs with a link to the full local log and recent allow/ask/deny decisions. Use typed structural fields and honor lock/privacy when the overlay closes.

**Files and settings.** `daemon/agentfs.py`, `adapters/base.py` and relevant adapters, `audit.py`, `bin/agentvoice`, `pages/AgentDetailsPage.qml`, `ui/PromptPreview.qml`. No new setting.

**Verify.** Compare preview against real synthetic adapter input/argv, including endpoint/native/index-only variants. Test attribution for two agents on the same backend, redaction and unavailable states. Preview Advanced, restart the shell and compare one live turn to its reported command, status and permission decision.

**Risk and going back.** A launch or error line can carry a token or prompt. Allowlist fields, sanitize terminal output and use PlainText. Old builds ignore the additional structural fields.

## Phase 8b — Advanced controls and agent management

**Goal · 14.** Add an editor for extra flags/environment, supported per-agent turn timeout, and controls for working directory and session/history options where supported. Reuse existing project/endpoint settings and delegate their edits to the owner. Show unsupported fields with reasons. Confirm extra launch options, start fresh, reset and deletion. Preserve export, duplicate, remove and restore. Duplicate with a new stable ID and safe tool/crew grants, excluding secrets, sessions and replay rights. Reset shows exactly what will be reset and offers a restorable snapshot. Start fresh ends only the selected session.

**Files and settings.** `runtime.py`, `daemon/adapters/`, `agentfs.py`, `wake_listen.py` session boundary, `pages/AgentDetailsPage.qml`, `AgentFolders.qml`. New `agentLaunchOptions={}` → Advanced, typed per-ID overrides for allowed flags, nonsecret environment values, timeout and supported resume/history overrides. Empty inherits existing behavior. Use structured arguments, a backend-specific allowlist, validated paths and a secret store/reference if credentials are needed. Reject hook/MCP/sandbox/exec/loader overrides even after confirmation.

**Verify.** Test safe and rejected options, cold/warm adapter launches, cancellation, correctly scoped reset, duplicate without grants and stable existing IDs. Preview each warning, cancel then confirm once, restart the shell and run one synthetic turn with a safe option.

**Risk and going back.** An old build ignores new overrides and could resume older sessions. Stop new processes, restore reviewed legacy-compatible settings, and invalidate any session that should remain fresh before restarting it. Managed folder exports stay readable.

## Phase 9a — Wake decisions that match the controls

**Goal · 18.** First fix the vocabulary. Today a Sherpa hit wakes immediately. On an eligible missed burst, the fallback can ask Vosk and Whisper to agree. Today's `crossCheckEngines=both` describes the votes inside that fallback. It does not require the spotter and a second stage to agree on every wake. Preserve that path for existing configurations. Add explicit “first only”, “either stage” and “both stages agree” modes. Define candidate windows and same-agent agreement. A strict second stage with an unavailable verifier visibly refuses the configuration or holds wakes closed. Preserve the independent emergency-stop path.

**Files and settings.** `daemon/crosscheck.py`, `wake_listen.py` at `Pipeline.feed_wake/apply`, `runtime.py`, `pages/ListeningPage.qml`. New `wakeDecisionMode="legacy"` → Listening decision selector with an accurate description of legacy behavior. Retain `engine`, `wakeCrossCheck`, `crossCheckEngines` and thresholds. Unsupported engine combinations have a reason.

**Verify.** Extend `test_crosscheck.py`, `test_sherpa_wake.py`, `test_wake_reconcile.py`. Cover first hit/second miss, first miss rescued, disagreement, out-of-window vote and unavailable engines. Record true accepts, distractor accepts, rejects, time and CPU on the same clip set. Preview the selector, restart the shell, and verify selected modes with `agentvoice monitor` and spoken names/distractors.

**Risk and going back.** Old builds restore legacy semantics even if a stricter mode was selected. Make that loss explicit before returning the mic to use.

## Phase 9b — Listening pipeline and adaptive gate

**Goal · 18, 17.** Lay out microphone → first listener → second check → decision. Show applicable levels and engine-specific controls inside each stage. Place openWakeWord training/verifier with that engine, Sherpa/Vosk options with theirs. Keep device/level meter, phrase navigation to its existing owner, wake tests, fixed gate, margin, cross-check windows/trailing words/hints and engine setup. Collapse fine-tuning. Add adjustment for how quickly the room noise floor rises and falls, live.

**Files and settings.** `pages/ListeningPage.qml`, `daemon/noise_floor.py`, `wake_listen.py` at gate reconciliation. New `gateRiseTenths=5` and `gateFallTenths=30` → Listening Advanced, displayed as 0.5 and 3.0 dB/s, the current rates. Give the integer controls bounds/steps. Change attributes in place. Reconcile model constructor inputs as specs, check artifact mtimes independently of settings changes, and release replaced models with `Pipeline._release()`.

**Verify.** Drive synthetic noise steps and measure dB change per second, fixed-gate fallback, warm-up, clamps and absence of model rebuilds on slider changes. Preview every supported engine and its unavailable state, restart the shell, and observe the live gate while changing rates. Verify lock drops frames before the meter.

**Risk and going back.** An adapting gate must never learn speech or its own chime. Old builds use their fixed adaptation rates and prior controls.

## Phase 10a — Counts, timings and cutoff events

**Goal · data for 7, 13, 18 and bug C.** Produce structural events at wake decision, completed transcription, first audible reply and turn completion/length cutoff. Correlate with an opaque turn ID and stable agent ID. Define wake-to-reply as accepted wake → first audible reply, and transcription time as STT start → final text. Count a turn once, identify typed/follow-up turns separately and exclude them from wake-latency averages. Label second-check rejections as such. They provide a measurable proxy for false wakes. Keep daily/weekly agent totals and hourly wake buckets in local bounded aggregates. Track uptime from service start and RSS from the daemon process. Maintain a last-chat link only for a real accessible saved ID.

**Files and settings.** Small event hooks in `wake_listen.py`, new `daemon/stats.py`, `runtime.py` state, `paths.py`, `chats.py`, and a read-only decision count on `pages/ListeningPage.qml`. No setting. Store counts, durations and IDs only. Saving off creates no transcript, summary or searchable chat.

**Verify.** Compare deterministic fixtures with an independent count from structural journal events. Test simultaneous agents, duplicates, clock boundaries, daemon restart, no samples, and retention/deleted chats. Measure storage and event cost. Preview the decision count, restart the shell for QML, and run synthetic voice turns with speech logging off.

**Risk and going back.** Unmatched IDs can give plausible but wrong averages. Publish sample counts and missing values. Old builds ignore separate aggregates.

## Phase 10b — Conversation controls and long turns

**Goal · 13, bug C.** Keep compact Patient/Balanced/Snappy/Custom pace at the top. Group follow-ups, live open-mic on/off with time left and action, progress while working, and talking over the agent. Draw lead-in → speech → end pause → reply. Label the lead-in, maximum speech duration and end pause with their effective times, including the 90-second maximum when configured. Show a real limit-hit notice with a focused link to the maximum. Put detailed timing, shortest turn, echo/deaf period, interruption sensitivity and other sliders under collapsed Advanced. Include the command list from 3b. Distinguish turning off open mic from stopping a reply or disabling the service.

**Files and settings.** `pages/ConversationPage.qml`, `Settings.qml` deep link, daemon state from 2/10a. Reuse existing timing, mic, barge and narration keys. Keep the user's `maxUtteranceMs="90000"` effective. The shipped fallback remains 30,000 ms unless explicitly changed.

**Verify.** Test numeric/string boundaries and exact-once cutoff notification via daemon fixtures. Preview preset/custom, off/on/countdown and limit-hit pages, restart the shell, then run a synthetic **90-second** capped turn and a shorter natural turn. Check the count, deep link and actual new limit after adjustment.

**Risk and going back.** A view refresh must not reset a user's timing. Older builds retain the value and their old maximum-turn behavior without the alert.

## Phase 11 — Voice library and transcription

**Goal · 19, bug F.** Keep the speech/chime quick switches. Show each agent's voice, speed, Test and direct link to the right Agents card. Open the library on **Downloaded**. Combine search with one compact filter for availability, accent and voice traits. Reserve a leading trash slot even on undeletable rows. Align names and Test buttons, and list every agent using a voice. Preserve use-for, fetch, retry, sample, remove and in-use protection. Put “Hearing you”, the supported transcription model choices, their local resource/download status and live transcription in collapsed Advanced. Explain in one line that transcription turns speech into text on this machine before sending a request to an agent.

**Files and settings.** `pages/VoicePage.qml`, `ui/VoiceLibraryRow.qml`, `Settings.qml::assignVoice`, `daemon/voices.py`, `models.lock` if the downloadable catalog grows. Reuse `model` (STT), `livePartials`, `speakReplies` and `chimes`. The library filter is view state.

**Verify.** Extend catalog/pinning and voice-assignment checks if the catalog changes. Verify the relevant model loader accepts every offered choice. Preview mixed installed/missing/shared rows and compare name/Test coordinates, restart the shell and hear a sample, then transcribe with the selected model.

**Risk and going back.** Offer only supported artifacts. Preserve local voice assignments and protect in-use files. Reset an STT model unknown to an older build to its prior supported value before downgrade.

## Phase 12a — Other settings, keys and maintenance

**Goal · 20, 21.** Rename Display & privacy to **Other settings** with an alias for old deep links. Keep readout visibility/linger, Omarchy Agents-panel integration and step-aside for other recorders. Refer to chat storage controls on Chats. Flag enabling journal speech logging, explain its retention and require confirmation. State that the mic closes on screen lock. Expose actual keybindings with a link to their editable source. Move repair/remove here from About. Warn about effects, confirm once and preserve existing backup/recovery behavior.

**Files and settings.** `pages/DisplayPage.qml` (or renamed file plus route alias), `AboutPage.qml`, `Settings.qml`, sidebar and `pages/qmldir`. Existing keys only.

**Verify.** Use `clicks` with stubbed repair/remove/logging to check cancel writes nothing and confirm issues one action. Preview the new page, restart the shell and keyboard-walk the real links without running removal on the live desktop. Box-test a changed installer.

**Risk and going back.** A stale route or duplicate writer can strand a setting. Check every old link and key. Old builds still expose maintenance on About.

## Phase 12b — Stable popup and readout

**Goal · 2, 3, 20, bugs B and D.** Remove only the popup's global “what Claude Code may do” editor. Keep agent chips, mic, stop, settings, live state and genuine pending permission prompts. Reserve the last-heard row across turns. Locked geometry fixes popup/HUD size and anchor. Dynamic allows intentional content growth with a stable last-heard slot. In both, support the dim previous answer above the current partial transcript, with keyboard-accessible overflow. Preserve live-readout timing and immediately clear both texts on lock, agent/chat switch or expiry. Provide a synthetic Show preview.

**Files and settings.** `Panel.qml`, `Hud.qml`, Other settings page, `Settings.qml` and small state-publish hook in `wake_listen.py` if a separate last-reply field is needed. New `readoutSizeMode="locked"`, `keepLastReply=true`, `readoutPosition="bar"` (today's bar-relative anchor, with top/bottom choices), and `readoutSize="medium"` (a preset bounded by the display). Sole controls on Other settings. Apply position to the free-standing HUD and keep the popup anchored to its bar icon. Set bounds for small screens and scaling.

**Verify.** Extend lock/state fixtures. Preview identical synthetic idle/capture/transcribing/reply transitions with `popup` and a HUD fixture. Record width, height and anchor across turns. Require zero geometry change in Locked and no last-heard flicker in either mode. Restart the shell, speak two turns, lock mid-partial and check immediate clearing. Exercise the status report's separate #10 case, muted mic plus typed-terminal reply, and record it independently if still open.

**Risk and going back.** Layer-shell can draw over the lock screen. Old versions restore their original dynamic single readout and popup editor.

## Phase 13a — About and diagnostics

**Goal · 21, 22.** Show installed version, commit, branch-at-install or detached label and install time. Compare daemon stamp/banner with live plugin metadata and report a mismatch. Show what runs locally (wake/STT/Piper), what sends requests to a backend, and actual availability/connection evidence for Claude Code, Codex, other supported CLIs, Ollama/llama.cpp or configured endpoints. Show unknown or unavailable when a probe cannot establish connectivity. Use the full 3b reference, including configured wake phrases and a one-line effect. Add copy diagnostics, an explicit check for updates against the selected fork, short changelog, license and README.

**Files and settings.** `pages/AboutPage.qml`, `Settings.qml`, `daemon/endpoints.py`, `bin/agentvoice`, `install.sh` for install provenance as needed, `README.md` and `LICENSE` links. No new knob. Diagnostics use an allowlist of build, nonsecret settings and structural error codes. Exclude transcripts, prompts, search terms, file contents, environment secrets and endpoint credentials. Render external text plainly.

**Verify.** Test detached/offline/unauthenticated, daemon–plugin mismatch, and synthetic secrets in both log streams. Box-test installer changes and verify the stamp on disk. Preview About, restart the shell and inspect the actual copied payload, command lookup and a user-triggered update result.

**Risk and going back.** Never claim a backend connected from its executable's presence. Keep the prior version line parseable and show an unknown branch for older installs.

## Phase 13b — Find a setting and set up a fresh install

**Goal · 22, 17.** Add settings search by familiar words and key, with results that open the correct agent/page/tab, expand Advanced and focus the control. Retain sidebar and keyboard shortcuts as the page count grows. Guide a new user through mic/level, wake test and first agent, with skip, resume and a manual restart of setup. Reuse canonical page actions. Preserve configured installs and launch each test from its corresponding setup step.

**Files and settings.** `Settings.qml` navigation only, `ui/SidebarNav.qml`, new search/setup components and labeled page anchors. Store a local, versioned walkthrough completion marker outside the plugin as UI state. Skipping optional setup changes no daemon setting.

**Verify.** Test the search index against page/key ownership and legacy deep links, including synonyms such as “pause”. Preview fresh and configured states. Restart the shell and complete keyboard-only and light-theme walks from both narrow and wide windows. Check screen-reader names, traversal and focus after returning.

**Risk and going back.** Onboarding must not overwrite a working agent or reappear every login. Older builds ignore the marker.

## Phase 14 — Overview with verifiable numbers

**Goal · 7.** Keep active agents, service controls, mic gain/level and mute. The current Overview exposes a meter and gate adjustment link. Match the sketch's actual input gain with a bounded control for the selected PipeWire source, showing its current units and unavailable state. Keep wake threshold separately labeled on Listening. Show per-agent turns today/this week, mean wake-to-first-audible-reply and mean transcription time with sample counts, accepted wakes/second-stage rejects, hourly wake chart, service uptime and RSS. Link each agent's last accessible saved chat. Show no-data states when appropriate.

**Files and settings.** `pages/OverviewPage.qml`, stats from 10a, `Settings.qml` for links, `bin/agentvoice`/device helper for actual source gain. No new Agent Voice setting. Gain belongs to the audio device.

**Verify.** Compare rendered figures to known fixture totals and structural journal, process uptime and RSS. Preview idle, no history, multi-agent and full day/week, restart the shell and follow two last-chat links. Verify a gain change affects the intended input, then restore it.

**Risk and going back.** A different device or silent turn must not distort measurements. Older builds show the original Overview. System input gain persists independently.

## Phase 15 — Background completion without another wake

**Goal · 24.** Start from `collab.Runtime` reports currently held for the next turn. Add a trusted completion event for crew work and for supported adapter sub-agents and long commands. Correlate the job, owner, turn and final status. For a backend without a reliable event, use a supervised completion from a job Agent Voice actually started, or report the limitation. Treat model-written “done” and arbitrary process output as text. Give each valid event a short attributed spoken line and a desktop notification. The daemon schedules delivery without starting microphone capture or requiring the next user turn.

**Files and settings.** `daemon/collab.py`, `adapters/base.py` and adapters with verified events, a small completion queue, `wake_listen.py` speech arbitration, `pages/AgentsPage.qml`. New `agentCompletionNotices={}` → per-agent switch on Agents. Proposed default is enabled for an existing enabled agent. Explicit off suppresses both surfaces. Queue behind the user and other agents. If locked, muted or in DND, issue a neutral notification only through the normal desktop notification policy. Consume the speech event without replaying it after unlock. Stop stale audio on lock. Serialize, deduplicate and expire events. Never put the spoken line in a notification process's argv.

**Verify.** Test duplicate/replayed/cancelled completions, fake sender, wrong session, two agents, settings changes while queued, lock/mute/DND during playback, and loss of the notification service. Preview the switch and busy states, restart the shell, then finish a harmless background command and a sub-agent task without speaking again. Record finish-to-notification and finish-to-speech latency. Repeat while the user is talking and under suppression.

**Risk and going back.** Repeated or private speech is a release blocker. An older daemon returns to next-turn reports. Drain/cancel transient announcements at rollback to avoid duplicates.

## Phase 16 — Install one candidate and hand off to Phase 17

**Goal · all items and A–K.** Integration and entry evidence only. Review `project-status-2026-11-21.md` again. Copy the mapping below into the RC notes and add delivered SHAs or a reason and owner for every deferral. H must have passed. Carry forward outstanding live checks from Phases 12–16 of the earlier plan, including spoken passes/stop, live permission cards, Codex quota, Gemini/endpoint targets, full-shell keyboard use and muted-terminal #10. Keep approved scope visible in the handoff.

**Files and settings.** Candidate ref on `fork`, existing install/bench scripts, `~/agentvoice-notes/redesign/phase16notes.md` and evidence. No new feature or setting. Consolidate the reviewed branches into a single named RC descending from `redesign-0`. Keep release and publication decisions for after the sweep. Use a clean detached worktree at the exact SHA. Install its daemon payload, deploy its corresponding plugin files, restart the shell for QML, and compare installed `daemon/`, `bin/`, `desktop/`, `install.sh`, `requirements*.txt` and `models.lock` against the archived commit allowing only documented generated files. Compare manifest/QML hashes separately. Record the version stamp, service start/banner, shell load and dirty status. A matching version label alone is insufficient.

**Verify the entry gate.** Run the common green check and both CI environments. Review the phase preview gallery, then perform a synthetic installed wake/reply/stop. Rerun the **Phase 8 latency baseline on today's hardware** using the protocol and caveats in `bench/FINDINGS.md` §33, `bench/start_bench.py`, `bench/turn_latency.py` and `bench/preamble_size.py`. Pair the baseline and candidate on equivalent hardware, audio device, agents, settings, sample count and warm/cold conditions. Use a baseline build on disposable state for comparison. Record raw counts, median/p95, hardware/load, prompt bytes/characters, process count and RSS. Separate controlled samples from observational journal timings.

Hand the user the exact installed SHA, baseline, tested downgrade steps, item ledger, known limitations, and fixtures for **V-01 through V-23** in `~/agentvoice-notes/phase-17-plan.md`. Include a completion scenario for item 24 under V-08/V-12. The user's sweep builds nothing. It uses throwaway projects, synthetic prompts, a test browser profile and `logSpeech` off, marks each backend/device live, fixture-only or not verified, and records severity, reproduction and follow-up in `phase17notes.md`. Include the 19-task UX walk, privacy checks, performance comparisons and release-blocker decisions.

**Risk and going back.** Mixed daemon/UI revisions invalidate the sweep. Restore both from the same verified safe build and repeat the identity checks.

## Security review points

| Boundary | Enforce at runtime | Evidence required |
|---|---|---|
| Detected tools | Discovery reads bounded manifests and executable identities without running them. Grant an exact integration per stable agent, constrained by backend capability, existing permission level and personal deny. Recheck on invocation and on return for content-bearing searches. Close or replace warm servers when a grant changes. | An unknown tool, changed definition, unsupported backend, revoked grant and malformed configuration all deny. Compare two agents' actual tool lists and invocations. |
| Chat search | Bind caller identity on the daemon side. Use the canonical owner/explicit replay grant before reading searchable content. Limit results and bytes. Suppress even hit counts for inaccessible chats. Treat excerpts as data. Saving, retention, purge and quarantine apply to all derived stores and ongoing requests. | Same query as owner, grantee, former grantee, participant with session only and quarantined caller. Place a canary in a forbidden chat and check every response/output channel. |
| Skills, notes and import | Resolve stable, allowed roots and logical IDs. Reject path traversal, symlinks including dangling ones, special files, collisions and oversized trees. Recheck both ends while holding storage locks. Use current skill bounds (64 files, 2 MiB, 20,000-character SKILL.md), history and revision checks. Private ↔ Communal changes require a deliberate human action showing the audience. Agents retain only their scoped note operations. Preserve notes-write deny, note locks, taint and fail-closed corrupt metadata. | Attempt move/copy/import/undo across two synthetic scopes, with denied access, stale revision, failed staging or restart. Verify content, metadata and effective visibility from each agent after each outcome. External skill sources remain intact. |
| Crew map and quarantine | The table and drawing edit the same list. Enforce authenticated source → target → ability over the existing `SO_PEERCRED` call socket and validate the caller belongs to the live turn. Intersect links with target enablement, accepts-work, caller collaboration level, target posture, depth 3, cycle/rate/task limits and lock/stop. Ask-first binds the exact payload and revision. A quarantine boundary can only reduce ability. Isolate inbound brief-only tasks from chat replay, native resumes, pending asides and outgoing calls. | Test at lookup, acceptance, queue dispatch, result delivery and direct CLI/MCP invocation. Cancel or withhold stale work. Link removal blocks future use. Unquarantine/reverse creates no grant without an explicit edit. Check the map, table and saved list against a real tool call. |
| Launch, speech and diagnostics | Preserve the orders guard at Trusted. Hook entry uses a quoted command, catches exceptions and issues an explicit decision on every exit, with `onFailure: block`. No home-directory fallback for Edits. Resolve paths non-strictly, retain `NEVER_SILENT` and evaluate what searches can return. Send speech, search terms, folder text, briefs and notifications via stdin, private 0600 files, local IPC or an approved endpoint body. Use `safe_for_terminal`, `as_prompt` where applicable to non-speech arguments, validated fixed commands and the existing launcher quoting. All untrusted UI text, including titles, hints and notifications, displays literally. | Inspect real synthetic process arguments, both stdout/stderr and `journalctl --user -u agentvoice -o json` with `logSpeech` off. Mutation-test each new guard. Preserve content-free audit and structural timings. Keep models pinned/verified with `models.lock`. Leave dependency-range policy as documented in CLAUDE.md. |
| Mic lock and shared actions | Preserve independent user-enabled and session-locked flags. Drop frames before measurement, abandon in-flight capture, hide HUD immediately, silence completion speech and keep prior user mute on unlock. Preserve existing lock detection/poll and last-known state on an undetermined result. All switch, bar, key, voice and CLI routes reach the same applicable guard. Distinguish stopping the daemon, muting the microphone and stopping a turn. | Lock while listening, capturing, sharing, speaking and showing a partial. Unlock with the mic previously muted. Under lock a completion may produce a content-free desktop notification. A failed action gives a reason which clears when its cause clears. |

**Restricted downgrade procedure.** Exercise this on copies before changing the installed build. Stop the daemon, cancel chains/children, drain announcements, and make a private, versioned backup of settings, agent/communal folders, chats, grants and derived caches. Finish or roll back storage transactions. Materialize disabled/opted-out skills and communal material outside any root the old build loads, and rebuild its caches. Set old-readable main/extra collaboration and tool switches off for affected agents. Check voice, Send, CLI, native sessions and MCP directly under the old binaries. If old code cannot express quarantine, communal isolation or an ask-first restriction, keep that service/agent stopped on the old build. Restore the saved policy only with a daemon that enforces it. Directory modes and rollback copies matter as much as the version stamp.

These controls govern Agent Voice's daemon, tools and managed adapters. Trusted or hookless programs running as the desktop user can have direct filesystem access. Preserve outside-edit detection, Keep/Revert, the orders guard where supported and honest capability labels. The previously deferred general sandbox remains a separate project.

## Feedback and bug mapping

The entries are planned deliveries. For the RC, record actual evidence and any explicitly reasoned deferral in the phase notes before the sweep starts.

| Feedback | Delivering phase(s) | User-visible acceptance |
|---|---|---|
| 1 | 3a | A command in a clear spoken clause runs once and is acknowledged. |
| 2 | 12b | Global Claude permission editor removed from popup. |
| 3 | 12b | Last-heard row stays in place across turns. |
| 4 | 0 | Ordinary saves through the plugin path cause zero unintended reloads. |
| 5 | 7c | Chats has a sidebar home. Conversation remains settings. Agent details still opens past chats. |
| 6 | 7a–7c | Topic titles, summaries, agent/date/length, scoped search for humans and agents, themed conversation bubbles. |
| 7 | 10a, 14 | Per-agent today/week, timings, accepted/rejected wakes, uptime, RSS, last-chat links and mic controls. |
| 8 | 5a | Compact identity/model/effort, responsive cards, preserved controls and inheritance, deduplicated footer. |
| 9 | 5b | One Agent details tab per agent. |
| 10 | 5b | Traits, free text, templates, hints, meters and audible Try it. |
| 11 | 3b, 5a, 6b–6d | Agent Voice reference, working switches on supported integrations, Unused, move/Ctrl-copy/undo. Name any unsupported tool and reason in the RC ledger. |
| 12 | 6e | One file per note topic with safe move/copy/undo between scopes. |
| 13 | 2, 3b, 10a–10b | Pace, timeline, Advanced, live open mic and commands, interruption controls and cutoff notice. |
| 14 | 1, 8a–8b | Real runtime inspection, launch/session controls, audit, export/duplicate/reset and confirmations. |
| 15 | 5a, 6a–6f, 7c | Communal tools/opt-out, effective preview, history, import/export, skill capabilities, notes and shared chats. |
| 16 | 4a–4c | Human approval, directed list enforced, quarantine, accessible table and graphical editor. |
| 17 | 1, 4b–14 | Shared components, clear stage order, collapsed fine-tuning and risk confirmations across pages. |
| 18 | 9a–9b, 10a | Real wake pipeline, agreement, contextual verifier and live gate adaptation, decision counts. |
| 19 | 11 | Per-agent voice/speed, Downloaded first, compact filter/search, aligned rows and Advanced transcription. |
| 20 | 7c, 12a–12b | Other settings, chat privacy/usage/purge, readout placement/size/preview, two texts, keys and lock notice. |
| 21 | 3b, 12a, 13a | About shows installed provenance, local/remote capabilities and commands. Maintenance lives in Other settings. |
| 22 | 0, 1, 3a, 13a–13b, 16 | Early reload fix, command safeguards, diagnostics/update/changelog/license/README, search, setup, keyboard/light review. |
| 24 | 15 | Attributed background speech and notification without another wake, queued/suppressed as configured. |

| Section 23 bug | Delivering phase | Evidence that closes it |
|---|---|---|
| A · embedded commands ignored | 3a | Positive mid-sentence fixture and spoken example pass alongside false-trigger negatives. |
| B · popup bounces | 12b | Zero locked-geometry delta across disappearing/returning transcript data. |
| C · silent 30-second cutoff | 10a–10b | Real cutoff event at configured limit, visible warning and shortcut, 90-second case exercised. |
| D · global popup permission editor | 12b | Per-agent editing remains reachable and genuine request cards still work. |
| E · duplicate Agents footer | 5a | Footer gone and all former global/inherited keys still have one working home. |
| F · misaligned Voice rows | 11 | Equal column positions with and without an available trash action. |
| G · read-only Tools & skills | 6b–6d | Each usable control changes effective tool access or skill supply for the chosen agent. |
| H · shell resets on save | 0 | Repeatable file-event probe passes before any feature branch. |
| I · open mic loses earlier turns | 2 | Both permission transitions traced with a remembered synthetic turn and current permission posture. |
| J · surprise chime / apparent new chat | 2 | Chime reason and real chat/session boundary independently verified. |
| K · open-mic-off display lingers | 2 | Measured close-to-clear and distinct ordinary follow-up state. |

## Open questions for the user

1. Which backends and audio devices must pass **live** before release? The plan records fixture-only coverage separately, including for endpoints.
2. Should the Agent Voice skill only explain commands, or may it invoke a named subset through existing permissions? This plan starts with the skill explaining commands.
3. Should clear embedded commands run as proposed in 3a, including your “and keep listening, because…” example? The proposed grammar leaves ambiguous speech with the agent.
4. Should background completion announcements start enabled per agent, and is a neutral notification sufficient while locked or in DND?
