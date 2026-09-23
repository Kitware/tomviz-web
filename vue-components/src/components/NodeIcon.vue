<script setup lang="ts">
/**
 * A node's icon: an `mdi-*` name, an image URL, or the kind's default.
 */
import { computed } from 'vue'

import type { NodeKind } from '@/layout'

const DEFAULT_ICONS: Record<NodeKind, string> = {
  source: 'mdi-database-outline',
  transform: 'mdi-function-variant',
  sink: 'mdi-eye-outline',
  sinkGroup: 'mdi-layers-triple-outline',
  other: 'mdi-cube-outline',
}

const props = withDefaults(defineProps<{ icon?: string; kind: NodeKind; size?: number }>(), {
  icon: '',
  size: 16,
})

const isImage = computed(() => Boolean(props.icon) && !props.icon.startsWith('mdi-'))
const mdi = computed(() => (props.icon && !isImage.value ? props.icon : DEFAULT_ICONS[props.kind]))
</script>

<template>
  <img v-if="isImage" class="tv-node-icon" :src="icon" :width="size" :height="size" alt="" />
  <v-icon v-else class="tv-node-icon" :icon="mdi" :size="size" />
</template>

<style scoped>
.tv-node-icon {
  display: block;
  flex: none;
}
</style>
