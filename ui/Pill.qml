import QtQuick
import qs.Commons
import qs.Commons as Commons

// A small rounded label: "codex", "edits", "quarantined", "3 skills".
//
// `tone` as StatusCard and HeaderStrip spell it: "idle" (dim), "active"
// (the text colour), "busy" (accent) or "alert" (urgent). Plain text: a pill
// often shows a name somebody typed.
Rectangle {
  id: pill

  property string text: ""
  property string tone: "idle"
  property string tooltip: ""
  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  readonly property color toneColor: tone === "alert" ? urgent
                                     : tone === "busy" ? accent
                                     : tone === "active" ? foreground : dim

  visible: text !== ""
  implicitWidth: label.implicitWidth + Style.space(14)
  implicitHeight: label.implicitHeight + Style.space(4)
  radius: height / 2
  color: Qt.rgba(toneColor.r, toneColor.g, toneColor.b, 0.12)
  border.width: 1
  border.color: Qt.rgba(toneColor.r, toneColor.g, toneColor.b, 0.45)

  Text {
    id: label
    anchors.centerIn: parent
    width: Math.min(implicitWidth, pill.width - Style.space(10))
    text: pill.text
    textFormat: Text.PlainText
    elide: Text.ElideRight
    color: pill.toneColor
    font.family: pill.fontFamily
    font.pixelSize: Style.font.caption
  }
  MouseArea {
    id: area
    anchors.fill: parent
    enabled: pill.tooltip !== ""
    hoverEnabled: true
    acceptedButtons: Qt.NoButton
  }
  Tip { tipText: pill.tooltip; shown: area.containsMouse; fontFamily: pill.fontFamily }
}
