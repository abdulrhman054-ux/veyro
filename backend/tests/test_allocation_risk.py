"""Leo's plan, risk rules: 40% per stock always, 50% per sector, inverse-volatility weights, correlation warning, fees."""
from __future__ import annotations

import math
import os
import tempfile

os.environ.setdefault("VEYRO_DATA_DIR", tempfile.mkdtemp(prefix="veyro-test-"))

import pytest  # noqa: E402

from veyro import allocation, db, market  # noqa: E402

PX = {"A": 10.0, "B": 10.0, "C": 10.0, "D": 10.0, "2280.SR": 10.0, "USDSAR=X": 3.75, "SARUSD=X": 0.2667}


def sess(i, t, rating="Buy", conv="medium"):
    return {"id": i, "ticker": t, "status": "done", "mode": "real", "rating": rating,
            "verdict": {"conviction": conv, "lang": "en", "reason": "r"}}


def series(daily_sigma, seed, n=130, common=None):
    """Deterministic closes whose daily returns have roughly the given size; `common` adds a shared factor."""
    closes, p = [], 100.0
    for i in range(n):
        r = daily_sigma * math.sin(seed * 1.7 + i * 0.9) + (common[i] if common else 0.0)
        p *= 1 + r
        closes.append(p)
    return {"dates": [f"2026-{3 + i // 28:02d}-{i % 28 + 1:02d}" for i in range(n)], "closes": closes}


@pytest.fixture(autouse=True)
def world(monkeypatch):
    db.conn()
    db.set_setting("broker_fees", None)
    db.set_setting("sharia", {"enabled": False})
    monkeypatch.setattr(market, "last_price", lambda t: {"price": PX[t], "currency": "SAR" if t.endswith(".SR") or t == "USDSAR=X" else "USD"} if t in PX else None)
    monkeypatch.setattr(market, "sector", lambda t: {"A": "tech", "B": "tech", "C": "food", "D": "energy"}.get(t))


def rows(p):
    return {r["ticker"]: r for r in p["rows"]}


def test_single_pick_is_capped_at_40pct_rest_in_cash():
    p = allocation.plan([sess("a", "A")], 1000, "USD")
    assert rows(p)["A"]["cost"] <= 400.01 and p["cash_left"] >= 599.99 and "few_picks" in p["notes"]


def test_two_picks_each_capped():
    p = allocation.plan([sess("a", "A"), sess("c", "C", "Overweight")], 1000, "USD")
    assert all(r["cost"] <= 400.01 for r in p["rows"]) and p["cash_left"] >= 199.99


def test_sector_cap_50pct():
    # A and B are both tech with heavy weights: together they may not pass 50%
    p = allocation.plan([sess("a", "A", conv="high"), sess("b", "B", conv="high"), sess("c", "C", "Overweight", "low"),
                         sess("d", "D", "Overweight", "low")], 1000, "USD")
    r = rows(p)
    assert r["A"]["cost"] + r["B"]["cost"] <= 500.01
    assert r["A"]["sector"] == "tech"


def test_inverse_volatility_gives_calmer_stock_more(monkeypatch):
    h = {"A": series(0.03, 1), "C": series(0.01, 2), "D": series(0.02, 3)}
    monkeypatch.setattr(market, "history", lambda t, period="3mo": h.get(t))
    p = allocation.plan([sess("a", "A"), sess("c", "C"), sess("d", "D")], 3000, "USD")
    r = rows(p)
    assert r["C"]["risk_adj"] > 1 > r["A"]["risk_adj"]
    assert r["C"]["target"] > r["A"]["target"]
    assert 0.5 <= r["A"]["risk_adj"] and r["C"]["risk_adj"] <= 2.0


def test_correlated_pair_is_flagged(monkeypatch):
    common = [0.02 * math.sin(i * 1.3) for i in range(130)]
    h = {"A": series(0.002, 1, common=common), "B": series(0.002, 5, common=common), "C": series(0.02, 9)}
    monkeypatch.setattr(market, "history", lambda t, period="3mo": h.get(t))
    p = allocation.plan([sess("a", "A"), sess("b", "B"), sess("c", "C")], 3000, "USD")
    pairs = {(x["a"], x["b"]) for x in p["correlated"]}
    assert ("A", "B") in pairs and not any("C" in pr for pr in pairs)


def test_fees_are_deducted_and_flagged_when_not_set():
    p = allocation.plan([sess("a", "A"), sess("c", "C"), sess("d", "D")], 1000, "USD")
    assert "fees_not_set" in p["notes"] and p["fees_total"] == 0
    allocation.save_fees("us", rate=0.01, minimum=1.0, vat=0.15)
    p2 = allocation.plan([sess("a", "A"), sess("c", "C"), sess("d", "D")], 1000, "USD")
    assert "fees_not_set" not in p2["notes"] and p2["fees_total"] > 0
    for r in p2["rows"]:
        assert r["cost"] == pytest.approx(r["shares"] * 10 + r["fee"], abs=0.02)
        assert r["fee"] >= 1.15 - 1e-9          # the minimum fee plus VAT
        assert r["cost"] <= 400.01
    assert sum(r["cost"] for r in p2["rows"]) + p2["cash_left"] == pytest.approx(1000, abs=0.05)


def test_fee_minimum_is_in_the_stocks_currency():
    allocation.save_fees("sa", rate=0.0, minimum=3.75, vat=0.0)   # SAR 3.75 = $1
    p = allocation.plan([sess("a", "2280.SR")], 1000, "USD")
    assert rows(p)["2280.SR"]["fee"] == pytest.approx(1.0, abs=0.01)


def test_bad_fee_input_refused():
    with pytest.raises(ValueError):
        allocation.save_fees("us", rate=0.5, minimum=0, vat=0)


def test_fees_api_saves_and_validates():
    from fastapi.testclient import TestClient
    from veyro.app import app
    c = TestClient(app, base_url="http://127.0.0.1:8765")
    r = c.put("/api/fees", json={"market": "sa", "rate": 0.00155, "minimum": 0, "vat": 0.15})
    assert r.status_code == 200 and r.json()["broker_fees"]["sa"] == {"rate": 0.00155, "min": 0.0, "vat": 0.15, "set": True}
    assert c.put("/api/fees", json={"market": "xx", "rate": 0}).status_code == 400
