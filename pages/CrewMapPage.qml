import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// Crew map (master plan M8, feedback item 16): who may do what to whom.
//
// The saved list is the rule, and the daemon enforces it (crew_links.py,
// collab.py): an agent reaches another only along a link here that allows
// what it is trying to do, a list that cannot be read refuses everything,
// and a quarantined agent starts nothing. This page is only an editor of
// two settings, `crewLinks` and `crewQuarantine`, and every edit, from the
// map or the table, goes through commit(): the page trims the lists to what
// quarantine lets a link carry, `agentvoice crew check` judges them with the
// daemon's own validator (crew_links.check_write), and only what it accepts
// is written, by writeQuarantine() and writeLinks() from applyChecked() and
// nowhere else (tests/test_crew_links.py holds that).
//
// The drawn map (M9): agent boxes that drag, a line per link with an arrow
// at the agent it reaches (ui/CrewEdge.qml), drag from an agent's dot onto
// another to link them, a red zone to quarantine by dragging into, and an
// inspector for whatever was clicked. Where the boxes sit is the page's own
// business, kept in $XDG_STATE_HOME/agentvoice/crew-layout.json, which the
// daemon never reads; with nothing saved they stand in a ring.
//
// What the page works out for itself -- whether the list can be read, what
// each link allows once quarantine is applied, the effective line -- mirrors
// crew_links.py, and tests/test_crew_links.py runs these functions in node
// against the Python over the same cases, so the page cannot promise what
// the daemon will not do.
Column {
  id: page

  required property var s

  spacing: Style.space(16)

  // --- the agents -----------------------------------------------------------
  // Every agent the settings have, switched off ones too: they keep their
  // links, and a link to one is refused while it is off.
  function crewIds() {
    var out = ["main"]
    for (var i = 0; i < page.s.voiceAgents.length; i++) {
      var id = page.s.agentId(page.s.voiceAgents[i])
      if (out.indexOf(id) < 0) out.push(id)
    }
    return out
  }
  readonly property var ids: crewIds()
  function entryOf(id) {
    for (var i = 0; i < page.s.voiceAgents.length; i++)
      if (page.s.agentId(page.s.voiceAgents[i]) === id) return page.s.voiceAgents[i]
    return null
  }
  function labelOf(id) {
    if (id === "main") return page.s.mainLabel
    var e = entryOf(id)
    return e ? page.s.agentLabel(e) : id
  }
  // runtime.collab_choice: missing is "announce", anything else unreadable
  // is "ask".
  function levelOf(id) {
    var holder = id === "main" ? page.s.cfg : entryOf(id)
    var key = id === "main" ? "mainCollaboration" : "collaboration"
    if (!holder || holder[key] === undefined) return "announce"
    var v = holder[key]
    return ["off", "ask", "announce", "allow"].indexOf(v) >= 0 ? v : "ask"
  }
  function trustOf(id) {
    if (id === "main") {
      var all = page.s.setting("permissions", {})
      var v = all && typeof all === "object" ? all[page.s.mainAgent] : ""
      return typeof v === "string" && v !== "" ? v : page.s.permissionLevel
    }
    var e = entryOf(id)
    return e && ["ask", "edits", "trusted"].indexOf(e.level) >= 0 ? e.level : "ask"
  }
  function isOff(id) {
    var e = entryOf(id)
    return id !== "main" && (e === null || e.enabled === false)
  }

  // --- reading the two settings, as crew_links.py does ------------------------
  readonly property var abilities: ["ask", "delegate", "message", "pass"]
  readonly property var intoQuarantine: ["ask", "delegate"]
  readonly property var verbs: ({ ask: "ask", delegate: "give a task", message: "message", pass: "pass the conversation" })

  function validId(v) { return typeof v === "string" && /^[a-z0-9][a-z0-9-]{0,47}$/.test(v) }
  // { links, why }: links null when the list cannot be read.
  function parseLinks(raw) {
    if (!Array.isArray(raw)) return { links: null, why: "crewLinks is not a list" }
    if (raw.length > 128) return { links: null, why: "crewLinks has more than 128 links" }
    var out = [], pairs = {}
    for (var i = 0; i < raw.length; i++) {
      var e = raw[i], n = i + 1
      if (!e || typeof e !== "object" || Array.isArray(e)) return { links: null, why: "link " + n + " is not an object" }
      for (var k in e)
        if (["from", "to", "allow", "askFirst"].indexOf(k) < 0) return { links: null, why: "link " + n + " has a key no link has (" + String(k).slice(0, 24) + ")" }
      if (!validId(e.from) || !validId(e.to)) return { links: null, why: "link " + n + " does not name two agents by id" }
      if (e.from === e.to) return { links: null, why: "link " + n + " links an agent to itself" }
      if (!Array.isArray(e.allow) || e.allow.some(function(a) { return typeof a !== "string" }))
        return { links: null, why: "link " + n + " has no list of what it allows" }
      for (var j = 0; j < e.allow.length; j++)
        if (page.abilities.indexOf(e.allow[j]) < 0) return { links: null, why: "link " + n + " allows something no link can (" + e.allow[j].slice(0, 24) + ")" }
      for (var a = 0; a < e.allow.length; a++)
        if (e.allow.indexOf(e.allow[a]) !== a) return { links: null, why: "link " + n + " lists an ability twice" }
      var askFirst = e.askFirst === undefined ? false : e.askFirst
      if (typeof askFirst !== "boolean") return { links: null, why: "link " + n + "'s askFirst is not true or false" }
      var pair = e.from + ">" + e.to
      if (pairs[pair]) return { links: null, why: "link " + n + " repeats a link from " + e.from + " to " + e.to }
      pairs[pair] = true
      out.push({ from: e.from, to: e.to,
                 allow: page.abilities.filter(function(x) { return e.allow.indexOf(x) >= 0 }),
                 askFirst: askFirst })
    }
    return { links: out, why: "" }
  }
  function parseQuarantine(raw) {
    if (!Array.isArray(raw)) return { ids: null, why: "crewQuarantine is not a list" }
    if (raw.length > 64) return { ids: null, why: "crewQuarantine has more than 64 entries" }
    for (var i = 0; i < raw.length; i++)
      if (!page.validId(raw[i])) return { ids: null, why: "quarantine entry " + (i + 1) + " is not an agent id" }
    return { ids: raw.filter(function(v, i) { return raw.indexOf(v) === i }), why: "" }
  }
  // A missing key is the default, []; what the store holds otherwise is
  // what shell.json says.
  function rawOf(key) {
    var c = page.s.cfg
    return c && c[key] !== undefined ? c[key] : []
  }
  readonly property var readLinks: parseLinks(rawOf("crewLinks"))
  readonly property var readQuarantine: parseQuarantine(rawOf("crewQuarantine"))
  readonly property bool readable: readLinks.links !== null && readQuarantine.ids !== null
  readonly property string problem: readLinks.why || readQuarantine.why
  // What is saved, or -- while edits wait for the check -- what the last of
  // them will save, so a second edit builds on the first. A refused check
  // empties the queue and this falls back to what is saved.
  readonly property var links: queue.length ? queue[queue.length - 1].crewLinks : (readLinks.links || [])
  readonly property var quarantine: queue.length ? queue[queue.length - 1].crewQuarantine : (readQuarantine.ids || [])

  function isQuarantined(id) { return page.quarantine.indexOf(id) >= 0 }
  function linkOf(from, to) {
    for (var i = 0; i < page.links.length; i++)
      if (page.links[i].from === from && page.links[i].to === to) return page.links[i]
    return null
  }
  // crew_links.Crew.abilities: none from a quarantined agent, only ask and
  // delegate into one.
  function effectiveOf(from, to) {
    var l = linkOf(from, to)
    if (!page.readable || !l || from === to || isQuarantined(from)) return []
    if (isQuarantined(to)) return l.allow.filter(function(a) { return page.intoQuarantine.indexOf(a) >= 0 })
    return l.allow.slice()
  }
  function reachOf(id) {
    var out = []
    for (var i = 0; i < page.links.length; i++) {
      var l = page.links[i]
      if (l.from !== id) continue
      var got = effectiveOf(id, l.to)
      if (got.length) out.push({ id: l.to, allow: got })
    }
    return out
  }
  function reachedBy(id) {
    var out = []
    for (var i = 0; i < page.links.length; i++) {
      var l = page.links[i]
      if (l.to !== id) continue
      var got = effectiveOf(l.from, id)
      if (got.length) out.push({ id: l.from, allow: got })
    }
    return out
  }
  function reachWords(list) {
    if (!list.length) return "nobody"
    return list.map(function(r) { return page.labelOf(r.id) + " (" + r.allow.join(", ") + ")" }).join(" · ")
  }

  // "Theo → Sora: delegate · asks you first (link) · announces (Theo's level)"
  function effectiveLine(from, to) {
    var head = labelOf(from) + " → " + labelOf(to) + ": "
    if (!page.readable) return head + "nothing, the crew links can't be read"
    var l = linkOf(from, to)
    if (!l) return head + "no link"
    if (isQuarantined(from)) return head + "nothing, " + labelOf(from) + " is quarantined"
    var got = effectiveOf(from, to)
    if (!got.length) return head + (l.allow.length ? "nothing that may go into quarantine" : "allows nothing")
    var level = levelOf(from)
    var who = labelOf(from) + "'s level"
    if (level === "off") return head + "nothing, " + labelOf(from) + "'s collaboration is off"
    var bits = [got.join(", ")]
    if (isQuarantined(to)) bits.push(labelOf(to) + " is quarantined: the brief alone")
    if (isOff(to)) bits.push(labelOf(to) + " is switched off")
    if (l.askFirst)
      bits.push("asks you first (link" + (trustOf(from) === "trusted" ? "; advisory, " + labelOf(from) + " is Trusted" : "") + ")")
    bits.push(level === "ask" ? "asks you first (" + who + ")"
              : level === "announce" ? "announces (" + who + ")"
              : "goes quietly (" + who + ")")
    return head + bits.join(" · ")
  }

  // --- what a write is ---------------------------------------------------------
  // Each returns the whole new list; nothing here writes.
  function everyoneLinks(list) {
    var out = []
    for (var i = 0; i < list.length; i++)
      for (var j = 0; j < list.length; j++)
        if (i !== j) out.push({ from: list[i], to: list[j], allow: page.abilities.slice(), askFirst: false })
    return out
  }
  function copyLinks() {
    return page.links.map(function(l) { return { from: l.from, to: l.to, allow: l.allow.slice(), askFirst: l.askFirst } })
  }
  function withLink(from, to) {
    var out = copyLinks()
    if (from === to || !validId(from) || !validId(to) || linkOf(from, to)) return out
    // A new line carries `ask`, as a link drawn on the map (M9) will.
    out.push({ from: from, to: to, allow: ["ask"], askFirst: false })
    return out
  }
  function withAbility(from, to, ability, on) {
    return copyLinks().map(function(l) {
      if (l.from !== from || l.to !== to) return l
      var allow = l.allow.filter(function(a) { return a !== ability })
      if (on) allow.push(ability)
      l.allow = page.abilities.filter(function(a) { return allow.indexOf(a) >= 0 })
      return l
    })
  }
  function withAskFirst(from, to, on) {
    return copyLinks().map(function(l) {
      if (l.from === from && l.to === to) l.askFirst = on === true
      return l
    })
  }
  function withoutLink(from, to) {
    return copyLinks().filter(function(l) { return !(l.from === from && l.to === to) })
  }
  // Quarantining loses: every link out, and what a link in may not carry.
  // Releasing gives none of it back.
  function quarantineLoses(id) {
    var out = 0, trimmed = 0
    for (var i = 0; i < page.links.length; i++) {
      var l = page.links[i]
      if (l.from === id) out++
      else if (l.to === id && l.allow.some(function(a) { return page.intoQuarantine.indexOf(a) < 0 })) trimmed++
    }
    return { out: out, trimmed: trimmed }
  }
  function linksQuarantining(id) {
    return copyLinks().filter(function(l) { return l.from !== id }).map(function(l) {
      if (l.to === id) l.allow = l.allow.filter(function(a) { return page.intoQuarantine.indexOf(a) >= 0 })
      return l
    })
  }

  // A link the page would write must say no more than will happen: none out
  // of a quarantined agent, only ask and delegate into one. The validator
  // refuses anything else, so the page trims first -- what it drops counts
  // for nothing in the daemon already (crew_links.Crew.abilities), and
  // quarantining from the page always dropped it.
  function trimmed(list, held) {
    return list.filter(function(l) { return held.indexOf(l.from) < 0 }).map(function(l) {
      var c = { from: l.from, to: l.to, allow: l.allow.slice(), askFirst: l.askFirst === true }
      if (held.indexOf(l.to) >= 0) c.allow = c.allow.filter(function(a) { return page.intoQuarantine.indexOf(a) >= 0 })
      return c
    })
  }
  // "Also allow the reverse": the same abilities and ask-first, the other way.
  function withReverse(from, to) {
    var l = linkOf(from, to), out = copyLinks()
    if (!l || from === to || linkOf(to, from)) return out
    out.push({ from: to, to: from, allow: l.allow.slice(), askFirst: l.askFirst === true })
    return out
  }

  // --- the only way anything is saved ---------------------------------------
  // Every edit: the whole of both lists as they should be, queued; each is
  // checked by `agentvoice crew check` (stdin, one JSON line) and saved only
  // if the daemon's validator takes it. A refusal drops the queue -- every
  // later edit was built on the refused one -- and says why.
  property var queue: []
  property string saveNote: ""
  readonly property bool saving: queue.length > 0
  // What the saved pair was when the queued edits were built on it (canonical
  // JSON). Each edit is applied only while the saved pair is still that:
  // anything written underneath in between -- another window, an agent,
  // `omarchy bar set` -- would otherwise be overwritten by a snapshot taken
  // before it, a release undone by an unrelated edit (Codex review of M9).
  property string expectSaved: ""
  function savedPair() {
    return page.s.crewCanon(rawOf("crewLinks")) + "|" + page.s.crewCanon(rawOf("crewQuarantine"))
  }
  function commit(links, quarantine, what) {
    page.lastAction = what
    page.saveNote = ""
    if (!page.queue.length) page.expectSaved = savedPair()
    page.queue = page.queue.concat([{ crewLinks: trimmed(links, quarantine), crewQuarantine: quarantine.slice(), what: what }])
    nextCheck()
  }
  // Not while a crew list this page saved is still unconfirmed: the check
  // compares the pair this page believes is saved with the file on disk
  // (Codex review of M9, pass 2), and until the store has read its own
  // write back the file may be behind this page by exactly that save. The
  // store keeps a key in `pending` until shell.json agrees (or the write
  // fails, or its deadline passes); its `busy` drops for a moment between
  // two queued writes, which made the slow-write preview refuse itself.
  function crewSettling() {
    var p = page.s.store.pending || {}
    return p.crewLinks !== undefined || p.crewQuarantine !== undefined
  }
  function nextCheck() {
    if (!page.queue.length || checker.running || checker.head !== null || crewSettling()) return
    var head = page.queue[0]
    checker.head = head
    checker.launched = false
    checker.out = ""
    checker.gotOut = false
    checker.gotExit = false
    checker.code = -1
    checker.pending = JSON.stringify({ crewLinks: head.crewLinks, crewQuarantine: head.crewQuarantine,
                                       saved: { crewLinks: rawOf("crewLinks"), crewQuarantine: rawOf("crewQuarantine") } }) + "\n"
    checker.running = true
  }
  // Saved only on exit status 0 *and* {"ok": true, both lists}: a checker
  // that printed yes and then failed has not said yes (Codex review of M9).
  function checked(head, out, code) {
    if (!page.queue.length || head !== page.queue[0]) return
    var d = null
    try { d = JSON.parse(String(out).trim().split("\n").pop()) } catch (e) { d = null }
    if (code !== 0 || !d || d.ok !== true || !Array.isArray(d.crewLinks) || !Array.isArray(d.crewQuarantine)) {
      refused(d && d.ok === false && typeof d.why === "string" && d.why !== "" ? d.why : "the crew links could not be checked")
      return
    }
    if (savedPair() !== page.expectSaved) {
      refused("the crew links changed outside Settings while this was being saved, so it was not; what is shown now is what is saved")
      return
    }
    page.queue = page.queue.slice(1)
    applyChecked(d.crewLinks, d.crewQuarantine)
    page.expectSaved = page.s.crewCanon(d.crewLinks) + "|" + page.s.crewCanon(d.crewQuarantine)
    nextCheck()
  }
  function refused(why) {
    page.saveNote = "Not saved: " + String(why).slice(0, 300) + "."
    page.queue = []
    page.pendingQuarantine = ""
  }
  // What the validator took. Quarantine first, so the daemon holds the
  // agent apart before its links change; a list that did not change is not
  // written at all.
  function applyChecked(links, quarantine) {
    var c = page.s.cfg || {}
    if (page.s.crewCanon(quarantine) !== page.s.crewCanon(c.crewQuarantine === undefined ? [] : c.crewQuarantine))
      writeQuarantine(quarantine)
    if (page.s.crewCanon(links) !== page.s.crewCanon(c.crewLinks === undefined ? [] : c.crewLinks))
      writeLinks(links)
  }
  function writeLinks(list) {
    page.s.crewOwnWrite(list, null)
    page.s.put("crewLinks", list)
  }
  function writeQuarantine(list) {
    page.s.crewOwnWrite(null, list)
    page.s.put("crewQuarantine", list)
  }
  Connections {
    target: page.s.store
    function onPendingChanged() { if (!page.crewSettling()) page.nextCheck() }
  }
  Process {
    id: checker
    property var head: null
    property string pending: ""
    property bool launched: false
    // The answer is judged once both the output and the exit status are in,
    // whichever arrives last.
    property string out: ""
    property bool gotOut: false
    property bool gotExit: false
    property int code: -1
    function settle() {
      if (!checker.gotOut || !checker.gotExit || checker.head === null) return
      var h = checker.head
      checker.head = null
      page.checked(h, checker.out, checker.code)
    }
    command: ["agentvoice", "crew", "check"]
    stdinEnabled: true
    onStarted: { checker.launched = true; write(checker.pending); checker.pending = "" }
    onExited: function(exitCode) { checker.code = exitCode; checker.gotExit = true; checker.settle() }
    // `running` going false, not onExited: a spawn that never started emits
    // no exit, and an edit that saved nothing must say so.
    onRunningChanged: {
      if (running) return
      if (!launched && checker.head !== null) {
        var h = checker.head
        checker.head = null
        if (page.queue.length && h === page.queue[0]) page.refused("the agentvoice command could not be run, so the links could not be checked")
      }
      // The next edit waiting, if any: its turn comes when this process has
      // gone, not when its output ended, while it was still running.
      Qt.callLater(page.nextCheck)
    }
    stdout: StdioCollector {
      onStreamFinished: { checker.out = text; checker.gotOut = true; checker.settle() }
    }
  }

  // The edits. Quarantining and deleting come from a confirmation only
  // (tests/test_confirms.py).
  function quarantineAgent(id) {
    if (!page.readable || isQuarantined(id)) return
    page.pendingQuarantine = ""
    commit(linksQuarantining(id), page.quarantine.concat([id]), "quarantine " + labelOf(id))
  }
  function releaseAgent(id) {
    if (!page.readable || !isQuarantined(id)) return
    commit(copyLinks(), page.quarantine.filter(function(q) { return q !== id }), "release " + labelOf(id))
  }
  function linkEveryone() {
    commit(everyoneLinks(page.ids), page.quarantine, "link everyone")
  }
  function removeLink(from, to) {
    commit(withoutLink(from, to), page.quarantine, "link delete " + labelOf(from) + " → " + labelOf(to))
  }
  function addLink(from, to) {
    if (!page.readable) return
    if (isQuarantined(from)) { page.saveNote = labelOf(from) + " is quarantined, so it starts nothing: no link from it."; return }
    if (from === to || linkOf(from, to)) return
    commit(withLink(from, to), page.quarantine, "link add " + labelOf(from) + " → " + labelOf(to))
  }
  function setAbility(from, to, ability, on) {
    commit(withAbility(from, to, ability, on), page.quarantine, "link " + ability + (on ? " on " : " off ") + labelOf(from) + " → " + labelOf(to))
  }
  function setAskFirst(from, to, on) {
    commit(withAskFirst(from, to, on), page.quarantine, "ask first " + (on ? "on " : "off ") + labelOf(from) + " → " + labelOf(to))
  }
  function addReverse(from, to) {
    if (!page.readable || isQuarantined(to) || linkOf(to, from)) return
    commit(withReverse(from, to), page.quarantine, "link reverse " + labelOf(to) + " → " + labelOf(from))
  }
  // An unreadable list is replaced by none; the other, if readable, kept.
  function clearUnreadable() {
    commit(page.readLinks.links === null ? [] : page.links,
           page.readQuarantine.ids === null ? [] : page.quarantine, "crew reset")
  }
  property string lastAction: ""

  // --- the map's own state: which view, what is selected, where boxes sit -----
  property string view: "map"
  // { kind: "link", from, to } or { kind: "agent", id }, or null.
  property var selected: null
  function select(sel) { page.selected = sel }
  function isSelectedLink(from, to) { return page.selected !== null && page.selected.kind === "link" && page.selected.from === from && page.selected.to === to }
  function isSelectedAgent(id) { return page.selected !== null && page.selected.kind === "agent" && page.selected.id === id }
  // An agent dropped in the quarantine zone, waiting for the confirm; and
  // where it stood before, to go back to on Cancel.
  property string pendingQuarantine: ""
  property var pendingFrom: null

  // Links whose two ends are both agents here: the ones that can be drawn.
  // The rest name an agent removed or renamed and are listed under the map.
  function drawable() { return page.links.filter(function(l) { return page.ids.indexOf(l.from) >= 0 && page.ids.indexOf(l.to) >= 0 }) }
  function strays() { return page.links.filter(function(l) { return page.ids.indexOf(l.from) < 0 || page.ids.indexOf(l.to) < 0 }) }
  // "A D ?": what a line carries now, one letter each, "?" when it asks
  // you first, a dash when it carries nothing.
  readonly property var letters: ({ ask: "A", delegate: "D", message: "M", pass: "P" })
  function chipText(from, to) {
    var got = effectiveOf(from, to), l = linkOf(from, to)
    var t = got.length ? got.map(function(a) { return page.letters[a] }).join(" ") : "–"
    return t + (l && l.askFirst && got.length ? " ?" : "")
  }

  // Where each box sits, as fractions of the map (x across, y down, of its
  // centre). From the layout file; an agent with no spot, or one on the
  // wrong side of the zone for its quarantine, stands where the ring puts it.
  readonly property string layoutPath: (Quickshell.env("XDG_STATE_HOME") || (Quickshell.env("HOME") + "/.local/state")) + "/agentvoice/crew-layout.json"
  property var layout: ({})
  function parseLayout(text) {
    var out = {}
    if (typeof text !== "string" || text.length > 65536) return out
    var d
    try { d = JSON.parse(text) } catch (e) { return out }
    var spots = d && typeof d === "object" && d.spots && typeof d.spots === "object" && !Array.isArray(d.spots) ? d.spots : {}
    for (var k in spots) {
      var v = spots[k]
      if (!validId(k) || !v || typeof v !== "object") continue
      if (typeof v.x !== "number" || typeof v.y !== "number" || !isFinite(v.x) || !isFinite(v.y)) continue
      if (v.x < 0 || v.x > 1 || v.y < 0 || v.y > 1) continue
      out[k] = { x: v.x, y: v.y }
    }
    return out
  }
  function layoutText(spots) { return JSON.stringify({ version: 1, spots: spots }) + "\n" }
  function saveSpot(id, fx, fy) {
    var l = Object.assign({}, page.layout)
    l[id] = { x: Math.round(Math.max(0, Math.min(1, fx)) * 10000) / 10000,
              y: Math.round(Math.max(0, Math.min(1, fy)) * 10000) / 10000 }
    page.layout = l
    layoutFile.setText(layoutText(l))
  }
  function forgetSpot(id) {
    var l = Object.assign({}, page.layout)
    delete l[id]
    page.layout = l
    layoutFile.setText(layoutText(l))
  }
  FileView {
    id: layoutFile
    path: page.layoutPath
    printErrors: false
    property bool retried: false
    onLoaded: page.layout = page.parseLayout(text())
    // The folder may not be there yet on a first save: made, then once more.
    onSaveFailed: if (!retried) { retried = true; mkdirLayout.running = true }
  }
  Process {
    id: mkdirLayout
    command: ["mkdir", "-p", page.layoutPath.replace(/\/[^\/]*$/, "")]
    onExited: layoutFile.setText(page.layoutText(page.layout))
  }

  // The ring: agents not quarantined around the middle of the space above
  // the zone, the first at the top; quarantined ones in a row in the zone.
  function ringCentre(id, w, h, zoneH, boxW, boxH) {
    var top = h - zoneH
    if (isQuarantined(id) || id === page.pendingQuarantine) {
      var held = page.ids.filter(function(a) { return page.isQuarantined(a) || a === page.pendingQuarantine })
      var k = Math.max(0, held.indexOf(id))
      return Qt.point(w * (k + 1) / (held.length + 1), top + zoneH / 2 + 8)
    }
    var free = page.ids.filter(function(a) { return !page.isQuarantined(a) && a !== page.pendingQuarantine })
    var n = free.length, i = Math.max(0, free.indexOf(id))
    if (n <= 1) return Qt.point(w / 2, top / 2)
    var rx = Math.max(0, w / 2 - boxW / 2 - 10), ry = Math.max(0, top / 2 - boxH / 2 - 10)
    // Two side by side rather than one above the other; more from the top.
    var a = (n === 2 ? Math.PI : -Math.PI / 2) + 2 * Math.PI * i / n
    return Qt.point(w / 2 + rx * Math.cos(a), top / 2 + ry * Math.sin(a))
  }
  function centreOf(id, w, h, zoneH, boxW, boxH) {
    var spot = page.layout[id]
    var held = isQuarantined(id) || id === page.pendingQuarantine
    if (spot) {
      var x = spot.x * w, y = spot.y * h
      var inZone = y > h - zoneH
      if (inZone === held)
        return Qt.point(Math.max(boxW / 2, Math.min(w - boxW / 2, x)), Math.max(boxH / 2, Math.min(h - boxH / 2, y)))
    }
    return ringCentre(id, w, h, zoneH, boxW, boxH)
  }
  // An agent's box let go at (x, y), in map pixels: into the zone asks
  // first, out of it releases, anywhere else only moves it.
  function dropped(id, x, y, w, h, zoneH, before) {
    var inZone = y > h - zoneH
    if (inZone && !isQuarantined(id)) {
      if (!page.readable) return
      page.pendingFrom = before
      page.pendingQuarantine = id
      saveSpot(id, x / w, y / h)
      select({ kind: "agent", id: id })
      return
    }
    saveSpot(id, x / w, y / h)
    if (!inZone && isQuarantined(id)) releaseAgent(id)
  }
  function selectedLink() {
    var sel = page.selected
    return sel && sel.kind === "link" ? page.linkOf(sel.from, sel.to) : null
  }
  function selectedAgent() {
    var sel = page.selected
    return sel && sel.kind === "agent" && page.ids.indexOf(sel.id) >= 0 ? sel.id : ""
  }
  property bool deleteAsked: false
  function armDelete() { page.deleteAsked = true }
  // A line drawn from one agent onto another: a new link carrying ask, or
  // the one already there, selected either way.
  function drawLink(from, to) {
    if (!from || !to || from === to) return
    if (!linkOf(from, to)) addLink(from, to)
    if (linkOf(from, to)) select({ kind: "link", from: from, to: to })
  }
  function quarantineQuestion(id) {
    var lose = quarantineLoses(id)
    return "Quarantine " + labelOf(id) + "? It loses " + lose.out + " link" + (lose.out === 1 ? "" : "s") +
           " out" + (lose.trimmed ? ", message and pass on " + lose.trimmed + " link" + (lose.trimmed === 1 ? "" : "s") + " in" : "") +
           ", its sessions and its shared chats. Releasing it gives none back."
  }
  // Cancel on the confirm, or it ran out: the box goes back where it was.
  function quarantineCancelled(id) {
    if (page.pendingQuarantine !== id) return
    page.pendingQuarantine = ""
    if (page.pendingFrom) saveSpot(id, page.pendingFrom.x, page.pendingFrom.y)
    else forgetSpot(id)
    page.pendingFrom = null
  }

  PageHeader {
    width: parent.width
    title: "Crew map"
    subtitle: "Who may ask, give work to, pass to or message whom. Agents reach each other only along a link here; a pass you start yourself needs none."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  // --- what needs saying first --------------------------------------------------
  Card {
    width: parent.width
    visible: !page.readable
    title: "The crew links can't be read"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: page.problem.charAt(0).toUpperCase() + page.problem.slice(1) + ". Until they can, no agent can reach another, and nothing goes into or out of quarantine. They were changed outside Settings; fix them there, or start again with nothing linked here."
      color: page.s.urgent
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    DangerButton {
      text: "Start again with no links"
      question: "Replace the unreadable crew settings with none, so nobody is linked?"
      confirmText: "Replace"
      maxWidth: parent.width
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onConfirmed: page.clearUnreadable()
    }
  }

  Card {
    width: parent.width
    visible: page.readable && page.links.length === 0
    title: "No links yet, so agents cannot reach each other"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "Add links below, or put back what there was before crew links: every agent able to ask, give work to, pass to and message every other."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    DangerButton {
      text: "Link everyone as before"
      iconText: "\u{f0337}"
      question: "Let all " + page.ids.length + " agents ask, give work to, pass to and message each other?"
      confirmText: "Link everyone"
      tooltipText: "Writes a link each way between every two agents, allowing everything, none asking you first."
      maxWidth: parent.width
      enabled: page.ids.length > 1
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onConfirmed: page.linkEveryone()
    }
  }

  Text {
    width: parent.width
    visible: page.s.crewOutsideAt !== ""
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: "Changed outside Settings at " + page.s.crewOutsideAt + ". What is shown is what is saved now."
    color: page.s.urgent
    font.family: page.s.fontFamily
    font.pixelSize: Style.font.caption
  }

  // --- Map or Table, and whether the last edit was saved ---------------------------
  Item {
    width: parent.width
    visible: page.readable
    height: viewChoice.implicitHeight
    SegmentedChoice {
      id: viewChoice
      accessibleName: "Show the crew as"
      anchors.left: parent.left
      options: [{ value: "map", label: "Map", tooltip: "The crew drawn: drag to link, click to change." },
                { value: "table", label: "Table", tooltip: "Every link in a row, every agent with its quarantine switch." }]
      value: page.view
      foreground: page.s.foreground
      accent: page.s.accent
      fontFamily: page.s.fontFamily
      onCommitted: function(v) { page.view = v }
    }
    Text {
      anchors.right: parent.right
      anchors.verticalCenter: viewChoice.verticalCenter
      visible: page.saving
      textFormat: Text.PlainText
      text: "Checking and saving…"
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
  }
  Text {
    width: parent.width
    visible: page.saveNote !== ""
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: page.saveNote
    color: page.s.urgent
    font.family: page.s.fontFamily
    font.pixelSize: Style.font.caption
  }

  // --- the links, drawn -------------------------------------------------------------
  Card {
    id: mapCard
    width: parent.width
    visible: page.readable && page.view === "map"
    title: "Map"
    subtitle: "Drag from a dot onto another agent to link; click to change."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Item {
      id: map
      objectName: "crewMap"
      width: parent.width
      readonly property real zoneH: Style.space(78)
      readonly property real boxW: Math.max(Style.space(64), Math.min(Style.space(116), width / 4.6))
      readonly property real boxH: Style.space(34)
      height: Math.round(Math.max(Style.space(280), Math.min(Style.space(420), width * 0.6))) + zoneH
      clip: true

      // Past this many lines the labels would cover the map: only the lines
      // of the selected agent or link keep theirs, and the rest go faint.
      readonly property bool crowded: page.drawable().length > 14
      // An agent being dragged: its centre, so the lines follow it.
      property string dragId: ""
      property real dragX: 0
      property real dragY: 0
      // A link being drawn from an agent's dot to the pointer.
      property string linkFrom: ""
      property real linkX: 0
      property real linkY: 0

      function centreAt(id) {
        if (id === dragId) return Qt.point(dragX, dragY)
        return page.centreOf(id, width, height, zoneH, boxW, boxH)
      }
      function agentAt(x, y) {
        for (var i = 0; i < page.ids.length; i++) {
          var c = centreAt(page.ids[i])
          if (Math.abs(x - c.x) <= boxW / 2 + 4 && Math.abs(y - c.y) <= boxH / 2 + 4) return page.ids[i]
        }
        return ""
      }

      // A click on nothing clears what was selected.
      MouseArea {
        anchors.fill: parent
        onClicked: page.select(null)
      }

      Rectangle {
        id: zone
        objectName: "quarantineZone"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: map.zoneH
        radius: Style.space(8)
        color: Qt.rgba(page.s.urgent.r, page.s.urgent.g, page.s.urgent.b, 0.10)
        border.color: Qt.rgba(page.s.urgent.r, page.s.urgent.g, page.s.urgent.b, 0.55)
        border.width: 1
        Text {
          anchors.left: parent.left
          anchors.top: parent.top
          anchors.margins: Style.space(6)
          textFormat: Text.PlainText
          text: "Quarantine: drag an agent here"
          color: page.s.urgent
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
      }

      Repeater {
        model: page.drawable()
        delegate: Item {
          id: eItem
          required property var modelData
          readonly property string from: modelData.from
          readonly property string to: modelData.to
          readonly property bool chosen: page.isSelectedLink(from, to)
          readonly property bool inert: page.effectiveOf(from, to).length === 0
          readonly property bool both: page.linkOf(to, from) !== null
          // Touching what is selected: drawn in full on a crowded map.
          readonly property bool near: chosen || page.isSelectedAgent(from) || page.isSelectedAgent(to) || page.isSelectedAgent(map.dragId)
                                       || map.dragId === from || map.dragId === to
          readonly property bool shown: !map.crowded || near
          width: map.width
          height: map.height

          CrewEdge {
            id: edge
            anchors.fill: parent
            x1: map.centreAt(eItem.from).x
            y1: map.centreAt(eItem.from).y
            x2: map.centreAt(eItem.to).x
            y2: map.centreAt(eItem.to).y
            halfW: map.boxW / 2
            halfH: map.boxH / 2
            bend: eItem.both ? Style.space(34) : 0
            chipT: eItem.both ? 0.36 : 0.5
            inert: eItem.inert
            lineWidth: eItem.chosen ? 2.5 : 1.5
            color: eItem.chosen ? page.s.accent
                 : eItem.inert ? page.s.dim
                 : Qt.rgba(page.s.foreground.r, page.s.foreground.g, page.s.foreground.b, 0.75)
            opacity: eItem.shown ? 1 : 0.22
          }
          Rectangle {
            id: chip
            objectName: "edge:" + eItem.from + ">" + eItem.to
            visible: eItem.shown
            x: edge.midX - width / 2
            y: edge.midY - height / 2
            width: chipLabel.implicitWidth + Style.space(10)
            height: chipLabel.implicitHeight + Style.space(4)
            radius: height / 2
            color: eItem.chosen ? page.s.accent : page.s.background
            border.color: chip.activeFocus ? page.s.accent : (eItem.inert ? page.s.dim : page.s.faint)
            border.width: chip.activeFocus ? 2 : 1
            activeFocusOnTab: true
            Accessible.role: Accessible.Button
            Accessible.name: page.effectiveLine(eItem.from, eItem.to)
            Keys.onPressed: function(e) {
              if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) {
                page.select({ kind: "link", from: eItem.from, to: eItem.to }); e.accepted = true
              } else if (e.key === Qt.Key_Delete || e.key === Qt.Key_Backspace) {
                page.select({ kind: "link", from: eItem.from, to: eItem.to })
                page.armDelete()
                e.accepted = true
              }
            }
            Text {
              id: chipLabel
              anchors.centerIn: parent
              textFormat: Text.PlainText
              text: page.chipText(eItem.from, eItem.to)
              color: eItem.chosen ? page.s.background : page.s.foreground
              font.family: page.s.fontFamily
              font.pixelSize: Style.font.caption
            }
            MouseArea {
              anchors.fill: parent
              anchors.margins: -Style.space(4)
              cursorShape: Qt.PointingHandCursor
              onClicked: page.select({ kind: "link", from: eItem.from, to: eItem.to })
            }
          }
        }
      }

      // The line that follows the pointer while a link is being drawn.
      CrewEdge {
        anchors.fill: parent
        visible: map.linkFrom !== ""
        x1: map.linkFrom !== "" ? map.centreAt(map.linkFrom).x : 0
        y1: map.linkFrom !== "" ? map.centreAt(map.linkFrom).y : 0
        x2: map.linkX
        y2: map.linkY
        halfW: map.boxW / 2
        halfH: map.boxH / 2
        color: page.s.accent
        inert: map.agentAt(map.linkX, map.linkY) === ""
      }

      Repeater {
        model: page.ids
        delegate: Rectangle {
          id: node
          required property var modelData
          readonly property string aid: modelData
          readonly property bool held: page.isQuarantined(aid)
          readonly property bool asking: page.pendingQuarantine === aid
          readonly property point home: page.centreOf(aid, map.width, map.height, map.zoneH, map.boxW, map.boxH)
          objectName: "agent:" + aid
          width: map.boxW
          height: map.boxH
          x: home.x - width / 2
          y: home.y - height / 2
          radius: Style.space(6)
          color: page.isSelectedAgent(aid) ? Qt.rgba(page.s.accent.r, page.s.accent.g, page.s.accent.b, 0.22) : page.s.background
          border.color: node.activeFocus || page.isSelectedAgent(aid) ? page.s.accent : (held || asking ? page.s.urgent : page.s.faint)
          border.width: node.activeFocus ? 2 : 1
          opacity: page.isOff(aid) ? 0.6 : 1
          activeFocusOnTab: true
          Accessible.role: Accessible.Button
          Accessible.name: page.labelOf(aid) + (held ? ", quarantined" : "")

          function rebind() {
            node.x = Qt.binding(function() { return node.home.x - node.width / 2 })
            node.y = Qt.binding(function() { return node.home.y - node.height / 2 })
          }
          // Moved with the arrow keys: the same as a drag let go there.
          function nudge(dx, dy) {
            var c = node.home
            page.dropped(node.aid, Math.max(map.boxW / 2, Math.min(map.width - map.boxW / 2, c.x + dx)),
                         Math.max(map.boxH / 2, Math.min(map.height - map.boxH / 2, c.y + dy)),
                         map.width, map.height, map.zoneH, page.layout[node.aid] || null)
          }
          Keys.onPressed: function(e) {
            var step = (e.modifiers & Qt.ShiftModifier) ? Style.space(48) : Style.space(12)
            if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) {
              page.select({ kind: "agent", id: node.aid }); e.accepted = true
            } else if (e.key === Qt.Key_Left) { node.nudge(-step, 0); e.accepted = true }
            else if (e.key === Qt.Key_Right) { node.nudge(step, 0); e.accepted = true }
            else if (e.key === Qt.Key_Up) { node.nudge(0, -step); e.accepted = true }
            else if (e.key === Qt.Key_Down) { node.nudge(0, step); e.accepted = true }
          }

          Text {
            anchors.left: parent.left
            anchors.right: dot.left
            anchors.leftMargin: Style.space(8)
            anchors.rightMargin: Style.space(4)
            anchors.verticalCenter: parent.verticalCenter
            elide: Text.ElideRight
            textFormat: Text.PlainText
            text: page.labelOf(node.aid)
            color: node.held || node.asking ? page.s.urgent : page.s.foreground
            font.family: page.s.fontFamily
            font.pixelSize: Style.font.body
          }
          MouseArea {
            id: body
            anchors.fill: parent
            preventStealing: true
            cursorShape: drag.active ? Qt.ClosedHandCursor : Qt.OpenHandCursor
            drag.target: node
            // The box stays under the pointer where it was grabbed, rather
            // than trailing it by the drag threshold.
            drag.smoothed: false
            drag.minimumX: 0
            drag.minimumY: 0
            drag.maximumX: map.width - node.width
            drag.maximumY: map.height - node.height
            property var before: null
            onPressed: body.before = page.layout[node.aid] || null
            onPositionChanged: if (drag.active) {
              map.dragX = node.x + node.width / 2
              map.dragY = node.y + node.height / 2
              map.dragId = node.aid
            }
            onReleased: {
              if (map.dragId === node.aid) {
                var cx = node.x + node.width / 2, cy = node.y + node.height / 2
                map.dragId = ""
                page.dropped(node.aid, cx, cy, map.width, map.height, map.zoneH, body.before)
              } else {
                page.select({ kind: "agent", id: node.aid })
              }
              node.rebind()
            }
            onCanceled: { map.dragId = ""; node.rebind() }
          }
          // The dot a link is drawn from. None on a quarantined agent: it
          // starts nothing.
          Rectangle {
            id: dot
            objectName: "dot:" + node.aid
            visible: !node.held
            anchors.right: parent.right
            anchors.rightMargin: Style.space(5)
            anchors.verticalCenter: parent.verticalCenter
            width: Style.space(12)
            height: width
            radius: width / 2
            color: map.linkFrom === node.aid ? page.s.accent : Qt.rgba(page.s.accent.r, page.s.accent.g, page.s.accent.b, 0.55)
            border.color: page.s.accent
            MouseArea {
              anchors.fill: parent
              anchors.margins: -Style.space(5)
              preventStealing: true
              cursorShape: Qt.CrossCursor
              onPressed: function(m) {
                var q = mapToItem(map, m.x, m.y)
                map.linkX = q.x; map.linkY = q.y
                map.linkFrom = node.aid
              }
              onPositionChanged: function(m) {
                var q = mapToItem(map, m.x, m.y)
                map.linkX = q.x; map.linkY = q.y
              }
              onReleased: function(m) {
                var q = mapToItem(map, m.x, m.y)
                var target = map.agentAt(q.x, q.y)
                var from = map.linkFrom
                map.linkFrom = ""
                if (target === "" || target === from) return
                page.drawLink(from, target)
              }
              onCanceled: map.linkFrom = ""
            }
          }
        }
      }
    }

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "A ask · D give a task · M message · P pass · ? asks you first · dashed: carries nothing as things stand. A line goes one way; the arrow is at the agent it reaches." +
            (map.crowded ? " With this many lines, click an agent to label its own." : "")
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      visible: page.ids.length < 2
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "There is only one agent, so there is nobody to link it to. Add another on the Agents page."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      visible: page.strays().length > 0
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: page.strays().length + (page.strays().length === 1 ? " link names" : " links name") +
            " an agent that is not here now (removed, or renamed), so " + (page.strays().length === 1 ? "it is" : "they are") +
            " not drawn and match nothing. Delete them in the table."
      color: page.s.urgent
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    // --- the inspector: what was clicked --------------------------------------------
    Text {
      width: parent.width
      visible: page.selectedLink() === null && page.selectedAgent() === ""
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "Nothing selected. Tab reaches each agent and each line's label; Enter opens it, the arrow keys move an agent, Delete on a line's label asks to delete it."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    Column {
      id: linkInspector
      objectName: "linkInspector"
      width: parent.width
      spacing: Style.space(6)
      visible: page.selectedLink() !== null
      readonly property string from: page.selectedLink() ? page.selectedLink().from : ""
      readonly property string to: page.selectedLink() ? page.selectedLink().to : ""
      Rectangle { width: parent.width; height: 1; color: page.s.faint }
      Text {
        width: parent.width
        elide: Text.ElideRight
        textFormat: Text.PlainText
        text: linkInspector.from !== "" ? page.labelOf(linkInspector.from) + "  →  " + page.labelOf(linkInspector.to) : ""
        color: page.s.foreground
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.body
      }
      LinkEditor {
        width: parent.width
        visible: linkInspector.from !== ""
        pg: page
        from: linkInspector.from
        to: linkInspector.to
      }
      Flow {
        width: parent.width
        spacing: Style.space(8)
        ActionButton {
          readonly property bool there: linkInspector.from !== "" && page.linkOf(linkInspector.to, linkInspector.from) !== null
          text: there ? "Go to " + page.labelOf(linkInspector.to) + " → " + page.labelOf(linkInspector.from) : "Also allow the reverse"
          bordered: true
          focusable: true
          enabled: there || (linkInspector.from !== "" && !page.isQuarantined(linkInspector.to))
          tooltipText: there ? "The reverse line is already there."
                       : page.isQuarantined(linkInspector.to) ? page.labelOf(linkInspector.to) + " is quarantined, so it starts nothing."
                       : "Adds " + page.labelOf(linkInspector.to) + " → " + page.labelOf(linkInspector.from) + " with the same abilities."
          fontFamily: page.s.fontFamily
          foreground: page.s.foreground
          onClicked: {
            var f = linkInspector.from, t = linkInspector.to
            if (!there) page.addReverse(f, t)
            page.select({ kind: "link", from: t, to: f })
          }
        }
        DangerButton {
          id: deleteLine
          text: "Delete line"
          question: linkInspector.from !== "" ? "Delete the link from " + page.labelOf(linkInspector.from) + " to " + page.labelOf(linkInspector.to) + "?" : ""
          confirmText: "Delete"
          maxWidth: linkInspector.width
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onConfirmed: {
            page.removeLink(linkInspector.from, linkInspector.to)
            page.select(null)
          }
        }
      }
    }

    Column {
      id: agentInspector
      objectName: "agentInspector"
      width: parent.width
      spacing: Style.space(6)
      visible: page.selectedAgent() !== ""
      readonly property string aid: page.selectedAgent()
      readonly property bool held: aid !== "" && page.isQuarantined(aid)
      property string linkTo: ""
      Rectangle { width: parent.width; height: 1; color: page.s.faint }
      Text {
        width: parent.width
        elide: Text.ElideRight
        textFormat: Text.PlainText
        text: agentInspector.aid === "" ? "" : page.labelOf(agentInspector.aid) + (agentInspector.held ? "  · quarantined" : "") + (page.isOff(agentInspector.aid) ? "  · switched off" : "")
        color: agentInspector.held ? page.s.urgent : page.s.foreground
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.body
      }
      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: agentInspector.aid === "" ? "" : "Can reach: " + page.reachWords(page.reachOf(agentInspector.aid))
        color: page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: agentInspector.aid === "" ? "" : "Reached by: " + page.reachWords(page.reachedBy(agentInspector.aid))
        color: page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      // Linking from the keyboard: the same as drawing a line.
      Flow {
        width: parent.width
        spacing: Style.space(8)
        visible: !agentInspector.held
        Dropdown {
          id: linkToChoice
          width: Style.space(170)
          showLabel: false
          readonly property var others: page.ids.filter(function(id) { return id !== agentInspector.aid })
          options: others.map(function(id) { return { value: id, label: "Link to " + page.labelOf(id) } })
          value: others.indexOf(agentInspector.linkTo) >= 0 ? agentInspector.linkTo : (others.length ? others[0] : "")
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onChanged: function(v) { agentInspector.linkTo = v }
        }
        ActionButton {
          text: "Add link"
          bordered: true
          focusable: true
          enabled: linkToChoice.value !== "" && page.linkOf(agentInspector.aid, linkToChoice.value) === null
          tooltipText: page.linkOf(agentInspector.aid, linkToChoice.value) !== null ? "That link is already there." : "A new line allows ask; add more in its inspector."
          fontFamily: page.s.fontFamily
          foreground: page.s.foreground
          onClicked: page.drawLink(agentInspector.aid, linkToChoice.value)
        }
      }
      DangerButton {
        id: quarantineButton
        visible: !agentInspector.held && agentInspector.aid !== ""
        text: "Quarantine"
        question: agentInspector.aid !== "" ? page.quarantineQuestion(agentInspector.aid) : ""
        confirmText: "Quarantine"
        maxWidth: agentInspector.width
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onConfirmed: page.quarantineAgent(agentInspector.aid)
        onCancelled: page.quarantineCancelled(agentInspector.aid)
      }
      ActionButton {
        visible: agentInspector.held
        text: "Release"
        bordered: true
        focusable: true
        tooltipText: "Ends the quarantine. It gets back no link, session or chat it lost."
        fontFamily: page.s.fontFamily
        foreground: page.s.foreground
        onClicked: page.releaseAgent(agentInspector.aid)
      }
    }
    // A drop in the zone arms the confirm; a Delete on a line's label arms
    // the line's.
    Connections {
      target: page
      function onPendingQuarantineChanged() {
        Qt.callLater(function() {
          if (page.pendingQuarantine !== "" && page.pendingQuarantine === agentInspector.aid) quarantineButton.arm()
        })
      }
      function onDeleteAskedChanged() {
        if (!page.deleteAsked) return
        page.deleteAsked = false
        Qt.callLater(function() { if (linkInspector.visible) deleteLine.arm() })
      }
    }
  }

  // --- the links, as a table ------------------------------------------------------
  Card {
    width: parent.width
    visible: page.readable && page.view === "table"
    title: "Links"
    subtitle: page.links.length === 1 ? "1 link. A link goes one way." : page.links.length + " links. A link goes one way."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Repeater {
      // Built only while the table is shown: 56 rows of chips for eight
      // agents, rebuilt on every save, behind a hidden map, cost seconds.
      model: page.readable && page.view === "table" ? page.links : []
      delegate: Column {
        id: row
        required property var modelData
        readonly property string from: modelData.from
        readonly property string to: modelData.to
        width: parent ? parent.width : 0
        spacing: Style.space(6)

        Rectangle { width: parent.width; height: 1; color: page.s.faint }

        Item {
          width: parent.width
          height: Math.max(pairText.implicitHeight, del.implicitHeight)
          Text {
            id: pairText
            anchors.left: parent.left
            anchors.right: del.left
            anchors.rightMargin: Style.space(8)
            anchors.verticalCenter: parent.verticalCenter
            elide: Text.ElideRight
            textFormat: Text.PlainText
            text: page.labelOf(row.from) + "  →  " + page.labelOf(row.to)
            color: page.s.foreground
            font.family: page.s.fontFamily
            font.pixelSize: Style.font.body
          }
          DangerButton {
            id: del
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: "Delete"
            question: "Delete the link from " + page.labelOf(row.from) + " to " + page.labelOf(row.to) + "?"
            confirmText: "Delete"
            maxWidth: row.width
            foreground: page.s.foreground
            fontFamily: page.s.fontFamily
            onConfirmed: page.removeLink(row.from, row.to)
          }
        }

        LinkEditor {
          width: parent.width
          pg: page
          from: row.from
          to: row.to
        }
      }
    }

    Hint {
      width: parent.width
      text: "“Ask me first” is advisory for Trusted agents."
      detail: "The card is answered only from this screen, but an agent at Trust everything can run commands without asking, and so could set itself up to answer its own card. Below Trusted it would have to ask you first."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
    }

    // Adding one: from, to, and a first ability of `ask`.
    Flow {
      width: parent.width
      spacing: Style.space(8)
      property string addFrom: page.ids.length > 0 ? page.ids[0] : ""
      property string addTo: page.ids.length > 1 ? page.ids[1] : ""
      id: adder
      Dropdown {
        width: Style.space(150)
        showLabel: false
        options: page.ids.map(function(id) { return { value: id, label: "From " + page.labelOf(id) } })
        value: adder.addFrom
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onChanged: function(v) { adder.addFrom = v }
      }
      Dropdown {
        width: Style.space(150)
        showLabel: false
        options: page.ids.map(function(id) { return { value: id, label: "To " + page.labelOf(id) } })
        value: adder.addTo
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onChanged: function(v) { adder.addTo = v }
      }
      ActionButton {
        text: "Add link"
        bordered: true
        focusable: true
        enabled: adder.addFrom !== adder.addTo && page.linkOf(adder.addFrom, adder.addTo) === null
        tooltipText: adder.addFrom === adder.addTo ? "An agent needs no link to itself."
                     : page.linkOf(adder.addFrom, adder.addTo) !== null ? "That link is already there." : "A new link allows ask; add more on its row."
        fontFamily: page.s.fontFamily
        foreground: page.s.foreground
        onClicked: page.addLink(adder.addFrom, adder.addTo)
      }
    }
  }

  // --- the agents -------------------------------------------------------------------
  Card {
    width: parent.width
    visible: page.readable && page.view === "table"
    title: "Agents"
    subtitle: "Who each can reach, and who can reach it."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "A quarantined agent starts nothing, is only asked questions and given tasks with the brief alone, writes no communal note, and what it answers comes back marked. Quarantining it also ends its sessions and the chats shared with it; releasing it gives none of that back."
      color: page.s.dim
      font.family: page.s.fontFamily
      font.pixelSize: Style.font.caption
    }

    Repeater {
      model: page.readable && page.view === "table" ? page.ids : []
      delegate: Column {
        id: arow
        required property var modelData
        readonly property string aid: modelData
        readonly property bool held: page.isQuarantined(aid)
        width: parent ? parent.width : 0
        spacing: Style.space(4)

        Rectangle { width: parent.width; height: 1; color: page.s.faint }

        Item {
          width: parent.width
          height: Math.max(nameText.implicitHeight, qButton.implicitHeight, releaseButton.implicitHeight)
          Text {
            id: nameText
            anchors.left: parent.left
            anchors.right: arow.held ? releaseButton.left : qButton.left
            anchors.rightMargin: Style.space(8)
            anchors.verticalCenter: parent.verticalCenter
            elide: Text.ElideRight
            textFormat: Text.PlainText
            text: page.labelOf(arow.aid) + (arow.held ? "  · quarantined" : "") + (page.isOff(arow.aid) ? "  · switched off" : "")
            color: arow.held ? page.s.urgent : page.s.foreground
            font.family: page.s.fontFamily
            font.pixelSize: Style.font.body
          }
          DangerButton {
            id: qButton
            visible: !arow.held
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: "Quarantine"
            question: page.quarantineQuestion(arow.aid)
            confirmText: "Quarantine"
            maxWidth: arow.width
            foreground: page.s.foreground
            fontFamily: page.s.fontFamily
            onConfirmed: page.quarantineAgent(arow.aid)
          }
          ActionButton {
            id: releaseButton
            visible: arow.held
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: "Release"
            bordered: true
            focusable: true
            tooltipText: "Ends the quarantine. It gets back no link, session or chat it lost."
            fontFamily: page.s.fontFamily
            foreground: page.s.foreground
            onClicked: page.releaseAgent(arow.aid)
          }
        }
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          textFormat: Text.PlainText
          text: "Can reach: " + page.reachWords(page.reachOf(arow.aid))
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          textFormat: Text.PlainText
          text: "Reached by: " + page.reachWords(page.reachedBy(arow.aid))
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }
  }

  // One link's abilities, Ask me first and what it amounts to: a table row
  // and the map's inspector both draw this, and both edit through `pg`.
  component LinkEditor: Column {
    id: ed
    property var pg
    property string from: ""
    property string to: ""
    readonly property var link: from !== "" && pg ? pg.linkOf(from, to) : null
    spacing: Style.space(6)

    ToggleChips {
      width: parent.width
      options: ed.pg.abilities.map(function(a) {
        var why = ed.pg.isQuarantined(ed.from) ? ed.pg.labelOf(ed.from) + " is quarantined, so it starts nothing."
                : ed.pg.isQuarantined(ed.to) && ed.pg.intoQuarantine.indexOf(a) < 0
                  ? ed.pg.labelOf(ed.to) + " is quarantined: a link into it carries only ask and delegate." : ""
        return { value: a, label: a, tooltip: "Lets " + ed.pg.labelOf(ed.from) + " " + ed.pg.verbs[a] + " " + ed.pg.labelOf(ed.to) + ".",
                 disabledReason: why }
      })
      chipStates: {
        var st = {}
        for (var i = 0; i < ed.pg.abilities.length; i++)
          st[ed.pg.abilities[i]] = ed.link && ed.link.allow.indexOf(ed.pg.abilities[i]) >= 0 ? "on" : "off"
        return st
      }
      foreground: ed.pg.s.foreground
      accent: ed.pg.s.accent
      fontFamily: ed.pg.s.fontFamily
      onToggled: function(value, state) { ed.pg.setAbility(ed.from, ed.to, value, state === "on") }
    }
    Row {
      spacing: Style.space(8)
      FocusSwitch {
        // Found by name by bench/preview/targets/crew.qml.
        objectName: "askFirst"
        accessibleName: "Ask me first"
        checked: ed.link !== null && ed.link.askFirst === true
        foreground: ed.pg.s.foreground
        accent: ed.pg.s.accent
        onToggled: ed.pg.setAskFirst(ed.from, ed.to, !(ed.link !== null && ed.link.askFirst === true))
      }
      Text {
        anchors.verticalCenter: parent.verticalCenter
        textFormat: Text.PlainText
        text: "Ask me first" + (ed.pg.trustOf(ed.from) === "trusted" ? " (advisory: " + ed.pg.labelOf(ed.from) + " is Trusted)" : "")
        color: ed.pg.s.foreground
        font.family: ed.pg.s.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: ed.from !== "" ? ed.pg.effectiveLine(ed.from, ed.to) : ""
      color: ed.pg.s.dim
      font.family: ed.pg.s.fontFamily
      font.pixelSize: Style.font.caption
    }
  }
}
