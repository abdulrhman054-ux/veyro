"""Free screen without AI (screening.py): Altman Z'', Piotroski F-score, trend, verdict rules, track record."""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ.setdefault("VEYRO_DATA_DIR", tempfile.mkdtemp(prefix="veyro-test-"))

import pytest  # noqa: E402

from veyro import db, market, screening  # noqa: E402


def co(**over):
    """A healthy, improving company: two years of lines, newest first (all in the same currency unit)."""
    lines = {
        "total_assets": [1000.0, 950.0, 900.0], "current_assets": [500.0, 450.0], "current_liabilities": [250.0, 250.0],
        "total_liabilities": [400.0, 420.0], "retained_earnings": [300.0, 250.0], "equity": [600.0, 530.0],
        "long_term_debt": [100.0, 120.0], "shares": [100.0, 100.0], "revenue": [1200.0, 1050.0],
        "gross_profit": [480.0, 400.0], "ebit": [150.0, 120.0], "net_income": [100.0, 80.0], "cfo": [140.0, 110.0],
    }
    for k, v in over.items():
        lines[k] = v
    return {"quote_type": "EQUITY", "sector": "Consumer Defensive", "industry": "Packaged Foods", "years": ["2025-12-31", "2024-12-31"], "lines": lines}


def test_altman_z_double_prime_matches_the_formula():
    # X1 = (500-250)/1000 = 0.25, X2 = 300/1000 = 0.30, X3 = 150/1000 = 0.15, X4 = 600/400 = 1.5
    # Z'' = 6.56*0.25 + 3.26*0.30 + 6.72*0.15 + 1.05*1.5 = 1.64 + 0.978 + 1.008 + 1.575 = 5.201
    a = screening.altman(co())
    assert a["status"] == "safe" and a["z"] == pytest.approx(5.20, abs=0.01)


def test_altman_distress_and_grey_zones():
    bad = co(current_assets=[200.0], current_liabilities=[400.0], retained_earnings=[-300.0], ebit=[-20.0], equity=[100.0], total_liabilities=[900.0])
    assert screening.altman(bad)["status"] == "distress"          # Z'' well below 1.10
    # Z'' = 6.56*0.02 + 3.26*0.05 + 6.72*0.08 + 1.05*0.4286 = 0.131 + 0.163 + 0.538 + 0.450 = 1.28 (grey)
    grey = co(current_assets=[300.0], current_liabilities=[280.0], retained_earnings=[50.0], ebit=[80.0], equity=[300.0], total_liabilities=[700.0])
    z = screening.altman(grey)
    assert z["status"] == "grey" and 1.10 <= z["z"] <= 2.60, z


def test_altman_never_guesses_missing_lines_and_skips_financials():
    a = screening.altman(co(retained_earnings=[]))
    assert a["status"] == "unknown" and "x2" in a["missing"]
    bank = dict(co(), sector="Financial Services", industry="Banks - Regional")
    assert screening.altman(bank)["status"] == "not_applicable"


def test_piotroski_all_nine_on_an_improving_company():
    p = screening.piotroski(co())
    assert p["known"] == 9 and p["score"] == 9 and p["status"] == "good", p["tests"]


def test_piotroski_counts_each_test_and_only_what_can_be_checked():
    worse = co(net_income=[-50.0, 80.0], cfo=[-10.0, 110.0], long_term_debt=[200.0, 120.0], shares=[120.0, 100.0],
               current_assets=[300.0, 450.0], gross_profit=[300.0, 400.0], revenue=[900.0, 1050.0])
    p = screening.piotroski(worse)
    assert p["tests"]["roa_positive"] is False and p["tests"]["no_new_shares"] is False and p["tests"]["leverage_down"] is False
    assert p["status"] == "weak" and p["score"] <= 2 and p["loss_making"] is True
    few = screening.piotroski(co(cfo=[], shares=[], gross_profit=[], long_term_debt=[]))
    assert few["known"] < 7 and few["status"] in ("incomplete", "unknown")   # never "good" on partial data


def test_bank_quality_is_profitability_only():
    bank = dict(co(), sector="Financial Services", industry="Banks - Regional")
    p = screening.piotroski(bank)
    assert p["financial"] is True and set(p["tests"]) == {"roa_positive", "roa_not_falling"} and p["status"] == "good"


def test_trend_rsi_and_drawdown():
    up = [100 + i * 0.5 for i in range(250)]
    t = screening.trend(up)
    assert t["status"] == "up" and t["rsi"] == 100.0 and "stretched" in t["flags"] and t["max_drawdown"] == 0
    down = [200 - i * 0.5 for i in range(250)]
    d = screening.trend(down)
    assert d["status"] == "down" and d["max_drawdown"] == pytest.approx(1 - down[-1] / 200, abs=1e-4)
    assert screening.trend(up[:120])["status"] == "unknown"


def test_verdicts_follow_the_rules():
    up = [100 + i * 0.5 for i in range(250)]
    down = [200 - i * 0.5 for i in range(250)]
    assert screening.evaluate("AAA", co(), up)["verdict"] == "pass"
    bad = co(current_assets=[200.0], current_liabilities=[400.0], retained_earnings=[-300.0], ebit=[-20.0], equity=[100.0], total_liabilities=[900.0])
    r = screening.evaluate("BBB", bad, up)
    assert r["verdict"] == "exclude" and r["reasons"][0]["code"] == "distress"
    healthy_down = screening.evaluate("CCC", co(), down)
    assert healthy_down["verdict"] == "watch" and any(x["code"] == "downtrend" for x in healthy_down["reasons"])
    loser = co(net_income=[-50.0, 80.0])
    assert any(x["code"] == "loss_and_downtrend" for x in screening.evaluate("DDD", loser, down)["reasons"])
    assert screening.evaluate("EEE", {"error": "unavailable"}, up)["verdict"] == "insufficient"
    assert screening.evaluate("SPY", {"quote_type": "ETF"}, up)["verdict"] == "not_equity"


def test_screen_logs_once_and_track_scores_against_the_index(monkeypatch):
    db.conn()
    with db.tx() as c:
        c.execute("DELETE FROM screen_log")
    up = [100 + i * 0.5 for i in range(250)]
    monkeypatch.setattr(screening, "statements", lambda s: co())
    monkeypatch.setattr(market, "history", lambda s, period="1y": {"closes": up, "dates": []})
    monkeypatch.setattr(market, "last_price", lambda s: {"price": 500.0})
    monkeypatch.setattr(market, "splits", lambda s: [])
    from veyro import valuation
    monkeypatch.setattr(valuation, "score", lambda *a, **k: {})
    r = screening.screen(["AAA"])
    assert r["AAA"]["verdict"] == "pass"
    screening.screen(["AAA"])                                   # same verdict again within 5 days: logged once
    assert len(db.q("SELECT * FROM screen_log WHERE ticker='AAA'")) == 1
    with db.tx() as c:
        c.execute("UPDATE screen_log SET screened_on='2026-01-05', price=100, bench_price=500")
    # 20 sessions later the stock is at 110 (+10%) and the index at 525 (+5%): excess +5%
    monkeypatch.setattr(market, "close_on_or_before", lambda t, d: 110.0 if t == "AAA" else 525.0)
    t = screening.track(today=date(2026, 9, 25))["by_verdict"]["pass"]["horizons"]["20"]
    assert t["n"] == 1 and t["avg_excess"] == pytest.approx(0.05) and t["beat_index"] == 1.0


def test_economy_quality_mode_never_pays_for_excluded_stocks(monkeypatch):
    from veyro import extras
    res = {"AAA": {"verdict": "pass", "quality": {"score": 8}, "health": {"z": 4.0}},
           "BBB": {"verdict": "exclude", "quality": {"score": 1}, "health": {"z": 0.5}},
           "CCC": {"verdict": "watch", "quality": {"score": 5}, "health": {"z": 2.0}}}
    monkeypatch.setattr(screening, "screen", lambda syms, log_results=True: res)
    rows = extras.prescreen(["BBB", "CCC", "AAA"], "quality")
    assert [r["ticker"] for r in rows] == ["AAA", "CCC", "BBB"]
    assert [r["ticker"] for r in rows if r["score"] is not None] == ["AAA", "CCC"]   # what economy mode may pick


def test_api_validates_symbols():
    from fastapi.testclient import TestClient
    from veyro import app as app_mod
    c = TestClient(app_mod.app, base_url="http://127.0.0.1")
    assert c.post("/api/screen/free", json={"symbols": ["../etc"]}).status_code == 400
    assert c.post("/api/screen/free", json={"symbols": []}).status_code == 422
