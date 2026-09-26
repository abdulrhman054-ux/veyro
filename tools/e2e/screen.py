"""Free screen without AI: the window with its four checks and verdicts (Arabic and English, 390 px), the
"analyse only those that passed" hand-off to the watchlist, economy mode's quality pre-screen never paying for an
excluded stock, the glossary terms and the track record in the trust dashboard."""
import os, time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8766"
OUT = str(__import__("pathlib").Path(__file__).resolve().parents[2] / "verification" / "e2e") + "/"
res, errors = [], []
SYMS = ["KO", "AAPL", "1120.SR", "1211.SR", "NVDA"]


def check(n, ok, d=""):
    res.append((n, ok, d)); print(("PASS " if ok else "FAIL ") + n + (f" :: {d}" if d else ""), flush=True)


def watchlist(page, syms):
    page.locator(".seg button").nth(2).click()
    if page.locator(".picklist button.linkish").count(): page.locator(".picklist button.linkish").click()
    for x in list(page.locator(".picklist .chip.pick .x").all()): x.click()
    add = page.locator(".tsearch input").first
    for tk in syms:
        add.fill(tk); add.press("Enter"); page.wait_for_timeout(120)


def verdicts(page):
    return {r.get_attribute("data-verdict"): None for r in page.locator(".free-screen-tbl tr[data-verdict]").all()} and \
        {page.locator(".free-screen-tbl tr[data-verdict]").nth(i).locator("b.pixel").inner_text(): page.locator(".free-screen-tbl tr[data-verdict]").nth(i).get_attribute("data-verdict")
         for i in range(page.locator(".free-screen-tbl tr[data-verdict]").count())}


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
    for lang in ("ar", "en"):
        ctx = b.new_context(viewport={"width": 1440, "height": 1000})
        ctx.add_init_script(f"localStorage.setItem('veyro.welcomed','1'); localStorage.setItem('veyro.prefs.v1', JSON.stringify({{lang: '{lang}'}}));")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(BASE); page.wait_for_timeout(1500)
        L = lang.upper()
        watchlist(page, SYMS)
        page.locator("[data-free-screen]").click()
        t0 = time.time()
        while time.time() - t0 < 30 and not page.locator(".free-screen-tbl").count():
            time.sleep(0.2)
        v = verdicts(page)
        check(f"{L}: each stock gets its screening verdict", v == {"KO": "pass", "AAPL": "watch", "1120.SR": "pass", "1211.SR": "exclude", "NVDA": "insufficient"}, str(v))
        txt = page.locator(".free-screen").inner_text()
        z = "خطر تعثّر مالي" if lang == "ar" else "Financial distress risk"
        check(f"{L}: an excluded stock shows its reason without a click", z in page.locator(".free-screen-tbl tr.fs-why:not([hidden])").first.inner_text(),
              page.locator(".free-screen-tbl tr.fs-why:not([hidden])").first.inner_text()[:120])
        check(f"{L}: a bank is marked 'Altman doesn't apply', not scored", ("ما ينطبق" if lang == "ar" else "n/a (financial") in txt)
        check(f"{L}: it says plainly it's a screen, not a recommendation", ("مو توصية شراء" if lang == "ar" else "not a buy recommendation") in txt)
        page.locator(".free-screen-tbl tr[data-verdict=pass] button.linkish").first.click(); page.wait_for_timeout(300)
        check(f"{L}: opening a row lists the 9 quality tests", page.locator(".fs-tests .fs-test").count() == 9, str(page.locator(".fs-tests .fs-test").count()))
        page.wait_for_timeout(700); page.screenshot(path=OUT + f"screen_{lang}.png", full_page=False)
        page.locator("[data-analyse-passes]").click(); page.wait_for_timeout(500)
        picks = sorted(page.locator(".picklist .chip.pick .pixel").all_inner_texts())
        check(f"{L}: 'analyse only those that passed' puts just them in the watchlist", picks == ["1120.SR", "KO"] and page.locator(".modal-bg").count() == 0, str(picks))
        ctx.close()

    # economy mode: the quality pre-screen analyses the best and never an excluded stock
    ctx = b.new_context(viewport={"width": 1440, "height": 1000}, locale="en-US")
    ctx.add_init_script("localStorage.setItem('veyro.welcomed','1');")
    page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE); page.wait_for_timeout(1500)
    d = page.locator(".startbar label.check input[type=checkbox]").last
    if d.is_checked(): d.uncheck()
    watchlist(page, ["1211.SR", "AAPL", "KO", "NVDA"])
    page.locator("label.budget input").fill("")
    eco = page.locator(".startbar label.check", has_text="Economy")
    eco.locator("input[type=checkbox]").check()
    eco.locator("select").first.select_option("2")
    page.locator("select[aria-label='Pre-screen method']").select_option("quality")
    page.locator(".startbar button.primary").click(); page.wait_for_timeout(500)
    if page.locator("[role=alertdialog] button.primary").count(): page.locator("[role=alertdialog] button.primary").first.click()
    t0 = time.time()
    while time.time() - t0 < 30 and not page.locator(".side .card", has_text="Free pre-screen").count():
        time.sleep(0.2)
    page.wait_for_timeout(800)
    rows = page.locator(".side .card", has_text="Free pre-screen").locator("li")
    lines = [rows.nth(i).inner_text().replace("\n", " ") for i in range(rows.count())]
    chosen = [x.split(" ")[0] for x in lines if "full analysis" in x]
    check("economy 'quality': analyses the passing and watched stocks, never the excluded one", chosen == ["KO", "AAPL"] and not any(x.startswith("1211.SR") and "full analysis" in x for x in lines), " || ".join(lines))
    page.screenshot(path=OUT + "screen_economy_quality.png", full_page=True)
    page.locator(".startbar button.ghost", has_text="Stop").click(); page.wait_for_timeout(1500)
    for _ in range(3):
        if not page.locator(".modal-bg").count(): break
        page.locator(".modal-bg button.primary").last.click(); page.wait_for_timeout(300)

    # glossary and the trust dashboard's screen record
    page.locator("nav button", has_text="History").click(); page.wait_for_timeout(2000)
    tr = page.locator("[data-screen-track]")
    check("trust dashboard shows the free-screen record (waiting for 20 and 60 days)", tr.count() == 1 and "waiting" in tr.inner_text(), tr.inner_text()[:160] if tr.count() else "")
    ctx.close()

    ctx = b.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script("localStorage.setItem('veyro.welcomed','1'); localStorage.setItem('veyro.prefs.v1', JSON.stringify({lang: 'ar'}));")
    page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE); page.wait_for_timeout(1200)
    page.locator(".seg button").nth(1).click()
    page.locator(".tsearch input").first.fill("KO")
    page.locator("[data-free-screen]").click()
    t0 = time.time()
    while time.time() - t0 < 30 and not page.locator(".free-screen-tbl").count():
        time.sleep(0.2)
    check("390 px: one stock screens and the page doesn't scroll sideways", page.locator(".free-screen-tbl tr[data-verdict=pass]").count() == 1
          and page.evaluate("document.documentElement.scrollWidth") <= 392, str(page.evaluate("document.documentElement.scrollWidth")))
    page.wait_for_timeout(700); page.screenshot(path=OUT + "screen_390.png", full_page=False)
    b.close()

check("no console errors", not errors, "; ".join(errors[:5]))
print("ALL OK" if all(ok for _, ok, _ in res) else "SOME FAILED")
