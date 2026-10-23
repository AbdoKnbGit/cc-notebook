import { expect, mock, test } from 'claude-code/testing'
import { bridgeContext, commandOf, initialLab, notebookContext, parseGenerated, TOOL, LEGACY_TOOL, PANE } from '../hooks/notebook/model'
import { editorRows } from '../hooks/notebook/editor'
import { fitPlot, plotSource, clearImageCache } from '../hooks/notebook/images'
import { diagram, inlineMath, mathText, raster, imageUri } from '../hooks/notebook/rich'
import { terminalPlot } from '../hooks/notebook/plot'
import { notebookGraphics, graphicsReport } from '../hooks/notebook/graphics'

const CMD = { origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } } as const
const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII='
const run = ($: any, args: string) => $.command.run({ command: 'lab', args, ...CMD })
const input = async (ui: any, text: string, kind = 'submit') => ui.input({ key: (await ui.find({ type: 'Input' })).props.key, text, kind })
const mount = ($: any, surface = 'terminal') => $.ui.mount({ plugin: 'cc-notebook', surface, component: 'Pane', requestId: PANE, props: { title: 'Lab', isFocused: true, bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} }, viewport: { columns: 80, rows: 40 } })
const sample = () => ({ path: '/work/notebook.nb.md', revision: 'r1', title: 'Experiment', kernel: { alive: false, busy: false, id: null, python: 'python' }, variables: [], activity: [], history_count: 0, cells: [
  { id: 'md', type: 'markdown', source: '# Question', status: 'ready', run: null },
  { id: 'py', type: 'python', source: 'x = 41\nx + 1', status: 'ready', run: null },
  { id: 'ai', type: 'ai', source: 'Explain this result', status: 'ready', run: null },
] })

test('Typst and Mermaid cells display a bounded native diagram while editing keeps the source', async ($, on) => {
  const asset = { file: '/work/diagram.png', preview: '/work/diagram-preview.png', width: 240, height: 120, preview_width: 240, preview_height: 120 }
  const w = world(on, { env: { TERM_PROGRAM: 'ghostty' }, drawing: asset })
  on('fs.stat', () => ({ value: { kind: 'file', size: 2000, mtimeMs: 1, isLink: false } }))
  await ($ as any).session.start({ source: 'startup', cwd: '/work' })
  for (const kind of ['typst', 'mermaid']) {
    const source = kind === 'typst' ? '#circle(radius: 10pt)' : 'graph LR\nQ[Charge density ρ] --> E[Electric field E]'
    w.view.cells[0].source = '```' + kind + '\n' + source + '\n```'
    w.view.cells[0].rich = [{ kind, text: source }]
    await run($, 'open notebook.nb.md')
    const ui = await mount($)
    const image = await ui.find({ type: 'Image' })
    expect(image?.props.source.file).toBe(asset.preview)
    expect(image?.props.columns).toBe(20)
    expect(image?.props.rows).toBe(5)
    expect(await ui.find({ type: 'Code' })).toBeUndefined()
    await ui.press({ key: 'lab-edit' })
    expect((await ui.find({ type: 'Input' })).props.value).toBe(w.view.cells[0].source)
    await ui.press({ key: 'lab-cancel-edit' })
    await ui.unmount()
  }
  expect(w.calls.some(c => ['run', 'update', 'add'].includes(c.action))).toBe(false)
})

test('diagram previews fall back to a small terminal raster instead of hiding behind source', async ($, on) => {
  const asset = { file: '/work/diagram.png', preview: '/work/diagram-preview.png', width: 240, height: 120, preview_width: 240, preview_height: 120, pixels: '/work/diagram-pixels.json' }
  const w = world(on, { env: { TERM_PROGRAM: 'Windows_Terminal' }, drawing: asset })
  on('fs.stat', () => ({ value: { kind: 'file', size: 2000, mtimeMs: 1, isLink: false } }))
  on('fs.read', () => ({ value: JSON.stringify({ width: 1, height: 1, rgba: '4080c0ff' }) }))
  w.view.cells[0].source = '```typst\n#circle(radius: 10pt)\n```'
  w.view.cells[0].rich = [{ kind: 'typst', text: '#circle(radius: 10pt)' }]
  await ($ as any).session.start({ source: 'startup', cwd: '/work' })
  await run($, 'open notebook.nb.md')
  const ui = await mount($)
  const raster = await ui.find({ type: 'Raster' })
  expect(raster?.props.columns).toBe(20)
  expect(raster?.props.rows).toBe(5)
  expect(await ui.find({ type: 'Code' })).toBeUndefined()
  await ui.unmount()
})

test('automatic setup streams progress and uses the installed runtime for notebook operations', async ($, on) => {
  const w = world(on)
  let installs = 0
  on('process.spawn', async function* (_$, e) {
    installs++
    expect(e.argv[0]).toBe('/base/python')
    const data = JSON.stringify({ progress: 'Downloading packages…' }) + '\n' + JSON.stringify({ ok: true, result: { python: '/managed/python', typst: '/managed/typst', latex: true } }) + '\n'
    yield { stream: 'stdout', text: data.slice(0, 19) }
    yield { stream: 'stdout', text: data.slice(19) }
    return { value: { code: 0, signal: null } }
  })
  await run($, 'python auto')
  await run($, 'new automatic.nb.md')
  await run($, 'run 2')
  expect(installs).toBe(1)
  expect(w.calls.some(c => c.action === 'run')).toBe(true)
  expect(w.bridgeCommands.every(e => e.argv[0] === '/managed/python' && e.init.env.CLAUDE_NOTEBOOK_TYPST === '/managed/typst')).toBe(true)
})

test('failed automatic setup stays retryable and never starts the bridge', async ($, on) => {
  const w = world(on)
  let attempts = 0
  on('process.spawn', async function* () {
    attempts++
    yield { stream: 'stdout', text: JSON.stringify(attempts === 1 ? { ok: false, error: 'Network unavailable. Retry /lab setup.' } : { ok: true, result: { python: '/managed/python', warning: 'Advanced LaTeX unavailable; retry /lab setup.' } }) + '\n' }
    return { value: { code: attempts === 1 ? 1 : 0, signal: null } }
  })
  await run($, 'python auto')
  const failed = await run($, 'new retry.nb.md')
  expect(failed.text).toContain('Network unavailable')
  expect(w.calls.length).toBe(0)
  const retried = await run($, 'setup')
  expect(retried.text).toContain('Advanced LaTeX unavailable')
  await run($, 'new retry.nb.md')
  expect(attempts).toBe(2)
  expect(w.calls.at(-1).action).toBe('new')
})

test('missing Python gives an actionable error without attempting downloads', async ($, on) => {
  world(on, { missingPython: true })
  let spawned = false
  on('process.spawn', async function* () { spawned = true; return { value: { code: 1, signal: null } } })
  const result = await run($, 'setup')
  expect(result.text).toContain('Python 3.10 or newer was not found')
  expect(spawned).toBe(false)
})

function world(on: any, options: { answer?: string; deny?: boolean; failedSave?: boolean; missingPython?: boolean; toolMissing?: boolean; toolBroken?: boolean; toolListThrows?: boolean; env?: Record<string, string>; drawing?: any } = {}) {
  mock.store(on)
  const clock = mock.clock(on)
  mock.env(on, { DISABLE_AUTOUPDATER: '1', CLAUDE_NOTEBOOK_PYTHON: 'python', ...options.env })
  on('session.cwd', () => ({ value: '/work' }))
  on('session.id', () => ({ value: 'test-session' }))
  on('session.model', () => ({ value: 'claude-sonnet-4-6' }))
  on('command.register', () => ({ value: undefined }))
  let toolConnected = !options.toolMissing && !options.toolBroken
  const registrations: any[] = [], focuses: any[] = []
  on('tool.register', (_$: any, e: any) => { registrations.push(e); toolConnected = !options.toolBroken; return { value: { tool: TOOL } } })
  on('tool.list', () => {
    if (options.toolListThrows) throw new Error('Tool discovery unavailable')
    return { value: toolConnected ? [{ name: TOOL, description: 'Lab notebook', mcp: true }] : [] }
  })
  on('session.start', () => ({ cwd: '/work' }))
  const checked: string[] = []
  on('tool.check', (_$: any, e: any) => { checked.push(e.tool); return { decision: options.deny ? 'deny' : 'allow', reason: 'Test permission policy' } })
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.focus', (_$: any, e: any) => { focuses.push(e); return {} })
  on('ui.toast', () => ({ value: undefined }))
  const view: any = sample(), calls: any[] = [], prompts: string[] = [], bridgeCommands: any[] = []
  on('model.complete', (_$: any, e: any) => {
    prompts.push(e.prompt)
    return { value: { isAnswered: true, text: options.answer ?? '{"cells":[{"type":"python","source":"x + 2"}]}', usage: { input_tokens: 20, output_tokens: 10, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 } } }
  })
  on('process.run', (_$: any, e: any) => {
    let result: any = {}, error: string | null = null
    if (String(e.argv[1]).endsWith('/notebook/drawing.py')) return { value: { exitCode: 0, stdout: JSON.stringify({ ok: true, asset: options.drawing }), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    if (e.argv.includes('-c')) return { value: { exitCode: options.missingPython ? 1 : 0, stdout: options.missingPython ? '' : '/base/python\n', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    if (!String(e.argv[1]).endsWith('/notebook/bridge.py')) return { value: { exitCode: 1, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    bridgeCommands.push(e)
    if (e.argv[2] === 'start') result = { runtime: '/tmp/cc-notebook-runtime/test' }
    else if (e.argv[2] === 'doctor') result = { python: 'python', modules: { ipykernel: true } }
    else {
      const r = JSON.parse(e.init.stdin)
      calls.push(r)
      if (r.action === 'update' && options.failedSave) error = 'Notebook changed on disk. Refresh before saving.'
      else if (r.action === 'update') { view.cells.find((c: any) => c.id === r.id).source = r.source; view.revision = 'r2' }
      else if (r.action === 'add') view.cells.push({ id: 'added', type: r.type, source: r.source ?? '', status: 'ready', run: null })
      else if (r.action === 'run') { view.kernel.alive = true; const cell = view.cells.find((c: any) => c.id === r.id), oldRun = cell.run; cell.run = { outputs: [{ output_type: 'execute_result', data: { 'text/plain': '42' } }], images: oldRun?.images ?? [], image_info: oldRun?.image_info, duration_ms: 12, at: (oldRun?.at ?? 0) + 1 }; cell.status = 'ok' }
      else if (r.action === 'apply_generation') view.cells.push(...r.cells.map((c: any, i: number) => ({ ...c, id: `gen-${i}`, status: 'ready', generated_from: r.id, run: null })))
      result = r.action === 'context' ? { prompt: 'Explain', context: [], context_key: 'ctx' } : view
    }
    return { value: { exitCode: 0, stdout: JSON.stringify(error ? { ok: false, error } : { ok: true, result }), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  return { view, calls, prompts, clock, bridgeCommands, focuses, registrations, checked, connectTools: () => { toolConnected = true } }
}

test('notebook command preserves quoted Windows paths and validates AI JSON', () => {
  expect(commandOf('open "C:\\my work\\n.nb.md"')).toEqual({ action: 'open', value: 'C:\\my work\\n.nb.md' })
  expect(parseGenerated('```json\n{"cells":[{"type":"python","source":"x=1","extra":"drop"}]}\n```')).toEqual([{ type: 'python', source: 'x=1' }])
  for (const value of ['null', '{}', '{"cells":[]}', '{"cells":[{"type":"shell","source":"bad"}]}']) expect(() => parseGenerated(value)).toThrow()
})

test('notebook opens across surfaces without starting Python; editing never executes', async ($, on) => {
  const w = world(on)
  await run($, 'new notebook.nb.md')
  for (const surface of ['terminal', 'desktop', 'vscode']) {
    const ui = await mount($, surface)
    expect(await ui.find({ type: 'Text', text: 'LAB NOTEBOOK' })).toBeDefined()
    await ui.unmount()
  }
  const ui = await mount($)
  await ui.press({ key: 'cell-py' })
  await ui.press({ key: 'lab-edit' })
  await input(ui, 'x = 100')
  expect(w.view.cells[1].source).toBe('x = 100')
  expect(w.calls.some(c => c.action === 'run')).toBe(false)
  await ui.press({ key: 'lab-run' })
  expect(await ui.find({ type: 'Text', text: '42' })).toBeDefined()
  expect(w.calls.filter(c => c.action === 'run').length).toBe(1)
  await ui.unmount()
})

test('export accepts a new filename with spaces and import clears the active path', async ($, on) => {
  const w = world(on)
  await run($, 'new n.nb.md')
  await run($, 'export ipynb "C:\\my work\\results v2.ipynb"')
  expect(w.calls.at(-1)).toMatchObject({ action: 'export', format: 'ipynb', destination: 'C:\\my work\\results v2.ipynb' })
  await run($, 'export markdown')
  expect(w.calls.at(-1).format).toBe('markdown')
  expect(w.calls.at(-1).destination).toBeUndefined()
  await run($, 'import "C:\\my work\\import.ipynb"')
  expect(w.calls.at(-1).source).toBe('C:\\my work\\import.ipynb')
  expect(w.calls.at(-1).path).toBeUndefined()
})

test('conflicting save retains the editor draft and reports the conflict', async ($, on) => {
  const w = world(on, { failedSave: true })
  await run($, 'new n.nb.md')
  const ui = await mount($)
  await ui.press({ key: 'lab-edit' })
  await input(ui, 'keep my draft', 'change')
  await input(ui, 'keep my draft')
  expect(await ui.find({ type: 'Text', text: /changed on disk/ })).toBeDefined()
  expect((await ui.find({ type: 'Input' })).props.value).toBe('keep my draft')
  expect(w.view.cells[0].source).toBe('# Question')
  await ui.unmount()
})

test('generation creates reviewable cells without executing them', async ($, on) => {
  const w = world(on)
  await run($, 'new n.nb.md')
  const answer = await run($, 'generate 3')
  expect(answer.text).toContain('Generated cells saved')
  expect(w.prompts.length).toBe(1)
  expect(w.calls.some(c => c.action === 'apply_generation' && c.context_key === 'ctx')).toBe(true)
  expect(w.calls.some(c => c.action === 'run')).toBe(false)
})

test('malformed AI output leaves cells intact', async ($, on) => {
  const w = world(on, { answer: 'not JSON' })
  await run($, 'new n.nb.md')
  await run($, 'generate 3')
  expect(w.view.cells.length).toBe(3)
  expect(w.calls.some(c => c.action === 'apply_generation')).toBe(false)
})

test('denied notebook tool cannot start a bridge or run code', async ($, on) => {
  const w = world(on, { deny: true })
  const result = await $.tool.call({ tool: TOOL, action: 'run', id: 'py', revision: 'r1' } as never)
  expect(result.deny).toContain('Test permission policy')
  expect(w.calls).toEqual([])
})

test('notebook tool returns bounded text results and draws inline plots on supported surfaces', async ($, on) => {
  const w = world(on, { env: { TERM_PROGRAM: 'ghostty', TERM: 'xterm-ghostty' } })
  const file = '/work/.claude-notebook/outputs/test/plot-preview.png'
  w.view.cells[1].run = { outputs: [{ output_type: 'display_data', data: { 'text/plain': '<Figure>' } }], images: [file], image_info: { [file]: { preview: file, width: 800, height: 400, preview_width: 800, preview_height: 400 } }, duration_ms: 10, at: 1 }
  on('fs.stat', () => ({ value: { kind: 'file', size: 1000, mtimeMs: 1, isLink: false } }))
  on('fs.read', () => ({ value: { base64: PNG } }))
  await ($ as any).session.start({ source: 'startup', cwd: '/work' })
  const reply = await $.tool.call({ tool: TOOL, action: 'run', id: 'py', revision: 'r1' } as never)
  expect(JSON.stringify(reply)).not.toContain('image/png')
  expect(typeof reply.result).toBe('string')
  expect(JSON.parse(reply.result as string).cells).toHaveLength(1)
  expect(JSON.parse(reply.result as string).cells[0].run.images).toContain(file)
  expect(JSON.parse(reply.result as string)._notebookOperation.action).toBe('run')
  expect(w.calls[0].action).toBe('run')
  for (const surface of ['terminal', 'desktop', 'vscode'] as const) {
    const ui = await $.ui.mount({ plugin: 'cc-notebook', surface, component: 'ToolResult', requestId: 'notebook-output', props: { tool_use_id: 'notebook-output', tool: TOOL, output: JSON.stringify(reply), isErrored: false }, viewport: { columns: 100, rows: 40 } } as any)
    if (surface === 'terminal') {
      const shown: any = await ui.find({ type: 'Image' })
      expect(shown?.props.source.file).toBe(file)
    }
    expect(await ui.find({ type: 'Text', text: /Experiment/ })).toBeDefined()
    await ui.unmount()
  }
})

test('adding an AI cell hides old executions and shows only the new instruction', async ($, on) => {
  const w = world(on)
  const oldImage = '/work/old-python-plot.png'
  w.view.cells[1].run = { outputs: [{ output_type: 'stream', text: 'OLD_CELL_OUTPUT' }], images: [oldImage], duration_ms: 10, at: 1 }
  const reply = await $.tool.call({ tool: TOOL, action: 'add', type: 'ai', source: 'Explain this experiment without running code.', revision: 'r1' } as never)
  const payload = JSON.parse(reply.result as string)
  expect(payload._notebookOperation.action).toBe('add')
  expect(payload.cells).toHaveLength(1)
  expect(payload.cells[0]).toMatchObject({ id: 'added', type: 'ai', run: null })
  expect(reply.result).not.toContain(oldImage)
  expect(reply.result).not.toContain('OLD_CELL_OUTPUT')
  const ui = await $.ui.mount({ plugin: 'cc-notebook', surface: 'terminal', component: 'ToolResult', requestId: 'ai-cell-added', props: { tool_use_id: 'ai-cell-added', tool: TOOL, output: JSON.stringify(reply), isErrored: false }, viewport: { columns: 100, rows: 40 } } as any)
  expect(await ui.find({ type: 'Text', text: /Added AI cell/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /AI instructions have no execution output/ })).toBeDefined()
  expect(await ui.find({ type: 'Image' })).toBeUndefined()
  expect((await ui.drawn()).toString()).not.toContain('OLD_CELL_OUTPUT')
  await ui.unmount()
})

test('full notebook results stay attached to their own cells', async ($, on) => {
  const w = world(on, { env: { TERM_PROGRAM: 'ghostty', TERM: 'xterm-ghostty' } })
  const image = '/work/cell-two.png'
  w.view.cells[0].run = { outputs: [{ output_type: 'stream', text: 'FIRST_CELL_OUTPUT' }], images: [], duration_ms: 2, at: 1 }
  w.view.cells[1].run = { outputs: [{ output_type: 'display_data', data: { 'text/plain': 'SECOND_CELL_FIGURE' } }], images: [image], image_info: { [image]: { preview: image, width: 400, height: 200, preview_width: 400, preview_height: 200 } }, duration_ms: 3, at: 2 }
  w.view.cells[0].status = 'ok'
  on('fs.stat', () => ({ value: { kind: 'file', size: 1000, mtimeMs: 1, isLink: false } }))
  on('fs.read', () => ({ value: { base64: PNG } }))
  await ($ as any).session.start({ source: 'startup', cwd: '/work' })
  const reply = await $.tool.call({ tool: TOOL, action: 'status' } as never)
  const payload = JSON.parse(reply.result as string)
  expect(payload.cells[0].run.outputs[0].text).toBe('FIRST_CELL_OUTPUT')
  expect(payload.cells[0].run.images).toEqual([])
  expect(payload.cells[1].run.outputs[0].text).toBe('SECOND_CELL_FIGURE')
  expect(payload.cells[1].run.images).toEqual([image])
  const ui = await $.ui.mount({ plugin: 'cc-notebook', surface: 'terminal', component: 'ToolResult', requestId: 'full-notebook-status', props: { tool_use_id: 'full-notebook-status', tool: TOOL, output: JSON.stringify(reply), isErrored: false }, viewport: { columns: 100, rows: 40 } } as any)
  expect(await ui.find({ type: 'Text', text: /Cell 1 · ok/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /FIRST_CELL_OUTPUT/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Cell 2 · ready/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /SECOND_CELL_FIGURE/ })).toBeDefined()
  const shown: any = await ui.find({ type: 'Image' })
  expect(shown?.props.source.file).toBe(image)
  await ui.unmount()
})

test('SSH uses cached PNG bytes and retains the original image path', async ($, on) => {
  const w = world(on, { env: { SSH_CONNECTION: 'test', TERM: 'xterm-kitty' } })
  const file = '/work/.claude-notebook/outputs/test/remote-preview.png'
  w.view.cells[1].run = { outputs: [], images: [file], duration_ms: 10, at: 1 }
  on('fs.stat', () => ({ value: { kind: 'file', size: 4, mtimeMs: 1, isLink: false } }))
  on('fs.read', () => ({ value: { base64: PNG } }))
  await ($ as any).session.start({ source: 'startup', cwd: '/work' })
  await run($, 'new n.nb.md')
  await run($, 'select 2')
  const ui = await mount($)
  const shown: any = await ui.find({ type: 'Image' })
  expect(shown?.props.source.png).toBe(PNG)
  expect((await ui.find({ type: 'Link', text: /Open original image/ }))?.props.href).toBe(imageUri(file))
  await ui.unmount()
})

test('plot fitting respects narrow windows, tall plots and resize generations', async () => {
  for (const w of [1, 10, 40, 120, 400]) for (const h of [1, 20, 100]) {
    const box = fitPlot(100, 2000, w, h)
    expect(box.columns).toBeLessThanOrEqual(w)
    expect(box.rows).toBeLessThanOrEqual(h)
  }
  clearImageCache()
  let reads = 0
  const fake = { fs: { stat: async () => ({ kind: 'file', size: 4, mtimeMs: 1 }), read: async () => { reads++; return { base64: 'YWJjZA==' } } } } as any
  const a = await plotSource(fake, '/p.png', { columns: 80, rows: 20 }, false)
  const b = await plotSource(fake, '/p.png', { columns: 40, rows: 10 }, false)
  expect(a).not.toEqual(b)
  await plotSource(fake, '/p.png', { columns: 80, rows: 20 }, true)
  await plotSource(fake, '/p.png', { columns: 40, rows: 10 }, true)
  expect(reads).toBe(1)
  fake.fs.stat = async () => ({ kind: 'file', size: 3_000_000 })
  expect(await plotSource(fake, '/large.png', { columns: 40, rows: 10 }, true)).toBe(null)
})

test('Mermaid fits a narrow pane and keeps unsupported diagrams as source', () => {
  const art = diagram('graph LR\n A[Question] --> B[Experiment]\n B --> C[Result]', 24)
  expect(art).not.toBe(null)
  expect(art!.split('\n').every(line => line.length <= 24)).toBe(true)
  expect(art).toContain('Experiment')
  expect(diagram('not-a-diagram', 80)).toBe(null)
  expect(diagram('graph TD\n A --> B' + 'x'.repeat(5000), 80)).toBe(null)
  expect(diagram('graph TD\n A[😀] --> B', 80)).toBe(null)
})

test('math preserves code, currency and unsupported commands', () => {
  expect(mathText('E = mc^2')).toBe('E = mc²')
  expect(mathText('\\frac{1}{2} + \\alpha')).toBe('(1)/(2) + α')
  expect(mathText('\\dfrac{1}{n}\\sum_i (y_i - \\bar{y})^2')).toBe('(1)/(n)∑ᵢ (yᵢ - ȳ)²')
  expect(mathText('\\hat{\\sigma}^2')).toBe('σ̂²')
  expect(mathText('x_{abc} + y_{ij}')).toBe('x_{abc} + yᵢⱼ')
  expect(mathText('\\unsupported{x}')).toBe('\\unsupported{x}')
  expect(inlineMath('R squared is $1 - R^2$.')).toBe('R squared is 1 - R².')
  expect(inlineMath('The mean is \\bar{y}.')).toBe('The mean is ȳ.')
  expect(inlineMath('Value: $1$ and cost: $5.')).toBe('Value: $1$ and cost: $5.')
  expect(inlineMath('Keep $ x^2$ as text')).toBe('Keep $ x^2$ as text')
  expect(inlineMath('Costs $5 and $10. `$x^2$` and $x^2$')).toBe('Costs $5 and $10. `$x^2$` and x²')
  expect(inlineMath('```python\nprint("$x^2$")\n```')).toContain('$x^2$')
  expect(inlineMath('![test](plot.png) and \\(x^2\\)')).toBe('![test](plot.png) and x²')
  expect(imageUri('C:\\my work\\plot #1.png')).toBe('file:///C:/my%20work/plot%20%231.png')
})

test('Raster uses the terminal default for transparency rather than a guessed white or black', () => {
  const pixels = { width: 1, height: 2, rgba: 'ff0000ff00000000' }
  const dark = raster(pixels, 1, 1, false)
  const light = raster(pixels, 1, 1, true)
  expect(dark?.length).toBe(16)
  expect(dark).toBe(light)
  expect(raster({ width: 1, height: 1, rgba: '00000000' }, 1, 1, false)).toBe('IAAAAAAAAAEAAAAB')
  expect(raster({ width: 1, height: 1, rgba: 'ff000080' }, 1, 1, false)).not.toBe(raster({ width: 1, height: 1, rgba: 'ff000080' }, 1, 1, true))
  expect(raster(pixels, 0, 1, false)).toBe(null)
  expect(raster({ ...pixels, rgba: 'bad' }, 10, 10, false)).toBe(null)
})

test('forced Windows images still use Raster in output order without leaking pixels into model replies', async ($, on) => {
  const w = world(on, { env: { OS: 'Windows_NT', WT_SESSION: 'test', CLAUDE_CODE_FORCE_TERMINAL_IMAGES: '1' } })
  const asset = { file: '/work/plot.png', preview: '/work/preview.png', pixels: '/work/pixels.json', width: 100, height: 50, preview_width: 100, preview_height: 50 }
  w.view.cells[1].run = { outputs: [
    { output_type: 'stream', text: 'Before image' },
    { output_type: 'display_data', asset, data: { 'text/plain': '<Figure>' } },
    { output_type: 'stream', text: 'After image' },
  ], images: [asset.file], image_info: { [asset.file]: asset }, duration_ms: 1, at: 1 }
  on('fs.stat', () => ({ value: { kind: 'file', size: 100, mtimeMs: 1, isLink: false } }))
  on('fs.read', () => ({ value: JSON.stringify({ width: 1, height: 2, rgba: 'ff0000ff0000ffff' }) }))
  await ($ as any).session.start({ source: 'startup', cwd: '/work' })
  const reply = await $.tool.call({ tool: TOOL, action: 'open', path: '/work/notebook.nb.md' } as never)
  expect(JSON.stringify(reply)).not.toContain('ff0000ff0000ffff')
  await run($, 'select 2')
  const ui = await mount($)
  const drawing = JSON.stringify(await ui.drawn())
  expect(await ui.find({ type: 'Raster' })).toBeDefined()
  expect(await ui.find({ type: 'Image' })).toBeUndefined()
  expect(await ui.find({ type: 'Link', text: /Open original image/ })).toBeDefined()
  expect(drawing.indexOf('Before image')).toBeLessThan(drawing.indexOf('Raster'))
  expect(drawing.indexOf('Raster')).toBeLessThan(drawing.indexOf('After image'))
  expect(drawing).not.toContain('<Figure>')
  await ui.unmount()
})

test('forced images cannot bypass unsupported terminals, multiplexers or background sessions', () => {
  for (const env of [
    { TERM_PROGRAM: 'Windows_Terminal' }, { WT_SESSION: 'test' },
    { TERM_PROGRAM: 'vscode', TERM: 'xterm-kitty' }, { TERM: 'xterm-256color' },
    { TERM_PROGRAM: 'ghostty', TMUX: '/tmp/tmux' }, { TERM: 'xterm-kitty', STY: 'screen' },
    { TERM: 'xterm-kitty', CLAUDE_CODE_SESSION_KIND: 'background' },
  ]) {
    const graphics = notebookGraphics({ ...env, CLAUDE_CODE_FORCE_TERMINAL_IMAGES: '1' })
    expect(graphics.native).toBe(false)
    expect(graphics.forceIgnored).toBe(true)
    expect(graphicsReport(graphics)).toContain('prevent broken image placeholders')
  }
  for (const flag of ['', '0', 'FALSE', ' off ', '   ']) expect(notebookGraphics({ CLAUDE_CODE_FORCE_TERMINAL_IMAGES: flag }).forceIgnored).toBe(false)
})

test('native graphics choose the correct local, SSH and iTerm2 transport', () => {
  expect(notebookGraphics({ TERM_PROGRAM: 'ghostty', WT_SESSION: 'inherited' })).toMatchObject({ native: true, bytes: false })
  expect(notebookGraphics({ KITTY_WINDOW_ID: '1' })).toMatchObject({ native: true, bytes: false })
  expect(notebookGraphics({ TERM: 'xterm-kitty', SSH_CONNECTION: 'remote' })).toMatchObject({ native: true, bytes: true })
  expect(notebookGraphics({ TERM: 'xterm', KITTY_WINDOW_ID: 'server-local', SSH_TTY: '/dev/pts/1' }).native).toBe(false)
  expect(notebookGraphics({ TERM_PROGRAM: 'iTerm.app' })).toMatchObject({ native: true, bytes: true })
  expect(notebookGraphics({ TERM_PROGRAM: 'iTerm.app', CLAUDE_CODE_ALT_SCREEN_FULL_REPAINT: '1' }).native).toBe(false)
})

test('iTerm2 receives PNG bytes for native typeset equations, never an unsupported file source', async ($, on) => {
  const w = world(on, { env: { TERM_PROGRAM: 'iTerm.app' } })
  const asset = { file: '/work/iterm-math.png', preview: '/work/iterm-math-preview.png', width: 80, height: 20, preview_width: 80, preview_height: 20 }
  w.view.cells[0].rich = [{ kind: 'math', text: 'x^2', dark: asset }]
  on('fs.stat', () => ({ value: { kind: 'file', size: 100, mtimeMs: 1, isLink: false } }))
  on('fs.read', () => ({ value: { base64: PNG } }))
  await ($ as any).session.start({ source: 'startup', cwd: '/work' })
  await run($, 'new n.nb.md')
  const ui = await mount($)
  const image: any = await ui.find({ type: 'Image' })
  expect(image?.props.source.png).toBe(PNG)
  expect(image?.props.source.file).toBeUndefined()
  await ui.unmount()
})

test('forced Windows equations retain readable math and the original typeset image link', async ($, on) => {
  const w = world(on, { env: { WT_SESSION: 'test', CLAUDE_CODE_FORCE_TERMINAL_IMAGES: '1' } })
  const asset = { file: '/work/math.png', preview: '/work/math-preview.png', width: 80, height: 20, preview_width: 80, preview_height: 20 }
  w.view.cells[0].rich = [{ kind: 'math', text: 'x^2', dark: asset }]
  await ($ as any).session.start({ source: 'startup', cwd: '/work' })
  await run($, 'new n.nb.md')
  const ui = await mount($)
  expect(await ui.find({ type: 'Image' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: 'x²' })).toBeDefined()
  expect((await ui.find({ type: 'Link', text: 'Open typeset equation' }))?.props.href).toBe(imageUri(asset.file))
  expect((await run($, 'graphics')).text).toContain('Sixel')
  expect((await run($, 'doctor')).text).toContain('prevent broken image placeholders')
  await ui.unmount()
})

const plotData = () => ({ version: 1, title: 'Decay experiment', xlabel: 'Time (s)', ylabel: 'Signal', limits: [0, 6, 0, 1], series: [{ points: [[0, 1], [2, .368], [6, .05]], color: '#2563eb', label: 'Measured', connected: true, dashed: false }] })

test('terminal plots preserve labels and reject unsupported or unbounded data', () => {
  const data = plotData()
  const chart = terminalPlot(data, 60, false)!
  expect(chart.title).toBe('Decay experiment')
  expect(chart.xlabel).toBe('Time (s)')
  expect(chart.ylabel).toBe('Signal')
  expect(chart.xlabels).toEqual(['0', '3', '6'])
  expect(chart.ylabels[0]).toBe('1')
  expect(chart.ylabels[chart.rows - 1]).toBe('0')
  expect(chart.columns).toBeLessThanOrEqual(60)
  expect(terminalPlot({ ...data, limits: [0, 0, 0, 1] }, 60, false)).toBe(null)
  expect(terminalPlot({ ...data, version: 2 }, 60, false)).toBe(null)
  expect(terminalPlot(data, 10, false)).toBe(null)
  data.series[0]!.points = [[1e100, 1e100], [2e100, 2e100]]
  expect(terminalPlot(data, 60, false)).not.toBe(null)
  data.series[0]!.points = [[NaN, 1]]
  expect(terminalPlot(data, 60, false)).toBe(null)
})

test('unsupported image terminals show a transparent data chart with readable axis labels', async ($, on) => {
  const w = world(on, { env: { OS: 'Windows_NT', TERM_PROGRAM: 'Windows_Terminal' } })
  const asset = { file: '/work/curve.png', preview: '/work/curve-preview.png', pixels: '/work/curve-pixels.json', plot: '/work/curve-plot.json', width: 800, height: 400, preview_width: 800, preview_height: 400 }
  w.view.cells[1].run = { outputs: [{ output_type: 'display_data', asset }], images: [asset.file], image_info: { [asset.file]: asset }, duration_ms: 1, at: 1 }
  on('fs.stat', () => ({ value: { kind: 'file', size: 500, mtimeMs: 1, isLink: false } }))
  on('fs.read', () => ({ value: JSON.stringify(plotData()) }))
  await ($ as any).session.start({ source: 'startup', cwd: '/work' })
  await run($, 'new n.nb.md')
  await run($, 'select 2')
  const ui = await mount($)
  expect(await ui.find({ type: 'Text', text: 'Time (s)' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'Signal' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'Decay experiment' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'Terminal chart · plotted data' })).toBeDefined()
  expect(await ui.find({ type: 'Raster' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: asset.file })).toBeUndefined()
  await ui.unmount()
})

test('Markdown cells show explanation, Mermaid and readable equations together', async ($, on) => {
  const w = world(on)
  w.view.cells[0].rich = [
    { kind: 'markdown', text: '# The experiment\n\nEnergy is $E=mc^2$.' },
    { kind: 'mermaid', text: 'graph TD\n A[Question] --> B[Experiment]' },
    { kind: 'math', text: 'E=mc^2' },
  ]
  await ($ as any).session.start({ source: 'startup', cwd: '/work' })
  await run($, 'new n.nb.md')
  const ui = await mount($)
  expect(await ui.find({ type: 'Markdown', text: /Energy is E=mc²/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Question/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^E=mc²$/ })).toBeDefined()
  expect(await ui.find({ type: 'Code' })).toBeUndefined()
  await ui.unmount()
})

test('supported terminal uses the light equation preview when the host theme is light', async ($, on) => {
  const w = world(on, { env: { TERM_PROGRAM: 'ghostty' } })
  const asset = { file: '/work/light.png', preview: '/work/light-preview.png', width: 80, height: 20, preview_width: 80, preview_height: 20 }
  w.view.cells[0].rich = [{ kind: 'math', text: 'x^2', light: asset, dark: { ...asset, preview: '/work/dark.png' } }]
  on('config.list', () => ({ value: [{ key: 'theme', value: 'light' }] } as any))
  on('fs.stat', () => ({ value: { kind: 'file', size: 100, mtimeMs: 1, isLink: false } }))
  await ($ as any).session.start({ source: 'startup', cwd: '/work' })
  await run($, 'new n.nb.md')
  const ui = await mount($)
  const image: any = await ui.find({ type: 'Image' })
  expect(image?.props.source.file).toBe('/work/light-preview.png')
  expect(image?.props.columns).toBeLessThanOrEqual(28)
  await ui.unmount()
})

test('native image refusal switches to Raster after the mounted capability probe', async ($, on) => {
  const w = world(on, { env: { TERM_PROGRAM: 'ghostty' } })
  const asset = { file: '/work/probe.png', preview: '/work/probe-preview.png', pixels: '/work/probe-pixels.json', width: 10, height: 10, preview_width: 10, preview_height: 10 }
  w.view.cells[0].rich = [{ kind: 'image', text: 'Probe', asset }]
  on('fs.stat', () => ({ value: { kind: 'file', size: 100, mtimeMs: 1, isLink: false } }))
  on('fs.read', () => ({ value: JSON.stringify({ width: 1, height: 1, rgba: 'ff0000ff' }) }))
  on('ui.blit', () => ({ value: { deny: 'Image draws only alt text on this terminal' } }))
  await ($ as any).session.start({ source: 'startup', cwd: '/work' })
  await run($, 'new n.nb.md')
  const ui = await mount($)
  expect(await ui.find({ type: 'Image' })).toBeDefined()
  await w.clock.advance(300)
  await w.clock.settle()
  await ui.redraw({ title: 'Lab', isFocused: true, bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} } as any)
  expect(await ui.find({ type: 'Raster' })).toBeDefined()
  expect(await ui.find({ type: 'Image' })).toBeUndefined()
  await ui.unmount()
})

test('completed Python cells can expand their source without rerunning', async ($, on) => {
  const w = world(on)
  w.view.cells[1].source = 'a = 1\nb = 2\nc = 3\nlast_line = a + b + c'
  w.view.cells[1].run = { outputs: [{ output_type: 'stream', text: '6' }], images: [], duration_ms: 1, at: 1 }
  await run($, 'new n.nb.md')
  await run($, 'select 2')
  const ui = await mount($)
  expect((await ui.find({ type: 'Code' }))?.props.source).not.toContain('last_line')
  await ui.press({ key: 'lab-code-toggle' })
  expect((await ui.find({ type: 'Code' }))?.props.source).toContain('last_line')
  expect(w.calls.some(c => c.action === 'run')).toBe(false)
  await ui.unmount()
})

test('the editor keeps complete source, blank lines and latest typing when saved', async ($, on) => {
  const w = world(on)
  const original = Array.from({ length: 300 }, (_, i) => `line ${i + 1} ${'long '.repeat(20)}`).join('\n') + '\n\n'
  w.view.cells[0].source = original
  await run($, 'new n.nb.md')
  await run($, 'edit 1')
  const ui = await mount($)
  const first = await ui.find({ type: 'Input' })
  expect(first.props.value).toBe(original)
  const edited = original + 'new final line\n\n'
  await input(ui, edited, 'change')
  expect((await ui.find({ type: 'Input' })).props.key).toBe(first.props.key)
  expect(w.view.cells[0].source).toBe(original)
  await ui.press({ key: 'lab-save-edit' })
  expect(w.view.cells[0].source).toBe(edited)
  expect(w.calls.filter(c => c.action === 'update').length).toBe(1)
  expect(w.calls.some(c => c.action === 'run')).toBe(false)
  await ui.press({ key: 'lab-edit' })
  await input(ui, 'do not save', 'change')
  await ui.press({ key: 'lab-cancel-edit' })
  expect(w.view.cells[0].source).not.toContain('do not save')
  await ui.unmount()
  for (const rows of [8, 12, 24, 60, 100]) for (const columns of [12, 24, 40, 80, 160]) {
    expect(editorRows(rows, columns)).toBeLessThanOrEqual(Math.max(2, rows - 3))
    expect(editorRows(rows, columns)).toBeGreaterThanOrEqual(2)
  }
})

test('stdio discovery becoming ready is observed without creating a loopback server', async ($, on) => {
  const w = world(on, { toolMissing: true })
  on('prompt.submit', (_$: any, e: any) => ({ text: e.text, context: e.context }))
  await run($, 'new n.nb.md')
  w.connectTools()
  const reply = await $.prompt.submit({ text: 'Change cell 2 and run it', wait: false, origin: { kind: 'composer' } })
  expect(w.registrations.length).toBe(0)
  expect(reply.context?.join('\n')).toContain(TOOL)
  expect(reply.context?.join('\n')).toContain('available in this session')
  expect(w.calls.some(c => c.action === 'run')).toBe(false)
})

test('missing stdio discovery leaves commands usable without registering HTTP tools', async ($, on) => {
  const w = world(on, { toolBroken: true })
  const result = await run($, 'tools')
  expect(w.registrations.length).toBe(0)
  expect(result.text).toContain('not available')
  expect(result.text).toContain('/reload-plugins')
  expect(w.calls.length).toBe(0)
  await ($ as any).session.start({ source: 'startup', cwd: '/work' })
  await run($, 'new n.nb.md')
  expect(w.calls.at(-1).action).toBe('new')
  expect(w.registrations.length).toBe(0)
})

test('tool-list exceptions preserve same-kernel fallback and ordinary chat', async ($, on) => {
  const w = world(on, { toolListThrows: true })
  on('prompt.submit', (_$: any, e: any) => ({ text: e.text, context: e.context }))
  await run($, 'new n.nb.md')
  expect((await run($, 'tools')).text).toContain('status check succeeded')
  const reply = await $.prompt.submit({ text: 'Explain the current result', wait: false, origin: { kind: 'composer' } })
  expect(reply.context?.join('\n')).toContain('SAME live notebook kernel')
  expect(w.registrations.length).toBe(0)
  expect(w.calls.some(c => c.action === 'run')).toBe(false)
})

test('legacy notebook tool calls still use their actual permission name', async ($, on) => {
  const w = world(on)
  await run($, 'new n.nb.md')
  const reply = await $.tool.call({ tool: LEGACY_TOOL, action: 'run', id: 'py', revision: 'r1' } as never)
  expect(reply).not.toHaveProperty('deny')
  expect(w.checked).toContain(LEGACY_TOOL)
  expect(w.calls.at(-1).action).toBe('run')
})

test('a broken native tool supplies the exact same-kernel CLI connection without executing Python', async ($, on) => {
  const w = world(on, { toolBroken: true })
  on('prompt.submit', (_$: any, e: any) => ({ text: e.text, context: e.context }))
  await run($, 'new n.nb.md')
  const check = await run($, 'tools')
  expect(check.text).toContain('status check succeeded')
  const reply = await $.prompt.submit({ text: 'Change cell 2 and run it', wait: false, origin: { kind: 'composer' } })
  const text = reply.context?.join('\n') || ''
  expect(text).toContain('SAME live notebook kernel')
  expect(text).toContain('/notebook/bridge.py')
  expect(text).toContain('/tmp/cc-notebook-runtime/test')
  expect(text).toContain('permission checks')
  expect(w.calls.some(c => c.action === 'run')).toBe(false)
  await run($, 'edit 2')
  const editing = await $.prompt.submit({ text: 'Change cell 2', wait: false, origin: { kind: 'composer' } })
  expect(editing.context?.join('\n')).toContain('Finish the open cell edit')
  expect(editing.context?.join('\n')).not.toContain('/notebook/bridge.py')
})

test('CLI instructions preserve path data while avoiding Windows shell backslash escaping', () => {
  const data = JSON.parse(bridgeContext('C:\\my env\\python.exe', 'C:\\my plugin', 'C:\\work\\runtime', 'C:\\work\\λ.nb.md').split('\n').at(-1)!)
  expect(data.argv).toEqual(['C:/my env/python.exe', 'C:/my plugin/notebook/bridge.py', 'request', '--runtime', 'C:/work/runtime'])
  expect(data.stdin.path).toBe('C:/work/λ.nb.md')
  const unix = JSON.parse(bridgeContext('/env/python', '/plugin', '/runtime', '/work/back\\slash.nb.md').split('\n').at(-1)!)
  expect(unix.stdin.path).toBe('/work/back\\slash.nb.md')
})

test('complex LaTeX fallback leads with its full-resolution link instead of pages of raw commands', async ($, on) => {
  const w = world(on)
  const source = '\\boxed{\\frac{1}{2}}'
  const asset = { file: '/work/complex.png', preview: '/work/complex-preview.png', width: 80, height: 20, preview_width: 80, preview_height: 20 }
  w.view.cells[0].rich = [{ kind: 'math', text: source, dark: asset }]
  await ($ as any).session.start({ source: 'startup', cwd: '/work' })
  await run($, 'new n.nb.md')
  const ui = await mount($)
  expect(await ui.find({ type: 'Link', text: 'Open typeset equation' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: source })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /native image display unavailable/ })).toBeDefined()
  await ui.unmount()
})

test('the next chat prompt gets selected cell and execution status without starting Python or generation', async ($, on) => {
  const w = world(on)
  on('prompt.submit', (_$: any, e: any) => ({ text: e.text, context: e.context }))
  const submit = (text: string) => $.prompt.submit({ text, wait: false, origin: { kind: 'composer' } })
  expect((await submit('hello')).context).toBeUndefined()
  await run($, 'new n.nb.md')
  await run($, 'run 2')
  const before = w.calls.length
  const reply = await submit('Explain the cell I just ran')
  expect(reply.text).toBe('Explain the cell I just ran')
  expect(reply.context?.join('\n')).toContain('"number":2')
  expect(reply.context?.join('\n')).toContain('"status":"ok"')
  expect(reply.context?.join('\n')).toContain('42')
  expect(reply.context?.join('\n')).toContain('current sources, outputs and revision')
  expect(w.calls.length).toBe(before)
  expect(w.prompts.length).toBe(0)
  // An unreadable cached result must not block the person's ordinary chat.
  w.view.cells[1].run = { at: 1 }
  await run($, 'refresh')
  const recovered = await submit('hello again')
  expect(recovered.text).toBe('hello again')
  expect(recovered.context).toBeUndefined()
})

test('notebook prompt snapshots bound output and exclude draft source and image payloads', () => {
  expect(notebookContext(initialLab())).toBe(null)
  const v: any = sample()
  v.cells[1].run = { outputs: [{ output_type: 'stream', text: 'data:image/png;base64,AAAA ' + 'x'.repeat(10000) }], images: ['/work/image.png'], execution_count: 3, at: 10, duration_ms: 5 }
  v.cells[1].status = 'stale'
  const context = notebookContext({ ...initialLab(), view: v, selected: 'py', draft: 'PRIVATE_UNSAVED_DRAFT' })!
  expect(context).toContain('"unsavedEdit":true')
  expect(context).toContain('"status":"stale"')
  expect(context).not.toContain('PRIVATE_UNSAVED_DRAFT')
  expect(context).not.toContain('base64')
  expect(context.length).toBeLessThan(4000)
})
