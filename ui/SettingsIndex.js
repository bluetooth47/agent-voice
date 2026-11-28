.pragma library

// Settings search (master plan M28): where every setting lives.
//
// One entry per setting, from its label, its key and the words somebody
// might look for it by ("where is the pause setting?") to the page, the agent,
// the tab and the control. The control is an `objectName` on that page
// (`anchor`); Settings.qml's reveal() finds it, unfolds whatever holds it,
// scrolls to it, outlines it and gives it the keyboard.
//
// An entry is one of:
//   key           a setting: a manifest key or a defaults-only key;
//   key + field   the main agent's key and the same field of every other
//                 agent's entry in voiceAgents: one result per agent;
//   field         a voiceAgents field with no main twin on that page;
//   action        something that is not a setting (Mute mic, Run setup).
// `when` says when the control is on screen at all, for one that is hidden
// unless something else is chosen; a search for it still lands, and says so.
// `advanced` marks one folded under an Advanced section, for the result's
// path.
//
// The list between BEGIN and END is plain JSON, so tests/test_settings_search
// can read it: every manifest key and every defaults-only key must have an
// entry, on the page that writes it, with an anchor that page really has.
// Keep it JSON: double quotes, no trailing commas, no comments inside.

// BEGIN ENTRIES
var ENTRIES = [
{"key": "micThresholdDb", "label": "Microphone gate", "page": "listening", "anchor": "set-micThresholdDb", "words": "gate threshold sensitivity loud quiet level volume noise mic cut off"},
{"key": "adaptiveGate", "label": "Gate follows the room", "page": "listening", "anchor": "set-adaptiveGate", "words": "adaptive dynamic automatic fixed gate noise floor room"},
{"key": "gateMarginDb", "label": "Margin above the room", "page": "listening", "anchor": "set-gateMarginDb", "advanced": true, "words": "gate margin adaptive noise floor"},
{"key": "gateRiseTenths", "label": "Gate rises at most", "page": "listening", "anchor": "gateRiseKnob", "advanced": true, "words": "how fast adapt adapts speed gate rise slow fast"},
{"key": "gateFallTenths", "label": "Gate falls at most", "page": "listening", "anchor": "gateFallKnob", "advanced": true, "words": "how fast adapt adapts speed gate fall slow fast"},
{"key": "engine", "label": "Wake word engine", "page": "listening", "anchor": "set-engine", "words": "vosk openwakeword sherpa onnx listener hotword detector"},
{"key": "owwThresholdPct", "label": "openWakeWord detection threshold", "page": "listening", "anchor": "set-owwThresholdPct", "when": "openWakeWord is chosen and installed", "words": "sensitivity false wakes wake word"},
{"key": "sherpaThresholdPct", "label": "sherpa-onnx detection threshold", "page": "listening", "anchor": "set-sherpaThresholdPct", "when": "sherpa-onnx is chosen and installed", "words": "sensitivity false wakes wake word"},
{"key": "shortNameBoostPct", "label": "Short-name boost", "page": "listening", "anchor": "set-shortNameBoostPct", "when": "sherpa-onnx is chosen and installed", "words": "short names boost sherpa wake word"},
{"key": "wakeAlsoSounds", "label": "Also sounds like", "page": "listening", "anchor": "alsoSoundsSection", "when": "sherpa-onnx is chosen and installed", "words": "also wake on words that sounds like sound-alike alternative spelling misheard"},
{"key": "useVerifier", "label": "Only wake for my voice", "page": "listening", "anchor": "set-useVerifier", "when": "openWakeWord is chosen and installed", "words": "verifier speaker my voice personal train"},
{"key": "wakeCrossCheck", "label": "Second check for short names", "page": "listening", "anchor": "set-wakeDecision", "words": "cross check whisper second look verify decision either"},
{"key": "wakeBothAgree", "label": "Both stages must agree", "page": "listening", "anchor": "set-wakeDecision", "words": "decision both agree strict false wakes stages"},
{"key": "crossCheckEngines", "label": "Second check: who votes", "page": "listening", "anchor": "secondCheckVotes", "words": "cross check vosk whisper votes"},
{"key": "crossCheckMinMs", "label": "Second check: shortest burst", "page": "listening", "anchor": "set-crossCheckMinMs", "advanced": true, "words": "cross check burst minimum"},
{"key": "crossCheckMaxMs", "label": "Second check: longest burst", "page": "listening", "anchor": "set-crossCheckMaxMs", "advanced": true, "words": "cross check burst maximum"},
{"key": "crossCheckTrailingWords", "label": "Second check: words allowed after the name", "page": "listening", "anchor": "set-crossCheckTrailingWords", "advanced": true, "words": "cross check trailing words"},
{"key": "crossCheckWhisperHint", "label": "Second check: tell Whisper the names", "page": "listening", "anchor": "set-crossCheckWhisperHint", "advanced": true, "words": "cross check whisper hint prompt names"},
{"key": "wakeConfidencePct", "label": "Grammar confidence", "page": "listening", "anchor": "set-wakeConfidencePct", "when": "Vosk is the engine", "words": "wake word confidence sensitivity false wakes threshold accuracy vosk"},
{"action": "wakeTest", "label": "Test my wake word", "page": "listening", "anchor": "wakeTestGroup", "words": "wake test try count calibrate"},

{"key": "trailingSilenceMs", "label": "Pause that ends a turn", "page": "conversation", "anchor": "pauseKnob", "advanced": true, "words": "pause silence end of turn stop listening wait endpoint finished"},
{"key": "leadInMs", "label": "Time to start speaking", "page": "conversation", "anchor": "leadInKnob", "advanced": true, "words": "lead in wait start delay begin"},
{"key": "quickEndMs", "label": "Shorter pause when you sound finished", "page": "conversation", "anchor": "quickKnob", "advanced": true, "words": "pause quick end finished sentence"},
{"key": "minUtteranceMs", "label": "Ignore a turn shorter than", "page": "conversation", "anchor": "minKnob", "advanced": true, "words": "discard shortest turn minimum cough noise"},
{"key": "maxUtteranceMs", "label": "Longest a turn can be", "page": "conversation", "anchor": "maxKnob", "advanced": true, "words": "longest turn hard ceiling limit maximum cut off long 30 seconds 90"},
{"key": "echoTailMs", "label": "Deaf period after speaking", "page": "conversation", "anchor": "echoKnob", "advanced": true, "words": "echo tail deaf after reply"},
{"action": "pace", "label": "Pace", "page": "conversation", "anchor": "set-pace", "words": "patient balanced snappy timings preset speed"},
{"key": "conversationMode", "label": "Keep listening after a reply", "page": "conversation", "anchor": "set-conversationMode", "words": "follow up followup conversation without wake word"},
{"key": "followUpMs", "label": "Follow-up window", "page": "conversation", "anchor": "set-followUpMs", "words": "follow up followup window how long listening after"},
{"key": "openMicIdleMin", "label": "Open mic closes after", "page": "conversation", "anchor": "set-openMicIdleMin", "words": "open mic idle minutes timeout"},
{"key": "openMicAddressedOnly", "label": "Only answer if it's meant for you", "page": "conversation", "anchor": "set-openMicAddressedOnly", "words": "open mic addressed meant for you ignore other people"},
{"key": "openMicAuto", "label": "Open the mic after every wake", "page": "conversation", "anchor": "set-openMicAuto", "words": "open mic automatic always"},
{"key": "narration", "label": "Talk while it works", "page": "conversation", "anchor": "set-narration", "words": "narration progress updates tell me what it is doing brief detailed"},
{"key": "narrationSilenceS", "label": "Quiet before it says anything", "page": "conversation", "anchor": "set-narrationSilenceS", "words": "doing narration silence seconds progress"},
{"key": "fullStopAnytime", "label": "Stop everything by voice, without the wake word", "page": "conversation", "anchor": "set-fullStopAnytime", "words": "full stop emergency stop halt cancel"},
{"key": "bargeOnHeadset", "label": "Interrupt by talking, on a headset", "page": "conversation", "anchor": "set-bargeOnHeadset", "words": "let me interrupt barge in talk over headset headphones"},
{"key": "bargeIn", "label": "Interrupt by talking, on speakers too", "page": "conversation", "anchor": "set-bargeIn", "words": "let me interrupt barge in talk over speakers"},
{"key": "bargeFactor", "label": "How much louder you must be", "page": "conversation", "anchor": "set-bargeFactor", "advanced": true, "words": "interrupt barge in sensitivity louder"},
{"key": "commandsInSentences", "label": "Commands inside a sentence", "page": "conversation", "anchor": "commandsRow", "words": "voice commands sentence edges clause alone stop listening"},
{"action": "commandList", "label": "Voice commands", "page": "conversation", "anchor": "commandList", "words": "commands list what can I say spoken"},

{"key": "speakReplies", "label": "Speak replies aloud", "page": "voice", "anchor": "set-speakReplies", "words": "speak voice silent text only tts mute replies"},
{"key": "chimes", "label": "Sounds for listening, heard and done", "page": "voice", "anchor": "set-chimes", "words": "chime chimes beep sound effects ding"},
{"key": "model", "label": "Transcription model", "page": "voice", "anchor": "set-model", "advanced": true, "words": "whisper speech to text stt accuracy tiny base small"},
{"key": "livePartials", "label": "Live transcript while you speak", "page": "voice", "anchor": "set-livePartials", "advanced": true, "words": "partial live transcript words as you speak"},
{"action": "voiceLibrary", "label": "Voice library", "page": "voice", "anchor": "voiceLibrary", "words": "voices download piper remove sample listen"},

{"key": "saveChats", "label": "Save conversations", "page": "chats", "anchor": "set-saveChats", "words": "save chats history keep conversations disk"},
{"key": "chatRetention", "label": "Keep saved chats", "page": "chats", "anchor": "set-chatRetention", "words": "retention delete after days week month forever"},
{"key": "chatSummaries", "label": "Names and summaries", "page": "chats", "anchor": "set-chatSummaries", "words": "chat titles names summaries"},
{"key": "keepHistory", "label": "Keep this session's conversation", "page": "chats", "anchor": "set-keepHistory", "words": "history session conversation memory"},
{"action": "deleteAllChats", "label": "Delete all saved chats", "page": "chats", "anchor": "deleteAllChats", "words": "delete purge erase chats"},

{"key": "hud", "label": "Show what it heard and what it answered", "page": "other", "anchor": "set-hud", "words": "readout show while working hud readout overlay on screen text display"},
{"key": "hudLingerMs", "label": "How long the readout stays afterwards", "page": "other", "anchor": "set-hudLingerMs", "words": "hud readout linger stay time"},
{"key": "hudSize", "label": "Readout size", "page": "other", "anchor": "set-hudSize", "words": "hud readout size locked dynamic"},
{"key": "hudKeepReply", "label": "Keep the last answer on screen while I talk", "page": "other", "anchor": "set-hudKeepReply", "words": "hud readout keep reply answer"},
{"key": "hudPosition", "label": "Readout position", "page": "other", "anchor": "set-hudPosition", "words": "hud readout top bottom position"},
{"key": "hudTextSize", "label": "Readout text size", "page": "other", "anchor": "set-hudTextSize", "words": "hud readout font text size small large"},
{"action": "hudPreview", "label": "Preview the readout", "page": "other", "anchor": "hudPreview", "words": "hud readout preview test"},
{"key": "agentsPanel", "label": "Show each voice agent in Omarchy's Agents panel", "page": "other", "anchor": "set-agentsPanel", "words": "agents panel omarchy"},
{"key": "yieldToRecorders", "label": "Step aside when another app records", "page": "other", "anchor": "set-yieldToRecorders", "words": "yield recorders zoom meeting other app microphone"},
{"key": "logSpeech", "label": "Write what is said to the system log", "page": "other", "anchor": "set-logSpeech", "words": "log journal privacy transcript speech logging"},
{"key": "keepStats", "label": "Keep usage numbers for the Overview", "page": "other", "anchor": "set-keepStats", "words": "stats statistics usage numbers privacy"},
{"action": "clearStats", "label": "Clear stats", "page": "other", "anchor": "clearStats", "words": "stats statistics delete clear usage"},
{"action": "keys", "label": "Keys", "page": "other", "anchor": "keysGroup", "words": "keyboard shortcuts keybindings bindings hotkeys push to talk"},
{"action": "repair", "label": "Repair", "page": "other", "anchor": "repair", "words": "repair reinstall install fix broken"},
{"action": "remove", "label": "Remove Agent Voice", "page": "other", "anchor": "removeEverything", "words": "remove uninstall delete everything"},

{"key": "mainName", "field": "label", "label": "Name", "page": "agents", "anchor": "agent-label", "words": "agent name label display called"},
{"key": "phrase", "field": "name", "label": "Wake phrase", "page": "agents", "anchor": "agent-name", "words": "wake word phrase hotword trigger name call hey computer"},
{"key": "mainProgram", "field": "agent", "label": "Runs on", "page": "agents", "anchor": "agent-program", "words": "program backend cli claude code codex gemini antigravity copilot default agent"},
{"key": "agentModels", "field": "model", "label": "Model", "page": "agents", "anchor": "agent-model", "words": "model opus sonnet haiku fable gpt llm"},
{"key": "agentEfforts", "field": "effort", "label": "Effort", "page": "agents", "anchor": "agent-model", "words": "effort thinking reasoning how hard low medium high"},
{"key": "permissions", "field": "level", "label": "Permission level", "page": "agents", "anchor": "agent-level", "words": "permission level trust trusted ask edits allow approve safety"},
{"key": "projectDir", "field": "projectDir", "label": "Project folder", "page": "agents", "anchor": "agent-projectDir", "words": "project folder directory workspace repo working"},
{"key": "voice", "field": "voice", "label": "Voice", "page": "agents", "anchor": "agent-voice", "words": "voice piper tts speaker sounds like accent"},
{"key": "voiceSpeed", "field": "speed", "label": "Speaking speed", "page": "agents", "anchor": "agent-speed", "words": "speed rate pace fast slow talk"},
{"key": "mainSpeakWhenDone", "field": "speakWhenDone", "label": "Speak up when work finishes", "page": "agents", "anchor": "agent-speakWhenDone", "words": "announce background task done finished notification"},
{"key": "mainNotesWrite", "field": "notesWrite", "label": "May write notes", "page": "agents", "anchor": "agent-collab", "words": "notes write memory"},
{"key": "mainCollaboration", "field": "collaboration", "label": "Starts collaboration", "page": "agents", "anchor": "agent-collab", "words": "collaboration crew delegate ask other agents"},
{"key": "mainAcceptsWork", "field": "acceptsWork", "label": "Accepts work from agents", "page": "agents", "anchor": "agent-collab", "words": "accepts work delegate tasks crew"},
{"key": "mainChatSearch", "field": "chatSearch", "label": "Searches saved chats", "page": "agents", "anchor": "agent-collab", "words": "chat search saved chats own all off"},
{"key": "endpointUrl", "field": "endpointUrl", "label": "Endpoint URL", "page": "agents", "anchor": "agent-endpoint", "when": "the agent runs on an endpoint", "words": "endpoint url openai ollama lm studio vllm local server api"},
{"key": "endpointModel", "field": "endpointModel", "label": "Endpoint model", "page": "agents", "anchor": "agent-endpoint", "when": "the agent runs on an endpoint", "words": "endpoint model ollama local"},
{"key": "endpointIsAgent", "field": "endpointIsAgent", "label": "This endpoint is an agent", "page": "agents", "anchor": "agent-endpoint", "when": "the agent runs on an endpoint", "words": "endpoint agent hermes"},
{"key": "endpointTimeoutS", "field": "endpointTimeoutS", "label": "Endpoint timeout", "page": "agents", "anchor": "agent-endpoint", "when": "the agent runs on an endpoint", "words": "endpoint timeout seconds"},
{"key": "endpointHistoryTurns", "field": "endpointHistoryTurns", "label": "Endpoint turns remembered", "page": "agents", "anchor": "agent-endpoint", "when": "the agent runs on an endpoint", "words": "endpoint history turns memory"},
{"key": "owwModel", "label": "Wake model", "page": "agents", "agent": "main", "anchor": "set-owwModel", "when": "openWakeWord is chosen and installed", "words": "openwakeword phrase wake word jarvis alexa mycroft marvin"},
{"field": "narration", "label": "Talk while it works", "page": "agents", "anchor": "agent-narration", "words": "narration progress updates"},
{"field": "enabled", "label": "On", "page": "agents", "anchor": "agent-enabled", "words": "switch off disable enable agent"},
{"key": "voiceAgents", "label": "Add an agent", "page": "agents", "anchor": "addAgent", "words": "new agent add more agents another"},

{"key": "mainTools", "field": "tools", "label": "Tools", "page": "agentdetails", "tab": "tools", "anchor": "toolsTab", "words": "tools mcp servers desktop browser cli switches"},
{"key": "mainSkillsOff", "field": "skillsOff", "label": "Skills", "page": "agentdetails", "tab": "tools", "anchor": "skillsHeading", "words": "skills switch off unused"},
{"key": "mainResume", "field": "resume", "label": "Resume its conversation", "page": "agentdetails", "tab": "advanced", "anchor": "set-resume", "words": "resume session continue conversation fresh"},
{"key": "mainIdleTimeoutS", "field": "idleTimeoutS", "label": "Stop a turn after", "page": "agentdetails", "tab": "advanced", "anchor": "set-idleTimeoutS", "words": "hung-turn limit timeout hung stuck 90 seconds watchdog"},
{"key": "mainExtraArgs", "field": "extraArgs", "label": "Extra flags", "page": "agentdetails", "tab": "advanced", "anchor": "set-extraArgs", "words": "flags arguments command line options args"},
{"action": "agentEnv", "label": "Environment variables", "page": "agentdetails", "tab": "advanced", "anchor": "agentEnv", "words": "environment variables env api key"},

{"key": "desktopTools", "label": "Desktop tools", "page": "communal", "tab": "tools", "anchor": "set-desktopTools", "words": "desktop tools windows screenshot hyprland every agent"},
{"key": "browserTools", "label": "Browser", "page": "communal", "tab": "tools", "anchor": "set-browserTools", "words": "browser chrome web every agent"},
{"key": "omarchySkill", "label": "Omarchy skill", "page": "communal", "tab": "tools", "anchor": "set-omarchySkill", "words": "omarchy skill every agent"},
{"key": "agentvoiceSkill", "label": "Agent Voice skill", "page": "communal", "tab": "tools", "anchor": "set-agentvoiceSkill", "words": "agent voice skill every agent"},
{"key": "sharedTools", "label": "Tools found on this machine", "page": "communal", "tab": "tools", "anchor": "sharedToolsList", "words": "mcp servers detected found shared tools cli"},
{"key": "communalOff", "label": "Who gets Communal", "page": "communal", "tab": "who", "anchor": "communalWho", "words": "communal opt out who gets rules shared"},
{"key": "communalSkills", "label": "Communal skills", "page": "communal", "tab": "skills", "anchor": "communalList", "words": "communal skills shared group every agent remove add search"},

{"key": "crewLinks", "label": "Crew links", "page": "crew", "anchor": "crewMap", "words": "crew map links who may reach collaboration delegate"},
{"key": "crewQuarantine", "label": "Quarantine", "page": "crew", "anchor": "quarantineZone", "words": "quarantine isolate untrusted crew"},

{"action": "service", "label": "Voice service on or off", "page": "overview", "anchor": "serviceSwitch", "words": "service start stop turn off on power enable disable"},
{"action": "mute", "label": "Mute mic", "page": "overview", "anchor": "muteButton", "words": "mute unmute pause listening microphone deafen privacy"},

{"action": "diagnostics", "label": "Copy diagnostics", "page": "about", "anchor": "copyDiagnostics", "words": "diagnostics bug report help logs support"},
{"action": "updates", "label": "Check for updates", "page": "about", "anchor": "checkUpdates", "words": "update upgrade version new release"},
{"action": "setup", "label": "Run setup again", "page": "about", "anchor": "runSetup", "words": "setup first run wizard onboarding walk through start again"}
];
// END ENTRIES

// Lower case, letters and digits only, single spaces.
function norm(s) {
  return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim()
}

function wordsOf(s) {
  var n = norm(s)
  return n === "" ? [] : n.split(" ")
}

// How well one query word fits one candidate, 0 for not at all. A word of the
// label counts most, then a synonym, then the key, then the agent and page.
function tokenScore(t, c) {
  var best = 0
  for (var i = 0; i < c.labelWords.length; i++) {
    var w = c.labelWords[i]
    if (w === t) best = Math.max(best, 12)
    else if (w.indexOf(t) === 0) best = Math.max(best, 10)
    else if (t.length >= 3 && w.indexOf(t) > 0) best = Math.max(best, 5)
  }
  for (var j = 0; j < c.synonyms.length; j++) {
    var s = c.synonyms[j]
    if (s === t) best = Math.max(best, 8)
    else if (s.indexOf(t) === 0) best = Math.max(best, 6)
  }
  if (t.length >= 3 && c.keyNorm.indexOf(t) >= 0) best = Math.max(best, 4)
  for (var k = 0; k < c.agentWords.length; k++)
    if (c.agentWords[k].indexOf(t) === 0) best = Math.max(best, 4)
  for (var m = 0; m < c.pageWords.length; m++)
    if (c.pageWords[m].indexOf(t) === 0) best = Math.max(best, 2)
  return best
}

function pageLabel(pages, id) {
  for (var i = 0; i < pages.length; i++) if (pages[i].id === id) return String(pages[i].label)
  return id
}

var TAB_LABELS = { "tools": "Tools & skills", "advanced": "Advanced", "who": "Who gets it",
                   "prompt": "Role & instructions", "notes": "Notes", "chats": "Chats",
                   "rules": "Rules", "skills": "Skills", "preview": "Preview" }

// Every result there could be: an entry per setting, the agent ones once per
// agent, and each page by its own name. `pages` is Settings.pages
// ([{id, label}]); `agents` is [{id, label}], the main agent first as "main".
function candidates(pages, agents) {
  var out = []
  function add(e, agent, agentLabel, order) {
    var page = String(e.page)
    var path = [pageLabel(pages, page)]
    if (agentLabel) path.push(agentLabel)
    if (e.tab) path.push(TAB_LABELS[e.tab] || e.tab)
    if (e.advanced) path.push("Advanced")
    var keyText = e.key || e.field || e.action || ""
    out.push({
      label: String(e.label), page: page, agent: agent || "", tab: String(e.tab || ""),
      anchor: String(e.anchor || ""), when: String(e.when || ""), key: keyText,
      kind: e.action ? "action" : "setting", path: path.join(" › "), order: order,
      labelWords: wordsOf(e.label), synonyms: wordsOf(e.words), keyNorm: norm(keyText).replace(/ /g, ""),
      agentWords: wordsOf(agentLabel), pageWords: wordsOf(pageLabel(pages, page))
    })
  }
  for (var i = 0; i < ENTRIES.length; i++) {
    var e = ENTRIES[i]
    if (e.field !== undefined) {
      for (var a = 0; a < agents.length; a++) {
        var ag = agents[a]
        if (ag.id === "main" && e.key === undefined) continue
        add(e, ag.id, ag.label, i)
      }
    } else {
      add(e, e.agent || "", e.agent === "main" && agents.length > 0 ? agents[0].label : "", i)
    }
  }
  for (var p = 0; p < pages.length; p++) {
    out.push({ label: String(pages[p].label), page: String(pages[p].id), agent: "", tab: "",
               anchor: "", when: "", key: "", kind: "page", path: "Page", order: -1,
               labelWords: wordsOf(pages[p].label), synonyms: [], keyNorm: "",
               agentWords: [], pageWords: [] })
  }
  return out
}

// The best `limit` results for `query`, best first. Every word of the query
// must fit somewhere; a label that starts with the whole query comes first.
function search(query, pages, agents, limit) {
  var q = wordsOf(query)
  if (q.length === 0) return []
  var whole = norm(query)
  var all = candidates(pages || [], agents || [])
  var scored = []
  for (var i = 0; i < all.length; i++) {
    var c = all[i]
    var total = 0
    var fits = true
    for (var t = 0; t < q.length && fits; t++) {
      var s = tokenScore(q[t], c)
      if (s === 0) fits = false
      total += s
    }
    if (!fits) continue
    var label = norm(c.label)
    if (label === whole) total += 30
    else if (label.indexOf(whole) === 0) total += 20
    if (c.kind === "page") total += 1
    scored.push({ c: c, score: total })
  }
  scored.sort(function(x, y) {
    if (y.score !== x.score) return y.score - x.score
    return x.c.order - y.c.order
  })
  var out = []
  for (var j = 0; j < scored.length && out.length < (limit || 12); j++) {
    var r = scored[j].c
    out.push({ label: r.label, page: r.page, agent: r.agent, tab: r.tab, anchor: r.anchor,
               when: r.when, key: r.key, kind: r.kind, path: r.path })
  }
  return out
}
