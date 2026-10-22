// Development smoke test: real Typst compilation, no network or model calls.
// npm ci, then node scripts/test_visuals.mjs (requires Python and /lab setup).
import { build } from 'esbuild'
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const root = process.cwd()
const out = path.join(root, '.cache', 'transcript-previews')
await mkdir(out, { recursive: true })
const slash = p => p.replaceAll('\\', '/')
const typstPath = p => slash(p).replace(/^[A-Za-z]:/, '')
let typst
for (const python of ['python3', 'python']) {
  const found = spawnSync(python, ['notebook/setup_env.py', '--find-typst'], { encoding: 'utf8' })
  try { typst = JSON.parse(found.stdout).typst } catch {}
  if (typst) break
}
if (!typst) throw new Error('Run /lab setup first to install Typst.')
await build({ entryPoints: ['hooks/lib/mermaid.ts'], bundle: true, format: 'esm', platform: 'node', outfile: path.join(out, 'mermaid.mjs') })
const { prepareMermaid } = await import(pathToFileURL(path.join(out, 'mermaid.mjs')))
const cases = path.join(root, 'tests', 'fixtures', 'transcript')
const files = (await readdir(cases)).filter(f => f.endsWith('.md')).sort()
let count = 0
for (const file of files) {
  for (const mode of ['dark', 'light']) {
    for (const width of [280, 700]) {
      const folder = path.join(out, `${file.slice(0, -3)}-${mode}-${width}`)
      await mkdir(folder, { recursive: true })
      const source = await readFile(path.join(cases, file), 'utf8')
      const rendered = await prepareMermaid(source, mode, slash(folder), writeFile)
      const text = process.platform === 'win32' ? rendered.replaceAll(slash(path.parse(root).root), '/') : rendered
      if (source.includes('```mermaid') && text.includes('```mermaid')) throw new Error(`Mermaid was not rendered: ${file}`)
      const doc = path.join(folder, 'doc.json')
      await writeFile(doc, JSON.stringify({ base: typstPath(cases), segments: [text] }))
      const input = { theme: mode, width, grid: width === 700 ? 1 : 0, height: 300, 'design-w': width, 'design-h': 300, top: 0, row: 14, doc: typstPath(doc), 'theme-dir': typstPath(path.join(root, 'render/themes/claude-code')) }
      const result = spawnSync(typst, ['compile', '--root', path.parse(root).root, '--package-path', 'render/packages', '--format', 'png', '--ppi', '144', ...Object.entries(input).flatMap(([k, v]) => ['--input', `${k}=${v}`]), 'render/md.typ', path.join(folder, 'page-{0p}.png')], {
        encoding: 'utf8', timeout: 60000,
        env: { ...process.env, HTTP_PROXY: 'http://127.0.0.1:9', HTTPS_PROXY: 'http://127.0.0.1:9', ALL_PROXY: 'http://127.0.0.1:9', TYPST_PACKAGE_CACHE_PATH: path.join(out, 'empty-packages') },
      })
      if (result.status !== 0) throw new Error(`${file} ${mode} ${width}: ${result.stderr || result.error}`)
      const pages = (await readdir(folder)).filter(f => f.endsWith('.png'))
      if (!pages.length) throw new Error(`No PNG: ${file}`)
      for (const page of pages) {
        const bytes = await readFile(path.join(folder, page))
        if (bytes.length < 100 || bytes.readUInt32BE(16) < 100 || bytes.readUInt32BE(20) < 20) throw new Error(`Empty PNG: ${file}`)
      }
      count++
      console.log(`PASS ${file} ${mode} ${width}pt`)
    }
  }
}
console.log(`${count} real offline renders passed. Previews: ${out}`)
