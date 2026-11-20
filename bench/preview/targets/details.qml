// The Agent details and Communal pages (merged plan, Phase 12), driven end
// to end through the real `agentvoice agents` command:
//
//   preview.sh --live-config --wait 100 --out /tmp/d details
//   grep PREVIEW /tmp/d.log; cat /tmp/d.writes
//
// Saves each of an agent's three files and both communal files, and checks
// the "What this agent is told" preview picks each one up; makes a save
// conflict and keeps "mine"; edits a file by hand and reverts it from the
// notice; forces a save the CLI refuses and checks the typed text stays and
// the reason shows; walks the tabs by synthetic click,
// saves on leaving the box, exports, removes an agent from Advanced and undoes it,
// restores one from the trash list, and trashes and restores a folder no
// agent uses. preview.sh points `agentvoice agents` at a scratch data folder
// (PREVIEW_DATA) and shell.json at a scratch copy, so nothing real is
// touched. Every check is a PREVIEW PASS or FAIL line in the log.
import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: {
      seed.running = true
      overlay.open('{"page":"agentdetails","agent":"main"}')
    }

    TestEvent { id: input }

    readonly property string scratch: Quickshell.env("PREVIEW_DATA")

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
    function details() { return find(content(), function(i) { return i.previewParts !== undefined && i.pickTab !== undefined }) }
    function editor(file) { return find(content(), function(i) { return i.file === file && i.saved !== undefined }) }
    function button(label) { return find(content(), function(i) { return i.text === label && i.clicked !== undefined }) }
    function click(item, label) {
      if (!item) { check(false, "found " + label); return }
      var flick = overlay.pageScroll
      if (flick && content()) {
        var y = item.mapToItem(content(), 0, 0).y
        flick.contentY = Math.max(0, Math.min(y - 120, flick.contentHeight - flick.height))
      }
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function told(text) {
      var p = details()
      if (!p) return ""
      for (var i = 0; i < p.previewParts.length; i++)
        if (String(p.previewParts[i].text).indexOf(text) >= 0) return p.previewParts[i].from
      return ""
    }
    function indexOf(id) {
      for (var i = 0; i < overlay.voiceAgents.length; i++)
        if (overlay.agentId(overlay.voiceAgents[i]) === id) return i
      return -1
    }
    function sh(script) {
      shell.command = ["bash", "-c", script, "preview", overlay.scratch]
      shell.running = true
    }

    // The folders, made from the scratch shell.json, as the daemon makes them.
    Process {
      id: seed
      command: ["agentvoice", "agents", "migrate"]
      onRunningChanged: if (!running) overlay.folders.refresh()
    }
    Process { id: shell }

    property int step: 0
    property int warm: 0
    property string made: ""
    property string trashName: ""

    Timer {
      interval: 2000
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || seed.running || ++overlay.warm < 3) return
        overlay.step++
        var p = overlay.details()
        var e
        switch (overlay.step) {
        case 1:
          overlay.check(p !== null && p.target === "main", "Agent details is open on the main agent")
          e = overlay.editor("role.md")
          overlay.check(e && e.loaded && e.exists, "its role is read from the migrated folder")
          if (e) e.save("Synthetic role: quick lookups.")
          break
        case 2:
          e = overlay.editor("role.md")
          overlay.check(e && e.saved === "Synthetic role: quick lookups." && e.status === "Saved · applies on the next turn",
                        "the role saved and says it applies on the next turn (" + (e ? e.status : "") + ")")
          overlay.editor("personality.md").save("Synthetic personality: dry and brief.")
          break
        case 3:
          overlay.check(overlay.told("Synthetic personality") === "From " + overlay.mainLabel + "'s personality",
                        "the preview shows the personality, labelled by its source (" + overlay.told("Synthetic personality") + ")")
          overlay.check(overlay.told("Synthetic role") === "", "its own role is not in what it is told")
          // Typed into the box, then saved by moving focus away, as a click
          // elsewhere does. (Ctrl+S and the keyboard walk need keyboard
          // focus, which a preview never takes: they are checked in the
          // real shell.)
          e = overlay.editor("instructions.md")
          var area = overlay.find(e, function(i) { return i.placeholderText !== undefined && i.textFormat !== undefined })
          overlay.check(area !== null, "the instructions box is found")
          if (area) {
            area.forceActiveFocus()
            area.text = "Synthetic instruction, saved on leaving the box."
            overlay.check(e.status.indexOf("Unsaved") === 0, "typing shows Unsaved (" + e.status + ")")
            overlay.pageScroll.forceActiveFocus()
          }
          break
        case 4:
          e = overlay.editor("instructions.md")
          overlay.check(e && e.saved === "Synthetic instruction, saved on leaving the box.", "leaving the box saved the instructions (" + (e ? e.status : "") + ")")
          overlay.check(overlay.told("saved on leaving the box") === "From " + overlay.mainLabel + "'s instructions", "the preview shows them")
          // Typing in the personality while someone else saves it: an idle
          // editor would just reload, so the edit must be under way.
          var parea = overlay.find(overlay.editor("personality.md"), function(i) { return i.placeholderText !== undefined && i.textFormat !== undefined })
          parea.forceActiveFocus()
          parea.text = "Mine, typed before the other save landed."
          overlay.sh('printf %s "\\"Written elsewhere.\\"" | agentvoice agents write main personality.md --line')
          break
        case 5:
          overlay.folders.refresh()
          // Leaving the box saves it, on the stamp read before the other save.
          Qt.callLater(function() { overlay.pageScroll.forceActiveFocus() })
          break
        case 6:
          e = overlay.editor("personality.md")
          overlay.check(e && e.conflictStamp !== "" && e.holding, "a stale save is refused, not applied (" + (e ? e.note : "") + ")")
          overlay.click(overlay.button("Keep mine"), "Keep mine")
          break
        case 7:
          e = overlay.editor("personality.md")
          overlay.check(e && e.saved === "Mine, typed before the other save landed." && !e.holding, "Keep mine replaced the other version")
          // A hand edit of the role, outside Settings.
          overlay.sh('printf "Edited by hand." > "$1/agents/main/role.md"')
          break
        case 8:
          overlay.folders.refresh()
          break
        case 9:
          e = overlay.editor("role.md")
          overlay.check(e && e.saved === "Edited by hand." && e.changedOutside, "a hand edit shows, with the outside-change notice")
          overlay.click(overlay.button("Revert"), "Revert")
          break
        case 10:
          e = overlay.editor("role.md")
          overlay.check(e && e.saved === "Synthetic role: quick lookups." && !e.changedOutside, "Revert put the saved version back")
          // A save the CLI refuses: the file has become a symlink.
          overlay.sh('rm "$1/agents/main/role.md" && ln -s /etc/hostname "$1/agents/main/role.md"')
          break
        case 11:
          overlay.editor("role.md").save("Typed, and refused.")
          break
        case 12:
          e = overlay.editor("role.md")
          overlay.check(e && e.holding && e.unsaved === "Typed, and refused." && e.note.indexOf("Not saved:") === 0,
                        "a refused save keeps the text and says why (" + (e ? e.note : "") + ")")
          overlay.sh('rm "$1/agents/main/role.md"')
          break
        case 13:
          overlay.editor("role.md").showTheirs()
          overlay.goTo("communal", "")
          break
        case 14:
          e = overlay.editor("rules.md")
          overlay.check(e && e.loaded, "Communal shows its rules")
          if (e) e.save("Synthetic rule: never shout.")
          overlay.editor("defaults.md").save("Synthetic default: metric units.")
          break
        case 15:
          overlay.check(overlay.editor("rules.md").saved === "Synthetic rule: never shout." &&
                        overlay.editor("defaults.md").saved === "Synthetic default: metric units.", "both communal files saved")
          overlay.goTo("agentdetails", "")
          break
        case 16:
          overlay.check(p && p.target === "main", "Agent details remembered the agent")
          overlay.check(overlay.told("never shout") === "From Communal · rules", "the rules reach the preview")
          overlay.check(overlay.told("metric units") === "From Communal · defaults", "and the defaults")
          overlay.click(overlay.button("Tools & skills"), "Tools & skills tab")
          break
        case 17:
          overlay.check(p.tab === "tools" && overlay.find(overlay.content(), function(i) { return i.text === "Desktop tools" }) !== null,
                        "a click opens Tools & skills")
          overlay.click(overlay.button("Chats"), "Chats tab")
          break
        case 18:
          overlay.check(p.tab === "chats", "a click opens Chats")
          overlay.check(overlay.s_saveText(), "Chats says what it shows (" + (overlay.saveChats ? "saving on" : "saving off") + ")")
          overlay.click(overlay.button("Advanced"), "Advanced tab")
          break
        case 19:
          overlay.check(p.tab === "advanced", "and Advanced")
          overlay.click(overlay.button("Export"), "Export")
          break
        case 20:
          overlay.check(overlay.folders.done.indexOf("Copied to ") === 0, "Export copied the folder (" + overlay.folders.done + ")")
          overlay.goTo("agents", "")
          break
        case 21:
          var ap = overlay.find(overlay.content(), function(i) { return i.addAgent !== undefined })
          overlay.made = ""
          if (ap) ap.addAgent()
          break
        case 22:
          overlay.made = overlay.agentId(overlay.voiceAgents[overlay.voiceAgents.length - 1] || {})
          overlay.check(overlay.made !== "" && overlay.folders.note === "", "an agent was added to remove (" + overlay.made + ")")
          overlay.goTo("agentdetails", overlay.made)
          break
        case 23:
          overlay.check(p && p.target === overlay.made && p.tab === "prompt", "the deep link opens its details")
          e = overlay.editor("instructions.md")
          overlay.check(e && e.target === overlay.made && e.loaded, "its editors read its own folder")
          // As the Dropdown does on a pick: assigns its own value, which
          // cuts its binding to the page.
          var dd = overlay.find(overlay.content(), function(i) { return i.options === p.choices && i.value !== undefined })
          if (dd) dd.value = overlay.made
          p.pickTab("advanced")
          break
        case 24:
          var rm = overlay.button("Remove")
          overlay.click(rm, "Remove")
          overlay.click(overlay.button("Remove " + p.name + "?"), "Remove, confirmed")
          break
        case 25:
          overlay.check(overlay.indexOf(overlay.made) < 0 && overlay.folders.trashed !== null, "Remove took it off the list, into the trash")
          overlay.check(p.target === "main", "and the page fell back to the main agent")
          var dd2 = overlay.find(overlay.content(), function(i) { return i.options === p.choices && i.value !== undefined })
          overlay.check(dd2 && dd2.value === "main", "and so did the agent picker (" + (dd2 ? dd2.value : "none") + ")")
          overlay.click(overlay.button("Undo"), "Undo")
          break
        case 26:
          overlay.check(overlay.indexOf(overlay.made) >= 0 && overlay.folders.trashed === null, "Undo put it back")
          overlay.folders.remove(overlay.indexOf(overlay.made))
          break
        case 27:
          overlay.trashName = overlay.folders.trashed ? overlay.folders.trashed.name : ""
          overlay.check(overlay.trashName !== "", "removed again")
          break
        case 28:
          overlay.check(overlay.folders.trash.length > 0 && overlay.folders.trash[0].name === overlay.trashName, "the trash list shows it")
          p.pickTab("advanced")
          overlay.click(overlay.find(overlay.content(), function(i) { return i.text === "Restore" && i.clicked !== undefined }), "Restore")
          break
        case 29:
          overlay.check(overlay.indexOf(overlay.made) >= 0, "Restore from the trash list put it back")
          overlay.sh('agentvoice agents create stray-preview')
          break
        case 30:
          overlay.folders.refresh()
          break
        case 31:
          overlay.check(overlay.folders.orphans.indexOf("stray-preview") >= 0, "a folder no agent uses is listed")
          var before = overlay.voiceAgents.length
          overlay.click(overlay.button("Move to trash"), "Move to trash")
          overlay.made = String(before)
          break
        case 32:
          overlay.check(overlay.folders.orphans.indexOf("stray-preview") < 0 &&
                        overlay.folders.trash.length > 0 && overlay.folders.trash[0].orphan === true,
                        "it went to the trash, marked as having no agent")
          overlay.folders.restore(overlay.folders.trash[0].name)
          break
        case 33:
          overlay.check(overlay.folders.done.indexOf("Put the folder stray-preview back") === 0 &&
                        String(overlay.voiceAgents.length) === overlay.made,
                        "restoring it brings the folder back and adds no agent (" + overlay.folders.done + ")")
          overlay.goTo("agentdetails", "main")
          break
        case 34:
          // A second save while the first is still writing is saved next.
          e = overlay.editor("role.md")
          e.save("Queued, first.")
          e.save("Queued, second.")
          break
        case 35:
          e = overlay.editor("role.md")
          overlay.check(e && e.saved === "Queued, second." && !e.holding,
                        "a save made during another is saved after it (" + (e ? e.saved : "") + ")")
          // Typing for one agent, then picking another before leaving the box.
          e = overlay.editor("personality.md")
          var area2 = overlay.find(e, function(i) { return i.placeholderText !== undefined && i.textFormat !== undefined })
          area2.forceActiveFocus()
          area2.text = "Typed for the main agent, then the agent changed."
          overlay.goTo("agentdetails", overlay.agentId(overlay.voiceAgents[overlay.voiceAgents.length - 1] || {}))
          break
        case 36:
          e = overlay.editor("personality.md")
          var area3 = overlay.find(e, function(i) { return i.placeholderText !== undefined && i.textFormat !== undefined })
          overlay.check(e && e.target !== "main" && area3.text.indexOf("Typed for the main agent") < 0,
                        "the other agent's editor does not show the main agent's typing")
          overlay.pageScroll.forceActiveFocus()
          overlay.goTo("agentdetails", "main")
          break
        case 37:
          e = overlay.editor("personality.md")
          overlay.check(e && e.saved === "Typed for the main agent, then the agent changed." && overlay.folders.note === "",
                        "and that typing was saved under the main agent (" + (e ? e.saved : "") + overlay.folders.note + ")")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        }
      }
    }
    function s_saveText() {
      var want = overlay.saveChats ? "No saved chats with" : "Saving chats is off"
      return overlay.find(overlay.content(), function(i) { return typeof i.text === "string" && i.text.indexOf(want) === 0 }) !== null
          || (overlay.saveChats && overlay.find(overlay.content(), function(i) { return i.openChat !== undefined }) !== null)
    }
  }
}
