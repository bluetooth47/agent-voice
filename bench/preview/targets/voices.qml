// End to end on the Voice page's library and the main instructions, through
// real saves and the real `agentvoice voice` command. Run with --live-config:
//
//   preview.sh --live-config --wait 90 --out /tmp/v voices
//   grep PREVIEW /tmp/v.log
//
// It downloads one voice for real (en_GB-alba-medium, 63MB) and removes it
// again, and plays a few seconds of a sample through the speakers. It needs
// the installed engine to have `agentvoice voice` (install.sh first).
import QtQuick
import QtTest
import Quickshell
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open('{"page":"voice"}')

    TestEvent { id: input }

    property int passed: 0
    property int failed: 0
    function check(ok, what) {
      if (ok) passed++; else failed++
      console.warn("PREVIEW " + (ok ? "PASS " : "FAIL ") + what)
    }
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
    function findAll(item, test, out) {
      out = out || []
      if (!item) return out
      if (item.visible !== false && test(item)) out.push(item)
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) findAll(kids[i], test, out)
      return out
    }
    function content() { return overlay.pageScroll ? overlay.pageScroll.contentItem : null }
    function reveal(item) {
      var f = overlay.pageScroll
      if (!f || !item) return
      var y = item.mapToItem(f.contentItem, 0, 0).y
      f.contentY = Math.max(0, Math.min(y - 40, f.contentHeight - f.height))
    }
    function click(b, label) {
      if (!b) { check(false, "found " + label); return false }
      reveal(b)
      console.warn("PREVIEW click " + label)
      input.mouseClick(b, b.width / 2, b.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
      return true
    }
    function rows() {
      return findAll(content(), function(i) { return i.onDisk !== undefined && i.removable !== undefined })
    }
    function rowFor(name, detailHas) {
      var r = rows()
      for (var i = 0; i < r.length; i++)
        if (r[i].label === name && (!detailHas || r[i].detail.indexOf(detailHas) >= 0)) return r[i]
      return null
    }
    function buttonIn(root, prefix) {
      return find(root, function(i) { return i.clicked !== undefined && typeof i.text === "string"
                                              && i.text.indexOf(prefix) === 0 })
    }
    function chip(text) {
      return find(content(), function(i) { return i.text === text && i.clicked !== undefined })
    }

    property int warm: 0
    property int step: 0
    property real t0: 0
    property string target: "en_GB-alba-medium"

    Timer {
      interval: 1000
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        overlay.step++
        switch (overlay.step) {
        case 1:
          overlay.check(overlay.rows().length === overlay.rawVoiceOptions.length,
                        "the library lists all " + overlay.rawVoiceOptions.length + " voices (" + overlay.rows().length + ")")
          overlay.click(overlay.chip("British"), "filter British")
          break
        case 2:
          overlay.check(overlay.rows().length === 8, "British shows 8 (" + overlay.rows().length + ")")
          overlay.click(overlay.chip("Downloaded"), "filter Downloaded")
          break
        case 3:
          overlay.check(overlay.rows().length === overlay.voicesOnDisk.length,
                        "Downloaded shows what is on disk (" + overlay.rows().length + ")")
          overlay.check(overlay.rows().every(function(r) { return r.onDisk }), "and every one says so")
          var lessac = overlay.rowFor("Lessac", "medium")
          overlay.check(lessac && !lessac.removable, "the default voice cannot be removed")
          overlay.click(overlay.buttonIn(lessac, "▶ Test"), "test Lessac")
          break
        case 5:
          overlay.check(overlay.samplePlaying === "lessac-medium", "the sample is playing")
          var l5 = overlay.rowFor("Lessac", "medium")
          overlay.check(l5 && l5.playing, "and its row shows it")
          overlay.click(overlay.buttonIn(l5, "■ Stop"), "stop Lessac")
          break
        case 6:
          overlay.check(overlay.samplePlaying === "", "the sample stopped")
          overlay.click(overlay.chip("All"), "filter All")
          break
        case 7:
          var a = overlay.rowFor("Alba")
          overlay.check(a && !a.onDisk, "Alba is not on disk yet")
          overlay.click(overlay.buttonIn(a, "Download"), "download Alba")
          overlay.t0 = Date.now()
          break
        case 8:
          overlay.check(overlay.fetching === overlay.target, "the download started")
          break
        default:
          if (overlay.step < 60 && overlay.step > 8 && overlay.voicesOnDisk.indexOf(overlay.target) < 0) {
            if (overlay.step % 3 === 0) console.warn("PREVIEW downloading " + overlay.fetchPct + "%")
            break
          }
          if (overlay.step >= 9 && overlay.step < 100) {
            overlay.check(overlay.voicesOnDisk.indexOf(overlay.target) >= 0,
                          "Alba arrived in " + Math.round((Date.now() - overlay.t0) / 1000) + "s")
            overlay.check(overlay.fetchError === "", "with no error (" + overlay.fetchError + ")")
            var a2 = overlay.rowFor("Alba")
            overlay.check(a2 && a2.onDisk && a2.removable, "its row offers Test and Remove")
            // Use for the main agent: a real save of `voice`.
            overlay.assignVoice("", overlay.target)
            overlay.step = 100
          }
          break
        case 103:
          overlay.check(String(overlay.setting("voice", "")) === overlay.target, "Use for main saved the voice")
          var a3 = overlay.rowFor("Alba")
          overlay.check(a3 && a3.users === "main" && !a3.removable, "it shows as the main agent's, so not removable")
          overlay.assignVoice("", "lessac-medium")
          break
        case 106:
          var a4 = overlay.rowFor("Alba")
          overlay.check(a4 && a4.removable, "back to Lessac, Alba can be removed")
          overlay.click(overlay.find(a4, function(i) { return i.clicked !== undefined && i.tooltipText === "Delete it from this machine" }),
                        "remove Alba")
          break
        case 109:
          overlay.check(overlay.voicesOnDisk.indexOf(overlay.target) < 0, "Alba was removed")
          // The main card's instructions: a summary there, edited on Agent
          // details (Phase 12), through a real save.
          overlay.goTo("agents", "main")
          break
        case 111:
          var boxes = overlay.findAll(overlay.content(), function(i) { return i.committed !== undefined && i.maxLength !== undefined })
          overlay.check(boxes.length === 0, "the Agents page edits no file (boxes: " + boxes.length + ")")
          overlay.click(overlay.find(overlay.content(), function(i) { return i.text === "Edit in Agent details →" && i.clicked !== undefined }),
                        "Edit in Agent details")
          break
        case 112:
          overlay.check(overlay.page === "agentdetails" && overlay.detailsAgent === "main", "the link opens the main agent's details")
          var box = overlay.find(overlay.content(), function(i) { return i.committed !== undefined && i.maxLength === 2000 })
          overlay.check(box !== null, "with its instructions editor")
          if (box) box.committed("Call me Sam. Keep it short.")
          break
        case 114:
          // Saved to agents/main/instructions.md through `agentvoice agents`
          // (Phase 10), in the preview's scratch data folder, and read back
          // as the stamp the CLI returned; never to shell.json any more.
          var fold = overlay.find(overlay.content(), function(i) { return i.target === "main" && i.file === "instructions.md" && i.saved !== undefined })
          overlay.check(fold !== null && fold.saved === "Call me Sam. Keep it short." && fold.exists,
                        "the main instructions were saved to its folder and read back")
          overlay.check(String(overlay.setting("agentInstructions", "")) !== "Call me Sam. Keep it short.",
                        "nothing was written to the retired agentInstructions setting")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        }
      }
    }
  }
}
