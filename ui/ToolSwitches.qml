import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// One agent's tool switches (merged plan, Phase 13), in a group that starts
// shut: desktop tools, the browser and the Omarchy commands, each "same as
// every agent", on or off. The settings for every agent are at the foot of
// the Agents page; a switch here beats them for this agent only.
//
// A tool this agent's program cannot use shows why instead of a switch:
// a control that does nothing must say why. Which programs can use which
// tool is the table in daemon/agentfs.py (DESKTOP_PROGRAMS and the rest);
// test_tools_skills.py holds this copy to it.
//
//   ToolSwitches {
//     choices: entry.tools || {}           // key -> "inherit" | "on" | "off"
//     globals: { desktop: true, browser: false, omarchySkill: true }
//     program: "claude"
//     expanded: page.isOpen("tools:sora")
//     onToggled: function(open) { ... }
//     onPicked: function(key, value) { ... }
//     notesWrite: entry.notesWrite || "allow"   // "allow" | "deny" (Phase 14)
//     onNotesPicked: function(value) { ... }
//     collaboration: entry.collaboration === undefined ? "announce" : String(entry.collaboration)
//     onCollaborationPicked: function(value) { ... }
//     acceptsWork: entry.acceptsWork !== false
//     onAcceptsWorkPicked: function(value) { ... }
//   }
//
// Notes (Phase 14) are a row of their own: whether this agent may write its
// own and the communal notes through Agent Voice's notes tools. Reading is
// always allowed. Only Claude Code and Codex take the notes tools.
// Collaboration (Phase 16) sets what an agent can start with other agents
// and whether it takes work from them.
Column {
  id: sw

  property var choices: ({})
  property var globals: ({})
  property string program: ""
  property bool expanded: false

  property color foreground: Commons.Color.foreground
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  signal toggled(bool expanded)
  signal picked(string key, string value)
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

  readonly property var rows: [
    { key: "desktop", label: "Desktop tools", short: "desktop" },
    { key: "browser", label: "Browser", short: "browser" },
    { key: "omarchySkill", label: "Omarchy commands", short: "Omarchy commands" }
  ]

  // What it has now, on the header while the group is shut.
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

  Button {
    text: (sw.expanded ? "▾  " : "▸  ") + "Tools & collaboration" +
          (sw.expanded ? "" : " · " + sw.summary)
    focusable: true
    foreground: sw.foreground
    fontFamily: sw.fontFamily
    // Asks, without assigning: `expanded` stays bound to the page, so a
    // deep link can open the group again after a click shut it.
    onClicked: sw.toggled(!sw.expanded)
  }

  Column {
    width: parent.width
    visible: sw.expanded
    spacing: Style.space(8)

    Repeater {
      model: sw.rows
      SettingRow {
        id: row
        required property var modelData
        readonly property string why: sw.whyNot(modelData.key)
        readonly property string picked: sw.choice(modelData.key)
        width: parent.width
        stacked: why === ""
        label: modelData.label
        hint: why !== "" ? why
              : picked === "inherit"
                ? (sw.globals[modelData.key] === true ? "On" : "Off") + ", as for every agent."
                : (picked === "on" ? "On" : "Off") + " for this agent, whatever the setting for every agent is."
        changed: why === "" && picked !== "inherit"
        foreground: sw.foreground
        fontFamily: sw.fontFamily
        onReset: sw.picked(modelData.key, "inherit")
        SegmentedChoice {
          visible: row.why === ""
          options: [
            { value: "inherit", label: "Same as every agent" },
            { value: "on", label: "On" },
            { value: "off", label: "Off" }
          ]
          value: row.picked
          foreground: sw.foreground
          fontFamily: sw.fontFamily
          onCommitted: function(v) { if (v !== row.picked) sw.picked(row.modelData.key, v) }
        }
      }
    }
    SettingRow {
      id: notesRow
      width: parent.width
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
      stacked: sw.collabWhyNot === ""
      label: "Collaboration"
      hint: sw.collabWhyNot !== "" ? sw.collabWhyNot : sw.collabHints[sw.collabLevel]
      changed: sw.collabWhyNot === "" && sw.collabLevel !== "announce"
      foreground: sw.foreground
      fontFamily: sw.fontFamily
      onReset: sw.collaborationPicked("announce")
      SegmentedChoice {
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
      visible: sw.program !== ""
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
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: "The settings for every agent are under “On the desktop” at the foot of this page. " +
            "A change applies from its next turn, in the same conversation."
      color: sw.dim
      font.family: sw.fontFamily
      font.pixelSize: Style.font.caption
    }
  }
}
