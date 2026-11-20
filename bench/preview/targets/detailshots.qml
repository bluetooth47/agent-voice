// Agent details and Communal in every state they draw (merged plan, Phase
// 12, A12-3), for screenshots:
//
//   preview.sh --live-config --wait 8 --size 520x720 --shots 4 \
//     --arg '{"page":"agentdetails","agent":"main","tab":"prompt"}' detailshots
//
// Before the page opens, the scratch folders (PREVIEW_DATA) are made and
// spoiled on purpose, all with synthetic text: the main agent's role is
// over its 300 characters, its personality is not UTF-8, its instructions
// file is missing; the communal rules were changed outside Settings, and
// the communal defaults are a symlink, so saving them fails. There is one
// agent in the trash and one folder no agent uses. "tab" picks the Agent
// details tab, "saveChats": false turns saving chats off in the scratch
// shell.json, "failSave" saves the defaults so the failure shows, and
// "width" draws the card that many pixels wide.
import QtQuick
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    readonly property var arg: {
      try { return JSON.parse(Quickshell.env("PREVIEW_ARG") || "{}") } catch (e) { return {} }
    }
    Component.onCompleted: {
      if (overlay.arg.saveChats === false) overlay.put("saveChats", false)
      seed.running = true
    }

    Process {
      id: seed
      command: ["bash", "-c",
        "d=\"$1\"; agentvoice agents migrate >/dev/null; " +
        "printf '%s' \"$(printf 'Synthetic role, far too long. %.0s' $(seq 1 14))\" > \"$d/agents/main/role.md\"; " +
        "printf 'Dry\\xff\\xfe and brief.' > \"$d/agents/main/personality.md\"; " +
        "rm -f \"$d/agents/main/instructions.md\"; " +
        "printf '%s' '\"Synthetic rule: ask before deleting anything.\"' | agentvoice agents write communal rules.md --line >/dev/null; " +
        "printf 'Synthetic rule, edited by hand.' > \"$d/communal/rules.md\"; " +
        "rm -f \"$d/communal/defaults.md\"; ln -s /etc/hostname \"$d/communal/defaults.md\"; " +
        "agentvoice agents create spare-agent >/dev/null; " +
        "agentvoice agents trash spare-agent --line <<< '{\"id\":\"spare-agent\",\"name\":\"spare\",\"label\":\"Spare\"}' >/dev/null; " +
        "agentvoice agents create stray-folder >/dev/null",
        "seed", Quickshell.env("PREVIEW_DATA")]
      onRunningChanged: if (!running) {
        overlay.folders.refresh()
        overlay.open(Quickshell.env("PREVIEW_ARG") || "{}")
        if (overlay.arg.failSave) failer.start()
        // "width": the card drawn that wide, to see the narrow layout.
        if (overlay.arg.width) narrow.start()
      }
    }
    Timer {
      id: failer
      interval: 1500
      onTriggered: {
        var e = overlay.find(overlay.pageScroll.contentItem, function(i) { return i.file === "defaults.md" && i.save !== undefined })
        if (e) e.save("Synthetic default that cannot be saved.")
      }
    }
    Timer {
      id: narrow
      interval: 300
      onTriggered: {
        var w = overlay.findIn(overlay, function(i) { return i.objectName === "settingsCard" })
        if (w) w.width = Number(overlay.arg.width)
      }
    }
    // Through `data` as well as `children`: the card is inside a window.
    function findIn(node, test) {
      if (!node) return null
      if (test(node)) return node
      var kids = []
      var list = node.data || node.children || []
      for (var i = 0; i < list.length; i++) kids.push(list[i])
      if (node.contentItem) kids.push(node.contentItem)
      for (var k = 0; k < kids.length; k++) {
        var hit = findIn(kids[k], test)
        if (hit) return hit
      }
      return null
    }
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

    Scroller { target: overlay }
  }
}
