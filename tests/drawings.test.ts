import { expect, test } from 'claude-code/testing'
import { drawingBox, drawingPreview, clearDrawingCache } from '../hooks/notebook/drawings'

const asset = { file: '/work/d.png', preview: '/work/p.png', width: 240, height: 120, preview_width: 240, preview_height: 120 }

test('diagram previews remain at natural size and fit tiny and wide panes', () => {
  expect(drawingBox(asset, 100, 25)).toEqual({ columns: 20, rows: 5 })
  expect(drawingBox(asset, 10, 20)).toEqual({ columns: 10, rows: 3 })
  for (const columns of [8, 24, 80, 120]) for (const rows of [3, 8, 20, 40]) {
    const box = drawingBox({ ...asset, width: 1000, height: 2000 }, columns, rows)
    expect(box.columns).toBeLessThanOrEqual(columns)
    expect(box.rows).toBeLessThanOrEqual(rows)
  }
})

test('preview caches include source, size and theme, reuse pending jobs and repair evicted PNGs', async () => {
  clearDrawingCache()
  const requests: any[] = []
  let exists = true
  const $ = {
    plugin: { root: '/plugin' }, session: { cwd: async () => '/work' },
    fs: { stat: async () => { if (!exists) throw new Error('evicted'); return { kind: 'file' } } },
    process: { run: async (argv: string[], init: any) => {
      requests.push({ argv, ...JSON.parse(init.stdin) })
      return { stdout: JSON.stringify({ ok: true, asset }) }
    } },
  } as any
  const draw = (source = '#circle()', columns = 80, light = false) => drawingPreview($, 'typst', source, columns, 20, light, '/python', '/typst')
  await Promise.all([draw(), draw()])
  expect(requests.length).toBe(1)
  await draw('#circle()', 24)
  await draw('#circle()', 24, true)
  await draw('#rect()')
  expect(requests.length).toBe(4)
  exists = false
  await draw()
  expect(requests.length).toBe(5)
  expect(requests[0].argv).toEqual(['/python', '/plugin/notebook/drawing.py'])
  expect(requests[0].workspace).toBe('/work')
  expect(requests[0].source).toBe('#circle()')
})

test('the reported Maxwell labels reach the graphical compiler, including Unicode and apostrophes', async () => {
  clearDrawingCache()
  const source = `graph LR
  Q[Charge density ρ] -->|Gauss's law ∇·E = ρ/ε0| E[Electric field E]
  J[Current density J] -->|Ampère–Maxwell law| B[Magnetic field B]
  E -->|Ampère–Maxwell: ∂E/∂t term| B
  B -->|Faraday's law ∇×E = −∂B/∂t| E
  B -->|Gauss's law for magnetism ∇·B = 0| M[No magnetic monopoles]`
  let request: any
  const $ = {
    plugin: { root: '/plugin' }, session: { cwd: async () => '/work' },
    process: { run: async (_argv: any, init: any) => { request = JSON.parse(init.stdin); return { stdout: JSON.stringify({ ok: true, asset }) } } },
  } as any
  expect((await drawingPreview($, 'mermaid', source, 40, 12, false, 'python')).asset).toEqual(asset)
  expect(request.source).toBe(source)
  for (const label of ['Charge density ρ', '∇·E', '∂E/∂t', 'No magnetic monopoles']) expect(request.svg).toContain(label)
})
