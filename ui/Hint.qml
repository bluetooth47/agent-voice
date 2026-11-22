import QtQuick
import qs.Commons
import qs.Commons as Commons

// One plain line under a control, with the rest in a tooltip.
//
// The rule for the redesign (feedback item 17): what a control does fits on
// one line; why, and the exceptions, are there on hover. A dotted underline
// says there is more. `tone: "warn"` draws the line in the urgent colour, for
// a hint that is a warning rather than a description.
//
//   Hint { width: parent.width; text: "Runs without asking."; detail: "…" }
Text {
  id: hint

  property string detail: ""
  property string tone: ""
  property color foreground: Commons.Color.foreground
  property color urgent: Commons.Color.urgent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  visible: text !== ""
  textFormat: Text.PlainText
  elide: Text.ElideRight
  maximumLineCount: 1
  color: tone === "warn" ? urgent : dim
  font.family: fontFamily
  font.pixelSize: Style.font.caption
  font.underline: detail !== "" && area.containsMouse

  MouseArea {
    id: area
    anchors.fill: parent
    enabled: hint.detail !== "" || hint.truncated
    hoverEnabled: true
    acceptedButtons: Qt.NoButton
  }
  // Truncated text gets its whole self as the tooltip too, so a narrow
  // window never hides the end of a sentence for good.
  Tip {
    tipText: hint.detail !== "" ? (hint.truncated ? hint.text + "\n\n" : "") + hint.detail
                                : (hint.truncated ? hint.text : "")
    shown: area.containsMouse
    fontFamily: hint.fontFamily
  }
}
