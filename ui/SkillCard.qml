import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// One skill as a card in a lane (master plan, M11): its name, a line of what
// it is for, where it comes from, and -- folded away until the caret is
// clicked -- the details: description, source path, size, problems, the
// names it shadows or is shadowed by, and who gets it.
//
// The switch, when `switchable`, only *asks*: toggled(on) goes to the page,
// which writes the setting through its overlay function. Buttons placed
// inside the card (Give a copy…) sit under the details, always visible.
// Every text is plain: a description is whatever a skill's author wrote.
//
//   SkillCard {
//     title: "weekly-report"; subtitle: "How to write the weekly report"
//     badge: "~/.claude/skills"; status: "Not given: switched off for Theo"
//     details: [{ label: "Source", value: "~/.claude/skills/weekly-report" }]
//     switchable: true; checked: false
//     onToggled: function(on) { page.s.setAgentSkill(page.target, "weekly-report", on) }
//   }
Rectangle {
  id: card

  property string title: ""
  property string subtitle: ""
  property string badge: ""
  property string badgeTone: "idle"
  // One line under the title when it is not given, or why it is off.
  property string status: ""
  property bool statusUrgent: false
  // [{label, value}], shown when unfolded.
  property var details: []
  property bool switchable: false
  property bool checked: false
  property string switchTooltip: ""
  property bool expanded: false
  property bool dimmed: false

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  default property alias actions: actionRow.data

  signal toggled(bool on)

  width: parent ? parent.width : implicitWidth
  implicitHeight: column.implicitHeight + Style.space(12)
  height: implicitHeight
  radius: Style.cornerRadius
  color: header.containsMouse || activeFocus ? Style.hoverFillFor(foreground, accent) : "transparent"
  border.width: 1
  border.color: activeFocus ? accent : Qt.rgba(foreground.r, foreground.g, foreground.b, 0.22)
  activeFocusOnTab: true
  Keys.onReturnPressed: card.expanded = !card.expanded
  Keys.onEnterPressed: card.expanded = !card.expanded
  Keys.onSpacePressed: if (card.switchable) card.toggled(!card.checked)

  Column {
    id: column
    x: Style.space(8)
    y: Style.space(6)
    width: parent.width - Style.space(16)
    spacing: Style.space(3)

    Item {
      width: parent.width
      height: Math.max(titleColumn.implicitHeight, toggle.visible ? toggle.implicitHeight : 0)

      MouseArea {
        id: header
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: parent.width - (toggle.visible ? toggle.width + Style.space(6) : 0)
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: { card.forceActiveFocus(); card.expanded = !card.expanded }
      }
      Column {
        id: titleColumn
        width: header.width
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(1)
        Row {
          width: parent.width
          spacing: Style.space(6)
          Text {
            id: caret
            text: card.expanded ? "▾" : "▸"
            color: card.dim
            font.family: card.fontFamily
            font.pixelSize: Style.font.caption
            anchors.verticalCenter: parent.verticalCenter
          }
          Text {
            width: Math.min(implicitWidth, parent.width - caret.width - parent.spacing
                            - (badgePill.visible ? badgePill.width + parent.spacing : 0))
            text: card.title
            textFormat: Text.PlainText
            elide: Text.ElideRight
            color: card.dimmed ? card.dim : card.foreground
            font.family: card.fontFamily
            font.pixelSize: Style.font.body
            anchors.verticalCenter: parent.verticalCenter
          }
          Pill {
            id: badgePill
            text: card.badge
            tone: card.badgeTone
            foreground: card.foreground
            accent: card.accent
            urgent: card.urgent
            fontFamily: card.fontFamily
            anchors.verticalCenter: parent.verticalCenter
          }
        }
        Text {
          width: parent.width
          visible: text !== ""
          text: card.subtitle
          textFormat: Text.PlainText
          elide: Text.ElideRight
          maximumLineCount: 1
          color: card.dim
          font.family: card.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
      ToggleSwitch {
        id: toggle
        visible: card.switchable
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        checked: card.checked
        foreground: card.foreground
        accent: card.accent
        onToggled: card.toggled(!card.checked)
      }
    }
    Text {
      width: parent.width
      visible: text !== ""
      text: card.status
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: card.statusUrgent ? card.urgent : card.dim
      font.family: card.fontFamily
      font.pixelSize: Style.font.caption
    }
    Column {
      width: parent.width
      visible: card.expanded
      spacing: Style.space(2)
      Repeater {
        model: card.details
        Text {
          required property var modelData
          width: column.width
          wrapMode: Text.WrapAnywhere
          textFormat: Text.PlainText
          text: String(modelData.label) + ": " + String(modelData.value)
          color: modelData.urgent === true ? card.urgent : card.dim
          font.family: card.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }
    Flow {
      id: actionRow
      width: parent.width
      visible: children.length > 0
      spacing: Style.space(6)
    }
  }
}
