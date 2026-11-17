// Two settings changed 100ms apart, through Settings.qml's own put() (the
// store's queue; it was persist() until the settings rebuild, c3a681d),
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
      onTriggered: { console.warn("PREVIEW write hud"); overlay.put("hud", false); second.start() }
    }
    Timer {
      id: second; interval: 100
      onTriggered: { console.warn("PREVIEW write chimes"); overlay.put("chimes", false) }
    }
  }
}
