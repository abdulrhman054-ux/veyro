"""Unit tests for budget plans, beginner picks, pricing, voice clean-up, search aliases and Stop."""
from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import time

os.environ.setdefault("VEYRO_DATA_DIR", tempfile.mkdtemp(prefix="veyro-test-"))

import pytest  # noqa: E402

from veyro import allocation, beginner, db, market, runner  # noqa: E402
from veyro.voice import clean_line  # noqa: E402

PRICES = {"AAPL": (200.0, "USD"), "MSFT": (400.0, "USD"), "KO": (70.0, "USD"), "PG": (165.0, "USD"),
          "2222.SR": (27.0, "SAR"), "2280.SR": (55.0, "SAR"), "7010.SR": (42.0, "SAR"), "1120.SR": (95.0, "SAR"),
          "1211.SR": (50.0, "SAR"), "USDSAR=X": (3.75, "SAR"), "SARUSD=X": (0.2667, "USD")}


@pytest.fixture(autouse=True)
def fake_prices(monkeypatch):
    monkeypatch.setattr(market, "last_price", lambda t: {"price": PRICES[t][0], "currency": PRICES[t][1]} if t in PRICES else None)
    db.conn()


def sess(i, t, rating, conv="unstated", status="done"):
    return {"id": i, "ticker": t, "status": status, "mode": "real", "rating": rating,
            "verdict": {"conviction": conv, "lang": "en", "reason": f"reason {t}"}}


def test_plan_weights_whole_shares_and_cash():
    p = allocation.plan([sess("a", "AAPL", "Buy", "high"), sess("b", "MSFT", "Overweight"), sess("c", "KO", "Sell")], 5000, "USD")
    rows = {r["ticker"]: r for r in p["rows"]}
    assert set(rows) == {"AAPL", "MSFT"}
    assert rows["AAPL"]["target"] > rows["MSFT"]["target"]          # Buy+high outweighs Overweight
    assert all(float(r["shares"]).is_integer() for r in p["rows"])
    spent = sum(r["cost"] for r in p["rows"])
    assert spent <= 5000 and abs(p["cash_left"] - (5000 - spent)) < 0.01
    assert [s["ticker"] for s in p["skipped"]] == ["KO"] and p["skipped"][0]["reason"]["en"] == "reason KO"


def test_plan_caps_concentration_at_40_percent():
    p = allocation.plan([sess("a", "AAPL", "Buy", "high"), sess("b", "MSFT", "Overweight", "low"), sess("c", "KO", "Overweight", "low")], 10000)
    assert max(r["target"] for r in p["rows"]) <= 4000.01


def test_plan_converts_currency():
    p = allocation.plan([sess("a", "2280.SR", "Buy")], 375, "USD")   # $375 = 1406 SAR; 40% cap = 562 SAR -> 10 shares at 55
    r = p["rows"][0]
    assert r["shares"] == 10 and r["price_currency"] == "SAR" and r["cost"] <= 375 * 0.4 + 0.01
    assert "few_picks" in p["notes"]


def test_plan_no_positive_calls_keeps_cash():
    p = allocation.plan([sess("a", "AAPL", "Hold")], 1000)
    assert p["rows"] == [] and p["cash_left"] == 1000 and "no_positive" in p["notes"]


def test_beginner_picks_are_affordable_and_spread():
    r = beginner.suggest(1000, "SAR", "sa", "cautious", 3)
    picks = r["picks"]
    assert len(picks) == 3
    assert all(p["price_in_budget"] <= 1000 for p in picks)
    assert len({p["sector"] for p in picks}) == 3


def test_beginner_small_budget_still_finds_something():
    picks = beginner.suggest(100, "USD", "us", "balanced", 3)["picks"]
    assert picks and all(p["price_in_budget"] <= 100 for p in picks)


def test_price_longest_prefix():
    assert runner.price_for("claude-opus-5-5") == (4.00, 20.00)
    assert runner.price_for("claude-opus-5") == (5.00, 25.00)
    assert runner.price_for("claude-fable-5-1") == (10.00, 50.00)
    assert runner.price_for("claude-sonnet-5-20260101") == (2.00, 10.00)
    assert runner.price_for("gpt-6-luna") is None


def test_clean_line_strips_markdown_and_quotes():
    assert clean_line('"**Breaking** news!"') == "Breaking news!"
    assert clean_line("- line: خبر *مهم*") == "خبر مهم"
    assert clean_line("3*4 and 2*5") == "3*4 and 2*5"


def test_search_arabic_alias(monkeypatch):
    monkeypatch.setattr(market.yf, "Search", None)   # no network: aliases only
    assert market.search("ارامكو")[0]["symbol"] == "2222.SR"
    assert market.search("إنفيديا")[0]["symbol"] == "NVDA"


def test_bus_ignores_events_after_end():
    loop = asyncio.new_event_loop()
    b = runner.Bus(loop)
    b.publish({"type": "end", "status": "done"})
    b.publish({"type": "agent_message"})
    assert [e["type"] for e in b.events] == ["end"]
    loop.close()


def test_cancellable_stream_stops_immediately():
    cancel = threading.Event()

    def slow():
        yield "a"
        time.sleep(5)
        yield "b"
    st = runner._cancellable(slow, {}, cancel)
    it = iter(st)
    assert next(it) == "a"
    threading.Timer(0.2, cancel.set).start()
    t0 = time.time()
    with pytest.raises(runner._Cancelled):
        next(it)
    assert time.time() - t0 < 1.5


def test_saudi_stocks_benchmark_against_tasi():
    assert runner.benchmark_for("2222.SR") == "^TASI.SR"
    assert runner.benchmark_for("AAPL") == "SPY"


def test_beginner_market_tips_follow_market():
    assert {t["market"] for t in beginner.market_tips("us", "ar")} == {"us"}
    assert {t["market"] for t in beginner.market_tips("both", "en")} == {"sa", "us"}
    assert set(beginner.market_status("sa")) == {"sa"}


def test_small_budget_leftover_buys_whole_shares(monkeypatch):
    px = {"KO": 68.0, "PG": 165.0, "NVDA": 130.0}
    monkeypatch.setattr(market, "last_price", lambda t: {"price": px[t], "currency": "USD"} if t in px else None)
    p = allocation.plan([sess(t, t, "Buy") for t in px], 300, "USD")
    got = {r["ticker"]: r["shares"] for r in p["rows"]}
    assert got["KO"] == 1 and got["PG"] == 1 and p["cash_left"] == 67.0


def test_live_hub_ticks_change_and_gold_per_gram():
    from veyro import live
    hub = live.LiveHub()
    hub.on_tick({"id": "AAPL", "price": 110.0, "previous_close": 100.0, "time": 1_700_000_000_000})
    q = hub.quotes["AAPL"]
    assert q["live"] and round(q["change_pct"], 6) == 10.0
    hub.on_tick({"id": "SAR=X", "price": 3.75, "previous_close": 3.75})
    hub.on_tick({"id": "GC=F", "price": 3110.34768, "previous_close": 3110.34768})
    assert round(hub.quotes["GOLD24_SAR_G"]["price"], 2) == 375.0          # 3110.35 $/oz * 3.75 / 31.1035 g
    assert round(hub.quotes["GOLD21_SAR_G"]["price"], 2) == 328.13


def test_paper_portfolio_return_and_alpha(monkeypatch):
    from veyro import extras
    px = {"AAPL": 100.0, "SPY": 500.0}
    monkeypatch.setattr(market, "last_price", lambda t: {"price": px[t], "currency": "USD"} if t in px else None)
    extras.paper_add("AAPL", 3, None, "Buy")
    px.update({"AAPL": 110.0, "SPY": 510.0})
    v = extras.paper_view()
    p = next(x for x in v["positions"] if x["ticker"] == "AAPL" and not x["closed_at"])
    assert round(p["ret"], 4) == 0.10 and round(p["bench_ret"], 4) == 0.02 and round(p["alpha"], 4) == 0.08
    v = extras.paper_close(p["id"])
    assert next(x for x in v["positions"] if x["id"] == p["id"])["exit_price"] == 110.0


def test_price_alert_fires_once():
    from veyro import assistant, extras
    assistant.init()
    extras.add_price_alert("GC=F", "above", 3000)
    extras.check_price("GC=F", 2990)
    assert all(a["triggered_at"] is None for a in extras.price_alerts() if a["symbol"] == "GC=F")
    extras.check_price("GC=F", 3001)
    extras.check_price("GC=F", 3010)
    fired = [a for a in assistant.alerts() if a["kind"] == "price" and a["ticker"] == "GC=F"]
    assert len(fired) == 1


def test_prescreen_ranks_uptrend_first(monkeypatch):
    from veyro import extras
    up = [100 + i for i in range(120)]
    down = [220 - i for i in range(120)]
    monkeypatch.setattr(market, "history", lambda t, p="3mo": {"closes": up if t == "UP" else down if t == "DN" else []})
    rows = extras.prescreen(["DN", "UP", "NONE"])
    assert [r["ticker"] for r in rows] == ["UP", "DN", "NONE"] and rows[-1]["score"] is None


def test_stooq_parsing_and_fallback(monkeypatch):
    from veyro import datasources
    monkeypatch.setattr(datasources, "_get", lambda url, timeout=10: "Symbol,Date,Time,Open,High,Low,Close,Prev\nAAPL.US,2026-09-25,22:00:00,1,2,0.5,210.5,208\n")
    monkeypatch.setattr(datasources, "current", lambda: "stooq")
    q = datasources.quote("AAPL")
    assert q["price"] == 210.5 and q["prev_close"] == 208 and q["source"] == "Stooq"
    assert datasources.quote("2222.SR") is None     # not covered -> caller falls back to Yahoo
    assert datasources.stooq_symbol("GC=F") == "xauusd"


def test_budget_cap_blocks_new_paid_sessions():
    from veyro import budget
    db.set_setting("monthly_cap_usd", 1.0)
    with db.tx() as c:
        c.execute("INSERT INTO sessions(id,ticker,trade_date,created_at,mode,lang,status,cost_usd) VALUES('cap1','AAPL','2026-09-01',?, 'real','en','done',1.25)",
                  (db.now(),))
    s = budget.spent()
    assert s["spent"] >= 1.25 and budget.blocked()
    db.set_setting("monthly_cap_usd", None)
    assert not budget.blocked()


def test_trust_scores_direction_against_index(monkeypatch):
    from datetime import date
    from veyro import assistant
    close = {"AAPL": 110.0, "MSFT": 105.0, "KO": 100.0, "SPY": 102.0}
    monkeypatch.setattr(market, "close_on_or_before", lambda t, d: close[t])
    base = {"price_at_verdict": 100.0, "spy_at_verdict": 100.0, "benchmark": "SPY", "provider": "anthropic", "quick_model": "q", "deep_model": "d", "cost_usd": 1.0}
    rows = [{**base, "ticker": "AAPL", "rating": "Buy", "created_at": "2026-09-01", "trade_date": "2026-09-01"},    # +10% vs +2%: right
            {**base, "ticker": "MSFT", "rating": "Sell", "created_at": "2026-09-02", "trade_date": "2026-09-02"},   # +5% vs +2%: wrong
            {**base, "ticker": "KO", "rating": "Hold", "created_at": "2026-08-03", "trade_date": "2026-08-03"}]
    t = assistant.trust(rows, date(2026, 9, 25))
    assert t["overall"]["n"] == 2 and t["overall"]["hits"] == 1 and t["overall"]["hit_rate"] == 0.5
    assert round(t["by_rating"]["Buy"]["avg_edge"], 4) == 0.08 and t["by_rating"]["Hold"]["n"] == 0
    assert [m["month"] for m in t["months"]] == ["2026-08", "2026-09"]


def test_saudi_benchmark_falls_back_to_ksa(monkeypatch):
    monkeypatch.setattr(market, "history", lambda t, p="3mo": {"closes": [1.0]} if t == "^TASI.SR" else {"closes": [1.0] * 60})
    assert runner.usable_benchmark("^TASI.SR") == "KSA"
    monkeypatch.setattr(market, "history", lambda t, p="3mo": {"closes": [1.0] * 60})
    assert runner.usable_benchmark("^TASI.SR") == "^TASI.SR"
    assert runner.usable_benchmark("SPY") == "SPY"


def test_yahoo_failure_falls_back_to_stooq(monkeypatch):
    from veyro import datasources
    monkeypatch.undo()   # use the real last_price with a failing Yahoo
    class Boom:
        def __getattr__(self, n):
            raise RuntimeError("yahoo down")
    monkeypatch.setattr(market, "yf", Boom())
    monkeypatch.setattr(datasources, "current", lambda: "yahoo")
    monkeypatch.setattr(datasources, "stooq_quote", lambda t: {"price": 99.0, "currency": "USD", "source": "Stooq", "as_of": "x"})
    market._cache.clear()
    assert market.last_price("MSFT")["source"] == "Stooq"
