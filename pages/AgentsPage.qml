import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// Every agent, the same way (feedback item 8, master plan M5): a header
// strip per agent -- state dot, name, wake phrase, what it runs on, effort,
// voice and speed, permission level -- that unfolds into cards, two across
// when there is room: Identity, Endpoint (endpoint agents only),
// Permissions, Voice, Tools, Collaboration, notes & chats, Agent.
//
// The main agent and the extra ones are one component, `AgentBlock`, below.
// They used to be two copies of every row, which is how they drifted apart.
// What differs is where a value is stored: the main agent's settings are
// top-level keys (some per program, in maps), an extra agent's are fields of
// its entry in `voiceAgents`. Every write goes through `writeField`, which
// names each key and field in its source, so the one-page tests can see the
// page that writes it.
//
// Settings are per agent because each is a judgement about one program: a
// model name means something to one CLI and nothing to the next, and a
// permission level that followed `omarchy default agent` would hand the
// next agent a decision nobody made about it.
//
// The tools every agent gets were the "On the desktop" group at the foot of
// this page, where they read as the last agent's (bug E). They are on
// Communal → Tools now; each agent's Tools card says which it has and where
// that comes from. Since M10 that card only reads: an agent's own tool
// switches, and the tools found on this machine, are set on Agent details →
// Tools & skills (`s.setAgentTool`), which the card links to.
Column {
  id: page

  required property var s

  spacing: Style.space(10)

  // --- the main agent's per-program settings ------------------------------------
  // Stored keyed by program in three maps, so switching Omarchy's default
  // agent and back finds each one's settings where it left them.
  readonly property string main: s.mainAgent

  function mapValue(key, agent) {
    var all = s.setting(key, {})
    if (!all || typeof all !== "object" || agent === "") return ""
    var v = all[agent]
    return typeof v === "string" ? v : ""
  }
  function putMap(key, agent, value) {
    if (agent === "") return
    var all = {}
    var current = s.setting(key, {})
    if (current && typeof current === "object")
      for (var k in current) all[k] = current[k]
    var v = String(value).trim()
    if (v === "") delete all[agent]
    else all[agent] = v
    s.put(key, all)
  }

  // Levels are stored per agent: trust is a judgement about one program's
  // capabilities, and letting it survive `omarchy default agent` would hand
  // the next one a decision nobody made about it.
  function setLevel(value) { putMap("permissions", page.main, value) }
  // Per agent, like the level: a model name means something to one CLI and
  // nothing to the next, so it must not follow `omarchy default agent`.
  function setModel(value) { putMap("agentModels", page.main, value) }
  // Per agent, like the model it depends on.
  function setEffort(value) { putMap("agentEfforts", page.main, value) }

  readonly property string mainVoice: String(s.setting("voice", "lessac-medium"))
  readonly property bool mainSpeaks: s.setting("speakReplies", true) === true
  readonly property int mainSpeed: Number(s.setting("voiceSpeed", 100)) || 100
  readonly property string mainModel: mapValue("agentModels", page.main)
  readonly property string mainEffort: mapValue("agentEfforts", page.main)
  // What is saved for this agent, else what the daemon says is in force.
  readonly property string mainLevel: mapValue("permissions", page.main) || s.permissionLevel

  // --- which agents are open ----------------------------------------------------
  // Kept here, by agent id ("main" for the main agent), not on the strips. A
  // strip's own `expanded` was a binding the header click overwrote, so any
  // time one was rebuilt it came back shut -- and every save rebuilt them all.
  property var openCards: ({})
  function isOpen(key) { return openCards[key] === true }
  function setOpen(key, open) {
    if (key === "" || isOpen(key) === open) return
    var all = {}
    for (var k in openCards) all[k] = openCards[k]
    if (open) all[key] = true
    else delete all[key]
    openCards = all
  }
  // A deep link ({page: "agents", agent: "sarah"}), a new agent, a rename.
  // {..., tab: "tools"} also marks that agent's Tools card (focusTools).
  Connections {
    target: page.s
    function onFocusAgentChanged() { page.openLinked() }
  }
  // Which agent starts open: the one linked to, else the main one when it is
  // the only one. Decided once the settings have loaded, not at creation --
  // before that every list reads empty, so the main agent always opened.
  function openLinked() {
    if (s.focusAgent === "") return
    setOpen(s.focusAgent, true)
  }
  property bool openingDecided: false
  function decideOpening() {
    if (openingDecided || !s.store.loaded) return
    openingDecided = true
    if (s.focusAgent !== "") openLinked()
    else if (s.voiceAgents.length === 0) setOpen("main", true)
  }
  Connections {
    target: page.s.store
    function onLoadedChanged() { page.decideOpening() }
  }
  Component.onCompleted: decideOpening()

  // --- the extra agents -------------------------------------------------------
  function saveAgents(list) { s.put("voiceAgents", list) }

  // An entry as it was, every field its own property. Defined rather than
  // assigned: a field named "__proto__" (JSON.parse makes it an ordinary
  // field) would otherwise go through the prototype setter and vanish from
  // the saved list (Codex review, M5).
  function copyEntry(a) {
    var copy = {}
    var keys = Object.keys(a || {})
    for (var k = 0; k < keys.length; k++)
      Object.defineProperty(copy, keys[k], { value: a[keys[k]], enumerable: true, writable: true, configurable: true })
    return copy
  }

  // One field of one entry. Every other field of that entry, and every other
  // entry, is copied as it was -- including fields this build does not know,
  // so a newer build's settings survive an edit here (test_agents_page.py
  // runs this function and compares the rest byte for byte).
  function updateAgent(index, key, value) {
    var list = []
    for (var i = 0; i < s.voiceAgents.length; i++) {
      var a = s.voiceAgents[i] || {}
      var copy = copyEntry(a)
      // Written down before anything changes, the wake phrase above all: an
      // entry from before ids existed is known by the one derived from it.
      copy.id = s.agentId(a)
      if (i === index) {
        if (value === undefined) delete copy[key]
        else copy[key] = value
      }
      list.push(copy)
    }
    saveAgents(list)
  }

  function addAgent() {
    if (s.voiceAgents.length >= s.maxAgents) return
    var taken = {}
    var mine = s.activePhrase.split(" ")
    for (var m = 0; m < mine.length; m++) taken[mine[m]] = true
    for (var i = 0; i < s.voiceAgents.length; i++)
      taken[String((s.voiceAgents[i] || {}).name || "")] = true
    var name = ""
    for (var j = 0; j < s.nameSuggestions.length && name === ""; j++)
      if (!taken[s.nameSuggestions[j]]) name = s.nameSuggestions[j]
    var list = []
    for (var n = 0; n < s.voiceAgents.length; n++) {
      var a = s.voiceAgents[n] || {}
      var copy = copyEntry(a)
      copy.id = s.agentId(a)
      list.push(copy)
    }
    var id = s.newAgentId(name)
    // No `instructions`: they live in its folder now (merged plan, Phase 10).
    list.push({ id: id, name: name, label: "", agent: "claude", model: "", effort: "", voice: "",
                speed: 0, narration: "", level: "ask", projectDir: "" })
    s.focusAgent = id
    saveAgents(list)
    s.folders.create(id)
  }

  // --- agent folders (merged plan, Phases 10 and 12) ----------------------------
  // Adding an agent makes its folder; removing one moves the folder to the
  // trash with its settings entry beside it, so Undo gives the agent back
  // whole. The work is the overlay's AgentFolders, shared with Agent
  // details, so an operation and its Undo outlive this page.
  function removeAgent(index) { s.folders.remove(index) }
  function undoRemove() { s.folders.undo() }

  // What is in an agent's folder, in one line, for the Agent card: the files
  // are edited on Agent details, never here (one editor per file). Sizes
  // only, from the daemon while it runs, else from the overlay's own read.
  function folderSummary(id, legacy) {
    var mine = s.serviceActive ? s.vAgentFiles[id] : undefined
    var f = mine || s.folders.folders[id]
    if (!f) return s.folders.foldersRead ? "No folder yet." : ""
    var files = f.files || {}
    function size(name, word) {
      var x = files[name] || {}
      if (name === "instructions.md" && x.exists !== true && String(legacy || "").trim() !== "")
        return word + ": the old setting, " + String(legacy).trim().length + " characters"
      return word + ": " + ((x.chars || 0) > 0 ? x.chars + " characters" : "none")
    }
    var out = [size("role.md", "Role"), size("personality.md", "personality"),
               size("instructions.md", "instructions")].join(" · ")
    var outside = f.changed_outside || []
    var skillsOutside = outside.filter(function(n) { return n.indexOf("skills/") === 0 })
    if (outside.length > skillsOutside.length) out += " · changed outside Settings"
    // A skill is made by hand; it is kept on Agent details' Tools & skills.
    if (skillsOutside.length > 0)
      out += " · " + (skillsOutside.length === 1 ? "a skill" : skillsOutside.length + " skills") +
             " added or changed outside Settings (Tools & skills)"
    if ((f.problems || []).length > 0) out += " · " + f.problems[0]
    return out
  }

  // --- tool switches (merged plan, Phase 13) ----------------------------------
  // Each agent's own, beating the settings for every agent on Communal →
  // Tools. Read here for the Tools card's summary and the Rule of Two; since
  // M10 they are written on Agent details → Tools & skills only, through
  // `s.setAgentTool`.
  readonly property var toolGlobals: ({
    desktop: s.setting("desktopTools", false) === true,
    browser: s.setting("browserTools", false) === true,
    omarchySkill: s.setting("omarchySkill", true) === true,
    agentvoiceSkill: s.setting("agentvoiceSkill", true) === true
  })
  readonly property var sharedTools: s.setting("sharedTools", {})
  // Leave out the keys for the notes and collaboration defaults.
  function putAgentNotes(index, value) {
    updateAgent(index, "notesWrite", value === "allow" ? undefined : "deny")
  }
  function putAgentCollab(index, value) {
    updateAgent(index, "collaboration", value === "announce" ? undefined : value)
  }
  function putAgentAccepts(index, value) {
    updateAgent(index, "acceptsWork", value ? undefined : false)
  }
  // Master plan M20: "own" is the default, so it is left out. "all" arrives
  // only from ToolSwitches' question (its onConfirmed).
  function putAgentChatSearch(index, value) {
    updateAgent(index, "chatSearch", value === "own" ? undefined : value)
  }
  // Master plan M27: on is the default, so it is left out; only false is
  // written (anything else the daemon reads as off).
  function putAgentSpeakWhenDone(index, value) {
    updateAgent(index, "speakWhenDone", value === true ? undefined : false)
  }
  // The quarantine, read for the Chat search row's hint (written on the
  // Crew map only): a list, or "unreadable" when it is not one.
  readonly property var crewQuarantine: s.setting("crewQuarantine", [])
  function quarantineOf(agentId) {
    if (!Array.isArray(crewQuarantine)) return "unreadable"
    return crewQuarantine.indexOf(agentId === "" ? "main" : agentId) >= 0
  }
  // The Rule of Two (merged plan, Phase 13): reading web pages, acting
  // without asking, and being able to change what the other agents are
  // told, all in one agent. A warning, not a block. Denying notes writes
  // (Phase 14) does not lift it: at Trust everything a Claude agent can
  // still rewrite the communal rules and skills with a shell command
  // (Phase 13 review).
  // Since M10 an MCP server found on this machine and switched on counts as
  // outside content too: what it returns is text nobody here wrote.
  function ruleOfTwo(program, level, choices) {
    var own = (choices && typeof choices === "object") ? choices : {}
    var c = own.browser
    var browser = program === "claude" && (c === "on" || (c !== "off" && toolGlobals.browser))
    var shared = (sharedTools && typeof sharedTools === "object") ? sharedTools : {}
    var server = false
    var keys = Object.keys(own).concat(Object.keys(shared))
    for (var i = 0; i < keys.length; i++) {
      if (keys[i].indexOf("mcp:") !== 0) continue
      var v = own[keys[i]] !== undefined ? own[keys[i]] : shared[keys[i]]
      if (/^on:[0-9a-f]{32}$/.test(String(v))) server = true
    }
    server = server && (program === "claude" || program === "codex")
    if ((!browser && !server) || level !== "trusted") return ""
    var what = browser && server ? "web pages and a tool server's output" : browser ? "web pages" : "a tool server's output"
    return "It reads " + what + ", acts without asking, and can change what the other agents are " +
           "told (the communal rules, skills and notes). Outside text could steer it into doing that. " +
           "Turning " + (browser ? "its browser" : "the server") + " off, or asking first, takes the risk away."
  }

  // --- every write, by agent and field ------------------------------------------
  // index -1 is the main agent. Each key and each field is named, so the page
  // that writes it says so in its source (test_settings_pages.py's
  // FIELD_HOMES reads these). Values arrive already cleaned by the control.
  function writeField(index, field, value) {
    if (index < 0) {
      switch (field) {
      case "label": s.put("mainName", value); break
      case "name": s.put("phrase", value); break
      case "agent": runOn(value); break
      case "model": setModel(value); break
      case "effort": setEffort(value); break
      case "level": setLevel(value); break
      case "voice": s.put("voice", value); s.chooseVoice(value); break
      case "speed": s.put("voiceSpeed", value); break
      case "projectDir": s.put("projectDir", value); break
      case "notesWrite": s.put("mainNotesWrite", value); break
      case "collaboration": s.put("mainCollaboration", value); break
      case "acceptsWork": s.put("mainAcceptsWork", value); break
      case "chatSearch": s.put("mainChatSearch", value); break
      case "speakWhenDone": s.put("mainSpeakWhenDone", value); break
      }
      return
    }
    switch (field) {
    case "enabled": updateAgent(index, "enabled", value); break
    case "label": updateAgent(index, "label", value); break
    case "name": updateAgent(index, "name", value); break
    case "agent": updateAgent(index, "agent", value); break
    case "model": updateAgent(index, "model", value); break
    case "effort": updateAgent(index, "effort", value); break
    case "level": updateAgent(index, "level", value); break
    case "voice": updateAgent(index, "voice", value); s.chooseVoice(value); break
    case "speed": updateAgent(index, "speed", value); break
    case "narration": updateAgent(index, "narration", value); break
    case "projectDir": updateAgent(index, "projectDir", value); break
    case "notesWrite": putAgentNotes(index, value); break
    case "collaboration": putAgentCollab(index, value); break
    case "acceptsWork": putAgentAccepts(index, value); break
    case "chatSearch": putAgentChatSearch(index, value); break
    case "speakWhenDone": putAgentSpeakWhenDone(index, value); break
    }
  }
  // The EndpointEditor's edited(key, value), for the main agent; an extra
  // agent's goes straight to updateAgent with the key it was given.
  function putMainEndpoint(key, value) {
    switch (key) {
    case "endpointUrl": s.put("endpointUrl", value); break
    case "endpointModel": s.put("endpointModel", value); break
    case "endpointIsAgent": s.put("endpointIsAgent", value); break
    case "endpointTimeoutS": s.put("endpointTimeoutS", value); break
    case "endpointHistoryTurns": s.put("endpointHistoryTurns", value); break
    }
  }

  // "Runs on" for the main agent. Chosen locally until both endpoint boxes
  // are filled, because a half-filled endpoint is not in use.
  property bool endpointChosen: s.usingEndpoint || String(s.setting("endpointUrl", "")) !== ""
  // The main agent's own program; "" follows Omarchy's default.
  readonly property string mainProgram: String(s.setting("mainProgram", ""))
  function runOn(v) {
    if (v === "endpoint") { page.endpointChosen = true; return }
    page.endpointChosen = false
    var program = v === "omarchy" ? "" : v
    if (program !== page.mainProgram) page.s.put("mainProgram", program)
    // Clearing both is what hands the turn back from an endpoint.
    if (String(page.s.setting("endpointUrl", "")) !== "") page.s.put("endpointUrl", "")
    if (String(page.s.setting("endpointModel", "")) !== "") page.s.put("endpointModel", "")
  }
  // A move to "trusted" waits here for a second click, by agent id.
  property string trustPending: ""

  readonly property var levelTones: ({ trusted: "alert", edits: "busy" })
  readonly property var programChoices: page.s.programOptions.map(function(o) {
    return o.value === "endpoint" ? { value: "endpoint", label: "OpenAI-compatible endpoint" } : o })

  PageHeader {
    width: parent.width
    title: "Agents"
    subtitle: "Who answers, what each one may do, and where. Click an agent to open it."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  Text {
    width: parent.width
    wrapMode: Text.WordWrap
    visible: page.s.usingOww && page.s.voiceAgents.length > 0
    text: "⚠  openWakeWord hears only its own phrase, so the agents below the first " +
          "cannot be woken. Switch the wake engine to Vosk on the Listening page."
    textFormat: Text.PlainText
    color: page.s.urgent
    font.family: page.s.fontFamily
    font.pixelSize: Style.font.caption
  }

  // --- one agent ------------------------------------------------------------------
  // agentIndex -1 is the main agent. Inline components do not see the page's
  // ids, so the page comes in as `pg`.
  component AgentBlock: HeaderStrip {
    id: blk
    // Master plan M28: Settings search finds a control inside one agent's
    // block by this name first, then by the control's own ("agent-model").
    objectName: "agent-" + agentId

    required property var pg
    property int agentIndex: -1

    readonly property var s: pg.s
    readonly property bool isMain: agentIndex < 0
    readonly property var entry: isMain ? ({}) : (s.voiceAgents[agentIndex] || ({}))
    // What everything else knows it by; see Settings.agentId.
    readonly property string agentId: isMain ? "main" : s.agentId(entry)
    readonly property string label: isMain ? s.mainLabel : s.agentLabel(entry)
    readonly property string wake: isMain ? s.activePhrase : String(entry.name || "")
    readonly property var info: isMain ? ({}) : s.crewInfo(agentId)
    readonly property string program: isMain ? (pg.endpointChosen ? "endpoint" : pg.main)
                                             : String(entry.agent || "claude")
    readonly property bool endpoint: program === "endpoint"
    // The value the "Runs on" list shows: the main agent has Omarchy's
    // default as a choice of its own.
    readonly property string runsOn: isMain ? (pg.endpointChosen ? "endpoint" : (pg.mainProgram || "omarchy"))
                                            : program
    readonly property string model: isMain ? pg.mainModel : String(entry.model || "")
    readonly property string effort: isMain ? pg.mainEffort : String(entry.effort || "")
    readonly property var efforts: isMain ? s.vEfforts : (Array.isArray(info.efforts) ? info.efforts : [])
    // Whether `efforts` is the daemon's answer for the model in force. An
    // extra agent the daemon has not built yet is listed with no efforts and
    // no posture, which says nothing about its model (Codex review, M5).
    readonly property bool effortsKnown: isMain ? s.serviceActive && s.vEffortsKnown
                                                : Array.isArray(info.efforts) && String(info.posture || "") !== ""
    readonly property var levels: isMain ? s.agentLevels
                                         : (Array.isArray(info.levels) ? info.levels : ["ask", "edits", "trusted"])
    readonly property string level: isMain ? pg.mainLevel : String(entry.level || "ask")
    readonly property string posture: isMain ? s.vPosture : String(info.posture || "")
    // "" for an extra agent is "same as the main agent".
    readonly property string voice: isMain ? pg.mainVoice : String(entry.voice || "")
    readonly property string voiceHeard: voice !== "" ? voice : pg.mainVoice
    // 0 (or nothing) for an extra agent is "same as the main agent".
    readonly property int speed: isMain ? pg.mainSpeed : Number(entry.speed || 0)
    readonly property int speedHeard: speed > 0 ? speed : pg.mainSpeed
    // The pace ▶ Test asks for, by playSample's own rule (a speed out of
    // range plays at the main agent's), so its button knows its own sample.
    readonly property int testPace: speedHeard >= 50 && speedHeard <= 200 ? speedHeard : pg.mainSpeed
    readonly property string projectDir: isMain ? s.projectDir : String(entry.projectDir || "")
    readonly property var tools: isMain ? s.setting("mainTools", {}) : (entry.tools || ({}))
    // Exactly "allow" is allow; anything else is what the daemon reads as
    // deny (runtime.notes_choice), so the switch never says more. A missing
    // field on an extra agent is "allow".
    readonly property string notesWrite: isMain
        ? (s.setting("mainNotesWrite", "allow") === "allow" ? "allow" : "deny")
        : (entry.notesWrite === undefined || entry.notesWrite === "allow" ? "allow" : "deny")
    readonly property string collaboration: isMain ? String(s.setting("mainCollaboration", "announce"))
        : (entry.collaboration === undefined ? "announce" : String(entry.collaboration))
    readonly property bool acceptsWork: isMain ? s.setting("mainAcceptsWork", true) !== false
                                               : entry.acceptsWork !== false
    // Master plan M20: missing is "own" (runtime.chat_search_choice).
    readonly property string chatSearch: isMain ? String(s.setting("mainChatSearch", "own"))
        : (entry.chatSearch === undefined ? "own" : String(entry.chatSearch))
    // Master plan M27: missing is on, and only a true is on
    // (runtime.speak_when_done_choice), so the switch never says more.
    readonly property bool speakWhenDone: isMain ? s.setting("mainSpeakWhenDone", true) === true
        : (entry.speakWhenDone === undefined || entry.speakWhenDone === true)
    // What it can announce at all, by program: tier 1 needs the crew tools
    // (Claude Code, Codex), tier 2 a process that outlives its turn.
    readonly property string speakWhenDoneHint: {
      if (endpoint) return "Nothing to announce: an endpoint does no work in the background."
      if (program === "claude")
        return "When its own background command or helper finishes, or a task it gave another agent to report back on, it says one short line without waiting for its name, and a notification appears. Only the notification while the screen is locked, the microphone is muted or notifications are silenced."
      if (program === "codex")
        return "When a task it gave another agent to report back on finishes, it says so in one short line and a notification appears. Codex's own background work ends with each turn, so there is none of that to announce."
      return "Nothing to announce for " + (s.programLabel(program) || "this program") + ": only Claude Code and Codex agents start work Agent Voice can see finish."
    }
    // Missing means on, so lists from before the switch keep every agent.
    readonly property bool on: isMain || entry.enabled !== false
    readonly property string st: s.agentStatus(isMain ? "" : agentId)
    property bool customModel: false
    onProgramChanged: customModel = false

    function write(field, value) { pg.writeField(agentIndex, field, value) }
    function modelProblem() {
      if (isMain && pg.main === "") return "No default agent is set."
      if (isMain) return s.serviceActive && !s.vTakesModel ? pg.main + " does not take a model from here." : ""
      return info.takes_model === false ? s.programLabel(program) + " does not take a model from here." : ""
    }

    width: pg.width
    controlled: true
    expanded: pg.isOpen(agentId)
    onToggled: function(open) { pg.setOpen(blk.agentId, open) }
    dimmed: !on
    name: label || "New agent"
    status: (wake !== "" ? "“" + wake + "” · " : "") + (on ? st : "switched off")
    tone: on ? s.statusTone(st) : "idle"
    // Most important first: the first pill is the last to give way.
    pills: {
      var out = []
      if (!endpoint)
        out.push({ text: s.levelLabel(level, levels).toLowerCase(), tone: pg.levelTones[level] || "idle",
                   tooltip: "Permission: " + s.levelLabel(level, levels) + (posture !== "" ? " (in force: " + posture + ")" : "") })
      var runs = endpoint ? "Endpoint" : (s.programLabel(program) || "no agent")
      var m = endpoint ? String(isMain ? s.setting("endpointModel", "") : (entry.endpointModel || "")) : model
      out.push({ text: runs + (m !== "" ? " · " + m : ""),
                 tooltip: isMain && !endpoint && pg.mainProgram === "" ? "Omarchy's default coding agent" : "What it runs on" })
      if (!endpoint && effort !== "")
        out.push({ text: s.effortNames[effort] || effort, tooltip: "Effort" })
      out.push({ text: pg.mainSpeaks ? s.voiceName(voiceHeard) + " · " + speedHeard + "%" : "silent",
                 tooltip: !pg.mainSpeaks ? "Replies are not spoken."
                          : "Voice and speaking speed" +
                            (!isMain && voice === "" ? "; the voice follows the main agent" : "") +
                            (!isMain && speed === 0 ? "; the speed follows the main agent" : "") })
      return out
    }
    problem: !on ? ""
             : isMain
               ? (!pg.endpointChosen && pg.main === ""
                  ? "No default agent is set. Choose one with `omarchy default agent`."
                  : s.projectDir.trim() === "" && pg.mainLevel === "edits" && !pg.endpointChosen
                    ? "No project folder, so “edits are fine” has nothing to be inside: every change is asked about."
                    : "")
               : String(info.problem || "") !== "" ? String(info.problem)
               : wake !== "" && !/^[a-z]+( [a-z]+){0,2}$/.test(wake)
                 ? "A wake phrase is one to three plain words, letters only." : ""
    warning: on && !endpoint ? pg.ruleOfTwo(program, level, tools) : ""
    foreground: s.foreground
    fontFamily: s.fontFamily

    CardGrid {
      width: parent.width

      // --- Identity --------------------------------------------------------------
      Card {
        title: "Identity"
        foreground: blk.s.foreground
        fontFamily: blk.s.fontFamily

        Text {
          width: parent.width
          visible: blk.isMain
          wrapMode: Text.WordWrap
          text: "Always on: something has to answer “" + blk.s.activePhrase + "”."
          textFormat: Text.PlainText
          color: blk.s.dim
          font.family: blk.s.fontFamily
          font.pixelSize: Style.font.caption
        }

        // Name and wake phrase side by side when the card is wide enough.
        Grid {
          id: names
          width: parent.width
          columns: width >= Style.space(200) ? 2 : 1
          columnSpacing: Style.space(10)
          rowSpacing: Style.space(8)
          readonly property real cell: columns === 2 ? (width - columnSpacing) / 2 : width

          SettingRow {
            objectName: "agent-label"
            width: names.cell
            stacked: true
            label: "Name"
            hint: "Shown on screen."
            help: "What it is called on screen, in saved chats and in the Agents panel. Any text, " +
                  "up to 40 characters. Empty uses the wake phrase."
            changed: blk.isMain ? blk.s.changed("mainName") : blk.s.cleanLabel(blk.entry.label) !== ""
            foreground: blk.s.foreground
            fontFamily: blk.s.fontFamily
            onReset: blk.isMain ? blk.s.resetKey("mainName") : blk.write("label", "")
            TextField {
              text: blk.isMain ? String(blk.s.setting("mainName", "")) : blk.s.cleanLabel(blk.entry.label)
              placeholderText: blk.s.capitalised(blk.wake) || "a name to show"
              foreground: blk.s.foreground
              font.family: blk.s.fontFamily
              onEditingFinished: {
                var v = blk.s.cleanLabel(text)
                var was = blk.isMain ? String(blk.s.setting("mainName", "")) : blk.s.cleanLabel(blk.entry.label)
                if (v !== was) blk.write("label", v)
              }
            }
          }

          SettingRow {
            objectName: "agent-name"
            width: names.cell
            stacked: true
            label: "Wake phrase"
            hint: blk.isMain && blk.s.owwLive ? "A wake model, under Agent." : "What wakes it."
            help: (blk.isMain ? "What you say to start a turn with this agent, such as a name. "
                              : "What you say to wake it. Changing it keeps the conversation. ") +
                  "One to three plain words; Enter saves."
            changed: blk.isMain && !blk.s.owwLive && blk.s.changed("phrase")
            foreground: blk.s.foreground
            fontFamily: blk.s.fontFamily
            onReset: blk.s.resetKey("phrase")
            TextField {
              visible: !(blk.isMain && blk.s.owwLive)
              text: blk.isMain ? blk.s.setting("phrase", "hey computer") : blk.wake
              placeholderText: blk.isMain ? "a name or phrase — the words that wake it" : "the word that wakes it"
              foreground: blk.s.foreground
              font.family: blk.s.fontFamily
              onEditingFinished: {
                var v = text.trim().toLowerCase().replace(/\s+/g, " ")
                if (blk.isMain) {
                  // The main phrase is checked here; an extra agent's is
                  // saved as typed and its header says what is wrong.
                  if (!/^[a-z']+( [a-z']+){0,2}$/.test(v)) { text = blk.s.setting("phrase", "hey computer"); return }
                  if (v !== blk.s.setting("phrase", "hey computer")) blk.write("name", v)
                } else if (v !== blk.wake) blk.write("name", v)
              }
            }
            Text {
              visible: blk.isMain && blk.s.owwLive
              text: blk.s.capitalised(blk.s.activePhrase)
              textFormat: Text.PlainText
              color: blk.s.foreground
              font.family: blk.s.fontFamily
            }
          }
        }

        SettingRow {
          objectName: "agent-program"
          width: parent.width
          stacked: true
          label: "Runs on"
          hint: blk.endpoint ? "Any OpenAI-compatible endpoint: Ollama, LM Studio, vLLM, OpenAI, xAI, Hermes."
                : blk.isMain && blk.pg.mainProgram === "" ? "Omarchy's default, which `omarchy default agent` changes."
                : "Its own program, whatever Omarchy's default agent is."
          changed: blk.isMain ? (blk.pg.mainProgram !== "" || blk.pg.endpointChosen) : blk.program !== "claude"
          foreground: blk.s.foreground
          fontFamily: blk.s.fontFamily
          onReset: { blk.customModel = false; blk.write("agent", blk.isMain ? "omarchy" : "claude") }
          // A dropdown: seven choices do not fit on one row of chips.
          Dropdown {
            width: parent.width
            showLabel: false
            options: blk.isMain
                     ? [{ value: "omarchy", label: "Omarchy's default" +
                          (blk.s.defaultAgent ? " (" + blk.s.programLabel(blk.s.defaultAgent) + ")" : "") }]
                       .concat(blk.pg.programChoices)
                     : blk.pg.programChoices
            value: blk.runsOn
            foreground: blk.s.foreground
            fontFamily: blk.s.fontFamily
            onChanged: function(v) {
              if (v === blk.runsOn) return
              blk.customModel = false
              blk.write("agent", v)
            }
          }
        }

        // The model and its effort, joined: effort means nothing without the
        // model it belongs to. Only the levels the model in force takes,
        // which the daemon publishes.
        SettingRow {
          objectName: "agent-model"
          width: parent.width
          visible: !blk.endpoint
          stacked: true
          label: "Model"
          // An effort saved that the model in force does not take: the
          // picker shows it as saved, so "Default" clears it, and when the
          // model takes no effort at all the reset link does (Codex review,
          // M5; the old Effort row had a reset of its own).
          readonly property bool staleEffort: blk.effort !== "" && blk.effortsKnown && blk.efforts.indexOf(blk.effort) < 0
          hint: staleEffort
                ? (blk.efforts.length > 0 ? "⚠  The effort saved is not one this model takes, so the default is in use."
                                          : "⚠  An effort is saved, and this model takes none: reset clears it.")
                : "Only for voice. A new model starts a new conversation; effort keeps it."
          changed: staleEffort
          onReset: blk.write("effort", "")
          help: "Your other sessions keep their own model. Effort is how hard it thinks before answering."
          foreground: blk.s.foreground
          fontFamily: blk.s.fontFamily
          Column {
            width: parent.width
            spacing: Style.space(6)
            ModelPicker {
              // Never wider than the card: a long model name elides, and the
              // effort half stays in reach.
              width: Math.min(implicitWidth, parent.width)
              models: blk.s.agentModelChoices(blk.program, blk.model)
              model: blk.customModel ? "__other__" : blk.model
              modelReason: blk.modelProblem()
              efforts: blk.efforts.length > 0 ? blk.s.effortChoices(blk.efforts) : []
              effort: blk.effort
              effortReason: blk.efforts.length > 0 ? ""
                            : blk.s.serviceActive ? "This model takes no effort level."
                            : "Shown once the service is running, for a model that takes one."
              foreground: blk.s.foreground
              accent: blk.s.accent
              fontFamily: blk.s.fontFamily
              onModelCommitted: function(v) {
                if (v === "__other__") { blk.customModel = true; return }
                blk.customModel = false
                if (v !== blk.model) blk.write("model", v)
              }
              onEffortCommitted: function(v) { if (v !== blk.effort) blk.write("effort", v) }
            }
            TextField {
              width: parent.width
              visible: blk.customModel
              text: blk.model
              placeholderText: "type a model name or full model id"
              foreground: blk.s.foreground
              font.family: blk.s.fontFamily
              onEditingFinished: {
                if (text.trim() !== blk.model) blk.write("model", text.trim())
              }
            }
            Text {
              width: parent.width
              wrapMode: Text.WordWrap
              visible: blk.model !== ""
                       && !/^[A-Za-z0-9][A-Za-z0-9._:\/@\[\]-]{0,127}$/.test(blk.model)
              text: "⚠  Not accepted as a model name, so the default is in use."
              color: blk.s.urgent
              font.family: blk.s.fontFamily
              font.pixelSize: Style.font.caption
            }
          }
        }
      }

      // --- Endpoint (endpoint agents only) -----------------------------------------
      // The model, effort, permission and folder rows do not apply to one:
      // agentvoice offers an endpoint no tools.
      Card {
        objectName: "agent-endpoint"
        visible: blk.endpoint
        title: "Endpoint"
        foreground: blk.s.foreground
        fontFamily: blk.s.fontFamily

        EndpointEditor {
          width: parent.width
          url: String(blk.isMain ? blk.s.setting("endpointUrl", "") : (blk.entry.endpointUrl || ""))
          model: String(blk.isMain ? blk.s.setting("endpointModel", "") : (blk.entry.endpointModel || ""))
          isAgent: blk.isMain ? blk.s.setting("endpointIsAgent", false) === true : blk.entry.endpointIsAgent === true
          timeoutS: Number(blk.isMain ? blk.s.setting("endpointTimeoutS", 0) : (blk.entry.endpointTimeoutS || 0))
          historyTurns: blk.isMain ? Number(blk.s.setting("endpointHistoryTurns", 8))
                        : blk.entry.endpointHistoryTurns === undefined ? 8 : Number(blk.entry.endpointHistoryTurns)
          foreground: blk.s.foreground
          urgent: blk.s.urgent
          fontFamily: blk.s.fontFamily
          onEdited: function(key, value) { if (blk.isMain) blk.pg.putMainEndpoint(key, value); else blk.pg.updateAgent(blk.agentIndex, key, value) }
        }
        // An extra agent's endpoint has no folder of ours (the daemon reports
        // it as not governed), so this always applies to one.
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          visible: !blk.isMain || blk.s.vOverriding !== "" || !blk.s.vGoverned
          text: (blk.isMain && blk.s.vOverriding !== ""
                 ? "⚠  Answering instead of " + blk.s.vOverriding + ", Omarchy's default. " : "⚠  ") +
                "It works on its own machine, in a directory it chooses: the project " +
                "folder and permission level here reach nothing over there. Restrain " +
                "it where it runs."
          textFormat: Text.PlainText
          color: blk.s.urgent
          font.family: blk.s.fontFamily
          font.pixelSize: Style.font.caption
        }
      }

      // --- Permissions -----------------------------------------------------------
      // The directory and what is allowed in it are one decision, not two: a
      // permission level with no root to apply to means nothing.
      Card {
        visible: !blk.endpoint
        title: "Permissions"
        foreground: blk.s.foreground
        fontFamily: blk.s.fontFamily

        SettingRow {
          objectName: "agent-level"
          width: parent.width
          stacked: true
          label: "Level"
          hint: blk.level === "trusted"
                ? (blk.isMain ? "Nothing is asked. A spoken sentence can edit files and run commands here with nothing able to stop it."
                              : "Nothing is asked. A sentence starting with “" + blk.wake + "” can edit files and run commands in its folder.")
                : blk.level === "edits"
                  ? "Source files in its folder are edited without asking. Commands, the network and anything outside still ask."
                  : blk.levels.indexOf("edits") < 0 && blk.s.serviceActive
                    ? (blk.isMain ? blk.pg.main : blk.s.programLabel(blk.program)) +
                      " cannot put a question on screen, so it is held read-only and may refuse work rather than ask."
                    : "Every change is asked about on screen. An unanswered question is denied." +
                      (blk.isMain ? "" : " Its own level: what you allow the main agent does not carry over.")
          help: (blk.posture !== "" ? "In force: " + blk.posture + ".\n\n" : "") +
                "Reading is free except for keys, credentials and shell history. Under " +
                "“edits”, files that make something else run — .git/hooks, .envrc, " +
                ".claude/settings.json — still ask. Your home directory is not accepted " +
                "as a project: it holds the file this level is stored in."
          disabledReason: blk.isMain && blk.pg.main === "" ? "No default agent is set." : ""
          foreground: blk.s.foreground
          fontFamily: blk.s.fontFamily
          Column {
            width: parent.width
            spacing: Style.space(6)
            SegmentedChoice {
              wrap: true
              width: parent.width
              options: blk.s.levelChoices(blk.levels)
              value: blk.pg.trustPending === blk.agentId ? "trusted" : blk.level
              foreground: blk.s.foreground
              accent: blk.level === "trusted" ? blk.s.urgent : blk.s.accent
              fontFamily: blk.s.fontFamily
              onCommitted: function(v) {
                if (v === "trusted") { blk.pg.trustPending = blk.agentId; return }
                blk.pg.trustPending = ""
                blk.write("level", v)
              }
            }
            Flow {
              width: parent.width
              visible: blk.pg.trustPending === blk.agentId
              spacing: Style.space(10)
              Text {
                width: Math.min(implicitWidth, parent.width)
                wrapMode: Text.WordWrap
                text: blk.isMain ? "Let a spoken sentence run anything here?"
                                 : "Let a spoken sentence run anything in its folder?"
                color: blk.s.urgent
                font.family: blk.s.fontFamily
                font.pixelSize: Style.font.caption
              }
              Button {
                text: "Trust it"
                bordered: true
                foreground: blk.s.urgent
                accent: blk.s.urgent
                fontFamily: blk.s.fontFamily
                onClicked: { blk.pg.trustPending = ""; blk.write("level", "trusted") }
              }
              Button {
                text: "Cancel"
                bordered: true
                foreground: blk.s.foreground
                fontFamily: blk.s.fontFamily
                onClicked: blk.pg.trustPending = ""
              }
            }
          }
        }

        SettingRow {
          objectName: "agent-projectDir"
          width: parent.width
          stacked: true
          label: "Project folder"
          hint: "Where it works. A new folder starts a new conversation."
          help: "History is kept per project, so changing the folder starts afresh."
          changed: blk.isMain ? blk.s.changed("projectDir") : blk.projectDir !== ""
          foreground: blk.s.foreground
          fontFamily: blk.s.fontFamily
          onReset: blk.isMain ? blk.s.resetKey("projectDir") : blk.write("projectDir", "")
          TextField {
            text: blk.projectDir
            placeholderText: blk.isMain ? "~  (your home directory)" : "its folder  (empty: your home directory)"
            foreground: blk.s.foreground
            font.family: blk.s.fontFamily
            onEditingFinished: {
              if (text !== blk.projectDir) blk.write("projectDir", text.trim())
            }
          }
        }
      }

      // --- Voice -----------------------------------------------------------------
      Card {
        title: "Voice"
        foreground: blk.s.foreground
        fontFamily: blk.s.fontFamily

        SettingRow {
          objectName: "agent-voice"
          width: parent.width
          stacked: true
          label: "Voice"
          // "" (same as the main agent) is never missing: the main voice is
          // what it would download, and that row says so on its own agent.
          hint: blk.voice !== "" && blk.s.voiceMissing(blk.voice) ? "Not on this machine yet — choosing it downloads it (about 60MB)."
                : !blk.isMain && blk.voice === "" ? "Follows the main agent (" + blk.s.voiceName(blk.pg.mainVoice) + ")."
                : "Which Piper voice it speaks in."
          disabledReason: blk.pg.mainSpeaks ? "" : "Replies are not spoken."
          changed: blk.isMain ? blk.s.changed("voice") : blk.voice !== ""
          foreground: blk.s.foreground
          fontFamily: blk.s.fontFamily
          onReset: {
            if (blk.isMain) { blk.s.resetKey("voice"); blk.s.chooseVoice(blk.s.defaults.voice || "") }
            else blk.write("voice", "")
          }
          Row {
            width: parent.width
            spacing: Style.space(8)
            Dropdown {
              width: parent.width - testButton.width - parent.spacing
              showLabel: false
              fontFamily: blk.s.fontFamily
              foreground: blk.s.foreground
              options: blk.isMain ? blk.s.voiceOptions
                                  : [{ label: "Same as the main agent", value: "" }].concat(blk.s.voiceOptions)
              value: blk.voice
              onChanged: function(v) { if (v !== blk.voice) blk.write("voice", v) }
            }
            // About a minute of the voice it would speak in, at its own pace.
            Button {
              id: testButton
              readonly property bool playing: blk.s.samplePlaying === blk.voiceHeard && blk.s.samplePace === blk.testPace
              anchors.verticalCenter: parent.verticalCenter
              text: playing ? "■ Stop" : "▶ Test"
              bordered: true
              focusable: true
              enabled: blk.pg.mainSpeaks && !blk.s.voiceMissing(blk.voiceHeard)
              tooltipText: !blk.pg.mainSpeaks ? "Replies are not spoken."
                           : blk.s.voiceMissing(blk.voiceHeard) ? "Not on this machine yet."
                           : playing ? "Stop the sample" : "Hear about a minute of this voice at its speed"
              foreground: blk.s.foreground
              fontFamily: blk.s.fontFamily
              onClicked: blk.s.playSample(blk.voiceHeard, blk.testPace)
            }
          }
        }

        // Choosing the voice already starts the download. This is for
        // afterwards: a download declined, a terminal closed, no network at
        // the time. Without it the only way back would be to pick a
        // different voice and pick this one again.
        Column {
          width: parent.width
          spacing: Style.space(6)
          visible: blk.voice !== "" && blk.s.voiceMissing(blk.voice)

          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            text: "“" + blk.s.voiceName(blk.voice) + "” is not on this machine, so it is " +
                  "speaking in one that is."
            textFormat: Text.PlainText
            color: blk.s.urgent
            font.family: blk.s.fontFamily
            font.pixelSize: Style.font.caption
          }
          Button {
            // Names the voice, as the dropdown does. Passing no name left it
            // to install.sh to read the setting, which is a race the flag
            // exists to avoid.
            text: "Try the download again…"
            bordered: true
            foreground: blk.s.foreground
            fontFamily: blk.s.fontFamily
            onClicked: blk.s.fetchVoice(blk.voice)
          }
        }

        KnobRow {
          objectName: blk.isMain ? "agent-speed" : ""
          width: parent.width
          visible: blk.isMain
          foreground: blk.s.foreground; fontFamily: blk.s.fontFamily
          label: "Speaking speed"
          description: "Agents set to \"same as the main agent\" follow this one."
          help: "A percent of the voice's natural pace: 100 is as recorded, 150 is half " +
                "again as fast. Piper stretches or squeezes each sound, so it stays the " +
                "same voice rather than going higher. Takes effect from the next reply " +
                "with nothing reloaded. Double-click the slider for 100."
          enabled: blk.pg.mainSpeaks
          value: blk.s.setting("voiceSpeed", 100)
          defaultValue: blk.s.defaults.voiceSpeed !== undefined ? blk.s.defaults.voiceSpeed : 100
          changed: blk.s.changed("voiceSpeed")
          minimum: 50; maximum: 200; stepSize: 5
          unit: "%"
          onCommitted: function(v) { blk.write("speed", Math.round(v)) }
          onReset: blk.s.resetKey("voiceSpeed")
        }

        SettingRow {
          objectName: blk.isMain ? "" : "agent-speed"
          width: parent.width
          visible: !blk.isMain
          stacked: true
          label: "Speaking speed"
          hint: blk.speed > 0 ? "Its own pace, whatever the main agent's is."
                              : "Follows the main agent (" + blk.pg.mainSpeed + "%)."
          changed: blk.speed > 0
          foreground: blk.s.foreground
          fontFamily: blk.s.fontFamily
          onReset: blk.write("speed", 0)
          Column {
            width: parent.width
            spacing: Style.space(6)
            SegmentedChoice {
              width: parent.width
              wrap: true
              options: [
                { value: "main", label: "Same as the main agent" },
                { value: "own", label: "Its own" }
              ]
              value: blk.speed > 0 ? "own" : "main"
              foreground: blk.s.foreground
              fontFamily: blk.s.fontFamily
              onCommitted: function(v) {
                if (v === "own" && blk.speed === 0) blk.write("speed", blk.pg.mainSpeed)
                else if (v === "main" && blk.speed > 0) blk.write("speed", 0)
              }
            }
            KnobRow {
              width: parent.width
              visible: blk.speed > 0
              foreground: blk.s.foreground; fontFamily: blk.s.fontFamily
              label: "Speed"
              value: blk.speed > 0 ? blk.speed : 100
              defaultValue: 100
              minimum: 50; maximum: 200; stepSize: 5
              unit: "%"
              onCommitted: function(v) {
                if (Math.round(v) !== blk.speed) blk.write("speed", Math.round(v))
              }
            }
          }
        }

        SettingRow {
          objectName: "agent-narration"
          width: parent.width
          visible: !blk.isMain
          stacked: true
          label: "Talk while it works"
          hint: String(blk.entry.narration || "") === ""
                ? "Follows Conversation (" + String(blk.s.setting("narration", "off")) + ")."
                : "Its own choice, whatever the main setting is."
          changed: String(blk.entry.narration || "") !== ""
          foreground: blk.s.foreground
          fontFamily: blk.s.fontFamily
          onReset: blk.write("narration", "")
          SegmentedChoice {
            width: parent.width
            wrap: true
            options: [
              { value: "", label: "Same as main" },
              { value: "off", label: "Off" },
              { value: "brief", label: "Brief" },
              { value: "detailed", label: "Detailed" }
            ]
            value: String(blk.entry.narration || "")
            foreground: blk.s.foreground
            fontFamily: blk.s.fontFamily
            onCommitted: function(v) {
              if (v !== String(blk.entry.narration || "")) blk.write("narration", v)
            }
          }
        }

        // Master plan M27: speaking up when background work finishes.
        ToggleRow {
          objectName: "agent-speakWhenDone"
          width: parent.width
          label: "Speak up when work finishes"
          hint: blk.speakWhenDoneHint
          checked: blk.speakWhenDone
          foreground: blk.s.foreground
          fontFamily: blk.s.fontFamily
          onToggled: blk.write("speakWhenDone", !blk.speakWhenDone)
        }
      }

      // --- Tools -----------------------------------------------------------------
      Card {
        title: "Tools"
        subtitle: "Its switches are on Agent details."
        // A deep link with tab "tools" points here.
        highlighted: blk.s.focusTools && blk.s.focusAgent === blk.agentId
        foreground: blk.s.foreground
        fontFamily: blk.s.fontFamily

        ToolSwitches {
          width: parent.width
          part: "tools"
          choices: blk.tools
          globals: blk.pg.toolGlobals
          shared: blk.pg.sharedTools
          program: blk.program
          foreground: blk.s.foreground
          accent: blk.s.accent
          urgent: blk.s.urgent
          fontFamily: blk.s.fontFamily
          onDetailsAsked: blk.s.goTo("agentdetails", blk.agentId, "tools")
          onSharedAsked: blk.s.goTo("communal", "", "tools")
        }
      }

      // --- Collaboration, notes & chats -------------------------------------------
      Card {
        objectName: "agent-collab"
        title: "Collaboration, notes & chats"
        foreground: blk.s.foreground
        fontFamily: blk.s.fontFamily

        ToolSwitches {
          width: parent.width
          part: "collab"
          program: blk.program
          notesWrite: blk.notesWrite
          collaboration: blk.collaboration
          acceptsWork: blk.acceptsWork
          foreground: blk.s.foreground
          accent: blk.s.accent
          urgent: blk.s.urgent
          fontFamily: blk.s.fontFamily
          onNotesPicked: function(value) { blk.write("notesWrite", value) }
          onCollaborationPicked: function(value) { blk.write("collaboration", value) }
          onAcceptsWorkPicked: function(value) { blk.write("acceptsWork", value) }
          chatSearch: blk.chatSearch
          agentLabel: blk.label
          quarantined: blk.pg.quarantineOf(blk.agentId)
          chatsSaved: blk.s.setting("saveChats", false) === true
          onChatSearchPicked: function(value) { blk.write("chatSearch", value) }
        }
      }

      // --- Agent -----------------------------------------------------------------
      Card {
        title: "Agent"
        foreground: blk.s.foreground
        fontFamily: blk.s.fontFamily

        ToggleRow {
          objectName: "agent-enabled"
          width: parent.width
          visible: !blk.isMain
          label: "On"
          hint: blk.on ? "Off keeps every setting here, but its wake phrase stops waking it and it leaves the popup and the Agents panel. A turn it is running is stopped."
                       : "Switched off: saying “" + blk.wake + "” does nothing. Every setting is kept."
          checked: blk.on
          foreground: blk.s.foreground
          fontFamily: blk.s.fontFamily
          onToggled: blk.write("enabled", !blk.on)
        }

        Text {
          width: parent.width
          visible: blk.isMain
          wrapMode: Text.WordWrap
          text: "To silence everything, mute the microphone or stop the service."
          textFormat: Text.PlainText
          color: blk.s.dim
          font.family: blk.s.fontFamily
          font.pixelSize: Style.font.caption
        }

        // One dropdown per engine rather than one that swaps its options:
        // swapping left the previous engine's value displayed.
        SettingRow {
          objectName: "set-owwModel"
          width: parent.width
          visible: blk.isMain && blk.s.owwLive
          stacked: true
          label: "Wake model"
          hint: "Only these ship pretrained. Another phrase means training your own model, on Listening."
          changed: blk.s.changed("owwModel")
          foreground: blk.s.foreground
          fontFamily: blk.s.fontFamily
          onReset: blk.s.resetKey("owwModel")
          Dropdown {
            showLabel: false
            fontFamily: blk.s.fontFamily
            foreground: blk.s.foreground
            options: blk.s.owwOptions
            value: blk.s.setting("owwModel", "hey_jarvis")
            onChanged: function(v) { blk.s.put("owwModel", v) }
          }
        }

        // In agents/<id>/ (merged plan, Phases 10 and 12), edited on Agent
        // details: one editor per file.
        SettingRow {
          width: parent.width
          stacked: true
          label: "Role, personality and instructions"
          hint: blk.pg.folderSummary(blk.agentId, blk.isMain ? blk.s.setting("agentInstructions", "") : blk.entry.instructions)
          foreground: blk.s.foreground
          fontFamily: blk.s.fontFamily
          Button {
            text: "Edit in Agent details →"
            bordered: true
            focusable: true
            foreground: blk.s.foreground
            fontFamily: blk.s.fontFamily
            onClicked: blk.s.goTo("agentdetails", blk.agentId)
          }
        }

        DangerButton {
          visible: !blk.isMain
          maxWidth: parent.width
          // The button does not wrap; a long name is said in the question.
          text: blk.label !== "" && blk.label.length <= 16 ? "Remove " + blk.label : "Remove this agent"
          question: "Really remove " + (blk.label || "this agent") + "?"
          confirmText: "Remove"
          foreground: blk.s.foreground
          urgent: blk.s.urgent
          fontFamily: blk.s.fontFamily
          onConfirmed: blk.pg.removeAgent(blk.agentIndex)
        }
      }
    }
  }

  // --- the main agent -----------------------------------------------------------
  AgentBlock { pg: page }

  // --- the extra agents ---------------------------------------------------------
  // By count, not by the list. `s.voiceAgents` is a new array after every
  // save of any setting, and a Repeater handed a new array rebuilds every
  // delegate: each agent shut, a dropdown open inside it vanished, a
  // half-typed name was lost. A count that has not changed rebuilds nothing.
  Repeater {
    model: page.s.voiceAgents.length
    delegate: AgentBlock {
      required property int index
      pg: page
      agentIndex: index
    }
  }

  Row {
    spacing: Style.space(12)
    Button {
      objectName: "addAgent"
      text: page.s.voiceAgents.length >= page.s.maxAgents
            ? "That is the most there can be (" + page.s.maxAgents + ")"
            : "Add an agent"
      iconText: "\u{f0415}"
      bordered: true
      enabled: page.s.voiceAgents.length < page.s.maxAgents
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onClicked: page.addAgent()
    }
    Text {
      anchors.verticalCenter: parent.verticalCenter
      width: page.width - x
      wrapMode: Text.WordWrap
      text: "Each is woken by its own name and keeps its own conversation. They can work " +
            "at the same time; they speak one at a time, and never over you."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  // A removed agent, with the way back (Phase 10). Stays until the next
  // removal or an undo: the trash keeps it either way (`agentvoice agents
  // trash-list`).
  // A Flow, so a long name wraps the button under the words rather than
  // pushing it past the page's edge, where it could not be clicked.
  Flow {
    width: parent.width
    visible: page.s.folders.trashed !== null
    spacing: Style.space(12)
    Text {
      width: Math.min(implicitWidth, parent.width)
      wrapMode: Text.WordWrap
      text: page.s.folders.trashed ? "Moved " + page.s.folders.trashed.label + " to the trash, with its folder and settings." : ""
      textFormat: Text.PlainText
      color: page.s.foreground
      font.family: page.s.fontFamily
    }
    Button {
      text: "Undo"
      iconText: "\u{f054c}"
      bordered: true
      enabled: !page.s.folders.busy
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onClicked: page.undoRemove()
    }
  }
  Text {
    width: parent.width
    visible: page.s.folders.note !== ""
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: page.s.folders.note
    color: page.s.urgent
    font.family: page.s.fontFamily
  }

  // Where the switches for every agent went (bug E).
  Button {
    text: "Tools for every agent: Communal → Tools ›"
    focusable: true
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
    fontSize: Style.font.caption
    onClicked: page.s.goTo("communal", "", "tools")
  }
}
