# Notes: voice commands skill and command list

Written 2026-11-19. Notes only; nothing is built yet.

## What was asked

1. **A skill for the agent.** It should teach the agent running inside Agent
   Voice the built-in phrases and commands (handoff, open mic, new chat,
   goodbye, and so on). Then it can tell the user exactly what to say, or
   run the matching `agentvoice` command itself, instead of guessing.
   Prompted by the terminal handoff: it worked, but the agent had to read
   the source to find the phrase.
2. **A list of trigger words and commands for the user.** Either a README
   section, a section on the About page, or both.

## Where things live today

- Spoken phrases: `daemon/speech_text.py`. Each one has to be the whole
  transcript, after lowercasing and dropping punctuation.
  - Stop the reply (`_STOP_PHRASES`): stop, stop talking, stop it, cancel,
    cancel that, never mind, be quiet, shut up, that's all, forget it, abort.
  - Goodbye, which ends the conversation and goes back to the wake word
    (`_GOODBYES`): goodbye, bye, bye bye, see you, talk to you later, I'm
    done, we're done, good night, and others. "Okay, thanks," in front of
    one still counts (`_GOODBYE_LEAD`).
  - Stop every agent (`_FULL_STOPS`): full stop, stop everything,
    everybody stop, stop all, emergency stop, all stop.
  - New chat (`_NEW_CHATS`): new chat, start a new conversation, fresh
    chat, and similar.
  - Continue a saved chat (`_CONTINUE`): "continue the chat about X",
    "resume our conversation", "go back to the chat about X".
  - Open mic (`_OPEN_MIC`): keep listening, open mic, let's talk, let's have
    a conversation, and others.
  - Close the open mic (`_CLOSE_MIC`): stop listening, mic off, go to sleep,
    wait for the wake word, and others.
  - Terminal handoff (`_HANDOFF`): "move this to the terminal", "continue in
    a terminal", "hand it over to my terminal", and similar. Handled by
    `hand_off()` in `daemon/wake_listen.py`.
- Wake phrases come from settings, one per agent (Theo, Sora, Hazel), so the
  list has to be read at build time, not written in by hand.
- Still to find: the yes and no words for the permission prompt, dictation
  phrases, and how a name in front of a request picks an agent.
- CLI (`bin/agentvoice`): start, stop, toggle, mic, interrupt, talk, lock,
  unlock, locked, open-mic on/off, wake-test, type, talk-end, permit,
  pending, calibrate, monitor, voice, chats (continue, new), endpoint,
  history, status, is-active.
- Existing skill: `daemon/omarchy_skill.py` writes a Claude Code plugin
  folder with `skills/omarchy/SKILL.md`. The Claude adapter loads it with
  `--plugin-dir` for its own process only. Backends that load no skill get a
  shorter text in their instructions (`instructions_text`). The daemon
  rebuilds it when `stale()` says so.
- README: has "Input modes", "Saved conversations", "More than one agent"
  and "Mute, not stop", but no single list of phrases.
- About page (`pages/AboutPage.qml`): only "What is installed",
  "Maintenance" and "Remove". No command list.

## Ideas for when it is built

- Put the new skill next to the Omarchy one, in the same generated plugin
  folder (for example `skills/agentvoice/SKILL.md`), so it needs no new
  loading path. Add the short version to `instructions_text` for Codex and
  the other backends.
- Generate the phrase lists from the sets in `speech_text.py` rather than
  copying them, so the skill, the README and the About page can't drift
  from the code. A test could hold them equal.
- Include the agents' wake phrases from settings.
- The skill should say what the agent can't do itself. For example, a
  handoff started from inside a turn stops that same turn, so the agent
  should tell the user the phrase rather than trigger it.
- If `stale()` only hashes `omarchy_skill.py`, it should also cover the
  phrase sets, so a changed phrase rebuilds the skill.

## Open questions for the user

- README, About page, or both? The About page could show a short list with
  a link to the full README section.
- Should the skill let the agent run `agentvoice` commands (for example
  `agentvoice open-mic on`) directly, or only tell the user what to say?
