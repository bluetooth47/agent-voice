"""Config, state publishing, and speech for the agentvoice daemon.

Three small concerns that the wake loop should not have to know about:

  Config      resolves a knob from shell.json (where the bar widget writes it),
              falling back to the local TOML, then to a built-in default.
  StateFile   publishes what the daemon is doing, for the bar to read.
  Speaker     turns text into audio with Piper.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import tomllib
from pathlib import Path

from paths import (RUNTIME_DIR, SHELL_JSON, VOICE_ID, config_toml, piper_voices,
                   voice_id, voice_stem)

PLUGIN_ID = "duaneoca.agentvoice"

# Mirrors manifest.json's barWidget.defaults. Duplicated deliberately: the
# daemon has to run with no plugin installed and no config file present.
#: What a model name may look like: "sonnet", "claude-opus-5-5",
#: "gpt-5.1-codex", "anthropic/claude[1m]". No leading dash, so it can never be
#: read as a flag, and no whitespace, so it is always exactly one argument.
_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@\[\]-]{0,127}")

#: Every effort level any backend here accepts. A closed list rather than a
#: pattern, because the value becomes an argv element after `--effort`.
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")

#: A name for an extra agent, which is also the word that wakes it: one to
#: three plain lowercase words. Letters only, because it goes into a Vosk
#: grammar and is matched against what Whisper writes.
_AGENT_NAME = re.compile(r"[a-z]+( [a-z]+){0,2}")
#: An agent's stable id: what grants, the Agents panel, saved chats and the
#: permission hook know it by, so renaming it or changing its wake phrase
#: breaks none of them. Plain, because it travels in argv and file names.
_AGENT_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
#: The longest display name kept. Any text, but it is drawn on one line.
LABEL_MAX = 40

#: The program behind an agent, as Omarchy spells it. Checked against the
#: adapters that exist when the agent is built; this only keeps the value a
#: plain word.
_PROGRAM = re.compile(r"[a-z][a-z0-9-]{0,31}")

#: A Piper voice as the settings spell it: "lessac-medium", "en_GB-alan-medium".
_VOICE = VOICE_ID

#: How many extra agents are listened for. Every name is one more word the
#: grammar can match, and one more process and voice held in memory.
MAX_AGENTS = 8

#: How fast a voice speaks, as a percent of its natural pace. Piper slows by
#: stretching each phoneme (length_scale), so the bounds are where it still
#: sounds like speech rather than a tape at the wrong speed.
SPEED_MIN, SPEED_MAX = 50, 200


def speed_pct(value, fallback: int = 100) -> int:
    """A speaking speed as a whole percent inside the bounds, or `fallback`.

    Read from a hand-editable file, so anything that is not a number reads as
    unset rather than raising inside the run loop."""
    if isinstance(value, bool):
        return fallback
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return fallback
    if n <= 0:
        return fallback
    return max(SPEED_MIN, min(SPEED_MAX, n))


#: Custom instructions are added to the agent's system prompt on every turn,
#: so a pasted essay costs tokens on every question. Long enough for a
#: paragraph of preferences; past that it is a document, not an instruction.
INSTRUCTIONS_MAX = 2000

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def agent_id_for(name: str) -> str:
    """The id an agent saved before ids existed gets: its wake phrase, as the
    Agents panel already spelled it. So nothing it owned -- a panel record, a
    grant, a running process's hook -- changes name on the upgrade. "main"
    is the main agent's, so an extra agent called that is "agent-main"."""
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:48].strip("-")
    return "agent-main" if s == "main" else s


def display_name(value, fallback: str) -> str:
    """A display name as shown: any text, one line, at most LABEL_MAX
    characters, control characters dropped. Empty falls back to the wake
    phrase with each word capitalised ("hey jarvis" -> "Hey Jarvis")."""
    text = " ".join((value if isinstance(value, str) else "").split())
    text = "".join(c for c in text if c.isprintable())[:LABEL_MAX].strip()
    return text or " ".join(w[:1].upper() + w[1:] for w in (fallback or "").split())


def instructions_text(value) -> str:
    """Standing instructions for an agent: plain text, trimmed, bounded.

    Read from a hand-editable file and handed to an agent CLI, so anything
    that is not a string reads as none, and control characters other than a
    newline are dropped rather than passed on."""
    if not isinstance(value, str):
        return ""
    text = _CONTROL.sub("", value.replace("\r\n", "\n").replace("\t", " ")).strip()
    return text[:INSTRUCTIONS_MAX].rstrip()

#: wakeAlsoSounds: a key is one plain word; an alternative is one to three
#: plain words, or up to twelve ARPAbet phones in capitals.
_ALSO_WORD = re.compile(r"[a-z]{1,32}")
_ALSO_WORDS = re.compile(r"[a-z]{1,32}( [a-z]{1,32}){0,2}")
_ALSO_PHONES = re.compile(r"[A-Z]{1,3}[0-2]?( [A-Z]{1,3}[0-2]?){0,11}")

DEFAULTS = {
    "engine": "vosk",
    "phrase": "hey computer",
    "owwModel": "hey_jarvis",
    "owwThresholdPct": 90,
    # sherpa-onnx keywords_threshold, as a percent like the others. 25 is the
    # library's default and held up in FINDINGS §23; 50 lost half the wakes.
    "sherpaThresholdPct": 15,
    # Vosk + Whisper re-check short bursts sherpa-onnx let pass; crosscheck.py.
    "wakeCrossCheck": True,
    # The Advanced wake settings: everything tuned by hand to get "theo"
    # waking, each one a setting now. See Config.wake_tuning().
    "shortNameBoostPct": 150,
    "crossCheckMinMs": 300,
    "crossCheckMaxMs": 2600,
    # word -> other ways it is said, for sherpa-onnx: a word from its
    # lexicon, or phones written out ("TH IY1 AH0"). Was ALT_PHONES.
    "wakeAlsoSounds": {"theo": ["TH IY1 AH0"]},
    # Which engines vote in the second check; crosscheck.MODES.
    "crossCheckEngines": "both",
    # Words allowed after the name ("Theo, you there?"). Was 3, fixed.
    "crossCheckTrailingWords": 3,
    # Whisper is prompted with the agents' names (FINDINGS §24).
    "crossCheckWhisperHint": True,
    # sherpa-onnx also listens for "full stop" in every frame, so it stops
    # everything at once, with no wake word and no Whisper.
    "fullStopAnytime": True,
    "leadInMs": 5000,
    "trailingSilenceMs": 1200,
    "quickEndMs": 800,
    "minUtteranceMs": 400,
    "maxUtteranceMs": 30000,
    "micThresholdDb": -38,
    # Follow the room: the gate becomes the noise floor plus gateMarginDb.
    # Off until it has been live-tested; see noise_floor.py.
    "adaptiveGate": False,
    "gateMarginDb": 10,
    "echoTailMs": 350,
    "refractoryMs": 2000,
    # The float is what the code reads; the percent is what the bar schema
    # exposes, because that schema has no float type. __getitem__ converts.
    "wakeConfidence": 0.70,
    "wakeConfidencePct": 70,
    "model": "tiny.en",
    "speakReplies": True,
    "chimes": True,
    "keepHistory": True,
    # Saved chats (chats.py): off, because the conversation was memory-only
    # by design and writing it to disk is the user's choice to make.
    "saveChats": False,
    "chatRetention": "forever",
    "livePartials": "auto",
    "bargeIn": False,
    "bargeOnHeadset": True,
    # Every declared setting needs a default here: the check script requires
    # one, `omarchy bar set` needs something to compare against, and the
    # daemon has to run with no plugin installed and no config file at all.
    "useVerifier": True,
    "hud": True,
    "hudLingerMs": 2000,
    "bargeFactor": 150,
    "permissions": {},
    "agentModels": {},
    "agentEfforts": {},
    # Agents beyond the main one, each woken by its own name. See
    # Config.agents(): every field is checked there, because a name becomes
    # part of a grammar and a model or effort becomes an argument.
    "voiceAgents": [],
    "projectDir": "",
    "endpointUrl": "",
    "endpointModel": "",
    "endpointIsAgent": False,
    # 0 is the adapter's own default (120s, 300s for an agent).
    "endpointTimeoutS": 0,
    "endpointHistoryTurns": 8,
    # Plan 12a and 12b. Desktop tools are opt-in: they reach outside the
    # project, and at "trusted" they act without asking.
    "desktopTools": False,
    # Plan 12d: Claude in Chrome for Claude Code agents. Opt-in: it is the
    # person's own signed-in browser.
    "browserTools": False,
    "omarchySkill": True,
    "conversationMode": True,
    "yieldToRecorders": True,
    "logSpeech": False,
    "followUpMs": 7000,
    "narration": "off",
    "narrationSilenceS": 7,
    "openMicIdleMin": 10,
    "openMicAddressedOnly": True,
    "openMicAuto": False,
    "voice": "lessac-medium",
    "voiceSpeed": 100,
    "agentInstructions": "",
    "agentsPanel": True,
    # The main agent's display name: shown in the readout, the popup, saved
    # chats and the Agents panel. Empty is its wake phrase, capitalised.
    "mainName": "",
}

# The TOML predates the plugin and uses snake_case under sections. Kept working
# so the loop still runs on a box without Omarchy's shell.
TOML_ALIASES = {
    "phrase": ("wake", "phrase"),
    "engine": ("wake", "engine"),
    "owwModel": ("wake", "oww_model"),
    "owwThresholdPct": ("wake", "oww_threshold_pct"),
    "sherpaThresholdPct": ("wake", "sherpa_threshold_pct"),
    "wakeCrossCheck": ("wake", "cross_check"),
    "shortNameBoostPct": ("wake", "short_name_boost_pct"),
    "crossCheckMinMs": ("wake", "cross_check_min_ms"),
    "crossCheckMaxMs": ("wake", "cross_check_max_ms"),
    "wakeAlsoSounds": ("wake", "also_sounds"),
    "crossCheckEngines": ("wake", "cross_check_engines"),
    "crossCheckTrailingWords": ("wake", "cross_check_trailing_words"),
    "crossCheckWhisperHint": ("wake", "cross_check_whisper_hint"),
    "fullStopAnytime": ("wake", "full_stop_anytime"),
    "leadInMs": ("timing", "lead_in_ms"),
    "trailingSilenceMs": ("timing", "trailing_silence_ms"),
    "quickEndMs": ("timing", "quick_end_ms"),
    "minUtteranceMs": ("timing", "min_utterance_ms"),
    "maxUtteranceMs": ("timing", "max_utterance_ms"),
    "model": ("stt", "model"),
    "micThresholdDb": ("audio", "mic_threshold_db"),
    "adaptiveGate": ("audio", "adaptive_gate"),
    "gateMarginDb": ("audio", "gate_margin_db"),
    "echoTailMs": ("audio", "echo_tail_ms"),
    # No manifest entry, deliberately: a refractory window is a property of
    # how the detector behaves, not a knob worth a slider. It still needs a
    # default and an alias so the TOML path can reach it.
    "refractoryMs": ("wake", "refractory_ms"),
    # Written as a float here and as a whole percent in the schema; see
    # _from_toml, which converts.
    "wakeConfidence": ("audio", "wake_confidence"),
    "livePartials": ("stt", "live_partials"),
    "bargeIn": ("audio", "barge_in"),
    "bargeOnHeadset": ("audio", "barge_on_headset"),
    "useVerifier": ("wake", "use_verifier"),
    "hud": ("ui", "hud"),
    "hudLingerMs": ("ui", "hud_linger_ms"),
    "chimes": ("ui", "chimes"),
    "keepHistory": ("ui", "keep_history"),
    "saveChats": ("ui", "save_chats"),
    "chatRetention": ("ui", "chat_retention"),
    "bargeFactor": ("audio", "barge_factor"),
    "permissions": ("agent", "permissions"),
    "agentModels": ("agent", "models"),
    "agentEfforts": ("agent", "efforts"),
    "voiceAgents": ("agent", "voice_agents"),
    "projectDir": ("agent", "project_dir"),
    "endpointUrl": ("agent", "endpoint_url"),
    "endpointModel": ("agent", "endpoint_model"),
    "endpointIsAgent": ("agent", "endpoint_is_agent"),
    "endpointTimeoutS": ("agent", "endpoint_timeout_s"),
    "endpointHistoryTurns": ("agent", "endpoint_history_turns"),
    "desktopTools": ("agent", "desktop_tools"),
    "browserTools": ("agent", "browser_tools"),
    "omarchySkill": ("agent", "omarchy_skill"),
    "conversationMode": ("wake", "conversation_mode"),
    "yieldToRecorders": ("wake", "yield_to_recorders"),
    "logSpeech": ("ui", "log_speech"),
    "followUpMs": ("timing", "follow_up_ms"),
    "narration": ("ui", "narration"),
    "narrationSilenceS": ("timing", "narration_silence_s"),
    "openMicIdleMin": ("wake", "open_mic_idle_min"),
    "openMicAddressedOnly": ("wake", "open_mic_addressed_only"),
    "openMicAuto": ("wake", "open_mic_auto"),
    "agentsPanel": ("ui", "agents_panel"),
    "mainName": ("agent", "main_name"),
}


class Config:
    """Reloaded between utterances so knobs can be turned mid-session."""

    def __init__(self) -> None:
        self._stamps: tuple = ()
        self._values: dict = dict(DEFAULTS)
        self.source = "defaults"
        self.reload()

    @staticmethod
    def _stamp(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def _from_shell_json(self) -> dict:
        try:
            data = json.loads(SHELL_JSON.read_text())
        except Exception:
            return {}
        layout = (data.get("bar") or {}).get("layout") or {}
        for entries in layout.values():
            for entry in entries or []:
                if entry.get("id") == PLUGIN_ID:
                    return {k: v for k, v in entry.items() if k != "id"}
        return {}

    def _from_toml(self) -> dict:
        try:
            raw = tomllib.loads(config_toml().read_text())
        except Exception:
            return {}
        out = {}
        for key, (section, name) in TOML_ALIASES.items():
            value = (raw.get(section) or {}).get(name)
            if value is not None:
                out[key] = value
        # The file writes a float and __getitem__ reads the percent, which is
        # always present from DEFAULTS -- so `wake_confidence = 0.80` in the
        # TOML used to be read, merged, and then ignored by every caller.
        # Converting it here is what makes editing the file do something.
        if "wakeConfidence" in out and "wakeConfidencePct" not in out:
            try:
                out["wakeConfidencePct"] = round(float(out["wakeConfidence"]) * 100)
            except (TypeError, ValueError):
                pass
        return out

    def reload(self) -> bool:
        """True if anything on disk changed since the last read."""
        stamps = (self._stamp(SHELL_JSON), self._stamp(config_toml()))
        if stamps == self._stamps:
            return False
        self._stamps = stamps

        merged = dict(DEFAULTS)
        merged.update(self._from_toml())
        widget = self._from_shell_json()
        merged.update(widget)
        changed = merged != self._values
        self._values = merged
        self.source = f"shell.json[{PLUGIN_ID}]" if widget else (
            "agentvoice.toml" if config_toml().exists() else "defaults")
        return changed

    def __getitem__(self, key: str):
        # The bar schema has no float type, so confidence travels as a whole
        # percent and is converted here rather than everywhere it is read.
        if key == "wakeConfidence" and "wakeConfidencePct" in self._values:
            try:
                return float(self._values["wakeConfidencePct"]) / 100.0
            except (TypeError, ValueError):
                return float(DEFAULTS["wakeConfidence"])
        return self._values.get(key, DEFAULTS.get(key))

    #: get_int / get_bool / get_str rather than int / bool / str: the short
    #: names shadowed the builtins inside this class and read oddly at the
    #: call site (`cfg.str("voice")`).
    #:
    #: Every reader goes through one of these three, and every one of them
    #: has to survive a value of the wrong type. shell.json is hand-edited,
    #: written by `omarchy bar set`, and synced between machines, so
    #: `"leadInMs": "abc"` is a thing it can hold -- and this is read from
    #: inside the run loop, where a ValueError is the daemon stopping. The
    #: built-in default is the answer instead, because a knob that cannot be
    #: parsed has not been set.
    def get_int(self, key: str) -> int:
        try:
            return int(self[key])
        except (TypeError, ValueError):
            return self._fallback(key, int)

    def get_bool(self, key: str) -> bool:
        value = self[key]
        if isinstance(value, str):
            # JSON has a boolean; a TOML or hand edit may still say "true".
            return value.strip().lower() in ("1", "true", "yes", "on")
        try:
            return bool(value)
        except (TypeError, ValueError):
            return self._fallback(key, bool)

    def get_str(self, key: str) -> str:
        value = self[key]
        return "" if value is None else str(value)

    @staticmethod
    def _fallback(key: str, cast):
        """The shipped default for `key`, or the type's zero."""
        try:
            return cast(DEFAULTS[key])
        except (KeyError, TypeError, ValueError):
            return cast()

    def level_for(self, agent: str | None) -> str:
        """The permission level chosen for this agent, defaulting to "ask".

        Levels are per agent because trust is a judgement about one program's
        capabilities, and those differ enormously: Claude Code can be stopped
        mid-call by a hook we answer, Codex cannot be stopped at all. A single
        global level meant that trusting Claude Code silently handed the same
        trust to whatever `omarchy default agent` was switched to next.

        Anything unrecognised reads as "ask". An agent nobody has made a
        decision about has not been trusted, and the absence of a decision
        must never be read as a permissive one.
        """
        raw = self["permissions"]
        if not isinstance(raw, dict) or not agent:
            return "ask"
        value = raw.get(agent)
        return value if value in ("ask", "edits", "trusted") else "ask"

    def model_for(self, agent: str | None) -> str | None:
        """The model chosen for this agent, or None for the CLI's own default.

        Per agent for the same reason levels are: "sonnet" means something to
        Claude Code and nothing to Codex, so a name chosen for one must not be
        handed to whatever `omarchy default agent` is switched to next.

        The value becomes an argv element after `--model`, so anything that
        could be read as a flag or is not plainly a model name reads as unset.
        """
        raw = self["agentModels"]
        if not isinstance(raw, dict) or not agent:
            return None
        value = raw.get(agent)
        if not isinstance(value, str):
            return None
        value = value.strip()
        if not value or not _MODEL_NAME.fullmatch(value):
            return None
        return value

    def effort_for(self, agent: str | None) -> str | None:
        """The effort level chosen for this agent, or None for its default.

        Per agent like the model, and for the same reason. Anything outside
        EFFORT_LEVELS reads as unset: it would otherwise be an argument to a
        CLI that can run commands.
        """
        raw = self["agentEfforts"]
        if not isinstance(raw, dict) or not agent:
            return None
        value = raw.get(agent)
        return value if isinstance(value, str) and value in EFFORT_LEVELS else None

    def wake_tuning(self) -> dict:
        """The Advanced wake settings, clamped and cleaned.

        - short_boost: sherpa-onnx boost for names of three phones or fewer
          (was SHORT_BOOST, 1.5), 0.5 to 3.0;
        - burst_min_ms / burst_max_ms: how long a burst of speech may be for
          the second check to look at it (was 300 and 2600). The minimum is
          kept below the maximum, so a hand edit cannot close the window;
        - engines / trailing / whisper_hint: how the second check votes
          (crosscheck.decide), unknown modes read as "both";
        - also_sounds: {word: [alternative, ...]}. An alternative is either
          lower-case words (one to three, looked up in the lexicon) or
          upper-case phones ("TH IY1 AH0"). Anything else is dropped here,
          and a phone the model has no token for is dropped when listening
          starts. At most 16 words with 8 alternatives each.
        """
        def clamp(key, lo, hi):
            return max(lo, min(hi, self.get_int(key)))

        boost = clamp("shortNameBoostPct", 50, 300) / 100.0
        lo = clamp("crossCheckMinMs", 100, 1000)
        hi = clamp("crossCheckMaxMs", 1000, 5000)
        if lo >= hi:
            lo = min(DEFAULTS["crossCheckMinMs"], hi - 100)
        raw = self["wakeAlsoSounds"]
        also: dict[str, list[str]] = {}
        if isinstance(raw, dict):
            for word, alts in raw.items():
                if len(also) >= 16:
                    break
                word = str(word).strip().lower()
                if not _ALSO_WORD.fullmatch(word) or not isinstance(alts, list):
                    continue
                clean = []
                for alt in alts:
                    if not isinstance(alt, str):
                        continue
                    alt = " ".join(alt.split())
                    if alt and alt not in clean and (
                            _ALSO_WORDS.fullmatch(alt) or _ALSO_PHONES.fullmatch(alt)):
                        clean.append(alt)
                if clean:
                    also[word] = clean[:8]
        engines = self.get_str("crossCheckEngines")
        return {"short_boost": boost, "burst_min_ms": lo, "burst_max_ms": hi,
                "also_sounds": also,
                "engines": engines if engines in ("both", "whisper", "vosk") else "both",
                "trailing": clamp("crossCheckTrailingWords", 0, 6),
                "whisper_hint": self.get_bool("crossCheckWhisperHint")}

    def agents(self) -> list[dict]:
        """The extra agents, each woken by its own name, cleaned up.

        Read from a list that is hand-editable and synced between machines,
        so every field is checked rather than trusted, the same way the
        per-agent maps above are:

        - a name that is not one to three plain words is dropped, along with
          its agent: it could never be heard, and it goes into a grammar;
        - a second agent with a name already taken is dropped, because one
          word cannot wake two agents;
        - a model, effort or voice that is not plainly one reads as unset, as
          it does for the main agent;
        - a permission level that is not one of the three reads as "ask".
          An agent nobody has made a decision about has not been trusted.

        An agent switched off (`"enabled": false`) is left out, so its name
        leaves the wake grammar and nothing routes to it, but its name stays
        taken: switching it back on must not find a second agent answering
        to it. Only an explicit false is off; a missing or odd value is on,
        so lists written before the switch existed don't change.

        At most MAX_AGENTS, in the order they were added.
        """
        return self._agents()[0]

    def disabled_agents(self) -> set[str]:
        """The ids of agents that are configured but switched off."""
        return self._agents()[1]

    def _agents(self) -> tuple[list[dict], set[str]]:
        raw = self["voiceAgents"]
        if not isinstance(raw, list):
            return [], set()
        out: list[dict] = []
        off: set[str] = set()
        seen: set[str] = set()
        seen_ids: set[str] = set()
        for entry in raw:
            if len(out) + len(off) >= MAX_AGENTS:
                break
            if not isinstance(entry, dict):
                continue
            name = " ".join(str(entry.get("name") or "").lower().split())
            if (len(name) > 32 or not _AGENT_NAME.fullmatch(name)
                    or name in seen):
                continue
            seen.add(name)
            raw_id = entry.get("id")
            agent_id = raw_id.strip() if isinstance(raw_id, str) else ""
            if not _AGENT_ID.fullmatch(agent_id) or agent_id == "main":
                agent_id = agent_id_for(name)
            if agent_id in seen_ids:
                # Two agents answering to one id would share grants, chats
                # and a panel record. Only a hand edit can do this; the
                # settings page never writes a duplicate.
                continue
            seen_ids.add(agent_id)
            if entry.get("enabled") is False:
                off.add(agent_id)
                continue
            program = str(entry.get("agent") or "claude").strip().lower()
            model = entry.get("model")
            model = model.strip() if isinstance(model, str) else ""
            effort = entry.get("effort")
            voice = entry.get("voice")
            voice = voice.strip() if isinstance(voice, str) else ""
            level = entry.get("level")
            folder = entry.get("projectDir")
            # 0 is "same as the main agent"; anything unreadable reads as that.
            speed = speed_pct(entry.get("speed"), 0)
            talk = entry.get("narration")
            out.append({
                "name": name,
                "id": agent_id,
                "label": display_name(entry.get("label"), name),
                "agent": program if _PROGRAM.fullmatch(program) else "",
                "model": model if _MODEL_NAME.fullmatch(model) else "",
                "effort": effort if effort in EFFORT_LEVELS else "",
                "voice": voice if _VOICE.fullmatch(voice) else "",
                "speed": speed,
                # "" follows the main setting.
                "narration": talk if talk in NARRATION_LEVELS else "",
                "instructions": instructions_text(entry.get("instructions")),
                "level": level if level in ("ask", "edits", "trusted") else "ask",
                "projectDir": folder.strip() if isinstance(folder, str) else "",
                # Its own OpenAI-compatible endpoint, when its program is
                # "endpoint" (plan 7b); None otherwise.
                "endpoint": (endpoint_entry(entry.get("endpointUrl"),
                                            entry.get("endpointModel"),
                                            entry.get("endpointIsAgent"),
                                            entry.get("endpointTimeoutS"),
                                            entry.get("endpointHistoryTurns"))
                             if program == "endpoint" else None),
            })
        return out, off

    def main_endpoint(self) -> dict | None:
        """The main agent's endpoint, cleaned like an extra agent's, or None
        when the URL or the model is missing."""
        return endpoint_entry(self["endpointUrl"], self["endpointModel"],
                              self["endpointIsAgent"], self["endpointTimeoutS"],
                              self["endpointHistoryTurns"])

    def agent_named(self, name: str | None) -> dict | None:
        """The extra agent whose wake phrase is `name`, or None."""
        if not name:
            return None
        for spec in self.agents():
            if spec["name"] == name:
                return spec
        return None

    def agent_by_id(self, agent_id: str | None) -> dict | None:
        """The extra agent with this stable id, or None. What the permission
        hook and saved chats look an agent up by: a rename keeps the id."""
        if not agent_id:
            return None
        for spec in self.agents():
            if spec["id"] == agent_id:
                return spec
        return None

    def narration(self, spec: dict | None = None) -> str:
        """How much an agent says while it works: its own choice on its
        card, else the main setting. One of NARRATION_LEVELS."""
        own = (spec or {}).get("narration") or ""
        if own in NARRATION_LEVELS:
            return own
        level = self.get_str("narration")
        return level if level in NARRATION_LEVELS else "off"

    def narration_silence_s(self) -> float:
        """Seconds of quiet before the first progress sentence, 3 to 30."""
        return float(min(30, max(3, self.get_int("narrationSilenceS"))))

    def main_label(self, phrase: str = "") -> str:
        """The main agent's display name: `mainName`, else its wake phrase."""
        return display_name(self["mainName"], phrase or self.get_str("phrase"))


def endpoint_entry(url, model, is_agent=False, timeout_s=0,
                   history_turns=8) -> dict | None:
    """An endpoint as the adapter takes it, from hand-editable settings.

    The URL goes through endpoints.clean_url, so what is used is what the
    page showed; a model that is not plainly a model name reads as unset,
    as it does for a CLI. None when either is missing: a half-filled
    endpoint is not in use. No key here, ever -- see paths.endpoint_key.
    """
    from endpoints import clean_url
    url = clean_url(url if isinstance(url, str) else "")
    model = model.strip() if isinstance(model, str) else ""
    if not url or not _MODEL_NAME.fullmatch(model):
        return None

    def number(value, default, lo, hi):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return default
        return max(lo, min(hi, value))

    timeout = number(timeout_s, 0, 0, 600)
    return {"url": url, "model": model, "is_agent": is_agent is True,
            # 0 is the adapter's default; anything set is at least 10s.
            "timeout_s": max(10, timeout) if timeout else 0,
            "history_turns": number(history_turns, 8, 0, 50)}


#: How much progress talk: nothing, the stage, or files and searches too.
NARRATION_LEVELS = ("off", "brief", "detailed")


#: How much of a reply travels to the screen. It was 400 characters, which
#: cut a long answer off mid-sentence in the very readout meant for reading it
#: -- "the popup is too small" was partly this. The state file is rewritten
#: once per sentence, in tmpfs, so a few kilobytes cost nothing.
REPLY_MAX = 8000

#: Exchanges kept for the conversation view. A session is rarely more.
HISTORY_MAX = 200


class History:
    """The session's exchanges, for the conversation view.

    Beside the state file, in the runtime directory: tmpfs, 0600, gone at
    logout -- the same place and the same lifetime as the current exchange
    the panel already shows, kept for the session rather than for one turn.
    Never the journal, which keeps weeks, and never anywhere on disk. That is
    the line logSpeech draws, and this stays on the right side of it.

    One JSON object per line, appended as each turn ends, so the screen can
    watch the file and add what is new without re-reading the rest.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or RUNTIME_DIR / "history.jsonl"

    def append(self, entry: dict) -> None:
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                         0o600)
            # Tightened even if it already existed: a file somebody else made
            # loose is still holding what was said.
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(line)
            self._trim()
        except OSError:
            # A readout, not a record anything depends on. Losing it must
            # not cost the turn -- the same rule as the state file.
            pass

    def _trim(self) -> None:
        lines = self.path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= HISTORY_MAX:
            return
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("\n".join(lines[-HISTORY_MAX:]) + "\n", encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


class StateFile:
    """What the daemon is doing, written where the bar widget can watch it.

    Same contract shape Voxtype uses for its own indicator: one small file,
    rewritten on every transition. Written to a temp file and renamed so a
    watcher never reads a half-written line.
    """

    def __init__(self) -> None:
        # 0o700, and the file 0o600 below. This holds the verbatim transcript
        # and the agent's reply, so it is the same thing the prompt in argv
        # was: your speech, readable by somebody else with an account here.
        # It was 0644 in a 0755 directory and safe only because systemd makes
        # $XDG_RUNTIME_DIR 0700 -- which is a protection we inherit rather
        # than one we set, and not ours to rely on.
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            RUNTIME_DIR.chmod(0o700)      # mkdir's mode is ignored if it exists
        except OSError:
            pass
        self.path = RUNTIME_DIR / "state"
        self._last: dict = {}
        #: Publishes come from more than one thread once there are extra
        #: agents, and every one of them writes the same temporary file.
        self._lock = threading.RLock()
        #: Given (state, extra) and returns what to actually show. The daemon
        #: sets it so that the microphone's state and each agent's can be
        #: combined into the one line the bar has room for. None shows what
        #: was published, as it always did.
        self.overlay = None
        # Facts that hold for the whole session and belong in every payload,
        # so the panel can render what the running agent actually supports
        # instead of keeping its own copy of that knowledge and drifting.
        self._context: dict = {}
        #: Given every payload written, after it is written. The daemon sets
        #: it to keep Omarchy's Agents panel in step; see agents_panel.py.
        self.mirror = None

    def describe(self, **fields) -> None:
        """Set the sticky fields merged into every subsequent publish."""
        with self._lock:
            if fields != self._context:
                self._context = dict(fields)
                if self._last:
                    # Written as it stands, not through the overlay: it is
                    # already what the overlay made of the last publish.
                    self._write(self._last.get("state", "off"),
                                {k: v for k, v in self._last.items()
                                 if k != "state" and k not in self._context})

    def publish(self, state: str, **extra) -> None:
        with self._lock:
            if self.overlay is not None:
                state, extra = self.overlay(state, extra)
            self._write(state, extra)

    def _write(self, state: str, extra: dict) -> None:
        payload = {"state": state, **self._context, **extra}
        if payload == self._last:
            return
        self._last = payload
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(payload))
            # Before the rename, so the file is never briefly world readable
            # under its real name.
            tmp.chmod(0o600)
        except FileNotFoundError:
            # The state file lives in /run, which is tmpfs, is cleanable, and
            # is deleted outright by this project's own uninstaller. The
            # directory was created once in __init__, so when it went the next
            # publish raised FileNotFoundError out of the run loop and killed
            # the daemon -- twice, in one session. Losing the readout the bar
            # watches is a cosmetic failure; it must not be a fatal one.
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(payload))
        tmp.replace(self.path)
        if self.mirror is not None:
            try:
                self.mirror(payload)
            except Exception as e:      # a side panel must never stop the readout
                print(f"agents panel: {type(e).__name__}: {e}", flush=True)

    @property
    def current(self) -> str:
        """The last state published, for code that must not act out of turn."""
        return str(self._last.get("state", "off"))

    def clear(self) -> None:
        """Best effort: this runs on the way out, including while unwinding a
        failure. It raised the same error as the exception it was cleaning up
        after, which replaced the traceback that said what really happened."""
        try:
            self.publish("off")
        except OSError:
            pass


#: How much audio is handed to PortAudio in one blocking write.
#:
#: Piper returns an entire sentence as a single chunk -- 10.53 seconds of
#: audio in one 464KB buffer, measured on lessac-medium with the sentence
#: that exposed this -- and `out.write()` of that blocks until nearly all of
#: it has played. `_stop` was checked only before a chunk and `watch` only
#: after one, so a sentence could not be interrupted once begun, and *every*
#: way of stopping speech went through one of those two: a locked screen, a
#: mute, another application taking the microphone, the Stop button, the
#: interrupt keybind, and barge-in. Measured before this change: cancel() one
#: second in, and it kept talking for 10.29 seconds.
#:
#: 50ms is one slice of ~1100 samples at 22050Hz. Small enough that a stop is
#: inaudible as a delay, large enough that the write loop is not the thing
#: using the CPU.
SLICE_MS = 50


class Speaker:
    """Piper, loaded once and reused. 22ms to first audio, 22x realtime.

    Splits on sentences before synthesising, because Piper returns a whole
    utterance before yielding its first chunk -- so a long reply would
    otherwise sit silent while the entire thing renders.
    """

    #: Set when the requested voice was not on disk and another was used
    #: instead. The caller prints it, because silence with the reason in a log
    #: is the failure this exists to avoid.
    substituted_for: str = ""

    #: Speaking speed in percent. A plain attribute, assigned by the caller
    #: after its spec check: a speed is a number, not a new model.
    speed: int = 100
    #: The voice's own pace. Some voices ship a length_scale other than 1,
    #: so a speed is applied on top of it rather than instead of it.
    _base_scale: float = 1.0

    def __init__(self, voice: str = "lessac-medium") -> None:
        from piper import PiperVoice
        voice, substituted = self._resolve(voice)
        path = (piper_voices() / f"{voice_stem(voice)}.onnx")
        self._voice = PiperVoice.load(str(path))
        self._rate = getattr(self._voice.config, "sample_rate", 22050)
        self._base_scale = float(getattr(self._voice.config, "length_scale", 1.0) or 1.0)
        self.name = voice
        self.substituted_for = substituted
        #: What the settings asked for, which is what a later reload compares
        #: against. Comparing the loaded name would see a substitution as a
        #: changed setting and reload Piper on every reload.
        self.requested = substituted or voice
        self._stop = threading.Event()
        #: When the last say() put its first sound out, by the wall clock. The
        #: end of the turn's latency: everything before it is silence.
        self.first_audio_at: float | None = None

    def superseded(self) -> bool:
        """True when the voice originally asked for has since been downloaded.

        Anything a model loads is reconciled rather than constructed once, and
        a voice file can appear underneath a running daemon -- install.sh
        fetches it. Without this, a substitution outlived the download and the
        only cure was changing an unrelated setting to force a rebuild.
        """
        if not self.substituted_for:
            return False
        return (piper_voices() / f"{voice_stem(self.substituted_for)}.onnx").exists()

    @staticmethod
    def _resolve(voice: str) -> tuple[str, str]:
        """The requested voice, or any other one on disk.

        The settings list every voice the project knows, marking the ones not
        downloaded -- and selecting one used to raise here, leaving the daemon
        with no speaker at all. Nothing then retried until some unrelated
        setting changed, so the only cure people found was switching the wake
        engine and back. Falling back keeps speech working and names the
        substitution; being wrong out loud beats being silent.
        """
        here = piper_voices()
        if (piper_voices() / f"{voice_stem(voice)}.onnx").exists():
            return voice, ""
        available = sorted(voice_id(p.stem) for p in here.glob("*.onnx")
                           if VOICE_ID.fullmatch(voice_id(p.stem)))
        if not available:
            raise FileNotFoundError(f"no piper voice at {here}")
        # Prefer the default when it is one of them: it is the voice every
        # install has, so the substitution is the least surprising one.
        pick = "lessac-medium" if "lessac-medium" in available else available[0]
        return pick, voice

    @staticmethod
    def sentences(text: str) -> list[str]:
        """Split for synthesis, by the same rules the streaming split uses.

        It was `re.split(r"(?<=[.!?])\\s+")` here, which undid the care taken
        in speech_text: that pattern splits "J. Smith" and "version 2.1. Next"
        wherever the streaming path had deliberately kept them together, so
        the same reply was chunked one way on its way to the screen and
        another on its way to Piper.
        """
        from speech_text import iter_sentences
        return list(iter_sentences([text.strip()]))

    def length_scale(self) -> float:
        """Piper's length_scale for the current speed: larger is slower."""
        return self._base_scale * 100.0 / speed_pct(self.speed)

    def synthesis_config(self):
        """None at normal speed, so Piper keeps its own defaults untouched."""
        if speed_pct(self.speed) == 100:
            return None
        from piper import SynthesisConfig
        return SynthesisConfig(length_scale=self.length_scale())

    def cancel(self) -> None:
        self._stop.set()

    def say(self, text: str, watch=None) -> float:
        """Speak, sentence by sentence. Returns seconds of audio produced.

        `watch` is called between audio chunks and stops the speech when it
        returns true -- which is how barge-in listens while we are talking.
        Called here rather than from a thread on purpose: this opens a
        PortAudio output stream while an input stream is already running, and
        driving two of those from two threads is what crashed every benchmark
        script that tried it (libasound, use-after-free, SEGV). One thread,
        one interleaved loop, no shared PCM handles.
        """
        import numpy as np
        import sounddevice as sd

        self._stop.clear()
        self.first_audio_at = None
        total = 0.0
        slice_n = max(1, int(self._rate * SLICE_MS / 1000))
        syn = self.synthesis_config()
        # Only handed over when it says something, so normal speed calls
        # Piper exactly as it always has.
        opts = {"syn_config": syn} if syn is not None else {}
        with sd.OutputStream(samplerate=self._rate, channels=1,
                             dtype="int16") as out:
            for sentence in self.sentences(text):
                if self._stop.is_set():
                    break
                for chunk in self._voice.synthesize(sentence, **opts):
                    if self._stop.is_set():
                        break
                    pcm = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
                    # Sliced, because Piper hands back a whole sentence as one
                    # chunk and a blocking write of that cannot be interrupted.
                    for at in range(0, len(pcm), slice_n):
                        if self._stop.is_set():
                            break
                        out.write(pcm[at:at + slice_n])
                        if self.first_audio_at is None:
                            self.first_audio_at = time.time()
                        total += len(pcm[at:at + slice_n]) / self._rate
                        if watch is not None and watch():
                            self._stop.set()
                            break
            if self._stop.is_set():
                # What has been written is already inside PortAudio's buffer
                # and would go on playing after this returns. abort() drops it;
                # stop() and close() drain it, which is the wrong direction for
                # every caller that asked us to be quiet.
                out.abort()
        return total
