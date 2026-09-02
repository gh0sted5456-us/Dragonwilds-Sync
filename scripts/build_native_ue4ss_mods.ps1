param(
    [string]$BuildRoot = "$env:TEMP\dragonwilds-sync-native-ue4ss",
    [switch]$KeepBuildTree,
    [switch]$CriticalOnly,
    [string]$UePseudoToken = $env:UEPSEUDO_PAT
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Ue4ssCommit = '0bfec09ee30b7c4cda8aa151e2fdb15cbe6c10c9'
$SourceRoot = Join-Path $BuildRoot 'RE-UE4SS'
$BuildDir = Join-Path $BuildRoot 'build'
$ModsSource = Join-Path $RepoRoot 'native\ue4ss-mods'
$StageRoot = Join-Path $RepoRoot 'resources\NativeRuntimeMods'

$AllMods = @('DragonLink', 'DragonLink-StacksWeights', 'DragonLink-Chat', 'DragonLink-Connect', 'DragonLink-ProximityLoot')
$SelectedMods = if ($CriticalOnly) { @('DragonLink', 'DragonLink-Chat', 'DragonLink-Connect') } else { $AllMods }
$BuildTargets = if ($CriticalOnly) { @('DragonLink', 'DragonLinkChat', 'DragonLinkConnect') } else { @('DragonLink', 'DragonLinkStacksWeights', 'DragonLinkChat', 'DragonLinkConnect', 'DragonLinkProximityLoot') }

foreach ($tool in @('git', 'cmake')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Required native build tool is unavailable: $tool"
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot '.git'))) {
    New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
    git clone https://github.com/UE4SS-RE/RE-UE4SS.git $SourceRoot
    if ($LASTEXITCODE -ne 0) { throw "Could not clone pinned UE4SS source (exit $LASTEXITCODE)" }
}

git -C $SourceRoot fetch origin $Ue4ssCommit --depth=1
if ($LASTEXITCODE -ne 0) { throw "Could not fetch pinned UE4SS commit $Ue4ssCommit" }
git -C $SourceRoot checkout --detach $Ue4ssCommit
if ($LASTEXITCODE -ne 0) { throw "Could not check out pinned UE4SS commit $Ue4ssCommit" }

# The pinned UE4SS revision depends on Re-UE4SS/UEPseudo, an upstream private
# repository. Official UE4SS CI checks it out with UEPSEUDO_PAT. Never bake or
# print that token; inject it only as a temporary HTTP Authorization header.
if ([string]::IsNullOrWhiteSpace($UePseudoToken)) {
    throw 'UEPSEUDO_PAT is required to compile UE4SS C++ mods from a clean checkout. Configure an Epic-linked GitHub token with access to Re-UE4SS/UEPseudo.'
}
$credentialBytes = [Text.Encoding]::ASCII.GetBytes("x-access-token:$UePseudoToken")
$authorization = 'AUTHORIZATION: basic ' + [Convert]::ToBase64String($credentialBytes)
$oldCount = $env:GIT_CONFIG_COUNT
$oldKey = $env:GIT_CONFIG_KEY_0
$oldValue = $env:GIT_CONFIG_VALUE_0
try {
    $env:GIT_CONFIG_COUNT = '1'
    $env:GIT_CONFIG_KEY_0 = 'http.https://github.com/.extraheader'
    $env:GIT_CONFIG_VALUE_0 = $authorization
    git -C $SourceRoot -c url.https://github.com/.insteadOf=git@github.com: submodule update --init --recursive --depth=1
    if ($LASTEXITCODE -ne 0) { throw 'Could not initialize UE4SS submodules with the supplied UEPSEUDO_PAT' }
}
finally {
    if ($null -eq $oldCount) { Remove-Item Env:GIT_CONFIG_COUNT -ErrorAction SilentlyContinue } else { $env:GIT_CONFIG_COUNT = $oldCount }
    if ($null -eq $oldKey) { Remove-Item Env:GIT_CONFIG_KEY_0 -ErrorAction SilentlyContinue } else { $env:GIT_CONFIG_KEY_0 = $oldKey }
    if ($null -eq $oldValue) { Remove-Item Env:GIT_CONFIG_VALUE_0 -ErrorAction SilentlyContinue } else { $env:GIT_CONFIG_VALUE_0 = $oldValue }
    $authorization = $null
    $credentialBytes = $null
}

$CppMods = Join-Path $SourceRoot 'cppmods'
foreach ($Name in $SelectedMods) {
    $Source = Join-Path $ModsSource $Name
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) { throw "Native mod source is missing: $Name" }
    $Destination = Join-Path $CppMods $Name
    if (Test-Path -LiteralPath $Destination) { Remove-Item -LiteralPath $Destination -Recurse -Force }
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse
}

$CppModsCmake = Join-Path $CppMods 'CMakeLists.txt'
$CmakeText = Get-Content -LiteralPath $CppModsCmake -Raw
foreach ($Name in $SelectedMods) {
    $Line = "add_subdirectory(`"$Name`")"
    if (-not $CmakeText.Contains($Line)) { $CmakeText += "`r`n$Line" }
}
Set-Content -LiteralPath $CppModsCmake -Value $CmakeText -Encoding utf8

# A persistent developer build tree can remember a different Visual Studio
# generator. Reconfigure from a clean build directory and let CMake choose the
# newest Visual Studio installation available on the machine/Actions runner.
if (Test-Path -LiteralPath $BuildDir) { Remove-Item -LiteralPath $BuildDir -Recurse -Force }
cmake -S $SourceRoot -B $BuildDir -A x64
if ($LASTEXITCODE -ne 0) { throw "Native UE4SS CMake configuration failed with exit code $LASTEXITCODE" }
& cmake --build $BuildDir --config Game__Shipping__Win64 --target $BuildTargets --parallel
if ($LASTEXITCODE -ne 0) { throw "Native DragonLink build failed with exit code $LASTEXITCODE" }

$Candidates = Get-ChildItem -LiteralPath $BuildDir -Filter '*.dll' -Recurse
$Outputs = @{
    'main.dll' = ($Candidates | Where-Object Name -eq 'DragonLink.dll' | Select-Object -First 1)
    'DragonLink-StacksWeights.dll' = ($Candidates | Where-Object Name -eq 'DragonLink-StacksWeights.dll' | Select-Object -First 1)
    'DragonLink-Chat.dll' = ($Candidates | Where-Object Name -eq 'DragonLink-Chat.dll' | Select-Object -First 1)
    'DragonLink-Connect.dll' = ($Candidates | Where-Object Name -eq 'DragonLink-Connect.dll' | Select-Object -First 1)
}
$RequiredOutputs = if ($CriticalOnly) { @('main.dll', 'DragonLink-Chat.dll', 'DragonLink-Connect.dll') } else { @('main.dll', 'DragonLink-StacksWeights.dll', 'DragonLink-Chat.dll', 'DragonLink-Connect.dll') }

$Target = Join-Path $StageRoot 'DragonLink\dlls'
New-Item -ItemType Directory -Force -Path $Target | Out-Null
foreach ($legacyName in @('DragonLink-Core.dll', 'DragonLink-Items.dll', 'DragonLink-Stacks.dll', 'DragonLink-Weights.dll', 'DragonLink-ProximityLoot.dll')) {
    $legacyPath = Join-Path $Target $legacyName
    if (Test-Path -LiteralPath $legacyPath) { Remove-Item -LiteralPath $legacyPath -Force }
}
foreach ($Name in $RequiredOutputs) {
    if (-not $Outputs[$Name]) { throw "Native build did not produce $Name" }
    Copy-Item -LiteralPath $Outputs[$Name].FullName -Destination (Join-Path $Target $Name) -Force
}
Copy-Item -LiteralPath (Join-Path $ModsSource 'DragonLink\DragonLink.ini') -Destination (Join-Path $StageRoot 'DragonLink\DragonLink.ini') -Force
Set-Content -LiteralPath (Join-Path $StageRoot 'DragonLink\enabled.txt') -Value '' -Encoding ascii

if (-not $CriticalOnly) {
    $ProximityOutput = $Candidates | Where-Object Name -eq 'DragonLink-ProximityLoot.dll' | Select-Object -First 1
    if (-not $ProximityOutput) { throw 'Native build did not produce DragonLink-ProximityLoot.dll' }
    $ProximityRoot = Join-Path $StageRoot 'DragonLink-ProximityLoot'
    $ProximityTarget = Join-Path $ProximityRoot 'dlls'
    New-Item -ItemType Directory -Force -Path $ProximityTarget | Out-Null
    Copy-Item -LiteralPath $ProximityOutput.FullName -Destination (Join-Path $ProximityTarget 'main.dll') -Force
    Copy-Item -LiteralPath (Join-Path $ModsSource 'DragonLink-ProximityLoot\ProximityLoot.ini') -Destination (Join-Path $ProximityRoot 'ProximityLoot.ini') -Force
    $proximityEnabled = Join-Path $ProximityRoot 'enabled.txt'
    if (Test-Path -LiteralPath $proximityEnabled) { Remove-Item -LiteralPath $proximityEnabled -Force }
}

Write-Host "Staged native UE4SS mods in $StageRoot"
if ($CriticalOnly) { Write-Host 'Critical build verified: DragonLink host + Chat + Connect.' }
if ($KeepBuildTree) { Write-Host "Native build tree retained at $BuildRoot." }
