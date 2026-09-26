import time, sys, json
from playwright.sync_api import sync_playwright
BASE = "http://127.0.0.1:8766"
OUT = str(__import__("pathlib").Path(__file__).resolve().parents[2] / "verification" / "e2e") + "/"
errors = []
res = []
def check(n, ok, d=""):
    res.append((n, ok, d)); print(("PASS " if ok else "FAIL ") + n + (f" :: {d}" if d else ""), flush=True)

def advance_until(page, cond, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond(): return True
        d = page.locator("button.dlg")
        if d.count():
            try: d.first.click(timeout=500)
            except Exception: pass
        time.sleep(0.4)
    return False

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=__import__("os").environ.get("CHROMIUM") or None)
    ctx = b.new_context(viewport={"width": 1440, "height": 1000}, locale="ar-SA")
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE); page.wait_for_timeout(1500)
    # dismiss welcome if present
    if page.locator(".modal-bg button.primary").count():
        page.locator(".modal-bg button.primary").first.click()
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    page.screenshot(path=OUT + "01_office_idle.png")
    # --- single real session with ticker search
    page.locator("button", has_text="سهم واحد").first.click()
    demo = page.locator("label.check input[type=checkbox]")
    if demo.is_checked(): demo.uncheck()
    inp = page.locator(".tsearch input").first
    inp.fill(""); inp.type("ارامكو", delay=40); page.wait_for_timeout(900)
    page.screenshot(path=OUT + "02_search.png")
    has_hit = page.locator(".tsearch-list li", has_text="2222.SR").count() > 0
    check("ticker search by Arabic name shows 2222.SR", has_hit)
    inp.press("Enter"); page.wait_for_timeout(300)
    check("picking fills the symbol", inp.input_value() == "2222.SR", inp.input_value())
    inp.fill("NVDA")
    page.locator("button.primary", has_text="ابدأ").first.click()
    page.wait_for_timeout(2500)
    page.screenshot(path=OUT + "03_session_running.png")
    ok = advance_until(page, lambda: page.locator(".verdict-box").count() > 0, 300)
    check("session reaches Leo's verdict", ok)
    page.screenshot(path=OUT + "04_verdict.png")
    # minutes full analysis expander
    btn = page.locator(".logitem .linkish").first
    if btn.count():
        btn.click(); page.wait_for_timeout(1500)
        check("minutes: full analysis expands", page.locator(".logitem .detail").count() > 0)
        page.screenshot(path=OUT + "05_minutes_detail.png")
    # --- stop test
    page.locator("button.primary", has_text="جلسة جديدة").first.click()
    page.wait_for_timeout(800)
    if page.locator("[role=alertdialog]").count(): page.locator("[role=alertdialog] button.ghost").click()
    page.wait_for_timeout(2500)
    t0 = time.time()
    page.locator("button.ghost", has_text="إيقاف").first.click()
    stopped = False
    while time.time() - t0 < 25:
        if page.locator("button.primary", has_text="جلسة جديدة").count(): stopped = True; break
        d = page.locator("button.dlg")
        if d.count():
            try: d.first.click(timeout=300)
            except Exception: pass
        time.sleep(0.2)
    check("Stop ends the session quickly", stopped, f"{time.time()-t0:.1f}s")
    page.screenshot(path=OUT + "06_after_stop.png")
    # --- beginner mode
    page.locator("button", has_text="أنا مبتدئ").first.click()
    page.locator("label.budget input").fill("1000")
    page.locator("label.budget select").select_option("SAR")
    page.locator("button", has_text="اقترح لي").first.click()
    page.wait_for_timeout(1500)
    page.screenshot(path=OUT + "07_beginner_picks.png")
    npick = page.locator(".chip.pick input[type=checkbox]").count()
    check("beginner suggestions shown", npick > 0, str(npick))
    page.locator("button.primary", has_text="حلّلها").first.click()
    ok = advance_until(page, lambda: page.locator("[aria-label='دليل المبتدئ']").count() > 0, 900)
    check("beginner guide appears after analysis", ok)
    page.wait_for_timeout(2500)
    page.screenshot(path=OUT + "08_beginner_guide.png", full_page=True)
    if page.locator("[aria-label='دليل المبتدئ'] button.primary").count():
        page.locator("[aria-label='دليل المبتدئ'] button.primary").click()
    # --- screen persistence: world news search text
    page.locator("nav button", has_text="أخبار العالم").click(); page.wait_for_timeout(1000)
    si = page.locator("main > div:not([hidden]) input.field").first
    if si.count():
        si.fill("النفط"); page.locator("nav button", has_text="المكتب").click(); page.wait_for_timeout(400)
        page.locator("nav button", has_text="أخبار العالم").click(); page.wait_for_timeout(400)
        check("world-news search text kept across screens", si.input_value() == "النفط", si.input_value())
    # --- report
    page.locator("nav button", has_text="التقرير").click(); page.wait_for_timeout(2000)
    page.screenshot(path=OUT + "09_report.png", full_page=True)
    check("report shows phases", page.locator(".phase").count() >= 4, str(page.locator(".phase").count()))
    # --- settings
    page.locator("nav button", has_text="الإعدادات").click(); page.wait_for_timeout(1200)
    page.screenshot(path=OUT + "10_settings.png", full_page=True)
    opts = page.locator("#deep option").all_inner_texts()
    check("deep model list offers Fable 5.1 and Haiku", any("Fable 5.1" in o for o in opts) and any("Haiku" in o for o in opts), str(opts[:4]))
    # --- english + mobile
    page.set_viewport_size({"width": 390, "height": 860})
    page.locator("nav button", has_text="المكتب").click(); page.wait_for_timeout(800)
    sw = page.evaluate("document.documentElement.scrollWidth")
    check("no horizontal scroll at 390px", sw <= 392, str(sw))
    page.screenshot(path=OUT + "11_mobile.png", full_page=True)
    b.close()
check("no console errors", not errors, "; ".join(errors[:5]))
json.dump(res, open(OUT + "results.json", "w"), ensure_ascii=False, indent=1)
