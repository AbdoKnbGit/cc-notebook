import { build } from 'esbuild'
import { mkdir, copyFile, stat } from 'node:fs/promises'
await mkdir('hooks/notebook/vendor', { recursive: true })
await build({
  stdin: { contents: "export { renderMermaidASCII } from './node_modules/beautiful-mermaid/src/ascii/index.ts'", resolveDir: process.cwd() },
  bundle: true, format: 'esm', platform: 'neutral', target: 'es2022', minify: true,
  outfile: 'hooks/notebook/vendor/mermaid.js',
})
await copyFile('node_modules/beautiful-mermaid/LICENSE', 'hooks/notebook/vendor/LICENSE.beautiful-mermaid')
await mkdir('hooks/lib/vendor', { recursive: true })
await build({
  stdin: { contents: "export { renderMermaid as renderMermaidSVG } from 'beautiful-mermaid-svg'", resolveDir: process.cwd() },
  bundle: true, format: 'esm', platform: 'neutral', target: 'es2022', minify: true,
  outfile: 'hooks/lib/vendor/mermaid.js',
})
await copyFile('node_modules/beautiful-mermaid-svg/LICENSE', 'hooks/lib/vendor/LICENSE.beautiful-mermaid')
await copyFile('node_modules/@dagrejs/dagre/LICENSE', 'hooks/lib/vendor/LICENSE.dagre')
await copyFile('node_modules/@dagrejs/graphlib/LICENSE', 'hooks/lib/vendor/LICENSE.graphlib')

// Claude refuses hook modules above 1 MiB, including vendored imports.
for (const file of ['hooks/lib/vendor/mermaid.js', 'hooks/notebook/vendor/mermaid.js']) {
  if ((await stat(file)).size > 1048576) throw new Error(`${file} exceeds Claude's hook module limit`)
}
