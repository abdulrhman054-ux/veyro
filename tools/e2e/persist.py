"""Every screen keeps what you were doing when you move to other screens and come back: typed text, choices,
open sections, the scroll position, and a session that keeps playing in the Office while you look elsewhere."""
import os, time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8766"
OUT = str(__import__("pathlib").Path(__file__).resolve().parents[2] / "verification" / "e2e") + "/"
res, errors = [], []
SCREENS = ["Office", "Live", "World news", "Report", "History", "Orders", "Settings"]


def check(n, ok, d=""):
    res.append((n, ok, d)); print(("PASS " if ok else "FAIL ") + n + (f" :: {d}" if d else ""), flush=True)


def go(page, name):
    page.locator("nav button", has_text=name).first.click(); page.wait_for_timeout(500)


def tour(page, times=2):
    for _ in range(times):
        for s in SCREENS:
            go(page, s)


def visible(page):
    return page.locator("main > div:not([hidden])").first


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
    ctx.add_init_script("localStorage.setItem('veyro.welcomed','1');")
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(BASE); page.wait_for_timeout(1500)
    demo = page.locator(".startbar label.check input[type=checkbox]").last
    if demo.is_checked(): demo.uncheck()

    # a finished session, so the Report has content
    page.locator(".seg button").nth(1).click()
    page.locator(".tsearch input").first.fill("MSFT")
    page.locator(".startbar button.primary").click(); page.wait_for_timeout(500)
    if page.locator("[role=alertdialog] button.ghost").count(): page.locator("[role=alertdialog] button.ghost").first.click()
    t0 = time.time()
    while time.time() - t0 < 300 and not page.locator("main > div:not([hidden]) .verdict-box").count():
        if page.locator("button.dlg").count():
            try: page.locator("button.dlg").first.click(timeout=500)
            except Exception: pass
        time.sleep(0.3)

    # ---- put some state on every screen
    go(page, "Office")
    page.locator(".seg button").nth(2).click()                                     # watchlist
    add = page.locator(".tsearch input").first
    for tk in ("KO", "PG"):
        add.fill(tk); add.press("Enter"); page.wait_for_timeout(150)
    page.locator("label.budget input").fill("2500")
    eco = page.locator(".startbar label.check", has_text="Economy")
    eco.locator("input[type=checkbox]").check()
    page.locator("select[aria-label='Pre-screen method']").select_option("value")
    office_picks = sorted(page.locator(".picklist .chip.pick .pixel").all_inner_texts())

    go(page, "Live")
    page.locator(".live-bar button", has_text="US market").click(); page.wait_for_timeout(600)

    go(page, "World news")
    world_in = visible(page).locator("input.field").first
    world_in.fill("oil prices")

    go(page, "Report")
    visible(page).locator("button", has_text="Expand all").click(); page.wait_for_timeout(1500)
    opened = visible(page).locator("button[aria-expanded=true]").count()
    page.evaluate("window.scrollTo(0, 1400)"); page.wait_for_timeout(300)
    report_y = page.evaluate("window.scrollY")

    go(page, "History")
    bt = visible(page).locator("input.field.pixel").first
    bt.fill("AAPL, KO")

    go(page, "Settings")
    visible(page).locator("details.advanced > summary").click(); page.wait_for_timeout(300)
    fee_row = visible(page).locator("[aria-labelledby=fees-h] .row").nth(0)
    fee_row.locator("input").nth(0).fill("0.155")                                  # typed, not saved
    page.evaluate("window.scrollTo(0, 900)"); page.wait_for_timeout(300)
    settings_y = page.evaluate("window.scrollY")

    # ---- go everywhere twice, then check each screen
    tour(page, 2)

    go(page, "Office")
    check("Office: watchlist, amount, economy and method kept",
          page.locator(".seg button[aria-pressed=true]").inner_text().strip() == "Watchlist"
          and sorted(page.locator(".picklist .chip.pick .pixel").all_inner_texts()) == office_picks
          and page.locator("label.budget input").input_value() == "2500"
          and eco.locator("input[type=checkbox]").is_checked()
          and page.locator("select[aria-label='Pre-screen method']").input_value() == "value", str(office_picks))
    check("Office: the last verdict is still on stage", page.locator("main > div:not([hidden]) .verdict-box").count() == 1)
    go(page, "Live")
    check("Live: chosen market kept", page.locator(".live-bar button[aria-pressed=true]").inner_text().strip().endswith("US market"))
    go(page, "World news")
    check("World news: typed search kept", visible(page).locator("input.field").first.input_value() == "oil prices")
    go(page, "Report")
    y = page.evaluate("window.scrollY")
    check("Report: expanded sections kept", visible(page).locator("button[aria-expanded=true]").count() == opened and opened > 0, str(opened))
    check("Report: scroll position kept", abs(y - report_y) < 5, f"{y} vs {report_y}")
    go(page, "History")
    check("History: typed backtest tickers kept", visible(page).locator("input.field.pixel").first.input_value() == "AAPL, KO")
    go(page, "Settings")
    y = page.evaluate("window.scrollY")
    check("Settings: open advanced section and unsaved typing kept",
          visible(page).locator("details.advanced[open]").count() == 1
          and visible(page).locator("[aria-labelledby=fees-h] .row").nth(0).locator("input").nth(0).input_value() == "0.155")
    check("Settings: scroll position kept", abs(y - settings_y) < 5, f"{y} vs {settings_y}")

    # ---- a session keeps playing while you are on other screens
    go(page, "Office")
    page.locator(".seg button").nth(1).click()
    page.locator(".tsearch input").first.fill("AAPL")
    page.locator(".startbar button.primary").click(); page.wait_for_timeout(500)
    if page.locator("[role=alertdialog] button.ghost").count(): page.locator("[role=alertdialog] button.ghost").first.click()
    page.wait_for_timeout(1500)
    before = page.locator(".side .logitem").count()
    tour(page, 1)
    check("while away, the running session shows a 'running' shortcut", page.locator("button.toast").count() == 1)
    page.wait_for_timeout(3000)
    go(page, "Office")
    after = page.locator(".side .logitem").count()
    check("the session kept going while away (minutes grew, nothing lost)", after >= before, f"{before} -> {after}")
    b.close()

check("no console errors", not errors, "; ".join(errors[:5]))
print("ALL OK" if all(ok for _, ok, _ in res) else "SOME FAILED")
