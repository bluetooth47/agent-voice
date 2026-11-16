// Steps the tallest scrolling list under `target` down by 90% of its height
// shortly after each of preview.sh's shots, so `--shots N` walks the page one
// screenful at a time. A step taken 0.75s before a shot did not always reach
// the screenshot, so it moves right after a shot instead and gets the whole
// gap to be drawn.
import QtQuick
import Quickshell

Item {
  id: scroller
  property var target: null
  readonly property real waitS: Number(Quickshell.env("PREVIEW_WAIT") || 3)
  readonly property real gapS: Number(Quickshell.env("PREVIEW_GAP") || 1.5)

  function find(node, depth) {
    if (!node || depth > 60) return null
    var best = null
    if (node instanceof Flickable && node.visible && node.contentHeight > node.height + 1)
      best = node
    var kids = []
    if (node.contentItem) kids.push(node.contentItem)
    var list = node.data || node.children || []
    for (var i = 0; i < list.length; i++) kids.push(list[i])
    for (var k = 0; k < kids.length; k++) {
      var f = find(kids[k], depth + 1)
      if (f && (!best || f.contentHeight > best.contentHeight)) best = f
    }
    return best
  }

  function step() {
    var f = find(scroller.target, 0)
    if (f) f.contentY = Math.min(f.contentHeight - f.height, f.contentY + f.height * 0.9)
  }

  Timer { id: every; interval: scroller.gapS * 1000; repeat: true; onTriggered: scroller.step() }
  Timer {
    interval: (scroller.waitS + 0.25) * 1000
    running: true
    onTriggered: { scroller.step(); every.start() }
  }
}
