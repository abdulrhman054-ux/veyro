"""Run the framework's backtest through Veyro's API with the fake model (2 dates) and print the summary."""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["VEYRO_DATA_DIR"] = tempfile.mkdtemp(prefix="veyro-bt-")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-FAKE-not-a-real-key-000")
os.environ["FAKE_RATING"] = "Buy"
from tests import fake_llm  # noqa: E402
fake_llm.install()
from fastapi.testclient import TestClient  # noqa: E402
from veyro.app import app  # noqa: E402

with TestClient(app) as c:
    job = c.post("/api/backtest", json={"tickers": ["AAPL"], "start": "2026-08-03", "end": "2026-08-17", "every_n_days": 14}).json()
    print("started:", job["cells"], "cells", job["dates"])
    for _ in range(200):
        j = c.get(f"/api/backtest/{job['id']}").json()
        if j["status"] != "running":
            break
        time.sleep(3)
    print("status:", j["status"], "done:", j["done"], "summary:", j.get("summary"), "failures:", j.get("failures"))
    print("memory entries:", len(c.get("/api/framework/decisions").json()["entries"]))
