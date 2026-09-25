"""Veyro local server: REST + WebSocket API and the built frontend."""
from __future__ import annotations

import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import assistant, db, market, runner, world
from .config import CHARACTERS, LIST_BASE, MAX_BATCH, MAX_SCREEN, PRICING, PROVIDERS, RECOMMEND, ROOT, STATIC_DIR
from .execution import service as exec_service
from .execution.routes import router as exec_router
from .anthropic_relay import router as relay_router
from .secrets_store import ScrubFilter, delete_secret, get_secret, llm_key, mask, scrub, set_secret

load_dotenv(ROOT / ".env")  # development only; keys entered in the app live in the OS keyring

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for h in logging.getLogger().handlers:
    h.addFilter(ScrubFilter())
log = logging.getLogger("veyro")

TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-=^]{0,14}$")


MAIN_LOOP: asyncio.AbstractEventLoop | None = None   # event loop for session buses when work runs in a worker thread


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()
    db.conn()
    db.mark_orphans()
    exec_service.init()
    assistant.init()
    sched = assistant.Scheduler(asyncio.get_running_loop())
    if os.environ.get("VEYRO_NO_SCHEDULER") != "1":
        sched.start()
    from .lazy import warm_up
    warm_up()
    yield
    sched.stop.set()


app = FastAPI(title="Veyro", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


app.include_router(exec_router)
app.include_router(relay_router)


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def _loopback_host(host: str) -> bool:
    """Veyro only serves loopback names. A foreign Host means DNS rebinding (a website whose name was re-pointed
    at 127.0.0.1 sends a matching Origin, so the Origin test alone can't stop it)."""
    name = host.rsplit(":", 1)[0] if not host.endswith("]") else host
    return name.lower() in LOOPBACK_HOSTS


@app.middleware("http")
async def same_origin_only(request, call_next):
    """Changes can only come from Veyro's own page: another website open in the browser can't drive the
    local API (requests without an Origin header, e.g. local tools, are allowed)."""
    if not _loopback_host(request.headers.get("host", "")):
        return JSONResponse({"error": "host"}, status_code=403)
    if request.method in ("POST", "PUT", "DELETE", "PATCH") and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        if origin and not _same_origin(origin, request.headers.get("host", "")):
            return JSONResponse({"error": "origin"}, status_code=403)
    return await call_next(request)


def _same_origin(origin: str, host: str) -> bool:
    from urllib.parse import urlparse
    o = urlparse(origin)
    return o.scheme in ("http", "https") and bool(host) and o.netloc == host


def _ws_ok(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    host = ws.headers.get("host", "")
    return _loopback_host(host) and (not origin or _same_origin(origin, host))


@app.exception_handler(Exception)
async def _unhandled(_req, exc: Exception):
    log.error("unhandled: %s", scrub(repr(exc)))
    return JSONResponse({"error": "internal"}, status_code=500)


def _ticker(t: str) -> str:
    t = (t or "").strip().upper()
    if not TICKER_RE.match(t):
        raise HTTPException(400, "invalid_ticker")
    return t


# ---------------------------------------------------------------- settings & keys
class SettingsIn(BaseModel):
    provider: str | None = None
    quick_model: str | None = None
    deep_model: str | None = None
    analysts: list[str] | None = None
    debate_rounds: int | None = None
    risk_rounds: int | None = None
    reasoning_depth: str | None = None
    anthropic_workspace_id: str | None = None
    data_source: str | None = None
    monthly_cap_usd: float | None = None   # 0 = no cap
    custom_model: bool = False   # the user typed a model ID that isn't in the framework's list


def settings_payload() -> dict:
    provider, quick, deep = runner.settings_models()
    keys = {}
    for p in PROVIDERS:
        k, src = llm_key(p)
        keys[p] = {"present": bool(k), "masked": mask(k), "source": src}
    return {
        "provider": provider, "quick_model": quick, "deep_model": deep,
        "providers": {p: {"label": v["label"], "quick": v["quick"], "deep": v["deep"], "extra": bool(v.get("extra")),
                          "needs_key": v["env"] is not None, "listable": p in LIST_BASE or p in ("anthropic", "ollama"),
                          "recommend": RECOMMEND.get(p)} for p, v in PROVIDERS.items()},
        "keys": keys,
        "pricing": {m: list(v) for m, v in PRICING.items()},
        "limits": {"batch": MAX_BATCH, "screen": MAX_SCREEN},
        "spend": __import__("veyro.budget", fromlist=["x"]).spent(),
        "data_source": __import__("veyro.datasources", fromlist=["x"]).current(),
        "estimate": runner.estimate(provider, quick, deep),
        "team": runner.team_settings(),
        "reasoning_depth": db.get_setting("reasoning_depth", "default"),
        "anthropic_workspace_id": db.get_setting("anthropic_workspace_id"),
        "data_keys": {k: {"present": bool(get_secret(f"data:{k}")), "masked": mask(get_secret(f"data:{k}"))}
                      for k in ("fred", "alpha_vantage", "typesafe")},
    }


@app.get("/api/settings")
def get_settings():
    return settings_payload()


@app.put("/api/settings")
def put_settings(s: SettingsIn):
    provider = s.provider or runner.settings_models()[0]
    if provider not in PROVIDERS:
        raise HTTPException(400, "unknown_provider")
    db.set_setting("provider", provider)
    for role, value in (("quick", s.quick_model), ("deep", s.deep_model)):
        if not value:
            continue
        value = value.strip()
        known = value in PROVIDERS[provider][role]
        if not known and not (s.custom_model and runner.MODEL_ID_RE.match(value)):
            raise HTTPException(400, "unknown_model")
        db.set_setting(f"{role}_model:{provider}", value)
    if s.analysts is not None:
        a = [x for x in runner.ANALYSTS if x in s.analysts]
        if not a:
            raise HTTPException(400, "need_one_analyst")
        db.set_setting("team_analysts", a)
    if s.debate_rounds is not None:
        db.set_setting("team_debate_rounds", max(1, min(3, s.debate_rounds)))
    if s.risk_rounds is not None:
        db.set_setting("team_risk_rounds", max(1, min(3, s.risk_rounds)))
    if s.anthropic_workspace_id is not None:
        ws = s.anthropic_workspace_id.strip()
        if ws and not re.fullmatch(r"wrkspc_[A-Za-z0-9]{8,64}", ws):
            raise HTTPException(400, "bad_workspace")
        db.set_setting("anthropic_workspace_id", ws or None)
    if s.monthly_cap_usd is not None:
        if not 0 <= s.monthly_cap_usd <= 100000:
            raise HTTPException(400, "bad_cap")
        db.set_setting("monthly_cap_usd", s.monthly_cap_usd or None)
    if s.data_source is not None:
        from .datasources import SOURCES
        if s.data_source not in SOURCES:
            raise HTTPException(400, "bad_source")
        db.set_setting("data_source", s.data_source)
    if s.reasoning_depth is not None:
        if s.reasoning_depth not in ("default", "low", "medium", "high"):
            raise HTTPException(400, "bad_depth")
        db.set_setting("reasoning_depth", s.reasoning_depth)
    return settings_payload()


class DataKeyIn(BaseModel):
    source: str
    key: str = Field(min_length=6, max_length=200)


@app.post("/api/data_keys")
def save_data_key(k: DataKeyIn):
    if k.source not in ("fred", "alpha_vantage", "typesafe") or any(c.isspace() for c in k.key.strip()):
        raise HTTPException(400, "bad_key")
    set_secret(f"data:{k.source}", k.key.strip())
    return settings_payload()


@app.delete("/api/data_keys/{source}")
def delete_data_key(source: str):
    if source not in ("fred", "alpha_vantage", "typesafe"):
        raise HTTPException(400, "bad_key")
    delete_secret(f"data:{source}")
    runner.unset_env({"fred": "FRED_API_KEY", "alpha_vantage": "ALPHA_VANTAGE_API_KEY", "typesafe": "TYPESAFE_API_KEY"}[source])
    return settings_payload()


class KeyIn(BaseModel):
    provider: str
    key: str = Field(min_length=10, max_length=400)


@app.post("/api/keys")
def save_key(k: KeyIn):
    if k.provider not in PROVIDERS or PROVIDERS[k.provider]["env"] is None:
        raise HTTPException(400, "unknown_provider")
    value = k.key.strip()
    if any(c.isspace() for c in value):
        raise HTTPException(400, "invalid_key")
    set_secret(f"llm:{k.provider}", value)
    return {**settings_payload(), "test": test_connection(k.provider)}  # masked only, plus a live check


def test_connection(provider: str | None = None) -> dict:
    """One tiny real call with the saved key and the chosen models. Never returns the key."""
    import os
    provider = provider or runner.settings_models()[0]
    prov, quick, deep = runner.settings_models()
    if provider != prov:
        quick, deep = PROVIDERS[provider]["default_quick"], PROVIDERS[provider]["default_deep"]
    key, _ = llm_key(provider)
    if not key:
        return {"ok": False, "code": "no_key", "models": {}, "provider": PROVIDERS[provider]["label"]}
    if PROVIDERS[provider]["env"]:
        runner.activate_key(provider, key)
    from .voice import Voice
    results = {}
    for role, model in (("quick", quick), ("deep", deep)):
        if not model:
            results[role] = {"model": "—", "ok": False, "code": "model"}
            continue
        try:
            Voice(provider, model)._ask("Reply with the single word OK.", "ping")
            results[role] = {"model": model, "ok": True}
        except Exception as e:  # noqa: BLE001
            results[role] = {"model": model, "ok": False, "code": runner.classify(e)}
    ok = all(r["ok"] for r in results.values())
    first_err = next((r["code"] for r in results.values() if not r["ok"]), None)
    return {"ok": ok, "code": first_err, "models": results, "provider": PROVIDERS[provider]["label"],
            "workspace": bool(db.get_setting("anthropic_workspace_id"))}


@app.post("/api/keys/test")
def keys_test():
    r = test_connection()
    return r if r["ok"] else JSONResponse(r)


@app.get("/api/models/live")
def live_models(provider: str = "anthropic"):
    """The models the saved key can actually use, straight from the provider, so the owner can pick any of
    them (not only the ones Veyro ships with). Claude: Anthropic Models API; Ollama: the local model list;
    OpenAI-compatible providers: their /models endpoint."""
    if provider not in PROVIDERS:
        raise HTTPException(400, "unknown_provider")
    key, _ = llm_key(provider)
    if not key:
        return JSONResponse({"ok": False, "code": "no_key"})
    try:
        if provider == "anthropic":
            import anthropic
            from .anthropic_relay import base_url as relay_url
            client = anthropic.Anthropic(api_key=key, base_url=relay_url(), max_retries=1, timeout=20)
            models = [{"id": m.id, "name": m.display_name} for m in client.models.list(limit=100)]
        elif provider == "ollama":
            import httpx
            base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/").removesuffix("/v1")
            r = httpx.get(f"{base}/api/tags", timeout=10)
            r.raise_for_status()
            models = [{"id": m["name"], "name": m["name"]} for m in r.json().get("models", [])]
        elif provider in LIST_BASE:
            import openai
            client = openai.OpenAI(api_key=key, base_url=LIST_BASE[provider], max_retries=1, timeout=20)
            models = sorted(({"id": m.id, "name": m.id} for m in client.models.list()), key=lambda m: m["id"])
        else:
            return JSONResponse({"ok": False, "code": "not_listable"})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "code": runner.classify(e)})
    return {"models": models[:500]}


@app.delete("/api/keys/{provider}")
def remove_key(provider: str):
    if provider not in PROVIDERS:
        raise HTTPException(400, "unknown_provider")
    delete_secret(f"llm:{provider}")
    if PROVIDERS[provider]["env"]:
        runner.unset_env(PROVIDERS[provider]["env"])
    return settings_payload()


# ---------------------------------------------------------------- market
@app.get("/api/market/status")
def market_status():
    s = market.market_status()
    return s or {"open": None, "status": "unavailable"}


@app.get("/api/market/history/{ticker}")
def market_history(ticker: str):
    h = market.history(_ticker(ticker))
    if not h:
        return {"available": False}
    return {"available": True, **h}


@app.get("/api/market/search")
def market_search(q: str = ""):
    """Find a ticker by company name (Arabic or English) or symbol."""
    q = q.strip()
    if not 1 <= len(q) <= 60:
        return {"results": []}
    return {"results": [r for r in market.search(q, 8) if TICKER_RE.match(r["symbol"])]}


@app.get("/api/market/screeners")
def screeners():
    return {"screeners": market.SCREENERS}


@app.get("/api/market/screen/{screener}")
def run_screen(screener: str, count: int = 5, budget: float | None = None, currency: str = "USD"):
    if screener not in market.SCREENERS:
        raise HTTPException(400, "unknown_screener")
    try:
        return {"available": True, "candidates": market.screen(screener, max(1, min(count, MAX_SCREEN)),
                                                               _max_price(_budget(budget, currency)))}
    except market.MarketDataUnavailable:
        return {"available": False, "candidates": []}


# ---------------------------------------------------------------- sessions
class SessionIn(BaseModel):
    ticker: str
    lang: str = "ar"
    demo: bool = False
    trade_date: str | None = None   # YYYY-MM-DD, today or earlier (point-in-time analysis)
    budget: float | None = None     # money the owner wants to invest; the Portfolio Manager sees it as free cash
    budget_currency: str = "USD"


def _budget(amount: float | None, currency: str) -> dict | None:
    if amount is None or amount <= 0:
        return None
    if currency not in ("USD", "SAR") or amount > 1e10:
        raise HTTPException(400, "bad_budget")
    return {"amount": round(float(amount), 2), "currency": currency}


def _cap_reached():
    """Refuse new paid analyses once this month's cap is reached (demo runs are free and always allowed)."""
    from . import budget
    if budget.blocked():
        return JSONResponse({"ok": False, "code": "budget_cap", "spend": budget.spent()})
    return None


def _max_price(b: dict | None) -> float | None:
    """The budget in USD (screeners list US stocks), so only affordable candidates are suggested."""
    if not b:
        return None
    from .allocation import fx
    rate = fx(b["currency"], "USD")
    return b["amount"] * rate if rate else None


def _trade_date(d: str | None) -> str | None:
    if not d:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) or not ("2005-01-01" <= d <= runner.ny_today()):
        raise HTTPException(400, "bad_date")
    return d


@app.post("/api/sessions")
async def create_session(s: SessionIn):
    if s.lang not in ("ar", "en"):
        raise HTTPException(400, "invalid_lang")
    t = _ticker(s.ticker)
    if not s.demo and (r := _cap_reached()):
        return r
    sid = runner.start_session(asyncio.get_running_loop(), t, s.lang, s.demo, trade_date=_trade_date(s.trade_date),
                               budget=_budget(s.budget, s.budget_currency))
    return {"id": sid}


@app.post("/api/sessions/{sid}/cancel")
def cancel(sid: str):
    return {"ok": runner.cancel_session(sid)}


@app.get("/api/sessions")
def sessions(light: bool = False):
    rows = db.list_sessions()
    if light:   # ids and status only, no live prices (fast)
        return {"sessions": [{"id": r["id"], "status": r["status"], "ticker": r["ticker"]} for r in rows]}
    _prefetch_prices(rows)
    return {"sessions": [enrich(r) for r in rows]}


def _prefetch_prices(rows: list[dict]) -> None:
    """Warm the quote cache for every distinct ticker/benchmark in parallel (was one slow call per row)."""
    from concurrent.futures import ThreadPoolExecutor
    syms = {r["ticker"] for r in rows if r.get("status") == "done"}
    syms |= {((r.get("config") or {}).get("benchmark")) or runner.benchmark_for(r["ticker"]) for r in rows if r.get("status") == "done"}
    if syms:
        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(market.last_price, syms))


def enrich(r: dict) -> dict:
    """Add price-now and SPY-now from real data, and the returns over the same period."""
    out = dict(r)
    bench = ((r.get("config") or {}).get("benchmark")) or runner.benchmark_for(r["ticker"])
    out["benchmark"] = bench
    now_px = market.last_price(r["ticker"]) if r.get("status") == "done" else None
    spy_now = market.last_price(bench) if r.get("status") == "done" else None
    out["price_now"] = now_px["price"] if now_px else None
    out["spy_now"] = spy_now["price"] if spy_now else None
    out["ret"] = (out["price_now"] / r["price_at_verdict"] - 1) if out["price_now"] and r.get("price_at_verdict") else None
    out["spy_ret"] = (out["spy_now"] / r["spy_at_verdict"] - 1) if out["spy_now"] and r.get("spy_at_verdict") else None
    return out


@app.get("/api/sessions/{sid}")
def session(sid: str):
    s = db.get_session(sid)
    if not s:
        raise HTTPException(404, "not_found")
    return s


class TranslateIn(BaseModel):
    what: str  # 'detail_ar' | 'voice_ar' | 'voice_en'


@app.post("/api/turns/{tid}/translate")
def translate(tid: int, body: TranslateIn):
    """Lazily create the Arabic detail or the missing-language voice line for a turn."""
    t = db.q1("SELECT t.*, s.ticker, s.mode FROM turns t JOIN sessions s ON s.id=t.session_id WHERE t.id=?", (tid,))
    if not t:
        raise HTTPException(404, "not_found")
    if body.what not in ("detail_ar", "voice_ar", "voice_en"):
        raise HTTPException(400, "bad_field")
    if t.get(body.what):
        return {body.what: t[body.what]}
    if t["mode"] == "demo":
        return JSONResponse({"ok": False, "code": "demo"})
    provider, quick, _ = runner.settings_models()
    key, _ = llm_key(provider)
    if not key:
        return JSONResponse({"ok": False, "code": "no_key"})
    import os
    runner.activate_key(provider, key)
    from .voice import Voice
    v = Voice(provider, quick)
    try:
        if body.what == "detail_ar":
            val = v.translate_detail(t["detail_en"])
        else:
            lang = body.what[-2:]
            val = v.speak(t["character"], t["ticker"], t["detail_en"], lang)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "code": runner.classify(e)})
    db.update_turn(tid, **{body.what: val})
    return {body.what: val}


class VerdictTextIn(BaseModel):
    lang: str


@app.post("/api/sessions/{sid}/verdict_text")
def verdict_text(sid: str, body: VerdictTextIn):
    """Leo's verdict line + reason in the requested language, voiced in character (cached)."""
    if body.lang not in ("ar", "en"):
        raise HTTPException(400, "invalid_lang")
    s = db.get_session(sid)
    if not s or not s.get("verdict"):
        return JSONResponse({"ok": False, "code": "not_found"})
    v = s["verdict"]
    texts = v.get("texts") or {}
    if body.lang in texts:
        return texts[body.lang]
    if s["mode"] == "demo" or s["rating"] in (None, "DEMO"):
        return JSONResponse({"ok": False, "code": "demo"})
    pm = next((t for t in reversed(s["turns"]) if t["node"] == "Portfolio Manager"), None)
    if not pm:
        return JSONResponse({"ok": False, "code": "no_decision"})
    provider, quick, _ = runner.settings_models()
    key, _ = llm_key(provider)
    if not key:
        return JSONResponse({"ok": False, "code": "no_key"})
    import json
    import os
    runner.activate_key(provider, key)
    from .voice import Voice
    try:
        out = Voice(provider, quick).verdict(s["ticker"], s["rating"], pm["detail_en"], body.lang)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "code": runner.classify(e)})
    texts[body.lang] = {"line": out["line"], "reason": out["reason"]}
    v["texts"] = texts
    db.update_session(sid, verdict_json=json.dumps(v))
    return texts[body.lang]


# ---------------------------------------------------------------- scans
class ScanIn(BaseModel):
    kind: str  # 'watchlist' | 'screener'
    tickers: list[str] = []
    reuse: bool = True              # reopen today's finished analysis of a stock instead of paying again
    economy_top: int | None = None  # economy mode: free price pre-screen, full analysis only on the best N
    screener: str | None = None
    count: int = 3
    lang: str = "ar"
    demo: bool = False
    budget: float | None = None
    budget_currency: str = "USD"


def _loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return MAIN_LOOP


# Plain "def": the pre-screen, screeners and FX lookups are network calls; FastAPI runs this in a worker
# thread so the event loop (and every live WebSocket) keeps flowing meanwhile.
@app.post("/api/scans")
def create_scan(s: ScanIn):
    if s.lang not in ("ar", "en"):
        raise HTTPException(400, "invalid_lang")
    if not s.demo and (r := _cap_reached()):
        return r
    source = None
    if s.kind == "watchlist":
        tickers = list(dict.fromkeys(_ticker(t) for t in s.tickers))
        if not 1 <= len(tickers) <= MAX_BATCH:
            raise HTTPException(400, "watchlist_size")
    elif s.kind == "screener":
        if s.screener not in market.SCREENERS:
            raise HTTPException(400, "unknown_screener")
        try:
            source = market.screen(s.screener, max(1, min(s.count, MAX_SCREEN)), _max_price(_budget(s.budget, s.budget_currency)))
        except market.MarketDataUnavailable:
            raise HTTPException(502, "screener_unavailable") from None
        tickers = [c["symbol"] for c in source]
    else:
        raise HTTPException(400, "bad_kind")
    prescreen = None
    if s.economy_top and 0 < s.economy_top < len(tickers):
        from . import extras
        prescreen = extras.prescreen(tickers)
        tickers = [r["ticker"] for r in prescreen if r["score"] is not None][:s.economy_top] or tickers[:s.economy_top]
    scan_id = runner.start_scan(_loop(), s.kind, tickers, s.screener, source, s.lang, s.demo,
                                budget=_budget(s.budget, s.budget_currency), reuse=s.reuse and not s.demo)
    return {"id": scan_id, "tickers": tickers, "source": source, "prescreen": prescreen,
            "estimate": runner.estimate(*runner.settings_models(), sessions=len(tickers)) if not s.demo else None}


@app.get("/api/scans")
def scans():
    return {"scans": db.list_scans()}


@app.get("/api/scans/{scan_id}")
def scan(scan_id: str):
    s = db.get_scan(scan_id)
    if not s:
        raise HTTPException(404, "not_found")
    s["sessions"] = runner.rank(s["sessions"])
    return s


@app.get("/api/scans/{scan_id}/allocation")
def scan_allocation(scan_id: str, budget: float, currency: str = "USD"):
    """Leo's budget plan across a finished watchlist or scan."""
    from . import allocation
    b = _budget(budget, currency)
    s = db.get_scan(scan_id)
    if not s or not b:
        raise HTTPException(404, "not_found")
    return allocation.plan(s["sessions"], b["amount"], b["currency"])


@app.get("/api/sessions/{sid}/allocation")
def session_allocation(sid: str, budget: float, currency: str = "USD"):
    from . import allocation
    b = _budget(budget, currency)
    s = db.get_session(sid)
    if not s or not b:
        raise HTTPException(404, "not_found")
    return allocation.plan([s], b["amount"], b["currency"])


@app.post("/api/scans/{scan_id}/cancel")
def cancel_scan(scan_id: str):
    ev = runner.SCAN_CANCEL.get(scan_id)
    if ev:
        ev.set()
    return {"ok": bool(ev)}


# ---------------------------------------------------------------- websockets
async def _pump(ws: WebSocket, bus: runner.Bus | None):
    if not _ws_ok(ws):
        await ws.close(code=1008)
        return
    await ws.accept()
    if bus is None:
        await ws.send_json({"type": "error", "code": "not_found"})
        await ws.close()
        return
    q, backlog = bus.subscribe()
    try:
        for ev in backlog:
            await ws.send_json(ev)
        if not (backlog and backlog[-1]["type"] == "end"):
            while True:
                ev = await q.get()
                await ws.send_json(ev)
                if ev["type"] == "end":
                    break
        await ws.close()
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(q)


@app.websocket("/ws/sessions/{sid}")
async def ws_session(ws: WebSocket, sid: str):
    await _pump(ws, runner.BUSES.get(sid))


@app.websocket("/ws/scans/{scan_id}")
async def ws_scan(ws: WebSocket, scan_id: str):
    await _pump(ws, runner.SCAN_BUSES.get(scan_id))


# ---------------------------------------------------------------- live board
@app.get("/api/live/catalog")
def live_catalog():
    from . import beginner, live
    mk = beginner.market_status("both")
    y = market.market_status()          # Yahoo knows US holidays; prefer it over regular hours when available
    if y and y.get("open") is not None:
        mk["us"]["open"] = bool(y["open"])
    return {**live.catalog(), "markets": mk}


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    """Streams quote updates for the symbols the screen asks for ({"want": [...]}), batched every 250 ms."""
    from . import live
    if not _ws_ok(ws):
        await ws.close(code=1008)
        return
    await ws.accept()
    hub = live.HUB
    hub.start()
    loop = asyncio.get_running_loop()
    q, snap = hub.subscribe(loop, set())

    async def reader():
        while True:
            msg = await ws.receive_json()
            want = {str(x)[:20].upper() for x in (msg.get("want") or [])[:120] if TICKER_RE.match(str(x).upper()) or str(x).upper() in live.GOLD_G or str(x).upper() in live.base_symbols()}
            hub.add_symbols({w for w in want if w not in live.GOLD_G})
            await ws.send_json({"type": "snapshot", "quotes": hub.update_want(q, want), "stream": hub.stream_ok})

    rtask = asyncio.create_task(reader())
    try:
        while not rtask.done():
            try:
                batch = await asyncio.wait_for(q.get(), timeout=10)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping", "stream": hub.stream_ok})
                continue
            await asyncio.sleep(0.25)          # gather a burst of ticks into one frame
            while not q.empty():
                batch += q.get_nowait()
            latest = {x["symbol"]: x for x in batch}
            await ws.send_json({"type": "ticks", "quotes": list(latest.values()), "stream": hub.stream_ok})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        rtask.cancel()
        hub.unsubscribe(q)


# ---------------------------------------------------------------- Albie: world news
@app.get("/api/world/news")
def world_news(lang: str = "ar"):
    if lang not in ("ar", "en"):
        raise HTTPException(400, "invalid_lang")
    return world.news(lang)


@app.get("/api/world/markets")
def world_markets():
    return world.markets()


class WorldIn(BaseModel):
    lang: str = "ar"
    ticker: str | None = None


def _llm_ready():
    provider, quick, _ = runner.settings_models()
    key, _ = llm_key(provider)
    if not key:
        return None
    import os
    runner.activate_key(provider, key)
    return provider, quick


@app.post("/api/world/briefing")
def world_briefing(body: WorldIn):
    if body.lang not in ("ar", "en"):
        raise HTTPException(400, "invalid_lang")
    ready = _llm_ready()
    if not ready:
        return JSONResponse({"ok": False, "code": "no_key"})
    try:
        return {"text": world.briefing(body.lang, *ready)}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "code": runner.classify(e)})


class SearchIn(BaseModel):
    q: str = Field(min_length=2, max_length=120)
    lang: str = "ar"


@app.get("/api/world/search")
def world_search(q: str, lang: str = "ar"):
    if lang not in ("ar", "en") or not (2 <= len(q) <= 120):
        raise HTTPException(400, "bad_query")
    return world.search(q, lang)


@app.post("/api/world/analyze")
def world_analyze(body: SearchIn):
    if body.lang not in ("ar", "en"):
        raise HTTPException(400, "invalid_lang")
    ready = _llm_ready()
    found = world.search(body.q, body.lang)
    if not ready:
        return JSONResponse({"ok": False, "code": "no_key", "items": found["items"]})
    try:
        return world.analyze(body.q, body.lang, *ready)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "code": runner.classify(e)})


@app.post("/api/world/link")
def world_link(body: WorldIn):
    if body.lang not in ("ar", "en"):
        raise HTTPException(400, "invalid_lang")
    t = _ticker(body.ticker or "")
    ready = _llm_ready()
    if not ready:
        return JSONResponse({"ok": False, "code": "no_key"})
    move = world.stock_move(t)
    try:
        return {"text": world.link(t, body.lang, *ready, move), "move": move, "ticker": t}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "code": runner.classify(e)})


# ---------------------------------------------------------------- the framework's own memory, backtests, exports
def _framework_cfg() -> dict:
    from tradingagents.default_config import DEFAULT_CONFIG
    import copy
    from .config import TA_HOME
    provider, quick, deep = runner.settings_models()
    team = runner.team_settings()
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    from .anthropic_relay import base_url as relay_url
    cfg.update({"llm_provider": provider, "quick_think_llm": quick, "deep_think_llm": deep,
                "backend_url": relay_url() if provider == "anthropic" else None,
                "output_language": "English", "max_debate_rounds": team["debate_rounds"],
                "max_risk_discuss_rounds": team["risk_rounds"], **runner.reasoning_config(provider),
                "benchmark_map": runner.benchmark_map(),
                "results_dir": str(TA_HOME / "logs"), "data_cache_dir": str(TA_HOME / "cache"),
                "memory_log_path": str(TA_HOME / "memory" / "trading_memory.md")})
    return cfg


@app.get("/api/framework/decisions")
def framework_decisions():
    """TradingAgents' own decision log: each decision is later settled with its realised return and
    alpha against the regional benchmark, and a reflection the agents learn from."""
    from tradingagents.decision_log import TradingMemoryLog
    try:
        entries = TradingMemoryLog(_framework_cfg()).load_entries()
    except Exception:  # noqa: BLE001
        entries = []
    out = [{k: e.get(k) for k in ("date", "ticker", "rating", "pending", "raw", "alpha", "holding", "resolved", "reflection")}
           for e in entries]
    return {"entries": list(reversed(out))}


BACKTESTS: dict[str, dict] = {}


class BacktestIn(BaseModel):
    tickers: list[str]
    start: str
    end: str
    every_n_days: int = 7


@app.post("/api/backtest")
def start_backtest(b: BacktestIn):
    """The framework's own backtest: the full team on each (ticker, date) cell, then scored per rating."""
    import threading
    import uuid
    from tradingagents.backtest import iter_grid
    tickers = list(dict.fromkeys(_ticker(t) for t in b.tickers))[:3]
    start, end = _trade_date(b.start), _trade_date(b.end)
    if not tickers or not start or not end or start > end:
        raise HTTPException(400, "bad_backtest")
    dates = iter_grid(start, end, max(1, min(30, b.every_n_days)))[:12]
    cells = len(tickers) * len(dates)
    if cells == 0:
        raise HTTPException(400, "bad_backtest")
    provider, quick, deep = runner.settings_models()
    key, _ = llm_key(provider)
    if not key:
        return JSONResponse({"ok": False, "code": "no_key"})
    if r := _cap_reached():
        return r
    if PROVIDERS[provider]["env"]:
        import os
        runner.activate_key(provider, key)
    job = {"id": uuid.uuid4().hex[:10], "tickers": tickers, "dates": dates, "cells": cells, "status": "running",
           "done": 0, "summary": None, "failures": [], "estimate": runner.estimate(provider, quick, deep, sessions=cells)}
    BACKTESTS[job["id"]] = job
    from . import budget
    # The framework's backtest takes no usage callback, so its tokens can't be counted: its high estimate is
    # recorded against this month's cap instead (over-counting is safer than a backtest that costs "$0").
    budget.reserve_extra(job["estimate"].get("high") or 0, f"backtest {job['id']} ({cells} cells)")

    def work():
        from pathlib import Path
        from tradingagents.backtest import run_backtest, summarize
        from tradingagents.decision_log import TradingMemoryLog
        cfg = _framework_cfg()
        run_id = f"veyro_{job['id']}"
        log_path = Path(cfg["results_dir"]) / "backtest" / run_id / "trading_memory.md"

        def poll():
            import time
            while job["status"] == "running":
                try:
                    job["done"] = len(TradingMemoryLog({"memory_log_path": str(log_path)}).load_entries())
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(3)
        threading.Thread(target=poll, daemon=True).start()
        try:
            res = run_backtest(tickers, dates, cfg, selected_analysts=tuple(runner.team_settings()["analysts"]), run_id=run_id)
            summ = summarize(res)
            job["summary"] = {"resolved": summ.resolved, "pending": summ.pending, "unscored": summ.unscored, "holding": summ.holding,
                              "by_rating": {r: {"count": s.count, "hit_rate": s.hit_rate, "mean_alpha": s.mean_alpha}
                                            for r, s in summ.by_rating.items()}}
            job["failures"] = [f"{t} {d}" for t, d, _ in res.failures]
            job["done"] = res.cells_run + res.skipped
            job["status"] = "done"
        except Exception as e:  # noqa: BLE001
            job["status"] = "error"
            job["error"] = runner.classify(e)
    threading.Thread(target=work, daemon=True, name=f"backtest-{job['id']}").start()
    return job


@app.get("/api/backtest/{job_id}")
def backtest_status(job_id: str):
    job = BACKTESTS.get(job_id)
    if not job:
        return JSONResponse({"ok": False, "code": "not_found"})
    return job


@app.get("/api/sessions/{sid}/export.zip")
def export_report(sid: str):
    """The framework's own report tree for this session (markdown files), zipped."""
    import io
    import zipfile
    from pathlib import Path
    s = db.get_session(sid)
    d = ((s or {}).get("config") or {}).get("export_dir")
    if not d or not Path(d).is_dir():
        raise HTTPException(404, "no_export")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in Path(d).rglob("*.md"):
            z.write(f, f.relative_to(d))
    from fastapi.responses import Response as _R
    return _R(buf.getvalue(), media_type="application/zip",
              headers={"Content-Disposition": f'attachment; filename="veyro-{s["ticker"]}-{s["trade_date"]}-report.zip"'})


# ---------------------------------------------------------------- daily assistant
@app.get("/api/favorites")
def get_favorites():
    return {"favorites": assistant.favorites()}


@app.get("/api/favorites/quotes")
def favorite_quotes():
    return {"quotes": assistant.favorite_quotes(), "source": market.SOURCE}


@app.post("/api/favorites/{ticker}")
def add_favorite(ticker: str):
    return {"favorites": assistant.add_favorite(_ticker(ticker))}


@app.delete("/api/favorites/{ticker}")
def remove_favorite(ticker: str):
    return {"favorites": assistant.remove_favorite(_ticker(ticker))}


@app.get("/api/assistant")
def assistant_prefs():
    return assistant.prefs()


class AssistIn(BaseModel):
    morning_enabled: bool | None = None
    morning_time: str | None = None
    alerts_enabled: bool | None = None
    alert_threshold: float | None = None
    alerts_news: bool | None = None
    morning_count: int | None = None
    ui_lang: str | None = None


@app.put("/api/assistant")
def put_assistant(p: AssistIn):
    try:
        return assistant.set_prefs(p.model_dump())
    except ValueError:
        raise HTTPException(400, "bad_time") from None


@app.post("/api/assistant/morning/run")
def morning_now():
    """Run the morning report now (the user pressed the button)."""
    if not assistant.favorites():
        return JSONResponse({"ok": False, "code": "no_favorites"})
    if r := _cap_reached():
        return r
    sid = assistant.run_morning(_loop())
    return {"scan_id": sid} if sid else JSONResponse({"ok": False, "code": "no_key"})


@app.get("/api/alerts")
def get_alerts():
    rows = assistant.alerts()
    return {"alerts": rows, "unread": sum(1 for r in rows if not r["read"]),
            "morning_scan": db.get_setting("assist:morning_scan")}


@app.post("/api/alerts/read")
def read_alerts():
    assistant.mark_read()
    return {"ok": True}


@app.post("/api/alerts/check")
def check_now():
    return {"new": assistant.check_alerts()}


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=400)
    lang: str = "ar"


@app.post("/api/sessions/{sid}/ask")
def ask_team(sid: str, body: AskIn):
    if body.lang not in ("ar", "en"):
        raise HTTPException(400, "invalid_lang")
    try:
        r = assistant.ask(sid, body.question.strip(), body.lang)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "code": runner.classify(e)})
    return JSONResponse(r) if r.get("ok") is False else r


@app.get("/api/sessions/{sid}/qa")
def ask_history(sid: str):
    return {"qa": assistant.qa_list(sid)}


@app.get("/api/learning")
def learning_card():
    return assistant.learning(enrich)


@app.get("/api/trust")
def trust():
    """The trust dashboard: how the team's calls actually did, by month, rating and model."""
    from . import extras
    rows = db.list_sessions(500)
    _prefetch_prices(rows)
    return {**assistant.trust([enrich(r) for r in rows if r["mode"] == "real" and r["status"] == "done"]),
            "paper": extras.paper_view()["totals"]}


@app.get("/api/spend")
def spend():
    from . import budget
    return budget.spent()


# ---------------------------------------------------------------- reuse, virtual portfolio, price alerts
@app.get("/api/reusable")
def sessions_reusable(ticker: str, trade_date: str | None = None):
    from . import extras
    return {"session": extras.reusable(_ticker(ticker), _trade_date(trade_date))}


@app.post("/api/sessions/{sid}/replay")
def session_replay(sid: str):
    """Show a finished analysis again in the Office (rebuilt from the database, no model calls)."""
    from . import extras
    s = db.get_session(sid)
    if not s or s["status"] != "done":
        raise HTTPException(404, "not_found")
    if sid not in runner.BUSES or not runner.BUSES[sid].closed:
        runner.BUSES[sid] = runner.Bus(_loop())
        extras.replay(sid)
    return {"id": sid}


class PaperIn(BaseModel):
    ticker: str
    shares: float = Field(gt=0, le=1e7)
    session_id: str | None = None
    rating: str | None = None


@app.get("/api/paper")
def paper():
    from . import extras
    return extras.paper_view()


@app.post("/api/paper")
def paper_add(p: PaperIn):
    from . import extras
    try:
        return extras.paper_add(_ticker(p.ticker), p.shares, p.session_id, p.rating)
    except ValueError:
        return JSONResponse({"ok": False, "code": "no_price"})


class PaperPlanIn(BaseModel):
    items: list[PaperIn]


@app.post("/api/paper/plan")
def paper_plan(p: PaperPlanIn):
    from . import extras
    out, added, failed = extras.paper_view(), [], []
    for it in p.items[:60]:
        try:
            out = extras.paper_add(_ticker(it.ticker), it.shares, it.session_id, it.rating)
            added.append(it.ticker)
        except ValueError:
            failed.append(it.ticker)      # no price right now: say so instead of pretending
    if not added:
        return JSONResponse({"ok": False, "code": "no_price", "failed": failed})
    return {**out, "added": added, "failed": failed}


@app.post("/api/paper/{pid}/close")
def paper_close(pid: int):
    from . import extras
    try:
        return extras.paper_close(pid)
    except ValueError:
        return JSONResponse({"ok": False, "code": "no_price"})


@app.delete("/api/paper/{pid}")
def paper_delete(pid: int):
    from . import extras
    return extras.paper_remove(pid)


class PriceAlertIn(BaseModel):
    symbol: str
    op: str
    value: float


@app.get("/api/price_alerts")
def price_alerts_list():
    from . import extras
    return {"alerts": extras.price_alerts()}


@app.post("/api/price_alerts")
def price_alerts_add(a: PriceAlertIn):
    from . import extras, live
    sym = a.symbol.strip().upper()
    if not (TICKER_RE.match(sym) or sym in live.base_symbols()):
        raise HTTPException(400, "invalid_ticker")
    try:
        return {"alerts": extras.add_price_alert(sym, a.op, a.value)}
    except ValueError:
        raise HTTPException(400, "bad_alert") from None


@app.delete("/api/price_alerts/{aid}")
def price_alerts_delete(aid: int):
    from . import extras
    return {"alerts": extras.delete_price_alert(aid)}


# ---------------------------------------------------------------- beginner mode
class BeginnerIn(BaseModel):
    amount: float = Field(gt=0, le=1e9)
    currency: str = "SAR"
    market: str = "sa"        # 'sa' | 'us' | 'both'
    risk: str = "balanced"    # 'cautious' | 'balanced' | 'bold'
    count: int = 3


def _beginner_args(b: BeginnerIn) -> BeginnerIn:
    if b.currency not in ("USD", "SAR") or b.market not in ("sa", "us", "both") or b.risk not in ("cautious", "balanced", "bold"):
        raise HTTPException(400, "bad_profile")
    b.count = max(1, min(5, b.count))
    return b


@app.post("/api/beginner/suggest")
def beginner_suggest(b: BeginnerIn):
    """Beginner-friendly companies the owner can afford with this amount (real prices)."""
    from . import beginner
    b = _beginner_args(b)
    return beginner.suggest(b.amount, b.currency, b.market, b.risk, b.count)


class BeginnerStartIn(BeginnerIn):
    tickers: list[str]
    lang: str = "ar"
    demo: bool = False


@app.post("/api/beginner/start")
def beginner_start(b: BeginnerStartIn):
    from . import beginner
    _beginner_args(b)
    if b.lang not in ("ar", "en"):
        raise HTTPException(400, "invalid_lang")
    tickers = list(dict.fromkeys(_ticker(t) for t in b.tickers))[:5]
    if not tickers:
        raise HTTPException(400, "watchlist_size")
    if not b.demo and (r := _cap_reached()):
        return r
    budget = _budget(b.amount, b.currency)
    scan_id = runner.start_scan(_loop(), "beginner", tickers, None, None, b.lang, b.demo, budget=budget)
    beginner.save_profile(scan_id, {"amount": budget["amount"], "currency": b.currency, "market": b.market, "risk": b.risk})
    return {"id": scan_id, "tickers": tickers, "source": None,
            "estimate": runner.estimate(*runner.settings_models(), sessions=len(tickers)) if not b.demo else None}


@app.get("/api/beginner/{scan_id}/guide")
def beginner_guide(scan_id: str, lang: str = "ar"):
    from . import beginner
    if lang not in ("ar", "en"):
        raise HTTPException(400, "invalid_lang")
    g = beginner.guide(scan_id, lang)
    return JSONResponse(g) if g.get("ok") is False else g


# ---------------------------------------------------------------- about
@app.get("/api/about")
def about():
    lic = ROOT / "third_party" / "TradingAgents" / "LICENSE"
    return {"framework": "TradingAgents", "author": "Tauric Research", "version": "0.5.1",
            "license": "Apache-2.0", "url": "https://github.com/TauricResearch/TradingAgents",
            "license_text": lic.read_text(encoding="utf-8") if lic.exists() else None,
            "characters": list(CHARACTERS)}


@app.get("/api/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------- frontend
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")
    if (STATIC_DIR / "fonts").exists():
        app.mount("/fonts", StaticFiles(directory=STATIC_DIR / "fonts"), name="fonts")

    @app.get("/{path:path}")
    def spa(path: str):
        f = (STATIC_DIR / path).resolve()
        if path and f.is_file() and STATIC_DIR.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(STATIC_DIR / "index.html")
