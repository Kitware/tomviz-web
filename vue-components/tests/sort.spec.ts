import { describe, expect, it } from 'vitest'

import { buildGraph, depthFirstOrder, sortNodes } from '@/layout'
import { FIXTURES, fanIn, fanOut, linear, sinkGroup } from './fixtures'

const labels = (nodes: ReturnType<typeof linear>) => sortNodes(nodes).map((n) => n.label)

describe('depth-first order', () => {
  it('keeps a linear chain in order', () => {
    expect(labels(linear())).toEqual([
      'sample.vti',
      'Gaussian Filter',
      'Threshold',
      'Contour',
      'Volume Stats',
    ])
  })

  it('keeps chains together and orders siblings by creation', () => {
    expect(labels(fanOut())).toEqual([
      'sample.vti',
      'Gaussian Filter',
      'Median Filter',
      'Compare',
      'Diff Viewer',
      'Error Plot',
    ])
  })

  it('emits every root before the node they merge into', () => {
    expect(labels(fanIn())).toEqual(['Source A', 'Source B', 'Merge', 'Normalize', 'Export'])
  })

  it('lists a branch entirely before the next root', () => {
    const order = labels(sinkGroup())
    expect(order.indexOf('sample_B.vti')).toBeGreaterThan(order.indexOf('Volume'))
    expect(order.slice(0, 6)).toEqual([
      'sample_A.vti',
      'Gaussian Filter',
      'Visualizations',
      'Outline',
      'Slice',
      'Volume',
    ])
  })

  it('is independent of the input order', () => {
    const nodes = fanOut()
    const shuffled = [...nodes].reverse()
    expect(depthFirstOrder(buildGraph(shuffled)).map((n) => n._id)).toEqual(
      depthFirstOrder(buildGraph(nodes)).map((n) => n._id),
    )
  })

  it('handles every fixture without losing nodes', () => {
    for (const build of Object.values(FIXTURES)) {
      const nodes = build()
      expect(sortNodes(nodes)).toHaveLength(nodes.length)
    }
  })
})
