/**
 * The desktop tomviz pipeline icons, inlined. Black strokes and fills are
 * replaced with `currentColor` so the icons tint like the desktop's, while
 * icons with their own palette (persistence, breakpoint) keep it.
 */
import autoexecute from './autoexecute.svg?raw'
import breakpoint from './breakpoint.svg?raw'
import filter from './filter.svg?raw'
import filter_disabled from './filter_disabled.svg?raw'
import icon_join from './icon_join.svg?raw'
import icon_leave from './icon_leave.svg?raw'
import port_data_disk from './port_data_disk.svg?raw'
import port_data_ram from './port_data_ram.svg?raw'
import port_imagedata from './port_imagedata.svg?raw'
import port_labelmap from './port_labelmap.svg?raw'
import port_molecule from './port_molecule.svg?raw'
import port_persistent_disk from './port_persistent_disk.svg?raw'
import port_persistent_pin from './port_persistent_pin.svg?raw'
import port_persistent_ram from './port_persistent_ram.svg?raw'
import port_table from './port_table.svg?raw'
import port_tiltseries from './port_tiltseries.svg?raw'
import port_transient from './port_transient.svg?raw'

const RAW: Record<string, string> = {
  autoexecute,
  breakpoint,
  filter,
  filter_disabled,
  icon_join,
  icon_leave,
  port_data_disk,
  port_data_ram,
  port_imagedata,
  port_labelmap,
  port_molecule,
  port_persistent_disk,
  port_persistent_pin,
  port_persistent_ram,
  port_table,
  port_tiltseries,
  port_transient,
}

const CACHE = new Map<string, string>()

function prepare(svg: string): string {
  return svg
    .replace(/<\?xml[^>]*\?>/g, '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/#000000\b|#000\b/g, 'currentColor')
    .trim()
}

export type IconName = keyof typeof RAW

export function iconMarkup(name: string): string {
  let markup = CACHE.get(name)
  if (markup === undefined) {
    markup = prepare(RAW[name] ?? '')
    CACHE.set(name, markup)
  }
  return markup
}

export const ICON_NAMES = Object.keys(RAW)

/** The icon drawn inside an output port square, by port type. */
export function portTypeIcon(portType: string | undefined): string {
  switch (portType) {
    case 'TiltSeries':
      return 'port_tiltseries'
    case 'LabelMap':
      return 'port_labelmap'
    case 'Table':
      return 'port_table'
    case 'Molecule':
      return 'port_molecule'
    default:
      return 'port_imagedata'
  }
}
