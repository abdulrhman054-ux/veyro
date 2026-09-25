"""Assemble the self-contained runtime for the Electron app (no install needed on the target PC).

desktop/runtime/python   <- a copy of this machine's CPython (stdlib + DLLs) + the backend's
                            installed packages (TradingAgents etc.), minus dev-only tools.
Then run `npm run dist` in desktop/ to produce:
  desktop/dist/win-unpacked/Veyro.exe   (portable folder: copy anywhere, double-click)
  desktop/dist/Veyro-Portable.exe       (single portable exe)
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "desktop" / "runtime" / "python"
BASE = Path(sys.base_prefix)                     # the real CPython install behind the venv
SITE = ROOT / ".venv" / "Lib" / "site-packages"

SKIP_STDLIB = {"test", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3", "site-packages", "__pycache__"}
SKIP_PKGS = ("playwright", "pytest", "_pytest", "pip", "setuptools", "pluggy", "iniconfig", "greenlet")


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
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    print(f"runtime ready: {OUT} ({size:.0f} MB)")


if __name__ == "__main__":
    main()
