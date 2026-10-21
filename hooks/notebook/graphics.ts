// Capability policy for Claude Code's Image element, not the terminal's full
// protocol set. In particular, the host has no Sixel Image backend yet.
export type Graphics = { native: boolean; bytes: boolean; reason: string; forceIgnored: boolean }
const isSet = (value?: string) => !!value?.trim() && !/^(0|false|no|off)$/i.test(value.trim())

export function notebookGraphics(env: Record<string, string | undefined>): Graphics {
  const program = env.TERM_PROGRAM ?? ''
  const term = env.TERM ?? ''
  const ssh = !!(env.SSH_CONNECTION || env.SSH_TTY)
  const forced = isSet(env.CLAUDE_CODE_FORCE_TERMINAL_IMAGES)
  const fallback = (reason: string): Graphics => ({ native: false, bytes: ssh, reason, forceIgnored: forced })
  if (['bg', 'background'].includes(env.CLAUDE_CODE_SESSION_KIND ?? '')) return fallback('Background sessions cannot display terminal images.')
  if (env.TMUX || env.STY) return fallback('Claude Code does not pass image graphics through tmux or screen.')
  if (/vscode/i.test(program)) return fallback('The VS Code terminal cannot display Claude Code\'s native image protocol.')
  // An explicit program takes precedence over inherited Windows Terminal IDs.
  // Over SSH, TERM identifies the client; server-local window IDs do not.
  if (/windows[_ -]?terminal/i.test(program) || (!ssh && !program && env.WT_SESSION)) {
    return fallback('Windows Terminal uses Sixel, which Claude Code\'s Image element does not support yet.')
  }
  if (/^iterm\.app$/i.test(program)) {
    if (isSet(env.CLAUDE_CODE_ALT_SCREEN_FULL_REPAINT)) return fallback('iTerm2 images require CLAUDE_CODE_ALT_SCREEN_FULL_REPAINT to be unset.')
    return { native: true, bytes: true, reason: 'iTerm2 native images use PNG bytes. Requires iTerm2 3.5+, Claude Code 2.1.305+ and /tui fullscreen.', forceIgnored: false }
  }
  const kitty = ssh ? /kitty|ghostty/i.test(term) : /kitty|ghostty/i.test(program + ' ' + term) || !!env.KITTY_WINDOW_ID
  if (kitty) return { native: true, bytes: ssh, reason: 'Kitty/Ghostty native images requested; the host checks availability when drawing.', forceIgnored: false }
  return fallback('No compatible native image terminal detected. Installing a renderer or forcing images cannot add support to the host.')
}

export function graphicsReport(graphics: Graphics): string {
  return [
    `Notebook graphics: ${graphics.native ? 'native images requested' : 'terminal previews'}.`,
    graphics.reason,
    ...(graphics.forceIgnored ? ['CLAUDE_CODE_FORCE_TERMINAL_IMAGES is ignored here to prevent broken image placeholders.'] : []),
    ...(!graphics.native ? ['Equations use readable text, line charts use plotted data, and other images use thumbnails. Original images and typeset equations remain available through their links.'] : []),
  ].join('\n')
}
