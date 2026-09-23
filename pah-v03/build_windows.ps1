param(
    [string]$OutputRoot = "dist",
    [switch]$SkipCorpus
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python -m pip install -U pip
python -m pip install . pyinstaller pytest pymupdf pillow pikepdf
python -m pytest -q

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name "PDFAccessibilityHelper" `
    --collect-all ocrmypdf `
    --collect-all pdf_a11y `
    --collect-all opendataloader_pdf `
    --collect-all pypdfium2 `
    --collect-all pikepdf `
    --collect-all fitz `
    --collect-all PIL `
    --hidden-import yaml `
    "launcher.py"

$app = Join-Path $root "$OutputRoot\PDFAccessibilityHelper"
$runtime = Join-Path $app "runtime"
New-Item -ItemType Directory -Force -Path $runtime | Out-Null

$tesseractCandidates = @(
    "$env:ProgramFiles\Tesseract-OCR\tesseract.exe",
    "$env:LOCALAPPDATA\Programs\Tesseract-OCR\tesseract.exe",
    "C:\tools\tesseract\tesseract.exe"
)
$tesseractExe = $tesseractCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $tesseractExe) {
    $cmd = Get-Command tesseract.exe -ErrorAction SilentlyContinue
    if ($cmd) { $tesseractExe = $cmd.Source }
}
if (-not $tesseractExe) { throw "Tesseract installation not found." }
$tesseractDir = Split-Path -Parent $tesseractExe
Copy-Item -Path $tesseractDir -Destination (Join-Path $runtime "tesseract") -Recurse -Force

$javaExe = Get-ChildItem "$env:ProgramFiles\Eclipse Adoptium" -Recurse -File -Filter java.exe -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match '\\bin\\java\.exe$' } |
    Sort-Object FullName -Descending |
    Select-Object -First 1
if (-not $javaExe) {
    $cmd = Get-Command java.exe -ErrorAction SilentlyContinue
    if ($cmd) { $javaExe = Get-Item $cmd.Source }
}
if (-not $javaExe) { throw "Temurin Java runtime not found." }
$jreRoot = Split-Path -Parent (Split-Path -Parent $javaExe.FullName)
Copy-Item -Path $jreRoot -Destination (Join-Path $runtime "jre") -Recurse -Force

$veraTarget = Join-Path $runtime "verapdf"
& "$root\scripts\install_verapdf.ps1" -InstallDir $veraTarget

Copy-Item "$root\README.md" $app -Force
Copy-Item "$root\LICENSE" $app -Force
Copy-Item "$root\THIRD_PARTY.md" $app -Force

$tessBundled = Join-Path $runtime "tesseract\tesseract.exe"
$javaBundled = Join-Path $runtime "jre\bin\java.exe"
$vera = Get-ChildItem $veraTarget -Recurse -File -Filter verapdf.bat | Select-Object -First 1
if (-not (Test-Path $tessBundled)) { throw "Bundled Tesseract executable is missing." }
if (-not (Test-Path $javaBundled)) { throw "Bundled Java executable is missing." }
if (-not $vera) { throw "Bundled veraPDF launcher is missing." }
& $tessBundled --version | Select-Object -First 1
& $javaBundled -version
& $vera.FullName --version

# PyInstaller --windowed creates a GUI-subsystem EXE. Start-Process -Wait is
# required here; a bare PowerShell invocation can return before the GUI process
# has written its diagnostic/batch output files.
$diag = Join-Path $app "build-diagnostics.json"
$exe = Join-Path $app "PDFAccessibilityHelper.exe"
$diagProc = Start-Process -FilePath $exe -ArgumentList @("--diagnostics", "`"$diag`"") -Wait -PassThru
if ($diagProc.ExitCode -ne 0) { throw "Frozen-app diagnostics failed with exit code $($diagProc.ExitCode)" }
$diagJson = Get-Content $diag -Raw | ConvertFrom-Json
if (-not $diagJson.ok) { throw "Frozen-app diagnostics reported missing dependencies." }

if (-not $SkipCorpus) {
    python .\scripts\generate_test_corpus.py
    $corpusOutput = Join-Path $root "test-corpus\output"
    if (Test-Path $corpusOutput) { Remove-Item $corpusOutput -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $corpusOutput | Out-Null

    $corpusInput = Join-Path $root "test-corpus\input"
    $batchProc = Start-Process -FilePath $exe -ArgumentList @("--batch", "`"$corpusInput`"", "`"$corpusOutput`"") -Wait -PassThru
    if ($batchProc.ExitCode -ne 0) { throw "Corpus run aborted with exit code $($batchProc.ExitCode)" }
    $summary = Get-Content (Join-Path $corpusOutput "batch-result.json") -Raw | ConvertFrom-Json
    if ($summary.processed -ne 11) { throw "Corpus run processed $($summary.processed) files instead of 11." }
    if ($summary.failed -lt 2) { throw "Corpus expected at least the malformed and encrypted fixtures to fail cleanly." }

    Copy-Item (Join-Path $root "test-corpus") (Join-Path $app "test-corpus") -Recurse -Force
}

Write-Host "Portable Windows build created at $app"
