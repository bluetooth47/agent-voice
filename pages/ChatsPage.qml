import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// Chats (phase M18, feedback items 5, 6 and 20): every saved conversation
// and this session's, as their own sidebar page instead of a second mode of
// the overlay behind a lone "Conversation" button on its top row -- a name
// the Conversation settings page already had.
//
// At the top, what is kept and for how long: the three privacy settings
// that used to be on Display (`saveChats`, `chatRetention`, `keepHistory`,
// same names and values), where the chats are and what they take up, and
// Delete all saved chats. Under it the browser (Chats.qml), the same one
// Agent details and Communal show filtered.
Column {
  id: page

  required property var s

  spacing: Style.space(14)

  readonly property bool saving: page.s.setting("saveChats", false) === true

  // `agentvoice chats stats --json`: {dir, exists, chats, pinned, bytes}.
  // Read when the page opens, when the number of chats changes and after a
  // delete -- not on a timer: each read is a Python process.
  property var stats: ({})
  property bool statsRead: false
  function readStats() {
    if (statter.running) { statter.again = true; return }
    statter.running = true
  }
  Process {
    id: statter
    property bool again: false
    command: ["agentvoice", "chats", "stats", "--json"]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var d = JSON.parse(text)
          if (d && typeof d === "object") { page.stats = d; page.statsRead = true }
        } catch (e) {}
      }
    }
    onRunningChanged: if (!running && again) { again = false; running = true }
  }
  Component.onCompleted: page.readStats()
  Connections {
    target: browser
    function onSavedCountChanged() { statsDebounce.restart() }
  }
  Timer { id: statsDebounce; interval: 400; onTriggered: page.readStats() }

  function sizeText(bytes) {
    var b = Number(bytes) || 0
    if (b < 1024) return b + " bytes"
    if (b < 1024 * 1024) return (b / 1024).toFixed(b < 10240 ? 1 : 0) + " KB"
    return (b / 1048576).toFixed(b < 10485760 ? 1 : 0) + " MB"
  }
  readonly property int chatCount: Number(page.stats.chats) || 0
  // The folder as a person would type it.
  readonly property string where: {
    var d = String(page.stats.dir || (page.s.dataHome + "/agentvoice/chats"))
    var home = String(Quickshell.env("HOME") || "")
    return home !== "" && d.indexOf(home + "/") === 0 ? "~" + d.slice(home.length) : d
  }
  readonly property string retentionText: ({
    "forever": "kept forever", "90d": "kept 90 days", "30d": "kept 30 days", "last100": "the last 100 kept"
  })[String(page.s.setting("chatRetention", "forever"))] || "kept forever"

  // Delete all saved chats: `agentvoice chats delete --all`, run only from
  // the DangerButton's onConfirmed (tests/test_confirms.py). It takes the
  // lock the daemon saves under, and a turn that was running when it did is
  // not saved afterwards (chats.record's `began`), so nothing deleted comes
  // back.
  property string purgeNote: ""
  Process {
    id: purger
    property bool launched: false
    command: ["agentvoice", "chats", "delete", "--all"]
    onStarted: launched = true
    stdout: StdioCollector {
      onStreamFinished: {
        var n = parseInt(text, 10)
        if (!isNaN(n)) page.purgeNote = n === 1 ? "1 saved chat deleted." : n + " saved chats deleted."
      }
    }
    stderr: StdioCollector {
      onStreamFinished: if (text.trim() !== "") page.purgeNote = text.trim()
    }
    onRunningChanged: if (!running) {
      if (!launched) page.purgeNote = "Nothing was deleted: agentvoice could not be started."
      page.readStats()
    }
  }
  function deleteAllChats() {
    if (purger.running) return
    page.purgeNote = ""
    purger.launched = false
    purger.running = true
  }

  PageHeader {
    width: parent.width
    title: "Chats"
    subtitle: "Every saved conversation, and this session's. Search them, read them, and pick one up again."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  Card {
    id: saving
    width: parent.width
    title: "Saving and privacy"
    subtitle: (page.saving ? "Saving on · " + page.retentionText : "Saving off: nothing is kept once a conversation ends")
              + (page.statsRead && page.chatCount > 0
                 ? " · " + page.chatCount + (page.chatCount === 1 ? " chat, " : " chats, ") + page.sizeText(page.stats.bytes)
                 : "")
    foldable: true
    expanded: page.s.chatsSettingsOpen !== undefined ? page.s.chatsSettingsOpen
              : !(page.saving && page.chatCount > 0)
    onToggled: function(open) { page.s.chatsSettingsOpen = open }
    foreground: page.s.foreground
    accent: page.s.accent
    fontFamily: page.s.fontFamily

    ToggleRow {
      width: parent.width
      label: "Save conversations"
      hint: "Keep chats on disk so they can be browsed and continued later. Readable by you alone."
      help: "Saved in ~/.local/share/agentvoice/chats, one file per chat, owner-only. " +
            "Off by default, because nothing said is written to disk unless you choose it. " +
            "Switching it off stops saving; chats already saved stay until you delete them " +
            "here.\n\nWith it on, say “new chat” to start afresh, or " +
            "“continue the chat about …” to pick one up again."
      checked: page.saving
      changed: page.s.changed("saveChats")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("saveChats", !checked)
      onReset: page.s.resetKey("saveChats")
    }

    SettingRow {
      width: parent.width
      stacked: true
      visible: page.saving
      label: "Keep saved chats"
      hint: "Counted from when each was last used. Pinned chats are always kept."
      changed: page.s.changed("chatRetention")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onReset: page.s.resetKey("chatRetention")
      SegmentedChoice {
        options: [
          { value: "forever", label: "Forever" },
          { value: "90d", label: "90 days" },
          { value: "30d", label: "30 days" },
          { value: "last100", label: "Last 100" }
        ]
        value: String(page.s.setting("chatRetention", "forever"))
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(v) { page.s.put("chatRetention", v) }
      }
    }

    ToggleRow {
      width: parent.width
      label: "Keep this session's conversation"
      hint: "“This session” below. In memory only, readable by you alone, gone at logout."
      help: "Off deletes what is already kept. Separate from saving: keeping this session's " +
            "view writes nothing to disk, and saving chats does not need it."
      checked: page.s.setting("keepHistory", true) === true
      changed: page.s.changed("keepHistory")
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      onToggled: page.s.put("keepHistory", !checked)
      onReset: page.s.resetKey("keepHistory")
    }

    // Where they are, what they take up, and the one way to remove them all.
    Item {
      width: parent.width
      height: Math.max(storeText.implicitHeight, purgeButton.implicitHeight)

      Column {
        id: storeText
        anchors.left: parent.left
        anchors.right: purgeButton.left
        anchors.rightMargin: Style.space(12)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(2)
        Text {
          width: parent.width
          wrapMode: Text.Wrap
          text: !page.statsRead ? "Reading what is saved…"
                : !page.stats.exists || page.chatCount === 0 ? "No saved chats in " + page.where
                : page.chatCount + (page.chatCount === 1 ? " saved chat" : " saved chats")
                  + (Number(page.stats.pinned) > 0 ? " (" + page.stats.pinned + " pinned)" : "")
                  + " · " + page.sizeText(page.stats.bytes) + " · " + page.where
          textFormat: Text.PlainText
          color: page.s.foreground
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
        Text {
          width: parent.width
          wrapMode: Text.Wrap
          text: "Delete all removes every agent's saved chats, pinned ones too, and cannot be undone. " +
                "This session's view, and what each agent's own program keeps of its conversations, are not touched."
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
        Text {
          width: parent.width
          visible: page.purgeNote !== ""
          wrapMode: Text.Wrap
          text: page.purgeNote
          textFormat: Text.PlainText
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
      }

      DangerButton {
        id: purgeButton
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: "Delete all saved chats"
        enabled: page.chatCount > 0
        busy: purger.running
        tooltipText: page.chatCount > 0 ? "" : "There are no saved chats"
        question: "Delete all " + page.chatCount + (page.chatCount === 1 ? " saved chat" : " saved chats")
                  + ", every agent's, pinned too?"
        confirmText: "Delete all"
        maxWidth: Math.max(Style.space(260), parent.width * 0.6)
        foreground: page.s.foreground
        urgent: page.s.urgent
        fontFamily: page.s.fontFamily
        onConfirmed: page.deleteAllChats()
      }
    }
  }

  Chats {
    id: browser
    width: parent.width
    // The rest of the page's window, so the list and the open chat scroll
    // inside it and the page itself does not.
    height: Math.max(Style.space(420), (page.s.pageScroll ? page.s.pageScroll.height : Style.space(600))
                                       - y - Style.space(20))
    s: page.s
    followSummon: true
  }
}
