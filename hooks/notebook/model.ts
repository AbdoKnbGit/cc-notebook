import type { CellOutput, LabState, NotebookView } from '../../types'
export type { CellKind, CellOutput, LabState, NotebookView, NotebookCell } from '../../types'
export const initialLab = (): LabState => ({ view: null, selected: null, draft: null, draftRevision: null, busy: null, error: null, notice: null, cost: null, showVars: false, showCode: false })
export const PANE = 'cc-lab'
export const TOOL = 'mcp__cc-notebook__notebook'
export const actions = ['status', 'new', 'demo', 'open', 'add', 'update', 'remove', 'move', 'run', 'run_all', 'vars', 'restart', 'interrupt', 'export', 'import'] as const
export const cleanText = (text: string) => text.replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, '').replace(/[\x00-\x08\x0b-\x1f\x7f]/g, '')
const modelText = (text: string) => cleanText(text).replace(/data:image\/[\w.+-]+;base64,[A-Za-z0-9+/=]+/g, '[embedded image omitted]')
export function outputText(output: CellOutput): string {
  return cleanText(output.text ?? output.data?.['text/plain'] ?? [output.ename, output.evalue, ...(output.traceback ?? [])].filter(Boolean).join('\n'))
}
export function parseGenerated(text: string): { type: 'python' | 'markdown'; source: string }[] {
  const parsed = JSON.parse(text.trim().replace(/^```(?:json)?\s*\n/, '').replace(/\n```\s*$/, ''))
  if (!parsed || !Array.isArray(parsed.cells) || parsed.cells.length < 1 || parsed.cells.length > 8) throw new Error('AI reply must contain 1–8 cells. Nothing was changed.')
  for (const c of parsed.cells) {
    if (!c || !['python', 'markdown'].includes(c.type) || typeof c.source !== 'string' || c.source.length > 100000) throw new Error('AI returned an invalid cell. Nothing was changed.')
  }
  return parsed.cells.map((c: { type: 'python' | 'markdown'; source: string }) => ({ type: c.type, source: c.source }))
}
export function commandOf(raw: string): { action: string; value: string } {
  const text = raw.trim()
  const at = text.indexOf(' ')
  return { action: (at < 0 ? text : text.slice(0, at)).toLowerCase() || 'show', value: (at < 0 ? '' : text.slice(at + 1)).trim().replace(/^"(.*)"$/, '$1') }
}
export function compactView(view: NotebookView) {
  const blocks = (rich: NotebookView['cells'][number]['rich']) => rich?.map(b => ({ ...b, text: modelText(b.text), target: b.target ? modelText(b.target) : undefined }))
  return { ...view, activity: view.activity.slice(-3), cells: view.cells.map(c => ({ ...c, rich: blocks(c.rich), source: modelText(c.source).slice(0, 12000), run: c.run ? { ...c.run, outputs: c.run.outputs.map(o => ({ output_type: o.output_type, text: modelText(outputText(o)).slice(0, 5000), asset: o.asset, rich: blocks(o.rich) })) } : null })) }
}
