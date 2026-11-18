import QtQuick
import qs.Commons
import qs.Commons as Commons

// One agent on the Agents page: the same card for the main agent and every
// extra one, which used to be drawn two different ways in two different
// boxes.
//
// The header is always shown: name, what runs it (program, model, effort),
// a "default" badge on the main agent, and its state. Clicking the header
// opens and closes the body, which holds that agent's settings -- the
// caller's children go there.
//
//   AgentCard {
//     width: parent.width
//     name: "Sarah"; wakeName: "sarah"; summary: "claude · opus · high"
//     isDefault: false; status: "listening"; switchedOff: false
//     SettingRow { ... }
//   }
Rectangle {
  id: card

  property string name: ""
  property string wakeName: ""
  property string summary: ""
  property string status: ""
  // As StatusCard: "idle", "active", "busy", "alert".
  property string tone: "idle"
  property bool isDefault: false
  property bool expanded: false
  // Switched off on its card: the header is drawn dimmed, every setting kept.
  property bool switchedOff: false
  // Shown under the header in the urgent colour when something stops this
  // agent working (no folder for "edits", a name the recogniser lacks).
  property string problem: ""

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  // Translucent rather than Qt.darker: darker is dimmer only on a dark
  // theme, and on a light one made every hint as black as the label.
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  default property alias body: bodyColumn.data

  signal toggled(bool expanded)

  readonly property color toneColor: tone === "alert" ? urgent
                                     : tone === "busy" ? accent
                                     : tone === "active" ? foreground : dim
  readonly property int pad: Style.space(12)

  implicitHeight: column.implicitHeight + pad * 2
  height: implicitHeight
  radius: Style.cornerRadius
  color: "transparent"
  border.width: 1
  border.color: problem !== "" ? Qt.rgba(urgent.r, urgent.g, urgent.b, 0.6)
                : expanded ? Qt.rgba(foreground.r, foreground.g, foreground.b, 0.35)
                : Qt.rgba(foreground.r, foreground.g, foreground.b, 0.18)

  Column {
    id: column
    x: card.pad
    y: card.pad
    width: parent.width - card.pad * 2
    spacing: Style.space(10)

    Item {
      id: header
      width: parent.width
      height: Math.max(names.implicitHeight, side.implicitHeight)
      opacity: card.switchedOff ? 0.5 : 1.0

      MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: { card.expanded = !card.expanded; card.toggled(card.expanded) }
      }

      Text {
        id: chevron
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: Style.space(14)
        text: card.expanded ? "" : ""
        color: card.dim
        font.family: card.fontFamily
        font.pixelSize: Style.font.caption
      }

      Column {
        id: names
        anchors.left: chevron.right
        anchors.leftMargin: Style.space(6)
        anchors.right: side.left
        anchors.rightMargin: Style.space(10)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(2)

        Row {
          spacing: Style.space(8)
          Text {
            text: card.name || "New agent"
            textFormat: Text.PlainText
            color: card.foreground
            font.family: card.fontFamily
            font.pixelSize: Style.font.subtitle
            font.bold: true
          }
          Text {
            visible: card.wakeName !== "" && card.wakeName.toLowerCase() !== card.name.toLowerCase()
            anchors.baseline: parent.children[0].baseline
            text: "“" + card.wakeName + "”"
            textFormat: Text.PlainText
            color: card.dim
            font.family: card.fontFamily
            font.pixelSize: Style.font.caption
          }
          Rectangle {
            visible: card.isDefault
            anchors.verticalCenter: parent.children[0].verticalCenter
            width: badge.implicitWidth + Style.space(10)
            height: badge.implicitHeight + Style.space(4)
            radius: Style.cornerRadius
            color: "transparent"
            border.width: 1
            border.color: card.dim
            Text {
              id: badge
              anchors.centerIn: parent
              text: "default"
              color: card.dim
              font.family: card.fontFamily
              font.pixelSize: Style.font.caption
            }
          }
        }
        Text {
          width: parent.width
          visible: text !== ""
          text: card.summary
          textFormat: Text.PlainText
          color: card.dim
          font.family: card.fontFamily
          font.pixelSize: Style.font.caption
          elide: Text.ElideRight
        }
      }

      Row {
        id: side
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(6)
        Rectangle {
          anchors.verticalCenter: parent.verticalCenter
          width: Style.space(7); height: width; radius: width / 2
          visible: card.status !== ""
          color: card.toneColor
        }
        Text {
          visible: card.status !== ""
          text: card.status
          color: card.toneColor
          font.family: card.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }

    Text {
      width: parent.width
      visible: card.problem !== ""
      text: "⚠  " + card.problem
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: card.urgent
      font.family: card.fontFamily
      font.pixelSize: Style.font.caption
    }

    Column {
      id: bodyColumn
      width: parent.width
      visible: card.expanded
      spacing: Style.space(10)
    }
  }
}
