# Benchmark findings

Measured 2026-09-21 on the development machine: MacBookPro11,5 (2014),
i7-4980HQ, 4 cores / 8 threads, AVX2 without AVX-512, 16GB, no usable ML GPU.
Corpus: 17 clips, 98s, read aloud by the project author into the built-in
laptop microphone.

These numbers describe *this* machine. Re-run `bench/` anywhere else before
trusting them.

## 1. Custom vocabulary beats model size, decisively

A fourteen-word `initial_prompt` outperforms a six-times-larger model at a
sixth of the latency.

| config | overall WER | domain WER | perceived latency |
|---|---|---|---|
| whisper tiny.en | 9.8% | 27.2% | 317ms |
| **whisper tiny.en + vocab** | **4.9%** | **9.9%** | **358ms** |
| whisper small.en, no vocab | 7.8% | 18.6% | 2165ms |

Confirmed independently through Voxtype's whisper.cpp (f16 rather than
faster-whisper's int8, so absolute numbers differ, conclusion does not):
tiny.en 11.0% -> 6.5% with the prompt; base.en + vocab lands at 6.9%.

Custom vocabulary is therefore a first-class component, not a tuning detail.
It ships as `daemon/vocab.txt`, overridable at `~/.config/agentvoice/vocab.txt`.

## 2. Ordinary speech is already solved; jargon is the whole problem

WER by category, no vocabulary prompt:

| engine | short | plain | domain | long |
|---|---|---|---|---|
| vosk-small | 10.0% | 2.5% | **39.2%** | 10.5% |
| whisper tiny.en | 0.0% | 0.0% | **28.2%** | 2.6% |
| whisper base.en | 0.0% | 1.2% | **25.1%** | 2.6% |
| whisper small.en | 0.0% | 2.6% | **18.6%** | 2.6% |

tiny.en scores 0.0% on conversational speech. Every remaining error is a
proper noun. No engine at any size transcribed `kubectl` correctly:
"cook controlled", "coupe control", "koop control", "Koopkertrol".

## 3. Rank on perceived latency, not real-time factor

Vosk consumes audio while you are still speaking, so only the tail remains
when you stop. Whisper cannot start until the utterance ends, so its whole
run is dead air. whisper-tiny has the **better** RTF (0.13 vs 0.23) and **ten
times** the perceived latency (317ms vs 30ms -- the no-vocab figure from the
table in §1; this paragraph said 323ms, which is the RSS number from §6).
Published RTF rankings pick the wrong engine for this workload.

Voxtype's `whisper.eager_processing` ("transcribe overlapping chunks while you
are still speaking") is the mitigation and is untested here.

## 4. TTS has margin to spare

| engine | short reply | 190-char paragraph | RTF |
|---|---|---|---|
| espeak-ng | 6ms | 15ms | 0.002 |
| piper lessac-low | 18ms | 332ms | 0.034 |
| **piper lessac-medium** | **22ms** | **438ms** | **0.045** |

22x faster than realtime. Piper returns `first_audio == total` on most lines,
meaning it synthesises a whole utterance before yielding — so sentence
splitting must happen in the daemon, not be delegated to Piper.

## 5. Two hardware realities

**Thermal throttling.** `package_throttle_count` reached 13,471 during these
runs. Back-to-back sweeps pushed small.en from 2165ms to 6283ms while WER held
constant. Sustained inference degrades this laptop 2-3x, so a long voice
session gets slower. Budget for it.

**Microphone gain.** ALSA `Capture` shipped at +12dB, clipping 1.46% of samples
at a normal speaking distance. Accuracy survived it, but install-time gain
calibration belongs in the product. `record.py` now refuses to accept a clipped
clip silently.

## 6. Packaging

The whole stack imports into one process on Arch's system Python 3.14:
pacman's `python-vosk` alongside wheel-installed `faster-whisper` and
`piper-tts`, via a venv built with `--system-site-packages`. onnxruntime and
ctranslate2 both publish cp314 wheels. No AUR package is required for the
benchmark.

---

# Later findings (2026-09-22)

Same machine. These supersede parts of the section above.

## 7. The energy gate was destroying the wake word

openWakeWord builds embeddings over a sliding window of *contiguous*
audio. The daemon dropped every frame below the microphone gate before the
detector saw it, which fragments the phrase. Measured over twelve recordings
of the author saying "hey jarvis", one persistent detector, fed as the daemon
feeds it:

| gate | frames kept | detected |
|---|---|---|
| -36 dBFS | 30% | 9/12, two scoring ~0.07 |
| -44 dBFS | 33% | 11/12 |
| **none** | **100%** | **11/12, every peak 1.00** |

openWakeWord is now fed every frame. The gate still guards the Vosk grammar,
which genuinely needs it, and still decides when a turn has ended.

## 8. A grammar cannot reject a phonetic neighbour

Vosk's grammar must choose between the phrase and `[unk]`, so a near miss maps
onto the phrase at full confidence. Measured:

| grammar | attack | score |
|---|---|---|
| "hey claude" | "hey cloud" | **1.00** |
| "hey codex" | "hey kodak" | **1.00** |
| "hey pi" | "apple pie" | 0.89 |
| "hey hermes" | "hey herbie" | **1.00** |

No confidence threshold can fix this; there is nothing to threshold.
openWakeWord scores the same class of attack at 0.898 against 0.996 for the
real phrase, which *is* separable — at 0.90.

Correction: that 0.90 is a statement about the **pretrained** phrases only, and
it shipped as the default for every model including ones you train yourself,
where it is unreachable. See §15.

## 9. The personal verifier earns its place

Both detectors fed identical live audio, eleven utterances:

| | fired | mean peak |
|---|---|---|
| with verifier | 11/11 | 0.963 |
| base model | 11/11 | 0.987 |

Then twelve held-out other-speaker clips — six Piper voices at synthesis
parameters outside the training range:

| | accepted | mean peak |
|---|---|---|
| with verifier | **0/12** | 0.134 |
| base model | 8/12 | 0.718 |

So it costs 0.024 of headroom on the owner's voice and rejects every
other-speaker clip the base model would have let through. That is the whole
argument for openWakeWord's extra 154MB.

Caveat: the other speakers are synthetic, and the verifier was trained on
synthetic negatives from the same voices at different parameters. So the
attribution above -- 8/12 accepted against 0/12 -- is a result about TTS
output.

Corrected 2026-10-04: a real stranger at the microphone is no longer untested.
Six utterances, none acknowledged, with the owner waking it first try in the
same session. That result is end-to-end rather than attributable, for the
reason §17 gives, so neither finding supersedes the other: this one says what
the verifier contributes, and §17 says what happens to a person.

## 10. Memory, and what it costs to hold

| component | RSS |
|---|---|
| whisper `tiny.en` | 323 MB (indifferent to `cpu_threads`) |
| openWakeWord + scipy + sklearn | 179 MB |
| Vosk model | 114 MB |
| Piper voice | 48 MB |

The daemon idles near 594 MB with only the models in use. Releasing a model
needs `malloc_trim(0)` as well as dropping the reference — glibc otherwise
keeps the arenas and RSS barely moves (Vosk: 67MB freed on the drop, 117MB
after the trim).

CPU is not a concern: openWakeWord inference is 2.97ms per 80ms frame, 3.7%
of one core, and the whole daemon idles at 5.3%. `vad_threshold` does not
reduce that — it runs Silero VAD *after* the predictions and adds ~22%.

## 11. Barge-in is a hardware problem, not a software one

One microphone about a foot from the speaker it is listening to, at the
machine's normal listening volume (70%). Two separate questions, opposite
answers.

**Does the detector false-fire on our own speech?** No, at any volume.

| playback volume | bleed median | bleed p90 | mic absmax | wake score |
|---|---|---|---|---|
| 30% | -45.6 | -44.0 | 1733 | 0.001 silent |
| 50% | -43.7 | -36.4 | 4982 | 0.001 silent |
| 70% | -37.3 | -27.3 | 16537 | 0.001 silent |
| 100% | -29.5 | -18.1 | 32733 | 0.000 silent |

Listening while talking is safe. (At 100% the microphone input clips —
absmax 32733 — so full volume is a bad idea for other reasons.)

**Can it hear you over our own speech?** No, and the reason is a level
problem, not a model problem. Our own playback reaches the microphone at
the same loudness as the user's voice:

| condition | bed level | SNR | fires | median peak |
|---|---|---|---|---|
| quiet room | — | — | 19/20 | 0.95 |
| over our own reply | -32.6 dBFS | +1.2 dB | 5/20 | 0.44 |
| AEC, converged | -44.8 dBFS | +13.4 dB | 19/20 | 0.93 |

Levels are the 75th-percentile frame — the speech, not the pauses —
because SNR is the quantity that survives a change of speaker volume or
microphone gain, and both knobs move.

How much SNR the detector needs, sweeping a scaled bleed bed:

| SNR | +30 | +24 | +18 | +12 | +6 | 0 | -6 |
|---|---|---|---|---|---|---|---|
| fires /20 | 19 | 18 | 12 | 11 | 9 | 5 | 1 |

Reliable detection wants ~+24 dB. Reality at a normal volume is +1.2 dB,
a deficit of about 23 dB. A trained interrupt phrase would be swamped
identically — the failure is acoustic masking, not vocabulary — so the
hermes-satellite approach of training a second phrase does not transfer
to a machine with one microphone.

### SNR alone does not predict detection

The converged canceller scores 19/20 at +13.4 dB, while a *scaled* bleed
bed at +12 dB scores 11/20. Same SNR, very different outcome: what the
canceller leaves behind is decorrelated from the wake word and overlaps
its spectrum far less than speech-shaped bleed at equal level. Masking is
spectral, so any level-only rule of thumb here will mislead.

### The echo canceller works, with two caveats worth the space

`pactl load-module module-echo-cancel aec_method=webrtc` removes ~12 dB of
the active bleed level (median -37.3 to -45.9, p90 -27.3 to -43.7, absmax
16537 to 1296) and restores detection completely. Two things nearly made
this measurement a lie:

*The stock settings destroy the signal while looking like a triumph.*
webrtc's noise suppressor and AGC are on by default. They drop the median
bleed to -67 dBFS — an apparent 31 dB win — while clipping transients to
full scale (absmax 32768) and gating the wake word to **0/20**. Reporting
the median alone would have inverted the conclusion. Pass
`analog_gain_control=0 digital_gain_control=0 noise_suppression=0` and
leave the canceller alone to do its actual job.

*It converges slowly.* Over 45s of continuous far-end audio:

| elapsed | median | p90 |
|---|---|---|
| 0-9s | -44.7 | -29.0 |
| 9-18s | -47.0 | -41.1 |
| 18-27s | -47.7 | -46.3 |
| 36-45s | -49.1 | -46.8 |

The p90 improves ~18 dB but takes ~30 seconds. A spoken reply is five to
ten. Whether the filter stays converged across a session of many short
replies is untested, and is the open question that decides whether
acoustic barge-in is buildable here.

So: half duplex, with an explicit interrupt on a keybind. `agentvoice
interrupt` (SIGUSR2) cancels the speaker and the agent, and is a no-op
when the daemon is idle.

**Method note.** A first pass at this was wrong in two ways, both of the
same kind. The machine's volume had been turned down and later muted while
the measurements ran, so one "cancelled" bed was really silence and the
canceller appeared perfect; and levels were summarised as medians, which
is exactly what hid the full-scale clipping under AGC. Every number above
was re-measured at a known, verified volume with audio confirmed present,
and levels are reported as distributions. Detection figures come from
mixing recorded bleed into clean wake clips: that models the echo adding
linearly and does not exercise webrtc's double-talk suppressor, so the
converged AEC figure is an upper bound. Replaying wake clips through the
speaker instead was tried and rejected as a method — the round trip costs
so much fidelity that even a quiet room scores 3/6, leaving no headroom to
measure anything.

## 12. What each agent CLI can actually be asked to do

Version currency on 2026-09-22, against `mise latest`:

| CLI | installed | latest |
|---|---|---|
| claude | 2.1.278 | 2.1.278 |
| gemini | 0.60.0 | 0.60.0 |
| codex | 0.154.0 | 0.155.1 |
| agy (Antigravity) | — | 1.2.8 |

Nothing here is stale. The question is not age but capability, and it
differs enough per backend that one permission model cannot cover them.

### Verified by running the binaries

- **Claude Code** — PreToolUse hook via `--settings`, receives the pending
  call on stdin and blocks on the verdict. The only backend that can turn a
  spoken request into a question on screen. `--permission-prompt-tool`, the
  documented flag for exactly this, is accepted, loads the MCP server, and
  is never consulted.
- **Codex** — `codex exec --json`, four-line envelope, `thread_id` resumes
  and genuinely carries context. No interception point: withholding
  `--approve-for-me` leaves it at `approval: never`, `sandbox: read-only`.
- **Gemini** — one-shot, no session handle. Withdrawn for individual Code
  Assist accounts in June 2026; an AI Studio API key still drives the same
  binary, which is a paid, per-token arrangement rather than a plan.
- **Antigravity (`agy` 1.2.8)** — installed and its flags read off the
  binary, but not run: a turn needs a Google login. Every documented
  headless flag exists verbatim, except `--print-timeout`, which the docs
  give as 5 minutes and the binary as `0s`, meaning wait forever.

### Why Antigravity is the interesting one

It is the only backend whose own surface expresses what agentvoice's
permission levels mean, rather than collapsing them to safe-or-trusted:

    --mode plan | accept-edits     read-only, or edits without asking
    --add-dir <path>               scope the workspace to the project
    --sandbox                      terminal restrictions
    --dangerously-skip-permissions the trusted level, named honestly

Access matters more than features here. Antigravity CLI is included at
every tier including free, on a personal Google account, which is the
arrangement an Omarchy user is likely to have -- where Gemini now wants a
billed API key.

**It has PreToolUse hooks, and they cannot grant.** The decision vocabulary
is richer than Claude's (`allow`, `deny`, `ask`, `force_ask`,
`deny_unless_prior_grant`), but in headless mode `allow` is ignored: the
hook fires, returns valid JSON, raises no error, and the call is denied
anyway. Upstream issue #1053, open against 1.2.7. A hook there can restrict
and never permit, so it cannot be the thing that asks -- the same shape of
trap as `--permission-prompt-tool`, and worth re-testing before any adapter
depends on it.

## 13. `--add-dir` adds to a workspace; it does not restrict to one

Antigravity was given the `edits` level on the strength of its flags:
`--mode accept-edits` with `--add-dir <project>` reads exactly like "files
in the project change without asking". Tested on 2026-09-23 against agy
1.2.8, it is not:

    project:  /tmp/.../proj      --add-dir points here
    target:   /tmp/.../outside/target.txt
    prompt:   "write CHANGED into <target>, then say done"

    result:   status SUCCESS, "Done. Updated target.txt"
    target:   CHANGED

Repeated with `allowNonWorkspaceAccess: false` in
`~/.gemini/antigravity-cli/settings.json` -- the setting the docs describe
as restricting access outside project directories -- with the same result.
The workspace had also been trusted wholesale at login
(`trustedWorkspaces: ["$HOME"]`), which is the likeliest reason, and
there is no per-invocation flag that restricts: `--sandbox` is terminal
restrictions, not file ones.

So the level was withdrawn. Our `edits` means *inside the project*, and the
same screen shows Claude Code honouring exactly that, so a user would read
across. A permission name that means one thing on one row and something
broader on the next is worse than having one fewer option.

Two locks, because a stored setting outlives the reasoning behind it: an
adapter only accepts a level it still declares, and the flag is chosen
defensively at the call site as well.

**What would bring it back:** a demonstration that writes outside the
project are refused. That is a measurement, not a reading of the flags --
the flags said it already.

## 14. Latency, across every backend that has answered

Measured 2026-09-23, same prompt ("In two short sentences, what is a wake
word?"), wall clock from request to last token.

| backend | model | time | tools |
|---|---|---|---|
| Groq | qwen/qwen3.8-27b | 0.19s | no |
| Groq | openai/gpt-oss-20b | 0.40s | no |
| OpenAI | gpt-4o-mini | 1.9s | no |
| Codex | gpt-5.6-terra | 2.8s | yes |
| xAI Grok | grok-4.20-reasoning | 3.23s | no |
| xAI Grok | grok-4.7 | 4.57s | no |
| Ollama (Mac mini, LAN) | qwen3:4b | 7.6s | no |
| Antigravity | default | 12.2s | yes |

For a voice interface this is the ranking that matters, and it does not
line up with capability. The agentic CLIs are doing more -- a session, a
sandbox, tools -- and pay for it. A chat endpoint has none of that and
answers before the speaker has finished the wake-word chime.

Groq being forty times faster than a 4B on local hardware is worth
sitting with: the bottleneck for local inference is not the model size,
it is that the machine is also doing everything else.

**Cloudflare blocks urllib.** Groq answers `403, error code 1010` to
`Python-urllib/3.13` and `200` to the identical request carrying a named
User-Agent. Every Groq model was unreachable until the adapter identified
itself, and the failure looks like an auth problem rather than a client
one. Assume any provider behind Cloudflare does the same.

**Grok is not Groq.** Keys tell them apart: `xai-` is xAI's Grok, `gsk_`
is Groq the inference provider. A `gsk_` key sent to `api.x.ai` returns
"Incorrect API key provided", which reads like a bad key rather than the
wrong company.

Omarchy supports the first and has never heard of the second:
`omarchy default agent grok` installs `npm:@xai-official/grok`, and
`groq` appears nowhere in its tree. So the fastest backend measured here
is reachable only through the endpoint adapter -- which makes that path
the route to a class of providers the desktop has no concept of, rather
than a fallback for exotic cases.

Reasoning models are worth checking individually rather than per
backend: `grok-4.20-0309-reasoning` and `qwen3:4b` both leaked nothing,
but a model that emits its thinking would have it read aloud verbatim.

## 15. A locally trained wake model cannot reach the default threshold

`owwThresholdPct` defaults to **90**, which §8 justifies with the
pretrained phrases (§8): `"hey jarvis"` peaks 0.996, a phonetic attack 0.898.
That number does not transfer to a model you train yourself, and nothing said so.

Measured against 25 recordings of the owner saying `"hey claude"`, made by
`agentvoice-train-verifier` on this machine's microphone, using a `hey_claude`
model trained through LiveKit's notebook:

| threshold | raw model | with the owner's verifier |
| --------- | --------- | ------------------------ |
| 0.90      | 1/25      | **0/25**                 |
| 0.80      | 4/25      | 8/25                     |
| 0.73      | 5/25      | 17/25                    |
| 0.63      | 5/25      | 19/25                    |
| 0.50      | 10/25     | 19/25                    |

Peak score with the verifier: min 0.005, **median 0.775**, max 0.868. So at the
shipped default the wake word fires on none of the owner's own recordings. The
reported symptom was not a wake word that misfired; it was a microphone
indicator that never lit, with no log line to explain it, because nothing had
happened.

**The lead-in matters, and nearly produced the opposite conclusion.** Fed from
a reset, the same 25 clips give a median of **0.069**, not 0.775, and 0/25 at
every threshold down to 0.30. openWakeWord scores from a rolling buffer of 16
embedding frames, about 1.3s; a 2.0s clip fed cold spends most of itself
filling that buffer. Measuring that way would have blamed the trained model.
Two seconds of silence in front of each clip is the honest condition, because
live audio never stops. Any future measurement of a wake model here must do
the same.

`agentvoice-train-verifier` now measures this and offers a threshold, since it
has the recordings in hand. Clips below 0.2 are excluded as not containing the
phrase at all: 6 of the 25 scored 0.005, and counting them as evidence for a
lower threshold drove the first version of the suggestion to its floor, which
would fire on a television.

Unmeasured, and not implied by any of the above: whether this verifier rejects
a *different* person saying the phrase. Every number here is about waking for
the right one.

**Correction, next day.** Every figure above was taken against a verifier
trained on four contrast clips from one synthesised voice, because fetching
other speakers was silently broken -- `spin()` ran its command through
`exec`, which cannot run a shell function, so every voice download failed and
reported only "could not fetch". With that fixed, the same speaker and the same
`hey_claude` model, retrained against twelve clips from three voices:

| threshold | raw model | with the new verifier |
| --------- | --------- | -------------------- |
| 0.95      | 1/25      | 22/25                |
| 0.89      | 5/25      | **25/25**            |
| 0.80      | 13/25     | 25/25                |

Peak with the verifier: min **0.935**, median **0.963**, max 0.976 -- against
min 0.005, median 0.775 before. The floor moved further than the median, which
is the part that matters: nothing sits near the threshold any more.

So the earlier reading, that a locally trained model cannot reach 90, was a
measurement of the contrast set rather than of the model. Four clips from one
voice is not enough to separate anything, and a verifier fitted on it suppresses
its own speaker. The suggestion mechanism was right throughout; fed an adequate
contrast set it recommended 89, which every one of the speaker's recordings
clears.

Two things improved at once and they are not separable from these numbers
alone: the contrast set went from 4 clips/1 voice to 12/3, and the recordings
were made again -- 25 of 25 register above the noise floor now against 19 of 25,
and the raw model's median rose from 0.362 to 0.808 on the new set. The raw
column shows the recordings alone cannot account for the verifier's gain: at
0.89 the raw model still only reaches 5 of 25.

## 16. A DO_NOT_TRUST folder is escaped by a longer rule, not by a different one

Measured 2026-10-04 against gemini-cli 0.60.0, in an isolated
`GEMINI_CLI_HOME` so the machine's own answers were not touched.

| trustedFolders.json | cwd | `gemini -p` |
|---|---|---|
| `{W: DO_NOT_TRUST}` | `W/project` | exit **55** |
| `{W: DO_NOT_TRUST, W/project: TRUST_FOLDER}` | `W/project` | exit **0** |

Two things follow, and the adapter had the first right and the second wrong.

The refusal is inherited: an explicit `DO_NOT_TRUST` on a directory distrusts
every folder beneath it, so on this machine -- which has one line, home marked
`DO_NOT_TRUST` -- no project under home can run a Gemini turn. `folder_trust`
mirrored that correctly.

But `why_unavailable` told anyone in that position to set a project folder in
the settings instead, which is advice that cannot work: the new folder inherits
the same refusal. Longest prefix is what overrides it, so the fix is to trust
*that folder specifically* -- the second row above. The guidance now branches on
which refusal it is, because "nothing has been written about this folder" is
escaped by choosing a different one and `DO_NOT_TRUST` is not.

Worth noting what this does not say: with a trusted folder, Gemini answered in
10.9s on this machine the same day. Nothing is wrong with the backend or its
auth. The whole of its unavailability here is one line in a file the user wrote
deliberately, which is the outcome the review was aiming for -- agentvoice used
to set `GEMINI_CLI_TRUST_WORKSPACE=true` itself and hand every folder its own
hooks, skills and MCP servers.

## 17. A real stranger, six attempts, none acknowledged

Measured 2026-10-04, in the room, with the configuration the daemon logged at
the time: openWakeWord `hey_claude` at **0.86** with the owner's verifier,
energy gate -40 dBFS, after a from-scratch reinstall and a retrained verifier.

| speaker | utterances of "hey claude" | acknowledged |
|---|---|---|
| one person other than the owner | 6 | **0** |
| the owner, same session | 1 | 1, first try |

The owner's turn is in the journal in full -- 3.0s of audio, whisper 324ms,
first token 683ms, agent 8.5s -- and `journalctl` records exactly one wake
event in the window, which corroborates the count independently of anyone
remembering it.

This closes the gap the first of the README's open questions had been
carrying, and that §9 here left open: every previous other-speaker number came
from synthetic voices, and 8/12 accepted by the base model against 0/12 with
the verifier was a result about TTS output, not about a person.

**What it does not establish.** The verifier's own contribution. The base model
was never run against those six utterances, and they were not recorded, so
0/6 is a measurement of the stack as configured and cannot separate "the
verifier rejected them" from "the wake model never scored them above 0.86 at
all". The synthetic test could make that attribution precisely because the same
clips were replayed both ways. One speaker and n=6 is also a demonstration
rather than a rate.

So the honest claim is the end-to-end one: a stranger at this microphone, with
this threshold and this verifier, did not get in, and the owner did. The
cheapest way to earn the stronger claim is to keep the next stranger's attempts
as wavs and replay them with the verifier disabled -- which is what
`bench/record.py` is for, and which costs the stranger nothing extra.

## 18. Nine backends removed rather than shipped leaking

Measured 2026-10-16, after a marketplace reviewer declined to accept the
argv disclosure as documented-and-known.

Every agent on the shared CLI template passed the spoken prompt as a
command-line argument, where `/proc/<pid>/cmdline` is mode 0444 on an
ordinary Linux box. Moving them to stdin needed knowing which of them reads
a prompt there. Asked directly, with a prompt piped in:

| CLI | what it did |
|---|---|
| crush | crashed |
| opencode | opened an interactive TUI |
| hermes | opened an interactive TUI |
| grok | `Not signed in` |
| cursor-agent | `Authentication required` |
| muse | `workspace trust ... is undecided` |
| omp | `No default model selected` |
| pi | `No API key found` |
| openclaw | not installed -- a mise stub, per §7 of the README's risks |
| **copilot** | **ran the turn** |

So only copilot could be shown to accept a prompt on stdin, which matches
the only one whose `--help` documents piped stdin. The other nine could not
be moved without guessing, and a prompt written to a channel a CLI is not
reading is a turn that hangs until the watchdog kills it.

They were removed. None had ever answered a live turn -- the README had
called them untested since they were added -- so the cost is a shorter list
rather than lost capability, and the standing rule is now explicit: a backend
earns its place with one real turn proving where its prompt goes, or it is
not offered.

Worth noting what this says about `--help` as evidence. Nine CLIs documented
a headless `-p` form and every one of those forms was real; what no help page
mentioned was whether the same prompt could arrive privately. The flag was
never the question.

## 19. The wait after you stop talking, and where it went

Measured 2026-11-15 on the dev machine, `claude` 2.1.325, Whisper `base.en`
(the setting in use here, not the `tiny.en` default), trailing pause 1600ms.

**From the journal, 82 real turns before any change.** Median 7.6s of audio,
median Whisper 1105ms (p90 1511ms), all of it after the person had stopped.
The ~320ms in the README was short benchmark clips on `tiny.en`; real
utterances are longer. Claude's own "first token" figure was median 3133ms,
p90 7606ms -- and it is counted from when the request left, so it never
included starting the CLI.

**Starting `claude -p` per turn costs about a second.** Haiku, trivial prompt,
`stream-json` output:

| | `system/init` | first text |
|---|---|---|
| a process started for the turn | 973ms | 2255ms |
| the same, `--resume` | 1021ms | 2545ms |
| a process already running, first turn | 155ms | 1292ms |
| a process already running, second turn | 31ms | 1404ms |

That second is the CLI coming up and connecting MCP servers (desktop-control
here), every turn. A waiting process holds ~230MB RSS. `--input-format
stream-json` keeps stdin open between turns; `--resume` works with it (same
session id, history intact), and a PreToolUse hook passed with `--settings`
still fires and still blocks -- checked with a hook that denied a Bash call.

**End to end, real loop, real Whisper, real CLI.** An 8.1s two-part
utterance (Piper, with a 0.7s pause mid-way) fed to the frame loop at real
time, wake forced on the first frame, no speaker; timed from the last voiced
frame to the agent's first words:

| | run 1 | run 2 |
|---|---|---|
| before (7dd52b2) | 6.65s | 5.25s |
| after: pieces at pauses, quick end, warm claude | 2.98s | 3.00s |

After, the line the daemon now prints said `pause 1.1s · whisper 0.0s ·
claude warm 1.7s` and `pause 1.3s · whisper 0.0s · claude warm 1.6s`.
Whisper's total work went *up* -- 1634ms and 1979ms across two pieces, against
1015-1124ms in one -- because a piece cut at a pause is sometimes heard again;
none of it was waited for. The quick end fired after 1.1-1.3s rather than its
800ms because the last piece was still in Whisper until then: on `base.en`
the model's speed, not the setting, is the floor.

## 20. Saying what it is doing, and when the sounds start

Same machine and CLI as §19, Haiku, a scratch folder of three empty files.

**The sentence before a tool was spoken after it.** `iter_sentences` emits a
sentence when it sees the whitespace that follows it, and merges anything
under 20 characters forward. A text block that ends in a tool call has no
whitespace until the next block -- after the tool. With a tool call now
flushing what is waiting, a real turn spoke its plan at the instant the tool
started: 3.2s and 6.2s into the turn, each on the same timestamp as the tool
marker.

**Asked for a sentence "before using tools", Haiku gave one before every
tool call** -- two plan sentences for two tools in a one-line question. A
desktop-control session in this machine's journal made 113 screenshot calls
in one turn. Reworded to one sentence up front, no narration, one at the end:
"look at each text file one at a time" ran four tools and spoke one plan
sentence, one change of approach, and the answer.

**The sounds.** `play()` returned in 25-27ms (stream opened, playback handed
to PortAudio's thread) and the sound then ran for its full length -- 60, 160
and 290ms -- while the caller went on. The first call in a fresh process took
1429ms, which is importing sounddevice and initialising PortAudio; the daemon
has done both for the microphone before any sound is played.

## 21. On a headset, barge-in has nothing to fight

Measured 2026-11-15 on the current development machine (not the MacBook of
§11), output and input both on a Bluetooth headset: OpenRun Pro 2 by Shokz,
HFP (`headset-head-unit`), PipeWire. A Piper reply was played into the ears
while the headset's own microphone recorded, and `BargeIn` was fed what it
heard -- the same script as §11's bleed measurement.

  our own voice, as the headset mic heard it   median -180 dBFS (digital
                                               silence), peak -71.2 dBFS
  BargeIn at factor 1.1, 1.5 and 2.0           fired on our voice: never
  gate                                         -38.4 dBFS (the floor)

The headset cancels its own echo before the audio leaves it, so the 24 dB
of headroom §11 could not find is more like 100. That is the case `bargeIn`
was written for and could not be turned on for by default, because the
daemon had no way to know it was in it. Now it asks: `headset.py` reads the
default sink from `pactl` (two spawns, 23ms, done on the idle poll) and
`bargeOnHeadset`, on by default, listens over the reply when it is a headset
or headphones.

Not measured: the user's voice level *during* playback. Some HFP headsets
attenuate the microphone while they play (half-duplex echo suppression),
which would make talking over the reply harder than talking into silence.
If it does not stop for you on a headset, that is the first thing to check,
with `bargeFactor` the knob.

## 22. A two-syllable name said alone never woke

Reported as "I cannot start Sarah" (an extra agent, Vosk engine, wake phrase
"computer"). The guess was that wake words come from a fixed list. They do
not: `vosk_model_find_word` finds "sarah" (and "sara", "zara", "jarvis") in
the small English lexicon, and the daemon already refuses and explains any
name it lacks.

The real cause is the gate. Frames under `micThresholdDb` are never fed to
the grammar, so it never hears the silence it needs to finish a word, and a
name said on its own with a pause after it can only wake through a partial.
A partial needs three consecutive loud 200ms frames (600ms). "computer" is
three syllables and gets there; "sarah" does not.

Measured by synthesizing clips with both installed Piper voices (ryan,
lessac), scaling the speech to -20 and -28 dBFS over -60 dBFS noise, and
feeding them through the real `Pipeline.feed_wake` with the installed
vosk-model-small-en-us-0.15, phrase "computer", names ["sarah"], gate -38,
confidence 0.70:

| clip                     | before  | after   |
|--------------------------|---------|---------|
| "Computer"               | 4 / 4   | 4 / 4   |
| "Sarah"                  | 0 / 4   | 2 / 4   |
| "Hey Sarah"              | 0 / 4   | 4 / 4   |
| "Sarah, what time is it" | 4 / 4   | 4 / 4   |

The two misses after the fix are ryan's "Sarah", which Piper speaks in
0.20s -- one frame, shorter than anyone says it.

The fix: on the first frame under the gate after a loud run, ask the grammar
for `FinalResult()`. That carries word confidence, so the 0.70 bar applies,
which a partial never had.

The cost, on 19 other words in both voices at both levels (76 clips): false
wakes went from 12 to 19. Every one of the seven new ones is a sound-alike of
a name: Sahara and Zara (lessac, both levels), Commuter (ryan, both levels),
Sorrow (ryan, -20). The worst existing ones are unchanged and are not caused
by this: "okay" waking "computer", "sounds good", "salad" and "zero" waking
"sarah", all through the partial path, which has no confidence to check.
That path is the weaker of the two and a better place to look next.

Synthesized speech is not a person in a room, so these are relative numbers
for one change, not a detection rate.

## 23. sherpa-onnx keyword spotting against Vosk

`bench/wake_clips.py` makes
the corpus: the §22 recipe widened to all three installed Piper voices (amy,
lessac, ryan), -20 and -28 dBFS over -60 dBFS noise, 0.6s lead and 1.2s tail.
30 positive clips (five phrasings of "computer" and "sarah") and 150 negative
ones: 19 near-miss words, among them every §22 false wake, and six ordinary
sentences. `bench/wake_bench.py` scores each engine in 200ms frames from a
fresh detector. Vosk runs through the daemon's real `Pipeline.feed_wake`
(vosk-model-small-en-us-0.15, gate -38, confidence 0.70); sherpa-onnx 2.0.1
runs `KeywordSpotter`, one thread, with no gate. i7-1185G7.

| clip                        | Vosk     | sherpa gigaspeech-3.3M (defaults) | sherpa zh-en-3M (boost 0.5, thr 0.25) |
|-----------------------------|----------|-----------------------------------|----------------------------------------|
| Computer                    | 6 / 6    | 6 / 6                             | 6 / 6                                  |
| Sarah                       | 4 / 6    | 4 / 6                             | 4 / 6                                  |
| Hey Sarah                   | 6 / 6    | 6 / 6                             | 6 / 6                                  |
| Sarah, what time is it      | 6 / 6    | 6 / 6                             | 6 / 6                                  |
| Computer, open the browser  | 6 / 6    | 6 / 6                             | 6 / 6                                  |
| **false wakes**             | 63 / 150 | 15 / 150                          | 4 / 150                                |
| on the six plain sentences  | 7 / 36   | 0 / 36                            | 0 / 36                                 |
| fires, after speech ends    | -0.28s   | +0.22s                            | +0.22s                                 |
| CPU, one core               | 1.8%     | 4.4%                              | 4.1%                                   |

All three engines miss the same two clips: ryan's "Sarah", which Piper says
in 0.29s. Vosk's false wakes include "okay", "sounds good", "computation",
"competitor" and four ordinary sentences. Its confidence bar can't fix them:
0.50 gives 65, 0.90 still gives 60, because nearly all of them come through
the partial path, which has no confidence. That path is also why Vosk fires
before the word ends (the negative delay). sherpa-onnx's four remaining false
wakes are all "Sarong" heard as "sarah".

The zh-en column was tuned on this same corpus (score 0.25/0.5/1/2 against
threshold 0.15-0.5), so 4/150 is optimistic. The untuned defaults are the
honest number: 27/30 detected and 8/150 false wakes for zh-en, and the
gigaspeech column above. Threshold 0.5 removes every false wake and loses
roughly half the detections on both models. int8 and the 8-frame chunk
changed nothing worth having (the chunk costs 6.2% CPU for no earlier fire).

Footprint: the zh-en model loads in about 44MB RSS, against Vosk's 114MB
(§10). Files: a 12MB encoder (4.4MB as int8), plus the decoder, the
joiner, tokens and a 3.2MB CMU-style lexicon (`en.phone`). Keywords are
written as text and turned into phones through that lexicon, so a new agent
name needs no training. A name missing from the lexicon has the same
refusal path Vosk's `_knows` gives today.

As with §22, synthesized speech is not a person in a room. The gap is large
enough to justify adding the engine, and small enough that live testing must
decide the default.

**Wired in as `engine = "sherpa"`.** The daemon loads the model once with a
placeholder keyword: keywords given to a stream are *added* to the
constructor's file, not swapped for them, so the file holds a phone string
nobody says behind threshold 1.0. The phrase and names then go on the
stream. A new stream took 0.7ms and loading the model about 1s, so a
threshold or name change opens a stream, and only a phrase change (which
can force a Vosk fallback) reloads. Run through the daemon's own `Pipeline`
on the same corpus (`wake_bench.py daemon-sherpa`, threshold 0.25): 28/30
detected, 3/150 false wakes, 4.5% CPU. That matches the prototype's
4/150, so the stream-keyword route costs nothing. The lexicon lacks
"ziggy", so it was replaced with "otto" in the suggested agent names.

## 24. A second check for short names: Vosk and Whisper must agree

The user reported valid wakes being dropped with "theo" as the main phrase
and "sora" as an agent. Nothing in the journal showed it, because a miss
prints nothing. Measured on the §23 corpus extended for these names
(`/tmp/theo-bench`: five Piper voices at -20 and -28 dBFS, 190 clips),
sherpa-onnx at threshold 0.10 caught "Theo" 5/10, "Hey Theo" 5/10, "Sora"
3/10 and "Hey Sora" 6/10. Thresholds 0.03 and 0.10 gave identical results,
so the slider cannot fix this.

Each clip was then put through the two other engines the daemon already has:

| clip       | Vosk grammar heard it | Whisper base.en heard it first |
|------------|-----------------------|--------------------------------|
| Theo       | 10/10                 | 10/10                          |
| Hey Theo   | 9/10                  | 9/10                           |
| Sora       | 10/10 (as "zora")     | 8/10                           |
| Hey Sora   | 8/10 (as "zora")      | 10/10                          |
| Video      | 8/10 as theo          | 0                              |
| Cleo       | 7/10 as theo          | 0                              |
| Leo / Neo  | 5/10, 4/10 as theo    | 0                              |
| Story      | 10/10 as zora         | 2/10 as sora                   |
| Sorry      | 7/10 as zora          | 0                              |

Vosk's lexicon has no "sora". Of the spellings it does know, "zora" heard
Sora 10/10. "soar a" and "sore a" heard it 3/10, and "laura" and "torah"
fell somewhere in between. Whisper was prompted with "Theo, Sora." and
counted only when the name opened the transcript, after an optional "hey".

Each engine wakes on the other's mistakes but rarely on the same one, so the
rule is that both must name the same agent. This runs only on a burst of
speech 0.3-2.6s long that sherpa-onnx let pass. A name Vosk cannot hear at
all is left to Whisper alone, and only when the transcript is the bare name.
Whisper is skipped when Vosk heard nothing and every name has a Vosk vote,
so background talk costs a grammar pass (about 100ms) and no transcription.

Through the daemon's own `Pipeline` (gate -46 dBFS, sherpa at 0.10):

| clip        | spotter alone | with the second check |
|-------------|---------------|-----------------------|
| Theo        | 5/10          | 10/10                 |
| Hey Theo    | 5/10          | 8/10                  |
| Sora        | 3/10          | 6/10                  |
| Hey Sora    | 6/10          | 10/10                 |
| Cleo        | 2/10          | 2/10 (the spotter's)  |
| Story       | 0/10          | 2/10                  |
| all others  | 0             | 0                     |

The cost is time. faster-whisper pads every clip to its 30s window, so a
half-second burst takes 0.8-1.7s to transcribe, with tiny.en no faster than
base.en. A wake through the second check therefore lands about a second
later than a spotter wake. Frames queue while it runs, and the queue is
unbounded, so nothing said in that second is lost. It is setting
`wakeCrossCheck`, on by default, and it keeps the Vosk model resident
(114MB, §10) on the sherpa engine. Synthesized speech again: the live miss
rate decides whether it earns its keep.

## 25. What Whisper writes for "goodbye" and "full stop"

2026-11-17. Piper (ryan, amy, lessac medium; en_GB alan medium) said each
phrase, padded with 0.25s silence before and 0.5s after, transcribed by
faster-whisper base.en (int8, beam 1, vocab.txt as the prompt) -- the
user's configured model.

- "Full stop." / "Full stop!" came back as the words in 8 of 8 clips
  ("Full stop", "Full stop.", "Full stop!"), never as a bare ".". Safe to
  match on.
- "Stop everything" and "Everybody stop": 4/4 each, as words.
- "Goodbye": 4/4. "Bye bye": 4/4, written "Bye bye" or "Bye-bye".
  "See you later": 4/4. "Okay, thanks, goodbye" and "That's all, goodbye":
  4/4.
- "Bye." alone: 3/4. Ryan's came back as "Die!", so a bare "bye" can miss;
  "goodbye" is the one to say.

Synthetic voices, no room noise: this says the transcripts have the right
words, not how often a real "goodbye" across a room gets through.

## 26. The automatic wake test, first run, and "full stop" as a keyword

2026-11-17, i7-1185G7, the user's live settings: sherpa-onnx zh-en-3M at
threshold 20%, short-name boost 150%, second check on with both engines
voting, Whisper base.en, gate -27 dBFS. `daemon/wake_auto.py` (the
automatic test) fed each clip through its own Pipeline: five Piper voices
(alan, amy, lessac, ryan-high, ryan-medium), speech at -16 and -24 dBFS RMS
over -60 dBFS noise, engine state reset between clips. 100 clips, 92s.

| said | woke it | by the spotter | by the second check |
|---|---|---|---|
| "Theo." / "Hey Theo." | 15/20 | 3 | 12 |
| "Sora." / "Hey Sora." | 16/20 | 8 | 8 |
| "Full stop." (keyword) | 8/10 | 8 | — |

False wakes: 0 of 50 clips (Video, Leo, Cleo, Story, Sorry, Okay, Thank
you, Rodeo, "Hello there", a sentence; at -16 dBFS). The distractor list
has since gained "Bus stop", "I'm full" and "Pull up", which this run did
not include.

The first live manual test reported 0 tries and 0 wakes in 90s, and the
page showed nothing at all. The page half is found: the daemon deleted
wake-test.json at start, and the page's file watcher, set up while the file
was missing, never fired once it appeared. The file now always exists, and
the page also re-reads it every second while open. The 0 tries is not
explained: the daemon's timer ran, so frames reached the test, but nothing
crossed the -27 dBFS gate for long enough to count. The test now reports
the loudest frame against the gate, so the next run says which.

Synthetic voices: compare settings with these, not your own rate.

## 27. A gate that follows the room, and live text that turns into Whisper's

2026-11-17, i7-1185G7, branch `phase-b`. Both benches use synthetic audio:
compare settings with them, not as the rates you will get.

### The adaptive gate (`bench/gate_bench.py`)

Six synthetic rooms, each 40s of the bed alone and then, in shuffled
order, requests, wake names and sound-alikes at -26 dBFS speech: a quiet
room (white noise, -62), a fan (pink, -46), a loud fan (pink, -36, above the
shipped fixed gate), music (synthesized chords, -42), a TV (one low-passed
Piper voice with gaps, -42) and people talking (three of those, -40). Three
Piper voices, 15 requests per room (two with a 0.5s pause mid-sentence), 12
wake clips ("Theo.", "Hey Theo.", "Sora.", "Hey Sora."), 18 sound-alikes.
The live wake engine (sherpa-onnx, second check, both engines). The fixed
gate is the shipped -38; the adaptive one learns as the daemon does, from
every frame outside a capture. Margin 10 dB. Endpointing is the run loop's
energy rule with a 1.2s pause: "on time" ends within a second of that.

The first version took the floor as the 10th percentile, so it sat in the
gaps. Beside the TV that put the gate at -51, under the TV's own speech,
and held 6 of 6 turns open (`--quick`, two voices). Three percentiles, run
side by side:

| floor | TV turns held open | rooms worse than fixed on wakes |
|---|---|---|
| 10th percentile | 6/6 | TV (2/8 vs 7/8) |
| 30th | 0 | music (6/8 vs 7/8) |
| median | 0 | none |

Those three ran in parallel, and the second check timed out now and then
under the load, so their wake counts are rough. Everything below ran alone.

The median at full size beat the fixed gate on every turn, but lost wakes:
TV 8/12 against 11/12, people talking 8 against 9, music 10 against 11.
The gate, 6 to 8 dB higher there, cut the quiet syllables out of a short
name, and the second check's bursts came up short. So the wake word's own
checks (the second check's bursts, the Vosk grammar) now use a gate
`WAKE_SLACK_DB` = 6 dB lower than the one that ends a turn. With that:

| room | gate | adaptive at | turns on time / late / held open | wakes | false wakes |
|---|---|---|---|---|---|
| quiet room | fixed | -38 | 15 / 0 / 0 | 12/12 | 0/18 |
| | adaptive | -52.0 | 15 / 0 / 0 | 12/12 | 0/18 |
| fan | fixed | -38 | 15 / 0 / 0 | 11/12 | 0/18 |
| | adaptive | -36.7 | 15 / 0 / 0 | 12/12 | 0/18 |
| loud fan | fixed | -38 | 0 / 2 / 13 | 1/12 | 0/18 |
| | adaptive | -26.9 | 15 / 0 / 0 | 9/12 | 0/18 |
| music | fixed | -38 | 5 / 10 / 0 | 9/12 | 0/18 |
| | adaptive | -34.1 | 15 / 0 / 0 | 10/12 | 0/18 |
| TV | fixed | -38 | 12 / 3 / 0 | 10/12 | 0/18 |
| | adaptive | -31.5 | 15 / 0 / 0 | 10/12 | 0/18 |
| people talking | fixed | -38 | 4 / 6 / 5 | 8/12 | 0/18 |
| | adaptive | -29.7 | 15 / 0 / 0 | 10/12 | 0/18 |

No turn was cut off and no request was missed in any room, either way.
396s. At least as good as the fixed gate in every room on every measure,
which is the bar the plan set; it still ships off by default until it has
been tried in a real room. The fixed gate's own wake counts move by one or
two between runs of identical audio (quiet room 10/12 in one run, 12/12 in
the next), so a difference of one is noise; the loud fan is not.

### Accurate live text (`bench/live_text_bench.py`)

Six requests with one to three parts and 0.7s pauses, two Piper voices, at
-24 dBFS. Frames through the daemon's own `hear()` at real time, with the
real Vosk recogniser and Whisper base.en on its worker.

- Fallbacks (Whisper's text replaced by Vosk's again): **0** in 12.
- Pause to swap: median **0.78s**, max 0.98s.
- Last text on screen equal to the transcript sent: **12/12**.
- Updates on screen per request: median 13.5.

The run before showed 11/12: Vosk made "the" out of the silence after the
last pause, and it stayed on screen behind Whisper's finished text. The open
rough segment is now hidden until somebody speaks after a cut.

## 28. What a saved chat costs

i7-1185G7, 2026-11-17, `daemon/chats.py` on the home SSD, while the
installer box was downloading in the background (so if anything these are
high). Synthetic chats of ten exchanges each (12-word requests, 40-word
replies), timed with `perf_counter` over 30 records and 5 searches:

| saved chats | one turn recorded (median / max) | "continue the chat about …" search |
|---|---|---|
| 100 | 6.7ms / 9.4ms | 59ms |
| 500 | 12.6ms / 18.2ms | 188ms |

A record rewrites the chat file and the index under a lock, after the reply
has been spoken, so nobody waits for it. The search reads every chat of that
agent, which grows with the count but stays well under the time it takes to
say the reply. Off by default: with `saveChats` off, nothing above runs and
nothing reaches the disk (`test_chats.py::test_nothing_is_written_with_saving_off`).

## 29. Progress talk, replayed against recorded turns

i7-1185G7, 2026-11-18. `bench/narration/record_turns.py` ran 31 real Claude
Code turns (29 on Sonnet, 2 on the default model) in throwaway clones of
this repository, with the voice preamble, and kept each stream-json line
with the millisecond it arrived. `bench/narration/replay.py` puts each one
through `claude_code.parse_line`, `iter_sentences` and `narration.Narrator`
on the recorded clock. Speech lengths are estimated at 2.75 words a second,
so the timings of spoken sentences are estimates, not measurements.

| | brief | detailed |
|---|---|---|
| turns / tool calls | 31 / 125 | 31 / 125 |
| turn length, median / longest | 8.7s / 121s | same |
| turns of 15s or more | 10 | 10 |
| progress lines said | 9, in 8 turns | 9, in 8 turns |
| repeats, invented, secrets | 0, 0, 0 | 0, 0, 0 |
| cut off by the agent's next sentence | 1 | 2 |

What the recordings changed:

- **Most turns need nothing.** Half end within 8.7s, before seven seconds
  of quiet has passed, and Claude with the voice preamble already says a
  sentence between most tool calls.
- **Only while a tool is running.** The first version also spoke between
  tools. In c16 its line started two seconds before the answer and was cut
  off by it, because the model had already been writing the answer.
- **Not what the agent just said.** "Running the project's check script
  now." followed by "I'm running the checks." was the first line the replay
  produced. A line whose words the agent's last sentence already covered is
  dropped now.
- **A helper's work is the helper's.** "I've started a helper" used to
  come after the line about the helper's reads. Now the start is told only
  when nothing else has happened yet.
- **Long web queries are not read out.** An eight-word query took five
  seconds to say and ran into the answer. Up to six words are said.

The cuts that remain happen at the next chunk of audio, a word break, so
the answer is never spoken over. Plan.md's target was zero; one line in
31 turns (two at detailed) is the honest result.

Codex: not recorded. The account hit its usage limit (until Nov 27), so its
activity parsing (`codex.activity_chunks`) is tested against the event shapes
its adapter already handles, not a recording. Gemini, Antigravity, Copilot
and endpoints stream no tool events, so they get no progress talk.

## 30. What the terminal handoff costs a turn

i7-1185G7, 2026-11-18. While an agent's chat is in a terminal, each turn to
that agent first checks whether any process still has the session id in
its arguments (`session_held_elsewhere`, a read of every
`/proc/<pid>/cmdline` this user can see). With 286 processes running, it
took a median of **4.1ms**, max 5.1ms, over 30 runs. It runs only for an
agent whose chat was handed to a terminal, and stops for good once the
terminal is closed.

Nothing else in Phase E was measured. The open microphone and the handoff
are tested for what they decide (`tests/test_open_mic.py`, 68 tests), not
yet in a room.


## 31. Desktop tools, the Omarchy skill, and endpoints per agent

i7-1185G7, Omarchy 4.5.0-3, Claude Code with `--model haiku` for every
turn below (the cheapest model that runs tools), 2026-11-18.

**Desktop tools (`daemon/desktop_mcp.py`).** Starting the server, the MCP
handshake and the tool list take a median of **94ms** (max 96ms, 10 runs):
the price added to a cold agent start when `desktopTools` is on. A real
`list_windows` against the live Hyprland took 116ms.

Two real Claude turns through `--mcp-config`:

| turn | asked | what happened |
|---|---|---|
| no hook, `--allowedTools list_windows` | count the windows | answered "1", 5.4s, 3 turns |
| hook as Sora (level "ask"), timeout 4s | `list_windows`, then `notify` | list allowed with no card; `notify` asked, nobody answered, denied twice; 28.7s |

The second turn also showed Claude's `ToolSearch` being asked about,
because every MCP tool is deferred and loaded through it first. It only loads
a schema; the tool it loads is judged when called. Now in `NO_EFFECT`.

Also found in that turn, by accident: a hook command with its spaces
stripped (a mistake in the test harness, not the adapter) let `notify`
through, with no card at all. It is the fail-open
CLAUDE.md describes: a hook that cannot start is a non-blocking error.
The adapter quotes the command, and `test_permission_hook` holds that.

**The Omarchy skill (`daemon/omarchy_skill.py`).** Built from
`omarchy commands --json` (425 commands, 145 kept from everyday groups) and
`hyprctl binds -j` (162 described bindings without the media keys): a
27KB SKILL.md, plus a 5.9KB list for backends that load no skill. Building
it takes about 1s, mostly `omarchy commands --json`.

The same question with and without `--plugin-dir`, Skill tool only:
"the exact command to silence notifications, to copy text out of a screen
region by OCR, and to show the weather as a notification".

| | silence | OCR | weather | time |
|---|---|---|---|---|
| with the skill | `omarchy toggle notification silencing` | `omarchy capture text` | `omarchy notification weather` | 6.1s, 3 turns |
| without | `omarchy-toggle-notification-silencing` | `omarchy-cmd-ocr` (does not exist) | `notify-send … wttr.in` | 8.1s, 1 turn |

3 of 3 exact with it, 1 of 3 without. With `--tools ""` both runs gave
identical, generic answers (makoctl, tesseract, curl). That is no evidence
either way: without the Skill tool a skill cannot load, so that comparison
says nothing about the skill. A voice session has its tools, so it is the
first table that applies. A question about something common (the
scratchpad) was answered correctly with and without, so the gain is in
the commands an agent would otherwise have to guess.

**Endpoints.** Not measured with a real turn this time: no endpoint key is
on this machine and no local server is running. Running llama.cpp's server
from its release build was attempted and refused by the session's
permission rules. The presets offered are the four from §14, which did
answer real turns. The thinking filter, the URL clean-up, the connection test
and the model list are tested against a real HTTP server on localhost
(`tests/test_endpoints.py`).

## 32. The editor, the browser, Hyprland's Lua dispatch, and a second mouse

i7-1185G7, Hyprland 0.56.2 with Omarchy 4.5's Lua config, VS Code 1.146
with the Claude Code extension 2.1.327, 2026-11-18.

**A bug from §31 the stubs could not see.** Hyprland with a Lua config reads
`hyprctl dispatch X` as Lua, so `hyprctl dispatch closewindow
address:0x…` is a syntax error ("')' expected near 'address'"). Phase F's
focus, move, close and workspace tools all used that form, and so did the
skill's scratchpad lines. The unit tests had passed because the stub
`hyprctl` answers "ok" to anything. The tools now send the Lua form first
(`hl.dsp.window.close({ window = "address:0x…" })`) and fall back to the
old one, as Omarchy's own scripts do. Against the real compositor: focus
"done", close "ok", scratchpad toggled and back "ok". The skill picks its
spelling from whether `~/.config/hypr/hyprland.lua` exists.

**Editor tools** (`open_in_editor`, `show_changes`), against the real
desktop with `code` as Omarchy's default editor:
- `open_in_editor calc.py line 4 col 7` opened VS Code at that line.
- `show_changes` on a scratch repo with one edited file opened a VS Code
  diff of HEAD against the working copy. The HEAD copy is written to
  `$XDG_RUNTIME_DIR/agentvoice/diffs/` (0700, file 0600).

**`--ide` was not shown to work, so it is not offered.** VS Code was opened
three times on a scratch folder. Each time the extension (auto-updated to
2.1.327 on the first start) never activated: no line in the extension host
log and no `~/.claude/ide/*.lock`, which `claude --ide` needs to find the
editor. Without a lock file there is nothing for a voice session to connect
to, and the repo rule is one real turn before a feature ships. Worth
retrying once VS Code has been restarted by hand after the update.

**The browser.** Claude in Chrome was not connected during this session
(Chrome was not running), so the browser rule has no real turn yet. What it
decides is tested (`tests/test_desktop_tools.py`: 13 consequential
actions, 10 ordinary ones, at Trusted, through a chat grant).

**A second mouse (plan 12c spike).**
- (c) **Hyprland has no second pointer.** Its binary implements
  `zwlr_virtual_pointer_manager_v1`, which drives the seat's one pointer,
  and nothing for more than one seat. `hyprctl devices` lists one pointer.
  ydotool works the same way, through `/dev/uinput`. Either one moves your
  cursor.
- (a) **Acting without the pointer works.** Window commands (hyprctl Lua
  dispatch), the editor (`code --goto`, `--diff`) and the browser (Claude
  in Chrome drives the page through the extension, not the OS pointer) all
  act with the pointer where you left it. `hyprctl cursorpos` read
  `971, 1977` before and after the window and editor runs above. The ghost
  cursor prototype (`bench/spike/ghost/`) is a Quickshell overlay-layer
  surface with an empty input region and no keyboard focus. It drew over
  the real desktop (screenshot checked) and the cursor did not move.
  Click-through was not measured, because that needs a pointer event, which
  is what this avoids.
- (b) A headless monitor for the agent was not tried. Option (a) needs no
  second output, and clicks there would still borrow the one pointer.

**Decision:** option (a). The agent acts through commands. Where it acts on
screen, it is shown by a ghost cursor on the overlay layer. The real pointer
is never moved, and `ydotool` is never used for the agent. The overlay is
the next thing to build. It needs a source of "where": a window's centre
for the desktop tools, and the click coordinates of a browser action,
which arrive in the tool input the hook already sees.


## 33. Phase 8 baselines: preamble, latency, start cost, and what each backend can take

i7-1185G7 (8 threads), 2026-11-19, the installed `dev` build `2eeb919`,
`claude` 2.1.328, `codex-cli` 0.170.0, Whisper `base.en`, trailing pause
1600ms, sound on a Shokz OpenRun Pro 2 (Bluetooth headset). These are the
numbers the agent-folder phases (merged plan, Phases 9 to 16) must not make
worse. Raw runs and summaries: `bench/baselines/phase8.json`.

**Tests.** `./bin/agentvoice-check` green, **1763 passed** before Phase 8
added any (Plan B's figure, confirmed).

### What each backend is handed today

`bench/preamble_size.py`, the real settings (Omarchy skill on, no main
instructions). Tokens are characters / 4 and only for comparison.

| backend | preamble chars | ~tokens |
|---|---|---|
| claude | 856 | 214 |
| codex, gemini, agy, copilot | 6,837 | 1,709 |
| endpoint (chat or agent) | 856 | 214 |

| agent | program | instructions | preamble chars |
|---|---|---|---|
| main (Theo) | claude | 0 | 856 |
| sora | claude | 24 | 957 |
| jarvis-ajc (Hazel) | codex | 0 | 6,837 |

The parts: spoken style 856, the instructions header 75, and for the four
CLIs other than Claude the Omarchy skill's short form (`omarchy_skill.
instructions()`, the command list filtered for a backend with no skill
loader) at **5,979**. Endpoints get none of it. That short form is the
finding: it reaches Codex, Gemini, Antigravity and Copilot on every turn and
is four times the plan's 1,500-character budget for a skills index and three
times the 2,000 allowed for instructions. Claude gets the skill as a plugin
instead: 319 characters of front matter always, the 27,122-character file
only when it decides to read it. Phase 11 should give the others the same
progressive-disclosure shape (name, one line, path) or a budget of its own,
and say which.

### Latency, controlled: send to first text (`bench/start_bench.py`)

Each agent built as the daemon builds it: its program, model, effort,
permission level (Sora at Ask keeps her hook; Theo and Hazel are Trusted),
id, standing instructions, desktop tools, Chrome and the Omarchy skill. In
an empty scratch folder rather than the agent's project, prompt "Reply with
the single word OK", 20 runs each. Every run produced text and no warm run
fell back to cold. Sora's set ran in the final harness, which also counts a
turn that errors after text as failed (none did). Theo's and Hazel's ran in
the first one: same level (both are Trusted) but Hazel's desktop server was
not given her id, and an error after text would not have been noticed.
Timed from `send()` to the first chunk with text: the part a bigger preamble
can slow, and the instrument the Phase 11 gate is judged on.

| agent | start | median | p95 | min | max |
|---|---|---|---|---|---|
| main (Claude Opus, medium, trusted) | cold | 3.36s | 4.68s | 2.83s | 5.81s |
| main | warm | **2.21s** | **3.37s** | 1.64s | 4.81s |
| sora (Claude Haiku, low, ask) | cold | 1.76s | 2.19s | 1.60s | 2.43s |
| sora | warm | **0.73s** | **1.08s** | 0.64s | 1.19s |
| jarvis-ajc (Codex gpt-6.2-sol, medium, trusted) | fresh | **3.33s** | **4.22s** | 2.90s | 5.10s |
| jarvis-ajc | resume | 3.37s | 4.13s | 2.71s | 5.08s |

- **A cold start costs about 1.1s on both Claude models** (Haiku 1.76
  against 0.73, Opus 3.36 against 2.21). That is the price a Phase 15 task
  turn or a Phase 16 side question pays when it cannot use a warm process,
  and it matches §19's "about a second" for the CLI coming up and
  connecting MCP.
- **Codex has no warm path here**: every turn is a new `codex exec`, and
  resuming the session costs the same as starting one (3.37 against 3.33).
- **What 20 runs can resolve.** Bootstrapping each set against itself, the
  median of 20 runs moves by ±60ms for Sora, ±480ms for Opus and ±355ms for
  Codex, at 95%. Forty runs give ±39, ±395 and ±235ms; eighty, ±27, ±320 and
  ±170ms. A 150ms gate on the median can be judged on Haiku and on nothing
  else measured here. Most of Opus's spread is the model, not the CLI, so
  more runs barely help. The p95 gate is no better: an unchanged build
  trips it in about a third of 20-run Opus pairs and a fifth of Codex
  pairs. The plan's acceptance table now judges both gates on Sora,
  interleaving old and new builds, and holds the other two to their noise
  range.
- Sora was first run at Trusted by mistake (the bench forced
  `ask_permission=False`; Codex's review caught it). At Trusted: warm 0.71s
  median, 0.87s p95; cold 1.83s and 2.26s. At her real Ask level the median
  is the same and the tail longer. Theo and Hazel are Trusted, so their runs
  were already at their own level.
- Five-run smoke versions before `--agent` existed (default models,
  Trusted: Haiku cold 1.79s, warm 0.57s; Opus 4.16s, 2.30s; Codex 3.82s
  fresh, 3.14s resume) are summaries only, kept in the JSON.

### Latency, real use: end of speech to first word (`bench/turn_latency.py`)

From the journal's own `heard → spoke` line (a reply only shown, `heard →
showed`, is left out), attributed by the follow-up line printed after the
reply, else by the line that started the capture. Names are taken only from
the daemon's own start-up lines, so nothing said can be echoed. These turns
were whatever was asked, tool runs included, so the spread is the user's
day, not the code's:

| window | agent | turns | median | p95 | wake turns | wake → word median | p95 |
|---|---|---|---|---|---|---|---|
| build `2eeb919` | Theo | 30 | 5.9s | 11.5s | 5 | 11.7s | 14.8s |
| build `2eeb919` | Hazel | 16 | 11.6s | 31.0s | 4 | 15.6s | 22.8s |
| build `87ce8e7` | Sora | 26 | 5.2s | 17.6s | 10 | 10.6s | 156.9s |
| Nov 15 to 19, all builds | Theo | 264 | 8.6s | 25.1s | 39 | 14.8s | 36.8s |
| Nov 15 to 19, all builds | Sora | 53 | 4.9s | 25.6s | 21 | 10.7s | 37.5s |
| Nov 15 to 19, all builds | Hazel | 26 | 8.4s | 13.4s | 6 | 14.6s | 22.8s |

- No turns on `2eeb919` were attributed to Sora; `87ce8e7` is her most
  recent build with 20 or more. Hazel has 16 on `2eeb919`, fewer than 20.
- 35 turns over the whole window could not be attributed (`?`), mostly
  nameless wakes while other agents were configured.
- **Wake to first word includes the request itself**, because the user is
  talking between the two. It is derived (the `audio` line's time plus the
  printed spans after transcription), to the journal's resolution. The 157s
  p95 is one real turn whose printed end-to-word was itself 144.4s (journal,
  2026-11-16 20:07:34, build `87ce8e7`).
- Two agents answering at once on the same adapter can still be confused:
  the journal has no turn id to join on.
- **20 controlled voice turns per agent were not run.** That needs someone
  talking, and the user chose not to (2026-11-19). S covers the part these phases change, and these journal figures
  are the real-use check (J in the plan's acceptance table), never the gate.

### What each backend can take (the Phase 8 matrix)

Read from source by Codex (`file:line` for every cell) and spot-checked
here; "turn" marks what a real turn has shown (this file, a phase note, or a
replayed recording), everything else is from source and not run.

| backend | working folder | instructions reach it by | resumes | Agent Voice MCP / plugin dir | restrained at ask · edits · trusted by | cancel | native `SKILL.md` |
|---|---|---|---|---|---|---|---|
| Claude Code | process cwd (turn) | `--append-system-prompt-file`, or the constant style inline (turn) | warm process, else `--resume` (turn) | both (turn) | hook · hook (in-project edits silent) · browser hook only, and only with `browserTools` on | SIGTERM to the process group | yes, via the generated plugin (turn) |
| Codex | process cwd | `with_preamble` on stdin | `exec … resume <thread_id>` (turn) | MCP via `-c mcp_servers`, no plugin dir | Codex defaults, observed read-only (turn), plus `--guard` **only if desktop tools are on** · no separate edits · `--approve-for-me`, no guard | SIGTERM to the process group | unknown; Phase 13 needs one real turn |
| Gemini | process cwd; folder trust checked there (turn) | `with_preamble` on stdin, `-p ""` | no, one-shot (turn) | neither | `--approval-mode plan` · none · `yolo` | SIGTERM to the process group | unknown |
| Antigravity | process cwd, `--add-dir` (turn) | `with_preamble` in one stream-json message | `--conversation <id>` (id from a recorded turn) | neither | `--mode plan` · withdrawn, falls back to ask · `--dangerously-skip-permissions` | SIGTERM to the process group | unknown |
| Copilot | process cwd | `with_preamble` on stdin (stdin from a turn) | no | neither | CLI defaults (`--allow-all` stripped) · none · `--allow-all` | SIGTERM to the process group | unknown |
| endpoint | none (HTTP) | a `system` message | client-side replay of in-memory history | neither | nothing here can restrain it | close the response; the server may keep going | no |

So only Claude Code and Codex can **start** collaboration (they take the
MCP server); every reachable agent can **receive** it. No backend was
cancelled for this matrix; that column is from source.

**Found by reading for the matrix** (not fixed in Phase 8, which writes no
product code):

- **A Codex main agent would lose its conversation on every idle poll.**
  `reconcile_agent` keeps the adapter only when
  `getattr(agent, "ask_permission", None) == want_ask`
  (`daemon/wake_listen.py:2070`), and `Codex` and `Gemini` never set
  `ask_permission` (Codex keeps `full_auto`), so the check is always false:
  the adapter is rebuilt and `session_id` set to `None` every refresh.
  Nobody here runs Codex as the main agent (Theo is Claude; Hazel is an
  extra agent, rebuilt by `reconcile_crew` only when her whole spec dict
  changes), so it has not been seen. The fix is one attribute on each
  adapter and a test that a refresh keeps the session.
- Codex below Trusted with desktop tools **off** has no Agent Voice
  restraint at all beyond Codex's own defaults; the `--guard` comes with the
  desktop server. `crew_mcp.py` must carry its own.


## 34. What watching the agent folders costs the idle poll

i7-1185G7, 2026-11-19, Phase 9. The daemon now checks the agent and
communal folders on every idle poll (`agentfs.stamp()`: an `lstat` of each
tracked file and its history folder, no reads), and re-reads them only when
a stamp changed (`agentfs.summary()`). With eight agents, the communal
folder and one skill each, 200 runs: `stamp()` **median 1.48ms, max
2.15ms**; `summary()` median 10.0ms, max 16.9ms over 50 runs. With no
folders at all, which is every machine until Phase 10 creates them, the
check finds nothing, logs nothing and publishes nothing.

## 35. Phase 11: what the folder pieces cost a turn, and whether the roster earns its place

i7-1185G7, 2026-11-19, Phase 11, `claude` 2.1.328. Each agent's preamble
now carries, in this order, the communal rules and defaults, its
personality, its instructions, the Omarchy commands and a roster of the
other reachable agents (merged plan, 3.6). On this machine the folders are
the empty templates, so only the roster is new: two lines, about 200
characters. Preambles (`bench/preamble_size.py`, and the daemon's own log
line, which agree): main 856 → **1057**, sora 957 → **1158**, jarvis-ajc
6,837 → **7036**. With every folder empty and no other agent the preamble
is byte for byte 2eeb919's, for all seven backends and 84 combinations
(`tests/test_preamble.py` against `tests/fixtures/preamble/2eeb919.json`).

**Send to first text** (`bench/start_bench.py --variants`, interleaved run
by run in one session so drift hits each alike; 20 runs per variant, no
failures). `none` is the Phase 10 preamble, `folders` what the daemon now
assigns, `full` every budget filled with synthetic text (rules, defaults
and personality 1500 each, instructions 2000, eight roster lines of 380):

| | none | folders | full |
|---|---|---|---|
| sora (Haiku, ask) cold, median / p95 | 1.86 / 2.18s | 1.84 / 2.03s | 1.88 / 2.14s |
| sora warm | 0.69 / 0.85s | 0.64 / 0.70s | 0.76 / 0.91s |
| main (Opus, trusted) cold | 3.33 / 4.46s | 3.37 / 6.46s | — |
| main warm | 2.20 / 3.45s | 2.15 / 3.08s | — |

**The gate holds.** Judged on Sora, as §33 says it must be: median +0.02s
cold and −0.05s warm with the real folders, +0.02s and +0.07s with every
budget full (gate +0.15s); p95 at most +0.06s (gate 10% or 0.30s). On
main both medians are inside the ±0.48s noise of an Opus median; its cold
p95 moved 2s on one slow run, which is the noise §33 says an Opus p95 has
(it trips on an unchanged build in a third of 20-run pairs). jarvis-ajc
(Codex) was measured after Codex's usage limit lifted, with 10 interleaved
runs per variant to spare the quota: fresh 3.64 → 3.23s, resume 3.32 →
3.15s median (p95 4.42 → 3.89s, 4.09 → 3.86s). Faster, which is noise
(a 20-run Codex median moves ±0.36s on its own); nothing points to a cost.

**After Codex's review** the roster lines became escaped JSON objects
(`{"name": …, "wake_phrase": …, "role": …}`), so a name or role cannot pass
for the prompt's own words. That adds about 52 characters for two agents:
main **1109**, sora **1210**, jarvis-ajc **7088**. Each line is still cut
at 380 characters, so the `full` variant above, eight lines of 380, is
still the most the roster can add; it was not re-measured.

**The roster earns its place** (`bench/roster_check.py`, Theo, five
questions with the roster and five without; the role lines were synthetic,
given for the run only, since this machine's role files are empty). With
it, all five answers named the right agent and its wake phrase ("Hazel
handles coding and refactoring … say 'hazel'"; "Sora is built for quick,
short answers"). Without it, Theo went looking with his own tools and
found other things: another Claude session on the machine, Claude Code's
subagent types, and once said the other agents "are for searching,
planning or fetching pages". So the roster stays in the preamble.

## 36. Phase 13: what three skills cost a turn

i7-1185G7, 2026-11-19, Phase 13, `claude` 2.1.328. A Claude agent with
skills is handed a plugin folder built for it (`agent-plugins/<id>-<hash>`)
holding the Omarchy skill and its own and the communal skills; Claude Code
puts each skill's name and description in its prompt and loads the body
only when a request needs it. Codex and the other CLIs are told an index of
up to 1500 characters instead. On this machine nobody has a skill yet, so
every prompt is unchanged (main 1109, sora 1210, jarvis-ajc 7088 characters,
from the daemon's own log after install) and the argv is the same as before.

**Send to first text with three synthetic skills** (`bench/start_bench.py
--variants folders,skills`: `skills` is the real folders plus three communal
skills of about 3,000 characters each, built in a scratch data folder so no
real agent saw them; interleaved run by run). Three rounds on Sora (Haiku,
ask), the gate's agent:

| Sora | folders | skills | change |
|---|---|---|---|
| round 1 cold, 20 runs, **the test suite running alongside** | 3.05 / 3.96s | 2.78 / 4.27s | −0.27 / +0.31s |
| round 1 warm | 0.94 / 1.40s | 0.93 / 1.29s | −0.01 / −0.11s |
| round 2 cold, 20 runs, quiet | 2.05 / 4.05s | 2.23 / 3.88s | +0.18 / −0.17s |
| round 2 warm | 0.88 / 1.20s | 0.95 / 1.19s | +0.07 / −0.01s |
| round 3 cold, 30 runs, quiet | 2.00 / 3.89s | 2.03 / 2.34s | +0.03 / −1.55s |
| rounds 2 and 3 cold pooled (50) | 2.02 / 4.04s | 2.07 / 3.26s | +0.06 / −0.78s |

(median / p95.) **The gate holds**, on the quiet runs: +0.06s on the pooled
cold median and +0.07s warm (gate +0.15s), p95 lower or level (gate 10% or
0.30s). Round 2's +0.18s cold median is outside the gate on its own; round
3, run straight after with half as many runs again, shows +0.03s, and Haiku
cold starts moved by up to 2.4s between runs in all three rounds (min 1.7s,
max 4.5s), which is what a 20-run median cannot resolve to 0.15s. Round 1
is reported but not judged: the full test suite ran during its cold half.

Main (Opus, trusted), 20 runs: cold 3.27 → 3.49s median (p95 5.92 →
5.24s), warm 2.02 → 2.17s (p95 3.07 → 2.80s); both medians inside the
±0.48s noise of an Opus median (§33). jarvis-ajc (Codex) was **not run**:
Codex's usage limit was spent by the review, and with no skill on this
machine its prompt is byte for byte what it was.

## 37. Phase 14: what the notes server costs a turn

Since Phase 14 every Claude Code and Codex agent is started with one more
MCP server, `crew_mcp.py` (the notes tools), whatever `desktopTools` says.
Measured 2026-11-20 on the i7-1185G7, quiet machine, with
`bench/start_bench.py --agent sora --variants nocrew,folders`: `nocrew` is
the Phase 13 argv (the real folders, no notes server), `folders` is what the
daemon now starts; interleaved run by run. Sora is Claude Haiku at Ask, the
gate's agent (§35).

| Sora | nocrew | with notes server | change |
|---|---|---|---|
| round 1 cold, 20 runs | 1.86 / 2.39s | 1.98 / 2.47s | +0.12 / +0.08s |
| round 1 warm | 0.86 / 1.04s | 0.89 / 1.34s | +0.03 / +0.30s |
| round 2 cold, 30 runs | 1.82 / 2.49s | 1.83 / 2.33s | +0.01 / −0.16s |
| round 2 warm | 0.77 / 0.92s | 0.76 / 0.93s | −0.01 / +0.01s |
| pooled cold, 50 | 1.83 / 2.40s | 1.88 / 2.47s | +0.05 / +0.07s |
| pooled warm, 50 | 0.78 / 1.01s | 0.79 / 1.13s | +0.01 / +0.12s |

(median / p95.) **The gate holds** on the pooled runs: +0.05s cold and
+0.01s warm on the median (gate +0.15s), p95 +0.07s and +0.12s (gate 10% or
0.30s, whichever is larger). Round 1's warm p95 sat exactly on the 0.30s
line on its own; round 2 shows +0.01s. The server itself answers
`initialize` about 75ms after it is started (25ms of that is the
interpreter), so a cold start can pay up to that much while Claude Code
waits for its MCP servers; a warm process has paid it before the turn.

Main (Opus) and jarvis-ajc (Codex) were **not run**: Codex's usage limit
was spent by the review, and an Opus median's ±0.48s noise (§33) cannot
show a cost Haiku's cannot.

## 38. Phase 15: what a pass costs over a direct turn (A15-6)

Measured 2026-11-20 on the i7-1185G7 against the installed build (1cf6825),
with `bench/pass_latency.py`: each round sends one synthetic question to
the target as a direct typed turn (`agentvoice type`) and as a pass from the
main agent (`agentvoice pass TARGET --from main`), interleaved, and times
from the command returning to the target's first reply text in the state
file. Both include the daemon's poll and the target's own start. 8.5s pass
between turns so a passed turn's 7s follow-up window has lapsed (a typed
message waits for one, which is not what is measured).

| Target | direct, median (min–max) | pass, median (min–max) | pass − direct |
|---|---|---|---|
| Sora (Claude Haiku, Ask), n=5 | 0.70s (0.61–0.73) | 0.61s (0.58–0.64) | −0.09s |
| Hazel (Codex, Trusted), n=3 | 5.99s (5.38–6.14) | 5.72s (4.76–5.80) | −0.27s |

**A pass from the CLI or the sheet costs nothing measurable over a direct
turn**: the task turn runs on the target's own adapter, and the warm Claude
process is kept (both resumed the same shared-chat session here, which is
where a passed agent stays). No separate adapter instance for task turns is
needed (the plan's fallback above 5s).

**A spoken pass adds what it is designed to add**, from the live check:
the confirmation line ("Passing this chat to Sora.", about 1.8s here) and
the 3s window in which "stop" cancels -- about 4.8s before the target's turn
starts (10:05:47.45 typed, 10:05:49.25 said, 10:05:52.26 dispatched). That
is inside A15-6's 5s, just; a longer spoken line (an endpoint's host named)
would pass it, and is what the disclosure costs.

**Not measured**: voiced passes against voiced direct turns in one session
with J-style lines (the plan's form of A15-6), which needs someone talking;
and the first pass to a target with no session in the chat (the "replayed"
case: a new session, a cold CLI for Codex). §33's cold rows are that floor.
The wrong first versions of the bench read the previous turn's reply still in
the state file (0.00s rows) and then timed the follow-up window; both are
fixed in the script and none of their numbers are used here.

## 39. Phase 16: what a side question costs (A16-6)

Measured 2026-11-20 on the i7-1185G7 against the installed build (7300d9e
for the first, c47aae1 for the rest), from the daemon's own structural line
`ask <id>: <target> answered <caller> in <s>`: from the moment the side
adapter is built to the end of its answer, so it includes the CLI starting
cold (a fresh adapter, a new session, `--no-session-persistence` /
`--ephemeral`) and the whole answer, not only the first text. Questions were
one-number arithmetic, synthetic, asked by Theo through `ask_agent` in typed
turns.

| Target | n | side turn, each | median |
|---|---|---|---|
| Sora (Claude Haiku, low, Ask) | 4 | 2.7, 2.7, 2.7, 3.0s | 2.7s |
| Hazel (Codex gpt-6.2-sol, medium, Trusted) | 2 | 5.5, 7.2s | 6.4s |

**A side question costs about what §33 says a cold start costs, plus the
answer**: Haiku's cold first text is 1.76s and the whole one-word answer
lands at 2.7s; Codex's fresh first text is 3.33s and its answer 5.5–7.2s.
Over 5s for Codex, which is the plan's line for considering a warm side
process. **Not done, on purpose**: a warm side process would keep a second
Codex/Claude process alive per agent for questions that are rare, and Codex
has no warm path in this adapter at all (§33: every turn is a new `codex
exec`), so for Codex there is nothing to keep warm. The caller waits in
silence for this, its watchdog kept alive by the daemon; the time is spent
inside the caller's own turn, which in these runs took 13s (one question)
to about 25s (three).

Small numbers: n=4 and n=2, from one evening. Enough to place the cost
against §33's floor, not to gate anything.
