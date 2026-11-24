import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// The foldable header of one agent (feedback item 8): a state dot, the
// name, a row of pills, and a caret. Shut, the strip is the whole agent on
// one line; open, the caller's children appear underneath.
//
//   HeaderStrip {
//     width: parent.width
//     name: "Theo"; tone: "active"; status: "listening"
//     pills: [{ text: "claude" }, { text: "edits", tone: "busy" },
//             { text: "quarantined", tone: "alert", tooltip: "…" }]
//     SettingRow { ... }
//   }
//
// Keyboard: one Tab stop on the strip; Enter or Space folds it.
FocusScope {
  id: strip

  property string name: ""
  property string status: ""
  // "idle", "active", "busy", "alert", as StatusCard.
  property string tone: "idle"
  // [{ text, tone, tooltip }], most important first: the first sits next
  // to the caret and is the last to give way when the strip is narrow.
  property var pills: []
  property bool expanded: false
  property bool foldable: true
  property bool dimmed: false
  // Shown under the strip, folded or open: `problem` (urgent) when something
  // stops the agent working, `warning` (accent) for a risk that stops
  // nothing, as the Agents page's old AgentCard drew them.
  property string problem: ""
  property string warning: ""

  property color foreground: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent
  readonly property color dim: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.6)
  property string fontFamily: Style.font.family

  readonly property color toneColor: tone === "alert" ? urgent
                                     : tone === "busy" ? accent
                                     : tone === "active" ? foreground : dim

  default property alias body: inner.data

  signal toggled(bool expanded)

  // `controlled`: the caller owns `expanded` (a binding, as on the Agents
  // page, where a save or a deep link must not find it overwritten), so a
  // click only asks, through toggled(), and the binding answers.
  property bool controlled: false
  function flip() {
    if (!foldable) return
    if (controlled) { toggled(!expanded); return }
    expanded = !expanded
    toggled(expanded)
  }
  // Folded while something in the body had the focus (a field being
  // edited, a programmatic collapse): the focus comes to the strip rather
  // than staying on a hidden control.
  onExpandedChanged: {
    if (expanded) return
    for (var i = strip.Window.activeFocusItem; i; i = i.parent)
      if (i === inner) { bar.forceActiveFocus(); return }
  }

  implicitHeight: column.implicitHeight
  height: implicitHeight

  Column {
    id: column
    width: parent.width
    spacing: Style.space(8)

    Rectangle {
      id: bar
      width: parent.width
      height: Math.max(nameText.implicitHeight, pillRow.implicitHeight) + Style.space(12)
      radius: Style.cornerRadius
      activeFocusOnTab: strip.foldable
      Accessible.role: Accessible.Button
      Accessible.name: strip.name + (strip.foldable ? (strip.expanded ? ", open" : ", folded") : "")
      Accessible.description: strip.problem !== "" ? strip.problem : strip.status
      Accessible.focusable: true
      Accessible.onPressAction: strip.flip()
      focus: true
      color: barArea.containsMouse || activeFocus
             ? Style.hoverFillFor(strip.foreground, strip.accent) : "transparent"
      border.width: activeFocus ? 1 : 0
      border.color: strip.accent
      opacity: strip.dimmed ? 0.5 : 1

      Keys.onReturnPressed: strip.flip()
      Keys.onEnterPressed: strip.flip()
      Keys.onSpacePressed: strip.flip()

      Rectangle {
        id: dot
        anchors.left: parent.left
        anchors.leftMargin: Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
        width: Style.space(8)
        height: width
        radius: width / 2
        color: strip.toneColor
      }
      Text {
        id: nameText
        anchors.left: dot.right
        anchors.leftMargin: Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
        width: Math.min(implicitWidth, parent.width * 0.4)
        text: strip.name
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: strip.foreground
        font.family: strip.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
      }
      Text {
        id: statusText
        anchors.left: nameText.right
        anchors.leftMargin: Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
        width: Math.max(0, Math.min(implicitWidth, pillRow.x - x - Style.space(8)))
        visible: strip.status !== "" && width > Style.space(20)
        text: strip.status
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: strip.dim
        font.family: strip.fontFamily
        font.pixelSize: Style.font.caption
      }
      // Pills on the right, as many as fit: a narrow window keeps the name
      // and drops pills from the left rather than overlapping them.
      Row {
        id: pillRow
        anchors.right: caret.left
        anchors.rightMargin: Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(4)
        layoutDirection: Qt.RightToLeft
        readonly property real room: caret.x - Style.space(8) - (nameText.x + nameText.width + Style.space(8))
        // From natural widths, not laid-out positions: a hidden pill is not
        // laid out, so reading x back would feed the answer into itself.
        function fits(i) {
          var w = 0
          for (var j = 0; j <= i; j++) {
            var it = pillRepeater.itemAt(j)
            if (!it) return true
            w += it.implicitWidth + (j > 0 ? spacing : 0)
          }
          return w <= room
        }
        Repeater {
          id: pillRepeater
          model: strip.pills
          Pill {
            required property var modelData
            required property int index
            text: String(modelData.text || "")
            tone: String(modelData.tone || "idle")
            tooltip: String(modelData.tooltip || "")
            foreground: strip.foreground
            accent: strip.accent
            urgent: strip.urgent
            fontFamily: strip.fontFamily
            // Right-to-left, so index 0 is rightmost; later pills give way.
            visible: text !== "" && pillRow.fits(index)
          }
        }
      }
      Text {
        id: caret
        anchors.right: parent.right
        anchors.rightMargin: Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
        visible: strip.foldable
        width: visible ? implicitWidth : 0
        text: strip.expanded ? "▾" : "▸"
        color: strip.dim
        font.family: strip.fontFamily
        font.pixelSize: Style.font.body
      }
      MouseArea {
        id: barArea
        anchors.fill: parent
        hoverEnabled: true
        enabled: strip.foldable
        cursorShape: Qt.PointingHandCursor
        onClicked: { bar.forceActiveFocus(); strip.flip() }
      }
    }

    Text {
      width: parent.width
      visible: strip.problem !== ""
      text: "⚠  " + strip.problem
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: strip.urgent
      font.family: strip.fontFamily
      font.pixelSize: Style.font.caption
    }
    Text {
      width: parent.width
      visible: strip.warning !== ""
      text: "⚠  " + strip.warning
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: strip.accent
      font.family: strip.fontFamily
      font.pixelSize: Style.font.caption
    }

    Column {
      id: inner
      width: parent.width
      visible: strip.expanded
      spacing: Style.space(6)
    }
  }
}
