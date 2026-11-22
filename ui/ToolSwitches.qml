import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// One agent's tool switches (merged plan, Phase 13) and its collaboration
// rows (Phases 14 and 16), drawn as one of two cards on the Agents page
// (master plan M5): `part: "tools"` or `part: "collab"`. Both halves share
// the tables below, which is why they are one piece.
//
// Tools: desktop tools, the browser and the Omarchy commands, as chips that
// cycle "every agent" → on → off. Each chip's line underneath says what the
// agent has *and where that comes from* -- an inherited "off" is the setting
// for every agent (Communal → Tools), not a missing control.
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
//     program: "claude"
//     onPicked: function(key, value) { ... }
//     onSharedAsked: s.goTo("communal", "", "tools")
//     notesWrite: entry.notesWrite || "allow"   // "allow" | "deny" (Phase 14)
//     onNotesPicked: function(value) { ... }
//     collaboration: entry.collaboration === undefined ? "announce" : String(entry.collaboration)
//     onCollaborationPicked: function(value) { ... }
//     acceptsWork: entry.acceptsWork !== false
//     onAcceptsWorkPicked: function(value) { ... }
//   }
//
// Notes (Phase 14): whether this agent may write its own and the communal
// notes through Agent Voice's notes tools. Reading is always allowed. Only
// Claude Code and Codex take the notes tools. Collaboration (Phase 16) sets
// what an agent can start with other agents and whether it takes work from
// them.
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

  signal picked(string key, string value)
  // The link to the switches for every agent; the page knows where they are.
  signal sharedAsked()
  // "allow" or "deny": notesWrite / mainNotesWrite.
  property string notesWrite: "allow"
  signal notesPicked(string value)
  property string collaboration: "announce"
  signal collaborationPicked(string value)
  property bool acceptsWork: true
  signal acceptsWorkPicked(bool value)

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
      tooltip: "This machine's omarchy commands and keybindings, so “open a scratchpad” is one command." }
  ]

  // What it has now, in one line (the header's tooltip).
  readonly property string summary: {
    var on = []
    for (var i = 0; i < rows.length; i++)
      if (effective(rows[i].key) && whyNot(rows[i].key) === "") on.push(rows[i].short)
    var out = on.length > 0 ? on.join(", ") : "no tools"
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

  // --- tools ---------------------------------------------------------------------
  ToggleChips {
    width: parent.width
    visible: sw.part === "tools"
    allowInherit: true
    inheritLabel: "every agent"
    options: sw.rows.map(function(r) {
      return { value: r.key, label: r.label, tooltip: r.tooltip, disabledReason: sw.whyNot(r.key) } })
    chipStates: ({ desktop: sw.choice("desktop"), browser: sw.choice("browser"),
                   omarchySkill: sw.choice("omarchySkill") })
    inherited: sw.globals
    foreground: sw.foreground
    accent: sw.accent
    urgent: sw.urgent
    fontFamily: sw.fontFamily
    onToggled: function(value, state) { if (state !== sw.choice(value)) sw.picked(value, state) }
  }
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
        detail: sw.whyNot(modelData.key)
        foreground: sw.foreground
        fontFamily: sw.fontFamily
      }
    }
  }
  Button {
    visible: sw.part === "tools"
    text: "For every agent: Communal → Tools ›"
    focusable: true
    foreground: sw.foreground
    fontFamily: sw.fontFamily
    fontSize: Style.font.caption
    tooltipText: "A chip set here beats the setting for every agent, for this agent only. " +
                 "A change applies from its next turn, in the same conversation."
    onClicked: sw.sharedAsked()
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
}
