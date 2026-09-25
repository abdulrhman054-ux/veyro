"""Browser checks for the 2026-09 review: first-run language, 'both markets', plan wording, and the optional
Sharia screen turned on and off (suggestions, the plan and the badges must change; off = as before)."""
import json, os, time
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


def put_settings(page, body):
    return page.evaluate("b => fetch('/api/settings', {method: 'PUT', headers: {'content-type': 'application/json'}, body: JSON.stringify(b)}).then(r => r.status)", body)


def beginner_picks(page, market, amount, cur):
    page.locator("nav button", has_text="Office").click(); page.wait_for_timeout(400)
    page.locator(".seg button").first.click()
    page.locator(".startbar select").first.select_option(market)
    page.locator("label.budget input").fill(str(amount))
    page.locator("label.budget select").select_option(cur)
    page.locator(".startbar button", has_text="Suggest for me").first.click()
    page.wait_for_timeout(1800)
    return [page.locator(".chip.pick .pixel").nth(i).inner_text() for i in range(page.locator(".chip.pick .pixel").count())]


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
    # --- a new visitor with an English browser gets English (was: an Arabic-only welcome blocking the language button)
    ctx = b.new_context(viewport={"width": 1440, "height": 1000}, locale="en-US")
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE); page.wait_for_timeout(1500)
    check("first run follows an English browser", page.evaluate("document.documentElement.lang") == "en"
          and page.locator(".modal-bg").count() > 0 and "Welcome" in page.locator(".modal-bg").first.inner_text())
    page.locator(".modal-bg button.primary").first.click(); page.wait_for_timeout(300)
    page.locator(".startbar label.check input[type=checkbox]").last.uncheck() if page.locator(".startbar label.check input[type=checkbox]").last.is_checked() else None

    # --- 'both markets' suggests from both
    both = beginner_picks(page, "both", 1000, "SAR")
    check("beginner 'both markets' mixes Saudi and US picks", any(s.endswith(".SR") for s in both) and any(not s.endswith(".SR") for s in both), str(both))

    # --- Sharia screen: off by default, no badges
    page.locator("nav button", has_text="Settings").click(); page.wait_for_timeout(800)
    tog = page.locator("#s-sharia").locator("xpath=..").locator("input[type=checkbox]").first
    check("Sharia screening is in Settings and off by default", tog.count() == 1 and not tog.is_checked())
    off = beginner_picks(page, "sa", 1000, "SAR")
    check("off: no Sharia badges or notes", page.locator("[data-sharia]").count() == 0 and page.locator("text=Sharia screening is on").count() == 0, str(off))
    page.screenshot(path=OUT + "sharia_off_beginner.png", full_page=True)

    # --- turn it on from Settings
    page.locator("nav button", has_text="Settings").click(); page.wait_for_timeout(600)
    tog.check(); page.wait_for_timeout(800)
    check("toggle on shows the methodology picker (AAOIFI default)", page.locator("#sharia-method").input_value() == "aaoifi")
    page.screenshot(path=OUT + "sharia_settings_on.png", full_page=True)
    on = beginner_picks(page, "sa", 1000, "SAR")
    page.wait_for_timeout(1200)
    statuses = [page.locator(".chip.pick [data-sharia]").nth(i).get_attribute("data-sharia") for i in range(page.locator(".chip.pick [data-sharia]").count())]
    check("on: suggestions change (non-compliant stc dropped)", "7010.SR" in off and "7010.SR" not in on and on != off, f"off={off} on={on}")
    check("on: every suggestion carries a Compliant badge", statuses and all(s == "compliant" for s in statuses), str(statuses))
    check("on: the note and disclaimer are shown", page.locator("text=Sharia screening is on").count() > 0 and page.locator("text=not a religious ruling").count() > 0)
    page.screenshot(path=OUT + "sharia_on_beginner.png", full_page=True)

    # --- watchlist badges, plan excludes the non-compliant bank, verdict/report badge
    page.locator(".seg button").nth(2).click()
    add = page.locator(".tsearch input").first
    for tk in ("AAPL", "JPM", "MSFT"):
        add.fill(tk); add.press("Enter"); page.wait_for_timeout(200)
    page.wait_for_timeout(1500)
    wl = {page.locator(".picklist .chip.pick").nth(i).locator(".pixel").inner_text(): page.locator(".picklist .chip.pick").nth(i).locator("[data-sharia]").get_attribute("data-sharia")
          for i in range(page.locator(".picklist .chip.pick").count())}
    check("watchlist chips carry badges", wl.get("JPM") == "not_compliant" and wl.get("AAPL") == "compliant", json.dumps(wl))
    page.locator("label.budget input").fill("3000"); page.locator("label.budget select").select_option("USD")
    page.locator(".startbar button.primary").click(); page.wait_for_timeout(400)
    if page.locator("[role=alertdialog] button.primary").count(): page.locator("[role=alertdialog] button.primary").first.click()
    saw_verdict_badge = False

    def done():
        global saw_verdict_badge
        if page.locator(".verdict-box .sharia-panel [data-sharia]").count(): saw_verdict_badge = True
        return page.locator(".modal .plan").count() > 0
    ok = advance_until(page, done, 400)
    page.wait_for_timeout(2500)
    page.screenshot(path=OUT + "sharia_on_plan.png", full_page=True)
    plan_txt = page.locator(".modal .plan").first.inner_text() if ok else ""
    check("on: plan leaves out the non-compliant bank and says why", ok and page.locator("[data-sharia-excluded=JPM]").count() == 1
          and "JPM" not in page.locator(".modal .plan .reco.buy").first.inner_text(), plan_txt[:300].replace("\n", " | "))
    check("on: the verdict shows a Sharia badge", saw_verdict_badge)
    check("ranking rows carry badges", page.locator(".modal .board-rank [data-sharia]").count() >= 3)
    check("plan says '1 share' (singular)", "1 shares" not in plan_txt, plan_txt[:200].replace("\n", " | "))
    page.locator(".modal .board-rank button").first.click(); page.wait_for_timeout(2000)   # "View" opens that report
    rp = page.locator("main > div:not([hidden]) .sharia-panel")   # the Office (and its verdict box) stays mounted, hidden
    check("report shows the Sharia panel with methodology and data date", rp.count() > 0
          and "AAOIFI" in rp.first.inner_text() and "2026-06-30" in rp.first.inner_text(), rp.first.inner_text()[:160] if rp.count() else "")
    page.screenshot(path=OUT + "sharia_on_report.png", full_page=True)

    # --- switch methodology: MSCI (total-assets based) is accepted and results follow it
    check("methodology switch saved", put_settings(page, {"sharia_method": "msci"}) == 200)
    # --- turn it off again: app back to exactly the old behaviour
    check("toggle off saved", put_settings(page, {"sharia_enabled": False, "sharia_method": "aaoifi"}) == 200)
    page.reload(); page.wait_for_timeout(1500)
    again = beginner_picks(page, "sa", 1000, "SAR")
    check("off again: suggestions back to the original, no badges", again == off and page.locator("[data-sharia]").count() == 0, str(again))
    b.close()

check("no console errors", not errors, "; ".join(errors[:5]))
print("ALL OK" if all(ok for _, ok, _ in res) else "SOME FAILED")
