// The Chats page (phase M18), on synthetic chats in a scratch data folder
// and a synthetic shell.json:
//
//   preview.sh --scratch-data --config bench/preview/configs/crew3.json \
//     --state bench/preview/states/showcase.json --out /tmp/c chats
//
// --arg list (the default): the page, the chat passed from Theo to Sora open.
//   empty: nothing saved and saving off (the seed writes nothing).
//   session: "This session" open: 200 synthetic exchanges (with --state the
//     seed writes them into the scratch runtime folder, never the real one).
//   html: the chat whose text looks like HTML, open.
//   details: Sora's Chats tab on Agent details. communal: Communal → Chats.
//   drive: clicks and keys, each check a PREVIEW PASS or FAIL line --
//     eleven pages and their shortcuts; HTML-looking text drawn as text;
//     the search box asks `chats search` with the words on stdin (OUT.chats
//     holds each call's argv, and the words must not be in it); the keyboard
//     path search → open → Continue; a rename on stdin; the filter chips;
//     Delete all cancelled (nothing goes), then confirmed (every chat goes).
//     `chats continue` and `chats new` are logged to OUT.writes, never sent.
//   names (M19): two chats that open alike, named apart by their agents;
//     summaries in the rows and under the open chat's title; a renamed
//     chat keeping its own name; `agent:sora after:3d` answered by the
//     search with the filters on stdin; a filter it cannot read said under
//     the box; the Names and summaries switch writing off and back.
//   grep PREVIEW /tmp/c.log; cat /tmp/c.writes /tmp/c.chats
import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    readonly property string want: Quickshell.env("PREVIEW_ARG") || "list"
    readonly property string dataDir: Quickshell.env("PREVIEW_DATA") || "/nonexistent"
    Component.onCompleted: overlay.open('{"page":"chats"}')

    TestEvent { id: input }
    property var keys: null
    // Inside an Item of the overlay's window, so key events find it.
    function keyEvents() {
      if (!overlay.keys) overlay.keys = Qt.createQmlObject("import QtTest; TestEvent {}", overlay.pageScroll.contentItem)
      return overlay.keys
    }
    function key(k) { keyEvents().keyClick(k, Qt.NoModifier, -1) }
    function type(text) {
      for (var i = 0; i < text.length; i++) keyEvents().keyClick(text.toUpperCase().charCodeAt(i), Qt.NoModifier, -1)
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
    function findAll(item, test, out) {
      out = out || []
      if (!item || item.visible === false || item.opacity === 0) return out
      if (test(item)) out.push(item)
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) findAll(kids[i], test, out)
      return out
    }
    function pageRoot() { return overlay.pageScroll ? overlay.pageScroll.contentItem : null }
    function browser() { return find(pageRoot(), function(i) { return i.followSummon !== undefined && i.scope !== undefined }) }
    function button(text) {
      return find(pageRoot(), function(i) { return i.clicked !== undefined && i.text === text })
    }
    function buttonStarting(prefix) {
      return find(pageRoot(), function(i) { return i.clicked !== undefined && typeof i.text === "string" && i.text.indexOf(prefix) === 0 })
    }
    function textItem(sub) {
      return find(pageRoot(), function(i) { return i.textFormat !== undefined && typeof i.text === "string" && i.text.indexOf(sub) >= 0 && i.font !== undefined && i.selectByMouse === undefined })
    }
    function click(item, label) {
      if (!item) { console.warn("PREVIEW FAIL miss " + label); overlay.failed++; return }
      console.warn("PREVIEW click " + label)
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    property int failed: 0
    property int passed: 0
    function check(ok, what) {
      console.warn("PREVIEW " + (ok ? "PASS " : "FAIL ") + what)
      if (ok) passed++; else failed++
    }

    // The files, as the run goes on.
    property var index: ({ chats: [] })
    FileView {
      id: indexFile
      path: overlay.dataDir + "/chats/index.json"
      printErrors: false
      blockLoading: true
      onLoaded: { try { overlay.index = JSON.parse(text()) } catch (e) {} }
      onLoadFailed: overlay.index = ({ chats: [] })
    }
    property string argvLog: ""
    FileView {
      id: chatsLog
      path: (Quickshell.env("PREVIEW_WRITES") || "/nonexistent").replace(/\.writes$/, ".chats")
      printErrors: false
      blockLoading: true
      onLoaded: overlay.argvLog = text()
    }
    property string writesLog: ""
    FileView {
      id: writesFile
      path: Quickshell.env("PREVIEW_WRITES") || "/nonexistent"
      printErrors: false
      blockLoading: true
      onLoaded: overlay.writesLog = text()
    }
    function reread() { indexFile.reload(); chatsLog.reload(); writesFile.reload() }
    function chatTitled(sub) {
      var list = overlay.index.chats || []
      for (var i = 0; i < list.length; i++) if (String(list[i].title).indexOf(sub) >= 0) return list[i]
      return null
    }

    property var steps: {
      // Phase M19: written names and summaries, the switch, and filters.
      if (want === "names") return [
        function() { overlay.put("saveChats", true); overlay.reread() },
        function() {
          var b = overlay.browser()
          overlay.check(b !== null && b.chatRowCount === 9, "nine synthetic chats listed (" + (b ? b.chatRowCount : "") + ")")
          overlay.check(overlay.textItem("Yellowing tomato leaves") !== null && overlay.textItem("Laptop battery drain in suspend") !== null,
                        "two chats that open alike show different written names")
          overlay.check(overlay.textItem("Likely overwatering") !== null, "a row shows its summary instead of the last line")
          overlay.check(overlay.textItem("Release checklist") !== null && overlay.textItem("Twelve-step") === null,
                        "a renamed chat keeps its own name over the written one")
          overlay.check(overlay.textItem("Hey, can you help me") === null, "no row is titled with the shared first words")
          var g = overlay.chatTitled("synthetic garden")
          if (g) overlay.showChat(g.id)
        },
        function() {
          overlay.check(overlay.textItem("named by Theo") !== null, "the open chat says its name was written by its agent")
          overlay.check(overlay.textItem("Sora took over the watering plan") !== null, "and shows the summary under it")
          var field = overlay.find(overlay.pageRoot(), function(i) { return String(i.placeholderText).indexOf("Search chats") === 0 })
          overlay.check(field !== null && String(field.placeholderText).indexOf("agent:") >= 0, "the search box hints at its filters")
          if (field) field.forceActiveFocus()
          overlay.type("agent:sora after:3d")
          overlay.key(Qt.Key_Return)
        },
        function() { overlay.reread() },
        function() {
          var b = overlay.browser()
          var titles = b ? b.rows.filter(function(r) { return r.chat !== undefined }).map(function(r) { return String(r.chat.title) }) : []
          overlay.check(b !== null && b.results !== null, "the filters were answered by `chats search`")
          overlay.check(titles.indexOf("Laptop battery drain in suspend") >= 0 && titles.indexOf("Yellowing tomato leaves") < 0,
                        "agent:sora keeps Sora's chats and drops Theo's (" + titles.join(" | ") + ")")
          overlay.check(titles.indexOf("The synthetic garden: shady and sunny beds") >= 0
                        && titles.indexOf("Translate “good morning” into Japanese and Greek 🌅") < 0,
                        "after:3d keeps today's and drops Sora's five-day-old chat")
          overlay.check(overlay.argvLog.indexOf("agent:sora") < 0, "the filters are not in any argv")
          var field = overlay.find(overlay.pageRoot(), function(i) { return String(i.placeholderText).indexOf("Search chats") === 0 })
          if (field) { field.forceActiveFocus(); overlay.key(Qt.Key_Escape); overlay.type("garden before:someday"); overlay.key(Qt.Key_Return) }
        },
        function() {},
        function() {
          overlay.check(overlay.textItem("Left out: before:") !== null, "a filter it cannot read is said, not swallowed")
          var card = overlay.find(overlay.pageRoot(), function(i) { return i.foldable === true && i.title === "Saving and privacy" })
          if (card && !card.expanded) card.flip()
        },
        function() {
          var row = overlay.find(overlay.pageRoot(), function(i) { return i.label === "Names and summaries" })
          overlay.check(row !== null && row.visible, "the switch is on the Chats page, with saving on")
          overlay.check(overlay.textItem("at most ten an hour") !== null, "beside it, the cost and the limit")
          overlay.click(overlay.button("Off"), "Names and summaries: Off")
        },
        function() {
          overlay.check(overlay.setting("chatSummaries", "owner") === "off", "Off writes chatSummaries off")
          overlay.click(overlay.button("By the chat's agent"), "Names and summaries: back on")
        },
        function() {
          overlay.check(overlay.setting("chatSummaries", "off") === "owner", "and back to owner")
          console.warn("PREVIEW done: " + overlay.passed + " passed, " + overlay.failed + " failed")
        }
      ]
      if (want === "drive") return [
        function() { overlay.put("saveChats", true); overlay.reread() },
        function() {
          overlay.check(overlay.pages.length === 11, "eleven pages in the sidebar")
          overlay.check(overlay.pages[overlay.pageForKey(Qt.Key_6)].id === "chats", "Ctrl+6 is Chats")
          overlay.check(overlay.pages[overlay.pageForKey(Qt.Key_0)].id === "other", "Ctrl+0 is the tenth page, Other settings")
          // The old id, kept as an alias (M26).
          overlay.goTo("display", "")
          overlay.check(overlay.page === "other", "the old display link opens Other settings")
          overlay.check(overlay.pages[overlay.pageForKey(Qt.Key_PageDown)].id === "about", "Ctrl+PgDn from Other settings reaches About")
          overlay.check(overlay.button("Conversation") === null, "no Conversation button on the top row")
          overlay.goTo("chats", "")
        },
        function() {
          var b = overlay.browser()
          overlay.check(b !== null && b.chatRowCount === 7, "seven synthetic chats listed (" + (b ? b.chatRowCount : "no browser") + ")")
          var t = overlay.textItem("<b>bold?</b>")
          overlay.check(t !== null && t.textFormat === Text.PlainText, "an HTML-looking title is drawn as plain text")
          overlay.check(overlay.textItem("Hazel") !== null, "a renamed agent's chat shows its current name")
          overlay.check(overlay.textItem("Scout") !== null, "a removed agent's chat shows the name it was saved under")
          // The search box, from the keyboard.
          var field = overlay.find(overlay.pageRoot(), function(i) { return String(i.placeholderText).indexOf("Search chats") === 0 })
          if (field) field.forceActiveFocus()
          overlay.check(field !== null && field.activeFocus, "the search box takes the focus")
          overlay.type("WATERING")
          overlay.key(Qt.Key_Return)
        },
        function() {
          overlay.reread()
          var b = overlay.browser()
          overlay.check(b !== null && b.results !== null, "the search was answered by `chats search`")
          var first = b ? b.rows.filter(function(r) { return r.chat !== undefined })[0] : null
          overlay.check(first && String(first.chat.title).indexOf("synthetic garden") >= 0, "the best match is the garden chat")
        },
        function() {
          overlay.reread()
          overlay.check(overlay.argvLog.indexOf("search --json") >= 0, "the page ran `chats search --json`")
          overlay.check(overlay.argvLog.toLowerCase().indexOf("watering") < 0, "the words are not in any argv")
          // Down to the first result with Tab, open it with Enter.
          var rowCell = overlay.find(overlay.pageRoot(), function(i) { return i.activeFocusOnTab === true && i.border !== undefined && i.radius !== undefined && i.width > 100 && i.parent && i.parent.modelData !== undefined && i.parent.modelData.chat !== undefined })
          if (rowCell) rowCell.forceActiveFocus()
          overlay.key(Qt.Key_Return)
        },
        function() {
          var b = overlay.browser()
          overlay.check(b !== null && b.savedChatOpen && String(b.chat.title).indexOf("garden") >= 0, "Enter on a result opens it")
          var bubbles = overlay.findAll(overlay.pageRoot(), function(i) { return i.mine !== undefined && i.stripe !== undefined })
          var mine = bubbles.filter(function(x) { return x.mine })
          var theirs = bubbles.filter(function(x) { return !x.mine })
          overlay.check(mine.length >= 3 && theirs.length >= 3, "your lines and the agents' in separate bubbles (" + mine.length + " / " + theirs.length + ")")
          var sora = theirs.filter(function(x) { return x.who.indexOf("Sora") === 0 })[0]
          var theo = theirs.filter(function(x) { return x.who === "Theo" })[0]
          overlay.check(sora && theo && String(sora.stripe) !== String(theo.stripe), "Sora's replies and Theo's in different colours")
          overlay.check(overlay.textItem("Sora asked Hazel") !== null, "a question between agents folded to one line")
          var cont = overlay.button("Continue")
          if (cont) cont.forceActiveFocus()
          overlay.key(Qt.Key_Space)
        },
        function() { overlay.reread() },
        function() {
          overlay.check(/agentvoice chats continue [0-9a-f]{16}\n/.test(overlay.writesLog), "Space on Continue runs `chats continue ID` (logged, not sent)")
          overlay.click(overlay.button("Rename"), "Rename")
        },
        function() {
          var f = overlay.find(overlay.pageRoot(), function(i) { return i.begin !== undefined && i.activeFocus })
          overlay.check(f !== null, "Rename opens a focused field")
          if (f) { f.selectAll(); overlay.type("GARDEN PLAN"); overlay.key(Qt.Key_Return) }
        },
        function() {
          overlay.reread()
        },
        function() {
          overlay.check(overlay.chatTitled("garden plan") !== null, "the rename landed in the chat")
          overlay.check(overlay.argvLog.toLowerCase().indexOf("garden plan") < 0, "the new title was not in argv")
          // The chips: Hazel's chats only, then all again.
          var field = overlay.find(overlay.pageRoot(), function(i) { return String(i.placeholderText).indexOf("Search chats") === 0 })
          if (field) { field.forceActiveFocus(); overlay.key(Qt.Key_Escape) }
        },
        function() {
          overlay.click(overlay.button("Hazel"), "the Hazel chip")
        },
        function() {
          var b = overlay.browser()
          // One: she spoke in the forecast chat; being asked a question in the
          // garden chat (an aside) does not make her one of its speakers.
          overlay.check(b && b.agentFilter === "hazel" && b.chatRowCount === 1, "the Hazel chip keeps the chat she spoke in (" + (b ? b.chatRowCount : "") + ")")
          overlay.click(overlay.button("Hazel"), "the Hazel chip again")
        },
        function() {
          var b = overlay.browser()
          overlay.check(b && b.agentFilter === "all" && b.chatRowCount === 7, "a second click shows every chat again")
          // The card is folded once there are chats: open it from the keyboard.
          var card = overlay.find(overlay.pageRoot(), function(i) { return i.foldable === true && i.title === "Saving and privacy" })
          overlay.check(card !== null && card.expanded === false, "the settings card starts folded when chats are saved")
          if (card) card.flip()
        },
        function() {
          var t = overlay.find(overlay.pageRoot(), function(i) { return i.label === "Save conversations" })
          overlay.check(t !== null, "opened, it shows Save conversations")
          overlay.click(overlay.buttonStarting("⚠ Delete all saved chats"), "Delete all: arm")
        },
        function() {
          overlay.check(overlay.buttonStarting("Delete all") !== null && overlay.textItem("Delete all 7 saved chats") !== null,
                        "the confirm states the count and the scope")
          overlay.key(Qt.Key_Return)   // Cancel has the focus: Enter cancels
        },
        function() {
          overlay.reread()
        },
        function() {
          overlay.check((overlay.index.chats || []).length === 7, "a cancelled Delete all deletes nothing")
          overlay.check(overlay.argvLog.indexOf("delete --all") < 0, "and runs nothing")
          overlay.click(overlay.buttonStarting("⚠ Delete all saved chats"), "Delete all: arm again")
        },
        function() { overlay.click(overlay.button("Delete all"), "Delete all: confirm") },
        function() { overlay.reread() },
        function() {
          overlay.check((overlay.index.chats || []).length === 0 && overlay.index.purged > 0, "a confirmed Delete all leaves no chat")
          overlay.check(overlay.textItem("saved chats deleted") !== null, "and says how many went")
        },
        function() { console.warn("PREVIEW done: " + overlay.passed + " passed, " + overlay.failed + " failed") }
      ]
      return [
        function() { overlay.put("saveChats", want !== "empty"); overlay.reread() },
        function() {
          var c = want === "html" ? overlay.chatTitled("bold?") : overlay.chatTitled("synthetic garden")
          if (want === "details") overlay.goTo("agentdetails", "sora", "chats")
          else if (want === "communal") overlay.goTo("communal", "", "chats")
          else if (want === "session") overlay.goTo("chats", "")
          else if (c) overlay.showChat(c.id)
          console.warn("PREVIEW showing " + want + " on page " + overlay.page)
        }
      ]
    }
    property int step: 0
    Timer {
      interval: 900
      repeat: true
      running: true
      onTriggered: {
        if (overlay.step >= 2 && overlay.step - 2 < overlay.steps.length) overlay.steps[overlay.step - 2]()
        overlay.step++
      }
    }
  }
}
