param(
    [Parameter(Mandatory = $true)]
    [string]$SourceZip
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$source = [IO.Path]::GetFullPath($SourceZip)
$ueTarget = [IO.Path]::GetFullPath((Join-Path $projectRoot "resources\DragonwildsServerRuntime\UE4SS-core-latest.zip"))
$rsTarget = [IO.Path]::GetFullPath((Join-Path $projectRoot "resources\RuneSchema-core-latest.zip"))
if (-not $ueTarget.StartsWith($projectRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "UE4SS target escaped project" }
if (-not $rsTarget.StartsWith($projectRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "RuneSchema target escaped project" }
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Source ZIP was not found: $source" }

$ueTemp = "$ueTarget.pending"
$rsTemp = "$rsTarget.pending"
[IO.File]::Delete($ueTemp)
[IO.File]::Delete($rsTemp)
$input = [IO.Compression.ZipFile]::OpenRead($source)
try {
    $ueOut = [IO.Compression.ZipFile]::Open($ueTemp, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($entry in $input.Entries) {
            $name = $entry.FullName.Replace("\", "/")
            if ($name -match "(?i)/RuneSchema/mods/.+") { continue }
            $copy = $ueOut.CreateEntry($name, [IO.Compression.CompressionLevel]::Optimal)
            if ($entry.Length -gt 0) {
                $src = $entry.Open()
                $dst = $copy.Open()
                try { $src.CopyTo($dst) } finally { $dst.Dispose(); $src.Dispose() }
            }
        }
    } finally { $ueOut.Dispose() }

    $rsOut = [IO.Compression.ZipFile]::Open($rsTemp, [IO.Compression.ZipArchiveMode]::Create)
    try {
        $prefix = "UE4SS_v3.0.1-1028-gd7e7826d/ue4ss/Mods/RuneSchema/"
        foreach ($entry in $input.Entries) {
            $name = $entry.FullName.Replace("\", "/")
            if (-not $name.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { continue }
            $relative = $name.Substring($prefix.Length)
            if (-not $relative -or $relative -match "(?i)^mods/.+") { continue }
            $copy = $rsOut.CreateEntry("RuneSchema/$relative", [IO.Compression.CompressionLevel]::Optimal)
            if ($entry.Length -gt 0) {
                $src = $entry.Open()
                $dst = $copy.Open()
                try { $src.CopyTo($dst) } finally { $dst.Dispose(); $src.Dispose() }
            }
        }
        [void]$rsOut.CreateEntry("RuneSchema/mods/")
        [void]$rsOut.CreateEntry("RuneSchema/enabled.txt")
    } finally { $rsOut.Dispose() }
} finally { $input.Dispose() }

[IO.File]::Move($ueTemp, $ueTarget, $true)
[IO.File]::Move($rsTemp, $rsTarget, $true)
Get-FileHash -Algorithm SHA256 -LiteralPath $ueTarget, $rsTarget | Select-Object Path, Hash
Get-Item -LiteralPath $ueTarget, $rsTarget | Select-Object FullName, Length
