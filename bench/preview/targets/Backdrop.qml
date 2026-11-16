// An opaque theme-coloured layer under whatever the target shows, so a
// screenshot holds the preview and nothing that happens to be on screen.
import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons as Commons

PanelWindow {
  color: Commons.Color.background
  WlrLayershell.namespace: "agentvoice-preview-backdrop"
  WlrLayershell.layer: WlrLayer.Top
  WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
  exclusionMode: ExclusionMode.Ignore
  anchors { top: true; bottom: true; left: true; right: true }
}
