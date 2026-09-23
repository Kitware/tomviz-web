/// <reference types="vite/client" />

declare module 'vue' {
  export interface GlobalComponents {
    VIcon: (typeof import('vuetify/components'))['VIcon']
    VProgressCircular: (typeof import('vuetify/components'))['VProgressCircular']
    VProgressLinear: (typeof import('vuetify/components'))['VProgressLinear']
  }
}

export {}
