// The popup and the HUD through one conversation (phase M3, bug B): the
// state file is rewritten every PREVIEW_GAP seconds with the next state of
// a turn -- idle, capture, a partial, thinking, speaking, follow-up -- and
// after each the popup's height and the HUD's size are logged:
//
//   readout-measure STEP popup=H hud=WxH
//
// Run with --state (any file: it gives the scratch runtime directory this
// writes into and the stub that says the service is up), e.g.
//
//   bench/preview/preview.sh --state bench/preview/states/showcase.json \
//     --wait 2.4 --gap 2 --shots 6 readout
//
// PREVIEW_ARG "dynamic" first sets hudSize to dynamic through the stubbed
// `omarchy bar set`; pair it with --live-config so the write comes back.
// The HUD is a layer-shell surface of its own and appears where the real one
// would, beside the backdrop; it never takes the keyboard.
import QtQuick
import Quickshell
import Quickshell.Io
import "plugin"

ShellRoot {
  Backdrop { }

  Panel {
    id: voice

    readonly property string base: '"agent": "claude", "level": "ask", "posture": "asks before every change", ' +
                                    '"remembers": true, "governed": true, "level_db": -48'
    readonly property string previous: "Two things: the design review at two, and a call with the printer at four thirty."
    readonly property var steps: [
      ["idle", { state: "listening", transcript: "What's on my calendar this afternoon?",
                 reply: voice.previous, audio_s: 2.4, ms: 312, latency_ms: 2140 }],
      ["capture", { state: "capture", transcript: "", reply: "", last_reply: voice.previous,
                    audio_s: 0, ms: 0, latency_ms: 0 }],
      ["partial", { state: "capture", transcript: "Move the printer call", reply: "",
                    last_reply: voice.previous, audio_s: 0, ms: 0, latency_ms: 0 }],
      ["thinking", { state: "thinking", transcript: "Move the printer call to tomorrow morning, and tell them why.",
                     reply: "", last_reply: voice.previous, audio_s: 3.1, ms: 290, latency_ms: 0 }],
      ["speaking", { state: "speaking", transcript: "Move the printer call to tomorrow morning, and tell them why.",
                     reply: "Done. The printer call is now tomorrow at nine. I told them the design review " +
                            "ran long and you wanted the afternoon clear, and asked them to bring the " +
                            "revised quote. Anything else for tomorrow?",
                     audio_s: 3.1, ms: 290, latency_ms: 1980 }],
      ["followup", { state: "followup", window: "followup",
                     transcript: "Move the printer call to tomorrow morning, and tell them why.",
                     reply: "Done. The printer call is now tomorrow at nine. I told them the design review " +
                            "ran long and you wanted the afternoon clear, and asked them to bring the " +
                            "revised quote. Anything else for tomorrow?",
                     audio_s: 3.1, ms: 290, latency_ms: 1980 }]
    ]
    property int step: -1

    FileView {
      id: stateOut
      path: (Quickshell.env("XDG_RUNTIME_DIR") || "/nonexistent") + "/agentvoice/state"
      printErrors: true
    }
    Process {
      id: setDynamic
      command: ["omarchy", "bar", "set", "duaneoca.agentvoice", "hudSize", "\"dynamic\"", "--json"]
    }

    // Children of the panel, not of ShellRoot: a Timer placed directly under
    // ShellRoot never fires.
    Timer {
      interval: 300
      running: true
      onTriggered: {
        if (Quickshell.env("PREVIEW_ARG") === "dynamic") setDynamic.running = true
        voice.open()
      }
    }
    Timer {
      interval: Number(Quickshell.env("PREVIEW_GAP") || 2) * 1000
      running: true
      repeat: true
      triggeredOnStart: true
      onTriggered: {
        voice.step++
        if (voice.step >= voice.steps.length) { stop(); return }
        var s = voice.steps[voice.step][1]
        var json = JSON.stringify(s)
        // The state's own key first: the CLI's vstate anchors on it.
        stateOut.setText("{" + json.slice(1, -1) + ", " + voice.base + "}")
        measure.restart()
      }
    }
    // Once the panel has laid out the new state.
    Timer {
      id: measure
      interval: 900
      onTriggered: {
        var popup = -1, hud = "?"
        for (var i = 0; i < voice.data.length; i++) {
          var o = voice.data[i]
          if (o && o.loadedContentHeight !== undefined && o.contentHeight !== undefined)
            popup = Math.round(o.contentHeight)
          if (o && o.lingerMs !== undefined && o.implicitHeight !== undefined)
            hud = Math.round(o.implicitWidth) + "x" + Math.round(o.implicitHeight)
                  + (o.visible ? "" : "(hidden)")
        }
        console.log("readout-measure", voice.steps[voice.step][0], "popup=" + popup, "hud=" + hud)
      }
    }
  }
}
