import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// One agent's tool switches (merged plan, Phase 13) and its collaboration
// rows (Phases 14 and 16), drawn as one of two cards on the Agents page
// (master plan M5): `part: "tools"` or `part: "collab"`. Both halves share
// the tables below, which is why they are one piece.
//
// Tools: what the agent has of the desktop tools, the browser and the
// Omarchy commands, *and where that comes from* -- an inherited "off" is the
// setting for every agent (Communal → Tools), not a missing control -- and
// how many tools found on this machine are switched on for it. Read only
// since M10: an agent's own switches live on Agent details → Tools & skills
// (the one writer, `s.setAgentTool`), which `detailsAsked` opens.
//
// A tool this agent's program cannot use stays visible as a disabled chip
// that says why: a control that does nothing must say why. Which programs
// can use which tool is the table in daemon/agentfs.py (DESKTOP_PROGRAMS and
// the rest); test_tools_skills.py holds this copy to it.
//
//   ToolSwitches {
//     part: "tools"                        // or "collab"
//     choices: entry.tools || {}           // key -> "inherit" | "on" | "off"
//     globals: { desktop: true, browser: false, omarchySkill: true }
//     shared: s.setting("sharedTools", {})   // the found tools for every agent (M10)
//     program: "claude"
//     onDetailsAsked: s.goTo("agentdetails", agentId, "tools")
//     onSharedAsked: s.goTo("communal", "", "tools")
//     notesWrite: entry.notesWrite || "allow"   // "allow" | "deny" (Phase 14)
//     onNotesPicked: function(value) { ... }
//     collaboration: entry.collaboration === undefined ? "announce" : String(entry.collaboration)
//     onCollaborationPicked: function(value) { ... }
//     acceptsWork: entry.acceptsWork !== false
//     onAcceptsWorkPicked: function(value) { ... }
//     chatSearch: entry.chatSearch === undefined ? "own" : String(entry.chatSearch)
//     agentLabel: "Theo"
//     quarantined: false                   // or "unreadable"
//     chatsSaved: true
//     onChatSearchPicked: function(value) { ... }   // "all" only after the question
//   }
//
// Notes (Phase 14): whether this agent may write its own and the communal
// notes through Agent Voice's notes tools. Reading is always allowed. Only
// Claude Code and Codex take the notes tools. Collaboration (Phase 16) sets
// what an agent can start with other agents and whether it takes work from
// them. Chat search (master plan M20): which saved chats its chat tools may
// find and read -- none, its own and the ones shared with it, or every one.
// "Every chat" widens what it reads to every agent's conversations, so it is
// asked first (a ToolConfirm here), and chatSearchPicked("all") is emitted
// from that question's onConfirmed and nowhere else
// (tests/test_chat_search.py).
Column {
  id: sw

  property string part: "tools"
  property var choices: ({})
  property var globals: ({})
  property string program: ""

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  // The found tools' switches for every agent (sharedTools), to count the
  // ones this agent follows.
  property var shared: ({})
  // The links to its own switches and to the ones for every agent; the page
  // knows where they are.
  signal detailsAsked()
  signal sharedAsked()
  // "allow" or "deny": notesWrite / mainNotesWrite.
  property string notesWrite: "allow"
  signal notesPicked(string value)
  property string collaboration: "announce"
  signal collaborationPicked(string value)
  property bool acceptsWork: true
  signal acceptsWorkPicked(bool value)
  // "off", "own" or "all": chatSearch / mainChatSearch (M20). Missing is
  // "own"; anything else is what the daemon reads as off.
  property string chatSearch: "own"
  signal chatSearchPicked(string value)
  // Its name, for the question before "Every chat".
  property string agentLabel: ""
  // true when it is quarantined, "unreadable" when the quarantine list cannot
  // be read: either way the daemon gives it no chat.
  property var quarantined: false
  // saveChats: with nothing saved there is nothing to search.
  property bool chatsSaved: true
  // The question before "Every chat" is up.
  property bool confirmingAll: false

  readonly property var desktopPrograms: ["claude", "codex"]
  readonly property var browserPrograms: ["claude"]
  // The programs that take Agent Voice's notes tools: agentfs.NOTES_PROGRAMS.
  readonly property var notesPrograms: ["claude", "codex"]
  readonly property bool notesDenied: notesWrite !== "allow"
  readonly property string notesWhyNot: {
    if (program === "endpoint") return "An endpoint runs nothing on this machine, so it has no notes tools."
    if (program === "") return "No program is chosen for it."
    if (notesPrograms.indexOf(program) < 0) return "Notes need Claude Code or Codex."
    return ""
  }
  // The programs that can start collaboration: agentfs.COLLAB_PROGRAMS.
  readonly property var collabPrograms: ["claude", "codex"]
  readonly property string collabWhyNot: {
    if (program === "endpoint")
      return "An endpoint can be asked and given work (what it is sent leaves this machine), but cannot start any."
    if (program === "") return "No program is chosen for it."
    if (collabPrograms.indexOf(program) < 0)
      return "Can be asked and given work, but cannot start any: only Claude Code and Codex can."
    return ""
  }
  readonly property string collabLevel:
    ["off", "ask", "announce", "allow"].indexOf(collaboration) >= 0 ? collaboration : "ask"
  // Keep these descriptions in step with agentfs.COLLAB_SAYS.
  readonly property var collabHints: ({
    off: "Starts nothing with other agents: the tools are not offered to it.",
    ask: "Asks you first, on screen and out loud, before it asks, gives work to, passes to or messages another agent.",
    announce: "Says out loud when it gives work to or passes to another agent, with three seconds to say stop; " +
              "questions and messages go quietly, shown on screen.",
    allow: "Works with the other agents quietly; it is still shown on screen, in the chat and in the audit log. " +
           "Sending anything to an endpoint is still said out loud."
  })

  // The programs that take the crew server, and so the chat tools (M20).
  readonly property var chatsPrograms: ["claude", "codex"]
  readonly property string chatsWhyNot: {
    if (program === "endpoint") return "An endpoint runs nothing on this machine, so it has no chat tools."
    if (program === "") return "No program is chosen for it."
    if (chatsPrograms.indexOf(program) < 0) return "Chat search needs Claude Code or Codex."
    return ""
  }
  readonly property string chatScope: ["off", "own", "all"].indexOf(chatSearch) >= 0 ? chatSearch : "off"
  // What the scope does not hold, by program: the permission hook asks a
  // Claude agent below Trusted before it reads the chat files directly;
  // Codex has no hook, and its read-only sandbox reads files.
  readonly property string chatsFilesNote: program === "codex"
      ? "Codex can read the chat files directly at any level: it has no permission hook."
      : "at Trust everything it could read the chat files directly; below that it is asked first."
  readonly property string chatsHint: {
    if (quarantined === "unreadable")
      return "The crew settings can't be read, so it can search no chat until they are fixed on the Crew map."
    if (quarantined === true)
      return "Quarantined, so it can search no chat whatever this says. Release it on the Crew map."
    if (chatScope === "off")
      return "It has no chat tools. Even so, " + chatsFilesNote
    var out = (chatScope === "own" ? "Its own saved chats and the ones shared with it."
                                   : "Every saved chat, every agent's.") +
              " Searches are never logged. This holds through its chat tools: " + chatsFilesNote
    if (!chatsSaved)
      out += " Nothing is being saved now (Chats page), so there is nothing to search."
    return out
  }
  // Every way in to the choice comes here. "Every chat" only opens the
  // question; the question's own button says yes to it.
  function pickChatSearch(v) {
    if (v === "all") {
      if (chatScope !== "all") confirmingAll = true
      return
    }
    confirmingAll = false
    if (v !== chatScope) chatSearchPicked(v)
  }

  function choice(key) {
    var c = (choices && typeof choices === "object") ? choices[key] : undefined
    return (c === "on" || c === "off") ? c : "inherit"
  }
  function effective(key) {
    var c = choice(key)
    return c === "inherit" ? globals[key] === true : c === "on"
  }
  function whyNot(key) {
    if (program === "endpoint") return "An endpoint runs nothing on this machine."
    if (program === "") return "No program is chosen for it."
    if (key === "desktop" && desktopPrograms.indexOf(program) < 0)
      return "Its program cannot take Agent Voice's tools; only Claude Code and Codex can."
    if (key === "browser" && browserPrograms.indexOf(program) < 0)
      return "Only Claude Code can use Claude in Chrome."
    return ""
  }
  // One line per tool: what it has, and where that comes from.
  function source(key) {
    if (whyNot(key) !== "") return "not available"
    var c = choice(key)
    if (c === "inherit") return (globals[key] === true ? "on" : "off") + ", as for every agent"
    return (c === "on" ? "on" : "off") + ", this agent's own"
  }

  readonly property var rows: [
    { key: "desktop", label: "Desktop tools", short: "desktop",
      tooltip: "Open apps, move and close windows, switch workspaces, play and pause, change the volume, " +
               "notify, use the clipboard and see the screen. Each goes through its permission level." },
    { key: "browser", label: "Browser", short: "browser",
      tooltip: "Claude in Chrome: your own browser, signed in as you. Sending, buying, posting and the " +
               "like are asked about at every level." },
    { key: "omarchySkill", label: "Omarchy commands", short: "Omarchy commands",
      tooltip: "This machine's omarchy commands and keybindings, so “open a scratchpad” is one command." },
    { key: "agentvoiceSkill", label: "How Agent Voice works", short: "Agent Voice help",
      tooltip: "A reference on Agent Voice's spoken commands, wake phrases and settings. It explains; it starts nothing." }
  ]

  // How many tools found on this machine are switched on for it, by the
  // settings alone: its own "on:…" entries, and the ones for every agent it
  // does not switch off. Whether each still matches what was approved, and
  // whether its program can use it, is on Agent details.
  readonly property int foundOn: {
    var own = (choices && typeof choices === "object") ? choices : {}
    var all = (shared && typeof shared === "object") ? shared : {}
    var n = 0, seen = {}
    var keys = Object.keys(own).concat(Object.keys(all))
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i]
      if (seen[k] || !/^(mcp|cli):/.test(k)) continue
      seen[k] = true
      var v = own[k] !== undefined ? own[k] : all[k]
      if (/^on:[0-9a-f]{32}$/.test(String(v))) n++
    }
    return n
  }

  // What it has now, in one line (the header's tooltip).
  readonly property string summary: {
    var on = []
    for (var i = 0; i < rows.length; i++)
      if (effective(rows[i].key) && whyNot(rows[i].key) === "") on.push(rows[i].short)
    var out = on.length > 0 ? on.join(", ") : "no tools"
    if (foundOn > 0) out += " · " + foundOn + " found on this machine"
    if (notesWhyNot === "" && notesDenied) out += " · notes read only"
    if (collabWhyNot === "") {
      if (collabLevel === "off") out += " · collaboration off"
      else if (collabLevel === "ask") out += " · asks before collaborating"
      else if (collabLevel === "allow") out += " · collaborates quietly"
    }
    if (!acceptsWork) out += " · questions only"
    return out
  }

  width: parent ? parent.width : 0
  spacing: Style.space(8)

  // --- tools (read only since M10) -----------------------------------------------
  Column {
    width: parent.width
    visible: sw.part === "tools"
    spacing: Style.space(2)
    Repeater {
      model: sw.rows
      Hint {
        required property var modelData
        width: parent.width
        text: modelData.label + ": " + sw.source(modelData.key)
        detail: sw.whyNot(modelData.key) !== "" ? sw.whyNot(modelData.key) : modelData.tooltip
        foreground: sw.foreground
        fontFamily: sw.fontFamily
      }
    }
    Hint {
      width: parent.width
      text: "Found on this machine: " + (sw.foundOn === 0 ? "none switched on"
                                          : sw.foundOn + " switched on")
      detail: "MCP servers in Claude Code's and Codex's own settings, and command-line tools " +
              "such as gh. Each is off until it is switched on, for this agent or for every agent."
      foreground: sw.foreground
      fontFamily: sw.fontFamily
    }
  }
  Flow {
    width: parent.width
    visible: sw.part === "tools"
    spacing: Style.space(8)
    ActionButton {
      text: "Change on Agent details › Tools & skills"
      focusable: true
      foreground: sw.foreground
      fontFamily: sw.fontFamily
      fontSize: Style.font.caption
      tooltipText: "This agent's own switches, which beat the ones for every agent, and the tools " +
                   "found on this machine. A change applies from its next turn, in the same conversation."
      onClicked: sw.detailsAsked()
    }
    ActionButton {
      text: "For every agent: Communal → Tools ›"
      focusable: true
      foreground: sw.foreground
      fontFamily: sw.fontFamily
      fontSize: Style.font.caption
      onClicked: sw.sharedAsked()
    }
  }

  // --- collaboration and notes -----------------------------------------------------
  SettingRow {
    width: parent.width
    visible: sw.part === "collab"
    stacked: sw.collabWhyNot === ""
    label: "Collaboration"
    hint: sw.collabWhyNot !== "" ? sw.collabWhyNot : sw.collabHints[sw.collabLevel]
    changed: sw.collabWhyNot === "" && sw.collabLevel !== "announce"
    foreground: sw.foreground
    fontFamily: sw.fontFamily
    onReset: sw.collaborationPicked("announce")
    SegmentedChoice {
      width: parent.width
      wrap: true
      visible: sw.collabWhyNot === ""
      options: [
        { value: "off", label: "Off" },
        { value: "ask", label: "Ask me first" },
        { value: "announce", label: "Announce" },
        { value: "allow", label: "Quietly" }
      ]
      value: sw.collabLevel
      foreground: sw.foreground
      fontFamily: sw.fontFamily
      onCommitted: function(v) { if (v !== sw.collabLevel) sw.collaborationPicked(v) }
    }
  }
  SettingRow {
    width: parent.width
    visible: sw.part === "collab" && sw.program !== ""
    stacked: true
    label: "Takes work from agents"
    hint: sw.acceptsWork
          ? "Other agents may ask it questions, give it tasks and pass it a conversation. " +
            "It works at its own permission level; their request is never your approval."
          : "Other agents may ask it questions, but not give it tasks or pass it a conversation. " +
            "A pass you start yourself still works."
    changed: !sw.acceptsWork
    foreground: sw.foreground
    fontFamily: sw.fontFamily
    onReset: sw.acceptsWorkPicked(true)
    SegmentedChoice {
      width: parent.width
      wrap: true
      options: [
        { value: "true", label: "Yes" },
        { value: "false", label: "Questions only" }
      ]
      value: String(sw.acceptsWork)
      foreground: sw.foreground
      fontFamily: sw.fontFamily
      onCommitted: function(v) { if ((v === "true") !== sw.acceptsWork) sw.acceptsWorkPicked(v === "true") }
    }
  }
  SettingRow {
    width: parent.width
    visible: sw.part === "collab"
    stacked: sw.notesWhyNot === ""
    label: "Notes"
    hint: sw.notesWhyNot !== "" ? sw.notesWhyNot
          : sw.notesDenied
            ? "Reads its own and the communal notes, and cannot write them. Held by the notes tools at every level."
            : "Reads and writes its own and the communal notes. At “ask first” it asks before each write."
    changed: sw.notesWhyNot === "" && sw.notesDenied
    foreground: sw.foreground
    fontFamily: sw.fontFamily
    onReset: sw.notesPicked("allow")
    SegmentedChoice {
      width: parent.width
      wrap: true
      visible: sw.notesWhyNot === ""
      options: [
        { value: "allow", label: "May write" },
        { value: "deny", label: "Read only" }
      ]
      value: sw.notesDenied ? "deny" : "allow"
      foreground: sw.foreground
      fontFamily: sw.fontFamily
      onCommitted: function(v) { if (v !== (sw.notesDenied ? "deny" : "allow")) sw.notesPicked(v) }
    }
  }
  SettingRow {
    width: parent.width
    visible: sw.part === "collab"
    stacked: sw.chatsWhyNot === ""
    label: "Chat search"
    hint: sw.chatsWhyNot !== "" ? sw.chatsWhyNot : sw.chatsHint
    changed: sw.chatsWhyNot === "" && sw.chatScope !== "own"
    foreground: sw.foreground
    fontFamily: sw.fontFamily
    onReset: sw.pickChatSearch("own")
    SegmentedChoice {
      id: chatChoice
      width: parent.width
      wrap: true
      visible: sw.chatsWhyNot === ""
      options: [
        { value: "off", label: "Off" },
        { value: "own", label: "Its own and shared" },
        { value: "all", label: "Every chat" }
      ]
      value: sw.chatScope
      foreground: sw.foreground
      fontFamily: sw.fontFamily
      onCommitted: function(v) { sw.pickChatSearch(v) }
    }
  }
  ToolConfirm {
    width: parent.width
    visible: sw.part === "collab" && sw.confirmingAll && sw.chatsWhyNot === ""
    title: "Let " + (sw.agentLabel || "this agent") + " search every saved chat?"
    lines: [
      { label: "It can find", value: "Every saved chat: every agent's, including the ones " +
                                     (sw.agentLabel || "it") + " was never part of" },
      { label: "Who gets it", value: (sw.agentLabel || "This agent") + " only" },
      { label: "How much", value: "At most 10 matches a search and 8000 characters a read, through its chat tools. " +
                                  "What it searches for is never logged." }
    ]
    warning: sw.program === "codex"
             ? "Codex has no permission hook: at any level it could read the chat files directly whatever this says."
             : "At Trust everything it could read the chat files directly whatever this says."
    confirmText: "Allow every chat"
    foreground: sw.foreground
    accent: sw.accent
    urgent: sw.urgent
    fontFamily: sw.fontFamily
    onConfirmed: { sw.confirmingAll = false; sw.chatSearchPicked("all") }
    // The chip picked is held as chosen while a write goes round
    // (SegmentedChoice); nothing was written, so it goes back at once and
    // a second "Every chat" asks again.
    onCancelled: { sw.confirmingAll = false; chatChoice.holding = false }
  }
}
