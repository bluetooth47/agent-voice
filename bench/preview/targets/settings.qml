// The settings overlay, opened on the page PREVIEW_ARG names (a summon
// payload such as {"mode":"history"}; empty means the settings page).
// When the page scrolls it steps down a screenful between shots (Scroller).
import QtQuick
import Quickshell
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open(Quickshell.env("PREVIEW_ARG") || "{}")

    // A child of the overlay: a Timer placed directly under ShellRoot, or
    // in an Item there, never fired.
    Scroller { target: overlay }
  }
}
