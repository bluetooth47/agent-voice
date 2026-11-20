import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// Every agent, as the same card.
//
// The main agent and the extra ones used to be drawn two different ways in
// three different boxes: the main one's model, effort and permission level
// as loose controls under "project folder and permissions", the API
// endpoint near the bottom of the page, and the extra agents as cards under
// "more agents". Now each is one card with the same rows in the same order,
// and the endpoint is what the main agent *runs on* rather than a section of
// its own -- which is what it always was: set both boxes and it answers
// instead of Omarchy's default.
//
// Settings are per agent because each is a judgement about one program: a
// model name means something to one CLI and nothing to the next, and a
// permission level that followed `omarchy default agent` would hand the
// next agent a decision nobody made about it.
Column {
  id: page

  required property var s

  spacing: Style.space(14)

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
  readonly property string mainModel: mapValue("agentModels", page.main)
  readonly property string mainEffort: mapValue("agentEfforts", page.main)
  // What is saved for this agent, else what the daemon says is in force.
  readonly property string mainLevel: mapValue("permissions", page.main) || s.permissionLevel

  // --- which cards are open ---------------------------------------------------
  // Kept here, by agent name, not on the cards. A card's own `expanded` was
  // a binding to focusAgent that the header click overwrote, so any time a
  // card was rebuilt it came back shut -- and every save rebuilt them all.
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
  Connections {
    target: page.s
    function onFocusAgentChanged() { page.openLinked() }
  }
  // Which card starts open: the one linked to, else the main card when it is
  // the only one. Decided once the settings have loaded, not at creation --
  // before that every list reads empty, so the main card always opened.
  function openLinked() {
    if (s.focusAgent === "") return
    setOpen(s.focusAgent, true)
    if (s.focusTools) setOpen("tools:" + s.focusAgent, true)
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

  function updateAgent(index, key, value) {
    var list = []
    for (var i = 0; i < s.voiceAgents.length; i++) {
      var copy = {}
      var a = s.voiceAgents[i] || {}
      for (var k in a) copy[k] = a[k]
      // Written down before anything changes, the wake phrase above all: an
      // entry from before ids existed is known by the one derived from it.
      copy.id = s.agentId(a)
      if (i === index) copy[key] = value
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
      var copy = {}
      var a = s.voiceAgents[n] || {}
      for (var k in a) copy[k] = a[k]
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

  // What is in an agent's folder, in one line, for the card: the files are
  // edited on Agent details, never here (one editor per file). Sizes only,
  // from the daemon while it runs, else from the overlay's own read.
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
  // Each agent's own, beating the settings for every agent at the foot of
  // this page. Written as inherit / on / off; inherit is written by leaving
  // the key out, so an entry nobody changed stays as it was.
  readonly property var toolGlobals: ({
    desktop: s.setting("desktopTools", false) === true,
    browser: s.setting("browserTools", false) === true,
    omarchySkill: s.setting("omarchySkill", true) === true
  })
  function toolMap(current, key, value) {
    var all = {}
    if (current && typeof current === "object")
      for (var k in current) all[k] = current[k]
    if (value === "inherit") delete all[key]
    else all[key] = value
    return all
  }
  function putMainTool(key, value) { s.put("mainTools", toolMap(s.setting("mainTools", {}), key, value)) }
  function putAgentTool(index, key, value) {
    updateAgent(index, "tools", toolMap((s.voiceAgents[index] || {}).tools, key, value))
  }
  // The Rule of Two (merged plan, Phase 13): reading web pages, acting
  // without asking, and being able to change what the other agents are
  // told, all in one agent. A warning, not a block. Denying notes writes
  // (Phase 14) does not lift it: at Trust everything a Claude agent can
  // still rewrite the communal rules and skills with a shell command
  // (Phase 13 review).
  function ruleOfTwo(program, level, choices) {
    var c = (choices && typeof choices === "object") ? choices.browser : undefined
    var browser = c === "on" || (c !== "off" && toolGlobals.browser)
    if (!browser || program !== "claude" || level !== "trusted") return ""
    return "It reads web pages, acts without asking, and can change what the other agents are " +
           "told (the communal rules and skills). A page could steer it into doing that. " +
           "Turning its browser off, or asking first, takes the risk away."
  }

  // `named` leaves the program out, for the main card, whose title is it.
  function summary(program, model, effort, level, levels, named) {
    var parts = named ? [] : [s.programLabel(program) || "no agent"]
    if (model !== "") parts.push(model)
    if (effort !== "") parts.push(s.effortNames[effort] || effort)
    parts.push(s.levelLabel(level, levels).toLowerCase())
    return parts.join(" · ")
  }

  // "Runs on" for the main card. Chosen locally until both endpoint boxes
  // are filled, because a half-filled endpoint is not in use.
  property bool endpointChosen: s.usingEndpoint || String(s.setting("endpointUrl", "")) !== ""
  property bool customModel: false
  onMainChanged: customModel = false
  // The main agent's own program; "" follows Omarchy's default.
  readonly property string mainProgram: String(s.setting("mainProgram", ""))
  function runOn(v) {
    if (v === "endpoint") { page.endpointChosen = true; return }
    page.endpointChosen = false
    page.customModel = false
    var program = v === "omarchy" ? "" : v
    if (program !== page.mainProgram) page.s.put("mainProgram", program)
    // Clearing both is what hands the turn back from an endpoint.
    if (String(page.s.setting("endpointUrl", "")) !== "") page.s.put("endpointUrl", "")
    if (String(page.s.setting("endpointModel", "")) !== "") page.s.put("endpointModel", "")
  }
  // A move to "trusted" waits here for a second click.
  property string trustPending: ""

  PageHeader {
    width: parent.width
    title: "Agents"
    subtitle: "Who answers, what each one may do, and where. Click a card to open it."
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

  // --- the main agent -----------------------------------------------------------
  AgentCard {
    id: mainCard
    width: parent.width
    readonly property string st: page.s.agentStatus("")
    name: page.s.mainLabel
    wakeName: page.s.activePhrase
    isDefault: true
    summary: page.endpointChosen
             ? "Endpoint · " + String(page.s.setting("endpointModel", "") || "no model yet") + " · " +
               String(page.s.setting("endpointUrl", "") || "no address yet")
             : page.summary(page.main, page.mainModel, page.mainEffort, page.mainLevel, page.s.agentLevels, false)
    status: st
    tone: page.s.statusTone(st)
    problem: !page.endpointChosen && page.main === ""
             ? "No default agent is set. Choose one with `omarchy default agent`."
             : page.s.projectDir.trim() === "" && page.mainLevel === "edits" && !page.endpointChosen
               ? "No project folder, so “edits are fine” has nothing to be inside: every change is asked about."
               : ""
    warning: page.endpointChosen ? ""
             : page.ruleOfTwo(page.main, page.mainLevel, page.s.setting("mainTools", {}))
    expanded: page.isOpen("main")
    onToggled: function(open) { page.setOpen("main", open) }
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: "Always on: something has to answer “" + page.s.activePhrase + "”. To silence everything, mute the microphone or stop the service."
      textFormat: Text.PlainText
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    SettingRow {
      width: parent.width
      stacked: true
      label: "Name"
      hint: "What it is called on screen, in saved chats and in the Agents panel. Any text. Empty uses the wake phrase."
      changed: page.s.changed("mainName")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.s.resetKey("mainName")
      TextField {
        text: String(page.s.setting("mainName", ""))
        placeholderText: page.s.capitalised(page.s.activePhrase)
        foreground: page.s.foreground
        font.family: page.s.fontFamily
        onEditingFinished: {
          var v = page.s.cleanLabel(text)
          if (v !== String(page.s.setting("mainName", ""))) page.s.put("mainName", v)
        }
      }
    }

    // One dropdown per engine rather than one that swaps its options.
    // Swapping left the previous engine's value displayed -- picking "hey
    // claude" under Vosk and then switching engines still showed "hey
    // claude", which openWakeWord has no model for.
    SettingRow {
      width: parent.width
      visible: !page.s.owwLive
      stacked: true
      label: "Wake phrase"
      hint: "What you say to start a turn with this agent. One to three plain words, such as a name. Press Enter to save."
      changed: page.s.changed("phrase")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.s.resetKey("phrase")
      TextField {
        text: page.s.setting("phrase", "hey computer")
        placeholderText: "a name or phrase — the words that wake it"
        foreground: page.s.foreground
        font.family: page.s.fontFamily
        onEditingFinished: {
          // Same rule as the extra agents' names: one to three plain words.
          var v = text.trim().toLowerCase().replace(/\s+/g, " ")
          if (!/^[a-z']+( [a-z']+){0,2}$/.test(v)) { text = page.s.setting("phrase", "hey computer"); return }
          if (v !== page.s.setting("phrase", "hey computer")) page.s.put("phrase", v)
        }
      }
    }

    SettingRow {
      width: parent.width
      visible: page.s.owwLive
      stacked: true
      label: "Wake phrase"
      hint: "Only these ship pretrained. Another phrase means training your own model, on Listening."
      changed: page.s.changed("owwModel")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.s.resetKey("owwModel")
      Dropdown {
        showLabel: false
        fontFamily: page.s.fontFamily
        foreground: page.s.foreground
        options: page.s.owwOptions
        value: page.s.setting("owwModel", "hey_jarvis")
        onChanged: function(v) { page.s.put("owwModel", v) }
      }
    }

    SettingRow {
      width: parent.width
      stacked: true
      label: "Runs on"
      hint: page.endpointChosen
            ? "Any OpenAI-compatible endpoint: Ollama, LM Studio, vLLM, OpenAI, xAI, Hermes."
            : page.mainProgram === ""
              ? "Omarchy's default coding agent, which `omarchy default agent` changes."
              : "Its own choice, whatever Omarchy's default agent is."
      changed: page.mainProgram !== "" || page.endpointChosen
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.runOn("omarchy")
      // A dropdown: seven choices do not fit on one row of chips.
      Dropdown {
        width: parent.width
        showLabel: false
        // The same programs an extra agent can run, after Omarchy's default.
        options: [{ value: "omarchy", label: "Omarchy's default" + (page.s.defaultAgent ? " (" + page.s.programLabel(page.s.defaultAgent) + ")" : "") }]
                 .concat(page.s.programOptions.map(function(o) {
                   return o.value === "endpoint" ? { value: "endpoint", label: "OpenAI-compatible endpoint" } : o }))
        value: page.endpointChosen ? "endpoint" : (page.mainProgram || "omarchy")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onChanged: function(v) { page.runOn(v) }
      }
    }

    // --- running on an endpoint ---
    Column {
      width: parent.width
      visible: page.endpointChosen
      spacing: Style.space(10)

      EndpointEditor {
        width: parent.width
        url: String(page.s.setting("endpointUrl", ""))
        model: String(page.s.setting("endpointModel", ""))
        isAgent: page.s.setting("endpointIsAgent", false) === true
        timeoutS: Number(page.s.setting("endpointTimeoutS", 0))
        historyTurns: Number(page.s.setting("endpointHistoryTurns", 8))
        foreground: page.s.foreground
        urgent: page.s.urgent
        fontFamily: page.s.fontFamily
        // Each key named, so the page that writes it says so in its source.
        onEdited: function(key, value) {
          switch (key) {
          case "endpointUrl": page.s.put("endpointUrl", value); break
          case "endpointModel": page.s.put("endpointModel", value); break
          case "endpointIsAgent": page.s.put("endpointIsAgent", value); break
          case "endpointTimeoutS": page.s.put("endpointTimeoutS", value); break
          case "endpointHistoryTurns": page.s.put("endpointHistoryTurns", value); break
          }
        }
      }
      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        visible: page.s.vOverriding !== "" || !page.s.vGoverned
        text: (page.s.vOverriding !== ""
               ? "⚠  Answering instead of " + page.s.vOverriding + ", Omarchy's default. "
               : "⚠  ") +
              "It works on its own machine, in a directory it chooses: the project " +
              "folder and permission level here reach nothing over there. Restrain " +
              "it where it runs."
        textFormat: Text.PlainText
        color: page.s.urgent
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
    }

    // --- running on Omarchy's agent ---
    Column {
      width: parent.width
      visible: !page.endpointChosen
      spacing: Style.space(10)

      SettingRow {
        width: parent.width
        stacked: true
        label: "Model"
        hint: "Only for voice; your other sessions keep their own. Changing it starts a new conversation."
        disabledReason: page.main === "" ? "No default agent is set."
                        : page.s.serviceActive && !page.s.vTakesModel
                          ? page.main + " does not take a model from here." : ""
        changed: page.mainModel !== ""
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: page.setModel("")
        Column {
          spacing: Style.space(6)
          Dropdown {
            width: parent.width
            showLabel: false
            fontFamily: page.s.fontFamily
            foreground: page.s.foreground
            options: page.s.agentModelChoices(page.main, page.mainModel)
            value: page.customModel ? "__other__" : page.mainModel
            onChanged: function(v) {
              if (v === "__other__") { page.customModel = true; return }
              page.customModel = false
              if (v !== page.mainModel) page.setModel(v)
            }
          }
          TextField {
            width: parent.width
            visible: page.customModel
            text: page.mainModel
            placeholderText: "type a model name or full model id"
            foreground: page.s.foreground
            font.family: page.s.fontFamily
            onEditingFinished: {
              if (text.trim() !== page.mainModel) page.setModel(text)
            }
          }
          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            visible: page.mainModel !== ""
                     && !/^[A-Za-z0-9][A-Za-z0-9._:\/@\[\]-]{0,127}$/.test(page.mainModel)
            text: "⚠  Not accepted as a model name, so the default is in use."
            color: page.s.urgent
            font.family: page.s.fontFamily
            font.pixelSize: Style.font.caption
          }
        }
      }

      // Only the levels the model in force takes: the daemon publishes them.
      SettingRow {
        width: parent.width
        stacked: true
        label: "Effort"
        hint: page.mainEffort !== "" && page.s.vEfforts.length > 0
              && page.s.vEfforts.indexOf(page.mainEffort) < 0
              ? "⚠  The level saved is not one this model takes, so the default is in use."
              : "How hard it thinks before answering. Changing it keeps the conversation."
        disabledReason: page.s.vEfforts.length > 0 ? ""
                        : page.s.serviceActive ? "This model takes no effort level."
                        : "Shown once the service is running, for a model that takes one."
        changed: page.mainEffort !== ""
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: page.setEffort("")
        SegmentedChoice {
          options: page.s.effortChoices(page.s.vEfforts)
          value: page.s.vEfforts.indexOf(page.mainEffort) >= 0 ? page.mainEffort : ""
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onCommitted: function(v) { page.setEffort(v) }
        }
      }

      SettingRow {
        width: parent.width
        stacked: true
        label: "Permission"
        hint: page.mainLevel === "trusted"
              ? "Nothing is asked. A spoken sentence can edit files and run commands here with nothing able to stop it."
              : page.mainLevel === "edits"
                ? "Source files in the folder are edited without asking. Commands, the network and anything outside still ask."
                : page.s.agentLevels.indexOf("edits") < 0 && page.s.serviceActive
                  ? page.main + " cannot put a question on screen, so it is held read-only and may refuse work rather than ask."
                  : "Every change is asked about on screen. An unanswered question is denied."
        help: (page.s.vPosture !== "" ? "In force: " + page.s.vPosture + ".\n\n" : "") +
              "Reading is free except for keys, credentials and shell history. Under " +
              "“edits”, files that make something else run — .git/hooks, .envrc, " +
              ".claude/settings.json — still ask. Your home directory is not accepted " +
              "as a project: it holds the file this level is stored in."
        disabledReason: page.main === "" ? "No default agent is set." : ""
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        Column {
          spacing: Style.space(6)
          SegmentedChoice {
            width: parent.width
            options: page.s.levelChoices(page.s.agentLevels)
            value: page.trustPending === "main" ? "trusted" : page.mainLevel
            foreground: page.s.foreground
            accent: page.mainLevel === "trusted" ? page.s.urgent : page.s.accent
            fontFamily: page.s.fontFamily
            onCommitted: function(v) {
              if (v === "trusted") { page.trustPending = "main"; return }
              page.trustPending = ""
              page.setLevel(v)
            }
          }
          Row {
            visible: page.trustPending === "main"
            spacing: Style.space(10)
            Text {
              anchors.verticalCenter: parent.verticalCenter
              text: "Let a spoken sentence run anything here?"
              color: page.s.urgent
              font.family: page.s.fontFamily
              font.pixelSize: Style.font.caption
            }
            Button {
              text: "Trust it"
              bordered: true
              foreground: page.s.urgent
              accent: page.s.urgent
              fontFamily: page.s.fontFamily
              onClicked: { page.trustPending = ""; page.setLevel("trusted") }
            }
            Button {
              text: "Cancel"
              bordered: true
              foreground: page.s.foreground
              fontFamily: page.s.fontFamily
              onClicked: page.trustPending = ""
            }
          }
        }
      }

      // The directory and what is allowed in it are one decision, not two:
      // a permission level with no root to apply to means nothing.
      SettingRow {
        width: parent.width
        stacked: true
        label: "Project folder"
        hint: "Where it works. Changing it starts a new conversation, because history is kept per project."
        changed: page.s.changed("projectDir")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: page.s.resetKey("projectDir")
        TextField {
          text: page.s.projectDir
          placeholderText: "~  (your home directory)"
          foreground: page.s.foreground
          font.family: page.s.fontFamily
          onEditingFinished: {
            if (text !== page.s.projectDir) page.s.put("projectDir", text.trim())
          }
        }
      }
    }

    // In agents/main/ (merged plan, Phases 10 and 12), edited on Agent
    // details: one editor per file.
    SettingRow {
      width: parent.width
      label: "Role, personality and instructions"
      hint: page.folderSummary("main", page.s.setting("agentInstructions", ""))
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      Button {
        text: "Edit in Agent details →"
        bordered: true
        focusable: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.goTo("agentdetails", "main")
      }
    }

    ToolSwitches {
      width: parent.width
      choices: page.s.setting("mainTools", {})
      globals: page.toolGlobals
      program: page.endpointChosen ? "endpoint" : page.main
      expanded: page.isOpen("tools:main")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: function(open) { page.setOpen("tools:main", open) }
      onPicked: function(key, value) { page.putMainTool(key, value) }
    }

    SettingRow {
      width: parent.width
      stacked: true
      label: "Voice"
      hint: page.s.voiceMissing(page.mainVoice) ? "Not on this machine yet — choosing a voice downloads it (about 60MB)."
                                            : "Which Piper voice this agent speaks in."
      disabledReason: page.mainSpeaks ? "" : "Replies are not spoken."
      changed: page.s.changed("voice")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: { page.s.resetKey("voice"); page.s.chooseVoice(page.s.defaults.voice || "") }
      Dropdown {
        showLabel: false
        fontFamily: page.s.fontFamily
        foreground: page.s.foreground
        options: page.s.voiceOptions
        value: page.mainVoice
        onChanged: function(v) {
          if (v === page.mainVoice) return
          page.s.put("voice", v)
          page.s.chooseVoice(v)
        }
      }
    }

    // Choosing the voice already starts the download. This is for
    // afterwards: a download declined, a terminal closed, no network at the
    // time. Without it the only way back would be to pick a different voice
    // and pick this one again.
    Column {
      width: parent.width
      spacing: Style.space(6)
      visible: page.s.voiceMissing(page.mainVoice)

      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        text: "“" + page.s.voiceName(page.mainVoice) + "” is not on this machine, so it is " +
              "speaking in one that is."
        textFormat: Text.PlainText
        color: page.s.urgent
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      Button {
        // Names the voice, as the dropdown does. Passing no name left it to
        // install.sh to read the setting, which is a race the flag exists
        // to avoid.
        text: "Try the download again…"
        bordered: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.fetchVoice(page.mainVoice)
      }
    }

    KnobRow {
      width: parent.width
      foreground: page.s.foreground; fontFamily: page.s.fontFamily
      label: "Speaking speed"
      description: "Its pace. Agents set to \"same as the main agent\" follow this one."
      help: "A percent of the voice's natural pace: 100 is as recorded, 150 is half " +
            "again as fast. Piper stretches or squeezes each sound, so it stays the " +
            "same voice rather than going higher. Takes effect from the next reply " +
            "with nothing reloaded. Double-click the slider for 100."
      enabled: page.mainSpeaks
      value: page.s.setting("voiceSpeed", 100)
      defaultValue: page.s.defaults.voiceSpeed !== undefined ? page.s.defaults.voiceSpeed : 100
      changed: page.s.changed("voiceSpeed")
      minimum: 50; maximum: 200; stepSize: 5
      unit: "%"
      onCommitted: function(v) { page.s.put("voiceSpeed", Math.round(v)) }
      onReset: page.s.resetKey("voiceSpeed")
    }
  }

  // --- the extra agents ---------------------------------------------------------
  // By count, not by the list. `s.voiceAgents` is a new array after every
  // save of any setting, and a Repeater handed a new array rebuilds every
  // delegate: each card shut, a dropdown open inside it vanished, a half-typed
  // name was lost. A count that has not changed rebuilds nothing.
  Repeater {
    model: page.s.voiceAgents.length

    delegate: AgentCard {
      id: card
      required property int index
      readonly property var modelData: page.s.voiceAgents[card.index] || ({})

      readonly property string agentName: String(modelData.name || "")
      // What everything else knows it by; see Settings.agentId.
      readonly property string agentId: page.s.agentId(modelData)
      readonly property string label: page.s.agentLabel(modelData)
      readonly property string program: String(modelData.agent || "claude")
      readonly property string model: String(modelData.model || "")
      readonly property string effort: String(modelData.effort || "")
      // 0 (or nothing) is "same as the main agent".
      readonly property int speed: Number(modelData.speed || 0)
      readonly property string level: String(modelData.level || "ask")
      readonly property var info: page.s.crewInfo(card.agentId)
      readonly property var efforts: Array.isArray(card.info.efforts) ? card.info.efforts : []
      readonly property var levels: Array.isArray(card.info.levels) ? card.info.levels : ["ask", "edits", "trusted"]
      readonly property string st: page.s.agentStatus(card.agentId)
      // Missing means on, so lists from before the switch keep every agent.
      readonly property bool on: card.modelData.enabled !== false
      property bool customModel: false
      property bool confirmRemove: false

      width: page.width
      name: card.label || "New agent"
      wakeName: card.agentName
      summary: card.program === "endpoint"
               ? "Endpoint · " + String(card.modelData.endpointModel || "no model yet") + " · " +
                 String(card.modelData.endpointUrl || "no address yet")
               : page.summary(card.program, card.model, card.effort, card.level, card.levels)
      status: card.on ? card.st : "switched off"
      tone: card.on ? page.s.statusTone(card.st) : "idle"
      switchedOff: !card.on
      problem: !card.on ? ""
               : String(card.info.problem || "") !== "" ? String(card.info.problem)
               : card.agentName !== "" && !/^[a-z]+( [a-z]+){0,2}$/.test(card.agentName)
                 ? "A wake phrase is one to three plain words, letters only." : ""
      warning: card.on ? page.ruleOfTwo(card.program, card.level, card.modelData.tools) : ""
      expanded: page.isOpen(card.agentId)
      onToggled: function(open) { page.setOpen(card.agentId, open) }
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily

      Timer { id: removeTimeout; interval: 4000; onTriggered: card.confirmRemove = false }

      ToggleRow {
        width: parent.width
        label: "On"
        hint: card.on ? "Off keeps every setting here, but its wake phrase stops waking it and it leaves the popup and the Agents panel. A turn it is running is stopped."
                      : "Switched off: saying “" + card.agentName + "” does nothing. Every setting is kept."
        checked: card.on
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onToggled: page.updateAgent(card.index, "enabled", !card.on)
      }

      SettingRow {
        width: parent.width
        stacked: true
        label: "Name"
        hint: "What it is called on screen, in saved chats and in the Agents panel. Any text. Empty uses the wake phrase."
        changed: page.s.cleanLabel(card.modelData.label) !== ""
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: page.updateAgent(card.index, "label", "")
        TextField {
          text: page.s.cleanLabel(card.modelData.label)
          placeholderText: page.s.capitalised(card.agentName) || "a name to show"
          foreground: page.s.foreground
          font.family: page.s.fontFamily
          onEditingFinished: {
            var v = page.s.cleanLabel(text)
            if (v !== page.s.cleanLabel(card.modelData.label)) page.updateAgent(card.index, "label", v)
          }
        }
      }

      SettingRow {
        width: parent.width
        stacked: true
        label: "Wake phrase"
        hint: "What you say to wake it. One to three plain words. Changing it keeps the conversation."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        TextField {
          text: card.agentName
          placeholderText: "the word that wakes it"
          foreground: page.s.foreground
          font.family: page.s.fontFamily
          onEditingFinished: {
            var v = text.trim().toLowerCase().replace(/\s+/g, " ")
            if (v !== card.agentName) page.updateAgent(card.index, "name", v)
          }
        }
      }

      // The same dropdown as the main card's "Runs on", less Omarchy's
      // default: an extra agent always names its program.
      SettingRow {
        width: parent.width
        stacked: true
        label: "Runs on"
        hint: card.program === "endpoint"
              ? "Any OpenAI-compatible endpoint: Ollama, LM Studio, vLLM, OpenAI, xAI, Hermes."
              : "Its own program, whatever Omarchy's default agent is."
        changed: card.program !== "claude"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: { card.customModel = false; page.updateAgent(card.index, "agent", "claude") }
        Dropdown {
          width: parent.width
          showLabel: false
          options: page.s.programOptions.map(function(o) {
            return o.value === "endpoint" ? { value: "endpoint", label: "OpenAI-compatible endpoint" } : o })
          value: card.program
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onChanged: function(v) {
            if (v === card.program) return
            card.customModel = false
            page.updateAgent(card.index, "agent", v)
          }
        }
      }

      // Its own OpenAI-compatible endpoint (plan 7b). The model, effort,
      // permission and folder rows below do not apply to one: agentvoice
      // offers an endpoint no tools.
      Column {
        width: parent.width
        visible: card.program === "endpoint"
        spacing: Style.space(10)

        EndpointEditor {
          width: parent.width
          url: String(card.modelData.endpointUrl || "")
          model: String(card.modelData.endpointModel || "")
          isAgent: card.modelData.endpointIsAgent === true
          timeoutS: Number(card.modelData.endpointTimeoutS || 0)
          historyTurns: card.modelData.endpointHistoryTurns === undefined ? 8
                        : Number(card.modelData.endpointHistoryTurns)
          foreground: page.s.foreground
          urgent: page.s.urgent
          fontFamily: page.s.fontFamily
          onEdited: function(key, value) { page.updateAgent(card.index, key, value) }
        }
        // An endpoint has no folder of ours (the daemon reports it as not
        // governed), so this always applies, unlike on the main card.
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          text: "⚠  It works on its own machine, in a directory it chooses: the project " +
                "folder and permission level here reach nothing over there. Restrain " +
                "it where it runs."
          textFormat: Text.PlainText
          color: page.s.urgent
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
      }

      SettingRow {
        width: parent.width
        stacked: true
        label: "Model"
        visible: card.program !== "endpoint"
        hint: "Only for voice; your other sessions keep their own. Changing it starts a new conversation."
        disabledReason: card.info.takes_model === false
                        ? page.s.programLabel(card.program) + " does not take a model from here." : ""
        changed: card.model !== ""
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: page.updateAgent(card.index, "model", "")
        Column {
          spacing: Style.space(6)
          Dropdown {
            width: parent.width
            showLabel: false
            fontFamily: page.s.fontFamily
            foreground: page.s.foreground
            options: page.s.agentModelChoices(card.program, card.model)
            value: card.customModel ? "__other__" : card.model
            onChanged: function(v) {
              if (v === "__other__") { card.customModel = true; return }
              card.customModel = false
              if (v !== card.model) page.updateAgent(card.index, "model", v)
            }
          }
          TextField {
            width: parent.width
            visible: card.customModel
            text: card.model
            placeholderText: "type a model name or full model id"
            foreground: page.s.foreground
            font.family: page.s.fontFamily
            onEditingFinished: {
              if (text.trim() !== card.model) page.updateAgent(card.index, "model", text.trim())
            }
          }
          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            visible: card.model !== ""
                     && !/^[A-Za-z0-9][A-Za-z0-9._:\/@\[\]-]{0,127}$/.test(card.model)
            text: "⚠  Not accepted as a model name, so the default is in use."
            color: page.s.urgent
            font.family: page.s.fontFamily
            font.pixelSize: Style.font.caption
          }
        }
      }

      SettingRow {
        width: parent.width
        stacked: true
        label: "Effort"
        visible: card.program !== "endpoint"
        hint: card.effort !== "" && card.efforts.length > 0 && card.efforts.indexOf(card.effort) < 0
              ? "⚠  The level saved is not one this model takes, so the default is in use."
              : "How hard it thinks before answering. Changing it keeps the conversation."
        disabledReason: card.efforts.length > 0 ? ""
                        : page.s.serviceActive ? "This model takes no effort level."
                        : "Shown once the service is running, for a model that takes one."
        changed: card.effort !== ""
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: page.updateAgent(card.index, "effort", "")
        SegmentedChoice {
          options: page.s.effortChoices(card.efforts)
          value: card.efforts.indexOf(card.effort) >= 0 ? card.effort : ""
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onCommitted: function(v) { page.updateAgent(card.index, "effort", v) }
        }
      }

      SettingRow {
        width: parent.width
        stacked: true
        label: "Permission"
        visible: card.program !== "endpoint"
        hint: card.level === "trusted"
              ? "Nothing is asked. A sentence starting with “" + card.agentName +
                "” can edit files and run commands in its folder."
              : card.level === "edits"
                ? "Source files in its folder are edited without asking. Commands, the network and anything outside still ask."
                : card.levels.indexOf("edits") < 0 && page.s.serviceActive
                  ? page.s.programLabel(card.program) + " cannot put a question on screen, so it is held read-only and may refuse work rather than ask."
                  : "Every change is asked about on screen. An unanswered question is denied. Its own level: what you allow the main agent does not carry over."
        help: (String(card.info.posture || "") !== "" ? "In force: " + card.info.posture + ".\n\n" : "") +
              "Reading is free except for keys, credentials and shell history. Under " +
              "“edits”, files that make something else run — .git/hooks, .envrc, " +
              ".claude/settings.json — still ask. Your home directory is not accepted " +
              "as a project: it holds the file this level is stored in."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        Column {
          spacing: Style.space(6)
          SegmentedChoice {
            width: parent.width
            options: page.s.levelChoices(card.levels)
            value: page.trustPending === card.agentId ? "trusted" : card.level
            foreground: page.s.foreground
            accent: card.level === "trusted" ? page.s.urgent : page.s.accent
            fontFamily: page.s.fontFamily
            onCommitted: function(v) {
              if (v === "trusted") { page.trustPending = card.agentId; return }
              page.trustPending = ""
              page.updateAgent(card.index, "level", v)
            }
          }
          Row {
            visible: page.trustPending === card.agentId
            spacing: Style.space(10)
            Text {
              anchors.verticalCenter: parent.verticalCenter
              text: "Let a spoken sentence run anything in its folder?"
              color: page.s.urgent
              font.family: page.s.fontFamily
              font.pixelSize: Style.font.caption
            }
            Button {
              text: "Trust it"
              bordered: true
              foreground: page.s.urgent
              accent: page.s.urgent
              fontFamily: page.s.fontFamily
              onClicked: { page.trustPending = ""; page.updateAgent(card.index, "level", "trusted") }
            }
            Button {
              text: "Cancel"
              bordered: true
              foreground: page.s.foreground
              fontFamily: page.s.fontFamily
              onClicked: page.trustPending = ""
            }
          }
        }
      }

      SettingRow {
        width: parent.width
        stacked: true
        label: "Project folder"
        visible: card.program !== "endpoint"
        hint: "Where it works. Changing it starts a new conversation, because history is kept per project."
        changed: String(card.modelData.projectDir || "") !== ""
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: page.updateAgent(card.index, "projectDir", "")
        TextField {
          text: String(card.modelData.projectDir || "")
          placeholderText: "its folder  (empty: your home directory)"
          foreground: page.s.foreground
          font.family: page.s.fontFamily
          onEditingFinished: {
            if (text !== String(card.modelData.projectDir || ""))
              page.updateAgent(card.index, "projectDir", text.trim())
          }
        }
      }

      // In agents/<id>/, edited on Agent details (Phase 12).
      SettingRow {
        width: parent.width
        label: "Role, personality and instructions"
        hint: page.folderSummary(card.agentId, card.modelData.instructions)
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        Button {
          text: "Edit in Agent details →"
          bordered: true
          focusable: true
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onClicked: page.s.goTo("agentdetails", card.agentId)
        }
      }

      ToolSwitches {
        width: parent.width
        choices: card.modelData.tools || ({})
        globals: page.toolGlobals
        program: card.program
        expanded: page.isOpen("tools:" + card.agentId)
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onToggled: function(open) { page.setOpen("tools:" + card.agentId, open) }
        onPicked: function(key, value) { page.putAgentTool(card.index, key, value) }
      }

      SettingRow {
        width: parent.width
        stacked: true
        label: "Voice"
        hint: page.s.voiceMissing(String(card.modelData.voice || ""))
              ? "Not on this machine yet — choosing a voice downloads it (about 60MB)."
              : "Which Piper voice this agent speaks in."
        disabledReason: page.mainSpeaks ? "" : "Replies are not spoken."
        changed: String(card.modelData.voice || "") !== ""
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: page.updateAgent(card.index, "voice", "")
        Dropdown {
          showLabel: false
          fontFamily: page.s.fontFamily
          foreground: page.s.foreground
          options: [{ label: "Same as the main agent", value: "" }].concat(page.s.voiceOptions)
          value: String(card.modelData.voice || "")
          onChanged: function(v) {
            if (v === String(card.modelData.voice || "")) return
            page.updateAgent(card.index, "voice", v)
            page.s.chooseVoice(v)
          }
        }
      }

      // As on the main card: a way back after a declined or failed download.
      Column {
        width: parent.width
        spacing: Style.space(6)
        visible: String(card.modelData.voice || "") !== ""
                 && page.s.voiceMissing(String(card.modelData.voice || ""))

        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          text: "“" + page.s.voiceName(String(card.modelData.voice || "")) + "” is not on this machine, so it is " +
                "speaking in one that is."
          textFormat: Text.PlainText
          color: page.s.urgent
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
        Button {
          text: "Try the download again…"
          bordered: true
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onClicked: page.s.fetchVoice(String(card.modelData.voice || ""))
        }
      }

      SettingRow {
        width: parent.width
        stacked: true
        label: "Speaking speed"
        hint: card.speed > 0 ? "Its own pace, whatever the main agent's is."
                             : "Follows the main agent (" + Number(page.s.setting("voiceSpeed", 100)) + "%)."
        changed: card.speed > 0
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: page.updateAgent(card.index, "speed", 0)
        Column {
          spacing: Style.space(6)
          SegmentedChoice {
            options: [
              { value: "main", label: "Same as the main agent" },
              { value: "own", label: "Its own" }
            ]
            value: card.speed > 0 ? "own" : "main"
            foreground: page.s.foreground
            fontFamily: page.s.fontFamily
            onCommitted: function(v) {
              if (v === "own" && card.speed === 0)
                page.updateAgent(card.index, "speed", Number(page.s.setting("voiceSpeed", 100)) || 100)
              else if (v === "main" && card.speed > 0)
                page.updateAgent(card.index, "speed", 0)
            }
          }
          KnobRow {
            width: parent.width
            visible: card.speed > 0
            foreground: page.s.foreground; fontFamily: page.s.fontFamily
            label: "Speed"
            value: card.speed > 0 ? card.speed : 100
            defaultValue: 100
            minimum: 50; maximum: 200; stepSize: 5
            unit: "%"
            onCommitted: function(v) {
              if (Math.round(v) !== card.speed) page.updateAgent(card.index, "speed", Math.round(v))
            }
          }
        }
      }

      SettingRow {
        width: parent.width
        stacked: true
        label: "Talk while it works"
        hint: String(card.modelData.narration || "") === ""
              ? "Follows Conversation (" + String(page.s.setting("narration", "off")) + ")."
              : "Its own choice, whatever the main setting is."
        changed: String(card.modelData.narration || "") !== ""
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: page.updateAgent(card.index, "narration", "")
        SegmentedChoice {
          options: [
            { value: "", label: "Same as main" },
            { value: "off", label: "Off" },
            { value: "brief", label: "Brief" },
            { value: "detailed", label: "Detailed" }
          ]
          value: String(card.modelData.narration || "")
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onCommitted: function(v) {
            if (v !== String(card.modelData.narration || "")) page.updateAgent(card.index, "narration", v)
          }
        }
      }

      Button {
        text: card.confirmRemove ? "Remove " + (card.label || "this agent") + "? Click again"
                                 : "Remove " + (card.label || "this agent")
        iconText: "\u{f0a7a}"
        bordered: true
        foreground: card.confirmRemove ? page.s.urgent : page.s.foreground
        accent: page.s.urgent
        fontFamily: page.s.fontFamily
        onClicked: {
          if (!card.confirmRemove) { card.confirmRemove = true; removeTimeout.restart(); return }
          card.confirmRemove = false
          page.removeAgent(card.index)
        }
      }
    }
  }

  Row {
    spacing: Style.space(12)
    Button {
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

  // What every agent gets on the desktop (plan 12a, 12b), whichever program
  // runs it, unless its card's "Tools & collaboration" says otherwise
  // (Phase 13).
  SettingsGroup {
    width: parent.width
    title: "ON THE DESKTOP"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: "For every agent, unless its card's “Tools & collaboration” says otherwise."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    ToggleRow {
      width: parent.width
      label: "Desktop tools"
      hint: "Claude Code agents can open apps, move and close windows, switch workspaces, " +
            "play and pause, change the volume, notify, use the clipboard and see the screen."
      help: "Each tool goes through the agent's own permission level, like anything " +
            "else it does: listing windows is free, a change is asked about below " +
            "Trusted, reading the clipboard is asked about below Trusted, and a " +
            "screenshot is asked about every time, at every level. Locking the screen " +
            "or suspending works only when you said so in that request.

" +
            "Apps are opened by the name the launcher shows, never as a command."
      checked: page.s.setting("desktopTools", false) === true
      changed: page.s.changed("desktopTools")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("desktopTools", !checked)
      onReset: page.s.resetKey("desktopTools")
    }

    ToggleRow {
      width: parent.width
      label: "Browser"
      hint: "Claude Code agents can use Claude in Chrome: your own browser, signed in as you."
      help: "Reading pages, finding things and scrolling follow the agent's permission " +
            "level. Anything whose own description says it sends, buys, posts, books, " +
            "deletes or the like, running code in a page, uploading a file, and any " +
            "click that does not say what it does are asked about at every level, " +
            "Trusted and \u201callow all in this chat\u201d included. The question is " +
            "said out loud as well as shown.\n\nNeeds the Claude in Chrome extension."
      checked: page.s.setting("browserTools", false) === true
      changed: page.s.changed("browserTools")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("browserTools", !checked)
      onReset: page.s.resetKey("browserTools")
    }

    ToggleRow {
      width: parent.width
      label: "Omarchy skill"
      hint: "Agents know this machine's omarchy commands and keybindings, so “open a " +
            "scratchpad” or “next background” is one command, not a search."
      help: "Built from the commands installed here at install time, and again when " +
            "Omarchy updates. Claude Code loads it as a skill for the voice session only; " +
            "Codex, Gemini, Antigravity and Copilot get a shorter list in their " +
            "instructions. Endpoints get nothing: they run nothing on this machine."
      checked: page.s.setting("omarchySkill", true) === true
      changed: page.s.changed("omarchySkill")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("omarchySkill", !checked)
      onReset: page.s.resetKey("omarchySkill")
    }
  }
}
