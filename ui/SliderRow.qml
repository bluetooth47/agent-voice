import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// One numeric setting: the label, "?" and "reset" on the left and the
// number on the right, the slider underneath, and one short line saying
// what it does -- a SettingRow with a slider in it. It commits only on
// release, so dragging does not fire `omarchy bar set` on every frame.
//
// Master plan M29: this was the root-level KnobRow, the last setting row
// not built from ui/. It drew its own header beside SettingRow's, so the two
// drifted (a label that rendered markup, a "?" and a "reset" the keyboard
// could not reach, no way to say why a slider did not apply). It now has
// SettingRow's shape and words: `hint` under the slider, `disabledReason`
// in place of it with the row dimmed, the explanation folded behind "?".
//
// The slider is ui/VoiceSlider rather than Omarchy's PanelSlider, which
// snapped back to the old value on release, let the handle and the number
// disagree mid-drag, and could be left stuck mid-drag by the scrolling page
// (see VoiceSlider for the measurements). The number can be typed: click it,
// or press Enter on the slider.
//
//   SliderRow {
//     width: parent.width
//     label: "Follow-up window"
//     hint: "How long it keeps listening after speaking."
//     value: s.setting("followUpMs", 7000); minimum: 0; maximum: 30000; stepSize: 500
//     changed: s.changed("followUpMs")
//     onCommitted: function(v) { s.put("followUpMs", Math.round(v)) }
//     onReset: s.resetKey("followUpMs")
//   }
Column {
  id: knob

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  // Translucent rather than Qt.darker: darker is dimmer only on a dark
  // theme, and on a light one made every hint as black as the label.
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  property string label: ""
  property string hint: ""
  // The long explanation, folded behind a "?" beside the label.
  property string help: ""
  property bool helpOpen: false
  // Why the slider does not apply right now. Shown in place of the hint,
  // with the row dimmed and the slider disabled, as SettingRow does.
  property string disabledReason: ""
  readonly property bool applies: disabledReason === ""
  // Shows a "reset" link beside the label; clicking it emits reset().
  property bool changed: false
  signal reset()
  property real value: 0
  property real minimum: 0
  property real maximum: 1
  property real stepSize: 1
  property string unit: "ms"
  // NaN for none. When set, a double click on the slider goes back to it.
  property real defaultValue: NaN
  // Names for the notches, from `minimum` up, for a slider that picks one of
  // a few named choices rather than a number. Shown in place of the number,
  // and the number cannot be typed.
  property var labels: []
  // For a setting stored in whole steps of a smaller unit (master plan M23:
  // the gate's rates are tenths of a dB/s, because the bar schema has no
  // float type): the number is shown, and typed, divided by this, to
  // `decimals` places. 1 is the plain whole number it always was.
  property real displayDivisor: 1
  property int decimals: 0

  // The Flickable a wheel over the slider scrolls. Found by walking up when
  // not given.
  property Flickable scrollTarget: null

  signal committed(real value)

  readonly property real shown: slider.shown

  function display(v) {
    if (labels.length > 0)
      return String(labels[Math.max(0, Math.min(labels.length - 1, Math.round(v - minimum)))])
    if (displayDivisor !== 1)
      return (v / displayDivisor).toFixed(decimals) + unit
    return Math.round(v) + unit
  }

  // Open the box for typing an exact number.
  function startTyping() {
    if (labels.length > 0 || !enabled || !applies) return
    entry.text = displayDivisor !== 1 ? (shown / displayDivisor).toFixed(decimals)
                                      : String(Math.round(shown))
    entry.visible = true
    entry.forceActiveFocus()
    entry.selectAll()
  }

  spacing: Style.space(2)

  Item {
    width: parent.width
    height: Math.max(labelText.implicitHeight, valueText.implicitHeight, entry.implicitHeight)
    opacity: knob.applies ? 1 : 0.5

    Row {
      anchors.left: parent.left
      anchors.right: valueBox.left
      anchors.rightMargin: Style.space(8)
      anchors.verticalCenter: parent.verticalCenter
      spacing: Style.space(8)

      Text {
        id: labelText
        width: Math.min(implicitWidth, parent.width - extras.width - parent.spacing)
        text: knob.label
        textFormat: Text.PlainText
        color: knob.foreground
        font.family: knob.fontFamily
        font.pixelSize: Style.font.body
        // Two lines before it is cut, as SettingRow's label.
        wrapMode: Text.Wrap
        maximumLineCount: 2
        elide: Text.ElideRight
      }

      Row {
        id: extras
        anchors.verticalCenter: labelText.verticalCenter
        spacing: Style.space(8)

        TextLink {
          visible: knob.help !== ""
          text: knob.helpOpen ? "×" : "?"
          lit: knob.helpOpen
          foreground: knob.foreground
          accent: knob.accent
          dim: knob.dim
          font.family: knob.fontFamily
          accessibleName: (knob.helpOpen ? "Hide what " : "Explain ") + knob.label
          onActivated: knob.helpOpen = !knob.helpOpen
        }
        TextLink {
          visible: knob.changed && knob.enabled && knob.applies
          text: "reset"
          foreground: knob.foreground
          accent: knob.accent
          dim: knob.dim
          font.family: knob.fontFamily
          accessibleName: "Reset " + knob.label
          onActivated: knob.reset()
        }
      }
    }

    Item {
      id: valueBox
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      width: entry.visible ? entry.width : valueText.implicitWidth
      height: parent.height

      Text {
        id: valueText
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        visible: !entry.visible
        text: knob.display(knob.shown)
        textFormat: Text.PlainText
        color: valueHover.containsMouse ? knob.foreground : knob.dim
        font.family: knob.fontFamily
        font.pixelSize: Style.font.body
        font.underline: valueHover.containsMouse && knob.labels.length === 0
        MouseArea {
          id: valueHover
          anchors.fill: parent
          anchors.margins: -Style.space(4)
          hoverEnabled: true
          enabled: knob.labels.length === 0 && knob.enabled && knob.applies
          cursorShape: Qt.IBeamCursor
          onClicked: knob.startTyping()
        }
      }

      // Type an exact number. Enter saves (snapped to the step and clamped),
      // Escape or clicking away leaves it as it was; either way the keyboard
      // goes back to the slider.
      TextInput {
        id: entry
        visible: false
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: Style.space(70)
        horizontalAlignment: TextInput.AlignRight
        color: knob.foreground
        selectionColor: Commons.Color.accent
        selectedTextColor: Commons.Color.background
        font.family: knob.fontFamily
        font.pixelSize: Style.font.body
        Accessible.role: Accessible.EditableText
        Accessible.name: knob.label + (knob.unit !== "" ? ", in " + knob.unit.trim() : "")
        property IntValidator whole: IntValidator { bottom: -1000000; top: 1000000 }
        property RegularExpressionValidator decimal: RegularExpressionValidator {
          regularExpression: /-?[0-9]{0,6}([.][0-9]{0,3})?/
        }
        validator: knob.displayDivisor !== 1 ? decimal : whole
        onAccepted: {
          // Typed in the units shown; saved in the setting's own steps.
          var v = knob.displayDivisor !== 1 ? Math.round(parseFloat(text) * knob.displayDivisor)
                                            : parseInt(text, 10)
          visible = false
          slider.forceActiveFocus()
          if (!isNaN(v)) slider.choose(v)
        }
        Keys.onEscapePressed: function(e) { visible = false; slider.forceActiveFocus(); e.accepted = true }
        onActiveFocusChanged: if (!activeFocus) visible = false
      }
    }
  }

  VoiceSlider {
    id: slider
    width: parent.width
    enabled: knob.enabled && knob.applies
    value: knob.value
    minimum: knob.minimum
    maximum: knob.maximum
    stepSize: knob.stepSize
    defaultValue: knob.defaultValue
    foreground: knob.foreground
    scrollTarget: knob.scrollTarget
    accessibleName: knob.label
    valueText: knob.display(knob.shown)
    onCommitted: function(v) { knob.committed(v) }
    onTypeWanted: knob.startTyping()
  }

  Text {
    width: parent.width
    visible: text !== ""
    wrapMode: Text.WordWrap
    text: knob.applies ? knob.hint : knob.disabledReason
    textFormat: Text.PlainText
    color: knob.dim
    font.family: knob.fontFamily
    font.pixelSize: Style.font.caption
    bottomPadding: Style.space(4)
  }

  Text {
    width: parent.width
    visible: knob.helpOpen && knob.help !== ""
    text: knob.help
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    color: knob.dim
    font.family: knob.fontFamily
    font.pixelSize: Style.font.caption
    leftPadding: Style.space(8)
    bottomPadding: Style.space(4)
    Rectangle {
      width: Math.max(1, Style.space(2))
      height: parent.height
      color: Qt.rgba(knob.foreground.r, knob.foreground.g, knob.foreground.b, 0.25)
    }
  }
}
