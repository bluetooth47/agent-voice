// About (master plan M26): this install and both builds, Copy diagnostics and
// what it copies, Check for updates, what runs here and what goes out, the
// local-server probe, every voice command, and the changelog.
//
//   preview.sh --config bench/preview/configs/voice.json --state \
//     bench/preview/states/showcase.json --scratch-data --size 1100x760 \
//     --wait 30 --out /tmp/about about
//   grep PREVIEW /tmp/about.log; cat /tmp/about.writes
//
// What the page reads is preview.sh's synthetic machine: a made-up install
// stamp, a journal holding a line marked PREVIEW-TRANSCRIPT that the report
// must leave out, fake claude and codex on PATH and a day of usage numbers.
// Copy, Check for updates and Look reach the clipboard or the network, so the
// stub logs them and answers with fixed text; the documents reach a logging
// pager stub.
//
// --arg:
//   walk   (default) the page, clicked, every write read back
//   shot   the page with the report shown, scrolled half a screenful per tick
import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Settings {
    id: overlay
    Component.onCompleted: overlay.open('{"page":"about"}')

    TestEvent { id: input }

    readonly property string arg: Quickshell.env("PREVIEW_ARG") || "walk"
    property int passed: 0
    property int failed: 0
    function check(ok, what) {
      if (ok) passed++; else failed++
      console.warn("PREVIEW " + (ok ? "PASS " : "FAIL ") + what)
    }
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
    function content() { return overlay.pageScroll ? overlay.pageScroll.contentItem : null }
    function named(name) { return find(content(), function(i) { return i.objectName === name }) }
    function text(needle) {
      return find(content(), function(i) { return i.text !== undefined && i.clicked === undefined
                                                  && String(i.text).indexOf(needle) >= 0 })
    }
    function valueOf(name) { var r = named(name); return r ? String(r.value) : "" }
    function click(item, label) {
      if (!item) { check(false, "found " + label); return }
      var flick = overlay.pageScroll
      if (flick && content()) {
        var y = item.mapToItem(content(), 0, 0).y
        flick.contentY = Math.max(0, Math.min(y - 160, flick.contentHeight - flick.height))
      }
      console.warn("PREVIEW click " + label)
      input.mouseClick(item, item.width / 2, item.height / 2, Qt.LeftButton, Qt.NoModifier, -1)
    }
    function button(label) {
      return find(content(), function(i) { return i.clicked !== undefined && i.text === label })
    }
    function aboutPage() { return find(content(), function(i) { return i.pluginDir !== undefined && i.copyNote !== undefined }) }

    property string writes: ""
    Process {
      id: writesReader
      command: ["sh", "-c", "cat \"$PREVIEW_WRITES\" 2>/dev/null"]
      stdout: StdioCollector { onStreamFinished: overlay.writes = text }
    }
    function readWrites() { writesReader.running = true }
    function lines(needle) {
      return overlay.writes.split("\n").filter(function(l) { return l.indexOf(needle) >= 0 }).length
    }

    property int step: 0
    property int warm: 0
    Timer {
      interval: 1400
      repeat: true
      running: true
      onTriggered: {
        if (!overlay.store.loaded || ++overlay.warm < 3) return
        overlay.step++
        if (overlay.arg === "shot") {
          if (overlay.step === 2) overlay.click(overlay.named("showReport"), "Show")
          else if (overlay.step > 6 && overlay.pageScroll) {
            var f = overlay.pageScroll
            f.contentY = Math.min(f.contentY + f.height * 0.5, Math.max(0, f.contentHeight - f.height))
          }
          return
        }
        var p = overlay.aboutPage()
        switch (overlay.step) {
        case 1:
          break
        case 2:
          overlay.check(p !== null && p.info !== null, "the install was read")
          overlay.check(overlay.valueOf("rowVersion") === "0.2.0", "version 0.2.0 (" + overlay.valueOf("rowVersion") + ")")
          overlay.check(overlay.valueOf("rowService").indexOf("abc1234def56 (detached)") === 0
                        && overlay.valueOf("rowService").indexOf("installed 2026-11-23 09:30") > 0,
                        "the service: its commit, detached, its install time (" + overlay.valueOf("rowService") + ")")
          overlay.check(overlay.valueOf("rowSettings").indexOf("not a git checkout") > 0,
                        "these settings: a copy that is not a checkout (" + overlay.valueOf("rowSettings") + ")")
          overlay.check(overlay.named("buildNote") !== null && String(overlay.named("buildNote").text).indexOf("Could not tell") === 0,
                        "and so it cannot tell whether they match, and says so")
          // What runs here and what goes out.
          overlay.check(overlay.text("sherpa-onnx · on this machine") !== null || overlay.text("Vosk · on this machine") !== null,
                        "the wake word runs here")
          overlay.check(overlay.text("Whisper") !== null && overlay.text("Piper · on this machine") !== null,
                        "transcription and voices run here")
          overlay.check(overlay.text("cloud · has answered 12 turns here") !== null, "Claude Code has answered, from the record")
          overlay.check(overlay.text("cloud · installed; no turn answered here yet") !== null,
                        "Codex is installed, and that is all it says")
          overlay.check(overlay.text("cloud · not found") !== null, "Gemini is not found")
          overlay.check(overlay.text("connected") === null, "nothing is called connected")
          // The commands, from the table.
          overlay.check(overlay.text("Wake phrases: ") !== null && overlay.text("for Theo") !== null,
                        "the wake phrases, with who answers to each")
          overlay.check(p !== null && p.commandTable !== null && p.commandTable.commands.length >= 8,
                        "every command (" + (p && p.commandTable ? p.commandTable.commands.length : 0) + ")")
          overlay.check(overlay.text("Full stop  ·  on its own · no wake word needed") !== null, "Full stop, and where it counts")
          overlay.check(overlay.text("“stop everything”") !== null, "its phrases")
          overlay.check(overlay.named("changelogTop") !== null && /^M\d+ · \S/.test(String(overlay.named("changelogTop").text))
                        && String(overlay.named("changelogTop").text).indexOf("**") < 0,
                        "the changelog's newest entry")
          overlay.readWrites()
          break
        case 3:
          overlay.check(overlay.writes.trim() === "", "opening the page reached out to nothing (" + overlay.writes.trim() + ")")
          overlay.click(overlay.named("showReport"), "Show what it copies")
          break
        case 4:
          break
        case 5:
          overlay.check(p !== null && p.reportText.indexOf("Agent Voice diagnostics") === 0, "the report is shown")
          overlay.check(p !== null && p.reportText.indexOf("PREVIEW-TRANSCRIPT") < 0 && p.reportText.indexOf("walrus") < 0,
                        "without the journal's transcript line")
          overlay.check(p !== null && p.reportText.indexOf("agent 6.3s, first token 410ms") > 0, "with its structural lines")
          overlay.check(p !== null && p.reportText.indexOf("1 other lines left out") > 0, "and it says one was left out")
          overlay.click(overlay.named("copyDiagnostics"), "Copy")
          break
        case 6:
          overlay.check(p !== null && p.copyNote.indexOf("Copied: 31 lines") === 0, "Copy says what it did (" + (p ? p.copyNote : "") + ")")
          overlay.click(overlay.named("checkUpdates"), "Check for updates")
          break
        case 7:
          overlay.check(overlay.text("Up to date with origin. (asked origin, https://github.com/example/agent-voice.git)") !== null,
                        "the update check names the remote it asked")
          overlay.click(overlay.named("probeLocal"), "Look for local models")
          break
        case 8:
          overlay.check(overlay.text("Ollama: answering, 3 models · llama.cpp server: nothing on port 8080") !== null,
                        "the probe says what answered, and not that anything uses it")
          overlay.click(overlay.button("License (MIT)"), "License")
          break
        case 9:
          overlay.readWrites()
          break
        case 10:
          overlay.check(overlay.lines("diagnostics copy --plugin") === 1, "Copy ran once, with this folder")
          overlay.check(overlay.lines("about updates --json --plugin") === 1, "the update check ran once, on the click")
          overlay.check(overlay.lines("endpoint probe-local") === 1, "the probe ran once, on the click")
          overlay.check(overlay.lines("omarchy-launch-tui --app-id=org.omarchy.agentvoice-docs env LESSSECURE=1 less -- ") === 1
                        && overlay.lines("/LICENSE") === 1, "License opened read only in a pager")
          overlay.check(overlay.lines("bar set") === 0, "About wrote no setting")
          console.warn("PREVIEW writes:\n" + overlay.writes)
          console.warn("PREVIEW DONE " + overlay.passed + " passed, " + overlay.failed + " failed")
          break
        }
      }
    }
  }
}
