import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// Tabs across the top of a page: `options` is [{ id, label }], `current` an
// id. Wraps onto a second line at a narrow width rather than running off the
// edge, which Omarchy's ButtonGroup (one Row) would.
//
// Keyboard: one Tab stop; Left/Right (or h/l) move and pick, the way the
// sidebar's Up/Down do.
FocusScope {
  id: strip

  property var options: []
  property string current: ""
  // What a screen reader calls it (master plan M29).
  property string accessibleName: ""
  property color foreground: Commons.Color.foreground
  property string fontFamily: Style.font.family

  signal picked(string id)

  activeFocusOnTab: true
  Accessible.role: Accessible.PageTabList
  Accessible.name: accessibleName !== "" ? accessibleName : "Tabs"
  Accessible.description: {
    for (var i = 0; i < options.length; i++) if (options[i].id === current) return "Open: " + options[i].label
    return ""
  }
  Accessible.focusable: true
  implicitHeight: flow.implicitHeight
  width: parent ? parent.width : 300

  function step(d) {
    if (options.length === 0) return
    var i = 0
    for (var k = 0; k < options.length; k++) if (options[k].id === current) i = k
    i = Math.max(0, Math.min(options.length - 1, i + d))
    picked(options[i].id)
  }
  Keys.onLeftPressed: step(-1)
  Keys.onRightPressed: step(1)
  Keys.onPressed: function(e) {
    if (e.key === Qt.Key_H) { step(-1); e.accepted = true }
    else if (e.key === Qt.Key_L) { step(1); e.accepted = true }
  }

  Flow {
    id: flow
    width: parent.width
    spacing: Style.space(6)

    Repeater {
      model: strip.options

      Button {
        required property var modelData
        text: modelData.label
        selected: modelData.id === strip.current
        // The focus ring sits on the chosen tab while the strip has focus.
        hasCursor: strip.activeFocus && modelData.id === strip.current
        bordered: true
        foreground: strip.foreground
        fontFamily: strip.fontFamily
        onClicked: { strip.forceActiveFocus(); strip.picked(modelData.id) }
      }
    }
  }
}
