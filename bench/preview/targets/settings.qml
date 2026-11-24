// The settings overlay, opened on the page PREVIEW_ARG names (a summon
// payload such as {"mode":"history"}; empty means the settings page).
// When the page scrolls it steps down a screenful between shots (Scroller).
//
// `"narrow": true` in the payload (master plan M29) draws the card itself
// 500px wide, for the narrow layout: a --size crop only cuts a wide one.
// open() ignores the extra key.
import QtQuick
import Quickshell
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open(Quickshell.env("PREVIEW_ARG") || "{}")

    readonly property bool narrow: {
      try { return JSON.parse(Quickshell.env("PREVIEW_ARG") || "{}").narrow === true } catch (e) { return false }
    }
    Timer {
      interval: 300; running: overlay.narrow
      onTriggered: {
        for (var i = overlay.pageScroll; i; i = i.parent)
          if (i.objectName === "settingsCard") { i.width = 500; return }
      }
    }

    // A child of the overlay: a Timer placed directly under ShellRoot, or
    // in an Item there, never fired.
    Scroller { target: overlay }
  }
}
