import QtQuick
import QtQuick.Shapes
import qs.Commons
import qs.Commons as Commons

// One line on the Crew map (master plan M9): a link from one agent's box to
// another's, with an arrowhead at the agent it reaches.
//
// Given the two boxes' centres and their half-sizes, it draws from border
// to border, not centre to centre, so the arrowhead is never hidden under a
// box. `bend` bows the line sideways by that many pixels: the page gives a
// link whose reverse also exists a bend, and because the two directions'
// normals point opposite ways the same bend sends the pair apart instead of
// on top of each other. A link with no reverse is drawn straight.
//
// Nothing here is clickable: a stroke has no hit area worth aiming at. The
// page puts a chip at (midX, midY), a point on the curve, and that chip
// is what is clicked or reached with Tab.
Item {
  id: edge

  property real x1: 0
  property real y1: 0
  property real x2: 0
  property real y2: 0
  // Half the width and height of the boxes at either end.
  property real halfW: 40
  property real halfH: 16
  property real bend: 0
  property color color: Commons.Color.foreground
  property real lineWidth: 1.5
  // A link that carries nothing as things stand (into or out of quarantine,
  // or an empty one): dashed.
  property bool inert: false

  // Straight from centre to centre, and its unit normal.
  readonly property real dx: x2 - x1
  readonly property real dy: y2 - y1
  readonly property real len: Math.max(1, Math.sqrt(dx * dx + dy * dy))
  readonly property real nx: -dy / len
  readonly property real ny: dx / len
  // The control point of the quadratic curve.
  readonly property real cx: (x1 + x2) / 2 + nx * bend
  readonly property real cy: (y1 + y2) / 2 + ny * bend

  // Where a ray from a box's centre towards (tx, ty) leaves the box, plus a
  // small gap.
  function exit(px, py, tx, ty, gap) {
    var ux = tx - px, uy = ty - py
    var l = Math.max(0.001, Math.sqrt(ux * ux + uy * uy))
    ux /= l; uy /= l
    var t = Math.min(Math.abs(ux) > 0.0001 ? halfW / Math.abs(ux) : 1e9,
                     Math.abs(uy) > 0.0001 ? halfH / Math.abs(uy) : 1e9)
    return Qt.point(px + ux * (t + gap), py + uy * (t + gap))
  }
  readonly property point start: exit(x1, y1, cx, cy, 2)
  readonly property point end: exit(x2, y2, cx, cy, 3)
  // Where on the curve the page puts the chip, from the start (0) to the
  // end (1). A pair going both ways puts each chip nearer its own start,
  // so the two never sit side by side over a short gap.
  property real chipT: 0.5
  readonly property real midX: (1 - chipT) * (1 - chipT) * start.x + 2 * (1 - chipT) * chipT * cx + chipT * chipT * end.x
  readonly property real midY: (1 - chipT) * (1 - chipT) * start.y + 2 * (1 - chipT) * chipT * cy + chipT * chipT * end.y

  // The arrowhead: along the curve's direction at its end.
  readonly property real ax: end.x - cx
  readonly property real ay: end.y - cy
  readonly property real al: Math.max(0.001, Math.sqrt(ax * ax + ay * ay))
  readonly property real ux: ax / al
  readonly property real uy: ay / al
  readonly property real head: 9
  readonly property real wing: 4.5

  Shape {
    anchors.fill: parent
    preferredRendererType: Shape.CurveRenderer

    ShapePath {
      strokeColor: edge.color
      strokeWidth: edge.lineWidth
      fillColor: "transparent"
      capStyle: ShapePath.RoundCap
      strokeStyle: edge.inert ? ShapePath.DashLine : ShapePath.SolidLine
      dashPattern: [4, 3]
      startX: edge.start.x
      startY: edge.start.y
      PathQuad {
        x: edge.end.x - edge.ux * edge.head * 0.6
        y: edge.end.y - edge.uy * edge.head * 0.6
        controlX: edge.cx
        controlY: edge.cy
      }
    }
    ShapePath {
      strokeColor: "transparent"
      fillColor: edge.color
      startX: edge.end.x
      startY: edge.end.y
      PathLine {
        x: edge.end.x - edge.ux * edge.head - edge.uy * edge.wing
        y: edge.end.y - edge.uy * edge.head + edge.ux * edge.wing
      }
      PathLine {
        x: edge.end.x - edge.ux * edge.head + edge.uy * edge.wing
        y: edge.end.y - edge.uy * edge.head - edge.ux * edge.wing
      }
      PathLine { x: edge.end.x; y: edge.end.y }
    }
  }
}
