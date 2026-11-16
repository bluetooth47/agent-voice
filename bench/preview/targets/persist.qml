// Two settings changed 100ms apart, through Settings.qml's own persist(),
// with each write taking PREVIEW_SET_DELAY seconds. Both should arrive in
// <out>.writes.
import QtQuick
import Quickshell
import "plugin"

ShellRoot {
  Settings {
    id: overlay
    Timer {
      interval: 1500; running: true
      onTriggered: { console.warn("PREVIEW write hud"); overlay.persist("hud", "false", true); second.start() }
    }
    Timer {
      id: second; interval: 100
      onTriggered: { console.warn("PREVIEW write chimes"); overlay.persist("chimes", "false", true) }
    }
  }
}
