import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// What every agent shares: the communal rules and defaults (merged plan,
// Phase 12), the shared skills (Phase 13) and the shared notes (Phase 14),
// one tab each. Shared chats join as a tab when they are built (Phase 15).
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

  readonly property string tab: s.communalTab === "skills" || s.communalTab === "notes" ? s.communalTab : "rules"
  TabStrip {
    width: parent.width
    options: [{ id: "rules", label: "Rules & defaults" }, { id: "skills", label: "Skills" },
              { id: "notes", label: "Notes" }]
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
      if (s.agentId(s.voiceAgents[i] || {}) === id) return s.agentLabel(s.voiceAgents[i])
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
}
