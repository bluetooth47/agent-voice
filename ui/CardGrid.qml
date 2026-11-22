import QtQuick
import qs.Commons
import qs.Commons as Commons

// Cards two across when there is room, one above the other when there is
// not. `wideAt` is the grid's own width: 520 px of page is what the overlay
// leaves beside the sidebar at about 760 px wide, the width the plan names.
//
// Each child is given the column's width (a binding, so it follows a
// resize); children only set their own height, or let it follow content.
// A row is as tall as its tallest card.
//
//   CardGrid { width: parent.width; Card { ... } Card { ... } }
Grid {
  id: grid

  property real wideAt: Style.space(520)
  readonly property bool wide: width >= wideAt
  readonly property real cellWidth: wide ? (width - columnSpacing) / 2 : width

  columns: wide ? 2 : 1
  columnSpacing: Style.space(12)
  rowSpacing: Style.space(12)

  function fit(kid) {
    // A Repeater is a child too, and has nothing to lay out.
    if (!kid || kid.width === undefined || kid.toString().indexOf("Repeater") === 0) return
    kid.width = Qt.binding(function() { return grid.cellWidth })
  }
  onChildrenChanged: {
    for (var i = 0; i < children.length; i++) fit(children[i])
  }
}
