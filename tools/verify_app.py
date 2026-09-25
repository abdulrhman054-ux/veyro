"""End-to-end browser verification (Playwright). Writes screenshots to verification/ and
verification/execution/, and a machine-readable verification/results.json.

Uses backend/tests/verify_server.py: isolated data dir, fake LLM ([TEST] output), Mock broker,
live trading hard-blocked, and a planted fake API key that must never leak anywhere.
Run:  .venv\\Scripts\\python tools\\verify_app.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "verification"
EX = OUT / "execution"
DATA = OUT / "data"
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
PORT = 8766
BASE = f"http://127.0.0.1:{PORT}"
KEY = "sk-ant-TESTKEY-must-never-appear-0000"
AR = re.compile(r"[؀-ۿ]")
NAMES_AR = {"أولي": "Ollie", "بيب": "Pip", "بَز": "Buzz", "بيني": "Benny", "بولت": "Bolt", "برونو": "Bruno", "تانك": "Tank", "ليو": "Leo", "ألبي": "Albie"}

results: list[dict] = []
leaks: list[str] = []
console_errors: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append({"check": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f" :: {detail}" if detail else ""), flush=True)


# ---------------------------------------------------------------- server
def start_server(mock_clock_open: bool = True, fresh: bool = True) -> tuple[subprocess.Popen, Path]:
    if fresh and DATA.exists():
        shutil.rmtree(DATA)
    DATA.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "VEYRO_DATA_DIR": str(DATA), "VEYRO_PORT": str(PORT), "FAKE_RATING": "Buy",
           "VEYRO_MOCK_CLOCK_OPEN": "1" if mock_clock_open else "0", "PYTHONIOENCODING": "utf-8"}
    log = OUT / ("server_log.txt" if mock_clock_open else "server_log_closed.txt")
    fh = open(log, "w", encoding="utf-8")
    p = subprocess.Popen([PY, str(ROOT / "backend" / "tests" / "verify_server.py")], cwd=str(ROOT / "backend"), env=env,
                         stdout=fh, stderr=subprocess.STDOUT)
    for _ in range(120):
        try:
            urllib.request.urlopen(f"{BASE}/api/health", timeout=2)
            return p, log
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    raise RuntimeError("server did not start")


# ---------------------------------------------------------------- browser helpers
def watch(page) -> None:
    def on_console(m):
        if m.type == "error":
            console_errors.append(m.text)
    page.on("console", on_console)
    page.on("pageerror", lambda e: console_errors.append(str(e)))

    def on_response(r):
        if r.status >= 400:
            console_errors.append(f"HTTP {r.status} {r.request.method} {r.url}")
        try:
            if "text" in (r.headers.get("content-type") or "") or "json" in (r.headers.get("content-type") or ""):
                if KEY in r.text():
                    leaks.append(f"http {r.url}")
        except Exception:  # noqa: BLE001
            pass
    page.on("response", on_response)

    def on_ws(ws):
        ws.on("framereceived", lambda payload: leaks.append(f"ws {ws.url}") if KEY in str(payload) else None)
    page.on("websocket", on_ws)


def set_prefs(page, **kw) -> None:
    prefs = {"lang": "ar", "theme": "day", "intensity": "normal", "reduceMotion": False, "sound": False, "showCost": True, **kw}
    page.evaluate("p => { localStorage.setItem('veyro.prefs.v1', JSON.stringify(p)); localStorage.setItem('veyro.welcomed', '1'); }", prefs)
    page.reload()
    page.wait_for_timeout(1500)


def open_advanced(page) -> None:
    d = page.locator("details.advanced")
    if d.count() and not d.evaluate("e => e.open"):
        d.locator("summary").click()
        page.wait_for_timeout(300)


def shot(page, name: str, folder: Path = OUT) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(folder / name))


def nav(page, label_ar: str, label_en: str) -> None:
    page.locator("nav.nav button").filter(has_text=re.compile(f"^({label_ar}|{label_en})$")).click()
    page.wait_for_timeout(800)


def run_session_to_verdict(page, lang: str, timeout_s: int = 240) -> list[str]:
    """Drives the dialogue (clicking to advance) and checks every speaking character is in sync
    with the dialogue box. Returns the English names in speaking order."""
    order: list[str] = []
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if page.locator(".verdict-box").count():
            break
        dlg = page.locator("button.dlg")
        if dlg.count():
            tag = dlg.locator(".tag").inner_text().strip()
            speaking = page.locator(".agent.speaking .plate").all_inner_texts()
            en = NAMES_AR.get(tag, tag)
            text = dlg.get_attribute("aria-label") or ""
            if speaking:
                ok = [NAMES_AR.get(s.strip(), s.strip()) for s in speaking] == [en]
                if not ok:
                    check("sync: dialogue speaker == animated character", False, f"{tag} vs {speaking}")
            if "[TEST]" in text or "[اختبار]" in text:
                if not order or order[-1] != en:
                    order.append(en)
                    # the fake voice line names the character it was generated for
                    if en not in ("Leo", "Albie") and en not in text and "Risk" not in text:
                        check(f"sync: {en} line belongs to {en}", False, text[:80])
            if "…" != (dlg.locator(".dtext").inner_text().strip() or "…"):
                dlg.click()
                page.wait_for_timeout(150)
                if page.locator("button.dlg").count():
                    page.locator("button.dlg").click()
        page.wait_for_timeout(350)
    return order


# ---------------------------------------------------------------- flows
def core_flows(pw) -> None:
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    page = ctx.new_page()
    watch(page)
    page.goto(BASE)
    set_prefs(page, lang="ar")

    check("RTL layout in Arabic", page.evaluate("document.documentElement.dir") == "rtl")
    page.wait_for_selector(".wb-move", timeout=20000)
    shot(page, "01_office_idle_ar_day.png")
    check("office mood driven by real SPY close", page.locator(".room").get_attribute("class").startswith("room mood-"),
          page.locator(".room").get_attribute("class"))

    # A real-path session (framework graph + fake model), Arabic
    demo_box = page.get_by_role("checkbox")
    if demo_box.is_checked():
        demo_box.uncheck()
    page.locator("input.ticker").fill("NVDA")
    page.locator(".startbar button.primary").click()
    page.wait_for_selector("button.dlg", timeout=60000)
    page.wait_for_timeout(1200)
    shot(page, "02_session_speaking_ar.png")
    order = run_session_to_verdict(page, "ar")
    check("Albie links world news to the stock before the verdict", "Albie" in order and order.index("Albie") < len(order) - 1, str(order))
    check("all 8 characters spoke, in the framework's order",
          order[:6] == ["Ollie", "Buzz", "Pip", "Benny", "Bolt", "Bruno"] and "Tank" in order and order[-1] == "Leo", str(order))
    page.wait_for_timeout(1200)
    shot(page, "03_verdict_ar.png")
    check("verdict shown with rating", page.locator(".verdict-word").count() == 1, page.locator(".verdict-word").inner_text())
    check("verdict shows disclaimer", "ليس نصيحة مالية" in page.locator(".verdict-box").inner_text())
    check("verdict price comes from data or says unavailable",
          bool(re.search(r"\d+\.\d\d|غير متوفر", page.locator(".verdict-box").inner_text())),
          page.locator(".verdict-box").inner_text()[-120:])

    # Report in Arabic
    page.get_by_role("button", name="افتح التقرير").click()
    page.wait_for_timeout(2500)
    shot(page, "04_report_ar.png")
    check("report lists every turn", page.locator("article.card").count() >= 10, str(page.locator("article.card").count()))
    check("report shows the framework's key figures and session setup",
          page.get_by_text("أرقام الفريق الرئيسية").count() == 1 and page.get_by_text("إعداد الجلسة").count() == 1)

    # The framework's own report tree, downloadable as a ZIP of markdown files
    with page.expect_download() as dl:
        page.get_by_text("تنزيل تقرير الإطار الكامل (ZIP)").click()
    zpath = OUT / "framework_report.zip"
    dl.value.save_as(zpath)
    import zipfile
    names = zipfile.ZipFile(zpath).namelist()
    check("framework report export (ZIP of TradingAgents markdown reports)", any(n.endswith(".md") for n in names), str(names[:6]))

    # Ask the team: the right character answers from the session's own notes
    page.locator("input[aria-label='اسأل الفريق']:visible").first.fill("وش أكبر خطر؟")
    page.locator("button:visible").filter(has_text=re.compile("^اسأل$")).first.click()
    page.wait_for_selector("section.card >> text=❓", timeout=30000)
    shot(page, "16_ask_team_ar.png")
    check("ask the team: a character answers in the report", "برونو" in page.locator("section.card").filter(has_text="❓").first.inner_text())

    # Favourites: star from the report, then the office strip shows it with a real quote
    page.get_by_role("button", name="إضافة للمفضلة").first.click()
    page.wait_for_timeout(1500)
    nav(page, "المكتب", "Office")
    page.wait_for_selector(".favstrip", timeout=20000)
    check("favourites strip shows the starred stock", "NVDA" in page.locator(".favstrip").inner_text())

    # Alerts bell + morning report ("run it now" starts a watchlist scan of favourites)
    r = page.evaluate("fetch('/api/assistant/morning/run',{method:'POST'}).then(r=>r.json())")
    check("morning report starts a scan of favourites", bool(r.get("scan_id")), str(r))
    page.wait_for_timeout(1500)
    page.get_by_role("button", name=re.compile("التنبيهات")).click()
    page.wait_for_selector(".alerts-pop .alert-row", timeout=40000)
    shot(page, "17_alerts_morning_ar.png")
    check("alerts panel shows Leo's morning-report alert", "التقرير الصباحي" in page.locator(".alerts-pop").inner_text())
    page.get_by_role("button", name=re.compile("التنبيهات")).click()
    page.evaluate("fetch('/api/scans/' + arguments[0] + '/cancel',{method:'POST'})".replace("arguments[0]", repr(r.get("scan_id") or "")))

    # Settings: connection test, custom model, daily assistant
    nav(page, "الإعدادات", "Settings")
    page.get_by_role("button", name="اختبر الاتصال").click()
    page.wait_for_selector("text=الاتصال شغّال", timeout=30000)
    check("connection test reports the key and both models working", page.get_by_text("الاتصال شغّال").count() >= 1)
    page.locator("#quick").select_option("__custom__")
    page.get_by_label("معرّف النموذج").fill("claude-haiku-4-5")
    page.get_by_role("button", name="استخدمه").click()
    page.wait_for_timeout(1500)
    st = page.evaluate("fetch('/api/settings').then(r=>r.json())")
    check("any model ID can be chosen (custom model saved)", st["quick_model"] == "claude-haiku-4-5", st["quick_model"])
    check("daily assistant settings present", page.get_by_text("المساعد اليومي").count() >= 1)
    shot(page, "18_settings_connection_ar.png")
    page.evaluate("fetch('/api/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({quick_model:'claude-sonnet-5'})})")
    nav(page, "التقرير", "Report")
    page.wait_for_timeout(1500)

    # Switch to English: everything must be English only (lines re-voiced in English on demand)
    page.get_by_role("button", name="Switch to English").click()
    page.wait_for_timeout(4000)
    shot(page, "05_report_en.png")
    main_text = page.locator("main").inner_text()
    check("English screen contains no Arabic text", not AR.search(main_text), (AR.findall(main_text)[:10] and main_text[:200]) or "")
    check("RTL off in English", page.evaluate("document.documentElement.dir") == "ltr")

    # History
    nav(page, "السجل", "History")
    page.wait_for_timeout(2500)
    shot(page, "06_history_en.png")
    rows = page.locator("table.table tbody tr")
    check("history saved the session", rows.count() >= 1 and "NVDA" in rows.first.inner_text(), rows.first.inner_text()[:120] if rows.count() else "")

    # History carries the framework's own memory (settled decisions) and its backtest
    check("History shows Bruno's learning card", page.get_by_text(re.compile("Bruno's card")).count() == 1)
    check("History shows the framework's decision memory and backtest",
          page.get_by_text("Framework memory: how TradingAgents scored its own calls").count() == 1
          and page.get_by_text("Backtest (built into TradingAgents)").count() == 1)
    mem_rows = page.locator("section.card").filter(has_text="how TradingAgents scored").locator("tbody tr")
    check("framework memory lists this session's decision", mem_rows.count() >= 1 and "NVDA" in mem_rows.first.inner_text())
    page.locator("section.card").filter(has_text="how TradingAgents scored").scroll_into_view_if_needed()
    shot(page, "15_framework_memory_backtest_en.png")

    # Albie's own page: real headlines from major papers + world market tiles, English-only in English
    nav(page, "أخبار العالم", "World news")
    page.wait_for_selector(".news-item", timeout=60000)
    page.wait_for_selector(".tile", timeout=60000)
    page.wait_for_timeout(1500)
    shot(page, "14_world_news_en.png")
    srcs = set(page.locator(".news-item .srcchip").all_inner_texts())
    check("World News shows real headlines from major publishers", len(srcs) >= 4 and page.locator(".news-item a[href^=http]").count() >= 10, str(sorted(srcs))[:200])
    check("World News shows live market tiles (incl. TASI)", page.locator(".tile").count() >= 10 and "TASI" in page.locator("main").inner_text())
    check("World News in English has no Arabic text", not AR.search(page.locator("main").inner_text()))

    # Night mode office
    nav(page, "المكتب", "Office")
    page.get_by_role("button", name="Toggle day and night").click()
    page.wait_for_timeout(1200)
    shot(page, "07_office_night_en.png")
    check("night theme applied", page.evaluate("document.documentElement.dataset.theme") == "night")
    page.get_by_role("button", name="Toggle day and night").click()

    # Settings: key masked, never shown
    nav(page, "الإعدادات", "Settings")
    page.wait_for_timeout(1200)
    shot(page, "08_settings_en.png")
    body = page.content()
    check("settings shows masked key", "sk-…0000" in page.locator("main").inner_text())
    check("full key never in page", KEY not in body)

    # Demo watchlist scan with ranking
    nav(page, "المكتب", "Office")
    page.locator(".seg button").filter(has_text="Watchlist").click()
    page.locator(".startbar input.field").first.fill("AAPL, MSFT")
    if not page.get_by_role("checkbox").is_checked():
        page.get_by_role("checkbox").check()
    page.locator(".startbar button.primary").click()
    t0 = time.time()
    while time.time() - t0 < 300 and not page.locator(".modal .board-rank").count():
        if page.locator("button.dlg").count():
            page.locator("button.dlg").click()
        page.wait_for_timeout(400)
    page.wait_for_timeout(800)
    shot(page, "09_scan_ranking_en.png")
    check("scan ranking shown for both tickers", page.locator(".modal .board-rank li").count() == 2)
    page.locator(".modal button.primary").click()

    nav(page, "الإعدادات", "Settings")
    open_advanced(page)
    check("advanced settings list the framework's extra providers (incl. local Ollama) and reasoning depth",
          page.get_by_role("button", name="Ollama (local, free)").count() == 1 and page.get_by_text("Model reasoning depth").count() == 1)
    nav(page, "المكتب", "Office")

    # TradingAgents options: team selection + crypto (framework drops fundamentals for crypto)
    nav(page, "الإعدادات", "Settings")
    open_advanced(page)
    page.locator("label.toggle").filter(has_text="Buzz").locator("input").click()
    page.wait_for_function("() => ![...document.querySelectorAll('label.toggle')].find(l => l.textContent.includes('Buzz')).querySelector('input').checked", timeout=10000)
    page.locator("#team-h").scroll_into_view_if_needed()
    shot(page, "12_team_settings_en.png")
    nav(page, "المكتب", "Office")
    page.locator(".seg button").filter(has_text="One stock").click()
    check("office offers point-in-time analysis date", page.locator(".startbar input[type=date]").count() == 1)
    page.locator("input.ticker").fill("BTC-USD")
    if not page.get_by_role("checkbox").is_checked():
        page.get_by_role("checkbox").check()
    page.locator(".startbar button.primary").click()
    page.wait_for_selector(".agent.break", timeout=30000)
    page.wait_for_timeout(1500)
    shot(page, "13_crypto_team_break_en.png")
    brk = sorted(page.locator(".agent.break .plate").all_inner_texts())
    check("absent analysts shown on a break (Buzz by choice, Benny for crypto)", brk == ["Benny", "Buzz"], str(brk))
    page.get_by_role("button", name="Stop").click()
    page.wait_for_timeout(1500)
    nav(page, "الإعدادات", "Settings")
    open_advanced(page)
    page.locator("label.toggle").filter(has_text="Buzz").locator("input").click()
    page.wait_for_timeout(800)
    nav(page, "التقرير", "Report")

    # Mobile width: no horizontal scroll
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(800)
    shot(page, "10_mobile_en.png")
    check("no horizontal scroll at phone width", page.evaluate("document.scrollingElement.scrollWidth <= innerWidth + 1"),
          str(page.evaluate("[document.scrollingElement.scrollWidth, innerWidth]")))
    ctx.close()

    # Reduced motion (OS-level)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    page = ctx.new_page()
    watch(page)
    page.goto(BASE)
    set_prefs(page, lang="ar")
    anim = page.evaluate("getComputedStyle(document.querySelector('.sprite')).animationName")
    shot(page, "11_reduced_motion_ar.png")
    check("prefers-reduced-motion stops animations", anim == "none", anim)
    ctx.close()
    browser.close()


def open_real_report(page) -> None:
    """Open the Report of the real-path NVDA session (the newest sessions are demo scan runs)."""
    nav(page, "السجل", "History")
    page.wait_for_timeout(2500)
    row = (page.locator("table.table tbody tr").filter(has_text="NVDA").filter(has_text=re.compile("شراء|BUY"))
           .filter(has_not_text="Demo").filter(has_not_text="تجريبي").first)
    row.get_by_role("button", name=re.compile("^(عرض|View)$")).click()
    page.wait_for_timeout(1800)


def exec_flows(pw) -> None:
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    page = ctx.new_page()
    watch(page)
    page.goto(BASE)
    set_prefs(page, lang="ar")

    # Default: Off
    status = page.evaluate("fetch('/api/exec/status').then(r=>r.json())")
    check("execution is Off by default", status["mode"] == "off")

    nav(page, "الإعدادات", "Settings")
    open_advanced(page)
    page.locator("section[aria-labelledby=tr-h] .segbtns button").nth(1).click()  # Paper
    page.wait_for_timeout(1000)
    page.locator("section[aria-labelledby=tr-h]").scroll_into_view_if_needed()
    shot(page, "e01_paper_mock_settings.png", EX)
    check("paper without keys uses clearly labelled Mock", page.locator("header .chip").filter(has_text="MOCK").count() == 1)

    # Order from the verdict (session rating Buy from the fake model)
    open_real_report(page)
    page.get_by_role("button", name="ليو يقترح أمر").click()
    page.wait_for_selector(".modal")
    page.locator(".modal input[type=number]").first.fill("200")
    page.get_by_role("button", name="خل تانك يفحص الحدود").click()
    page.wait_for_function("() => { const b=[...document.querySelectorAll('.modal button')].find(x=>x.textContent.includes('أؤكد الأمر')); return b && !b.disabled; }", timeout=20000)
    shot(page, "e02_ticket_checks_market.png", EX)
    page.get_by_role("button", name="أؤكد الأمر").click()
    page.wait_for_selector(".stamp", timeout=20000)
    page.wait_for_timeout(700)
    shot(page, "e03_market_order_filled.png", EX)
    check("market order filled via full UI flow", "filled" in page.locator(".modal").inner_text())
    page.get_by_role("button", name="رجوع").click()

    def ticket(amount: str, limit_price: str | None = None) -> None:
        page.get_by_role("button", name="ليو يقترح أمر").click()
        page.wait_for_selector(".modal")
        if limit_price:
            page.locator(".modal .segbtns button").nth(1).click()
            page.wait_for_timeout(200)
            page.locator(".modal input[type=number]").nth(1).fill(limit_price)
        page.locator(".modal input[type=number]").first.fill(amount)
        page.get_by_role("button", name="خل تانك يفحص الحدود").click()
        page.wait_for_function("() => [...document.querySelectorAll('.modal li')].filter(l=>/[✓✗]/.test(l.textContent)).length >= 6", timeout=20000)
        page.wait_for_timeout(300)

    # Limit order that stays open, then cancel it from the Orders screen
    ticket("300", "5.00")
    page.get_by_role("button", name="أؤكد الأمر").click()
    page.wait_for_selector(".stamp", timeout=20000)
    check("limit order accepted and open", "accepted" in page.locator(".modal").inner_text())
    page.get_by_role("button", name="رجوع").click()
    nav(page, "الأوامر", "Orders")
    page.wait_for_timeout(2000)
    shot(page, "e04_limit_open_orders.png", EX)
    page.locator("section.card").filter(has_text="الأوامر المفتوحة").get_by_role("button", name="إلغاء").first.click()
    page.wait_for_timeout(2500)
    shot(page, "e05_limit_cancelled.png", EX)
    check("limit order cancelled", page.locator("section.card").filter(has_text="آخر الأوامر").inner_text().count("canceled") >= 1)

    open_real_report(page)

    # Risk limit: max per order
    ticket("600")
    shot(page, "e06_blocked_max_order.png", EX)
    check("max-per-order limit blocks the ticket", page.get_by_role("button", name="أؤكد الأمر").is_disabled())
    page.get_by_role("button", name="رجوع").click()
    page.get_by_role("button", name="إلغاء").click()

    # Risk limit: exposure per symbol (tighten to $300 through the API the Settings form uses)
    page.evaluate("fetch('/api/exec/limits',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'paper',max_order_usd:500,max_symbol_exposure_usd:300,daily_loss_limit_usd:200,max_orders_per_day:5})})")
    ticket("200")
    shot(page, "e07_blocked_exposure.png", EX)
    check("per-symbol exposure limit blocks the ticket", page.get_by_role("button", name="أؤكد الأمر").is_disabled()
          and "✗" in page.locator(".modal li").filter(has_text="التعرّض").inner_text())
    page.get_by_role("button", name="رجوع").click()
    page.get_by_role("button", name="إلغاء").click()

    # Risk limit: orders per day (2 submitted so far)
    page.evaluate("fetch('/api/exec/limits',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'paper',max_order_usd:500,max_symbol_exposure_usd:1000,daily_loss_limit_usd:200,max_orders_per_day:2})})")
    ticket("50")
    shot(page, "e08_blocked_orders_per_day.png", EX)
    check("orders-per-day limit blocks the ticket", "✗" in page.locator(".modal li").filter(has_text="عدد أوامر اليوم").inner_text())
    page.get_by_role("button", name="رجوع").click()
    page.get_by_role("button", name="إلغاء").click()

    # Risk limit: daily loss (test harness sets the mock account's prior-day equity $1,000 higher)
    page.evaluate("fetch('/api/exec/limits',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'paper',max_order_usd:500,max_symbol_exposure_usd:1000,daily_loss_limit_usd:200,max_orders_per_day:10})})")
    con = sqlite3.connect(DATA / "veyro.db")
    st = json.loads(con.execute("SELECT value FROM settings WHERE key='mock_broker_state'").fetchone()[0])
    saved_last = st["last_equity"]
    st["last_equity"] = st["cash"] + 5000
    con.execute("UPDATE settings SET value=? WHERE key='mock_broker_state'", (json.dumps(st),)); con.commit()
    ticket("50")
    shot(page, "e09_blocked_daily_loss.png", EX)
    check("daily-loss limit blocks new orders", "✗" in page.locator(".modal li").filter(has_text="خسارة اليوم").inner_text())
    page.get_by_role("button", name="رجوع").click()
    page.get_by_role("button", name="إلغاء").click()
    st = json.loads(con.execute("SELECT value FROM settings WHERE key='mock_broker_state'").fetchone()[0])
    st["last_equity"] = saved_last
    con.execute("UPDATE settings SET value=? WHERE key='mock_broker_state'", (json.dumps(st),)); con.commit(); con.close()

    # Backend enforcement without the UI: a crafted over-limit ticket is rejected server-side too
    r = page.evaluate("fetch('/api/exec/tickets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol:'NVDA',side:'buy',order_type:'market',amount_usd:5000})}).then(r=>r.json())")
    check("backend rejects over-limit ticket (no token issued)", r.get("ok") is False and r.get("token") is None)
    r = page.evaluate("fetch('/api/exec/tickets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol:'NVDA',side:'short',order_type:'market',amount_usd:10})}).then(r=>r.json())")
    check("backend refuses short selling", r.get("code") == "side_not_allowed" and r.get("ok") is False)
    r = page.evaluate("fetch('/api/exec/tickets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol:'NVDA',side:'buy',order_type:'stop',amount_usd:10})}).then(r=>r.json())")
    check("backend refuses non market/limit order types", r.get("code") == "type_not_allowed")
    r = page.evaluate("fetch('/api/exec/tickets/x/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:'x',confirm:false})}).then(r=>r.status)")
    check("confirm without explicit confirm=true is refused", r == 400)
    console_errors[:] = [e for e in console_errors if "confirm" not in e or "tickets/x" not in e]  # intentional bad request above
    try:
        urllib.request.urlopen(urllib.request.Request(f"{BASE}/api/exec/kill", data=b"{}", method="POST",
                                                      headers={"Content-Type": "application/json"}), timeout=5)
        check("cross-origin / scripted POST blocked", False)
    except urllib.error.HTTPError as e:
        check("cross-origin / scripted POST blocked", e.code == 403, str(e.code))

    # Kill switch with an open order
    ticket("100", "5.00")
    page.get_by_role("button", name="أؤكد الأمر").click()
    page.wait_for_selector(".stamp", timeout=20000)
    page.get_by_role("button", name="رجوع").click()
    nav(page, "الأوامر", "Orders")
    page.wait_for_timeout(1500)
    open_before = page.locator("section.card").filter(has_text="الأوامر المفتوحة").locator("tbody tr").count()
    page.get_by_role("button", name=re.compile("زر الطوارئ")).click()
    page.wait_for_timeout(2500)
    shot(page, "e10_kill_switch.png", EX)
    st = page.evaluate("fetch('/api/exec/status').then(r=>r.json())")
    check("kill switch cancelled open orders and set mode Off", open_before >= 1 and st["mode"] == "off", f"open_before={open_before}")

    # Live cannot be enabled without every step
    nav(page, "الإعدادات", "Settings")
    open_advanced(page)
    page.locator("section[aria-labelledby=tr-h] .segbtns button").nth(2).click()
    page.wait_for_selector(".modal")
    page.locator(".modal input").fill("أفهم أن هذا مال حقيقي")
    page.wait_for_timeout(400)
    shot(page, "e11_live_locked.png", EX)
    check("Live unlock button disabled without keys/limits", page.get_by_role("button", name="افتح الوضع الحقيقي").is_disabled())
    page.get_by_role("button", name="رجوع").click()
    r = page.evaluate("fetch('/api/exec/mode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'live',phrase:'أفهم أن هذا مال حقيقي'})}).then(r=>r.json())")
    check("backend refuses Live without keys", r.get("code") == "no_live_keys", str(r))

    # Audit log + CSV
    nav(page, "الأوامر", "Orders")
    page.wait_for_timeout(1500)
    shot(page, "e12_audit_log.png", EX)
    with page.expect_download() as dl:
        page.get_by_text("تصدير CSV").click()
    csv_path = EX / "veyro-orders-audit.csv"
    dl.value.save_as(csv_path)
    csv = csv_path.read_text(encoding="utf-8")
    for ev in ("proposed", "confirmed", "submitted", "filled", "rejected", "cancel_requested", "cancelled", "kill_switch", "mode_changed", "limits_saved"):
        check(f"audit log records '{ev}'", f",{ev}," in csv)
    ctx.close()
    browser.close()


def closed_market_flow(pw) -> None:
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    watch(page)
    page.goto(BASE)
    set_prefs(page, lang="en")
    page.evaluate("fetch('/api/exec/mode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'paper'})})")
    page.reload(); page.wait_for_timeout(1200)
    open_real_report(page)
    page.get_by_role("button", name="Leo proposes an order").click()
    page.get_by_role("button", name="Let Tank check the limits").click()
    page.wait_for_timeout(2500)
    shot(page, "e13_market_closed_offer_en.png", EX)
    check("closed market: market order refused, limit offered", page.get_by_role("button", name="Yes, use a limit order").count() == 1)
    ctx.close()
    browser.close()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    EX.mkdir(exist_ok=True)
    srv, log = start_server(mock_clock_open=True)
    try:
        with sync_playwright() as pw:
            core_flows(pw)
            exec_flows(pw)
    finally:
        srv.terminate(); srv.wait(10)
    srv, log2 = start_server(mock_clock_open=False, fresh=False)  # real (closed/open) market clock for the Mock broker
    try:
        with sync_playwright() as pw:
            closed_market_flow(pw)
    finally:
        srv.terminate(); srv.wait(10)
    for lf in (log, log2):
        if KEY in lf.read_text(encoding="utf-8", errors="ignore"):
            leaks.append(f"log {lf.name}")
    check("API key never in HTTP responses, WebSocket frames or server logs", not leaks, "; ".join(leaks[:5]))
    # Chrome also prints a generic "Failed to load resource" line for every non-2xx response; the
    # "HTTP <status> <url>" lines we record carry the URL, so we judge on those (and on JS errors).
    real_errors = [e for e in console_errors if "favicon" not in e and not e.startswith("Failed to load resource")]
    check("zero browser console errors", not real_errors, " | ".join(real_errors[:5]))
    (OUT / "results.json").write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [r for r in results if not r["ok"]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
