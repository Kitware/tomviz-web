/**
 * The data the pipeline widget renders. These interfaces describe the
 * trame-dataclass models of the application (`NodeModel`, `InputPortModel`,
 * `OutputPortModel`, `ViewModel`), as the client sees them: plain reactive
 * objects whose fields carry the names of the tomviz_pipeline library.
 */

export type NodeState = 'New' | 'Stale' | 'Current'
export type NodeExecState = 'Idle' | 'Running' | 'Failed' | 'Canceled'
/** `tomviz_pipeline.DataLocation` values. */
export type DataLocation = 'none' | 'memory' | 'disk'
export type PersistenceMode = 'memory' | 'disk'

export type NodeKind = 'source' | 'transform' | 'sink' | 'sinkGroup' | 'other'

export interface ViewData {
  _id: string
  color: string
}

export interface OutputPortData {
  _id: string
  name: string
  port_type: string
  /** The owning node; resolves to the same object as in the node list. */
  node: NodeData | null
  has_data: boolean
  persistent: boolean
  persistence_mode: PersistenceMode | string
  data_location: DataLocation | string
}

export interface InputPortData {
  _id: string
  name: string
  accepted_types: string[]
  /** The output port feeding this input, or null when unlinked. */
  link: OutputPortData | null
  /** False when the link's effective type no longer suits this input. */
  link_valid?: boolean
}

export interface NodeData {
  _id: string
  /** The graph id, assigned in creation order. */
  node_id: number
  /** Schema-v2 type string: `source.reader`, `transform.python`, `sink.slice`, `sinkGroup`. */
  type_name: string
  label: string
  /** An `mdi-*` name, an image URL, or empty for the kind's default. */
  icon: string
  state: NodeState | string
  exec_state: NodeExecState | string
  breakpoint: boolean
  at_breakpoint: boolean
  progress_step: number
  progress_maximum: number
  progress_message: string
  expanded: boolean
  inputs: InputPortData[]
  outputs: OutputPortData[]
  /** Sinks only: the render view the sink draws in. */
  view?: ViewData | null
  /** Sinks only: whether the user wants the visualization shown. */
  Visibility?: boolean
}

export interface Point {
  x: number
  y: number
}

export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

export function rectRight(rect: Rect): number {
  return rect.x + rect.width
}

export function rectBottom(rect: Rect): number {
  return rect.y + rect.height
}

export function rectCenter(rect: Rect): Point {
  return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 }
}

export function rectContains(rect: Rect, point: Point): boolean {
  return (
    point.x >= rect.x &&
    point.x <= rectRight(rect) &&
    point.y >= rect.y &&
    point.y <= rectBottom(rect)
  )
}
