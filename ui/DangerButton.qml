import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// A button that destroys something, and the one way to ask "really?".
//
// The first click does nothing but *arm* it: the button is replaced, in
// place, by a strip that names what will happen ("Really remove Theo?") with
// Cancel and the action side by side. It disarms by itself after `armMs`
// (6 s), on Escape, on Cancel, or when it is disabled while armed. Cancel
// has the keyboard focus, so an Enter that was meant for something else
// cancels rather than destroys. Never a modal: nothing else on the page is
// blocked while it waits.
//
// The action runs only in `onConfirmed`. That is a rule the tests hold
// (tests/test_settings_pages.py): every destructive verb a page can run
// appears inside an onConfirmed handler, so a plain onClicked cannot reach
// one by accident. Before this piece each page grew its own "click again"
// flag and timer -- three copies, three timeouts, and none could be
// cancelled from the keyboard.
//
//   DangerButton {
//     text: "Remove"
//     question: "Really remove " + name + "?"
//     confirmText: "Remove"
//     onConfirmed: s.folders.remove(index)
//   }
FocusScope {
  id: danger

  property string text: ""
  property string iconText: "\u{f0a7a}"
  property string question: "Really?"
  property string confirmText: "Yes"
  property string cancelText: "Cancel"
  property string tooltipText: ""
  property int armMs: 6000
  property bool busy: false
  // The widest the armed strip may be. A long name wraps the question (two
  // lines at most, then elided, the whole of it in a tooltip) and moves
  // the buttons under it, so Cancel and Confirm never run off the page.
  // A caller in a column of known width passes that width.
  property real maxWidth: Style.space(360)

  property color foreground: Commons.Color.foreground
  property color urgent: Commons.Color.urgent
  property string fontFamily: Style.font.family

  readonly property bool armed: _armed
  property bool _armed: false
  // True from arming until Cancel has the focus: the idle button hides
  // under the focus in between, which is not "focus left".
  property bool _settling: false

  signal confirmed()
  signal cancelled()

  function arm() {
    if (!enabled || busy) return
    _armed = true
    _settling = true
    disarmTimer.restart()
    // After the strip exists: Cancel takes the focus, so the next Enter
    // cancels.
    Qt.callLater(function() {
      if (danger._armed) cancelButton.forceActiveFocus()
      danger._settling = false
    })
  }
  function disarm() {
    if (!_armed) return
    var hadFocus = cancelButton.activeFocus || confirmButton.activeFocus
    _armed = false
    disarmTimer.stop()
    refocus(hadFocus)
    cancelled()
  }
  function confirm() {
    if (!_armed || !enabled || busy) return
    var hadFocus = cancelButton.activeFocus || confirmButton.activeFocus
    _armed = false
    disarmTimer.stop()
    refocus(hadFocus)
    confirmed()
  }
  // The strip's buttons are hidden once it disarms; focus left on a hidden
  // item goes nowhere on the next Tab (found by the gallery's keyboard
  // walk), so it comes back to the button it started on.
  function refocus(hadFocus) {
    if (hadFocus && idle.visible) idle.forceActiveFocus()
  }

  onEnabledChanged: if (!enabled) disarm()
  onBusyChanged: if (busy) disarm()
  onVisibleChanged: if (!visible) disarm()
  // Tabbing (or clicking) away disarms it, so an Escape pressed elsewhere is
  // never needed to put it back (Codex review, M1).
  onActiveFocusChanged: if (!activeFocus && _armed && !_settling) disarm()

  Timer { id: disarmTimer; interval: danger.armMs; onTriggered: danger.disarm() }

  implicitWidth: _armed ? strip.implicitWidth : idle.implicitWidth
  implicitHeight: _armed ? strip.implicitHeight : idle.implicitHeight
  width: implicitWidth
  height: implicitHeight

  Keys.onEscapePressed: function(e) {
    if (danger._armed) { danger.disarm(); e.accepted = true } else e.accepted = false
  }

  Button {
    id: idle
    visible: !danger._armed
    // The warning sign says "this destroys something" before it is clicked;
    // the action's own icon waits for the strip.
    text: "⚠ " + danger.text
    tooltipText: danger.tooltipText
    bordered: true
    focusable: true
    enabled: danger.enabled && !danger.busy
    opacity: enabled ? 1 : 0.45
    foreground: danger.foreground
    accent: danger.urgent
    fontFamily: danger.fontFamily
    onClicked: danger.arm()
  }

  Flow {
    id: strip
    visible: danger._armed
    spacing: Style.space(8)
    // From natural widths only, so nothing here depends on its own result.
    width: Math.min(danger.maxWidth, question.implicitWidth + cancelButton.implicitWidth
                                     + confirmButton.implicitWidth + spacing * 2)

    Text {
      id: question
      width: Math.min(implicitWidth, strip.width)
      height: Math.max(implicitHeight, cancelButton.implicitHeight)
      verticalAlignment: Text.AlignVCenter
      text: danger.question
      // The question often holds a name somebody typed.
      textFormat: Text.PlainText
      wrapMode: Text.Wrap
      maximumLineCount: 2
      elide: Text.ElideRight
      color: danger.urgent
      font.family: danger.fontFamily
      font.pixelSize: Style.font.body
      MouseArea {
        id: questionArea
        anchors.fill: parent
        enabled: question.truncated
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
      }
      Tip { tipText: question.truncated ? danger.question : ""; shown: questionArea.containsMouse; fontFamily: danger.fontFamily }
    }
    Button {
      id: cancelButton
      text: danger.cancelText
      bordered: true
      focusable: true
      foreground: danger.foreground
      fontFamily: danger.fontFamily
      onClicked: danger.disarm()
      KeyNavigation.right: confirmButton
    }
    Button {
      id: confirmButton
      text: danger.confirmText
      iconText: danger.iconText
      bordered: true
      focusable: true
      foreground: danger.urgent
      accent: danger.urgent
      fontFamily: danger.fontFamily
      onClicked: danger.confirm()
      KeyNavigation.left: cancelButton
    }
  }
}
