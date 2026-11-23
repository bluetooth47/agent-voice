import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// One agent's voice, read-only: who it is, which voice and speed it speaks
// at, a ▶ Test, and a link to where it is changed. Voice and speed keep
// their home on the Agents card (master plan, M25), so this row only reads
// and navigates; it knows nothing about settings, the page wires the signals.
//
//   test()     play about a minute of this voice at this speed
//   change()   open this agent's card on the Agents page
//
// The Test and "Change on Agents" cells are fixed-width and anchored to the
// right edge, so they line up from row to row whatever the name is.
Item {
  id: row

  property string name: ""
  property string voiceName: ""
  property string pace: ""           // "100%"
  property string note: ""           // "Follows the main agent"
  property bool playing: false
  property bool canTest: true
  property string testTip: ""
  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property string fontFamily: Style.font.family

  signal test()
  signal change()

  readonly property int cell: Style.space(96)
  readonly property int linkCell: Style.space(148)

  width: parent ? parent.width : 400
  implicitHeight: Math.max(info.implicitHeight, Style.space(30)) + Style.space(12)

  Rectangle {
    anchors.fill: parent
    radius: Style.cornerRadius
    color: row.playing ? Qt.rgba(row.accent.r, row.accent.g, row.accent.b, 0.12)
                       : (hover.hovered ? Qt.rgba(row.foreground.r, row.foreground.g, row.foreground.b, 0.05)
                                        : "transparent")
  }
  HoverHandler { id: hover }

  Column {
    id: info
    objectName: "agentName"
    anchors.left: parent.left
    anchors.leftMargin: Style.space(8)
    anchors.right: testCell.left
    anchors.rightMargin: Style.space(8)
    anchors.verticalCenter: parent.verticalCenter
    spacing: Style.space(2)

    Text {
      width: parent.width
      text: row.name
      color: row.foreground
      font.family: row.fontFamily
      font.pixelSize: Style.font.body
      font.bold: true
      elide: Text.ElideRight
      textFormat: Text.PlainText
    }
    Text {
      width: parent.width
      text: row.voiceName + (row.pace !== "" ? "  ·  " + row.pace : "") +
            (row.note !== "" ? "  ·  " + row.note : "")
      color: row.foreground
      opacity: 0.6
      font.family: row.fontFamily
      font.pixelSize: Style.font.bodySmall
      elide: Text.ElideRight
      textFormat: Text.PlainText
    }
  }

  Item {
    id: testCell
    objectName: "agentTestCell"
    anchors.right: linkCell.left
    anchors.rightMargin: Style.space(6)
    anchors.verticalCenter: parent.verticalCenter
    width: row.cell
    height: testButton.implicitHeight
    Button {
      id: testButton
      width: parent.width
      text: row.playing ? "■ Stop" : "▶ Test"
      enabled: row.canTest
      tooltipText: row.testTip
      bordered: true
      selected: row.playing
      foreground: row.foreground
      fontFamily: row.fontFamily
      onClicked: row.test()
    }
  }

  Item {
    id: linkCell
    objectName: "agentChangeCell"
    anchors.right: parent.right
    anchors.rightMargin: Style.space(4)
    anchors.verticalCenter: parent.verticalCenter
    width: row.linkCell
    height: changeButton.implicitHeight
    Button {
      id: changeButton
      width: parent.width
      text: "Change on Agents →"
      tooltipText: "Voice and speed are set on this agent's card"
      bordered: true
      foreground: row.foreground
      fontFamily: row.fontFamily
      onClicked: row.change()
    }
  }
}
