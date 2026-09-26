"""Screenshots for the README (docs/screenshots/), taken from the test server: demo mode and sample data only,
no real prices or analysis. Run: start tools/e2e/ui_server.py (port 8766), then
    python tools/capture_readme.py
"""
import os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8766"
OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
W, H = 1440, 900


def ctx_for(b, lang, w=W, h=H):
    c = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
    c.add_init_script(f"localStorage.setItem('veyro.welcomed','1'); localStorage.setItem('veyro.prefs.v1', JSON.stringify({{lang: '{lang}'}}));")
    return c


def wait(page, sel, t=120):
    t0 = time.time()
    while time.time() - t0 < t:
        if page.locator(sel).count():
            return True
        time.sleep(0.2)
    return False


def shot(page, name, full=False):
    page.wait_for_timeout(700)
    page.screenshot(path=str(OUT / name), full_page=full)
    print("saved", name)


def demo_run(page, ticker):
    page.locator(".seg button").nth(1).click()
    d = page.locator(".startbar label.check input[type=checkbox]").last
    if not d.is_checked(): d.check()
    page.locator(".tsearch input").first.fill(ticker)
    page.keyboard.press("Escape")                       # close the search suggestions
    page.locator(".startbar button.primary").click()
    page.mouse.click(5, 5)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)

    # 1-3. Arabic office, a Saudi stock in demo mode: the debate, the risk room, the decision
    c = ctx_for(b, "ar"); page = c.new_page(); page.goto(BASE); page.wait_for_timeout(1500)
    shot(page, "01_office_ar.png")
    demo_run(page, "2222.SR")
    wait(page, ".room.scene-debate"); page.wait_for_timeout(2500); shot(page, "02_debate_ar.png")
    wait(page, ".room.scene-risk [data-quip=warn]"); page.wait_for_timeout(2600); shot(page, "03_risk_ar.png")   # after the scene wipe
    wait(page, "main > div:not([hidden]) .verdict-box", 200)
    page.keyboard.press("Escape"); page.evaluate("document.activeElement && document.activeElement.blur()"); page.mouse.click(5, 5)
    shot(page, "04_decision_ar.png")
    # the minutes / report of that run
    page.locator("main > div:not([hidden]) .verdict-box button.primary").first.click(); page.wait_for_timeout(2500)
    shot(page, "05_report_ar.png")
    c.close()

    # 6. beginner mode: amount -> suggestions that fit it (Saudi market, SAR)
    c = ctx_for(b, "ar"); page = c.new_page(); page.goto(BASE); page.wait_for_timeout(1500)
    page.locator(".seg button").first.click()
    page.locator(".startbar select").first.select_option("sa")
    page.locator("label.budget input").fill("5000"); page.locator("label.budget select").select_option("SAR")
    page.locator(".startbar button", has_text="اقترح لي").first.click(); page.wait_for_timeout(2500)
    shot(page, "06_beginner_ar.png")
    c.close()

    # 7. free screen without AI on a mixed US + Saudi watchlist
    c = ctx_for(b, "ar"); page = c.new_page(); page.goto(BASE); page.wait_for_timeout(1500)
    page.locator(".seg button").nth(2).click()
    if page.locator(".picklist button.linkish").count(): page.locator(".picklist button.linkish").click()
    for x in list(page.locator(".picklist .chip.pick .x").all()): x.click()
    add = page.locator(".tsearch input").first
    for tk in ("KO", "AAPL", "2222.SR", "1120.SR", "1211.SR"):
        add.fill(tk); add.press("Enter"); page.wait_for_timeout(120)
    page.locator("[data-free-screen]").click(); wait(page, ".free-screen-tbl")
    shot(page, "07_free_screen_ar.png")
    c.close()

    # 8. live board (fake feed in the test server)
    c = ctx_for(b, "ar"); page = c.new_page(); page.goto(BASE); page.wait_for_timeout(1500)
    page.locator("nav button", has_text="مباشر").click(); page.wait_for_timeout(4000)
    shot(page, "08_live_ar.png")
    page.locator(".live-bar button", has_text="السوق الأمريكي").click(); page.wait_for_timeout(4000)
    shot(page, "08b_live_us_ar.png")
    c.close()

    # 9. English office, a US stock in demo mode
    c = ctx_for(b, "en"); page = c.new_page(); page.goto(BASE); page.wait_for_timeout(1500)
    demo_run(page, "AAPL")
    wait(page, ".room.scene-charts", 60); page.wait_for_timeout(2500); shot(page, "09_charts_en.png")
    c.close()

    # 10. phone width
    c = ctx_for(b, "ar", 390, 844); page = c.new_page(); page.goto(BASE); page.wait_for_timeout(1500)
    demo_run(page, "2222.SR"); wait(page, ".mobile-caption button.dlg", 60); page.wait_for_timeout(3000)
    page.evaluate("window.scrollTo(0, document.querySelector('.office').getBoundingClientRect().top + window.scrollY - 8)")
    shot(page, "10_phone_ar.png")
    c.close()
    b.close()
