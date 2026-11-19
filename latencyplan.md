# Cutting dead time between prompt and spoken reply

Written 2026-11-18 against e331d31 (installed).

## What the numbers say

The last 25 turns in the journal (`heard → spoke` lines), warm Claude:

| span | typical | worst |
|---|---|---|
| pause (end of speech → endpoint) | 1.1–1.7s | 2.1s |
| whisper | 0.0–0.1s | 2.8s |
| claude warm (sent → first text) | 1.5–4.5s | 80s (tool turns) |
| first sentence | 0.0–0.7s | |
| **voice (sentence ready → first sound)** | **0.5–3.3s** | **5.8s** |

The "voice" span is the gap you notice: the text is already on screen and
then nothing plays. Its cause, measured with Piper on this machine:

| voice | 5 chars | 46 chars | 158 chars | speed |
|---|---|---|---|---|
| ryan-high (main agent) | 0.2s | 1.1s | **3.6s** | ~2x realtime |
| amy-medium | 0.08s | 0.25s | 0.7s | ~13x |
| lessac-medium | 0.08s | 0.35s | 0.7–1.0s | ~8–12x |

Piper renders a whole sentence before it gives back any audio, so the first
sound waits for the full first sentence to render. `answer()` publishes the
text and then calls `speak()`, which synthesizes and then plays.

There is a second gap the latency line never shows. Synthesis and playback
take turns: sentence 2 doesn't start rendering until sentence 1 has finished
playing. With ryan-high that puts a pause of 1–3.6s **between every
sentence**. Each sentence also opens a new PortAudio stream (27–48ms) and
takes the floor again.

## The plan, in order

### 1. Measure the parts (small, do first)
- Break `voice` into floor wait, chime settle, synthesis, stream open and
  first write, so `report_latency` shows where the time goes.
- Add `gaps` to the line: total silence between sentences after the first
  sound. This is what step 2 fixes, and nothing measures it today.
- `bench/tts/`: replay recorded replies through `Speaker` offline and report
  time to first audio and gaps per voice. No microphone or Claude quota
  needed.
- Find out why some turns log `claude warm 0.0s`.

### 2. Render ahead while speaking (biggest win)
- One `Speaker` session per reply: one output stream for the whole reply,
  plus a synthesis worker thread that renders sentence N+1 (and beyond)
  while N plays. Playback stays on the one thread, which keeps the "one
  thread drives PortAudio" rule in `Speaker.say()`. The worker only runs
  onnxruntime and never touches PortAudio.
- `answer()` feeds sentences into the session as they arrive from Claude
  instead of blocking on each `speak()`.
- Stopping, barge-in, the lock watch and the floor all keep their current
  places: the watch still runs between 50ms slices, and stopping also drops
  the rendered queue.
- Expected: gaps between sentences fall to about 0 for any voice faster than
  realtime (ryan-high is about 2x, so it keeps up).

### 3. Keep the text in step with the voice
- Show a sentence when its first audio plays, not before it's rendered.
  After step 2 that delay is usually small, but the text should never run
  ahead of the voice.
- With no speaker, text shows right away, as it does today.

### 4. A short first chunk (cuts time to first sound)
- When the first sentence is long, split it at a clause break (comma,
  semicolon, colon, dash) after about 4 words. The opening goes to Piper on
  its own: with ryan-high, about 20 characters render in 0.3–0.5s instead of
  1–3.6s. Step 2 renders the rest while it plays.
- Split very long later sentences (more than about 140 characters) the same
  way, so rendering stays ahead.
- Tests in `test_speech_text.py`, and listen for prosody at the joins
  (Piper may lower the pitch at a split as if the sentence ended).

### 5. A short opening from the agent
- Add a line to the voice system prompt: start with a short sentence that
  answers or acknowledges, then give detail. A short first sentence shows up
  sooner as text and renders in a fraction of a second. Check it against
  bench/narration's recorded turns before turning it on.

### 6. Voice cost is visible
- Show each voice's measured speed in the voice library ("ryan-high: 1.1s
  for a short sentence"). After steps 2 and 4, a high voice should only cost
  a few hundred ms up front. If it still costs more, the user can see that
  and pick.
- Try onnxruntime thread settings for Piper (intra-op threads); the daemon
  shares 8 cores with whisper and sherpa.

### Out of scope for now
- The 1.1–1.7s pause: `trailingSilenceMs` is set to 1600 on purpose. Lower
  `quickEndMs` instead if it bothers you.
- Sending to Claude on partial transcripts: it saves time but risks answering
  a sentence you hadn't finished.

## Expected result
A typical warm turn today: 1.3 pause + 2.5 claude + 1.2 voice ≈ 5s, plus
1–3s between sentences. After steps 2–4: the voice span drops to about
0.3–0.5s, and the pauses between sentences mostly go away.

## Process
New branch `latency-2` from `test-fixes`. Run `./bin/agentvoice-check`
before each commit, push only to `fork`, and install last (installing
restarts the daemon and kills a running turn).
