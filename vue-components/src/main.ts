import type { App } from 'vue'

import components from './components'

export function install(app: App) {
  for (const [name, component] of Object.entries(components)) {
    app.component(name, component)
  }
}

export * from './layout'
export type { ContextTarget, SelectionTarget } from './components/types'
