// The permission card (phase M7): a question waiting, Allow greyed out with
// the daemon's reason, and an Allow the daemon refused -- all from a
// synthetic card, with the answer going to preview.sh's stub, never to a
// real agent's question.
//
//   PREVIEW_PERMIT=refuse bench/preview/preview.sh --wait 2.5 --gap 2.5 \
//     --shots 2 --size 620x560 --arg verified card       # pending, then refused
//   bench/preview/preview.sh --wait 2.5 --size 620x560 --arg unverified card
//   bench/preview/preview.sh --wait 2.5 --gap 2.5 --shots 2 --arg allow card
//   bench/preview/preview.sh --wait 2.5 --gap 2.5 --shots 2 --arg next card
//
// `next`: a second card is waiting when the first is answered, and comes up
// next (Codex review of M7, pass 2), rather than being left to time out.
//
// It writes the card to <out>.card, which the stubbed `agentvoice pending`
// hands the overlay as the daemon would. The stub logs the verdict to
// <out>.writes and what arrived on stdin to <out>.permit; this target checks
// the nonce came on stdin and never on argv, and logs PREVIEW lines.
import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    TestEvent { id: input }

    readonly property string scenario: Quickshell.env("PREVIEW_ARG") || "verified"
    readonly property string writesPath: Quickshell.env("PREVIEW_WRITES") || "/tmp/agentvoice-preview-card.writes"
    readonly property string cardPath: writesPath.replace(/\.writes$/, ".card")
    readonly property string permitPath: writesPath.replace(/\.writes$/, ".permit")
    readonly property real waitS: Number(Quickshell.env("PREVIEW_WAIT") || 3)
    readonly property real gapS: Number(Quickshell.env("PREVIEW_GAP") || 1.5)
    readonly property string nonce: "0123456789abcdef0123456789abcdef"
    readonly property var card: {
      var c = { id: "a1b2c3d4e5f6", tool: "Bash", who: "sora", label: "Sora", chain: "",
                summary: "git push fork phase-m7 && gh pr create --fill",
                note: "", truncated: 0, length: 45, input: {}, sessionWide: true,
                announce: false, asked_at: 0, timeout: 45,
                digest: "5f2b9c0e7a1d4c3b8e6f0a9d2c7b4e1f3a8d6c0b9e2f7a4d1c8b3e6f0a9d2c7b" }
      if (scenario === "unverified") {
        c.verified = false
        c.why = "it was started by a shell that is not running /usr/share/omarchy/shell"
      } else {
        c.verified = true
        c.nonce = overlay.nonce
      }
      return c
    }

    Process {
      id: cardWriter
      command: ["sh", "-c", 'printf "%s\\n" "$1" > "$2"', "sh", JSON.stringify(overlay.card), overlay.cardPath]
      onExited: overlay.open('{"mode":"permission","id":"a1b2c3d4e5f6"}')
    }
    Component.onCompleted: cardWriter.running = true

    function find(item, test) {
      if (!item || item.visible === false || item.opacity === 0) return null
      if (test(item)) return item
      var kids = item.children || []
      for (var i = 0; i < kids.length; i++) {
        var hit = find(kids[i], test)
        if (hit) return hit
      }
      return null
    }
    // The overlay's card, found from the page scroller it always holds.
    function overlayCard() {
      for (var i = overlay.pageScroll; i; i = i.parent) if (i.objectName === "settingsCard") return i
      return null
    }
    function button(label) {
      return find(overlayCard(), function(i) {
        return i.clicked !== undefined && i.text === label
      })
    }
    function report(step) {
      console.warn("PREVIEW " + step + " opened=" + overlay.opened + " mode=" + overlay.mode +
                   " mayAllow=" + overlay.mayAllow + " answered=" + overlay.answered +
                   " note=" + JSON.stringify(overlay.answerNote) +
                   " summary=" + JSON.stringify(String(overlay.request.summary || "")))
    }

    // Before the first shot: what is on screen.
    Timer {
      interval: overlay.waitS * 600
      running: true
      onTriggered: {
        overlay.report("shown")
        var allow = overlay.button("Allow once")
        console.warn("PREVIEW allow-enabled=" + (allow ? allow.enabled : "missing"))
      }
    }
    // Between the first and second shots: press Allow once (verified, allow).
    Timer {
      interval: (overlay.waitS + overlay.gapS * 0.3) * 1000
      running: overlay.scenario !== "unverified"
      onTriggered: {
        var b = overlay.button("Allow once")
        if (!b) { console.warn("PREVIEW miss Allow once"); return }
        if (overlay.scenario === "next") {
          // The second question, waiting under its own id by the time the
          // first is answered.
          var second = JSON.parse(JSON.stringify(overlay.card))
          second.id = "f6e5d4c3b2a1"
          second.who = "jarvis-ajc"; second.label = "Hazel"
          second.summary = "rm -rf build/ && make"
          second.length = second.summary.length
          nextWriter.command = ["sh", "-c", 'printf "%s\\n" "$1" > "$2"', "sh",
                                JSON.stringify(second), overlay.cardPath]
          nextWriter.running = true
        }
        console.warn("PREVIEW click Allow once")
        input.mouseClick(b, b.width / 2, b.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
      }
    }
    Timer {
      interval: (overlay.waitS + overlay.gapS * 0.55) * 1000
      running: overlay.scenario !== "unverified"
      onTriggered: { overlay.report("answered"); stdinCheck.running = true }
    }
    Process { id: nextWriter }
    Process {
      id: stdinCheck
      command: ["sh", "-c", 'printf "argv: "; cat "$1"; printf "stdin: "; cat "$2"',
                "sh", overlay.writesPath, overlay.permitPath]
      stdout: StdioCollector {
        onStreamFinished: {
          var t = String(text)
          var argv = (t.split("stdin: ")[0] || "")
          var stdin = (t.split("stdin: ")[1] || "")
          console.warn("PREVIEW " + t.trim().replace(/\n/g, " | "))
          console.warn("PREVIEW nonce-on-stdin=" + (stdin.indexOf(overlay.nonce) >= 0) +
                       " nonce-on-argv=" + (argv.indexOf(overlay.nonce) >= 0) +
                       " digest-on-stdin=" + (stdin.indexOf(overlay.card.digest) >= 0))
        }
      }
    }
  }
}
