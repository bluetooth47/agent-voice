import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// Starters for an empty box (phase M6, feedback item 10): "Start from:" and
// one button per template, each showing its text on hover. A click hands
// the text up; the page puts it in the box, where it can be changed before
// it is ever told to anyone, and saves it the way the box saves typing.
//
// `starters`: [{ id, label, text }], from `agentvoice agents templates`.
Flow {
  id: row

  property var starters: []
  property string title: "Start from:"
  property color foreground: Commons.Color.foreground
  property string fontFamily: Style.font.family

  signal picked(string text)

  spacing: Style.space(6)
  width: parent ? parent.width : 300

  Text {
    height: Style.spacing.controlHeight
    verticalAlignment: Text.AlignVCenter
    text: row.title
    textFormat: Text.PlainText
    color: row.foreground
    opacity: 0.6
    font.family: row.fontFamily
    font.pixelSize: Style.font.caption
  }
  Repeater {
    model: row.starters
    Button {
      required property var modelData
      text: String(modelData.label || modelData.id)
      tooltipText: String(modelData.text || "")
      bordered: true
      focusable: true
      foreground: row.foreground
      fontFamily: row.fontFamily
      fontSize: Style.font.caption
      onClicked: row.picked(String(modelData.text || ""))
    }
  }
}
