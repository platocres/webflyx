from pathlib import Path

root = Path("pdf-accessibility-helper")

# pdf-a11y falls back from OpenDataLoader to its built-in heuristic tagger
# when the JVM tagger fails. Our generated config must include the fallback
# thresholds or pdf-a11y raises KeyError("heuristic") and masks the real cause.
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

# Tighten the adversarial-corpus gate. Merely failing cleanly is not enough:
# most valid fixtures must produce a remediated output (ready or review).
build_path = root / "scripts" / "build_windows.ps1"
text = build_path.read_text(encoding="utf-8")
gate = '    if ($summary.failed -lt 2) { throw "Corpus expected at least the malformed and encrypted fixtures to fail cleanly." }\n'
stronger = gate + '''    if (($summary.ready + $summary.review) -lt 7) { throw "Corpus expected at least 7 valid fixtures to produce remediated output." }
    if ($summary.failed -gt 4) { throw "Corpus had too many failures: $($summary.failed) of 11." }
'''
if "at least 7 valid fixtures" not in text:
    if gate not in text:
        raise SystemExit("Could not locate corpus gate")
    text = text.replace(gate, stronger, 1)
build_path.write_text(text, encoding="utf-8")

print("Patched fallback tagger configuration and strengthened corpus acceptance gate.")
