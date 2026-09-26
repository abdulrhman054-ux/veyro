"""End-to-end: a real (fake-model) watchlist scan with a budget runs every session to a verdict.
Guards against the scan loop passing anything but the budget dict into sessions."""
from __future__ import annotations

import asyncio
import os
import tempfile
import time

os.environ.setdefault("VEYRO_DATA_DIR", tempfile.mkdtemp(prefix="veyro-scan-"))
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-FAKE-not-a-real-key-000")

from tests import fake_llm  # noqa: E402
from veyro import db, market, runner  # noqa: E402


def test_watchlist_with_budget_completes(monkeypatch):
    fake_llm.install(monkeypatch)
    monkeypatch.setattr(market, "history", lambda *a, **k: None)
    monkeypatch.setattr(market, "last_price", lambda t: {"price": 100.0, "currency": "USD", "as_of": "x", "source": "stub"})
    db.conn()
    loop = asyncio.new_event_loop()
    try:
        scan_id = runner.start_scan(loop, "watchlist", ["AAPL", "MSFT"], None, None, "en", False,
                                    budget={"amount": 1000.0, "currency": "USD"})
        t0 = time.time()
        while not runner.SCAN_BUSES[scan_id].closed and time.time() - t0 < 240:
            time.sleep(0.5)
        sessions = db.get_scan(scan_id)["sessions"]
        assert [s["status"] for s in sessions] == ["done", "done"], [(s["ticker"], s["status"]) for s in sessions]
        assert all((s["config"] or {}).get("budget") == {"amount": 1000.0, "currency": "USD"} for s in sessions)
    finally:
        loop.close()
