/**
 * The pipelines of the desktop PipelineStripWidgetDemo, as the data the
 * widget receives. Port specs read `name:Type`.
 */
import type { InputPortData, NodeData, OutputPortData, ViewData } from '@/layout/types'

export const VIEW: ViewData = { _id: 'view1', color: '#ff0000' }

export class GraphBuilder {
  nodes: NodeData[] = []
  private nextNode = 1
  private nextPort = 1

  node(
    type_name: string,
    label: string,
    inputs: string[] = [],
    outputs: string[] = [],
    extra: Partial<NodeData> = {},
  ): NodeData {
    const id = this.nextNode++
    const node: NodeData = {
      _id: `n${id}`,
      node_id: id,
      type_name,
      label,
      icon: '',
      state: 'New',
      exec_state: 'Idle',
      breakpoint: false,
      at_breakpoint: false,
      progress_step: 0,
      progress_maximum: 0,
      progress_message: '',
      expanded: false,
      inputs: [],
      outputs: [],
      ...extra,
    }
    node.inputs = inputs.map((spec): InputPortData => {
      const [name, type] = spec.split(':')
      return { _id: `p${this.nextPort++}`, name, accepted_types: [type ?? 'ImageData'], link: null }
    })
    node.outputs = outputs.map((spec): OutputPortData => {
      const [name, type] = spec.split(':')
      return {
        _id: `p${this.nextPort++}`,
        name,
        port_type: type ?? 'ImageData',
        node,
        has_data: false,
        persistent: true,
        persistence_mode: 'memory',
        data_location: 'none',
      }
    })
    this.nodes.push(node)
    return node
  }

  source(label: string, outputs = ['volume:ImageData'], extra: Partial<NodeData> = {}) {
    return this.node('source.reader', label, [], outputs, extra)
  }

  transform(
    label: string,
    inputs = ['volume:ImageData'],
    outputs = ['volume:ImageData'],
    extra: Partial<NodeData> = {},
  ) {
    return this.node('transform.python', label, inputs, outputs, extra)
  }

  sink(label: string, inputs = ['volume:ImageData'], type = 'sink.outline') {
    return this.node(type, label, inputs, [], { view: VIEW, Visibility: true })
  }

  group(label = 'Visualizations', passthrough = ['volume:ImageData']) {
    return this.node('sinkGroup', label, passthrough, passthrough)
  }

  link(from: NodeData, output: string, to: NodeData, input: string) {
    const out = from.outputs.find((p) => p.name === output)
    const inp = to.inputs.find((p) => p.name === input)
    if (!out || !inp) throw new Error(`No such port: ${output} -> ${input}`)
    inp.link = out
    return this
  }

  /** Link the first output of `from` to the first input of `to`. */
  chain(from: NodeData, to: NodeData) {
    return this.link(from, from.outputs[0].name, to, to.inputs[0].name)
  }
}

export function linear() {
  const b = new GraphBuilder()
  const src = b.source('sample.vti')
  const gauss = b.transform('Gaussian Filter')
  const thresh = b.transform('Threshold')
  const contour = b.transform('Contour')
  const stats = b.sink('Volume Stats', ['volume:ImageData'], 'sink.volumeStats')
  b.chain(src, gauss).chain(gauss, thresh).chain(thresh, contour).chain(contour, stats)
  return b.nodes
}

export function multiOutput() {
  const b = new GraphBuilder()
  const src = b.source('Load Data')
  const segment = b.transform(
    'Segment',
    ['volume:ImageData'],
    ['volume:ImageData', 'table:Table', 'out2:Molecule'],
  )
  const stats = b.sink('Stats', ['volume:ImageData'], 'sink.volumeStats')
  const plot = b.sink('Plot', ['table:Table'], 'sink.plot')
  const viewer = b.sink('Molecule Viewer', ['molecule:Molecule'], 'sink.molecule')
  b.chain(src, segment)
  b.link(segment, 'volume', stats, 'volume')
  b.link(segment, 'table', plot, 'table')
  b.link(segment, 'out2', viewer, 'molecule')
  return b.nodes
}

export function fanIn() {
  const b = new GraphBuilder()
  const a = b.source('Source A')
  const c = b.source('Source B')
  const merge = b.transform('Merge', ['volA:ImageData', 'volB:ImageData'], ['merged:ImageData'])
  const normalize = b.transform('Normalize')
  const exp = b.sink('Export')
  b.link(a, 'volume', merge, 'volA')
  b.link(c, 'volume', merge, 'volB')
  b.chain(merge, normalize).chain(normalize, exp)
  return b.nodes
}

export function fanOut() {
  const b = new GraphBuilder()
  const src = b.source('sample.vti')
  const gauss = b.transform('Gaussian Filter')
  const median = b.transform('Median Filter')
  const compare = b.transform(
    'Compare',
    ['volA:ImageData', 'volB:ImageData'],
    ['diff:ImageData', 'stats:Table'],
  )
  const diff = b.sink('Diff Viewer')
  const err = b.sink('Error Plot', ['table:Table'], 'sink.plot')
  b.chain(src, gauss).chain(src, median)
  b.link(gauss, 'volume', compare, 'volA')
  b.link(median, 'volume', compare, 'volB')
  b.link(compare, 'diff', diff, 'volume')
  b.link(compare, 'stats', err, 'table')
  return b.nodes
}

export function complex() {
  const b = new GraphBuilder()
  const src = b.source('tilt_series.mrc', ['volume:TiltSeries'])
  const denoise = b.transform('Denoise (BM3D)')
  const segment = b.transform('Segment', ['volume:ImageData'], ['labels:ImageData', 'stats:Table'])
  const align = b.transform('Align Tilt')
  const recon = b.transform('Reconstruct (SIRT)', ['volume:ImageData'], ['volume:Volume'])
  const exp = b.sink('Export Volume')
  const plot = b.sink('Segmentation Plot', ['table:Table'], 'sink.plot')
  b.chain(src, denoise).chain(denoise, segment).chain(denoise, align)
  b.chain(align, recon).chain(recon, exp)
  b.link(segment, 'stats', plot, 'table')
  return b.nodes
}

export function tomography() {
  const b = new GraphBuilder()
  const src = b.source('experiment.tiff', ['volume:TiltSeries'])
  const recon = b.transform('Reconstruction', ['volume:TiltSeries'], ['volume:Volume'])
  const pad = b.transform('Pad')
  const align = b.transform('Align')
  const denoise = b.transform('Denoise', ['volume:ImageData'], ['volume:Volume', 'metrics:Table'])
  const plot = b.sink('Plot', ['table:Table'], 'sink.plot')
  const outline = b.sink('Outline')
  const slice = b.sink('Slice', ['volume:ImageData'], 'sink.slice')
  const volume = b.sink('Volume', ['volume:ImageData'], 'sink.volume')
  b.chain(src, recon).chain(recon, pad).chain(pad, align).chain(align, denoise)
  b.link(denoise, 'metrics', plot, 'table')
  b.link(denoise, 'volume', outline, 'volume')
  b.link(denoise, 'volume', slice, 'volume')
  b.link(denoise, 'volume', volume, 'volume')
  return b.nodes
}

export function sinkGroup() {
  const b = new GraphBuilder()
  const a = b.source('sample_A.vti')
  const gauss = b.transform('Gaussian Filter')
  const group = b.group()
  const outline = b.sink('Outline')
  const slice = b.sink('Slice', ['volume:ImageData'], 'sink.slice')
  const volume = b.sink('Volume', ['volume:ImageData'], 'sink.volume')
  const c = b.source('sample_B.vti')
  const median = b.transform('Median Filter')
  const outline2 = b.sink('Outline 2')
  const slice2 = b.sink('Slice 2', ['volume:ImageData'], 'sink.slice')
  const volume2 = b.sink('Volume 2', ['volume:ImageData'], 'sink.volume')
  b.chain(a, gauss).chain(gauss, group)
  b.chain(group, outline).chain(group, slice).chain(group, volume)
  b.chain(c, median)
  b.chain(median, outline2).chain(median, slice2).chain(median, volume2)
  return b.nodes
}

export function empty(): NodeData[] {
  return []
}

export const FIXTURES = {
  linear,
  multiOutput,
  fanIn,
  fanOut,
  complex,
  tomography,
  sinkGroup,
  empty,
}

export function byLabel(nodes: NodeData[], label: string): NodeData {
  const node = nodes.find((n) => n.label === label)
  if (!node) throw new Error(`No node labelled ${label}`)
  return node
}
