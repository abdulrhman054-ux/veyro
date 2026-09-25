"""Browser checks for the fourth review round (frontend findings): each one failed on the build before its fix."""
import os, tempfile, time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8766"
OUT = str(__import__("pathlib").Path(__file__).resolve().parents[2] / "verification" / "e2e") + "/"
NOPRICE = os.path.join(tempfile.gettempdir(), "veyro_e2e_noprice")
res, errors = [], []


def check(n, ok, d=""):
    res.append((n, ok, d)); print(("PASS " if ok else "FAIL ") + n + (f" :: {d}" if d else ""), flush=True)


def visible(page):
    return page.locator("main > div:not([hidden])").first


def js(page, code):
    return page.evaluate(code)


if os.path.exists(NOPRICE): os.remove(NOPRICE)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
    ctx = b.new_context(viewport={"width": 1440, "height": 950}, locale="en-US")
    ctx.add_init_script("localStorage.setItem('veyro.welcomed','1');")
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE); page.wait_for_timeout(1500)

    # 1. virtual portfolio: selling when there's no current price says so (it used to do nothing)
    js(page, "fetch('/api/paper', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ticker: 'FLKY', shares: 3})})")
    page.wait_for_timeout(500)
    open(NOPRICE, "w").close()
    page.locator("nav button", has_text="History").click(); page.wait_for_timeout(1500)
    row = visible(page).locator("tr", has_text="FLKY").first
    row.locator("button", has_text="Sell (paper)").click(); page.wait_for_timeout(800)
    note = visible(page).locator("[aria-labelledby=paper-h] [role=status]")
    check("paper sell with no price explains the position stays open", note.count() == 1 and "stays open" in note.inner_text(), note.inner_text() if note.count() else "")
    os.remove(NOPRICE)

    # 17. broker fees typed in Arabic digits are accepted
    page.locator("nav button", has_text="Settings").click(); page.wait_for_timeout(800)
    visible(page).locator("details.advanced > summary").click(); page.wait_for_timeout(300)
    fr = visible(page).locator("[aria-labelledby=fees-h] .row").nth(0)
    fr.locator("input").nth(0).fill("٠٫١٥٥"); fr.locator("input").nth(1).fill("١٥"); fr.locator("button").click(); page.wait_for_timeout(800)
    saved = js(page, "fetch('/api/settings').then(r => r.json()).then(j => j.broker_fees && j.broker_fees.sa)")
    check("broker fees in Arabic digits (٠٫١٥٥ %) are saved as 0.155 %", bool(saved) and abs(saved.get("rate", 0) - 0.00155) < 1e-9 and saved.get("min") == 15, str(saved))

    # 3. Report section jumps land below the sticky header and section menu (1100 px wide)
    page.set_viewport_size({"width": 1100, "height": 900})
    js(page, "fetch('/api/sessions', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ticker: 'AAPL', lang: 'en', demo: true})})")
    t0 = time.time()   # the demo takes about a minute to reach its verdict
    while time.time() - t0 < 150 and js(page, "fetch('/api/sessions?light=1').then(r => r.json()).then(j => j.sessions[0] && j.sessions[0].status)") != "done":
        time.sleep(1)
    page.reload(); page.wait_for_timeout(1500)
    page.locator("nav button", has_text="History").click(); page.wait_for_timeout(1500)
    visible(page).locator("button", has_text="View").first.click(); page.wait_for_timeout(2500)
    nav = visible(page).locator(".report-nav button")
    nav.nth(3).click(); page.wait_for_timeout(1500)
    covered = js(page, """(() => {
      const nav = document.querySelector('main > div:not([hidden]) .report-nav').getBoundingClientRect();
      const ph = [...document.querySelectorAll('main > div:not([hidden]) .phase')][2];
      return ph ? Math.round(ph.getBoundingClientRect().top - nav.bottom) : null; })()""")
    check("Report: a section jump isn't hidden under the sticky bars", covered is not None and covered >= 0, f"heading top − menu bottom = {covered}px")

    # 16. 'Analyse' from the Live board lands on the start bar, not the Office's old scroll spot
    page.set_viewport_size({"width": 1440, "height": 900})
    page.locator("nav button", has_text="Office").click(); page.wait_for_timeout(500)
    page.set_viewport_size({"width": 1440, "height": 600})
    js(page, "window.scrollTo(0, 500)"); page.wait_for_timeout(300)
    y0 = js(page, "window.scrollY")
    page.locator("nav button", has_text="Live").click(); page.wait_for_timeout(1500)
    visible(page).locator("button", has_text="Analyse").first.click(); page.wait_for_timeout(800)
    y = js(page, "window.scrollY")
    check("Live → Analyse opens the Office at the top", y0 > 100 and y < 5, f"left at {y0}, back at {y}")
    page.set_viewport_size({"width": 1440, "height": 900})

    # 15. index fund: an amount below one unit says so (not 'buys 0 units ($0)'), one unit is singular
    close = lambda: [page.locator(".modal-bg button.primary").last.click() for _ in range(page.locator(".modal-bg").count())]
    close()
    page.locator(".seg button").first.click()
    d = page.locator(".startbar label.check input[type=checkbox]").last
    if d.is_checked(): d.uncheck()
    page.locator(".startbar select").first.select_option("us")
    page.locator("label.budget input").fill("100"); page.locator("label.budget select").select_option("USD")
    page.locator(".startbar button", has_text="Suggest for me").first.click(); page.wait_for_timeout(1800)
    idx = page.locator(".index-funds")
    t = idx.inner_text() if idx.count() else ""
    check("index fund below one unit: 'isn't enough for one unit'", "isn't enough for one unit" in t and "buys 0 units" not in t, t.replace("\n", " | ")[:220])
    check("index fund with one unit: '1 unit' (singular)", "buys 1 unit (" in t, "")

    # 7. the estimate follows the economy switch (watchlist of 6, analyse the best 2)
    page.locator(".seg button").nth(2).click()
    if page.locator(".picklist button.linkish").count(): page.locator(".picklist button.linkish").click()
    add = page.locator(".tsearch input").first
    for tk in ("AAPL", "MSFT", "NVDA", "KO", "PG", "JPM"):
        add.fill(tk); add.press("Enter"); page.wait_for_timeout(120)
    page.locator("label.budget input").fill("")
    est = lambda: page.locator(".startbar .estimate b").inner_text() if page.locator(".startbar .estimate b").count() else ""
    eco = page.locator(".startbar label.check", has_text="Economy")
    if eco.locator("input[type=checkbox]").is_checked(): eco.locator("input[type=checkbox]").uncheck()
    page.wait_for_timeout(300); before = est()
    eco.locator("input[type=checkbox]").check(); eco.locator("select").first.select_option("2"); page.wait_for_timeout(300)
    after = est()
    check("estimate shrinks when economy analyses only the best 2", bool(before) and before != after, f"{before} → {after}")
    ctx.close()

    # 10. phone: the dialogue box is full width from the first letter (it used to grow sideways while typing)
    ctx = b.new_context(viewport={"width": 390, "height": 844}, locale="en-US")
    ctx.add_init_script("localStorage.setItem('veyro.welcomed','1');")
    page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE); page.wait_for_timeout(1200)
    page.locator(".seg button").nth(1).click()
    d = page.locator(".startbar label.check input[type=checkbox]").last
    if not d.is_checked(): d.check()
    page.locator(".tsearch input").first.fill("KO")
    page.locator(".startbar button.primary").click()
    t0 = time.time()
    while time.time() - t0 < 30 and not page.locator(".mobile-caption button.dlg").count():
        time.sleep(0.1)
    page.wait_for_timeout(300)
    w = js(page, "(() => { const d = document.querySelector('.mobile-caption button.dlg'), c = document.querySelector('.mobile-caption'); return d && c ? [Math.round(d.getBoundingClientRect().width), Math.round(c.clientWidth)] : null; })()")
    check("390 px: the dialogue box fills the width while typing", bool(w) and w[0] >= w[1] - 40, str(w))
    b.close()

check("no console errors", not errors, "; ".join(errors[:5]))
print("ALL OK" if all(ok for _, ok, _ in res) else "SOME FAILED")
