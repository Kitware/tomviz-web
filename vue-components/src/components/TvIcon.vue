<script setup lang="ts">
import { computed } from 'vue'

import { iconMarkup } from '@/icons'

const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 16 })
const markup = computed(() => iconMarkup(props.name))
const style = computed(() => ({ width: `${props.size}px`, height: `${props.size}px` }))
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -- bundled, trusted SVG markup -->
  <span class="tv-icon" :style="style" v-html="markup" />
</template>

<style scoped>
.tv-icon {
  display: inline-block;
  flex: none;
  line-height: 0;
}
.tv-icon :deep(svg) {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
