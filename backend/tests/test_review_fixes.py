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


# ---------------------------------------------------------------- monthly spend cap
class _Gen:
    def __init__(self, model, i, o):
        from types import SimpleNamespace
        self.message = SimpleNamespace(usage_metadata={"input_tokens": i, "output_tokens": o}, response_metadata={"model_name": model})


def _spend(model, i, o):
    from types import SimpleNamespace
    return SimpleNamespace(generations=[[_Gen(model, i, o)]])


def _fresh_month(monkeypatch):
    from veyro import budget
    with db.tx() as c:
        c.execute("DELETE FROM sessions")
    db.set_setting("monthly_cap_usd", "1")
    monkeypatch.setattr(budget, "month_key", lambda: db.now()[:7])
    return budget


def test_cancelled_session_cost_counts_toward_cap(monkeypatch):
    # A session stopped just before the verdict had spent real money but was recorded as $0.
    import asyncio
    from veyro import runner
    budget = _fresh_month(monkeypatch)

    def fake_real(sid, ticker, lang, em, cancel, trade_date, budget_):
        tr = runner.UsageTracker()
        runner.TRACKERS[sid] = tr
        tr.on_llm_end(_spend("claude-opus-5-5", 100_000, 100_000))   # $0.40 + $2.00
        raise runner._Cancelled()
    monkeypatch.setattr(runner, "_run_real", fake_real)
    runner.start_session(asyncio.new_event_loop(), "AAPL", "en", False, wait=True)
    assert budget.spent()["spent"] >= 2.4 - 1e-6
    assert budget.blocked()


def test_partially_priced_session_counts_known_part(monkeypatch):
    # One unpriced model made the whole session count as $0.
    from veyro import runner
    budget = _fresh_month(monkeypatch)
    tr = runner.UsageTracker()
    tr.on_llm_end(_spend("claude-opus-5-5", 100_000, 100_000))
    tr.on_llm_end(_spend("some-unknown-model", 1000, 1000))
    usage = tr.summary()
    db.create_session("p1", "AAPL", "2026-09-25", "real", "anthropic", "q", "d", "en")
    db.update_session("p1", status="done", usage_json=__import__("json").dumps(usage), cost_usd=usage["cost_usd"])
    assert usage["cost_usd"] is None
    assert budget.spent()["spent"] >= 2.4 - 1e-6


def test_running_sessions_reserve_their_estimate(monkeypatch):
    # The cap only looked at finished sessions, so several runs started together all passed the check.
    from veyro import runner
    budget = _fresh_month(monkeypatch)
    db.set_setting("monthly_cap_usd", "4")
    for i in range(3):
        db.create_session(f"r{i}", "AAPL", "2026-09-25", "real", "anthropic", "claude-sonnet-5", "claude-opus-5-5", "en")
    hi = runner.estimate("anthropic", "claude-sonnet-5", "claude-opus-5-5")["high"]
    assert 3 * hi >= 4 and budget.spent()["spent"] == 0
    assert budget.blocked()


def test_backtest_reserves_its_estimate(monkeypatch):
    from veyro import budget as B
    budget = _fresh_month(monkeypatch)
    db.set_setting("monthly_cap_usd", "100")
    B.reserve_extra(12.5, "backtest")
    assert budget.spent()["spent"] >= 12.5


# ---------------------------------------------------------------- Stop while a voice line / the verdict is being made
def test_stop_does_not_wait_for_a_voice_call():
    import asyncio
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from veyro import runner
    bus = runner.Bus(asyncio.new_event_loop())
    cancel = threading.Event()
    em = runner.Emitter(bus, cancel)
    pool = ThreadPoolExecutor(1)
    em.put(pool.submit(lambda: (time.sleep(3), [{"type": "agent_message"}])[1]))   # a slow voice call
    time.sleep(0.2)
    cancel.set()
    t0 = time.time()
    em.put({"type": "end", "status": "cancelled"})
    em.close()
    assert time.time() - t0 < 1.0
    assert [e["type"] for e in bus.events] == ["end"]
    pool.shutdown(wait=False)


def test_stop_after_verdict_recorded_still_shows_the_verdict():
    import asyncio
    import threading
    from concurrent.futures import Future
    from veyro import runner
    bus = runner.Bus(asyncio.new_event_loop())
    cancel = threading.Event()
    em = runner.Emitter(bus, cancel)
    f: Future = Future()
    f.set_result([{"type": "verdict", "rating": "Buy"}, {"type": "end", "status": "done"}])
    cancel.set()
    em.put(f)
    em.close()
    assert [e["type"] for e in bus.events] == ["verdict", "end"]


def test_scan_that_hits_an_error_still_ends(monkeypatch):
    # Any exception in the scan loop killed its thread silently: the scan stayed "running" and its socket waited forever.
    import asyncio
    import time
    from veyro import extras, runner
    monkeypatch.setattr(extras, "reusable", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("database is locked")))
    scan_id = runner.start_scan(asyncio.new_event_loop(), "watchlist", ["AAPL"], None, None, "en", False, reuse=True)
    bus = runner.SCAN_BUSES[scan_id]
    t0 = time.time()
    while not bus.closed and time.time() - t0 < 5:
        time.sleep(0.05)
    assert bus.closed and bus.events[-1]["type"] == "end"
    assert db.get_scan(scan_id)["status"] == "error"


# ---------------------------------------------------------------- removing a key must stop it being used
def test_removed_llm_key_is_no_longer_active(monkeypatch):
    import keyring
    from keyring.backend import KeyringBackend
    from veyro import runner
    from veyro.secrets_store import llm_key, set_secret

    class Mem(KeyringBackend):
        priority = 1
        store: dict = {}
        def get_password(self, s, u): return self.store.get((s, u))
        def set_password(self, s, u, p): self.store[(s, u)] = p
        def delete_password(self, s, u): self.store.pop((s, u), None)
    keyring.set_keyring(Mem())
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    set_secret("llm:anthropic", "sk-ant-api03-REMOVEME-000000000000001234")
    runner.activate_key("anthropic", llm_key("anthropic")[0])
    r = _client("127.0.0.1").delete("/api/keys/anthropic")
    assert r.status_code == 200
    assert llm_key("anthropic")[0] is None
    assert "ANTHROPIC_API_KEY" not in __import__("os").environ


def test_closing_a_paper_position_without_a_price_is_refused(monkeypatch):
    # With no quote, the position was closed at its entry price: a made-up 0% result.
    from veyro import extras
    with db.tx() as c:
        c.execute("DELETE FROM paper")
    extras.paper_add("AAPL", 2)
    pid = db.q1("SELECT id FROM paper")["id"]
    monkeypatch.setattr(market, "last_price", lambda t: None)
    with pytest.raises(ValueError):
        extras.paper_close(pid)
    assert db.q1("SELECT closed_at FROM paper WHERE id=?", (pid,))["closed_at"] is None


# ---------------------------------------------------------------- morning report follows the favourites' own markets
def test_morning_report_runs_on_tadawul_sunday_not_friday(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from veyro import assistant
    monkeypatch.setattr(assistant, "prefs", lambda: {"morning_enabled": True, "morning_time": "08:00"})
    monkeypatch.setattr(assistant, "favorites", lambda: ["2222.SR"])
    db.set_setting("assist:morning_last", None)
    riy = ZoneInfo("Asia/Riyadh")
    sunday = datetime(2026, 9, 27, 9, 0, tzinfo=riy)    # Tadawul open day; still Sunday in New York
    friday = datetime(2026, 9, 25, 9, 0, tzinfo=riy)    # Tadawul closed; a New York weekday
    assert assistant.morning_due(sunday)
    assert not assistant.morning_due(friday)
    monkeypatch.setattr(assistant, "favorites", lambda: ["AAPL"])
    assert not assistant.morning_due(sunday.astimezone(ZoneInfo("America/New_York")))



def test_beginner_guide_covers_settlement_limits_horizon_and_index_funds():
    sa = " ".join(t["tip"] for t in beginner.market_tips("sa", "en"))
    us = " ".join(t["tip"] for t in beginner.market_tips("us", "en"))
    assert "T+2" in sa and "10%" in sa and "T+1" in us and "7%, 13% or 20%" in us
    static = " ".join(en for _, en in beginner.STATIC_TIPS.values())
    assert "emergency fund" in static and "long run" in static and "index fund" in static


# ---------------------------------------------------------------- trust dashboard: don't score calls younger than the holding period
def _call(tk, rating, made, p0=100.0, b0=100.0, bench="SPY"):
    return {"ticker": tk, "rating": rating, "created_at": made + "T12:00:00+00:00", "finished_at": made + "T12:10:00+00:00",
            "trade_date": made, "price_at_verdict": p0, "spy_at_verdict": b0, "benchmark": bench}


def test_trust_does_not_score_calls_minutes_old(monkeypatch):
    # Seen in the UI: three Buy calls a few minutes old, stock and index both flat -> "0% hit rate".
    from datetime import date
    from veyro import assistant
    monkeypatch.setattr(market, "close_on_or_before", lambda t, d: 110.0 if t == "AAPL" else 101.0)
    today = date(2026, 9, 25)
    t = assistant.trust([_call("MSFT", "Buy", "2026-09-25"), _call("NVDA", "Buy", "2026-09-25"), _call("AAPL", "Buy", "2026-08-01")], today)
    assert t["overall"]["n"] == 1 and t["overall"]["hits"] == 1 and t["pending"] == 2


def test_trust_scores_at_a_fixed_horizon_not_until_now(monkeypatch):
    from datetime import date
    from veyro import assistant
    asked = []

    def close(t, d):
        asked.append((t, d))
        return {"AAPL": 105.0, "SPY": 101.0}[t]
    monkeypatch.setattr(market, "close_on_or_before", close)
    t = assistant.trust([_call("AAPL", "Buy", "2026-09-01")], date(2026, 9, 25))
    assert ("AAPL", "2026-09-08") in asked                        # 5 US trading days after Tue 1 Sep
    assert t["horizons"]["5"]["n"] == 1 and t["horizons"]["20"]["waiting"] == 1
    assert t["overall"]["avg_edge"] == pytest.approx(0.04)


def test_trust_counts_repeat_calls_once_and_shows_uncertainty(monkeypatch):
    from datetime import date
    from veyro import assistant
    monkeypatch.setattr(market, "close_on_or_before", lambda t, d: 105.0 if t == "AAPL" else 100.0)
    rows = [_call("AAPL", "Buy", "2026-08-03"), _call("AAPL", "Buy", "2026-08-04"), _call("AAPL", "Buy", "2026-08-20")]
    t = assistant.trust(rows, date(2026, 9, 25))
    assert t["overall"]["n"] == 2 and t["overall"]["distinct"] == 2
    lo, hi = assistant.wilson(6, 10)
    assert lo == pytest.approx(0.3127, abs=1e-3) and hi == pytest.approx(0.8318, abs=1e-3)
    assert t["min_sample"] == 30 and t["overall"]["enough"] is False


def test_trading_days_follow_the_market():
    from veyro import assistant
    assert assistant.add_trading_days("2026-09-24", 1, "2222.SR") == "2026-09-27"   # Thu -> Sun on Tadawul
    assert assistant.add_trading_days("2026-09-24", 1, "AAPL") == "2026-09-25"      # Thu -> Fri in the US


# ---------------------------------------------------------------- side calls: counted and capped; custom prices
class _FakeLLM:
    def __init__(self, cbs, model="claude-sonnet-5"):
        self.cbs, self.model = cbs, model
    def invoke(self, msgs):
        from types import SimpleNamespace
        for cb in self.cbs:
            cb.on_llm_end(_spend(self.model, 1_000_000, 100_000))    # $2 + $1 on Sonnet 5
        return SimpleNamespace(content="ok")


def _voice(monkeypatch, model="claude-sonnet-5", **kw):
    from veyro import voice
    captured = {}

    class Client:
        def __init__(self, provider, model, base_url=None, callbacks=None):
            captured["cbs"] = callbacks
        def get_llm(self):
            return _FakeLLM(captured["cbs"], model)
    monkeypatch.setattr(voice, "create_llm_client", lambda provider, model, base_url=None, **k: Client(provider, model, base_url, k.get("callbacks")))
    return voice.Voice("anthropic", model, **kw)


def test_side_calls_are_counted_in_the_month(monkeypatch):
    budget = _fresh_month(monkeypatch)
    db.set_setting("spend_extra", [])
    db.set_setting("monthly_cap_usd", "100")
    _voice(monkeypatch, what="translate")._ask("s", "u")
    sp = budget.spent()
    assert sp["other_usd"] == pytest.approx(3.0) and sp["other_calls"] == 1 and sp["spent"] >= 3.0


def test_side_calls_refused_at_cap_but_key_test_allowed(monkeypatch):
    from veyro.budget import CapReached
    budget = _fresh_month(monkeypatch)
    db.set_setting("spend_extra", [])
    db.set_setting("monthly_cap_usd", "1")
    budget.record_extra(1.5, "albie")
    with pytest.raises(CapReached):
        _voice(monkeypatch, what="ask")._ask("s", "u")
    assert _voice(monkeypatch, what="key_test", allow_over_cap=True)._ask("s", "u") == "ok"
    from veyro import runner
    assert runner.classify(CapReached()) == "budget_cap"


def test_custom_price_makes_an_unpriced_model_count(monkeypatch):
    from veyro import runner
    budget = _fresh_month(monkeypatch)
    db.set_setting("spend_extra", [])
    db.set_setting("monthly_cap_usd", "100")
    db.set_setting("custom_prices", None)
    _voice(monkeypatch, model="gpt-6-luna", what="translate")._ask("s", "u")
    assert budget.spent()["unpriced_calls"] == 1 and budget.spent()["other_usd"] == 0
    db.set_setting("custom_prices", {"gpt-6-luna": [1.0, 4.0]})
    assert runner.price_for("gpt-6-luna") == (1.0, 4.0)
    _voice(monkeypatch, model="gpt-6-luna", what="translate")._ask("s", "u")
    assert budget.spent()["other_usd"] == pytest.approx(1.4)
    db.set_setting("custom_prices", None)


def test_trust_rating_endpoint(monkeypatch):
    from veyro import assistant
    monkeypatch.setattr(assistant, "trust", lambda rows, today=None: {"horizon": 5, "min_sample": 30,
                        "by_rating": {"Buy": {"n": 12, "hits": 7, "hit_rate": 7 / 12, "ci_low": 0.32, "ci_high": 0.81, "enough": False}}})
    from veyro import app as A
    A._TRUST_CACHE.clear()
    r = _client("127.0.0.1").get("/api/trust/rating/Buy").json()
    assert r["n"] == 12 and r["enough"] is False and r["horizon"] == 5
    assert _client("127.0.0.1").get("/api/trust/rating/Sell").json()["n"] == 0
