from __future__ import annotations

import sys
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"Could not locate {label}")
    return text.replace(old, new, 1)


def main() -> None:
    root = Path(sys.argv[1]).resolve()

    # veraPDF downloader: follow the official redirect robustly on Windows CI.
    p = root / "scripts" / "install_verapdf.ps1"
    s = p.read_text(encoding="utf-8")
    s = replace_once(
        s,
        '    Invoke-WebRequest -Uri "https://downloads.verapdf.org/rel/verapdf-installer.zip" -OutFile $zip\n',
        '    & curl.exe -L --fail --silent --show-error "https://downloads.verapdf.org/rel/verapdf-installer.zip" -o $zip\n'
        '    if ($LASTEXITCODE -ne 0) { throw "veraPDF download failed with exit code $LASTEXITCODE" }\n',
        "veraPDF download line",
    )
    p.write_text(s, encoding="utf-8")

    # Extra import-order guard for asyncio.
    p = root / "launcher.py"
    s = p.read_text(encoding="utf-8")
    if "import asyncio\n" not in s:
        s = replace_once(s, "import argparse\n", "import argparse\nimport asyncio\n", "launcher argparse import")
    p.write_text(s, encoding="utf-8")

    # Keep subprocess.Popen class-compatible while hiding helper consoles.
    p = root / "src" / "pdf_accessibility_helper" / "runtime.py"
    s = p.read_text(encoding="utf-8")
    old_start = "        def hidden_popen(*args, **kwargs):  # type: ignore[no-untyped-def]"
    old_end = "        subprocess.Popen = hidden_popen  # type: ignore[assignment]"
    start = s.find(old_start)
    end = s.find(old_end)
    if start < 0 or end < 0:
        raise SystemExit("Could not locate hidden_popen implementation")
    end += len(old_end)
    new_block = '''        class HiddenPopen(_ORIGINAL_POPEN):
            """Popen-compatible subclass that suppresses helper consoles on Windows.

            Keeping subprocess.Popen as a class matters because asyncio and other
            libraries subclass it during import.
            """

            def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                if _CHILD_LAUNCH_BLOCKED.is_set():
                    raise ChildLaunchBlocked("Processing was stopped; helper process launch was blocked.")

                creationflags = int(kwargs.get("creationflags", 0) or 0)
                creationflags &= ~int(getattr(subprocess, "CREATE_NEW_CONSOLE", 0) or 0)
                creationflags |= int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)
                kwargs["creationflags"] = creationflags

                startupinfo = kwargs.get("startupinfo")
                if startupinfo is None:
                    startupinfo = subprocess.STARTUPINFO()
                else:
                    try:
                        startupinfo = copy.copy(startupinfo)
                    except Exception:
                        pass
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
                kwargs["startupinfo"] = startupinfo

                if kwargs.get("stdin") is None:
                    kwargs["stdin"] = subprocess.DEVNULL

                super().__init__(*args, **kwargs)
                _register_child(self)

        subprocess.Popen = HiddenPopen  # type: ignore[assignment]'''
    s = s[:start] + new_block + s[end:]
    p.write_text(s, encoding="utf-8")

    # PDF catalog tagging marker + version fallback/report identity.
    p = root / "src" / "pdf_accessibility_helper" / "pipeline.py"
    s = p.read_text(encoding="utf-8")
    marker = '''        if not root.get("/Lang", None):
            root["/Lang"] = pikepdf.String("en-US")

        viewer = root.get("/ViewerPreferences", None)
'''
    marker_replacement = '''        if not root.get("/Lang", None):
            root["/Lang"] = pikepdf.String("en-US")

        # Acrobat and PDF/UA validators require the catalog to declare that
        # the document is marked/tagged in addition to having StructTreeRoot.
        mark_info = root.get("/MarkInfo", None)
        if mark_info is None:
            mark_info = pikepdf.Dictionary()
            root["/MarkInfo"] = mark_info
        mark_info["/Marked"] = True

        viewer = root.get("/ViewerPreferences", None)
'''
    s = replace_once(s, marker, marker_replacement, "accessibility metadata insertion point")
    if "from . import __version__" not in s:
        s = replace_once(
            s,
            "from .models import BatchResult, FileResult\n",
            "from .models import BatchResult, FileResult\nfrom . import __version__\n",
            "models import",
        )
    s = replace_once(
        s,
        '        except importlib.metadata.PackageNotFoundError:\n            versions[label] = "unknown"\n',
        '        except importlib.metadata.PackageNotFoundError:\n'
        '            versions[label] = __version__ if label == "PDF Accessibility Helper" else "unknown"\n',
        "tool version fallback",
    )
    s = s.replace("v0.4 uses an adaptive workflow:", "v0.4.2 uses an adaptive workflow:")
    p.write_text(s, encoding="utf-8")

    # Windows buttons: ask the shell to open folders/files with their registered handler.
    p = root / "windows_frontend" / "main.go"
    s = p.read_text(encoding="utf-8")
    s = replace_once(
        s,
        '\tprocSHBrowseForFolderW   = shell32.NewProc("SHBrowseForFolderW")\n'
        '\tprocSHGetPathFromIDListW = shell32.NewProc("SHGetPathFromIDListW")\n',
        '\tprocSHBrowseForFolderW   = shell32.NewProc("SHBrowseForFolderW")\n'
        '\tprocSHGetPathFromIDListW = shell32.NewProc("SHGetPathFromIDListW")\n'
        '\tprocShellExecuteW         = shell32.NewProc("ShellExecuteW")\n',
        "shell32 declarations",
    )
    open_start = s.find("func openPath(path string) {")
    open_end_marker = "\n}\n\nfunc wndProc"
    open_end = s.find(open_end_marker, open_start)
    if open_start < 0 or open_end < 0:
        raise SystemExit("Could not locate openPath function")
    open_end += 3
    new_open = r'''func openPath(owner syscall.Handle, path string) error {
	path = strings.TrimSpace(path)
	if path == "" {
		return fmt.Errorf("no path was provided")
	}
	if _, err := os.Stat(path); err != nil {
		return fmt.Errorf("the path does not exist: %s", path)
	}

	result, _, callErr := procShellExecuteW.Call(
		uintptr(owner),
		uintptr(unsafe.Pointer(utf16("open"))),
		uintptr(unsafe.Pointer(utf16(path))),
		0,
		0,
		SW_SHOW,
	)
	if result <= 32 {
		if callErr != nil && callErr != syscall.Errno(0) {
			return fmt.Errorf("Windows could not open %s: %v", path, callErr)
		}
		return fmt.Errorf("Windows could not open %s (ShellExecute code %d)", path, result)
	}
	return nil
}
'''
    s = s[:open_start] + new_open + s[open_end:]
    old_handlers = '''\t\tcase ID_OPEN:
\t\t\tstate.mu.Lock()
\t\t\tp := state.outputDir
\t\t\tstate.mu.Unlock()
\t\t\topenPath(p)
\t\tcase ID_REPORT:
\t\t\tstate.mu.Lock()
\t\t\tp := filepath.Join(state.outputDir, "_accessibility_reports", "Accessibility_Remediation_Summary.html")
\t\t\tstate.mu.Unlock()
\t\t\topenPath(p)
'''
    new_handlers = '''\t\tcase ID_OPEN:
\t\t\tstate.mu.Lock()
\t\t\tp := state.outputDir
\t\t\tstate.mu.Unlock()
\t\t\tif err := openPath(hwnd, p); err != nil {
\t\t\t\tmessageBox(hwnd, "Open output folder", err.Error(), MB_OK|MB_ICONERROR)
\t\t\t}
\t\tcase ID_REPORT:
\t\t\tstate.mu.Lock()
\t\t\tp := filepath.Join(state.outputDir, "_accessibility_reports", "Accessibility_Remediation_Summary.html")
\t\t\tstate.mu.Unlock()
\t\t\tif err := openPath(hwnd, p); err != nil {
\t\t\t\tmessageBox(hwnd, "View report", err.Error(), MB_OK|MB_ICONERROR)
\t\t\t}
'''
    s = replace_once(s, old_handlers, new_handlers, "button handlers")
    p.write_text(s, encoding="utf-8")

    # Version identity.
    for rel in ("src/pdf_accessibility_helper/__init__.py", "pyproject.toml"):
        p = root / rel
        p.write_text(p.read_text(encoding="utf-8").replace("0.4.0", "0.4.2"), encoding="utf-8")

    # Synchronous frozen-engine tests and packaged version.
    p = root / "scripts" / "build_windows.ps1"
    s = p.read_text(encoding="utf-8")
    s = s.replace("0.4.0 - adaptive performance build", "0.4.2 - adaptive performance build")
    s = replace_once(
        s,
        '& $engine --diagnostics $diag\nif ($LASTEXITCODE -ne 0) { throw "Frozen-app diagnostics failed with exit code $LASTEXITCODE" }',
        '$p = Start-Process -FilePath $engine -ArgumentList @("--diagnostics", $diag) -Wait -PassThru\n'
        'if ($p.ExitCode -ne 0) { throw "Frozen-app diagnostics failed with exit code $($p.ExitCode)" }',
        "diagnostics invocation",
    )
    s = replace_once(
        s,
        '& $engine --runtime-self-test $runtimeSelfTest\nif ($LASTEXITCODE -ne 0) { throw "Hidden-child runtime self-test failed with exit code $LASTEXITCODE" }',
        '$p = Start-Process -FilePath $engine -ArgumentList @("--runtime-self-test", $runtimeSelfTest) -Wait -PassThru\n'
        'if ($p.ExitCode -ne 0) { throw "Hidden-child runtime self-test failed with exit code $($p.ExitCode)" }',
        "runtime self-test invocation",
    )
    s = replace_once(
        s,
        '    & $engine --batch (Join-Path $root "test-corpus\\input") $corpusOutput\n'
        '    if ($LASTEXITCODE -ne 0) { throw "Corpus run aborted with exit code $LASTEXITCODE" }',
        '    $p = Start-Process -FilePath $engine -ArgumentList @("--batch", (Join-Path $root "test-corpus\\input"), $corpusOutput) -Wait -PassThru\n'
        '    if ($p.ExitCode -ne 0) { throw "Corpus run aborted with exit code $($p.ExitCode)" }',
        "corpus invocation",
    )
    p.write_text(s, encoding="utf-8")

    # Patch-time assertions.
    assert 'mark_info["/Marked"] = True' in (root / "src/pdf_accessibility_helper/pipeline.py").read_text(encoding="utf-8")
    assert 'class HiddenPopen(_ORIGINAL_POPEN)' in (root / "src/pdf_accessibility_helper/runtime.py").read_text(encoding="utf-8")
    assert 'ShellExecuteW' in (root / "windows_frontend/main.go").read_text(encoding="utf-8")
    print("v0.4.2 source patches applied")


if __name__ == "__main__":
    main()
