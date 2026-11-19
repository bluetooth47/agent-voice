# Agent Voice: full test plan

Written 2026-11-18, against build 9e1918f (branch `phase-g`, Phases A–G).
Covers the whole application, not only the recent phases.

---

## 0. How this plan works

### 0.1 Three kinds of test

| tier | who runs it | needs | what it proves |
|---|---|---|---|
| **A. Automated** | Claude | nothing | the code does what the tests say, on this machine and on a bare one |
| **B. Scripted, no voice** | Claude | the installed service, the desktop | every CLI command, file, protocol and screen works for real, without speaking |
| **C. Live voice** | you speak, Claude watches the journal and the state file | you at the desk, a quiet room | the product works in a room, end to end |

Tiers D (robustness), E (privacy and security), F (measurements) and
G (install, upgrade, uninstall) mix the three. Each test says who runs it.

### 0.2 Recording results

Results go in `testresults.md`, one row per test ID:

| ID | result | evidence | note |
|---|---|---|---|
| C-WAKE-01 | pass / fail / blocked / skipped | journal line, state field, screenshot path, number | what happened |

- **pass** only when the expected result was seen, not inferred.
- **blocked** when something outside the test stopped it (no key, Chrome
  not running). Say what.
- A failure gets a short reproduction and stays open until it is fixed and
  re-run.

### 0.3 What Claude watches during live tests

- `journalctl --user -u agentvoice -f -o cat`: structural lines (wake,
  timings, tool markers, errors, lock). Speech text only if `logSpeech` is
  on.
- `$XDG_RUNTIME_DIR/agentvoice/state` (JSON): `state`, `transcript`,
  `reply`, `who`, `live`, `open_mic`, `level_db`, `gate_db`, `floor_db`,
  `crew`.
- `$XDG_RUNTIME_DIR/agentvoice/permissions/*.request`: pending questions.
- `agentvoice status`, `agentvoice history`, `agentvoice chats list`.
- Screenshots with `grim` for anything on screen.

### 0.4 Before starting

1. Note the settings as they are, so they can be put back:
   `cp ~/.config/omarchy/shell.json ~/agentvoice-test-shell.json.bak`.
2. Turn `logSpeech` **on** for the live session, so Claude can see what was
   heard. Turn it **off** at the end (E-PRIV-01 checks it).
3. Quiet room first. Noise tests come in their own block.
4. Speakers for most tests. A headset for the C-BARGE block.
5. Chrome running with the Claude in Chrome extension, for the browser
   block.
6. For the endpoint block, one of: a key for Groq/OpenAI/xAI, Ollama on the
   Mac mini, or the llama.cpp server in `~/.cache/agentvoice-bench/`.

### 0.5 Order of work

1. Tier A (about 30 min, unattended).
2. Tier B (about 1 hour, unattended, a few screenshots).
3. Tier C in blocks of 20–30 minutes, grouped so settings change as little
   as possible (section 11 has the session plan).
4. D, E, F alongside, where they fit.
5. G last, because uninstall removes the thing being tested.

---

## 1. Tier A: automated

| ID | test | how | pass when |
|---|---|---|---|
| A-01 | Full check | `./bin/agentvoice-check` | all 15 static checks ok, every test passes |
| A-02 | Installer in a box | `AGENTVOICE_BOX=1 ./bin/agentvoice-check` | 9 of 9 box installs pass |
| A-03 | Bare runner | fresh venv with `requirements-dev.txt` only, `AGENTVOICE_STRICT=1` | passes with no ML wheels installed |
| A-04 | No skips | `AGENTVOICE_NO_SKIPS=1` on the full venv | no test skips |
| A-05 | Mutation spot-checks | reintroduce 5 known bugs one at a time (hook exits non-zero; `--settings` dropped; thinking filter disabled; desktop prefix check loosened; Lua dispatch replaced by legacy only) | each makes at least one test go red |
| A-06 | qmllint on every QML file | part of A-01 | no missing-property warnings |
| A-07 | Each branch builds | check out `dev`, `phase-b` … `phase-g` and run A-01 on each | green on every branch (they will be merged in order) |

---

## 2. Tier B: scripted, no voice (Claude runs)

### 2.1 Service and CLI

| ID | command | expected |
|---|---|---|
| B-CLI-01 | `agentvoice status` | JSON with `state`, `agent`, `level`, `crew`; `state` is `listening` |
| B-CLI-02 | `agentvoice is-active` | `yes`, exit 0, while running |
| B-CLI-03 | `agentvoice stop` then `is-active` | `no`; bar icon goes to off |
| B-CLI-04 | `agentvoice start` | back to `listening` within ~5s; banner in journal names build 9e1918f |
| B-CLI-05 | `agentvoice toggle` twice | off then on |
| B-CLI-06 | `agentvoice mic` twice | state `muted` then `listening`; service stays up (pid unchanged) |
| B-CLI-07 | `agentvoice lock`, `locked`, `unlock` | `locked` prints yes / exit 0, then no / exit 1; state shows closed mic while locked |
| B-CLI-08 | `agentvoice interrupt` with nothing playing | no error, no state change |
| B-CLI-09 | `agentvoice talk` / `talk-end` | a capture opens and closes (state `recording` then back); empty turn discarded |
| B-CLI-10 | `agentvoice open-mic on` / `off` | `open_mic` appears in state with `who` and `until`, then goes |
| B-CLI-11 | `agentvoice wake-test start` / `stop` | `wake-test.json` status goes `running` → `stopped`; file mode 0600 |
| B-CLI-12 | `agentvoice wake-test auto` | finishes in ~1.5 min; `wake-auto.json` has hit rates per name and 0 false wakes |
| B-CLI-13 | `agentvoice pending` with none | empty / `{}` |
| B-CLI-14 | `agentvoice permit <bad-id> allow` | refused, nothing written |
| B-CLI-15 | `agentvoice history` | last exchanges, printed through `safe_for_terminal` |
| B-CLI-16 | `agentvoice chats list/show/rename/pin/unpin/export/delete` on a test chat | each works; export writes Markdown to ~/Documents without overwriting |
| B-CLI-17 | `agentvoice chats continue <bad>` | usage error, exit 2 |
| B-CLI-18 | `agentvoice voice sample amy-medium` | plays about a minute of speech |
| B-CLI-19 | `agentvoice voice fetch <voice not installed>` then `remove` | downloads, hash checked against models.lock, then removed |
| B-CLI-20 | `agentvoice voice fetch <voice not in models.lock>` | refused |
| B-CLI-21 | `agentvoice calibrate` | prints a verdict about barge-in in this room |
| B-CLI-22 | `agentvoice monitor` for 10s | live scores print; daemon unaffected |
| B-CLI-23 | `agentvoice endpoint clean/presets/models/test/key` | as in B-EP below |
| B-CLI-24 | unknown subcommand | usage, non-zero exit |
| B-CLI-25 | `agentvoice-train-verifier --help` | runs, explains itself |

### 2.2 State file and runtime directory

| ID | test | expected |
|---|---|---|
| B-RT-01 | modes | `$XDG_RUNTIME_DIR/agentvoice` 0700; state, history, wake-test files 0600 |
| B-RT-02 | state written atomically | 200 reads during a turn never give a half-written JSON |
| B-RT-03 | pid file | names the live daemon; removed on stop |
| B-RT-04 | grants directory | emptied at daemon start |

### 2.3 Endpoints (no key needed for most)

| ID | test | expected |
|---|---|---|
| B-EP-01 | `endpoint clean` on 15 typed forms (localhost:11434, a pasted /chat/completions, a public host with no scheme, `user:key@host`) | matches the table in tests/test_endpoints.py |
| B-EP-02 | `endpoint test localhost:11434 llama3.2` with nothing running | "Ollama isn't running (nothing on port 11434)" |
| B-EP-03 | `endpoint test` on a closed random port | "wrong port?" |
| B-EP-04 | `endpoint test https://api.groq.com/openai/v1 x` with no key | "it wants an API key" |
| B-EP-05 | `endpoint key set` via stdin, then `show`, then `clear` | masked, file 0600, gone |
| B-EP-06 | key never in argv | `ps -eo args` during `key set` shows no key |
| B-EP-07 | with a real endpoint (llama.cpp / Ollama / a key) | `models` lists it; `test` gives a first-word time |
| B-EP-08 | reasoning model (Qwen3) through `test` | reply has no `<think>` text |

### 2.4 Desktop tools server (real desktop, harmless actions only)

| ID | test | expected |
|---|---|---|
| B-MCP-01 | handshake + tools/list | 19 tools; median start < 150 ms |
| B-MCP-02 | `list_windows`, `active_window`, `list_workspaces` | real windows listed |
| B-MCP-03 | `focus_window` on the terminal | "done" (Lua dispatch) |
| B-MCP-04 | `switch_workspace` to the current one | "done" |
| B-MCP-05 | `open_app` "Files", then `close_window` on it | Nautilus opens, then closes |
| B-MCP-06 | `move_window` of a scratch window to workspace 9 and back | moves, focus does not follow |
| B-MCP-07 | `notify` | notification appears |
| B-MCP-08 | `clipboard_write` then `clipboard_read` | round trip |
| B-MCP-09 | `volume set` to the current level | unchanged volume, "volume N%" |
| B-MCP-10 | `media play-pause` with nothing playing | "nothing is playing" |
| B-MCP-11 | `open_in_editor` README line 100 | VS Code opens at line 100 |
| B-MCP-12 | `show_changes` on a scratch repo | VS Code diff opens; HEAD copy in runtime/diffs 0600 |
| B-MCP-13 | `open_project_layout` on a scratch folder | terminal and editor open there |
| B-MCP-14 | `lock_screen` with no "lock" in the last transcript | refused, screen stays unlocked |
| B-MCP-15 | `suspend` with no "suspend/sleep" in the last transcript | refused |
| B-MCP-16 | `screenshot` with nobody answering | card appears, times out, "refused", no file left in /tmp |

### 2.5 Permission hook (real Claude turns, Haiku, scratch folder)

| ID | level | asked to | expected |
|---|---|---|---|
| B-HOOK-01 | ask | read a file | no card, allowed |
| B-HOOK-02 | ask | write a file | card; silence → denied after the timeout |
| B-HOOK-03 | ask | read `~/.ssh/config` | card ("this reads …") |
| B-HOOK-04 | ask | grep a folder holding a `.env` | card |
| B-HOOK-05 | edits | write inside the project | allowed |
| B-HOOK-06 | edits | write `.claude/settings.json` inside the project | card (NEVER_SILENT) |
| B-HOOK-07 | edits | write outside the project | card |
| B-HOOK-08 | trusted | Bash | allowed, no hook process |
| B-HOOK-09 | ask | WebSearch | card |
| B-HOOK-10 | ask | a desktop `list_windows` | allowed |
| B-HOOK-11 | ask | desktop `notify` | card (measured in §31) |
| B-HOOK-12 | ask | ToolSearch | no card |
| B-HOOK-13 | any | answer "allow all in this chat", then another write | second write not asked; a new chat asks again |
| B-HOOK-14 | any | `agentvoice permit <id> deny` from the CLI | denied with reason |
| B-HOOK-15 | any | kill the turn while a card is up | request file removed |
| B-HOOK-16 | any | corrupt the response file | denied |

### 2.6 Omarchy skill

| ID | test | expected |
|---|---|---|
| B-SK-01 | `omarchy_skill.py show` | Lua scratchpad line; 145 commands; no install/update commands |
| B-SK-02 | stamp | matches `omarchy-version` + generator hash |
| B-SK-03 | the 3-question comparison from §31, rerun | 3/3 with the skill |

### 2.7 Every screen, drawn (preview.sh, no real settings touched)

Each in the current theme and in `flexoki-light`, checked against a
screenshot by eye: nothing cut off, nothing overlapping, nothing unreadable.

| ID | target | arg / state |
|---|---|---|
| B-UI-01 | settings → Overview | `--state states/showcase.json` |
| B-UI-02 | settings → Agents, every card open in turn (main, Sora, an endpoint agent) | scratch shell.json |
| B-UI-03 | settings → Listening, Advanced open | |
| B-UI-04 | settings → Conversation | |
| B-UI-05 | settings → Voice, the library | |
| B-UI-06 | settings → Display | |
| B-UI-07 | settings → About | |
| B-UI-08 | popup (bar widget) | idle, thinking, speaking, open mic, muted, locked states |
| B-UI-09 | HUD readout | a long reply; a reply with an HTML-looking string (shown as plain text) |
| B-UI-10 | conversation view, session | with a thinking block (folded, greyed) |
| B-UI-11 | conversation view, saved chats | list grouped Today/This week/Older, a chat open |
| B-UI-12 | permission card | a Bash request; a browser request with a note; a 400+ character command (truncation note) |
| B-UI-13 | Omarchy Agents panel | a record for Theo and Sora |
| B-UI-14 | `clicks` target | every control writes the key it should (`.writes` log) |
| B-UI-15 | `knob` target | a slider commits on release only |

---

## 3. Tier C: live voice (you speak)

Each test: what to say, what should happen, what Claude checks. "Theo" is
the main wake word and "Sora" the extra agent, as set now.

### 3.1 Waking

| ID | say / do | expected | Claude checks |
|---|---|---|---|
| C-WAKE-01 | "Theo" ×10, normal voice, 1 m away | ≥8 wakes, chime each time | journal `wake` lines; FINDINGS rate |
| C-WAKE-02 | "Theo" ×10 from 3 m | record the rate | |
| C-WAKE-03 | "Theo" ×5, quietly | record the rate | |
| C-WAKE-04 | "Sora" ×10 | ≥8 wakes, Sora's voice answers | `who` = sora |
| C-WAKE-05 | "Hey Theo, …" in one breath | wakes, and the request is kept without the name | transcript has no "hey theo" |
| C-WAKE-06 | 5 min of normal talk not using the names | 0 wakes | no `wake` lines |
| C-WAKE-07 | words close to the names: "theory", "see you", "soda", "tío" ×3 each | 0 or few wakes; record each | |
| C-WAKE-08 | manual wake test from the Listening page, 10 tries | page shows tries, hits, how each was caught, near misses, loudest level vs gate | |
| C-WAKE-09 | automatic wake test from the page | finishes, shows per-voice results | |
| C-WAKE-10 | verifier on: someone else (or a recording of another voice) says "Theo" | does not wake | journal `verifier` reject |
| C-WAKE-11 | switch engine to Vosk, then openWakeWord, then back to sherpa | each wakes on its phrase; switching never needs a restart | journal reload lines |
| C-WAKE-12 | change the wake phrase on the main card | new phrase wakes, old does not, conversation kept | |

### 3.2 Hearing the request

| ID | say / do | expected |
|---|---|---|
| C-HEAR-01 | short request ("Theo, what time is it?") | answered; transcript correct |
| C-HEAR-02 | long request with two pauses of ~1s | not cut off; one turn |
| C-HEAR-03 | stop talking and wait | turn ends about `trailingSilenceMs` later (1.2s); "quick end" sooner after a finished sentence |
| C-HEAR-04 | wake, then say nothing | gives up after `leadInMs`; no turn sent |
| C-HEAR-05 | wake, cough only | discarded (`minUtteranceMs`) |
| C-HEAR-06 | talk for 35s | cut at 30s (`maxUtteranceMs`), turn sent |
| C-HEAR-07 | Live transcript: Off / On / Accurate / Auto | HUD shows nothing / Vosk text / Vosk text replaced by Whisper's at pauses; last text = what was sent |
| C-HEAR-08 | transcription model tiny.en vs base.en | both work; note the time in the journal timing line |
| C-HEAR-09 | push-to-talk keybind: hold, speak, release | turn sent on release, no wake word |
| C-HEAR-10 | names and paths ("open noise_floor.py") | transcript usable; record misses |

### 3.3 Answering and speaking

| ID | say / do | expected |
|---|---|---|
| C-SPEAK-01 | a question with a 3-sentence answer | speech starts on the first sentence, before the reply is finished |
| C-SPEAK-02 | an answer with markdown, a list, a URL, code | spoken sensibly (no "asterisk", no reading out the code) |
| C-SPEAK-03 | change the voice (Voice page), ask again | new voice; no restart |
| C-SPEAK-04 | speed 80% and 150% | speed changes |
| C-SPEAK-05 | speak replies off | text only in the HUD; nothing spoken |
| C-SPEAK-06 | chimes off | no chimes; on: listening, heard and done chimes |
| C-SPEAK-07 | a long task (> LONG_TURN_S) | "done" chime at the end |
| C-SPEAK-08 | after a reply, wait for the echo tail | no self-wake from its own voice |

### 3.4 Stopping

| ID | say / do | expected |
|---|---|---|
| C-STOP-01 | "Theo" during a reply | reply stops, new turn opens |
| C-STOP-02 | "full stop" while it speaks, no wake word (speakers) | note: the mic is ignored while speaking on speakers, so expect no stop; on a headset it stops |
| C-STOP-03 | "full stop" while it thinks | everything stops at once, no capture opens |
| C-STOP-04 | interrupt keybind during a reply | stops; listens again |
| C-STOP-05 | popup STOP | stops everyone |
| C-STOP-06 | "Sora, stop" while Sora and Theo both work | only Sora stops |
| C-STOP-07 | click the bar icon mid-reply | popup opens, reply continues (item 8) |

### 3.5 Conversation, follow-up and open mic

| ID | say / do | expected |
|---|---|---|
| C-CONV-01 | ask, then within 7s ask a follow-up with no wake word | answered, same conversation (it remembers) |
| C-CONV-02 | wait past the follow-up window, speak | ignored |
| C-CONV-03 | conversation mode off | wake word needed every time |
| C-CONV-04 | "Theo, keep listening" | "I'm listening…", accent bar icon, OPEN MIC line with minutes |
| C-CONV-05 | two requests with no name, 30s apart | both answered |
| C-CONV-06 | talk to someone else / play a video (open mic, "only if meant for you" on) | silent; journal "(open mic: not meant for it)" |
| C-CONV-07 | "Sora, what time is it?" during Theo's open mic | Sora answers; open mic now Sora's |
| C-CONV-08 | "stop" during an open-mic reply | reply stops, mic stays open |
| C-CONV-09 | "stop listening" / "goodbye" / "go to sleep" | mic closes, icon back |
| C-CONV-10 | open from the popup tile, Closes after = 1 min, say nothing | closes by itself after 1 min |
| C-CONV-11 | "open the mic after every wake" on | every wake opens the mic |
| C-CONV-12 | mute or lock during open mic | open mic ends |

### 3.6 More than one agent

| ID | say / do | expected |
|---|---|---|
| C-CREW-01 | give Theo a long task, then Sora a question while Theo works | Sora answers; Theo carries on; never two voices at once |
| C-CREW-02 | Theo and Sora finish at the same moment | one speaks, then the other, never interleaved |
| C-CREW-03 | start talking while an answer is due | it waits until you finish |
| C-CREW-04 | add a third agent with a new name, Vosk-known word | wakes on its name, own voice |
| C-CREW-05 | name it a word the engine does not know | refused with the reason on the card |
| C-CREW-06 | switch Sora off on its card | "Sora" does nothing; chip gone; card dimmed; switch on → works, settings kept |
| C-CREW-07 | switch Sora off mid-turn | its turn stops at once |
| C-CREW-08 | set Sora's display name to "Research" | HUD, chip, card, permission card say Research; "Sora" still wakes it |
| C-CREW-09 | change Sora's wake phrase mid-conversation | new phrase wakes; conversation and "allow all" grant kept |
| C-CREW-10 | main card Name = "Theo" | popup chip and Overview say Theo |
| C-CREW-11 | Sora's own model/effort/voice/speed/instructions | each applies; effort/voice/instructions keep the conversation; model starts a new one |
| C-CREW-12 | remove an agent | gone everywhere; its Agents panel record removed |
| C-CREW-13 | 8 agents | the 9th cannot be added |

### 3.7 Permission levels, live

| ID | say / do (Sora at ask, Theo at trusted) | expected |
|---|---|---|
| C-PERM-01 | "Sora, create a file hello.txt in my project" | card on screen naming Sora; Allow → file made |
| C-PERM-02 | same, Deny | not made; Sora says it was refused |
| C-PERM-03 | same, ignore the card | denied after 45s |
| C-PERM-04 | "Allow all in this chat" then a second write | second not asked |
| C-PERM-05 | Theo (trusted) writes a file | no card |
| C-PERM-06 | Sora at edits, write in its folder vs outside | inside allowed; outside asked |
| C-PERM-07 | the "Trust it" confirmation when choosing Trusted | the setting only changes after "Trust it" |
| C-PERM-08 | project folder empty + edits | page warns; edits behaves as ask |

### 3.8 Saved conversations and history

| ID | say / do | expected |
|---|---|---|
| C-CHAT-01 | Save conversations on; two short chats with "Theo, new chat" between | both in the conversation view |
| C-CHAT-02 | "Theo, continue the chat about <topic 1>" | "Continuing …"; next request carries on |
| C-CHAT-03 | two chats with similar titles, ambiguous continue | it names both and asks |
| C-CHAT-04 | in the view: search, agent filter, rename, pin, export, delete (two clicks) | each works; pinned survives retention |
| C-CHAT-05 | retention "last 100" with a test pile | pruned on next new chat |
| C-CHAT-06 | Save conversations off | view is the session view; nothing new in the chats folder |
| C-CHAT-07 | keep this session's conversation off | history file removed at once |
| C-CHAT-08 | log out / reboot | session history gone; saved chats stay |

### 3.9 Progress talk

| ID | say / do | expected |
|---|---|---|
| C-NARR-01 | Brief: "Theo, run the checks and tell me if they pass" | after ~7s, "I'm running the checks." once; nothing over the answer |
| C-NARR-02 | Detailed: "Theo, read noise_floor.py and explain it" | file name said as words |
| C-NARR-03 | a turn touching `.env` | "a config file", never the name or contents |
| C-NARR-04 | Sora's card Off, main Brief | Sora silent while working, Theo talks |
| C-NARR-05 | narration line cut by the answer | cut at a word break |

### 3.10 Terminal handoff

| ID | say / do | expected |
|---|---|---|
| C-TERM-01 | "Theo, move this to a terminal" | terminal opens in the project folder with the chat resumed; "Moved to a terminal." |
| C-TERM-02 | "Theo, what were we doing?" while it is open | "That chat is open in a terminal…" |
| C-TERM-03 | type in the terminal, close it, ask Theo about it | Theo knows what was typed |
| C-TERM-04 | "new chat" while the terminal holds the old one | fresh chat, voice works |
| C-TERM-05 | handoff from an endpoint agent | refused, with a spoken reason |

### 3.11 Endpoints, live

| ID | say / do | expected |
|---|---|---|
| C-EP-01 | an agent on an endpoint (preset or typed) | answers; HUD and chip name it |
| C-EP-02 | a reasoning model | thinking never spoken; greyed in the view |
| C-EP-03 | turns remembered = 0 | no memory between turns; 8 → remembers |
| C-EP-04 | timeout 10s against a slow model | turn ends with "stopped responding after 10s", spoken |
| C-EP-05 | main agent on an endpoint, then cleared | Omarchy's agent answers again |
| C-EP-06 | an endpoint marked "is an agent" | posture text changes; longer timeout |

### 3.12 Desktop, editor, browser

| ID | say / do | expected |
|---|---|---|
| C-DESK-01 | "Theo, what windows are open?" | correct list, no card |
| C-DESK-02 | "Sora, move the browser to workspace 3" | card (ask); allowed → moved |
| C-DESK-03 | "Theo, open Files" / "close it" | opens / closes |
| C-DESK-04 | "Theo, pause the music" / "turn it down" | works |
| C-DESK-05 | "Theo, take a screenshot and describe the screen" | card even for trusted Theo; allowed → correct description |
| C-DESK-06 | "Theo, lock the screen" | locks; the mic closes while locked (C-LOCK) |
| C-DESK-07 | "Theo, open the README at line 100" | VS Code at line 100 |
| C-DESK-08 | "Theo, show me what changed in <repo>" | VS Code diff |
| C-DESK-09 | "Theo, open a scratchpad" / "next background" / "turn on do not disturb" | exact omarchy commands used (skill) |
| C-BROW-01 | "Theo, go to example.com and read me the heading" | no card |
| C-BROW-02 | "Theo, put a kettle in a cart on <shop> and check out" | checkout click asked out loud and on screen; deny |
| C-BROW-03 | "Theo, run some JavaScript on the page to count links" | asked even at trusted |
| C-BROW-04 | Browser setting off | agent says it has no browser |

### 3.13 Barge-in and headset

| ID | say / do | expected |
|---|---|---|
| C-BARGE-01 | headset on, talk over a reply | reply stops (bargeOnHeadset) |
| C-BARGE-02 | headset, barge off | reply continues |
| C-BARGE-03 | speakers, bargeIn on, after `calibrate` says it can work | stops on loud speech, not on its own voice; record false stops |
| C-BARGE-04 | unplug the headset mid-reply | output moves; no crash |

### 3.14 Lock, mute, recorders

| ID | say / do | expected |
|---|---|---|
| C-LOCK-01 | lock the screen, say "Theo" | no wake; HUD hidden at once |
| C-LOCK-02 | lock mid-reply | speech stops within a chunk |
| C-LOCK-03 | unlock | listening again; a mic muted before the lock stays muted |
| C-LOCK-04 | mute (right click / keybind) | mic released (no orange dot), models stay loaded |
| C-LOCK-05 | start a screen recording / a call app using the mic | daemon steps aside (yieldToRecorders); back after |
| C-LOCK-06 | service switch off in the panel | ~600MB released; back in 3–4s |

### 3.15 Noise and the adaptive gate

| ID | say / do | expected |
|---|---|---|
| C-NOISE-01 | gate follows the room on; fan on | Listening page shows the room and gate rising; wakes still work |
| C-NOISE-02 | music at a normal level | wake works; turns end about 1s after you stop |
| C-NOISE-03 | TV with speech | no false wakes over 5 min |
| C-NOISE-04 | adaptive off, same rooms | compare with FINDINGS §27 |

---

## 4. Tier D: robustness

| ID | test | expected |
|---|---|---|
| D-01 | restart the service 10 times, some during startup | no core dump (`coredumpctl list agentvoice`) |
| D-02 | kill -9 the daemon | systemd state shows it; `agentvoice start` recovers; stale pid ignored |
| D-03 | claude not on PATH (rename temporarily in a scratch PATH test) | spoken, explained failure; no loop of errors |
| D-04 | agent CLI errors (usage limit) | failure kind spoken once; conversation dropped if it would fail again |
| D-05 | no network | endpoint and claude errors spoken plainly |
| D-06 | hostile local endpoint (endless line, endless frames, huge error) | memory stays bounded (tests exist; rerun with RSS watch) |
| D-07 | corrupt shell.json values (hand edit: wrong types, flags as model names) | defaults used, nothing passed as a flag |
| D-08 | corrupt chats index | rebuilt from chat files |
| D-09 | disk full for the chats folder (tmpfs quota) | turn still answered; "chat not saved" |
| D-10 | microphone unplugged / changed | daemon survives; says so; recovers when back |
| D-11 | 1 hour idle | RSS stable (record before/after); no drift in CPU |
| D-12 | 50 turns in a row | no growth in sessions, history capped at 200 |
| D-13 | Omarchy theme change while settings are open | colours follow live |
| D-14 | shell restart while a permission card is up | request still answerable or times out to deny |

---

## 5. Tier E: privacy and security

| ID | test | expected |
|---|---|---|
| E-PRIV-01 | `logSpeech` off: one turn, then `journalctl -o json` | no transcript or reply text anywhere, including carriage-return lines |
| E-PRIV-02 | prompts not in argv | `ps -eo args` during a turn shows no spoken words for any backend |
| E-PRIV-03 | runtime files | all 0600/0700, owned by you |
| E-PRIV-04 | saved chats | dir 0700, files 0600 |
| E-PRIV-05 | endpoint keys | not in shell.json, state, history, journal, or the Agents panel records |
| E-PRIV-06 | locked screen | nothing heard, nothing shown over the lock screen |
| E-SEC-01 | permission hook fails | every failure path ends in a denial (rename runtime.py in a scratch copy and run the hook) |
| E-SEC-02 | dangling symlink trick from CLAUDE.md | asked, not allowed |
| E-SEC-03 | a spoken sentence asking to change shell.json's permission level | asked at every level below trusted |
| E-SEC-04 | HTML in a transcript or reply | shown as text in HUD, view, card |
| E-SEC-05 | redirect from an endpoint with a key | refused, key not sent |
| E-SEC-06 | key over plain http to a public host | refused |
| E-SEC-07 | desktop tool name spoofing (another MCP server named like ours) | not given our allowances |
| E-SEC-08 | browser consequential action at trusted | asked (C-BROW-02) |
| E-SEC-09 | lock/suspend without the words | refused (B-MCP-14/15) |
| E-SEC-10 | the agent tries to edit the plugin's own config through Bash at "edits" | asked |

---

## 6. Tier F: measurements to record

| ID | number | how |
|---|---|---|
| F-01 | wake-to-chime latency | journal timing, 10 wakes |
| F-02 | end-of-speech to first audio, per backend (Claude warm/cold, endpoint) | journal latency line, 5 turns each |
| F-03 | Whisper time per second of audio, tiny.en and base.en | journal |
| F-04 | idle RSS and CPU, service on / muted / off | `ps`, 5 min each |
| F-05 | wake hit rate and false wakes (C-WAKE-01..07) | counts |
| F-06 | desktop server start | B-MCP-01 |
| F-07 | skill build time | `time omarchy_skill.py build` |
| F-08 | battery drain per hour listening (laptop on battery) | `upower`, 1 h |

Every number goes into `bench/FINDINGS.md` §33 with the date and hardware.

---

## 7. Tier G: install, upgrade, uninstall

| ID | test | expected |
|---|---|---|
| G-01 | `install.sh --yes` over the current build | "Build X, replacing Y"; skill line; service restarted |
| G-02 | install the published version (older) over this one | downgrade reported in both directions |
| G-03 | `install.sh --dev` | app linked to the checkout |
| G-04 | keybinds offer: already present, absent, conflicting | each case says what it did; backup made |
| G-05 | `install.sh --sherpa` / openWakeWord extras | installed, page shows them available |
| G-06 | uninstall from the panel's Remove button | service, venv, models, skill, app removed; chats folder kept and named if it holds chats; keybinds removed with backup |
| G-07 | reinstall after uninstall | works from cold; Whisper model downloads on first use |
| G-08 | box (A-02) | 9/9 |

---

## 8. Settings coverage

Every setting must be changed once from its page and seen to take effect
without a restart (the reconcile rule). The test that covers each:

| setting | test | setting | test |
|---|---|---|---|
| phrase | C-WAKE-12 | micThresholdDb | C-NOISE-04 |
| adaptiveGate / gateMarginDb | C-NOISE-01 | wakeConfidencePct | C-WAKE-11 (Vosk) |
| leadInMs | C-HEAR-04 | trailingSilenceMs / quickEndMs | C-HEAR-03 |
| minUtteranceMs | C-HEAR-05 | maxUtteranceMs | C-HEAR-06 |
| model | C-HEAR-08 | speakReplies | C-SPEAK-05 |
| chimes | C-SPEAK-06 | keepHistory | C-CHAT-07 |
| saveChats / chatRetention | C-CHAT-01/05 | voice / voiceSpeed | C-SPEAK-03/04 |
| echoTailMs | C-SPEAK-08 | engine / owwModel / owwThresholdPct / sherpaThresholdPct | C-WAKE-11 |
| wakeCrossCheck and crossCheck* (5) | C-WAKE-07, B-CLI-12 | shortNameBoostPct | B-CLI-12 |
| conversationMode / followUpMs | C-CONV-01..03 | yieldToRecorders | C-LOCK-05 |
| logSpeech | E-PRIV-01 | agentsPanel | B-UI-13 |
| narration / narrationSilenceS | C-NARR-01..05 | openMic* (3) | C-CONV-04..11 |
| fullStopAnytime | C-STOP-03 | livePartials | C-HEAR-07 |
| mainName | C-CREW-10 | projectDir | C-PERM-06/08 |
| agentInstructions | C-CREW-11 (main) | endpoint* (5) | C-EP-01..06 |
| desktopTools | C-DESK-* | browserTools | C-BROW-* |
| omarchySkill | C-DESK-09 | bargeOnHeadset / bargeIn / bargeFactor | C-BARGE-* |
| hud / hudLingerMs | B-UI-09, C-HEAR-01 | useVerifier | C-WAKE-10 |
| voiceAgents (all fields), permissions, agentModels, agentEfforts, wakeAlsoSounds | C-CREW-*, C-PERM-*, C-WAKE-07 | | |

---

## 9. Backends

| backend | turn | remembers | permissions | notes |
|---|---|---|---|---|
| Claude Code | C-HEAR-01 | C-CONV-01 | C-PERM-* | main path |
| Codex | one turn after Nov 27 (usage limit) | resumes | levels it offers | blocked until then |
| Gemini | not installed | — | — | skipped, say so |
| Antigravity | one turn if installed | | | |
| Copilot | one turn if installed | does not remember | | |
| Endpoint | C-EP-01 | C-EP-03 | none (no tools) | |

---

## 10. Pass criteria for the whole run

- Tier A, B, E: every test passes or is blocked with a reason.
- Tier C: at least 90% pass. Every failure has a reproduction.
- No crash, no core dump, no permission that failed open, no speech in
  the journal with `logSpeech` off.
- Every Tier F number recorded.

Failures found are fixed on a `test-fixes` branch cut from `phase-g`, each
with a test that would have caught it. Then the affected tests are rerun.

---

## 11. Session plan for the live tests

| session | length | blocks | settings to set first |
|---|---|---|---|
| 1 | 30 min | C-WAKE, C-HEAR | logSpeech on, quiet room |
| 2 | 30 min | C-SPEAK, C-STOP, C-CONV | |
| 3 | 30 min | C-CREW, C-PERM | Sora at ask, Theo trusted |
| 4 | 30 min | C-CHAT, C-NARR, C-TERM | saveChats on, narration brief |
| 5 | 30 min | C-EP, C-DESK, C-BROW | an endpoint; desktop and browser on; Chrome running |
| 6 | 20 min | C-BARGE, C-LOCK, C-NOISE | headset; a fan, music, TV |
| 7 | 15 min | E-PRIV-01, put settings back, G-06/G-07 | logSpeech off |

Claude prepares each session (settings, journal watch), calls out each test
as it comes, and fills `testresults.md` as it goes.
