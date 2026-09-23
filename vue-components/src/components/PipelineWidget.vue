<script setup lang="ts">
/**
 * The pipeline widget: the desktop tomviz pipeline strip as a Vue component.
 *
 * Nodes are laid out one row each in depth-first order (see `layout/`),
 * links are routed through the left gutter, and the selection is one of a
 * node, an output port or a link (identified by its input port). The
 * component owns no graph state: it renders `nodes`, reflects `activeNode`
 * and `tipPort`, and emits every change it wants made, including the link
 * a drag from an output square to an input dot asks for.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import {
  buildGraph,
  canLink,
  computeBrightSet,
  computeLayout,
  depthFirstOrder,
  membersOf,
  passthroughSource,
  pendingLink,
  portTypeColor,
  routeLinks,
  type InputPortData,
  type Link,
  type NodeData,
  type OutputPortData,
  type Point,
} from '@/layout'
import * as C from '@/layout/constants'
import LinkLayer from './LinkLayer.vue'
import NodeCard from './NodeCard.vue'
import PortShapes from './PortShapes.vue'
import type { ContextTarget, SelectionTarget } from './types'

const DRAG_THRESHOLD = 10
const INPUT_HIT_RADIUS = C.DotRadius + 3

const props = withDefaults(
  defineProps<{
    nodes: NodeData[]
    /** Id of the selected model: a node, an output port or an input port (link). */
    activeNode?: string[]
    /** Id of the output port new nodes attach to. */
    tipPort?: string | null
    /** Suppress mutations (deletion, double click, link dragging) while the graph runs. */
    locked?: boolean
    /** Focus mode: fade everything more than one hop from the selection. */
    dimming?: boolean
    /** How far dimmed elements fade toward the background, 0 to 1. */
    dimLevel?: number
    animateLinksOnHover?: boolean
    animateLinksOnSelection?: boolean
  }>(),
  {
    activeNode: () => [],
    tipPort: null,
    locked: false,
    dimming: false,
    dimLevel: 0.75,
    animateLinksOnHover: true,
    animateLinksOnSelection: true,
  },
)

const emit = defineEmits<{
  'update:activeNode': [ids: string[]]
  'toggle-expanded': [node: NodeData]
  'toggle-visibility': [node: NodeData]
  'toggle-breakpoint': [node: NodeData]
  'leave-group': [node: NodeData]
  'link-request': [request: { output: OutputPortData; input: InputPortData }]
  dblclick: [node: NodeData]
  contextmenu: [target: ContextTarget]
  delete: [target: SelectionTarget]
}>()

// ---- layout ----------------------------------------------------------------

const root = ref<HTMLElement | null>(null)
const canvas = ref<HTMLElement | null>(null)
const width = ref(300)
let observer: ResizeObserver | null = null

onMounted(() => {
  if (!root.value) return
  width.value = root.value.clientWidth || width.value
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver((entries) => {
      // Whole pixels only: a fractional width would size the link layer a
      // hair wider than the container and earn it a horizontal scrollbar.
      const w = Math.floor(entries[0]?.contentRect.width ?? 0)
      if (w) width.value = w
    })
    observer.observe(root.value)
  }
})
onBeforeUnmount(() => {
  observer?.disconnect()
  stopDrag()
})

const graph = computed(() => buildGraph(props.nodes || []))
const order = computed(() => depthFirstOrder(graph.value))
const layout = computed(() => computeLayout(graph.value, order.value, width.value))
const routing = computed(() => routeLinks(graph.value, layout.value))
const geometries = computed(() => layout.value.order.map((n) => layout.value.geometry.get(n._id)!))

// ---- selection ---------------------------------------------------------------

const selectedId = computed(() => props.activeNode?.[0] ?? null)

function findPort(id: string): OutputPortData | null {
  for (const node of props.nodes || []) {
    const port = node.outputs?.find((p) => p._id === id)
    if (port) return port
  }
  return null
}

function findInput(id: string): InputPortData | null {
  for (const node of props.nodes || []) {
    const input = node.inputs?.find((p) => p._id === id)
    if (input) return input
  }
  return null
}

const selection = computed<SelectionTarget | null>(() => {
  const id = selectedId.value
  if (!id) return null
  if (graph.value.byId.has(id)) return { kind: 'node', id }
  if (findPort(id)) return { kind: 'port', id }
  if (findInput(id)?.link) return { kind: 'link', id }
  return null
})

const selectedNodeId = computed(() =>
  selection.value?.kind === 'node' ? selection.value.id : null,
)
const selectedPortId = computed(() =>
  selection.value?.kind === 'port' ? selection.value.id : null,
)
const selectedLinkId = computed(() =>
  selection.value?.kind === 'link' ? selection.value.id : null,
)

/** The tip ring sits on the port feeding a group, and hides behind a selected link. */
const tipPortVisual = computed(() => {
  if (!props.tipPort || selectedLinkId.value) return null
  const port = findPort(props.tipPort)
  if (!port) return null
  const source = passthroughSource(graph.value, port)
  return (source ?? port)._id
})

const bright = computed(() =>
  props.dimming ? computeBrightSet(graph.value, selection.value) : null,
)

function select(target: SelectionTarget | null) {
  const ids = target ? [target.id] : []
  const current = props.activeNode ?? []
  if (ids.length === current.length && ids.every((id, i) => id === current[i])) return
  emit('update:activeNode', ids)
}

const selectNode = (node: NodeData) => select({ kind: 'node', id: node._id })
const selectPort = (port: OutputPortData) => select({ kind: 'port', id: port._id })
const selectLink = (link: Link | InputPortData) =>
  select({ kind: 'link', id: 'input' in link ? link.input._id : link._id })

// ---- hover -----------------------------------------------------------------

const hoveredLinkId = ref<string | null>(null)
const hoverLink = (link: Link | null) => (hoveredLinkId.value = link?.id ?? null)

// ---- drag to link ------------------------------------------------------------

interface DragState {
  port: OutputPortData
  origin: Point
  cursor: Point
  active: boolean
  target: InputPortData | null
}

const drag = ref<DragState | null>(null)
let suppressNextClick = false

function canvasPoint(event: { clientX: number; clientY: number }): Point {
  const rect = canvas.value?.getBoundingClientRect()
  return { x: event.clientX - (rect?.left ?? 0), y: event.clientY - (rect?.top ?? 0) }
}

function inputAt(point: Point): InputPortData | null {
  for (const g of geometries.value) {
    for (let i = 0; i < g.inputDots.length; i++) {
      const dot = g.inputDots[i]
      if (Math.hypot(dot.x - point.x, dot.y - point.y) <= INPUT_HIT_RADIUS) {
        return g.node.inputs[i] ?? null
      }
    }
  }
  return null
}

function onDragStart(port: OutputPortData, event: PointerEvent) {
  if (props.locked) return
  const origin = canvasPoint(event)
  drag.value = { port, origin, cursor: origin, active: false, target: null }
  window.addEventListener('pointermove', onDragMove)
  window.addEventListener('pointerup', onDragEnd)
  window.addEventListener('keydown', onDragKey)
}

function onDragMove(event: PointerEvent) {
  const state = drag.value
  if (!state) return
  state.cursor = canvasPoint(event)
  if (!state.active) {
    const distance =
      Math.abs(state.cursor.x - state.origin.x) + Math.abs(state.cursor.y - state.origin.y)
    if (distance < DRAG_THRESHOLD) return
    state.active = true
    suppressNextClick = true
  }
  const input = inputAt(state.cursor)
  state.target = input && canLink(graph.value, state.port, input) ? input : null
}

function onDragEnd() {
  const state = drag.value
  stopDrag()
  if (state?.active && state.target) {
    emit('link-request', { output: state.port, input: state.target })
  }
}

function onDragKey(event: KeyboardEvent) {
  if (event.key === 'Escape') stopDrag()
}

function stopDrag() {
  drag.value = null
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragEnd)
  window.removeEventListener('keydown', onDragKey)
}

const pending = computed(() => {
  const state = drag.value
  if (!state?.active) return null
  const owner = state.port.node ? layout.value.geometry.get(state.port.node._id) : undefined
  if (!owner) return null
  const index = owner.node.outputs.findIndex((p) => p._id === state.port._id)
  const source = owner.outputDots[index]
  if (!source) return null
  let target: Point | null = null
  if (state.target) {
    for (const g of geometries.value) {
      const i = g.node.inputs.findIndex((p) => p._id === state.target!._id)
      if (i >= 0) target = g.inputDots[i]
    }
  }
  return {
    ...pendingLink(routing.value, source, owner.showPorts, target, state.cursor),
    color: portTypeColor(state.port.port_type),
  }
})

const dropTargetId = computed(() => drag.value?.target?._id ?? null)

function onCanvasClick() {
  if (suppressNextClick) {
    suppressNextClick = false
    return
  }
  select(null)
}

// ---- keyboard --------------------------------------------------------------

interface Row {
  y: number
  target: SelectionTarget
}

/** Cards and links merged into one list ordered by their vertical position. */
const rows = computed<Row[]>(() => {
  const list: Row[] = []
  for (const item of layout.value.items) {
    const y = item.rect.y + item.rect.height / 2
    if (item.type === 'port' && item.port)
      list.push({ y, target: { kind: 'port', id: item.port._id } })
    else list.push({ y, target: { kind: 'node', id: item.node._id } })
  }
  for (const g of routing.value.links) {
    const ys = g.points.map((p) => p.y)
    list.push({
      y: (Math.min(...ys) + Math.max(...ys)) / 2,
      target: { kind: 'link', id: g.link.id },
    })
  }
  return list.sort((a, b) => a.y - b.y)
})

function navigate(direction: 1 | -1) {
  const list = rows.value
  if (!list.length) return
  const current = selection.value
  let index = current ? list.findIndex((r) => r.target.id === current.id) : -1
  if (index < 0) index = direction > 0 ? -1 : list.length
  const next = Math.min(list.length - 1, Math.max(0, index + direction))
  select(list[next].target)
}

function onKeydown(event: KeyboardEvent) {
  switch (event.key) {
    case 'ArrowDown':
      navigate(1)
      break
    case 'ArrowUp':
      navigate(-1)
      break
    case 'Delete':
    case 'Backspace':
      if (selection.value && !props.locked) emit('delete', selection.value)
      break
    case 'Escape':
      if (drag.value) stopDrag()
      else select(null)
      break
    default:
      return
  }
  event.preventDefault()
}

// ---- forwarding ------------------------------------------------------------

function onMenu(target: ContextTarget) {
  emit('contextmenu', target)
}

function onLinkMenu(link: Link, x: number, y: number) {
  emit('contextmenu', { kind: 'link', id: link.id, node: link.to, x, y })
}

function onDblclick(node: NodeData) {
  if (!props.locked) emit('dblclick', node)
}

function onLeaveGroup(node: NodeData) {
  if (!props.locked) emit('leave-group', node)
}

watch(
  () => props.nodes,
  () => {
    // A selection that no longer resolves (node removed) is dropped.
    if (selectedId.value && !selection.value) select(null)
  },
)

watch(
  () => props.locked,
  (locked) => {
    if (locked) stopDrag()
  },
)

defineExpose({ layout, routing })
</script>

<template>
  <div
    ref="root"
    class="tomviz-pipeline"
    :class="{ 'tomviz-pipeline--dragging': drag?.active }"
    :style="{ '--tv-dim-opacity': String(1 - dimLevel) }"
    tabindex="0"
    @click="onCanvasClick"
    @keydown="onKeydown"
  >
    <div ref="canvas" class="tomviz-pipeline__canvas" :style="{ height: `${layout.height}px` }">
      <NodeCard
        v-for="g in geometries"
        :key="g.node._id"
        :geometry="g"
        :members="membersOf(graph, g.node)"
        :selected="g.node._id === selectedNodeId"
        :selected-port-id="selectedPortId"
        :selected-member-id="selectedNodeId"
        :locked="locked"
        :bright="bright"
        @select="selectNode"
        @select-port="selectPort"
        @toggle-expanded="emit('toggle-expanded', $event)"
        @toggle-visibility="emit('toggle-visibility', $event)"
        @toggle-breakpoint="emit('toggle-breakpoint', $event)"
        @leave-group="onLeaveGroup"
        @menu="onMenu"
        @dblclick="onDblclick"
      />

      <LinkLayer
        :links="routing.links"
        :height="layout.height"
        :selected-link-id="selectedLinkId"
        :hovered-link-id="hoveredLinkId"
        :animate-on-hover="animateLinksOnHover"
        :animate-on-selection="animateLinksOnSelection"
        :bright="bright"
        :pending="pending"
        @select="selectLink"
        @hover="hoverLink"
        @menu="onLinkMenu"
      />

      <PortShapes
        v-for="g in geometries"
        :key="`ports-${g.node._id}`"
        :geometry="g"
        :members="membersOf(graph, g.node)"
        :selected-port-id="selectedPortId"
        :selected-link-id="selectedLinkId"
        :selected-member-id="selectedNodeId"
        :tip-port-id="tipPortVisual"
        :drop-target-id="dropTargetId"
        :bright="bright"
        :locked="locked"
        @select-port="selectPort"
        @select-link="selectLink"
        @select-member="selectNode"
        @select-node="selectNode"
        @drag-start="onDragStart"
        @menu="onMenu"
      />
    </div>
  </div>
</template>

<style scoped>
.tomviz-pipeline {
  --tv-surface: rgb(var(--v-theme-surface, 255, 255, 255));
  --tv-on-surface: rgb(var(--v-theme-on-surface, 0, 0, 0));
  --tv-highlight: rgb(var(--v-theme-primary, 25, 118, 210));
  --tv-tip: #e53935;
  position: relative;
  width: 100%;
  /* In a flex column host, take the remaining height so a click on the
     empty space below the strip still reaches the widget (deselect). */
  flex: 1 0 auto;
  outline: none;
  color: var(--tv-on-surface);
}
.tomviz-pipeline--dragging {
  cursor: crosshair;
  user-select: none;
}
.tomviz-pipeline:focus-visible {
  box-shadow: inset 0 0 0 1px var(--tv-highlight);
}
.tomviz-pipeline__canvas {
  position: relative;
  width: 100%;
  /* Nothing of the strip may scroll its container sideways: clip (not hide,
     which would make a scroll container) whatever pokes past the edges. */
  overflow-x: clip;
}
</style>
