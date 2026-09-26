from playwright.sync_api import sync_playwright
S=str(__import__("pathlib").Path(__file__).resolve().parents[2] / "verification" / "e2e")
import sys
L = sys.argv[1]
with sync_playwright() as p:
    b=p.chromium.launch(executable_path=__import__("os").environ.get("CHROMIUM") or None); pg=b.new_page(viewport={"width":1440,"height":1300}, locale="ar-SA")
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type=="error" else None)
    pg.goto("http://127.0.0.1:8766"); pg.wait_for_timeout(1200)
    if pg.locator(".modal-bg button.primary").count(): pg.locator(".modal-bg button.primary").first.click()
    if L=="en": pg.locator("header button", has_text="English").click()
    pg.locator("nav button").nth(1).click(); pg.wait_for_timeout(3000)
    a = pg.locator(".live-tile .px").first.inner_text(); pg.wait_for_timeout(2500); b2 = pg.locator(".live-tile .px").all_inner_texts()
    print("tiles:", pg.locator(".live-tile").count(), "badge:", pg.locator(".livebadge").inner_text())
    pg.screenshot(path=f"{S}/live_{L}_sa.png", full_page=True)
    pg.locator(".live-bar .segbtns button").nth(1).click(); pg.wait_for_timeout(3000)
    pg.screenshot(path=f"{S}/live_{L}_us.png", full_page=True)
    print("us first tile:", pg.locator(".live-tile .nm").nth(3).inner_text())
    pg.locator(".live-tile .btn.mini").first.click(); pg.wait_for_timeout(800)
    print("office ticker:", pg.locator(".startbar .tsearch input").input_value())
    print("errors:", errs)
    b.close()
