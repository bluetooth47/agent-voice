import QtQuick
import qs.Commons
import qs.Commons as Commons

// A label and a value on one line, the row the About page's tables are made
// of (master plan M26). The value is always plain text: it can hold a remote's
// URL, an agent's name or a model's, none of which is markup.
Item {
  id: infoRow

  property string label: ""
  property string value: ""
  // False draws the value in the urgent colour: something to act on.
  property bool ok: true
  property real labelWidth: Style.space(150)

  property color foreground: Commons.Color.foreground
  property color urgent: Commons.Color.urgent
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  width: parent ? parent.width : 0
  implicitHeight: Math.max(rowLabel.implicitHeight, rowValue.implicitHeight)
  height: implicitHeight

  Text {
    id: rowLabel
    width: infoRow.labelWidth
    wrapMode: Text.Wrap
    text: infoRow.label
    textFormat: Text.PlainText
    color: infoRow.foreground
    font.family: infoRow.fontFamily
    font.pixelSize: Style.font.caption
  }
  Text {
    id: rowValue
    anchors.left: rowLabel.right
    anchors.right: parent.right
    wrapMode: Text.WordWrap
    text: infoRow.value
    textFormat: Text.PlainText
    color: infoRow.ok ? infoRow.dim : infoRow.urgent
    font.family: infoRow.fontFamily
    font.pixelSize: Style.font.caption
  }
}
