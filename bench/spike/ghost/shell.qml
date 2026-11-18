// Plan 12c spike, option (a): a "ghost cursor" that shows where the agent
// is acting, drawn on an overlay layer that takes no input, so the real
// pointer never moves and clicks go straight through to what is under it.
//
// Run: qs -p bench/spike/ghost   (the position comes from GHOST_AT="x,y",
// or the middle of the screen; GHOST_LABEL names who is acting)
import QtQuick
import Quickshell
import Quickshell.Wayland

ShellRoot {
  PanelWindow {
    id: overlay
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "agentvoice-ghost"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    // An empty input region: every click and every motion passes through.
    mask: Region {}

    readonly property var at: {
      var raw = Quickshell.env("GHOST_AT") || ""
      var m = raw.match(/^(\d+),(\d+)$/)
      return m ? Qt.point(Number(m[1]), Number(m[2])) : Qt.point(width / 2, height / 2)
    }

    Item {
      id: ghost
      x: overlay.at.x - 18
      y: overlay.at.y - 18
      width: 36; height: 36
      Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: "transparent"
        border.width: 3
        border.color: "#e0a030"
        SequentialAnimation on scale {
          loops: Animation.Infinite
          NumberAnimation { from: 0.8; to: 1.15; duration: 600; easing.type: Easing.InOutQuad }
          NumberAnimation { from: 1.15; to: 0.8; duration: 600; easing.type: Easing.InOutQuad }
        }
      }
      Rectangle { anchors.centerIn: parent; width: 6; height: 6; radius: 3; color: "#e0a030" }
      Text {
        x: parent.width + 6; y: 6
        text: Quickshell.env("GHOST_LABEL") || "Theo"
        color: "#e0a030"
        font.pixelSize: 14
        font.bold: true
      }
    }
  }
}
