// Other settings (master plan M26): reached through the old "display" id,
// the readout with the Agents panel, privacy (the journal switch asks first),
// the keys read live, and Maintenance (Repair, Remove).
//
//   preview.sh --config bench/preview/configs/voice.json --state \
//     bench/preview/states/showcase.json --scratch-data --size 1100x760 \
//     --wait 30 --out /tmp/other other
//   grep PREVIEW /tmp/other.log; cat /tmp/other.writes
//
// Nothing real is touched: `omarchy bar set` goes to the scratch shell.json,
// the keys come from preview.sh's synthetic bindings.lua and fake hyprctl,
// and Repair, Remove and Open bindings file reach logging stubs.
//
// --arg:
//   walk   (default) the page, clicked, every write read back
//   shot   the page, scrolled half a screenful per tick (for --shots)
//   privacy  the journal switch's question open (for a screenshot)
import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    // The old id, on purpose: it is an alias now.
    Component.onCompleted: overlay.open('{"page":"display"}')

    TestEvent { id: input }

    readonly property string arg: Quickshell.env("PREVIEW_ARG") || "walk"
    property int passed: 0
    property int failed: 0
    function check(ok, what) {
      if (ok) passed++; else failed++
      console.warn("PREVIEW " + (ok ? "PASS " : "FAIL ") + what)
    }
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
    function content() { return overlay.pageScroll ? overlay.pageScroll.contentItem : null }
    function named(name) { return find(content(), function(i) { return i.objectName === name }) }
    function text(needle) {
      return find(content(), function(i) { return i.text !== undefined && i.clicked === undefined
                                                  && String(i.text).indexOf(needle) >= 0 })
    }
    function button(prefix) {
      return find(content(), function(i) { return i.clicked !== undefined && typeof i.text === "string"
                                                  && i.text.indexOf(prefix) === 0 })
    }
    function toggleFor(label) {
      // A ToggleRow: the row whose label matches, then its switch.
      var row = find(content(), function(i) { return i.label === label && i.toggled !== undefined })
      return row
    }
    function click(item, label) {
      if (!item) { check(false, "found " + label); return }
      var flick = overlay.pageScroll
      if (flick && content()) {
        var y = item.mapToItem(content(), 0, 0).y
        flick.contentY = Math.max(0, Math.min(y - 160, flick.contentHeight - flick.height))
      }
      console.warn("PREVIEW click " + label)
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function clickSwitch(label) {
      var row = toggleFor(label)
      if (!row) { check(false, "found the switch " + label); return }
      var sw = find(row, function(i) { return i.trackWidth !== undefined })
      click(sw || row, "switch " + label)
    }

    // What the stubs logged so far, read back from <out>.writes.
    property string writes: ""
    Process {
      id: writesReader
      command: ["sh", "-c", "cat \"$PREVIEW_WRITES\" 2>/dev/null"]
      stdout: StdioCollector { onStreamFinished: overlay.writes = text }
    }
    function readWrites() { writesReader.running = true }
    function lines(needle) {
      return overlay.writes.split("\n").filter(function(l) { return l.indexOf(needle) >= 0 }).length
    }

    property int step: 0
    property int warm: 0
    Timer {
      interval: 1300
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        overlay.step++
        if (overlay.arg === "privacy") {
          // The journal question open, for a screenshot. Writes nothing.
          if (overlay.step === 2) overlay.clickSwitch("\u26a0 Write what is said to the system log")
          return
        }
        if (overlay.arg === "shot") {
          if (overlay.step > 6 && overlay.pageScroll) {
            var f = overlay.pageScroll
            f.contentY = Math.min(f.contentY + f.height * 0.5, Math.max(0, f.contentHeight - f.height))
          }
          return
        }
        switch (overlay.step) {
        case 1:
          overlay.check(overlay.page === "other", "the old display link opens Other settings (" + overlay.page + ")")
          overlay.check(overlay.text("What belongs to no one page") !== null, "the page says what it is")
          var labels = overlay.pages.map(function(p) { return p.label })
          overlay.check(labels.indexOf("Other settings") === 9 && labels.indexOf("Display") < 0,
                        "the sidebar says Other settings, tenth")
          overlay.check(overlay.toggleFor("Show each voice agent in Omarchy's Agents panel") !== null,
                        "the Agents panel switch is with the readout")
          overlay.check(overlay.button("Preview") !== null, "Preview is there")
          overlay.check(overlay.named("clearStats") !== null, "Clear stats is there")
          overlay.check(overlay.text("The mic always closes while the screen is locked") !== null, "the lock line")
          // The keys, read live.
          overlay.check(overlay.text("Hold F8") !== null, "Hold F8, from the bindings file")
          overlay.check(overlay.text("Super+Ctrl+Space") !== null, "Super+Ctrl+Space")
          overlay.check(overlay.text("Hyprland has not loaded it") !== null,
                        "the line Hyprland did not load is marked")
          overlay.check(overlay.named("openBindings") !== null && overlay.named("openBindings").enabled,
                        "Open bindings file is there")
          overlay.check(overlay.text("Middle-click the bar icon") !== null, "the bar icon's clicks")
          overlay.readWrites()
          break
        case 2:
          overlay.check(overlay.writes.trim() === "", "opening the page wrote nothing (" + overlay.writes.trim() + ")")
          overlay.clickSwitch("⚠ Write what is said to the system log")
          break
        case 3:
          overlay.check(overlay.named("logSpeechConfirm") !== null, "turning logging on asks first")
          overlay.readWrites()
          break
        case 4:
          overlay.check(overlay.lines("logSpeech") === 0, "and the question wrote nothing")
          overlay.click(overlay.find(overlay.named("logSpeechConfirm"), function(i) {
            return i.clicked !== undefined && i.text === "Cancel" }), "logging: Cancel")
          break
        case 5:
          overlay.check(overlay.named("logSpeechConfirm") === null, "Cancel closes the question")
          overlay.readWrites()
          break
        case 6:
          overlay.check(overlay.lines("logSpeech") === 0, "Cancel wrote nothing")
          overlay.clickSwitch("⚠ Write what is said to the system log")
          break
        case 7:
          overlay.click(overlay.find(overlay.named("logSpeechConfirm"), function(i) {
            return i.clicked !== undefined && i.text === "Turn logging on" }), "logging: Turn logging on")
          break
        case 8:
          overlay.readWrites()
          break
        case 9:
          overlay.check(overlay.lines("logSpeech true") === 1, "the confirm wrote logSpeech true, once")
          overlay.check(overlay.setting("logSpeech", false) === true, "and the switch is on")
          overlay.clickSwitch("⚠ Write what is said to the system log")
          break
        case 10:
          overlay.readWrites()
          break
        case 11:
          overlay.check(overlay.lines("logSpeech false") === 1, "off is one click")
          overlay.check(overlay.named("logSpeechConfirm") === null, "with no question")
          overlay.click(overlay.named("openBindings"), "Open bindings file")
          break
        case 12:
          overlay.click(overlay.button("Repair"), "Repair")
          break
        case 13:
          // Repair dismisses the overlay (the installer opens a terminal).
          overlay.check(!overlay.opened, "Repair closed the overlay for its terminal")
          overlay.open('{"page":"other"}')
          break
        case 14:
          var rm = overlay.named("removeEverything")
          overlay.click(overlay.find(rm, function(i) { return i.clicked !== undefined }), "Remove: arm")
          break
        case 15:
          overlay.check(overlay.named("removeEverything") !== null && overlay.named("removeEverything").armed,
                        "the first click only arms Remove")
          overlay.click(overlay.button("Cancel"), "Remove: Cancel")
          break
        case 16:
          overlay.readWrites()
          break
        case 17:
          overlay.check(overlay.lines("--uninstall") === 0, "Cancel removed nothing")
          overlay.check(overlay.lines("omarchy-launch-editor") === 1 && overlay.lines("/hypr/bindings.lua") === 1,
                        "Open bindings file asked the editor for bindings.lua, once")
          overlay.check(overlay.lines("install.sh' '--no-keybinds'") === 1, "Repair ran the installer, once")
          var rm2 = overlay.named("removeEverything")
          overlay.click(overlay.find(rm2, function(i) { return i.clicked !== undefined }), "Remove: arm again")
          break
        case 18:
          overlay.click(overlay.button("Remove"), "Remove: Remove (confirm)")
          break
        case 19:
          overlay.readWrites()
          break
        case 20:
          overlay.check(overlay.lines("--uninstall --with-widget") === 1, "the confirm ran the removal, once")
          console.warn("PREVIEW writes:\n" + overlay.writes)
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        }
      }
    }
  }
}
