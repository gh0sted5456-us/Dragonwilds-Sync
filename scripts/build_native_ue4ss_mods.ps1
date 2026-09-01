param(
    [string]$BuildRoot = "$env:TEMP\dragonwilds-sync-native-ue4ss",
    [switch]$KeepBuildTree
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Ue4ssCommit = '0bfec09ee30b7c4cda8aa151e2fdb15cbe6c10c9'
$SourceRoot = Join-Path $BuildRoot 'RE-UE4SS'
$BuildDir = Join-Path $BuildRoot 'build'
$ModsSource = Join-Path $RepoRoot 'native\ue4ss-mods'
$StageRoot = Join-Path $RepoRoot 'resources\NativeRuntimeMods'

if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot '.git'))) {
    New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
    git -c url.https://github.com/.insteadOf=git@github.com: clone https://github.com/UE4SS-RE/RE-UE4SS.git $SourceRoot
}

git -C $SourceRoot fetch origin $Ue4ssCommit --depth=1
git -C $SourceRoot checkout --detach $Ue4ssCommit
git -C $SourceRoot -c url.https://github.com/.insteadOf=git@github.com: submodule update --init --recursive --depth=1

$CppMods = Join-Path $SourceRoot 'cppmods'
foreach ($Name in @('DragonLink', 'DragonLink-StacksWeights', 'DragonLink-Chat', 'DragonLink-Connect', 'DragonLink-ProximityLoot')) {
    $Destination = Join-Path $CppMods $Name
    if (Test-Path -LiteralPath $Destination) { Remove-Item -LiteralPath $Destination -Recurse -Force }
    Copy-Item -LiteralPath (Join-Path $ModsSource $Name) -Destination $Destination -Recurse
}
$CppModsCmake = Join-Path $CppMods 'CMakeLists.txt'
$CmakeText = Get-Content -LiteralPath $CppModsCmake -Raw
foreach ($Name in @('DragonLink', 'DragonLink-StacksWeights', 'DragonLink-Chat', 'DragonLink-Connect', 'DragonLink-ProximityLoot')) {
    $Line = "add_subdirectory(`"$Name`")"
    if (-not $CmakeText.Contains($Line)) { $CmakeText += "`r`n$Line" }
}
Set-Content -LiteralPath $CppModsCmake -Value $CmakeText -Encoding utf8

cmake -S $SourceRoot -B $BuildDir -G 'Visual Studio 18 2026' -A x64
if ($LASTEXITCODE -ne 0) { throw "Native UE4SS CMake configuration failed with exit code $LASTEXITCODE" }
cmake --build $BuildDir --config Game__Shipping__Win64 --target DragonLink DragonLinkStacksWeights DragonLinkChat DragonLinkConnect DragonLinkProximityLoot --parallel
if ($LASTEXITCODE -ne 0) { throw "Native DragonLink build failed with exit code $LASTEXITCODE" }

$Candidates = Get-ChildItem -LiteralPath $BuildDir -Filter '*.dll' -Recurse
$Outputs = @{
    'main.dll' = ($Candidates | Where-Object Name -eq 'DragonLink.dll' | Select-Object -First 1)
    'DragonLink-StacksWeights.dll' = ($Candidates | Where-Object Name -eq 'DragonLink-StacksWeights.dll' | Select-Object -First 1)
    'DragonLink-Chat.dll' = ($Candidates | Where-Object Name -eq 'DragonLink-Chat.dll' | Select-Object -First 1)
    'DragonLink-Connect.dll' = ($Candidates | Where-Object Name -eq 'DragonLink-Connect.dll' | Select-Object -First 1)
}
$ProximityOutput = $Candidates | Where-Object Name -eq 'DragonLink-ProximityLoot.dll' | Select-Object -First 1
$Target = Join-Path $StageRoot 'DragonLink\dlls'
New-Item -ItemType Directory -Force -Path $Target | Out-Null
(Join-Path $Target 'DragonLink-Core.dll') | ForEach-Object { if (Test-Path -LiteralPath $_) { Remove-Item -LiteralPath $_ -Force } }
(Join-Path $Target 'DragonLink-Items.dll') | ForEach-Object { if (Test-Path -LiteralPath $_) { Remove-Item -LiteralPath $_ -Force } }
(Join-Path $Target 'DragonLink-Stacks.dll') | ForEach-Object { if (Test-Path -LiteralPath $_) { Remove-Item -LiteralPath $_ -Force } }
(Join-Path $Target 'DragonLink-Weights.dll') | ForEach-Object { if (Test-Path -LiteralPath $_) { Remove-Item -LiteralPath $_ -Force } }
(Join-Path $Target 'DragonLink-ProximityLoot.dll') | ForEach-Object { if (Test-Path -LiteralPath $_) { Remove-Item -LiteralPath $_ -Force } }
foreach ($Name in $Outputs.Keys) {
    if (-not $Outputs[$Name]) { throw "Native build did not produce $Name" }
    Copy-Item -LiteralPath $Outputs[$Name].FullName -Destination (Join-Path $Target $Name) -Force
}
Copy-Item -LiteralPath (Join-Path $ModsSource 'DragonLink\DragonLink.ini') -Destination (Join-Path $StageRoot 'DragonLink\DragonLink.ini') -Force
Set-Content -LiteralPath (Join-Path $StageRoot 'DragonLink\enabled.txt') -Value '' -Encoding ascii

if (-not $ProximityOutput) { throw 'Native build did not produce DragonLink-ProximityLoot.dll' }
$ProximityRoot = Join-Path $StageRoot 'DragonLink-ProximityLoot'
$ProximityTarget = Join-Path $ProximityRoot 'dlls'
New-Item -ItemType Directory -Force -Path $ProximityTarget | Out-Null
Copy-Item -LiteralPath $ProximityOutput.FullName -Destination (Join-Path $ProximityTarget 'main.dll') -Force
Copy-Item -LiteralPath (Join-Path $ModsSource 'DragonLink-ProximityLoot\ProximityLoot.ini') -Destination (Join-Path $ProximityRoot 'ProximityLoot.ini') -Force
(Join-Path $ProximityRoot 'enabled.txt') | ForEach-Object { if (Test-Path -LiteralPath $_) { Remove-Item -LiteralPath $_ -Force } }

if (-not $KeepBuildTree) { Write-Host "Native build tree retained at $BuildRoot for reproducibility." }
Write-Host "Staged native UE4SS mods in $StageRoot"
