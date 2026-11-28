import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// What agents share: the communal rules and defaults (Phase 12), with their
// History and an Import (M15); who takes any of it, `communalOff`, and the
// whole prompt one agent ends up with (M15, Who gets it and Preview); the tools
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
  // How many agents are told these: the main one and every switched on one
  // that has not opted out of Communal (M15).
  readonly property int told: {
    var n = 0
    var all = page.agentList()
    for (var i = 0; i < all.length; i++)
      if (all[i].enabled && page.takes(all[i].id)) n++
    return n
  }

  PageHeader {
    width: parent.width
    title: "Communal"
    subtitle: "What every agent is told. Each agent's own role, personality and instructions are on Agent details."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  readonly property string tab: ["who", "preview", "tools", "skills", "notes", "chats"].includes(s.communalTab)
                                ? s.communalTab : "rules"
  TabStrip {
    width: parent.width
    options: [{ id: "rules", label: "Rules & defaults" }, { id: "who", label: "Who gets it" },
              { id: "preview", label: "Preview" }, { id: "tools", label: "Tools" },
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
    text: (page.told === 0 ? "Told to no agent now: every one has opted out (Who gets it)"
           : "Told to " + (page.told === 1 ? "one agent" : page.told + " agents") +
             " that " + (page.told === 1 ? "is" : "are") + " switched on and take" + (page.told === 1 ? "s" : "") +
             " Communal") +
          ", with every request, before each one's own instructions."
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
    // One column: a SettingRow lays out a single child (M15 found the
    // History drawn over the box in the preview).
    Column {
      width: parent.width
      spacing: Style.space(6)
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
      // M15: every save is a version; view, diff and restore them here.
      FileHistory {
        target: "communal"
        file: "rules.md"
        stamp: rulesEditor.stamp
        outside: rulesEditor.changedOutside
        watch: page.watch
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onRestored: rulesEditor.reload()
      }
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
    // One column: a SettingRow lays out a single child (M15 found the
    // History drawn over the box in the preview).
    Column {
      width: parent.width
      spacing: Style.space(6)
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
      FileHistory {
        target: "communal"
        file: "defaults.md"
        stamp: defaultsEditor.stamp
        outside: defaultsEditor.changedOutside
        watch: page.watch
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onRestored: defaultsEditor.reload()
      }
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
        ActionButton {
          text: "Open folder"
          iconText: "\u{f0770}"
          bordered: true
          focusable: true
          enabled: page.folder !== undefined
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onClicked: { opener.command = ["xdg-open", page.folderPath]; opener.running = true }
        }
        ActionButton {
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
        ActionButton {
          text: page.importing ? "Close import" : "Import…"
          iconText: "\u{f0220}"
          tooltipText: "Bring rules, defaults and skills in from an exported folder: checked first, asked, and undoable"
          bordered: true
          focusable: true
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onClicked: page.importing = !page.importing
        }
      }
      // M15: a dry run, a confirm, one commit, Undo.
      CommunalImport {
        width: parent.width
        visible: page.importing
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onChanged: { page.s.folders.refresh(); page.loadSkills() }
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

  // --- Who gets it (M15) -----------------------------------------------------------------
  // `communalOff`: the agents that take nothing from Communal. Written here
  // alone (tests/test_settings_pages.py). An unreadable list reads as nobody
  // opted out -- the rules may be what keeps an agent careful -- and says so.
  property bool importing: false
  readonly property var communalOffRaw: s.setting("communalOff", [])
  readonly property bool communalOffReadable: {
    var raw = page.communalOffRaw
    if (!Array.isArray(raw) || raw.length > 64) return false
    for (var i = 0; i < raw.length; i++)
      if (typeof raw[i] !== "string" || !/^[a-z0-9][a-z0-9-]{0,47}$/.test(raw[i])) return false
    return true
  }
  function agentList() {
    var out = [{ id: "main", label: s.mainLabel, enabled: true }]
    for (var i = 0; i < s.voiceAgents.length; i++) {
      var a = s.voiceAgents[i] || {}
      var id = s.agentId(a)
      if (id) out.push({ id: id, label: s.agentLabel(a) || id, enabled: a.enabled !== false })
    }
    return out
  }
  function takes(id) { return !page.communalOffReadable || page.communalOffRaw.indexOf(id) < 0 }
  // The new list: what is there now (ids of agents that still exist, so a
  // removed agent's id never opts out a new one that takes its id), with
  // `id` added or taken out.
  function setTakes(id, on) {
    var known = page.agentList().map(function(a) { return a.id })
    var list = (page.communalOffReadable ? page.communalOffRaw : []).filter(function(x) {
      return known.indexOf(x) >= 0 && x !== id
    })
    if (!on) list.push(id)
    s.put("communalOff", list)
  }
  property string freshNote: ""
  Process {
    id: freshStarter
    property string who: ""
    property string err: ""
    property bool started: false
    onStarted: started = true
    stderr: StdioCollector { onStreamFinished: freshStarter.err = String(text).trim() }
    onRunningChanged: if (!running) {
      page.freshNote = !freshStarter.started ? "Not started: the agentvoice command could not be run."
                     : freshStarter.err !== "" ? "Not started: " + freshStarter.err.split("\n").pop()
                     : freshStarter.who + " starts a new conversation on its next request."
    }
  }
  function startFresh(id, label) {
    if (freshStarter.running) return
    freshNote = ""
    freshStarter.who = label
    freshStarter.err = ""
    freshStarter.started = false
    freshStarter.command = ["agentvoice", "chats", "new", id]
    freshStarter.running = true
  }

  Column {
    objectName: "communalWho"
    width: parent.width
    spacing: Style.space(10)
    visible: page.tab === "who"

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "An agent switched on here is told the communal rules and defaults with every request " +
            "and given the communal skills. Switched off, it is told none of them and given none; " +
            "its own role, personality, instructions, skills and notes are unchanged."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      visible: !page.communalOffReadable
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "The list of agents that opted out cannot be read, so every agent takes Communal. " +
            "Switching one below writes a fresh list."
      color: page.s.urgent
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Repeater {
      model: page.agentList()
      Column {
        required property var modelData
        width: parent.width
        spacing: Style.space(4)
        readonly property bool on: page.takes(modelData.id)
        ToggleRow {
          width: parent.width
          label: modelData.label + (modelData.enabled ? "" : " (switched off)")
          hint: parent.on ? "Told the communal rules and defaults; given the communal skills."
                          : "Told nothing from Communal, and given no communal skill."
          help: "Read on the agent's next request; an idle agent's process is let go so it starts " +
                "with the change. A conversation already under way keeps what it was told before: " +
                "text already sent cannot be recalled, which is what Start fresh is for."
          checked: parent.on
          changed: !parent.on
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onToggled: page.setTakes(modelData.id, !checked)
          onReset: page.setTakes(modelData.id, true)
        }
        Row {
          visible: !parent.on
          spacing: Style.space(8)
          leftPadding: Style.space(10)
          Text {
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(implicitWidth, page.width - freshButton.width - Style.space(40))
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
            text: "Its current conversation may still hold what it was told before."
            color: page.s.dim
            font.family: page.s.fontFamily
            font.pixelSize: Style.font.caption
          }
          ActionButton {
            id: freshButton
            text: "Start fresh"
            tooltipText: "Its next request begins a new conversation; this one stays in Chats"
            bordered: true
            focusable: true
            enabled: !freshStarter.running
            foreground: page.s.foreground
            fontFamily: page.s.fontFamily
            onClicked: page.startFresh(modelData.id, modelData.label)
          }
        }
      }
    }
    Text {
      width: parent.width
      visible: page.freshNote !== ""
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: page.freshNote
      color: page.freshNote.indexOf("Not ") === 0 ? page.s.urgent : page.s.foreground
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "Communal notes stay reachable through the notes tools whatever is switched here: " +
            "they are information an agent looks up when it needs it, not instructions it is told. " +
            "Quarantine on the Crew map is what keeps an agent from writing them."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  // --- Preview (M15) ----------------------------------------------------------------------
  // One agent's whole prompt, piece by piece, from `agentvoice agents prompt`:
  // its adapter's own builder over what the daemon hands it, so what is
  // shown is what is sent.
  property string previewAgent: "main"
  property var promptView: null
  property string promptError: ""
  readonly property string promptWatch: page.watch + JSON.stringify(s.vAgentFiles) +
                                        JSON.stringify(page.communalOffRaw) + s.folders.epoch
  onPromptWatchChanged: if (page.tab === "preview") promptDelay.restart()
  Timer { id: promptDelay; interval: 300; onTriggered: page.loadPrompt() }
  function loadPrompt() {
    if (prompter.running) { promptDelay.restart(); return }
    prompter.forAgent = page.previewAgent
    prompter.command = ["agentvoice", "agents", "prompt", page.previewAgent, "--json"]
    prompter.running = true
  }
  Process {
    id: prompter
    property string forAgent: ""
    stdout: StdioCollector {
      onStreamFinished: {
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (!d || !Array.isArray(d.pieces) || prompter.forAgent !== page.previewAgent) return
        page.promptError = ""
        page.promptView = d
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t !== "" && prompter.forAgent === page.previewAgent)
          page.promptError = t.replace(/^agentvoice agents: /, "").split("\n").pop()
      }
    }
  }
  Connections {
    target: page.s.store
    function onSaved(key) { if (page.tab === "preview") promptDelay.restart() }
  }

  Column {
    width: parent.width
    spacing: Style.space(10)
    visible: page.tab === "preview"

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "Everything one agent is sent ahead of each request, in the order it is sent, built " +
            "the way its program builds it. Pick an agent."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    AgentTabs {
      width: parent.width
      agents: page.agentList().map(function(a) { return { id: a.id, label: a.label, tone: page.takes(a.id) ? "active" : "idle" } })
      current: page.previewAgent
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onPicked: function(id) { page.previewAgent = id; page.promptView = null; page.loadPrompt() }
    }
    Text {
      width: parent.width
      visible: page.promptView !== null
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: page.promptView === null ? "" :
            page.promptView.total + " characters in all (about " + Math.round(page.promptView.total / 4) +
            " tokens), sent with every request · " + page.promptView.program_label +
            (page.promptView.takes_communal ? "" : " · takes nothing from Communal") +
            (page.promptView.runs ? "" : " · Agent Voice cannot run this program, so it is sent nothing")
      color: page.s.foreground
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.bodySmall
    }
    PromptPreview {
      width: parent.width
      parts: page.promptView === null ? [] :
             page.promptView.pieces.map(function(x) {
               return { label: x.label, from: x.source, text: x.text, how: x.precedence, chars: x.chars }
             }).concat((page.promptView.beside || []).map(function(x) {
               return { label: x.label, from: x.source, text: "", note: x.note }
             }))
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
    }
    Text {
      width: parent.width
      visible: page.promptView === null && page.promptError === ""
      text: prompter.running ? "Reading…" : ""
      textFormat: Text.PlainText
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      visible: page.promptError !== ""
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "Could not show it: " + page.promptError
      color: page.s.urgent
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
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
      objectName: "set-desktopTools"
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
      objectName: "set-browserTools"
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
      objectName: "set-omarchySkill"
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

    ToggleRow {
      objectName: "set-agentvoiceSkill"
      width: parent.width
      label: "Agent Voice skill"
      hint: "Agents can look up how Agent Voice works (its spoken commands, wake phrases and " +
            "settings) instead of guessing. It explains; it starts nothing."
      help: "Built from the daemon's own tables, so it matches what is installed, and built " +
            "again when a command, a wake phrase or a setting changes. Claude Code loads it " +
            "as a skill for the voice session only; Codex, Gemini, Antigravity and Copilot " +
            "are told one line saying where to read it. Endpoints get nothing. It never " +
            "teaches an agent to answer a permission question or change a setting: those " +
            "stay yours."
      checked: page.s.setting("agentvoiceSkill", true) === true
      changed: page.s.changed("agentvoiceSkill")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("agentvoiceSkill", !checked)
      onReset: page.s.resetKey("agentvoiceSkill")
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
      ActionButton {
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
      objectName: "sharedToolsList"
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
        ActionButton {
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

  // --- Skills (Phase 13; a grouping since M31) -------------------------------------
  // Every skill an agent has, who has it, and which are communal, from
  // `skills communal`, the daemon's own reading (skillscan.grouping). A skill
  // every agent that takes skills already has is communal by itself;
  // `communalSkills` adds others and keeps one out of that rule. Communal
  // gives nobody a copy and withholds nothing: each agent's Exclude, on its
  // own Tools & skills tab, is what does that.
  property var skillRows: null
  property var skillAgents: []
  property bool skillsReadable: true
  property string skillError: ""
  property string skillQuery: ""
  readonly property string skillWatch: page.watch + JSON.stringify(s.vAgentFiles) +
                                       JSON.stringify(s.folders.folders)
  onSkillWatchChanged: skillDelay.restart()
  onTabChanged: { if (tab === "skills") loadSkills(); if (tab === "tools") scanTools(false)
                 if (tab === "preview") loadPrompt() }
  Component.onCompleted: { if (tab === "skills") loadSkills(); if (tab === "tools") scanTools(false)
                           if (tab === "preview") loadPrompt() }
  Timer { id: skillDelay; interval: 250; onTriggered: if (page.tab === "skills") page.loadSkills() }
  function loadSkills() {
    if (skillReader.running) { skillDelay.restart(); return }
    skillReader.running = true
  }
  Process {
    id: skillReader
    command: ["agentvoice", "skills", "communal", "--json"]
    stdout: StdioCollector {
      onStreamFinished: {
        var d
        try { d = JSON.parse(String(text)) } catch (e) { return }
        if (!d || !Array.isArray(d.rows) || !Array.isArray(d.agents)) return
        page.skillError = ""
        page.skillRows = d.rows
        page.skillAgents = d.agents
        page.skillsReadable = d.readable !== false
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        var t = String(text).trim()
        if (t !== "") page.skillError = t.replace(/^agentvoice (agents|skills): /, "").split("\n").pop()
      }
    }
  }
  // The command reads shell.json from disk, which the store writes a moment
  // after the page shows a change: read again once a save has landed.
  Connections {
    target: page.s.store
    function onSaved(key) { if (page.tab === "skills") skillDelay.restart() }
  }
  readonly property var communalRows: (skillRows || []).filter(function(r) { return r.communal === true })
  readonly property var shownRows: {
    var q = page.skillQuery.trim().toLowerCase()
    var all = skillRows || []
    if (q === "") return all
    return all.filter(function(r) {
      return String(r.name).toLowerCase().indexOf(q) >= 0 ||
             String(r.description || "").toLowerCase().indexOf(q) >= 0
    })
  }
  // An agent that cannot be part of Communal at all, and why: it takes no
  // skills, or it takes nothing from Communal (master plan, M11: "marks
  // each agent whose backend cannot take skills and why").
  function outsideLine(l) {
    if (l.delivery === "none")
      return l.label + " takes no skills: " + (l.program === "endpoint" ? "an endpoint runs nothing on this machine"
             : l.program === "" ? "no program is chosen" : "Agent Voice cannot run " + l.program) + "."
    if (l.takes_communal === false)
      return l.label + " takes nothing from Communal (Who gets it), so it is left out here and keeps its skills as its own."
    return ""
  }
  function joinNames(xs) {
    if (xs.length <= 1) return xs.join("")
    return xs.slice(0, -1).join(", ") + " and " + xs[xs.length - 1]
  }
  // Who does not have a skill, grouped by why: "Theo and Sora (Claude Code
  // has no skill of this name); Hazel (takes no skills)".
  function lacksText(lacks) {
    var whys = [], who = {}
    for (var i = 0; i < lacks.length; i++) {
      if (!(lacks[i].why in who)) { who[lacks[i].why] = []; whys.push(lacks[i].why) }
      who[lacks[i].why].push(lacks[i].label)
    }
    return whys.map(function(w) {
      var n = who[w]
      return (n.length <= 1 ? n.join("") : n.slice(0, -1).join(", ") + " or " + n[n.length - 1]) + " (" + w + ")"
    }).join("; ")
  }
  // Who has a skill, who does not and why, and who excluded it.
  function rowStatus(r) {
    var has = r.has || [], lacks = r.lacks || [], excl = r.excluded || []
    var out = has.length === 0 ? "No agent has it now."
              : (lacks.length === 0 ? "Every agent has it: " : "Has it: ") + page.joinNames(has) + "."
    if (lacks.length > 0) out += " Not " + page.lacksText(lacks) + "."
    if (excl.length > 0) out += " Excluded by " + page.joinNames(excl) + "."
    if (r.problem) out += " " + r.problem
    return out
  }
  // `communalSkills` with one name added to or taken out of Communal, or
  // null when what is there cannot be read (then nothing is written over
  // it). Out of Communal, a skill every agent has goes on "remove", so the
  // automatic rule leaves it out until it is added back; into Communal it
  // comes off "remove", and goes on "add" unless every agent has it.
  function communalEdited(cur, name, on, auto) {
    var re = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}(:[A-Za-z0-9][A-Za-z0-9._-]{0,63})?$/
    if (!re.test(String(name)) || (on !== true && on !== false)) return null
    if (cur === undefined || cur === null) cur = {}
    if (typeof cur !== "object" || Array.isArray(cur)) return null
    var keys = Object.keys(cur)
    for (var k = 0; k < keys.length; k++) if (keys[k] !== "add" && keys[k] !== "remove") return null
    function names(v) {
      if (v === undefined || v === null) return []
      if (!Array.isArray(v) || v.length > 256) return null
      var out = []
      for (var i = 0; i < v.length; i++) {
        if (typeof v[i] !== "string" || !re.test(v[i])) return null
        if (out.indexOf(v[i]) < 0) out.push(v[i])
      }
      return out
    }
    var add = names(cur.add), remove = names(cur.remove)
    if (add === null || remove === null) return null
    for (var j = 0; j < add.length; j++) if (remove.indexOf(add[j]) >= 0) return null
    add = add.filter(function(n) { return n !== name })
    remove = remove.filter(function(n) { return n !== name })
    if (on && auto !== true) add.push(name)
    if (!on && auto === true) remove.push(name)
    if (add.length > 256 || remove.length > 256) return null
    return { add: add, remove: remove }
  }
  // The question before a change, under the card it was asked from: one
  // name in one list at a time (a communal skill is in both).
  property string skillAsking: ""
  property string skillAskingIn: ""
  property bool skillAskingOn: false
  function askCommunal(r, on, list) {
    page.skillNote = ""
    if (!page.skillsReadable) {
      page.skillNote = "Not changed: which skills are communal cannot be read. Fix or remove communalSkills in shell.json."
      return
    }
    page.skillAskingOn = on
    page.skillAskingIn = list
    page.skillAsking = r.name
  }
  // Written only from the confirm's onConfirmed (tests/test_communal_skills.py).
  function setCommunal(r, on) {
    page.skillAsking = ""
    var next = page.communalEdited(page.s.setting("communalSkills", {}), r.name, on, r.auto === true)
    if (next === null) {
      page.skillNote = "Not changed: which skills are communal cannot be read. Fix or remove communalSkills in shell.json."
      return
    }
    page.s.put("communalSkills", next)
  }
  function confirmLines(r, on) {
    if (on) {
      var lacks = r.lacks || []
      return [{ label: "Who has it", value: (r.has || []).length > 0 ? page.joinNames(r.has) : "No agent has it now" },
              { label: "Who doesn't", value: lacks.length > 0 ? page.lacksText(lacks) : "Every agent has it" },
              { label: "What changes", value: "It is listed under From communal for each agent that has " +
                "it, where each can exclude it. No agent is given a copy it does not have already." }]
    }
    return [{ label: "What changes", value: "It goes back to each agent's own skills, still on wherever " +
              "it was on. Nothing is switched off." +
              (r.auto === true ? " Every agent has it, so it stays out of Communal until you add it back." : "") }]
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

  Column {
    objectName: "communalSkills"
    width: parent.width
    spacing: Style.space(10)
    visible: page.tab === "skills"

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: "A communal skill is one the agents share. Nothing is copied: an agent whose program " +
            "does not have it does not get it, and each skill says who that is. A skill every agent " +
            "already has is communal by itself. Each agent can exclude a communal skill on its own " +
            "Tools & skills tab."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Repeater {
      model: page.skillAgents.filter(function(l) { return page.outsideLine(l) !== "" })
      Text {
        required property var modelData
        width: parent.width
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: page.outsideLine(modelData)
        color: modelData.delivery === "none" ? page.s.urgent : page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
    Text {
      width: parent.width
      visible: page.skillRows === null || page.skillError !== ""
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: page.skillError !== "" ? "Could not read the skills: " + page.skillError : "Reading…"
      color: page.skillError !== "" ? page.s.urgent : page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      visible: page.skillRows !== null && !page.skillsReadable
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "Which skills are communal cannot be read (communalSkills in shell.json), so only the " +
            "ones every agent has are shown as communal, and nothing here can be changed until it is " +
            "fixed or removed. Nobody is given or denied a skill because of it."
      color: page.s.urgent
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    Card {
      objectName: "communalList"
      width: parent.width
      visible: page.skillRows !== null
      title: "Communal skills" + (page.communalRows.length > 0 ? " · " + page.communalRows.length : "")
      subtitle: "Shared by every agent that has them."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      Text {
        width: parent.width
        visible: page.communalRows.length === 0
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: "None yet. Switch one on under All skills; a skill every agent has is communal by itself."
        color: page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      Repeater {
        model: page.communalRows
        Column {
          required property var modelData
          width: parent.width
          spacing: Style.space(6)
          SkillCard {
            width: parent.width
            title: modelData.name
            subtitle: modelData.description
            badge: modelData.added === true ? "added" : "every agent has it"
            status: page.rowStatus(modelData)
            statusUrgent: modelData.problem !== ""
            details: [{ label: "Found in", value: (modelData.sources || []).join(", ") || "nowhere now" }]
                     .concat(modelData.path ? [{ label: "Where", value: modelData.path }] : [])
            foreground: page.s.foreground
            fontFamily: page.s.fontFamily
            ActionButton {
              text: "Remove…"
              bordered: true
              focusable: true
              enabled: page.skillsReadable
              foreground: page.s.foreground
              fontFamily: page.s.fontFamily
              fontSize: Style.font.caption
              tooltipText: "Take it out of Communal, after asking. Each agent keeps it as its own."
              onClicked: page.askCommunal(modelData, false, "communal")
            }
            // Made or edited by hand (a skill always is): Keep saves this
            // version, so the outside-change notice goes (Phase 13).
            ActionButton {
              visible: modelData.folder === true && modelData.changed_outside === true
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
          ToolConfirm {
            visible: page.skillAsking === modelData.name && page.skillAskingIn === "communal"
            title: "Remove " + modelData.name + " from Communal?"
            lines: page.confirmLines(modelData, false)
            confirmText: "Remove"
            foreground: page.s.foreground
            fontFamily: page.s.fontFamily
            onConfirmed: page.setCommunal(modelData, false)
            onCancelled: page.skillAsking = ""
          }
        }
      }
    }

    Card {
      objectName: "allSkills"
      width: parent.width
      visible: page.skillRows !== null
      title: "All skills" + ((page.skillRows || []).length > 0
                             ? " · " + (page.skillQuery.trim() !== "" ? page.shownRows.length + " of " : "") +
                               page.skillRows.length : "")
      subtitle: "Every skill any agent has, with a switch for Communal."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      SearchField {
        width: parent.width
        placeholder: "Search skills"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onSearched: function(t) { page.skillQuery = t }
      }
      Text {
        width: parent.width
        visible: page.shownRows.length === 0
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: page.skillQuery.trim() !== "" ? "No skill matches “" + page.skillQuery.trim() + "”."
                                           : "No agent has any skill."
        color: page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      Repeater {
        model: page.shownRows
        Column {
          required property var modelData
          width: parent.width
          spacing: Style.space(6)
          SkillCard {
            width: parent.width
            title: modelData.name
            subtitle: modelData.description
            // One place, and how many more: a long badge squeezes the name.
            badge: (modelData.sources || []).length > 1 ? modelData.sources[0] + " +" + (modelData.sources.length - 1)
                                                         : (modelData.sources || []).join("")
            status: page.rowStatus(modelData)
            statusUrgent: modelData.problem !== ""
            details: [{ label: "Found in", value: (modelData.sources || []).join(", ") || "nowhere now" }]
                     .concat(modelData.path ? [{ label: "Where", value: modelData.path }] : [])
            switchable: page.skillsReadable
            checked: modelData.communal === true
            switchTooltip: modelData.communal === true ? "In Communal. Switch off to take it out, after asking."
                                                       : "Not in Communal. Switch on to add it, after asking."
            foreground: page.s.foreground
            fontFamily: page.s.fontFamily
            onToggled: function(on) { page.askCommunal(modelData, on, "all") }
          }
          ToolConfirm {
            visible: page.skillAsking === modelData.name && page.skillAskingIn === "all"
            title: page.skillAskingOn ? "Add " + modelData.name + " to Communal?"
                                      : "Remove " + modelData.name + " from Communal?"
            lines: page.confirmLines(modelData, page.skillAskingOn)
            confirmText: page.skillAskingOn ? "Add to Communal" : "Remove"
            foreground: page.s.foreground
            fontFamily: page.s.fontFamily
            onConfirmed: page.setCommunal(modelData, page.skillAskingOn)
            onCancelled: page.skillAsking = ""
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
      text: "Agent Voice's communal skills folder is separate: a skill kept there is given to every " +
            "agent that takes Communal. A skill is a folder holding SKILL.md, which starts with a line " +
            "of ---, then “name:” (the folder's name) and “description:” (one line on when to use it, " +
            "at most 300 characters), then ---, then the instructions. Scripts beside it are run by each " +
            "agent at its own permission level, never by Agent Voice."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    ActionButton {
      text: "Open the communal skills folder"
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
    // Phase M13: every agent's notes are lanes here too; one opens on that
    // agent's own Notes tab.
    onOpenElsewhere: function(id) { page.s.goTo("agentdetails", id, "notes") }
  }

  // --- Chats (Phase 15) -----------------------------------------------------------
  // Conversations more than one agent spoke in: the Chats page's browser
  // (Chats.qml), shown for those alone (phase M18).
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
            "on the Chats page."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.body
    }
    ActionButton {
      visible: !page.s.saveChats
      text: "Go to Chats →"
      focusable: true
      bordered: true
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onClicked: page.s.goTo("chats", "")
    }
    Chats {
      width: parent.width
      height: Math.max(Style.space(420), (page.s.pageScroll ? page.s.pageScroll.height : Style.space(600))
                                         - Style.space(80))
      visible: page.tab === "chats"
      s: page.s
      scope: "multi"
      showSession: false
    }
  }
}
