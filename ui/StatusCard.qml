import QtQuick
import qs.Commons
import qs.Commons as Commons

// A small boxed status line: an icon, a title, a subtitle, and a state chip
// on the right. For "what is each agent doing" on the overview page and in
// the bar popup, and for problems worth a box ("No project folder").
//
// `tone` colours the chip and the icon: "idle" (dim), "active" (foreground),
// "busy" (accent), "alert" (urgent). Clickable when `clickable` is set,
// which emits clicked().
Rectangle {
  id: card

  property string icon: ""
  property string title: ""
  property string subtitle: ""
  property string status: ""
  property string tone: "idle"
  property bool clickable: false

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  // Translucent rather than Qt.darker: darker is dimmer only on a dark
  // theme, and on a light one made every hint as black as the label.
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  // Anything extra on the right, after the chip (a button, a switch).
  default property alias trailing: trailingSlot.data

  signal clicked()

  readonly property color toneColor: tone === "alert" ? urgent
                                     : tone === "busy" ? accent
                                     : tone === "active" ? foreground : dim

  implicitHeight: content.implicitHeight + Style.space(16)
  height: implicitHeight
  radius: Style.cornerRadius
  color: hover.containsMouse && clickable
         ? Qt.rgba(foreground.r, foreground.g, foreground.b, 0.06) : "transparent"
  border.width: 1
  border.color: tone === "alert" ? Qt.rgba(urgent.r, urgent.g, urgent.b, 0.6)
                : Qt.rgba(foreground.r, foreground.g, foreground.b, 0.18)

  MouseArea {
    id: hover
    anchors.fill: parent
    hoverEnabled: card.clickable
    enabled: card.clickable
    cursorShape: card.clickable ? Qt.PointingHandCursor : Qt.ArrowCursor
    onClicked: card.clicked()
  }

  Item {
    id: content
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.verticalCenter: parent.verticalCenter
    anchors.leftMargin: Style.space(10)
    anchors.rightMargin: Style.space(10)
    implicitHeight: Math.max(texts.implicitHeight, chip.implicitHeight, trailingSlot.childrenRect.height)

    Text {
      id: glyph
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
      visible: card.icon !== ""
      width: visible ? Style.space(20) : 0
      text: card.icon
      color: card.toneColor
      font.family: card.fontFamily
      font.pixelSize: Style.font.title
    }

    Column {
      id: texts
      anchors.left: glyph.right
      anchors.leftMargin: glyph.visible ? Style.space(8) : 0
      anchors.right: chip.left
      anchors.rightMargin: Style.space(8)
      anchors.verticalCenter: parent.verticalCenter
      spacing: Style.space(1)

      Text {
        width: parent.width
        text: card.title
        // A name the user typed, or a transcript: never markup.
        textFormat: Text.PlainText
        color: card.foreground
        font.family: card.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
        elide: Text.ElideRight
      }
      Text {
        width: parent.width
        visible: text !== ""
        text: card.subtitle
        textFormat: Text.PlainText
        color: card.dim
        font.family: card.fontFamily
        font.pixelSize: Style.font.caption
        elide: Text.ElideRight
      }
    }

    Text {
      id: chip
      anchors.right: trailingSlot.left
      anchors.rightMargin: trailingSlot.width > 0 ? Style.space(8) : 0
      anchors.verticalCenter: parent.verticalCenter
      visible: card.status !== ""
      text: card.status
      color: card.toneColor
      font.family: card.fontFamily
      font.pixelSize: Style.font.caption
      font.bold: card.tone !== "idle"
    }

    Item {
      id: trailingSlot
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      width: childrenRect.width
      height: childrenRect.height
    }
  }
}
