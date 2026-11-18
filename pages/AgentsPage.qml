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
    function onFocusAgentChanged() { page.setOpen(page.s.focusAgent, true) }
  }
  // Which card starts open: the one linked to, else the main card when it is
  // the only one. Decided once the settings have loaded, not at creation --
  // before that every list reads empty, so the main card always opened.
  property bool openingDecided: false
  function decideOpening() {
    if (openingDecided || !s.store.loaded) return
    openingDecided = true
    if (s.focusAgent !== "") setOpen(s.focusAgent, true)
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
    list.push({ id: id, name: name, label: "", agent: "claude", model: "", effort: "", voice: "",
                speed: 0, narration: "", instructions: "", level: "ask", projectDir: "" })
    s.focusAgent = id
    saveAgents(list)
  }

  function removeAgent(index) {
    var list = s.voiceAgents.slice()
    list.splice(index, 1)
    saveAgents(list)
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
            : "Omarchy's default coding agent. Change it with `omarchy default agent`."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      SegmentedChoice {
        options: [
          { value: "omarchy", label: "Omarchy's default" + (page.s.defaultAgent ? " (" + page.s.defaultAgent + ")" : "") },
          { value: "endpoint", label: "OpenAI-compatible endpoint" }
        ]
        value: page.endpointChosen ? "endpoint" : "omarchy"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(v) {
          if (v === "endpoint") { page.endpointChosen = true; return }
          page.endpointChosen = false
          // Clearing both is what hands the turn back to Omarchy's agent.
          if (String(page.s.setting("endpointUrl", "")) !== "") page.s.put("endpointUrl", "")
          if (String(page.s.setting("endpointModel", "")) !== "") page.s.put("endpointModel", "")
        }
      }
    }

    // --- running on an endpoint ---
    Column {
      width: parent.width
      visible: page.endpointChosen
      spacing: Style.space(10)

      SettingRow {
        width: parent.width
        stacked: true
        label: "Address"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        TextField {
          text: page.s.setting("endpointUrl", "")
          placeholderText: "http://your-machine:11434/v1"
          foreground: page.s.foreground
          font.family: page.s.fontFamily
          onEditingFinished: {
            if (text !== page.s.setting("endpointUrl", "")) page.s.put("endpointUrl", text.trim())
          }
        }
      }
      SettingRow {
        width: parent.width
        stacked: true
        label: "Model"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        TextField {
          text: page.s.setting("endpointModel", "")
          placeholderText: "model name, e.g. llama3.2"
          foreground: page.s.foreground
          font.family: page.s.fontFamily
          onEditingFinished: {
            if (text !== page.s.setting("endpointModel", "")) page.s.put("endpointModel", text.trim())
          }
        }
      }
      ToggleRow {
        width: parent.width
        label: "This endpoint is an agent"
        hint: "It can run commands or change files on its own machine, as Hermes can."
        help: "agentvoice cannot tell from the URL, so it claims nothing about the far " +
              "end unless you say — and gives it longer to answer, because an agent " +
              "goes quiet while it runs tools.\n\nagentvoice offers an endpoint no " +
              "tools and gates nothing, so the permission level does not reach it. " +
              "What the endpoint itself can do is not visible from here: Ollama cannot " +
              "touch anything, while Hermes has a terminal and a filesystem on its host."
        checked: page.s.setting("endpointIsAgent", false) === true
        changed: page.s.changed("endpointIsAgent")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onToggled: page.s.put("endpointIsAgent", !checked)
        onReset: page.s.resetKey("endpointIsAgent")
      }
      SettingRow {
        width: parent.width
        label: "API key"
        hint: "Ollama and LM Studio need none. For one that does, use the login keyring."
        help: "The login keyring unlocks when you log in and only this session can read it:\n" +
              "  secret-tool store --label=agentvoice \\\n" +
              "      service agentvoice endpoint api.openai.com\n" +
              "Keyed by host and port, so two services on one machine do not share a key. " +
              "Failing that, ~/.config/agentvoice/endpoint.key. Never in this settings " +
              "file — it is the desktop's config and gets copied around."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
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

    SettingRow {
      width: parent.width
      stacked: true
      label: "Custom instructions"
      hint: "Added to what this agent is told on every turn. Changing them keeps the conversation."
      help: "How to address you, what to keep in mind, how long to talk. They sit after the " +
            "rule that replies are spoken, so asking for lists or code blocks will still be read out " +
            "as speech. Up to 2000 characters."
      changed: page.s.changed("agentInstructions")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.s.resetKey("agentInstructions")
      InstructionsBox {
        value: String(page.s.setting("agentInstructions", ""))
        placeholder: "e.g. Call me Sam. Keep answers to one sentence unless I ask for more."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(t) { page.s.put("agentInstructions", t) }
      }
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
      summary: page.summary(card.program, card.model, card.effort, card.level, card.levels)
      status: card.on ? card.st : "switched off"
      tone: card.on ? page.s.statusTone(card.st) : "idle"
      switchedOff: !card.on
      problem: !card.on ? ""
               : String(card.info.problem || "") !== "" ? String(card.info.problem)
               : card.agentName !== "" && !/^[a-z]+( [a-z]+){0,2}$/.test(card.agentName)
                 ? "A wake phrase is one to three plain words, letters only." : ""
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
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
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

      SettingRow {
        width: parent.width
        stacked: true
        label: "Program"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        SegmentedChoice {
          options: page.s.programOptions
          value: card.program
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onCommitted: function(v) {
            card.customModel = false
            page.updateAgent(card.index, "agent", v)
          }
        }
      }

      SettingRow {
        width: parent.width
        stacked: true
        label: "Model"
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
        }
      }

      SettingRow {
        width: parent.width
        stacked: true
        label: "Effort"
        hint: "How hard it thinks before answering. Changing it keeps the conversation."
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
        hint: card.level === "trusted"
              ? "Nothing is asked. A sentence starting with “" + card.agentName +
                "” can edit files and run commands in its folder."
              : "Its own level and folder: what you allow the main agent does not carry over."
        help: String(card.info.posture || "") !== "" ? "In force: " + card.info.posture + "." : ""
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
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
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

      SettingRow {
        width: parent.width
        stacked: true
        label: "Custom instructions"
        hint: "Its own, separate from the main agent's. Changing them keeps the conversation."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        InstructionsBox {
          value: String(card.modelData.instructions || "")
          placeholder: "What " + (card.label || "this agent") + " should always keep in mind"
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onCommitted: function(t) { page.updateAgent(card.index, "instructions", t) }
        }
      }

      SettingRow {
        width: parent.width
        stacked: true
        label: "Voice"
        hint: page.s.voiceMissing(String(card.modelData.voice || ""))
              ? "Not downloaded yet — choosing it starts the download." : ""
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
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
}
