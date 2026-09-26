"""Unit tests never touch the network: price history and sector lookups return 'unavailable' unless a test stubs them."""
import pytest


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    from veyro import market
    monkeypatch.setattr(market, "history", lambda t, period="3mo": None)
    monkeypatch.setattr(market, "sector", lambda t: None)
    monkeypatch.setattr(market, "dividends", lambda t: [])
    monkeypatch.setattr(market, "dividends_or_none", lambda t: [])
    from veyro import valuation
    monkeypatch.setattr(valuation, "_fetch", lambda t: {"error": "unavailable"})
