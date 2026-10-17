param([string]$Source='')
$ErrorActionPreference='Stop'
if(-not $Source){$Source=if($env:MEOW_UPSTREAM_DIR){$env:MEOW_UPSTREAM_DIR}else{Join-Path $PSScriptRoot '..\upstream\115us-dfolauncher'}}
$revision=(& git -C $Source rev-parse HEAD).Trim()
if($revision -ne '2e80468daec25820beaf3d6eceea79a40c6dda31'){throw 'Upstream GM revision differs from reviewed baseline'}
$workspace=Join-Path $env:TEMP ('meowgm-native-fixture-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $workspace | Out-Null
Copy-Item -LiteralPath (Join-Path $Source 'gm') -Destination $workspace -Recurse
$module=Join-Path $workspace 'gm'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../apps/manager/tests/native_bridge_fixture_test.go') -Destination (Join-Path $module 'cmd/gmtool/meow_fixture_test.go')
$env:GOCACHE=Join-Path $env:TEMP 'go-mod115-cache'
$env:GOMODCACHE=Join-Path $env:TEMP 'go-mod115-cache/modules'
$env:GOTMPDIR=$env:TEMP
$env:GOPROXY='https://goproxy.cn,direct'
$go=if($env:MEOW_GO){$env:MEOW_GO}else{'go'}
Push-Location $module
try {
 & $go test -mod=readonly ./cmd/gmtool -run '^TestMeowNativeBridge(ReadModifyReceipt|Int64Identifiers)$' -count=1 -v
 if($LASTEXITCODE -ne 0){throw 'Native synthetic fixture failed'}
 Write-Output "Native fixture workspace: $workspace"
} finally {Pop-Location}
