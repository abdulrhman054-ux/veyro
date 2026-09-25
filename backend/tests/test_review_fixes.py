"""Regression tests for bugs found in the 2026-09 end-to-end review (docs/REVIEW.md). Each test failed before its fix."""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("VEYRO_DATA_DIR", tempfile.mkdtemp(prefix="veyro-test-"))

import pytest  # noqa: E402

from veyro import allocation, beginner, db, market  # noqa: E402

PRICES = {"AAPL": (210.0, "USD"), "MSFT": (420.0, "USD"), "NVDA": (130.0, "USD"), "KO": (68.0, "USD"), "PG": (165.0, "USD"),
          "2222.SR": (27.5, "SAR"), "2280.SR": (55.0, "SAR"), "7010.SR": (42.0, "SAR"), "1120.SR": (95.0, "SAR"),
          "1211.SR": (50.0, "SAR"), "USDSAR=X": (3.75, "SAR"), "SARUSD=X": (0.2667, "USD")}


@pytest.fixture(autouse=True)
def fake_prices(monkeypatch):
    monkeypatch.setattr(market, "last_price", lambda t: {"price": PRICES[t][0], "currency": PRICES[t][1]} if t in PRICES else None)
    db.conn()


def sess(i, t, rating, conv="unstated", status="done"):
    return {"id": i, "ticker": t, "status": status, "mode": "real", "rating": rating,
            "verdict": {"conviction": conv, "lang": "en", "reason": f"reason {t}"}}


def test_plan_leftover_fill_respects_40_percent_cap():
    # Reproduced in the UI: $2,000 over three Buys -> AAPL got 4 shares = $840 = 42% after the leftover top-up.
    p = allocation.plan([sess("a", "MSFT", "Buy"), sess("b", "NVDA", "Buy"), sess("c", "AAPL", "Buy")], 2000, "USD")
    for r in p["rows"]:
        assert r["cost"] <= 0.4 * 2000 + 0.01, (r["ticker"], r["cost"])


def test_plan_small_budget_exception_still_allows_one_share():
    # The documented exception: when a single whole share is above 40% of a small amount, one share is still allowed.
    p = allocation.plan([sess("a", "MSFT", "Buy"), sess("b", "KO", "Buy"), sess("c", "NVDA", "Buy")], 1000, "USD")
    rows = {r["ticker"]: r for r in p["rows"]}
    assert rows["MSFT"]["shares"] == 1       # $420 = 42% of $1,000, allowed as the single-share exception
    assert rows["KO"]["cost"] <= 400.01 and rows["NVDA"]["cost"] <= 400.01


def test_beginner_both_markets_suggests_from_both():
    # Reproduced in the UI: "both" markets with SAR 1,000 suggested three Saudi stocks and no US stock,
    # because Coca-Cola (food) was skipped as the same sector as Almarai.
    r = beginner.suggest(1000, "SAR", "both", "balanced", 3)
    syms = [p["symbol"] for p in r["picks"]]
    assert any(s.endswith(".SR") for s in syms) and any(not s.endswith(".SR") for s in syms), syms


# ---------------------------------------------------------------- DNS rebinding: only loopback Host names are served
def _client(host):
    from fastapi.testclient import TestClient
    from veyro.app import app
    return TestClient(app, base_url=f"http://{host}:8765")


def test_foreign_host_cannot_change_settings():
    # A page on attacker.example whose DNS was re-pointed at 127.0.0.1 sends Origin == Host, so the old
    # same-origin test passed and it could clear the spend cap.
    c = _client("attacker.example")
    r = c.put("/api/settings", json={"monthly_cap_usd": 0}, headers={"origin": "http://attacker.example:8765"})
    assert r.status_code == 403
    assert c.get("/api/settings").status_code == 403


def test_foreign_host_websocket_refused():
    from starlette.websockets import WebSocketDisconnect
    c = _client("attacker.example")
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/ws/sessions/none", headers={"origin": "http://attacker.example:8765", "host": "attacker.example:8765"}) as ws:
            ws.receive_json()
    with _client("127.0.0.1").websocket_connect("/ws/sessions/none", headers={"origin": "http://127.0.0.1:8765", "host": "127.0.0.1:8765"}) as ws:
        assert ws.receive_json()["code"] == "not_found"   # loopback is still served


def test_loopback_host_still_works():
    c = _client("127.0.0.1")
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/settings", headers={"host": "localhost:8765"}).status_code == 200
