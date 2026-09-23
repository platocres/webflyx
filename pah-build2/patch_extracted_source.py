from pathlib import Path

root = Path("pdf-accessibility-helper")

# Release version for the Windows portability/validation milestone.
for rel in ("pyproject.toml", "src/pdf_accessibility_helper/__init__.py"):
    p = root / rel
    text = p.read_text(encoding="utf-8")
    text = text.replace('version = "0.2.0"', 'version = "0.2.2"')
    text = text.replace('__version__ = "0.2.0"', '__version__ = "0.2.2"')
    p.write_text(text, encoding="utf-8")

# pdf-a11y falls back from OpenDataLoader to its built-in heuristic tagger
# when the JVM tagger fails. Keep that fallback fully configured so an
# upstream failure never gets masked by KeyError("heuristic").
config_path = root / "src" / "pdf_accessibility_helper" / "config.py"
text = config_path.read_text(encoding="utf-8")
needle = '            "opendataloader": {},\n'
replacement = '''            "opendataloader": {},
            "heuristic": {
                "heading_thresholds": {
                    "h1": 20.0,
                    "h2": 16.0,
                    "h3": 13.0,
                    "h4": 11.5,
                },
                "body_min_size": 8.5,
            },
'''
if '"heuristic": {' not in text:
    if needle not in text:
        raise SystemExit("Could not locate opendataloader config block")
    text = text.replace(needle, replacement, 1)
config_path.write_text(text, encoding="utf-8")

# PyInstaller --windowed starts with sys.stdout/sys.stderr == None on Windows.
# OpenDataLoader's Python runner relays Java output to sys.stdout and otherwise
# crashes with "'NoneType' object has no attribute 'write'", forcing pdf-a11y
# onto its weaker fallback tagger. Give libraries a writable null stream.
launcher = root / "launcher.py"
text = launcher.read_text(encoding="utf-8")
if "def _ensure_standard_streams()" not in text:
    text = text.replace(
        "import json\nfrom pathlib import Path\n",
        "import json\nimport os\nimport sys\nfrom pathlib import Path\n",
        1,
    )
    text = text.replace(
        "\n\ndef main() -> int:\n",
        '''\n\ndef _ensure_standard_streams() -> None:
    """Provide writable streams in a PyInstaller --windowed executable."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def main() -> int:
    _ensure_standard_streams()
''',
        1,
    )
launcher.write_text(text, encoding="utf-8")

# Strengthen corpus acceptance. Ordinary documents must survive OCR/tagging,
# get structure + language metadata, and must use OpenDataLoader rather than
# silently falling back to the approximation tagger.
build_path = root / "scripts" / "build_windows.ps1"
text = build_path.read_text(encoding="utf-8")
gate = '    if ($summary.failed -lt 2) { throw "Corpus expected at least the malformed and encrypted fixtures to fail cleanly." }\n'
stronger = gate + r'''    $detailPath = Join-Path $corpusOutput "_accessibility_reports\Accessibility_Remediation_Summary.json"
    if (-not (Test-Path $detailPath)) { throw "Corpus detail report was not generated." }
    $detail = Get-Content $detailPath -Raw | ConvertFrom-Json

    $expectedGood = @(
        "01_digital_simple.pdf",
        "02_scanned_handout.pdf",
        "03_mixed_text_and_scan.pdf",
        "04_multicolumn.pdf",
        "05_table.pdf",
        "06_meaningful_image.pdf",
        "07_existing_metadata.pdf",
        "08_existing_tagged_minimal.pdf"
    )
    foreach ($name in $expectedGood) {
        $row = $detail.files | Where-Object { $_.source_file -eq $name } | Select-Object -First 1
        if (-not $row) { throw "Corpus report is missing $name." }
        if ($row.status -eq "failed") { throw "Ordinary corpus fixture failed: $name :: $($row.error)" }
        if (-not $row.output_file) { throw "Ordinary corpus fixture produced no output: $name" }
        if ($row.pages_without_text_after -gt 0) { throw "Text verification failed after OCR for $name." }
        if (-not $row.structure_tree_present) { throw "Structure tree missing after remediation for $name." }
        if (-not $row.document_language_present) { throw "Document language missing after remediation for $name." }
        $fallback = @($row.warnings | Where-Object { $_ -like "opendataloader tagging failed*" })
        if ($fallback.Count -gt 0) { throw "OpenDataLoader fell back on $name :: $($fallback -join '; ')" }
    }

    foreach ($name in @("02_scanned_handout.pdf", "03_mixed_text_and_scan.pdf")) {
        $row = $detail.files | Where-Object { $_.source_file -eq $name } | Select-Object -First 1
        if (-not $row.ocr_attempted) { throw "OCR path was not exercised for $name." }
        if ($row.pages_without_text_before -lt 1) { throw "OCR fixture did not begin with an image-only page: $name." }
        if ($row.pages_without_text_after -ne 0) { throw "OCR did not produce extractable text for $name." }
    }

    $malformed = $detail.files | Where-Object { $_.source_file -eq "10_malformed_truncated.pdf" } | Select-Object -First 1
    $encrypted = $detail.files | Where-Object { $_.source_file -eq "11_password_protected.pdf" } | Select-Object -First 1
    if ($malformed.status -ne "failed") { throw "Malformed fixture should fail cleanly." }
    if ($encrypted.status -ne "failed") { throw "Encrypted fixture should fail cleanly." }
'''
if "OpenDataLoader fell back on" not in text:
    if gate not in text:
        raise SystemExit("Could not locate corpus gate")
    text = text.replace(gate, stronger, 1)
build_path.write_text(text, encoding="utf-8")

print("Patched v0.2.2: fallback config, windowed stdout shim, and strict corpus gates.")
