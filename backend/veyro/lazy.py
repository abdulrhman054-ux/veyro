"""Heavy libraries (yfinance pulls in pandas and numpy) load on first use, not at startup, so the
app window opens fast. A background warm-up loads them right after the server is up."""
from __future__ import annotations

import importlib
import threading


class LazyModule:
    def __init__(self, name: str):
        self._name = name
        self._mod = None
        self._lock = threading.Lock()

    def _load(self):
        if self._mod is None:
            with self._lock:
                if self._mod is None:
                    self._mod = importlib.import_module(self._name)
        return self._mod

    def __getattr__(self, attr):
        return getattr(self._load(), attr)


yf = LazyModule("yfinance")


def warm_up() -> None:
    """Import what the first screens and the first session need, off the request path."""
    def run():
        for name in ("yfinance", "tradingagents.graph.trading_graph", "langchain_anthropic"):
            try:
                importlib.import_module(name)
            except Exception:  # noqa: BLE001
                pass
    threading.Thread(target=run, daemon=True, name="warm-up").start()
