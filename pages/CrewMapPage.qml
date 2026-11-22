import QtQuick
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
// two settings, `crewLinks` and `crewQuarantine`, and every write goes
// through writeLinks() or writeQuarantine(): the drawn map (M9) will call
// the same two.
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
  readonly property var links: readLinks.links || []
  readonly property var quarantine: readQuarantine.ids || []

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

  // --- the only writes ---------------------------------------------------------
  function writeLinks(list) {
    page.s.crewOwnWrite(list, null)
    page.s.put("crewLinks", list)
  }
  function writeQuarantine(list) {
    page.s.crewOwnWrite(null, list)
    page.s.put("crewQuarantine", list)
  }
  // From a confirmation only (tests/test_confirms.py): the quarantine goes
  // out first, so the daemon holds the agent apart before its links change.
  function quarantineAgent(id) {
    if (!page.readable || isQuarantined(id)) return
    page.lastAction = "quarantine " + labelOf(id)
    writeQuarantine(page.quarantine.concat([id]))
    writeLinks(linksQuarantining(id))
  }
  function releaseAgent(id) {
    if (!page.readable) return
    page.lastAction = "release " + labelOf(id)
    writeQuarantine(page.quarantine.filter(function(q) { return q !== id }))
  }
  function linkEveryone() {
    page.lastAction = "link everyone"
    writeLinks(everyoneLinks(page.ids))
  }
  function removeLink(from, to) {
    page.lastAction = "link delete " + labelOf(from) + " → " + labelOf(to)
    writeLinks(withoutLink(from, to))
  }
  function clearUnreadable() {
    page.lastAction = "crew reset"
    if (page.readLinks.links === null) writeLinks([])
    if (page.readQuarantine.ids === null) writeQuarantine([])
  }
  property string lastAction: ""

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

  // --- the links ------------------------------------------------------------------
  Card {
    width: parent.width
    visible: page.readable
    title: "Links"
    subtitle: page.links.length === 1 ? "1 link. A link goes one way." : page.links.length + " links. A link goes one way."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    Repeater {
      model: page.readable ? page.links : []
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

        ToggleChips {
          width: parent.width
          options: page.abilities.map(function(a) {
            var why = page.isQuarantined(row.from) ? page.labelOf(row.from) + " is quarantined, so it starts nothing."
                    : page.isQuarantined(row.to) && page.intoQuarantine.indexOf(a) < 0
                      ? page.labelOf(row.to) + " is quarantined: a link into it carries only ask and delegate." : ""
            return { value: a, label: a, tooltip: "Lets " + page.labelOf(row.from) + " " + page.verbs[a] + " " + page.labelOf(row.to) + ".",
                     disabledReason: why }
          })
          chipStates: {
            var st = {}
            for (var i = 0; i < page.abilities.length; i++)
              st[page.abilities[i]] = row.modelData.allow.indexOf(page.abilities[i]) >= 0 ? "on" : "off"
            return st
          }
          foreground: page.s.foreground
          accent: page.s.accent
          fontFamily: page.s.fontFamily
          onToggled: function(value, state) { page.writeLinks(page.withAbility(row.from, row.to, value, state === "on")) }
        }

        Row {
          spacing: Style.space(8)
          ToggleSwitch {
            // Found by name by bench/preview/targets/crew.qml.
            objectName: "askFirst"
            checked: row.modelData.askFirst === true
            foreground: page.s.foreground
            accent: page.s.accent
            onToggled: page.writeLinks(page.withAskFirst(row.from, row.to, !row.modelData.askFirst))
          }
          Text {
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: "Ask me first" + (page.trustOf(row.from) === "trusted" ? " (advisory: " + page.labelOf(row.from) + " is Trusted)" : "")
            color: page.s.foreground
            font.family: page.s.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          textFormat: Text.PlainText
          text: page.effectiveLine(row.from, row.to)
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
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
      Button {
        text: "Add link"
        bordered: true
        focusable: true
        enabled: adder.addFrom !== adder.addTo && page.linkOf(adder.addFrom, adder.addTo) === null
        tooltipText: adder.addFrom === adder.addTo ? "An agent needs no link to itself."
                     : page.linkOf(adder.addFrom, adder.addTo) !== null ? "That link is already there." : "A new link allows ask; add more on its row."
        fontFamily: page.s.fontFamily
        foreground: page.s.foreground
        onClicked: page.writeLinks(page.withLink(adder.addFrom, adder.addTo))
      }
    }
  }

  // --- the agents -------------------------------------------------------------------
  Card {
    width: parent.width
    visible: page.readable
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
      model: page.readable ? page.ids : []
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
            question: {
              var lose = page.quarantineLoses(arow.aid)
              return "Quarantine " + page.labelOf(arow.aid) + "? It loses " + lose.out + " link" + (lose.out === 1 ? "" : "s") +
                     " out" + (lose.trimmed ? ", message and pass on " + lose.trimmed + " link" + (lose.trimmed === 1 ? "" : "s") + " in" : "") +
                     ", its sessions and its shared chats. Releasing it gives none back."
            }
            confirmText: "Quarantine"
            maxWidth: arow.width
            foreground: page.s.foreground
            fontFamily: page.s.fontFamily
            onConfirmed: page.quarantineAgent(arow.aid)
          }
          Button {
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
}
