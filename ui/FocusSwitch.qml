import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// Omarchy's ToggleSwitch, reachable from the keyboard (master plan M29).
//
// ToggleSwitch has no focus of its own: it is built to sit in a row whose
// panel keeps a keyboard cursor (`hasCursor`). The settings pages keep no
// such cursor, so every switch on them could be flipped only with a pointer,
// and settings search landing on one could only outline it (M28's open
// issue 2). This one takes Tab focus while shown, draws the switch's own
// cursor ring while it has it, flips on Space or Enter, and is a named check
// box to a screen reader. Every switch in pages/ and ui/ is one of these
// (tests/test_keyboard.py); ToggleRow names it after its label.
ToggleSwitch {
  id: sw

  property string accessibleName: ""

  function flip() { if (sw.enabled && !sw.busy) sw.toggled() }

  activeFocusOnTab: visible && enabled
  hasCursor: activeFocus
  Keys.onSpacePressed: sw.flip()
  Keys.onReturnPressed: sw.flip()
  Keys.onEnterPressed: sw.flip()

  Accessible.role: Accessible.CheckBox
  Accessible.name: accessibleName
  Accessible.checkable: true
  Accessible.checked: checked
  Accessible.focusable: true
  Accessible.onToggleAction: sw.flip()
  Accessible.onPressAction: sw.flip()

  // The accent outline every focusable piece here draws (TextLink, the
  // slider, a card's head): the switch's own cursor ring alone was faint on
  // both a dark and a light theme.
  Rectangle {
    anchors.fill: parent
    visible: sw.activeFocus
    color: "transparent"
    radius: Style.cornerRadius
    border.width: 1
    border.color: sw.accent
  }
}
