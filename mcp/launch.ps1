# Keep paths as arguments: CMD would expand %, & and other path characters.
$ErrorActionPreference = 'Stop'
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $OutputEncoding
[Console]::OutputEncoding = $OutputEncoding

$candidates = @()
if ($env:CLAUDE_NOTEBOOK_PYTHON) {
    $candidates += @{ command = $env:CLAUDE_NOTEBOOK_PYTHON; prefix = @() }
}
$candidates += @{ command = 'py'; prefix = @('-3') }
$candidates += @{ command = 'python3'; prefix = @() }
$candidates += @{ command = 'python'; prefix = @() }
$selected = $null
$check = 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
foreach ($candidate in $candidates) {
    try {
        if ([System.IO.Path]::IsPathRooted($candidate.command)) {
            if (-not (Test-Path -LiteralPath $candidate.command -PathType Leaf)) { continue }
            $executable = $candidate.command
        } else {
            $executable = (Get-Command -Name $candidate.command -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
        }
        $probeArgs = @($candidate.prefix) + @('-I', '-S', '-c', $check)
        & $executable @probeArgs *> $null
        if ($LASTEXITCODE -eq 0) {
            $selected = @{ command = $executable; prefix = $candidate.prefix }
            break
        }
    } catch {
        # An old or removed interpreter must not prevent ordinary discovery.
    }
}
if ($null -eq $selected) {
    [Console]::Error.WriteLine('cc-notebook: Python 3.10 or newer is required. Install Python, reopen the terminal, then retry the plugin.')
    exit 1
}
$serverArgs = @($selected.prefix) + @('-I', '-S', '-X', 'utf8', (Join-Path $PSScriptRoot 'server.py'))
& $selected.command @serverArgs
exit $LASTEXITCODE
