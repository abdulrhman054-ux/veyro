"""Execution safety tests. Uses the Mock broker only (no Alpaca keys, no live orders ever).

Run:  .venv\\Scripts\\python -m pytest backend/tests -q
"""
import ast
import os
import pathlib
import tempfile

import pytest

os.environ["VEYRO_DATA_DIR"] = tempfile.mkdtemp(prefix="veyro-exec-test-")
os.environ["VEYRO_BLOCK_LIVE"] = "1"          # hard guard: live broker can never be constructed in tests
os.environ["VEYRO_MOCK_CLOCK_OPEN"] = "1"      # mock broker behaves as if the market were open

import keyring  # noqa: E402
from keyring.backend import KeyringBackend  # noqa: E402


class MemKeyring(KeyringBackend):
    priority = 1
    store: dict = {}

    def get_password(self, s, u): return self.store.get((s, u))
    def set_password(self, s, u, p): self.store[(s, u)] = p
    def delete_password(self, s, u): self.store.pop((s, u), None)


keyring.set_keyring(MemKeyring())  # never touch the real Windows vault from tests

from veyro import db, market  # noqa: E402
from veyro.execution import service as S  # noqa: E402

PRICES = {"AAPL": 200.0, "MSFT": 400.0, "SPY": 500.0}


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    # fresh DB + deterministic prices (market.last_price is the real Yahoo quote in the app)
    db._conn = None
    os.environ["VEYRO_DATA_DIR"] = tempfile.mkdtemp(prefix="veyro-exec-test-")
    import importlib
    import veyro.config as cfg
    importlib.reload(cfg)
    db.DB_PATH = cfg.DB_PATH
    db.DATA_DIR = cfg.DATA_DIR
    db.conn()
    S.init()
    monkeypatch.setattr(market, "last_price", lambda t: {"price": PRICES[t], "currency": "USD", "as_of": "test", "source": "test"} if t in PRICES else None)
    yield


def to_paper():
    S.set_mode("paper")
    assert S.status()["broker"] == "mock"


def test_default_mode_is_off_and_blocks_orders():
    assert S.mode() == "off"
    with pytest.raises(S.ExecError) as e:
        S.propose(symbol="AAPL", side="buy", order_type="market", amount_usd=100)
    assert e.value.code == "mode_off"


def test_market_order_full_flow_and_audit():
    to_paper()
    t = S.propose(symbol="AAPL", side="buy", order_type="market", amount_usd=200)
    assert t["ok"] and t["token"] and t["est_cost"] == 200
    r = S.confirm(t["id"], t["token"])
    assert r["order"]["status"] == "filled"
    events = [a["event"] for a in reversed(S.audit_rows())]
    assert events[-4:] == ["proposed", "confirmed", "submitted", "filled"]
    row = S.audit_rows()[0]
    assert row["limits_json"] and row["mode"] == "paper" and row["broker"] == "mock"


def test_limit_order_open_then_cancel():
    to_paper()
    t = S.propose(symbol="AAPL", side="buy", order_type="limit", amount_usd=300, limit_price=150)
    assert t["ok"] and t["qty"] == 2
    o = S.confirm(t["id"], t["token"])["order"]
    assert o["status"] == "accepted"  # 150 < 200 last price: stays open
    S.cancel(o["id"])
    assert any(a["event"] == "cancelled" for a in S.audit_rows())


def test_token_required_single_use():
    to_paper()
    t = S.propose(symbol="AAPL", side="buy", order_type="market", amount_usd=50)
    with pytest.raises(S.ExecError) as e:
        S.confirm(t["id"], "wrong")
    assert e.value.code == "bad_token"
    S.confirm(t["id"], t["token"])
    with pytest.raises(S.ExecError) as e:
        S.confirm(t["id"], t["token"])
    assert e.value.code == "ticket_used"


def test_max_order_limit_rejected():
    to_paper()
    t = S.propose(symbol="AAPL", side="buy", order_type="market", amount_usd=600)  # default max 500
    assert not t["ok"] and t["token"] is None
    assert [c["id"] for c in t["checks"] if not c["ok"]] == ["max_order"]


def test_symbol_exposure_limit():
    to_paper()
    for _ in range(2):
        t = S.propose(symbol="MSFT", side="buy", order_type="market", amount_usd=450)
        S.confirm(t["id"], t["token"])
    t = S.propose(symbol="MSFT", side="buy", order_type="market", amount_usd=200)  # 900 + 200 > 1000
    assert "symbol_exposure" in [c["id"] for c in t["checks"] if not c["ok"]]


def test_orders_per_day_limit():
    to_paper()
    S.set_limits("paper", {**S.limits("paper"), "max_orders_per_day": 2})
    for _ in range(2):
        t = S.propose(symbol="AAPL", side="buy", order_type="market", amount_usd=10)
        S.confirm(t["id"], t["token"])
    t = S.propose(symbol="AAPL", side="buy", order_type="market", amount_usd=10)
    assert "orders_today" in [c["id"] for c in t["checks"] if not c["ok"]]


def test_daily_loss_limit_blocks_new_orders():
    to_paper()
    S.broker_for("paper").account()  # creates the mock account
    st = db.get_setting("mock_broker_state")
    st["last_equity"] = st["cash"] + 1000  # simulate a -$1000 day
    db.set_setting("mock_broker_state", st)
    t = S.propose(symbol="AAPL", side="buy", order_type="market", amount_usd=10)
    assert "daily_loss" in [c["id"] for c in t["checks"] if not c["ok"]]


def test_limits_rechecked_at_confirm():
    to_paper()
    t = S.propose(symbol="AAPL", side="buy", order_type="market", amount_usd=100)
    S.set_limits("paper", {**S.limits("paper"), "max_order_usd": 50})
    with pytest.raises(S.ExecError) as e:
        S.confirm(t["id"], t["token"])
    assert e.value.code == "limit_hit"


def test_no_short_selling():
    to_paper()
    t = S.propose(symbol="AAPL", side="sell", order_type="market", qty=1)
    assert "no_short" in [c["id"] for c in t["checks"] if not c["ok"]]


def test_refuses_disallowed_order_kinds():
    to_paper()
    for kw, code in [({"side": "short"}, "side_not_allowed"), ({"order_type": "stop"}, "type_not_allowed"),
                     ({"symbol": "BTC-USD"}, "bad_symbol"), ({"symbol": "AAPL240621C00200000"}, "bad_symbol")]:
        args = {"symbol": "AAPL", "side": "buy", "order_type": "market", "amount_usd": 10, **kw}
        with pytest.raises(S.ExecError) as e:
            S.propose(**args)
        assert e.value.code == code


def test_market_closed_refuses_market_orders(monkeypatch):
    monkeypatch.setenv("VEYRO_MOCK_CLOCK_OPEN", "0")
    monkeypatch.setattr(market, "market_status", lambda: {"open": False, "next_open": "2026-09-25T13:30:00+00:00", "next_close": None})
    to_paper()
    with pytest.raises(S.ExecError) as e:
        S.propose(symbol="AAPL", side="buy", order_type="market", amount_usd=10)
    assert e.value.code == "market_closed"
    t = S.propose(symbol="AAPL", side="buy", order_type="limit", amount_usd=400, limit_price=190)  # limit for next open is allowed
    assert t["ok"] and t["market_open"] is False


def test_live_requires_every_unlock_step():
    with pytest.raises(S.ExecError) as e:
        S.set_mode("live", S.LIVE_PHRASES["ar"])
    assert e.value.code == "no_live_keys"
    # keys present (validation skipped because VEYRO_BLOCK_LIVE=1 prevents contacting Alpaca live)
    S.save_keys("live", "AKTESTKEY1234", "x" * 32)
    with pytest.raises(S.ExecError) as e:
        S.set_mode("live", S.LIVE_PHRASES["ar"])
    assert e.value.code == "limits_not_set"
    S.set_limits("live", S.DEFAULT_LIMITS)
    with pytest.raises(S.ExecError) as e:
        S.set_mode("live", "yes")
    assert e.value.code == "phrase_mismatch"
    S.set_mode("live", S.LIVE_PHRASES["ar"])
    assert S.mode() == "live" and S.live_unlocked()
    # even when unlocked, the dev guard makes the live broker impossible to build here
    with pytest.raises(S.ExecError) as e:
        S.propose(symbol="AAPL", side="buy", order_type="market", amount_usd=10)
    assert e.value.code == "live_blocked_in_dev"
    S.set_mode("paper")
    assert not S.live_unlocked()
    S.set_mode("live", S.LIVE_PHRASES["en"])  # re-unlock needs the phrase again
    S.set_mode("off")


def test_kill_switch_cancels_open_orders_and_turns_off():
    to_paper()
    t = S.propose(symbol="AAPL", side="buy", order_type="limit", amount_usd=300, limit_price=100)
    S.confirm(t["id"], t["token"])
    assert len(S.broker_for("paper").orders("open")) == 1
    r = S.kill()
    assert r["cancelled"] == 1 and S.mode() == "off"
    assert S.audit_rows()[0]["event"] == "kill_switch"


def test_liquidate_requires_phrase():
    to_paper()
    t = S.propose(symbol="AAPL", side="buy", order_type="market", amount_usd=100)
    S.confirm(t["id"], t["token"])
    with pytest.raises(S.ExecError):
        S.liquidate("ok")
    r = S.liquidate(S.LIQUIDATE_PHRASES["en"])
    assert r["closed"] and not S.broker_for("paper").positions()


def test_csv_export_has_every_event():
    to_paper()
    t = S.propose(symbol="AAPL", side="buy", order_type="market", amount_usd=20)
    S.confirm(t["id"], t["token"])
    csv = S.audit_csv()
    for ev in ("mode_changed", "proposed", "confirmed", "submitted", "filled"):
        assert ev in csv


def test_submit_is_only_called_from_confirm():
    """Static check: no code path other than service.confirm() (and the liquidation helper inside the
    Mock broker, reached only via service.liquidate) calls a broker's submit/submit_order."""
    root = pathlib.Path(__file__).resolve().parents[1] / "veyro"
    callers = []
    for f in root.rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for call in [c for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)]:
                target = call.func.value
                if isinstance(target, ast.Name) and target.id == "pool":
                    continue  # concurrent.futures thread pool in the session runner, not a broker
                if call.func.attr in ("submit", "submit_order"):
                    callers.append(f"{f.name}:{fn.name}")
    assert sorted(set(callers)) == sorted({"service.py:confirm", "broker.py:close_all"}), callers


def test_keys_never_in_status_payload():
    S.save_keys("live", "AKTESTKEY1234", "s3cr3t-" + "y" * 30)
    txt = str(S.status())
    assert "s3cr3t" not in txt and "AKTESTKEY1234" not in txt
