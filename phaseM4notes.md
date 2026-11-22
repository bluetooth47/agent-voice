# Phase M4: The command table, and commands inside sentences (item 1, bug A)

Written 2026-11-21, unattended (started by the runner script). Branch
`phase-m4`, cut from `phase-m3` at 1ac9ff7. Result commit: the notes commit
on top of 72c9589, pushed to `fork/phase-m4` only; `dev` fast-forwarded to
it and pushed to `fork`. Model: Claude Opus 5.5, xhigh. **Stop point 1
follows this phase.**

Commits: 9646c25 (the phase), 72dc2e5 (Codex pass 1 fixes), 72c9589 (Codex
pass 2 fixes), then these notes.

Deployed: **yes**, 72c9589 through `bin/agentvoice-deploy --install` (its
strict check green in a fresh worktree, 3194 tests), daemon idle (state
`listening`, every agent idle, open mic off). It replaced d4c209f (the way
back: `bin/agentvoice-deploy --install d4c209f9ba78`). Installed: **yes**:
build 0.2.0 (72c9589) replaced 0.2.0 (d4c209f); the service is active.
**Shell restart needed** for the new control (`pages/ConversationPage.qml`;
`Panel.qml` changed only in a comment): not run, stop point 1.

`./bin/agentvoice-check`: green, **3194 tests** (was 2973; +221), 14 of 14
static checks, "the check wrote nothing in the tree: ok". Box: not run
(`install.sh` did not change).

## What was built

**The command table** (`daemon/speech_text.py`, `COMMANDS`). Ten commands,
the same as before: full stop, goodbye, stop, open mic, close the open mic,
move to a terminal, pass, take over, new chat, continue a chat. Per command:
id, label, a one-line effect, where it may sit (the plan's policy table,
row for row), its whole-transcript phrases, its in-sentence phrases,
whether it needs the wake word (only full stop does not, on sherpa-onnx),
the CLI equivalent, the fixed sentence said when it fires inside a sentence,
and whether it ends the conversation. The phrase sets are **the same set
objects** as before (`_STOP_PHRASES` and the rest), so nothing was lost and
one edit reaches the table. A test holds them equal to literal copies of
the pre-M4 sets.

**`find_command(text, mode, names)`**. The rules from before M4 are applied
first, unchanged (`exact`). Then, if the mode allows it, a command at the
start or end of what was said (`edges`) or in a clause of its own
(`clause`). It matches on Whisper's text before punctuation is thrown
away. Where there is no punctuation at all, clause cues ("and", "because",
...) stand in, but only for verb-first phrases in a transcript that does not
open with a subject. It never fires:
- with something after the command ("stop listening to that song",
  "stop listening, to that song");
- after a negation anywhere in the sentence before it ("don't keep
  listening", "do not, under any circumstances, keep listening"). A bare
  "No," is an answer;
- in quoted or reported speech: quotation marks, or a verb of saying in the
  sentence before it ("she asked me, keep listening");
- as a bare question ("keep listening?"; "can you keep listening?" counts);
- when anything else said is a command too: two in-sentence phrases, one
  said twice, or a clause of the rest that is a command by the old rules
  ("Keep listening. Stop.");
- after a greeting ("hello, goodbye").
Inside a sentence only forms that are plainly instructions count: "keep
listening", "open the mic", "stop listening", "turn the mic off". Not "open
mic", "close mic" or "mic off", which are nouns as often as not.

**The setting** `commandsInSentences`, three places (manifest schema +
default, `runtime.DEFAULTS` + TOML alias `[wake] commands_in_sentences`,
the control on the Conversation page under a new SPOKEN COMMANDS group):

| Key | Values (default) | Unreadable | Control |
|---|---|---|---|
| `commandsInSentences` | alone / edges / clause (edges) | alone: any other value, and whenever the settings cannot be read (`Config.commands_in_sentences`) | Conversation → Spoken commands → Commands inside a sentence |

**One hook in the daemon**, `Daemon.sentence_command` (`wake_listen.py`).
It is called after the existing checks for a command said on its own, from
the run loop's one-agent chain and from `_send` (several agents). A test
holds those two callers. It returns nothing for an exact command, which the
old chain still handles exactly as before. It never acts:
- on typed text or partial text;
- while locked (asked afresh: `locked_now()`) or lent out;
- while another program records (`recording_elsewhere()`, pw-dump at that
  moment);
- on the agent's own voice: the command's words in something `speak()` said
  up to 2 s before the person started talking;
- for an agent that cannot answer.
When a command fires:
- open mic, close and goodbye act at once and say the table's sentence once
  ("Open mic on.", "Open mic off.", "Goodbye."), shown on the HUD;
- new chat and continue a chat act inside the agent's turn
  (`answer(command=…)` → `chat_in_sentence`). A chat that cannot be
  continued says why and keeps the question back;
- the rest of the sentence goes to the agent once, never read for a command
  again;
- after goodbye or close, no follow-up window, including the window of a
  turn still working when it was said.
The journal line is `command: open_mic (edges, end, with a request)`. It
never holds the words.

**Undo.** "no" or "cancel that" (`is_undo`), started within 3 s of the end
of the turn that carried the rest, puts an open-mic switch back and says the
opposite sentence. "cancel that" then also stops, as before. The same
guards apply. It is refused once the mode is `alone`, with several agents
when the "no" is for another agent, after any lock, after any explicit
switch from the popup or the CLI, and after any other open-mic change
(`_open_mic_gen`). After "…, stop listening" nothing listens without the wake
word, so the frame loop opens a 3 s `undo` capture. It takes only "no" (or a
stop or full stop) and drops anything else unsent, with no live partials and
nothing left on screen. The popup reads STILL LISTENING then.

**`agentvoice commands [--json]`** (`daemon/voice_commands.py`): the table
plus each enabled agent's wake phrase, read from the settings. No daemon
needed. Text output goes through `safe_for_terminal`. It is for M14, M24 and
M26.

**`bench/commands_scan.py`**: the detector over the saved chats, counts
only. `--sample FILE` writes the sentences holding a command's words (0600,
never overwritten) for the user to label; `--labels FILE` gives the
false-trigger and miss counts per mode.

**Tests.** New `tests/test_commands.py` (215) covers:
- the table, and alone mode equal to the old matchers on 400+ inputs (every
  string literal in the existing command tests, both corpora, every phrase
  in four spellings);
- the corpora per mode: new `tests/fixtures/commands/fire.txt` (39) and
  `nofire.txt` (76, 18 of them review findings);
- each never-fires rule turned on by one word, the setting's fallbacks,
  shell.json and reload;
- the hook in every refused context, the crew path, the in-turn chat
  commands, undo;
- the real frame loop (open mic + "no"; goodbye with no window; the undo
  window taking "no", dropping anything else and passing a full stop);
- the CLI, and the scan (counts only, 0600 sample).
Additions to `test_speech_text.py` (the table uses those very sets; a stop
is never found inside a sentence), `test_interrupt.py` ("cancel that"
undoes and still stops) and `test_open_mic.py` (its own reminder heard back;
"keep listening to me"; said once). `conftest.py` stubs `recording_elsewhere`
and `locked_now`, as it already stubs the headset probe, so no test asks this
machine's pw-dump or compositor. `test_crew.py`'s `_send` stub takes the new
keyword.

**Mutations**: 83 in three rounds (31 on the phase, 28 on pass 1's fixes, 24
on pass 2's). Each was reintroduced and each now turns a test red. Along the
way 8 survived; each got a test, and 3 mutations with broken syntax were
rewritten and run again. One was equivalent: the undo's own lock check,
duplicated by the shared guard. That check was later replaced by a
`listening` check, which a test holds.

**Preview.** The `clicks` target clicks "Own clause" and logs `bar set
duaneoca.agentvoice commandsInSentences "clause"`. Screenshots: dark
520×720 and 1600×1000, flexoki-light 520×720. The binding-loop warnings in
the log are the same 9 as on M3.

**Docs.** README ("Commands inside a sentence"), CODEBASE (speech_text,
voice_commands, the hook, undo, the CLI row), FINDINGS §43.

## Shared files touched, and where

- `daemon/wake_listen.py` (big shared):
  - imports; `_IN_TURN_COMMANDS` beside `_empty_turn`;
  - `__init__`: `_said_lately`, `_undo`, `_open_mic_gen`;
  - `reconcile_lock` and `apply_lock_command` drop the undo on a lock;
  - `speak` (`note_said`);
  - `answer` (`command=`; the echo branch needs text);
  - `continue_by_topic` (new, out of `chat_turn`, same words), `chat_turn`;
  - `start_open_mic`, `end_open_mic` and `pass_open_mic` move the
    generation; `apply_open_mic_command` drops the undo;
  - a new section after `pass_command`: `command_names` (out of
    `pass_command`), `note_said`, `recording_elsewhere`, `locked_now`,
    `_command_refused`, `sentence_command`, `undo_clock`, `undo_due`,
    `take_undo`, `chat_in_sentence`;
  - `_send` (`heard_at`, the hook, a failed dispatch starts the undo
    clock); `dispatch` (`command=`, resets `ends_pending`); `_turn`
    (`command`, `ends`, `ends_pending`, `undo_clock`);
  - the run loop: the `undo` capture in the wake phase; an empty undo
    capture closed in the command handler and when another agent speaks;
    no partials for it; a silent timeout; its branch and the `take_undo`
    branch at the top of the chain; the hook branch in the one-agent chain;
    the follow-up after `ends`; `heard_at=spoke_at` to `_send`.
- `daemon/crew.py`: `Persona.ends_pending`.
- `daemon/runtime.py`: the default, TOML alias, `commands_in_sentences()`;
  `_from_toml` skips a section that is not a table and catches
  `OverflowError` (both pre-existing crashes found by Codex).
- `daemon/speech_text.py`: the table and matcher, appended; nothing above
  them changed.
- `Panel.qml` (big shared): one comment. `Settings.qml`: untouched.
- `pages/ConversationPage.qml`, `manifest.json`, `bin/agentvoice`
  (`commands`), `bench/preview/targets/clicks.qml`.

## Measured

FINDINGS §43:
- Corpus: alone 0/39 fired, 0/76 misfired; **edges 36/39, 0/76**; clause
  39/39, 0/76. The three that need `clause` are the mid-sentence ones,
  including the user's own example.
- The user's saved chats (counts only): 213 transcripts, 0 would fire in any
  mode, 3 held a command's words (all refused). With the first version's
  phrase list it was 5, still 0 fired.
- Tests 2973 → 3194; the check's test run ~2 min 35 s, as before.

## Different from the plan, and why

- **Typed messages are never read for a command inside a sentence.** The
  plan does not say. A typed message is deliberate text, and "…, and keep
  listening" typed into a box should not open the room's microphone. Typed
  commands said on their own work as before.
- **"pass this to NAME" adds nothing.** Its "Start" row is the request after
  the name, which it already had. It is marked as matched by the old rules.
- **The in-sentence phrases are a subset**, instructions only (above). The
  whole-transcript phrases are all still there.
- **What is said when a command is said on its own is unchanged** ("I'm
  listening. Say stop listening when you're done.", "Starting a new
  chat."). Only a command inside a sentence says the table's sentence. A
  continued chat inside a sentence says "Continuing that chat." rather than
  its title, since the plan asks for a fixed sentence.
- **The sentence comes first**, then the reply to the rest, for every
  command, as the plan orders it, so "…, goodbye" says "Goodbye." before the
  answer.
- **The undo window runs 3 s from the end of the turn carrying the rest**,
  not from the acknowledgement, which on speakers would end while the mic
  is deaf. After "…, stop listening" a 3 s undo-only capture listens for the
  "no" (from the first review); the plan has no such window.
- **In `edges` and `clause`, "continue the chat about X. A question?"
  splits** at the end of a sentence (3+ words after it), so the question
  reaches the agent. In `alone` it is the old rule, everything as the topic.
- **Dictation is asked of pw-dump at the moment a command would fire**,
  whatever `yieldToRecorders` says; "cannot tell" is not dictation, as for
  lending the microphone (open issue 6).
- **No in-sentence commands in echo mode** or for an agent that is not set up.
- **Most tests are in a new file**, `test_commands.py`. The three files the
  plan names got targeted additions.
- **Codex ran on the read-only copy both times**: `codex sandbox linux --
  true` still panics ("Failed to execvp linux"). The clone's HEAD and status
  were unchanged after both passes, and both copies were deleted.

## Codex review

- **Pass 1** (16 findings; 13 fixed in 72dc2e5, 3 not changed). Fixed:
  - noun phrases misfiring ("The venue hosts jazz and open mic");
  - a negation or verb of saying across a comma, and an object after one;
  - a quoted continue;
  - competing commands hidden in the rest ("Keep listening. Stop. Read the
    notes.", "Keep listening. That's it.");
  - a title split at a colon;
  - the minus sign and question mark lost at the cut;
  - the own-voice check missing "good bye" against "goodbye";
  - a stale lock state at the hook, and a chat command run over a lock;
  - echo mode losing a chat command;
  - undo: no mode check, no guards, a newer switch undone, a dispatch that
    never ran leaving the window open, no way to undo a close;
  - a goodbye over a working turn;
  - a TOML crash (`wake = "x"`).

  Not changed:
  - an exact "continue the chat about X …" still wins in every mode. It is
    the old rule, and the split already refuses a competing command;
  - a sentence the hook refuses, or a typed one, goes on as before M4, so a
    whole-transcript continue still continues;
  - the transcript print under `logSpeech` or a TTY is pre-existing and
    documented.
- **Pass 2** (13 findings, all fixed in 72c9589):
  - "She asked me, keep listening";
  - a negation two clauses back;
  - "I prefer to sit and keep listening";
  - "hello, goodbye";
  - a quoted continue after a lead word;
  - a title tail of two words;
  - "Keep listening and cancel that";
  - "No. 5" as an undo;
  - undo surviving an explicit off, a lock (polled or told) or a mute, and
    taking another agent's "no";
  - an undo window after switching to alone, or after the popup reopened
    the mic;
  - a full stop dropped in the undo window;
  - the goodbye race with a finishing turn;
  - the undo capture clearing the idle readout and outliving another
    agent's reply;
  - partials and dropped words shown from the undo window;
  - ".5 litres";
  - "goodnight" inside "goodnightmares";
  - `wake_confidence = inf`.
- **Pass 2's fixes were not re-reviewed by Codex** (credits, below). They
  have their own tests and 24 mutations.

## Found along the way

- **`poll_session()` also takes the CLI's command file.** Called from the
  run loop it would eat a push-to-talk press or an `open-mic` command meant
  for the loop. That is why the hook uses `locked_now()` (`reconcile_lock`
  only). `speak()` already calls `poll_session()` from the run loop in
  one-agent mode; whether that ever ate a command was not checked
  (open issue 11).
- **A saved chat holds no command said on its own**: such turns never reach
  the agent. So the scan's corpus is exactly the sentences a command could
  misfire on, and holds no record of bug A's misses.
- **Two pre-existing TOML crashes** in `Config._from_toml` (a section that
  is not a table; `wake_confidence = inf`) would have stopped the daemon on
  start. Fixed, with tests.
- **An exact "goodbye" said over a working turn**, with several agents, does
  not take down that turn's coming follow-up window. Fixed for the
  in-sentence path only (open issue 4).

## Not verified

- **All voice checks** (stop point 1, the plan's list):
  - the example sentence in each mode;
  - the false-trigger list said aloud ("stop listening to that song", "keep
    listening to me explain", "don't start a new chat", a quoted command);
  - one command at the start and one at the end;
  - "no" after "…, and keep listening", and after "…, stop listening" (the
    3 s window, labelled STILL LISTENING);
  - the journal line for a real spoken command (seen only in tests);
  - the own-voice check with barge-in on speakers;
  - dictation with Voxtype recording.
- **The Conversation page control in the real shell** (needs
  `omarchy-restart-shell`). Seen only in `preview.sh`, where the click wrote
  the key.
- **Several agents speaking**: the crew path (`_send`, `_turn`, a goodbye
  over a working turn, the undo window for another agent) is held by tests
  only.
- **Labelling the 3 near-miss transcripts**:
  `python3 bench/commands_scan.py --sample /tmp/m4-sample.jsonl`, set
  `meant`, then `--labels`. The default stays `edges` until then.

## Going back

`bin/agentvoice-deploy --install d4c209f9ba78` from the clone, then
`omarchy-restart-shell` for the QML. No stored data changes:
`commandsInSentences` sits unused in shell.json, and is only written if the
control is touched. An older build ignores it: commands fire only when said
on their own, `agentvoice commands` does not exist, and there is no undo.

## Open issues, for the next phase

1. **Question 4 taken by default: `edges`.** The measured false triggers
   were 0 for both `edges` and `clause`, so they do not favour `clause`.
   Labelling the 3 near-misses at stop 1 could change that.
2. **Codex credits overspent again**: 32.81 against ~17 (below). Both passes
   wrote long answers (pass 2: 57,677 tokens). **188.39 left for M5–M29**,
   about 7.5 per phase. Next phases should cap the findings in the prompt
   (say, "at most 8, most severe first") and send only the code diff.
3. **Pass 2's fixes were not reviewed by Codex.**
4. **An exact "goodbye" over a working turn** (several agents) still lets
   that turn open its follow-up window when it ends. This is pre-existing,
   and `alone` must stay the old behaviour, so it was not changed. Question:
   fix it for the exact path too?
5. **A request finishing just as the screen locks is still sent** (the 2 s
   lock poll). Pre-existing. Only commands now ask afresh.
6. **"Cannot tell" whether something records (no pw-dump) counts as not
   dictating**, as for lending the microphone. Should a command refuse
   instead?
7. **A broken `agentvoice.toml` with a readable shell.json**: the daemon
   reads `alone` (settings not readable), and the page shows the shell.json
   value. Pre-existing for every guarded setting.
8. **"…, goodbye" says "Goodbye." before answering the rest**, the plan's
   order. It might read better after. Question for stop 1.
9. **A continued chat inside a sentence does not say which chat** (fixed
   sentence). "Continuing <title>." would tell the user which one was
   picked. Question.
10. **Without punctuation the rules are narrow** ("I'll take notes and keep
    listening" does not fire). Whisper punctuates nearly always; worth a
    look in the labelled sample.
11. **`speak()` calls `poll_session()` from the run loop**, which takes the
    command file. Pre-existing; not investigated whether it ever dropped a
    command.
12. **`agentvoice commands` prints phrases as matched** ("dont stop
    listening", "thats all"). The pages in M24 and M26 may want them spelt
    with apostrophes.
13. **M2 open issue 2** (saying the agent's name in open mic stops its turn)
    is still open; M4 did not touch the wake word.
14. **Carried, still open**: the Voice library trash icon (M25); M0's small
    test and bench fixes; agy's `carries_session_across`; the runner's
    sandbox test command (`codex sandbox linux -- true` panics).

## Codex credits used

**32.81** (221.20 at the end of M3 → 188.39, read from the session logs'
`rate_limits.credits.balance`; the first call of this phase also read
221.20, so nothing came in between):
- pass 1: **14.89** (221.20 → 206.30). `gpt-6.2-astra`, medium effort,
  sub-agents disabled, read-only copy, the code diff only (1,388 lines):
  48,519 tokens.
- pass 2: **17.91** (206.30 → 188.39). The same, pass 1's fix diff only (574
  lines): 57,677 tokens.

**188.39 left** for M5–M29.

## Live checklist: what was said, what happened

- After the install: `agentvoice commands --json` on the installed build
  gave mode `edges`, 10 commands, wake phrases main/Theo "theo", sora/Sora
  "sora", jarvis-ajc/Hazel "hazel".
- Typed to Sora (`agentvoice type sora`): "Reply with the single word OK,
  and keep listening." She answered "OK" (agent 5.5 s, first token
  1385 ms). The open mic stayed off; the journal held only `⌨ typed` and
  the timing line (logSpeech off, no `command:` line). A typed sentence is
  not read for a command, as designed.
- Nothing said by voice; no shell restart; no settings changed.
