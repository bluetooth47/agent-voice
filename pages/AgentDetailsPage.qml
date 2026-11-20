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
  // the page and coming back finds the same agent.
  readonly property var choices: {
    var out = [{ label: s.mainLabel + "  (main)", value: "main" }]
    for (var i = 0; i < s.voiceAgents.length; i++) {
      var a = s.voiceAgents[i] || {}
      var id = s.agentId(a)
      if (id === "") continue
      out.push({ label: (s.agentLabel(a) || id) + (a.enabled === false ? "  (switched off)" : ""), value: id })
    }
    return out
  }
  readonly property string target: {
    for (var i = 0; i < choices.length; i++) if (choices[i].value === s.detailsAgent) return s.detailsAgent
    return "main"
  }
  readonly property bool isMain: target === "main"
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
  readonly property var folder: s.folders.folders[target]
  readonly property bool folderMissing: s.folders.foldersRead && folder === undefined

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

  property string tab: s.detailsTab
  readonly property var tabs: [
    { id: "prompt", label: "Personality & instructions" },
    { id: "tools", label: "Tools & skills" },
    { id: "chats", label: "Chats" },
    { id: "advanced", label: "Advanced" }
  ]
  function pickTab(id) { s.detailsTab = id; page.tab = id }

  PageHeader {
    width: parent.width
    title: "Agent details"
    subtitle: "What each agent is for, who it is and what it is told. Its voice, program and " +
              "permission are on the Agents page."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  Dropdown {
    width: parent.width
    showLabel: false
    options: page.choices
    value: page.target
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
    onChanged: function(v) { page.s.detailsAgent = v }
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

  // An agent with no folder: the files below cannot be saved until it has
  // one. The daemon makes any missing folder when it starts, too.
  Row {
    visible: page.folderMissing
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

    SettingRow {
      width: parent.width
      stacked: true
      label: "Role"
      hint: "What " + page.name + " is for, and when to pass it work. The other agents are told " +
            "this about it; " + page.name + " is not."
      help: "One or two lines, up to 300 characters, such as “Quick answers and lookups; hand " +
            "anything that needs code to Theo.” Every other agent sees it in its list of agents " +
            "here, as information about " + page.name + ", never as instructions to follow."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      FileEditor {
        id: roleEditor
        target: page.target
        file: "role.md"
        limit: 300
        minHeight: Style.space(48)
        watch: page.watch
        placeholder: "e.g. Quick answers and lookups."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
    }

    SettingRow {
      width: parent.width
      stacked: true
      label: "Personality"
      hint: "Who " + page.name + " is: manner, tone, how it talks. Told to it on every turn."
      help: "Up to 1500 characters, told to " + page.name + " under “About you”. For what it " +
            "should do or remember, use its instructions below; for how it sounds, its voice is on " +
            "the Agents page.\n\nA change is told to it from its next turn, but a conversation " +
            "already under way keeps its history, and it may go on answering as it has been. A new " +
            "conversation starts with the change."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      FileEditor {
        id: personalityEditor
        target: page.target
        file: "personality.md"
        limit: 1500
        watch: page.watch
        placeholder: "e.g. Warm and a little dry. Speaks plainly, never gushes."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }
    }

    SettingRow {
      width: parent.width
      stacked: true
      label: "Standing instructions"
      hint: "What " + page.name + " should always do or keep in mind. Changing them keeps the conversation."
      help: "How to address you, what to keep in mind, how long to talk. They sit after the " +
            "rule that replies are spoken, so asking for lists or code blocks will still be read out " +
            "as speech. Up to 2000 characters."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      // The old setting (`agentInstructions`, or the entry's `instructions`)
      // only until instructions.md exists (Phase 10).
      FileEditor {
        id: instructionsEditor
        target: page.target
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
        text: "In this order, at the start of every conversation. Its own request comes after."
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

  property var previewParts: []
  property string previewError: ""
  readonly property string previewWatch: page.watch + roleEditor.stamp + personalityEditor.stamp +
                                         instructionsEditor.stamp +
                                         JSON.stringify(s.vAgentFiles["communal"] || {}) +
                                         JSON.stringify(s.folders.folders["communal"] || {})
  onPreviewWatchChanged: previewDelay.restart()
  onTargetChanged: { previewParts = []; confirmRemove = false; loadPreview() }
  Component.onCompleted: loadPreview()
  Timer { id: previewDelay; interval: 250; onTriggered: page.loadPreview() }

  // A source path, in words.
  function fromWords(source) {
    var src = String(source || "")
    if (src === "built in") return "Built in"
    if (src === "communal/rules.md") return "From Communal · rules"
    if (src === "communal/defaults.md") return "From Communal · defaults"
    if (src === "each agent's role.md") return "From each other agent's role"
    var m = src.match(/^agents\/[^\/]+\/(personality|instructions)\.md$/)
    if (m) return "From " + page.name + "'s " + m[1]
    return src
  }
  function loadPreview() {
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
            note: label.indexOf("Omarchy commands") === 0
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
  // What it can use, worked out from the program and the switches on the
  // Agents page. Per-agent switches come later (merged plan, Phase 13).
  Column {
    id: toolsTab
    width: parent.width
    spacing: Style.space(10)
    visible: page.tab === "tools"

    readonly property bool claude: page.program === "claude"
    readonly property bool mcp: page.program === "claude" || page.program === "codex"
    readonly property bool endpoint: page.program === "endpoint"

    Repeater {
      model: [
        { label: "Desktop tools",
          state: toolsTab.endpoint ? "No: an endpoint runs nothing on this machine."
               : !toolsTab.mcp ? "No: " + page.s.programLabel(page.program) + " cannot take them."
               : page.s.setting("desktopTools", false) === true ? "On" : "Off" },
        { label: "Browser",
          state: toolsTab.endpoint ? "No: an endpoint runs nothing on this machine."
               : !toolsTab.claude ? "No: only Claude Code agents can use Claude in Chrome."
               : page.s.setting("browserTools", false) === true ? "On" : "Off" },
        { label: "Omarchy commands",
          state: toolsTab.endpoint ? "No: an endpoint runs nothing on this machine."
               : page.s.setting("omarchySkill", true) !== true ? "Off"
               : toolsTab.claude ? "On, as a skill" : "On, in what it is told" }
      ]
      SettingRow {
        required property var modelData
        width: parent.width
        label: modelData.label
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        Text {
          text: modelData.state
          textFormat: Text.PlainText
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: "These follow the switches at the foot of the Agents page, which apply to every agent " +
            "that can use them."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Button {
      text: "Change on Agents page →"
      focusable: true
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      fontSize: Style.font.caption
      onClicked: page.s.goTo("agents", "")
    }
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      readonly property var skills: {
        var out = []
        var files = (page.folder || {}).files || {}
        for (var k in files) {
          var m = k.match(/^skills\/([^\/]+)\/SKILL\.md$/)
          if (m) out.push(m[1])
        }
        return out
      }
      text: skills.length === 0
            ? "No skills in " + page.name + "'s folder."
            : "In " + page.name + "'s folder: " + skills.join(", ") + ". Skills in agent folders are " +
              "not given to agents yet."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  // --- Chats ------------------------------------------------------------------------
  // This agent's saved chats, from the same index the conversation view reads.
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
    var want = isMain ? "" : target
    var out = []
    for (var i = 0; i < chatIndex.length; i++) {
      var c = chatIndex[i] || {}
      if (/^[0-9a-f]{16}$/.test(String(c.id || "")) && String(c.agent_id || "") === want) out.push(c)
    }
    out.sort(function(a, b) { return (Number(b.updated) || 0) - (Number(a.updated) || 0) })
    return out
  }
  function openChat(id) {
    s.openChat = ""
    s.openChat = id
    s.showPage("history")
  }

  Column {
    width: parent.width
    spacing: Style.space(6)
    visible: page.tab === "chats"

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
          }
          Text {
            width: parent.width
            visible: text !== ""
            elide: Text.ElideRight
            textFormat: Text.PlainText
            text: String(chatRow.modelData.preview || "")
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
  property bool confirmRemove: false
  Timer { id: removeTimeout; interval: 4000; onTriggered: page.confirmRemove = false }
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
          Button {
            visible: !page.isMain && page.index >= 0
            text: page.confirmRemove ? "Remove " + page.name + "?" : "Remove"
            iconText: "\u{f0a7a}"
            bordered: true
            focusable: true
            enabled: !page.s.folders.busy
            foreground: page.confirmRemove ? page.s.urgent : page.s.foreground
            fontFamily: page.s.fontFamily
            onClicked: {
              if (!page.confirmRemove) { page.confirmRemove = true; removeTimeout.restart(); return }
              page.confirmRemove = false
              page.s.folders.remove(page.index)
            }
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
              Button {
                text: "Move to trash"
                bordered: true
                focusable: true
                enabled: !page.s.folders.busy
                foreground: page.s.foreground
                fontFamily: page.s.fontFamily
                onClicked: page.s.folders.trashOrphan(String(orphanRow.modelData))
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
