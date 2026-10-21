import { expect, mock, test } from 'claude-code/testing'
import { commandOf, parseGenerated, TOOL, PANE } from '../hooks/notebook/model'
import { fitPlot, plotSource, clearImageCache } from '../hooks/notebook/images'

const CMD = { origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 100 } } as const
const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII='
const run = ($: any, args: string) => $.command.run({ command: 'lab', args, ...CMD })
const mount = ($: any, surface = 'terminal') => $.ui.mount({ plugin: 'cc-notebook', surface, component: 'Pane', requestId: PANE, props: { title: 'Lab', isFocused: true, bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} }, viewport: { columns: 80, rows: 40 } })
const sample = () => ({ path: '/work/notebook.nb.md', revision: 'r1', title: 'Experiment', kernel: { alive: false, busy: false, id: null, python: 'python' }, variables: [], activity: [], history_count: 0, cells: [
  { id: 'md', type: 'markdown', source: '# Question', status: 'ready', run: null },
  { id: 'py', type: 'python', source: 'x = 41\nx + 1', status: 'ready', run: null },
  { id: 'ai', type: 'ai', source: 'Explain this result', status: 'ready', run: null },
] })

function world(on: any, options: { answer?: string; deny?: boolean; failedSave?: boolean; env?: Record<string, string> } = {}) {
  mock.store(on)
  mock.clock(on)
  mock.env(on, { DISABLE_AUTOUPDATER: '1', ...options.env })
  on('session.cwd', () => ({ value: '/work' }))
  on('session.id', () => ({ value: 'test-session' }))
  on('session.model', () => ({ value: 'claude-sonnet-4-6' }))
  on('command.register', () => ({ value: undefined }))
  on('tool.register', () => ({ value: undefined }))
  on('session.start', () => ({ cwd: '/work' }))
  on('tool.check', () => ({ decision: options.deny ? 'deny' : 'allow', reason: 'Test permission policy' }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  const view: any = sample(), calls: any[] = [], prompts: string[] = []
  on('model.complete', (_$: any, e: any) => {
    prompts.push(e.prompt)
    return { value: { isAnswered: true, text: options.answer ?? '{"cells":[{"type":"python","source":"x + 2"}]}', usage: { input_tokens: 20, output_tokens: 10, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 } } }
  })
  on('process.run', (_$: any, e: any) => {
    let result: any = {}, error: string | null = null
    if (!String(e.argv[1]).endsWith('/notebook/bridge.py')) return { value: { exitCode: 1, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    if (e.argv[2] === 'start') result = { runtime: '/work/.claude-notebook/runtime/test' }
    else if (e.argv[2] === 'doctor') result = { python: 'python', modules: { ipykernel: true } }
    else {
      const r = JSON.parse(e.init.stdin)
      calls.push(r)
      if (r.action === 'update' && options.failedSave) error = 'Notebook changed on disk. Refresh before saving.'
      else if (r.action === 'update') { view.cells.find((c: any) => c.id === r.id).source = r.source; view.revision = 'r2' }
      else if (r.action === 'add') view.cells.push({ id: 'added', type: r.type, source: r.source ?? '', status: 'ready', run: null })
      else if (r.action === 'run') { view.kernel.alive = true; view.cells.find((c: any) => c.id === r.id).run = { outputs: [{ output_type: 'execute_result', data: { 'text/plain': '42' } }], images: [], duration_ms: 12, at: 1 }; view.cells.find((c: any) => c.id === r.id).status = 'ok' }
      else if (r.action === 'apply_generation') view.cells.push(...r.cells.map((c: any, i: number) => ({ ...c, id: `gen-${i}`, status: 'ready', generated_from: r.id, run: null })))
      result = r.action === 'context' ? { prompt: 'Explain', context: [], context_key: 'ctx' } : view
    }
    return { value: { exitCode: 0, stdout: JSON.stringify(error ? { ok: false, error } : { ok: true, result }), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  return { view, calls, prompts }
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
  await ui.input({ key: 'edit-py', text: 'x = 100' })
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
  await ui.input({ key: 'edit-md', text: 'keep my draft', kind: 'change' })
  await ui.input({ key: 'edit-md', text: 'keep my draft' })
  expect(await ui.find({ type: 'Text', text: /changed on disk/ })).toBeDefined()
  expect((await ui.find({ type: 'Input', key: 'edit-md' })).props.value).toBe('keep my draft')
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
  const reply = await $.tool.call({ tool: TOOL, action: 'open', path: '/work/notebook.nb.md' } as never)
  expect(JSON.stringify(reply)).not.toContain('image/png')
  expect(w.calls[0].action).toBe('open')
  for (const surface of ['terminal', 'desktop', 'vscode'] as const) {
    const ui = await $.ui.mount({ plugin: 'cc-notebook', surface, component: 'ToolResult', requestId: 'notebook-output', props: { tool_use_id: 'notebook-output', tool: TOOL, output: JSON.stringify(w.view), isErrored: false }, viewport: { columns: 100, rows: 40 } } as any)
    if (surface === 'terminal') {
      const shown: any = await ui.find({ type: 'Image' })
      expect(shown?.props.source.file).toBe(file)
    }
    expect(await ui.find({ type: 'Text', text: /Experiment/ })).toBeDefined()
    await ui.unmount()
  }
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
  expect(await ui.find({ type: 'Text', text: file })).toBeDefined()
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
