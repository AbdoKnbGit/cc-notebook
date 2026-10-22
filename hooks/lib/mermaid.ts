// Mermaid is a presentation transform only. The conversation and notebook
// retain the editable source; cached SVGs belong to this answer's render key.
import { renderMermaidSVG } from './vendor/mermaid.js'
import { FENCE } from './markdown'

const MAX_SOURCE = 12000
const MAX_BLOCKS = 8

export async function mermaidSvg(source: string, theme: 'dark' | 'light', box?: { width: number; height: number }): Promise<string> {
  if (source.length > MAX_SOURCE || source.split(/[\n;]/).length > 160 || (source.match(/--|==|\.\./g) ?? []).length > 250) {
    throw new Error('Diagram too large for live rendering')
  }
  const dark = theme === 'dark'
  const fg = dark ? '#e6edf3' : '#24292f'
  const bg = dark ? '#242424' : '#ffffff'
  // Typst's SVG reader has no CSS custom properties or web fonts. Resolve
  // the vendor's complete palette to concrete colours, and use local fonts.
  const colours: Record<string, string> = {
    bg, fg, _text: fg, '_text-sec': dark ? '#c1c7cf' : '#4c5563',
    '_text-muted': dark ? '#a1a9b4' : '#59636e', '_text-faint': dark ? '#848d97' : '#6e7781',
    _line: dark ? '#8ca1b8' : '#637c97', _arrow: dark ? '#8cbbff' : '#2563eb',
    '_node-fill': dark ? '#303947' : '#eff6ff', '_node-stroke': dark ? '#8ca1b8' : '#637c97',
    '_group-fill': bg, '_group-hdr': dark ? '#303947' : '#eff6ff',
    '_inner-stroke': dark ? '#637083' : '#b7c3d0', '_key-badge': dark ? '#38475d' : '#e0ecff',
  }
  const options = { bg, fg, transparent: true, font: 'DejaVu Sans' }
  let rendered = await renderMermaidSVG(source, options)
  // Long horizontal graphs otherwise become unreadable postage stamps in
  // a narrow pane. Choose a vertical layout only when its fitted labels
  // would be substantially larger. This never changes the saved source.
  if (box && /^\s*(?:graph|flowchart)\s+(?:LR|RL)\b/i.test(source)) {
    const fit = (svg: string) => {
      const width = Number(/<svg[^>]*\bwidth="([\d.]+)"/.exec(svg)?.[1])
      const height = Number(/<svg[^>]*\bheight="([\d.]+)"/.exec(svg)?.[1])
      return width > 0 && height > 0 ? Math.min(1, box.width / width, box.height / height) : 1
    }
    if (fit(rendered) < 0.7) {
      const vertical = await renderMermaidSVG(source.replace(/^(\s*(?:graph|flowchart)\s+)(LR|RL)\b/i, '$1TD'), options)
      if (fit(vertical) > fit(rendered) * 1.15) rendered = vertical
    }
  }
  const svg = rendered
    .replace(/<style>[\s\S]*?<\/style>/g, '<style>text { font-family: "DejaVu Sans", sans-serif; } .mono { font-family: monospace; }</style>')
    .replace(/var\(--([\w-]+)\)/g, (_, key: string) => colours[key] ?? '')
    .replace(/ style="--[^"]*"/g, '')
  if (svg.length > 2000000 || /<script|<foreignObject|\b(?:href|src)\s*=\s*["'](?!#)|var\(|color-mix\(|@import|\bon\w+\s*=/i.test(svg)) {
    throw new Error('Diagram requires unsupported SVG features')
  }
  return svg
}

export async function prepareMermaid(
  text: string,
  theme: 'dark' | 'light',
  dir: string,
  write: (path: string, svg: string) => Promise<unknown>,
  box?: { width: number; height: number },
): Promise<string> {
  if (!/mermaid/i.test(text)) return text
  const lines = text.replace(/\r\n?/g, '\n').split('\n')
  const result: string[] = []
  let count = 0
  for (let i = 0; i < lines.length; i++) {
    const start = FENCE.exec(lines[i]!)
    if (!start) { result.push(lines[i]!); continue }
    let end = i + 1
    for (; end < lines.length; end++) {
      const close = FENCE.exec(lines[end]!)
      if (close && close[2]![0] === start[2]![0] && close[2]!.length >= start[2]!.length && lines[end]!.trim() === close[2]) break
    }
    const original = lines.slice(i, end + 1)
    // Only complete, top-level fences are executable diagrams. An example
    // nested in a longer code fence and a streaming partial remain code.
    if (end < lines.length && start[1] === '' && /^mermaid$/i.test(start[3] ?? '') && count < MAX_BLOCKS) {
      count++
      try {
        const svg = await mermaidSvg(lines.slice(i + 1, end).join('\n'), theme, box)
        const path = `${dir}/mermaid-${count}.svg`
        await write(path, svg)
        result.push(`![Mermaid diagram](<${path.replace(/ /g, '%20')}>)`)
      } catch { result.push(...original) }
    } else result.push(...original)
    i = end
  }
  return result.join('\n')
}
