import type { InputPortData, NodeData, NodeKind, OutputPortData } from './types'

/** A link, identified by its input port: an input holds at most one. */
export interface Link {
  id: string
  input: InputPortData
  output: OutputPortData
  from: NodeData
  to: NodeData
}

export interface Graph {
  nodes: NodeData[]
  byId: Map<string, NodeData>
  links: Link[]
  /** Links by the id of the node they leave. */
  outgoing: Map<string, Link[]>
  /** Links by the id of the node they enter. */
  incoming: Map<string, Link[]>
  /** Links by the id of the output port they leave. */
  outgoingByPort: Map<string, Link[]>
  /** Sink members of every sink group, by group id. */
  members: Map<string, NodeData[]>
  /** The group a sink belongs to, by sink id. */
  groupOf: Map<string, NodeData>
}

export function nodeKind(node: NodeData): NodeKind {
  const type = node.type_name || ''
  if (type === 'sinkGroup') return 'sinkGroup'
  if (type.startsWith('source')) return 'source'
  if (type.startsWith('transform')) return 'transform'
  if (type.startsWith('sink')) return 'sink'
  return 'other'
}

export function isSinkGroup(node: NodeData): boolean {
  return nodeKind(node) === 'sinkGroup'
}

/** Sinks and sink groups: nodes that produce no data of their own. */
export function isTerminal(node: NodeData): boolean {
  const kind = nodeKind(node)
  return kind === 'sink' || kind === 'sinkGroup'
}

/** Sources and transforms may carry a breakpoint. */
export function canHaveBreakpoint(node: NodeData): boolean {
  const kind = nodeKind(node)
  return kind === 'source' || kind === 'transform'
}

function push<K, V>(map: Map<K, V[]>, key: K, value: V) {
  const list = map.get(key)
  if (list) list.push(value)
  else map.set(key, [value])
}

/**
 * Index a node list. Links are derived from the inputs: an input's `link` is
 * the output port feeding it, whose `node` must be in the list for the link to
 * count (a reference the client has not resolved yet is ignored).
 */
export function buildGraph(nodes: NodeData[]): Graph {
  const byId = new Map<string, NodeData>()
  for (const node of nodes) byId.set(node._id, node)

  const links: Link[] = []
  const outgoing = new Map<string, Link[]>()
  const incoming = new Map<string, Link[]>()
  const outgoingByPort = new Map<string, Link[]>()
  for (const to of nodes) {
    for (const input of to.inputs || []) {
      const output = input.link
      const from = output?.node ? byId.get(output.node._id) : undefined
      if (!output || !from) continue
      const link: Link = { id: input._id, input, output, from, to }
      links.push(link)
      push(outgoing, from._id, link)
      push(incoming, to._id, link)
      push(outgoingByPort, output._id, link)
    }
  }

  const members = new Map<string, NodeData[]>()
  const groupOf = new Map<string, NodeData>()
  for (const node of nodes) {
    if (!isSinkGroup(node)) continue
    const list: NodeData[] = []
    for (const link of outgoing.get(node._id) || []) {
      if (nodeKind(link.to) !== 'sink') continue
      if (list.some((n) => n._id === link.to._id)) continue
      list.push(link.to)
      groupOf.set(link.to._id, node)
    }
    members.set(node._id, list)
  }

  return { nodes, byId, links, outgoing, incoming, outgoingByPort, members, groupOf }
}

export function upstreamNodes(graph: Graph, node: NodeData): NodeData[] {
  return (graph.incoming.get(node._id) || []).map((link) => link.from)
}

export function downstreamNodes(graph: Graph, node: NodeData): NodeData[] {
  return (graph.outgoing.get(node._id) || []).map((link) => link.to)
}

export function membersOf(graph: Graph, group: NodeData): NodeData[] {
  return graph.members.get(group._id) || []
}

/** The output port feeding a group's passthrough, for the tip highlight. */
export function passthroughSource(graph: Graph, port: OutputPortData): OutputPortData | null {
  const group = port.node ? graph.byId.get(port.node._id) : undefined
  if (!group || !isSinkGroup(group)) return null
  const index = group.outputs.findIndex((p) => p._id === port._id)
  const input = group.inputs[index]
  return input?.link ?? null
}
