// The bar widget's popup, opened on its own with no bar behind it, so it
// can be looked at without opening the real one (which takes the keyboard).
// It anchors to the top-left corner for want of a bar icon to sit under.
import QtQuick
import Quickshell
import "plugin"

ShellRoot {
  Backdrop { }

  Panel {
    id: voice
    // A sibling of the panel's own contents, not of ShellRoot: a Timer
    // placed directly under ShellRoot never fires.
    Timer {
      interval: 300
      running: true
      onTriggered: voice.open()
    }
  }
}
