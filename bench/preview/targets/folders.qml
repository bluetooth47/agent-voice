// The Agents page and the agent folders (merged plan, Phase 10), end to end
// through real saves and the real `agentvoice agents` command:
//
//   preview.sh --live-config --wait 30 --out /tmp/f folders
//   grep PREVIEW /tmp/f.log
//
// Adds an agent (its folder is made), saves its instructions on Agent
// details (into the folder, not shell.json), removes it from the Agents page
// (folder and settings to the trash), and undoes that (both back,
// instructions intact). preview.sh points
// `agentvoice agents` at a scratch data folder and shell.json at a scratch
// copy, so no real agent or setting is touched.
import QtQuick
import Quickshell
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open('{"page":"agents"}')

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
    function content() { return overlay.pageScroll ? overlay.pageScroll.contentItem : null }
    function page() { return find(content(), function(i) { return i.addAgent !== undefined && i.undoRemove !== undefined }) }
    function box(id) { return find(content(), function(i) { return i.target === id && i.file === "instructions.md" && i.saved !== undefined }) }
    function indexOf(id) {
      for (var i = 0; i < overlay.voiceAgents.length; i++)
        if (overlay.agentId(overlay.voiceAgents[i]) === id) return i
      return -1
    }

    property int warm: 0
    property int step: 0
    property int before: 0
    property string made: ""

    Timer {
      interval: 1500
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        overlay.step++
        var p = overlay.page()
        switch (overlay.step) {
        case 1:
          overlay.check(p !== null, "the Agents page is open")
          overlay.before = overlay.voiceAgents.length
          if (p) p.addAgent()
          break
        case 2:
          overlay.check(overlay.voiceAgents.length === overlay.before + 1, "an agent was added")
          overlay.made = overlay.agentId(overlay.voiceAgents[overlay.voiceAgents.length - 1] || {})
          overlay.check(overlay.folders.note === "", "its folder was made (" + (overlay.folders.note || "no note") + ")")
          overlay.goTo("agentdetails", overlay.made)
          break
        case 3:
          var b = overlay.box(overlay.made)
          overlay.check(b !== null && b.exists, "its instructions editor reads the new folder")
          if (b) b.save("Be brief, synthetic test.")
          break
        case 4:
          var b3 = overlay.box(overlay.made)
          overlay.check(b3 && b3.saved === "Be brief, synthetic test." && b3.note === "",
                        "its instructions were saved to the folder")
          var entry = overlay.voiceAgents[overlay.indexOf(overlay.made)] || {}
          overlay.check(entry.instructions === undefined, "and not into its settings entry")
          overlay.goTo("agents", "")
          break
        case 5:
          p.removeAgent(overlay.indexOf(overlay.made))
          break
        case 6:
          overlay.check(overlay.indexOf(overlay.made) < 0, "removing it took it off the list")
          overlay.check(overlay.folders.trashed !== null && overlay.folders.trashed.name.indexOf(overlay.made + "-") === 0,
                        "and says it went to the trash")
          p.undoRemove()
          break
        case 7:
          overlay.check(overlay.indexOf(overlay.made) >= 0, "Undo put it back")
          overlay.check(overlay.folders.trashed === null && overlay.folders.note === "", "with nothing left to say")
          overlay.goTo("agentdetails", overlay.made)
          break
        case 8:
          var b6 = overlay.box(overlay.made)
          overlay.check(b6 && b6.saved === "Be brief, synthetic test.", "its instructions came back with it")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        }
      }
    }
  }
}
