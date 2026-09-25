"""Scratch UI-test server: verify_server + stubbed market data (Yahoo is blocked in this sandbox)."""
import os, sys, tempfile, time, math
ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[2])
os.environ["VEYRO_DATA_DIR"] = tempfile.mkdtemp(prefix="veyro-ui-")
os.environ["VEYRO_PORT"] = "8766"
os.environ["VEYRO_NO_SCHEDULER"] = "1"
os.environ["FAKE_RATING"] = os.environ.get("FAKE_RATING", "Buy")
sys.path.insert(0, ROOT + "/backend")
import runpy
from veyro import market
P = {"AAPL": 210.0, "MSFT": 420.0, "NVDA": 130.0, "KO": 68.0, "PG": 165.0, "SPY": 560.0, "2222.SR": 27.5, "2280.SR": 55.0,
     "7010.SR": 42.0, "1120.SR": 95.0, "1211.SR": 50.0, "JPM": 200.0, "9412.SR": 11.0, "SPYM": 70.0, "VT": 120.0, "USDSAR=X": 3.75, "SARUSD=X": 0.2667}
def last_price(t):
    if t not in P: return None
    return {"price": P[t], "currency": "SAR" if t.endswith(".SR") or t == "USDSAR=X" else "USD", "as_of": "2026-09-25T15:00:00+00:00", "source": "stub"}
def history(t, period="3mo"):
    base = P.get(t, 100.0)
    closes = [round(base * (1 + 0.03 * math.sin(i / 6)), 2) for i in range(60)]
    return {"ticker": t, "dates": [f"2026-07-{(i % 28) + 1:02d}" for i in range(60)], "closes": closes, "source": "stub"}
market.last_price = last_price
market.history = history
market.market_status = lambda: {"open": True, "status": "open", "source": "stub"}
market.search = lambda q, limit=8: [{"symbol": "2222.SR", "name": "Saudi Aramco", "exchange": "Tadawul", "type": "EQUITY", "source": "Veyro"}] if "ر" in q or "ar" in q.lower() else [{"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "type": "EQUITY", "source": "stub"}]
# optional Sharia screen: sample fundamentals (Yahoo is blocked here). stc is given 45% debt so it fails AAOIFI's 30%.
from veyro import sharia
def _co(ind, **kw):
    d = {"quote_type": "EQUITY", "industry": ind, "summary": "", "currency": "USD", "financial_currency": "USD", "fx": 1.0,
         "market_cap": 1000.0, "avg_market_cap_36m": 1000.0, "total_assets": 1000.0, "total_debt": 100.0, "cash_st": 100.0,
         "receivables": 50.0, "revenue": 400.0, "interest_income": 4.0, "bs_date": "2026-06-30", "fetched_at": "2026-09-25T00:00:00+00:00"}
    d.update(kw); return d
FUND = {"AAPL": _co("Consumer Electronics"), "MSFT": _co("Software - Infrastructure"), "NVDA": _co("Semiconductors"),
        "KO": _co("Beverages - Non-Alcoholic"), "PG": _co("Household & Personal Products"), "JPM": _co("Banks - Diversified"),
        "2280.SR": _co("Packaged Foods"), "1211.SR": _co("Other Industrial Metals & Mining"), "2222.SR": _co("Oil & Gas Integrated"),
        "7010.SR": _co("Telecom Services", total_debt=450.0), "1120.SR": _co("Banks - Regional"), "1180.SR": _co("Banks - Diversified")}
sharia.fetch_raw = lambda s: FUND.get(s) or {"error": "unavailable", "fetched_at": "2026-09-25T00:00:00+00:00"}
# pre-screen "value" mode: sample company facts and dividends (Yahoo is blocked here). NVDA is made loss-making.
from veyro import valuation
def _v(sector, pe, eps=1.0, cur="USD"):
    return {"quote_type": "EQUITY", "sector": sector, "currency": cur, "financial_currency": cur, "trailing_pe": pe, "trailing_eps": eps}
VAL = {"AAPL": _v("Technology", 30), "MSFT": _v("Technology", 35), "NVDA": _v("Technology", None, eps=-1.0), "GOOGL": _v("Communication Services", 22),
       "META": _v("Communication Services", 26), "KO": _v("Consumer Defensive", 24), "PG": _v("Consumer Defensive", 25), "WMT": _v("Consumer Defensive", 38),
       "PEP": _v("Consumer Defensive", 21), "JPM": _v("Financial Services", 12), "V": _v("Financial Services", 30), "AMZN": _v("Consumer Cyclical", 40),
       "JNJ": _v("Healthcare", 17), "INTC": _v("Technology", 60), "AMD": _v("Technology", 90),
       "2222.SR": _v("Energy", 16, cur="SAR"), "2280.SR": _v("Consumer Defensive", 22, cur="SAR"), "2050.SR": _v("Consumer Defensive", 30, cur="SAR"),
       "7010.SR": _v("Communication Services", 14, cur="SAR"), "7020.SR": _v("Communication Services", 18, cur="SAR"),
       "1120.SR": _v("Financial Services", 18, cur="SAR"), "1180.SR": _v("Financial Services", 11, cur="SAR"), "1150.SR": _v("Financial Services", 14, cur="SAR"),
       "1010.SR": _v("Financial Services", 10, cur="SAR"), "1211.SR": _v("Basic Materials", None, eps=-0.5, cur="SAR"), "2010.SR": _v("Basic Materials", 40, cur="SAR")}
valuation._fetch = lambda s: VAL.get(s) or {"error": "unavailable"}
DIVS = {"KO": [("2026-03-01", 0.51), ("2026-06-01", 0.51)], "2222.SR": [("2026-03-01", 0.4), ("2026-06-01", 0.4)],
        "7010.SR": [("2026-04-01", 1.0)]}
market.dividends_or_none = lambda s: DIVS.get(s, [])
market.dividends = lambda s: DIVS.get(s, [])
# slow the fake model a little so animations/stop can be observed
from tests import fake_llm
_orig = fake_llm.FakeChat._generate
def slow(self, *a, **k):
    time.sleep(float(os.environ.get("FAKE_DELAY", "0.6"))); return _orig(self, *a, **k)
fake_llm.FakeChat._generate = slow
# fake live feed (Yahoo is blocked here): random-walk ticks in the stream's own message shape
import random
from veyro import live
BASE = {"GC=F": 2650.0, "SI=F": 31.2, "PL=F": 980.0, "PA=F": 1010.0, "HG=F": 4.3, "SAR=X": 3.75, "^GSPC": 5600.0, "^IXIC": 17900.0, "^DJI": 41000.0, "^TASI.SR": 12100.0}
def fake_stream(self):
    px = {s: BASE.get(s, P.get(s, 50.0)) for s in self.symbols}
    self.stream_ok = True
    while True:
        for s in random.sample(sorted(self.symbols), k=min(6, len(self.symbols))):
            px.setdefault(s, 50.0)
            prev = BASE.get(s, P.get(s, 50.0))
            px[s] *= 1 + random.uniform(-0.0015, 0.0015)
            self.on_tick({"id": s, "price": px[s], "time": int(time.time()*1000), "previous_close": prev, "currency": "SAR" if s.endswith(".SR") or s == "SAR=X" else "USD",
                          "day_high": prev*1.01, "day_low": prev*0.99})
        time.sleep(0.4)
live.LiveHub._stream_loop = fake_stream
live.LiveHub._snapshot = lambda self, syms: None
sys.argv = ["verify_server.py"]
runpy.run_path(ROOT + "/backend/tests/verify_server.py", run_name="__main__")
