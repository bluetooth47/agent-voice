import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// What every agent shares: the communal rules and defaults (merged plan,
// Phase 12). Shared skills, notes and chats join this page as they are
// built (Phases 13 to 15); until then it is one subject, so it has no tabs.
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
