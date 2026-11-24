import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import ".."
import "../ui"

// How a wake word gets through, drawn the way the sound goes (master plan
// M23, feedback item 18): four numbered stages, each holding only its own
// settings.
//
//   1. Microphone -- the meter, the gate (fixed, or following the room) and
//      how fast it follows. Everything after it judges only what this lets
//      through as speech.
//   2. First listener -- the engine and its sensitivity, and the blocks
//      that belong to one engine alone, shown only for that engine:
//      openWakeWord's "your voice" (the verifier, and training a phrase),
//      sherpa-onnx's short-name boost and "also sounds like".
//   3. Second check -- who votes, and its window. Greyed with the reason on
//      an engine that has none.
//   4. Decision -- when a wake counts (master plan M22), Vosk's confidence
//      bar, and today's wakes and turn-downs.
//
// Every key keeps its single home here; the phrase and the openWakeWord
// model stay on the Agents card, shown with a link. Fine-tuning is folded
// under each stage's own Advanced, never beside the settings people came
// for. Testing the wake word is not a stage: it sits underneath.
Column {
  id: page
  // Found by name by bench/preview/targets/decision.qml and listening.qml.
  objectName: "listeningPage"

  required property var s

  // --- sherpa-onnx's "also sounds like" ---------------------------------------
  // The words "also sounds like" can be set for: every word of the main
  // phrase and of each agent switched on, once each.
  readonly property var wakeWords: {
    var seen = {}, out = []
    function add(name, who) {
      var ws = String(name || "").toLowerCase().split(" ")
      for (var i = 0; i < ws.length; i++) {
        var w = ws[i]
        if (!/^[a-z]+$/.test(w) || seen[w]) continue
        seen[w] = true
        out.push({ word: w, who: who })
      }
    }
    add(s.activePhrase, "main")
    for (var i = 0; i < s.voiceAgents.length; i++) {
      var a = s.voiceAgents[i] || {}
      if (a.enabled !== false) add(a.name, String(a.name || ""))
    }
    return out
  }
  function alsoSounds() {
    // Unset means the shipped default (theo's second reading), as the
    // daemon reads it, not an empty list.
    var v = s.setting("wakeAlsoSounds", s.defaults.wakeAlsoSounds || {})
    return v && typeof v === "object" && !Array.isArray(v) ? v : ({})
  }
  function alsoText(word) {
    var list = alsoSounds()[word]
    return Array.isArray(list) ? list.join(", ") : ""
  }
  function alsoDefault(word) {
    var d = s.defaults.wakeAlsoSounds || {}
    return Array.isArray(d[word]) ? d[word].join(", ") : ""
  }
  // Comma-separated in the box; a list per word in the setting. Lower case
  // is words, capitals are phones: that is how the daemon tells them apart.
  function setAlso(word, text) {
    var all = {}, cur = alsoSounds()
    for (var k in cur) all[k] = cur[k]
    var parts = String(text).split(",").map(function(t) { return t.trim().replace(/\s+/g, " ") })
                                       .filter(function(t) { return t !== "" })
    if (parts.length === 0) all[word] = []
    else all[word] = parts.slice(0, 8)
    s.put("wakeAlsoSounds", all)
  }
  readonly property string ccEngines: String(s.setting("crossCheckEngines", "both"))

  // --- 1. the microphone: how fast the gate follows the room (M23) -----------
  readonly property bool adaptive: s.setting("adaptiveGate", false) === true
  // Tenths of a dB per second, as the settings hold them: [rise, fall].
  // daemon/noise_floor.py SPEEDS holds the same numbers, and
  // tests/test_gate_speed.py fails when the two drift apart. Normal is the
  // pair the gate always had.
  readonly property var gateSpeeds: ({ slow: [2, 15], normal: [5, 30], fast: [15, 80] })
  // Read as the daemon reads them (runtime.Config.gate_rates): a whole number,
  // clamped to its bounds; anything else is the shipped rate, so the page
  // never shows a speed the daemon is not using.
  function tenths(key, def, lo, hi) {
    var v = s.setting(key, def)
    if (typeof v === "string" && /^-?[0-9]{1,6}$/.test(v.trim())) v = parseInt(v.trim(), 10)
    if (typeof v !== "number" || !isFinite(v) || Math.floor(v) !== v) return def
    return Math.max(lo, Math.min(hi, v))
  }
  readonly property int riseTenths: tenths("gateRiseTenths", 5, 1, 30)
  readonly property int fallTenths: tenths("gateFallTenths", 30, 5, 100)
  // The preset the two rates make, or "custom" when they were set apart
  // under Advanced (or by hand).
  readonly property string gateSpeed: {
    for (var k in gateSpeeds)
      if (gateSpeeds[k][0] === riseTenths && gateSpeeds[k][1] === fallTenths) return k
    return "custom"
  }
  readonly property var gateSpeedOptions: [
    { label: "Slow", value: "slow",
      tooltip: "Rises 0.2 dB/s, falls 1.5 dB/s: about a minute to follow a room 10 dB louder." },
    { label: "Normal", value: "normal",
      tooltip: "Rises 0.5 dB/s, falls 3.0 dB/s, as it always has: about 30 s for 10 dB louder." },
    { label: "Fast", value: "fast",
      tooltip: "Rises 1.5 dB/s, falls 8.0 dB/s: about 20 s for 10 dB louder." }
  ]
  // One preset is two keys, written together.
  function chooseGateSpeed(v) {
    var pair = gateSpeeds[v]
    if (!pair) return
    s.put("gateRiseTenths", pair[0])
    s.put("gateFallTenths", pair[1])
  }
  function rate(tenths) { return (Number(tenths) / 10).toFixed(1) }
  // What the numbers mean in a room, from bench/gate_speed.py (FINDINGS §56):
  // a 10 dB step in a fan's noise. The 30 s memory is why quieter is about
  // the same at every speed: half of it has to hear the new room first.
  readonly property string gateSpeedHint: {
    if (gateSpeed === "slow")
      return "About a minute to follow a room that gets 10 dB louder; quieter in about 20 s. Steadiest beside music or a TV."
    if (gateSpeed === "fast")
      return "About 20 s to follow a room that gets 10 dB louder; quieter in about 16 s."
    if (gateSpeed === "normal")
      return "About 30 s to follow a room that gets 10 dB louder; quieter in about 18 s."
    return "Custom: rises " + rate(riseTenths) + " dB/s and falls " + rate(fallTenths)
           + " dB/s (Advanced). Choosing a speed sets both."
  }

  // --- 3. the second check -----------------------------------------------------
  // Why the second check does not run, or "": the engine has none (said
  // plainly, not hidden, so the stage does not vanish and leave nobody the
  // wiser), or it is switched off below.
  readonly property string secondCheckReason: {
    if (s.usingOww && !s.owwAvailable)
      return "openWakeWord is not installed, so Vosk is listening instead, and Vosk has no second check."
    if (s.owwLive) return "openWakeWord has no second check: the spotter decides alone."
    if (s.usingSherpa && !s.sherpaAvailable)
      return "sherpa-onnx is not installed, so Vosk is listening instead, and Vosk has no second check."
    if (!s.sherpaLive) return "Vosk has no second check: its grammar decides alone."
    if (s.setting("wakeCrossCheck", true) !== true)
      return "Off: “When a wake counts” below is First only."
    return ""
  }
  readonly property string votesLabel: ccEngines === "whisper" ? "Whisper" : ccEngines === "vosk" ? "Vosk"
                                       : "Vosk and Whisper"

  // --- 4. when a wake counts (master plan M22) ---------------------------------
  // One control for two keys, wakeCrossCheck and wakeBothAgree, because these
  // three are the real choices: "both" with the second check off is not a
  // fourth, it is wakes held closed, and the daemon says so.
  readonly property string decision: s.setting("wakeBothAgree", false) === true ? "both"
                                     : s.setting("wakeCrossCheck", true) === true ? "either" : "first"
  readonly property var decisionOptions: [
    { label: "First only", value: "first",
      tooltip: "The spotter decides alone. No second check." },
    { label: "Either stage", value: "either",
      tooltip: "A spotter hit wakes at once; the second check rescues a short name it missed." },
    { label: "Both must agree", value: "both",
      tooltip: "A spotter hit waits until the second check hears the same name: about 0.8 s more." }
  ]
  // Why "Both must agree" cannot run now, or "". What the page can see for
  // itself first, so it refuses with the service off too; then the daemon's
  // answer for what only it knows: an engine that fell back, a Vosk model
  // that is not on disk.
  readonly property string bothBlocker: {
    if (s.usingOww) return "openWakeWord has no second check"
    if (!s.usingSherpa) return "Vosk has no second check"
    if (!s.sherpaAvailable) return "sherpa-onnx is not installed, and Vosk, listening instead, has no second check"
    var d = s.vWakeDecision || {}
    if (s.serviceActive && (d.blocked === "fallback" || (d.blocked === "no-vosk" && ccEngines === "vosk")))
      return String(d.why || "")
    return ""
  }
  // Said under the selector when "Both must agree" was refused; cleared by
  // another pick, and when its cause goes (a note that outlives its cause is
  // its own bug).
  property string decisionRefused: ""
  onBothBlockerChanged: if (bothBlocker === "") decisionRefused = ""
  function chooseDecision(v) {
    if (v === "both" && bothBlocker !== "") {
      decisionRefused = "Not chosen: " + bothBlocker + ", so the two stages could never agree "
                        + "and no wake would count."
      // The chip holds a pick for its round trip; this one writes nothing.
      decisionChoice.holding = false
      return
    }
    decisionRefused = ""
    // In this order, so every state in between is one of the three.
    if (v === "both") {
      s.put("wakeCrossCheck", true)
      s.put("wakeBothAgree", true)
    } else {
      s.put("wakeBothAgree", false)
      s.put("wakeCrossCheck", v === "either")
    }
  }
  // What to do about wakes held closed, by the daemon's reason.
  function closedFix(code) {
    if (code === "fallback") return "Choose another, or install sherpa-onnx (stage 2)."
    if (code === "off") return "Choose another to wake on one stage, or Either stage and then "
                               + "Both must agree to switch the second check back on."
    if (code === "no-vosk") return "Choose another, or let Whisper vote (stage 3: who votes)."
    return "Choose another, or switch to sherpa-onnx."
  }
  readonly property string decisionHint: {
    if (!s.sherpaLive)
      return (s.usingOww ? "openWakeWord" : "Vosk") + " has no second check, so it decides alone "
             + "whichever is chosen here. The choice is for sherpa-onnx."
    if (decision === "first")
      return "The spotter decides alone: the quickest, and short names such as Theo are missed more often."
    if (decision === "either")
      return "A spotter hit wakes at once, and the second check rescues a short name the spotter missed. Either can wake it."
    return "A spotter hit waits until the second check hears the same name: the fewest false wakes, "
           + "about 0.8 s later than the spotter alone, and only names both stages hear "
           + "(FINDINGS §55). Say the name above the microphone gate."
  }

  // --- today's numbers, for the decision ---------------------------------------
  // `agentvoice stats --json` (daemon/stats.py): counts only, never anything
  // said. Read when the page is built, each time the overlay opens, and when
  // a turn ends.
  property var today: null
  property bool counting: true
  property string todayProblem: ""
  Process {
    id: todayReader
    command: ["agentvoice", "stats", "--days", "1", "--json"]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var d = JSON.parse(text)
          if (!d || typeof d !== "object" || !d.day) throw "shape"
          page.today = d.day
          page.counting = d.keeping !== false
          page.todayProblem = ""
        } catch (e) {
          page.todayProblem = "Today's numbers could not be read."
        }
      }
    }
  }
  function readToday() {
    if (!todayReader.running) todayReader.running = true
  }
  Component.onCompleted: readToday()
  Connections {
    target: page.s
    function onOpenedChanged() { if (page.s.opened) page.readToday() }
    function onVStateChanged() { if (page.s.opened && page.s.vState === "listening") page.readToday() }
  }
  function count(n, one, many) { return n + " " + (n === 1 ? one : many) }
  readonly property string todayLine: {
    if (todayProblem !== "") return todayProblem
    if (!today) return ""
    var w = Number(today.wakes || 0)
    var by = today.rejected_by || {}
    var parts = ["Today: " + count(w, "wake", "wakes")]
    var confirmed = Number((today.wakes_by || {}).confirmed || 0)
    if (confirmed > 0) parts[0] += " (" + confirmed + " confirmed by the second check)"
    // The second check's count where there is one, or where it said no today
    // before the engine changed.
    if (s.sherpaLive || Number(by["second-check"] || 0) > 0)
      parts.push(Number(by["second-check"] || 0) + " rejected by the second check")
    if (Number(by.held || 0) > 0) parts.push(Number(by.held) + " held, then dropped")
    if (Number(by.confidence || 0) > 0) parts.push(Number(by.confidence) + " below the confidence bar")
    return parts.join(" · ") + (counting ? "" : ". Nothing new is counted: numbers are off (Display).")
  }

  // Which wake test is shown: "manual" (you say it) or "auto" (synthesized).
  property string testMode: "manual"
  function nameLine(name, row) {
    var r = row || {}
    var tries = Number(r.tries || 0), hits = Number(r.hits || 0)
    return "“" + name + "”: " + hits + " of " + tries
           + (tries > 0 ? " (" + Math.round(100 * hits / tries) + "%)" : "")
           + (hits > 0 ? " — spotter " + Number(r.spotter || 0) + ", second check " + Number(r["second check"] || 0)
                         + (Number(r.confirmed || 0) > 0 ? ", both " + Number(r.confirmed) : "")
                         + (Number(r.other || 0) > 0 ? ", other " + Number(r.other) : "") : "")
  }

  // --- what each stage says in one line, beside its title ------------------------
  readonly property string engineName: s.owwLive ? "openWakeWord" : s.sherpaLive ? "sherpa-onnx" : "Vosk"
  readonly property string micSummary: !adaptive
    ? "fixed at " + Math.round(Number(s.setting("micThresholdDb", -38))) + " dBFS"
    : "follows the room, " + (gateSpeed === "custom" ? "custom speed" : gateSpeed)
      + (s.serviceActive && !isNaN(s.gateDb) ? " · gate " + Math.round(s.gateDb) + " dBFS" : "")
  readonly property string listenerSummary: {
    var stand = (s.usingOww && !s.owwAvailable) || (s.usingSherpa && !s.sherpaAvailable)
    if (stand) return "Vosk, standing in: " + (s.usingOww ? "openWakeWord" : "sherpa-onnx") + " is not installed"
    if (s.owwLive) return "openWakeWord · threshold " + Number(s.setting("owwThresholdPct", 90)) + "%"
    if (s.sherpaLive) return "sherpa-onnx · threshold " + Number(s.setting("sherpaThresholdPct", 15)) + "%"
    return "Vosk · a grammar of the names"
  }
  readonly property string checkSummary: secondCheckReason !== ""
    ? (s.sherpaLive ? "off" : "none on " + engineName) : votesLabel + (ccEngines === "both" ? " must agree" : " decides")
  readonly property string decisionSummary: {
    if (s.serviceActive && s.vWakeDecision.closed === true) return "wakes held closed"
    if (s.owwLive) return "the spotter alone"
    if (!s.sherpaLive) return "confidence " + Number(s.setting("wakeConfidencePct", 70)) + "%"
    return decision === "first" ? "First only" : decision === "either" ? "Either stage" : "Both must agree"
  }

  spacing: Style.space(18)

  PageHeader {
    width: parent.width
    title: "Listening"
    subtitle: "How a wake word gets through, top to bottom: the microphone, the first listener, the second check, and the decision."
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily
  }

  Column {
    id: stages
    width: parent.width

    // --- 1 ---------------------------------------------------------------------
    StageBlock {
      objectName: "stageMicrophone"
      width: parent.width
      number: 1
      title: "Microphone"
      summary: page.micSummary
      tone: page.s.serviceActive && page.s.levelDb > -99 ? "active" : "idle"
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily

      // The gate is drawn on the live meter: the only way to set it well is to
      // talk and see where your voice falls against the line.
      LevelMeter {
        width: parent.width
        levelDb: page.s.serviceActive ? page.s.levelDb : -99
        gateDb: page.s.gateInForce
        minDb: -60
        idleText: page.s.serviceActive ? "no reading — the microphone is off"
                                       : "no reading — start the service to see your level"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
      }

      SettingRow {
        objectName: "set-adaptiveGate"
        width: parent.width
        label: "Gate"
        hint: page.adaptive
              ? "The line sits a margin above the room's own noise, and moves when the room gets louder or quieter."
              : "The line stays where you put it. Talk normally and put it under your voice."
        help: "It learns the room only while nobody is talking to it: never while you speak a " +
              "request, never while it speaks. It rises slowly and falls faster, because a gate " +
              "too high cuts words off. It never goes below -55 or above -25 dBFS, and until it " +
              "has heard three seconds of the room the fixed gate below is used. The wake " +
              "word is judged 6 dB below the line, so a short name's quiet syllables still count."
        changed: page.s.changed("adaptiveGate")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: page.s.resetKey("adaptiveGate")
        SegmentedChoice {
          objectName: "gateChoice"
          options: [{ label: "Fixed", value: "fixed",
                      tooltip: "The line stays where it is set." },
                    { label: "Follows the room", value: "dynamic",
                      tooltip: "The line sits a margin above the room's noise, and moves with it." }]
          value: page.adaptive ? "dynamic" : "fixed"
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onCommitted: function(v) { page.s.put("adaptiveGate", v === "dynamic") }
        }
      }

      // The live numbers, so "it moved" can be seen rather than taken on trust.
      Text {
        width: parent.width
        visible: page.adaptive
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: !page.s.serviceActive ? "Start the service to see the room's level."
              : isNaN(page.s.floorDb) ? "Listening to the room… the fixed gate holds until then."
              : "Room " + Math.round(page.s.floorDb) + " dBFS · gate " +
                Math.round(page.s.gateDb) + " dBFS"
        color: page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }

      SettingRow {
        objectName: "set-gateSpeed"
        width: parent.width
        visible: page.adaptive
        stacked: true
        label: "Adapts"
        hint: page.gateSpeedHint
        help: "How fast the line may follow the room. It remembers the last 30 seconds of " +
              "the room and takes the middle of them, so a louder room has to be half of " +
              "that before the line starts to move at all, whatever the speed: talk shorter " +
              "than about 15 seconds never moves it. After that, the speed is how quickly it " +
              "catches up (bench/gate_speed.py, FINDINGS §56)."
        changed: page.s.changed("gateRiseTenths") || page.s.changed("gateFallTenths")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: {
          page.s.resetKey("gateRiseTenths")
          page.s.resetKey("gateFallTenths")
        }
        SegmentedChoice {
          objectName: "gateSpeedChoice"
          options: page.gateSpeedOptions
          value: page.gateSpeed
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onCommitted: function(v) { page.chooseGateSpeed(v) }
        }
      }

      // The fixed level stays beside the meter, not under Advanced: with the
      // gate fixed (the default) it is the stage's only control, and the meter
      // is there to set it by eye.
      KnobRow {
        objectName: "set-micThresholdDb"
        width: parent.width
        foreground: page.s.foreground; fontFamily: page.s.fontFamily
        label: page.adaptive ? "Fixed gate (until it has heard the room)" : "Microphone gate"
        unit: " dBFS"
        description: "The red line above. Talk normally and put it under your voice."
        // It has one job on both engines -- deciding which frames count as you
        // talking, which is what ends your turn -- and one extra on Vosk.
        help: "Where your voice stops and the room starts. Anything above the line " +
              "counts as you talking, so this is what ends your turn: once you have " +
              "been under the line for the pause set on the Conversation page, it " +
              "stops listening. Set it too low and room noise holds the turn open; too " +
              "high and a quiet word cuts you off." +
              (page.s.owwLive || page.s.sherpaLive ? "" :
                "\n\nOn Vosk it also gates the wake word: quieter frames never reach " +
                "the grammar, so the phrase cannot be matched against room noise.")
        value: page.s.setting("micThresholdDb", -38)
        defaultValue: page.s.defaults.micThresholdDb !== undefined ? page.s.defaults.micThresholdDb : NaN
        changed: page.s.changed("micThresholdDb")
        minimum: -60; maximum: -20; stepSize: 1
        onCommitted: function(v) { page.s.put("micThresholdDb", v) }
        onReset: page.s.resetKey("micThresholdDb")
      }

      AdvancedSection {
        objectName: "micAdvanced"
        width: parent.width
        visible: page.adaptive
        count: 3
        summary: "margin " + Number(page.s.setting("gateMarginDb", 10)) + " dB · rises "
                 + page.rate(page.riseTenths) + " · falls " + page.rate(page.fallTenths) + " dB/s"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily

        KnobRow {
          objectName: "set-gateMarginDb"
          width: parent.width
          foreground: page.s.foreground; fontFamily: page.s.fontFamily
          label: "Margin above the room"
          unit: " dB"
          description: "How far above the room's noise you have to be to count as talking."
          help: "Lower hears softer speech, and more of the room. Higher needs you to speak up, " +
                "and ignores more of the room. 10 dB suits a desk microphone."
          value: page.s.setting("gateMarginDb", 10)
          defaultValue: page.s.defaults.gateMarginDb !== undefined ? page.s.defaults.gateMarginDb : NaN
          changed: page.s.changed("gateMarginDb")
          minimum: 3; maximum: 25; stepSize: 1
          onCommitted: function(v) { page.s.put("gateMarginDb", v) }
          onReset: page.s.resetKey("gateMarginDb")
        }

        KnobRow {
          objectName: "gateRiseKnob"
          width: parent.width
          foreground: page.s.foreground; fontFamily: page.s.fontFamily
          label: "Rises at most"
          unit: " dB/s"
          displayDivisor: 10; decimals: 1
          description: "How fast the line may climb when the room gets louder."
          help: "Faster follows a fan coming on sooner. It cannot learn your voice: it hears only " +
                "the room between requests, and talk shorter than about 15 seconds never moves " +
                "it at any speed."
          value: page.riseTenths
          defaultValue: page.s.defaults.gateRiseTenths !== undefined ? page.s.defaults.gateRiseTenths : NaN
          changed: page.s.changed("gateRiseTenths")
          minimum: 1; maximum: 30; stepSize: 1
          onCommitted: function(v) { page.s.put("gateRiseTenths", v) }
          onReset: page.s.resetKey("gateRiseTenths")
        }

        KnobRow {
          objectName: "gateFallKnob"
          width: parent.width
          foreground: page.s.foreground; fontFamily: page.s.fontFamily
          label: "Falls at most"
          unit: " dB/s"
          displayDivisor: 10; decimals: 1
          description: "How fast the line may drop when the room gets quieter."
          help: "Falling is faster than rising by default, because a line left too high cuts " +
                "words off, which is worse than holding a turn open a little longer."
          value: page.fallTenths
          defaultValue: page.s.defaults.gateFallTenths !== undefined ? page.s.defaults.gateFallTenths : NaN
          changed: page.s.changed("gateFallTenths")
          minimum: 5; maximum: 100; stepSize: 1
          onCommitted: function(v) { page.s.put("gateFallTenths", v) }
          onReset: page.s.resetKey("gateFallTenths")
        }
      }

      // Not a setting, deliberately: it is a security property, and a setting
      // is a thing that gets switched off once and forgotten.
      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        text: "\u{f033e}  The microphone closes while the screen is locked and opens again " +
              "when you unlock. A microphone you had muted stays muted."
        color: page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
    }

    // --- 2 ---------------------------------------------------------------------
    StageBlock {
      objectName: "stageListener"
      width: parent.width
      number: 2
      title: "First listener"
      summary: page.listenerSummary
      tone: (page.s.usingOww && !page.s.owwAvailable) || (page.s.usingSherpa && !page.s.sherpaAvailable)
            ? "alert" : "active"
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily

      SettingRow {
        objectName: "set-engine"
        width: parent.width
        stacked: true
        label: "Engine"
        hint: page.s.usingOww
              ? "Better at rejecting sound-alikes, and can learn your voice. Hears only its own phrase."
              : page.s.usingSherpa
              ? "Any phrase, and your other agents' names, with far fewer false wakes than Vosk."
              : "Any phrase, and your other agents' names. Weaker at rejecting sound-alikes."
        changed: page.s.changed("engine")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: page.s.resetKey("engine")
        SegmentedChoice {
          objectName: "engineChoice"
          options: page.s.engineOptions
          value: page.s.engine
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onCommitted: function(v) {
            page.s.put("engine", v)
            if (v === "openwakeword" && !page.s.owwAvailable) page.s.fetchNow(["--oww"])
            if (v === "sherpa" && !page.s.sherpaAvailable) page.s.fetchNow(["--sherpa"])
          }
        }
      }

      // The state that had no representation at all. Choosing openWakeWord
      // without the package installed left the daemon falling back to Vosk
      // while the page went on showing an openWakeWord model, threshold and
      // verifier. The controls below follow what is actually listening; this
      // says why.
      Column {
        width: parent.width
        spacing: Style.space(6)
        visible: page.s.usingOww && !page.s.owwAvailable

        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          text: "openWakeWord is not installed, so Vosk is listening instead. It can be " +
                "added now — about 154MB, and it brings real rejection plus verifiers " +
                "trained from your own voice."
          color: page.s.urgent
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
        Button {
          text: "Try installing openWakeWord again…"
          bordered: true
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onClicked: page.s.fetchNow(["--oww"])
        }
      }

      Column {
        width: parent.width
        spacing: Style.space(6)
        visible: page.s.usingSherpa && !page.s.sherpaAvailable

        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          text: "sherpa-onnx is not installed, so Vosk is listening instead. It can be " +
                "added now: about 60MB, for the same phrases and names with far fewer " +
                "false wakes."
          color: page.s.urgent
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
        Button {
          text: "Try installing sherpa-onnx again…"
          bordered: true
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onClicked: page.s.fetchNow(["--sherpa"])
        }
      }

      // Each engine's sensitivity. Vosk has none of its own here: its grammar
      // confidence is a decision, so it is in stage 4.
      KnobRow {
        objectName: "set-owwThresholdPct"
        width: parent.width
        visible: page.s.owwLive
        foreground: page.s.foreground; fontFamily: page.s.fontFamily
        label: "Detection threshold"
        unit: "%"
        description: "Higher rejects more near misses; lower wakes more easily."
        help: "Measured on a 2014 MacBook Pro: the real phrase peaks near 99 and a " +
              "phonetically similar phrase near 90, so 90 rejects the near miss and " +
              "still fires reliably."
        value: page.s.setting("owwThresholdPct", 90)
        defaultValue: page.s.defaults.owwThresholdPct !== undefined ? page.s.defaults.owwThresholdPct : NaN
        changed: page.s.changed("owwThresholdPct")
        minimum: 10; maximum: 99; stepSize: 1
        onCommitted: function(v) { page.s.put("owwThresholdPct", v) }
        onReset: page.s.resetKey("owwThresholdPct")
      }

      // sherpa-onnx shares Vosk's phrase -- both take it as text -- but not its
      // confidence bar: it has a keyword threshold of its own.
      KnobRow {
        objectName: "set-sherpaThresholdPct"
        width: parent.width
        visible: page.s.sherpaLive
        foreground: page.s.foreground; fontFamily: page.s.fontFamily
        label: "Detection threshold"
        unit: "%"
        description: "Higher rejects more sound-alikes; lower wakes more easily."
        help: "Measured on synthesized speech: anywhere from 15 to 35 caught the same " +
              "wakes, and higher mostly cut sound-alikes such as \"Sarong\" for \"Sarah\". " +
              "At 50 it missed about half the real ones."
        value: page.s.setting("sherpaThresholdPct", 15)
        defaultValue: page.s.defaults.sherpaThresholdPct !== undefined ? page.s.defaults.sherpaThresholdPct : NaN
        changed: page.s.changed("sherpaThresholdPct")
        minimum: 10; maximum: 60; stepSize: 5
        onCommitted: function(v) { page.s.put("sherpaThresholdPct", v) }
        onReset: page.s.resetKey("sherpaThresholdPct")
      }

      SettingRow {
        width: parent.width
        label: "Wake phrase"
        hint: "“" + page.s.activePhrase + "” wakes the main agent. It is set on its card, beside each other agent's name."
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        Button {
          text: "Agents ›"
          bordered: true
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onClicked: page.s.goTo("agents", "main")
        }
      }

      // --- sherpa-onnx's own block ---
      Column {
        objectName: "sherpaBlock"
        width: parent.width
        spacing: Style.space(8)
        visible: page.s.sherpaLive

        KnobRow {
          objectName: "set-shortNameBoostPct"
          width: parent.width
          foreground: page.s.foreground; fontFamily: page.s.fontFamily
          label: "Short-name boost"
          unit: "%"
          description: "How hard sherpa-onnx listens for names of three sounds or fewer, such as Theo."
          help: "Measured for \"theo\" on synthesized clips: 50 caught 5/30, 150 caught 8/30 " +
                "with no false wakes, and 300 caught 4/30 while \"Thank you\" and \"Rodeo\" woke it."
          value: page.s.setting("shortNameBoostPct", 150)
          defaultValue: page.s.defaults.shortNameBoostPct !== undefined ? page.s.defaults.shortNameBoostPct : NaN
          changed: page.s.changed("shortNameBoostPct")
          minimum: 50; maximum: 300; stepSize: 10
          onCommitted: function(v) { page.s.put("shortNameBoostPct", v) }
          onReset: page.s.resetKey("shortNameBoostPct")
        }

        AdvancedSection {
          objectName: "alsoSoundsSection"
          width: parent.width
          title: "Also sounds like"
          count: page.wakeWords.length
          summary: "other ways each name gets said"
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily

          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            text: "Other ways each name gets said, separated by commas. " +
                  "Lower case is words it knows (\"thea\"); capitals are sounds written out " +
                  "(\"TH IY1 AH0\"). One that can't be used is skipped, and the journal says why."
            textFormat: Text.PlainText
            color: page.s.dim
            font.family: page.s.fontFamily
            font.pixelSize: Style.font.caption
          }

          Repeater {
            model: page.s.sherpaLive ? page.wakeWords.length : 0
            delegate: SettingRow {
              id: alsoRow
              required property int index
              readonly property var entry: page.wakeWords[alsoRow.index] || ({})
              readonly property string word: String(alsoRow.entry.word || "")
              width: parent ? parent.width : 0
              stacked: true
              label: "“" + alsoRow.word + "”" + (alsoRow.entry.who === "main" ? "  (main agent)" : "")
              changed: page.alsoText(alsoRow.word) !== page.alsoDefault(alsoRow.word)
              foreground: page.s.foreground
              fontFamily: page.s.fontFamily
              onReset: {
                var d = page.alsoDefault(alsoRow.word)
                page.setAlso(alsoRow.word, d)
              }
              TextField {
                text: page.alsoText(alsoRow.word)
                placeholderText: "nothing extra"
                foreground: page.s.foreground
                font.family: page.s.fontFamily
                onEditingFinished: {
                  if (text.trim() !== page.alsoText(alsoRow.word)) page.setAlso(alsoRow.word, text)
                }
              }
            }
          }
        }
      }

      // --- openWakeWord's own block: your voice, and a phrase of your own ---
      Column {
        objectName: "owwBlock"
        width: parent.width
        spacing: Style.space(10)
        visible: page.s.owwLive

        SettingsGroup {
          width: parent.width
          title: "YOUR VOICE"
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily

          // Three states, not two. A trained verifier that is switched off read
          // as "no verifier yet" -- the one message that would send someone back
          // to redo work they had already done.
          StatusCard {
            width: parent.width
            icon: page.s.vVerifier ? "\u{f0483}" : "\u{f0484}"
            title: page.s.vVerifier ? "In use for “" + page.s.activePhrase + "”"
                   : page.s.setting("useVerifier", true) !== true ? "Trained, and switched off"
                   : "Not trained for “" + page.s.activePhrase + "” yet"
            subtitle: page.s.vVerifier ? "Only your voice saying the phrase gets through."
                      : page.s.setting("useVerifier", true) !== true ? "Anyone can wake it. The training is kept."
                      : "Anyone saying the phrase can wake it. Verifiers are per phrase."
            tone: page.s.vVerifier ? "active" : "idle"
            foreground: page.s.foreground
            fontFamily: page.s.fontFamily

            Button {
              text: "Train a verifier from your voice…"
              bordered: true
              enabled: page.s.owwLive
              foreground: page.s.foreground
              fontFamily: page.s.fontFamily
              onClicked: page.s.trainVerifier()
            }
          }

          // The switch that had no switch. `use_verifier` existed in OwwWake since
          // it was written and nothing passed it, so the only way to stop verifying
          // was to delete the .joblib -- which also threw the training away.
          ToggleRow {
            objectName: "set-useVerifier"
            width: parent.width
            label: "Only wake for my voice"
            hint: "Off lets anyone wake it. Your training stays on disk."
            help: "The stock wake models are speaker independent, so a podcast or phone " +
                  "saying the phrase gets through. A verifier trained on your voice is the " +
                  "only layer that knows who is talking — which also means it ignores " +
                  "anyone else at this computer, with nothing to say why."
            disabledReason: page.s.owwLive ? "" : "Only with openWakeWord."
            checked: page.s.setting("useVerifier", true) === true
            changed: page.s.changed("useVerifier")
            foreground: page.s.foreground
            fontFamily: page.s.fontFamily
            onToggled: page.s.put("useVerifier", !checked)
            onReset: page.s.resetKey("useVerifier")
          }
        }

        // Folded: a few hours in a notebook is not a setting.
        SettingsGroup {
          id: ownPhrase
          width: parent.width
          visible: page.s.owwLive
          title: "A PHRASE OF YOUR OWN"
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          property bool open: false

          SettingRow {
            width: parent.width
            label: "Train a new wake phrase"
            hint: "About 2.5 hours in a free Colab notebook. You edit two lines: the phrase and the output name."
            foreground: page.s.foreground
            fontFamily: page.s.fontFamily
            Button {
              text: ownPhrase.open ? "Hide" : "How…"
              bordered: true
              foreground: page.s.foreground
              fontFamily: page.s.fontFamily
              onClicked: ownPhrase.open = !ownPhrase.open
            }
          }

          Column {
            width: parent.width
            visible: ownPhrase.open
            spacing: Style.space(8)

            Text {
              width: parent.width
              wrapMode: Text.WordWrap
              text: "A verifier refines an existing model; it cannot create a new phrase. " +
                    "For one openWakeWord was not shipped with, train one in a Colab notebook " +
                    "— about 2.5 hours on the free tier, 90 minutes on Colab Pro.\n\n" +
                    "Only the small classifier head is trained; the feature models it sits on " +
                    "ship with openWakeWord and do not change. That is why it is quick, and " +
                    "why training is network-bound rather than GPU-bound."
              color: page.s.dim
              font.family: page.s.fontFamily
              font.pixelSize: Style.font.caption
            }
            Button {
              text: "Open the training notebook…"
              bordered: true
              foreground: page.s.foreground
              fontFamily: page.s.fontFamily
              onClicked: Quickshell.execDetached(["omarchy-launch-browser",
                "https://github.com/alfiedennen/openwakeword-colab-2026"])
            }
            Text {
              width: parent.width
              wrapMode: Text.WordWrap
              text: "Upstream's own notebook has not been maintained since 2023; this one is " +
                    "patched for current Python and torchaudio.\n\nSave the .onnx it gives you " +
                    "into ~/.local/share/agentvoice/wakewords/ and it appears in the phrase " +
                    "list on the Agents card, ready for its own verifier. Check it with " +
                    "'agentvoice monitor' before trusting it: this ships openwakeword 0.4.0, " +
                    "and a model built against a newer one should load but has not been proven to."
              color: page.s.dim
              font.family: page.s.fontFamily
              font.pixelSize: Style.font.caption
            }
          }
        }
      }
    }

    // --- 3 ---------------------------------------------------------------------
    StageBlock {
      objectName: "stageCheck"
      width: parent.width
      number: 3
      title: "Second check"
      summary: page.checkSummary
      tone: page.secondCheckReason === "" ? "active" : "idle"
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily

      SettingRow {
        objectName: "secondCheckVotes"
        width: parent.width
        stacked: true
        label: "Who votes"
        hint: page.ccEngines === "whisper" ? "Whisper alone decides, on every short burst: about a second of CPU each."
              : page.ccEngines === "vosk" ? "Vosk alone decides. Cheap, and wakes on sound-alikes such as \"Video\" for Theo."
              : "Vosk and Whisper must both hear the same name. Fewest false wakes (FINDINGS §24)."
        help: "When the spotter stays silent on a short burst of speech, the second check " +
              "listens to the burst again with slower, surer engines. Whether that alone can " +
              "wake it, or must agree with the spotter, is the decision below."
        disabledReason: page.secondCheckReason
        changed: page.s.changed("crossCheckEngines")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: page.s.resetKey("crossCheckEngines")
        SegmentedChoice {
          options: page.s.crossCheckOptions
          value: page.ccEngines
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onCommitted: function(v) { page.s.put("crossCheckEngines", v) }
        }
      }

      AdvancedSection {
        objectName: "checkAdvanced"
        width: parent.width
        visible: page.secondCheckReason === ""
        count: page.ccEngines !== "vosk" ? 4 : 2
        summary: "window " + Number(page.s.setting("crossCheckMinMs", 300)) + "–"
                 + Number(page.s.setting("crossCheckMaxMs", 2600)) + " ms"
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily

        KnobRow {
          objectName: "set-crossCheckMinMs"
          width: parent.width
          foreground: page.s.foreground; fontFamily: page.s.fontFamily
          label: "Shortest burst"
          unit: " ms"
          description: "Shorter bursts are clicks or breaths, and the second check skips them."
          value: page.s.setting("crossCheckMinMs", 300)
          defaultValue: page.s.defaults.crossCheckMinMs !== undefined ? page.s.defaults.crossCheckMinMs : NaN
          changed: page.s.changed("crossCheckMinMs")
          minimum: 100; maximum: 1000; stepSize: 50
          onCommitted: function(v) { page.s.put("crossCheckMinMs", v) }
          onReset: page.s.resetKey("crossCheckMinMs")
        }

        KnobRow {
          objectName: "set-crossCheckMaxMs"
          width: parent.width
          foreground: page.s.foreground; fontFamily: page.s.fontFamily
          label: "Longest burst"
          unit: " ms"
          description: "Longer is a sentence: a name inside one is someone talking about the agent, not to it."
          help: "Each check costs about a second of Whisper, so a wider window means more of them."
          value: page.s.setting("crossCheckMaxMs", 2600)
          defaultValue: page.s.defaults.crossCheckMaxMs !== undefined ? page.s.defaults.crossCheckMaxMs : NaN
          changed: page.s.changed("crossCheckMaxMs")
          minimum: 1000; maximum: 5000; stepSize: 100
          onCommitted: function(v) { page.s.put("crossCheckMaxMs", v) }
          onReset: page.s.resetKey("crossCheckMaxMs")
        }

        KnobRow {
          objectName: "set-crossCheckTrailingWords"
          width: parent.width
          visible: page.ccEngines !== "vosk"
          foreground: page.s.foreground; fontFamily: page.s.fontFamily
          label: "Words after the name"
          unit: ""
          description: "How many words may follow the name. 0 takes only the bare name."
          help: "\"Theo, you there?\" is two. Past this it is someone talking about the agent, " +
                "not to it, so it does not wake."
          value: page.s.setting("crossCheckTrailingWords", 3)
          defaultValue: page.s.defaults.crossCheckTrailingWords !== undefined ? page.s.defaults.crossCheckTrailingWords : NaN
          changed: page.s.changed("crossCheckTrailingWords")
          minimum: 0; maximum: 6; stepSize: 1
          onCommitted: function(v) { page.s.put("crossCheckTrailingWords", v) }
          onReset: page.s.resetKey("crossCheckTrailingWords")
        }

        ToggleRow {
          objectName: "set-crossCheckWhisperHint"
          width: parent.width
          visible: page.ccEngines !== "vosk"
          label: "Tell Whisper the names"
          hint: "Whisper is given the agents' names as a hint, which is how it spelled \"Theo\" right 10 of 10."
          checked: page.s.setting("crossCheckWhisperHint", true) === true
          changed: page.s.changed("crossCheckWhisperHint")
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onToggled: page.s.put("crossCheckWhisperHint", !checked)
          onReset: page.s.resetKey("crossCheckWhisperHint")
        }
      }
    }

    // --- 4 ---------------------------------------------------------------------
    StageBlock {
      objectName: "stageDecision"
      width: parent.width
      number: 4
      title: "Decision"
      summary: page.decisionSummary
      tone: page.s.serviceActive && page.s.vWakeDecision.closed === true ? "alert" : "active"
      last: true
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily

      SettingRow {
        objectName: "set-wakeDecision"
        width: parent.width
        stacked: true
        label: "When a wake counts"
        hint: page.decisionHint
        changed: page.s.changed("wakeCrossCheck") || page.s.changed("wakeBothAgree")
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onReset: {
          page.decisionRefused = ""
          page.s.resetKey("wakeBothAgree")
          page.s.resetKey("wakeCrossCheck")
        }
        SegmentedChoice {
          id: decisionChoice
          objectName: "decisionChoice"
          options: page.decisionOptions
          value: page.decision
          wrap: true
          width: parent.width
          foreground: page.s.foreground
          fontFamily: page.s.fontFamily
          onCommitted: function(v) { page.chooseDecision(v) }
        }
      }

      Text {
        objectName: "decisionRefused"
        width: parent.width
        visible: page.decisionRefused !== ""
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: page.decisionRefused
        color: page.s.urgent
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }

      // The daemon's word that "both" is chosen and cannot run: set by hand,
      // or the engine changed under it. Nothing wakes on one stage instead.
      Text {
        objectName: "decisionClosed"
        width: parent.width
        visible: page.s.serviceActive && page.s.vWakeDecision.closed === true
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: "Wakes are held closed: both stages must agree, and "
              + String(page.s.vWakeDecision.why || "the second check cannot run")
              + ". Nothing wakes on one stage instead. "
              + page.closedFix(String(page.s.vWakeDecision.blocked || ""))
        color: page.s.urgent
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }

      // Vosk's own bar: with no second check, its grammar's confidence is
      // the decision.
      KnobRow {
        objectName: "set-wakeConfidencePct"
        width: parent.width
        visible: !page.s.owwLive && !page.s.sherpaLive
        foreground: page.s.foreground; fontFamily: page.s.fontFamily
        label: "Grammar confidence"
        unit: "%"
        description: "How sure Vosk must be that it heard the phrase."
        help: "Weak against phonetic neighbours by nature: a grammar must pick between " +
              "the phrase and anything-else, so \"hey cloud\" scores as high as \"hey " +
              "claude\". Switch engines if a phone keeps waking it."
        value: page.s.setting("wakeConfidencePct", 70)
        defaultValue: page.s.defaults.wakeConfidencePct !== undefined ? page.s.defaults.wakeConfidencePct : NaN
        changed: page.s.changed("wakeConfidencePct")
        minimum: 0; maximum: 100; stepSize: 5
        onCommitted: function(v) { page.s.put("wakeConfidencePct", v) }
        onReset: page.s.resetKey("wakeConfidencePct")
      }

      // Today's count, so a change above can be judged by what it did.
      Text {
        objectName: "todayLine"
        width: parent.width
        visible: text !== ""
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: page.todayLine
        color: page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
  }

  // --- testing it ------------------------------------------------------------------
  // Not a stage: it runs the whole pipeline, as set above.
  SettingsGroup {
    objectName: "wakeTestGroup"
    width: parent.width
    title: "TEST MY WAKE WORD"
    foreground: page.s.foreground
    fontFamily: page.s.fontFamily

    // You say it ten times, or synthesized voices do.
    SettingRow {
      width: parent.width
      stacked: true
      label: "Test my wake word"
      hint: page.testMode === "manual"
            ? "You say the name ten times. Each wake is counted instead of answered, for up to 90 seconds."
            : "Every installed voice says each name, \"full stop\" and words that must not wake it, straight into the engines. About a minute and a half; the microphone is not used."
      foreground: page.s.foreground
      fontFamily: page.s.fontFamily
      SegmentedChoice {
        options: [{ label: "Manual", value: "manual" }, { label: "Automatic", value: "auto" }]
        value: page.testMode
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onCommitted: function(v) { page.testMode = v }
      }
    }

    // --- manual ---
    Column {
      width: parent.width
      spacing: Style.space(6)
      visible: page.testMode === "manual"

      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        visible: !page.s.serviceActive || page.s.wakeTestRunning
        text: !page.s.serviceActive ? "Start the service first."
              : "Say “" + page.s.activePhrase + "” on its own, with a pause after each. Nothing is answered while this runs. "
                + Number(page.s.vWakeTest.left_s || 0) + "s left."
        textFormat: Text.PlainText
        color: page.s.wakeTestRunning ? page.s.accent : page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      Button {
        text: page.s.wakeTestRunning ? "Stop" : "Start manual test"
        bordered: true
        enabled: page.s.serviceActive
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.wakeTest(!page.s.wakeTestRunning)
      }

      Column {
        width: parent.width
        spacing: Style.space(4)
        visible: page.s.serviceActive && String(page.s.vWakeTest.status || "") !== ""
        readonly property var t: page.s.vWakeTest

        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          text: Number(parent.t.hits || 0) + " of " + Number(parent.t.attempts || 0) + " tries woke it"
                + (Number(parent.t.attempts || 0) > 0 ? "  (" + Math.round(Number(parent.t.rate || 0) * 100) + "%)" : "")
                + (parent.t.status === "done" ? " — done." : parent.t.status === "timeout" ? " — time is up."
                   : parent.t.status === "stopped" ? " — stopped." : "")
          textFormat: Text.PlainText
          color: page.s.foreground
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.body
        }
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          readonly property real peak: Number(parent.t.peak_db !== undefined ? parent.t.peak_db : -99)
          readonly property real gate: Number(parent.t.gate_db || 0)
          text: "Loudest you were: " + (peak <= -99 ? "nothing heard" : peak.toFixed(0) + " dBFS")
                + ", gate " + gate.toFixed(0) + " dBFS."
                + (peak > -99 && peak < gate ? " You never reached the gate, so no try was counted: lower the microphone gate (stage 1), or speak up." : "")
          textFormat: Text.PlainText
          color: peak > -99 && peak < gate ? page.s.urgent : page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          visible: text !== ""
          text: Array.isArray(parent.t.by) && parent.t.by.length > 0 ? "Woke by: " + parent.t.by.join(", ") : ""
          textFormat: Text.PlainText
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          visible: text !== ""
          text: Array.isArray(parent.t.near) && parent.t.near.length > 0
                ? "Near misses:\n• " + parent.t.near.join("\n• ")
                : Number(parent.t.attempts || 0) > Number(parent.t.hits || 0)
                  ? "No near misses: the missed tries never reached a second look. Try a lower threshold or a higher short-name boost."
                  : ""
          textFormat: Text.PlainText
          color: page.s.dim
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }

    // --- automatic ---
    Column {
      width: parent.width
      spacing: Style.space(6)
      visible: page.testMode === "auto"
      readonly property var a: page.s.vWakeAuto
      readonly property string st: String(a.status || "")

      Button {
        text: page.s.wakeAutoRunning ? "Stop" : "Start automatic test"
        bordered: true
        enabled: page.s.engineInstalled
        foreground: page.s.foreground
        fontFamily: page.s.fontFamily
        onClicked: page.s.wakeTestAuto(!page.s.wakeAutoRunning)
      }
      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        visible: parent.st !== ""
        text: parent.st === "loading" ? "Loading the engines…"
              : parent.st === "failed" ? "It could not run: " + String(parent.a.error || "unknown error")
              : (parent.st === "running" ? "Clip " : parent.st === "stopped" ? "Stopped after " : "Done: ")
                + Number(parent.a.done || 0) + " of " + Number(parent.a.total || 0)
                + (parent.st === "done" ? " clips in " + Number(parent.a.seconds || 0) + "s." : "")
                + (parent.a.settings ? "  ·  " + String(parent.a.settings) : "")
        textFormat: Text.PlainText
        color: parent.st === "failed" ? page.s.urgent : page.s.foreground
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      Repeater {
        model: parent.a.names ? Object.keys(parent.a.names) : []
        delegate: Text {
          required property var modelData
          width: page.width
          wrapMode: Text.WordWrap
          text: page.nameLine(modelData, (page.s.vWakeAuto.names || {})[modelData])
          textFormat: Text.PlainText
          color: page.s.foreground
          font.family: page.s.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        visible: Number(parent.a.distractors || 0) > 0
        text: Array.isArray(parent.a["false"]) && parent.a["false"].length > 0
              ? "False wakes:\n• " + parent.a["false"].join("\n• ")
              : "No false wakes in " + Number(parent.a.distractors || 0) + " clips of sound-alikes and ordinary talk."
        textFormat: Text.PlainText
        color: Array.isArray(parent.a["false"]) && parent.a["false"].length > 0 ? page.s.urgent : page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        visible: parent.st !== ""
        text: String(parent.a.note || "")
        textFormat: Text.PlainText
        color: page.s.dim
        font.family: page.s.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
  }
}
