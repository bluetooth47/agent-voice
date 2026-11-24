import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// One tab per agent across the top of Agent details (feedback item 9),
// replacing the drop-down: every agent is one click away and you can see
// which one you are on.
//
// `agents`: [{ id, label, tone }] -- tone as StatusCard, drawn as a dot.
// One row, never wrapped: the main agent and eight more is nine tabs, and
// at nine (or whenever they no longer fit) the row scrolls sideways, with
// the chosen tab kept in view and a fade at an edge that has more beyond it.
//
// Keyboard: one Tab stop; Left/Right (or h/l) move and pick, the way the
// TabStrip does; Home/End jump to the ends.
FocusScope {
  id: tabs

  property var agents: []
  property string current: ""
  property int scrollAt: 9

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  readonly property bool scrolls: agents.length >= scrollAt || list.contentWidth > list.width + 1

  signal picked(string id)

  function indexOf(id) {
    for (var i = 0; i < agents.length; i++) if (String(agents[i].id) === id) return i
    return -1
  }
  function step(d) {
    if (agents.length === 0) return
    var i = Math.max(0, indexOf(current))
    i = Math.max(0, Math.min(agents.length - 1, i + d))
    picked(String(agents[i].id))
  }
  function toneColor(t) {
    return t === "alert" ? urgent : t === "busy" ? accent : t === "active" ? foreground : dim
  }

  activeFocusOnTab: true
  Accessible.role: Accessible.PageTabList
  Accessible.name: "Agents"
  Accessible.description: { var i = indexOf(current); return i >= 0 ? "Open: " + String(agents[i].label || agents[i].id) : "" }
  Accessible.focusable: true
  implicitHeight: list.height
  width: parent ? parent.width : 300

  Keys.onLeftPressed: step(-1)
  Keys.onRightPressed: step(1)
  Keys.onPressed: function(e) {
    if (e.key === Qt.Key_H) { step(-1); e.accepted = true }
    else if (e.key === Qt.Key_L) { step(1); e.accepted = true }
    else if (e.key === Qt.Key_Home && agents.length > 0) { picked(String(agents[0].id)); e.accepted = true }
    else if (e.key === Qt.Key_End && agents.length > 0) { picked(String(agents[agents.length - 1].id)); e.accepted = true }
  }

  function reveal() {
    Qt.callLater(function() {
      // The page may have been left (and this destroyed) in between: Settings
      // search opens an agent's tab and moves on within a frame (M28).
      if (!tabs || typeof tabs.indexOf !== "function") return
      var i = tabs.indexOf(tabs.current)
      if (i >= 0) list.positionViewAtIndex(i, ListView.Contain)
    })
  }
  // The chosen tab stays in view when it changes, when the list arrives or
  // is reordered, and when the row is resized.
  onCurrentChanged: reveal()
  onAgentsChanged: reveal()
  onWidthChanged: reveal()

  ListView {
    id: list
    width: parent.width
    height: Style.spacing.controlHeight + Style.space(6)
    orientation: ListView.Horizontal
    spacing: Style.space(4)
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    interactive: tabs.scrolls
    model: tabs.agents

    delegate: Button {
      id: tab
      required property var modelData
      required property int index
      readonly property bool chosen: String(modelData.id) === tabs.current
      anchors.verticalCenter: parent ? parent.verticalCenter : undefined
      text: String(modelData.label || modelData.id)
      // Room on the left for the state dot, drawn below in the agent's
      // tone (Button colours its own icon with the text colour).
      readonly property real dotSize: Style.space(7)
      readonly property real dotRoom: dotSize + Style.spacing.controlGap
      leftAlign: true
      leftPadding: horizontalPadding + dotRoom
      implicitWidth: label0.implicitWidth + horizontalPadding * 2 + dotRoom + Style.space(4)
      selected: chosen
      hasCursor: tabs.activeFocus && chosen
      bordered: true
      foreground: tabs.foreground
      accent: tabs.accent
      fontFamily: tabs.fontFamily
      tooltipText: String(modelData.tooltip || "")
      onClicked: { tabs.forceActiveFocus(); tabs.picked(String(modelData.id)) }
      // Measures the label as Button draws it (bold when chosen).
      Text {
        id: label0
        visible: false
        text: tab.text
        font.family: tabs.fontFamily
        font.pixelSize: Style.font.body
        font.bold: tab.chosen
      }
      Rectangle {
        x: tab.horizontalPadding + Style.space(2)
        anchors.verticalCenter: parent.verticalCenter
        width: tab.dotSize
        height: width
        radius: width / 2
        color: tabs.toneColor(String(tab.modelData.tone || "idle"))
      }
    }
  }

  // Fades at an edge with more tabs beyond it, so a scrolled row says so.
  Rectangle {
    visible: tabs.scrolls && !list.atXBeginning
    anchors.left: list.left
    width: Style.space(24)
    height: list.height
    gradient: Gradient {
      orientation: Gradient.Horizontal
      GradientStop { position: 0; color: Commons.Color.menu.background }
      GradientStop { position: 1; color: "transparent" }
    }
  }
  Rectangle {
    visible: tabs.scrolls && !list.atXEnd
    anchors.right: list.right
    width: Style.space(24)
    height: list.height
    gradient: Gradient {
      orientation: Gradient.Horizontal
      GradientStop { position: 0; color: "transparent" }
      GradientStop { position: 1; color: Commons.Color.menu.background }
    }
  }
}
