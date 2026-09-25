"""Assemble the self-contained runtime for the Electron app (no install needed on the target PC).

desktop/runtime/python   <- a copy of this machine's CPython (stdlib + DLLs) + the backend's
                            installed packages (TradingAgents etc.), minus dev-only tools.
desktop/runtime/backend  <- the backend source, precompiled.

Everything is precompiled to bytecode with "unchecked-hash" .pyc files: Python loads them without
checking file times, so they stay valid after the installer or the portable exe extracts the files
(timestamps change), and no launch ever recompiles thousands of modules. This is the main
start-up speed win on Windows.

Then run `npm run dist` in desktop/ to produce:
  desktop/dist/Veyro-Setup.exe          (recommended: installs once per user, no admin, fastest launches)
  desktop/dist/win-unpacked/Veyro.exe   (folder: copy anywhere, double-click; also fast)
`npm run dist:portable` also builds the single Veyro-Portable.exe (slower: it unpacks itself on every launch).
"""
from __future__ import annotations

import compileall
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "desktop" / "runtime" / "python"
BASE = Path(sys.base_prefix)                     # the real CPython install behind the venv
SITE = ROOT / ".venv" / "Lib" / "site-packages"

SKIP_STDLIB = {"test", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3", "site-packages", "__pycache__"}
SKIP_PKGS = ("playwright", "pytest", "_pytest", "pip", "setuptools", "pluggy", "iniconfig", "greenlet")
BACKEND_SRC = ROOT / "backend" / "veyro"
BACKEND_OUT = ROOT / "desktop" / "runtime" / "backend"


def precompile(path: Path) -> None:
    import py_compile
    ok = compileall.compile_dir(str(path), quiet=1, workers=0,
                                invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
    if not ok:
        print(f"note: some files under {path} did not compile (usually harmless test/template files)")


def ignore_pycache(_dir, names):
    return [n for n in names if n == "__pycache__"]


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for f in BASE.iterdir():
        if f.is_file() and f.suffix.lower() in (".exe", ".dll"):
            shutil.copy2(f, OUT / f.name)
    shutil.copytree(BASE / "DLLs", OUT / "DLLs", ignore=ignore_pycache)
    (OUT / "Lib").mkdir()
    for item in (BASE / "Lib").iterdir():
        if item.name in SKIP_STDLIB:
            continue
        if item.is_dir():
            shutil.copytree(item, OUT / "Lib" / item.name, ignore=ignore_pycache)
        else:
            shutil.copy2(item, OUT / "Lib" / item.name)
    dest = OUT / "Lib" / "site-packages"
    dest.mkdir()
    for item in SITE.iterdir():
        name = item.name.lower()
        if any(name == p or name.startswith(p + "-") or name.startswith(p + "_") for p in SKIP_PKGS):
            continue
        if item.is_dir():
            shutil.copytree(item, dest / item.name, ignore=ignore_pycache)
        else:
            shutil.copy2(item, dest / item.name)
    # the backend, copied and precompiled beside the runtime
    if BACKEND_OUT.exists():
        shutil.rmtree(BACKEND_OUT)
    shutil.copytree(BACKEND_SRC, BACKEND_OUT / "veyro", ignore=ignore_pycache)
    precompile(OUT / "Lib")
    precompile(BACKEND_OUT)
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    print(f"runtime ready: {OUT} ({size:.0f} MB)")


if __name__ == "__main__":
    main()
