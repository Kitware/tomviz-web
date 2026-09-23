<script setup lang="ts">
/**
 * One row of the strip: the node's header (icon, label, breakpoint, state,
 * menu, expand or visibility toggle) and, when expanded, one sub-card per
 * output port or, for a sink group, per member sink. The port shapes that
 * hang off the card are drawn by PortShapes, above the links.
 */
import { computed } from 'vue'

import {
  badgeColor,
  canHaveBreakpoint,
  css,
  nodeKind,
  portTypeColor,
  type BrightSet,
  type NodeData,
  type NodeGeometry,
  type OutputPortData,
  type Rect,
} from '@/layout'
import * as C from '@/layout/constants'
import NodeIcon from './NodeIcon.vue'
import TvIcon from './TvIcon.vue'
import type { ContextTarget, SelectionKind } from './types'

const props = defineProps<{
  geometry: NodeGeometry
  members: NodeData[]
  selected: boolean
  selectedPortId: string | null
  selectedMemberId: string | null
  locked: boolean
  bright: BrightSet | null
}>()

const emit = defineEmits<{
  select: [node: NodeData]
  'select-port': [port: OutputPortData]
  'toggle-expanded': [node: NodeData]
  'toggle-visibility': [node: NodeData]
  'toggle-breakpoint': [node: NodeData]
  'leave-group': [node: NodeData]
  menu: [target: ContextTarget]
  dblclick: [node: NodeData]
}>()

const nodeDim = computed(
  () => props.bright !== null && !props.bright.nodes.has(props.geometry.node._id),
)
const portDim = (port: OutputPortData) => props.bright !== null && !props.bright.ports.has(port._id)
const memberDim = (member: NodeData) => props.bright !== null && !props.bright.nodes.has(member._id)

const node = computed(() => props.geometry.node)
const kind = computed(() => nodeKind(node.value))
const color = computed(() => css(badgeColor(kind.value)))
const hasOutputs = computed(() => node.value.outputs.length > 0)
const showBreakpoint = computed(() => canHaveBreakpoint(node.value))
const running = computed(() => node.value.exec_state === 'Running')
const progress = computed(() => {
  const max = node.value.progress_maximum
  return max > 0 ? Math.min(100, (100 * node.value.progress_step) / max) : null
})

const stateIcon = computed(() => {
  switch (node.value.exec_state) {
    case 'Failed':
      return { icon: 'mdi-alert-circle', color: '#e53935', title: 'Failed' }
    case 'Canceled':
      return { icon: 'mdi-close-circle', color: '#e53935', title: 'Canceled' }
  }
  switch (node.value.state) {
    case 'Current':
      return { icon: 'mdi-check-circle-outline', color: '', title: 'Up to date' }
    case 'Stale':
      return { icon: 'mdi-help-circle-outline', color: '', title: 'Needs to run' }
  }
  return null
})

const px = (v: number) => `${v}px`

// Cards stretch to the container's right edge with CSS (left + right) rather
// than taking the layout's width, so a stale width measurement can never
// clip or overflow them; only the vertical positions come from the layout.
const style = computed(() => {
  const rect = props.geometry.rect
  return {
    left: px(rect.x),
    top: px(rect.y),
    right: px(C.Padding),
    height: px(rect.height),
    '--tv-badge': color.value,
  }
})

function subStyle(rect: Rect, accent: string) {
  const card = props.geometry.rect
  return {
    left: px(rect.x - card.x - 1.5),
    top: px(rect.y - card.y - 1.5),
    right: px(C.PortContentPad - 1.5),
    height: px(rect.height),
    '--tv-accent': accent,
  }
}

function menuAt(event: MouseEvent, kind: SelectionKind, id: string, target: NodeData) {
  emit('menu', { kind, id, node: target, x: event.clientX, y: event.clientY })
}

const breakpointTitle = computed(() =>
  node.value.at_breakpoint
    ? 'Resume execution'
    : node.value.breakpoint
      ? 'Remove breakpoint'
      : 'Create breakpoint',
)
</script>

<template>
  <div
    class="tv-card"
    :class="{
      'tv-card--selected': selected,
      'tv-card--collapsed': !geometry.showPorts && !geometry.showMembers,
      'tv-card--locked': locked,
      'tv-dim': nodeDim,
    }"
    :style="style"
    @click.stop="emit('select', node)"
    @dblclick.stop="emit('dblclick', node)"
    @contextmenu.prevent.stop="menuAt($event, 'node', node._id, node)"
  >
    <div class="tv-card__header">
      <NodeIcon :icon="node.icon" :kind="kind" />
      <span
        v-if="kind === 'sink' && node.view"
        class="tv-view-chip"
        :style="{ background: node.view.color }"
        title="View"
      />
      <span class="tv-card__label" :title="node.label">{{ node.label }}</span>

      <button
        v-if="showBreakpoint"
        class="tv-btn"
        :class="{ 'tv-btn--ghost': !node.breakpoint && !node.at_breakpoint }"
        :title="breakpointTitle"
        @click.stop="emit('toggle-breakpoint', node)"
      >
        <v-icon v-if="node.at_breakpoint" icon="mdi-play" size="16" />
        <TvIcon v-else name="breakpoint" />
      </button>

      <span class="tv-slot" :title="stateIcon?.title">
        <v-progress-circular v-if="running" indeterminate size="14" width="2" />
        <v-icon
          v-else-if="stateIcon"
          :icon="stateIcon.icon"
          size="16"
          :color="stateIcon.color || undefined"
        />
      </span>

      <button class="tv-btn" title="Menu" @click.stop="menuAt($event, 'node', node._id, node)">
        <v-icon icon="mdi-dots-vertical" size="16" />
      </button>
      <span class="tv-sep" />
      <button
        v-if="hasOutputs"
        class="tv-btn"
        :title="node.expanded ? 'Collapse' : 'Expand'"
        @click.stop="emit('toggle-expanded', node)"
      >
        <v-icon :icon="node.expanded ? 'mdi-chevron-down' : 'mdi-chevron-right'" size="16" />
      </button>
      <button
        v-else-if="kind === 'sink'"
        class="tv-btn"
        :title="node.Visibility ? 'Hide' : 'Show'"
        @click.stop="emit('toggle-visibility', node)"
      >
        <v-icon :icon="node.Visibility ? 'mdi-eye-outline' : 'mdi-eye-off-outline'" size="16" />
      </button>
      <span v-else class="tv-slot" />
    </div>

    <v-progress-linear
      v-if="running"
      class="tv-card__progress"
      :model-value="progress ?? 0"
      :indeterminate="progress === null"
      height="2"
      :title="node.progress_message"
    />

    <div
      v-for="(port, i) in geometry.showPorts ? node.outputs : []"
      :key="port._id"
      class="tv-subcard tv-subcard--port"
      :class="{ 'tv-subcard--selected': port._id === selectedPortId, 'tv-dim': portDim(port) }"
      :style="subStyle(geometry.portCards[i], css(portTypeColor(port.port_type)))"
      :title="`Output port: ${port.port_type}`"
      @click.stop="emit('select-port', port)"
      @dblclick.stop
      @contextmenu.prevent.stop="menuAt($event, 'port', port._id, node)"
    >
      <span class="tv-subcard__label">{{ port.name }}</span>
      <button class="tv-btn" title="Menu" @click.stop="menuAt($event, 'port', port._id, node)">
        <v-icon icon="mdi-dots-vertical" size="16" />
      </button>
    </div>

    <div
      v-for="(member, i) in geometry.showMembers ? members : []"
      :key="member._id"
      class="tv-subcard tv-subcard--member"
      :class="{
        'tv-subcard--selected': member._id === selectedMemberId,
        'tv-dim': memberDim(member),
      }"
      :style="subStyle(geometry.memberCards[i], css(badgeColor('sink')))"
      @click.stop="emit('select', member)"
      @dblclick.stop="emit('dblclick', member)"
      @contextmenu.prevent.stop="menuAt($event, 'node', member._id, member)"
    >
      <NodeIcon :icon="member.icon" kind="sink" />
      <span
        v-if="member.view"
        class="tv-view-chip"
        :style="{ background: member.view.color }"
        title="View"
      />
      <span class="tv-subcard__label" :title="member.label">{{ member.label }}</span>
      <button
        class="tv-btn"
        title="Leave group"
        :disabled="locked"
        @click.stop="emit('leave-group', member)"
      >
        <TvIcon name="icon_leave" :size="14" />
      </button>
      <button class="tv-btn" title="Menu" @click.stop="menuAt($event, 'node', member._id, member)">
        <v-icon icon="mdi-dots-vertical" size="16" />
      </button>
      <span class="tv-sep" />
      <button
        class="tv-btn"
        :title="member.Visibility ? 'Hide' : 'Show'"
        @click.stop="emit('toggle-visibility', member)"
      >
        <v-icon :icon="member.Visibility ? 'mdi-eye-outline' : 'mdi-eye-off-outline'" size="16" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.tv-card {
  position: absolute;
  box-sizing: border-box;
  border: 1.5px solid var(--tv-badge);
  border-radius: 4px;
  background: color-mix(in srgb, var(--tv-badge) 5%, var(--tv-surface));
  color: var(--tv-on-surface);
  font-size: 12px;
  line-height: 1;
  user-select: none;
  cursor: default;
}
.tv-card--selected {
  background: color-mix(in srgb, var(--tv-badge) 30%, var(--tv-surface));
}
.tv-card__header {
  display: flex;
  align-items: center;
  box-sizing: border-box;
  height: 29px;
  padding: 0 4px 0 6px;
  gap: 2px;
  border-radius: 2.5px 2.5px 0 0;
}
.tv-card--selected .tv-card__header {
  background: var(--tv-badge);
  color: #fff;
}
/* A collapsed card is all header: fill it entirely (no tinted strip below). */
.tv-card--collapsed .tv-card__header {
  height: 100%;
  border-radius: 2.5px;
}
.tv-card__label {
  flex: 1;
  min-width: 0;
  margin-left: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tv-card__progress {
  position: absolute;
  left: 0;
  right: 0;
  top: 27px;
}
.tv-btn,
.tv-slot {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  border: 0;
  border-radius: 2px;
  background: none;
  color: inherit;
  font: inherit;
}
.tv-btn {
  cursor: pointer;
}
.tv-btn:hover {
  background: color-mix(in srgb, currentColor 15%, transparent);
}
.tv-btn--ghost {
  opacity: 0;
}
.tv-card:hover .tv-btn--ghost {
  opacity: 0.25;
}
.tv-sep {
  flex: none;
  width: 1px;
  height: 20px;
  margin: 0 3px;
  background: currentColor;
  opacity: 0.5;
}
.tv-subcard {
  position: absolute;
  display: flex;
  align-items: center;
  box-sizing: border-box;
  padding: 0 2px 0 2px;
  gap: 2px;
  border: 1.5px solid var(--tv-accent);
  border-radius: 3px;
  background: var(--tv-surface);
  color: var(--tv-on-surface);
  font-size: 11px;
}
.tv-subcard--port {
  /* The icon square at the left edge is drawn by PortShapes. */
  padding-left: 24px;
}
.tv-subcard--selected {
  background: var(--tv-accent);
  color: #fff;
}
.tv-subcard--selected::after {
  content: '';
  position: absolute;
  inset: -4px;
  border: 2px solid var(--tv-highlight);
  border-radius: 6px;
  pointer-events: none;
}
.tv-subcard__label {
  flex: 1;
  min-width: 0;
  margin-left: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tv-view-chip {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.tv-dim {
  opacity: var(--tv-dim-opacity, 0.25);
}
.tv-dim .tv-dim {
  opacity: 1; /* a dimmed card already fades its sub-cards */
}
</style>
