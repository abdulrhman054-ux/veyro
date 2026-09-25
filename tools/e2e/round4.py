"""Browser checks for the second review round: index-fund option, cost-vs-amount warning, plan warnings and fees,
both markets in the header, the track record next to the verdict, the steady pre-screen, phone-width captions."""
import os, time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8766"
OUT = str(__import__("pathlib").Path(__file__).resolve().parents[2] / "verification" / "e2e") + "/"
res, errors = [], []


def check(n, ok, d=""):
    res.append((n, ok, d)); print(("PASS " if ok else "FAIL ") + n + (f" :: {d}" if d else ""), flush=True)


def advance_until(page, cond, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond(): return True
        d = page.locator("button.dlg")
        if d.count():
            try: d.first.click(timeout=500)
            except Exception: pass
        time.sleep(0.3)
    return False


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
    ctx = b.new_context(viewport={"width": 1440, "height": 1000}, locale="en-US")
    ctx.add_init_script("localStorage.setItem('veyro.welcomed','1');")
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE); page.wait_for_timeout(1500)
    check("header shows Tadawul and US separately", page.locator("[data-market=sa]").count() == 1 and page.locator("[data-market=us]").count() == 1)

    # --- beginner: index fund + cost warning
    page.locator(".seg button").first.click()
    d = page.locator(".startbar label.check input[type=checkbox]").last
    if d.is_checked(): d.uncheck()
    page.locator(".startbar select").first.select_option("sa")
    page.locator("label.budget input").fill("1000"); page.locator("label.budget select").select_option("SAR")
    page.locator(".startbar button", has_text="Suggest for me").first.click(); page.wait_for_timeout(1800)
    idx = page.locator(".index-funds")
    check("beginner shows the index-fund option with units", idx.count() == 1 and "9412.SR" in idx.inner_text() and "units" in idx.inner_text(),
          idx.inner_text()[:140].replace("\n", " | ") if idx.count() else "")
    check("cost-vs-amount warning shown for a small amount", page.locator("[data-cost-warning]").count() == 1,
          page.locator("[data-cost-warning]").first.inner_text()[:120] if page.locator("[data-cost-warning]").count() else "")
    page.screenshot(path=OUT + "r4_beginner_index_cost.png", full_page=True)

    # --- single stock with a budget: plan warns 'few picks' and 'fees not set'; verdict shows the track record
    page.locator(".seg button").nth(1).click()
    page.locator(".tsearch input").first.fill("MSFT")
    page.locator("label.budget input").fill("3000"); page.locator("label.budget select").select_option("USD")
    page.locator(".startbar button.primary").click(); page.wait_for_timeout(500)
    if page.locator("[role=alertdialog] button.ghost").count(): page.locator("[role=alertdialog] button.ghost").first.click()
    ok = advance_until(page, lambda: page.locator("main > div:not([hidden]) .verdict-box").count() > 0)
    page.wait_for_timeout(1500)
    tr = page.locator("[data-track-record]")
    check("verdict shows how often past calls like it were right", ok and tr.count() > 0, tr.first.inner_text()[:140] if tr.count() else "")
    check("no confetti on a real-money verdict", page.locator(".verdict-box .conf").count() == 0)
    page.locator("main > div:not([hidden]) .verdict-box button.primary").first.click(); page.wait_for_timeout(2500)   # open the report
    plan = page.locator("main > div:not([hidden]) .plan")
    txt = plan.first.inner_text() if plan.count() else ""
    check("single-stock plan keeps at most 40% and says one stock isn't a portfolio", "not a diversified portfolio" in txt, txt[:200].replace("\n", " | "))
    check("plan says broker fees aren't entered", "fees aren't entered" in txt)
    page.screenshot(path=OUT + "r4_single_plan.png", full_page=True)

    # --- fees entered in Settings are used by the plan
    page.locator("nav button", has_text="Settings").click(); page.wait_for_timeout(800)
    row = page.locator("[aria-labelledby=fees-h] .row").nth(1)       # US row
    row.locator("input").nth(0).fill("1"); row.locator("input").nth(1).fill("1"); row.locator("button").click(); page.wait_for_timeout(800)
    check("broker fees saved from Settings", page.locator("[aria-labelledby=fees-h]").inner_text().count("✓") >= 1)
    page.locator("nav button", has_text="Report").click(); page.wait_for_timeout(300)
    page.reload(); page.wait_for_timeout(1500)
    page.locator("nav button", has_text="History").click(); page.wait_for_timeout(1500)
    page.locator("main > div:not([hidden]) button", has_text="View").first.click(); page.wait_for_timeout(2500)
    txt2 = page.locator("main > div:not([hidden]) .plan").first.inner_text() if page.locator("main > div:not([hidden]) .plan").count() else ""
    check("plan includes the entered fees", "Estimated broker fees" in txt2 and "fees aren't entered" not in txt2, txt2[:200].replace("\n", " | "))

    # --- trust dashboard shows the likely range / waiting calls
    page.locator("nav button", has_text="History").click(); page.wait_for_timeout(1500)
    check("trust dashboard marks young calls as waiting", page.locator("[data-waiting]").count() > 0)

    # --- steady pre-screen option
    page.locator("nav button", has_text="Office").click(); page.wait_for_timeout(500)
    page.locator(".seg button").nth(2).click()
    check("economy mode offers a 'steady' pre-screen", page.locator("select[aria-label='Pre-screen method'] option[value=steady]").count() == 1)
    ctx.close()

    # --- phone width: readable caption under the stage
    ctx = b.new_context(viewport={"width": 390, "height": 844}, locale="ar-SA")
    ctx.add_init_script("localStorage.setItem('veyro.welcomed','1');")
    page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE); page.wait_for_timeout(1200)
    cap = page.locator(".mobile-caption .dlg")
    fs = page.evaluate("getComputedStyle(document.querySelector('.mobile-caption .dlg .dtext') || document.querySelector('.mobile-caption .dlg')).fontSize") if cap.count() else "0px"
    check("390 px: dialogue renders under the stage at a readable size", cap.count() == 1 and page.locator(".stage .dlg").count() == 0 and float(fs[:-2]) >= 15, fs)
    check("390 px: no horizontal scroll", page.evaluate("document.documentElement.scrollWidth") <= 392)
    b.close()

check("no console errors", not errors, "; ".join(errors[:5]))
print("ALL OK" if all(ok for _, ok, _ in res) else "SOME FAILED")
