/**
 * Link validation for drag-to-link, the desktop's rules: different nodes,
 * compatible types, and a group's passthrough only accepts sinks. An input
 * that already has a link may take another (the old one is replaced).
 */
import { type Graph, isSinkGroup, nodeKind } from './graph'
import type { InputPortData, NodeData, OutputPortData } from './types'

/** Every image-like port type shares the `ImageData` base type. */
export const IMAGE_PORT_TYPES = new Set(['ImageData', 'Volume', 'TiltSeries', 'LabelMap', 'Image'])

export function isPortTypeCompatible(portType: string, acceptedTypes: string[]): boolean {
  if (acceptedTypes.includes(portType)) return true
  return IMAGE_PORT_TYPES.has(portType) && acceptedTypes.includes('ImageData')
}

export function ownerOf(graph: Graph, port: OutputPortData): NodeData | null {
  return port.node ? (graph.byId.get(port.node._id) ?? null) : null
}

export function inputOwner(graph: Graph, input: InputPortData): NodeData | null {
  for (const node of graph.nodes) {
    if (node.inputs.some((p) => p._id === input._id)) return node
  }
  return null
}

export function canLink(graph: Graph, output: OutputPortData, input: InputPortData): boolean {
  const from = ownerOf(graph, output)
  const to = inputOwner(graph, input)
  if (!from || !to || from._id === to._id) return false
  if (!isPortTypeCompatible(output.port_type, input.accepted_types)) return false
  if (isSinkGroup(from) && nodeKind(to) !== 'sink') return false
  if (input.link && input.link._id === output._id) return false // already linked
  return !reaches(graph, to, from)
}

/** Whether `target` is downstream of (or is) `node`: the link would loop. */
function reaches(graph: Graph, node: NodeData, target: NodeData): boolean {
  const stack = [node]
  const seen = new Set<string>()
  while (stack.length) {
    const current = stack.pop()!
    if (current._id === target._id) return true
    if (seen.has(current._id)) continue
    seen.add(current._id)
    for (const link of graph.outgoing.get(current._id) || []) stack.push(link.to)
  }
  return false
}
