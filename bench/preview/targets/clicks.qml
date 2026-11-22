// Clicks through the settings overlay with synthetic mouse events and logs
// what each click wrote, to prove the controls are wired to the right keys
// rather than only drawn. Writes go to the preview's stubbed `omarchy bar
// set` log (<out>.writes), never to shell.json.
//
//   preview.sh --wait 12 --out /tmp/c.png clicks; cat /tmp/c.png.writes
import QtQuick
import QtTest
import Quickshell
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open('{"page":"display"}')

    TestEvent { id: input }

    function find(item, test) {
      if (!item) return null
      if (item.visible !== false && test(item)) return item
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) {
        var hit = find(kids[i], test)
        if (hit) return hit
      }
      return null
    }
    function click(item, label) {
      if (!item) { console.warn("PREVIEW miss " + label); return }
      // Scrolled into view first: a control below the fold is outside the
      // window, and a synthetic click there lands on nothing. The Voice
      // page's model chips sit under a 31-voice library, which is how this
      // target came to report a miss that was not one.
      var flick = overlay.pageScroll
      if (flick && content()) {
        var y = item.mapToItem(content(), 0, 0).y
        flick.contentY = Math.max(0, Math.min(y - 120, flick.contentHeight - flick.height))
      }
      console.warn("PREVIEW click " + label)
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function content() { return overlay.pageScroll ? overlay.pageScroll.contentItem : null }

    property int step: 0
    Timer {
      interval: 1200
      repeat: true
      running: true
      onTriggered: {
        overlay.step++
        var c = overlay.content()
        if (overlay.step === 2) {
          // The first switch on Display: the readout.
          overlay.click(overlay.find(c, function(i) { return i.trackWidth !== undefined && i.toggled !== undefined }), "first switch on Display (hud)")
        } else if (overlay.step === 3) {
          overlay.goTo("voice", "")
        } else if (overlay.step === 4) {
          overlay.click(overlay.find(c, function(i) { return i.text === "small.en" && i.clicked !== undefined }), "small.en chip")
        } else if (overlay.step === 5) {
          overlay.goTo("conversation", "")
        } else if (overlay.step === 6) {
          overlay.click(overlay.find(c, function(i) { return i.text === "Snappy" && i.clicked !== undefined }), "Snappy preset")
        } else if (overlay.step === 7) {
          // Phase M4: commands inside a sentence.
          overlay.click(overlay.find(c, function(i) { return i.text === "Own clause" && i.clicked !== undefined }), "Own clause (commandsInSentences)")
        } else if (overlay.step === 8) {
          overlay.goTo("agents", "main")
        } else if (overlay.step === 9) {
          overlay.click(overlay.find(c, function(i) { return i.text === "Ask first" && i.clicked !== undefined }), "Ask first")
        }
      }
    }
  }
}
