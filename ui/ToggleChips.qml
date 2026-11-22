import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// A row of on/off chips: tools an agent may use, traits of a personality.
//
// `options`: [{ value, label, tooltip, disabledReason }].
// `chipStates`: { value: "on" | "off" | "inherit" }. A value missing from it is
//            "inherit" when `allowInherit`, else "off" -- the safe reading,
//            since a switch nobody set must not turn something on.
// `inherited`: { value: true | false }, what "inherit" currently resolves to,
//            drawn as a lighter fill (on) or plain (off) with a tooltip.
//
// A click cycles on → off, or, with `allowInherit`, inherit → on → off →
// inherit. A disabled chip stays visible and focusable, and choosing it
// shows its reason under the row instead of doing nothing silently.
//
// Keyboard: one Tab stop; Left/Right (or h/l) move between chips, Space or
// Enter flips the one under the cursor.
FocusScope {
  id: chips

  property var options: []
  // Not `states`: every Item already has one, for its State list.
  property var chipStates: ({})
  property var inherited: ({})
  property bool allowInherit: false
  property string inheritLabel: "inherited"

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  property int cursor: 0
  property string why: ""

  signal toggled(string value, string state)

  function stateOf(v) {
    var s = chipStates ? chipStates[v] : undefined
    if (s === "on" || s === "off") return s
    if (s === "inherit" && allowInherit) return "inherit"
    return allowInherit ? "inherit" : "off"
  }
  function effectiveOn(v) {
    var s = stateOf(v)
    return s === "on" || (s === "inherit" && inherited && inherited[v] === true)
  }
  function nextState(s) {
    if (!allowInherit) return s === "on" ? "off" : "on"
    return s === "inherit" ? "on" : s === "on" ? "off" : "inherit"
  }
  function flip(i) {
    if (i < 0 || i >= options.length) return
    cursor = i
    var o = options[i]
    if (String(o.disabledReason || "") !== "") {
      why = String(o.label || o.value) + ": " + String(o.disabledReason)
      whyTimer.restart()
      return
    }
    why = ""
    toggled(String(o.value), nextState(stateOf(String(o.value))))
  }
  function tipFor(o) {
    var parts = []
    if (o.tooltip) parts.push(String(o.tooltip))
    if (o.disabledReason) parts.push(String(o.disabledReason))
    var v = String(o.value)
    if (stateOf(v) === "inherit") parts.push("Follows the shared setting: " + (inherited && inherited[v] === true ? "on" : "off"))
    return parts.join("\n")
  }

  Timer { id: whyTimer; interval: 6000; onTriggered: chips.why = "" }
  // A shorter list must not leave the cursor on a chip that is gone.
  onOptionsChanged: cursor = Math.max(0, Math.min(cursor, options.length - 1))

  activeFocusOnTab: true
  implicitHeight: column.implicitHeight
  width: parent ? parent.width : 300

  Keys.onLeftPressed: cursor = Math.max(0, cursor - 1)
  Keys.onRightPressed: cursor = Math.min(options.length - 1, cursor + 1)
  Keys.onSpacePressed: flip(cursor)
  Keys.onReturnPressed: flip(cursor)
  Keys.onEnterPressed: flip(cursor)
  Keys.onPressed: function(e) {
    if (e.key === Qt.Key_H) { cursor = Math.max(0, cursor - 1); e.accepted = true }
    else if (e.key === Qt.Key_L) { cursor = Math.min(options.length - 1, cursor + 1); e.accepted = true }
  }

  Column {
    id: column
    width: parent.width
    spacing: Style.space(4)

    Flow {
      width: parent.width
      spacing: Style.space(6)
      Repeater {
        model: chips.options
        Button {
          id: chip
          required property var modelData
          required property int index
          readonly property string st: chips.stateOf(String(modelData.value))
          readonly property bool off: String(modelData.disabledReason || "") !== ""
          text: String(modelData.label || modelData.value) + (st === "inherit" ? " · " + chips.inheritLabel : "")
          selected: st === "on"
          active: st === "inherit" && chips.effectiveOn(String(modelData.value))
          hasCursor: chips.activeFocus && index === chips.cursor
          bordered: true
          opacity: off ? 0.45 : 1
          tooltipText: chips.tipFor(modelData)
          foreground: chips.foreground
          accent: chips.accent
          fontFamily: chips.fontFamily
          fontSize: Style.font.caption
          onClicked: { chips.forceActiveFocus(); chips.flip(index) }
        }
      }
    }
    Text {
      width: parent.width
      visible: chips.why !== ""
      text: chips.why
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: chips.urgent
      font.family: chips.fontFamily
      font.pixelSize: Style.font.caption
    }
  }
}
