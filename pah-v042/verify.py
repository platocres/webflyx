from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import pikepdf


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    out = root / "test-corpus" / "output"
    summary = out / "_accessibility_reports" / "Accessibility_Remediation_Summary.csv"
    rows = list(csv.DictReader(summary.open(encoding="utf-8-sig")))

    checked = 0
    for row in rows:
        if row["status"] == "failed" or not row["output_file"]:
            continue
        pdf_path = out / row["output_file"]
        with pikepdf.Pdf.open(pdf_path) as pdf:
            catalog = pdf.Root
            if "/StructTreeRoot" not in catalog:
                raise SystemExit(f"{pdf_path.name}: missing StructTreeRoot")
            mark = catalog.get("/MarkInfo", None)
            if not mark or not bool(mark.get("/Marked", False)):
                raise SystemExit(f"{pdf_path.name}: missing /MarkInfo /Marked true")
        checked += 1

    if checked < 9:
        raise SystemExit(f"Expected at least 9 completed corpus PDFs, checked {checked}")

    version = (root / "dist" / "PDFAccessibilityHelper" / "VERSION.txt").read_text(encoding="utf-8").strip()
    if not re.match(r"^0\.4\.2\b", version):
        raise SystemExit(f"Wrong packaged version: {version}")

    html = (out / "_accessibility_reports" / "Accessibility_Remediation_Summary.html").read_text(encoding="utf-8")
    if "v0.4.2 uses an adaptive workflow" not in html:
        raise SystemExit("HTML report did not get v0.4.2 identity")

    app_dir = root / "dist" / "PDFAccessibilityHelper"
    for name in ("PDFAccessibilityHelper.exe", "PDFAccessibilityEngine.exe"):
        if not (app_dir / name).exists():
            raise SystemExit(f"Missing packaged executable: {name}")

    print(f"Verified tagged-PDF metadata on {checked} corpus outputs.")
    print(f"Verified packaged version: {version}")


if __name__ == "__main__":
    main()
