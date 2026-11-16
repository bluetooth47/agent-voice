import QtQuick
import qs.Commons
// Namespaced as well: on Qt 6.12 a bare `Color` resolves to QtQuick's own
// value-type helper, not to the theme, and every colour read through it was
// undefined. Omarchy's own QML writes Commons.Color for the same reason.
import qs.Commons as Commons
import qs.Ui
import "ui"

// A labelled slider that reports its value with a unit and only commits on
// release, so dragging does not fire `omarchy bar set` on every frame.
//
// The slider is ui/VoiceSlider rather than Omarchy's PanelSlider, which
// snapped back to the old value on release, let the handle and the number
// disagree mid-drag, and could be left stuck mid-drag by the scrolling page
// (see VoiceSlider for the measurements). The number beside the label can be
// clicked and typed into.
Column {
  id: knob

  // Kept so existing callers that pass it still load. Unused: VoiceSlider
  // reads the theme itself.
  property QtObject bar: null
  property color foreground: Commons.Color.foreground
  // Translucent rather than Qt.darker: darker is dimmer only on a dark
  // theme, and on a light one made every hint as black as the label.
  property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  property string label: ""
  property string description: ""
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

  // The Flickable a wheel over the slider scrolls. Found by walking up when
  // not given.
  property Flickable scrollTarget: null

  signal committed(real value)

  readonly property real shown: slider.shown

  function display(v) {
    if (labels.length > 0)
      return String(labels[Math.max(0, Math.min(labels.length - 1, Math.round(v - minimum)))])
    return Math.round(v) + unit
  }

  spacing: Style.space(2)

  Item {
    width: parent.width
    height: Math.max(labelText.implicitHeight, valueText.implicitHeight, entry.implicitHeight)

    Text {
      id: labelText
      anchors.left: parent.left
      anchors.right: valueBox.left
      anchors.verticalCenter: parent.verticalCenter
      text: knob.label
      color: knob.foreground
      font.family: knob.fontFamily
      font.pixelSize: Style.font.body
      elide: Text.ElideRight
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
        color: valueHover.containsMouse ? knob.foreground : knob.dim
        font.family: knob.fontFamily
        font.pixelSize: Style.font.body
        font.underline: valueHover.containsMouse && knob.labels.length === 0
        MouseArea {
          id: valueHover
          anchors.fill: parent
          anchors.margins: -Style.space(4)
          hoverEnabled: true
          enabled: knob.labels.length === 0 && knob.enabled
          cursorShape: Qt.IBeamCursor
          onClicked: {
            entry.text = String(Math.round(knob.shown))
            entry.visible = true
            entry.forceActiveFocus()
            entry.selectAll()
          }
        }
      }

      // Type an exact number. Enter saves (snapped to the step and clamped),
      // Escape or clicking away leaves it as it was.
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
        validator: IntValidator { bottom: -1000000; top: 1000000 }
        onAccepted: {
          var v = parseInt(text, 10)
          visible = false
          if (!isNaN(v)) slider.choose(v)
        }
        Keys.onEscapePressed: visible = false
        onActiveFocusChanged: if (!activeFocus) visible = false
      }
    }
  }

  VoiceSlider {
    id: slider
    width: parent.width
    enabled: knob.enabled
    value: knob.value
    minimum: knob.minimum
    maximum: knob.maximum
    stepSize: knob.stepSize
    defaultValue: knob.defaultValue
    foreground: knob.foreground
    scrollTarget: knob.scrollTarget
    onCommitted: function(v) { knob.committed(v) }
  }

  Text {
    width: parent.width
    visible: knob.description !== ""
    wrapMode: Text.WordWrap
    text: knob.description
    color: knob.dim
    font.family: knob.fontFamily
    font.pixelSize: Style.font.caption
    bottomPadding: Style.space(4)
  }
}
