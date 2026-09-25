"""Broker adapters. Alpaca (official alpaca-py SDK) for Paper/Live, and a clearly-labelled
Mock broker used only when Paper keys are missing (practice + development testing).

Only US equities, market/limit orders, cash only (no margin, no shorting, no options,
no crypto, no extended hours). These guards live in service.py and are re-checked here.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .. import db, market


class BrokerError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code, self.detail = code, detail


@dataclass
class OrderReq:
    symbol: str
    side: str            # 'buy' | 'sell'
    order_type: str      # 'market' | 'limit'
    qty: float | None
    notional: float | None
    limit_price: float | None
    client_order_id: str


def _f(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _order_dict(o: Any) -> dict:
    g = (lambda k: o.get(k)) if isinstance(o, dict) else (lambda k: getattr(o, k, None))
    val = lambda x: getattr(x, "value", x)  # noqa: E731
    ts = lambda x: x.isoformat() if hasattr(x, "isoformat") else x  # noqa: E731
    return {
        "id": str(g("id")), "client_order_id": g("client_order_id"), "symbol": g("symbol"),
        "side": val(g("side")), "type": val(g("type") or g("order_type")), "status": val(g("status")),
        "qty": _f(g("qty")), "notional": _f(g("notional")), "filled_qty": _f(g("filled_qty")) or 0.0,
        "filled_avg_price": _f(g("filled_avg_price")), "limit_price": _f(g("limit_price")),
        "time_in_force": val(g("time_in_force")),
        "submitted_at": ts(g("submitted_at")), "filled_at": ts(g("filled_at")), "canceled_at": ts(g("canceled_at")),
    }


class AlpacaBroker:
    label = "alpaca"

    def __init__(self, key_id: str, secret: str, paper: bool):
        from alpaca.trading.client import TradingClient
        self.paper = paper
        self.c = TradingClient(api_key=key_id, secret_key=secret, paper=paper)

    def _call(self, fn, *a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:  # noqa: BLE001
            code = getattr(e, "status_code", None)
            raise BrokerError("auth" if code in (401, 403) else "broker", f"{type(e).__name__}") from None

    def account(self) -> dict:
        a = self._call(self.c.get_account)
        return {"cash": _f(a.cash), "equity": _f(a.equity), "last_equity": _f(a.last_equity),
                "buying_power": _f(a.buying_power), "non_marginable_buying_power": _f(a.non_marginable_buying_power),
                "currency": a.currency, "trading_blocked": bool(a.trading_blocked), "status": getattr(a.status, "value", str(a.status))}

    def clock(self) -> dict:
        c = self._call(self.c.get_clock)
        return {"open": bool(c.is_open), "next_open": c.next_open.isoformat(), "next_close": c.next_close.isoformat(), "source": "Alpaca"}

    def asset(self, symbol: str) -> dict:
        a = self._call(self.c.get_asset, symbol)
        return {"symbol": a.symbol, "class": getattr(a.asset_class, "value", str(a.asset_class)), "tradable": bool(a.tradable),
                "fractionable": bool(a.fractionable), "name": a.name}

    def positions(self) -> list[dict]:
        out = []
        for p in self._call(self.c.get_all_positions):
            out.append({"symbol": p.symbol, "qty": _f(p.qty), "avg_entry_price": _f(p.avg_entry_price),
                        "current_price": _f(p.current_price), "market_value": _f(p.market_value),
                        "unrealized_pl": _f(p.unrealized_pl), "unrealized_plpc": _f(p.unrealized_plpc),
                        "side": getattr(p.side, "value", str(p.side))})
        return out

    def orders(self, status: str = "all", limit: int = 100) -> list[dict]:
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest
        r = GetOrdersRequest(status=QueryOrderStatus(status), limit=limit)
        return [_order_dict(o) for o in self._call(self.c.get_orders, filter=r)]

    def submit(self, req: OrderReq) -> dict:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
        side = OrderSide.BUY if req.side == "buy" else OrderSide.SELL
        common = dict(symbol=req.symbol, side=side, time_in_force=TimeInForce.DAY,
                      client_order_id=req.client_order_id, extended_hours=False)
        if req.order_type == "market":
            o = MarketOrderRequest(qty=req.qty, notional=req.notional, **common)
        else:
            o = LimitOrderRequest(qty=req.qty, limit_price=req.limit_price, **common)
        return _order_dict(self._call(self.c.submit_order, order_data=o))

    def cancel(self, order_id: str) -> None:
        self._call(self.c.cancel_order_by_id, order_id)

    def cancel_all(self) -> list[dict]:
        res = self._call(self.c.cancel_orders)
        return [{"id": str(getattr(r, "id", "")), "status": getattr(r, "status", None)} for r in (res or [])]

    def close_all(self) -> list[dict]:
        res = self._call(self.c.close_all_positions, cancel_orders=True)
        return [{"symbol": getattr(r, "symbol", None), "status": getattr(r, "status", None)} for r in (res or [])]


class MockBroker:
    """In-app practice broker. Everything it returns is labelled Mock. Prices come from real
    Yahoo quotes; fills, cash and positions are simulated. Never touches Alpaca."""
    label = "mock"
    _lock = threading.Lock()
    START_CASH = 100_000.0

    def __init__(self):
        with self._lock:
            st = db.get_setting("mock_broker_state")
            if not st:
                st = {"cash": self.START_CASH, "last_equity": self.START_CASH, "day": _today(), "positions": {}, "orders": []}
                db.set_setting("mock_broker_state", st)

    @staticmethod
    def _load() -> dict:
        return db.get_setting("mock_broker_state")

    @staticmethod
    def _save(st: dict) -> None:
        db.set_setting("mock_broker_state", st)

    def _px(self, symbol: str) -> float:
        p = market.last_price(symbol)
        if not p:
            raise BrokerError("no_price", symbol)
        return p["price"]

    def _roll_day(self, st: dict) -> None:
        if st.get("day") != _today():
            st["last_equity"] = self._equity(st, safe=True)
            st["day"] = _today()
            for o in st["orders"]:  # DAY orders expire
                if o["status"] in ("new", "accepted"):
                    o["status"], o["canceled_at"] = "expired", _now()

    def _equity(self, st: dict, safe: bool = False) -> float:
        total = st["cash"]
        for sym, p in st["positions"].items():
            try:
                total += p["qty"] * self._px(sym)
            except BrokerError:
                if not safe:
                    raise
                total += p["qty"] * p["avg"]
        return total

    def _match(self, st: dict) -> None:
        """Fill open orders whose conditions are met, using real last prices, only while the market is open."""
        if not self._clock_open():
            return
        for o in st["orders"]:
            if o["status"] not in ("new", "accepted"):
                continue
            px = self._px(o["symbol"])
            if o["type"] == "limit" and not ((o["side"] == "buy" and px <= o["limit_price"]) or (o["side"] == "sell" and px >= o["limit_price"])):
                continue
            fill_px = px if o["type"] == "market" else o["limit_price"]
            qty = o["qty"] if o["qty"] else round(o["notional"] / fill_px, 6)
            pos = st["positions"].setdefault(o["symbol"], {"qty": 0.0, "avg": 0.0})
            if o["side"] == "buy":
                cost = qty * fill_px
                if cost > st["cash"] + 1e-6:
                    o["status"] = "rejected"
                    continue
                pos["avg"] = (pos["avg"] * pos["qty"] + cost) / (pos["qty"] + qty)
                pos["qty"] += qty
                st["cash"] -= cost
            else:
                if qty > pos["qty"] + 1e-9:
                    o["status"] = "rejected"
                    continue
                pos["qty"] -= qty
                st["cash"] += qty * fill_px
                if pos["qty"] <= 1e-9:
                    st["positions"].pop(o["symbol"], None)
            o.update(status="filled", filled_qty=qty, filled_avg_price=fill_px, filled_at=_now())

    def _tick(self) -> dict:
        st = self._load()
        self._roll_day(st)
        self._match(st)
        self._save(st)
        return st

    def account(self) -> dict:
        with self._lock:
            st = self._tick()
            eq = self._equity(st, safe=True)
            return {"cash": round(st["cash"], 2), "equity": round(eq, 2), "last_equity": round(st["last_equity"], 2),
                    "buying_power": round(st["cash"], 2), "non_marginable_buying_power": round(st["cash"], 2),
                    "currency": "USD", "trading_blocked": False, "status": "MOCK"}

    @staticmethod
    def _dev_clock() -> bool:
        # Development/testing only: lets the Mock broker behave as if the market were open.
        # Has no effect on Alpaca brokers. Shown in the UI as "Mock clock (dev)".
        return os.environ.get("VEYRO_MOCK_CLOCK_OPEN") == "1"

    def _clock_open(self) -> bool:
        if self._dev_clock():
            return True
        mk = market.market_status()
        return bool(mk and mk.get("open"))

    def clock(self) -> dict:
        if self._dev_clock():
            return {"open": True, "next_open": None, "next_close": None, "source": "Mock clock (dev)"}
        mk = market.market_status()
        if not mk:
            raise BrokerError("no_clock")
        return {"open": bool(mk["open"]), "next_open": mk.get("next_open"), "next_close": mk.get("next_close"), "source": "Yahoo Finance"}

    def asset(self, symbol: str) -> dict:
        self._px(symbol)  # must have a real quote
        return {"symbol": symbol, "class": "us_equity", "tradable": True, "fractionable": True, "name": symbol}

    def positions(self) -> list[dict]:
        with self._lock:
            st = self._tick()
            out = []
            for sym, p in st["positions"].items():
                try:
                    cur = self._px(sym)
                except BrokerError:
                    cur = None
                mv = p["qty"] * cur if cur else None
                out.append({"symbol": sym, "qty": round(p["qty"], 6), "avg_entry_price": round(p["avg"], 4), "current_price": cur,
                            "market_value": round(mv, 2) if mv else None,
                            "unrealized_pl": round(mv - p["qty"] * p["avg"], 2) if mv else None,
                            "unrealized_plpc": (cur / p["avg"] - 1) if cur and p["avg"] else None, "side": "long"})
            return out

    def orders(self, status: str = "all", limit: int = 100) -> list[dict]:
        with self._lock:
            st = self._tick()
            os_ = st["orders"]
            if status == "open":
                os_ = [o for o in os_ if o["status"] in ("new", "accepted")]
            elif status == "closed":
                os_ = [o for o in os_ if o["status"] not in ("new", "accepted")]
            return [dict(o) for o in reversed(os_)][:limit]

    def submit(self, req: OrderReq) -> dict:
        with self._lock:
            st = self._load()
            self._roll_day(st)
            o = {"id": f"mock-{uuid.uuid4().hex[:10]}", "client_order_id": req.client_order_id, "symbol": req.symbol,
                 "side": req.side, "type": req.order_type, "status": "accepted", "qty": req.qty, "notional": req.notional,
                 "filled_qty": 0.0, "filled_avg_price": None, "limit_price": req.limit_price, "time_in_force": "day",
                 "submitted_at": _now(), "filled_at": None, "canceled_at": None, "mock": True}
            st["orders"].append(o)
            self._match(st)
            self._save(st)
            return dict(o)

    def cancel(self, order_id: str) -> None:
        with self._lock:
            st = self._load()
            for o in st["orders"]:
                if o["id"] == order_id and o["status"] in ("new", "accepted"):
                    o["status"], o["canceled_at"] = "canceled", _now()
                    self._save(st)
                    return
            raise BrokerError("not_open", order_id)

    def cancel_all(self) -> list[dict]:
        with self._lock:
            st = self._load()
            done = []
            for o in st["orders"]:
                if o["status"] in ("new", "accepted"):
                    o["status"], o["canceled_at"] = "canceled", _now()
                    done.append({"id": o["id"], "status": 200})
            self._save(st)
            return done

    def close_all(self) -> list[dict]:
        self.cancel_all()
        res = []
        for p in self.positions():
            o = self.submit(OrderReq(p["symbol"], "sell", "market", p["qty"], None, None, f"liq-{uuid.uuid4().hex[:8]}"))
            res.append({"symbol": p["symbol"], "status": o["status"]})
        return res


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today() -> str:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")


def dumps(o: Any) -> str:
    return json.dumps(o, default=str)
