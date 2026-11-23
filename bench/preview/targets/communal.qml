// Communal: who gets it, the whole prompt, History and Import (master plan,
// M15), driven by synthetic mouse events (QtTest's TestEvent: the real
// pointer never moves) through the real page, the real `agentvoice agents
// prompt|history|version|revert|import|import-undo` and a scratch data
// folder that communal.seed.py writes:
//
//   preview.sh --config bench/preview/configs/transfer3.json --scratch-data \
//     --wait 90 --out /tmp/cm communal
//   grep PREVIEW /tmp/cm.log; cat /tmp/cm.writes
//
// --arg shots walks one tab a screenful at a time instead (--arg shots:who,
// shots:preview, shots:rules), clicking nothing.
//
// Who gets it: three switches, all on; Sora's switched off writes
// `communalOff` ["sora"] (to the scratch shell.json) and offers Start fresh,
// which is logged, never sent to a daemon. Preview: Theo's prompt has the
// rules; Sora's has none and says she takes nothing from Communal; the
// total is the pieces plus their separators. Rules: History lists two
// versions; View shows the older one's diff; Restore puts it back and Undo
// brings the newer back. Import: Check lists the rules' diff, the new skill
// and the ignored README, and changes nothing; Import… asks, Import commits,
// Undo takes it back.
import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    readonly property string arg: Quickshell.env("PREVIEW_ARG") || ""
    readonly property bool shotsOnly: arg.indexOf("shots") === 0
    readonly property string shotsTab: arg.indexOf("shots:") === 0 ? arg.slice(6) : "who"
    Component.onCompleted: overlay.open('{"page":"communal"}')
    TestEvent { id: input }
    Loader {
      active: overlay.shotsOnly
      sourceComponent: Component { Scroller { target: overlay } }
    }
    Timer {
      interval: 1200
      running: overlay.shotsOnly
      onTriggered: overlay.goTo("communal", "", overlay.shotsTab)
    }
    // shots:rules also unfolds the rules' History with its older version
    // shown, and checks the synthetic export in the import box.
    Timer {
      interval: 2600
      running: overlay.shotsOnly && overlay.shotsTab === "rules"
      onTriggered: {
        var h = overlay.history("rules.md")
        if (h) { h.expanded = true; viewOld.start() }
        var p = overlay.page()
        if (p) p.importing = true
        importCheck.start()
      }
    }
    Timer {
      id: viewOld
      interval: 800
      onTriggered: { var h = overlay.history("rules.md"); if (h && h.versions.length > 1) h.view(String(h.versions[1].version)) }
    }
    Timer {
      id: importCheck
      interval: 600
      onTriggered: { var im = overlay.importer(); if (im) im.check(Quickshell.env("PREVIEW_DATA") + "/../import-me") }
    }

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
    function scrollTo(item, above) {
      var flick = overlay.pageScroll
      if (!item || !flick || !content()) return
      var y = item.mapToItem(content(), 0, 0).y
      flick.contentY = Math.max(0, Math.min(y - (above || 40), flick.contentHeight - flick.height))
    }
    function click(item, label) {
      if (!item) { check(false, "found " + label); return }
      scrollTo(item, 120)
      console.warn("PREVIEW click " + label)
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function page() { return find(content(), function(i) { return i.setTakes !== undefined }) }
    function row(label) { return find(content(), function(i) { return i.toggled !== undefined && i.hint !== undefined && String(i.label) === label }) }
    function switchIn(r) { return r ? find(r, function(i) { return i !== r && i.toggled !== undefined }) : null }
    function button(within, text) {
      return find(within, function(i) { return i.clicked !== undefined && String(i.text).indexOf(text) === 0 })
    }
    function history(file) { return find(content(), function(i) { return i.restored !== undefined && i.file === file }) }
    function importer() { return find(content(), function(i) { return i.commitImport !== undefined }) }
    function confirmBox() { return find(content(), function(i) { return i.confirmText !== undefined && i.lines !== undefined }) }

    property string writes: ""
    FileView {
      id: writesFile
      path: Quickshell.env("PREVIEW_WRITES") || "/nonexistent"
      printErrors: false
      onLoaded: overlay.writes = text()
    }
    property string files: ""
    Process {
      id: lister
      command: ["sh", "-c", "cd \"$PREVIEW_DATA\" && find communal -not -path '*/.history*' -type f | sort; " +
                            "printf 'RULES:'; tr '\\n' '|' < communal/rules.md"]
      stdout: StdioCollector { onStreamFinished: overlay.files = String(text) }
    }
    function look() { lister.running = true; writesFile.reload() }

    property int step: 0
    property int warm: 0
    Timer {
      interval: 2000
      repeat: true
      running: !overlay.shotsOnly
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        overlay.step++
        var p = overlay.page(), r, h, im, b
        switch (overlay.step) {
        case 1:
          overlay.goTo("communal", "", "who")
          break
        case 2:
          overlay.check(overlay.row("Theo") && overlay.row("Sora") && overlay.row("Hazel"), "a switch for each agent")
          overlay.check(overlay.row("Sora") && overlay.row("Sora").checked, "every agent takes Communal at first")
          overlay.click(overlay.switchIn(overlay.row("Sora")), "Sora's switch")
          break
        case 3:
          overlay.look()
          break
        case 4:
          overlay.check(overlay.writes.indexOf('communalOff ["sora"]') >= 0, "it writes communalOff [\"sora\"] (" + overlay.writes.trim().split("\n").pop() + ")")
          overlay.check(overlay.row("Sora") && !overlay.row("Sora").checked, "Sora's switch shows off")
          overlay.click(overlay.button(overlay.content(), "Start fresh"), "Start fresh")
          break
        case 5:
          overlay.look()
          break
        case 6:
          overlay.check(overlay.writes.indexOf("agentvoice chats new sora") >= 0, "Start fresh is `chats new sora` (logged, not sent)")
          overlay.goTo("communal", "", "preview")
          break
        case 7:
          overlay.check(p && p.promptView !== null && p.promptView.agent === "main", "Preview shows Theo's prompt")
          overlay.check(p && p.promptView && p.promptView.pieces.some(function(x) { return x.key === "rules" }), "Theo is told the rules")
          overlay.check(p && p.promptView && p.promptView.total === p.promptView.pieces.reduce(function(n, x) { return n + x.chars }, 0) + p.promptView.separators,
                        "the total is the pieces and their separators")
          if (p) { p.previewAgent = "sora"; p.promptView = null; p.loadPrompt() }
          break
        case 8:
          overlay.check(p && p.promptView && p.promptView.agent === "sora" && p.promptView.takes_communal === false,
                        "Sora's says she takes nothing from Communal")
          overlay.check(p && p.promptView && !p.promptView.pieces.some(function(x) { return x.key === "rules" || x.key === "defaults" }),
                        "and has no rules or defaults")
          overlay.check(p && p.promptView && p.promptView.pieces.some(function(x) { return x.key === "instructions" }),
                        "and keeps her own instructions")
          overlay.goTo("communal", "", "rules")
          break
        case 9:
          h = overlay.history("rules.md")
          overlay.check(h !== null, "History beside the rules editor")
          if (h) h.expanded = true
          break
        case 10:
          h = overlay.history("rules.md")
          overlay.check(h && h.versions.length === 2, "two saved versions (" + (h ? h.versions.length : "-") + ")")
          if (h && h.versions.length === 2) h.view(String(h.versions[1].version))
          break
        case 11:
          h = overlay.history("rules.md")
          overlay.check(h && h.shown && h.shown.diff.indexOf("+Never buy anything.") >= 0, "View shows the diff to now")
          overlay.click(overlay.find(h, function(i) { return i.clicked !== undefined && i.text === "Restore" && i.enabled }), "Restore the older one")
          break
        case 12:
          overlay.look()
          break
        case 13:
          overlay.check(overlay.files.indexOf("RULES:Ask before deleting anything.") >= 0 && overlay.files.indexOf("Never buy") < 0,
                        "Restore put the older rules back")
          h = overlay.history("rules.md")
          overlay.click(overlay.button(h, "Undo"), "Undo the restore")
          break
        case 14:
          overlay.look()
          break
        case 15:
          overlay.check(overlay.files.indexOf("Never buy anything.") >= 0, "Undo brought the newer rules back")
          overlay.click(overlay.button(overlay.content(), "Import…"), "Import…")
          break
        case 16:
          im = overlay.importer()
          overlay.check(im !== null, "the import box opens")
          if (im) {
            var field = overlay.find(im, function(i) { return i.placeholderText !== undefined })
            if (field) field.text = Quickshell.env("PREVIEW_DATA") + "/../import-me"
            overlay.click(overlay.button(im, "Check"), "Check")
          }
          break
        case 17:
          im = overlay.importer()
          overlay.check(im && im.planned && im.planned.problems.length === 0 && im.planned.changes === 2,
                        "Check lists two changes and no problem")
          overlay.check(im && im.planned && im.planned.ignored.join() === "README.txt", "and the README as ignored")
          overlay.check(im && im.planned && im.planned.reaches.join() === "Theo,Hazel", "reaching Theo and Hazel, not Sora (" + (im && im.planned ? im.planned.reaches.join() : "") + ")")
          overlay.look()
          break
        case 18:
          overlay.check(overlay.files.indexOf("packing-list") < 0, "Check changed nothing")
          im = overlay.importer()
          overlay.click(overlay.button(im, "Import…"), "the import's Import…")
          break
        case 19:
          b = overlay.confirmBox()
          overlay.check(b && b.title === "Import into Communal?" && JSON.stringify(b.lines).indexOf("skills/packing-list/SKILL.md") >= 0,
                        "it asks, listing the files")
          overlay.click(overlay.find(b, function(i) { return i.clicked !== undefined && i.text === "Import" }), "Import")
          break
        case 20:
          overlay.look()
          break
        case 21:
          overlay.check(overlay.files.indexOf("communal/skills/packing-list/SKILL.md") >= 0 && overlay.files.indexOf("Say when you are unsure.") >= 0,
                        "Import brought the skill and the rules in")
          overlay.click(overlay.button(overlay.importer(), "Undo"), "Undo the import")
          break
        case 22:
          overlay.look()
          break
        case 23:
          overlay.check(overlay.files.indexOf("packing-list") < 0 && overlay.files.indexOf("Say when you are unsure.") < 0,
                        "Undo took the import back")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        }
      }
    }
  }
}
