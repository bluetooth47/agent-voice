import QtQuick
import Quickshell.Io

// The agent folders' comings and goings, for every page (merged plan,
// Phases 10 and 12): adding an agent makes its folder; removing one moves
// the folder to the trash with its settings entry beside it, so Undo, or
// Restore from the trash list, gives the agent back whole.
//
// Here, beside the settings store, rather than on a page, for two reasons.
// The Agents page and Agent details both remove and restore agents, and a
// second copy of this would be a second set of the races the Phase 10
// review found. And a page is dropped the moment another is shown, which
// took an operation in flight and the Undo with it.
//
// Every operation goes through `agentvoice agents`, one at a time. The
// agent list is written here only as the second half of a folder move
// (`voiceAgents`, through the overlay's store); the Agents page stays the
// list's home for everything else, as `assignVoice` is a shortcut to it.
Item {
  id: af
  visible: false

  // The overlay (Settings.qml).
  property var s: null

  // Why the last operation failed, in words; "" when it did not.
  property string note: ""
  // What the last operation did, when that is worth saying ("Exported to …").
  property string done: ""
  // Bumped when an operation finishes, so editors drawn before their folder
  // existed (a card appears the moment it is added, before `agents create`
  // has run) read it again rather than saving against a missing folder.
  property int epoch: 0
  // The last agent moved to the trash: { name, label, index }, or null.
  property var trashed: null
  // Phase M17: the last agent reset to its defaults: { name (its trash
  // entry), label, id }, or null. Its Undo puts the old one back.
  property var resetDone: null
  // From launch until its result has been handled, so a second operation
  // cannot start in the moment between the process ending and its result
  // being read, and take that result's place (Phase 10 review).
  property bool busy: false
  property var queue: []
  // An operation whose second half is a save of the agent list holds the
  // queue until the store says that save landed or failed, so a late
  // failure can only ever roll back its own move (Phase 12 review).
  property bool awaitingSave: false

  // `agentvoice agents list --json`: every folder present, with its sizes,
  // problems and files changed outside Settings, read here so the pages have
  // them while the service is off (the daemon's copy, vAgentFiles, is
  // published only while it runs). Never the text.
  property var folders: ({})
  property bool foldersRead: false
  // `agentvoice agents trash-list --json`, newest first.
  property var trash: []

  function refresh() {
    if (!lister.running) lister.running = true
    if (!trashLister.running) trashLister.running = true
  }
  Component.onCompleted: refresh()

  // Every entry, each with the id the daemon derives written down, so an
  // entry from before ids existed keeps its folder's name across the save.
  function entries(skip) {
    var out = []
    for (var i = 0; i < s.voiceAgents.length; i++) {
      if (i === skip) continue
      var a = s.voiceAgents[i] || {}
      var copy = {}
      for (var k in a) copy[k] = a[k]
      copy.id = s.agentId(a)
      out.push(copy)
    }
    return out
  }
  function saveAgents(list) { s.put("voiceAgents", list) }

  // A folder is an orphan when no entry in the settings, switched off or
  // not, is known by its id.
  function hasAgent(id) {
    if (id === "main") return true
    for (var i = 0; i < s.voiceAgents.length; i++)
      if (s.agentId(s.voiceAgents[i] || {}) === id) return true
    return false
  }
  readonly property var orphans: {
    var out = []
    for (var t in af.folders)
      if (t !== "communal" && !af.hasAgent(t)) out.push(t)
    return out.sort()
  }
  function hasFolder(id) { return af.folders[id] !== undefined }

  // --- operations ---------------------------------------------------------------
  function op(args, input, what) {
    queue = queue.concat([{ args: args, input: input, what: what }])
    if (!busy) next()
  }
  function next() {
    if (queue.length === 0) return
    busy = true
    var n = queue[0]
    queue = queue.slice(1)
    proc.what = n.what
    proc.pending = n.input
    proc.out = ""
    proc.err = ""
    proc.command = ["agentvoice", "agents"].concat(n.args)
    proc.running = true
  }
  Process {
    id: proc
    property var what: ({})
    property string pending: ""
    property string out: ""
    property string err: ""
    stdinEnabled: true
    onStarted: if (proc.pending !== "") { write(proc.pending); proc.pending = "" }
    stdout: StdioCollector { onStreamFinished: proc.out = String(text).trim() }
    stderr: StdioCollector { onStreamFinished: proc.err = String(text).trim() }
    // `running` going false, not onExited, which a spawn that never started
    // does not emit. The streams are read a moment later, once both closed.
    onRunningChanged: if (!running) finished.restart()
  }
  Timer {
    id: finished
    interval: 200
    onTriggered: {
      af.handle(proc.what, proc.out, proc.err)
      af.epoch++
      af.refresh()
      if (af.awaitingSave) { saveTimeout.restart(); return }
      af.busy = false
      af.next()
    }
  }
  function release() {
    if (!af.awaitingSave) return
    af.awaitingSave = false
    saveTimeout.stop()
    af.busy = false
    af.next()
  }
  // The store gives a write up after a few seconds and says so; this is
  // only for a store that never answers at all.
  Timer { id: saveTimeout; interval: 15000; onTriggered: af.release() }
  function pending(verb, id) {
    if (af.busy && proc.what.verb === verb && proc.what.id === id) return true
    for (var i = 0; i < af.queue.length; i++)
      if (af.queue[i].what.verb === verb && af.queue[i].what.id === id) return true
    return false
  }

  // A new agent's folder, from the template. Its entry is saved by the
  // Agents page first; the agent works without the folder (it is told
  // nothing extra) and the daemon makes any missing one on its next start.
  function create(id) {
    op(["create", id], "", { verb: "create", id: id })
  }

  // Remove the entry at `index`: its folder and entry go to the trash, and
  // it leaves the list only once they are there, so a failure loses nothing.
  function remove(index) {
    var a = s.voiceAgents[index] || {}
    var entry = {}
    for (var k in a) entry[k] = a[k]
    entry.id = s.agentId(a)
    // A second entry claiming an id another entry has (only a hand edit can
    // make one) is not that agent: the settings drop it, and the folder is
    // the first entry's. Removed from the list alone, its folder untouched.
    for (var d = 0; d < index; d++) {
      if (s.agentId(s.voiceAgents[d] || {}) === entry.id) {
        af.note = ""
        saveAgents(entries(index))
        return
      }
    }
    // Twice in a row (a double click) would trash a second, empty entry
    // over the Undo for the real one.
    if (pending("trash", entry.id)) return
    // The settings entry goes over stdin as one JSON line.
    op(["trash", entry.id, "--line"], JSON.stringify(entry) + "\n",
       { verb: "trash", id: entry.id, index: index, label: s.agentLabel(a) || "this agent" })
  }

  function undo() {
    if (af.trashed === null) return
    restore(af.trashed.name, af.trashed.index)
  }

  // Phase M17: a copy of agent `id` ("main" too) -- its folder first, then
  // its entry added to the list, switched off. What the copy holds is the
  // daemon's decision (agent_manage.py): no grant, no secret, no session.
  function duplicate(id) {
    if (s.voiceAgents.length >= s.maxAgents) {
      af.note = "There are already " + s.maxAgents + " agents; remove one first."
      return
    }
    if (pending("duplicate", id)) return
    op(["duplicate", id], "", { verb: "duplicate", id: id })
  }

  // Phase M17: the entry at `index` back to a new agent's settings and its
  // folder to the starting templates. Both go to the trash first, so Undo,
  // or Restore from the trash list, gives the agent back whole.
  function resetAgent(index) {
    var a = s.voiceAgents[index] || {}
    var entry = {}
    for (var k in a) entry[k] = a[k]
    entry.id = s.agentId(a)
    if (pending("reset", entry.id) || pending("trash", entry.id)) return
    op(["reset", entry.id, "--line"], JSON.stringify(entry) + "\n",
       { verb: "reset", id: entry.id, index: index, label: s.agentLabel(a) || "this agent" })
  }
  function undoReset() {
    if (af.resetDone === null) return
    op(["unreset", af.resetDone.name], "",
       { verb: "unreset", name: af.resetDone.name, id: af.resetDone.id })
  }

  // Put a trash entry back: its folder, and its settings entry at `index`
  // (the end when not given). An entry trashed as an orphan folder has no
  // settings to put back, so only its folder returns.
  function restore(name, index) {
    var t = null
    for (var i = 0; i < af.trash.length; i++) if (af.trash[i].name === name) t = af.trash[i]
    var orphan = t !== null && t.orphan === true
    // Phase M17: its id still in the list means it was reset (ids are never
    // reused): putting it back replaces the reset one, folder and entry,
    // and the fresh folder goes to the trash in its turn.
    var tid = String(name).replace(/-[0-9]{19}$/, "")
    if (!orphan && tid !== "main" && af.hasAgent(tid)) {
      op(["unreset", name], "", { verb: "unreset", name: name, id: tid })
      return
    }
    if (!orphan && s.voiceAgents.length >= s.maxAgents) {
      af.note = "There are already " + s.maxAgents + " agents; remove one first."
      return
    }
    // Its wake phrase taken meanwhile (an agent added under the same name):
    // putting it back would silently change which agent answers it.
    var phrase = t !== null ? String(t.phrase || "") : ""
    if (!orphan && phrase !== "") {
      var holder = phrase === String(s.activePhrase).toLowerCase() ? s.mainLabel : ""
      for (var j = 0; holder === "" && j < s.voiceAgents.length; j++) {
        var a = s.voiceAgents[j] || {}
        if (String(a.name || "").toLowerCase().split(/\s+/).join(" ").trim() === phrase)
          holder = s.agentLabel(a) || phrase
      }
      if (holder !== "") {
        af.note = "Not restored: “" + phrase + "” now wakes " + holder +
                  ". Change one of their wake phrases first."
        return
      }
    }
    op(["restore", name], "", { verb: "restore", name: name,
                                index: index === undefined ? s.voiceAgents.length : index })
  }

  // A folder no agent uses: to the trash with a marker instead of settings.
  function trashOrphan(id) {
    if (hasAgent(id)) return
    op(["trash", id, "--line"], JSON.stringify({ id: id, orphan: true }) + "\n",
       { verb: "orphan", id: id })
  }

  // Text an editor could no longer save itself (it was closed, or moved to
  // another agent, mid-edit): saved on the stamp it was read at, so a newer
  // file is never overwritten; if it cannot be, the note says so.
  function keep(target, file, text, base) {
    if (base === "") return
    op(["write", target, file, "--line", "--base", base], JSON.stringify(text) + "\n",
       { verb: "keep", id: target, file: file })
  }

  // Phase M17: `chats new ID`, after a reset: that agent's conversation
  // only. Nothing to report when it cannot run: the daemon is not running,
  // so there is no conversation to end.
  Process { id: freshAfterReset }
  function startFresh(id) {
    if (freshAfterReset.running) return
    freshAfterReset.command = ["agentvoice", "chats", "new", id]
    freshAfterReset.running = true
  }

  function exportFolder(target) {
    op(["export", target], "", { verb: "export", id: target })
  }

  // The agent list is saved after its folder moved, through `omarchy bar
  // set`, which can fail. Then the folder is moved back, so the folders and
  // the list never disagree (Phase 10 review): a removal whose list was not
  // saved restores the folder; an undo whose list was not saved trashes it
  // again, settings entry and all.
  property var rollback: null
  Connections {
    target: af.s ? af.s.store : null
    function onSaved(key) {
      if (key !== "voiceAgents") return
      // Phase M17: a reset agent's conversation ends with the rest, even
      // when nothing the daemon rebuilds for (program, level) moved.
      if (af.rollback !== null && af.rollback.verb === "reset") af.startFresh(af.rollback.id)
      af.rollback = null
      af.release()
    }
    function onFailed(key, message) {
      if (key !== "voiceAgents") return
      if (af.rollback === null) { af.release(); return }
      var r = af.rollback
      af.rollback = null
      if (r.verb === "duplicate") {
        // The copy's folder, with no agent to use it: to the trash.
        af.op(["trash", r.id, "--line"], JSON.stringify({ id: r.id, orphan: true }) + "\n",
              { verb: "rolledback" })
        af.note = "The agent list could not be saved (" + message + "), so " +
                  r.label + " was not added; its folder went to the trash."
      } else if (r.verb === "reset") {
        af.resetDone = null
        af.op(["unreset", r.name], "", { verb: "rolledback" })
        af.note = "The agent list could not be saved (" + message + "), so " +
                  r.label + " was not reset; its folder was put back."
      } else if (r.verb === "unreset") {
        af.op(["reset", r.id, "--line"], JSON.stringify(r.entry) + "\n", { verb: "rolledback" })
        af.note = "The agent list could not be saved (" + message + "), so " +
                  r.label + " was not put back; it is reset again, and the trash keeps it."
      } else if (r.verb === "trash") {
        af.trashed = null
        af.op(["restore", r.name], "", { verb: "rolledback" })
        af.note = "The agent list could not be saved (" + message + "), so " +
                  r.label + " was not removed; its folder was put back."
      } else {
        af.op(["trash", r.id, "--line"], JSON.stringify(r.entry) + "\n",
              { verb: "rolledback" })
        af.note = "The agent list could not be saved (" + message + "), so " +
                  r.label + " was not put back; it is still in the trash."
      }
      af.release()
    }
  }

  function handle(what, out, err) {
    var why = err.replace(/^agentvoice agents: /, "") || "the agentvoice command could not be run"
    af.done = ""
    if (what.verb === "create") {
      // On success it prints the files it made, so empty output is failure.
      af.note = out !== "" ? ""
              : "Its folder was not made: " + why + ". It is made when the service next starts."
    } else if (what.verb === "trash") {
      if (!/^[a-z0-9][a-z0-9-]{0,47}-[0-9]{19}$/.test(out)) {
        af.note = "Nothing was removed: " + what.label + "'s folder could not be moved to the trash (" + why + ")."
        return
      }
      // The one entry that was removed: where it was, if it is still
      // there, else the first with its id. Never every entry with that id --
      // a hand edit can give two entries one id, and the other is not gone.
      var at = -1
      var here = s.voiceAgents[what.index] || {}
      if (s.agentId(here) === what.id) at = what.index
      for (var j = 0; at < 0 && j < s.voiceAgents.length; j++)
        if (s.agentId(s.voiceAgents[j] || {}) === what.id) at = j
      var list = entries(at)
      af.trashed = { name: out, label: what.label, index: at < 0 ? list.length : at }
      af.note = ""
      af.rollback = { verb: "trash", name: out, label: what.label }
      af.awaitingSave = true
      saveAgents(list)
    } else if (what.verb === "rolledback") {
      if (err !== "")
        af.note += " Moving the folder back failed too (" + why + "); " +
                   "`agentvoice agents trash-list` shows what the trash holds."
    } else if (what.verb === "restore") {
      var entry = null
      try { entry = JSON.parse(out) } catch (e) { entry = null }
      if (!entry || typeof entry !== "object") {
        af.note = "Could not restore: " + why + "."
        return
      }
      if (af.trashed && af.trashed.name === what.name) af.trashed = null
      af.note = ""
      // The folder came back under the id in its trash name, whatever the
      // saved entry says, so the entry is put back under that id too.
      entry.id = String(what.name).replace(/-[0-9]{19}$/, "")
      // The same rule as agentfs.is_folder_only.
      if (entry.orphan === true || typeof entry.name !== "string" || entry.name.trim() === "") {
        af.done = "Put the folder " + String(entry.id || what.name) + " back. No agent uses it."
        return
      }
      var back = entries(-1)
      back.splice(Math.min(what.index, back.length), 0, entry)
      af.rollback = { verb: "restore", id: s.agentId(entry), entry: entry,
                      label: s.agentLabel(entry) || "the agent" }
      s.focusAgent = s.agentId(entry)
      af.awaitingSave = true
      saveAgents(back)
    } else if (what.verb === "orphan") {
      af.note = /^[a-z0-9][a-z0-9-]{0,47}-[0-9]{19}$/.test(out) ? ""
              : "The folder " + what.id + " was not moved to the trash (" + why + ")."
      if (af.note === "") af.done = "Moved the folder " + what.id + " to the trash."
    } else if (what.verb === "keep") {
      if (/^[0-9a-f]{16}-[0-9]+$/.test(out)) return
      af.note = "An edit to " + what.id + "'s " + what.file + " was left unsaved when its editor closed, " +
                "and could not be saved then: " +
                (err.indexOf("conflict:") === 0 ? "the file had changed since it was opened." : why + ".")
    } else if (what.verb === "duplicate") {
      var d = null
      try { d = JSON.parse(out) } catch (e) { d = null }
      if (!d || !d.entry || typeof d.entry !== "object" || typeof d.entry.id !== "string") {
        af.note = "Not copied: " + why + "."
        return
      }
      var added = entries(-1)
      added.push(d.entry)
      var left = (d.left || []).map(function(x) { return String(x.name) }).join(", ")
      af.note = ""
      af.done = "Made " + s.agentLabel(d.entry) + ", switched off. Give it a wake phrase of its own " +
                "on the Agents page, then switch it on." +
                (left !== "" ? " Skills not copied: " + left + "." : "")
      af.rollback = { verb: "duplicate", id: d.entry.id, label: s.agentLabel(d.entry) || "the copy" }
      af.awaitingSave = true
      saveAgents(added)
    } else if (what.verb === "reset") {
      var rs = null
      try { rs = JSON.parse(out) } catch (e) { rs = null }
      if (!rs || !rs.entry || typeof rs.entry !== "object" ||
          !/^[a-z0-9][a-z0-9-]{0,47}-[0-9]{19}$/.test(String(rs.trash || ""))) {
        af.note = "Nothing was reset: " + why + "."
        return
      }
      var where = -1
      var was = s.voiceAgents[what.index] || {}
      if (s.agentId(was) === what.id) where = what.index
      for (var w = 0; where < 0 && w < s.voiceAgents.length; w++)
        if (s.agentId(s.voiceAgents[w] || {}) === what.id) where = w
      if (where < 0) {
        // Gone from the list meanwhile: the old folder goes back, as it was.
        af.op(["unreset", rs.trash], "", { verb: "rolledback" })
        af.note = what.label + " was removed while it was being reset; nothing was reset."
        return
      }
      var reset = entries(-1)
      rs.entry.id = what.id
      reset[where] = rs.entry
      af.note = ""
      af.resetDone = { name: rs.trash, label: what.label, id: what.id }
      af.rollback = { verb: "reset", name: rs.trash, label: what.label, id: what.id }
      af.awaitingSave = true
      saveAgents(reset)
    } else if (what.verb === "unreset") {
      var back2 = null
      try { back2 = JSON.parse(out) } catch (e) { back2 = null }
      if (!back2 || typeof back2 !== "object") {
        af.note = "Could not put it back: " + why + "."
        return
      }
      back2.id = what.id
      if (af.resetDone && af.resetDone.name === what.name) af.resetDone = null
      var list2 = entries(-1), at2 = -1
      for (var u = 0; u < list2.length; u++) if (s.agentId(list2[u]) === what.id) at2 = u
      if (at2 < 0) list2.push(back2)
      else list2[at2] = back2
      af.note = ""
      af.done = "Put " + (s.agentLabel(back2) || "it") + " back as it was before the reset."
      af.rollback = { verb: "unreset", id: what.id, entry: back2, label: s.agentLabel(back2) || "the agent" }
      s.focusAgent = what.id
      af.awaitingSave = true
      saveAgents(list2)
    } else if (what.verb === "export") {
      if (out !== "" && err === "") {
        af.note = ""
        af.done = "Copied to " + out
      } else {
        af.note = "Not exported: " + why + "."
      }
    }
  }

  // --- what is on disk ------------------------------------------------------------
  Process {
    id: lister
    command: ["agentvoice", "agents", "list", "--json"]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var d = JSON.parse(String(text))
          if (d && typeof d === "object") { af.folders = d; af.foldersRead = true }
        } catch (e) {}
      }
    }
  }
  Process {
    id: trashLister
    command: ["agentvoice", "agents", "trash-list", "--json"]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var d = JSON.parse(String(text))
          if (Array.isArray(d)) af.trash = d
        } catch (e) {}
      }
    }
  }
}
