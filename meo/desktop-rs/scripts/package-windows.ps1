<#
.SYNOPSIS
  Packs a built Meo AI Windows folder into a Velopack release.

.DESCRIPTION
  Stages meo-ai-desktop.exe with the Qt runtime (windeployqt), the QML sources and the MeoUI
  QML module, then runs `vpk pack`. The output (Setup.exe, the .nupkg full package and RELEASES
  feed) is written to -OutDir. Publishing to GitHub Releases is a separate step:
    vpk upload github --repoUrl https://github.com/QwQdoge/meo-ai --tag v<Version> --publish --token <token>
  so a release is never published as a side effect of packing.

.PARAMETER Version
  Release version, SemVer, e.g. 0.1.0-beta.10.

.PARAMETER BinDir
  Folder with meo-ai-desktop.exe, normally target\release.

.PARAMETER MeoUiQmlDir
  Folder that holds the MeoUI QML module (contains MeoUI\qmldir).

.PARAMETER MeoUiBinDir
  Folder that holds libmeoui.dll and the MeoUI plugin DLL.

.PARAMETER QtBinDir
  Qt 6 bin folder that contains windeployqt.exe, e.g. C:\Qt\6.9.1\msvc2022_64\bin.

.PARAMETER OutDir
  Where the stage folder and Velopack packages are written.

.PARAMETER VelopackVersion
  vpk version. It must match the velopack crate in Cargo.toml (1.2.161).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Version,
    [Parameter(Mandatory)] [string] $BinDir,
    [Parameter(Mandatory)] [string] $MeoUiQmlDir,
    [Parameter(Mandatory)] [string] $MeoUiBinDir,
    [Parameter(Mandatory)] [string] $QtBinDir,
    [string] $OutDir = 'dist',
    [string] $VelopackVersion = '1.2.161'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot          # meo/desktop-rs
$stage = Join-Path $OutDir 'stage'

# Pin vpk to the crate version so packages and the in-app updater agree.
dotnet tool install --global vpk --version $VelopackVersion 2>$null
if ($LASTEXITCODE -ne 0) { dotnet tool update --global vpk --version $VelopackVersion }

Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $stage | Out-Null

# The executable and the QML sources the app loads from beside it (qml_root in main.rs).
Copy-Item (Join-Path $BinDir 'meo-ai-desktop.exe') $stage
Copy-Item (Join-Path $root 'qml') (Join-Path $stage 'qml') -Recurse
Copy-Item (Join-Path $MeoUiQmlDir 'MeoUI') (Join-Path $stage 'qml\MeoUI') -Recurse
Copy-Item (Join-Path $MeoUiBinDir '*.dll') $stage

# Qt runtime and the QtQuick modules the QML imports.
& (Join-Path $QtBinDir 'windeployqt.exe') --release --no-translations --qmldir (Join-Path $stage 'qml') (Join-Path $stage 'meo-ai-desktop.exe')
if ($LASTEXITCODE -ne 0) { throw "windeployqt failed with exit code $LASTEXITCODE" }

vpk pack `
    --packId MeoAI `
    --packTitle 'Meo AI' `
    --packVersion $Version `
    --packDir $stage `
    --mainExe meo-ai-desktop.exe `
    --outputDir $OutDir
if ($LASTEXITCODE -ne 0) { throw "vpk pack failed with exit code $LASTEXITCODE" }

Write-Output "Packed Meo AI $Version into $OutDir (not published)."
