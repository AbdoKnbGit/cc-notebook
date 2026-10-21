// Keep the native multiline Input small enough to display its initial value.
// The entire draft stays in state; page navigation never saves or runs a cell.
export const EDIT_LINES = 8
export function editPage(source: string, start = 0) {
  const lines = source.split('\n')
  start = Math.max(0, Math.min(start, lines.length - 1))
  const end = Math.min(lines.length, start + EDIT_LINES)
  return { start, end, total: lines.length, text: lines.slice(start, end).join('\n') }
}

export function replacePage(source: string, start: number, end: number, text: string) {
  const lines = source.split('\n')
  const replacement = text.replace(/\r\n/g, '\n').split('\n')
  lines.splice(start, end - start, ...replacement)
  return { draft: lines.join('\n'), draftEnd: start + replacement.length }
}
