/**
 * Focus mode: from the selection, everything within one hop stays bright
 * and the rest is dimmed. Ports of a node cost one hop (none for a sink
 * group, whose ports are the members' doorway), following a link is free,
 * and a node seed gets one extra hop to pay for reaching its own ports.
 */
import type { Graph } from './graph'
import { isSinkGroup } from './graph'
import type { NodeData } from './types'

export interface BrightSet {
  nodes: Set<string>
  ports: Set<string>
  /** Links by input port id. */
  links: Set<string>
}

export interface DimSeed {
  kind: 'node' | 'port' | 'link'
  id: string
}

const MAX_HOPS = 1

export function computeBrightSet(graph: Graph, seed: DimSeed | null): BrightSet | null {
  if (!seed) return null
  const bright: BrightSet = { nodes: new Set(), ports: new Set(), links: new Set() }

  type Item =
    { kind: 'node'; node: NodeData; budget: number } | { kind: 'port'; id: string; budget: number }
  const queue: Item[] = []

  const portOwner = (id: string): NodeData | null => {
    for (const node of graph.nodes) {
      if (node.outputs.some((p) => p._id === id) || node.inputs.some((p) => p._id === id))
        return node
    }
    return null
  }

  if (seed.kind === 'node') {
    const node = graph.byId.get(seed.id)
    if (!node) return bright
    queue.push({ kind: 'node', node, budget: MAX_HOPS + 1 })
  } else if (seed.kind === 'port') {
    queue.push({ kind: 'port', id: seed.id, budget: MAX_HOPS })
  } else {
    const link = graph.links.find((l) => l.id === seed.id)
    if (!link) return bright
    bright.links.add(link.id)
    queue.push({ kind: 'port', id: link.output._id, budget: MAX_HOPS })
    queue.push({ kind: 'port', id: link.input._id, budget: MAX_HOPS })
  }

  const bestBudget = new Map<string, number>()
  while (queue.length) {
    const item = queue.shift()!
    const key = item.kind === 'node' ? `n:${item.node._id}` : `p:${item.id}`
    if ((bestBudget.get(key) ?? -1) >= item.budget) continue
    bestBudget.set(key, item.budget)

    if (item.kind === 'node') {
      bright.nodes.add(item.node._id)
      const cost = isSinkGroup(item.node) ? 0 : 1
      if (item.budget - cost < 0) continue
      for (const port of [...item.node.outputs, ...item.node.inputs]) {
        queue.push({ kind: 'port', id: port._id, budget: item.budget - cost })
      }
      continue
    }

    bright.ports.add(item.id)
    const owner = portOwner(item.id)
    if (owner) {
      const cost = isSinkGroup(owner) ? 0 : 1
      if (item.budget - cost >= 0)
        queue.push({ kind: 'node', node: owner, budget: item.budget - cost })
    }
    // Crossing a link is free.
    for (const link of graph.links) {
      if (link.output._id === item.id) {
        bright.links.add(link.id)
        queue.push({ kind: 'port', id: link.input._id, budget: item.budget })
      } else if (link.input._id === item.id) {
        bright.links.add(link.id)
        queue.push({ kind: 'port', id: link.output._id, budget: item.budget })
      }
    }
  }
  return bright
}
