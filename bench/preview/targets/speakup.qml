// Master plan M27: "Speak up when work finishes" on each agent's Voice card,
// driven with synthetic clicks and checked against what it wrote.
//
//   preview.sh --config bench/preview/configs/crew3.json \
//     --state bench/preview/states/showcase.json --size 1100x760 \
//     --wait 40 --out /tmp/m27/speakup speakup
//
// crew3 is Theo (main, Claude Code), Sora (Claude Code) and Hazel (Codex).
// Each switch starts on (the default); the main agent's writes the top-level
// key, an extra agent's writes `speakWhenDone: false` into its entry and,
// switched back, leaves the field out. The hint says what each program can
// announce: Claude its own background work and tasks it gave out, Codex
// only the tasks.
import QtQuick
import QtTest
import Quickshell
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open('{"page":"agents"}')

    TestEvent { id: input }

    function log(m) { console.warn("PREVIEW " + m) }
    function check(ok, what) { console.warn("PREVIEW " + (ok ? "PASS " : "FAIL ") + what) }
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
    function agentRoot(id) {
      return find(content(), function(i) { return i.agentId === id && i.pg !== undefined })
    }
    function voiceCard(id) {
      return find(agentRoot(id), function(i) { return i.title === "Voice" && i.highlighted !== undefined })
    }
    function speakRow(id) {
      return find(voiceCard(id), function(i) { return i.label === "Speak up when work finishes" && i.checked !== undefined })
    }
    function reveal(item) {
      var f = overlay.pageScroll
      if (!f || !item) return
      var y = item.mapToItem(f.contentItem, 0, 0).y
      f.contentY = Math.max(0, Math.min(y - 60, f.contentHeight - f.height))
    }
    function unfold(id) {
      var root = agentRoot(id)
      if (!root) { log("MISS " + id); return }
      if (root.expanded) return
      reveal(root)
      input.mouseClick(root, root.width / 2, 12, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function toggle(id) {
      var r = speakRow(id)
      var sw = r ? find(r, function(i) { return i.trackWidth !== undefined && i.toggled !== undefined }) : null
      if (!sw) { log("MISS switch " + id); return }
      reveal(r)
      log("click " + id + " speak up")
      input.mouseClick(sw, sw.width / 2, sw.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function entryOf(id) {
      var list = overlay.setting("voiceAgents", [])
      for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i]
      return null
    }

    readonly property var steps: [
      function() { unfold("main") },
      function() {
        var r = speakRow("main")
        check(r !== null, "the main agent's Voice card has the switch")
        check(r && r.checked === true, "on by default")
        check(r && String(r.hint).indexOf("background command or helper") >= 0,
              "Claude's hint names its own background work")
        reveal(r)
      },
      function() { toggle("main") },
      function() {
        check(overlay.setting("mainSpeakWhenDone", true) === false, "main: mainSpeakWhenDone false written")
        check(speakRow("main") && speakRow("main").checked === false, "main: the switch reads off")
      },
      function() { toggle("main") },
      function() { check(overlay.setting("mainSpeakWhenDone", false) === true, "main: back on") },
      function() { unfold("sora") },
      function() { reveal(speakRow("sora")); toggle("sora") },
      function() {
        var e = entryOf("sora")
        check(e !== null && e.speakWhenDone === false, "sora: speakWhenDone false in its entry")
        check(e !== null && e.futureField !== undefined, "sora: the rest of its entry kept")
      },
      function() { toggle("sora") },
      function() {
        var e = entryOf("sora")
        check(e !== null && e.speakWhenDone === undefined, "sora: on again leaves the field out")
      },
      function() { unfold("hazel") },
      function() {
        var r = speakRow("hazel")
        reveal(r)
        check(r && String(r.hint).indexOf("Codex") >= 0 && String(r.hint).indexOf("ends with each turn") >= 0,
              "hazel: the hint says Codex announces only tasks")
      },
      function() { log("DONE") }
    ]

    property int step: -1
    property int warm: 0
    Timer {
      interval: 1500
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        if (overlay.store.busy) return
        overlay.step++
        if (overlay.step < overlay.steps.length) overlay.steps[overlay.step]()
      }
    }
  }
}
