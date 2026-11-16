// The slider bugs, reproduced. A KnobRow inside a short scrolling list, the
// way Settings.qml holds them, with the shell.json round trip faked: a
// commit lands back in `value` 800ms later, about what `omarchy bar set`
// plus the jq reload takes. Every 40ms it logs what the handle shows
// (PanelSlider.liveValue), what the label shows (KnobRow.shown) and whether
// the slider thinks it is still being dragged.
//
// It drives itself with synthetic mouse events (QtTest's TestEvent, delivered
// through the window like real ones, grabs and all), so nobody's real pointer
// moves. Run with --wait 8 and read the PREVIEW lines in the log:
//   1.5s  drag from 20% to 63% of the track and let go
//   4.0s  drag diagonally, the way a hand does, inside the scrolling list
//   5.5s  shell.json changes underneath it (value := 12000)
import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons as Commons
import qs.Ui
import QtTest
import "plugin"

ShellRoot {
  Backdrop { }

  PanelWindow {
    id: win
    color: "transparent"
    WlrLayershell.namespace: "agentvoice-preview-knob"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }

    Rectangle {
      id: card
      width: 500; height: 300
      anchors.centerIn: parent
      color: Commons.Color.background
      border.color: Commons.Color.foreground

      Flickable {
        id: list
        anchors.fill: parent
        anchors.margins: 20
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        Column {
          id: column
          width: parent.width
          spacing: 20
          KnobRow {
            id: knob
            objectName: "knob"
            width: parent.width
            label: "Time to start speaking"
            minimum: 1000; maximum: 15000; stepSize: 500
            value: 5000
            onCommitted: function(v) {
              console.warn("PREVIEW commit", Date.now() % 100000, v)
              pending = v
              roundTrip.restart()
            }
            property real pending: 0
          }
          Rectangle { width: parent.width; height: 600; color: "transparent" }
        }
      }
    }

    Timer {
      id: roundTrip; interval: 800
      onTriggered: { knob.value = knob.pending; console.warn("PREVIEW landed", Date.now() % 100000, knob.value) }
    }

    function slider(node) {
      if (!node) return null
      // PanelSlider has liveValue; ui/VoiceSlider has shown.
      if (node.dragging !== undefined && (node.liveValue !== undefined || node.knobSize !== undefined)) return node
      for (var i = 0; i < node.children.length; i++) {
        var s = slider(node.children[i]); if (s) return s
      }
      return null
    }

    property string last: ""
    Timer {
      interval: 40; running: true; repeat: true
      onTriggered: {
        var s = win.slider(knob)
        if (!s) return
        var line = "handle=" + Math.round(s.liveValue !== undefined ? s.liveValue : s.shown) + " label=" + Math.round(knob.shown)
                   + " value=" + knob.value + " dragging=" + s.dragging
                   + " listY=" + Math.round(list.contentY)
        if (line !== win.last) console.warn("PREVIEW", Date.now() % 100000, line)
        win.last = line
      }
    }

    TestEvent { id: input }

    function external(v) { knob.value = v }

    function at(fraction) {
      var s = slider(knob)
      // PanelSlider insets the track by half the handle on each side.
      return s.knobSize / 2 + (s.width - s.knobSize) * fraction
    }
    property var steps: []
    function run(t, f) { steps.push({ t: t, f: f }) }

    Component.onCompleted: {
      var w = this
      run(1500, function() { var s = w.slider(knob); console.warn("PREVIEW A press 20%"); input.mousePress(s, w.at(0.2), s.height / 2, Qt.LeftButton, Qt.NoModifier, -1) })
      for (var i = 1; i <= 10; i++) (function(i) {
        run(1500 + i * 50, function() { var s = w.slider(knob); input.mouseMove(s, w.at(0.2 + 0.043 * i), s.height / 2, -1, Qt.LeftButton, Qt.NoModifier) })
      })(i)
      run(2200, function() { var s = w.slider(knob); console.warn("PREVIEW A release 63%"); input.mouseRelease(s, w.at(0.63), s.height / 2, Qt.LeftButton, Qt.NoModifier, -1) })
      run(4000, function() { var s = w.slider(knob); console.warn("PREVIEW B press 30%"); input.mousePress(s, w.at(0.3), s.height / 2, Qt.LeftButton, Qt.NoModifier, -1) })
      for (var j = 1; j <= 15; j++) (function(j) {
        run(4000 + j * 20, function() { var s = w.slider(knob); input.mouseMove(s, w.at(0.3) + j * 8, s.height / 2 - j * 5, -1, Qt.LeftButton, Qt.NoModifier) })
      })(j)
      run(4400, function() { var s = w.slider(knob); console.warn("PREVIEW B release"); input.mouseRelease(s, w.at(0.3) + 120, s.height / 2 - 75, Qt.LeftButton, Qt.NoModifier, -1) })
      run(5500, function() { win.external(12000); console.warn("PREVIEW external set 12000") })
      started = Date.now()
      clock.start()
    }

    // One clock running the schedule, rather than a Timer per step.
    property real started: 0
    property int next: 0
    Timer {
      id: clock
      interval: 10
      repeat: true
      onTriggered: {
        var t = Date.now() - win.started
        while (win.next < win.steps.length && win.steps[win.next].t <= t) {
          win.steps[win.next].f()
          win.next++
        }
        if (win.next >= win.steps.length) stop()
      }
    }
  }
}
