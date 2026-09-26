"""Measure the optional Sharia screen's data coverage per market with LIVE Yahoo data (run on a machine with internet).
Usage (from the repo root):  .venv/bin/python tools/sharia_coverage.py [aaoifi|sp|msci]
Prints, per market, how many stocks come out compliant / not compliant / unknown, and why the unknowns are unknown."""
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

os.environ.setdefault("VEYRO_DATA_DIR", tempfile.mkdtemp(prefix="veyro-cov-"))   # never touches your real data
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from veyro import beginner, market, sharia  # noqa: E402

method = sys.argv[1] if len(sys.argv) > 1 else "aaoifi"
universe = {"sa": [x[0] for x in beginner.UNIVERSE["sa"]], "us": [x[0] for x in beginner.UNIVERSE["us"]]}
for sym, _, _ in market.ALIASES:
    if "-USD" not in sym:
        universe["sa" if sym.endswith(".SR") else "us"].append(sym)
for m, syms in universe.items():
    syms = list(dict.fromkeys(syms))
    res = sharia.screen(syms, method)
    st = Counter(r["status"] for r in res.values())
    why = Counter(x["code"] + (":" + str(x.get("field") or x.get("value") or "")) for r in res.values() if r["status"] == "unknown" for x in r["reasons"])
    print(f"\n== {m.upper()} ({len(syms)} stocks, {method}): {dict(st)}")
    for k, n in why.most_common():
        print(f"   unknown because {k}: {n}")
    for s, r in sorted(res.items()):
        print(f"   {s:10} {r['status']:14} data {r['data_date'] or '-':10} {', '.join(x['code'] for x in r['reasons'])}")
