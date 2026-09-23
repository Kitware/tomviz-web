<script setup lang="ts">
/**
 * The port shapes of one node, drawn above the links: input dots on the top
 * edge, output squares (a group's join circles) below the card or the icon
 * squares of expanded port cards, and a collapsed group's member circles.
 * Dragging from an output square starts a link.
 */
import { computed } from 'vue'

import {
  badgeColor,
  css,
  invertColor,
  isSinkGroup,
  portTypeColor,
  type BrightSet,
  type InputPortData,
  type NodeData,
  type NodeGeometry,
  type OutputPortData,
} from '@/layout'
import * as C from '@/layout/constants'
import { portTypeIcon } from '@/icons'
import NodeIcon from './NodeIcon.vue'
import TvIcon from './TvIcon.vue'
import type { ContextTarget } from './types'

const props = defineProps<{
  geometry: NodeGeometry
  members: NodeData[]
  selectedPortId: string | null
  selectedLinkId: string | null
  selectedMemberId: string | null
  /** The tip port to ring in red, already redirected out of groups. */
  tipPortId: string | null
  /** The input a dragged link would land on. */
  dropTargetId: string | null
  bright: BrightSet | null
  locked: boolean
}>()

const emit = defineEmits<{
  'select-port': [port: OutputPortData]
  'select-link': [input: InputPortData]
  'select-member': [member: NodeData]
  'select-node': [node: NodeData]
  'drag-start': [port: OutputPortData, event: PointerEvent]
  menu: [target: ContextTarget]
}>()

const node = computed(() => props.geometry.node)
const group = computed(() => isSinkGroup(node.value))
const px = (v: number) => `${v}px`

function at(x: number, y: number, size: number) {
  return { left: px(x - size / 2), top: px(y - size / 2), width: px(size), height: px(size) }
}

const nodeDim = computed(() => props.bright !== null && !props.bright.nodes.has(node.value._id))
const portDim = (port: OutputPortData) => props.bright !== null && !props.bright.ports.has(port._id)
const inputDim = (input: InputPortData) =>
  props.bright !== null && (input.link ? !props.bright.links.has(input._id) : nodeDim.value)
const memberDim = (member: NodeData) => props.bright !== null && !props.bright.nodes.has(member._id)

function inputColor(input: InputPortData) {
  const type = input.link ? input.link.port_type : input.accepted_types[0]
  const color = portTypeColor(type)
  return css(input._id === props.selectedLinkId ? invertColor(color) : color)
}

function inputTitle(input: InputPortData) {
  const base = `Input port: ${input.name} (${input.accepted_types.join(', ')})`
  return input.link && input.link_valid === false
    ? `${base}: does not accept ${input.link.port_type}`
    : base
}

const squares = computed(() =>
  node.value.outputs.map((port, i) => {
    const point = props.geometry.outputDots[i]
    const rect = props.geometry.showPorts
      ? {
          left: px(point.x),
          top: px(point.y - C.OutputSquareEdge / 2),
          width: px(C.OutputSquareEdge),
          height: px(C.OutputSquareEdge),
        }
      : at(point.x, point.y, C.OutputSquareEdge)
    return { port, style: { ...rect, '--tv-accent': css(portTypeColor(port.port_type)) } }
  }),
)

function badges(port: OutputPortData) {
  if (group.value) return []
  const list: { name: string; corner: string; title: string }[] = []
  if (port.persistent) list.push({ name: 'port_persistent_pin', corner: 'tr', title: 'Persistent' })
  if (port.data_location === 'memory')
    list.push({ name: 'port_data_ram', corner: 'br', title: 'Data in memory' })
  else if (port.data_location === 'disk')
    list.push({ name: 'port_data_disk', corner: 'br', title: 'Data on disk' })
  return list
}

function menuAt(event: MouseEvent, kind: 'node' | 'port' | 'link', id: string, target: NodeData) {
  emit('menu', { kind, id, node: target, x: event.clientX, y: event.clientY })
}

function clickPort(port: OutputPortData) {
  // A group's join circles are not selectable on their own.
  if (group.value) emit('select-node', node.value)
  else emit('select-port', port)
}

function startDrag(port: OutputPortData, event: PointerEvent) {
  if (props.locked || event.button !== 0) return
  emit('drag-start', port, event)
}
</script>

<template>
  <template v-for="(input, i) in node.inputs" :key="input._id">
    <span
      class="tv-dot"
      :class="{
        'tv-dot--linked': input.link,
        'tv-dot--invalid': input.link && input.link_valid === false,
        'tv-dot--target': input._id === dropTargetId,
        'tv-dim': inputDim(input),
      }"
      :style="{
        ...at(geometry.inputDots[i].x, geometry.inputDots[i].y, 2 * C.DotRadius),
        '--tv-accent': inputColor(input),
      }"
      :title="inputTitle(input)"
      @click.stop="input.link && emit('select-link', input)"
      @contextmenu.prevent.stop="input.link && menuAt($event, 'link', input._id, node)"
    />
  </template>

  <template v-if="geometry.showPorts || geometry.hasBottomDots">
    <span
      v-for="{ port, style } in squares"
      :key="port._id"
      class="tv-square"
      :class="{
        'tv-square--round': group,
        'tv-square--selected': port._id === selectedPortId,
        'tv-square--tip': port._id === tipPortId,
        'tv-dim': portDim(port),
      }"
      :style="style"
      :title="group ? 'Drag to a sink input to join the group' : `Output port: ${port.port_type}`"
      @click.stop="clickPort(port)"
      @pointerdown="startDrag(port, $event)"
      @contextmenu.prevent.stop="
        group ? menuAt($event, 'node', node._id, node) : menuAt($event, 'port', port._id, node)
      "
    >
      <TvIcon :name="group ? 'icon_join' : portTypeIcon(port.port_type)" />
      <span
        v-for="badge in badges(port)"
        :key="badge.name"
        class="tv-badge"
        :class="`tv-badge--${badge.corner}`"
        :title="badge.title"
      >
        <TvIcon :name="badge.name" :size="10" />
      </span>
    </span>
  </template>

  <template v-if="group && !geometry.showMembers">
    <span
      v-for="(member, i) in members"
      :key="member._id"
      class="tv-square tv-square--round tv-member"
      :class="{
        'tv-square--selected': member._id === selectedMemberId,
        'tv-dim': memberDim(member),
      }"
      :style="{
        ...at(geometry.memberDots[i].x, geometry.memberDots[i].y, C.OutputSquareEdge),
        '--tv-accent': css(badgeColor('sink')),
      }"
      :title="member.label"
      @click.stop="emit('select-member', member)"
      @contextmenu.prevent.stop="menuAt($event, 'node', member._id, member)"
    >
      <NodeIcon :icon="member.icon" kind="sink" :size="14" />
      <span v-if="member.view" class="tv-member__view" :style="{ background: member.view.color }" />
    </span>
  </template>
</template>

<style scoped>
.tv-dot,
.tv-square {
  position: absolute;
  box-sizing: border-box;
  border: 1.5px solid var(--tv-accent);
  background: var(--tv-surface);
  color: var(--tv-accent);
}
.tv-dot {
  border-radius: 50%;
}
.tv-dot--linked {
  cursor: pointer;
}
/* An input whose link stopped matching types: an X instead of the dot. */
.tv-dot--invalid {
  border-color: transparent;
  background: none;
}
.tv-dot--invalid::before,
.tv-dot--invalid::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  width: 12px;
  height: 2px;
  margin: -1px 0 0 -6px;
  border-radius: 1px;
  background: var(--tv-accent);
}
.tv-dot--invalid::before {
  transform: rotate(45deg);
}
.tv-dot--invalid::after {
  transform: rotate(-45deg);
}
.tv-dot--target {
  background: var(--tv-accent);
  outline: 2px solid var(--tv-highlight);
  outline-offset: 2px;
}
.tv-square {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  cursor: pointer;
  touch-action: none;
}
.tv-square--round {
  border-radius: 50%;
}
.tv-square--selected {
  background: var(--tv-accent);
  color: #fff;
  outline: 2px solid var(--tv-highlight);
  outline-offset: 2px;
}
.tv-square--tip:not(.tv-square--selected) {
  outline: 2px solid var(--tv-tip);
  outline-offset: 2px;
}
.tv-badge {
  position: absolute;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  width: 12px;
  height: 12px;
  border: 0.5px solid var(--tv-accent);
  border-radius: 50%;
  background: var(--tv-surface);
  color: var(--tv-accent);
}
.tv-badge--tr {
  top: -7.5px;
  right: -7.5px;
}
.tv-badge--br {
  bottom: -7.5px;
  right: -7.5px;
}
.tv-member__view {
  position: absolute;
  right: -3px;
  bottom: -3px;
  width: 7px;
  height: 7px;
  border: 1px solid var(--tv-surface);
  border-radius: 2px;
}
.tv-dim {
  opacity: var(--tv-dim-opacity, 0.25);
}
</style>
