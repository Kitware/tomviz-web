import { describe, expect, it } from 'vitest'

import {
  buildGraph,
  computeLayout,
  depthFirstOrder,
  membersOf,
  nodeKind,
  rectBottom,
  type NodeData,
} from '@/layout'
import * as C from '@/layout/constants'
import { byLabel, FIXTURES, linear, multiOutput, sinkGroup } from './fixtures'

const WIDTH = 300

function layoutOf(nodes: NodeData[]) {
  const graph = buildGraph(nodes)
  return { graph, layout: computeLayout(graph, depthFirstOrder(graph), WIDTH) }
}

describe('node kinds', () => {
  it('derives the kind from the type string', () => {
    const nodes = sinkGroup()
    expect(nodeKind(byLabel(nodes, 'sample_A.vti'))).toBe('source')
    expect(nodeKind(byLabel(nodes, 'Gaussian Filter'))).toBe('transform')
    expect(nodeKind(byLabel(nodes, 'Visualizations'))).toBe('sinkGroup')
    expect(nodeKind(byLabel(nodes, 'Outline'))).toBe('sink')
  })
})

describe('layout of a linear chain', () => {
  const { layout } = layoutOf(linear())
  const rect = (label: string) => layout.geometry.get(byLabel(layout.order, label)._id)!.rect

  it('stacks cards after the gutter, one row each, indented by kind', () => {
    expect(layout.order.map((n) => n.label)[0]).toBe('sample.vti')
    expect(layout.cardWidth).toBe(WIDTH - C.GutterWidth - 2 * C.Padding)
    expect(rect('sample.vti')).toEqual({
      x: C.GutterWidth + C.Padding,
      y: C.Padding,
      width: layout.cardWidth,
      height: C.NodeCardHeight,
    })
    expect(rect('Gaussian Filter').x).toBe(C.GutterWidth + C.Padding + C.IndentWidth)
    expect(rect('Volume Stats').x).toBe(C.GutterWidth + C.Padding + 2 * C.IndentWidth)
  })

  it('reserves the output square, the direct link and the input dot between rows', () => {
    const source = rect('sample.vti')
    const gauss = rect('Gaussian Filter')
    const between =
      C.OutputSquareEdge -
      C.OutputSquareOverlap +
      C.DirectConnectionSpacing +
      C.CardSpacing +
      C.DotRadius +
      C.DirectConnectionSpacing
    expect(gauss.y).toBe(rectBottom(source) + between)
  })

  it('places input dots on the top edge and output squares below the card', () => {
    const g = layout.geometry.get(byLabel(layout.order, 'Gaussian Filter')._id)!
    expect(g.inputDots).toEqual([{ x: g.rect.x + C.PortIndent, y: g.rect.y }])
    expect(g.outputDots).toEqual([
      {
        x: g.rect.x + C.PortIndent,
        y: rectBottom(g.rect) + C.OutputSquareEdge / 2 - C.OutputSquareOverlap,
      },
    ])
    expect(g.hasBottomDots).toBe(true)
  })

  it('ends with padding after the last card', () => {
    const last = rect('Volume Stats')
    expect(layout.height).toBe(rectBottom(last) + C.CardSpacing + C.Padding)
  })
})

describe('expanded nodes', () => {
  it('grows the card by one sub-card per output and moves the link start to the card edge', () => {
    const nodes = multiOutput()
    const segment = byLabel(nodes, 'Segment')
    segment.expanded = true
    const { layout } = layoutOf(nodes)
    const g = layout.geometry.get(segment._id)!
    expect(g.showPorts).toBe(true)
    expect(g.hasBottomDots).toBe(false)
    expect(g.rect.height).toBe(
      C.NodeCardHeight +
        C.PortCardSpacing +
        3 * C.PortCardHeight +
        2 * C.PortCardSpacing +
        C.PortContentPad,
    )
    expect(g.portCards).toHaveLength(3)
    expect(g.portCards[0]).toEqual({
      x: g.rect.x + C.PortContentPad,
      y: g.rect.y + C.NodeCardHeight + C.PortCardSpacing,
      width: g.rect.width - 2 * C.PortContentPad,
      height: C.PortCardHeight,
    })
    expect(g.outputDots[1]).toEqual({
      x: g.portCards[1].x,
      y: g.portCards[1].y + C.PortCardHeight / 2,
    })
    expect(layout.items.filter((i) => i.type === 'port')).toHaveLength(3)
  })

  it('spaces several output squares of a collapsed node evenly', () => {
    const { layout } = layoutOf(multiOutput())
    const g = layout.geometry.get(byLabel(layout.order, 'Segment')._id)!
    expect(g.outputDots.map((p) => p.x)).toEqual([
      g.rect.x + C.PortIndent,
      g.rect.x + C.PortIndent + C.OutputSquareSpacing,
      g.rect.x + C.PortIndent + 2 * C.OutputSquareSpacing,
    ])
  })
})

describe('sink groups', () => {
  it('draws members inside the group, not as rows of the strip', () => {
    const { graph, layout } = layoutOf(sinkGroup())
    const group = byLabel(graph.nodes, 'Visualizations')
    expect(membersOf(graph, group).map((n) => n.label)).toEqual(['Outline', 'Slice', 'Volume'])
    expect(layout.order.map((n) => n.label)).toEqual([
      'sample_A.vti',
      'Gaussian Filter',
      'Visualizations',
      'sample_B.vti',
      'Median Filter',
      'Outline 2',
      'Slice 2',
      'Volume 2',
    ])
    const g = layout.geometry.get(group._id)!
    // Collapsed: three member circles, then the passthrough output.
    expect(g.memberDots).toHaveLength(3)
    expect(g.outputDots[0].x).toBe(g.rect.x + C.PortIndent + 3 * C.OutputSquareSpacing)
    expect(g.indent).toBe(2 * C.IndentWidth)
  })

  it('expands into member cards', () => {
    const nodes = sinkGroup()
    const group = byLabel(nodes, 'Visualizations')
    group.expanded = true
    const { layout } = layoutOf(nodes)
    const g = layout.geometry.get(group._id)!
    expect(g.showMembers).toBe(true)
    expect(g.memberCards).toHaveLength(3)
    expect(g.memberDots).toEqual([])
    // The passthrough "join" circle still hangs below an expanded group.
    expect(g.hasBottomDots).toBe(true)
    expect(g.outputDots[0].x).toBe(g.rect.x + C.PortIndent)
    const members = layout.items.filter((i) => i.type === 'member')
    expect(members.map((i) => i.node.label)).toEqual(['Outline', 'Slice', 'Volume'])
    expect(members[0].group).toBe(group)
  })
})

describe('every fixture', () => {
  it('lays out without overlapping rows', () => {
    for (const build of Object.values(FIXTURES)) {
      const { layout } = layoutOf(build())
      let lastBottom = 0
      for (const node of layout.order) {
        const rect = layout.geometry.get(node._id)!.rect
        expect(rect.y).toBeGreaterThan(lastBottom)
        lastBottom = rectBottom(rect)
      }
      expect(layout.height).toBeGreaterThanOrEqual(lastBottom)
    }
  })
})
