// Terminal graphics capability checks for Claude Code's native Image element.
export const isSet = (value: string | undefined) =>
  !!value && !/^(0|false|no|off)$/i.test(value.trim())

export function canDrawIn(env: {
  program: string
  term: string
  kitty: boolean
  tmux: boolean
  ssh: boolean
  background: boolean
  engineForced: boolean
  modForced: boolean
}): boolean {
  if (env.background) return false
  if (env.tmux) return env.modForced
  if (env.engineForced || env.modForced) return true
  if (env.ssh) return /ghostty|kitty/i.test(env.term)
  return /ghostty/i.test(env.program + env.term) || /kitty/i.test(env.term) || env.kitty
}
