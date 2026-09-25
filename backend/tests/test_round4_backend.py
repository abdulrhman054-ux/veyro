"""Regression tests for the fourth review round's backend findings (docs/REVIEW.md, round 4). Each failed before its fix."""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("VEYRO_DATA_DIR", tempfile.mkdtemp(prefix="veyro-test-"))

import pytest  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from veyro import budget, db, runner  # noqa: E402


class _Gen:
    def __init__(self, msg): self.message = msg


class _Resp:
    def __init__(self, model, i, o):
        self.generations = [[_Gen(AIMessage(content="x", usage_metadata={"input_tokens": i, "output_tokens": o, "total_tokens": i + o},
                                           response_metadata={"model_name": model}))]]


@pytest.fixture()
def fresh():
    db.conn()
    for r in db.q("SELECT id FROM sessions"):
        db.update_session(r["id"], created_at="2000-01-01T00:00:00+00:00")   # earlier tests' sessions: not this month
    db.set_setting("spend_extra", [])
    yield


def _running(sid):
    p, q, d = runner.settings_models()
    db.create_session(sid, "AAPL", "2026-09-25", "real", p, q, d, "en", None)
    return runner.estimate(p, q, d)["high"]


def test_interrupted_run_keeps_its_spend_after_restart(fresh):
    # Found by review: the tracker's cost was written only when a run ended normally, so a run cut off by closing
    # the app (or the parent watchdog) counted $0 against the cap after mark_orphans on the next start.
    _running("int1")
    t = runner.UsageTracker("int1")
    t.on_llm_end(_Resp("claude-opus-5-5", 200_000, 20_000))
    cost = t.summary()["cost_usd"]
    assert cost and cost > 0
    db.mark_orphans()
    s = budget.spent()
    assert s["spent"] >= cost - 1e-6, s


def test_running_session_reserves_the_rest_of_its_estimate(fresh):
    # With usage written as it arrives, a running session must still hold its remaining estimate (not drop to 0).
    high = _running("run1")
    runner.UsageTracker("run1").on_llm_end(_Resp("claude-sonnet-5", 1000, 100))
    s = budget.spent()
    assert s["spent"] > 0
    assert s["spent"] + s["reserved"] >= high - 1e-6, s


def test_calls_finishing_after_stop_still_count(fresh):
    # Found by review: Stop wrote the cost at once, and a model step still in flight reported tokens afterwards
    # that never reached the database.
    _running("stop1")
    t = runner.UsageTracker("stop1")
    t.on_llm_end(_Resp("claude-sonnet-5", 10_000, 1_000))
    first = t.summary()["cost_usd"]
    db.update_session("stop1", status="cancelled", cost_usd=first)   # what Stop / run_session's finally recorded
    t.on_llm_end(_Resp("claude-opus-5-5", 50_000, 5_000))            # the in-flight graph step lands later
    s = db.get_session("stop1")
    assert s["cost_usd"] > first + 1e-6, s["cost_usd"]


def test_cap_counts_the_run_about_to_start(fresh):
    # Found by review: with a $2 cap and one run in progress ($1.66 reserved), a second start was allowed and the
    # month could reach $3.32. The start check now adds the new run's own high estimate.
    from veyro import app as app_mod
    high = _running("cap1")
    db.set_setting("monthly_cap_usd", round(high * 1.2, 2))
    try:
        r = app_mod._cap_reached()
        assert r is not None and b'"budget_cap"' in r.body
        db.update_session("cap1", status="done", cost_usd=0.01)          # the run finished cheaply: room again
        assert app_mod._cap_reached() is None
    finally:
        db.set_setting("monthly_cap_usd", None)


# ---- splits and bonus shares, dividends against a price index, a horizon ending today
from datetime import date  # noqa: E402

from veyro import assistant, calendars, extras, market  # noqa: E402


@pytest.fixture()
def offline(monkeypatch):
    monkeypatch.setitem(calendars._cals, "us", None)
    monkeypatch.setitem(calendars._cals, "sa", None)
    monkeypatch.setattr(market, "splits", lambda t: [], raising=False)
    monkeypatch.setattr(market, "dividends", lambda t: [])
    yield monkeypatch


def _row(**kw):
    r = {"ticker": "NVDA", "rating": "Buy", "trade_date": "2026-09-08", "finished_at": "2026-09-08T15:00:00+00:00",
         "created_at": "2026-09-08T14:00:00+00:00", "price_at_verdict": 400.0, "spy_at_verdict": 600.0, "benchmark": "SPY",
         "quick_model": "q", "deep_model": "d"}
    r.update(kw)
    return r


def test_trust_counts_a_split_after_the_call(offline):
    # Found by review: a Buy at $400 before a 4-for-1 split, with the stock then at $104 (= $416 before the split),
    # was scored as a 74% loss. Yahoo's closes are split-adjusted; the recorded verdict price is not.
    hist = {"NVDA": {"2026-09-08": 100.0, "2026-09-15": 104.0}, "SPY": {"2026-09-08": 600.0, "2026-09-15": 606.0}}
    offline.setattr(market, "close_on_or_before", lambda t, d: max((v for k, v in hist[t].items() if k <= d), default=None))
    offline.setattr(market, "splits", lambda t: [("2026-09-10", 4.0)] if t == "NVDA" else [], raising=False)
    h = assistant.trust([_row()], today=date(2026, 9, 25))["horizons"]["5"]
    assert h["n"] == 1 and h["hits"] == 1 and h["avg_edge"] == pytest.approx(0.03, abs=1e-6), h


def test_trust_waits_for_the_close_of_the_last_day(offline):
    # Found by review: a 5-session horizon ending today was scored at once, with the previous day's close.
    hist = {"AAPL": {"2026-09-18": 200.0, "2026-09-24": 190.0}, "SPY": {"2026-09-18": 600.0, "2026-09-24": 606.0}}
    offline.setattr(market, "close_on_or_before", lambda t, d: max((v for k, v in hist[t].items() if k <= d), default=None))
    row = _row(ticker="AAPL", trade_date="2026-09-18", finished_at="2026-09-18T15:00:00+00:00", created_at="2026-09-18T14:00:00+00:00",
               price_at_verdict=200.0)
    assert assistant.add_trading_days("2026-09-18", 5, "AAPL") == "2026-09-25"
    h = assistant.trust([row], today=date(2026, 9, 25))["horizons"]["5"]
    assert h["n"] == 0 and h["waiting"] == 1, h


def _paper(offline, px):
    offline.setattr(market, "last_price", lambda t: px.get(t))
    db.conn()
    with db.tx() as c:
        c.execute("DELETE FROM paper")


def test_paper_counts_bonus_shares(offline):
    # Found by review: 10 NVDA bought at $400, then a 4-for-1 split and a price of $101 showed −74.75%.
    px = {"NVDA": {"price": 400.0, "currency": "USD"}, "SPY": {"price": 600.0, "currency": "USD"}}
    _paper(offline, px)
    extras.paper_add("NVDA", 10, None, "Buy")
    with db.tx() as c:
        c.execute("UPDATE paper SET opened_at='2026-01-05T08:00:00+00:00'")
    offline.setattr(market, "splits", lambda t: [("2026-06-10", 4.0)] if t == "NVDA" else [], raising=False)
    px["NVDA"] = {"price": 101.0, "currency": "USD"}
    pos = extras.paper_view()["positions"][0]
    assert pos["ret"] == pytest.approx(0.01, abs=1e-6), pos["ret"]
    assert pos["shares_now"] == 40


def test_paper_lead_over_a_price_index_leaves_dividends_out(offline):
    # Found by review: Aramco and TASI both flat, three dividends paid -> the lead over TASI showed +4.9%.
    # ^TASI.SR is a price index (no dividends), so the stock's lead is measured on price.
    px = {"2222.SR": {"price": 27.0, "currency": "SAR"}, "^TASI.SR": {"price": 11000.0, "currency": "SAR"},
          "SARUSD=X": {"price": 0.2667, "currency": "USD"}}
    _paper(offline, px)
    extras.paper_add("2222.SR", 100, None, "Buy")
    with db.tx() as c:
        c.execute("UPDATE paper SET opened_at='2026-01-05T08:00:00+00:00'")
    offline.setattr(market, "dividends", lambda t: [("2026-03-10", 0.44), ("2026-05-20", 0.44), ("2026-08-15", 0.44)] if t == "2222.SR" else [])
    v = extras.paper_view()
    pos = v["positions"][0]
    if pos["bench"] != "^TASI.SR":
        pytest.skip(f"benchmark here is {pos['bench']}")
    assert pos["ret"] > 0.04                       # what the owner received still includes the dividends
    assert pos["alpha"] == pytest.approx(0.0, abs=1e-9), pos["alpha"]
    assert v["totals"][0].get("bench_price_only") is True


def test_us_early_close_shows_closed():
    # Found by review: the day after Thanksgiving 2026 the NYSE closes at 13:00; at 14:00 Veyro still said "open",
    # so a quote from the 13:00 close was labelled as a live price.
    from datetime import datetime
    from zoneinfo import ZoneInfo
    if calendars._cal("us") is None:
        pytest.skip("exchange_calendars not installed")
    ny = ZoneInfo("America/New_York")
    assert calendars.is_open("us", datetime(2026, 11, 27, 14, 0, tzinfo=ny))["open"] is False
    assert calendars.is_open("us", datetime(2026, 11, 27, 12, 0, tzinfo=ny))["open"] is True
    assert calendars.is_open("us", datetime(2026, 11, 30, 15, 30, tzinfo=ny))["open"] is True    # a normal Monday


def test_saudi_takaful_insurer_is_unknown_not_non_compliant():
    # Found by review: Saudi cooperative insurers (8010.SR Tawuniya) came out "not compliant: conventional finance"
    # and were dropped from plans with a definite label. Their Sharia boards decide; free data can't.
    from veyro import sharia
    raw = {"quote_type": "EQUITY", "industry": "Insurance—Diversified", "summary": "", "currency": "SAR", "financial_currency": "SAR",
           "fx": 1.0, "market_cap": 1000.0, "avg_market_cap_36m": 1000.0, "total_assets": 1000.0, "total_debt": 10.0, "cash_st": 100.0,
           "receivables": 50.0, "revenue": 400.0, "interest_income": 4.0, "bs_date": "2026-06-30", "fetched_at": "2026-09-25T00:00:00+00:00"}
    r = sharia.evaluate("8010.SR", raw, today=date(2026, 9, 25))
    assert r["status"] == "unknown" and any(x["code"] == "takaful" for x in r["reasons"]), r
    assert sharia.evaluate("AIG", dict(raw, currency="USD", financial_currency="USD"), today=date(2026, 9, 25))["status"] == "not_compliant"


def test_plan_says_fees_are_missing_for_the_market_without_them(monkeypatch):
    # Found by review: with only US fees entered, a US + Saudi plan charged nothing on the Saudi rows and no longer
    # said that fees weren't entered.
    from veyro import allocation
    px = {"AAPL": (210.0, "USD"), "MSFT": (420.0, "USD"), "2222.SR": (27.5, "SAR"), "USDSAR=X": (3.75, "SAR"), "SARUSD=X": (0.2667, "USD")}
    monkeypatch.setattr(market, "last_price", lambda t: {"price": px[t][0], "currency": px[t][1]} if t in px else None)
    monkeypatch.setattr(market, "history", lambda t, period="6mo": None)
    monkeypatch.setattr(market, "sector", lambda t: None)
    db.conn()
    allocation.save_fees("us", 0.001, 1.0, 0.0)
    try:
        s = lambda i, t: {"id": i, "ticker": t, "status": "done", "mode": "real", "rating": "Buy",
                          "verdict": {"conviction": "unstated", "lang": "en", "reason": "r"}}
        p = allocation.plan([s("a", "AAPL"), s("b", "MSFT"), s("c", "2222.SR")], 5000, "USD")
        assert "fees_not_set" in p["notes"] and p["fees_missing"] == ["sa"], (p["notes"], p.get("fees_missing"))
    finally:
        db.set_setting("broker_fees", None)


def test_scan_joining_a_running_analysis_neither_drops_nor_cancels_it(monkeypatch):
    # Found by review: when a scan's stock was already being analysed (same stock, date and models), the scan
    # followed that run but left it out of its results and plan, and stopping the scan cancelled the owner's run.
    import asyncio
    import threading
    import time as _t
    from veyro import budget as spend_cap
    db.conn()
    loop = asyncio.new_event_loop()
    p, q, d = runner.settings_models()
    db.create_session("own1", "AAPL", "2026-09-25", "real", p, q, d, "en", None)
    runner.BUSES["own1"] = runner.Bus(loop)
    runner.CANCEL["own1"] = threading.Event()
    monkeypatch.setattr(runner, "start_session", lambda *a, **k: "own1")      # the lock hands back the running session
    monkeypatch.setattr(spend_cap, "blocked", lambda *a, **k: False)
    try:
        sid = runner.start_scan(loop, "watchlist", ["AAPL"], None, None, "en", False)
        t0 = _t.time()
        while not any(e["type"] == "scan_session" for e in runner.SCAN_BUSES[sid].events) and _t.time() - t0 < 10:
            _t.sleep(0.05)
        runner.SCAN_CANCEL[sid].set()                                           # the owner stops the scan
        t0 = _t.time()
        while not runner.SCAN_BUSES[sid].closed and _t.time() - t0 < 10:
            _t.sleep(0.05)
        assert db.get_session("own1")["status"] == "running"                   # the other run keeps going
        assert "own1" in [s["id"] for s in db.get_scan(sid)["sessions"]]       # and counts as the scan's result
    finally:
        runner.CANCEL["own1"].set()
        loop.close()


def test_owner_price_matches_the_dated_model_name_in_replies():
    # Found by review: the owner's price was matched exactly, but providers reply with dated names, so the real
    # usage stayed unpriced and the cap couldn't see it.
    db.conn()
    db.set_setting("custom_prices", {"acme-large": [2.0, 8.0]})
    try:
        assert runner.price_for("acme-large") == (2.0, 8.0)
        assert runner.price_for("acme-large-2026-01-15") == (2.0, 8.0)
        assert runner.price_for("acme-largest") is None
    finally:
        db.set_setting("custom_prices", {})


def test_one_run_per_instrument_whatever_the_spelling(monkeypatch):
    # Found by review: BTCUSD and BTC-USD open the same framework checkpoint but got separate run keys.
    import asyncio
    import threading
    gate = threading.Event()
    monkeypatch.setattr(runner, "_guarded", lambda *a, **k: gate.wait(10))
    db.conn()
    loop = asyncio.new_event_loop()
    try:
        a = runner.start_session(loop, "BTCUSD", "en", False)
        b = runner.start_session(loop, "BTC-USD", "en", False)
        assert a == b
    finally:
        gate.set()
        loop.close()


def test_backtest_on_an_unpriced_model_is_counted_as_unpriced(monkeypatch):
    # Found by review: a backtest whose model has no known price was recorded as $0 instead of "unpriced".
    import threading
    from veyro import app as app_mod
    db.conn()
    db.set_setting("spend_extra", [])
    monkeypatch.setattr(app_mod, "llm_key", lambda p: ("k", "env"))
    monkeypatch.setattr(runner, "estimate", lambda *a, **k: {"known": False, "low": None, "high": None, "currency": "USD", "sessions": 1})
    with monkeypatch.context() as m:
        m.setattr(threading.Thread, "start", lambda self: None)             # don't actually run the framework
        job = app_mod.start_backtest(app_mod.BacktestIn(tickers=["AAPL"], start="2026-01-05", end="2026-01-06"))
    assert "id" in job, job
    s = budget.spent()
    assert s["unpriced_calls"] >= 1, s
