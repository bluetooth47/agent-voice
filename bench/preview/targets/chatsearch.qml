// Chat search (master plan, M20) on the Agents page's Collaboration, notes &
// chats card, driven by synthetic clicks through the real settings store:
//
//   preview.sh --config bench/preview/configs/crew3.json \
//     --state bench/preview/states/showcase.json --size 1100x760 \
//     --wait 50 --out /tmp/cs chatsearch
//   grep PREVIEW /tmp/cs.log; cat /tmp/cs.writes
//
//   --arg shot   open the main agent's card and leave the question before
//                "Every chat" up, for a screenshot
//
// What it checks: the row is there with "Its own and shared" chosen; Off
// writes mainChatSearch "off"; "Every chat" only opens the question and
// writes nothing; Cancel writes nothing; "Allow every chat" writes "all";
// "Its own and shared" writes "own". Sora's entry gets chatSearch "all" only
// through the question, and loses the key on "Its own and shared". Hazel
// (Codex) is told Codex reads the files at any level. A quarantined Sora is
// told she can search nothing. Synthetic settings only (a scratch copy).
import QtQuick
import QtTest
import Quickshell
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open('{"page":"agents","agent":"main"}')

    TestEvent { id: input }

    readonly property string mode: Quickshell.env("PREVIEW_ARG") || "drive"
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
    function click(item, label) {
      if (!item) { check(false, "found " + label); return }
      var flick = overlay.pageScroll
      if (flick && content()) {
        var y = item.mapToItem(content(), 0, 0).y
        flick.contentY = Math.max(0, Math.min(y - 160, flick.contentHeight - flick.height))
      }
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function card(id) {
      return find(content(), function(i) { return i.agentId === id && i.pg !== undefined })
    }
    function switches(id) {
      return find(card(id), function(i) { return i.part === "collab" && i.chatSearchPicked !== undefined })
    }
    function row(sw) {
      return find(sw, function(i) { return i.label === "Chat search" && i.reset !== undefined })
    }
    function chip(item, text) {
      return find(item, function(i) { return i.clicked !== undefined && i.text === text })
    }
    function question(sw) {
      return find(sw, function(i) { return i.confirmText === "Allow every chat" })
    }
    function entryOf(id) {
      for (var i = 0; i < overlay.voiceAgents.length; i++)
        if (overlay.agentId(overlay.voiceAgents[i]) === id) return overlay.voiceAgents[i]
      return null
    }

    property int step: 0
    property int warm: 0

    Timer {
      interval: 2000
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        overlay.step++
        var sw, r, q, e
        if (overlay.mode === "shot") {
          if (overlay.step === 1) overlay.goTo("agents", "main", "tools")
          if (overlay.step === 2) overlay.click(overlay.chip(overlay.row(overlay.switches("main")), "Every chat"), "Every chat")
          if (overlay.step === 3) {
            q = overlay.question(overlay.switches("main"))
            if (q) overlay.pageScroll.contentY = Math.max(0, q.mapToItem(overlay.content(), 0, 0).y - 260)
            overlay.check(q !== null, "the question is up for the shot")
          }
          return
        }
        switch (overlay.step) {
        case 1:
          overlay.goTo("agents", "main", "tools")
          break
        case 2:
          sw = overlay.switches("main")
          r = overlay.row(sw)
          overlay.check(r !== null && sw.chatScope === "own", "the main card has a Chat search row, on Its own and shared")
          overlay.check(r !== null && String(r.hint).indexOf("Its own saved chats and the ones shared with it.") >= 0,
                        "its hint says what own reaches")
          overlay.check(r !== null && String(r.hint).indexOf("at Trust everything it could read the chat files directly") >= 0,
                        "and what it does not hold, for Claude (" + (r ? r.hint : "") + ")")
          overlay.click(overlay.chip(r, "Off"), "main Off")
          break
        case 3:
          overlay.check(overlay.setting("mainChatSearch", "?") === "off", "Off writes mainChatSearch = off")
          overlay.click(overlay.chip(overlay.row(overlay.switches("main")), "Every chat"), "main Every chat")
          break
        case 4:
          sw = overlay.switches("main")
          q = overlay.question(sw)
          overlay.check(q !== null && String(q.title).indexOf("search every saved chat?") >= 0,
                        "Every chat puts the question up (" + (q ? q.title : "none") + ")")
          overlay.check(overlay.setting("mainChatSearch", "?") === "off", "and writes nothing yet")
          overlay.click(overlay.chip(q, "Cancel"), "the question's Cancel")
          break
        case 5:
          sw = overlay.switches("main")
          overlay.check(overlay.question(sw) === null, "Cancel takes the question away")
          overlay.check(overlay.setting("mainChatSearch", "?") === "off", "and nothing was written")
          overlay.click(overlay.chip(overlay.row(sw), "Every chat"), "main Every chat again")
          break
        case 6:
          overlay.click(overlay.chip(overlay.question(overlay.switches("main")), "Allow every chat"), "Allow every chat")
          break
        case 7:
          overlay.check(overlay.setting("mainChatSearch", "?") === "all", "Allow every chat writes all")
          overlay.check(overlay.question(overlay.switches("main")) === null, "and the question goes")
          overlay.click(overlay.chip(overlay.row(overlay.switches("main")), "Its own and shared"), "main own")
          break
        case 8:
          overlay.check(overlay.setting("mainChatSearch", "?") === "own", "Its own and shared writes own")
          overlay.goTo("agents", "sora", "tools")
          break
        case 9:
          overlay.click(overlay.chip(overlay.row(overlay.switches("sora")), "Every chat"), "Sora Every chat")
          break
        case 10:
          e = overlay.entryOf("sora")
          overlay.check(e && e.chatSearch === undefined, "Sora's Every chat writes nothing before the question")
          overlay.click(overlay.chip(overlay.question(overlay.switches("sora")), "Allow every chat"), "Sora Allow every chat")
          break
        case 11:
          e = overlay.entryOf("sora")
          overlay.check(e && e.chatSearch === "all", "her entry gets chatSearch = all (" + JSON.stringify(e ? e.chatSearch : null) + ")")
          overlay.click(overlay.chip(overlay.row(overlay.switches("sora")), "Its own and shared"), "Sora own")
          break
        case 12:
          e = overlay.entryOf("sora")
          overlay.check(e && e.chatSearch === undefined, "Its own and shared removes the key, as the other defaults do")
          overlay.goTo("agents", "hazel", "tools")
          break
        case 13:
          r = overlay.row(overlay.switches("hazel"))
          overlay.check(r !== null && String(r.hint).indexOf("Codex can read the chat files directly at any level") >= 0,
                        "Hazel (Codex) is told Codex reads the files at any level")
          overlay.put("crewQuarantine", ["sora"])
          overlay.goTo("agents", "sora", "tools")
          break
        case 14:
          break
        case 15:
          r = overlay.row(overlay.switches("sora"))
          overlay.check(r !== null && String(r.hint).indexOf("Quarantined, so it can search no chat") === 0,
                        "a quarantined Sora is told she can search nothing (" + (r ? r.hint : "") + ")")
          overlay.put("crewQuarantine", [])
          break
        case 16:
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        }
      }
    }
  }
}
