"""Stop is immediate from every state: right after Start, mid-run (single stock, watchlist, beginner),
by the Esc key, and a verdict already shown is never taken back."""
import os, time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8766"
OUT_DBG = str(__import__("pathlib").Path(__file__).resolve().parents[2] / "verification" / "e2e") + "/"
res, errors = [], []


def check(n, ok, d=""):
    res.append((n, ok, d)); print(("PASS " if ok else "FAIL ") + n + (f" :: {d}" if d else ""), flush=True)


def idle(page):
    """The start button is back (the run has ended on screen)."""
    return page.locator(".startbar button.primary").count() > 0 and page.locator(".startbar button.ghost", has_text="Stop").count() == 0


def stop_and_time(page, how="click"):
    t0 = time.time()
    if how == "esc":
        page.keyboard.press("Escape")
    else:
        page.locator(".startbar button.ghost", has_text="Stop").click()
    while time.time() - t0 < 15 and not idle(page):
        time.sleep(0.05)
    return time.time() - t0


def status_of_last(page):
    return page.evaluate("fetch('/api/sessions?light=1').then(r => r.json()).then(j => j.sessions.map(s => s.status))")


def close_modals(page):
    for _ in range(3):
        if not page.locator(".modal-bg").count():
            return
        page.locator(".modal-bg button.primary").last.click(); page.wait_for_timeout(300)


def begin(page, mode, tickers=None):
    close_modals(page)
    page.wait_for_timeout(800)   # a stopped beginner run opens its guide (the plan for what finished) a moment later
    close_modals(page)
    page.locator(".seg button").nth(mode).click()
    if mode == 1:
        page.locator(".tsearch input").first.fill(tickers[0])
    elif mode == 2:
        if page.locator(".picklist button.linkish").count(): page.locator(".picklist button.linkish").click()
        for x in list(page.locator(".picklist .chip.pick .x").all()): x.click()
        add = page.locator(".tsearch input").first
        for tk in tickers:
            add.fill(tk); add.press("Enter"); page.wait_for_timeout(120)
    try:
        page.locator(".startbar button.primary").click(timeout=10000)
    except Exception:
        page.screenshot(path=OUT_DBG + f"stop_blocked_{mode}.png", full_page=True); raise
    page.wait_for_timeout(300)
    if page.locator("[role=alertdialog] button.ghost").count(): page.locator("[role=alertdialog] button.ghost").first.click()
    if page.locator("[role=alertdialog] button.primary").count(): page.locator("[role=alertdialog] button.primary").first.click()


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
    ctx.add_init_script("localStorage.setItem('veyro.welcomed','1');")
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE); page.wait_for_timeout(1500)
    d = page.locator(".startbar label.check input[type=checkbox]").last
    if d.is_checked(): d.uncheck()

    begin(page, 1, ["AAPL"]); page.wait_for_timeout(150)                        # right after Start
    t = stop_and_time(page)
    check("Stop right after Start ends at once", t < 1.5, f"{t:.2f}s")
    page.wait_for_timeout(2500)
    check("...and the session stays 'cancelled' after the worker winds down", status_of_last(page)[0] == "cancelled", str(status_of_last(page)[:2]))

    begin(page, 1, ["MSFT"]); page.wait_for_timeout(4000)                       # mid-run
    t = stop_and_time(page)
    check("Stop mid-run (single stock) ends at once", t < 1.5, f"{t:.2f}s")

    begin(page, 2, ["KO", "PG", "NVDA"]); page.wait_for_timeout(3000)            # watchlist
    t = stop_and_time(page)
    check("Stop mid-run (watchlist) ends at once and starts nothing more", t < 1.5, f"{t:.2f}s")
    page.wait_for_timeout(2500)
    running = [s for s in status_of_last(page) if s == "running"]
    check("...no session is left running", not running, str(status_of_last(page)[:4]))

    close_modals(page)
    page.locator(".seg button").first.click()                                  # beginner
    page.locator("label.budget input").fill("1000"); page.locator("label.budget select").select_option("SAR")
    page.locator(".startbar button", has_text="Suggest for me").first.click(); page.wait_for_timeout(1500)
    page.locator(".startbar button.primary").click(); page.wait_for_timeout(3000)
    t = stop_and_time(page)
    check("Stop mid-run (beginner) ends at once", t < 1.5, f"{t:.2f}s")

    begin(page, 1, ["AMD"]); page.wait_for_timeout(2500)                         # the Esc shortcut
    page.locator("body").click(position={"x": 5, "y": 5})
    t = stop_and_time(page, "esc")
    check("Esc stops at once", t < 1.5, f"{t:.2f}s")

    begin(page, 1, ["INTC"])                                                     # to the verdict, then no Stop
    t0 = time.time()
    while time.time() - t0 < 300 and not page.locator("main > div:not([hidden]) .verdict-box").count():
        if page.locator("button.dlg").count():
            try: page.locator("button.dlg").first.click(timeout=500)
            except Exception: pass
        time.sleep(0.3)
    page.keyboard.press("Escape"); page.wait_for_timeout(800)
    check("a verdict already shown is never taken back by Stop", page.locator("main > div:not([hidden]) .verdict-box").count() == 1
          and status_of_last(page)[0] == "done", str(status_of_last(page)[:1]))
    b.close()

check("no console errors", not errors, "; ".join(errors[:5]))
print("ALL OK" if all(ok for _, ok, _ in res) else "SOME FAILED")
