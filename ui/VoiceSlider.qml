import QtQuick
import qs.Commons
import qs.Commons as Commons

// A slider for a setting: snaps to its step while you drag, holds what you
// chose until the setting comes back, and is never left half-dragged.
//
// Omarchy's PanelSlider is built for live values (volume, brightness) and
// three of its behaviours are wrong for a setting that takes a round trip
// through shell.json. Each was measured with bench/preview `knob`:
//
//   - the handle went back to the old value the moment you let go and only
//     jumped forward when shell.json caught up (5000 for ~800ms after a
//     release at 10000). Here the released value is *held* until `value`
//     arrives at it, or until `holdMs` passes without it, which means the
//     write failed and the real value is the right thing to show.
//   - the handle moved continuously while the number snapped to the step
//     (handle 9821, label 10000). Here the handle snaps too.
//   - a drag that wandered vertically was taken by the scrolling page; the
//     slider never heard the release, stayed "dragging" for good, saved
//     nothing, and ignored every later change of `value`. Here the drag
//     cannot be stolen (preventStealing), and a cancelled one is put back.
//
// It also reads the theme itself (PanelSlider fell back to a hardcoded #333
// track without a bar, which on a light theme left the filled and empty
// parts the same dark grey), takes the keyboard, and resets to
// `defaultValue` on a double click.
//
// The wheel scrolls the page rather than changing the value: a settings list
// is scrolled past sliders far more often than it is adjusted with a wheel,
// and a wheel over a slider used to change a setting nobody meant to touch.
Item {
  id: slider

  property real value: 0
  property real minimum: 0
  property real maximum: 100
  property real stepSize: 1
  // NaN for none. When set, a double click goes back to it.
  property real defaultValue: NaN
  property int holdMs: 5000

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color background: Commons.Color.background

  // What the handle is showing right now: the drag, the held release, or
  // the value. Read this for a label beside the slider.
  readonly property real shown: dragging ? dragValue : (holding ? heldValue : value)
  readonly property bool dragging: mouse.pressed && _dragging
  readonly property bool holding: _holding

  // What a screen reader calls it, and how it reads the value (M29).
  property string accessibleName: ""
  property string valueText: ""

  // While dragging, every notch crossed.
  signal moved(real value)
  // Enter on a focused slider: the row beside it offers to type the number
  // (ui/SliderRow), which the pointer reaches by clicking the number.
  signal typeWanted()
  // Once per choice: on release, on a key (after a short pause), on reset.
  signal committed(real value)

  // The Flickable a wheel event should scroll. Found by walking up when not
  // given.
  property Flickable scrollTarget: null

  implicitWidth: Style.space(200)
  implicitHeight: Math.max(Style.space(24), knobSize + Style.space(8))
  activeFocusOnTab: enabled
  opacity: enabled ? 1 : 0.4

  Accessible.role: Accessible.Slider
  Accessible.name: accessibleName
  Accessible.description: valueText
  Accessible.focusable: true
  Accessible.onIncreaseAction: nudge(1)
  Accessible.onDecreaseAction: nudge(-1)

  readonly property real knobSize: Math.max(14, Math.round(Style.spacing.controlHeight * 0.38))
  readonly property real trackHeight: Math.max(4, Math.round(Style.spacing.controlHeight * 0.11))
  readonly property real range: Math.max(0.0001, maximum - minimum)
  readonly property int notches: Math.round(range / Math.max(0.0001, stepSize))
  readonly property real progress: Math.max(0, Math.min(1, (shown - minimum) / range))
  readonly property bool hot: mouse.containsMouse || dragging || activeFocus

  property bool _dragging: false
  property bool _holding: false
  property real dragValue: value
  property real heldValue: value
  property real keyValue: value

  function snap(v) {
    var n = Math.round((v - minimum) / stepSize)
    return Math.max(minimum, Math.min(maximum, minimum + n * stepSize))
  }

  function valueAt(x) {
    var w = track.width
    if (w <= 0) return minimum
    var f = Math.max(0, Math.min(1, (x - track.x) / w))
    return snap(minimum + f * range)
  }

  function hold(v) {
    heldValue = v
    _holding = !same(v, value)
    if (_holding) holdTimer.restart()
  }

  function same(a, b) { return Math.abs(a - b) < stepSize / 2 }

  function choose(v) {
    v = snap(v)
    hold(v)
    if (!same(v, value)) committed(v)
  }

  onValueChanged: {
    // The write arrived. Anything else arriving while held is either a stale
    // read from before it or somebody else's change; both resolve when the
    // hold does, so the handle does not jump about in between.
    if (_holding && same(value, heldValue)) {
      _holding = false
      holdTimer.stop()
    }
  }

  Timer {
    id: holdTimer
    interval: slider.holdMs
    onTriggered: slider._holding = false
  }

  function scroller() {
    if (scrollTarget) return scrollTarget
    var p = slider.parent
    while (p) {
      if (p instanceof Flickable) return p
      p = p.parent
    }
    return null
  }

  // --- drawing ------------------------------------------------------------------

  Rectangle {
    id: track
    anchors.verticalCenter: parent.verticalCenter
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.leftMargin: slider.knobSize / 2
    anchors.rightMargin: slider.knobSize / 2
    height: slider.trackHeight
    radius: height / 2
    color: Style.selectedFillFor(slider.foreground, slider.accent)
  }

  Rectangle {
    anchors.verticalCenter: track.verticalCenter
    anchors.left: track.left
    height: track.height
    radius: track.radius
    color: slider.foreground
    width: track.width * slider.progress
    Behavior on width {
      enabled: !slider.dragging
      NumberAnimation { duration: Style.duration(120); easing.type: Easing.OutCubic }
    }
  }

  // Notches, when there are few enough to mean something.
  Repeater {
    model: slider.notches > 0 && slider.notches <= 16 ? slider.notches + 1 : 0
    Rectangle {
      required property int index
      width: Math.max(1, Style.space(2))
      height: slider.trackHeight + Style.space(6)
      radius: 1
      anchors.verticalCenter: track.verticalCenter
      x: track.x + track.width * index / slider.notches - width / 2
      color: index / slider.notches <= slider.progress
             ? slider.foreground : Style.selectedFillFor(slider.foreground, slider.accent)
    }
  }

  Rectangle {
    id: knob
    width: slider.knobSize
    height: slider.knobSize
    radius: width / 2
    anchors.verticalCenter: track.verticalCenter
    x: track.x + track.width * slider.progress - width / 2
    color: slider.foreground
    border.width: Math.max(1, Style.space(2))
    border.color: slider.activeFocus ? slider.accent : slider.background
    scale: slider.hot ? 1.15 : 1.0
    Behavior on x {
      enabled: !slider.dragging
      NumberAnimation { duration: Style.duration(120); easing.type: Easing.OutCubic }
    }
    Behavior on scale { NumberAnimation { duration: Style.duration(100) } }
  }

  // --- input --------------------------------------------------------------------

  MouseArea {
    id: mouse
    anchors.fill: parent
    hoverEnabled: true
    enabled: slider.enabled
    cursorShape: Qt.PointingHandCursor
    // The fix for the stuck drag: a scrolling page can no longer take the
    // gesture half way, so the release always comes back here.
    preventStealing: true

    onPressed: function(m) {
      slider.forceActiveFocus()
      slider._dragging = true
      slider.dragValue = slider.valueAt(m.x)
      slider.moved(slider.dragValue)
    }
    onPositionChanged: function(m) {
      if (!slider._dragging) return
      var v = slider.valueAt(m.x)
      if (!slider.same(v, slider.dragValue)) {
        slider.dragValue = v
        slider.moved(v)
      }
    }
    onReleased: function(m) {
      if (!slider._dragging) return
      slider._dragging = false
      slider.choose(slider.valueAt(m.x))
    }
    // Should not happen with preventStealing, but if anything else takes the
    // pointer, nothing was chosen: go back rather than stay mid-drag.
    onCanceled: slider._dragging = false

    onDoubleClicked: {
      if (!isNaN(slider.defaultValue)) slider.choose(slider.defaultValue)
    }

    onWheel: function(w) {
      var f = slider.scroller()
      if (!f) { w.accepted = false; return }
      w.accepted = true
      var limit = Math.max(0, f.contentHeight - f.height)
      f.contentY = Math.max(0, Math.min(limit, f.contentY - w.angleDelta.y))
    }
  }

  // Keys move the handle at once and save after a pause, so holding an arrow
  // down is one write rather than one per repeat.
  Timer {
    id: keyCommit
    interval: 450
    onTriggered: slider.choose(slider.keyValue)
  }
  function nudge(steps) {
    var from = keyCommit.running ? keyValue : shown
    keyValue = snap(from + steps * stepSize)
    hold(keyValue)
    _holding = true
    holdTimer.restart()
    keyCommit.restart()
  }
  Keys.onLeftPressed: nudge(-1)
  Keys.onRightPressed: nudge(1)
  Keys.onPressed: function(e) {
    if (e.key === Qt.Key_PageUp) { nudge(Math.max(1, Math.round(notches / 10))); e.accepted = true }
    else if (e.key === Qt.Key_PageDown) { nudge(-Math.max(1, Math.round(notches / 10))); e.accepted = true }
    else if (e.key === Qt.Key_Home) { nudge(-notches); e.accepted = true }
    else if (e.key === Qt.Key_End) { nudge(notches); e.accepted = true }
    else if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter) { slider.typeWanted(); e.accepted = true }
  }
}
