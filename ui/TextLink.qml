import QtQuick
import qs.Commons
import qs.Commons as Commons

// A small word that does something when clicked: the "?" that unfolds a
// setting's explanation and the "reset" beside a changed one.
//
// Master plan M29's keyboard pass: these were a Text with a MouseArea, so
// nothing reached them from the keyboard, and a setting could be reset or
// explained only with a pointer. A TextLink takes Tab focus while shown,
// answers Enter and Space, draws an outline while it has the focus, and has
// a name for a screen reader ("Reset Follow-up window", not "reset").
//
//   TextLink { text: "reset"; accessibleName: "Reset " + label; onActivated: reset() }
Text {
  id: link

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  // Drawn at full strength while true (the "×" of an open explanation).
  property bool lit: false
  property string accessibleName: ""

  signal activated()

  textFormat: Text.PlainText
  color: hover.containsMouse || activeFocus || lit ? foreground : dim
  font.family: Style.font.family
  font.pixelSize: Style.font.caption
  font.underline: hover.containsMouse || activeFocus

  activeFocusOnTab: visible && enabled
  Keys.onReturnPressed: link.activated()
  Keys.onEnterPressed: link.activated()
  Keys.onSpacePressed: link.activated()

  Accessible.role: Accessible.Button
  Accessible.name: accessibleName !== "" ? accessibleName : text
  Accessible.focusable: true
  Accessible.onPressAction: link.activated()

  Rectangle {
    anchors.fill: parent
    anchors.margins: -Style.space(3)
    visible: link.activeFocus
    color: "transparent"
    radius: Style.cornerRadius
    border.width: 1
    border.color: link.accent
  }

  MouseArea {
    id: hover
    anchors.fill: parent
    anchors.margins: -Style.space(5)
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onClicked: link.activated()
  }
}
