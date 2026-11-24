import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// The small "Model: opus ▾" selector, the shape VS Code puts in a status
// bar: the current choice as text, the list one click away. For a choice
// that matters on a card but is not worth a full-width row (feedback item
// 8's "compact effort").
//
// `options` are what MenuList takes: strings or { value, label, detail,
// enabled }. As SegmentedChoice, the chosen value is held on screen until
// `value` arrives at it, so it does not flick back for the round trip
// through shell.json.
//
// A selector that cannot be used says why: set `disabledReason` and a click
// (or Enter) shows the reason instead of a list. Silence would look broken.
//
// Keyboard: one Tab stop; Enter, Space or Down opens the list.
FocusScope {
  id: sel

  property string label: ""
  property string value: ""
  property var options: []
  property string placeholder: "choose"
  // What a screen reader calls it when `label` is empty (master plan M29).
  property string accessibleName: ""
  property string disabledReason: ""
  property string tooltip: ""
  property int holdMs: 5000
  property bool framed: true

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  readonly property string shown: holding ? held : value
  property bool holding: false
  property string held: ""
  property bool reasonShown: false

  signal committed(string value)

  onValueChanged: if (holding && value === held) { holding = false; holdTimer.stop() }
  Timer { id: holdTimer; interval: sel.holdMs; onTriggered: sel.holding = false }
  Timer { id: reasonTimer; interval: 4000; onTriggered: sel.reasonShown = false }

  function labelFor(v) {
    for (var i = 0; i < options.length; i++) {
      var o = options[i]
      var ov = (o !== null && typeof o === "object") ? String(o.value) : String(o)
      if (ov === v) return (o !== null && typeof o === "object" && o.label !== undefined) ? String(o.label) : ov
    }
    return v
  }
  function open() {
    if (!enabled) return
    if (disabledReason !== "") { reasonShown = true; reasonTimer.restart(); return }
    menu.open()
  }

  activeFocusOnTab: true
  Accessible.role: Accessible.ComboBox
  Accessible.name: accessibleName !== "" ? accessibleName : (label !== "" ? label : placeholder)
  Accessible.description: disabledReason !== "" ? disabledReason : shown
  Accessible.focusable: true
  implicitWidth: natural
  implicitHeight: face.implicitHeight
  opacity: enabled && disabledReason === "" ? 1 : 0.5

  Keys.onReturnPressed: open()
  Keys.onEnterPressed: open()
  Keys.onSpacePressed: open()
  Keys.onDownPressed: open()

  // The natural width, from the texts' own implicit widths: the row cannot
  // be asked, because the value text is narrowed to fit the row.
  readonly property real pad: Style.space(framed ? 8 : 3)
  readonly property real natural: (labelText.visible ? labelText.implicitWidth + row.spacing : 0)
                                  + valueText.implicitWidth + row.spacing + caret.implicitWidth + pad * 2

  Rectangle {
    id: face
    implicitWidth: sel.natural
    implicitHeight: row.implicitHeight + Style.space(8)
    width: sel.width
    height: sel.height
    radius: Style.cornerRadius
    color: area.containsMouse || sel.activeFocus || menu.opened
           ? Style.hoverFillFor(sel.foreground, sel.accent) : "transparent"
    border.width: sel.activeFocus ? 1 : (sel.framed ? 1 : 0)
    border.color: sel.activeFocus ? sel.accent
                                  : Qt.rgba(sel.foreground.r, sel.foreground.g, sel.foreground.b, 0.18)

    Row {
      id: row
      anchors.verticalCenter: parent.verticalCenter
      x: sel.pad
      spacing: Style.space(4)
      Text {
        id: labelText
        visible: sel.label !== ""
        text: sel.label + ":"
        textFormat: Text.PlainText
        color: sel.dim
        font.family: sel.fontFamily
        font.pixelSize: Style.font.caption
        anchors.verticalCenter: parent.verticalCenter
      }
      Text {
        id: valueText
        text: sel.shown !== "" ? sel.labelFor(sel.shown) : sel.placeholder
        textFormat: Text.PlainText
        elide: Text.ElideRight
        width: Math.max(0, Math.min(implicitWidth, face.width - sel.natural + implicitWidth))
        color: sel.shown !== "" ? sel.foreground : sel.dim
        font.family: sel.fontFamily
        font.pixelSize: Style.font.caption
        font.bold: sel.shown !== ""
        anchors.verticalCenter: parent.verticalCenter
      }
      Text {
        id: caret
        text: "▾"
        color: sel.dim
        font.family: sel.fontFamily
        font.pixelSize: Style.font.caption
        anchors.verticalCenter: parent.verticalCenter
      }
    }
    MouseArea {
      id: area
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: { sel.forceActiveFocus(); sel.open() }
    }
  }

  Tip {
    tipText: sel.reasonShown ? sel.disabledReason : sel.tooltip
    shown: sel.reasonShown || (area.containsMouse && sel.tooltip !== "")
    fontFamily: sel.fontFamily
  }

  MenuList {
    id: menu
    y: sel.height + Style.space(2)
    entries: sel.options
    current: sel.shown
    fontFamily: sel.fontFamily
    onPicked: function(v) {
      if (v === sel.shown) return
      sel.held = v
      sel.holding = v !== sel.value
      if (sel.holding) holdTimer.restart()
      sel.committed(v)
    }
    onClosed: if (menu.heldFocus()) sel.forceActiveFocus()
  }
}
