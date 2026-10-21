import { build } from 'esbuild'
import { mkdir, copyFile } from 'node:fs/promises'
await mkdir('hooks/notebook/vendor', { recursive: true })
await build({
  stdin: { contents: "export { renderMermaidASCII } from './node_modules/beautiful-mermaid/src/ascii/index.ts'", resolveDir: process.cwd() },
  bundle: true, format: 'esm', platform: 'neutral', target: 'es2022', minify: true,
  outfile: 'hooks/notebook/vendor/mermaid.js',
})
await copyFile('node_modules/beautiful-mermaid/LICENSE', 'hooks/notebook/vendor/LICENSE.beautiful-mermaid')
