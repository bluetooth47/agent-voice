import QtQuick
import qs.Commons
import qs.Commons as Commons

// One number on the Overview (feedback item 7): "142 / turns today", with a
// line of context under it. The number is text, not a count this piece
// formats, so "1.6 s" and "—" (nothing measured yet) read the same way.
//
//   StatTile { value: "142"; label: "turns today"; caption: "↑ 12 on yesterday" }
Rectangle {
  id: tile

  property string value: "—"
  property string label: ""
  property string caption: ""
  property string tooltip: ""
  property string tone: "active"

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  readonly property color toneColor: tone === "alert" ? urgent
                                     : tone === "busy" ? accent
                                     : tone === "active" ? foreground : dim

  implicitWidth: Math.max(Style.space(110), column.implicitWidth + Style.space(20))
  implicitHeight: column.implicitHeight + Style.space(20)
  radius: Style.cornerRadius
  color: "transparent"
  border.width: 1
  border.color: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.18)

  Column {
    id: column
    x: Style.space(10)
    y: Style.space(10)
    width: parent.width - Style.space(20)
    spacing: Style.space(2)
    Text {
      width: parent.width
      text: tile.value
      textFormat: Text.PlainText
      elide: Text.ElideRight
      color: tile.toneColor
      font.family: tile.fontFamily
      font.pixelSize: Math.round(Style.font.body * 1.8)
      font.bold: true
    }
    Text {
      width: parent.width
      text: tile.label
      textFormat: Text.PlainText
      elide: Text.ElideRight
      color: tile.foreground
      font.family: tile.fontFamily
      font.pixelSize: Style.font.caption
    }
    Hint {
      width: parent.width
      text: tile.caption
      detail: tile.tooltip
      foreground: tile.foreground
      fontFamily: tile.fontFamily
    }
  }
}
