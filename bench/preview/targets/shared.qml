// Shared chats and passing a conversation (merged plan, Phase 15), on
// synthetic chats in a scratch data folder:
//
//   preview.sh --scratch-data --state bench/preview/states/collab.json \
//              --arg sheet --out /tmp/s shared
//
// --arg chat (the default): a chat passed from the main agent to Sora, each
// reply labelled. sheet: the Send to another agent sheet over it. communal:
// Communal's Chats tab. details: Sora's Chats tab on Agent details, with the
// Collaboration list from the state file. send: the sheet, its Send button
// clicked with a synthetic mouse event; `agentvoice pass ...` is logged to
// OUT.writes rather than run, so nothing is sent.
import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open('{"mode":"history"}')

    property string passed: ""
    FileView {
      path: (Quickshell.env("PREVIEW_DATA") || "/nonexistent") + "/chats/index.json"
      printErrors: false
      onLoaded: {
        var d = JSON.parse(text())
        for (var i = 0; i < d.chats.length; i++)
          if (d.chats[i].participants.length > 1) { overlay.passed = d.chats[i].id; break }
      }
    }

    TestEvent { id: input }
    function find(item, test) {
      if (!item) return null
      if (item.visible !== false && test(item)) return item
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) {
        var hit = find(kids[i], test)
        if (hit) return hit
      }
      return null
    }
    Timer {
      id: press
      interval: 700
      onTriggered: {
        var send = overlay.find(overlay.sendSheetView,
                                function(i) { return i.clicked !== undefined && i.text === "Send" })
        console.warn("PREVIEW " + (send ? "PASS" : "FAIL") + " found Send")
        if (send) input.mouseClick(send, send.width / 2, send.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
      }
    }

    // Which view, from --arg: chat (default), sheet, send, communal, details.
    readonly property string want: Quickshell.env("PREVIEW_ARG") || "chat"
    onPassedChanged: if (passed !== "") show.restart()
    Timer {
      id: show
      interval: 600
      onTriggered: {
        if (overlay.want === "communal") overlay.goTo("communal", "", "chats")
        else if (overlay.want === "details") overlay.goTo("agentdetails", "sora", "chats")
        else {
          overlay.showChat(overlay.passed)
          if (overlay.want === "sheet" || overlay.want === "send")
            overlay.openSendSheet("main", overlay.passed)
          if (overlay.want === "send") press.start()
        }
        console.warn("PREVIEW showing " + overlay.want)
      }
    }
  }
}
