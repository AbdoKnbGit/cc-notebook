import type { EngineInterface } from 'claude-code'

export type RuntimeChoice = { python: string; typst?: string | null; latex?: boolean; warning?: string | null; home?: string; log?: string }

export async function configuredPython($: EngineInterface) {
  const saved = await $.store.get('lab-python')
  return saved === 'auto' ? null : (typeof saved === 'string' && saved ? saved : await $.env.get('CLAUDE_NOTEBOOK_PYTHON')) || null
}

export async function setupRuntime($: EngineInterface, progress: (text: string | null) => Promise<void>, repair = false): Promise<RuntimeChoice> {
  await progress('Finding Python 3.10 or newer…')
  const configured = await configuredPython($)
  const windows = await $.env.get('OS') === 'Windows_NT'
  const candidates = [...(configured ? [[configured]] : []), ...(windows ? [['py', '-3'], ['python'], ['python3']] : [['python3'], ['python']])]
  let base: string | null = null
  for (const candidate of candidates) {
    try {
      const result = await $.process.run([...candidate, '-I', '-c', 'import sys; print(sys.executable if sys.version_info >= (3, 10) else "")'], { timeoutMs: 10000, env: { PYTHONUTF8: '1' } })
      if (result.exitCode === 0 && result.stdout.trim()) { base = result.stdout.trim(); break }
    } catch { /* Try another conventional interpreter name. */ }
  }
  if (!base) throw new Error('Python 3.10 or newer was not found. Install Python, reopen your terminal, then run /lab setup. On Windows, enable the Python installer’s PATH option.')
  const stream = $.process.spawn({ argv: [base, `${$.plugin.root}/notebook/setup_env.py`, ...(repair ? ['--repair'] : [])], env: { PYTHONUTF8: '1' } })
  let buffer = '', reply: { ok?: boolean; result?: RuntimeChoice; error?: string } | null = null
  for await (const chunk of stream) {
    if (chunk.stream !== 'stdout') continue
    buffer += chunk.text
    if (buffer.length > 64000) throw new Error('Unexpected setup output. Run /lab setup to retry.')
    let newline: number
    while ((newline = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, newline).trim()
      buffer = buffer.slice(newline + 1)
      if (!line) continue
      const event = JSON.parse(line)
      if (typeof event.progress === 'string') await progress(event.progress)
      if (typeof event.ok === 'boolean') reply = event
    }
  }
  const end = await stream.result
  if (end.code !== 0 || !reply?.ok || !reply.result?.python) throw new Error(reply?.error || 'Notebook setup stopped before completion. Run /lab setup to retry.')
  return reply.result
}
