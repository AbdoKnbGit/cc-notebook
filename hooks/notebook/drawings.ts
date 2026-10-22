import type { EngineInterface } from 'claude-code'
import type { ImageAsset } from '../../types'
import { mermaidSvg } from '../lib/mermaid'

type Preview = { asset?: ImageAsset; error?: string }
const recent = new Map<string, Promise<Preview>>()
export const clearDrawingCache = () => recent.clear()

// The notebook does not use chat's render queue or its on/off preference.
// Only the visible diagram is compiled; repeated redraws share one job.
export async function drawingPreview($: EngineInterface, kind: 'typst' | 'mermaid', source: string, columns: number, rows: number, light: boolean, python: string, typst?: string | null): Promise<Preview> {
  if (source.length > 12000 || source.split('\n').length > 160) return { error: 'Diagram exceeds the live preview limit.' }
  const workspace = await $.session.cwd()
  columns = Math.max(8, Math.min(120, Math.floor(columns)))
  rows = Math.max(3, Math.min(40, Math.floor(rows)))
  const theme = light ? 'light' : 'dark'
  const key = JSON.stringify([workspace, kind, source, columns, rows, theme, python, typst])
  let pending = recent.get(key)
  if (pending) {
    const result = await pending
    if (!result.asset || await $.fs.stat(result.asset.preview).then(s => s.kind === 'file', () => false)) return result
    recent.delete(key)
  }
  pending = compileDrawing($, workspace, kind, source, columns, rows, theme, python, typst)
  if (recent.size >= 24) recent.delete(recent.keys().next().value!)
  recent.set(key, pending)
  const result = await pending
  // Errors are retained too, avoiding repeated processes on every UI redraw.
  // Refresh, reopening the notebook or /lab setup clears the memory cache.
  return result
}

async function compileDrawing($: EngineInterface, workspace: string, kind: 'typst' | 'mermaid', source: string, columns: number, rows: number, theme: 'dark' | 'light', python: string, typst?: string | null): Promise<Preview> {
  try {
    const svg = kind === 'mermaid' ? await mermaidSvg(source, theme, { width: columns * 10, height: rows * 20 }) : undefined
    const ran = await $.process.run([python, `${$.plugin.root}/notebook/drawing.py`], {
      stdin: JSON.stringify({ workspace, kind, source, columns, rows, theme, svg }), timeoutMs: 20000,
      env: { PYTHONUTF8: '1', ...(typst ? { CLAUDE_NOTEBOOK_TYPST: typst } : {}) },
    })
    if (ran.isStdoutTruncated) return { error: 'Diagram preview reply was truncated.' }
    const reply = JSON.parse(ran.stdout)
    return reply.ok && reply.asset ? { asset: reply.asset } : { error: reply.error || 'Diagram preview unavailable.' }
  } catch (error) { return { error: error instanceof Error ? error.message : String(error) } }
}

// Previews are compiled at 12 x 24 pixels per cell. Keep a small diagram
// at its text-sized scale rather than stretching it to fill the pane.
export function drawingBox(asset: ImageAsset, columns: number, rows: number) {
  const scale = Math.min(1, Math.max(1, columns) * 12 / asset.width, Math.max(1, rows) * 24 / asset.height)
  return { columns: Math.max(1, Math.min(columns, Math.ceil(asset.width * scale / 12))), rows: Math.max(1, Math.min(rows, Math.ceil(asset.height * scale / 24))) }
}
