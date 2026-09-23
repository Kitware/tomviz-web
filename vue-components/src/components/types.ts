import type { NodeData } from '@/layout'

export type SelectionKind = 'node' | 'port' | 'link'

/** What is selected: a node, an output port, or a link (by its input port). */
export interface SelectionTarget {
  kind: SelectionKind
  id: string
}

export interface ContextTarget extends SelectionTarget {
  node: NodeData
  x: number
  y: number
}

export interface Selection {
  target: SelectionTarget | null
  nodeId: string | null
  portId: string | null
  linkId: string | null
}
