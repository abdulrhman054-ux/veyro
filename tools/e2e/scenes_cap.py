import time, sys, re
from playwright.sync_api import sync_playwright
S = str(__import__("pathlib").Path(__file__).resolve().parents[2] / "verification" / "e2e"); LANG = sys.argv[2] if len(sys.argv) > 2 else "ar"
seen = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=__import__("os").environ.get("CHROMIUM") or None)
    page = b.new_page(viewport={"width": 1440, "height": 1000}, locale="ar-SA")
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto("http://127.0.0.1:8766"); page.wait_for_timeout(1200)
    if page.locator(".modal-bg button.primary").count(): page.locator(".modal-bg button.primary").first.click()
    if LANG == "en": page.locator("header button", has_text="English").click(); page.wait_for_timeout(400)
    page.locator(".seg button").nth(1).click()
    d = page.locator("label.check input[type=checkbox]")
    if d.is_checked(): d.uncheck()
    page.locator(".tsearch input").first.fill("NVDA")
    page.locator(".startbar button.primary").click()
    t0 = time.time(); last_click = 0
    while time.time() - t0 < 400:
        cls = page.locator(".room").get_attribute("class") or ""
        m = re.search(r"scene-(\w+)", cls); sc = m.group(1) if m else "?"
        key = sc + ("-heat" if "heat-2" in cls or "heat-3" in cls else "") + ("-verdict" if "verdict-" in cls else "") + ("-speak" if "has-speaker" in cls else "")
        if key not in seen and ("has-speaker" in cls or "verdict-" in cls or sc == "office"):
            page.wait_for_timeout(1700)   # let the camera push in and the line type a bit
            page.locator(".stage").screenshot(path=f"{S}/scene_{LANG}_{len(seen):02d}_{key}.png")
            seen[key] = 1
        if "verdict-" in cls: break
        if time.time() - last_click > 3.5 and page.locator("button.dlg").count():
            try: page.locator("button.dlg").first.click(timeout=300); page.locator("button.dlg").first.click(timeout=300)
            except Exception: pass
            last_click = time.time()
        time.sleep(0.25)
    print("scenes:", list(seen)); print("errors:", errs)
    b.close()
