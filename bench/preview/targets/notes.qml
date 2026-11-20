// Notes (merged plan, Phase 14), driven by synthetic clicks through the real
// settings store and the real `agentvoice agents notes`:
//
//   preview.sh --live-config --wait 70 --out /tmp/n notes
//   grep PREVIEW /tmp/n.log; cat /tmp/n.writes
//
// The notes knob on the main card and on Sora's (Read only, then May write,
// watching mainNotesWrite and her entry's notesWrite); Sora's Notes tab on
// Agent details (a seeded note and a dropped file listed, the note opened,
// edited and saved, a save refused because the note changed underneath and
// then kept with "Keep mine", the lock and unlock, History and Restore);
// Communal's Notes tab, and a corrupt .meta.json shown as every note locked.
// Synthetic notes only, in the scratch data folder; shell.json is a scratch
// copy.
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
      overlay.open('{"page":"agents","agent":"main"}')
    }

    TestEvent { id: input }

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
    function click(item, label) {
      if (!item) { check(false, "found " + label); return }
      var flick = overlay.pageScroll
      if (flick && content()) {
        var y = item.mapToItem(content(), 0, 0).y
        flick.contentY = Math.max(0, Math.min(y - 120, flick.contentHeight - flick.height))
      }
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function card(id) {
      return find(content(), function(i) {
        return i.switchedOff !== undefined && (id === "main" ? i.isDefault === true : i.agentId === id)
      })
    }
    function switches(id) {
      return find(card(id), function(i) { return i.globals !== undefined && i.notesPicked !== undefined })
    }
    function notesRow(sw) {
      return find(sw, function(i) { return i.label === "Notes" && i.reset !== undefined })
    }
    function chip(item, text) {
      return find(item, function(i) { return i.clicked !== undefined && i.text === text })
    }
    function indexOf(id) {
      for (var i = 0; i < overlay.voiceAgents.length; i++)
        if (overlay.agentId(overlay.voiceAgents[i]) === id) return i
      return -1
    }
    function panel() { return find(content(), function(i) { return i.notesList !== undefined && i.openName !== undefined }) }
    function editor(p) { return find(p, function(i) { return i.committed !== undefined && i.reset !== undefined }) }
    function entry(p, name) {
      var l = p ? p.notesList : []
      for (var i = 0; i < l.length; i++) if (l[i].name === name) return l[i]
      return null
    }
    function row(p, name) {
      return find(p, function(i) { return i.modelData !== undefined && i.modelData.name === name && i.modelData.rev !== undefined })
    }

    // The folders as the daemon makes them, then one synthetic note for Sora
    // and a file dropped beside it.
    Process {
      id: seed
      command: ["bash", "-c",
        'agentvoice agents migrate >/dev/null && d="$1" && ' +
        'printf "%s\\n" "\\"Buy milk.\\"" | agentvoice agents notes sora write shopping --line >/dev/null && ' +
        'printf "png" > "$d/agents/sora/notes/photo.png"',
        "seed", Quickshell.env("PREVIEW_DATA")]
    }
    // A change made underneath the open editor, as an agent's write would be.
    // Saved from the editor the moment it lands, before the 4s poll would
    // notice it and (rightly) reload the idle editor instead.
    Process {
      id: underneath
      command: ["bash", "-c", 'printf "%s\\n" "\\"Changed by someone else.\\"" | agentvoice agents notes sora write shopping --line --base 2']
      onRunningChanged: if (!running) {
        var b = overlay.editor(overlay.panel())
        b.reset("My own version.")
        b.commit()
      }
    }
    Process {
      id: corrupt
      command: ["bash", "-c", 'mkdir -p "$1/communal/notes" && printf "%s\\n" "\\"x\\"" | agentvoice agents notes communal write shared --line >/dev/null && printf "{broken" > "$1/communal/notes/.meta.json"',
                "corrupt", Quickshell.env("PREVIEW_DATA")]
    }

    property int step: 0
    property int warm: 0

    Timer {
      interval: 2000
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || seed.running || ++overlay.warm < 3) return
        overlay.step++
        var sw, r, p, e, b, i
        switch (overlay.step) {
        case 1:
          overlay.goTo("agents", "main", "tools")
          break
        case 2:
          sw = overlay.switches("main")
          r = overlay.notesRow(sw)
          overlay.check(r !== null && r.stacked, "the main card's group has a Notes row with a switch")
          overlay.click(overlay.chip(r, "Read only"), "main Notes Read only")
          break
        case 3:
          overlay.check(overlay.setting("mainNotesWrite", "allow") === "deny",
                        "Read only writes mainNotesWrite = deny (" + overlay.setting("mainNotesWrite", "?") + ")")
          sw = overlay.switches("main")
          overlay.check(sw && sw.summary.indexOf("notes read only") >= 0, "the group's summary says so (" + (sw ? sw.summary : "") + ")")
          overlay.click(overlay.chip(overlay.notesRow(sw), "May write"), "main Notes May write")
          break
        case 4:
          overlay.check(overlay.setting("mainNotesWrite", "?") === "allow", "May write puts it back to allow")
          overlay.goTo("agents", "sora", "tools")
          break
        case 5:
          overlay.click(overlay.chip(overlay.notesRow(overlay.switches("sora")), "Read only"), "Sora Notes Read only")
          break
        case 6:
          i = overlay.indexOf("sora")
          e = i >= 0 ? overlay.voiceAgents[i] : {}
          overlay.check(e.notesWrite === "deny", "Read only writes her entry's notesWrite = deny (" + JSON.stringify(e.notesWrite) + ")")
          overlay.click(overlay.chip(overlay.notesRow(overlay.switches("sora")), "May write"), "Sora Notes May write")
          break
        case 7:
          i = overlay.indexOf("sora")
          e = i >= 0 ? overlay.voiceAgents[i] : {}
          overlay.check(e.notesWrite === undefined, "May write removes the key, so the entry is as it was")
          overlay.goTo("agentdetails", "sora", "notes")
          break
        case 8:
          break                           // the list is read on open
        case 9:
          p = overlay.panel()
          e = overlay.entry(p, "shopping")
          overlay.check(e !== null && e.rev === 1 && e.author === "you", "Sora's Notes tab lists the seeded note (" + JSON.stringify(e) + ")")
          overlay.check(p && p.otherFiles.length === 1 && p.otherFiles[0].name === "photo.png", "and the dropped file as another file")
          overlay.check(p && p.whyNot === "", "Claude Code takes the notes tools, so nothing says otherwise")
          overlay.click(overlay.row(p, "shopping"), "the shopping row")
          break
        case 10:
          p = overlay.panel()
          b = overlay.editor(p)
          overlay.check(p && p.openName === "shopping" && b && b.text === "Buy milk.", "a click opens it in the editor")
          b.reset("Buy milk and eggs.")
          b.commit()
          break
        case 11:
          p = overlay.panel()
          overlay.check(p && p.noteRev === 2 && p.justSaved, "saving writes rev 2 (" + (p ? p.noteRev + " " + p.noteNote : "") + ")")
          underneath.running = true
          break
        case 12:
          break
        case 13:
          p = overlay.panel()
          overlay.check(p && p.conflictRev === 3 && p.noteNote.indexOf("Changed since you opened it") === 0,
                        "a save on a rev that moved is refused and says why (" + (p ? p.noteNote : "") + ")")
          overlay.click(overlay.chip(p, "Keep mine"), "Keep mine")
          break
        case 14:
          p = overlay.panel()
          e = overlay.entry(p, "shopping")
          overlay.check(p && p.noteRev === 4 && p.conflictRev === -1 && p.noteText === "My own version.", "Keep mine saves it on the new rev")
          overlay.click(overlay.chip(overlay.row(p, "shopping"), "Lock"), "Lock")
          break
        case 15:
          p = overlay.panel()
          e = overlay.entry(p, "shopping")
          overlay.check(e && e.locked, "Lock locks it")
          overlay.click(overlay.chip(overlay.row(p, "shopping"), "Unlock"), "Unlock")
          break
        case 16:
          p = overlay.panel()
          e = overlay.entry(p, "shopping")
          overlay.check(e && !e.locked, "Unlock unlocks it")
          overlay.click(overlay.chip(p, "History"), "History")
          break
        case 17:
          p = overlay.panel()
          overlay.check(p && p.versions.length === 3, "History lists the three replaced versions (" + (p ? p.versions.length : 0) + ")")
          var oldest = p && p.versions.length ? p.versions[p.versions.length - 1] : null
          overlay.click(overlay.find(p, function(x) { return x.clicked !== undefined && x.text === "Restore" &&
                                                     x.parent && x.parent.modelData !== undefined && oldest &&
                                                     x.parent.modelData.version === oldest.version }), "Restore the oldest")
          break
        case 18:
          p = overlay.panel()
          overlay.check(p && p.noteText === "Buy milk." && p.noteRev === 5, "Restore puts the first version back as rev 5 (" + (p ? p.noteText + " " + p.noteRev : "") + ")")
          corrupt.running = true
          overlay.goTo("communal", "", "notes")
          break
        case 19:
          break
        case 20:
          p = overlay.panel()
          overlay.check(p && p.communal && p.listing && p.listing.locked_all, "a corrupt record reads as every note locked")
          var warn = overlay.find(overlay.content(), function(x) { return String(x.text).indexOf("cannot be read, so every note is") >= 0 })
          overlay.check(warn !== null, "and Communal's Notes tab says so")
          e = overlay.entry(p, "shared")
          overlay.check(e && e.locked, "its note shows locked")
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          Qt.quit()
          break
        }
      }
    }
  }
}
