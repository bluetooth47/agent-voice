// Settings search (master plan M28): the box at the top of the sidebar,
// driven from the keyboard, landing on controls on five pages, and the old
// deep links still resolving.
//
//   preview.sh --config bench/preview/configs/crew3.json --state \
//     bench/preview/states/showcase.json --size 1100x760 --wait 40 \
//     --out /tmp/search search
//   grep PREVIEW /tmp/search.log; cat /tmp/search.writes
//
// Searching writes nothing, and the run checks that: the write log must stay
// empty to the end.
//
// --arg:
//   walk     (default) everything above, checked
//   results  "pause" typed into the box, the results left open (screenshot)
//   landed   "pause" chosen: the Conversation page with the knob outlined
import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open("{}")

    readonly property string want: (Quickshell.env("PREVIEW_ARG") || "walk").split(",")[0]
    // ",narrow" on the argument draws the card itself 500px wide, for a
    // screenshot of the narrow layout (a --size crop only cuts a wide one).
    readonly property bool narrow: (Quickshell.env("PREVIEW_ARG") || "").indexOf(",narrow") >= 0
    Timer {
      interval: 400; running: true
      onTriggered: {
        if (!overlay.narrow) return
        for (var i = overlay.pageScroll; i; i = i.parent)
          if (i.objectName === "settingsCard") { i.width = 500; return }
      }
    }
    property var keys: null
    // Inside an Item of the overlay's window, so key events find it.
    function keyEvents() {
      if (!overlay.keys) overlay.keys = Qt.createQmlObject("import QtTest; TestEvent {}", overlay.pageScroll.contentItem)
      return overlay.keys
    }
    function key(k, mods) { keyEvents().keyClick(k, mods === undefined ? Qt.NoModifier : mods, -1) }
    function typeKeys(t) {
      for (var i = 0; i < t.length; i++)
        keyEvents().keyClick(t.charAt(i) === " " ? Qt.Key_Space : t.toUpperCase().charCodeAt(i), Qt.NoModifier, -1)
    }

    property int passed: 0
    property int failed: 0
    function check(ok, what) {
      if (ok) passed++; else failed++
      console.warn("PREVIEW " + (ok ? "PASS " : "FAIL ") + what)
    }
    function findIn(item, test) {
      if (!item) return null
      if (test(item)) return item
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) {
        var hit = findIn(kids[i], test)
        if (hit) return hit
      }
      return null
    }
    function windowRoot() {
      var i = overlay.pageScroll
      while (i && i.parent) i = i.parent
      return i
    }
    function byName(name) { return findIn(windowRoot(), function(i) { return i.objectName === name }) }
    function searchBox() { return findIn(byName("settingsSearchField"), function(i) { return i.placeholderText !== undefined }) }
    function searchPiece() { return findIn(windowRoot(), function(i) { return i.chosen !== undefined && i.results !== undefined }) }
    function focusIn(item) {
      var f = overlay.pageScroll ? overlay.pageScroll.Window.activeFocusItem : null
      for (var a = f; a; a = a.parent) if (a === item) return true
      return false
    }
    function resultIndex(label, pathPart) {
      var r = searchPiece().results
      for (var i = 0; i < r.length; i++)
        if (r[i].label === label && (!pathPart || r[i].path.indexOf(pathPart) >= 0)) return i
      return -1
    }
    function agentIdNamed(label) {
      var a = overlay.searchAgents
      for (var i = 0; i < a.length; i++) if (a[i].label === label) return a[i].id
      return ""
    }

    property string writes: ""
    Process {
      id: writesReader
      command: ["sh", "-c", "cat \"$PREVIEW_WRITES\" 2>/dev/null"]
      stdout: StdioCollector { onStreamFinished: overlay.writes = text }
    }

    property int step: 0
    property int warm: 0
    property var soraId: ""
    property var hazelId: ""
    Timer {
      interval: 900
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        overlay.step++
        var s = overlay.searchPiece()
        if (overlay.want === "results") {
          if (overlay.step === 1) { overlay.searchBox().forceActiveFocus(); overlay.typeKeys("pause") }
          return
        }
        if (overlay.want === "landed") {
          if (overlay.step === 1) { overlay.searchBox().forceActiveFocus(); overlay.typeKeys("pause") }
          if (overlay.step === 2) overlay.key(Qt.Key_Return)
          return
        }
        switch (overlay.step) {
        case 1:
          overlay.check(overlay.page === "overview", "a plain summons opens the Overview (" + overlay.page + ")")
          overlay.check(overlay.mode === "settings", "a configured install is not taken over by setup")
          overlay.check(s !== null && overlay.searchBox() !== null, "the search box is at the top of the sidebar")
          overlay.check(s.y < overlay.byName("settingsSearchField").height + 4, "above the page list")
          // Ctrl+F from the card, which holds the keyboard in the real shell
          // (its Exclusive focus is None in a preview, so given here).
          overlay.byName("settingsCard").forceActiveFocus()
          overlay.key(Qt.Key_F, Qt.ControlModifier)
          break
        case 2:
          overlay.check(overlay.searchBox().activeFocus, "Ctrl+F puts the cursor in the search box")
          overlay.typeKeys("pause")
          break
        case 3:
          overlay.check(s.results.length > 0 && s.results[0].key === "trailingSilenceMs",
                        "“pause” finds the pause that ends a turn first (" + (s.results.length ? s.results[0].label : "nothing") + ")")
          overlay.check(overlay.resultIndex("Mute mic") > 0, "and Mute mic further down")
          overlay.check(overlay.byName("settingsSearchResults").visible, "the results are drawn over the page")
          overlay.check(s.results.length > 0 && s.results[0].path === "Conversation › Advanced",
                        "its path says where (" + (s.results.length ? s.results[0].path : "") + ")")
          overlay.key(Qt.Key_Down)
          overlay.key(Qt.Key_Up)
          overlay.check(s.current === 0, "Down and Up move through the results and back")
          overlay.key(Qt.Key_Return)
          break
        case 4:
        case 5:
          if (overlay.revealing !== null) { overlay.step--; break }
          if (overlay.step === 5) break
          overlay.check(overlay.page === "conversation", "Enter opens the Conversation page (" + overlay.page + ")")
          var adv = overlay.byName("timingsAdvanced")
          overlay.check(adv !== null && adv.expanded === true, "the folded timings are unfolded")
          var knob = overlay.byName("pauseKnob")
          overlay.check(knob !== null && overlay.flashItem === knob, "the pause knob is outlined")
          overlay.check(overlay.byName("searchFlash").visible, "the outline is drawn")
          overlay.check(knob !== null && overlay.focusIn(knob), "the keyboard is on the knob")
          overlay.check(overlay.pageScroll.contentY > 0, "the page scrolled to it (" + Math.round(overlay.pageScroll.contentY) + ")")
          overlay.check(overlay.searchBox().text === "", "the box is cleared")
          // One agent's setting: Sora's model.
          overlay.soraId = overlay.agentIdNamed("Sora")
          overlay.hazelId = overlay.agentIdNamed("Hazel")
          overlay.check(overlay.soraId !== "" && overlay.hazelId !== "", "the agents are known to search")
          s.type("model")
          break
        case 6:
          var i = overlay.resultIndex("Model", "Sora")
          overlay.check(i >= 0 && overlay.resultIndex("Model", "Theo") >= 0 && overlay.resultIndex("Model", "Hazel") >= 0,
                        "“model” gives one result per agent")
          s.choose(i)
          break
        case 7:
        case 8:
          if (overlay.revealing !== null) { overlay.step--; break }
          if (overlay.step === 8) break
          overlay.check(overlay.page === "agents", "Sora's model opens the Agents page")
          var block = overlay.byName("agent-" + overlay.soraId)
          overlay.check(block !== null && block.expanded === true, "Sora's card is open")
          var found = overlay.flashItem
          var inside = false
          for (var a = found; a; a = a.parent) if (a === block) inside = true
          overlay.check(found !== null && found.objectName === "agent-model" && inside,
                        "the model row inside Sora's card is outlined")
          // A tab on Agent details: Hazel's extra flags.
          s.type("extra flags")
          s.choose(overlay.resultIndex("Extra flags", "Hazel"))
          break
        case 9:
        case 10:
          if (overlay.revealing !== null) { overlay.step--; break }
          if (overlay.step === 10) break
          overlay.check(overlay.page === "agentdetails" && overlay.detailsAgent === overlay.hazelId
                        && overlay.detailsTab === "advanced", "Hazel's Advanced tab opens (" +
                        overlay.page + " " + overlay.detailsAgent + " " + overlay.detailsTab + ")")
          overlay.check(overlay.flashItem !== null && overlay.flashItem.objectName === "set-extraArgs",
                        "Extra flags is outlined")
          // A Communal tab.
          s.type("browser")
          s.choose(overlay.resultIndex("Browser"))
          break
        case 11:
        case 12:
          if (overlay.revealing !== null) { overlay.step--; break }
          if (overlay.step === 12) break
          overlay.check(overlay.page === "communal" && overlay.communalTab === "tools", "Browser opens Communal → Tools")
          overlay.check(overlay.flashItem !== null && overlay.flashItem.objectName === "set-browserTools", "the Browser switch is outlined")
          // A control not on screen for this engine.
          s.type("openwakeword detection threshold")
          s.choose(0)
          break
        case 13:
        case 14:
          if (overlay.revealing !== null) { overlay.step--; break }
          if (overlay.step === 14) break
          overlay.check(overlay.page === "listening", "a hidden control still opens its page")
          overlay.check(overlay.searchNote.indexOf("not on screen right now") >= 0 && overlay.searchNote.indexOf("openWakeWord") >= 0,
                        "and says why it is not there (" + overlay.searchNote + ")")
          // A page by its name; the note goes with the page it was about.
          s.type("about")
          s.choose(overlay.resultIndex("About"))
          break
        case 15:
          overlay.check(overlay.page === "about", "a page found by its name opens")
          overlay.check(overlay.searchNote === "", "the note did not outlive its page")
          s.type("zzqx")
          overlay.check(s.results.length === 0, "nothing matches nonsense")
          s.clear()
          // Old deep links.
          overlay.open('{"page":"display"}')
          overlay.check(overlay.page === "other", "{page: display} still opens Other settings")
          overlay.open('{"mode":"history"}')
          overlay.check(overlay.page === "chats", "{mode: history} still opens Chats")
          overlay.open('{"page":"agentdetails","agent":"' + overlay.soraId + '","tab":"advanced"}')
          overlay.check(overlay.page === "agentdetails" && overlay.detailsTab === "advanced" && overlay.detailsAgent === overlay.soraId,
                        "{page: agentdetails, agent, tab} still opens that tab")
          overlay.open('{"page":"communal","tab":"who"}')
          overlay.check(overlay.communalTab === "who", "{page: communal, tab: who} still opens that tab")
          overlay.open('{"page":"conversation","focus":"maxUtteranceMs"}')
          overlay.check(overlay.page === "conversation", "{page: conversation, focus} still opens Conversation")
          break
        case 16:
          overlay.check(overlay.focusKey === "", "and its focus is taken by the page, as in M24")
          writesReader.running = true
          break
        case 17:
          overlay.check(overlay.writes.trim() === "", "searching wrote nothing (" + overlay.writes.trim() + ")")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        }
      }
    }
  }
}
