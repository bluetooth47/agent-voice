// The two skill screens as phase M31 made them, driven by synthetic clicks
// through the real settings store, the real `agentvoice agents catalog` and
// the real `agentvoice skills communal`, on the synthetic machine preview.sh
// makes and the folders skills.seed.py writes (never the person's own):
//
//   preview.sh --config bench/preview/configs/skills3.json --scratch-data \
//     --wait 90 --out /tmp/s skills
//   grep PREVIEW /tmp/s.log; cat /tmp/s.writes
//
// With PREVIEW_ARG=shots it only opens Sora's Tools & skills tab at its
// skills (shots-tools: at its tools), and with shots-communal Communal → Skills, stepping down a screenful between shots
// (`--arg shots --shots 6`), for screenshots.
//
// Agent details → Tools & skills shows Sora alone: From communal (the two
// communal-folder skills and screen-notes, which every agent's program
// has), then her own. Exclude and Include again write her skillsOff; so
// does her own switch. Communal → Skills lists the communal ones, then every
// skill with a search and a switch: adding docx asks (who has it, Hazel does
// not), writes nothing before the answer or on Cancel, and Add to Communal
// writes communalSkills.add; Remove on screen-notes asks and writes
// communalSkills.remove. Back on Sora's tab, docx is under From communal and
// screen-notes under her own, still on.
import QtQuick
import QtTest
import Quickshell
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    // "shots", "shots-communal", either with ":WIDTH" to draw the card that
    // wide (narrow 520 shows the window the user called cramped).
    readonly property string mode: String(Quickshell.env("PREVIEW_ARG") || "").split(":")[0]
    readonly property int cardWidth: Number(String(Quickshell.env("PREVIEW_ARG") || "").split(":")[1] || 0)
    readonly property bool shotsOnly: mode === "shots" || mode === "shots-tools" || mode === "shots-communal"
    Component.onCompleted: overlay.open(mode === "shots-communal"
                                        ? '{"page":"communal","tab":"skills"}'
                                        : '{"page":"agentdetails","agent":"sora","tab":"tools"}')

    Loader {
      active: overlay.shotsOnly
      sourceComponent: Component { Scroller { target: overlay } }
    }
    // Shots: the card drawn at the asked width, and the page started at the
    // skills (they sit under the tools on Agent details), once they are read.
    property bool placed: false
    Timer {
      interval: 300
      repeat: true
      running: overlay.shotsOnly && !overlay.placed
      onTriggered: {
        var w = overlay.pageScroll ? overlay.pageScroll.Window.window : null
        var cardItem = w ? overlay.find(w.contentItem, function(i) { return i.objectName === "settingsCard" }) : null
        if (cardItem && overlay.cardWidth > 0) cardItem.width = overlay.cardWidth
        var at = overlay.named(overlay.mode === "shots" ? "skillsHeading"
                               : overlay.mode === "shots-tools" ? "toolsTab" : "communalSkills")
        var ready = overlay.mode === "shots-communal" ? overlay.named("communalList") !== null
                                                      : overlay.named("fromCommunal") !== null
        if (!at || !ready || !overlay.content()) return
        var f = overlay.pageScroll
        f.contentY = Math.max(0, Math.min(at.mapToItem(overlay.content(), 0, 0).y - 8, f.contentHeight - f.height))
        overlay.placed = true
      }
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
    function named(name) { return find(content(), function(i) { return i.objectName === name }) }
    function details() { return find(content(), function(i) { return i.switchSkill !== undefined && i.communalStatus !== undefined }) }
    function communal() { return find(content(), function(i) { return i.setCommunal !== undefined && i.communalRows !== undefined }) }
    function card(within, name) {
      return find(within, function(i) { return i.switchable !== undefined && i.details !== undefined && String(i.title) === name })
    }
    function toggleOf(c) { return c ? find(c, function(i) { return i.trackWidth !== undefined && i.toggled !== undefined }) : null }
    function button(within, text) { return find(within, function(i) { return i.clicked !== undefined && String(i.text) === text }) }
    function confirmBox() { return find(content(), function(i) { return i.confirmText !== undefined && i.lines !== undefined }) }
    function search() { return find(content(), function(i) { return i.searched !== undefined && i.placeholder !== undefined }) }
    // Key events never reach the preview window, so the text is set and the
    // field's own signal sent, as typing then a pause would.
    function type(t) { var f = search(); if (!f) { check(false, "found the search"); return } f.text = t; f.searched(t) }
    function soraOff() {
      for (var i = 0; i < overlay.voiceAgents.length; i++)
        if (overlay.agentId(overlay.voiceAgents[i]) === "sora") return overlay.voiceAgents[i].skillsOff || []
      return []
    }
    function grouping() { return JSON.stringify(overlay.setting("communalSkills", {})) }
    function cards(section) {
      var d = details()
      var all = d && d.catalog && d.catalog.agent === "sora" ? d.catalog.skill_cards || [] : []
      return all.filter(function(x) { return x.section === section }).map(function(x) { return x.name }).sort().join()
    }
    function rowNames(list) { return (list || []).map(function(r) { return r.name }).sort().join() }

    property int step: 0
    property int warm: 0

    Timer {
      interval: 2000
      repeat: true
      running: !overlay.shotsOnly
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        overlay.step++
        var c, box, d, row
        var text = ""
        switch (overlay.step) {
        case 1:
          overlay.check(overlay.cards("communal") === "house-style,screen-notes,weekly-report",
                        "Sora's From communal: the communal folder's two and screen-notes (" + overlay.cards("communal") + ")")
          overlay.check(overlay.cards("own") === "big-guide,docx,half-done,tea-timer",
                        "her own: her folder's and Claude Code's, nothing of another agent's (" + overlay.cards("own") + ")")
          d = overlay.details()
          row = d && d.catalog ? d.catalog.skill_cards.filter(function(x) { return x.name === "weekly-report" })[0] : null
          overlay.check(row && row.source === "communal" && row.also.length === 1 && row.also[0].where === "~/.claude/skills",
                        "one weekly-report card, the communal one, with Claude Code's copy under Also in")
          overlay.check(overlay.named("fromCommunal") !== null && overlay.named("ownSkills") !== null,
                        "two sections, and no lane of any other agent")
          overlay.click(overlay.button(overlay.card(overlay.named("fromCommunal"), "screen-notes"), "Exclude"),
                        "screen-notes → Exclude for Sora")
          break
        case 2:
          overlay.check(JSON.stringify(overlay.soraOff()) === '["screen-notes"]',
                        "Exclude wrote her skillsOff (" + JSON.stringify(overlay.soraOff()) + ")")
          break
        case 3:
          break                         // the store saves, the catalog reads it again
        case 4:
          c = overlay.card(overlay.named("fromCommunal"), "screen-notes")
          overlay.check(c && String(c.status).indexOf("Excluded for Sora") === 0, "the card says it is excluded for her")
          overlay.click(overlay.button(c, "Include again"), "screen-notes → Include again")
          break
        case 5:
          overlay.check(JSON.stringify(overlay.soraOff()) === "[]", "Include again took it off her list")
          overlay.click(overlay.toggleOf(overlay.card(overlay.named("ownSkills"), "docx")), "docx → off for Sora")
          break
        case 6:
          overlay.check(JSON.stringify(overlay.soraOff()) === '["docx"]', "her own switch writes the same list")
          break
        case 7:
          break
        case 8:
          overlay.click(overlay.toggleOf(overlay.card(overlay.named("ownSkills"), "docx")), "docx → on again")
          break
        case 9:
          overlay.check(JSON.stringify(overlay.soraOff()) === "[]", "and back on")
          overlay.goTo("communal", "", "skills")
          break
        case 10:
          break
        case 11:
          c = overlay.communal()
          overlay.check(c && overlay.rowNames(c.communalRows) === "house-style,screen-notes,weekly-report",
                        "Communal skills: the three every agent has (" + (c ? overlay.rowNames(c.communalRows) : "") + ")")
          overlay.check(c && c.skillRows.length === 10, "All skills lists every skill an agent has (" + (c ? c.skillRows.length : 0) + ")")
          row = c ? c.skillRows.filter(function(r) { return r.name === "deploy-site" })[0] : null
          overlay.check(row && JSON.stringify(row.has) === '["Hazel"]' && row.lacks.length === 2 &&
                        row.lacks[0].why === "Claude Code has no skill of this name",
                        "deploy-site: Hazel has it, and it says why Theo and Sora do not")
          overlay.type("tea")
          break
        case 12:
          c = overlay.communal()
          overlay.check(c && overlay.rowNames(c.shownRows) === "tea-timer", "the search finds tea-timer alone")
          overlay.type("docx")
          break
        case 13:
          overlay.click(overlay.toggleOf(overlay.card(overlay.named("allSkills"), "docx")), "docx → into Communal")
          break
        case 14:
          box = overlay.confirmBox()
          text = box ? String(box.title) + JSON.stringify(box.lines) : ""
          overlay.check(box !== null && box.title === "Add docx to Communal?", "adding asks first")
          overlay.check(String(text).indexOf("Theo and Sora") >= 0 && String(text).indexOf("Hazel (Codex has no skill of this name)") >= 0 &&
                        String(text).indexOf("No agent is given a copy") >= 0,
                        "the confirm names who has it, who does not, and that nothing is copied")
          overlay.check(overlay.grouping() === "{}", "nothing is written before the answer")
          overlay.click(overlay.button(box, "Cancel"), "Cancel")
          break
        case 15:
          overlay.check(overlay.confirmBox() === null && overlay.grouping() === "{}", "Cancel closes it and writes nothing")
          overlay.click(overlay.toggleOf(overlay.card(overlay.named("allSkills"), "docx")), "docx → into Communal, again")
          break
        case 16:
          overlay.click(overlay.button(overlay.confirmBox(), "Add to Communal"), "Add to Communal")
          break
        case 17:
          overlay.check(overlay.grouping() === '{"add":["docx"],"remove":[]}', "it wrote communalSkills.add (" + overlay.grouping() + ")")
          overlay.type("")
          break
        case 18:
          break
        case 19:
          c = overlay.communal()
          row = c ? c.communalRows.filter(function(r) { return r.name === "docx" })[0] : null
          overlay.check(row && row.added === true, "docx is communal now, marked added")
          overlay.click(overlay.button(overlay.card(overlay.named("communalList"), "screen-notes"), "Remove…"),
                        "screen-notes → Remove…")
          break
        case 20:
          box = overlay.confirmBox()
          text = box ? String(box.title) + JSON.stringify(box.lines) : ""
          overlay.check(box !== null && box.title === "Remove screen-notes from Communal?", "Remove asks first")
          overlay.check(String(text).indexOf("Nothing is switched off") >= 0 && String(text).indexOf("until you add it back") >= 0,
                        "and says it goes back to each agent, still on, and stays out until added back")
          overlay.click(overlay.button(box, "Remove"), "Remove")
          break
        case 21:
          overlay.check(overlay.grouping() === '{"add":["docx"],"remove":["screen-notes"]}',
                        "it wrote communalSkills.remove (" + overlay.grouping() + ")")
          break
        case 22:
          break
        case 23:
          c = overlay.communal()
          overlay.check(c && overlay.rowNames(c.communalRows) === "docx,house-style,weekly-report",
                        "screen-notes is out of Communal (" + (c ? overlay.rowNames(c.communalRows) : "") + ")")
          overlay.goTo("agentdetails", "sora", "tools")
          break
        case 24:
          break
        case 25:
          overlay.check(overlay.cards("communal") === "docx,house-style,weekly-report",
                        "back on Sora's tab, docx is under From communal (" + overlay.cards("communal") + ")")
          d = overlay.details()
          row = d && d.catalog ? d.catalog.skill_cards.filter(function(x) { return x.name === "screen-notes" })[0] : null
          overlay.check(row && row.section === "own" && row.on === true && row.delivered === true,
                        "and screen-notes is her own again, still on and given")
          overlay.check(JSON.stringify(overlay.soraOff()) === "[]", "nothing was switched off for her")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          Qt.quit()
          break
        }
      }
    }
  }
}
