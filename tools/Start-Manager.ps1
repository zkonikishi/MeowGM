param([switch]$Initialize)
$ErrorActionPreference = 'Stop'
$suiteRoot = Split-Path -Parent $PSScriptRoot
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) { $runtime = $pythonCommand.Source } else {
    $runtime = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (-not (Test-Path -LiteralPath $runtime)) { throw 'Install Python 3.11+ first.' }
}
$serverScript = Join-Path $suiteRoot 'services\gateway\server.py'
if ($Initialize) { & $runtime $serverScript --init-admin } else { & $runtime $serverScript }
