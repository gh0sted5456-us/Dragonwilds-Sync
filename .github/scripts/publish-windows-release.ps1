$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$appRoot = Join-Path $repoRoot 'app-next'
$package = Get-Content -Raw -LiteralPath (Join-Path $appRoot 'package.json') | ConvertFrom-Json
$version = $package.version
if ($version -notmatch '^\d+\.\d+\.\d+-super-experimental$') { throw 'Expected an explicit Super Experimental package version.' }
$tag = "v$version"
$commit = $env:GITHUB_SHA
$repo = $env:GITHUB_REPOSITORY
if ($commit -notmatch '^[a-f0-9]{40}$' -or $repo -ne 'gh0sted5456-us/Dragonwilds-Sync') { throw 'Unexpected release repository or commit.' }
$artifacts = @(Get-ChildItem -LiteralPath (Join-Path $appRoot 'release') -Filter "RSDW-Sync-Super-Experimental-$version-portable.exe")
if ($artifacts.Count -ne 1) { throw 'Expected exactly one matching portable executable.' }
$buildInfo = Join-Path $appRoot 'release\BUILD-INFO.txt'
if (-not (Test-Path -LiteralPath $buildInfo)) { throw 'Verified build metadata is missing.' }

# Existing release tags are immutable identities: never silently move one to main.
$refs = @(git -C $repoRoot ls-remote --tags origin "refs/tags/$tag" "refs/tags/$tag^{}")
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the release tag.' }
if ($refs.Count -gt 0) {
  $peeled = @($refs | Where-Object { $_ -match '\^\{\}$' })
  $target = if ($peeled.Count) { ($peeled[0] -split '\s+')[0] } else { ($refs[0] -split '\s+')[0] }
  if ($target -ne $commit) { throw "Release tag $tag already points to another commit. Bump the package version; tags are never moved." }
}
$savedErrorPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue' # A missing release is expected on its first publication.
  gh release view $tag --repo $repo --json tagName 2>$null | Out-Null
  $exists = $LASTEXITCODE -eq 0
} finally { $ErrorActionPreference = $savedErrorPreference }
if ($exists) {
  if ($refs.Count -eq 0) { throw 'Release exists without a verifiable tag.' }
  gh release upload $tag $artifacts[0].FullName $buildInfo --repo $repo --clobber
} else {
  gh release create $tag $artifacts[0].FullName $buildInfo --repo $repo --target $commit --title "RSDW Sync $version" --notes-file (Join-Path $appRoot 'CHANGELOG.md') --prerelease
}
if ($LASTEXITCODE -ne 0) { throw 'GitHub release publication failed.' }
Write-Host "Published $tag from $commit"
