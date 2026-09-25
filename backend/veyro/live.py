"""Live board: streaming quotes for the US and Saudi markets and metals.

Source: Yahoo Finance's streaming feed (the same `wss://streamer.finance.yahoo.com` yfinance uses), which pushes
a message for every price change. When the stream is quiet (market closed) or unreachable, a snapshot poll
fills in the last traded price. Every quote carries its own timestamp and whether it came from the stream,
so the screen never presents a stale price as live. Exchange delays are whatever Yahoo applies.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import yfinance as yf

log = logging.getLogger("veyro.live")
SOURCE = "Yahoo Finance"
TROY_OZ_G = 31.1034768

# (symbol, English, Arabic)
BOARDS: dict[str, list[tuple[str, str, str]]] = {
    "us": [("AAPL", "Apple", "أبل"), ("MSFT", "Microsoft", "مايكروسوفت"), ("NVDA", "NVIDIA", "إنفيديا"),
           ("AMZN", "Amazon", "أمازون"), ("GOOGL", "Alphabet", "ألفابت"), ("META", "Meta", "ميتا"),
           ("TSLA", "Tesla", "تسلا"), ("AVGO", "Broadcom", "برودكوم"), ("JPM", "JPMorgan", "جي بي مورغان"),
           ("V", "Visa", "فيزا"), ("KO", "Coca-Cola", "كوكاكولا"), ("WMT", "Walmart", "وولمارت")],
    "sa": [("2222.SR", "Saudi Aramco", "أرامكو"), ("1120.SR", "Al Rajhi Bank", "الراجحي"), ("2010.SR", "SABIC", "سابك"),
           ("7010.SR", "stc", "الاتصالات السعودية"), ("1180.SR", "Saudi National Bank", "الأهلي"), ("2280.SR", "Almarai", "المراعي"),
           ("1211.SR", "Ma'aden", "معادن"), ("2082.SR", "ACWA Power", "أكوا باور"), ("1150.SR", "Alinma Bank", "الإنماء"),
           ("4013.SR", "Dr. Sulaiman Al Habib", "سليمان الحبيب"), ("5110.SR", "Saudi Electricity", "الكهرباء"),
           ("1010.SR", "Riyad Bank", "بنك الرياض")],
}
INDICES = {"us": [("^GSPC", "S&P 500", "إس آند بي 500"), ("^IXIC", "Nasdaq", "ناسداك"), ("^DJI", "Dow Jones", "داو جونز")],
           "sa": [("^TASI.SR", "TASI", "تاسي")]}
METALS = [("GC=F", "Gold", "الذهب", "oz"), ("SI=F", "Silver", "الفضة", "oz"), ("PL=F", "Platinum", "البلاتين", "oz"),
          ("PA=F", "Palladium", "البلاديوم", "oz"), ("HG=F", "Copper", "النحاس", "lb")]
FX = "SAR=X"   # riyals per dollar, for gold per gram in SAR
# Derived tiles (computed from gold and the riyal rate, labelled as calculated).
GOLD_G = {"GOLD24_SAR_G": ("Gold 24K per gram", "ذهب عيار 24 للجرام", 24), "GOLD21_SAR_G": ("Gold 21K per gram", "ذهب عيار 21 للجرام", 21)}


def catalog() -> dict:
    return {
        "boards": {m: [{"symbol": s, "en": en, "ar": ar} for s, en, ar in rows] for m, rows in BOARDS.items()},
        "indices": {m: [{"symbol": s, "en": en, "ar": ar} for s, en, ar in rows] for m, rows in INDICES.items()},
        "metals": [{"symbol": s, "en": en, "ar": ar, "unit": u} for s, en, ar, u in METALS]
                  + [{"symbol": k, "en": en, "ar": ar, "unit": "g", "derived": True} for k, (en, ar, _) in GOLD_G.items()],
        "source": SOURCE,
    }


def base_symbols() -> set[str]:
    out = {s for rows in BOARDS.values() for s, *_ in rows} | {s for rows in INDICES.values() for s, *_ in rows}
    return out | {s for s, *_ in METALS} | {FX}


def _iso(ms: float | int | None) -> str:
    t = (ms / 1000) if ms else time.time()
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")


class LiveHub:
    """One upstream connection shared by every open Live screen."""

    STALE_STREAM_S = 90     # no stream tick for this long -> refresh from a snapshot
    POLL_EVERY_S = 20

    def __init__(self):
        self.lock = threading.Lock()
        self.quotes: dict[str, dict] = {}
        self.symbols: set[str] = set(base_symbols())
        self.clients: dict[asyncio.Queue, tuple[asyncio.AbstractEventLoop, set[str]]] = {}
        self.started = False
        self.stream_ok = False
        self._ws = None
        self._stop = threading.Event()

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        with self.lock:
            if self.started:
                return
            self.started = True
        threading.Thread(target=self._poll_loop, daemon=True, name="live-poll").start()
        threading.Thread(target=self._stream_loop, daemon=True, name="live-stream").start()

    def add_symbols(self, syms: set[str]) -> None:
        new = syms - self.symbols
        if not new:
            return
        with self.lock:
            self.symbols |= new
        self._send_subscribe()
        threading.Thread(target=self._snapshot, args=(sorted(new),), daemon=True).start()

    # ------------------------------------------------------------ clients
    def subscribe(self, loop: asyncio.AbstractEventLoop, want: set[str]) -> tuple[asyncio.Queue, list[dict]]:
        q: asyncio.Queue = asyncio.Queue()
        with self.lock:
            self.clients[q] = (loop, set(want))
            snap = [dict(v) for k, v in self.quotes.items() if k in want]
        return q, snap

    def update_want(self, q: asyncio.Queue, want: set[str]) -> list[dict]:
        with self.lock:
            if q in self.clients:
                self.clients[q] = (self.clients[q][0], set(want))
            return [dict(v) for k, v in self.quotes.items() if k in want]

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self.lock:
            self.clients.pop(q, None)

    def _publish(self, quotes: list[dict]) -> None:
        with self.lock:
            targets = list(self.clients.items())
        for q, (loop, want) in targets:
            mine = [x for x in quotes if x["symbol"] in want]
            if mine:
                try:
                    loop.call_soon_threadsafe(q.put_nowait, mine)
                except RuntimeError:
                    pass

    # ------------------------------------------------------------ updates
    def _merge(self, sym: str, fields: dict) -> dict:
        with self.lock:
            q = self.quotes.setdefault(sym, {"symbol": sym})
            q.update({k: v for k, v in fields.items() if v is not None})
            if q.get("price") is not None and q.get("prev_close"):
                q["change"] = q["price"] - q["prev_close"]
                q["change_pct"] = q["change"] / q["prev_close"] * 100
            return dict(q)

    def _derived(self) -> list[dict]:
        with self.lock:
            g, fx = self.quotes.get("GC=F"), self.quotes.get(FX)
        if not g or not fx or not g.get("price") or not fx.get("price"):
            return []
        out = []
        for key, (_, _, karat) in GOLD_G.items():
            f = fx["price"] / TROY_OZ_G * karat / 24
            prev = (g.get("prev_close") or 0) * (fx.get("prev_close") or fx["price"]) / TROY_OZ_G * karat / 24 or None
            out.append(self._merge(key, {"price": g["price"] * f, "prev_close": prev, "currency": "SAR",
                                         "time": max(g.get("time", ""), fx.get("time", "")), "live": bool(g.get("live")), "derived": True}))
        return out

    def on_tick(self, msg: dict) -> None:
        sym = msg.get("id")
        if not sym or msg.get("price") is None:
            return
        fields = {"price": float(msg["price"]), "time": _iso(int(msg["time"]) if msg.get("time") else None),
                  "day_high": msg.get("day_high"), "day_low": msg.get("day_low"), "volume": msg.get("day_volume"),
                  "currency": msg.get("currency"), "live": True, "ts": time.time(), "market_hours": msg.get("market_hours")}
        if msg.get("previous_close"):
            fields["prev_close"] = float(msg["previous_close"])
        elif msg.get("change") is not None and fields["price"]:
            fields["prev_close"] = fields["price"] - float(msg["change"])
        out = [self._merge(sym, fields)]
        if sym in ("GC=F", FX):
            out += self._derived()
        self._publish(out)

    # ------------------------------------------------------------ upstream: snapshot poll
    def _snapshot(self, syms: list[str]) -> None:
        def one(sym: str) -> dict | None:
            try:
                fi = yf.Ticker(sym).fast_info
                p, pc = fi["lastPrice"], fi["previousClose"]
                if p is None or p != p:
                    return None
                return self._merge(sym, {"price": float(p), "prev_close": float(pc) if pc and pc == pc else None,
                                         "currency": fi.get("currency"), "day_high": fi.get("dayHigh"), "day_low": fi.get("dayLow"),
                                         "time": _iso(None), "live": False, "ts": time.time()})
            except Exception as e:  # noqa: BLE001
                log.info("live snapshot failed for %s: %s", sym, type(e).__name__)
                return None
        with ThreadPoolExecutor(max_workers=8) as ex:
            got = [x for x in ex.map(one, syms) if x]
        got += self._derived()
        if got:
            self._publish(got)

    def _poll_loop(self) -> None:
        self._snapshot(sorted(self.symbols))
        while not self._stop.wait(self.POLL_EVERY_S):
            now = time.time()
            with self.lock:
                stale = [s for s in self.symbols if now - self.quotes.get(s, {}).get("ts", 0) > self.STALE_STREAM_S]
            if stale:
                self._snapshot(stale)

    # ------------------------------------------------------------ upstream: stream
    def _send_subscribe(self) -> None:
        ws = self._ws
        if ws is None:
            return
        try:
            with self.lock:
                syms = sorted(self.symbols)
            ws.send(json.dumps({"subscribe": syms}))
        except Exception:  # noqa: BLE001
            pass

    def _stream_loop(self) -> None:
        from websockets.sync.client import connect
        from yfinance.live import BaseWebSocket
        decoder = BaseWebSocket(verbose=False)
        backoff = 2
        while not self._stop.is_set():
            try:
                with connect("wss://streamer.finance.yahoo.com/?version=2", open_timeout=15) as ws:
                    self._ws = ws
                    self.stream_ok = True
                    backoff = 2
                    self._send_subscribe()
                    last_sub = time.time()
                    while not self._stop.is_set():
                        if time.time() - last_sub > 15:    # Yahoo drops subscriptions that aren't refreshed
                            self._send_subscribe()
                            last_sub = time.time()
                        try:
                            raw = ws.recv(timeout=5)
                        except TimeoutError:
                            continue
                        try:
                            msg = decoder._decode_message(json.loads(raw).get("message", ""))
                        except Exception:  # noqa: BLE001
                            continue
                        self.on_tick(msg)
            except Exception as e:  # noqa: BLE001
                log.info("live stream unavailable (%s); snapshots continue", type(e).__name__)
            self._ws = None
            self.stream_ok = False
            self._stop.wait(backoff)
            backoff = min(60, backoff * 2)


HUB = LiveHub()
