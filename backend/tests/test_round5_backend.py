"""Regression tests for the review items first left for later (docs/REVIEW.md, round 5). Each failed before its fix."""
from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import time
from concurrent.futures import Future

os.environ.setdefault("VEYRO_DATA_DIR", tempfile.mkdtemp(prefix="veyro-test-"))

import pytest  # noqa: E402

from veyro import allocation, db, extras, market, runner  # noqa: E402


def test_closed_position_keeps_its_exchange_rate(monkeypatch):
    # Left for later in round 4: a closed Saudi position's US-dollar value moved with today's exchange rate.
    px = {"2222.SR": {"price": 27.0, "currency": "SAR"}, "AAPL": {"price": 200.0, "currency": "USD"},
          "^TASI.SR": {"price": 11000.0, "currency": "SAR"}, "SPY": {"price": 600.0, "currency": "USD"}}
    rate = {"v": 0.2667}
    monkeypatch.setattr(market, "last_price", lambda t: px.get(t))
    monkeypatch.setattr(market, "dividends", lambda t: [])
    monkeypatch.setattr(market, "splits", lambda t: [])
    monkeypatch.setattr(allocation, "fx", lambda a, b: 1.0 if a == b else rate["v"] if (a, b) == ("SAR", "USD") else 1 / rate["v"])
    db.conn()
    with db.tx() as c:
        c.execute("DELETE FROM paper")
    extras.paper_add("2222.SR", 100, None, "Buy")
    extras.paper_add("AAPL", 1, None, "Buy")
    sa = next(p for p in extras.paper_view()["positions"] if p["ticker"] == "2222.SR")
    extras.paper_close(sa["id"])
    before = extras.paper_view()["combined_usd"]["value"]
    rate["v"] = 0.30                                    # the riyal "moves" after the sale
    after = extras.paper_view()["combined_usd"]["value"]
    assert after == pytest.approx(before), (before, after)


def test_recorded_verdict_is_shown_when_stop_lands_while_it_returns():
    # Left for later in round 4: the verdict was recorded as "done", then Stop arrived before the verdict job had
    # returned its events; the screen dropped them and said "cancelled" while History showed the verdict.
    loop = asyncio.new_event_loop()
    bus, cancel = runner.Bus(loop), threading.Event()
    em = runner.Emitter(bus, cancel)
    f: Future = Future()
    em.put(f)
    time.sleep(0.3)
    em.verdict_in.set()          # recorded under the lock ...
    cancel.set()                 # ... then Stop, while the job is still returning
    time.sleep(0.5)
    f.set_result([{"type": "verdict", "rating": "Buy"}, {"type": "end", "status": "done"}])
    em.close()
    assert [e["type"] for e in bus.events] == ["verdict", "end"]
    loop.close()


def test_stop_during_start_up_keeps_the_run_key_busy(monkeypatch):
    # Found by review, left for later: a Stop during start-up (before the framework stream exists) freed the run
    # key at once, so a new run could open the same checkpoint while the old worker was still setting it up.
    gate = threading.Event()
    monkeypatch.setattr(runner, "run_session", lambda *a, **k: gate.wait(10))
    db.conn()
    loop = asyncio.new_event_loop()
    try:
        a = runner.start_session(loop, "QQQX", "en", False)
        runner.CANCEL[a].set()
        runner.BUSES[a].publish({"type": "end", "status": "cancelled"})   # what Stop does for the viewers
        with pytest.raises(runner.StillStopping):
            runner.start_session(loop, "QQQX", "en", False)
        gate.set()
        t0 = time.time()
        while a in runner.WORKERS and time.time() - t0 < 5:
            time.sleep(0.05)
        assert runner.start_session(loop, "QQQX", "en", False) != a
    finally:
        gate.set()
        loop.close()


def test_stream_stays_registered_until_its_checkpoint_is_closed():
    # Found by review, left for later: the stream left ACTIVE_STREAMS before its deferred cleanup (closing the
    # checkpoint) ran, so for that moment a new run could open the same checkpoint.
    cancel, gate, seen = threading.Event(), threading.Event(), []

    def make():
        gate.wait(5)
        yield ("updates", {})
    st = runner._cancellable(make, {}, cancel)
    runner._defer_cleanup(st, lambda: seen.append(id(cancel) in runner.ACTIVE_STREAMS))
    gate.set()
    st.t.join(5)
    assert seen == [True]
    assert id(cancel) not in runner.ACTIVE_STREAMS


def test_scan_skips_a_stock_whose_stopped_run_is_still_finishing(monkeypatch):
    # Found by review, left for later: waiting 2 minutes for a stopped run of the same stock, then failing (and
    # cancelling) the whole scan. Now that one stock is skipped and the scan goes on.
    from veyro import budget as spend_cap
    db.conn()
    loop = asyncio.new_event_loop()
    p, q, d = runner.settings_models()

    def fake_start(loop_, t, lang, demo, scan_id=None, budget=None):
        if t == "AAA":
            raise runner.StillStopping()
        sid = "skipb" + str(int(time.time() * 1000) % 100000)
        db.create_session(sid, t, "2026-09-25", "real", p, q, d, "en", scan_id)
        db.update_session(sid, status="done", rating="Hold")
        bus = runner.Bus(loop)
        bus.publish({"type": "end", "status": "done"})
        runner.BUSES[sid] = bus
        return sid
    monkeypatch.setattr(runner, "start_session", fake_start)
    monkeypatch.setattr(runner, "SKIP_WAIT_STEPS", 2, raising=False)
    monkeypatch.setattr(spend_cap, "blocked", lambda *a, **k: False)
    try:
        scan = runner.start_scan(loop, "watchlist", ["AAA", "BBB"], None, None, "en", False)
        t0 = time.time()
        while not runner.SCAN_BUSES[scan].closed and time.time() - t0 < 20:
            time.sleep(0.1)
        types = [(e["type"], e.get("index")) for e in runner.SCAN_BUSES[scan].events]
        assert ("scan_skipped", 0) in types and ("scan_session", 1) in types, types
        assert db.get_scan(scan)["status"] == "done"
    finally:
        loop.close()


def test_resumed_run_reuses_lines_already_voiced():
    # Found by review, left for later: resuming a stopped run voiced its finished steps again with new model calls.
    db.conn()
    p, q, d = runner.settings_models()
    db.create_session("old1", "MSFT", "2026-09-20", "real", p, q, d, "ar", None)
    db.update_session("old1", status="cancelled")
    db.add_turn("old1", 1, "Ollie", "Market Analyst", "RSI 55, trend up", "أولي: الترند صاعد", None)
    db.add_turn("old1", 2, "Bolt", "Bull Researcher", "Bull Analyst: point one", "بولت: نقطة أولى", None)
    db.add_turn("old1", 3, "Bolt", "Bull Researcher", "Bull Analyst: point two", "بولت: نقطة ثانية", None)
    db.create_session("new1", "MSFT", "2026-09-20", "real", p, q, d, "ar", None)
    got = runner.prior_lines("new1", "MSFT", "2026-09-20", "Market Analyst", "RSI 55, trend up", "ar")
    assert [r["line"] for r in got] == ["أولي: الترند صاعد"]
    hist = "Bull Analyst: point one\nBull Analyst: point two"          # the debate replays as its whole history
    assert [r["line"] for r in runner.prior_lines("new1", "MSFT", "2026-09-20", "Bull Researcher", hist, "ar")] == ["بولت: نقطة أولى", "بولت: نقطة ثانية"]
    assert runner.prior_lines("new1", "MSFT", "2026-09-20", "Market Analyst", "a different report", "ar") is None
    assert runner.prior_lines("new1", "MSFT", "2026-09-20", "Market Analyst", "RSI 55, trend up", "en") is None   # no English line
