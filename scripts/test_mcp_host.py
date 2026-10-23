"""Exercise real Claude MCP discovery and the shared kernel without model calls.

Requires Claude Code and the notebook requirements in --python (this interpreter
by default). Uses an isolated config, workspace and plugin snapshot. No user
credentials, installed plugins, or notebooks are changed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
TOOL = 'mcp__plugin_cc-notebook_notebook__notebook'
DRIVER = r'''
  on('command.run', { command: 'lab-transport-smoke' }, async ($) => {
    const cmd = async (args: string) => {
      // Claude forbids nested command.run dispatch while a command holds the
      // turn. Call the production handler, retaining the same $/state.
      const result = await labCommand($, {command:'lab',args})
      if (result.text?.includes('Notebook: ') && !result.text.includes('complete.')) throw new Error(result.text)
      return result
    }
    const call = async (args: Record<string,unknown>) => {
      const result = await $.tool.call({tool: 'mcp__plugin_cc-notebook_notebook__notebook', ...args} as never)
      if ('deny' in result || ('isError' in result && result.isError)) throw new Error(JSON.stringify(result))
      if (typeof result.result !== 'string') throw new Error('Tool response was not text')
      return JSON.parse(result.result)
    }
    try {
    await cmd('python ' + (await $.env.get('CC_NOTEBOOK_TEST_PYTHON')))
    await cmd('new checks/transport.nb.md')
    const diagnostic = await cmd('tools')
    if (!diagnostic.text?.includes('Read-only status call succeeded')) throw new Error(String(diagnostic.text))
    let view = await call({action:'status'})
    const id = view.cells.find((c: {type:string}) => c.type === 'python').id
    view = await call({action:'update',id,revision:view.revision,source:'transport_value = 41\nprint(transport_value)'})
    await call({action:'run',id,revision:view.revision})
    const before = await call({action:'status'})
    // This command uses the ordinary bridge. The native tool must see its state.
    await cmd('run 2')
    view = await call({action:'status'})
    if (!view.kernel.alive || view.kernel.id !== before.kernel.id) throw new Error('Native tool and commands used different kernels')
    view = await call({action:'update',id,revision:view.revision,source:'transport_value += 1\nprint(transport_value)'})
    const run = await call({action:'run',id,revision:view.revision})
    const text = JSON.stringify(run.cells[0].run.outputs)
    if (!text.includes('42')) throw new Error('Python state was lost: ' + text)
    if (run.cells.length !== 1) throw new Error('Run reply replayed unrelated cells')
    const result = {connected:true,sameKernel:true,value:42,cellScoped:true,tool:'mcp__plugin_cc-notebook_notebook__notebook'}
    return {text:'CC_NOTEBOOK_TRANSPORT_PASS=' + JSON.stringify(result)}
    } finally { await stopNotebook($) }
  })
'''


class HostDirectory(tempfile.TemporaryDirectory):
    def cleanup(self):
        # Windows can retain a child's current-directory handle briefly after
        # Claude exits. Retry that race instead of hiding cleanup errors.
        for attempt in range(20):
            try:
                return super().cleanup()
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.25)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--claude', default=shutil.which('claude') or shutil.which('claude.exe'))
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--log-dir', type=Path)
    args = parser.parse_args()
    if not args.claude:
        parser.error('Claude Code is not on PATH; pass --claude <executable>.')
    # Preserve venv symlinks: resolving bin/python selects the base interpreter.
    selected = os.path.abspath(args.python)
    subprocess.run([selected, '-I', '-c', 'import ipykernel,jupyter_client,nbformat,matplotlib,pandas,PIL'], check=True)
    with HostDirectory(prefix='notebook transport λ ') as temporary:
        base = Path(temporary)
        plugin, config, workspace = [base / p for p in ('plugin', 'config', 'workspace')]
        for path in (plugin, config, workspace):
            path.mkdir()
        for directory in ('.claude-plugin', 'hooks', 'mcp', 'types', 'notebook', 'render', 'examples'):
            shutil.copytree(ROOT / directory, plugin / directory, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.gitignore', 'types' if directory == '.claude-plugin' else '__absent__'))
        register = plugin / 'hooks/notebook/register.tsx'
        source = register.read_text(encoding='utf-8')
        command_start = "on('command.run', { command: 'lab' }, async ($, e) => {"
        command_end = "  })\n\n  on('ui.render', { component: 'Pane', requestId: PANE }"
        assert source.count(command_start) == source.count(command_end) == 1
        begin = source.index(command_start)
        end = source.index(command_end, begin)
        body = source[begin + len(command_start):end]
        source = source[:begin] + "on('command.run', { command: 'lab' }, labCommand)\n\n" + source[end + len('  })\n\n'):]
        # The host scanner requires named hook functions at module scope.
        source += '\nasync function labCommand($: EngineInterface, e: {command:string,args:string}) {' + body + '\n}\n'
        source = source.replace('export function registerNotebook(on: On) {', 'export function registerNotebook(on: On) {\n' + DRIVER, 1)
        source = source.replace("await $.command.register({ name: 'lab',", "await $.command.register({name:'lab-transport-smoke',description:'Isolated transport test',immediate:true})\n    await $.command.register({ name: 'lab',", 1)
        register.write_text(source, encoding='utf-8')
        log = base / 'host.log'
        env = {**os.environ, 'CLAUDE_CONFIG_DIR':str(config), 'CC_NOTEBOOK_TEST_PYTHON': selected,
               'ANTHROPIC_API_KEY':'sk-ant-local-transport-test-not-a-real-key',
               'ANTHROPIC_BASE_URL':'http://127.0.0.1:9', 'DISABLE_AUTOUPDATER':'1',
               'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC':'1'}
        command = [args.claude, '--plugin-dir', str(plugin), '--setting-sources', '',
                   '--allowedTools', TOOL, '--debug-file', str(log), '--no-session-persistence',
                   '-p', '/lab-transport-smoke']
        result = subprocess.run(command, cwd=workspace, env=env, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=150)
        diagnostics = log.read_text(encoding='utf-8', errors='replace') if log.exists() else ''
        # Logs contain secret loopback endpoints and local messaging tokens.
        # Retain a useful redacted log only when explicitly requested.
        redacted = re.sub(r'https?://[^\s\"<>]+', '[URL redacted]', diagnostics)
        if args.log_dir:
            args.log_dir.mkdir(parents=True, exist_ok=True)
            (args.log_dir / 'mcp-host.log').write_text(redacted, encoding='utf-8')
        output = result.stdout + '\n' + result.stderr
        if result.returncode or 'CC_NOTEBOOK_TRANSPORT_PASS=' not in output:
            print(re.sub(r'https?://[^\s\"<>]+', '[URL redacted]', output[-8000:]))
            raise RuntimeError('Real-host MCP integration failed. Use --log-dir to retain diagnostics.')
        if '$.tool.register: loopback MCP server listening' in diagnostics or 'InvalidHTTPResponse' in diagnostics:
            raise RuntimeError('The notebook still attempted HTTP tool discovery.')
        if '[API REQUEST]' in diagnostics:
            raise RuntimeError('The immediate test command unexpectedly attempted a model request.')
        print(next(line for line in result.stdout.splitlines() if 'CC_NOTEBOOK_TRANSPORT_PASS=' in line))


if __name__ == '__main__':
    main()
