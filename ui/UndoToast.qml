import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// "Moved summarise to Sora.  Undo (8)" -- the way back from a move, for ten
// seconds. Hovering it stops the clock, so somebody reaching for Undo is
// not beaten to it.
//
// It only offers: undo() is emitted and the page does the undoing, because
// only the page knows what was moved and from where. When the time runs out
// expired() is emitted and the offer is gone; Undo can never fire after
// that, which is the point of a deadline.
//
//   UndoToast { id: undo; onUndo: page.undoMove(lastMove) }
//   ... undo.show("Moved summarise to Sora.")
Rectangle {
  id: toast

  property string text: ""
  property string undoText: "Undo"
  property int timeoutMs: 10000
  property bool shown: false

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  property real remainingMs: 0
  readonly property int remainingS: Math.ceil(remainingMs / 1000)

  signal undo()
  signal expired()

  function show(message) {
    text = message
    remainingMs = timeoutMs
    shown = true
    tick.restart()
  }
  function dismiss() {
    tick.stop()
    shown = false
  }

  Timer {
    id: tick
    interval: 250
    repeat: true
    onTriggered: {
      if (hover.hovered) return
      toast.remainingMs -= interval
      if (toast.remainingMs <= 0) { toast.dismiss(); toast.expired() }
    }
  }
  HoverHandler { id: hover }

  visible: shown
  implicitWidth: row.implicitWidth + Style.space(20)
  implicitHeight: row.implicitHeight + Style.space(12)
  radius: Style.cornerRadius
  color: Commons.Color.popups.background
  border.width: 1
  border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.6)

  Keys.onEscapePressed: dismiss()

  Row {
    id: row
    x: Style.space(10)
    anchors.verticalCenter: parent.verticalCenter
    width: parent.width - Style.space(20)
    spacing: Style.space(10)
    Text {
      width: Math.min(implicitWidth, parent.width - undoButton.width - closeText.width - parent.spacing * 2)
      anchors.verticalCenter: parent.verticalCenter
      text: toast.text
      textFormat: Text.PlainText
      elide: Text.ElideRight
      color: toast.foreground
      font.family: toast.fontFamily
      font.pixelSize: Style.font.body
    }
    Button {
      id: undoButton
      anchors.verticalCenter: parent.verticalCenter
      text: toast.undoText + (toast.shown ? " (" + toast.remainingS + ")" : "")
      bordered: true
      focusable: true
      foreground: toast.foreground
      fontFamily: toast.fontFamily
      onClicked: {
        if (!toast.shown) return
        toast.dismiss()
        toast.undo()
      }
    }
    Text {
      id: closeText
      anchors.verticalCenter: parent.verticalCenter
      text: "×"
      color: closeArea.containsMouse ? toast.foreground : toast.dim
      font.family: toast.fontFamily
      font.pixelSize: Style.font.body
      MouseArea {
        id: closeArea
        anchors.fill: parent
        anchors.margins: -Style.space(5)
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: toast.dismiss()
      }
    }
  }
}
