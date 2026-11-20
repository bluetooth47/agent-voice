import QtQuick
import qs.Commons
import qs.Commons as Commons

// What an agent is told, piece by piece and in order, each piece labelled
// with where it comes from (merged plan, Phase 12: "the most important
// control against confusion in the plan"). Read only.
//
// `parts` is [{ label, from, text, note }]: `from` in words ("From
// Communal · rules"), `note` for a piece with no text to show (the Omarchy
// commands). Every text is someone's file, so it is drawn as plain text.
Column {
  id: pv

  property var parts: []
  property color foreground: Commons.Color.foreground
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  spacing: Style.space(10)
  width: parent ? parent.width : 300

  Repeater {
    model: pv.parts

    Column {
      required property var modelData
      required property int index
      width: pv.width
      spacing: Style.space(3)

      Row {
        width: parent.width
        spacing: Style.space(8)
        Text {
          id: partLabel
          text: (index + 1) + ". " + String(modelData.label || "")
          textFormat: Text.PlainText
          color: pv.foreground
          font.family: pv.fontFamily
          font.pixelSize: Style.font.body
          font.bold: true
        }
        Text {
          anchors.baseline: partLabel.baseline
          text: String(modelData.from || "")
          textFormat: Text.PlainText
          color: pv.dim
          font.family: pv.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
      Text {
        width: parent.width
        visible: text !== ""
        leftPadding: Style.space(10)
        wrapMode: Text.WrapAtWordBoundaryOrAnywhere
        textFormat: Text.PlainText
        text: String(modelData.text || "") !== "" ? String(modelData.text) : String(modelData.note || "")
        color: String(modelData.text || "") !== "" ? pv.foreground : pv.dim
        opacity: String(modelData.text || "") !== "" ? 0.85 : 1
        font.family: pv.fontFamily
        font.pixelSize: Style.font.bodySmall
        Rectangle {
          width: Math.max(1, Style.space(2))
          height: parent.height
          color: Qt.rgba(pv.foreground.r, pv.foreground.g, pv.foreground.b, 0.25)
        }
      }
    }
  }
}
