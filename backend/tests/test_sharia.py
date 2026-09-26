"""Sharia screening rules (sharia.evaluate): each ratio, each activity rule and the edge cases, on sample data."""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ.setdefault("VEYRO_DATA_DIR", tempfile.mkdtemp(prefix="veyro-test-"))

import pytest  # noqa: E402

from veyro import db, sharia  # noqa: E402

TODAY = date(2026, 9, 25)


def co(**kw):
    """A clean, compliant-looking company; override fields per test."""
    base = {"quote_type": "EQUITY", "industry": "Consumer Electronics", "summary": "Makes phones.", "currency": "USD",
            "financial_currency": "USD", "fx": 1.0, "market_cap": 1000.0, "avg_market_cap_36m": 1000.0, "total_assets": 1000.0,
            "total_debt": 100.0, "cash_st": 100.0, "receivables": 50.0, "equity": 500.0, "revenue": 400.0,
            "interest_income": 4.0, "bs_date": "2026-06-30", "fetched_at": "2026-09-20T00:00:00+00:00"}
    base.update(kw)
    return base


def ev(raw, method="aaoifi"):
    return sharia.evaluate("TEST", raw, method, today=TODAY)


def codes(r):
    return [x["code"] for x in r["reasons"]]


def test_clean_company_is_compliant_under_every_method():
    for m in sharia.METHODS:
        r = ev(co(), m)
        assert r["status"] == "compliant", (m, r)
        assert r["data_date"] == "2026-06-30" and r["method"] == m


# ---- financial ratios
def test_aaoifi_debt_ratio_over_30pct_of_market_cap_fails():
    r = ev(co(total_debt=301.0))
    assert r["status"] == "not_compliant" and "debt_ratio" in codes(r)
    assert ev(co(total_debt=300.0))["status"] == "compliant"   # "not exceed 30%": exactly 30% passes


def test_aaoifi_cash_ratio_fails():
    r = ev(co(cash_st=350.0))
    assert r["status"] == "not_compliant" and "cash_ratio" in codes(r)


def test_income_ratio_over_5pct_fails_and_sets_purification():
    r = ev(co(interest_income=30.0))   # 7.5% of revenue
    assert r["status"] == "not_compliant" and "income_ratio" in codes(r)
    assert r["purification"] == pytest.approx(0.075)
    assert ev(co())["purification"] == pytest.approx(0.01)


def test_sp_uses_36_month_average_market_cap_and_receivables_limit():
    # debt 32% of today's cap but 40% of the 3-year average: S&P fails where AAOIFI's limit is different
    raw = co(total_debt=320.0, market_cap=1000.0, avg_market_cap_36m=800.0)
    assert ev(raw, "sp")["status"] == "not_compliant"
    assert "receivables_ratio" in codes(ev(co(receivables=490.0), "sp"))     # < 49% is strict
    assert ev(co(receivables=480.0), "sp")["status"] == "compliant"


def test_msci_uses_total_assets_and_receivables_plus_cash():
    # debt is 20% of market cap but 40% of total assets: only MSCI (asset-based) fails
    raw = co(total_debt=200.0, market_cap=1000.0, total_assets=500.0, cash_st=10.0, receivables=10.0)
    assert ev(raw, "aaoifi")["status"] == "compliant"
    r = ev(raw, "msci")
    assert r["status"] == "not_compliant" and "debt_ratio" in codes(r)
    r2 = ev(co(cash_st=200.0, receivables=150.0), "msci")   # (150+200)/1000 = 35% >= 33.33%
    assert "receivables_ratio" in codes(r2)


def test_currency_conversion_for_market_cap_denominator():
    # balance sheet in USD, shares trade in SAR (fx 3.75): 100 USD debt = 375 SAR vs a 1000 SAR market cap
    r = ev(co(currency="SAR", financial_currency="USD", fx=3.75))
    assert r["status"] == "not_compliant" and r["ratios"]["debt"] == pytest.approx(0.375)
    assert codes(ev(co(fx=None)))[0] == "currency_mismatch"


# ---- business activity
@pytest.mark.parametrize("industry,activity", [
    ("Banks - Diversified", "conventional_finance"), ("Banks—Regional", "conventional_finance"),
    ("Insurance - Life", "conventional_finance"), ("Beverages - Brewers", "alcohol"),
    ("Beverages - Wineries & Distilleries", "alcohol"), ("Resorts & Casinos", "gambling"), ("Gambling", "gambling"),
])
def test_core_activity_exclusions_apply_to_every_method(industry, activity):
    for m in sharia.METHODS:
        r = ev(co(industry=industry), m)
        assert r["status"] == "not_compliant" and r["reasons"][0] == {"code": "activity", "value": activity, "industry": industry}


def test_method_specific_exclusions():
    assert ev(co(industry="Tobacco"), "aaoifi")["status"] == "compliant"   # not in AAOIFI's core list here
    assert ev(co(industry="Tobacco"), "sp")["status"] == "not_compliant"
    assert ev(co(industry="Aerospace & Defense"), "msci")["status"] == "not_compliant"
    assert ev(co(industry="Aerospace & Defense"), "sp")["status"] == "compliant"
    assert ev(co(industry="Lodging"), "msci")["status"] == "not_compliant"


def test_pork_and_adult_keywords_need_review_not_a_pass():
    r = ev(co(industry="Packaged Foods", summary="Processes pork, beef and chicken."))
    assert r["status"] == "unknown" and r["reasons"][0]["value"] == "pork"
    r = ev(co(industry="Entertainment", summary="Adult entertainment studio."), "aaoifi")
    assert r["status"] == "unknown" and r["reasons"][0]["value"] == "adult"
    assert ev(co(industry="Packaged Foods", summary="Dairy and juice."))["status"] == "compliant"


def test_bank_ratios_are_not_computed():
    r = ev(co(industry="Banks - Regional", total_debt=None, cash_st=None))
    assert r["status"] == "not_compliant" and codes(r) == ["activity"]


def test_islamic_bank_is_unknown_not_guessed():
    r = sharia.evaluate("1120.SR", co(industry="Banks - Regional"), "aaoifi", today=TODAY)
    assert r["status"] == "unknown" and codes(r) == ["islamic_finance"]


def test_ambiguous_industry_is_unknown():
    r = ev(co(industry="Credit Services"))
    assert r["status"] == "unknown" and codes(r) == ["ambiguous_industry"]


# ---- edge cases: missing data, negative equity, stale data
@pytest.mark.parametrize("field", ["total_debt", "cash_st", "market_cap"])
def test_missing_required_field_is_unknown_never_compliant(field):
    r = ev(co(**{field: None}))
    assert r["status"] == "unknown"
    assert {"code": "missing", "field": field} in r["reasons"]


def test_missing_everything_is_unknown():
    assert ev(None)["status"] == "unknown"
    assert ev({"error": "unavailable"})["status"] == "unknown"
    assert ev(co(industry=None))["status"] == "unknown"
    assert ev(co(bs_date=None))["status"] == "unknown"


def test_missing_income_data_is_flagged_not_hidden():
    r = ev(co(interest_income=None))
    assert r["status"] == "compliant" and codes(r) == ["income_not_checked"] and r["purification"] is None


def test_missing_receivables_matters_only_where_the_method_uses_it():
    assert ev(co(receivables=None), "aaoifi")["status"] == "compliant"
    assert ev(co(receivables=None), "sp")["status"] == "unknown"


def test_negative_equity_does_not_break_the_screen():
    # Book equity below zero (e.g. heavy buybacks): the methods divide by market cap or total assets, not equity,
    # so the result still follows the debt ratio. Debt 150% of market cap fails; low debt still passes.
    assert ev(co(equity=-500.0, total_debt=1500.0))["status"] == "not_compliant"
    assert ev(co(equity=-500.0))["status"] == "compliant"
    r = ev(co(market_cap=-5.0))
    assert r["status"] == "unknown" and {"code": "missing", "field": "market_cap"} in r["reasons"]


def test_stale_balance_sheet_is_unknown():
    r = ev(co(bs_date="2024-12-31", total_debt=1.0))
    assert r["status"] == "unknown" and codes(r) == ["stale"]
    # but a business-activity exclusion doesn't depend on how fresh the numbers are
    assert ev(co(bs_date="2024-12-31", industry="Gambling"))["status"] == "not_compliant"


def test_non_equities_are_not_screened():
    assert codes(ev(co(quote_type="ETF"))) == ["not_equity"]
    assert ev(co(quote_type="CRYPTOCURRENCY"))["status"] == "unknown"


def test_screen_caches_with_date_and_failed_fetch_is_unknown(monkeypatch):
    db.conn()
    calls = []

    def fake(sym):
        calls.append(sym)
        if sym == "BAD":
            raise ConnectionError("no network")
        return co(fetched_at=db.now())
    monkeypatch.setattr(sharia, "fetch_raw", fake)
    with db.tx() as c:
        c.execute("DELETE FROM sharia_cache")
    r = sharia.screen(["AAPL", "BAD"], "aaoifi")
    assert r["AAPL"]["status"] == "compliant" and r["AAPL"]["fetched_at"]
    assert r["BAD"]["status"] == "unknown" and codes(r["BAD"]) == ["no_data"]
    sharia.screen(["AAPL"], "aaoifi")
    assert calls.count("AAPL") == 1   # cached


def test_settings_default_off():
    with db.tx() as c:
        c.execute("DELETE FROM settings WHERE key='sharia'")
    assert sharia.settings() == {"enabled": False, "method": "aaoifi", "hide": False}
    with pytest.raises(ValueError):
        sharia.save_settings(method="made-up")


# ---- where the toggle applies: beginner suggestions and the budget plan
PX = {"AAPL": (210.0, "USD"), "MSFT": (420.0, "USD"), "KO": (68.0, "USD"), "PG": (165.0, "USD"), "JPM": (200.0, "USD"),
      "2280.SR": (55.0, "SAR"), "7010.SR": (42.0, "SAR"), "1120.SR": (95.0, "SAR"), "1211.SR": (50.0, "SAR"),
      "1180.SR": (35.0, "SAR"), "2222.SR": (27.5, "SAR"), "USDSAR=X": (3.75, "SAR"), "SARUSD=X": (0.2667, "USD")}
FUND = {"1120.SR": co(industry="Banks - Regional"), "1180.SR": co(industry="Banks - Diversified"),
        "1150.SR": co(industry="Banks - Regional"), "JPM": co(industry="Banks - Diversified"),
        "KO": co(industry="Beverages - Non-Alcoholic"), "MSFT": co(industry="Software - Infrastructure"),
        "AAPL": co(industry="Consumer Electronics"), "2280.SR": co(industry="Packaged Foods", summary="Dairy."),
        "7010.SR": co(industry="Telecom Services", total_debt=450.0), "1211.SR": co(industry="Other Industrial Metals & Mining"),
        "2222.SR": co(industry="Oil & Gas Integrated")}


@pytest.fixture
def world(monkeypatch):
    from veyro import market
    db.conn()
    with db.tx() as c:
        c.execute("DELETE FROM sharia_cache")
    monkeypatch.setattr(market, "last_price", lambda t: {"price": PX[t][0], "currency": PX[t][1]} if t in PX else None)
    monkeypatch.setattr(sharia, "fetch_raw", lambda s: FUND.get(s) or {"error": "unavailable", "fetched_at": db.now()})
    yield
    sharia.save_settings(enabled=False)


def test_beginner_suggestions_only_compliant_when_on(world):
    from veyro import beginner
    sharia.save_settings(enabled=False)
    off = beginner.suggest(1000, "SAR", "sa", "cautious", 3)
    assert "sharia" not in off
    sharia.save_settings(enabled=True, method="aaoifi")
    on = beginner.suggest(1000, "SAR", "sa", "cautious", 3)
    syms = [p["symbol"] for p in on["picks"]]
    assert all(FUND.get(s) and sharia.evaluate(s, FUND[s])["status"] == "compliant" for s in syms), syms
    ex = {e["symbol"]: e["status"] for e in on["sharia"]["excluded"]}
    assert ex["7010.SR"] == "not_compliant" and ex["1120.SR"] == "unknown" and ex["1180.SR"] == "not_compliant"
    assert ex["5110.SR"] == "unknown"   # no data -> never suggested as compliant


def test_beginner_says_so_when_too_few_remain(world):
    from veyro import beginner
    sharia.save_settings(enabled=True)
    r = beginner.suggest(1000, "SAR", "sa", "cautious", 5)
    assert len(r["picks"]) < 5 and r["sharia"]["short"] is True and r["sharia"]["wanted"] == 5


def _s(i, t):
    return {"id": i, "ticker": t, "status": "done", "mode": "real", "rating": "Buy",
            "verdict": {"conviction": "medium", "lang": "en", "reason": "r"}}


def test_plan_excludes_non_compliant_and_unknown_when_on(world):
    from veyro import allocation
    sess = [_s("a", "AAPL"), _s("b", "JPM"), _s("c", "MSFT"), _s("d", "NOPE")]
    sharia.save_settings(enabled=False)
    off = allocation.plan(sess, 5000, "USD")
    assert {r["ticker"] for r in off["rows"]} == {"AAPL", "JPM", "MSFT", "NOPE"} and off["sharia"] is None
    sharia.save_settings(enabled=True)
    on = allocation.plan(sess, 5000, "USD")
    assert {r["ticker"] for r in on["rows"]} == {"AAPL", "MSFT"}
    sk = {x["ticker"]: x["sharia"]["status"] for x in on["skipped"]}
    assert sk == {"JPM": "not_compliant", "NOPE": "unknown"}
    assert set(on["sharia"]["excluded"]) == {"JPM", "NOPE"}
