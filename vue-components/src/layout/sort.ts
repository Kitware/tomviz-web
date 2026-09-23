import { buildGraph, type Graph } from './graph'
import type { NodeData } from './types'

/**
 * The desktop's `SortOrder::DepthFirst`: a DFS reverse post-order that keeps
 * chains together, roots and siblings tie-broken by creation order (the graph
 * id, then the position in the list).
 */
export function depthFirstOrder(graph: Graph): NodeData[] {
  const creation = new Map<string, number>()
  graph.nodes.forEach((node, index) => creation.set(node._id, index))
  const byCreation = (a: NodeData, b: NodeData) =>
    a.node_id - b.node_id || (creation.get(a._id) ?? 0) - (creation.get(b._id) ?? 0)

  const roots = graph.nodes
    .filter((node) => !(graph.incoming.get(node._id) || []).length)
    .sort(byCreation)

  const result: NodeData[] = []
  const visited = new Set<string>()
  const stack: { node: NodeData; childrenPushed: boolean }[] = roots.map((node) => ({
    node,
    childrenPushed: false,
  }))

  while (stack.length) {
    const frame = stack[stack.length - 1]
    if (visited.has(frame.node._id)) {
      stack.pop()
      continue
    }
    if (frame.childrenPushed) {
      visited.add(frame.node._id)
      result.unshift(frame.node)
      stack.pop()
      continue
    }
    frame.childrenPushed = true
    const children = (graph.outgoing.get(frame.node._id) || [])
      .map((link) => link.to)
      .filter((node, index, list) => list.findIndex((n) => n._id === node._id) === index)
      .sort(byCreation)
    for (const child of children) {
      if (!visited.has(child._id)) stack.push({ node: child, childrenPushed: false })
    }
  }

  // Nodes on a cycle never reach post-order; append them so nothing is lost.
  for (const node of [...graph.nodes].sort(byCreation)) {
    if (!visited.has(node._id)) result.push(node)
  }
  return result
}

export function sortNodes(nodes: NodeData[]): NodeData[] {
  return depthFirstOrder(buildGraph(nodes))
}
