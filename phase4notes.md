# Phase 4 (plan.md Phase D): progress talk

Written 2026-11-18. Branch `phase-d`, cut from `phase-c` at cde8eb3, so it
carries Phases A to C too. Commit 0a05908, pushed to `fork/phase-d` only.
Not installed, not merged.

`./bin/agentvoice-check`: green, 1489 tests (was 1478 before the narration
tests, 1393 at the end of Phase C).

## What it does

- **Talk while it works** (Conversation page): Off / Brief / Detailed,
  **default Off**. Plan.md asked for your approval of the wording before
  audio was wired. You said to carry on, so it is wired but off. One click
  turns it on.
- **Quiet before it says anything** (`narrationSilenceS`, 7s, 3–30).
- Each agent's card has its own choice ("Same as main" by default). Changing
  it keeps the conversation.
- The HUD shows the line in the reply slot while it is said. It is not part
  of the saved reply.

## How

- `daemon/narration.py`:
  - `describe()` turns a tool call into words through a fixed table.
  - `compose()` groups bursts ("I've looked through six files and run two
    commands.").
  - `Narrator` handles the timing:
    - 7s of quiet first, then gaps of 10, 15 and 25s;
    - only while a tool is running;
    - only about a kind of activity the last line did not cover;
    - never the same sentence twice;
    - never what the agent just said itself;
    - never once the agent is writing words.
- Privacy:
  - `.env`, `~/.ssh`, `~/.gnupg`, keys, tokens and `auth.json` become "a
    config file";
  - a command line is never read out, only what it is for ("running the
    tests"), or its description at Detailed;
  - a command that sets or sends a key is "a command";
  - a finished line that still looks like a key is dropped.
- Adapters:
  - Claude's parsing is now `claude_code.parse_line()`, the same code for a
    live turn and the replay. It adds `Chunk.activity` (name, input, id, and
    whether a helper ran it) and `Chunk.tool_done`.
  - Codex: `codex.activity_chunks()`.
- Reply loop (`Daemon.answer`):
  - With narration on, the stream is read on a thread (`Ticker`), which
    yields `TICK` while the stream is quiet so a line can be said.
  - A line yields to the agent's words at the next audio chunk
    (`speak(cut=...)`) and never takes the floor from another agent
    (`_floor_busy`).
  - A Ticker left mid-turn cancels the agent, as closing the generator used
    to.
- Also fixed: the qmllint failure in `Chats.qml` that Phase C left (the
  recorded check run in c04 caught it).

## Measured (FINDINGS §29)

31 recorded turns (29 Sonnet, 2 default model), 125 tool calls. Lines were
said in 8 turns, 9 lines in all. No repeats, no invented lines, no secrets.
One line was cut by the agent's next sentence at Brief and two at Detailed.
Plan.md's target was zero cuts, so this is not quite met: a cut happens at a
word break, and the answer is never spoken over.

Half the turns end inside 8.7s, so most need nothing. Claude with the voice
preamble already talks between most tool calls. Narration mostly fills long
command runs (checks, tests) and helper work.

## Not done

- **Codex is not recorded**: its usage limit lasts until Nov 27.
  `activity_chunks` is tested against the known event shapes. Re-run
  `python bench/narration/record_turns.py --only x01 x02 x03 x04 x05` then.
- c30 and c32 are not recorded (Claude's 5-hour limit cut the batch short).
- No QML preview: the screen was locked the whole time. qmllint passed.
- Not live-tested.
- Seen in the recordings, not fixed: two text blocks from separate messages
  join without a space ("…once they finish.The crew.py review…"), so
  `iter_sentences` reads them as one sentence. This affects live turns too.
  Small follow-up in `parse_line`.

## Live checklist

1. Install (`install.sh --yes`) and restart the shell (QML changed).
2. Conversation → Talk while it works → Brief.
3. "Theo, run the checks and tell me if they pass." After about 7s of
   quiet, "I'm running the checks." (unless Theo already said so), then
   nothing until the answer.
4. "Theo, use a subagent to look at how the permission hook works." A line
   about the helper's reading.
5. Detailed: "Theo, read noise_floor.py and explain it". File names said as
   words.
6. Agents → Sora → Talk while it works → Off. Sora stays quiet; Theo still
   talks.
