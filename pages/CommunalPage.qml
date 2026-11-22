import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// What agents share: the communal rules and defaults (Phase 12), the tools
// every agent gets (moved here from the Agents page in M5, bug E; the tools
// found on this machine since M10, `sharedTools`), shared
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
  // controls; each agent's own switch (Agent details since M10) can still
  // say otherwise for itself.
  Column {
    width: parent.width
    spacing: Style.space(12)
    visible: page.tab === "tools"

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: "For every agent. An agent's own switch beats this: those are on Agent details → " +
            "Tools & skills, and each agent's Tools card on the Agents page says what it has."
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

    // --- found on this machine (M10) --------------------------------------------
    // Each MCP server in Claude Code's and Codex's own settings, and each
    // command-line tool Agent Voice looks for, with "on for every agent":
    // `sharedTools`, tool id -> "on:<fingerprint>" or "off". Off until
    // switched on; turning one on shows what it runs first (ToolConfirm) and
    // is written only from its onConfirmed. A personal off always wins.
    Flow {
      width: parent.width
      spacing: Style.space(8)
      topPadding: Style.space(8)
      Text {
        text: "Found on this machine"
        color: page.s.foreground
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
      }
      Button {
        text: toolScan.running ? "Scanning…" : "Rescan"
        focusable: true
        enabled: !toolScan.running
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        fontSize: Style.font.caption
        tooltipText: "Read the MCP servers in Claude Code's and Codex's settings, and look for the " +
                     "command-line tools, again. Reads files only; starts nothing."
        onClicked: page.scanTools(true)
      }
    }
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "On here is on for every agent whose program can use it, unless its own switch on Agent " +
            "details says off. An MCP server is enforced; a command-line tool is told, not enforced " +
            "(the agent is told whether it may use it; a shell can still run anything installed). " +
            "An agent at Trusted uses what it has without asking."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      visible: page.toolError !== "" || (page.toolList !== null && page.toolList.tools.length === 0)
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: page.toolError !== "" ? "Could not look: " + page.toolError
            : "Nothing found: no MCP server in Claude Code's or Codex's settings, and none of the " +
              "command-line tools Agent Voice looks for."
      color: page.toolError !== "" ? page.s.urgent : page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Repeater {
      model: page.toolList ? page.toolList.tools : []
      Column {
        id: shared
        required property var modelData
        width: parent.width
        spacing: Style.space(4)
        readonly property string value: page.sharedValue(modelData.id)
        readonly property bool approved: modelData.fp !== "" && value === "on:" + modelData.fp
        readonly property bool changed: value.indexOf("on:") === 0 && !approved

        ToggleRow {
          width: parent.width
          label: shared.modelData.name + (shared.modelData.kind === "cli" ? " · command-line tool" : " · MCP server")
          hint: !shared.modelData.found ? shared.modelData.name + " is not on PATH."
                : shared.changed ? "Changed since it was turned on, so it is off until it is turned on again."
                : shared.approved ? "On for every agent that can use it, unless its own switch says off."
                : "Off for every agent, unless its own switch says on."
          checked: shared.approved
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onToggled: {
            if (shared.approved) { page.confirmingTool = ""; page.putShared(shared.modelData.id, "off") }
            else if (shared.modelData.found && shared.modelData.fp !== "") page.confirmingTool = shared.modelData.id
          }
        }
        Text {
          width: parent.width
          wrapMode: Text.WrapAnywhere
          textFormat: Text.PlainText
          maximumLineCount: 4
          elide: Text.ElideRight
          text: shared.modelData.defs.map(function(d) {
            return (d.source !== "" ? d.source : d.where) + (d.project !== "" ? " (for " + d.project + ")" : "") +
                   (shared.modelData.kind === "mcp" ? ": " + d.command : "")
          }).join("\n") + (shared.modelData.kind === "mcp"
                            ? "\nFor " + shared.modelData.backends.map(function(b) {
                                return b === "claude" ? "Claude Code" : b === "codex" ? "Codex" : b }).join(" and ") + " agents."
                            : "")
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
        ToolConfirm {
          width: parent.width
          visible: page.confirmingTool === shared.modelData.id
          title: "Turn " + shared.modelData.name + " on for every agent?"
          lines: [
            { label: shared.modelData.kind === "cli" ? "Command" : "Runs",
              value: shared.modelData.defs.map(function(d) { return d.command }).join("\n") },
            { label: "Defined in", value: shared.modelData.defs.map(function(d) {
                return d.source !== "" ? d.source + " (" + d.where + ")" : d.where }).join("\n") },
            { label: "Who gets it",
              value: "Every agent whose program can use it (" + page.told + " now told these), " +
                     "except one whose own switch says off." }
          ]
          warning: "An agent at Trusted " + (shared.modelData.kind === "cli" ? "runs it" : "calls its tools") +
                   " without asking." + (shared.modelData.kind === "mcp"
                     ? " What a tool server returns is outside text: notes and answers are marked so." : "")
          confirmText: "Turn on for every agent"
          foreground: page.s.foreground
          accent: page.s.accent
          urgent: page.s.urgent
          fontFamily: page.s.fontFamily
          onConfirmed: {
            page.putShared(shared.modelData.id, "on:" + shared.modelData.fp)
            page.confirmingTool = ""
          }
          onCancelled: page.confirmingTool = ""
        }
      }
    }
    SettingRow {
      width: parent.width
      stacked: true
      label: "Add a command-line tool by name"
      hint: page.addNote !== "" ? page.addNote
            : "One Agent Voice does not look for. It is listed above, off, once it is found on PATH."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      Flow {
        width: parent.width
        spacing: Style.space(8)
        TextField {
          id: cliName
          width: Math.min(parent.width, Style.space(220))
          placeholderText: "e.g. rclone"
          foreground: page.s.foreground
          font.family: page.s.fontFamily
          onAccepted: page.addCli(text)
        }
        Button {
          text: "Add"
          bordered: true
          focusable: true
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onClicked: page.addCli(cliName.text)
        }
      }
    }
  }

  // The found tools (M10), from `agentvoice tools scan --json`.
  property var toolList: null
  property string toolError: ""
  property string confirmingTool: ""
  property string addNote: ""
  Timer { id: toolDelay; interval: 300; onTriggered: if (page.tab === "tools") page.scanTools(false) }
  Connections {
    target: page.s.store
    function onSaved(key) { if (key === "sharedTools") toolDelay.restart() }
  }
  function scanTools(force) {
    if (toolScan.running) { toolDelay.restart(); return }
    toolScan.command = ["agentvoice", "tools", "scan", "--json"].concat(force ? ["--rescan"] : [])
    toolScan.running = true
  }
  Process {
    id: toolScan
    stdout: StdioCollector {
      onStreamFinished: {
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (!d || !Array.isArray(d.tools)) return
        page.toolError = ""
        page.toolList = d
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t !== "") page.toolError = t.split("\n").pop()
      }
    }
  }
  function sharedValue(id) {
    var m = page.s.setting("sharedTools", {})
    var v = (m && typeof m === "object") ? m[id] : undefined
    return typeof v === "string" ? v : ""
  }
  // One key of sharedTools, the rest as it was.
  function putShared(id, value) {
    var current = page.s.setting("sharedTools", {})
    var all = {}
    if (current && typeof current === "object" && !Array.isArray(current)) {
      var keys = Object.keys(current)
      for (var k = 0; k < keys.length; k++)
        Object.defineProperty(all, keys[k], { value: current[keys[k]], enumerable: true,
                                              writable: true, configurable: true })
    }
    Object.defineProperty(all, id, { value: value, enumerable: true, writable: true, configurable: true })
    page.s.put("sharedTools", all)
  }
  // A CLI by name: written as off, which is how the scan learns to look for
  // it (a "cli:" key in any tools map).
  function addCli(raw) {
    var name = String(raw || "").trim().toLowerCase()
    if (!/^[a-z0-9][a-z0-9._+-]{0,31}$/.test(name)) {
      page.addNote = "A name is letters, digits, dots, dashes, plus or underscore, as you would type it."
      return
    }
    if (page.sharedValue("cli:" + name) !== "") { page.addNote = name + " is listed already."; return }
    page.addNote = ""
    cliName.text = ""
    page.putShared("cli:" + name, "off")
  }

  // --- Skills (Phase 13) ------------------------------------------------------------
  // The shared skills, and which agents get each: since M11 from `skills
  // lanes`, the daemon's own resolution -- every agent whose program can
  // take skills, unless it has its own of the same name or switched it off
  // on its Tools & skills tab -- and how each agent takes them at all.
  property var skillList: null
  property var skillLanes: []
  property string skillError: ""
  readonly property string skillWatch: page.watch + JSON.stringify(s.vAgentFiles) +
                                       JSON.stringify(s.folders.folders)
  onSkillWatchChanged: skillDelay.restart()
  onTabChanged: { if (tab === "skills") loadSkills(); if (tab === "tools") scanTools(false) }
  Component.onCompleted: { if (tab === "skills") loadSkills(); if (tab === "tools") scanTools(false) }
  Timer { id: skillDelay; interval: 250; onTriggered: if (page.tab === "skills") page.loadSkills() }
  function loadSkills() {
    if (skillReader.running) { skillDelay.restart(); return }
    skillReader.running = true
  }
  Process {
    id: skillReader
    command: ["agentvoice", "skills", "lanes", "--json"]
    stdout: StdioCollector {
      onStreamFinished: {
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (!d || !Array.isArray(d.communal) || !Array.isArray(d.lanes)) return
        page.skillError = ""
        page.skillList = d.communal
        page.skillLanes = d.lanes
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t !== "") page.skillError = t.replace(/^agentvoice (agents|skills): /, "").split("\n").pop()
      }
    }
  }
  // Phase M11: each agent, and how it takes the communal skills -- or why
  // it takes none (master plan, M11: "marks each agent whose backend
  // cannot take skills and why").
  function takesLine(l) {
    if (l.delivery === "none")
      return l.program === "endpoint" ? "takes no skills: an endpoint runs nothing on this machine"
             : l.program === "" ? "takes no skills: no program is chosen" : "takes no skills: Agent Voice cannot run " + l.program
    if (l.delivery === "plugin") return "loads each one itself when a request needs it"
    return "is told a list and reads a skill's file when it needs it (" + l.program_label + " cannot load Agent Voice's skills itself)"
  }
  // Who does not get one communal skill, and why.
  function notGiven(skill) {
    var out = []
    for (var i = 0; i < skillLanes.length; i++) {
      var l = skillLanes[i]
      if (!l.enabled || (skill.gets || []).indexOf(l.label) >= 0) continue
      var own = (l.skills || []).some(function(x) { return x.source === l.id && x.name === skill.name })
      out.push(l.label + (l.delivery === "none" ? " (takes no skills)"
                          : own ? " (has its own)" : " (switched off)"))
    }
    return out
  }
  // Phase M12: Communal and each agent's own skills as lanes; a card dragged
  // (Ctrl copies) or sent from its Move to… goes through the SkillMover,
  // which asks first when it widens (into Communal, out of a quarantined
  // agent) and offers Undo.
  function ownSkills(l) { return (l.skills || []).filter(function(x) { return x.source === l.id }) }
  function laneOf(id) {
    if (id === "communal") return page.skillList || []
    var l = page.skillLanes.filter(function(x) { return x.id === id })
    return l.length > 0 ? page.ownSkills(l[0]) : []
  }
  function skillLabel(id) {
    if (id === "communal") return "Communal"
    var l = page.skillLanes.filter(function(x) { return x.id === id })
    return l.length > 0 ? l[0].label : id
  }
  function skillRefusal(p, to) {
    if (!p || !p.name) return "Not a skill."
    if (p.problem !== "") return "It has a problem, so it is not moved until it is fixed: " + p.problem
    if (page.laneOf(to).some(function(x) { return x.name === p.name }))
      return page.skillLabel(to) + " already has a skill named " + p.name + "."
    return ""
  }
  function keepsOwn(name, to) {
    if (to !== "communal") return []
    return page.skillLanes.filter(function(l) {
      return page.ownSkills(l).some(function(x) { return x.name === name })
    }).map(function(l) { return l.id })
  }
  function skillDropped(p, copy, from, to) {
    var why = page.skillRefusal(p, to)
    if (why !== "") { page.skillNote = why; return }
    page.skillNote = ""
    skillMover.request(p.name, from, to, copy, page.keepsOwn(p.name, to))
  }
  readonly property var skillLaneList: [{ id: "communal", label: "Communal",
                                          reason: "Every agent will get it; asks first" }]
                                       .concat(skillLanes.map(function(l) { return { id: l.id, label: l.label } }))

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
            "own skill of the same name gets its own instead, and any agent can switch one off " +
            "on its Tools & skills tab. Drag a card between lanes to move it (hold Ctrl to copy), " +
            "or use its Move to…; Undo is offered for ten seconds."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Repeater {
      model: page.skillLanes
      Text {
        required property var modelData
        width: parent.width
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: modelData.label + (modelData.enabled ? "" : " (switched off)") + " " + page.takesLine(modelData) + "."
        color: modelData.delivery === "none" ? page.s.urgent : page.s.foreground
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
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
    Flow {
      id: communalLanes
      width: parent.width
      visible: page.skillList !== null
      spacing: Style.space(10)
      readonly property real laneWidth: width >= Style.space(760) ? (width - spacing) / 2 : width

      DropLane {
        width: communalLanes.laneWidth
        laneId: "communal"
        title: "Communal"
        subtitle: "Every agent's, unless it has its own of the same name or switches it off."
        count: (page.skillList || []).length
        emptyText: "No shared skills yet. Drag one here from an agent's lane to give it to every agent."
        refuse: function(p, copy, from) { return page.skillRefusal(p, "communal") }
        onReceived: function(p, copy, from) { page.skillDropped(p, copy, from, "communal") }
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        Repeater {
          model: page.skillList || []
          SkillCard {
            required property var modelData
            readonly property var missing: page.notGiven(modelData)
            width: parent.width
            draggable: true
            laneId: "communal"
            payload: ({ name: modelData.name, from: "communal", problem: modelData.problem || "" })
            lanes: page.skillLaneList
            onMoveRequested: function(to, copy) { page.skillDropped(payload, copy, "communal", to) }
            title: modelData.name
            subtitle: modelData.description
            status: modelData.problem !== "" ? "Not given to any agent: " + modelData.problem
                    : "Given to " + ((modelData.gets || []).length > 0 ? modelData.gets.join(", ") : "no agent") +
                      "." + (missing.length > 0 ? " Not to " + missing.join(", ") + "." : "") +
                      (modelData.changed_outside === true ? " Added or changed outside Settings." : "")
            statusUrgent: modelData.problem !== ""
            details: [{ label: "Where", value: modelData.path || "" }]
            foreground: page.s.foreground
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
      }

      Repeater {
        model: page.skillLanes
        DropLane {
          id: agentLane
          required property var modelData
          width: communalLanes.laneWidth
          laneId: modelData.id
          title: modelData.label
          subtitle: "Its own skills folder. Its switches are on its own Tools & skills tab."
          count: page.ownSkills(modelData).length
          emptyText: "No skills of its own."
          refuse: function(p, copy, from) { return page.skillRefusal(p, laneId) }
          onReceived: function(p, copy, from) { page.skillDropped(p, copy, from, laneId) }
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          Repeater {
            model: page.ownSkills(agentLane.modelData)
            SkillCard {
              required property var modelData
              width: parent.width
              draggable: true
              laneId: agentLane.laneId
              payload: ({ name: modelData.name, from: agentLane.laneId, problem: modelData.problem || "" })
              lanes: page.skillLaneList
              onMoveRequested: function(to, copy) { page.skillDropped(payload, copy, agentLane.laneId, to) }
              title: modelData.name
              subtitle: modelData.description
              status: modelData.problem !== "" ? "Not given: " + modelData.problem : ""
              statusUrgent: modelData.problem !== ""
              details: [{ label: "Where", value: modelData.path || "" }]
              foreground: page.s.foreground
              fontFamily: page.s.fontFamily
            }
          }
        }
      }
    }
    SkillMover {
      id: skillMover
      width: parent.width
      labels: {
        var out = { communal: "Communal" }
        page.skillLanes.forEach(function(l) { out[l.id] = l.label })
        return out
      }
      quarantined: page.s.setting("crewQuarantine", [])
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onChanged: { page.s.folders.refresh(); page.loadSkills() }
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
