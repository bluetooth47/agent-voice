# Phase 5 (plan.md Phase E): open mic and terminal handoff

Written 2026-11-18. Branch `phase-e`, cut from `phase-d` at 0a05908, so it
carries Phases A to D too. Commit 1c75562, pushed to `fork/phase-e` only.
Not installed, not merged.

`./bin/agentvoice-check`: green, 1557 tests (was 1489).

## 11. Open mic

- **Start:**
  - say "keep listening", "let's keep talking", "open mic" or "stay
    listening";
  - or use the popup's new **Open mic** tile (`agentvoice open-mic on`);
  - or turn on **Open the mic after every wake** (`openMicAuto`, off).
- **Stop:**
  - say "stop listening", "go to sleep", "goodbye" or "full stop";
  - or use the tile;
  - or mute, lock the screen or lend the microphone out;
  - or let **Closes after** (`openMicIdleMin`, 10 min, 1–60) pass with
    nothing said.

  A plain "stop" stops the reply and leaves the mic open.
- It stays with the agent it was started for. Naming another agent passes
  it over (`pass_open_mic`).
- **Visible:** the bar icon is the theme's accent colour while it is open.
  The readout and popup say "OPEN MIC · THEO · 8 MIN LEFT", and the tile
  shows the minutes. The daemon publishes `open_mic: {who, id, until}`.
- **Only answer if it's meant for you** (`openMicAddressedOnly`, on):
  - a turn heard without a name goes with `OPEN_MIC_PREAMBLE`, asking the
    agent to reply SKIP if it wasn't said to it;
  - a SKIP is never spoken, published or kept;
  - it costs one agent turn for each thing heard.
- How it works:
  - `Daemon.open_mic_due()` is asked whenever the loop is waiting for the
    wake word. It opens a capture of kind `"open"`, whose wait is the time
    left;
  - anything said resets that time (`touch_open_mic`);
  - in crew mode, `_due_follow_up` works with conversationMode off as long
    as the mic is open.

## 3. Terminal handoff

- Say "move this to a terminal" (also "open it in the terminal", "continue
  in a terminal", "take this over to a terminal" and similar). It works
  after a turn, or during one once the wake word has stopped it. `hand_off()`
  then:
  1. stops the turn and cancels the warm process (it would hold stale
     context);
  2. runs `setsid uwsm-app -- xdg-terminal-exec --dir=<agent folder> claude
     --resume <id>` (Codex: `codex resume <id>`). The id is checked against
     `[A-Za-z0-9][A-Za-z0-9_-]{7,79}` and passed as argv, never through a
     shell;
  3. says "Moved to a terminal." and closes the open mic if it was this
     agent's.
- While any process has that id on its command line, voice stays out of
  the chat. A turn to that agent gets "That chat is open in a terminal. Say
  new chat to start another one, or close the terminal first.", and
  `prime_agent` starts nothing. "New chat" lets go of it.
- When the terminal closes, the next turn resumes the chat, with what was
  typed there.
- Gemini, Antigravity, Copilot and endpoints refuse, with a spoken reason.
- Saved chats get `terminal` (a timestamp). The conversation view says "went
  on in a terminal …".

## Not done / caveats

- Not live-tested. No QML preview (the screen was locked). qmllint passed.
- The "meant for you" check relies on the model replying exactly SKIP. If it
  writes "SKIP." or "Skip", the match still catches it. A model that
  explains itself instead gets spoken.
- Plan.md asked for a minimum utterance length on the open mic. Not added:
  the normal `minUtteranceMs` applies, and the SKIP check is the main
  guard.
- The handoff assumes the terminal's `claude --resume` keeps the same
  session id (it does without `--fork-session`). Check this in the live
  test.

## Live checklist

1. Install and restart the shell (QML changed).
2. "Theo, keep listening." It answers "I'm listening…". The bar icon turns
   the accent colour and the readout says OPEN MIC. Ask two things with no
   wake word.
3. Talk to someone else in the room (or play a video). It should stay
   silent: "(open mic: not meant for it)" appears in the journal.
4. "Sora, what time is it?" (open mic for Theo). Sora answers, and the open
   mic is now Sora's.
5. "Stop listening." It answers "Okay…" and the icon goes back. Open it
   again from the popup tile and let it time out (set Closes after to 1
   min).
6. "Theo, move this to a terminal." A terminal opens in the project folder
   with the chat. Then "Theo, what were we doing?" should get "open in a
   terminal". Type something in the terminal, close it, and ask Theo about
   it.
