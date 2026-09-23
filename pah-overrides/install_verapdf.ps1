param(
    [Parameter(Mandatory=$true)]
    [string]$InstallDir
)

$ErrorActionPreference = "Stop"
$work = Join-Path $env:TEMP ("verapdf-build-" + [guid]::NewGuid().ToString("N"))
$zip = Join-Path $work "verapdf-installer.zip"
$extract = Join-Path $work "installer"
$xml = Join-Path $work "auto-install.xml"

New-Item -ItemType Directory -Force -Path $work, $extract | Out-Null
try {
    Invoke-WebRequest -Uri "https://software.verapdf.org/releases/verapdf-installer.zip" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $extract -Force

    $escaped = [System.Security.SecurityElement]::Escape((Resolve-Path (Split-Path -Parent $InstallDir)).Path + "\\" + (Split-Path -Leaf $InstallDir))
    @"
<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<AutomatedInstallation langpack="eng">
  <com.izforge.izpack.panels.htmlhello.HTMLHelloPanel id="welcome"/>
  <com.izforge.izpack.panels.target.TargetPanel id="install_dir">
    <installpath>$escaped</installpath>
  </com.izforge.izpack.panels.target.TargetPanel>
  <com.izforge.izpack.panels.packs.PacksPanel id="sdk_pack_select">
    <pack index="0" name="veraPDF GUI" selected="true"/>
    <pack index="1" name="veraPDF Mac and *nix Scripts" selected="true"/>
    <pack index="2" name="veraPDF Corpus and Validation model" selected="true"/>
    <pack index="3" name="veraPDF Documentation" selected="false"/>
    <pack index="4" name="veraPDF Sample Plugins" selected="false"/>
  </com.izforge.izpack.panels.packs.PacksPanel>
  <com.izforge.izpack.panels.install.InstallPanel id="install"/>
  <com.izforge.izpack.panels.finish.FinishPanel id="finish"/>
</AutomatedInstallation>
"@ | Set-Content -Path $xml -Encoding UTF8

    $installer = Get-ChildItem -Path $extract -Recurse -File | Where-Object {
        $_.Name -match '^(verapdf-install|vera-install)\.bat$'
    } | Select-Object -First 1

    if (-not $installer) {
        throw "Could not find the veraPDF Windows installer batch file in the official installer archive."
    }

    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    & $installer.FullName $xml
    if ($LASTEXITCODE -ne 0) {
        throw "veraPDF unattended installer exited with code $LASTEXITCODE"
    }

    $launcher = Get-ChildItem -Path $InstallDir -Recurse -File -Filter "verapdf.bat" | Select-Object -First 1
    if (-not $launcher) {
        throw "veraPDF installed, but verapdf.bat was not found under $InstallDir"
    }
    Write-Host "veraPDF installed at $InstallDir"
}
finally {
    Remove-Item -Path $work -Recurse -Force -ErrorAction SilentlyContinue
}
