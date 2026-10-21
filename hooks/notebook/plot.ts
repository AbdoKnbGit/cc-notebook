import { packCells } from './rich'

type Series = { points: ([number, number] | null)[]; color: string; label: string; connected: boolean; dashed: boolean }
type Plot = { version: 1; title: string; xlabel: string; ylabel: string; limits: [number, number, number, number]; series: Series[] }
const DEFAULT = 0x01000000
const label = (text: string) => text.replace(/[\x00-\x1f\x7f]/g, ' ').slice(0, 120)
export const tick = (n: number) => Number(n.toPrecision(3)).toString()

function valid(value: unknown): value is Plot {
  if (!value || typeof value !== 'object') return false
  const p = value as Plot
  return p.version === 1 && [p.title, p.xlabel, p.ylabel].every(s => typeof s === 'string' && s.length <= 160)
    && Array.isArray(p.limits) && p.limits.length === 4 && p.limits.every(Number.isFinite)
    && p.limits[0] !== p.limits[1] && p.limits[2] !== p.limits[3]
    && Array.isArray(p.series) && p.series.length > 0 && p.series.length <= 8
    && p.series.every(s => s && /^#[0-9a-f]{6}$/i.test(s.color) && typeof s.label === 'string' && s.label.length <= 120
      && typeof s.connected === 'boolean' && typeof s.dashed === 'boolean' && Array.isArray(s.points)
      && s.points.every(pt => pt === null || Array.isArray(pt) && pt.length === 2 && pt.every(Number.isFinite)))
    && p.series.reduce((n, s) => n + s.points.length, 0) <= 4096
}

// Liang–Barsky clips a segment before rasterizing. Out-of-view values must
// never become false lines along the axes or unbounded drawing loops.
function clip(x0: number, y0: number, x1: number, y1: number, w: number, h: number) {
  const dx = x1 - x0, dy = y1 - y0
  let start = 0, end = 1
  for (const [p, q] of [[-dx, x0], [dx, w - x0], [-dy, y0], [dy, h - y0]]) {
    if (p === 0) { if (q! < 0) return null; continue }
    const r = q! / p!
    if (p! < 0) start = Math.max(start, r)
    else end = Math.min(end, r)
    if (start > end) return null
  }
  return [x0 + start * dx, y0 + start * dy, x0 + end * dx, y0 + end * dy]
}

export function terminalPlot(value: unknown, width: number, light: boolean) {
  if (!valid(value) || !Number.isFinite(width) || width < 28) return null
  const p = value, columns = Math.min(100, Math.floor(width) - 11), rows = 12
  const w = columns * 2 - 1, h = rows * 4 - 1
  const [xmin, xmax, ymin, ymax] = p.limits
  const dx = xmax - xmin, dy = ymax - ymin
  if (!Number.isFinite(dx) || !Number.isFinite(dy)) return null
  const bits = Array<number>(columns * rows).fill(0), colors = [...bits]
  const dot = (x: number, y: number, color: number) => {
    x = Math.round(x); y = Math.round(y)
    if (x < 0 || x > w || y < 0 || y > h) return
    const at = Math.floor(y / 4) * columns + Math.floor(x / 2)
    bits[at]! |= (x % 2 ? [8, 16, 32, 128] : [1, 2, 4, 64])[y % 4]!
    colors[at] = color
  }
  const legend: { color: string; label: string }[] = []
  for (const series of p.series) {
    let color = parseInt(series.color.slice(1), 16)
    const rgb = [color >>> 16, (color >>> 8) & 255, color & 255]
    const brightness = rgb[0]! * .2126 + rgb[1]! * .7152 + rgb[2]! * .0722
    if ((!light && brightness < 90) || (light && brightness > 180)) {
      color = rgb.map(c => light ? Math.round(c * .6) : Math.min(255, c + 80)).reduce((n, c) => (n << 8) | c, 0)
    }
    legend.push({ color: '#' + color.toString(16).padStart(6, '0'), label: label(series.label) })
    let previous: number[] | null = null
    for (const point of series.points) {
      if (!point) { previous = null; continue }
      const x = (point[0] - xmin) / dx * w, y = (1 - (point[1] - ymin) / dy) * h
      if (!Number.isFinite(x) || !Number.isFinite(y)) return null
      const segment = previous && series.connected ? clip(previous[0]!, previous[1]!, x, y, w, h) : null
      if (segment) {
        const [a, b, c, d] = segment as [number, number, number, number]
        const steps = Math.max(1, Math.ceil(Math.max(Math.abs(c - a), Math.abs(d - b))))
        for (let n = 0; n <= steps; n++) if (!series.dashed || Math.floor(n / 4) % 2 === 0) dot(a + (c - a) * n / steps, b + (d - b) * n / steps, color)
      } else dot(x, y, color)
      previous = [x, y]
    }
  }
  const words: number[] = []
  bits.forEach((mask, i) => words.push(mask ? 0x2800 + mask : 32, mask ? colors[i]! : DEFAULT, DEFAULT))
  return { columns, rows, cells: packCells(words), title: label(p.title), xlabel: label(p.xlabel), ylabel: label(p.ylabel),
    xlabels: [tick(xmin), tick(xmin / 2 + xmax / 2), tick(xmax)],
    ylabels: Array.from({ length: rows }, (_, i) => i === 0 ? tick(ymax) : i === rows - 1 ? tick(ymin) : i === Math.floor(rows / 2) ? tick(ymax + (ymin - ymax) * (i * 4 + 1.5) / h) : ''), legend }
}
