import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// Pick one of a few named choices, all on screen at once: effort, the live
// transcript mode, the wake engine. A slider implied there was something
// between "high" and "max"; a dropdown hid the choices behind a click.
//
// Omarchy's ButtonGroup draws the chips and handles the keyboard (one Tab
// stop, Left/Right between chips, Enter picks). What this adds is the label
// and the same hold as VoiceSlider: the chosen chip stays chosen until
// `value` arrives at it rather than flicking back for the round trip.
//
// `options` is what ButtonGroup takes: strings, or {value, label, tooltip}.
// Values are strings; a caller with a number converts both ways.
Column {
  id: choice

  property string label: ""
  property string description: ""
  property var options: []
  property string value: ""
  property int holdMs: 5000

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  // Translucent rather than Qt.darker: darker is dimmer only on a dark
  // theme, and on a light one made every hint as black as the label.
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  readonly property string shown: holding ? held : value
  property bool holding: false
  property string held: ""

  signal committed(string value)

  onValueChanged: if (holding && value === held) { holding = false; holdTimer.stop() }

  Timer { id: holdTimer; interval: choice.holdMs; onTriggered: choice.holding = false }

  spacing: Style.space(4)
  opacity: enabled ? 1 : 0.4

  Text {
    width: parent.width
    visible: choice.label !== ""
    text: choice.label
    color: choice.foreground
    font.family: choice.fontFamily
    font.pixelSize: Style.font.body
    elide: Text.ElideRight
  }

  ButtonGroup {
    options: choice.options
    value: choice.shown
    foreground: choice.foreground
    accent: choice.accent
    fontFamily: choice.fontFamily
    enabled: choice.enabled
    onChanged: function(v) {
      if (v === choice.shown) return
      choice.held = v
      choice.holding = v !== choice.value
      if (choice.holding) holdTimer.restart()
      choice.committed(v)
    }
  }

  Text {
    width: parent.width
    visible: choice.description !== ""
    wrapMode: Text.WordWrap
    text: choice.description
    color: choice.dim
    font.family: choice.fontFamily
    font.pixelSize: Style.font.caption
  }
}
