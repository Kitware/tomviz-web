import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { reactive } from 'vue'

import PipelineWidget from '@/components/PipelineWidget.vue'
import { byLabel, fanOut, sinkGroup, tomography } from './fixtures'

const stubs = {
  'v-icon': { template: '<i class="v-icon" />' },
  'v-progress-circular': { template: '<i class="v-progress-circular" />' },
  'v-progress-linear': { template: '<i class="v-progress-linear" />' },
}

function mountWidget(nodes: ReturnType<typeof fanOut>, props = {}) {
  return mount(PipelineWidget, { props: { nodes, ...props }, global: { stubs } })
}

describe('PipelineWidget', () => {
  it('renders one card per strip row and one path per visible link', () => {
    const nodes = tomography()
    const wrapper = mountWidget(nodes)
    expect(wrapper.findAll('.tv-card')).toHaveLength(nodes.length)
    expect(wrapper.findAll('path.tv-link')).toHaveLength(nodes.length - 1)
    expect(wrapper.findAll('.tv-square')).toHaveLength(6) // one output square per data node
    expect(wrapper.text()).toContain('Reconstruction')
  })

  it('draws group members inside the group', () => {
    // Reactive like the trame-dataclass objects the app hands the widget.
    const nodes = reactive(sinkGroup())
    const wrapper = mountWidget(nodes)
    expect(wrapper.findAll('.tv-card')).toHaveLength(nodes.length - 3)
    expect(wrapper.findAll('.tv-member')).toHaveLength(3)
    byLabel(nodes, 'Visualizations').expanded = true
    return wrapper.vm.$nextTick().then(() => {
      expect(wrapper.findAll('.tv-member')).toHaveLength(0)
      expect(wrapper.findAll('.tv-subcard--member')).toHaveLength(3)
    })
  })

  it('emits the selection as model ids', async () => {
    const nodes = fanOut()
    const wrapper = mountWidget(nodes)
    await wrapper.find('.tv-card').trigger('click')
    expect(wrapper.emitted('update:activeNode')?.[0]).toEqual([[byLabel(nodes, 'sample.vti')._id]])

    await wrapper.find('.tv-square').trigger('click')
    expect(wrapper.emitted('update:activeNode')?.[1]).toEqual([
      [byLabel(nodes, 'sample.vti').outputs[0]._id],
    ])

    await wrapper.find('path.tv-link-hit').trigger('click')
    const compare = byLabel(nodes, 'Gaussian Filter')
    expect(wrapper.emitted('update:activeNode')?.[2]).toEqual([[compare.inputs[0]._id]])

    await wrapper.setProps({ activeNode: [compare.inputs[0]._id] })
    await wrapper.find('.tomviz-pipeline').trigger('click')
    expect(wrapper.emitted('update:activeNode')?.[3]).toEqual([[]])
  })

  it('reflects the selection and the tip, redirected out of a group', async () => {
    const nodes = sinkGroup()
    const gauss = byLabel(nodes, 'Gaussian Filter')
    const group = byLabel(nodes, 'Visualizations')
    const wrapper = mountWidget(nodes, {
      activeNode: [gauss._id],
      tipPort: group.outputs[0]._id,
    })
    expect(wrapper.find('.tv-card--selected').text()).toContain('Gaussian Filter')
    const tip = wrapper.find('.tv-square--tip')
    expect(tip.exists()).toBe(true)
    expect(tip.attributes('title')).toContain('ImageData')
    expect(tip.classes()).not.toContain('tv-square--round')

    await wrapper.setProps({ activeNode: [gauss.outputs[0]._id] })
    expect(wrapper.find('.tv-square--selected').exists()).toBe(true)
  })

  it('walks the rows with the arrow keys and asks for deletions', async () => {
    const nodes = fanOut()
    const wrapper = mountWidget(nodes)
    const rootEl = wrapper.find('.tomviz-pipeline')
    await rootEl.trigger('keydown', { key: 'ArrowDown' })
    expect(wrapper.emitted('update:activeNode')?.[0]).toEqual([[byLabel(nodes, 'sample.vti')._id]])

    await wrapper.setProps({ activeNode: [byLabel(nodes, 'sample.vti')._id] })
    await rootEl.trigger('keydown', { key: 'Delete' })
    expect(wrapper.emitted('delete')?.[0]).toEqual([
      { kind: 'node', id: byLabel(nodes, 'sample.vti')._id },
    ])

    await wrapper.setProps({ locked: true })
    await rootEl.trigger('keydown', { key: 'Delete' })
    expect(wrapper.emitted('delete')).toHaveLength(1)
  })

  it('emits toggles and context menus instead of mutating', async () => {
    const nodes = fanOut()
    const wrapper = mountWidget(nodes)
    const buttons = wrapper.find('.tv-card').findAll('button')
    await buttons[buttons.length - 1].trigger('click') // expand chevron
    expect(wrapper.emitted('toggle-expanded')?.[0]).toEqual([byLabel(nodes, 'sample.vti')])
    await wrapper.find('.tv-card').trigger('contextmenu', { clientX: 5, clientY: 7 })
    expect(wrapper.emitted('contextmenu')?.[0]?.[0]).toMatchObject({
      kind: 'node',
      id: byLabel(nodes, 'sample.vti')._id,
      x: 5,
      y: 7,
    })
  })
})

describe('drag to link', () => {
  function fire(type: string, x: number, y: number, target: EventTarget = window) {
    target.dispatchEvent(new MouseEvent(type, { clientX: x, clientY: y, bubbles: true }))
  }
  function press(wrapper: ReturnType<typeof mountWidget>, x: number, y: number) {
    fire('pointerdown', x, y, wrapper.find('.tv-square').element)
  }

  it('asks for a link when an output is dropped on an accepting input', async () => {
    const nodes = fanOut()
    const wrapper = mountWidget(nodes)
    const { layout } = wrapper.vm as unknown as {
      layout: ReturnType<typeof import('@/layout').computeLayout>
    }
    const source = byLabel(nodes, 'sample.vti')
    const err = byLabel(nodes, 'Error Plot')
    const sourceDot = layout.geometry.get(source._id)!.outputDots[0]
    const errDot = layout.geometry.get(err._id)!.inputDots[0]

    // Error Plot takes tables: the source's image port is refused there...
    press(wrapper, sourceDot.x, sourceDot.y)
    fire('pointermove', errDot.x, errDot.y)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.tv-link--pending').exists()).toBe(true)
    expect(wrapper.find('.tv-link--dashed').exists()).toBe(true)
    fire('pointerup', errDot.x, errDot.y)
    expect(wrapper.emitted('link-request')).toBeUndefined()

    // ...but the Diff Viewer's image input accepts it, replacing its link.
    const diff = byLabel(nodes, 'Diff Viewer')
    const diffDot = layout.geometry.get(diff._id)!.inputDots[0]
    press(wrapper, sourceDot.x, sourceDot.y)
    fire('pointermove', diffDot.x, diffDot.y)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.tv-dot--target').exists()).toBe(true)
    expect(wrapper.find('.tv-link--dashed').exists()).toBe(false)
    fire('pointerup', diffDot.x, diffDot.y)
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('link-request')?.[0]).toEqual([
      { output: source.outputs[0], input: diff.inputs[0] },
    ])
    expect(wrapper.find('.tv-link--pending').exists()).toBe(false)
  })

  it('does not start while locked', async () => {
    const nodes = fanOut()
    const wrapper = mountWidget(nodes, { locked: true })
    press(wrapper, 0, 0)
    fire('pointermove', 200, 200)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.tv-link--pending').exists()).toBe(false)
  })
})

describe('focus mode', () => {
  it('dims what is more than a hop from the selection', async () => {
    const nodes = fanOut()
    const wrapper = mountWidget(nodes, { dimming: true })
    expect(wrapper.findAll('.tv-card.tv-dim')).toHaveLength(0)
    await wrapper.setProps({ activeNode: [byLabel(nodes, 'Diff Viewer')._id] })
    const dimmed = wrapper.findAll('.tv-card.tv-dim').map((w) => w.text())
    expect(dimmed.some((t) => t.includes('sample.vti'))).toBe(true)
    expect(dimmed.some((t) => t.includes('Compare'))).toBe(false)
  })

  it('shows the view color on sink cards outside a group, like on members', () => {
    const wrapper = mountWidget(sinkGroup())
    const chips = wrapper.findAll('.tv-card .tv-view-chip')
    // The three ungrouped sinks of the second branch; the grouped ones are
    // circles under their group, which carry the color too.
    expect(chips).toHaveLength(3)
    expect(wrapper.findAll('.tv-member .tv-member__view')).toHaveLength(3)
    expect(chips[0].attributes('style')).toContain('rgb(255, 0, 0)')
  })

  it('offers to leave a group from an expanded member card', async () => {
    const nodes = reactive(sinkGroup())
    byLabel(nodes, 'Visualizations').expanded = true
    const wrapper = mountWidget(nodes)
    const leave = wrapper.find('.tv-subcard--member button[title="Leave group"]')
    await leave.trigger('click')
    expect(wrapper.emitted('leave-group')?.[0]?.[0]).toMatchObject({ label: 'Outline' })
  })
})
