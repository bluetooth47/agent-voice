import QtQuick
import Quickshell
import Quickshell.Io

// One copy of this widget's settings, for every control that shows or
// changes one.
//
// Why it exists: every control used to write through `omarchy bar set` and
// then wait for shell.json to come back through jq before it showed the new
// value. In between it showed the *old* one -- a slider released at 10000
// sat at 5000 for the whole round trip (bench/preview `knob` measured it),
// and a toggle flicked back before flicking forward. Here a change shows at
// once (`pending`), the write goes out, and the pending value is dropped only
// when shell.json agrees with it -- or, if it never does, when the write is
// given up on, which puts the real value back and says why in `error`.
//
// Writes go out one at a time, in the order they were made. `omarchy bar set`
// is applied by the shell over IPC, so two at once do not corrupt anything,
// but two writes of the *same* key started together can land in either order
// and leave the older value saved. A queue makes the last change the one
// that sticks. A key changed again before its write has started only sends
// the newest value.
//
// Usage:
//   SettingsStore { id: store; defaults: manifest.barWidget.defaults }
//   Toggle { checked: store.get("hud", true); onClicked: store.set("hud", !checked) }
//
// Bindings that call get() re-evaluate when anything changes, because get()
// reads `view`, which is replaced (not mutated) on every change.
Item {
  id: store
  visible: false

  property string widgetId: "duaneoca.agentvoice"
  // The manifest's barWidget.defaults, for isDefault() and reset(). Optional.
  property var defaults: ({})
  // How long a finished write may go unconfirmed by shell.json before the
  // control is put back. The shell applies a set in well under a second; this
  // is for a write that "succeeded" and changed nothing.
  property int confirmTimeoutMs: 4000

  // What shell.json holds for this widget, as last read.
  property var cfg: ({})
  // key -> value, for changes made here that shell.json has not shown yet.
  property var pending: ({})
  // cfg with pending laid over it. Read through get().
  property var view: ({})
  // The last write that failed, in words; empty when there is nothing to say.
  // Cleared by the next successful write.
  property string error: ""
  readonly property bool busy: writer.running || queue.length > 0
  property bool loaded: false

  signal saved(string key)
  signal failed(string key, string message)

  readonly property string configPath:
      (Quickshell.env("XDG_CONFIG_HOME") || ((Quickshell.env("HOME") || "") + "/.config"))
      + "/omarchy/shell.json"

  function get(key, fallback) {
    var v = view[key]
    return v === undefined || v === null ? fallback : v
  }

  function isDefault(key) {
    if (!defaults || defaults[key] === undefined) return true
    return same(get(key, defaults[key]), defaults[key])
  }

  function reset(key) {
    if (defaults && defaults[key] !== undefined) set(key, defaults[key])
  }

  function set(key, value) {
    var p = Object.assign({}, pending)
    p[key] = value
    pending = p
    if (waiting[key] !== undefined) {
      var w = Object.assign({}, waiting)
      delete w[key]
      waiting = w
    }
    rebuild()
    // Collapse onto a queued write of the same key that has not started.
    var q = queue.slice()
    for (var i = 0; i < q.length; i++) {
      if (q[i].key === key) {
        q[i] = { key: key, value: value }
        queue = q
        return
      }
    }
    q.push({ key: key, value: value })
    queue = q
    pump()
  }

  function reload() {
    if (!reader.running) reader.running = true
  }

  // --- internals --------------------------------------------------------------

  property var queue: []
  property var inFlight: null
  // key -> time its write finished, for the confirmation deadline.
  property var waiting: ({})

  function same(a, b) {
    return JSON.stringify(a) === JSON.stringify(b)
  }

  function rebuild() {
    view = Object.assign({}, cfg, pending)
  }

  function pump() {
    if (writer.running || queue.length === 0) return
    var q = queue.slice()
    inFlight = q.shift()
    queue = q
    writer.code = -1
    writer.command = ["omarchy", "bar", "set", widgetId, inFlight.key,
                      JSON.stringify(inFlight.value), "--json"]
    writer.running = true
  }

  function drop(key) {
    if (pending[key] === undefined) return
    var p = Object.assign({}, pending)
    delete p[key]
    pending = p
    var w = Object.assign({}, waiting)
    delete w[key]
    waiting = w
    rebuild()
  }

  function settle() {
    // A pending value shell.json now agrees with is done.
    var now = Date.now()
    for (var key in pending) {
      if (same(cfg[key], pending[key])) {
        drop(key)
        saved(key)
      } else if (waiting[key] !== undefined && now - waiting[key] > confirmTimeoutMs) {
        var msg = "Could not save " + key + ": the setting did not change."
        drop(key)
        error = msg
        failed(key, msg)
      }
    }
  }

  Process {
    id: writer
    property string errText: ""
    // -1 until it exits; still -1 afterwards means it never started.
    property int code: -1
    onExited: function(exitCode) { writer.code = exitCode }
    stderr: StdioCollector { onStreamFinished: writer.errText = String(text).trim() }
    // `running` going false, not onExited: a write that never started (no
    // `omarchy` on PATH) emits no exit, and would hold the queue for good.
    onRunningChanged: {
      if (running || !store.inFlight) return
      var done = store.inFlight
      store.inFlight = null
      Qt.callLater(function() {
        if (writer.code !== 0) {
          var msg = "Could not save " + done.key + ": "
                    + (writer.code === -1 ? "omarchy could not be run"
                       : (writer.errText || "omarchy bar set failed"))
          // Only if nothing newer for this key is waiting to go.
          var newer = store.queue.some(function(e) { return e.key === done.key })
          if (!newer) store.drop(done.key)
          store.error = msg
          store.failed(done.key, msg)
        } else {
          store.error = ""
          var w = Object.assign({}, store.waiting)
          w[done.key] = Date.now()
          store.waiting = w
          confirmTimer.restart()
        }
        writer.errText = ""
        store.reload()
        store.pump()
      })
    }
  }

  // Checks unconfirmed writes against their deadline. shell.json changing is
  // what normally settles them; this is the backstop for when it does not.
  Timer {
    id: confirmTimer
    interval: store.confirmTimeoutMs + 100
    onTriggered: { store.reload(); Qt.callLater(store.settle) }
  }

  Process {
    id: reader
    command: ["jq", "-c",
              "[.bar.layout[]?[]? | select(.id==$id)][0] // {}",
              "--arg", "id", store.widgetId, store.configPath]
    stdout: StdioCollector {
      onStreamFinished: {
        var parsed = {}
        try { parsed = JSON.parse(String(text).trim() || "{}") } catch (e) { parsed = {} }
        store.cfg = parsed
        store.loaded = true
        store.rebuild()
        store.settle()
      }
    }
  }

  // shell.json changes from more than one place -- this screen, the panel,
  // `omarchy bar set`, an editor -- and every one of them has to show here.
  FileView {
    path: store.configPath
    watchChanges: true
    printErrors: false
    onFileChanged: store.reload()
  }

  Component.onCompleted: reload()
}
