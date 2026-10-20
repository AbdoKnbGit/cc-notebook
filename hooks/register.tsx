import type { Register } from 'claude-code'
import { registerNotebook, startNotebook, stopNotebook } from './notebook/register'

export const register: Register = on => {
  registerNotebook(on)
  on('session.start', async ($, e, next) => {
    await startNotebook($)
    return next(e)
  })
  on('session.end', async ($, e, next) => {
    await stopNotebook($, e.reason)
    return next(e)
  })
}
