import * as C from './constants'
import { type Graph, membersOf, nodeKind } from './graph'
import type { NodeData, OutputPortData, Point, Rect } from './types'

export type LayoutItemType = 'node' | 'port' | 'member'

/** One hit-testable card: a node, an expanded output port, or a group member. */
export interface LayoutItem {
  type: LayoutItemType
  /** The card's node; for a member card, the member sink. */
  node: NodeData
  /** Port cards only. */
  port?: OutputPortData
  /** Member cards only: the group that holds the member. */
  group?: NodeData
  rect: Rect
}

export interface NodeGeometry {
  node: NodeData
  rect: Rect
  indent: number
  showPorts: boolean
  showMembers: boolean
  /** Output squares (or member circles) hang below the card. */
  hasBottomDots: boolean
  /** One per input, centered on the card's top edge. */
  inputDots: Point[]
  /**
   * Where links leave each output: the center of its square below the card,
   * or the left edge of its port card when the node is expanded.
   */
  outputDots: Point[]
  /** Collapsed groups: one circle per member, before the output squares. */
  memberDots: Point[]
  /** Expanded nodes: one sub-card per output. */
  portCards: Rect[]
  /** Expanded groups: one sub-card per member. */
  memberCards: Rect[]
}

export interface Layout {
  /** Strip order: the sorted nodes minus the sinks drawn inside a group. */
  order: NodeData[]
  items: LayoutItem[]
  geometry: Map<string, NodeGeometry>
  width: number
  height: number
  cardWidth: number
}

function indentLevel(graph: Graph, node: NodeData): number {
  const kind = nodeKind(node)
  const sources = (graph.incoming.get(node._id) || []).map((link) => link.from)
  if (!sources.length || kind === 'source') return 0
  if (kind === 'sink' || kind === 'sinkGroup') {
    return sources.some((n) => nodeKind(n) === 'transform') ? 2 : 1
  }
  return 1
}

/**
 * The vertical pass of the desktop widget: one row per node in strip order,
 * reserving above and below each card the space its port shapes and link
 * rows take, so routed links never cross a card.
 */
export function computeLayout(graph: Graph, sorted: NodeData[], width: number): Layout {
  const order = sorted.filter((node) => !graph.groupOf.has(node._id))
  const inStrip = new Set(order.map((node) => node._id))
  const cardWidth = Math.max(width - C.GutterWidth - 2 * C.Padding, C.MinCardWidth)
  const items: LayoutItem[] = []
  const geometry = new Map<string, NodeGeometry>()

  let y = C.Padding
  let prevNode: NodeData | null = null
  let prevCollapsed = false

  order.forEach((node, index) => {
    const nextNode = order[index + 1] ?? null
    const group = nodeKind(node) === 'sinkGroup'
    const members = group ? membersOf(graph, node) : []
    const inputs = node.inputs || []
    const outputs = node.outputs || []
    const expanded = Boolean(node.expanded)
    const showPorts = expanded && !group && outputs.length > 0
    const showMembers = expanded && group && members.length > 0

    // Input side: dots overflow above the card, then the link rows.
    if (inputs.length) {
      y += C.DotRadius
      let nGutter = 0
      let nDirect = 0
      for (const link of graph.incoming.get(node._id) || []) {
        if (!inStrip.has(link.from._id)) continue
        const direct = prevCollapsed && prevNode !== null && link.from._id === prevNode._id
        if (direct) nDirect++
        else nGutter++
      }
      const gutterSpace = nGutter > 0 ? C.PortClearance + (nGutter - 1) * C.LaneSpacing + 3 : 0
      let space = 0
      if (nGutter > 0 && nDirect > 0) space = Math.max(gutterSpace, C.DirectConnectionSpacing)
      else if (nGutter > 0) space = gutterSpace
      else if (nDirect > 0) space = C.DirectConnectionSpacing
      y += space
    }

    let height = C.NodeCardHeight
    const subCards = showPorts ? outputs.length : showMembers ? members.length : 0
    if (subCards) {
      height += C.PortCardSpacing
      height += subCards * C.PortCardHeight
      height += (subCards - 1) * C.PortCardSpacing
      height += C.PortContentPad
    }

    const indent = indentLevel(graph, node) * C.IndentWidth
    const rect: Rect = {
      x: C.GutterWidth + C.Padding + indent,
      y,
      width: cardWidth - indent,
      height,
    }
    items.push({ type: 'node', node, rect })

    const portCards: Rect[] = []
    const memberCards: Rect[] = []
    let subY = rect.y + C.NodeCardHeight + C.PortCardSpacing
    const subRect = () => {
      const r: Rect = {
        x: rect.x + C.PortContentPad,
        y: subY,
        width: rect.width - 2 * C.PortContentPad,
        height: C.PortCardHeight,
      }
      subY += C.PortCardHeight + C.PortCardSpacing
      return r
    }
    if (showPorts) {
      for (const port of outputs) {
        const r = subRect()
        portCards.push(r)
        items.push({ type: 'port', node, port, rect: r })
      }
    } else if (showMembers) {
      for (const member of members) {
        const r = subRect()
        memberCards.push(r)
        items.push({ type: 'member', node: member, group: node, rect: r })
      }
    }

    const dotX = (i: number, total: number) =>
      rect.x + C.PortIndent + (total <= 1 ? 0 : i * C.OutputSquareSpacing)
    const inputDots = inputs.map((_, i) => ({ x: dotX(i, inputs.length), y: rect.y }))
    const bottom = rect.y + rect.height
    const dotY = bottom + C.OutputSquareEdge / 2 - C.OutputSquareOverlap
    const offset = group && !showMembers ? members.length : 0
    const total = offset + outputs.length
    const memberDots =
      group && !showMembers ? members.map((_, i) => ({ x: dotX(i, total), y: dotY })) : []
    const outputDots = outputs.map((_, i) =>
      showPorts
        ? { x: portCards[i].x, y: portCards[i].y + portCards[i].height / 2 }
        : { x: dotX(offset + i, total), y: dotY },
    )

    const hasBottomDots =
      (!showPorts && outputs.length > 0) || (group && !showMembers && members.length > 0)
    geometry.set(node._id, {
      node,
      rect,
      indent,
      showPorts,
      showMembers,
      hasBottomDots,
      inputDots,
      outputDots,
      memberDots,
      portCards,
      memberCards,
    })

    y += height
    if (hasBottomDots) {
      y += C.OutputSquareEdge - C.OutputSquareOverlap
      let nGutter = 0
      let nDirect = 0
      for (const port of outputs) {
        const links = (graph.outgoingByPort.get(port._id) || []).filter((l) =>
          inStrip.has(l.to._id),
        )
        if (!links.length) continue
        const allDirect = nextNode !== null && links.every((l) => l.to._id === nextNode._id)
        if (allDirect) nDirect++
        else nGutter++
      }
      let space = 0
      if (nGutter > 0 && nDirect > 0) {
        space = Math.max(nGutter * C.LaneSpacing, C.DirectConnectionSpacing)
      } else if (nGutter > 0) space = nGutter * C.LaneSpacing
      else if (nDirect > 0) space = C.DirectConnectionSpacing
      y += space
    }
    y += C.CardSpacing

    prevNode = node
    prevCollapsed = !showPorts && outputs.length > 0
  })

  return { order, items, geometry, width, height: y + C.Padding, cardWidth }
}
