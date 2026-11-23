// Drives every control on the Conversation page and logs what each wrote, to
// compare the page before and after a redesign (master plan M24: "the same
// keys and values"). Page-agnostic: controls are found by their label (the
// old and new wording both listed), folds are opened wherever there are any,
// and a knob is driven through its own `committed` signal, which is what a
// slider release emits.
//
//   preview.sh --config bench/preview/configs/agents1.json \
//     --state bench/preview/states/showcase.json --scratch-data \
//     --size 1100x760 --wait 40 --out /tmp/cc conversationclicks
//   grep -a 'bar set\|agentvoice' /tmp/cc.writes | sort > /tmp/cc.after
//
// Run once in a checkout of the old page and once in the new one, and diff.
import QtQuick
import QtTest
import Quickshell
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open('{"page":"conversation"}')

    TestEvent { id: input }

    function find(item, test) {
      if (!item || item.visible === false || item.opacity === 0) return null
      if (test(item)) return item
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) {
        var hit = find(kids[i], test)
        if (hit) return hit
      }
      return null
    }
    function poke(name, value) { overlay[name] = value }
    function content() { return overlay.pageScroll ? overlay.pageScroll.contentItem : null }
    function click(item, label) {
      if (!item) { console.warn("PREVIEW miss " + label); return }
      var flick = overlay.pageScroll
      if (flick && content()) {
        var y = item.mapToItem(content(), 0, 0).y
        flick.contentY = Math.max(0, Math.min(y - 160, flick.contentHeight - flick.height))
      }
      console.warn("PREVIEW click " + label)
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    // A fold has a `flip` and an `expanded`: opened wherever there is one.
    function openFolds() {
      var n = 0
      var again = true
      while (again) {
        again = false
        var f = find(content(), function(i) { return i.expanded === false && i.flip !== undefined && i.summary !== undefined })
        if (f && n++ < 12) { f.expanded = true; again = true }
      }
    }
    function toggleFor(labels) {
      var row = find(content(), function(i) {
        return i.label !== undefined && labels.indexOf(String(i.label)) >= 0 && i.checked !== undefined && i.toggled !== undefined
      })
      if (!row) { console.warn("PREVIEW miss toggle " + labels[0]); return }
      click(find(row, function(i) { return i.trackWidth !== undefined && i.toggled !== undefined }), "toggle " + labels[0])
    }
    function knobFor(label, value) {
      var k = find(content(), function(i) { return i.label === label && i.stepSize !== undefined && i.committed !== undefined })
      if (!k) { console.warn("PREVIEW miss knob " + label); return }
      console.warn("PREVIEW knob " + label + " " + value)
      k.committed(value)
    }
    function chipFor(text) {
      click(find(content(), function(i) { return i.clicked !== undefined && i.text === text }), "chip " + text)
    }
    // The pace: a row of chips on the old page, a selector and its menu on the new one.
    function menuOf(sel) {
      var d = sel ? sel.data : []
      for (var i = 0; i < d.length; i++) if (d[i] && d[i].entries !== undefined && d[i].choose !== undefined) return d[i]
      return null
    }
    property var pending: null
    function pace(label, value) {
      var sel = find(content(), function(i) { return i.objectName === "paceChoice" })
      if (!sel) { chipFor(label); return }
      click(sel, "pace selector")
      pending = sel
    }
    function paceChoose(value) {
      var m = menuOf(pending)
      if (!m) { console.warn("PREVIEW miss pace menu"); return }
      for (var i = 0; i < m.entries.length; i++)
        if (String(m.entries[i].value) === value) { console.warn("PREVIEW pace " + value); m.choose(i); return }
    }

    property int step: 0
    property int warm: 0
    Timer {
      interval: 1500
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        overlay.step++
        switch (overlay.step) {
        case 1:
          // The full-stop switch is only live on sherpa-onnx; the engine
          // write is in both runs' logs.
          overlay.poke("sherpaAvailable", true)
          overlay.put("engine", "sherpa")
          overlay.openFolds()
          break
        case 2: overlay.pace("Snappy", "snappy"); break
        case 3: if (overlay.pending) overlay.paceChoose("snappy"); break
        case 4: overlay.toggleFor(["Keep listening after a reply"]); break
        case 5: overlay.knobFor("Follow-up window", 9000); break
        case 6: overlay.knobFor("Closes after", 20); break
        case 7: overlay.toggleFor(["Only answer if it's meant for you"]); break
        case 8: overlay.toggleFor(["Open the mic after every wake"]); break
        case 9: overlay.chipFor("Own clause"); break
        case 10: overlay.chipFor("Detailed"); break
        case 11: overlay.knobFor("Quiet before it says anything", 12); break
        case 12: overlay.knobFor("Time to start speaking", 6500); break
        case 13: overlay.knobFor("Pause that ends a turn", 1500); break
        case 14: overlay.knobFor("Shorter pause when you sound finished", 600); break
        case 15: overlay.knobFor("Ignore a turn shorter than", 500); break
        case 16: overlay.knobFor("Longest a turn can be", 60000); break
        case 17: overlay.toggleFor(["“Full stop” works without the wake word", "Stop everything by voice, without the wake word"]); break
        case 18: overlay.toggleFor(["Interrupt by talking, on a headset"]); break
        case 19: overlay.toggleFor(["On speakers too"]); break
        case 20: overlay.knobFor("How much louder you must be", 200); break
        case 21: overlay.knobFor("Deaf period after speaking", 500); break
        case 22: console.warn("PREVIEW DONE"); break
        }
      }
    }
  }
}
