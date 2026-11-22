// Drives every DangerButton the overlay has with synthetic clicks, and logs
// what each one wrote: armed → cancelled must write nothing, armed →
// confirmed must run the command (M1, feedback item 14).
//
//   preview.sh --live-config --scratch-data --wait 40 --out /tmp/c confirms
//   grep PREVIEW /tmp/c.log; cat /tmp/c.writes
//
// Nothing real is touched: `omarchy bar set` goes to a scratch shell.json
// (--live-config), `agentvoice agents` and `chats` to a scratch data folder
// (--scratch-data, seeded with synthetic chats), and the floating terminal
// that Remove Agent Voice opens is preview.sh's logging stub -- checked
// before the removal is confirmed, and skipped if it is not the stub.
import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open('{"page":"about"}')

    TestEvent { id: input }

    property bool launcherStubbed: false
    Process {
      running: true
      command: ["sh", "-c", "command -v omarchy-launch-floating-terminal-with-presentation"]
      stdout: StdioCollector {
        onStreamFinished: {
          overlay.launcherStubbed = text.indexOf("/agentvoice-preview.") >= 0
          console.warn("PREVIEW launcher is " + (overlay.launcherStubbed ? "the preview stub" : "NOT stubbed: " + text.trim()))
        }
      }
    }
    Process {
      id: writes
      command: ["sh", "-c", "cat \"$PREVIEW_WRITES\" 2>/dev/null | wc -l"]
      stdout: StdioCollector { onStreamFinished: console.warn("PREVIEW writes so far: " + text.trim()) }
    }
    function countWrites() { writes.running = true }

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
    function root() { return overlay.contentItem ? overlay.contentItem : null }
    function button(prefix) {
      return find(overlay.mode === "settings" ? overlay.pageScroll : overlayCard(), function(i) {
        return i.clicked !== undefined && typeof i.text === "string" && i.text.indexOf(prefix) === 0
      })
    }
    // The overlay's card, found from the page scroller it always holds:
    // the conversation view is a sibling of the pages inside it.
    function overlayCard() {
      for (var i = overlay.pageScroll; i; i = i.parent) if (i.objectName === "settingsCard") return i
      return null
    }
    function danger(of) { for (var i = of; i; i = i.parent) if (i.confirmed !== undefined && i.arm !== undefined) return i; return null }
    function click(item, label) {
      if (!item) { console.warn("PREVIEW miss " + label); return }
      var flick = overlay.pageScroll
      if (overlay.mode === "settings" && flick && flick.contentItem) {
        var y = item.mapToItem(flick.contentItem, 0, 0).y
        flick.contentY = Math.max(0, Math.min(y - 120, flick.contentHeight - flick.height))
      }
      console.warn("PREVIEW click " + label)
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    property var current: null
    function arm(prefix, label) {
      var b = button(prefix)
      current = danger(b)
      click(b, label + ": arm")
    }
    function report(label) {
      console.warn("PREVIEW " + label + ": armed=" + (current ? current.armed : "no button"))
      countWrites()
    }
    function firstAgentId() {
      var list = overlay.voiceAgents || []
      return list.length > 0 ? overlay.agentId(list[0]) : ""
    }
    // The first synthetic chat the seed wrote.
    property string chatId: ""
    property int chatCount: -1
    FileView {
      id: chatIndex
      path: (Quickshell.env("PREVIEW_DATA") || "/nonexistent") + "/chats/index.json"
      printErrors: false
      onLoaded: {
        var d = JSON.parse(text())
        overlay.chatCount = d.chats ? d.chats.length : 0
        if (overlay.chatId === "" && overlay.chatCount > 0) overlay.chatId = String(d.chats[0].id)
      }
    }

    // One step a tick; each confirms after a cancel, so both paths are seen.
    property var steps: [
      function() { overlay.report("start") },
      // Remove Agent Voice (About)
      function() { overlay.arm("⚠ Remove Agent Voice", "Remove Agent Voice") },
      function() { overlay.report("Remove Agent Voice armed") },
      function() { overlay.click(overlay.button("Cancel"), "Remove Agent Voice: Cancel") },
      function() { overlay.report("Remove Agent Voice cancelled") },
      function() { overlay.arm("⚠ Remove Agent Voice", "Remove Agent Voice") },
      function() {
        if (!overlay.launcherStubbed) { console.warn("PREVIEW SKIPPED confirming Remove Agent Voice: the launcher is not the stub"); return }
        overlay.click(overlay.button("Remove"), "Remove Agent Voice: Remove (confirm)")
      },
      function() { overlay.report("Remove Agent Voice confirmed") },
      // An agent's card (Agents)
      function() { overlay.open(JSON.stringify({ page: "agents", agent: overlay.firstAgentId() })) },
      function() { overlay.arm("⚠ Remove ", "Agents card") },
      function() { overlay.click(overlay.button("Cancel"), "Agents card: Cancel") },
      function() { overlay.report("Agents card cancelled") },
      function() { overlay.arm("⚠ Remove ", "Agents card") },
      function() { overlay.click(overlay.button("Remove"), "Agents card: Remove (confirm)") },
      function() { overlay.report("Agents card confirmed") },
      // Agent details, Advanced
      function() { overlay.open(JSON.stringify({ page: "agentdetails", agent: overlay.firstAgentId(), tab: "advanced" })) },
      function() { overlay.arm("⚠ Remove", "Agent details") },
      function() { overlay.click(overlay.button("Cancel"), "Agent details: Cancel") },
      function() { overlay.report("Agent details cancelled") },
      function() { overlay.arm("⚠ Remove", "Agent details") },
      function() { overlay.click(overlay.button("Remove"), "Agent details: Remove (confirm)") },
      function() { overlay.report("Agent details confirmed") },
      // A saved chat (conversation view)
      function() { overlay.put("saveChats", true) },
      function() {
        console.warn("PREVIEW synthetic chat: " + (overlay.chatId || "none") + " of " + overlay.chatCount)
        if (overlay.chatId !== "") overlay.showChat(overlay.chatId)
      },
      function() { overlay.arm("⚠ Delete", "chat Delete") },
      function() { overlay.click(overlay.button("Cancel"), "chat Delete: Cancel") },
      function() { overlay.report("chat Delete cancelled"); chatIndex.reload() },
      function() { console.warn("PREVIEW saved chats after Cancel: " + overlay.chatCount) },
      function() { overlay.arm("⚠ Delete", "chat Delete") },
      function() { overlay.click(overlay.button("Delete"), "chat Delete: Delete (confirm)") },
      function() { overlay.report("chat Delete confirmed"); chatIndex.reload() },
      function() { console.warn("PREVIEW saved chats after Delete: " + overlay.chatCount) },
      function() { console.warn("PREVIEW done") }
    ]
    property int step: 0
    Timer {
      interval: 1100
      repeat: true
      running: true
      onTriggered: {
        if (overlay.step >= 2 && overlay.step - 2 < overlay.steps.length) overlay.steps[overlay.step - 2]()
        overlay.step++
      }
    }
  }
}
