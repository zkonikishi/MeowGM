param(
    [string]$Python='C:/rust-toolchain/meowgm-build/Scripts/python.exe',
    [string]$ReleaseName='',
    [string]$OutputRoot='C:/dev-toolchain/releases/MeowGM',
    [switch]$SkipHostBuild,
    [switch]$IncludeSimulationTools
)
$ErrorActionPreference='Stop'
$suiteRoot=Split-Path -Parent $PSScriptRoot
# MeowGM has its own version source, independent from the launcher.
$managerManifest=Get-Content (Join-Path $suiteRoot 'apps/manager/src-tauri/Cargo.toml') -Raw
if($managerManifest -notmatch '(?m)^version\s*=\s*"([^"]+)"'){throw 'Manager package version missing'}
$managerVersion=$matches[1]
if(!$ReleaseName){$ReleaseName=$managerVersion}
$configPath=Join-Path $suiteRoot 'apps/manager/src-tauri/tauri.conf.json'
$config=Get-Content $configPath -Raw | ConvertFrom-Json
if($config.version -ne $managerVersion){$config.version=$managerVersion;$config | ConvertTo-Json -Depth 20 | Set-Content $configPath -Encoding utf8}
if($ReleaseName -notmatch '^[A-Za-z0-9._-]+$'){throw 'Invalid release directory name'}
$env:CARGO_HOME='C:/rust-toolchain/cargo'
$env:RUSTUP_HOME='C:/rust-toolchain/rustup'
$env:PATH="$env:CARGO_HOME/bin;$env:PATH"
$env:MEOW_LAUNCHER_EDITION='sponsor' # Shared updater wire compatibility; GM has one distribution.
# Shared dependency cache; edition-sensitive core and program are rebuilt by Cargo.
$env:CARGO_TARGET_DIR='C:/dev-toolchain/cache/cargo-meowgm-sponsor'
$env:PYTHONPYCACHEPREFIX='C:/dev-toolchain/cache/meowgm-pycache'
$env:PYINSTALLER_CONFIG_DIR='C:/dev-toolchain/cache/pyinstaller-meowgm'
$env:TEMP='C:/dev-toolchain/tmp';$env:TMP=$env:TEMP
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
# Import the installed MSVC environment; no downloads and no system settings changes.
$vcvars='C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Auxiliary/Build/vcvars64.bat'
if(!(Test-Path -LiteralPath $vcvars)){throw 'MSVC Build Tools with Windows SDK are required.'}
$vcCommand='"'+$vcvars.Replace('/','\')+'" >nul && set'
$envLines=& cmd.exe /d /c $vcCommand
if($LASTEXITCODE -ne 0){throw 'MSVC environment failed'}
foreach($line in $envLines){if($line -match '^([^=]+)=(.*)$'){[Environment]::SetEnvironmentVariable($matches[1],$matches[2],'Process')}}
Push-Location $suiteRoot
try {
    if(!$SkipHostBuild){
        if(!(Test-Path -LiteralPath $Python)){throw 'Python build environment is missing.'}
        & $Python -c "import paramiko, cryptography; assert paramiko.__version__ == '4.0.0'"
        if($LASTEXITCODE -ne 0){throw 'Required SSH dependency missing: install paramiko==4.0.0 in build environment.'}
        $stage=Join-Path $env:TEMP ('meowgm-package-'+[guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $stage -Force | Out-Null
        $env:GOCACHE=Join-Path $env:TEMP 'go-build-cache'
        $env:GOMODCACHE=Join-Path $env:TEMP 'go-mod-cache'
        $env:GOTMPDIR=$env:TEMP
        $modkit=Join-Path $env:TEMP 'meowgm-modkit.exe'
        $upstream=if($env:MEOW_UPSTREAM_DIR){$env:MEOW_UPSTREAM_DIR}else{Join-Path $PSScriptRoot '..\upstream\115us-dfolauncher'}
        $go=if($env:MEOW_GO){$env:MEOW_GO}else{'go'}
        Push-Location -LiteralPath $upstream
        try { & $go build -mod=readonly -o $modkit ./cmd/modkit; if($LASTEXITCODE -ne 0){throw 'Upstream modkit build failed'} } finally {Pop-Location}
        $gmtool=Join-Path $env:TEMP 'meowgm-gmtool.exe'
        $env:GOCACHE=Join-Path $env:TEMP 'go-mod115-cache'
        $env:GOMODCACHE=Join-Path $env:TEMP 'go-mod115-cache/modules'
        Push-Location -LiteralPath (Join-Path $upstream 'gm')
        try { & $go build -mod=readonly -o $gmtool ./cmd/gmtool; if($LASTEXITCODE -ne 0){throw 'Upstream gmtool build failed'} } finally {Pop-Location}
        $adminAssets=Join-Path $suiteRoot 'apps/admin'
        $gmSeeds=Join-Path $upstream 'gm/configs'
        $gateway=Join-Path $suiteRoot 'services/gateway'
        $extras=@()
        if($IncludeSimulationTools){
            $sim=Join-Path (Split-Path -Parent (Split-Path -Parent $suiteRoot)) '_src/MeowPay'
            if(!(Test-Path -LiteralPath "$sim/mock.py")){throw 'Simulation tools unavailable'}
            $extras=@('--add-data',"${sim}/mock.py:meowpay-simulator",'--add-data',"${sim}/config/catalog.defaults.json:meowpay-simulator/config")
        }
        & $Python -m PyInstaller --noconfirm --clean --onefile --name oo-manager-host --add-binary "${modkit}:tools" --add-binary "${gmtool}:tools" --add-data "${gmSeeds}:tools/configs" --distpath apps/manager/src-tauri/binaries --workpath "$stage/work" --specpath $stage --add-data "${adminAssets}:apps/admin" --add-data "${gateway}/admission.py:gateway-package" --add-data "${gateway}/deploy/managed_remote.py:gateway-package/deploy" @extras "$gateway/desktop_host.py"
        if($LASTEXITCODE -ne 0){throw 'Manager host build failed'}
    }
    & cargo build -p meow-manager --release --locked
    if($LASTEXITCODE -ne 0){throw 'Manager desktop build failed'}
    $release=Join-Path $OutputRoot $ReleaseName
    New-Item -ItemType Directory -Path $release -Force | Out-Null
    Copy-Item -LiteralPath "$env:CARGO_TARGET_DIR/release/meow-manager.exe" -Destination "$release/MeowGM.exe"
    Copy-Item -LiteralPath 'apps/manager/README.txt' -Destination "$release/管理器使用说明.txt"
    Copy-Item -LiteralPath 'apps/admin/UPSTREAM-UI.txt' -Destination "$release/上游界面来源.txt"
    $artifact=Get-Item -LiteralPath "$release/MeowGM.exe"
    $record=[ordered]@{product='MeowGM';version=$managerVersion;edition='unified';fileName='MeowGM.exe';size=$artifact.Length;sha256=(Get-FileHash -LiteralPath $artifact.FullName).Hash.ToLower();builtAt=(Get-Date).ToUniversalTime().ToString('o');productionVerified=$false}
    $record | ConvertTo-Json | Set-Content -LiteralPath "$release/artifact.json" -Encoding utf8
    Write-Output "Built: $($artifact.FullName)"
} finally {Pop-Location}
