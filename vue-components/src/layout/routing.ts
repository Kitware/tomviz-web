import { portTypeColor, type RGB } from './colors'
import * as C from './constants'
import type { Graph, Link } from './graph'
import type { Layout } from './layout'
import type { Point } from './types'

export interface LinkGeometry {
  link: Link
  /** A straight vertical segment to the next row. */
  direct: boolean
  points: Point[]
  /** SVG path data with rounded corners. */
  path: string
  color: RGB
  from: Point
  to: Point
}

export interface Routing {
  links: LinkGeometry[]
  gutterLaneCount: number
  /** Departure row of every output port that uses the gutter. */
  outputLanes: Map<string, number>
  /** Approach row of every input port that uses the gutter. */
  inputLanes: Map<string, number>
  /** Gutter column of every output port that uses the gutter. */
  gutterLanes: Map<string, number>
}

interface Span {
  portId: string
  minY: number
  maxY: number
}

export function gutterX(lane: number, laneCount: number): number {
  const maxLane = Math.max(laneCount - 1, 0)
  return C.GutterWidth - C.LaneSpacing / 2 - (maxLane - lane) * C.LaneSpacing
}

/** Where a pending link leaves the gutter while dragging: the next free column. */
export function pendingGutterX(laneCount: number): number {
  return Math.max(C.GutterWidth - C.LaneSpacing / 2 - laneCount * C.LaneSpacing, 2)
}

function fmt(p: Point): string {
  return `${round(p.x)} ${round(p.y)}`
}

function round(v: number): number {
  return Math.round(v * 100) / 100
}

/** An SVG path along `points`, each interior corner rounded by `radius`. */
export function roundedPolyline(points: Point[], radius: number): string {
  if (!points.length) return ''
  let d = `M ${fmt(points[0])}`
  for (let i = 1; i < points.length - 1; i++) {
    const prev = points[i - 1]
    const p = points[i]
    const next = points[i + 1]
    const d1 = { x: p.x - prev.x, y: p.y - prev.y }
    const d2 = { x: next.x - p.x, y: next.y - p.y }
    const len1 = Math.hypot(d1.x, d1.y)
    const len2 = Math.hypot(d2.x, d2.y)
    if (len1 === 0 || len2 === 0) {
      d += ` L ${fmt(p)}`
      continue
    }
    const r = Math.min(radius, len1 / 2, len2 / 2)
    const before = { x: p.x - (d1.x / len1) * r, y: p.y - (d1.y / len1) * r }
    const after = { x: p.x + (d2.x / len2) * r, y: p.y + (d2.y / len2) * r }
    d += ` L ${fmt(before)} Q ${fmt(p)} ${fmt(after)}`
  }
  if (points.length > 1) d += ` L ${fmt(points[points.length - 1])}`
  return d
}

/**
 * Route every link between two cards of the strip. A link to the very next
 * row is a straight line; every other one leaves its port downward (or
 * sideways from a port card), turns into the gutter, travels a column
 * assigned by interval coloring, and comes back to its input dot.
 */
export function routeLinks(graph: Graph, layout: Layout): Routing {
  const index = new Map<string, number>()
  layout.order.forEach((node, i) => index.set(node._id, i))
  const geometry = (id: string) => layout.geometry.get(id)!

  const visible = graph.links.filter((l) => index.has(l.from._id) && index.has(l.to._id))
  const isDirect = (l: Link) =>
    index.get(l.to._id) === index.get(l.from._id)! + 1 && !geometry(l.from._id).showPorts

  const source = (l: Link): Point => {
    const g = geometry(l.from._id)
    const i = l.from.outputs.findIndex((p) => p._id === l.output._id)
    return g.outputDots[i] ?? { x: g.rect.x + C.PortIndent, y: g.rect.y + g.rect.height }
  }
  const destination = (l: Link): Point => {
    const g = geometry(l.to._id)
    const i = l.to.inputs.findIndex((p) => p._id === l.input._id)
    return g.inputDots[i] ?? { x: g.rect.x + C.PortIndent, y: g.rect.y }
  }

  // Compact per-node rows for the ports that need the gutter.
  const outputLanes = new Map<string, number>()
  const inputLanes = new Map<string, number>()
  for (const node of layout.order) {
    let k = 0
    for (const port of node.outputs || []) {
      const links = (graph.outgoingByPort.get(port._id) || []).filter(
        (l) => index.has(l.to._id) && !isDirect(l),
      )
      if (links.length) outputLanes.set(port._id, k++)
    }
    k = 0
    for (const link of graph.incoming.get(node._id) || []) {
      if (index.has(link.from._id) && !isDirect(link)) inputLanes.set(link.input._id, k++)
    }
  }

  const departY = (l: Link, src: Point) =>
    geometry(l.from._id).showPorts
      ? src.y
      : src.y + C.SquareClearance + (outputLanes.get(l.output._id) ?? 0) * C.LaneSpacing
  const approachY = (l: Link, dst: Point) =>
    dst.y - C.DotClearance - (inputLanes.get(l.input._id) ?? 0) * C.LaneSpacing

  // One vertical span per source port, first-fit into gutter columns.
  const spans = new Map<string, Span>()
  for (const link of visible) {
    if (isDirect(link)) continue
    const dY = departY(link, source(link))
    const aY = approachY(link, destination(link))
    const span = spans.get(link.output._id)
    const lo = Math.min(dY, aY)
    const hi = Math.max(dY, aY)
    if (span) {
      span.minY = Math.min(span.minY, lo)
      span.maxY = Math.max(span.maxY, hi)
    } else {
      spans.set(link.output._id, { portId: link.output._id, minY: lo, maxY: hi })
    }
  }
  const sorted = [...spans.values()].sort((a, b) => a.minY - b.minY)
  const lanes: Span[][] = []
  const gutterLanes = new Map<string, number>()
  for (const span of sorted) {
    let assigned = lanes.findIndex(
      (lane) => !lane.some((s) => span.minY <= s.maxY && span.maxY >= s.minY),
    )
    if (assigned < 0) {
      assigned = lanes.length
      lanes.push([])
    }
    lanes[assigned].push(span)
    gutterLanes.set(span.portId, assigned)
  }
  const laneCount = lanes.length

  const links: LinkGeometry[] = visible.map((link) => {
    const src = source(link)
    const dst = destination(link)
    const color = portTypeColor(link.output.port_type)
    if (isDirect(link)) {
      const points = [src, dst]
      return {
        link,
        direct: true,
        points,
        path: roundedPolyline(points, 0),
        color,
        from: src,
        to: dst,
      }
    }
    const dY = departY(link, src)
    const aY = approachY(link, dst)
    const gx = gutterX(gutterLanes.get(link.output._id) ?? 0, laneCount)
    const points: Point[] = [src]
    if (dY !== src.y) points.push({ x: src.x, y: dY })
    points.push({ x: gx, y: dY })
    points.push({ x: gx, y: aY })
    points.push({ x: dst.x, y: aY })
    if (aY !== dst.y) points.push(dst)
    return {
      link,
      direct: false,
      points,
      path: roundedPolyline(points, C.LinkCornerRadius),
      color,
      from: src,
      to: dst,
    }
  })

  return { links, gutterLaneCount: laneCount, outputLanes, inputLanes, gutterLanes }
}

export interface PendingLink {
  path: string
  points: Point[]
  /** Whether the pending link ends on an accepted input. */
  valid: boolean
}

/**
 * The link being dragged from `source`: the real route into `target`'s dot
 * when there is one, else a run down and into the next free gutter column,
 * following the cursor vertically.
 */
export function pendingLink(
  routing: Routing,
  source: Point,
  fromPortCard: boolean,
  target: Point | null,
  cursor: Point,
): PendingLink {
  const gx = pendingGutterX(routing.gutterLaneCount)
  const dY = fromPortCard ? source.y : source.y + C.SquareClearance
  const points: Point[] = [source]
  if (dY !== source.y) points.push({ x: source.x, y: dY })
  points.push({ x: gx, y: dY })
  if (target) {
    const aY = target.y - C.DotClearance
    points.push({ x: gx, y: aY }, { x: target.x, y: aY }, target)
    return { path: roundedPolyline(points, C.LinkCornerRadius), points, valid: true }
  }
  points.push({ x: gx, y: cursor.y })
  return { path: roundedPolyline(points, C.LinkCornerRadius), points, valid: false }
}
