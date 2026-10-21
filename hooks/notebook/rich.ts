import { renderMermaidASCII } from './vendor/mermaid.js'

const diagramCache = new Map<string, string | null>()
export function diagram(source: string, columns: number): string | null {
  if (source.length > 4000 || source.split('\n').length > 60 || !/^(?:\s*%%[^\n]*\n)*\s*(?:graph|flowchart|sequenceDiagram|stateDiagram(?:-v2)?|classDiagram|erDiagram|xychart(?:-beta)?)\b/i.test(source)) return null
  // Wide, combining, and directional control characters can corrupt text layout.
  if (/[^\x20-\x7e\n\r\t\u00c0-\u024f\u0370-\u052f]/u.test(source)) return null
  const key = `${columns}:${source}`
  if (diagramCache.has(key)) return diagramCache.get(key)!
  let result: string | null = null
  try {
    const draw = (s: string) => renderMermaidASCII(s, { colorMode: 'none', paddingX: 2, paddingY: 1, boxBorderPadding: 0 }).trimEnd()
    result = draw(source)
    const fits = (s: string) => s.split('\n').length <= 100 && s.split('\n').every(line => line.length <= columns)
    if (!fits(result) && /^\s*(?:graph|flowchart)\s+(LR|RL)\b/i.test(source)) result = draw(source.replace(/^(\s*(?:graph|flowchart)\s+)(LR|RL)\b/i, '$1TD'))
    if (!fits(result)) result = null
  } catch { result = null }
  if (diagramCache.size >= 48) diagramCache.delete(diagramCache.keys().next().value!)
  diagramCache.set(key, result)
  return result
}

const symbols: Record<string, string> = { alpha: 'α', beta: 'β', gamma: 'γ', delta: 'δ', theta: 'θ', lambda: 'λ', mu: 'μ', pi: 'π', sigma: 'σ', tau: 'τ', phi: 'φ', omega: 'ω', Delta: 'Δ', Sigma: 'Σ', Omega: 'Ω', sum: '∑', prod: '∏', int: '∫', infty: '∞', pm: '±', times: '×', cdot: '·', le: '≤', leq: '≤', ge: '≥', geq: '≥', neq: '≠', approx: '≈', in: '∈', partial: '∂', nabla: '∇', to: '→' }
export function mathText(source: string): string {
  if (source.length > 4000) return source.slice(0, 4000) + '…'
  let text = source.replace(/\\(?:left|right)\b/g, '').replace(/\\([A-Za-z]+)/g, (whole, name: string) => symbols[name] ?? whole)
  for (let n = 0; n < 8; n++) {
    const next = text.replace(/\\frac\{([^{}]*)\}\{([^{}]*)\}/g, '($1)/($2)').replace(/\\sqrt\{([^{}]*)\}/g, '√($1)').replace(/\\(?:text|mathrm|mathbf)\{([^{}]*)\}/g, '$1')
    if (next === text) break
    text = next
  }
  // Unknown commands remain visible instead of presenting a misleading equation.
  if (/\\[A-Za-z]/.test(text)) return source
  return text.replace(/e\^\{([^{}]+)\}/g, 'exp($1)').replace(/\^\{([0-9+-]+)\}|\^([0-9+-])/g, (_m, a: string, b: string) => [...(a ?? b)].map(c => '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻'['0123456789+-'.indexOf(c)]).join(''))
    .replace(/_\{([0-9+-]+)\}|_([0-9+-])/g, (_m, a: string, b: string) => [...(a ?? b)].map(c => '₀₁₂₃₄₅₆₇₈₉₊₋'['0123456789+-'.indexOf(c)]).join('')).replace(/\\[,;! ]/g, ' ')
}

export function inlineMath(source: string): string {
  // Protect fenced/inline code and links before recognizing math delimiters.
  return source.split(/(`{3,}[\s\S]*?`{3,}|~{3,}[\s\S]*?~{3,}|`+[^`\n]*`+|!?\[[^\]\n]*\]\([^\n]*?\))/g).map((part, index) => {
    if (index % 2 || part.startsWith('    ') || part.startsWith('\t')) return part
    return part.replace(/(?<!\\)\\\(([^\n]*?)\\\)|(?<![\\$])\$(?![\s\d$])([^\n$]+?)(?<!\s)\$(?!\d|\$)/g, (_m, a: string, b: string) => mathText(a ?? b))
  }).join('')
}

export type Pixels = { width: number; height: number; rgba: string }
export function imageUri(path: string): string {
  const normalized = path.replace(/\\/g, '/')
  const prefix = normalized.startsWith('//') ? 'file:' : normalized.startsWith('/') ? 'file://' : 'file:///'
  return prefix + normalized.split('/').map((part, i) => i === 0 && /^[A-Za-z]:$/.test(part) ? part : encodeURIComponent(part)).join('/')
}
const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
export function packCells(words: number[]): string {
  const bytes = words.flatMap(n => [n & 255, (n >>> 8) & 255, (n >>> 16) & 255, (n >>> 24) & 255])
  let encoded = ''
  for (let i = 0; i < bytes.length; i += 3) {
    const n = (bytes[i]! << 16) | ((bytes[i + 1] ?? 0) << 8) | (bytes[i + 2] ?? 0)
    encoded += alphabet[(n >>> 18) & 63]! + alphabet[(n >>> 12) & 63]! + (i + 1 < bytes.length ? alphabet[(n >>> 6) & 63] : '=') + (i + 2 < bytes.length ? alphabet[n & 63] : '=')
  }
  return encoded
}
export function raster(pixels: Pixels, columns: number, rows: number, light: boolean): string | null {
  if (!Number.isInteger(columns) || !Number.isInteger(rows) || columns < 1 || rows < 1 || columns > 120 || rows > 40) return null
  const { width, height, rgba } = pixels
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width > 96 || height > 96 || !/^[a-f0-9]+$/i.test(rgba) || rgba.length !== width * height * 8) return null
  const words: number[] = []
  const pixel = (x: number, y: number) => {
    const at = (y * width + x) * 8
    const alpha = parseInt(rgba.slice(at + 6, at + 8), 16) / 255
    if (alpha === 0) return 0x01000000
    const channels = [0, 2, 4].map(offset => Math.round(parseInt(rgba.slice(at + offset, at + offset + 2), 16) * alpha + (light ? 255 : 24) * (1 - alpha)))
    // Reduce colour churn; the host quantizes any excess distinct pairs.
    return channels.map(v => Math.round(v / 36.43) * 36).reduce((n, v) => (n << 8) | v, 0)
  }
  for (let y = 0; y < rows; y++) for (let x = 0; x < columns; x++) {
    const sx = Math.min(width - 1, Math.floor(x * width / columns))
    const top = pixel(sx, Math.min(height - 1, Math.floor(y * height / rows)))
    const bottom = pixel(sx, Math.min(height - 1, Math.floor((y * 2 + 1) * height / (rows * 2))))
    words.push(top === 0x01000000 ? bottom === top ? 32 : 0x2584 : 0x2580, top === 0x01000000 ? bottom : top, top === 0x01000000 ? top : bottom)
  }
  return packCells(words)
}
