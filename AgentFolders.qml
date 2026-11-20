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
  // From launch until its result has been handled, so a second operation
  // cannot start in the moment between the process ending and its result
  // being read, and take that result's place (Phase 10 review).
  property bool busy: false
  property var queue: []

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
      af.busy = false
      af.refresh()
      af.next()
    }
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
    // The settings entry goes over stdin as one JSON line.
    op(["trash", entry.id, "--line"], JSON.stringify(entry) + "\n",
       { verb: "trash", id: entry.id, index: index, label: s.agentLabel(a) || "this agent" })
  }

  function undo() {
    if (af.trashed === null) return
    restore(af.trashed.name, af.trashed.index)
  }

  // Put a trash entry back: its folder, and its settings entry at `index`
  // (the end when not given). An entry trashed as an orphan folder has no
  // settings to put back, so only its folder returns.
  function restore(name, index) {
    var t = null
    for (var i = 0; i < af.trash.length; i++) if (af.trash[i].name === name) t = af.trash[i]
    var orphan = t !== null && t.orphan === true
    if (!orphan && s.voiceAgents.length >= s.maxAgents) {
      af.note = "There are already " + s.maxAgents + " agents; remove one first."
      return
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
    function onSaved(key) { if (key === "voiceAgents") af.rollback = null }
    function onFailed(key, message) {
      if (key !== "voiceAgents" || af.rollback === null) return
      var r = af.rollback
      af.rollback = null
      if (r.verb === "trash") {
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
      if (entry.orphan === true || typeof entry.name !== "string") {
        af.done = "Put the folder " + String(entry.id || what.name) + " back. No agent uses it."
        return
      }
      var back = entries(-1)
      back.splice(Math.min(what.index, back.length), 0, entry)
      af.rollback = { verb: "restore", id: s.agentId(entry), entry: entry,
                      label: s.agentLabel(entry) || "the agent" }
      s.focusAgent = s.agentId(entry)
      saveAgents(back)
    } else if (what.verb === "orphan") {
      af.note = /^[a-z0-9][a-z0-9-]{0,47}-[0-9]{19}$/.test(out) ? ""
              : "The folder " + what.id + " was not moved to the trash (" + why + ")."
      if (af.note === "") af.done = "Moved the folder " + what.id + " to the trash."
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
