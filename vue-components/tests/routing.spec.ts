import { describe, expect, it } from 'vitest'

import {
  buildGraph,
  computeLayout,
  depthFirstOrder,
  gutterX,
  roundedPolyline,
  routeLinks,
  type NodeData,
} from '@/layout'
import * as C from '@/layout/constants'
import { byLabel, fanIn, fanOut, FIXTURES, linear, multiOutput, tomography } from './fixtures'

function route(nodes: NodeData[], width = 300) {
  const graph = buildGraph(nodes)
  const layout = computeLayout(graph, depthFirstOrder(graph), width)
  const routing = routeLinks(graph, layout)
  const between = (from: string, to: string) =>
    routing.links.find((l) => l.link.from.label === from && l.link.to.label === to)!
  return { graph, layout, routing, between }
}

describe('rounded polylines', () => {
  it('emits straight segments and quadratic corners', () => {
    expect(
      roundedPolyline(
        [
          { x: 0, y: 0 },
          { x: 0, y: 10 },
        ],
        4,
      ),
    ).toBe('M 0 0 L 0 10')
    expect(
      roundedPolyline(
        [
          { x: 10, y: 0 },
          { x: 10, y: 20 },
          { x: 0, y: 20 },
        ],
        4,
      ),
    ).toBe('M 10 0 L 10 16 Q 10 20 6 20 L 0 20')
  })

  it('clamps the radius to half the shortest leg', () => {
    expect(
      roundedPolyline(
        [
          { x: 0, y: 0 },
          { x: 0, y: 4 },
          { x: 10, y: 4 },
        ],
        4,
      ),
    ).toBe('M 0 0 L 0 2 Q 0 4 2 4 L 10 4')
  })
})

describe('direct links', () => {
  it('draw a straight vertical line between adjacent rows', () => {
    const { between } = route(linear())
    const link = between('sample.vti', 'Gaussian Filter')
    expect(link.direct).toBe(true)
    expect(link.points).toHaveLength(2)
    // The transform row is indented, so the line leans by that much.
    expect(link.to.x - link.from.x).toBe(C.IndentWidth)
    expect(link.path).toBe(`M ${link.from.x} ${link.from.y} L ${link.to.x} ${link.to.y}`)
  })

  it('use no gutter lane at all in a linear chain', () => {
    const { routing } = route(linear())
    expect(routing.gutterLaneCount).toBe(0)
    expect(routing.links.every((l) => l.direct)).toBe(true)
  })
})

describe('gutter links', () => {
  it('route through the gutter when the destination is not the next row', () => {
    const { between } = route(fanOut())
    const link = between('sample.vti', 'Median Filter')
    expect(link.direct).toBe(false)
    const [src, depart, into, outOf, approach, dst] = link.points
    expect(depart).toEqual({ x: src.x, y: src.y + C.SquareClearance })
    expect(into.y).toBe(depart.y)
    expect(into.x).toBe(outOf.x)
    expect(into.x).toBeLessThan(C.GutterWidth)
    expect(into.x).toBeGreaterThan(0)
    expect(approach).toEqual({ x: dst.x, y: dst.y - C.DotClearance })
    expect(outOf.y).toBe(approach.y)
    expect(link.path.startsWith(`M ${src.x} ${src.y}`)).toBe(true)
    expect(link.path.split('Q')).toHaveLength(5) // four rounded corners
  })

  it('assign one column per overlapping span, packed toward the cards', () => {
    const { routing, between } = route(fanOut())
    // source -> Median and Gaussian -> Compare overlap; Compare -> Error Plot does not.
    expect(routing.gutterLaneCount).toBe(2)
    const sourceLane = routing.gutterLanes.get(
      between('sample.vti', 'Median Filter').link.output._id,
    )!
    const gaussLane = routing.gutterLanes.get(
      between('Gaussian Filter', 'Compare').link.output._id,
    )!
    expect(sourceLane).not.toBe(gaussLane)
    expect(gutterX(1, 2)).toBe(C.GutterWidth - C.LaneSpacing / 2)
    expect(gutterX(0, 2)).toBe(C.GutterWidth - C.LaneSpacing / 2 - C.LaneSpacing)
  })

  it('stack the approach rows of a fan-in', () => {
    const { between, routing } = route(fanIn())
    const a = between('Source A', 'Merge')
    const b = between('Source B', 'Merge')
    expect(b.direct).toBe(true)
    expect(a.direct).toBe(false)
    expect(routing.inputLanes.get(a.link.input._id)).toBe(0)
    expect(a.points[a.points.length - 2].y).toBe(a.to.y - C.DotClearance)
  })

  it('share one departure row and column for a fan-out from one port', () => {
    const { between, routing } = route(tomography())
    const outline = between('Denoise', 'Outline')
    const slice = between('Denoise', 'Slice')
    const volume = between('Denoise', 'Volume')
    expect(outline.direct).toBe(false)
    expect(slice.direct).toBe(false)
    expect(volume.direct).toBe(false)
    expect(new Set([outline.points[2].x, slice.points[2].x, volume.points[2].x]).size).toBe(1)
    expect(new Set([outline.points[1].y, slice.points[1].y, volume.points[1].y]).size).toBe(1)
    expect(routing.outputLanes.get(volume.link.output._id)).toBe(0)
  })

  it('leave an expanded port card sideways', () => {
    const nodes = multiOutput()
    byLabel(nodes, 'Segment').expanded = true
    const { between, layout } = route(nodes)
    const link = between('Segment', 'Plot')
    const g = layout.geometry.get(link.link.from._id)!
    expect(link.from).toEqual(g.outputDots[1])
    expect(link.points[1].x).toBeLessThan(link.from.x)
    expect(link.points[1].y).toBe(link.from.y)
  })

  it('color links by the source port type', () => {
    const { between } = route(multiOutput())
    expect(between('Segment', 'Plot').color).toEqual({ r: 0, g: 172, b: 172 })
    expect(between('Segment', 'Molecule Viewer').color).toEqual({ r: 194, g: 60, b: 108 })
  })
})

describe('every fixture', () => {
  it('routes every visible link with a path', () => {
    for (const build of Object.values(FIXTURES)) {
      const { graph, routing } = route(build())
      const grouped = graph.links.filter((l) => graph.groupOf.get(l.to._id)?._id === l.from._id)
      expect(routing.links).toHaveLength(graph.links.length - grouped.length)
      for (const link of routing.links) expect(link.path).toMatch(/^M /)
    }
  })
})
