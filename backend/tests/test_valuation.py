"""Free pre-screen 'value' mode: P/E against the sector in the same market, dividend yield from real payments."""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ.setdefault("VEYRO_DATA_DIR", tempfile.mkdtemp(prefix="veyro-test-"))

import pytest  # noqa: E402

from veyro import db, extras, market, valuation  # noqa: E402

TODAY = date(2026, 9, 25)


def inf(sector, pe=None, eps=1.0, qt="EQUITY", cur="USD", fcur=None):
    return {"quote_type": qt, "sector": sector, "currency": cur, "financial_currency": fcur or cur, "trailing_pe": pe, "trailing_eps": eps}


@pytest.fixture
def world(monkeypatch):
    db.conn()
    with db.tx() as c:
        c.execute("DELETE FROM valuation_cache")
    facts = {}
    divs = {}
    monkeypatch.setattr(valuation, "_fetch", lambda s: facts.get(s, {"error": "unavailable"}))
    monkeypatch.setattr(market, "dividends_or_none", lambda s: divs.get(s, []))
    monkeypatch.setattr(valuation, "reference_pool", lambda m: [])     # each test sets its own peers via the candidates
    return facts, divs


def run(tickers, closes):
    vols = {t: 0.0 for t in tickers}
    return valuation.score(tickers, {t: [closes[t]] for t in tickers}, vols, TODAY)


def test_cheaper_than_its_sector_ranks_higher(world):
    facts, _ = world
    facts.update({"A": inf("Technology", 15), "B": inf("Technology", 30), "C": inf("Technology", 20)})
    r = run(["A", "B", "C"], {"A": 100, "B": 100, "C": 100})
    assert r["A"]["pe_vs"] == "sector" and r["A"]["peer_pe"] == 20 and r["A"]["peers"] == 3
    assert r["A"]["score"] > r["C"]["score"] > r["B"]["score"]
    assert r["C"]["rel_value"] == 0


def test_bank_and_tech_are_not_compared_with_each_other(world):
    # A bank at P/E 10 among banks at 10 is fairly priced, not "cheap" next to software at 30
    facts, _ = world
    facts.update({f"BK{i}": inf("Financial Services", 10) for i in range(3)})
    facts.update({f"SW{i}": inf("Technology", 30) for i in range(3)})
    r = run(list(facts), {s: 100 for s in facts})
    assert r["BK0"]["rel_value"] == 0 and r["SW0"]["rel_value"] == 0


def test_saudi_is_compared_only_with_saudi(world, monkeypatch):
    facts, _ = world
    facts.update({"1.SR": inf("Energy", 10, cur="SAR"), "2.SR": inf("Energy", 12, cur="SAR"), "3.SR": inf("Energy", 14, cur="SAR"),
                  "X": inf("Energy", 40), "Y": inf("Energy", 40), "Z": inf("Energy", 40)})
    r = run(list(facts), {s: 100 for s in facts})
    assert r["1.SR"]["peer_pe"] == 12 and r["X"]["peer_pe"] == 40


def test_reference_pool_is_per_market():
    pool_sa, pool_us = valuation.reference_pool("sa"), valuation.reference_pool("us")
    assert pool_sa and all(s.endswith(".SR") for s in pool_sa)
    assert pool_us and not any(s.endswith(".SR") or s.endswith("-USD") for s in pool_us)


def test_too_few_sector_peers_uses_the_market_median(world):
    facts, _ = world
    facts.update({"A": inf("Utilities", 10), "B": inf("Technology", 20), "C": inf("Healthcare", 30)})
    r = run(["A", "B", "C"], {"A": 100, "B": 100, "C": 100})
    assert r["A"]["pe_vs"] == "market" and r["A"]["peer_pe"] == 20


def test_loss_making_and_missing_data_go_last_with_reasons(world):
    facts, _ = world
    facts.update({"A": inf("Technology", 15), "B": inf("Technology", 30), "C": inf("Technology", 20),
                  "L": inf("Technology", None, eps=-2.0), "F": inf(None, qt="ETF")})
    rows = extras.prescreen(["L", "A", "N", "F", "B", "C"], "value")
    order = [r["ticker"] for r in rows]
    assert order[:3] == ["A", "C", "B"]
    why = {r["ticker"]: r["value_note"] for r in rows}
    assert why["L"] == "loss_making" and why["N"] == "no_data" and why["F"] == "not_equity"
    assert all(r["score"] is None for r in rows[3:])


def test_prescreen_value_uses_history_closes(world, monkeypatch):
    facts, _ = world
    facts.update({"A": inf("Technology", None, eps=5.0), "B": inf("Technology", 20), "C": inf("Technology", 20)})
    monkeypatch.setattr(market, "history", lambda t, period="3mo": {"closes": [100.0] * 60})
    rows = {r["ticker"]: r for r in extras.prescreen(["A", "B", "C"], "value")}
    assert rows["A"]["pe"] == 20.0                      # no Yahoo P/E: price 100 / EPS 5 from the latest close


def test_pe_from_eps_only_in_the_same_currency():
    assert valuation.pe_of(inf("Energy", None, eps=2.0, cur="SAR"), 50.0) == (25.0, None)
    assert valuation.pe_of(inf("Energy", None, eps=2.0, cur="USD", fcur="TWD"), 50.0) == (None, "no_pe")
    assert valuation.pe_of(inf("Energy", 5000.0), 50.0) == (None, "no_pe")
    assert valuation.pe_of({"error": "unavailable"}, 50.0) == (None, "no_data")


def test_dividend_yield_counts_the_last_12_months_only(world):
    facts, divs = world
    divs["A"] = [("2025-06-01", 9.0), ("2025-12-01", 1.0), ("2026-06-01", 1.5)]   # the 2025-06 payment is too old
    y, high = valuation.trailing_yield("A", 50.0, TODAY)
    assert y == pytest.approx(2.5 / 50) and not high
    divs["S"] = [("2026-03-01", 12.0)]                                          # a one-off: 24%
    y, high = valuation.trailing_yield("S", 50.0, TODAY)
    assert high and y == pytest.approx(0.24)


def test_unusual_yield_is_capped_in_the_score(world):
    facts, divs = world
    facts.update({"A": inf("Energy", 20), "B": inf("Energy", 20), "C": inf("Energy", 20)})
    divs.update({"A": [("2026-03-01", 30.0)], "B": [("2026-03-01", 10.0)]})       # 30% (flagged) vs 10%
    r = run(["A", "B", "C"], {"A": 100, "B": 100, "C": 100})
    assert r["A"]["yield_unusual"] and r["A"]["score"] == r["B"]["score"]           # both counted at the 10% cap


def test_failed_dividend_fetch_is_not_zero_yield(world, monkeypatch):
    facts, _ = world
    facts.update({"A": inf("Energy", 20), "B": inf("Energy", 20), "C": inf("Energy", 20)})
    monkeypatch.setattr(market, "dividends_or_none", lambda s: None)
    r = run(["A", "B", "C"], {"A": 100, "B": 100, "C": 100})
    assert r["A"]["div_yield"] is None and r["A"]["value_note"] == "no_dividend_data" and r["A"]["score"] is not None


def test_facts_are_cached(world, monkeypatch):
    calls = []
    monkeypatch.setattr(valuation, "_fetch", lambda s: calls.append(s) or inf("Energy", 10))
    valuation.info("Q"); valuation.info("Q")
    assert calls == ["Q"]


def test_value_mode_reachable_from_the_scan_api(world, monkeypatch):
    from fastapi.testclient import TestClient
    from veyro import runner
    from veyro.app import app
    seen = {}
    monkeypatch.setattr(extras, "prescreen", lambda t, mode="momentum": seen.setdefault("mode", mode) and [{"ticker": x, "score": 1.0} for x in t])
    monkeypatch.setattr(runner, "start_scan", lambda *a, **k: "scan1")
    c = TestClient(app, base_url="http://127.0.0.1:8765")
    r = c.post("/api/scans", json={"kind": "watchlist", "tickers": ["AAPL", "MSFT", "KO"], "economy_top": 2, "prescreen_mode": "value", "demo": True})
    assert r.status_code == 200 and seen["mode"] == "value"
