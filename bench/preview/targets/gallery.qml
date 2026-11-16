// Every building block in ui/, on one card, wired to a real SettingsStore
// (reading the real shell.json; its writes go to preview.sh's stub). For
// screenshots in each theme: preview.sh --size 900x720 gallery
import QtQuick
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

    readonly property color fg: Commons.Color.menu.text
    readonly property string font: Style.font.menuFamily

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

    BorderSurface {
      anchors.centerIn: parent
      width: Style.space(860)
      height: Math.min(Style.space(680), parent.height - 20)
      radius: Style.cornerRadius
      color: Commons.Color.menu.background
      borderSpec: Border.surfaceSpec("menu", "border", Commons.Color.menu.border, Math.max(1, Style.space(2)))

      Row {
        anchors.fill: parent
        anchors.margins: Style.spacing.panelPadding
        spacing: Style.space(20)

        SidebarNav {
          id: nav
          width: Style.space(150)
          foreground: win.fg
          fontFamily: win.font
          current: "agents"
          pages: [
            { id: "overview", label: "Overview", icon: "" },
            { id: "agents", label: "Agents", icon: "\u{f06a9}", badge: "!" },
            { id: "listening", label: "Listening", icon: "" },
            { id: "conversation", label: "Conversation", icon: "" },
            { id: "voice", label: "Voice & sound", icon: "" },
            { id: "display", label: "Display & privacy", icon: "" },
            { id: "about", label: "About", icon: "" }
          ]
          onPicked: function(id) { current = id }
        }

        Flickable {
          width: parent.width - nav.width - parent.spacing
          height: parent.height
          contentHeight: col.implicitHeight
          clip: true
          boundsBehavior: Flickable.StopAtBounds

          Column {
            id: col
            width: parent.width
            spacing: Style.space(14)

            LevelMeter {
              width: parent.width
              levelDb: win.level
              gateDb: -38
              foreground: win.fg
            }

            Row {
              width: parent.width
              spacing: Style.space(10)
              StatusCard {
                width: (parent.width - parent.spacing) / 2
                icon: ""; title: "Claude"; subtitle: "opus · high · edits"
                status: "listening"; tone: "active"; foreground: win.fg; fontFamily: win.font
              }
              StatusCard {
                width: (parent.width - parent.spacing) / 2
                icon: ""; title: "Sarah"; subtitle: "codex · gpt-5"
                status: "thinking"; tone: "busy"; foreground: win.fg; fontFamily: win.font
              }
            }

            AgentCard {
              width: parent.width
              name: "Sarah"; wakeName: "hey sarah"; summary: "codex · gpt-5 · medium · edits in ~/src/site"
              status: "listening"; tone: "active"; expanded: true
              foreground: win.fg; fontFamily: win.font

              SegmentedChoice {
                width: parent.width
                label: "Effort"
                options: ["low", "medium", "high", "xhigh", "max"]
                value: "medium"
                foreground: win.fg; fontFamily: win.font
                onCommitted: function(v) { value = v }
              }
              SettingRow {
                width: parent.width
                label: "Speak replies aloud"
                hint: "Off leaves the reply as text in the panel."
                help: "A long explanation lives here, folded away until asked for."
                changed: !store.isDefault("hud")
                foreground: win.fg; fontFamily: win.font
                onReset: store.reset("hud")
                ToggleSwitch {
                  checked: store.get("hud", true) === true
                  foreground: win.fg
                  onToggled: store.set("hud", !checked)
                }
              }
              SettingRow {
                width: parent.width
                label: "Only wake for my voice"
                disabledReason: "Needs openWakeWord; Vosk has no model to attach a verifier to."
                foreground: win.fg; fontFamily: win.font
                ToggleSwitch { checked: false; foreground: win.fg }
              }
            }

            AgentCard {
              width: parent.width
              name: "Claude"; summary: "claude · opus · high · asks first"
              isDefault: true; status: "idle"
              problem: "No project folder, so “edits” has nothing to be inside."
              foreground: win.fg; fontFamily: win.font
            }

            KnobRow {
              width: parent.width
              label: "Time to start speaking"
              minimum: 1000; maximum: 15000; stepSize: 500
              defaultValue: 5000
              value: store.get("leadInMs", 5000)
              foreground: win.fg; fontFamily: win.font
              onCommitted: function(v) { store.set("leadInMs", v) }
            }
            KnobRow {
              width: parent.width
              label: "Effort (as a slider, today)"
              minimum: 1; maximum: 5; stepSize: 1; unit: ""
              labels: ["low", "medium", "high", "xhigh", "max"]
              value: 3
              foreground: win.fg; fontFamily: win.font
            }
          }
        }
      }
    }
  }
}
