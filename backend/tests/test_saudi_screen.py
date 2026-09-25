"""Saudi market scan: Yahoo's screener with region 'sa', Tadawul symbols only, budget compared in riyals,
and an honest fallback to Veyro's list of large Saudi companies when Yahoo's screener doesn't answer."""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("VEYRO_DATA_DIR", tempfile.mkdtemp(prefix="veyro-test-"))

import pytest  # noqa: E402

from veyro import db, market  # noqa: E402
from veyro.lazy import yf  # noqa: E402

SA_QUOTES = [{"symbol": "2222.SR", "quoteType": "EQUITY", "regularMarketPrice": 27.5, "regularMarketChangePercent": 1.2, "currency": "SAR", "shortName": "Aramco"},
             {"symbol": "AAPL", "quoteType": "EQUITY", "regularMarketPrice": 210.0},          # not Saudi: dropped
             {"symbol": "9412.SR", "quoteType": "ETF", "regularMarketPrice": 11.0},           # not a company: dropped
             {"symbol": "4190.SR", "quoteType": "EQUITY", "regularMarketPrice": 140.0, "regularMarketChangePercent": 0.5, "currency": "SAR"}]


@pytest.fixture
def screened(monkeypatch):
    calls = {}

    def fake(query, **kw):
        calls["query"], calls["kw"] = query, kw
        return {"quotes": SA_QUOTES if not isinstance(query, str) else [{"symbol": "MSFT", "quoteType": "EQUITY", "regularMarketPrice": 420.0},
                                                                         {"symbol": "2222.SR", "quoteType": "EQUITY", "regularMarketPrice": 27.5}]}
    monkeypatch.setattr(yf._load(), "screen", fake)
    return calls


def test_saudi_screener_uses_region_sa_and_keeps_tadawul_stocks_only(screened):
    out = market.screen("sa_day_gainers", 5)
    assert [c["symbol"] for c in out] == ["2222.SR", "4190.SR"]
    assert all(c["currency"] == "SAR" for c in out) and out[0]["name"] == "Aramco"
    q = screened["query"].to_dict()
    assert {"operator": "EQ", "operands": ["region", "sa"]} in q["operands"]
    assert screened["kw"]["sortField"] == "percentchange" and screened["kw"]["sortAsc"] is False


def test_us_screener_unchanged(screened):
    out = market.screen("most_actives", 5)
    assert [c["symbol"] for c in out] == ["MSFT"] and screened["query"] == "most_actives"


def test_budget_is_compared_in_riyals_for_saudi_lists(screened, monkeypatch):
    from veyro import app as A
    monkeypatch.setattr(market, "last_price", lambda t: {"price": 3.75, "currency": "SAR"} if t == "USDSAR=X" else None)
    assert A._max_price({"amount": 30.0, "currency": "USD"}, "sa_day_gainers") == pytest.approx(112.5)   # $30 = SAR 112.5
    out = market.screen("sa_day_gainers", 5, A._max_price({"amount": 30.0, "currency": "USD"}, "sa_day_gainers"))
    assert [c["symbol"] for c in out] == ["2222.SR"]                                                     # 4190 at SAR 140 doesn't fit


def test_saudi_fallback_when_yahoo_screener_is_down(monkeypatch):
    def down(*a, **k):
        raise ConnectionError("blocked")
    monkeypatch.setattr(yf._load(), "screen", down)
    px = {"2222.SR": (27.5, 27.0), "1120.SR": (95.0, 96.0), "2280.SR": (55.0, 54.0)}
    monkeypatch.setattr(market, "last_price", lambda t: {"price": px[t][0], "prev_close": px[t][1], "currency": "SAR"} if t in px else None)
    up = market.screen("sa_day_gainers", 5)
    assert [c["symbol"] for c in up] == ["2280.SR", "2222.SR"] and "Veyro list" in up[0]["source"]
    down_ = market.screen("sa_day_losers", 5)
    assert [c["symbol"] for c in down_] == ["1120.SR"]
    with pytest.raises(market.MarketDataUnavailable):
        market.screen("sa_most_actives", 5)      # needs volume from the screener: says unavailable, never guesses


def test_screeners_listed_with_market():
    from fastapi.testclient import TestClient
    from veyro.app import app
    r = TestClient(app, base_url="http://127.0.0.1:8765").get("/api/market/screeners").json()["screeners"]
    assert r["sa_day_gainers"]["market"] == "sa" and "ar" in r["sa_low_pe"] and "market" not in r["most_actives"]
