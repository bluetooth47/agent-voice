import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// What agents share: the communal rules and defaults (Phase 12), the tools
// every agent gets (moved here from the Agents page in M5, bug E), shared
// skills (Phase 13), shared notes (Phase 14) and conversations with more
// than one agent (Phase 15).
//
// The wording follows section 3.5 of the plan: a rule is text every agent
// is told, not a limit the app enforces, and an agent that runs at "Trust
// everything" can change these files itself. What the app does instead is
// make such a change visible, with Keep and Revert.
Column {
  id: page

  required property var s

  spacing: Style.space(16)

  readonly property string folderPath: s.dataHome + "/agentvoice/communal"
  readonly property var folder: s.folders.folders["communal"]
  readonly property string watch: JSON.stringify(s.vAgentFiles["communal"] || {}) +
                                  JSON.stringify(folder || {}) + s.folders.epoch
  // How many agents are told these: the main one and every switched on one.
  readonly property int told: {
    var n = 1
    for (var i = 0; i < s.voiceAgents.length; i++)
      if ((s.voiceAgents[i] || {}).enabled !== false) n++
    return n
  }

  PageHeader {
    width: parent.width
    title: "Communal"
    subtitle: "What every agent is told. Each agent's own role, personality and instructions are on Agent details."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  readonly property string tab: ["tools", "skills", "notes", "chats"].includes(s.communalTab) ? s.communalTab : "rules"
  TabStrip {
    width: parent.width
    options: [{ id: "rules", label: "Rules & defaults" }, { id: "tools", label: "Tools" },
              { id: "skills", label: "Skills" }, { id: "notes", label: "Notes" }, { id: "chats", label: "Chats" }]
    current: page.tab
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
    onPicked: function(id) { page.s.communalTab = id }
  }

  Column {
    width: parent.width
    spacing: Style.space(16)
    visible: page.tab === "rules"

  Text {
    width: parent.width
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: "Told to " + (page.told === 1 ? "your one agent" : "all " + page.told + " agents that are switched on") +
          ", with every request it is sent, before each one's own instructions."
    color: page.s.dim
    font.family: page.s.fontFamily
    font.pixelSize: Style.font.caption
  }

  SettingRow {
    width: parent.width
    stacked: true
    label: "Rules"
    hint: "Every agent is told to follow these. They are instructions, not locks: the app " +
          "does not enforce them."
    help: "Up to 1500 characters, such as “Never send a message or buy anything without asking " +
          "first.” An agent is asked to follow them, and a well-behaved one will, but nothing " +
          "stops one that does not. An agent at “Trust everything” can even change this file " +
          "itself; if anything changes it outside Settings, it shows here with Keep and Revert."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
    FileEditor {
      id: rulesEditor
      target: "communal"
      keeper: page.s.folders
      file: "rules.md"
      limit: 1500
      watch: page.watch
      placeholder: "e.g. Ask before deleting anything."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
    }
  }

  SettingRow {
    width: parent.width
    stacked: true
    label: "Defaults"
    hint: "Every agent is told these too, but where an agent's own instructions say otherwise, " +
          "its own instructions win."
    help: "Up to 1500 characters. For shared preferences, such as “Use metric units” or “Call me " +
          "Sam”, which one agent may still be told differently on its own page."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
    FileEditor {
      id: defaultsEditor
      target: "communal"
      keeper: page.s.folders
      file: "defaults.md"
      limit: 1500
      watch: page.watch
      placeholder: "e.g. Use metric units."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
    }
  }

  Process { id: opener }

  SettingRow {
    width: parent.width
    stacked: true
    label: "Folder"
    hint: "These files can be edited here or by hand; a hand edit applies on each agent's next turn."
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
          enabled: page.folder !== undefined
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onClicked: { opener.command = ["xdg-open", page.folderPath]; opener.running = true }
        }
        Button {
          text: "Export"
          iconText: "\u{f0207}"
          tooltipText: "Copy the rules, defaults and shared skills to a new folder in Downloads"
          bordered: true
          focusable: true
          enabled: page.folder !== undefined && !page.s.folders.busy
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onClicked: page.s.folders.exportFolder("communal")
        }
      }
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
    }
  }
  }

  // --- Tools (plan 12a, 12b; moved here in M5) --------------------------------------
  // What every agent gets on the desktop, whichever program runs it. They
  // were the "On the desktop" group at the foot of the Agents page, which
  // read as settings of the last agent above it (bug E). Same keys, same
  // controls; each agent's Tools card can still say otherwise for itself.
  Column {
    width: parent.width
    spacing: Style.space(12)
    visible: page.tab === "tools"

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: "For every agent. An agent's own switch beats this: each agent's Tools card, on the " +
            "Agents page, says which it has and where that comes from."
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
            "or suspending works only when you said so in that request.\n\n" +
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

  // --- Skills (Phase 13) ------------------------------------------------------------
  // The shared skills, from `agents skills communal`, and which agents get
  // each: every agent whose program can take skills, unless it has its own
  // of the same name.
  property var skillList: null
  property string skillError: ""
  readonly property string skillWatch: page.watch + JSON.stringify(s.vAgentFiles) +
                                       JSON.stringify(s.folders.folders)
  onSkillWatchChanged: skillDelay.restart()
  onTabChanged: if (tab === "skills") loadSkills()
  Component.onCompleted: if (tab === "skills") loadSkills()
  Timer { id: skillDelay; interval: 250; onTriggered: if (page.tab === "skills") page.loadSkills() }
  function loadSkills() {
    if (skillReader.running) { skillDelay.restart(); return }
    skillReader.running = true
  }
  Process {
    id: skillReader
    command: ["agentvoice", "agents", "skills", "communal", "--json"]
    stdout: StdioCollector {
      onStreamFinished: {
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (!Array.isArray(d)) return
        page.skillError = ""
        page.skillList = d
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t !== "") page.skillError = t.replace(/^agentvoice agents: /, "").split("\n").pop()
      }
    }
  }
  property string skillNote: ""
  Process {
    id: skillKeeper
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        page.skillNote = t === "" ? "" : "Not kept: " + t.replace(/^agentvoice agents: /, "").split("\n").pop()
      }
    }
    onRunningChanged: if (!running) { page.s.folders.refresh(); page.loadSkills() }
  }
  function keepSkill(name, stamp) {
    if (skillKeeper.running) return
    skillNote = ""
    skillKeeper.command = ["agentvoice", "agents", "ack", "communal", "skills/" + name + "/SKILL.md"]
                          .concat(stamp ? ["--base", stamp] : [])
    skillKeeper.running = true
  }
  Process {
    id: skillsFolder
    command: ["agentvoice", "agents", "skills-folder", "communal"]
    stdout: StdioCollector {
      onStreamFinished: {
        var path = String(text).trim()
        if (path !== "") { opener.command = ["xdg-open", path]; opener.running = true }
      }
    }
  }
  // Which agents have their own skill of this name (from the folder sizes
  // every page already reads), so the list can say who does not get it.
  function hiddenBy(name) {
    var out = []
    // Only agents that exist: a removed agent's folder may still be read
    // (the trash, an orphan) and must not be named here (Phase 13 review).
    var ids = { "main": true }
    for (var i = 0; i < s.voiceAgents.length; i++) ids[s.agentId(s.voiceAgents[i] || {})] = true
    for (var id in ids) {
      // The overlay's own read (every 3s on this page), else the daemon's.
      var f = s.folders.folders[id] || s.vAgentFiles[id]
      if (((f || {}).files || {})["skills/" + name + "/SKILL.md"]) out.push(labelOf(id))
    }
    return out
  }
  function labelOf(id) {
    if (id === "main") return s.mainLabel
    for (var i = 0; i < s.voiceAgents.length; i++)
      if (s.agentId(s.voiceAgents[i] || {}) === id) return s.agentLabel(s.voiceAgents[i]) || id
    return id
  }

  Column {
    width: parent.width
    spacing: Style.space(10)
    visible: page.tab === "skills"

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: "Given to every agent whose program can take skills: Claude Code loads each one " +
            "itself when a request needs it; Codex, Gemini, Antigravity and Copilot are told a list " +
            "and read a skill's file when they need it; an endpoint gets none. An agent with its " +
            "own skill of the same name gets its own instead."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      visible: page.skillList === null || page.skillError !== ""
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: page.skillError !== "" ? "Could not read the skills: " + page.skillError : "Reading…"
      color: page.skillError !== "" ? page.s.urgent : page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      visible: page.skillList !== null && page.skillList.length === 0
      wrapMode: Text.WordWrap
      text: "No shared skills yet."
      color: page.s.foreground
      font.family: page.s.fontFamily
    }
    Repeater {
      model: page.skillList || []
      SettingRow {
        required property var modelData
        readonly property var hidden: page.hiddenBy(modelData.name)
        width: parent.width
        label: modelData.name
        hint: (modelData.problem !== "" ? "Not given to any agent: " + modelData.problem
               : modelData.description +
                 (hidden.length > 0 ? " Not given to " + hidden.join(", ") + ", which " +
                                      (hidden.length === 1 ? "has its" : "have their") +
                                      " own of the same name." : "")) +
              (modelData.changed_outside === true ? " Added or changed outside Settings." : "")
        foreground: modelData.problem !== "" ? page.s.urgent : page.s.foreground
        fontFamily: page.s.fontFamily
        // Made or edited by hand (a skill always is): Keep saves this
        // version, so the outside-change notice goes (Phase 13).
        Button {
          visible: modelData.changed_outside === true
          text: "Keep"
          focusable: true
          enabled: !skillKeeper.running
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          fontSize: Style.font.caption
          tooltipText: "It applies already. Keep saves this version, so the notice goes."
          onClicked: page.keepSkill(modelData.name, modelData.stamp)
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
            "300 characters), then ---, then the instructions. Scripts beside it are run by each " +
            "agent at its own permission level, never by Agent Voice. Changes apply on each " +
            "agent's next turn."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Button {
      text: "Open the skills folder"
      iconText: "\u{f0770}"
      bordered: true
      focusable: true
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onClicked: skillsFolder.running = true
    }
  }

  // --- Notes (Phase 14) -----------------------------------------------------------
  NotesPanel {
    width: parent.width
    visible: page.tab === "notes"
    target: "communal"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  // --- Chats (Phase 15) -----------------------------------------------------------
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
  readonly property var chats: chatIndex.filter(function(c) {
    return c && Array.isArray(c.participants) && c.participants.length > 1 &&
           /^[0-9a-f]{16}$/.test(String(c.id || ""))
  }).sort(function(a, b) { return (Number(b.updated) || 0) - (Number(a.updated) || 0) })
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
      text: "Agent conversations"
      color: page.s.foreground
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.subtitle
      font.bold: true
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
      text: "No conversations with more than one agent yet."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.body
    }
    Repeater {
      model: page.s.saveChats && page.tab === "chats" ? page.chats : []
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
        Keys.onReturnPressed: page.openChat(String(chatRow.modelData.id))
        Keys.onSpacePressed: page.openChat(String(chatRow.modelData.id))
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
            text: String(chatRow.modelData.title || "Untitled")
            color: page.s.foreground
            font.family: page.s.fontFamily
            font.pixelSize: Style.font.body
          }
          Text {
            width: parent.width
            elide: Text.ElideRight
            textFormat: Text.PlainText
            text: {
              var people = chatRow.modelData.participants.map(function(id) { return page.labelOf(id) })
              var updated = Number(chatRow.modelData.updated) || 0
              return (updated ? Qt.formatDateTime(new Date(updated * 1000), "MMM d, h:mm AP") + " · " : "") +
                     people.join(", ")
            }
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
}
