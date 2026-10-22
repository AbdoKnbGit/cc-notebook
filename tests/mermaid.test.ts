import { expect, test } from 'claude-code/testing'
import { mermaidSvg, prepareMermaid } from '../hooks/lib/mermaid'
import { needsRoom, splitSegments } from '../hooks/lib/markdown'
import { findTypst } from '../hooks/lib/typst'

test('Mermaid renders offline SVG with legible colours and no CSS variables in both modes', async () => {
  for (const theme of ['dark', 'light'] as const) {
    const svg = await mermaidSvg('graph LR\nInput --> Hidden\nHidden --> Output', theme)
    expect(svg).toContain('<svg')
    expect(svg).toContain('Input')
    expect(svg).toContain(theme === 'dark' ? '#e6edf3' : '#24292f')
    expect(/var\(|color-mix\(|@import|https:\/\/fonts/.test(svg)).toBe(false)
    expect(svg).not.toContain('background:')
  }
})

test('rendering changes only closed top-level Mermaid fences and preserves surrounding Markdown', async () => {
  const files: Record<string, string> = {}
  const original = '# Neural network\n\n```mermaid\ngraph LR\n A --> B\n```\n\nCell 3 supplied the architecture.'
  const rendered = await prepareMermaid(original, 'dark', '/tmp/job', async (path, svg) => { files[path] = svg })
  expect(rendered).toBe('# Neural network\n\n![Mermaid diagram](</tmp/job/mermaid-1.svg>)\n\nCell 3 supplied the architecture.')
  expect(Object.keys(files)).toEqual(['/tmp/job/mermaid-1.svg'])
  expect(original).toContain('```mermaid')
  for (const source of ['```mermaid\ngraph LR\n A --> B', '````markdown\n```mermaid\ngraph LR\n A --> B\n```\n````', '  ```mermaid\n  graph LR\n  A --> B\n  ```']) {
    expect(await prepareMermaid(source, 'dark', '/tmp/job', async () => { throw new Error('must not write') })).toBe(source)
  }
})

test('bad syntax, size limits and disk failure leave diagram source available', async () => {
  for (const source of ['not a diagram', 'graph LR\n' + 'A --> B;'.repeat(300)]) {
    const text = '```mermaid\n' + source + '\n```'
    expect(await prepareMermaid(text, 'dark', '/tmp/job', async () => undefined)).toBe(text)
  }
  const text = '```mermaid\ngraph LR\nA --> B\n```'
  expect(await prepareMermaid(text, 'light', '/tmp/job', async () => { throw new Error('disk full') })).toBe(text)
  const many = Array(10).fill(text).join('\n\n')
  let writes = 0
  const rendered = await prepareMermaid(many, 'light', '/tmp/job', async () => { writes++ })
  expect(writes).toBe(8)
  expect(rendered.split('```mermaid').length - 1).toBe(2)
})

test('Mermaid participates in resize cache sizing and stays whole at a narrow width', () => {
  const text = '```mermaid\ngraph LR\n' + Array(20).fill('A --> B').join('\n') + '\n```'
  expect(needsRoom(text)).toBe(true)
  expect(splitSegments(text, 20, 10)).toEqual([text])
})

test('chat renderer reuses the notebook managed Typst without installing packages', async () => {
  const calls: string[][] = []
  const $ = {
    plugin: { root: Promise.resolve('/plugin') },
    process: { run: async (argv: string[]) => { calls.push(argv); return { exitCode: 0, stdout: '{"typst":"/home/user/.local/share/cc-notebook/tools/typst"}' } } },
  } as any
  expect(await findTypst($)).toBe('/home/user/.local/share/cc-notebook/tools/typst')
  expect(calls).toEqual([['python3', '/plugin/notebook/setup_env.py', '--find-typst']])
})
