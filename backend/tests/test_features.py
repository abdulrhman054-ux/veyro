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
    p = allocation.plan([sess("a", "2280.SR", "Buy")], 375, "USD")   # $375 = 1406 SAR -> 25 shares at 55 SAR
    r = p["rows"][0]
    assert r["shares"] == 25 and r["price_currency"] == "SAR" and r["cost"] <= 375


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
