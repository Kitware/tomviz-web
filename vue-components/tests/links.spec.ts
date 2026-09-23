import { describe, expect, it } from 'vitest'

import { buildGraph, canLink, computeBrightSet, isPortTypeCompatible } from '@/layout'
import { byLabel, fanOut, multiOutput, sinkGroup } from './fixtures'

describe('link validation', () => {
  it('matches types exactly or through the image base type', () => {
    expect(isPortTypeCompatible('TiltSeries', ['ImageData'])).toBe(true)
    expect(isPortTypeCompatible('Table', ['Table'])).toBe(true)
    expect(isPortTypeCompatible('Table', ['ImageData'])).toBe(false)
    expect(isPortTypeCompatible('ImageData', ['Volume'])).toBe(false)
  })

  it('refuses self links, mismatched types, loops and existing links', () => {
    const nodes = multiOutput()
    const graph = buildGraph(nodes)
    const segment = byLabel(nodes, 'Segment')
    const plot = byLabel(nodes, 'Plot')
    const stats = byLabel(nodes, 'Stats')
    const source = byLabel(nodes, 'Load Data')
    const [volume, table] = segment.outputs
    expect(canLink(graph, volume, segment.inputs[0])).toBe(false) // self
    expect(canLink(graph, volume, plot.inputs[0])).toBe(false) // image into table
    expect(canLink(graph, table, plot.inputs[0])).toBe(false) // already linked
    expect(canLink(graph, source.outputs[0], stats.inputs[0])).toBe(true) // replaces
    // Segment's output back into the source's consumer chain would loop.
    const loopNodes = fanOut()
    const loopGraph = buildGraph(loopNodes)
    const compare = byLabel(loopNodes, 'Compare')
    const gauss = byLabel(loopNodes, 'Gaussian Filter')
    expect(canLink(loopGraph, compare.outputs[0], gauss.inputs[0])).toBe(false)
  })

  it('only lets sinks join a group', () => {
    const nodes = sinkGroup()
    const graph = buildGraph(nodes)
    const group = byLabel(nodes, 'Visualizations')
    expect(canLink(graph, group.outputs[0], byLabel(nodes, 'Outline 2').inputs[0])).toBe(true)
    expect(canLink(graph, group.outputs[0], byLabel(nodes, 'Median Filter').inputs[0])).toBe(false)
  })
})

describe('dimming', () => {
  it('keeps a node, its ports and its neighbours through links bright', () => {
    const nodes = fanOut()
    const graph = buildGraph(nodes)
    const gauss = byLabel(nodes, 'Gaussian Filter')
    const bright = computeBrightSet(graph, { kind: 'node', id: gauss._id })!
    expect(bright.nodes.has(gauss._id)).toBe(true)
    expect(bright.ports.has(gauss.outputs[0]._id)).toBe(true)
    expect(bright.links.has(gauss.inputs[0]._id)).toBe(true)
    expect(bright.ports.has(byLabel(nodes, 'sample.vti').outputs[0]._id)).toBe(true)
    expect(bright.nodes.has(byLabel(nodes, 'sample.vti')._id)).toBe(true)
    expect(bright.nodes.has(byLabel(nodes, 'Compare')._id)).toBe(true)
    expect(bright.nodes.has(byLabel(nodes, 'Diff Viewer')._id)).toBe(false)
    // A sibling reading the same port is one free link hop away.
    expect(bright.nodes.has(byLabel(nodes, 'Median Filter')._id)).toBe(true)
  })

  it('walks through a group for free', () => {
    const nodes = sinkGroup()
    const graph = buildGraph(nodes)
    const outline = byLabel(nodes, 'Outline')
    const bright = computeBrightSet(graph, { kind: 'node', id: outline._id })!
    expect(bright.nodes.has(byLabel(nodes, 'Visualizations')._id)).toBe(true)
    expect(bright.nodes.has(byLabel(nodes, 'Gaussian Filter')._id)).toBe(true)
    expect(bright.nodes.has(byLabel(nodes, 'sample_A.vti')._id)).toBe(false)
  })

  it('is null without a selection', () => {
    expect(computeBrightSet(buildGraph(fanOut()), null)).toBeNull()
  })
})
