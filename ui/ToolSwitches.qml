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
//   }
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

  readonly property var desktopPrograms: ["claude", "codex"]
  readonly property var browserPrograms: ["claude"]

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
    return on.length > 0 ? on.join(", ") : "no tools"
  }

  width: parent ? parent.width : 0
  spacing: Style.space(8)

  Button {
    text: (sw.expanded ? "▾  " : "▸  ") + "Tools & collaboration" +
          (sw.expanded ? "" : " · " + sw.summary)
    focusable: true
    foreground: sw.foreground
    fontFamily: sw.fontFamily
    onClicked: { sw.expanded = !sw.expanded; sw.toggled(sw.expanded) }
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
