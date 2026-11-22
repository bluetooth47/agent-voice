import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// One agent's folder: what it is for, who it is, what it is told, its
// saved chats and the folder itself (merged plan, Phase 12).
//
// The Agents page holds the settings (program, model, voice, permission);
// this page holds the text. Each file has one editor, here, and the card on
// the Agents page shows a one-line summary with a link to it. Nothing on
// this page writes a setting: the knobs are summarised with a link back,
// and removing or restoring an agent goes through the overlay's
// AgentFolders, the same code the Agents page uses.
Column {
  id: page

  required property var s

  spacing: Style.space(14)

  // --- which agent -----------------------------------------------------------
  // Remembered on the overlay for the session (s.detailsAgent), so leaving
  // the page and coming back finds the same agent. One tab each (phase M6,
  // item 9), main first, keyed by the agent's id: a rename changes the
  // label and keeps the selection.
  readonly property var agentTabs: {
    var out = [{ id: "main", label: s.mainLabel || "Main agent",
                 tone: s.statusTone(s.agentStatus("")),
                 tooltip: "The main agent · " + s.agentStatus("") }]
    for (var i = 0; i < s.voiceAgents.length; i++) {
      var a = s.voiceAgents[i] || {}
      var id = s.agentId(a)
      if (id === "") continue
      var on = a.enabled !== false
      var st = s.agentStatus(id)
      out.push({ id: id, label: s.agentLabel(a) || id,
                 tone: on ? s.statusTone(st) : "idle",
                 tooltip: on ? st : "Switched off" })
    }
    return out
  }
  readonly property string target: {
    for (var i = 0; i < agentTabs.length; i++) if (agentTabs[i].id === s.detailsAgent) return s.detailsAgent
    return "main"
  }
  readonly property bool isMain: target === "main"
  // An agent whose id is `communal` (only a hand edit can make one): that
  // name is the shared folder's, so it has no folder of its own, and every
  // folder action here would reach the communal folder instead.
  readonly property bool reserved: target === "communal"
  // What the editors and folder actions work on: nothing, for that agent.
  readonly property string folderTarget: reserved ? "" : target
  readonly property int index: {
    if (isMain) return -1
    for (var i = 0; i < s.voiceAgents.length; i++)
      if (s.agentId(s.voiceAgents[i] || {}) === target) return i
    return -1
  }
  readonly property var entry: index >= 0 ? (s.voiceAgents[index] || {}) : ({})
  readonly property string name: isMain ? s.mainLabel : (s.agentLabel(entry) || target)
  readonly property bool on: isMain || entry.enabled !== false
  readonly property string program: isMain ? (s.usingEndpoint ? "endpoint" : s.mainAgent)
                                           : String(entry.agent || "claude")
  readonly property var info: isMain ? ({}) : s.crewInfo(target)
  readonly property string endpointUrl: isMain ? String(s.setting("endpointUrl", ""))
                                               : String(entry.endpointUrl || "")
  readonly property string endpointHost: endpointUrl.replace(/^[a-z]+:\/\//i, "").split("/")[0]
  readonly property string folderPath: s.dataHome + "/agentvoice/agents/" + target
  // The folder as `agents list` saw it; undefined until read, or if absent.
  readonly property var folder: reserved ? undefined : s.folders.folders[target]
  readonly property bool folderMissing: reserved || (s.folders.foldersRead && folder === undefined)

  // Changes when the folder changes on disk: the daemon's sizes while it
  // runs, the overlay's own read otherwise, and every folder operation.
  readonly property string watch: JSON.stringify(s.vAgentFiles[target] || {}) +
                                  JSON.stringify(folder || {}) + s.folders.epoch

  function mapValue(key, agent) {
    var all = s.setting(key, {})
    if (!all || typeof all !== "object" || agent === "") return ""
    var v = all[agent]
    return typeof v === "string" ? v : ""
  }
  // The knobs, in one line: they are changed on the Agents page.
  readonly property string knobs: {
    var parts = []
    if (program === "endpoint") {
      parts.push("Endpoint")
      var m = isMain ? String(s.setting("endpointModel", "")) : String(entry.endpointModel || "")
      if (m !== "") parts.push(m)
    } else {
      parts.push(s.programLabel(program) || "no program")
      var model = isMain ? mapValue("agentModels", program) : String(entry.model || "")
      if (model !== "") parts.push(model)
      var level = isMain ? (mapValue("permissions", program) || s.permissionLevel) : String(entry.level || "ask")
      parts.push(s.levelLabel(level).toLowerCase())
    }
    var voice = isMain ? String(s.setting("voice", "lessac-medium")) : String(entry.voice || "")
    parts.push(voice === "" ? "the main agent's voice" : s.voiceName(voice) + " voice")
    return parts.join(" · ")
  }

  // Bound, never assigned, so a deep link that resets the overlay's tab
  // resets this page's too (Phase 12 review).
  readonly property string tab: s.detailsTab
  readonly property var tabs: [
    { id: "prompt", label: "Personality & instructions" },
    { id: "tools", label: "Tools & skills" },
    { id: "notes", label: "Notes" },
    { id: "chats", label: "Chats" },
    { id: "advanced", label: "Advanced" }
  ]
  function pickTab(id) { s.detailsTab = id }

  PageHeader {
    width: parent.width
    title: "Agent details"
    subtitle: "What each agent is for, who it is and what it is told. Its voice, program and " +
              "permission are on the Agents page."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  // Bound, never assigned: a pick asks the overlay, and `current` follows
  // the page's agent, so a removed agent's tab can never stay chosen while
  // the editors show the main one (the Phase 12 review's drop-down bug).
  AgentTabs {
    id: agentPicker
    width: parent.width
    agents: page.agentTabs
    current: page.target
    foreground: page.s.foreground
    accent: page.s.accent
    urgent: page.s.urgent
    fontFamily: page.s.fontFamily
    onPicked: function(id) { page.s.detailsAgent = id }
  }

  // The knobs, summarised, with the way to change them.
  Flow {
    width: parent.width
    spacing: Style.space(10)
    Text {
      width: Math.min(implicitWidth, parent.width)
      wrapMode: Text.WordWrap
      text: page.knobs
      textFormat: Text.PlainText
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
      height: changeLink.height
      verticalAlignment: Text.AlignVCenter
    }
    Button {
      id: changeLink
      text: "Change on Agents page →"
      focusable: true
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      fontSize: Style.font.caption
      onClicked: page.s.goTo("agents", page.target)
    }
  }

  // Why this agent would not answer now, when it would not.
  Text {
    width: parent.width
    visible: text !== ""
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: !page.on ? "Switched off: saying “" + String(page.entry.name || "") + "” does not wake it. " +
                     "Everything here is kept for when it is switched on."
          : String(page.info.problem || "") !== "" ? "Cannot be reached: " + String(page.info.problem) + "."
          : ""
    color: page.s.urgent
    font.family: page.s.fontFamily
    font.pixelSize: Style.font.caption
  }
  Text {
    width: parent.width
    visible: page.program === "endpoint" && page.endpointHost !== ""
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: "Runs on an endpoint: everything under “What " + page.name + " is told” is sent to " +
          page.endpointHost + " with each request, the other agents' names and roles included."
    color: page.s.dim
    font.family: page.s.fontFamily
    font.pixelSize: Style.font.caption
  }

  Text {
    width: parent.width
    visible: page.reserved
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: "This agent's id is “communal”, which is the shared folder's name, so it has no folder " +
          "of its own and nothing here can be edited. Give it another id in shell.json."
    color: page.s.urgent
    font.family: page.s.fontFamily
    font.pixelSize: Style.font.caption
  }

  // An agent with no folder: the files below cannot be saved until it has
  // one. The daemon makes any missing folder when it starts, too.
  Row {
    visible: page.folderMissing && !page.reserved
    spacing: Style.space(10)
    Text {
      anchors.verticalCenter: parent.verticalCenter
      text: page.name + " has no folder yet."
      textFormat: Text.PlainText
      color: page.s.urgent
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.body
    }
    Button {
      text: "Make its folder"
      bordered: true
      focusable: true
      enabled: !page.s.folders.busy
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onClicked: page.s.folders.create(page.target)
    }
  }

  TabStrip {
    width: parent.width
    options: page.tabs
    current: page.tab
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
    onPicked: function(id) { page.pickTab(id) }
  }

  // --- Personality & instructions ----------------------------------------------
  Column {
    width: parent.width
    spacing: Style.space(16)
    visible: page.tab === "prompt"

    // Each box: a name, one line on what it is for (the rest on hover),
    // starters while it is empty, the editor and its meter (phase M6).
    Column {
      width: parent.width
      spacing: Style.space(4)
      Text {
        text: "Role"
        textFormat: Text.PlainText
        color: page.s.foreground
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
      }
      Hint {
        width: parent.width
        text: "What " + page.name + " is for. The other agents see it; " + page.name + " does not."
        detail: "One or two lines, such as “Quick answers and lookups; hand anything that needs " +
                "code to Theo.” Every other agent sees it in its list of agents here, as " +
                "information about " + page.name + ", never as instructions to follow."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
      StarterChips {
        width: parent.width
        visible: page.offerStarters(roleEditor)
        starters: page.starters.role || []
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onPicked: function(t) { roleEditor.fill(t) }
      }
      FileEditor {
        id: roleEditor
        target: page.folderTarget
        keeper: page.s.folders
        file: "role.md"
        limit: 300
        minHeight: Style.space(48)
        watch: page.watch
        placeholder: "e.g. Quick answers and lookups."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
    }

    Column {
      width: parent.width
      spacing: Style.space(4)
      Text {
        text: "Personality"
        textFormat: Text.PlainText
        color: page.s.foreground
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
      }
      Hint {
        width: parent.width
        text: "Who " + page.name + " is: manner and tone. Told to it on every turn."
        detail: "Up to 1500 characters, told to " + page.name + " under “About you”. For what " +
                "it should do or remember, use its instructions below; for how it sounds, its " +
                "voice is on the Agents page.\n\nA change is told to it from its next turn, but " +
                "a conversation already under way keeps its history, and it may go on answering " +
                "as it has been. A new conversation starts with the change."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
      // The trait chips: one managed line at the top of personality.md,
      // rewritten by `agents traits apply` and saved by the editor below,
      // so typed text is never touched and the save keeps its stamp check.
      Repeater {
        model: page.traitRows
        Row {
          required property var modelData
          spacing: Style.space(8)
          Text {
            width: Style.space(76)
            height: Style.spacing.controlHeight
            verticalAlignment: Text.AlignVCenter
            text: modelData.label
            textFormat: Text.PlainText
            color: page.s.dim
            font.family: page.s.fontFamily
            font.pixelSize: Style.font.caption
          }
          ToggleChips {
            width: Math.max(implicitWidth, Style.space(200))
            options: modelData.values.map(function(v) {
              return { value: v, label: v.charAt(0).toUpperCase() + v.slice(1),
                       disabledReason: page.traitsWhyNot }
            })
            chipStates: page.chipStates(modelData.id)
            foreground: page.s.foreground
            accent: page.s.accent
            urgent: page.s.urgent
            fontFamily: page.s.fontFamily
            onToggled: function(value, state) {
              page.setTrait(modelData.id, state === "on" ? value : null)
            }
          }
        }
      }
      Hint {
        width: parent.width
        text: page.traitsNote !== "" ? page.traitsNote
              : "The chips write one line at the top: “Traits: warm, brief, casual.”"
        tone: page.traitsNote !== "" ? "warn" : ""
        detail: "Only that line changes; everything you type below it is kept as it is. A " +
                "value you typed into the line yourself is kept too."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
      StarterChips {
        width: parent.width
        visible: page.offerStarters(personalityEditor)
        starters: page.starters.personality || []
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onPicked: function(t) { personalityEditor.fill(t) }
      }
      FileEditor {
        id: personalityEditor
        target: page.folderTarget
        keeper: page.s.folders
        file: "personality.md"
        limit: 1500
        watch: page.watch
        placeholder: "e.g. Warm and a little dry. Speaks plainly, never gushes."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
      // Try it: one sentence in its voice from what is in the boxes now.
      Flow {
        width: parent.width
        spacing: Style.space(10)
        Button {
          id: tryButton
          text: tryer.running ? "Trying…" : "▶ Try it"
          bordered: true
          focusable: true
          enabled: !tryer.running && !tryCooldown.running && !page.reserved && page.tryWhyNot === ""
          tooltipText: "Runs one short turn on " + page.name + "'s program, with no tools, and " +
                       "says its first sentence aloud. Uses what is in the boxes now, saved or " +
                       "not. Never saved to a chat. One try every 10 seconds."
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onClicked: page.tryIt()
        }
        Hint {
          width: Math.min(implicitWidth, parent.width)
          height: tryButton.height
          verticalAlignment: Text.AlignVCenter
          text: page.tryWhyNot !== "" ? page.tryWhyNot
                : tryCooldown.running && !tryer.running ? "One try every 10 seconds."
                : "Hear one sentence in " + page.name + "'s voice. Costs a short turn."
          tone: page.tryWhyNot !== "" ? "warn" : ""
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
        }
      }
      Text {
        width: parent.width
        visible: page.tryNote !== "" && page.tryFor === page.target
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: page.tryNote
        color: page.trySaid ? page.s.foreground : page.s.urgent
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
    }

    Column {
      width: parent.width
      spacing: Style.space(4)
      Text {
        text: "Standing instructions"
        textFormat: Text.PlainText
        color: page.s.foreground
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
      }
      Hint {
        width: parent.width
        text: "What " + page.name + " should always do or keep in mind."
        detail: "How to address you, what to keep in mind, how long to talk. They sit after " +
                "the rule that replies are spoken, so asking for lists or code blocks will still " +
                "be read out as speech. Up to 2000 characters. Changing them keeps the conversation."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
      StarterChips {
        width: parent.width
        visible: page.offerStarters(instructionsEditor)
        starters: page.starters.instructions || []
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onPicked: function(t) { instructionsEditor.fill(t) }
      }
      // The old setting (`agentInstructions`, or the entry's `instructions`)
      // only until instructions.md exists (Phase 10).
      FileEditor {
        id: instructionsEditor
        target: page.folderTarget
        keeper: page.s.folders
        file: "instructions.md"
        limit: 2000
        fallback: page.isMain ? String(page.s.setting("agentInstructions", ""))
                              : String(page.entry.instructions || "")
        watch: page.watch
        placeholder: "e.g. Call me Sam. Keep answers to one sentence unless I ask for more."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
    }

    // What the agent is told, built by the same code the daemon builds it
    // with (`agents preview`), after every save here and every change on disk.
    Column {
      width: parent.width
      spacing: Style.space(8)

      Item {
        width: parent.width
        height: Math.max(previewTitle.implicitHeight, refreshLink.height)
        Text {
          id: previewTitle
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          text: "What " + page.name + " is told"
          textFormat: Text.PlainText
          color: page.s.foreground
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.body
          font.bold: true
        }
        Button {
          id: refreshLink
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          text: previewer.running ? "Reading…" : "Refresh"
          focusable: true
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          fontSize: Style.font.caption
          onClicked: page.loadPreview()
        }
      }
      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        text: "In this order, with every request it is sent; the request itself comes after."
        color: page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      PromptPreview {
        width: parent.width
        parts: page.previewParts
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
      Text {
        width: parent.width
        visible: page.previewError !== ""
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: "Could not show it: " + page.previewError
        color: page.s.urgent
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
  }

  // --- starters, trait chips and Try it (phase M6, item 10) -------------------
  // The starters, read once: they ship with the plugin.
  property var starters: ({})
  Process {
    id: starterReader
    command: ["agentvoice", "agents", "templates", "--json"]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var d = JSON.parse(String(text))
          if (d && typeof d === "object") page.starters = d
        } catch (e) { }
      }
    }
  }
  // Offered only for a box that is read, empty and not being typed in.
  function offerStarters(ed) {
    return !page.reserved && ed.loaded && !ed.holding && !ed.editing && ed.current.trim() === ""
  }

  // The chips' rows, in the order traits.py writes them.
  readonly property var traitRows: [
    { id: "tone", label: "Tone", values: ["warm", "dry", "playful"] },
    { id: "length", label: "Length", values: ["brief", "detailed"] },
    { id: "formality", label: "Formality", values: ["casual", "formal"] }
  ]
  // What the managed line in the personality box says now, from `agents
  // traits apply` on the box's text: {traits: {tone, length, formality}, ...}.
  property var traitsNow: null
  property string traitsFor: ""
  property string traitsNote: ""
  readonly property string traitsWhyNot: page.reserved ? "this agent has no folder"
                                         : !personalityEditor.loaded ? "reading its personality first"
                                         : traitWriter.running ? "saving the last choice"
                                         : ""
  function chipStates(category) {
    var out = {}
    var now = page.traitsNow && page.traitsFor === page.target ? page.traitsNow.traits || {} : {}
    for (var r of page.traitRows)
      if (r.id === category)
        for (var v of r.values) out[v] = now[category] === v ? "on" : "off"
    return out
  }
  function readTraits() {
    if (page.reserved || !personalityEditor.loaded) return
    if (traitReader.running) { traitDelay.restart(); return }
    traitReader.forTarget = page.target
    traitReader.baseText = personalityEditor.current
    traitReader.pending = JSON.stringify({ text: personalityEditor.current }) + "\n"
    traitReader.running = true
  }
  // One choice: the box's text with its line rewritten, then saved by the
  // editor on its own stamp, exactly as if it had been typed.
  function setTrait(category, value) {
    if (page.traitsWhyNot !== "" || traitWriter.running) return
    var change = {}
    change[category] = value
    page.traitsNote = ""
    traitWriter.forTarget = page.target
    // What the choice was made on: a result for older text is dropped.
    traitWriter.baseText = personalityEditor.current
    traitWriter.baseStamp = personalityEditor.stamp
    traitWriter.pending = JSON.stringify({ text: personalityEditor.current, traits: change }) + "\n"
    traitWriter.running = true
  }
  Timer { id: traitDelay; interval: 300; onTriggered: page.readTraits() }
  Connections {
    target: personalityEditor
    function onCurrentChanged() { traitDelay.restart() }
    function onLoadedChanged() { traitDelay.restart() }
  }
  Process {
    id: traitReader
    property string forTarget: ""
    property string baseText: ""
    property string pending: ""
    command: ["agentvoice", "agents", "traits", "apply"]
    stdinEnabled: true
    onStarted: { write(traitReader.pending); traitReader.pending = "" }
    stdout: StdioCollector {
      onStreamFinished: {
        if (traitReader.forTarget !== page.target) return
        // Typed on since: the next read (already scheduled) says it.
        if (personalityEditor.current !== traitReader.baseText) return
        try {
          var d = JSON.parse(String(text))
          if (d && d.traits) { page.traitsNow = d; page.traitsFor = traitReader.forTarget }
        } catch (e) { }
      }
    }
  }
  Process {
    id: traitWriter
    property string forTarget: ""
    property string baseText: ""
    property string baseStamp: ""
    property string pending: ""
    property string err: ""
    command: ["agentvoice", "agents", "traits", "apply"]
    stdinEnabled: true
    onStarted: { traitWriter.err = ""; write(traitWriter.pending); traitWriter.pending = "" }
    stdout: StdioCollector {
      onStreamFinished: {
        if (traitWriter.forTarget !== page.target) return
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (!d || typeof d.text !== "string") return
        // The box was typed in, or reloaded from a newer file, while this
        // ran: saving it would put the older text back over the newer, on
        // a stamp that may be the new one (Codex review of M6).
        if (personalityEditor.current !== traitWriter.baseText ||
            personalityEditor.stamp !== traitWriter.baseStamp) {
          page.traitsNote = "Not changed: the personality changed while that was chosen. Choose again."
          page.readTraits()
          return
        }
        page.traitsNow = d
        page.traitsFor = traitWriter.forTarget
        personalityEditor.fill(d.text)
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t !== "" && traitWriter.forTarget === page.target)
          page.traitsNote = "Not changed: " + t.replace(/^agentvoice agents: /, "").split("\n").pop()
      }
    }
  }

  // Try it. The draft goes on stdin as one JSON line; the sentence comes
  // back on stdout, or why not on stderr (the service off, the screen
  // locked, an agent busy, the 10 s limit -- the daemon decides).
  // Where Try it cannot run, said before the press (try_it.backend_refusal
  // decides; the daemon asks it again).
  readonly property string tryWhyNot: {
    if (page.program === "claude") return ""
    if (page.program === "endpoint")
      return (page.isMain ? page.s.setting("endpointIsAgent", false) === true
                          : page.entry.endpointIsAgent === true)
             ? "Try it is off for an agent endpoint: its own tools cannot be switched off from here." : ""
    return "Try it runs only where a turn can start with no tools at all: Claude Code and plain " +
           "endpoints so far, not " + (page.s.programLabel(page.program) || page.program) + "."
  }
  property string tryNote: ""
  property string tryFor: ""
  property bool trySaid: false
  function tryIt() {
    if (tryer.running || page.reserved) return
    page.tryNote = ""
    page.trySaid = false
    tryer.forTarget = page.target
    tryer.launched = false
    tryer.answered = false
    tryer.command = ["agentvoice", "try", page.target]
    tryer.pending = JSON.stringify({ personality: personalityEditor.current,
                                     instructions: instructionsEditor.current }) + "\n"
    tryer.running = true
    tryCooldown.restart()
  }
  Timer { id: tryCooldown; interval: 10000 }
  Process {
    id: tryer
    property string forTarget: ""
    property string pending: ""
    property bool launched: false
    property bool answered: false
    stdinEnabled: true
    onStarted: { tryer.launched = true; write(tryer.pending); tryer.pending = "" }
    // `running` going false, not onExited: a spawn that never started emits
    // no exit, and a press that did nothing must say so.
    onRunningChanged: if (!running && !launched) {
      page.tryFor = tryer.forTarget
      page.trySaid = false
      page.tryNote = "Not tried: the agentvoice command could not be run."
    }
    stdout: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t === "") return
        tryer.answered = true
        page.tryFor = tryer.forTarget
        page.trySaid = true
        page.tryNote = "Said: “" + t + "”"
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t === "" || tryer.answered) return
        page.tryFor = tryer.forTarget
        page.trySaid = false
        page.tryNote = "Not tried: " + t.split("\n").pop()
      }
    }
  }

  property var previewParts: []
  property string previewError: ""
  // Everything the preview is built from: every folder (the other agents'
  // roles are in the roster), the agent list (names, wake phrases, who is
  // switched on) and who the daemon can reach.
  readonly property string previewWatch: page.watch + roleEditor.stamp + personalityEditor.stamp +
                                         instructionsEditor.stamp +
                                         JSON.stringify(s.vAgentFiles) + JSON.stringify(s.folders.folders) +
                                         JSON.stringify(s.voiceAgents) + JSON.stringify(s.vCrew) +
                                         s.mainLabel + s.activePhrase +
                                         // What it is given (Phase 13): the switches, its
                                         // program and level.
                                         JSON.stringify([s.setting("mainTools", {}),
                                                         s.setting("desktopTools", false),
                                                         s.setting("browserTools", false),
                                                         s.setting("omarchySkill", true),
                                                         s.setting("permissions", {}),
                                                         s.setting("mainProgram", ""),
                                                         s.mainAgent, s.usingEndpoint])
  onPreviewWatchChanged: { previewDelay.restart(); catalogDelay.restart() }
  onTargetChanged: {
    previewParts = []; catalog = null; removeButton.disarm(); loadPreview(); loadCatalog()
    traitsNow = null; traitsNote = ""; traitDelay.restart()
  }
  Component.onCompleted: { loadPreview(); loadCatalog(); starterReader.running = true }
  Timer { id: previewDelay; interval: 250; onTriggered: page.loadPreview() }

  // A source path, in words.
  function fromWords(source) {
    var src = String(source || "")
    if (src === "built in") return "Built in"
    if (src === "communal/rules.md") return "From Communal · rules"
    if (src === "communal/defaults.md") return "From Communal · defaults"
    if (src === "each agent's role.md") return "From each other agent's role"
    if (src === "skills folders") return "From " + page.name + "'s and the communal skills"
    var m = src.match(/^agents\/[^\/]+\/(personality|instructions)\.md$/)
    if (m) return "From " + page.name + "'s " + m[1]
    return src
  }
  function loadPreview() {
    if (page.reserved) { previewParts = []; return }
    if (previewer.running) { previewDelay.restart(); return }
    previewer.forTarget = page.target
    previewer.command = ["agentvoice", "agents", "preview", page.target, "--json"]
    previewer.running = true
  }
  Process {
    id: previewer
    property string forTarget: ""
    stdout: StdioCollector {
      onStreamFinished: {
        if (previewer.forTarget !== page.target) return
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (!Array.isArray(d)) return
        page.previewError = ""
        page.previewParts = d.map(function(x) {
          var label = String((x || {}).label || "")
          return {
            label: label,
            from: page.fromWords(x.source),
            text: String(x.text || ""),
            note: String((x || {}).note || "") !== "" ? String(x.note)
                  : label.indexOf("Omarchy commands") === 0
                  ? (page.program === "claude"
                     ? "Loaded by Claude Code as a skill, when a request needs one."
                     : "A list of this machine's omarchy commands, given in full.")
                  : ""
          }
        })
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t !== "" && previewer.forTarget === page.target)
          page.previewError = t.replace(/^agentvoice agents: /, "").split("\n").pop()
      }
    }
  }

  // --- Tools & skills -------------------------------------------------------------
  // Everything this agent can be given (merged plan, Phase 13), from `agents
  // catalog`, the daemon's own resolution: each tool switched on or off (its
  // own switch, or the setting for every agent), whether its program can use
  // it and why not, and whether it asks first at its level; then its skills.
  // The switches themselves are on its Agents card.
  property var catalog: null
  property string catalogError: ""
  function loadCatalog() {
    if (page.reserved) { catalog = null; return }
    if (cataloger.running) { catalogDelay.restart(); return }
    cataloger.forTarget = page.target
    cataloger.command = ["agentvoice", "agents", "catalog", page.target, "--json"]
    cataloger.running = true
  }
  Timer { id: catalogDelay; interval: 250; onTriggered: page.loadCatalog() }
  // The commands read shell.json from disk, which the store writes after
  // the page already shows a change: read again once a save has landed
  // (Phase 13 review: a switch could show its old value after saving).
  Connections {
    target: page.s.store
    function onSaved(key) { catalogDelay.restart(); previewDelay.restart() }
  }
  Process {
    id: cataloger
    property string forTarget: ""
    stdout: StdioCollector {
      onStreamFinished: {
        if (cataloger.forTarget !== page.target) return
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (!d || !Array.isArray(d.tools)) return
        page.catalogError = ""
        page.catalog = d
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t !== "" && cataloger.forTarget === page.target)
          page.catalogError = t.replace(/^agentvoice agents: /, "").split("\n").pop()
      }
    }
  }
  Process {
    id: skillsFolder
    stdout: StdioCollector {
      onStreamFinished: {
        var path = String(text).trim()
        if (path !== "") page.openFolder(path)
      }
    }
  }
  // Keep a skill made or changed by hand: `agents ack`, on the stamp shown.
  property string skillNote: ""
  Process {
    id: skillKeeper
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        page.skillNote = t === "" ? "" : "Not kept: " + t.replace(/^agentvoice agents: /, "").split("\n").pop()
      }
    }
    onRunningChanged: if (!running) { page.s.folders.refresh(); page.loadCatalog() }
  }
  function keepSkill(source, name, stamp) {
    if (skillKeeper.running) return
    skillNote = ""
    skillKeeper.command = ["agentvoice", "agents", "ack", source, "skills/" + name + "/SKILL.md"]
                          .concat(stamp ? ["--base", stamp] : [])
    skillKeeper.running = true
  }
  function openSkills() {
    skillsFolder.command = ["agentvoice", "agents", "skills-folder", page.target]
    skillsFolder.running = true
  }

  Column {
    id: toolsTab
    width: parent.width
    spacing: Style.space(10)
    visible: page.tab === "tools"

    readonly property var c: page.catalog && page.catalog.agent === page.target ? page.catalog : null
    readonly property var ownSkills: c ? c.skills.filter(function(x) { return x.source !== "communal" }) : []
    readonly property var sharedSkills: c ? c.skills.filter(function(x) { return x.source === "communal" }) : []

    Text {
      width: parent.width
      visible: toolsTab.c === null || page.catalogError !== ""
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      // Shown over an older reading too, which then may be out of date.
      text: page.catalogError !== "" ? "Could not read what it is given" +
                                       (toolsTab.c !== null ? " now; this may be out of date" : "") +
                                       ": " + page.catalogError : "Reading…"
      color: page.catalogError !== "" ? page.s.urgent : page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    Repeater {
      model: toolsTab.c ? toolsTab.c.tools : []
      SettingRow {
        required property var modelData
        width: parent.width
        label: modelData.label
        hint: !modelData.can ? modelData.why_not
              : !modelData.on ? ""
              : modelData.asks + (modelData.how !== "" ? " " + modelData.how : "")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        Text {
          text: !modelData.can ? "Cannot use"
                : (modelData.on ? "On" : "Off") +
                  (modelData.choice === "inherit" ? ", as for every agent" : ", its own switch")
          textFormat: Text.PlainText
          color: modelData.can && modelData.on ? page.s.foreground : page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }
    SettingRow {
      readonly property var collab: toolsTab.c ? toolsTab.c.collab : undefined

      width: parent.width
      visible: !!collab
      label: "Collaboration"
      hint: {
        if (!collab) return ""
        var levelWords = { off: "Off", ask: "Ask me first", announce: "Announce", allow: "Quietly" }
        var status = collab.can_start
                     ? page.name + " can start collaboration: " + (levelWords[collab.level] || levelWords.ask)
                     : page.name + " can be asked; " + page.name + " can't ask others."
        return [status, collab.can_start ? collab.says : collab.why_not, collab.receives]
               .filter(Boolean).join("\n")
      }
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
    }
    Button {
      text: "Change on " + page.name + "'s Agents card →"
      focusable: true
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      fontSize: Style.font.caption
      onClicked: page.s.goTo("agents", page.target, "tools")
    }

    Text {
      width: parent.width
      topPadding: Style.space(8)
      text: "Skills"
      color: page.s.foreground
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.body
      font.bold: true
    }
    Text {
      width: parent.width
      visible: toolsTab.c !== null
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: toolsTab.c ? toolsTab.c.delivery_how +
                         (toolsTab.c.skills_asks !== "" ? " A skill's scripts, at its level: " +
                          toolsTab.c.skills_asks.charAt(0).toLowerCase() + toolsTab.c.skills_asks.slice(1) : "")
                       : ""
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    Repeater {
      model: [
        { title: page.name + "'s own", items: toolsTab.ownSkills,
          empty: "None in " + page.name + "'s folder." },
        { title: "From Communal", items: toolsTab.sharedSkills,
          empty: "None in the communal folder." }
      ]
      Column {
        required property var modelData
        width: toolsTab.width
        spacing: Style.space(4)
        visible: toolsTab.c !== null
        Text {
          text: modelData.title
          textFormat: Text.PlainText
          color: page.s.foreground
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }
        Text {
          visible: modelData.items.length === 0
          text: modelData.empty
          textFormat: Text.PlainText
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
        Repeater {
          model: modelData.items
          Column {
            required property var modelData
            width: toolsTab.width
            spacing: Style.space(2)
            Text {
              width: parent.width
              wrapMode: Text.WordWrap
              textFormat: Text.PlainText
              text: modelData.name + " — " +
                    (modelData.problem !== "" ? "not given: " + modelData.problem
                     : modelData.shadowed ? "not given: " + page.name + " has its own of the same name"
                     : !modelData.delivered ? "not given to " + page.name
                     : modelData.description)
              color: modelData.problem !== "" ? page.s.urgent
                     : modelData.delivered ? page.s.foreground : page.s.dim
              font.family: page.s.fontFamily
              font.pixelSize: Style.font.caption
            }
            // Made or edited by hand (a skill always is), so it reads as
            // changed outside Settings until it is kept, as the other files.
            Flow {
              width: parent.width
              visible: modelData.changed_outside === true
              spacing: Style.space(8)
              Text {
                text: "Added or changed outside Settings."
                color: page.s.dim
                font.family: page.s.fontFamily
                font.pixelSize: Style.font.caption
              }
              Button {
                text: "Keep"
                focusable: true
                enabled: !skillKeeper.running
                foreground: page.s.foreground
                fontFamily: page.s.fontFamily
                fontSize: Style.font.caption
                tooltipText: "It applies already. Keep saves this version, so the notice goes."
                onClicked: page.keepSkill(modelData.source, modelData.name, modelData.stamp)
              }
            }
          }
        }
      }
    }
    Text {
      width: parent.width
      visible: page.skillNote !== ""
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: page.skillNote
      color: page.s.urgent
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: "A skill is a folder holding SKILL.md, which starts with a line of ---, then " +
            "“name:” (the folder's name) and “description:” (one line on when to use it, at most " +
            "300 characters), then ---, then the instructions. Scripts beside it are run by the " +
            "agent, never by Agent Voice. One in " + page.name + "'s folder beats a communal one " +
            "of the same name."
      textFormat: Text.PlainText
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Flow {
      width: parent.width
      spacing: Style.space(8)
      Button {
        text: "Open " + page.name + "'s skills folder"
        bordered: true
        focusable: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.openSkills()
      }
      Button {
        text: "Communal skills →"
        focusable: true
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        fontSize: Style.font.caption
        onClicked: page.s.goTo("communal", "", "skills")
      }
    }
  }

  // --- Notes (Phase 14) -------------------------------------------------------------
  // Its own notes. Whether it may write them is on its Agents card; the
  // catalog says whether its program takes the notes tools at all.
  NotesPanel {
    width: parent.width
    visible: page.tab === "notes" && !page.reserved
    target: page.target
    owner: page.name
    whyNot: page.catalog && page.catalog.agent === page.target && page.catalog.notes
            ? page.catalog.notes.why_not : ""
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }
  Text {
    width: parent.width
    visible: page.tab === "notes" && page.catalog && page.catalog.agent === page.target &&
             page.catalog.notes && page.catalog.notes.can
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: page.catalog && page.catalog.notes
          ? (page.catalog.notes.write === "allow" ? page.name + " may write notes. " : page.name + " may only read notes. ") +
            page.catalog.notes.asks
          : ""
    color: page.s.dim
    font.family: page.s.fontFamily
    font.pixelSize: Style.font.caption
  }
  Button {
    visible: page.tab === "notes" && !page.reserved
    text: "Change on " + page.name + "'s Agents card →"
    bordered: true
    focusable: true
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
    onClicked: page.s.goTo("agents", page.target, "tools")
  }

  // --- Chats ------------------------------------------------------------------------
  // Chats this agent can continue, from the same index the conversation view reads.
  property var chatIndex: []
  FileView {
    id: chatIndexFile
    path: page.s.dataHome + "/agentvoice/chats/index.json"
    watchChanges: true
    printErrors: false
    onFileChanged: chatIndexFile.reload()
    onLoaded: {
      try {
        var d = JSON.parse(chatIndexFile.text())
        page.chatIndex = (d && Array.isArray(d.chats)) ? d.chats : []
      } catch (e) { page.chatIndex = [] }
    }
    onLoadFailed: page.chatIndex = []
  }
  readonly property var chats: {
    var out = []
    for (var i = 0; i < chatIndex.length; i++) {
      var c = chatIndex[i] || {}
      if (!/^[0-9a-f]{16}$/.test(String(c.id || ""))) continue
      if (chatOwner(c) === target || (Array.isArray(c.agents) && c.agents.indexOf(target) >= 0)) out.push(c)
    }
    out.sort(function(a, b) { return (Number(b.updated) || 0) - (Number(a.updated) || 0) })
    return out
  }
  function chatOwner(chat) {
    return String(chat.owner || chat.agent_id || "main")
  }
  // A Repeater's modelData turns a JSON array into a list Array.isArray
  // does not recognise, so membership is checked by hand.
  function listHas(list, id) {
    if (!list || list.length === undefined) return false
    for (var i = 0; i < list.length; i++) if (list[i] === id) return true
    return false
  }
  function chatCaption(chat) {
    var preview = String(chat.preview || "")
    if (chatOwner(chat) === page.target) return preview
    var relation = ""
    if (page.listHas(chat.participants, page.target))
      relation = "passed to it"
    else if (page.listHas(chat.shared_with, page.target))
      relation = "shared"
    return relation && preview ? relation + " · " + preview : relation || preview
  }
  function openChat(id) {
    s.openChat = ""
    s.openChat = id
    s.showPage("history")
  }

  readonly property var collaborationTasks: {
    var open = [], finished = []
    for (var task of (s.vTasks || [])) {
      if (!task || (task.from !== target && task.to !== target)) continue
      if (task.state === "pending" || task.state === "active") open.push(task)
      else if (["completed", "cancelled", "failed", "refused"].indexOf(task.state) >= 0) finished.push(task)
    }
    // The daemon publishes tasks oldest first.
    return open.concat(finished.reverse().slice(0, 5))
  }
  function taskCaption(task) {
    var status = task.state
    if (task.state === "active") {
      status = "working"
    } else if (task.state === "pending") {
      status = task.kind === "pass" ? "passing" : "queued"
      var place = Number(task.position) || 0
      if (place > 0) {
        var suffix = place % 100 >= 11 && place % 100 <= 13 ? "th"
                     : (["th", "st", "nd", "rd"][place % 10] || "th")
        status += " (" + place + suffix + " in line)"
      }
    }
    return (task.from_label || task.from) + " → " + (task.to_label || task.to) + " · " + status
           + (task.reason ? " · " + task.reason : "")
  }

  Process {
    id: taskCanceller
    property string forTarget: ""
    property string note: ""
    property bool launched: false
    onStarted: launched = true
    onRunningChanged: if (!running && !launched) note = "Could not start agentvoice."
    stderr: StdioCollector {
      onStreamFinished: {
        var message = text.trim()
        if (message !== "") taskCanceller.note = message
      }
    }
  }

  Column {
    width: parent.width
    spacing: Style.space(6)
    visible: page.tab === "chats"

    Column {
      width: parent.width
      spacing: Style.space(6)

      Text {
        width: parent.width
        text: "Collaboration"
        color: page.s.foreground
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.subtitle
        font.bold: true
      }
      Text {
        width: parent.width
        visible: page.collaborationTasks.length === 0
        wrapMode: Text.WordWrap
        text: "No tasks between agents right now. Passing a chat to another agent shows here."
        color: page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.body
      }
      Repeater {
        model: page.tab === "chats" ? page.collaborationTasks : []
        Item {
          id: taskRow
          required property var modelData
          readonly property bool isOpen: modelData.state === "pending" || modelData.state === "active"
          width: parent.width
          height: Math.max(taskText.implicitHeight, isOpen ? cancelTask.implicitHeight : 0)

          Text {
            id: taskText
            anchors.left: parent.left
            anchors.right: taskRow.isOpen ? cancelTask.left : parent.right
            anchors.rightMargin: taskRow.isOpen ? Style.space(8) : 0
            anchors.verticalCenter: parent.verticalCenter
            wrapMode: Text.Wrap
            textFormat: Text.PlainText
            text: page.taskCaption(taskRow.modelData)
            color: taskRow.isOpen ? page.s.foreground : page.s.dim
            font.family: page.s.fontFamily
            font.pixelSize: Style.font.caption
          }
          Button {
            id: cancelTask
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            visible: taskRow.isOpen
            enabled: !taskCanceller.running
            text: "Cancel"
            bordered: true
            focusable: true
            foreground: page.s.foreground
            fontFamily: page.s.fontFamily
            fontSize: Style.font.caption
            onClicked: {
              taskCanceller.forTarget = page.target
              taskCanceller.note = ""
              taskCanceller.launched = false
              taskCanceller.command = ["agentvoice", "tasks", "cancel", String(taskRow.modelData.id)]
              taskCanceller.running = true
            }
          }
        }
      }
      Text {
        width: parent.width
        visible: taskCanceller.forTarget === page.target && text !== ""
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: taskCanceller.note
        color: page.s.urgent
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
    PanelSeparator {
      width: parent.width
      foreground: page.s.foreground
    }

    Text {
      width: parent.width
      visible: !page.s.saveChats
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "Saving chats is off, so nothing is kept once a conversation ends. It is switched on " +
            "on the Display page."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.body
    }
    Button {
      visible: !page.s.saveChats
      text: "Go to Display →"
      focusable: true
      bordered: true
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onClicked: page.s.goTo("display", "")
    }
    Text {
      width: parent.width
      visible: page.s.saveChats && page.chats.length === 0
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "No saved chats with " + page.name + " yet."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.body
    }
    Repeater {
      model: page.s.saveChats ? page.chats : []
      Rectangle {
        id: chatRow
        required property var modelData
        width: parent.width
        height: chatText.implicitHeight + Style.space(12)
        radius: Style.cornerRadius
        color: chatHover.containsMouse || chatRow.activeFocus
               ? Qt.rgba(page.s.foreground.r, page.s.foreground.g, page.s.foreground.b, 0.08) : "transparent"
        border.width: chatRow.activeFocus ? 1 : 0
        border.color: page.s.accent
        activeFocusOnTab: true
        Keys.onReturnPressed: page.openChat(String(modelData.id))
        Keys.onSpacePressed: page.openChat(String(modelData.id))
        Column {
          id: chatText
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          anchors.margins: Style.space(8)
          spacing: Style.space(2)
          Text {
            width: parent.width
            elide: Text.ElideRight
            textFormat: Text.PlainText
            text: (String(chatRow.modelData.title || "") || "Untitled") +
                  (chatRow.modelData.updated ? "  ·  " + Qt.formatDateTime(new Date(Number(chatRow.modelData.updated) * 1000), "MMM d, h:mm AP") : "")
            color: page.s.foreground
            font.family: page.s.fontFamily
            font.pixelSize: Style.font.body
          }
          Text {
            width: parent.width
            visible: text !== ""
            elide: Text.ElideRight
            textFormat: Text.PlainText
            text: page.chatCaption(chatRow.modelData)
            color: page.s.dim
            font.family: page.s.fontFamily
            font.pixelSize: Style.font.caption
          }
        }
        MouseArea {
          id: chatHover
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: page.openChat(String(chatRow.modelData.id))
        }
      }
    }
  }

  // --- Advanced ---------------------------------------------------------------------
  Process { id: opener }
  function openFolder(path) {
    opener.command = ["xdg-open", path]
    opener.running = true
  }
  function when(at) {
    return at > 0 ? Qt.formatDateTime(new Date(at * 1000), "MMM d, h:mm AP") : ""
  }

  Column {
    width: parent.width
    spacing: Style.space(12)
    visible: page.tab === "advanced"

    SettingRow {
      width: parent.width
      label: "Id"
      hint: "What its folder, saved chats and permissions know it by. It never changes, not even on a rename."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      Text {
        text: page.target
        textFormat: Text.PlainText
        color: page.s.foreground
        font.family: "monospace"
        font.pixelSize: Style.font.caption
      }
    }

    SettingRow {
      width: parent.width
      stacked: true
      label: "Folder"
      hint: "Its files can be edited here or by hand; a hand edit applies on its next turn."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      Column {
        width: parent.width
        spacing: Style.space(6)
        Text {
          width: parent.width
          wrapMode: Text.WrapAnywhere
          textFormat: Text.PlainText
          text: page.folderPath
          color: page.s.dim
          font.family: "monospace"
          font.pixelSize: Style.font.caption
        }
        Row {
          spacing: Style.space(8)
          Button {
            text: "Open folder"
            iconText: "\u{f0770}"
            bordered: true
            focusable: true
            enabled: !page.folderMissing
            foreground: page.s.foreground
            fontFamily: page.s.fontFamily
            onClicked: page.openFolder(page.folderPath)
          }
          Button {
            text: "Export"
            iconText: "\u{f0207}"
            tooltipText: "Copy its role, personality, instructions and skills to a new folder in Downloads"
            bordered: true
            focusable: true
            enabled: !page.folderMissing && !page.s.folders.busy
            foreground: page.s.foreground
            fontFamily: page.s.fontFamily
            onClicked: page.s.folders.exportFolder(page.target)
          }
          // Moves the folder and the settings entry to the trash; Undo and
          // the trash list below give it back.
          DangerButton {
            id: removeButton
            visible: !page.isMain && page.index >= 0
            text: "Remove"
            question: "Really remove " + page.name + "?"
            confirmText: "Remove"
            enabled: !page.s.folders.busy
            foreground: page.s.foreground
            urgent: page.s.urgent
            fontFamily: page.s.fontFamily
            onConfirmed: page.s.folders.remove(page.index)
          }
        }
      }
    }

    // What the last folder operation did, or why it failed; and the Undo for
    // a removal, from here or from the Agents page.
    Text {
      width: parent.width
      visible: page.s.folders.done !== ""
      wrapMode: Text.WrapAnywhere
      textFormat: Text.PlainText
      text: page.s.folders.done
      color: page.s.foreground
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      visible: page.s.folders.note !== ""
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: page.s.folders.note
      color: page.s.urgent
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    SettingRow {
      width: parent.width
      stacked: true
      label: "Trash"
      hint: "Removed agents, each with its folder and settings. Restore puts one back as it was."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      Column {
        width: parent.width
        spacing: Style.space(4)
        Text {
          visible: page.s.folders.trash.length === 0
          text: "The trash is empty."
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
        Repeater {
          model: page.s.folders.trash
          Item {
            id: trashRow
            required property var modelData
            width: parent.width
            height: Math.max(trashText.implicitHeight, restoreButton.height)
            Text {
              id: trashText
              anchors.left: parent.left
              anchors.right: restoreButton.left
              anchors.rightMargin: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              wrapMode: Text.WordWrap
              textFormat: Text.PlainText
              text: (String(trashRow.modelData.label || "") || String(trashRow.modelData.id)) +
                    (trashRow.modelData.orphan === true ? "  (a folder no agent used)" : "") +
                    "  ·  removed " + page.when(Number(trashRow.modelData.at)) +
                    (String(trashRow.modelData.problem || "") !== "" ? "  ·  " + trashRow.modelData.problem : "")
              color: page.s.foreground
              font.family: page.s.fontFamily
              font.pixelSize: Style.font.caption
            }
            Button {
              id: restoreButton
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              text: "Restore"
              bordered: true
              focusable: true
              enabled: !page.s.folders.busy && String(trashRow.modelData.problem || "") === ""
              foreground: page.s.foreground
              fontFamily: page.s.fontFamily
              onClicked: page.s.folders.restore(String(trashRow.modelData.name))
            }
          }
        }
      }
    }

    SettingRow {
      width: parent.width
      stacked: true
      visible: page.s.folders.orphans.length > 0
      label: "Folders with no agent"
      hint: "No agent in the settings uses these, so nothing reads them. Usually left by a hand edit of the agent list."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      Column {
        width: parent.width
        spacing: Style.space(4)
        Repeater {
          model: page.s.folders.orphans
          Item {
            id: orphanRow
            required property var modelData
            width: parent.width
            height: Math.max(orphanText.implicitHeight, orphanButtons.height)
            Text {
              id: orphanText
              anchors.left: parent.left
              anchors.right: orphanButtons.left
              anchors.rightMargin: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              elide: Text.ElideRight
              textFormat: Text.PlainText
              text: String(orphanRow.modelData)
              color: page.s.foreground
              font.family: "monospace"
              font.pixelSize: Style.font.caption
            }
            Row {
              id: orphanButtons
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(6)
              Button {
                text: "Open"
                bordered: true
                focusable: true
                foreground: page.s.foreground
                fontFamily: page.s.fontFamily
                onClicked: page.openFolder(page.s.dataHome + "/agentvoice/agents/" + String(orphanRow.modelData))
              }
              DangerButton {
                text: "Move to trash"
                question: "Move it to the trash?"
                confirmText: "Move"
                enabled: !page.s.folders.busy
                foreground: page.s.foreground
                urgent: page.s.urgent
                fontFamily: page.s.fontFamily
                onConfirmed: page.s.folders.trashOrphan(String(orphanRow.modelData))
              }
            }
          }
        }
      }
    }
  }

  // A removal from this page, with the way back.
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
      focusable: true
      enabled: !page.s.folders.busy
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onClicked: page.s.folders.undo()
    }
  }
}
