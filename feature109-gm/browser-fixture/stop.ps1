param([Parameter(Mandatory=$true)][int]$FixtureProcessId,
      [Parameter(Mandatory=$true)][string]$ExpectedStartTimeUtc)
$fixtureServerPath = Join-Path $PSScriptRoot 'server.cjs'
$fixtureProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$FixtureProcessId"
if (-not $fixtureProcess) { Write-Output 'Fixture process already exited'; exit 0 }
if ($fixtureProcess.Name -ne 'node.exe' -or -not $fixtureProcess.CommandLine -or
    $fixtureProcess.CommandLine.IndexOf($fixtureServerPath,[StringComparison]::OrdinalIgnoreCase) -lt 0) {
    throw 'Refusing to stop process: executable or absolute fixture server path does not match'
}
$expectedStart = [DateTime]::ParseExact($ExpectedStartTimeUtc,'o',[Globalization.CultureInfo]::InvariantCulture,[Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
$fixtureHandle = Get-Process -Id $FixtureProcessId -ErrorAction Stop
if ($fixtureHandle.StartTime.ToUniversalTime().Ticks -ne $expectedStart.Ticks) {
    throw 'Refusing to stop process: PID start time changed'
}
Stop-Process -InputObject $fixtureHandle -ErrorAction Stop
Write-Output "Stopped verified fixture node process $FixtureProcessId (forced fallback; prefer Ctrl+C for final pin receipt)"
