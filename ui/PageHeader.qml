import QtQuick
import qs.Commons
import qs.Commons as Commons

// The title at the top of a settings page, and one line saying what the
// page is for -- so somebody who opened the wrong one knows at once.
Column {
  id: header

  property string title: ""
  property string subtitle: ""

  property color foreground: Commons.Color.foreground
  // Translucent rather than Qt.darker: darker is dimmer only on a dark
  // theme, and on a light one made every hint as black as the label.
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  spacing: Style.space(3)

  Text {
    width: parent.width
    text: header.title
    color: header.foreground
    font.family: header.fontFamily
    font.pixelSize: Style.font.title
    font.bold: true
    elide: Text.ElideRight
  }
  Text {
    width: parent.width
    visible: text !== ""
    text: header.subtitle
    wrapMode: Text.WordWrap
    color: header.dim
    font.family: header.fontFamily
    font.pixelSize: Style.font.caption
  }
}
