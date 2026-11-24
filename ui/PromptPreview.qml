import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// What an agent is told, piece by piece and in order, each piece labelled
// with where it comes from (merged plan, Phase 12: "the most important
// control against confusion in the plan"). Read only.
//
// `parts` is [{ label, from, text, note, how, chars }]: `from` in words
// ("From Communal · rules"), `note` for a piece with no text to show (the
// Omarchy commands); since M15 (Communal → Preview) `how`, a line on how the
// piece stands against the others, and `chars`, its size, both optional.
// Every text is someone's file, so it is drawn as plain text.
//
// `concealed` (M16, Agent details → Advanced): each piece shows its label,
// source and size, and its text only once its own Show is pressed (or
// `revealAll` is set), so the whole prompt is never on screen by accident.
Column {
  id: pv

  property var parts: []
  property bool concealed: false
  property bool revealAll: false
  // Indexes whose Show was pressed. Replaced, never changed in place, so the
  // bindings below notice.
  property var revealed: ({})
  onPartsChanged: revealed = ({})
  function shown(i) { return !concealed || revealAll || revealed[i] === true }
  function toggle(i) {
    var next = {}
    for (var k in revealed) next[k] = revealed[k]
    next[i] = !(revealed[i] === true)
    revealed = next
  }
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
          text: String(modelData.from || "") +
                (modelData.chars !== undefined ? " · " + modelData.chars + " characters" : "")
          textFormat: Text.PlainText
          color: pv.dim
          font.family: pv.fontFamily
          font.pixelSize: Style.font.caption
        }
        ActionButton {
          anchors.verticalCenter: partLabel.verticalCenter
          visible: pv.concealed && !pv.revealAll && String(modelData.text || "") !== ""
          text: pv.revealed[index] === true ? "Hide" : "Show"
          focusable: true
          foreground: pv.foreground
          fontFamily: pv.fontFamily
          fontSize: Style.font.caption
          onClicked: pv.toggle(index)
        }
      }
      Text {
        width: parent.width
        visible: text !== ""
        leftPadding: Style.space(10)
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: String(modelData.how || "")
        color: pv.dim
        font.family: pv.fontFamily
        font.pixelSize: Style.font.caption
        font.italic: true
      }
      Text {
        width: parent.width
        visible: text !== ""
        leftPadding: Style.space(10)
        wrapMode: Text.WrapAtWordBoundaryOrAnywhere
        textFormat: Text.PlainText
        text: String(modelData.text || "") !== "" ? (pv.shown(index) ? String(modelData.text) : "")
                                                  : String(modelData.note || "")
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
