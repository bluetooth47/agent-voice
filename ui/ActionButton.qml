import QtQuick
import qs.Commons
import qs.Ui

// Omarchy's Button, reachable from the keyboard and named for a screen
// reader. Every button on a page or in a ui/ piece is one of these (master
// plan M29, tests/test_keyboard.py).
//
// Omarchy's Button is `focusable: false` unless told otherwise, so Tab went
// past it: 29 buttons across the pages could be pressed only with a pointer
// (the Listening page's eight, the agent cards' Test and Change, the voice
// library's rows, the endpoint editor's). Setting `focusable: true` on each
// is the guard-per-caller shape CLAUDE.md warns about -- the next button
// added forgets it -- so it is set here, once, with the accessible name.
//
// A button inside a control that keeps its own keyboard cursor (a chip in
// SegmentedChoice, ToggleChips or TabStrip) stays a plain Button: the control
// takes the focus, the arrows move between its parts, and a Tab stop per chip
// would make a row of nine chips nine stops.
Button {
  id: action

  // What a screen reader says. The visible text, else the tooltip (an
  // icon-only button), unless the caller names it.
  property string accessibleName: ""

  focusable: true

  Accessible.role: Accessible.Button
  Accessible.name: accessibleName !== "" ? accessibleName : (text !== "" ? text : tooltipText)
  Accessible.description: text !== "" ? tooltipText : ""
  Accessible.focusable: true
  Accessible.onPressAction: if (action.enabled) action.clicked()
}
