"""Session orchestration: runs TradingAgents (or the labelled Demo script) and streams
character events to the UI over an in-memory event bus.

Event types sent to the browser:
  session, market, agent_started, agent_message, agent_done, verdict, usage, error, end
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import queue
import re
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from langchain_core.callbacks import BaseCallbackHandler

from . import db, market
from .config import CHARACTERS, ESTIMATE_TOKENS, NODE_CHARACTER, PRICING, PROVIDERS, RISK_NODES, TA_HOME
from .secrets_store import get_secret, llm_key, scrub

log = logging.getLogger("veyro.runner")
DISCLAIMER = {"ar": "تحليل للمساعدة على التفكير، وليس نصيحة مالية.",
              "en": "Analysis to help you think, not financial advice."}
RATING_ORDER = ["Buy", "Overweight", "Hold", "Underweight", "Sell"]


# ---------------------------------------------------------------- pricing helpers
def price_for(model: str | None) -> tuple[float, float] | None:
    if not model:
        return None
    # The owner's own entry for a model with no known price. Providers often answer with a dated or suffixed name
    # ("my-model-2026-01-15" for "my-model"), so the same prefix rule as the built-in table applies.
    custom = db.get_setting("custom_prices") or {}
    for k in sorted(custom, key=len, reverse=True):
        if (model == k or model.startswith(k + "-") or model.startswith(k + "@")) and custom[k]:
            return (float(custom[k][0]), float(custom[k][1]))
    # Longest prefix wins, so "claude-opus-5-5" is never priced as "claude-opus-5".
    for k in sorted(PRICING, key=len, reverse=True):
        if model == k or model.startswith(k + "-") or model.startswith(k + "@"):
            return PRICING[k]
    return None


def estimate(provider: str, quick: str, deep: str, sessions: int = 1, team: dict | None = None, asset_type: str = "stock") -> dict:
    pq, pd = price_for(quick), price_for(deep)
    team = team or team_settings()
    n = len(analysts_for(asset_type, team["analysts"]))
    scale = (0.4 + 0.15 * n) * (1 + 0.35 * (team["debate_rounds"] - 1) + 0.25 * (team["risk_rounds"] - 1))
    if not pq or not pd:
        return {"known": False, "low": None, "high": None, "currency": "USD", "sessions": sessions}
    e = ESTIMATE_TOKENS

    def total(i: int) -> float:
        return scale * ((e["quick_in"][i] + e["voice_in"][i]) * pq[0] + (e["quick_out"][i] + e["voice_out"][i]) * pq[1]
                        + e["deep_in"][i] * pd[0] + e["deep_out"][i] * pd[1]) / 1_000_000

    return {"known": True, "low": round(total(0) * sessions, 2), "high": round(total(1) * sessions, 2),
            "currency": "USD", "sessions": sessions}


class UsageTracker(BaseCallbackHandler):
    """Collects token usage per model from every LLM call (framework + voice layer)."""

    def __init__(self, sid: str | None = None):
        self.lock = threading.Lock()
        self.by_model: dict[str, dict[str, int]] = {}
        self.sid = sid   # a session's tracker writes its cost to the database as each reply lands

    def on_llm_end(self, response, **kwargs):  # noqa: ANN001
        for gens in response.generations:
            for g in gens:
                msg = getattr(g, "message", None)
                um = getattr(msg, "usage_metadata", None) or {}
                meta = getattr(msg, "response_metadata", None) or {}
                model = meta.get("model_name") or meta.get("model") or "unknown"
                with self.lock:
                    d = self.by_model.setdefault(model, {"input": 0, "output": 0, "calls": 0})
                    d["input"] += int(um.get("input_tokens", 0) or 0)
                    d["output"] += int(um.get("output_tokens", 0) or 0)
                    d["calls"] += 1
        if self.sid:
            self.persist()

    def persist(self) -> None:
        """Write what has been spent so far. A run cut off by closing the app, and model calls that finish after Stop,
        still count against the monthly cap (they used to be written only when the run ended normally)."""
        u = self.summary()
        try:
            db.update_session(self.sid, usage_json=json.dumps(u), cost_usd=u["cost_usd"])
        except Exception as e:  # noqa: BLE001 - never break a model call over bookkeeping
            log.warning("could not record usage for %s: %s", self.sid, scrub(repr(e)))

    def summary(self) -> dict:
        with self.lock:
            models = copy.deepcopy(self.by_model)
        cost, known = 0.0, True
        for m, d in models.items():
            p = price_for(m)
            if p is None:
                known = False
                continue
            c = (d["input"] * p[0] + d["output"] * p[1]) / 1_000_000
            d["cost_usd"] = round(c, 4)
            cost += c
        return {"models": models, "cost_usd": round(cost, 4) if known else None,
                "cost_partial": round(cost, 4), "pricing_known": known}


# ---------------------------------------------------------------- event bus
class Bus:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.events: list[dict] = []
        self.subs: set[asyncio.Queue] = set()
        self.closed = False
        self.closed_at: float | None = None
        self.lock = threading.Lock()

    def publish(self, ev: dict) -> None:
        ev.setdefault("ts", time.time())
        with self.lock:
            if self.closed:
                return   # nothing after "end": late voice lines from a stopped session must not reach the UI
            self.events.append(ev)
            subs = list(self.subs)
        for s in subs:
            self.loop.call_soon_threadsafe(s.put_nowait, ev)
        if ev["type"] == "end":
            with self.lock:
                self.closed = True
                self.closed_at = time.time()

    def subscribe(self) -> tuple[asyncio.Queue, list[dict]]:
        q: asyncio.Queue = asyncio.Queue()
        with self.lock:
            backlog = list(self.events)
            self.subs.add(q)
        return q, backlog

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self.lock:
            self.subs.discard(q)


BUSES: dict[str, Bus] = {}
CANCEL: dict[str, threading.Event] = {}
TRACKERS: dict[str, "UsageTracker"] = {}   # live token counters, so a stopped or failed run still records its cost


# ---------------------------------------------------------------- in-character errors
ERRORS = {
    "budget_cap": ("Leo", "وصلنا سقف ميزانية التحليل لهذا الشهر، فما نبدأ طلب مدفوع جديد. تقدر ترفع السقف من الإعدادات. زئير!",
                   "This month's analysis budget cap is reached, so no new paid request starts. You can raise the cap in Settings. Roar!"),
    "no_key": ("Pip", "ما لقيت مفتاح! حطّ مفتاح API من الإعدادات وبنبدأ على طول، سكوااك!",
               "No key found! Add your API key in Settings and we'll get going, squawk!"),
    "auth": ("Pip", "الخط مقطوع! تأكد من المفتاح، شكله غلط أو منتهي، سكوااك!",
             "The line's dead! Check your API key, it looks wrong or expired, squawk!"),
    "rate": ("Tank", "شوي شوي… المزوّد يقول وصلنا الحد. استنى دقيقة وجرّب مرة ثانية. على مهلك… بثبات.",
             "Easy now… the provider says we hit a rate limit. Wait a minute and try again. slow and steady."),
    "network": ("Pip", "الإنترنت فصل عندنا! تأكد من الاتصال وجرّب مرة ثانية، سكوااك!",
                "We lost the internet! Check your connection and try again, squawk!"),
    "workspace": ("Pip", "مفتاحك يحتاج «معرّف مساحة العمل» (Workspace ID). حطه في الإعدادات تحت المفتاح، سكوااك!",
                  "Your key needs a Workspace ID. Add it in Settings under the key, squawk!"),
    "model": ("Ollie", "النموذج اللي اخترته ما رد علينا. غيّره من الإعدادات، هوو هوو!",
              "The model you picked didn't answer. Try another one in Settings, hoot!"),
    "data": ("Benny", "ما قدرت أجيب بيانات هذا السهم. تأكد من الرمز، قرمش!",
             "I couldn't fetch data for this ticker. Double-check the symbol, chomp!"),
    "cancelled": ("Leo", "وقّفنا الجلسة مثل ما طلبت. زئير!", "Session stopped, as you asked. roar!"),
    "unknown": ("Leo", "صار خلل غير متوقع ووقفنا الجلسة. التفاصيل محفوظة في السجل. زئير!",
                "Something unexpected broke and we stopped the session. Details are in the log. roar!"),
}


def classify(exc: BaseException) -> str:
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if name == "capreached":
        return "budget_cap"
    if "workspace" in msg:
        return "workspace"
    if "authentication" in name or "401" in msg or "invalid x-api-key" in msg or "invalid api key" in msg or "incorrect api key" in msg:
        return "auth"
    if "ratelimit" in name or "429" in msg or "rate limit" in msg:
        return "rate"
    if "connect" in name or "timeout" in name or "connection" in msg:
        return "network"
    if "notfound" in name or "model" in msg and ("not found" in msg or "does not exist" in msg):
        return "model"
    return "unknown"


def error_event(code: str, lang: str, detail: str = "") -> dict:
    ch, ar, en = ERRORS[code]
    return {"type": "error", "code": code, "character": ch, "text": ar if lang == "ar" else en,
            "texts": {"ar": ar, "en": en}, "detail": scrub(detail)[:400]}


# ---------------------------------------------------------------- helpers
def today_for(ticker: str | None) -> str:
    """Today's date in the stock's own market (Riyadh for Tadawul, New York otherwise)."""
    from .calendars import local_today, market_of
    return local_today(market_of(ticker))


def ny_today() -> str:
    return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")


ANALYSTS = ("market", "social", "news", "fundamentals")
ANALYST_CHARACTER = {"market": "Ollie", "social": "Buzz", "news": "Pip", "fundamentals": "Benny"}


def team_settings() -> dict:
    """User-chosen TradingAgents team: which analysts attend and how many debate/risk rounds."""
    analysts = [a for a in (db.get_setting("team_analysts") or list(ANALYSTS)) if a in ANALYSTS] or list(ANALYSTS)
    debate = int(db.get_setting("team_debate_rounds", 1) or 1)
    risk = int(db.get_setting("team_risk_rounds", 1) or 1)
    return {"analysts": [a for a in ANALYSTS if a in analysts], "debate_rounds": max(1, min(3, debate)),
            "risk_rounds": max(1, min(3, risk))}


def resolve_instrument(ticker: str) -> tuple[str, str]:
    """(canonical Yahoo symbol, asset_type) using the framework's own symbol rules."""
    from tradingagents.dataflows.symbols import crypto_base, normalize_symbol
    sym = normalize_symbol(ticker)
    return sym, ("crypto" if crypto_base(sym) else "stock")


def analysts_for(asset_type: str, analysts: list[str]) -> list[str]:
    # Same rule as the framework CLI: crypto has no company fundamentals.
    out = [a for a in analysts if not (asset_type == "crypto" and a == "fundamentals")]
    return out or ["market"]


# The framework's benchmark map has no Saudi entry, so Tadawul stocks would be scored against SPY.
# Veyro adds TASI for ".SR" (passed to the framework too, so its settled alpha uses the same index).
EXTRA_BENCHMARKS = {".SR": "^TASI.SR"}


# If Yahoo has no usable TASI history (it has kept only the latest day at times), Saudi calls are measured
# against the iShares MSCI Saudi Arabia ETF (KSA): full free history, and the riyal is pegged to the dollar,
# so its returns track the Saudi market closely. The session records which index was actually used.
SAUDI_FALLBACK = "KSA"


def usable_benchmark(bench: str) -> str:
    if bench != EXTRA_BENCHMARKS[".SR"]:
        return bench
    h = market.history(bench, "3mo")
    return bench if h and len(h.get("closes") or []) >= 20 else SAUDI_FALLBACK


def benchmark_map(saudi: str | None = None) -> dict:
    from tradingagents.default_config import DEFAULT_CONFIG
    return {**EXTRA_BENCHMARKS, **({".SR": saudi} if saudi else {}), **DEFAULT_CONFIG.get("benchmark_map", {})}


def benchmark_for(ticker: str) -> str:
    from tradingagents.default_config import DEFAULT_CONFIG
    bm = benchmark_map()
    for suffix, idx in bm.items():
        if suffix and ticker.upper().endswith(suffix.upper()):
            return idx
    return DEFAULT_CONFIG.get("benchmark_ticker") or bm.get("", "SPY")


def portfolio_context(budget: dict | None = None):
    """When optional execution is on, give the framework's decision agents the real book. Otherwise, when the
    owner entered a budget, the Portfolio Manager is told that much cash is free for this idea."""
    try:
        from .execution import service as ex
        m = ex.mode()
        if m == "off":
            if budget and budget.get("amount"):
                from tradingagents.portfolio import PortfolioContext
                return PortfolioContext(cash=float(budget["amount"]), currency=budget.get("currency") or "USD"), "budget"
            return None, None
        b = ex.broker_for(m)
        acct, pos = b.account(), b.positions()
        from tradingagents.portfolio import PortfolioContext, Position
        pc = PortfolioContext(cash=acct.get("cash"), currency="USD",
                              positions=[Position(ticker=p["symbol"], quantity=p["qty"], average_price=p.get("avg_entry_price"))
                                         for p in pos if p.get("qty")])
        return pc, b.label
    except Exception as e:  # noqa: BLE001
        log.info("portfolio context unavailable: %s", type(e).__name__)
        return None, None


def activate_key(provider: str, key: str | None) -> None:
    """Make the saved key visible to the framework's and the voice layer's clients (process-local only).
    Keyless providers (Ollama) need nothing."""
    env = PROVIDERS[provider]["env"]
    if env and key:
        set_env(env, key)


_ENV_AT_START: dict[str, str | None] = {}


def set_env(env: str, value: str) -> None:
    """Expose a key to the framework's clients, remembering what the environment (.env) had before."""
    _ENV_AT_START.setdefault(env, os.environ.get(env))
    os.environ[env] = value


def unset_env(env: str) -> None:
    """Undo set_env after the owner removes a key: it must stop being used now, not after a restart."""
    if env not in _ENV_AT_START:
        return
    orig = _ENV_AT_START.pop(env)
    if orig is None:
        os.environ.pop(env, None)
    else:
        os.environ[env] = orig


MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@\-]{1,99}$")


def settings_models() -> tuple[str, str, str]:
    provider = db.get_setting("provider", "anthropic")
    if provider not in PROVIDERS:
        provider = "anthropic"
    p = PROVIDERS[provider]
    quick = db.get_setting(f"quick_model:{provider}", p["default_quick"])
    deep = db.get_setting(f"deep_model:{provider}", p["default_deep"])
    return provider, quick, deep


def verdict_price(ticker: str, bench: str = "SPY") -> dict:
    px = market.last_price(ticker)
    spy = market.last_price(bench)
    return {"price": px["price"] if px else None, "spy": spy["price"] if spy else None,
            "as_of": (px or spy or {}).get("as_of"), "source": market.SOURCE if (px or spy) else None}


class Emitter:
    """Keeps UI events in order while voice lines are generated in parallel."""

    def __init__(self, bus: Bus, cancel: threading.Event | None = None):
        self.bus = bus
        self.cancel = cancel
        # Set (under STATUS_LOCK) the moment the verdict is recorded: from then on its events are always shown,
        # even if Stop lands while the verdict job is still returning them.
        self.verdict_in = threading.Event()
        self.q: queue.Queue = queue.Queue()
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()

    def put(self, item: dict | Future | Callable[[], list[dict]]) -> None:
        self.q.put(item)

    def _run(self):
        while True:
            item = self.q.get()
            if item is None:
                return
            try:
                if isinstance(item, Future):
                    # Wait in short steps so Stop is honoured even while a voice or verdict call is in flight
                    # (the call itself finishes in its worker; its line is simply never shown).
                    while not item.done() and not (self.cancel is not None and self.cancel.is_set()):
                        try:
                            item.result(timeout=0.2)
                        except FutureTimeout:
                            pass
                    if self.cancel is not None and self.cancel.is_set():
                        if not item.done() and self.verdict_in.is_set():
                            try:
                                item.result(timeout=30)   # recorded already: it is only returning its events
                            except Exception:  # noqa: BLE001
                                pass
                        evs = item.result() if item.done() and not item.cancelled() and not item.exception() else None
                        if not (isinstance(evs, list) and any(e.get("type") == "verdict" for e in evs)):
                            item.cancel()
                            continue   # stopped: don't wait for (or show) lines still being voiced
                        # the verdict was already recorded before Stop landed: show it, so the UI matches History
                    evs = item.result()
                    for ev in (evs if isinstance(evs, list) else [evs]):
                        self.bus.publish(ev)
                else:
                    self.bus.publish(item)
            except Exception as e:  # noqa: BLE001
                log.error("emitter item failed: %s", scrub(repr(e)))

    def close(self):
        self.q.put(None)
        self.t.join()


# ---------------------------------------------------------------- real session
def _extract(node: str, delta: dict) -> str | None:
    """The English output an agent node produced in this update, if any."""
    if not isinstance(delta, dict):
        return None
    if node == "Market Analyst":
        return delta.get("market_report") or None
    if node == "Sentiment Analyst":
        return delta.get("sentiment_report") or None
    if node == "News Analyst":
        return delta.get("news_report") or None
    if node == "Fundamentals Analyst":
        return delta.get("fundamentals_report") or None
    if node in ("Bull Researcher", "Bear Researcher"):
        return (delta.get("investment_debate_state") or {}).get("current_response") or None
    if node == "Research Manager":
        return delta.get("investment_plan") or None
    if node == "Trader":
        return delta.get("trader_investment_plan") or None
    if node in RISK_NODES:
        rs = delta.get("risk_debate_state") or {}
        key = {"Aggressive Analyst": "current_aggressive_response",
               "Conservative Analyst": "current_conservative_response",
               "Neutral Analyst": "current_neutral_response"}[node]
        return rs.get(key) or None
    if node == "Portfolio Manager":
        return delta.get("final_trade_decision") or None
    return None


def _tool_sources(delta: dict, vendors: dict, sources: dict) -> None:
    from tradingagents.dataflows.router import TOOLS_CATEGORIES
    tool_cat = {t: c for c, info in TOOLS_CATEGORIES.items() for t in info.get("tools", [])}
    for m in (delta or {}).get("messages", []) or []:
        name = getattr(m, "name", None)
        if not name:
            continue
        content = str(getattr(m, "content", ""))
        ok = not content.lower().startswith(("error", "failed")) and bool(content.strip())
        cat = tool_cat.get(name)
        vendor = vendors.get(cat, "yfinance") if cat else "yfinance"
        s = sources.setdefault(name, {"tool": name, "category": cat, "vendor": vendor, "ok": ok, "calls": 0})
        s["calls"] += 1
        s["ok"] = s["ok"] and ok


def reasoning_config(provider: str) -> dict:
    """Map the one "reasoning depth" setting onto the framework's provider-specific knobs."""
    depth = db.get_setting("reasoning_depth", "default")
    if depth not in ("low", "medium", "high"):
        return {}
    if provider == "anthropic":
        return {"anthropic_effort": depth}
    if provider == "openai":   # the framework forwards reasoning effort for OpenAI only (not xAI / DeepSeek)
        return {"openai_reasoning_effort": depth}
    if provider == "google":
        return {"google_thinking_level": "high" if depth == "high" else "low"}
    return {}


def run_session(sid: str, ticker: str, lang: str, demo: bool, trade_date: str | None = None, budget: dict | None = None) -> None:
    bus = BUSES[sid]
    cancel = CANCEL[sid]
    em = Emitter(bus, cancel)
    try:
        if demo:
            _run_demo(sid, ticker, lang, em, cancel)
        else:
            _run_real(sid, ticker, lang, em, cancel, trade_date, budget)
    except _Cancelled:
        em.put(error_event("cancelled", lang))
        db.update_session(sid, status="cancelled", finished_at=db.now())
        em.put({"type": "end", "status": "cancelled"})
    except Exception as e:  # noqa: BLE001
        if cancel.is_set():   # a failure while winding down after Stop is still a stop, not an error
            db.update_session(sid, status="cancelled", finished_at=db.now()) if (db.get_session(sid) or {}).get("status") == "running" else None
            em.put({"type": "end", "status": "cancelled"})
            return
        log.error("session %s crashed: %s", sid, scrub(repr(e)))
        code = classify(e)
        em.put(error_event(code, lang, repr(e)))
        db.update_session(sid, status="error", error=scrub(repr(e))[:500], finished_at=db.now())
        em.put({"type": "end", "status": "error"})
    finally:
        em.close()
        if not bus.closed:   # backstop: whatever happened above, the UI and scans always get an end
            stopped = cancel.is_set()
            if stopped:
                bus.publish(error_event("cancelled", lang))
            bus.publish({"type": "end", "status": "cancelled" if stopped else "error"})
            s = db.get_session(sid)
            if s and s.get("status") == "running":
                db.update_session(sid, status="cancelled" if stopped else "error", error=None if stopped else "incomplete",
                                  finished_at=db.now())
        tracker = TRACKERS.pop(sid, None)
        if tracker is not None:   # stopped or failed after spending: the monthly cap must still see the cost
            s = db.get_session(sid)
            if s and s.get("status") != "done" and not s.get("usage_json"):
                usage = tracker.summary()
                db.update_session(sid, usage_json=json.dumps(usage), cost_usd=usage["cost_usd"])


# ---------------------------------------------------------------- how the characters hand over to each other
def turn_context(node: str, said: dict[str, str]) -> str:
    """Tells the voice layer where this line sits in the conversation, so speakers answer each other in order
    (the debate is a real back-and-forth) while every fact still comes only from the speaker's own conclusion."""
    if node == "Bull Researcher":
        prev = said.get("Bear Researcher")
        return ("This is a live bull-vs-bear debate. Bruno the bear just argued (for reference only):\n" + prev[:700]
                + "\nYou may answer Bruno by name in a few words, but take every fact only from your own conclusion.") if prev \
            else "You open the bull-vs-bear debate after the four analysts have reported."
    if node == "Bear Researcher":
        prev = said.get("Bull Researcher")
        return ("This is a live bull-vs-bear debate. Bolt the bull just argued (for reference only):\n" + prev[:700]
                + "\nYou may answer Bolt by name in a few words, but take every fact only from your own conclusion.") if prev else ""
    if node == "Research Manager":
        return ("Leo now speaks as the Research Manager: he has heard Bolt (bull) and Bruno (bear) and sets the investment plan. "
                "Say which way the plan leans, exactly as the source states.")
    if node == "Trader":
        return "Leo now speaks as the Trader: he turns the investment plan into a concrete trade proposal."
    return ""


def fallback_line(ch: str, lang: str) -> str:
    c = CHARACTERS[ch]
    return (f"خلصت تحليلي، بس ما قدرت أصيغ الخلاصة بصوتي الآن. التحليل الكامل محفوظ في التقرير. {c['catch_ar']}" if lang == "ar"
            else f"My analysis is done, but I couldn't voice the summary just now. The full analysis is in the report. {c['catch_en']}")


def fallback_verdict(rating: str, lang: str) -> str:
    from_ar = {"Buy": "شراء", "Overweight": "زيادة تدريجية", "Hold": "احتفاظ", "Underweight": "تخفيف", "Sell": "بيع"}
    return (f"يا جماعة، القرار: {from_ar.get(rating, rating)}. التفاصيل الكاملة في التقرير. زئير!" if lang == "ar"
            else f"Friends, the call is: {rating}. The full reasoning is in the report. roar!")


def _run_real(sid: str, ticker: str, lang: str, em: Emitter, cancel: threading.Event, trade_date_in: str | None = None,
              budget: dict | None = None) -> None:
    from tradingagents.dataflows.config import run_config
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    provider, quick, deep = settings_models()
    if not quick or not deep:   # e.g. OpenRouter/Groq before a model was picked
        em.put(error_event("model", lang))
        db.update_session(sid, status="error", error="no_model", finished_at=db.now())
        em.put({"type": "end", "status": "error"})
        return
    key, _src = llm_key(provider)
    if not key:
        em.put(error_event("no_key", lang))
        db.update_session(sid, status="error", error="no_key", finished_at=db.now())
        em.put({"type": "end", "status": "error"})
        return
    activate_key(provider, key)

    def stop_point():
        if cancel.is_set():
            raise _Cancelled()   # Stop during start-up: don't go on fetching data or building the team

    # A past date is analysed point-in-time: the framework only lets agents see data up to that day.
    trade_date = trade_date_in or today_for(ticker)
    past = trade_date < today_for(ticker)
    team = team_settings()
    symbol, asset_type = resolve_instrument(ticker)
    analysts = analysts_for(asset_type, team["analysts"])
    bench = usable_benchmark(benchmark_for(symbol))
    stop_point()
    for dk, env in (("data:fred", "FRED_API_KEY"), ("data:alpha_vantage", "ALPHA_VANTAGE_API_KEY"), ("data:typesafe", "TYPESAFE_API_KEY")):
        v = get_secret(dk)
        if v:
            set_env(env, v)
    pc, pc_broker = portfolio_context(budget)
    stop_point()
    em.put({"type": "session", "id": sid, "ticker": symbol, "mode": "real", "lang": lang, "trade_date": trade_date,
            "provider": provider, "quick_model": quick, "deep_model": deep,
            "estimate": estimate(provider, quick, deep, team=team, asset_type=asset_type),
            "asset_type": asset_type, "analysts": analysts, "on_break": _on_break(analysts),
            "debate_rounds": team["debate_rounds"], "risk_rounds": team["risk_rounds"], "benchmark": bench,
            "portfolio_used": pc is not None, "portfolio_broker": pc_broker})
    ticker = symbol
    hist = market.history(ticker)
    em.put({"type": "market", "data": hist, "available": hist is not None})

    cfg = copy.deepcopy(DEFAULT_CONFIG)
    from .anthropic_relay import base_url as relay_url
    cfg.update({"llm_provider": provider, "quick_think_llm": quick, "deep_think_llm": deep,
                "backend_url": relay_url() if provider == "anthropic" else None,
                "output_language": "English",
                "max_debate_rounds": team["debate_rounds"], "max_risk_discuss_rounds": team["risk_rounds"],
                "checkpoint_enabled": True,  # a stopped or crashed run resumes from its last finished step
                **reasoning_config(provider),
                "benchmark_map": benchmark_map(bench if symbol.upper().endswith(".SR") else None),
                "data_vendors": __import__("veyro.datasources", fromlist=["x"]).framework_vendors(DEFAULT_CONFIG["data_vendors"]),
                "results_dir": str(TA_HOME / "logs"), "data_cache_dir": str(TA_HOME / "cache"),
                "memory_log_path": str(TA_HOME / "memory" / "trading_memory.md")})
    tracker = UsageTracker(sid)
    TRACKERS[sid] = tracker
    stop_point()
    ta = TradingAgentsGraph(selected_analysts=tuple(analysts), config=cfg, callbacks=[tracker])
    stop_point()
    from .voice import Voice
    voice = Voice(provider, quick, callbacks=[tracker])
    pool = ThreadPoolExecutor(max_workers=3)

    seq = 0
    final: dict[str, Any] = {}
    risk_buf: list[tuple[str, str]] = []
    sources: dict[str, dict] = {}
    active: set[str] = set()

    def started(ch: str, node: str):
        if ch not in active:
            active.add(ch)
            em.put({"type": "agent_started", "character": ch, "node": node})

    last_said: dict[str, str] = {}   # node -> latest English output, so speakers can answer each other

    def speak(ch: str, node: str, text: str, context: str = ""):
        nonlocal seq
        seq += 1
        my_seq = seq
        context = context or turn_context(node, last_said)
        last_said[node] = text

        def job():
            try:
                line = voice.speak(ch, ticker, text, lang, context)
                voiced = True
            except Exception as e:  # noqa: BLE001
                # The analysis itself is safe; only the short spoken line failed. Keep the full text and move on.
                log.info("voice line failed for %s: %s", node, type(e).__name__)
                line, voiced = fallback_line(ch, lang), False
            tid = db.add_turn(sid, my_seq, ch, node, text, line if voiced and lang == "ar" else None,
                              line if voiced and lang == "en" else None)
            return [{"type": "agent_message", "character": ch, "node": node, "turn_id": tid, "text": line, "lang": lang,
                     "texts": {lang: line}},
                    {"type": "agent_done", "character": ch, "node": node}]
        active.discard(ch)
        em.put(pool.submit(job))

    def albie_link():
        """Albie flies in with today's world headlines and links them to this stock's real move."""
        nonlocal seq
        seq += 1
        my_seq = seq
        em.put({"type": "agent_started", "character": "Albie", "node": "Global Link"})
        ctx = "\n\n".join(x for x in (final.get("news_report", "")[:1500], final.get("market_report", "")[:1500]) if x)

        def job():
            from . import world
            try:
                move = world.stock_move(ticker)
                line = world.link(ticker, lang, provider, quick, move, ctx)
                heads = world.news("en")["items"][:12]
            except Exception as e:  # noqa: BLE001
                log.info("albie link failed: %s", type(e).__name__)
                return [{"type": "agent_done", "character": "Albie", "node": "Global Link"}]
            detail = ("Global news link (Albie). Headlines considered:\n" + "\n".join(f"- [{h['source']}] {h['title']} ({h['link']})" for h in heads)
                      + (f"\n\nStock move: {move['change'] * 100:+.2f}% on {move['date']}" if move else ""))
            tid = db.add_turn(sid, my_seq, "Albie", "Global Link", detail, line if lang == "ar" else None, line if lang == "en" else None)
            return [{"type": "agent_message", "character": "Albie", "node": "Global Link", "turn_id": tid, "text": line, "lang": lang,
                     "texts": {lang: line}},
                    {"type": "agent_done", "character": "Albie", "node": "Global Link"}]
        em.put(pool.submit(job))

    albie_done = False

    def flush_risk():
        if not risk_buf:
            return
        merged = "\n\n".join(f"## {n}\n{t}" for n, t in risk_buf)
        risk_buf.clear()
        speak("Tank", "Risk Team", merged, "This is the risk team's debate (aggressive, conservative, neutral). Summarise it as one voice.")

    import json as _json
    thread = ta.begin_checkpoint(ticker, trade_date, asset_type, pc)   # framework checkpointing (resume support)
    resumed = bool(getattr(ta, "_resuming", False))
    try:
        with run_config(ta.config):
            init = ta.create_run_state(ticker, trade_date, asset_type=asset_type, portfolio=pc)
            config = {"analysts": analysts, "on_break": _on_break(analysts), "asset_type": asset_type, "trade_date": trade_date,
                      "past_date": past, "resumed": resumed,
                      "debate_rounds": team["debate_rounds"], "risk_rounds": team["risk_rounds"], "benchmark": bench,
                      "past_context": init.get("past_context") or "", "portfolio_context": init.get("portfolio_context") or "",
                      "portfolio_broker": pc_broker, "budget": budget, "reasoning": db.get_setting("reasoning_depth", "default"),
                      "optional_data": {"fred": bool(os.environ.get("FRED_API_KEY")), "alpha_vantage": bool(os.environ.get("ALPHA_VANTAGE_API_KEY")),
                                        "jev": bool(os.environ.get("TYPESAFE_API_KEY"))}}
            db.update_session(sid, config_json=_json.dumps(config))
            args = ta.propagator.get_graph_args()
            args["stream_mode"] = ["updates", "tasks"]
            if thread:
                args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = thread
            if resumed:
                # Replay what the interrupted run already finished, so every character still speaks in order.
                done_state = ta.graph.get_state({"configurable": {"thread_id": thread}}).values or {}
                final.update({k: v for k, v in done_state.items() if k != "messages"})
                em.put({"type": "resumed"})
                debate = done_state.get("investment_debate_state") or {}
                replay = [("Market Analyst", done_state.get("market_report")), ("Sentiment Analyst", done_state.get("sentiment_report")),
                          ("News Analyst", done_state.get("news_report")), ("Fundamentals Analyst", done_state.get("fundamentals_report")),
                          ("Bull Researcher", debate.get("bull_history")), ("Bear Researcher", debate.get("bear_history")),
                          ("Research Manager", done_state.get("investment_plan")), ("Trader", done_state.get("trader_investment_plan"))]
                for node, text in replay:
                    stop_point()   # replaying a resumed run's finished lines costs voice calls: stop at once
                    if text:
                        ch = NODE_CHARACTER[node]
                        started(ch, node)
                        again = prior_lines(sid, ticker, trade_date, node, text, lang)
                        if again is None:
                            speak(ch, node, text)
                            continue
                        # already voiced before the Stop: show the same lines again, no new model calls
                        last_said[node] = text
                        for r in again:
                            seq += 1
                            tid = db.add_turn(sid, seq, ch, node, r["detail_en"], r["line"] if lang == "ar" else None,
                                              r["line"] if lang == "en" else None)
                            em.put({"type": "agent_message", "character": ch, "node": node, "turn_id": tid, "text": r["line"],
                                    "lang": lang, "texts": {lang: r["line"]}})
                        em.put({"type": "agent_done", "character": ch, "node": node})
                        active.discard(ch)
            stop_point()
            stream = _cancellable(lambda: ta.graph.stream(ta.checkpoint_input(init), **args), ta.config, cancel)
            for mode, chunk in stream:
                if mode == "tasks":
                    node = chunk.get("name")
                    ch = NODE_CHARACTER.get(node)
                    if "input" in chunk and ch:
                        if node == "Portfolio Manager" or (ch != "Tank" and risk_buf):
                            flush_risk()
                        if node == "Portfolio Manager" and not albie_done:
                            albie_done = True
                            albie_link()
                        started(ch, node)
                    continue
                for node, delta in chunk.items():
                    if not isinstance(delta, dict):
                        continue
                    final.update(delta)
                    if node.startswith("tools_"):
                        _tool_sources(delta, cfg["data_vendors"], sources)
                        continue
                    out = _extract(node, delta)
                    if not out:
                        continue
                    ch = NODE_CHARACTER[node]
                    if node in RISK_NODES:
                        risk_buf.append((node, out))
                    elif node == "Portfolio Manager":
                        pass  # handled after the stream as the verdict
                    else:
                        speak(ch, node, out)
        ta.clear_checkpoint_on_success(ticker, trade_date, asset_type, pc)
    finally:
        # If Stop left the framework mid-step in its worker thread, that thread closes the checkpoint when it
        # finishes the step (so the run stays resumable); otherwise close it now.
        if not _defer_cleanup(locals().get("stream"), ta.end_checkpoint):
            ta.end_checkpoint()

    # The framework's own report tree (markdown files), offered as a download from the Report screen.
    try:
        export_dir = TA_HOME / "reports" / sid
        ta.save_reports({**init, **final}, ticker, save_path=export_dir)
        cfgd = db.get_session(sid).get("config") or {}
        cfgd["export_dir"] = str(export_dir)
        db.update_session(sid, config_json=_json.dumps(cfgd))
    except Exception as e:  # noqa: BLE001
        log.info("report export skipped: %s", type(e).__name__)

    flush_risk()
    decision = final.get("final_trade_decision") or ""
    rating = ta.process_signal(decision) if decision else "REVIEW"
    if cancel.is_set():
        raise _Cancelled()   # a stopped run must not enter the framework's decision memory
    try:
        ta.record_decision(ticker, trade_date, {**init, **final})
    except Exception as e:  # noqa: BLE001
        log.info("memory log skipped: %s", type(e).__name__)

    def verdict_job():
        try:
            return verdict_events()
        except Exception as e:  # noqa: BLE001
            # Never leave the office waiting: any failure here still ends the session.
            log.error("verdict failed: %s", scrub(repr(e)))
            db.update_session(sid, status="error", error=scrub(repr(e))[:500], finished_at=db.now())
            return [error_event(classify(e), lang, repr(e)), {"type": "end", "status": "error"}]

    def verdict_events():
        nonlocal seq
        seq += 1
        try:
            v = voice.verdict(ticker, rating, decision, lang)
        except Exception as e:  # noqa: BLE001
            log.info("verdict voice failed: %s", type(e).__name__)
            v = {"line": fallback_verdict(rating, lang), "reason": "", "conviction": "unstated"}
        tid = db.add_turn(sid, seq, "Leo", "Portfolio Manager", decision,
                          v["line"] if lang == "ar" else None, v["line"] if lang == "en" else None)
        if past:
            # A past-date analysis is priced at that day's close (real Yahoo close), not today's quote.
            p0, b0 = market.close_on_or_before(ticker, trade_date), market.close_on_or_before(bench, trade_date)
            px = {"price": p0, "spy": b0, "as_of": trade_date, "source": market.SOURCE + " (close)" if p0 else None}
        else:
            px = verdict_price(ticker, bench)
        usage = tracker.summary()
        verdict = {"rating": rating, "line": v["line"], "reason": v["reason"], "conviction": v["conviction"],
                   "lang": lang, "turn_id": tid, "sources": list(sources.values()),
                   "texts": {lang: {"line": v["line"], "reason": v["reason"]}},
                   "sentiment_note": "Social sentiment sources are fetched by the framework's sentiment analyst and cited in its report."}
        with STATUS_LOCK:   # Stop and the verdict can't both win: whichever comes first decides
            if cancel.is_set():
                return []   # stopped while Leo was speaking: keep the session "cancelled", don't record a verdict
            db.update_session(sid, status="done", finished_at=db.now(), rating=rating,
                              verdict_json=__import__("json").dumps(verdict),
                              price_at_verdict=px["price"], spy_at_verdict=px["spy"], price_time=px["as_of"],
                              price_source=px["source"], usage_json=__import__("json").dumps(usage),
                              cost_usd=usage["cost_usd"])
            em.verdict_in.set()
        return [{"type": "agent_message", "character": "Leo", "node": "Portfolio Manager", "turn_id": tid,
                 "text": v["line"], "lang": lang, "texts": {lang: v["line"]}},
                {"type": "verdict", **verdict, "price": px, "benchmark": bench, "disclaimer": DISCLAIMER[lang]},
                {"type": "agent_done", "character": "Leo", "node": "Portfolio Manager"},
                {"type": "usage", "data": usage},
                {"type": "end", "status": "done"}]

    em.put(pool.submit(verdict_job))
    pool.shutdown(wait=False)


def prior_lines(sid: str, ticker: str, trade_date: str, node: str, text: str, lang: str) -> list[dict] | None:
    """Lines the stopped run of this analysis already voiced for `node`, when a resumed run replays the same work:
    the run that was stopped (same stock and date), the same source text, and a line in this language. None when
    any of them is missing, so the caller voices it afresh."""
    col = "voice_ar" if lang == "ar" else "voice_en"
    prev = db.q1("SELECT id FROM sessions WHERE id<>? AND ticker=? AND trade_date=? AND mode='real' AND status IN ('cancelled','error') "
                 "ORDER BY created_at DESC LIMIT 1", (sid, ticker, trade_date))
    if not prev:
        return None
    rows = db.q(f"SELECT character, node, detail_en, {col} AS line FROM turns WHERE session_id=? AND node=? ORDER BY seq", (prev["id"], node))
    if not rows or any(not r["line"] or r["detail_en"].strip() not in text for r in rows):
        return None
    return rows


class _Cancelled(Exception):
    pass


class _CancellableStream:
    """Runs the framework's graph stream in a worker thread so Stop takes effect at once, even while one
    agent is in the middle of a long model call. The worker stops at the next step boundary."""

    def __init__(self, make, cfg: dict, cancel: threading.Event):
        self.q: queue.Queue = queue.Queue()
        self.cancel = cancel
        self.lock = threading.Lock()
        self.cleanup: Callable[[], None] | None = None
        self.finished = False

        def work():
            from tradingagents.dataflows.config import run_config
            try:
                with run_config(cfg):   # the framework's config lives in a context variable: set it in this thread
                    for item in make():
                        self.q.put(("item", item))
                        if cancel.is_set():
                            break
                self.q.put(("done", None))
            except BaseException as e:  # noqa: BLE001
                self.q.put(("err", e))
            finally:
                with self.lock:
                    self.finished = True
                    fn = self.cleanup
                try:
                    if fn:
                        fn()   # closes the checkpoint: the run key stays busy until this is done
                except Exception:  # noqa: BLE001
                    pass
                finally:
                    ACTIVE_STREAMS.pop(id(cancel), None)
        self.t = threading.Thread(target=work, daemon=True, name="graph-stream")
        self.t.start()

    def __iter__(self):
        while True:
            try:
                kind, val = self.q.get(timeout=0.25)
            except queue.Empty:
                if self.cancel.is_set():
                    raise _Cancelled() from None
                continue
            if self.cancel.is_set():
                raise _Cancelled()
            if kind == "item":
                yield val
            elif kind == "err":
                raise val
            else:
                return


def _cancellable(make, cfg: dict, cancel: threading.Event) -> _CancellableStream:
    st = _CancellableStream(make, cfg, cancel)
    with st.lock:
        if not st.finished:
            ACTIVE_STREAMS[id(cancel)] = st
    return st


def _defer_cleanup(stream, fn) -> bool:
    """Hand fn to a still-running stream worker. True if the worker will call it."""
    if not isinstance(stream, _CancellableStream):
        return False
    with stream.lock:
        if stream.finished:
            return False
        stream.cleanup = fn
        return True


def _on_break(analysts: list[str]) -> list[str]:
    return [ANALYST_CHARACTER[a] for a in ANALYSTS if a not in analysts]


# ---------------------------------------------------------------- demo session (clearly labelled)
DEMO_LINES = {
    "Ollie": ("[تجريبي] هذا مثال لطريقة كلامي: أشرح الشارت والمؤشرات بهدوء. في الجلسة الحقيقية أقرأ بيانات فعلية، هوو هوو!",
              "[Demo] This is how I'd sound: I walk through the chart and indicators calmly. In a real session I read actual data, hoot!"),
    "Buzz": ("[تجريبي] أنا أسمع وش يقول الناس عن السهم وأنقل لكم المزاج العام، بدون أرقام وهمية، بززز!",
             "[Demo] I listen to what people say about the stock and bring you the mood, no made-up numbers, bzzz!"),
    "Pip": ("[تجريبي] أنا أقرأ الأخبار وأبلغكم بالمهم منها. هنا ما في أخبار حقيقية لأنها جلسة تجريبية، سكوااك!",
            "[Demo] I read the news and flag what matters. No real headlines here because this is a demo, squawk!"),
    "Benny": ("[تجريبي] أنا أحسب الأرقام من القوائم المالية. في التجربة ما أعرض أرقام عشان ما نخترع شي، قرمش!",
              "[Demo] I crunch the financial statements. In the demo I show no figures so nothing is invented, chomp!"),
    "Bolt": ("[تجريبي] أنا أدافع عن فرصة الصعود وأجمع أقوى الحجج لها، مووو!",
             "[Demo] I argue the upside case and gather its strongest points, moo-ve!"),
    "Bruno": ("[تجريبي] وأنا أدافع عن سيناريو الهبوط وأطلع المخاطر اللي ممكن تفوتكم، غرر…",
              "[Demo] And I argue the downside and dig out the risks you might miss, grr…"),
    "Leo": ("[تجريبي] أوزن كلام الفريق كله قبل القرار.", "[Demo] I weigh the whole team before deciding."),
    "Tank": ("[تجريبي] فريق المخاطر يقول: خذ حذرك، المخاطر عالية والتذبذب كبير. حدّد حجم الدخول ووقف الخسارة قبل أي قرار. على مهلك… بثبات.",
             "[Demo] The risk team says: take care, the risk is high and so is the volatility. Set position size and stop-loss before any call. slow and steady."),
}
DEMO_ORDER = [("Ollie", "Market Analyst"), ("Buzz", "Sentiment Analyst"), ("Pip", "News Analyst"),
              ("Benny", "Fundamentals Analyst"), ("Bolt", "Bull Researcher"), ("Bruno", "Bear Researcher"),
              ("Leo", "Research Manager"), ("Tank", "Risk Team")]


def _run_demo(sid: str, ticker: str, lang: str, em: Emitter, cancel: threading.Event) -> None:
    trade_date = today_for(ticker)

    def nap(sec: float):
        if cancel.wait(sec):   # Stop interrupts the pause at once
            raise _Cancelled()
    em.put({"type": "session", "id": sid, "ticker": ticker, "mode": "demo", "lang": lang, "trade_date": trade_date,
            "provider": None, "quick_model": None, "deep_model": None,
            "estimate": {"known": True, "low": 0, "high": 0, "currency": "USD", "sessions": 1}})
    hist = market.history(ticker)
    em.put({"type": "market", "data": hist, "available": hist is not None})
    seq = 0
    team = team_settings()
    _sym, asset_type = resolve_instrument(ticker)
    off = _on_break(analysts_for(asset_type, team["analysts"]))
    db.update_session(sid, config_json=__import__("json").dumps({"analysts": analysts_for(asset_type, team["analysts"]), "on_break": off,
                                                                 "asset_type": asset_type, "benchmark": benchmark_for(ticker)}))
    em.put({"type": "team", "on_break": off, "asset_type": asset_type})
    for ch, node in DEMO_ORDER:
        if ch in off:
            continue
        if cancel.is_set():
            raise _Cancelled()
        em.put({"type": "agent_started", "character": ch, "node": node})
        nap(3.2)  # paced to roughly match the typewriter, so one character "thinks" at a time
        seq += 1
        ar, en = DEMO_LINES[ch]
        detail = f"[Demo] No analysis was run. {CHARACTERS[ch]['role']} output appears here in a real session."
        tid = db.add_turn(sid, seq, ch, node, detail, ar, en)
        em.put({"type": "agent_message", "character": ch, "node": node, "turn_id": tid, "text": ar if lang == "ar" else en, "lang": lang,
                "texts": {"ar": ar, "en": en}})
        em.put({"type": "agent_done", "character": ch, "node": node})
        nap(2.6)
    em.put({"type": "agent_started", "character": "Albie", "node": "Global Link"})
    nap(3.0)
    seq += 1
    a_ar = "[تجريبي] يا جماعة عندي لكم لفّة على العالم! في الجلسة الحقيقية أربط أخبار الصحف العالمية بحركة السهم. ريشتي تطير بالأخبار!"
    a_en = "[Demo] Fresh off the jet stream! In a real session I link world headlines from the big papers to this stock's move. feathers full of news!"
    tid_a = db.add_turn(sid, seq, "Albie", "Global Link", "[Demo] No global link was generated.", a_ar, a_en)
    em.put({"type": "agent_message", "character": "Albie", "node": "Global Link", "turn_id": tid_a, "text": a_ar if lang == "ar" else a_en,
            "lang": lang, "texts": {"ar": a_ar, "en": a_en}})
    em.put({"type": "agent_done", "character": "Albie", "node": "Global Link"})
    nap(2.6)
    em.put({"type": "agent_started", "character": "Leo", "node": "Portfolio Manager"})
    nap(1.2)
    line_ar = "[تجريبي] هنا أعلن القرار: شراء أو احتفاظ أو بيع، مع السبب ودرجة القناعة. هذي جلسة تجريبية وما فيها قرار حقيقي. زئير!"
    line_en = "[Demo] This is where I announce the call: buy, hold or sell, with the reason and conviction. This is a demo, so there is no real decision. roar!"
    seq += 1
    tid = db.add_turn(sid, seq, "Leo", "Portfolio Manager", "[Demo] No decision was made.", line_ar, line_en)
    px = verdict_price(ticker)
    verdict = {"rating": "DEMO", "line": line_ar if lang == "ar" else line_en,
               "reason": "جلسة تجريبية بدون تحليل حقيقي" if lang == "ar" else "Demo session, no real analysis",
               "texts": {"ar": {"line": line_ar, "reason": "جلسة تجريبية بدون تحليل حقيقي"},
                         "en": {"line": line_en, "reason": "Demo session, no real analysis"}},
               "conviction": "unstated", "lang": lang, "turn_id": tid, "sources": []}
    import json as _json
    db.update_session(sid, status="done", finished_at=db.now(), rating="DEMO", verdict_json=_json.dumps(verdict),
                      price_at_verdict=px["price"], spy_at_verdict=px["spy"], price_time=px["as_of"],
                      price_source=px["source"], usage_json=_json.dumps({"models": {}, "cost_usd": 0, "pricing_known": True}),
                      cost_usd=0)
    em.put({"type": "agent_message", "character": "Leo", "node": "Portfolio Manager", "turn_id": tid, "text": verdict["line"], "lang": lang,
            "texts": {"ar": line_ar, "en": line_en}})
    em.put({"type": "verdict", **verdict, "price": px, "disclaimer": DISCLAIMER[lang]})
    em.put({"type": "agent_done", "character": "Leo", "node": "Portfolio Manager"})
    em.put({"type": "usage", "data": {"models": {}, "cost_usd": 0, "pricing_known": True}})
    em.put({"type": "end", "status": "done"})


# ---------------------------------------------------------------- start / scans
# One real run per (stock, date, models): they share one framework checkpoint, so a second run at the same time
# would "resume" the first one's half-written state. A new Start attaches to the running one instead; while a
# stopped run's worker is still finishing its last step, a new one waits.
RUN_KEYS: dict[tuple, str] = {}
ACTIVE_STREAMS: dict[int, "_CancellableStream"] = {}   # id(cancel event) -> the stream worker still running
_run_lock = threading.Lock()


class StillStopping(Exception):
    """The previous run of this stock is still finishing its last step after Stop."""


WORKERS: set[str] = set()   # sessions whose worker thread (start-up, framework, voice, verdict) hasn't returned yet


def _key_busy(sid: str) -> str | None:
    """'running', 'stopping' or None for an earlier session holding a run key. A stopped run stays 'stopping'
    until its worker has returned and any framework step it left running has closed the checkpoint, including
    a Stop during start-up before the framework stream exists."""
    bus, cancel = BUSES.get(sid), CANCEL.get(sid)
    if bus is not None and not bus.closed and not (cancel is not None and cancel.is_set()):
        return "running"
    stopped = cancel is not None and cancel.is_set()   # a finished run already cleared its checkpoint
    if stopped and (sid in WORKERS or id(cancel) in ACTIVE_STREAMS):
        return "stopping"
    return None


PRUNE_AFTER_S = 1800


def prune(now: float | None = None) -> int:
    """Forget finished sessions' in-memory event lists after 30 minutes with no viewer (each holds the whole film
    plus price history; the desktop app can live in the tray for days). A later viewer gets it rebuilt from the
    database (app.ws_session). Scan buses are small and kept."""
    now = now or time.time()
    gone = 0
    for sid, bus in list(BUSES.items()):
        if bus.closed and bus.closed_at and now - bus.closed_at > PRUNE_AFTER_S and not bus.subs:
            BUSES.pop(sid, None)
            CANCEL.pop(sid, None)
            gone += 1
    with _run_lock:
        for k, sid in list(RUN_KEYS.items()):
            if sid not in BUSES:
                RUN_KEYS.pop(k, None)
    return gone


def start_session(loop: asyncio.AbstractEventLoop, ticker: str, lang: str, demo: bool,
                  scan_id: str | None = None, wait: bool = False, trade_date: str | None = None, budget: dict | None = None) -> str:
    prune()
    provider, quick, deep = settings_models()
    if not demo:
        # The instrument's own symbol (BTCUSD and BTC-USD share one framework checkpoint, so they share one run).
        key = (resolve_instrument(ticker)[0].upper(), trade_date or today_for(ticker), provider, quick, deep)
        with _run_lock:
            prev = RUN_KEYS.get(key)
            state = _key_busy(prev) if prev else None
            if state == "running":
                return prev          # the same analysis is already playing: follow it instead of paying twice
            if state == "stopping":
                raise StillStopping()
            sid = uuid.uuid4().hex[:12]
            RUN_KEYS[key] = sid
    else:
        sid = uuid.uuid4().hex[:12]
    db.create_session(sid, ticker, trade_date or today_for(ticker), "demo" if demo else "real",
                      None if demo else provider, None if demo else quick, None if demo else deep, lang, scan_id)
    BUSES[sid] = Bus(loop)
    CANCEL[sid] = threading.Event()
    WORKERS.add(sid)
    t = threading.Thread(target=_guarded, args=(sid, ticker, lang, demo, trade_date, budget), daemon=True, name=f"session-{sid}")
    t.start()
    if wait:
        t.join()
    return sid


def _guarded(sid, ticker, lang, demo, trade_date=None, budget=None):
    try:
        run_session(sid, ticker, lang, demo, trade_date, budget)
    finally:
        WORKERS.discard(sid)


SCAN_BUSES: dict[str, Bus] = {}
SKIP_WAIT_STEPS = 400   # × 0.3 s: how long a scan waits for a stopped run of the same stock to finish
SCAN_CANCEL: dict[str, threading.Event] = {}


def start_scan(loop: asyncio.AbstractEventLoop, kind: str, tickers: list[str], screener: str | None,
               source: list[dict] | None, lang: str, demo: bool, budget: dict | None = None, reuse: bool = False) -> str:
    """Analyse several tickers one after another, then rank them. Each is a full session."""
    scan_id = uuid.uuid4().hex[:12]
    db.create_scan(scan_id, kind, screener, tickers, source, lang, "demo" if demo else "real")
    bus = SCAN_BUSES[scan_id] = Bus(loop)
    stop = SCAN_CANCEL[scan_id] = threading.Event()

    joined: set[str] = set()   # runs this scan follows but didn't start (the same analysis was already playing)

    def work():
        try:
            run()
        except Exception as e:  # noqa: BLE001
            # e.g. "database is locked": never leave the scan "running" with its viewers waiting forever
            log.error("scan %s failed: %s", scan_id, scrub(repr(e)))
            for sid in [e2["session_id"] for e2 in bus.events if e2["type"] == "scan_session"]:
                if sid not in joined:
                    cancel_session(sid)
            db.update_scan(scan_id, status="error")
            bus.publish(error_event(classify(e), lang, repr(e)))
            bus.publish({"type": "end", "status": "error"})

    def run():
        bus.publish({"type": "scan", "id": scan_id, "kind": kind, "screener": screener, "tickers": tickers,
                     "source": source})
        for i, t in enumerate(tickers):
            if stop.is_set():
                break
            from . import budget as spend_cap, extras   # not "budget": that name is this scan's amount to invest
            old = extras.reusable(t) if reuse else None
            if not old and not demo and spend_cap.blocked(spend_cap.next_run_high()):
                bus.publish({"type": "scan_capped", "index": i, "spend": spend_cap.spent()})
                break   # this month's cap is reached: no more paid sessions
            if old:
                # Already analysed today with these models: show that result again instead of paying twice.
                sid = old["id"]
                if sid not in BUSES or not BUSES[sid].closed:
                    BUSES[sid] = Bus(loop)
                    extras.replay(sid)
                bus.publish({"type": "scan_session", "index": i, "ticker": t, "session_id": sid, "reused": True})
                db.set_setting(f"scan_extra:{scan_id}", (db.get_setting(f"scan_extra:{scan_id}") or []) + [sid])
            else:
                sid = None
                for _ in range(SKIP_WAIT_STEPS):   # the same stock's stopped run is finishing its last step: wait for it
                    try:
                        sid = start_session(loop, t, lang, demo, scan_id=scan_id, budget=budget)
                        break
                    except StillStopping:
                        if stop.is_set():
                            break
                        time.sleep(0.3)
                if sid is None:
                    if stop.is_set():
                        break
                    # An earlier stopped run of this stock is still finishing its last model step: skip this one
                    # stock rather than failing (and cancelling) the whole scan.
                    bus.publish({"type": "scan_skipped", "index": i, "ticker": t, "reason": "still_stopping"})
                    continue
                if (db.get_session(sid) or {}).get("scan_id") != scan_id:
                    # Someone else's run of the same analysis: count it as this scan's result, and never stop it.
                    joined.add(sid)
                    db.set_setting(f"scan_extra:{scan_id}", (db.get_setting(f"scan_extra:{scan_id}") or []) + [sid])
                bus.publish({"type": "scan_session", "index": i, "ticker": t, "session_id": sid, "joined": sid in joined})
            while not BUSES[sid].closed:
                if stop.is_set():
                    if sid in joined:
                        break   # stop following it; the run itself belongs to whoever started it
                    cancel_session(sid)
                time.sleep(0.3)
            s = db.get_session(sid)
            bus.publish({"type": "scan_result", "index": i, "ticker": t, "session_id": sid,
                         "status": s["status"], "rating": s["rating"]})
            if s["status"] == "error" and s.get("error") in ("no_key",):
                break  # nothing else can succeed without a key
        shown = [e["session_id"] for e in bus.events if e["type"] == "scan_session"]
        ranked = rank([x for x in (db.get_session(i) for i in shown) if x])
        db.update_scan(scan_id, status="cancelled" if stop.is_set() else "done")
        bus.publish({"type": "scan_ranked", "ranking": [{"ticker": s["ticker"], "rating": s["rating"],
                                                          "session_id": s["id"], "status": s["status"]} for s in ranked]})
        bus.publish({"type": "end", "status": "done"})

    threading.Thread(target=work, daemon=True, name=f"scan-{scan_id}").start()
    return scan_id


STATUS_LOCK = threading.Lock()


def cancel_session(sid: str) -> bool:
    """Stop now: the session ends for every viewer and in the database at once, whatever the worker is doing
    (a model call, fetching data at start-up, building the team). The worker notices at its next step and
    winds down; nothing it produces after this reaches the screen. A verdict already recorded stays."""
    ev = CANCEL.get(sid)
    if not ev:
        return False
    with STATUS_LOCK:
        ev.set()
        s = db.get_session(sid)
        if s and s["status"] == "running":
            db.update_session(sid, status="cancelled", finished_at=db.now())
            bus = BUSES.get(sid)
            if bus is not None and not bus.closed:
                bus.publish(error_event("cancelled", s["lang"]))
                bus.publish({"type": "end", "status": "cancelled"})
    return True


def rank(sessions: list[dict]) -> list[dict]:
    """Order finished scan sessions from most bullish to most bearish; REVIEW/errors last."""
    def key(s):
        r = s.get("rating")
        return RATING_ORDER.index(r) if r in RATING_ORDER else 99
    return sorted(sessions, key=key)
