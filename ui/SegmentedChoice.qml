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
//
// `wrap: true` (with a width set, as a stacked SettingRow sets it): when the
// chips do not fit on one line they wrap onto the next instead of running
// past the edge. For half-width cards (M5), where "Ask first | Edits are fine
// | Trust everything" is wider than the card. Off by default, because a
// control on the right of a SettingRow gets its width from its own size, and
// measuring against that would chase itself.
Column {
  id: choice

  property string label: ""
  property string description: ""
  property var options: []
  property string value: ""
  property int holdMs: 5000
  property bool wrap: false

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

  function pick(v) {
    if (v === choice.shown) return
    choice.held = v
    choice.holding = v !== choice.value
    if (choice.holding) holdTimer.restart()
    choice.committed(v)
  }
  readonly property bool wraps: wrap && width > 0 && measure.implicitWidth > width

  Item {
    width: choice.wraps ? choice.width : group.implicitWidth
    implicitWidth: group.implicitWidth
    height: choice.wraps ? flow.implicitHeight : group.implicitHeight

    // The width the chips want on one line, drawn nowhere and never
    // focused: the visible group cannot be asked once it is hidden. First,
    // so it sits under the real chips and can never take a click.
    ButtonGroup {
      id: measure
      visible: choice.wrap
      opacity: 0
      enabled: false
      focusable: false
      height: 0
      options: choice.options
      fontFamily: choice.fontFamily
    }

    ButtonGroup {
      id: group
      visible: !choice.wraps
      options: choice.options
      value: choice.shown
      foreground: choice.foreground
      accent: choice.accent
      fontFamily: choice.fontFamily
      enabled: choice.enabled
      onChanged: function(v) { choice.pick(v) }
    }

    // The same chips, wrapping. One Tab stop; Left/Right (h/l) walk the
    // chips and Enter or Space picks, as ButtonGroup does.
    Flow {
      id: flow
      visible: choice.wraps
      width: choice.width
      spacing: Style.spacing.md
      activeFocusOnTab: visible
      property int cursor: -1
      onActiveFocusChanged: {
        cursor = -1
        if (!activeFocus) return
        for (var i = 0; i < choice.options.length; i++)
          if (group.optionValue(choice.options[i]) === choice.shown) cursor = i
        if (cursor < 0) cursor = 0
      }
      Keys.onPressed: function(e) {
        if (e.key === Qt.Key_Left || e.key === Qt.Key_H) { flow.cursor = Math.max(0, flow.cursor - 1); e.accepted = true }
        else if (e.key === Qt.Key_Right || e.key === Qt.Key_L) {
          flow.cursor = Math.min(choice.options.length - 1, flow.cursor + 1); e.accepted = true
        } else if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) {
          if (flow.cursor >= 0 && flow.cursor < choice.options.length)
            choice.pick(group.optionValue(choice.options[flow.cursor]))
          e.accepted = true
        }
      }
      Repeater {
        model: choice.wraps ? choice.options : []
        Button {
          required property var modelData
          required property int index
          text: group.optionLabel(modelData)
          iconText: group.optionIcon(modelData)
          tooltipText: group.optionTooltip(modelData)
          selected: group.optionValue(modelData) === choice.shown
          hasCursor: flow.activeFocus && flow.cursor === index
          bordered: true
          foreground: choice.foreground
          accent: choice.accent
          fontFamily: choice.fontFamily
          enabled: choice.enabled
          onClicked: choice.pick(group.optionValue(modelData))
        }
      }
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
