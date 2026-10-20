import type { EngineInterface } from 'claude-code'

// Inspired by show-your-work's file/SSH transport and resize-generation design.
// Previews are immutable, content-addressed PNGs prepared by portable Python.
const recent = new Map<string, string>()
const MAX_BYTES = 2 * 1024 * 1024
export const clearImageCache = () => recent.clear()

export function fitPlot(width: number, height: number, columns: number, rows: number) {
  const maxCols = Math.max(1, Math.min(120, Math.floor(columns)))
  const maxRows = Math.max(1, Math.min(40, Math.floor(rows)))
  const aspect = width > 0 && height > 0 ? width / height : 4 / 3
  const cols = Math.max(1, Math.min(maxCols, Math.floor(maxRows * 2 * aspect)))
  return { columns: cols, rows: Math.max(1, Math.min(maxRows, Math.ceil(cols / aspect / 2))) }
}

export async function plotSource($: EngineInterface, file: string, box: { columns: number; rows: number }, bytes: boolean) {
  try {
    const stat = await $.fs.stat(file)
    if (stat.kind !== 'file' || stat.size > MAX_BYTES) return null
    if (!bytes) return { file, format: 'png' as const, generation: box.columns * 1000 + box.rows }
    const key = `${file}:${stat.size}:${stat.mtimeMs}`
    let png = recent.get(key)
    if (!png) {
      const raw = await $.fs.read(file, { as: 'bytes' })
      png = raw.base64
      if (Math.ceil(png.length * 3 / 4) > MAX_BYTES) return null
      // Bound retained base64 to three <=2 MiB images; no render-time processes.
      if (recent.size >= 3) recent.delete(recent.keys().next().value!)
      recent.set(key, png)
    }
    return { png }
  } catch { return null }
}
