// Every building block in ui/, wired to a real SettingsStore (reading the
// real shell.json; its writes go to preview.sh's stub). For screenshots in
// each theme and at each width:
//
//   preview.sh --size 960x760 --shots 6 gallery              wide, dark
//   preview.sh --size 560x760 --shots 9 --arg narrow gallery one column
//   preview.sh --theme flexoki-light --shots 6 gallery        light
//   preview.sh --arg narrow,long --shots 9 gallery            long labels
//
// Two scripted runs log what happened (PREVIEW lines in <out>.log) instead of
// relying on a screenshot to show it:
//
//   --arg danger   drives the DangerButton with synthetic clicks and keys:
//                  armed → cancelled, armed → confirmed, armed → Escape,
//                  armed → left alone past its 6 s
//   --arg keys     walks the pieces with Tab and presses their keys
//   --arg armed    arms the DangerButton and leaves it armed, for a shot
//
// Neither moves the real pointer or takes the keyboard (TestEvent sends
// events to this window only, and preview.sh turns Exclusive focus off).
import QtQuick
import QtTest
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "plugin"
import "plugin/ui"

ShellRoot {
  Backdrop { }

  PanelWindow {
    id: win
    color: "transparent"
    WlrLayershell.namespace: "agentvoice-preview-gallery"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }

    readonly property string arg: Quickshell.env("PREVIEW_ARG") || ""
    readonly property bool narrow: arg.indexOf("narrow") >= 0
    readonly property bool long: arg.indexOf("long") >= 0
    readonly property color fg: Commons.Color.menu.text
    readonly property color urgent: Commons.Color.urgent
    readonly property string font: Style.font.menuFamily
    function lbl(short, longer) { return win.long ? longer : short }

    SettingsStore {
      id: store
      defaults: ({ hud: true, leadInMs: 5000, chimes: true, livePartials: "auto" })
      onSaved: function(k) { console.warn("PREVIEW saved", k) }
      onFailed: function(k, m) { console.warn("PREVIEW failed", k, m) }
    }

    property real level: -60
    Timer {
      interval: 120; running: true; repeat: true
      onTriggered: win.level = -55 + 30 * Math.abs(Math.sin(Date.now() / 700))
    }

    // What the pieces emitted, shown on the page and logged.
    property string lastEvent: "—"
    function note(what) { lastEvent = what; console.warn("PREVIEW event " + what) }

    // Lanes for the drag pieces: which skill is where.
    property var lanes: [{ id: "theo", label: "Theo" }, { id: "sora", label: "Sora" },
                         { id: "communal", label: "Communal", reason: "Reaches every agent" },
                         { id: "hazel", label: "Hazel", disabledReason: "Quarantined: nothing moves in" }]
    property var placed: ({ summarise: "theo", "release-notes": "theo", "read-logs": "sora" })
    property var lastMove: null
    function move(name, to, copy) {
      if (to === "hazel") { note("refused " + name + " → hazel"); return }
      var from = placed[name]
      var next = {}
      for (var k in placed) next[k] = placed[k]
      if (copy) next[name + " (copy)"] = to
      else next[name] = to
      lastMove = { name: name, from: from, to: to, copy: copy }
      placed = next
      note((copy ? "copied " : "moved ") + name + " " + from + " → " + to)
      undoToast.show((copy ? "Copied " : "Moved ") + name + " to " + to + ".")
    }
    function undoMove() {
      var m = lastMove
      if (!m) return
      var next = {}
      for (var k in placed) next[k] = placed[k]
      if (m.copy) delete next[m.name + " (copy)"]
      else next[m.name] = m.from
      placed = next
      lastMove = null
      note("undid " + m.name)
    }
    function skillsIn(lane) {
      var out = []
      for (var k in placed) if (placed[k] === lane) out.push(k)
      return out.sort()
    }

    property var chipStates: ({ desktop: "on", browser: "inherit", skill: "off" })
    property int dangerArmMs: 6000
    property var tabsCurrent: "main"
    property var filters: ["mine"]

    BorderSurface {
      id: box
      anchors.centerIn: parent
      width: Math.min(Style.space(win.narrow ? 520 : 920), parent.width - 20)
      height: Math.min(Style.space(740), parent.height - 20)
      radius: Style.cornerRadius
      color: Commons.Color.menu.background
      borderSpec: Border.surfaceSpec("menu", "border", Commons.Color.menu.border, Math.max(1, Style.space(2)))

      Flickable {
        id: flick
        anchors.fill: parent
        anchors.margins: Style.spacing.panelPadding
        contentHeight: col.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
          id: col
          width: flick.width
          spacing: Style.space(16)

          Text {
            width: parent.width
            text: "ui/ gallery · " + (win.narrow ? "narrow" : "wide") + (win.long ? " · long labels" : "") +
                  "   last event: " + win.lastEvent
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: win.fg
            font.family: win.font
            font.pixelSize: Style.font.caption
          }

          // --- AgentTabs, HeaderStrip, Pill ------------------------------------
          AgentTabs {
            id: tabs
            width: parent.width
            current: win.tabsCurrent
            agents: [
              { id: "main", label: win.lbl("Theo", "Theo the extremely thorough reviewer"), tone: "active" },
              { id: "sora", label: "Sora", tone: "busy" }, { id: "hazel", label: "Hazel", tone: "alert" },
              { id: "a4", label: "Quill" }, { id: "a5", label: "Juniper" }, { id: "a6", label: "Basil" },
              { id: "a7", label: "Marlowe" }, { id: "a8", label: "Pip" }, { id: "a9", label: "Odessa" }
            ]
            foreground: win.fg; fontFamily: win.font
            onPicked: function(id) { win.tabsCurrent = id; win.note("tab " + id) }
          }

          HeaderStrip {
            id: header
            width: parent.width
            name: win.lbl("Theo", "Theo, who reviews every pull request twice")
            status: "listening"
            tone: "active"
            expanded: true
            pills: [{ text: win.lbl("quarantined", "quarantined since this morning"), tone: "alert",
                      tooltip: "No outgoing calls; answers are marked as outside content." },
                    { text: "edits", tone: "busy" }, { text: "claude" }, { text: "opus · high" }]
            foreground: win.fg; fontFamily: win.font
            onToggled: function(open) { win.note("header " + (open ? "open" : "shut")) }

            Row {
              spacing: Style.space(8)
              ModelPicker {
                id: modelPicker
                models: ["opus", "sonnet", { value: "haiku", label: "haiku", detail: "Fast, for short turns" }]
                model: "opus"
                efforts: ["low", "medium", "high", "xhigh", "max"]
                effort: "high"
                foreground: win.fg; fontFamily: win.font
                onModelCommitted: function(v) { model = v; win.note("model " + v) }
                onEffortCommitted: function(v) { effort = v; win.note("effort " + v) }
              }
              ModelPicker {
                models: ["gemini-2.5-pro"]
                model: "gemini-2.5-pro"
                effortReason: "Gemini's CLI has no effort setting."
                foreground: win.fg; fontFamily: win.font
              }
            }
            Hint {
              width: parent.width
              text: win.lbl("Runs without asking at Trusted.",
                          "Runs every tool without asking at Trusted, including the ones it found by itself in your MCP settings.")
              detail: "Below Trusted the hook asks for each MCP tool call. The orders guard still asks about writes to the agents' folders."
              tone: "warn"
              foreground: win.fg; fontFamily: win.font
            }
          }

          // --- Card, CardGrid, ToggleChips, CompactSelector, AdvancedSection ---
          CardGrid {
            width: parent.width
            Card {
              title: win.lbl("Tools", "Tools this agent may use when it is working on its own")
              subtitle: "Inherit follows Communal → Tools."
              foreground: win.fg; fontFamily: win.font
              ToggleChips {
                id: chips
                width: parent.width
                allowInherit: true
                chipStates: win.chipStates
                inherited: ({ browser: true, skill: false })
                options: [
                  { value: "desktop", label: "Desktop", tooltip: "Windows, clipboard, notifications" },
                  { value: "browser", label: win.lbl("Browser", "Browser automation with a real profile") },
                  { value: "skill", label: "Omarchy skill" },
                  { value: "mcp", label: "github (MCP)", disabledReason: "Found in ~/.claude.json; approve it on the Communal page first." }
                ]
                foreground: win.fg; fontFamily: win.font
                onToggled: function(v, st) {
                  var next = {}
                  for (var k in win.chipStates) next[k] = win.chipStates[k]
                  next[v] = st
                  win.chipStates = next
                  win.note("chip " + v + " → " + st)
                }
              }
            }
            Card {
              title: "Reading"
              subtitle: win.lbl("How it speaks.", "How it speaks, and how much it says while it is still working.")
              foldable: true
              foreground: win.fg; fontFamily: win.font
              onToggled: function(open) { win.note("card " + (open ? "open" : "shut")) }
              Row {
                spacing: Style.space(8)
                CompactSelector {
                  id: compact
                  label: "Talk"
                  value: "brief"
                  options: [{ value: "off", label: "Off" }, { value: "brief", label: "Brief" },
                            { value: "detailed", label: "Detailed", detail: "Reads tool names as it goes" }]
                  foreground: win.fg; fontFamily: win.font
                  onCommitted: function(v) { value = v; win.note("talk " + v) }
                }
                CompactSelector {
                  label: "Voice"
                  value: "lessac"
                  options: ["lessac"]
                  disabledReason: "Only one voice is installed. Add more on the Voice page."
                  foreground: win.fg; fontFamily: win.font
                }
              }
              AdvancedSection {
                id: advanced
                width: parent.width
                summary: "timeouts, extra flags"
                foreground: win.fg; fontFamily: win.font
                onToggled: function(open) { win.note("advanced " + (open ? "open" : "shut")) }
                SettingRow {
                  width: parent.width
                  label: "Idle timeout"
                  hint: "A turn silent this long is stopped."
                  foreground: win.fg; fontFamily: win.font
                  Text { text: "90 s"; color: win.fg; font.family: win.font }
                }
                SettingRow {
                  width: parent.width
                  label: "Resume the last session"
                  foreground: win.fg; fontFamily: win.font
                  ToggleSwitch { checked: true; foreground: win.fg }
                }
              }
            }
          }

          // --- DangerButton -----------------------------------------------------
          Card {
            width: parent.width
            title: "DangerButton"
            subtitle: "First click arms; Cancel has the focus; 6 s or Escape disarms."
            foreground: win.fg; fontFamily: win.font
            Flow {
              width: parent.width
              spacing: Style.space(12)
              DangerButton {
                id: danger
                armMs: win.dangerArmMs
                text: "Reset"
                question: win.lbl("Really reset Theo?", "Really reset Theo the extremely thorough reviewer?")
                confirmText: "Reset"
                foreground: win.fg; urgent: win.urgent; fontFamily: win.font
                onConfirmed: win.note("danger confirmed")
                onCancelled: win.note("danger cancelled")
              }
              DangerButton {
                text: "Delete"
                question: "Really delete this chat?"
                confirmText: "Delete"
                enabled: false
                tooltipText: "Nothing to delete"
                foreground: win.fg; urgent: win.urgent; fontFamily: win.font
              }
            }
          }

          // --- StageBlock -------------------------------------------------------
          Card {
            width: parent.width
            title: "Listening, as stages"
            foreground: win.fg; fontFamily: win.font
            Column {
              width: parent.width
              StageBlock { width: parent.width; number: 1; title: "Sound in"; summary: "Built-in mic"; tone: "active"; foreground: win.fg; fontFamily: win.font
                LevelMeter { width: parent.width; levelDb: win.level; gateDb: -38; foreground: win.fg } }
              StageBlock { width: parent.width; number: 2; title: "Gate"; summary: win.lbl("-38 dB, adapting", "-38 dB, adapting to the room as it gets louder or quieter"); tone: "active"; foreground: win.fg; fontFamily: win.font }
              StageBlock { width: parent.width; number: 3; title: "Wake word"; summary: "sherpa-onnx"; tone: "busy"; foreground: win.fg; fontFamily: win.font }
              StageBlock { width: parent.width; number: 4; title: "Second check"; summary: "Not installed"; tone: "alert"; last: true; foreground: win.fg; fontFamily: win.font
                Hint { width: parent.width; text: "Needs openWakeWord."; detail: "About 154MB, from the About page."; foreground: win.fg; fontFamily: win.font } }
            }
          }

          // --- StatTile, MiniBars ----------------------------------------------
          Flow {
            width: parent.width
            spacing: Style.space(10)
            StatTile { value: "142"; label: "turns today"; caption: "↑ 12 on yesterday"; foreground: win.fg; fontFamily: win.font }
            StatTile { value: "1.6 s"; label: "first word"; caption: "median, last 50"; tooltip: "From the end of your sentence to the first spoken word."; foreground: win.fg; fontFamily: win.font }
            StatTile { value: "3"; label: "false wakes"; caption: win.lbl("this week", "this week, all at night with the TV on"); tone: "alert"; foreground: win.fg; fontFamily: win.font }
            StatTile { value: "—"; label: "background jobs"; caption: "nothing measured yet"; tone: "idle"; foreground: win.fg; fontFamily: win.font }
          }
          MiniBars {
            id: bars
            width: parent.width
            unit: "turns"
            highlight: 14
            values: [0, 0, 0, 0, 0, 0, 1, 4, 9, 12, 8, 6, 3, 7, 11, 5, 2, 0, 0, 3, 6, 2, 0, 0]
            foreground: win.fg; fontFamily: win.font
          }
          MiniBars { width: parent.width; values: [0, 0, 0, 0]; labels: ["Mon", "Tue", "Wed", "Thu"]; foreground: win.fg; fontFamily: win.font }

          // --- DraggableCard, DropLane, UndoToast -------------------------------
          Grid {
            width: parent.width
            columns: win.narrow ? 1 : 3
            columnSpacing: Style.space(10)
            rowSpacing: Style.space(10)
            Repeater {
              model: ["theo", "sora", "hazel"]
              DropLane {
                id: lane
                required property string modelData
                width: win.narrow ? parent.width : (parent.width - 2 * parent.columnSpacing) / 3
                laneId: modelData
                title: modelData === "theo" ? "Theo" : modelData === "sora" ? "Sora" : "Hazel"
                subtitle: modelData === "hazel" ? "Quarantined" : ""
                count: win.skillsIn(modelData).length
                refuse: function(p, copy, from) { return lane.laneId === "hazel" ? "Hazel is quarantined: nothing moves in." : "" }
                foreground: win.fg; urgent: win.urgent; fontFamily: win.font
                onReceived: function(p, copy, from) { win.move(String(p.name), lane.laneId, copy) }
                Repeater {
                  model: win.skillsIn(lane.laneId)
                  DraggableCard {
                    required property string modelData
                    width: lane.width - Style.space(20)
                    title: modelData
                    subtitle: win.lbl("skill", "a skill that summarises long threads into three lines")
                    badge: modelData === "summarise" ? "communal" : ""
                    laneId: lane.laneId
                    payload: ({ name: modelData })
                    lanes: win.lanes
                    foreground: win.fg; fontFamily: win.font
                    onMoveRequested: function(to, copy) { win.move(modelData, to, copy) }
                  }
                }
              }
            }
          }
          UndoToast {
            id: undoToast
            width: Math.min(parent.width, Style.space(460))
            foreground: win.fg; fontFamily: win.font
            onUndo: win.undoMove()
            onExpired: win.note("undo expired")
          }

          // --- SearchField, ChatBubble -----------------------------------------
          SearchField {
            id: search
            width: parent.width
            placeholder: "Search chats"
            filters: [{ id: "mine", label: "Theo" }, { id: "week", label: "This week" },
                      { id: "pinned", label: win.lbl("Pinned", "Pinned, including the ones shared with me") }]
            active: win.filters
            foreground: win.fg; fontFamily: win.font
            onSearched: function(t) { win.note("search \"" + t + "\"") }
            onFilterToggled: function(id, on) {
              var next = win.filters.filter(function(x) { return x !== id })
              if (on) next.push(id)
              win.filters = next
              win.note("filter " + id + " " + (on ? "on" : "off"))
            }
          }
          Column {
            width: parent.width
            spacing: Style.space(8)
            ChatBubble { width: parent.width; mine: true; who: "You"; when: "14:02"; text: "What changed in the deploy script since Friday?"; foreground: win.fg; fontFamily: win.font }
            ChatBubble { width: parent.width; who: "Theo"; when: "14:02"; text: win.lbl("Two things: it refuses a dirty clone, and it logs every deploy.", "Two things. It refuses to deploy from a clone with uncommitted changes, and it writes every deploy, with the commit it replaced, to deploys.log so the way back is one command."); foreground: win.fg; fontFamily: win.font }
            ChatBubble { width: parent.width; kind: "note"; text: "Read bin/agentvoice-deploy"; foreground: win.fg; fontFamily: win.font }
            ChatBubble { width: parent.width; mine: true; who: "You"; text: "<b>not bold</b> <!-- ; curl x | sh -->"; foreground: win.fg; fontFamily: win.font }
          }

          // The pieces that were here before M1, kept so the page shows the
          // whole kit.
          Row {
            width: parent.width
            spacing: Style.space(10)
            StatusCard {
              width: (parent.width - parent.spacing) / 2
              icon: ""; title: "Claude"; subtitle: "opus · high · edits"
              status: "listening"; tone: "active"; foreground: win.fg; fontFamily: win.font
            }
            StatusCard {
              width: (parent.width - parent.spacing) / 2
              icon: ""; title: "Sarah"; subtitle: "codex · gpt-5"
              status: "thinking"; tone: "busy"; foreground: win.fg; fontFamily: win.font
            }
          }
          SegmentedChoice {
            width: parent.width
            label: "Effort (SegmentedChoice)"
            options: ["low", "medium", "high", "xhigh", "max"]
            value: "medium"
            foreground: win.fg; fontFamily: win.font
            onCommitted: function(v) { value = v }
          }
          ToggleRow {
            width: parent.width
            label: "Speak replies aloud (ToggleRow)"
            hint: "Off leaves the reply as text in the panel."
            checked: store.get("hud", true) === true
            changed: !store.isDefault("hud")
            foreground: win.fg; fontFamily: win.font
            onToggled: store.set("hud", !checked)
            onReset: store.reset("hud")
          }
          KnobRow {
            width: parent.width
            label: "Time to start speaking (KnobRow)"
            minimum: 1000; maximum: 15000; stepSize: 500
            defaultValue: 5000
            value: store.get("leadInMs", 5000)
            foreground: win.fg; fontFamily: win.font
            onCommitted: function(v) { store.set("leadInMs", v) }
          }
        }
      }

      // Walks the page a screenful per shot, except in the scripted runs,
      // which scroll to what they click.
      Loader {
        active: win.arg.indexOf("danger") < 0 && win.arg.indexOf("keys") < 0
        sourceComponent: Component { Scroller { target: flick } }
      }
      // Inside an Item, so its key events find this window.
      TestEvent { id: input }
    }

    // --- scripted runs ---------------------------------------------------------
    function click(item, label) {
      if (!item) { console.warn("PREVIEW miss " + label); return }
      var y = item.mapToItem(col, 0, 0).y
      flick.contentY = Math.max(0, Math.min(y - 120, flick.contentHeight - flick.height))
      console.warn("PREVIEW click " + label)
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function key(k, label) {
      console.warn("PREVIEW key " + label + " (focus: " + (win.contentItem.Window.activeFocusItem
                   ? String(win.contentItem.Window.activeFocusItem).split("(")[0] : "none") + ")")
      input.keyClick(k, Qt.NoModifier, -1)
    }
    function find(node, test) {
      if (!node) return null
      if (node.visible !== false && test(node)) return node
      var kids = node.children || []
      for (var i = 0; i < kids.length; i++) { var hit = find(kids[i], test); if (hit) return hit }
      return null
    }
    function dangerButton(text) {
      return find(danger, function(i) { return i.text === text && i.clicked !== undefined })
    }
    function state(label) {
      console.warn("PREVIEW state " + label + ": armed=" + danger.armed + " last=" + win.lastEvent)
    }

    // --arg armed: the DangerButton armed and left armed, for a screenshot
    // of the strip (with `long`, of its wrapping).
    Timer {
      interval: 300
      running: win.arg.indexOf("armed") >= 0
      onTriggered: { win.dangerArmMs = 600000; danger.arm() }
    }

    property int step: 0
    Timer {
      interval: 900
      repeat: true
      running: win.arg.indexOf("danger") >= 0
      onTriggered: {
        win.step++
        var s = win.step
        if (s === 2) win.click(win.dangerButton("⚠ Reset"), "arm")
        else if (s === 3) { win.state("after arm"); win.click(win.dangerButton("Cancel"), "Cancel") }
        else if (s === 4) { win.state("after Cancel"); win.click(win.dangerButton("⚠ Reset"), "arm") }
        else if (s === 5) win.click(win.dangerButton("Reset"), "Reset (confirm)")
        else if (s === 6) { win.state("after confirm"); win.click(win.dangerButton("⚠ Reset"), "arm") }
        else if (s === 7) win.key(Qt.Key_Escape, "Escape")
        else if (s === 8) { win.state("after Escape"); win.click(win.dangerButton("⚠ Reset"), "arm, then wait 6 s") }
        else if (s === 9) win.key(Qt.Key_Return, "Enter while armed (Cancel has focus)")
        else if (s === 10) { win.state("after Enter"); win.click(win.dangerButton("⚠ Reset"), "arm, then wait 6 s") }
        else if (s === 18) win.state("after 6.3 s untouched")
        else if (s === 19) console.warn("PREVIEW done")
      }
    }

    // Tab until the focus is inside `target` (at most 40 presses), the way
    // somebody without a mouse reaches it.
    function within(item, target) {
      for (var i = item; i; i = i.parent) if (i === target) return true
      return false
    }
    function focused() { return win.contentItem.Window.activeFocusItem }
    function tabTo(target, label) {
      for (var n = 0; n < 40 && !win.within(win.focused(), target); n++) input.keyClick(Qt.Key_Tab, Qt.NoModifier, -1)
      var ok = win.within(win.focused(), target)
      console.warn("PREVIEW tab to " + label + ": " + (ok ? "reached in " + n : "NOT reached"))
      if (ok) {
        var y = target.mapToItem(col, 0, 0).y
        flick.contentY = Math.max(0, Math.min(y - 120, flick.contentHeight - flick.height))
      }
    }
    function firstCard() { return win.find(col, function(i) { return i.moveRequested !== undefined }) }
    function undoButton() { return win.find(undoToast, function(i) { return i.clicked !== undefined && String(i.text).indexOf("Undo") === 0 }) }

    property var walk: [
      function() { tabs.forceActiveFocus(); console.warn("PREVIEW start on the agent tabs") },
      function() { win.key(Qt.Key_Right, "Right (next tab)") },
      function() { win.key(Qt.Key_End, "End (last tab)") },
      function() { win.tabTo(header, "header strip") },
      function() { win.key(Qt.Key_Space, "Space (folds)") },
      function() { win.key(Qt.Key_Space, "Space (opens)") },
      function() { win.tabTo(modelPicker, "model picker") },
      function() { win.key(Qt.Key_Return, "Enter (model menu)") },
      function() { win.key(Qt.Key_Down, "Down") },
      function() { win.key(Qt.Key_Return, "Enter (picks)") },
      function() { win.tabTo(chips, "tool chips") },
      function() { win.key(Qt.Key_Space, "Space (Desktop chip)") },
      function() { win.key(Qt.Key_Right, "Right") },
      function() { win.key(Qt.Key_Right, "Right") },
      function() { win.key(Qt.Key_Right, "Right") },
      function() { win.key(Qt.Key_Space, "Space (disabled chip: says why)") },
      function() { console.warn("PREVIEW chips say: " + chips.why) },
      function() { win.tabTo(compact, "compact selector") },
      function() { win.key(Qt.Key_Space, "Space (opens)") },
      function() { win.key(Qt.Key_Down, "Down") },
      function() { win.key(Qt.Key_Return, "Enter (picks)") },
      function() { win.tabTo(advanced, "Advanced") },
      function() { win.key(Qt.Key_Return, "Enter (opens)") },
      function() { win.tabTo(danger, "danger button") },
      function() { win.key(Qt.Key_Return, "Enter (arms)") },
      function() { win.state("armed by keyboard") },
      function() { win.key(Qt.Key_Escape, "Escape (disarms)") },
      function() { win.state("after Escape") },
      function() { win.key(Qt.Key_Return, "Enter (arms again)") },
      function() { win.key(Qt.Key_Tab, "Tab (Cancel to Remove)") },
      function() { win.state("on its own Reset button") },
      function() { win.key(Qt.Key_Tab, "Tab (leaves the strip)") },
      function() { win.state("after tabbing away") },
      function() { win.tabTo(bars, "hour bars") },
      function() { win.key(Qt.Key_Left, "Left") },
      function() { win.key(Qt.Key_Left, "Left (readout under the bars)") },
      function() { console.warn("PREVIEW bars read: " + bars.readout(bars.cursor)) },
      function() { win.tabTo(win.firstCard(), "first skill card") },
      function() { win.key(Qt.Key_Return, "Enter (Move to… menu)") },
      function() { win.key(Qt.Key_Down, "Down") },
      function() { win.key(Qt.Key_Return, "Enter (moves)") },
      function() { win.tabTo(win.undoButton(), "Undo") },
      function() { win.key(Qt.Key_Return, "Enter (undo)") },
      function() { win.tabTo(search, "search") },
      function() { input.keyClick(Qt.Key_D, Qt.NoModifier, -1); input.keyClick(Qt.Key_E, Qt.NoModifier, -1); console.warn("PREVIEW typed de") },
      function() { },
      function() { win.key(Qt.Key_Escape, "Escape (clears)") },
      function() { console.warn("PREVIEW done; last event: " + win.lastEvent) }
    ]
    Timer {
      interval: 450
      repeat: true
      running: win.arg.indexOf("keys") >= 0
      property int n: 0
      onTriggered: {
        if (n < win.walk.length) win.walk[n]()
        n++
      }
    }
  }
}
