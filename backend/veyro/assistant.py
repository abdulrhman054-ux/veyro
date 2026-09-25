"""The daily assistant: favourite stocks, smart alerts, the morning report, "ask the team",
and Bruno's monthly learning card.

Alerts use only real data (Yahoo quotes, headlines from strong publishers) and cost no model
tokens. The morning report is opt-in because every stock is a full paid session.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .lazy import yf   # loads on first use (fast startup)

from . import db, market, runner
from .config import MAX_BATCH

log = logging.getLogger("veyro.assistant")
NY = ZoneInfo("America/New_York")

SCHEMA = """
CREATE TABLE IF NOT EXISTS favorites (ticker TEXT PRIMARY KEY, added_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL, ticker TEXT,
  character TEXT NOT NULL, text_ar TEXT NOT NULL, text_en TEXT NOT NULL, link TEXT, ref TEXT, read INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS qa (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, ts TEXT NOT NULL, lang TEXT NOT NULL,
  question TEXT NOT NULL, character TEXT NOT NULL, answer TEXT NOT NULL
);
"""

DEFAULTS = {"morning_enabled": False, "morning_time": "08:00", "alerts_enabled": True, "alert_threshold": 3.0,
            "alerts_news": True, "morning_count": 5, "ui_lang": "ar"}


def init() -> None:
    with db.tx() as c:
        c.executescript(SCHEMA)


def prefs() -> dict:
    return {k: db.get_setting(f"assist:{k}", v) for k, v in DEFAULTS.items()}


def set_prefs(p: dict) -> dict:
    for k, v in p.items():
        if k not in DEFAULTS or v is None:
            continue
        if k == "morning_time" and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(v)):
            raise ValueError("bad_time")
        if k == "alert_threshold":
            v = max(1.0, min(20.0, float(v)))
        if k == "morning_count":
            v = max(1, min(MAX_BATCH, int(v)))
        if k == "ui_lang" and v not in ("ar", "en"):
            continue
        db.set_setting(f"assist:{k}", v)
    return prefs()


# ---------------------------------------------------------------- favourites
def favorites() -> list[str]:
    return [r["ticker"] for r in db.q("SELECT ticker FROM favorites ORDER BY added_at")]


def add_favorite(t: str) -> list[str]:
    with db.tx() as c:
        c.execute("INSERT OR IGNORE INTO favorites(ticker, added_at) VALUES(?,?)", (t, db.now()))
    return favorites()


def remove_favorite(t: str) -> list[str]:
    with db.tx() as c:
        c.execute("DELETE FROM favorites WHERE ticker=?", (t,))
    return favorites()


def quote(t: str) -> dict | None:
    """Last price vs previous close (real Yahoo quote); None when unavailable."""
    try:
        fi = yf.Ticker(t).fast_info
        last, prev = fi.get("lastPrice"), fi.get("previousClose")
        if last and prev:
            return {"ticker": t, "last": float(last), "prev": float(prev), "change": float(last) / float(prev) - 1}
    except Exception as e:  # noqa: BLE001
        log.info("quote %s unavailable: %s", t, type(e).__name__)
    return None


def favorite_quotes() -> list[dict]:
    out = []
    for t in favorites():
        q = market._cached(f"fq:{t}", 120, lambda t=t: quote(t))
        out.append(q or {"ticker": t, "last": None, "prev": None, "change": None})
    return out


# ---------------------------------------------------------------- alerts
def add_alert(kind: str, ticker: str | None, character: str, ar: str, en: str, link: str | None = None, ref: str | None = None) -> None:
    with db.tx() as c:
        c.execute("INSERT INTO alerts(ts,kind,ticker,character,text_ar,text_en,link,ref) VALUES(?,?,?,?,?,?,?,?)",
                  (db.now(), kind, ticker, character, ar, en, link, ref))


def alerts(limit: int = 50) -> list[dict]:
    return db.q("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))


def mark_read() -> None:
    with db.tx() as c:
        c.execute("UPDATE alerts SET read=1 WHERE read=0")


def _once(key: str) -> bool:
    """True the first time a key is seen (dedupe alerts)."""
    seen = db.get_setting("assist:seen", {}) or {}
    if key in seen:
        return False
    cutoff = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    seen = {k: v for k, v in seen.items() if v >= cutoff}
    seen[key] = datetime.now(timezone.utc).isoformat()
    db.set_setting("assist:seen", seen)
    return True


def check_alerts() -> int:
    p = prefs()
    if not p["alerts_enabled"]:
        return 0
    n = 0
    day = datetime.now(NY).strftime("%Y-%m-%d")
    th = float(p["alert_threshold"]) / 100
    for t in favorites():
        q = quote(t)
        if q and abs(q["change"]) >= th:
            step = int(abs(q["change"]) / th)  # alert again only when the move grows by another threshold step
            if _once(f"px:{t}:{day}:{'up' if q['change'] > 0 else 'down'}:{step}"):
                pct = f"{q['change'] * 100:+.2f}%"
                add_alert("price", t, "Pip",
                          f"خبر خبر! {t} تحرك {pct} اليوم، والسعر الآن {q['last']:.2f}$. سكوااك!",
                          f"News, news! {t} moved {pct} today; it's now ${q['last']:.2f}. Squawk!", ref=day)
                n += 1
        if p["alerts_news"]:
            n += _news_alert(t)
    return n


def _news_alert(t: str) -> int:
    from . import world
    try:
        found = world.search(f"{t} stock", "en", limit=15)
    except Exception:  # noqa: BLE001
        return 0
    fresh_after = datetime.now(timezone.utc) - timedelta(hours=3)
    for it in found.get("items", []):
        if not it.get("trusted") or not it.get("published"):
            continue
        try:
            if datetime.fromisoformat(it["published"]) < fresh_after:
                continue
        except ValueError:
            continue
        if not re.search(rf"\b{re.escape(t.split('.')[0].split('-')[0])}\b", it["title"], re.I):
            continue  # the headline must actually name the stock
        if _once(f"news:{it['link']}"):
            add_alert("news", t, "Albie",
                      f"من فوق الغيوم شفت خبر جديد عن {t} في {it['source']}. افتحه من الرابط. ريشتي تطير بالأخبار!",
                      f"From above the clouds: fresh {it['source']} story on {t}: \"{it['title']}\" feathers full of news!",
                      link=it["link"])
            return 1
    return 0


# ---------------------------------------------------------------- morning report
def morning_due(now_local: datetime | None = None) -> bool:
    p = prefs()
    if not p["morning_enabled"] or not favorites():
        return False
    now_local = now_local or datetime.now()
    if datetime.now(NY).weekday() >= 5:
        return False  # weekends: markets closed, nothing new to analyse
    hh, mm = map(int, p["morning_time"].split(":"))
    if (now_local.hour, now_local.minute) < (hh, mm):
        return False
    return db.get_setting("assist:morning_last") != now_local.strftime("%Y-%m-%d")


def run_morning(loop, lang: str | None = None) -> str | None:
    from .secrets_store import llm_key
    provider, _, _ = runner.settings_models()
    if not llm_key(provider)[0]:
        add_alert("morning", None, "Leo", "حان وقت التقرير الصباحي، بس ما فيه مفتاح نموذج. أضفه من الإعدادات. زئير!",
                  "Morning report time, but there's no model key. Add one in Settings. roar!")
        db.set_setting("assist:morning_last", datetime.now().strftime("%Y-%m-%d"))
        return None
    lang = lang or prefs()["ui_lang"]
    tickers = favorites()[:max(1, min(MAX_BATCH, int(prefs()["morning_count"] or 5)))]
    scan_id = runner.start_scan(loop, "watchlist", tickers, None, None, lang, False)
    db.set_setting("assist:morning_last", datetime.now().strftime("%Y-%m-%d"))
    db.set_setting("assist:morning_scan", scan_id)
    add_alert("morning", None, "Leo",
              f"صباح الخير! الفريق بدأ التقرير الصباحي لأسهمك المفضلة: {'، '.join(tickers)}. زئير!",
              f"Good morning! The team started the morning report on your favourites: {', '.join(tickers)}. roar!", ref=scan_id)
    return scan_id


class Scheduler:
    """Background loop: alerts every 5 minutes, the morning report once a day when enabled."""

    def __init__(self, loop):
        self.loop = loop
        self.stop = threading.Event()
        self.t = threading.Thread(target=self._run, daemon=True, name="veyro-assistant")

    def start(self):
        self.t.start()

    def _run(self):
        last_alert = 0.0
        while not self.stop.wait(30):
            try:
                if morning_due():
                    run_morning(self.loop)
                if time.time() - last_alert >= 300:
                    last_alert = time.time()
                    check_alerts()
                    from .extras import check_all_prices
                    check_all_prices()
            except Exception as e:  # noqa: BLE001
                log.info("assistant tick failed: %s", type(e).__name__)


# ---------------------------------------------------------------- ask the team
ASK_CHARS = ["Ollie", "Buzz", "Pip", "Benny", "Bolt", "Bruno", "Tank", "Leo", "Albie"]


def ask(sid: str, question: str, lang: str) -> dict:
    from .config import CHARACTERS, PROVIDERS, STYLE
    from .secrets_store import llm_key
    from .voice import LANG_RULES, Voice
    s = db.get_session(sid)
    if not s:
        return {"ok": False, "code": "not_found"}
    if s["mode"] == "demo":
        return {"ok": False, "code": "demo"}
    provider, quick, _ = runner.settings_models()
    key, _ = llm_key(provider)
    if not key:
        return {"ok": False, "code": "no_key"}
    runner.activate_key(provider, key)
    notes = "\n\n".join(f"### {t['character']} ({t['node']})\n{t['detail_en'][:2500]}" for t in s["turns"])
    roster = "\n".join(f"- {c}: {CHARACTERS[c]['role']}. Style ({lang}): {STYLE[c][lang]}" for c in ASK_CHARS if c in CHARACTERS)
    system = (
        "You run a cosy pixel-art office of animal analysts who just analysed a stock with the TradingAgents framework. "
        "A user asks the team a question. Pick the ONE character whose job best owns the question, and answer as that character.\n"
        f"Characters:\n{roster}\n"
        "Hard rules: answer ONLY from the session notes below; do not add facts, numbers or predictions that are not in them; "
        "if the notes don't answer it, say so honestly; keep risks; 2-4 short spoken sentences; end with that character's catchphrase. "
        f"Language: {LANG_RULES[lang]} Write ONLY in this language.\n"
        'Return ONLY JSON: {"character": "<name>", "answer": "<text>"}'
    )
    user = f"Ticker: {s['ticker']} · verdict: {s.get('rating')}\n\nSession notes:\n{notes[:24000]}\n\nQuestion: {question}"
    raw = Voice(provider, quick)._ask(system, user)
    m = re.search(r"\{.*\}", raw, re.S)
    data = {}
    if m:
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            data = {}
    ch = data.get("character") if data.get("character") in ASK_CHARS else "Leo"
    ans = str(data.get("answer") or raw).strip()
    with db.tx() as c:
        c.execute("INSERT INTO qa(session_id,ts,lang,question,character,answer) VALUES(?,?,?,?,?,?)", (sid, db.now(), lang, question, ch, ans))
    return {"character": ch, "answer": ans, "question": question}


def qa_list(sid: str) -> list[dict]:
    return db.q("SELECT * FROM qa WHERE session_id=? ORDER BY id", (sid,))


# ---------------------------------------------------------------- Bruno's monthly learning card
def learning(enrich) -> dict:
    """Deterministic numbers only: our scored calls (vs benchmark) and the framework's settled alpha."""
    from .runner import RATING_ORDER
    rows = [enrich(r) for r in db.list_sessions(500) if r["mode"] == "real" and r["status"] == "done"]
    month = datetime.now().strftime("%Y-%m")

    def score(r):
        if r.get("ret") is None or r.get("spy_ret") is None or r["rating"] not in RATING_ORDER:
            return None
        ex = r["ret"] - r["spy_ret"]
        d = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}[r["rating"]]
        return None if d == 0 or abs(ex) < 0.0005 else (ex * d > 0, ex)

    def block(rs):
        sc = [(r, score(r)) for r in rs]
        dirn = [(r, s) for r, s in sc if s]
        by_rating = {}
        for r, s in dirn:
            b = by_rating.setdefault(r["rating"], {"count": 0, "hits": 0})
            b["count"] += 1
            b["hits"] += int(s[0])
        by_ticker = {}
        for r, s in dirn:
            b = by_ticker.setdefault(r["ticker"], {"count": 0, "hits": 0, "excess": 0.0})
            b["count"] += 1
            b["hits"] += int(s[0])
            b["excess"] += s[1]
        return {"sessions": len(rs), "scored": len(dirn), "hits": sum(int(s[0]) for _, s in dirn),
                "by_rating": by_rating, "by_ticker": by_ticker}

    fw = []
    try:
        from tradingagents.decision_log import TradingMemoryLog
        from .app import _framework_cfg
        fw = [e for e in TradingMemoryLog(_framework_cfg()).load_entries() if not e["pending"]]
    except Exception:  # noqa: BLE001
        fw = []
    alphas = []
    for e in fw:
        try:
            alphas.append(float((e.get("alpha") or "").rstrip("%")) / 100)
        except ValueError:
            pass
    return {"month": month, "this_month": block([r for r in rows if (r.get("created_at") or "").startswith(month)]),
            "all_time": block(rows),
            "framework": {"settled": len(fw), "mean_alpha": (sum(alphas) / len(alphas)) if alphas else None}}
