export type IuiTheme = 'dark' | 'light'
export type CellKind = 'markdown' | 'python' | 'ai'
export type ImageAsset = { file: string; width: number; height: number; preview: string; preview_width: number; preview_height: number; pixels?: string; plot?: string }
export type RichBlock = { kind: 'markdown' | 'mermaid' | 'typst' | 'math' | 'image'; text: string; target?: string; asset?: ImageAsset; dark?: ImageAsset; light?: ImageAsset; error?: string }
export type CellOutput = { output_type: string; text?: string; ename?: string; evalue?: string; traceback?: string[]; data?: Record<string, string>; asset?: ImageAsset; rich?: RichBlock[] }
export type NotebookCell = {
  id: string; type: CellKind; source: string; status: string; generated_from?: string
  rich?: RichBlock[] | null
  run: null | { status: string; outputs: CellOutput[]; duration_ms: number; images: string[]; image_info?: Record<string, Omit<ImageAsset, 'file'>>; execution_count?: number; at: number }
}
export type NotebookView = {
  path: string; title: string; revision: string; cells: NotebookCell[]
  kernel: { alive: boolean; busy: boolean; id: string | null; python: string }
  variables: { name: string; type: string; shape?: string; preview?: string }[]
  activity: { at: number; text: string }[]; history_count: number
}
export type LabState = {
  view: NotebookView | null; selected: string | null; draft: string | null; draftRevision: string | null
  busy: string | null; error: string | null; notice: string | null; cost: number | null; showVars: boolean
  showCode: boolean
  editEpoch: number
  setup: string | null
}

declare module 'claude-code' {
  interface PluginState {
    'cc-notebook': { lab: LabState; done: number; isOn: boolean; uiDone: number }
  }
}
