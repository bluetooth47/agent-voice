// The Voice page (master plan M25): quick settings, each agent's voice with a
// link to its card, the library opening on Downloaded with a search box and
// one filter, the trash first in a column every row keeps (bug F), and
// transcription under Advanced.
//
//   preview.sh --config bench/preview/configs/voice.json --state \
//     bench/preview/states/showcase.json --scratch-data --size 1100x760 \
//     --wait 30 --out /tmp/voice voicepage
//   grep PREVIEW /tmp/voice.log; cat /tmp/voice.writes
//
// The `agentvoice voice` verb is a stub here: Test, Download and the trash
// log what they were asked (<out>.writes) and play, fetch and remove nothing.
// The disk is poked: lessac-medium, amy-medium and alba are "on disk".
//
// --arg:
//   walk   (default) the page, clicked and measured
//   shot   the page with the library on All and the Advanced open, scrolled
//          half a screenful per tick (for --shots)
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

    readonly property string arg: Quickshell.env("PREVIEW_ARG") || "walk"
    readonly property bool shot: arg === "shot"
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
    function findAll(item, test, out) {
      out = out || []
      if (!item) return out
      if (item.visible !== false && test(item)) out.push(item)
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) findAll(kids[i], test, out)
      return out
    }
    function findAny(item, test) {
      if (!item) return null
      if (test(item)) return item
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) {
        var hit = findAny(kids[i], test)
        if (hit) return hit
      }
      return null
    }
    function poke(name, value) { overlay[name] = value }
    function content() { return overlay.pageScroll ? overlay.pageScroll.contentItem : null }
    function named(name) { return find(content(), function(i) { return i.objectName === name }) }
    function anyNamed(name) { return findAny(content(), function(i) { return i.objectName === name }) }
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
    function libRows() {
      return findAll(content(), function(i) { return i.onDisk !== undefined && i.removable !== undefined })
    }
    function agentRows() { return findAll(content(), function(i) { return i.canTest !== undefined && i.voiceName !== undefined }) }
    function libRow(name, detailHas) {
      var r = libRows()
      for (var i = 0; i < r.length; i++)
        if (r[i].label === name && (!detailHas || r[i].detail.indexOf(detailHas) >= 0)) return r[i]
      return null
    }
    function agentRow(name) {
      var r = agentRows()
      for (var i = 0; i < r.length; i++) if (r[i].name === name) return r[i]
      return null
    }
    // The x of a row's named cell, in the page's own coordinates.
    function xOf(row, cell) {
      var c = findAny(row, function(i) { return i.objectName === cell })
      return c ? Math.round(c.mapToItem(content(), 0, 0).x) : -1
    }
    function xs(rows, cell) {
      var seen = {}
      for (var i = 0; i < rows.length; i++) seen[xOf(rows[i], cell)] = true
      return Object.keys(seen).sort().join(",")
    }
    function buttonIn(root, test) {
      return find(root, function(i) { return i.clicked !== undefined && test(i) })
    }
    function textIn(root, needle) {
      return find(root, function(i) { return i.text !== undefined && String(i.text).indexOf(needle) >= 0 }) !== null
    }
    function fold(name, open) {
      var a = anyNamed(name)
      if (!a) { check(false, "found " + name); return }
      if (a.expanded !== open) click(a.children[0], name + " header")
    }
    function menuOf(sel) {
      var d = sel ? sel.data : []
      for (var i = 0; i < d.length; i++) if (d[i] && d[i].entries !== undefined && d[i].choose !== undefined) return d[i]
      return null
    }
    function chooseFilter(value) {
      var m = menuOf(named("voiceFilter"))
      if (!m) { check(false, "the filter menu is there"); return }
      for (var i = 0; i < m.entries.length; i++) {
        var e = m.entries[i]
        if (String((e !== null && typeof e === "object") ? e.value : e) === value) { m.choose(i); return }
      }
      check(false, value + " is offered")
    }
    function search(text) {
      var f = named("voiceSearch")
      if (!f) { check(false, "found the search box"); return }
      var box = find(f, function(i) { return i.placeholderText !== undefined })
      if (box) box.text = text
      f.searched(text)
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
        if (overlay.step === 1) {
          overlay.poke("voicesOnDisk", ["lessac-medium", "amy-medium", "en_GB-alba-medium"])
          return
        }
        if (overlay.shot) {
          if (overlay.step === 3) overlay.chooseFilter("all")
          else if (overlay.step === 4) { overlay.fold("hearingAdvanced", true); overlay.pageScroll.contentY = 0 }
          else if (overlay.step > 5 && overlay.pageScroll) {
            var f = overlay.pageScroll
            f.contentY = Math.min(f.contentY + f.height * 0.5, Math.max(0, f.contentHeight - f.height))
          }
          return
        }
        switch (overlay.step) {
        case 2:
          var rows = overlay.libRows()
          overlay.check(rows.length === 3, "the library opens on Downloaded: 3 rows (" + rows.length + ")")
          overlay.check(overlay.named("voiceFilter").shown === "here", "and the filter says so (" + overlay.named("voiceFilter").shown + ")")
          overlay.check(overlay.agentRows().length === 4, "one row for the main agent and one per extra agent (" + overlay.agentRows().length + ")")
          overlay.check(overlay.named("hearingAdvanced") !== null && overlay.named("hearingAdvanced").expanded === false
                        && overlay.named("hearingAdvanced").count === 2, "transcription is folded under Advanced")
          // Bug F, measured: on disk and removable, on disk and in use,
          // on disk and the default.
          overlay.check(overlay.xs(rows, "trashCell") !== "" && overlay.xs(rows, "trashCell").indexOf(",") < 0,
                        "one x for the trash column across rows (" + overlay.xs(rows, "trashCell") + ")")
          overlay.check(overlay.xs(rows, "voiceName").indexOf(",") < 0, "one x for the name (" + overlay.xs(rows, "voiceName") + ")")
          overlay.check(overlay.xs(rows, "testCell").indexOf(",") < 0, "one x for the Test column (" + overlay.xs(rows, "testCell") + ")")
          overlay.check(overlay.xs(rows, "useCell").indexOf(",") < 0, "one x for Use for (" + overlay.xs(rows, "useCell") + ")")
          var amy = overlay.libRow("Amy", "medium")
          var lessac = overlay.libRow("Lessac", "medium")
          var alba = overlay.libRow("Alba", "medium")
          overlay.check(amy !== null && amy.users === "Sora" && !amy.removable, "Amy is Sora's, so it cannot be removed (" + (amy ? amy.users : "missing") + ")")
          overlay.check(lessac !== null && lessac.users === "Theo", "Lessac is Theo's (" + (lessac ? lessac.users : "missing") + ")")
          overlay.check(alba !== null && alba.users === "Friday" && !alba.removable, "Alba is Friday's")
          overlay.check(overlay.textIn(amy, "Used for Sora"), "the row says \"Used for Sora\"")
          overlay.check(overlay.xs([amy, lessac, alba], "voiceName").indexOf(",") < 0, "the extra line moves no column")
          // The trash button is there for a removable voice only.
          overlay.check(overlay.buttonIn(lessac, function(i) { return i.tooltipText === "Delete it from this machine" }) === null,
                        "the default voice has no trash button")
          // Agents, read from the settings.
          var sora = overlay.agentRow("Sora"), jarvis = overlay.agentRow("Jarvis"), main = overlay.agentRow("Theo")
          overlay.check(sora !== null && sora.pace === "130%" && sora.voiceName === "Amy", "Sora: Amy at 130%")
          overlay.check(jarvis !== null && jarvis.note === "follows the main agent" && jarvis.voiceName === "Lessac" && jarvis.pace === "100%",
                        "Jarvis follows the main agent (" + (jarvis ? jarvis.note : "missing") + ")")
          overlay.check(main !== null && main.voiceName === "Lessac", "the main agent: Lessac")
          var friday = overlay.agentRow("Friday")
          overlay.check(friday !== null && friday.note === "speed follows the main agent" && friday.canTest === true,
                        "Friday has its own voice and follows the speed (" + (friday ? friday.note : "missing") + ")")
          overlay.check(overlay.xs(overlay.agentRows(), "agentTestCell").indexOf(",") < 0
                        && overlay.xs(overlay.agentRows(), "agentChangeCell").indexOf(",") < 0, "the agent rows line up too")
          overlay.click(overlay.buttonIn(lessac, function(i) { return i.text === "▶ Test" }), "test Lessac in the library")
          break
        case 3:
          overlay.click(overlay.buttonIn(overlay.agentRow("Sora"), function(i) { return i.text === "▶ Test" }), "test Sora")
          break
        case 4:
          overlay.click(overlay.buttonIn(overlay.agentRow("Jarvis"), function(i) { return i.text === "Change on Agents →" }), "Jarvis: Change on Agents")
          break
        case 5:
          overlay.check(overlay.page === "agents" && overlay.focusAgent === "jarvis", "Change on Agents opens that agent's card (" + overlay.page + ", " + overlay.focusAgent + ")")
          overlay.goTo("voice")
          break
        case 6:
          overlay.chooseFilter("all")
          break
        case 7:
          var all = overlay.libRows()
          overlay.check(all.length === overlay.rawVoiceOptions.length, "All lists all " + overlay.rawVoiceOptions.length + " (" + all.length + ")")
          overlay.check(overlay.xs(all, "trashCell").indexOf(",") < 0 && overlay.xs(all, "voiceName").indexOf(",") < 0
                        && overlay.xs(all, "testCell").indexOf(",") < 0 && overlay.xs(all, "useCell").indexOf(",") < 0,
                        "across all " + all.length + " rows, installed, missing and in use: trash " + overlay.xs(all, "trashCell") +
                        ", name " + overlay.xs(all, "voiceName") + ", Test " + overlay.xs(all, "testCell") +
                        ", Use for " + overlay.xs(all, "useCell"))
          var missing = overlay.libRow("Ryan", "high")
          overlay.check(missing !== null && !missing.onDisk && overlay.buttonIn(missing, function(i) { return i.text === "Download" }) !== null,
                        "a missing voice offers Download in the same column")
          overlay.search("british female")
          break
        case 8:
          overlay.check(overlay.libRows().length === 5, "\"british female\" finds the 5 British women (" + overlay.libRows().length + ")")
          overlay.search("zzz")
          break
        case 9:
          overlay.check(overlay.libRows().length === 0 && overlay.textIn(overlay.content(), "No voice matches"), "a search with no match says so")
          overlay.search("")
          overlay.chooseFilter("here")
          break
        case 10:
          overlay.check(overlay.libRows().length === 3, "clearing the search and choosing Downloaded is back to 3")
          overlay.chooseFilter("male")
          break
        case 11:
          overlay.check(overlay.libRows().length === overlay.rawVoiceOptions.filter(function(v) { return v.gender === "male" }).length, "Male filters the list (" + overlay.libRows().length + ")")
          overlay.chooseFilter("here")
          overlay.assignVoice("", "lessac-medium")
          break
        case 12:
          overlay.fold("hearingAdvanced", true)
          break
        case 13:
          overlay.check(overlay.textIn(overlay.content(), "turns what you say into text on this machine"), "one line says what transcription does")
          overlay.click(overlay.find(overlay.named("hearingAdvanced"), function(i) { return i.text === "base.en" && i.clicked !== undefined }), "model base.en")
          break
        case 14:
          overlay.check(overlay.setting("model", "") === "base.en", "the model chip writes `model`")
          overlay.put("speakReplies", false)
          break
        case 15:
          overlay.check(overlay.agentRow("Sora").canTest === false, "with replies off the agent rows' Test is disabled")
          overlay.check(overlay.textIn(overlay.content(), "Replies are not spoken, so these voices are not heard"), "and the page says why")
          overlay.put("speakReplies", true)
          // Remove: Alba is Friday's, so give Friday back its own voice, then
          // the trash is there.
          overlay.assignVoice("friday", "")
          break
        case 16:
          var a2 = overlay.libRow("Alba", "medium")
          overlay.check(a2 !== null && a2.removable && a2.users === "", "Alba is free now, so it can be removed")
          overlay.click(overlay.buttonIn(a2, function(i) { return i.tooltipText === "Delete it from this machine" }), "trash Alba")
          break
        case 17:
          overlay.done()
          break
        }
      }
    }
    function done() { console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed") }
  }
}
