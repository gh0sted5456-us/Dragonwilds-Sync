param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,

    [Parameter(Mandatory = $true)]
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:FailureExitCode = 1

function Write-BuildLine {
    param([string]$Message = '')
    Write-Host $Message
    Add-Content -LiteralPath $LogPath -Value $Message
}

function Fail-Build {
    param([string]$Message, [int]$Code = 1)
    $script:FailureExitCode = $Code
    Write-BuildLine "[ERROR] $Message"
    throw $Message
}

function Resolve-NativeCommand {
    param([string[]]$Candidates)
    foreach ($name in $Candidates) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $cmd) {
            return $cmd.Source
        }
    }
    return $null
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$Label = $null
    )

    if ($Label) {
        Write-BuildLine $Label
    }

    $prettyArgs = ($Arguments | ForEach-Object {
        if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
    }) -join ' '
    Write-BuildLine "> $FilePath $prettyArgs"

    # Windows PowerShell 5.1 promotes native stderr records into PowerShell
    # error records.  With the script-wide ErrorActionPreference='Stop', a
    # harmless warning from npm/PyInstaller/electron-builder can otherwise
    # terminate this function before the native process has even returned.
    # Native tools are authoritative about success through their EXIT CODE,
    # not through which stream they write diagnostics to.
    $previousErrorActionPreference = $ErrorActionPreference
    $rc = 0
    try {
        $ErrorActionPreference = 'Continue'
        & $FilePath @Arguments 2>&1 | ForEach-Object {
            $line = $_.ToString()
            Write-Host $line
            Add-Content -LiteralPath $LogPath -Value $line
        }
        $rc = $LASTEXITCODE
        if ($null -eq $rc) { $rc = 0 }
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($rc -ne 0) {
        Fail-Build "Command failed with exit code ${rc}: $FilePath $prettyArgs" $rc
    }
}

function Test-RequiredFile {
    param([string]$RelativePath, [string]$Description)
    $full = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        Fail-Build "$Description is missing: $RelativePath"
    }
    Write-BuildLine "[OK] ${Description}: $RelativePath"
}

function Remove-BuildDirectory {
    param([string]$RelativePath)
    $full = Join-Path $ProjectRoot $RelativePath
    if (Test-Path -LiteralPath $full) {
        Write-BuildLine "Removing $RelativePath ..."
        Remove-Item -LiteralPath $full -Recurse -Force
    }
}

function Clear-ReleaseDirectory {
    $releaseRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot 'release'))
    $projectRootFull = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\') + '\'
    if (-not $releaseRoot.StartsWith($projectRootFull, [StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetFileName($releaseRoot) -ne 'release') {
        Fail-Build "Refusing to clear an unsafe release path: $releaseRoot"
    }
    if (Test-Path -LiteralPath $releaseRoot) {
        Write-BuildLine 'Removing the previous release directory so only this build remains ...'
        Remove-Item -LiteralPath $releaseRoot -Recurse -Force
    }
}

$archivePath = $null
$exitCode = 0
Push-Location $ProjectRoot
try {
    Write-BuildLine '============================================================'
    Write-BuildLine ' Dragonwilds Sync - Windows Build'
    Write-BuildLine '============================================================'
    Write-BuildLine "Project root: $ProjectRoot"
    Write-BuildLine "PowerShell: $($PSVersionTable.PSVersion)"
    Write-BuildLine "Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    Write-BuildLine ''

    $pythonOverride = [Environment]::GetEnvironmentVariable('DRAGONWILDS_SYNC_PYTHON')
    if ($pythonOverride) {
        if (-not (Test-Path -LiteralPath $pythonOverride -PathType Leaf)) {
            Fail-Build "DRAGONWILDS_SYNC_PYTHON does not point to a Python executable: $pythonOverride"
        }
        $pythonExe = (Resolve-Path -LiteralPath $pythonOverride).Path
        Write-BuildLine "Using explicit build Python from DRAGONWILDS_SYNC_PYTHON: $pythonExe"
    }
    else {
        $pythonExe = Resolve-NativeCommand @('py.exe', 'py', 'python.exe', 'python', 'python3.exe', 'python3')
    }
    if (-not $pythonExe) { Fail-Build 'Python 3 was not found. Install Python 3 and make either py or python available.' }

    $pythonPrefix = @()
    if ([System.IO.Path]::GetFileName($pythonExe) -ieq 'py.exe' -or [System.IO.Path]::GetFileName($pythonExe) -ieq 'py') {
        $pythonPrefix = @('-3')
    }

    $nodeExe = Resolve-NativeCommand @('node.exe', 'node')
    if (-not $nodeExe) { Fail-Build 'Node.js was not found.' }

    $npmExe = Resolve-NativeCommand @('npm.cmd', 'npm.exe', 'npm')
    if (-not $npmExe) { Fail-Build 'npm was not found.' }

    Write-BuildLine '[1/7] Toolchain check'
    Invoke-Native $pythonExe ($pythonPrefix + @('--version'))
    Invoke-Native $nodeExe @('--version')
    Invoke-Native $npmExe @('--version')
    Write-BuildLine ''

    Write-BuildLine '[2/7] Required files'
    Test-RequiredFile 'renderer\assets\dragonwilds_icon.ico' 'Application icon'
    Test-RequiredFile 'resources\recommended-mods.json' 'GitHub-ready creator recommendation feed'
    Test-RequiredFile 'scripts\check_ue4ss_lua.cjs' 'UE4SS Lua syntax verifier'
    Test-RequiredFile 'resources\RuneSchema-core-latest.zip' 'Bundled RuneSchema core'
    Test-RequiredFile 'resources\DragonwildsServerRuntime\UE4SS-core-latest.zip' 'Bundled Dragonwilds UE4SS runtime core'
    Test-RequiredFile 'resources\DragonwildsServerRuntime\version.dll' 'Bundled Dragonwilds server-only version.dll'
    Test-RequiredFile 'scripts\prepare_monaco.cjs' 'Monaco bundling helper'
    Test-RequiredFile 'backend\DragonwildsSync.Service.spec' 'PyInstaller service spec'
    Test-RequiredFile 'backend\requirements-build.txt' 'Pinned Python build requirements'
    Test-RequiredFile 'backend\dragonwilds_service.py' 'Headless Python service'
    Test-RequiredFile 'backend\runtime_platforms.py' 'Platform-aware runtime manifest negotiation'
    Test-RequiredFile 'backend\directory_host.py' 'Self-hosted federated World Directory'
    Test-RequiredFile 'backend\local_world.py' 'SinglePlayer World/mod engine'
    Test-RequiredFile 'backend\rsdw_cache.py' 'Shared RSDW APPDATA cache engine'
    Test-RequiredFile 'backend\mod_tags.py' 'Mod tags.txt parser'
    Test-RequiredFile 'backend\world_classification.py' 'Unified World classification schema'
    Test-RequiredFile 'backend\operator_identity.py' 'Ed25519 operator identity signing'
    Test-RequiredFile 'backend\crypto_runtime.py' 'Packaged Ed25519 runtime and protected-key diagnostics'
    Test-RequiredFile 'backend\character_submissions.py' 'Quarantined character submission workflow'
    Test-RequiredFile 'backend\rsdwl_packages.py' 'Typed RSDWL v2 package envelope'
    Test-RequiredFile 'backend\world_sharing.py' 'Legacy RSDWL v2 compatibility engine'
    Test-RequiredFile 'backend\profile_bundle.py' 'Unified RSDWL v3 profile bundle engine'
    Test-RequiredFile 'resources\tags.example.txt' 'Example mod tags.txt'
    Test-RequiredFile 'renderer\assets\guided\connect-world.png' 'Client guided-setup artwork'
    Test-RequiredFile 'renderer\assets\guided\settings-reference.png' 'Server guided-setup artwork'
    Test-RequiredFile 'renderer\assets\singleplayer-banner.png' 'SinglePlayer default banner'
    Test-RequiredFile 'renderer\assets\singleplayer-icon.png' 'SinglePlayer default icon'
    Test-RequiredFile 'electron\discord_rpc.cjs' 'Discord desktop Rich Presence transport'
    Test-RequiredFile 'electron\app_updater.cjs' 'Smart GitHub application updater'
    Test-RequiredFile 'resources\community-templates\tags.txt' 'Community tags.txt template'
    Test-RequiredFile 'resources\community-templates\mods.txt' 'Community mods.txt template'
    Test-RequiredFile 'resources\community-templates\enabled.txt' 'Community enabled.txt template'
    Write-BuildLine ''

    Write-BuildLine '[3/7] Build dependencies'
    # Python 3.14 is supported by current PyInstaller, but older 6.20 builds had
    # Windows/3.14 analysis failures. Keep the freezer deterministic instead of
    # accepting whichever PyInstaller happens to be installed globally.
    $expectedPyInstaller = '6.22.0'
    $installedPyInstaller = ''
    $installedPsutil = ''
    $installedCryptography = ''
    try {
        $installedPyInstaller = (& $pythonExe @pythonPrefix -c "import PyInstaller; print(PyInstaller.__version__)" 2>$null | Select-Object -First 1).ToString().Trim()
        $installedPsutil = (& $pythonExe @pythonPrefix -c "import psutil; print(psutil.__version__)" 2>$null | Select-Object -First 1).ToString().Trim()
        $installedCryptography = (& $pythonExe @pythonPrefix -c "import cryptography; print(cryptography.__version__)" 2>$null | Select-Object -First 1).ToString().Trim()
    } catch { }
    $pythonDepsMatch = ($installedPyInstaller -eq $expectedPyInstaller -and $installedPsutil -match '^7\.' -and $installedCryptography -match '^46\.')
    if ($pythonDepsMatch) {
        Write-BuildLine "[OK] Python build dependencies match (PyInstaller $installedPyInstaller, psutil $installedPsutil, cryptography $installedCryptography)."
    }
    else {
        Write-BuildLine "Python build dependencies differ (PyInstaller '$installedPyInstaller', psutil '$installedPsutil', cryptography '$installedCryptography'; expected PyInstaller $expectedPyInstaller, psutil 7.x, and cryptography 46.x)."
        Invoke-Native $pythonExe ($pythonPrefix + @('-m', 'pip', 'install', '--upgrade', '-r', (Join-Path $ProjectRoot 'backend\requirements-build.txt'))) 'Installing/upgrading the pinned Python build requirements...'
        $installedPyInstaller = (& $pythonExe @pythonPrefix -c "import PyInstaller; print(PyInstaller.__version__)" 2>$null | Select-Object -First 1).ToString().Trim()
        $installedPsutil = (& $pythonExe @pythonPrefix -c "import psutil; print(psutil.__version__)" 2>$null | Select-Object -First 1).ToString().Trim()
        $installedCryptography = (& $pythonExe @pythonPrefix -c "import cryptography; print(cryptography.__version__)" 2>$null | Select-Object -First 1).ToString().Trim()
        if ($installedPyInstaller -ne $expectedPyInstaller) { Fail-Build "PyInstaller version mismatch after pip install: found $installedPyInstaller, expected $expectedPyInstaller" }
        if ($installedPsutil -notmatch '^7\.') { Fail-Build "psutil version mismatch after pip install: found $installedPsutil, expected 7.x" }
        if ($installedCryptography -notmatch '^46\.') { Fail-Build "cryptography version mismatch after pip install: found $installedCryptography, expected 46.x" }
        Write-BuildLine "[OK] Pinned Python dependency versions verified after install (PyInstaller $installedPyInstaller, psutil $installedPsutil, cryptography $installedCryptography)."
    }

    $rootPackage = Get-Content -LiteralPath (Join-Path $ProjectRoot 'package.json') -Raw | ConvertFrom-Json
    $expectedElectron = [string]$rootPackage.devDependencies.electron
    $expectedBuilder = [string]$rootPackage.devDependencies.'electron-builder'
    $expectedMonaco = [string]$rootPackage.devDependencies.'monaco-editor'
    $expectedAsar = [string]$rootPackage.devDependencies.'@electron/asar'
    $electronPackage = Join-Path $ProjectRoot 'node_modules\electron\package.json'
    $builderPackage = Join-Path $ProjectRoot 'node_modules\electron-builder\package.json'
    $monacoPackage = Join-Path $ProjectRoot 'node_modules\monaco-editor\package.json'
    $asarPackage = Join-Path $ProjectRoot 'node_modules\@electron\asar\package.json'
    $nodeDependenciesMatch = $false
    if ((Test-Path -LiteralPath $electronPackage -PathType Leaf) -and (Test-Path -LiteralPath $builderPackage -PathType Leaf) -and (Test-Path -LiteralPath $monacoPackage -PathType Leaf) -and (Test-Path -LiteralPath $asarPackage -PathType Leaf)) {
        try {
            $installedElectron = [string]((Get-Content -LiteralPath $electronPackage -Raw | ConvertFrom-Json).version)
            $installedBuilder = [string]((Get-Content -LiteralPath $builderPackage -Raw | ConvertFrom-Json).version)
            $installedMonaco = [string]((Get-Content -LiteralPath $monacoPackage -Raw | ConvertFrom-Json).version)
            $installedAsar = [string]((Get-Content -LiteralPath $asarPackage -Raw | ConvertFrom-Json).version)
            $nodeDependenciesMatch = ($installedElectron -eq $expectedElectron -and $installedBuilder -eq $expectedBuilder -and $installedMonaco -eq $expectedMonaco -and $installedAsar -eq $expectedAsar)
            if ($nodeDependenciesMatch) {
                Write-BuildLine "[OK] Node build dependencies match package.json (Electron $installedElectron, electron-builder $installedBuilder, Monaco $installedMonaco, ASAR $installedAsar)."
            }
            else {
                Write-BuildLine "Node build dependency versions differ (Electron $installedElectron / builder $installedBuilder / Monaco $installedMonaco / ASAR $installedAsar; expected $expectedElectron / $expectedBuilder / $expectedMonaco / $expectedAsar)."
            }
        }
        catch {
            Write-BuildLine '[WARN] Could not read installed Node dependency versions; npm install will repair them.'
        }
    }
    if (-not $nodeDependenciesMatch) {
        Invoke-Native $npmExe @('install', '--include=dev', '--no-audit', '--no-fund') 'Installing the pinned Node build dependencies (Electron, builder, Monaco, ASAR)...'
    }

    # Do not assume npm repaired a stale dependency tree.  Re-read all pinned
    # versions after install so Monaco/Electron packaging failures are caught
    # here with a useful message instead of later during prepare/package.
    foreach ($requiredNodePackage in @($electronPackage, $builderPackage, $monacoPackage, $asarPackage)) {
        if (-not (Test-Path -LiteralPath $requiredNodePackage -PathType Leaf)) {
            Fail-Build "Pinned Node dependency was not installed: $requiredNodePackage"
        }
    }
    $installedElectron = [string]((Get-Content -LiteralPath $electronPackage -Raw | ConvertFrom-Json).version)
    $installedBuilder = [string]((Get-Content -LiteralPath $builderPackage -Raw | ConvertFrom-Json).version)
    $installedMonaco = [string]((Get-Content -LiteralPath $monacoPackage -Raw | ConvertFrom-Json).version)
    $installedAsar = [string]((Get-Content -LiteralPath $asarPackage -Raw | ConvertFrom-Json).version)
    if ($installedElectron -ne $expectedElectron) { Fail-Build "Electron version mismatch after npm install: found $installedElectron, expected $expectedElectron" }
    if ($installedBuilder -ne $expectedBuilder) { Fail-Build "electron-builder version mismatch after npm install: found $installedBuilder, expected $expectedBuilder" }
    if ($installedMonaco -ne $expectedMonaco) { Fail-Build "Monaco Editor version mismatch after npm install: found $installedMonaco, expected $expectedMonaco" }
    if ($installedAsar -ne $expectedAsar) { Fail-Build "@electron/asar version mismatch after npm install: found $installedAsar, expected $expectedAsar" }
    Write-BuildLine "[OK] Pinned Node dependency versions verified after install (Electron $installedElectron, electron-builder $installedBuilder, Monaco $installedMonaco, ASAR $installedAsar)."
    Write-BuildLine ''

    Write-BuildLine '[4/7] Verification'
    Invoke-Native $npmExe @('run', 'verify')
    Invoke-Native $pythonExe ($pythonPrefix + @('-m', 'py_compile',
        'backend\dragonwilds_service.py',
        'backend\server_engine.py',
        'backend\server_systems.py',
        'backend\network_client.py',
        'backend\profile_store.py',
        'backend\sync_engine.py',
        'backend\shared_mod_repository.py',
        'backend\world_identity.py',
        'backend\health_model.py',
        'backend\integrations.py',
        'backend\network_health.py',
        'backend\process_utils.py',
        'backend\security_policy.py',
        'backend\security_scanner.py',
        'backend\runtime_versions.py',
        'backend\runtime_platforms.py',
        'backend\directory_host.py',
        'backend\world_maintenance.py',
        'backend\server_layout.py',
        'backend\client_layout.py',
        'backend\character_profiles.py',
        'backend\local_world.py',
        'backend\network_benchmark.py',
        'backend\guided_setup.py',
        'backend\player_tracker.py',
        'backend\server_scheduler.py',
        'backend\world_save_distribution.py',
        'backend\rsdwl_packages.py',
        'backend\world_sharing.py',
        'backend\profile_bundle.py'))
    Write-BuildLine ''

    Write-BuildLine '[5/7] Cleaning old outputs'
    Remove-BuildDirectory 'dist-service'
    Remove-BuildDirectory 'build-service'
    # Portable-only policy: remove every prior package so stale installers or
    # artifacts from older versions cannot survive beside the new portable EXE.
    Clear-ReleaseDirectory
    Write-BuildLine ''

    Write-BuildLine '[6/7] Building headless Python service'
    Invoke-Native $pythonExe ($pythonPrefix + @('-m', 'PyInstaller',
        '--clean',
        '--noconfirm',
        '--distpath', (Join-Path $ProjectRoot 'dist-service'),
        '--workpath', (Join-Path $ProjectRoot 'build-service'),
        (Join-Path $ProjectRoot 'backend\DragonwildsSync.Service.spec')))

    $serviceExe = Join-Path $ProjectRoot 'dist-service\DragonwildsSync.Service.exe'
    if (-not (Test-Path -LiteralPath $serviceExe -PathType Leaf)) {
        Fail-Build 'PyInstaller completed without producing dist-service\DragonwildsSync.Service.exe.'
    }
    Write-BuildLine "[OK] Service EXE: $serviceExe"

    # Critical packaged-runtime smoke test. The service is a newline-delimited
    # JSON-RPC process over stdin/stdout, so a successful PyInstaller exit is
    # not enough: the packaged EXE must still have working standard streams.
    Write-BuildLine 'Testing packaged service JSON-RPC stdio...'
    $probeInput = '{"id":1,"method":"state.get","params":{}}'
    $probeOutput = @($probeInput | & $serviceExe 2>&1)
    $probeRc = $LASTEXITCODE
    $probeText = ($probeOutput | ForEach-Object { $_.ToString() }) -join "`n"
    if ($probeRc -ne 0) {
        Fail-Build "Packaged service smoke test exited with code $probeRc. Output: $probeText" $probeRc
    }
    if ($probeText -notmatch '\"id\"\s*:\s*1' -or $probeText -notmatch '\"ok\"\s*:\s*true') {
        Fail-Build "Packaged service did not answer JSON-RPC over stdio. Output: $probeText"
    }
    Write-BuildLine '[OK] Packaged service JSON-RPC stdio is working.'
    Write-BuildLine 'Testing packaged Ed25519 generation, signing, serialization, reload, and rejection...'
    $cryptoProbeInput = '{"id":2,"method":"application.cryptography.status","params":{}}'
    $cryptoProbeOutput = @($cryptoProbeInput | & $serviceExe 2>&1)
    $cryptoProbeRc = $LASTEXITCODE
    $cryptoProbeText = ($cryptoProbeOutput | ForEach-Object { $_.ToString() }) -join "`n"
    if ($cryptoProbeRc -ne 0) {
        Fail-Build "Packaged cryptography self-test exited with code $cryptoProbeRc. Output: $cryptoProbeText" $cryptoProbeRc
    }
    foreach ($requiredCryptoResult in @('"healthy"\s*:\s*true', '"sign_verify"\s*:\s*true', '"serialization_reload"\s*:\s*true', '"invalid_signature_rejected"\s*:\s*true')) {
        if ($cryptoProbeText -notmatch $requiredCryptoResult) {
            Fail-Build "Packaged cryptography self-test did not prove every required operation. Output: $cryptoProbeText"
        }
    }
    Write-BuildLine '[OK] Packaged cryptography runtime is healthy.'
    Write-BuildLine ''

    Write-BuildLine '[7/7] Building Electron portable EXE'
    # The Windows target (portable only -- no NSIS installer) is already
    # declared in package.json. Supplying only --win here avoids target
    # parsing differences between electron-builder CLI versions while still
    # producing whatever's configured there.
    $builderExe = Join-Path $ProjectRoot 'node_modules\.bin\electron-builder.cmd'
    if (-not (Test-Path -LiteralPath $builderExe -PathType Leaf)) {
        Fail-Build 'electron-builder was not installed under node_modules\.bin.'
    }
    $electronBuildComplete = $false
    for ($electronBuildAttempt = 1; $electronBuildAttempt -le 2; $electronBuildAttempt++) {
        try {
            Invoke-Native $builderExe @('--win')
            $electronBuildComplete = $true
            break
        }
        catch {
            if ($electronBuildAttempt -ge 2) { throw }
            Write-BuildLine '[WARN] Electron packaging hit a transient Windows/OneDrive file lock. Clearing only win-unpacked.tmp and retrying once.'
            Start-Sleep -Seconds 2
            $releaseRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot 'release'))
            $unpackedStaging = [IO.Path]::GetFullPath((Join-Path $releaseRoot 'win-unpacked.tmp'))
            if ([IO.Path]::GetFullPath((Split-Path -Parent $unpackedStaging)) -ne $releaseRoot) {
                Fail-Build "Refusing to clear an Electron staging path outside release: $unpackedStaging"
            }
            if (Test-Path -LiteralPath $unpackedStaging) {
                Remove-Item -LiteralPath $unpackedStaging -Recurse -Force
            }
        }
    }
    if (-not $electronBuildComplete) { Fail-Build 'Electron packaging did not complete.' }

    $releaseDir = Join-Path $ProjectRoot 'release'
    if (-not (Test-Path -LiteralPath $releaseDir -PathType Container)) {
        Fail-Build 'electron-builder completed without producing the release directory.'
    }

    $releaseExes = @(Get-ChildItem -LiteralPath $releaseDir -Filter '*.exe' -File -ErrorAction SilentlyContinue)
    if ($releaseExes.Count -lt 1) {
        Fail-Build 'The release directory exists, but no Windows .exe artifacts were produced.'
    }

    Write-BuildLine 'Verifying packaged Monaco + launcher resources...'
    $unpacked = Join-Path $releaseDir 'win-unpacked'
    $appAsar = Join-Path $unpacked 'resources\app.asar'
    $asarExe = Join-Path $ProjectRoot 'node_modules\.bin\asar.cmd'
    if (-not (Test-Path -LiteralPath $appAsar -PathType Leaf)) { Fail-Build 'Packaged app.asar was not produced.' }
    if (-not (Test-Path -LiteralPath $asarExe -PathType Leaf)) { Fail-Build '@electron/asar CLI is missing after dependency install.' }
    $asarListing = @(& $asarExe list $appAsar 2>&1 | ForEach-Object { $_.ToString().Replace('\', '/') })
    if ($LASTEXITCODE -ne 0) { Fail-Build 'Could not inspect packaged app.asar.' $LASTEXITCODE }
    if (-not ($asarListing | Where-Object { $_.TrimStart('/') -eq 'renderer/vendor/monaco/vs/loader.js' })) { Fail-Build 'Packaged Monaco loader.js is missing from app.asar.' }
    if (-not ($asarListing | Where-Object { $_.TrimStart('/') -eq 'renderer/vendor/monaco/vs/base/worker/workerMain.js' })) { Fail-Build 'Packaged Monaco worker runtime is missing from app.asar.' }
    Write-BuildLine '[OK] Packaged Monaco Editor runtime is present.'

    $packedRecommendations = Join-Path $unpacked 'resources\resources\recommended-mods.json'
    if (-not (Test-Path -LiteralPath $packedRecommendations -PathType Leaf)) { Fail-Build "Packaged launcher resource missing: $packedRecommendations" }
    Write-BuildLine '[OK] Packaged creator recommendation fallback is present; no third-party mod archive is bundled.'
    $bundledRuneSchema = Join-Path $ProjectRoot 'resources\RuneSchema-core-latest.zip'
    if (Test-Path -LiteralPath $bundledRuneSchema -PathType Leaf) {
        $packedRuneSchema = Join-Path $unpacked 'resources\resources\RuneSchema-core-latest.zip'
        if (-not (Test-Path -LiteralPath $packedRuneSchema -PathType Leaf)) { Fail-Build 'Bundled RuneSchema core was present in source but missing from packaged resources.' }
        Write-BuildLine '[OK] Packaged RuneSchema core resource is present.'
    }
    $packedUe4ss = Join-Path $unpacked 'resources\resources\DragonwildsServerRuntime\UE4SS-core-latest.zip'
    $packedServerLoader = Join-Path $unpacked 'resources\resources\DragonwildsServerRuntime\version.dll'
    foreach ($requiredRuntime in @($packedUe4ss, $packedServerLoader)) {
        if (-not (Test-Path -LiteralPath $requiredRuntime -PathType Leaf)) { Fail-Build "Packaged Dragonwilds runtime resource missing: $requiredRuntime" }
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $runtimeArchive = [IO.Compression.ZipFile]::OpenRead($packedUe4ss)
    try {
        $forbiddenRsdwTools = @($runtimeArchive.Entries | Where-Object { $_.FullName -match '(^|/)RSDWTools(/|$)' })
        if ($forbiddenRsdwTools.Count -gt 0) {
            Fail-Build 'Portable package still contains the removed RSDWTools UE4SS mod.'
        }
    }
    finally {
        $runtimeArchive.Dispose()
    }
    Write-BuildLine '[OK] Packaged Dragonwilds UE4SS core + server-only version.dll are present.'

    Write-BuildLine 'Removing verified Electron staging output ...'
    Remove-BuildDirectory 'release\win-unpacked'
    Remove-BuildDirectory 'release\win-unpacked.tmp'
    Remove-BuildDirectory 'release\builder-debug.yml'
    Remove-BuildDirectory 'release\builder-effective-config.yaml'
    $unexpectedReleaseItems = @(Get-ChildItem -LiteralPath $releaseDir -Force | Where-Object {
        -not ($_.PSIsContainer -eq $false -and $_.Extension -ieq '.exe')
    })
    if ($unexpectedReleaseItems.Count -gt 0) {
        Fail-Build "Portable-only release contains unexpected staging output: $(($unexpectedReleaseItems.Name -join ', '))"
    }
    Write-BuildLine '[OK] Release contains portable EXE artifacts only.'

    Write-BuildLine ''
    Write-BuildLine 'BUILD COMPLETE'
    foreach ($artifact in $releaseExes) {
        Write-BuildLine ("  {0} ({1:N1} MB)" -f $artifact.FullName, ($artifact.Length / 1MB))
    }
    Write-BuildLine "Finished: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
}
catch {
    $exitCode = $script:FailureExitCode
    if ($exitCode -lt 1) { $exitCode = 1 }
    Write-BuildLine ''
    Write-BuildLine 'BUILD FAILED'
    Write-BuildLine "Message: $($_.Exception.Message)"
    Write-BuildLine "At: $($_.InvocationInfo.PositionMessage)"
    Write-BuildLine "Finished: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
}
finally {
    try {
        $logDir = Join-Path $ProjectRoot 'build-logs'
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
        $archivePath = Join-Path $logDir "build_$stamp.log"
        Copy-Item -LiteralPath $LogPath -Destination $archivePath -Force
        Write-Host "Archived log: $archivePath"
    }
    catch {
        Write-Host "[WARN] Could not archive build log: $($_.Exception.Message)"
    }
    Pop-Location
}

exit $exitCode
