param(
    [string]$Python='C:/rust-toolchain/meowgm-build/Scripts/python.exe',
    [string]$ReleaseName='',
    [string]$Upstream='',
    [string]$OutputRoot='C:/dev-toolchain/releases/MeowGM',
    [switch]$SkipHostBuild,
    [switch]$IncludeSimulationTools
)
$ErrorActionPreference='Stop'
$suiteRoot=Split-Path -Parent $PSScriptRoot
if(!$Upstream){$Upstream=if($env:MEOW_UPSTREAM_DIR){$env:MEOW_UPSTREAM_DIR}else{Join-Path $suiteRoot 'upstream/115us-dfolauncher'}}
if(!$SkipHostBuild){
    foreach($required in @('go.mod','cmd/modkit','gm/go.mod','gm/cmd/gmtool','gm/configs')){
        if(!(Test-Path -LiteralPath (Join-Path $Upstream $required))){throw "GM upstream dependency missing: $required. Specify -Upstream with the reviewed 115us-dfolauncher checkout."}
    }
    $revision=& git -C $Upstream rev-parse HEAD
    if($LASTEXITCODE -ne 0 -or ($revision -join '').Trim() -ne '2e80468daec25820beaf3d6eceea79a40c6dda31'){throw 'Upstream GM revision differs from reviewed baseline'}
}

# MeowGM has its own version source, independent from the launcher.
$managerManifest=Get-Content (Join-Path $suiteRoot 'apps/manager/src-tauri/Cargo.toml') -Raw
if($managerManifest -notmatch '(?m)^version\s*=\s*"([^"]+)"'){throw 'Manager package version missing'}
$managerSemver=$matches[1]
$versionMetadata=Get-Content (Join-Path $suiteRoot 'apps/manager/version.json') -Raw | ConvertFrom-Json
$managerVersion=$versionMetadata.version
if($managerVersion -notmatch '^([0-9]{2})\.([1-9][0-9]*)(?:-(snapshot|pre|rc)-([1-9][0-9]*)|\.([1-9][0-9]*))?$'){throw 'Invalid GM public version'}
$expectedSemver="$($matches[1]).$($matches[2]).0"
if($matches[3]){$expectedSemver+="-$($matches[3])-$($matches[4])"}
elseif($matches[5]){$expectedSemver="$($matches[1]).$($matches[2]).$($matches[5])"}
if($managerSemver -ne $expectedSemver -or $versionMetadata.semver -ne $expectedSemver){throw 'GM internal SemVer mapping differs'}
if(!$ReleaseName){$ReleaseName=$managerVersion}
$configPath=Join-Path $suiteRoot 'apps/manager/src-tauri/tauri.conf.json'
$config=Get-Content $configPath -Raw | ConvertFrom-Json
if($config.version -ne $managerSemver){throw 'GM Tauri version differs from internal SemVer'}
if($ReleaseName -ne $managerVersion){throw 'Release directory must match GM public version'}
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
    Copy-Item -LiteralPath 'apps/manager/version.json' -Destination "$release/version.json"
    Copy-Item -LiteralPath 'apps/manager/README.txt' -Destination "$release/管理器使用说明.txt"
    Copy-Item -LiteralPath 'apps/admin/UPSTREAM-UI.txt' -Destination "$release/上游界面来源.txt"
    $artifact=Get-Item -LiteralPath "$release/MeowGM.exe"
    $record=[ordered]@{product='MeowGM';version=$managerVersion;internalSemver=$managerSemver;edition='unified';fileName='MeowGM.exe';size=$artifact.Length;sha256=(Get-FileHash -LiteralPath $artifact.FullName).Hash.ToLower();builtAt=(Get-Date).ToUniversalTime().ToString('o');productionVerified=$false}
    $record | ConvertTo-Json | Set-Content -LiteralPath "$release/artifact.json" -Encoding utf8
    Write-Output "Built: $($artifact.FullName)"
} finally {Pop-Location}
