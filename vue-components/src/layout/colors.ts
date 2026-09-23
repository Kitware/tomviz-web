import type { NodeKind } from './types'

export interface RGB {
  r: number
  g: number
  b: number
}

/** Card chrome color by node kind (the desktop's badgeColor). */
export const BADGE_COLORS: Record<NodeKind, RGB> = {
  source: { r: 76, g: 175, b: 80 },
  sinkGroup: { r: 255, g: 100, b: 30 },
  transform: { r: 33, g: 150, b: 243 },
  sink: { r: 255, g: 152, b: 0 },
  other: { r: 158, g: 158, b: 158 },
}

/** Port, dot and link color by port type (the desktop's portTypeColor). */
export const PORT_TYPE_COLORS: Record<string, RGB> = {
  ImageData: { r: 158, g: 118, b: 47 },
  TiltSeries: { r: 57, g: 73, b: 171 },
  Volume: { r: 171, g: 71, b: 188 },
  LabelMap: { r: 76, g: 175, b: 80 },
  Table: { r: 0, g: 172, b: 172 },
  Molecule: { r: 194, g: 60, b: 108 },
  Image: { r: 120, g: 144, b: 56 },
}

export const DEFAULT_COLOR: RGB = { r: 158, g: 158, b: 158 }

export function badgeColor(kind: NodeKind): RGB {
  return BADGE_COLORS[kind] ?? DEFAULT_COLOR
}

export function portTypeColor(portType: string | undefined): RGB {
  return (portType && PORT_TYPE_COLORS[portType]) || DEFAULT_COLOR
}

export function invertColor(color: RGB): RGB {
  return { r: 255 - color.r, g: 255 - color.g, b: 255 - color.b }
}

export function css(color: RGB, alpha = 1): string {
  return alpha >= 1
    ? `rgb(${color.r}, ${color.g}, ${color.b})`
    : `rgba(${color.r}, ${color.g}, ${color.b}, ${alpha})`
}

/** Linear blend of `color` toward `background` by `amount` in [0, 1]. */
export function blend(color: RGB, background: RGB, amount: number): RGB {
  const t = Math.min(1, Math.max(0, amount))
  return {
    r: Math.round(color.r + (background.r - color.r) * t),
    g: Math.round(color.g + (background.g - color.g) * t),
    b: Math.round(color.b + (background.b - color.b) * t),
  }
}
