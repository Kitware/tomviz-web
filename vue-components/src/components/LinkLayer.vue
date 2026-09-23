<script setup lang="ts">
/**
 * The SVG layer of routed links: a wide transparent corridor makes each
 * one clickable, the selected one gets a halo, the hovered and selected
 * links can flow with marching ants, and a link being dragged is drawn on
 * top (dashed until it reaches an input that accepts it).
 */
import { computed } from 'vue'

import {
  css,
  invertColor,
  type BrightSet,
  type Link,
  type LinkGeometry,
  type PendingLink,
  type RGB,
} from '@/layout'

const props = defineProps<{
  links: LinkGeometry[]
  height: number
  selectedLinkId: string | null
  hoveredLinkId: string | null
  animateOnHover: boolean
  animateOnSelection: boolean
  bright: BrightSet | null
  pending: (PendingLink & { color: RGB }) | null
}>()

const emit = defineEmits<{
  select: [link: Link]
  hover: [link: Link | null]
  menu: [link: Link, x: number, y: number]
}>()

const isSelected = (g: LinkGeometry) => g.link.id === props.selectedLinkId
const isHovered = (g: LinkGeometry) => g.link.id === props.hoveredLinkId
const isDim = (g: LinkGeometry) => props.bright !== null && !props.bright.links.has(g.link.id)

/** Hovered and selected links draw last, on top of the others. */
const ordered = computed(() => {
  const plain = props.links.filter((g) => !isSelected(g) && !isHovered(g))
  const top = props.links.filter((g) => isSelected(g) || isHovered(g))
  return [...plain, ...top]
})

const selected = computed(() => props.links.find(isSelected) ?? null)

function strokeOf(g: LinkGeometry) {
  return css(isSelected(g) ? invertColor(g.color) : g.color)
}

function animated(g: LinkGeometry) {
  return (isHovered(g) && props.animateOnHover) || (isSelected(g) && props.animateOnSelection)
}
</script>

<template>
  <!-- No viewBox: user units are pixels whatever the box is, and the box
       follows the container's width so it never overflows it. -->
  <svg class="tv-links" :height="height">
    <g v-if="selected" class="tv-halo">
      <path :d="selected.path" class="tv-halo__outer" />
      <path :d="selected.path" class="tv-halo__inner" />
    </g>
    <g v-for="g in ordered" :key="g.link.id" :class="{ 'tv-dim': isDim(g) }">
      <path
        class="tv-link"
        :class="{ 'tv-link--ants': animated(g) }"
        :d="g.path"
        :stroke="strokeOf(g)"
      />
      <path
        class="tv-link-hit"
        :d="g.path"
        @click.stop="emit('select', g.link)"
        @mouseenter="emit('hover', g.link)"
        @mouseleave="emit('hover', null)"
        @contextmenu.prevent.stop="emit('menu', g.link, $event.clientX, $event.clientY)"
      >
        <title>Link</title>
      </path>
    </g>
    <path
      v-if="pending"
      class="tv-link tv-link--pending"
      :class="{ 'tv-link--dashed': !pending.valid }"
      :d="pending.path"
      :stroke="css(pending.color)"
    />
  </svg>
</template>

<style scoped>
.tv-links {
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  overflow: visible;
  pointer-events: none;
}
.tv-link,
.tv-link-hit,
.tv-halo__outer,
.tv-halo__inner {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.tv-link {
  stroke-width: 3;
}
.tv-link--ants {
  stroke-dasharray: 3 1.5;
  animation: tv-march 0.5s linear infinite;
}
.tv-link--dashed {
  stroke-dasharray: 6 4;
}
.tv-link-hit {
  stroke: transparent;
  stroke-width: 8;
  pointer-events: stroke;
  cursor: pointer;
}
.tv-halo__outer {
  stroke: var(--tv-highlight);
  stroke-width: 10.5;
}
.tv-halo__inner {
  stroke: var(--tv-surface);
  stroke-width: 7.5;
}
.tv-dim {
  opacity: var(--tv-dim-opacity, 0.25);
}
@keyframes tv-march {
  from {
    stroke-dashoffset: 4.5;
  }
  to {
    stroke-dashoffset: 0;
  }
}
</style>
