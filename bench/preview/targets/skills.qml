// Skills on this machine, lanes and a switch per skill (master plan, M11),
// driven by synthetic clicks through the real settings store, the real
// `agentvoice agents catalog` and the real `agentvoice skills import`, on
// the synthetic machine preview.sh makes and the folders skills.seed.py
// writes (never the person's own):
//
//   preview.sh --config bench/preview/configs/skills3.json --scratch-data \
//     --wait 90 --out /tmp/s skills
//   grep PREVIEW /tmp/s.log; cat /tmp/s.writes
//
// With PREVIEW_ARG=shots it only opens Sora's tab and steps down a
// screenful between shots (`--arg shots --shots 6`), for screenshots.
//
// Sora's lane: her own, the broken one listed with why, and the three
// Claude Code finds by itself (one hidden by the communal skill of its
// name). Switching big-guide off writes her skillsOff and, since Theo has
// it off too, moves it to Unused, where it says it is too long to copy.
// crash-notes (Hazel switched it off) is given to Sora as a copy: the
// confirm names the source and who gets it, Cancel copies nothing, Give a
// copy makes it hers. A communal one is switched off and on for her alone.
// Communal → Skills says how each agent takes them.
import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    readonly property bool shotsOnly: Quickshell.env("PREVIEW_ARG") === "shots"
    Component.onCompleted: overlay.open('{"page":"agentdetails","agent":"sora","tab":"tools"}')

    Loader {
      active: overlay.shotsOnly
      sourceComponent: Component { Scroller { target: overlay } }
    }
    TestEvent { id: input }

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
        flick.contentY = Math.max(0, Math.min(y - 120, flick.contentHeight - flick.height))
      }
      console.warn("PREVIEW click " + label)
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function details() { return find(content(), function(i) { return i.importSkill !== undefined && i.switchSkill !== undefined }) }
    function lane(id) { return find(content(), function(i) { return i.laneId === id && i.received !== undefined }) }
    function card(within, name) {
      return find(within, function(i) { return i.switchable !== undefined && i.details !== undefined && String(i.title) === name })
    }
    function toggleOf(c) { return c ? find(c, function(i) { return i.trackWidth !== undefined && i.toggled !== undefined }) : null }
    function button(within, text) { return find(within, function(i) { return i.clicked !== undefined && String(i.text) === text }) }
    function confirmBox() { return find(content(), function(i) { return i.confirmText !== undefined && i.lines !== undefined }) }
    function soraOff() {
      for (var i = 0; i < overlay.voiceAgents.length; i++)
        if (overlay.agentId(overlay.voiceAgents[i]) === "sora") return overlay.voiceAgents[i].skillsOff || []
      return []
    }
    function skillsOf(field) {
      var d = details()
      return d && d.catalog ? d.catalog[field] : null
    }

    Process {
      id: probe
      property int code: -1
      command: ["test", "-f", Quickshell.env("PREVIEW_DATA") + "/agents/sora/skills/crash-notes/SKILL.md"]
      onExited: function(c) { probe.code = c }
    }

    property int step: 0
    property int warm: 0

    Timer {
      interval: 2000
      repeat: true
      running: !overlay.shotsOnly
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        overlay.step++
        var d, c, box, sk, names, lanes, unused, text
        switch (overlay.step) {
        case 1:
          d = overlay.details()
          sk = d && d.catalog ? d.catalog.skills : []
          names = sk.map(function(x) { return x.source + ":" + x.name }).sort()
          overlay.check(JSON.stringify(names) === JSON.stringify([
            "claude-synced:docx", "claude-user:big-guide", "claude-user:weekly-report",
            "communal:house-style", "communal:weekly-report", "sora:half-done", "sora:tea-timer"]),
                        "Sora's tab lists her own, the communal and Claude Code's own, nothing real (" + names.join(", ") + ")")
          var broken = sk.filter(function(x) { return x.name === "half-done" })[0]
          overlay.check(broken && !broken.delivered && broken.problem.indexOf("description") >= 0,
                        "a broken skill is listed, given to nobody, with why")
          var hidden = sk.filter(function(x) { return x.source === "claude-user" && x.name === "weekly-report" })[0]
          overlay.check(hidden && hidden.shadowed && !hidden.delivered, "Claude Code's weekly-report is hidden by the communal one")
          unused = (overlay.skillsOf("skill_lanes") || {}).unused || []
          // crash-notes: Hazel switched it off, and she is the only Codex
          // agent; weekly-report: every Claude agent gets the communal one
          // of that name instead.
          overlay.check(unused.map(function(x) { return x.name }).sort().join() === "crash-notes,weekly-report",
                        "Unused holds the ones nobody gets (" + unused.map(function(x) { return x.name }).join() + ")")
          overlay.click(overlay.toggleOf(overlay.card(overlay.lane("sora"), "big-guide")), "big-guide → off for Sora")
          break
        case 2:
          overlay.check(JSON.stringify(overlay.soraOff()) === '["big-guide"]',
                        "the switch wrote her skillsOff (" + JSON.stringify(overlay.soraOff()) + ")")
          break
        case 3:
          break                         // the store saves, the catalog reads it again
        case 4:
          unused = (overlay.skillsOf("skill_lanes") || {}).unused || []
          var big = unused.filter(function(x) { return x.name === "big-guide" })[0]
          overlay.check(big && big.copy_problem.indexOf("longer than") >= 0,
                        "big-guide is Unused now, and says it is too long to copy")
          overlay.click(overlay.button(overlay.card(overlay.lane("unused"), "crash-notes").parent, "Give a copy to Sora…"),
                        "crash-notes → Give a copy to Sora")
          break
        case 5:
          box = overlay.confirmBox()
          text = box ? box.title + JSON.stringify(box.lines) + box.warning : ""
          overlay.check(box !== null, "giving a skill asks first")
          overlay.check(text.indexOf(".agents/skills/crash-notes") >= 0 && text.indexOf("Sora only") >= 0,
                        "the confirm says where it is copied from and who gets it")
          probe.running = true
          break
        case 6:
          overlay.check(probe.code === 1, "nothing is copied before the answer")
          overlay.click(overlay.button(overlay.confirmBox(), "Cancel"), "Cancel")
          break
        case 7:
          overlay.check(overlay.confirmBox() === null, "Cancel closes it")
          probe.running = true
          break
        case 8:
          overlay.check(probe.code === 1, "Cancel copied nothing")
          overlay.click(overlay.button(overlay.card(overlay.lane("unused"), "crash-notes").parent, "Give a copy to Sora…"),
                        "Give a copy to Sora, again")
          break
        case 9:
          overlay.click(overlay.button(overlay.confirmBox(), "Give a copy"), "Give a copy")
          break
        case 10:
          break
        case 11:
          probe.running = true
          break
        case 12:
          overlay.check(probe.code === 0, "Give a copy put crash-notes in Sora's folder")
          sk = overlay.skillsOf("skills") || []
          var mine = sk.filter(function(x) { return x.source === "sora" && x.name === "crash-notes" })[0]
          overlay.check(mine && mine.delivered && mine.changed_outside === false,
                        "it is hers, given, and not marked changed outside Settings")
          overlay.click(overlay.toggleOf(overlay.card(overlay.lane("communal"), "house-style")), "house-style → off for Sora")
          break
        case 13:
          overlay.check(overlay.soraOff().indexOf("house-style") >= 0, "a communal skill is switched off for her alone")
          break
        case 14:
          break
        case 15:
          overlay.click(overlay.toggleOf(overlay.card(overlay.lane("communal"), "house-style")), "house-style → on again")
          break
        case 16:
          overlay.check(overlay.soraOff().indexOf("house-style") < 0 && overlay.soraOff().indexOf("big-guide") >= 0,
                        "and back on, leaving big-guide off (" + JSON.stringify(overlay.soraOff()) + ")")
          overlay.goTo("communal", "", "skills")
          break
        case 17:
          break
        case 18:
          c = overlay.find(overlay.content(), function(i) { return i.skillLanes !== undefined && i.takesLine !== undefined })
          lanes = c ? c.skillLanes : []
          overlay.check(lanes.length === 3, "Communal → Skills reads every agent's lane")
          var hz = lanes.filter(function(l) { return l.id === "hazel" })[0]
          overlay.check(hz && c.takesLine(hz).indexOf("told a list") >= 0, "and says Hazel (Codex) is told a list")
          var hs = (c ? c.skillList : []).filter(function(x) { return x.name === "house-style" })[0]
          overlay.check(hs && hs.gets.length === 3, "house-style goes to all three again (" + (hs ? hs.gets.join(", ") : "") + ")")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          Qt.quit()
          break
        }
      }
    }
  }
}
