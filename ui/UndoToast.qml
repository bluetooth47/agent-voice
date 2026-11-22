import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// "Moved summarise to Sora.  Undo (8)" -- the way back from a move, for ten
// seconds. Hovering it stops the clock, so somebody reaching for Undo is
// not beaten to it; the clock counts real elapsed time otherwise, so a
// stalled event loop cannot stretch the offer past its deadline.
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
  property real lastTick: 0
  readonly property int remainingS: Math.ceil(remainingMs / 1000)

  signal undo()
  signal expired()

  function show(message) {
    text = message
    remainingMs = timeoutMs
    lastTick = Date.now()
    shown = true
    tick.restart()
  }
  function dismiss() {
    // Undo is about to be hidden: a focus left on it would go nowhere.
    if (undoButton.activeFocus) {
      var next = undoButton.nextItemInFocusChain(true)
      if (next && next !== undoButton) next.forceActiveFocus()
    }
    tick.stop()
    shown = false
  }
  // Spends the time that really passed since the last look, unless the
  // pointer is resting on the toast. True while the offer still stands.
  function stillOpen() {
    var now = Date.now()
    if (!hover.hovered) remainingMs -= now - lastTick
    lastTick = now
    if (remainingMs > 0) return true
    if (shown) { dismiss(); expired() }
    return false
  }

  Timer {
    id: tick
    interval: 250
    repeat: true
    onTriggered: toast.stillOpen()
  }
  HoverHandler { id: hover }

  visible: shown
  // From the children's natural widths: the message is narrowed to fit the
  // toast, so the row's laid-out width would only repeat the last answer.
  implicitWidth: message.implicitWidth + undoButton.implicitWidth + closeText.implicitWidth
                 + row.spacing * 2 + Style.space(20)
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
      id: message
      width: Math.max(0, Math.min(implicitWidth, parent.width - undoButton.width - closeText.width - parent.spacing * 2))
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
        // Checked at the moment of the click, not at the last tick.
        if (!toast.shown || !toast.stillOpen()) return
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
