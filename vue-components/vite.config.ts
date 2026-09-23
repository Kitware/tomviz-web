import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

// The bundle is served by the trame module in src/tomviz_trame/widgets/module.
// Vue and Vuetify come from the trame client, so both stay external.
export default defineConfig({
  build: {
    sourcemap: true,
    lib: {
      entry: './src/main.ts',
      name: 'tomviz_widgets',
      formats: ['umd'],
      // package.json is type=module: name the UMD build .js ourselves.
      fileName: () => 'tomviz_widgets.umd.js',
      cssFileName: 'tomviz_widgets',
    },
    rollupOptions: {
      external: ['vue', 'vuetify'],
      output: {
        globals: {
          vue: 'Vue',
          vuetify: 'Vuetify',
        },
      },
    },
    outDir: '../src/tomviz_trame/widgets/module/serve',
    assetsDir: '.',
  },
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.spec.ts'],
  },
})
