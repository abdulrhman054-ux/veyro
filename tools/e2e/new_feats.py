import time, json, urllib.request
from playwright.sync_api import sync_playwright
S=str(__import__("pathlib").Path(__file__).resolve().parents[2] / "verification" / "e2e")
B="http://127.0.0.1:8766"
def api(p): return json.loads(urllib.request.urlopen(B+p).read())
res=[]
def check(n,ok,d=""): res.append(ok); print(("PASS " if ok else "FAIL ")+n+(f" :: {d}" if d else ""), flush=True)
def advance(pg, cond, t=300):
    t0=time.time()
    while time.time()-t0<t:
        if cond(): return True
        if pg.locator("button.dlg").count():
            try: pg.locator("button.dlg").first.click(timeout=300)
            except Exception: pass
        time.sleep(0.3)
    return False
with sync_playwright() as p:
    b=p.chromium.launch(executable_path=__import__("os").environ.get("CHROMIUM") or None); pg=b.new_page(viewport={"width":1440,"height":1000})
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type=="error" else None)
    pg.goto(B); pg.wait_for_timeout(1200)
    if pg.locator(".modal-bg button.primary").count(): pg.locator(".modal-bg button.primary").first.click()
    pg.locator(".seg button").nth(1).click()
    d=pg.locator("label.check input[type=checkbox]").last
    if d.is_checked(): d.uncheck()
    pg.locator(".tsearch input").first.fill("NVDA"); pg.locator(".startbar button.primary").click()
    check("session reaches verdict", advance(pg, lambda: pg.locator(".verdict-box").count()>0))
    print("VERDICT:", pg.locator(".verdict-box").inner_text().replace("\n"," / ")[:300])
    pg.wait_for_timeout(500); btn=pg.locator(".verdict-box button").nth(1)
    check("verdict offers add-to-paper", btn.count()>0)
    if btn.count(): btn.click(); pg.wait_for_timeout(1200); print("BTN:", btn.inner_text())
    check("paper position stored", any(x["ticker"]=="NVDA" for x in api("/api/paper")["positions"]))
    n_before=len(api("/api/sessions?light=1")["sessions"])
    pg.locator(".startbar button.primary").click(); pg.wait_for_timeout(1000)
    check("reuse offer shown", pg.locator("[role=alertdialog]").count()>0)
    pg.locator("[role=alertdialog] button.primary").click()
    check("reused result replays to verdict", advance(pg, lambda: pg.locator(".verdict-box").count()>0, 120))
    check("no new paid session created", len(api("/api/sessions?light=1")["sessions"])==n_before)
    pg.screenshot(path=f"{S}/nf_reuse.png")
    # economy watchlist
    pg.locator(".seg button").nth(2).click()
    for _ in range(pg.locator(".chip.pick .x").count()): pg.locator(".chip.pick .x").first.click()
    for tk in ["AAPL","MSFT","KO","NVDA"]:
        i=pg.locator(".startbar .tsearch input").first; i.fill(tk); i.press("Enter")
    pg.locator(".startbar label.check", has_text="اقتصادي").locator("input").check()
    pg.locator(".startbar label.check", has_text="اقتصادي").locator("select").select_option("2")
    pg.locator(".startbar button.primary").click(); pg.wait_for_timeout(1500)
    check("economy prescreen shown", pg.locator("text=الفحص المجاني").count()>0)
    check("only 2 go to full analysis", pg.locator(".side .board-rank").first.locator("li").count()==2, str(pg.locator(".side .board-rank").first.locator("li").count()))
    pg.screenshot(path=f"{S}/nf_economy.png")
    check("economy scan finishes", advance(pg, lambda: pg.locator("[aria-label='لوحة الترتيب'], .modal-bg").count()>0, 400))
    pg.screenshot(path=f"{S}/nf_ranking.png")
    if pg.locator(".modal-bg button.primary").count(): pg.locator(".modal-bg button.primary").last.click()
    # live price alert
    pg.locator("nav button", has_text="مباشر").click(); pg.wait_for_timeout(2500)
    tile=pg.locator(".live-grid").nth(1).locator(".live-tile").first
    tile.locator("button[aria-label='تنبيه سعر']").click()
    tile.locator(".alertform select").select_option("above")
    tile.locator(".alertform input").fill("1")
    tile.locator(".alertform button.primary").click(); pg.wait_for_timeout(4000)
    fired=[a for a in api("/api/alerts")["alerts"] if a["kind"]=="price"]
    check("price alert fires on a live tick", len(fired)>=1, fired[0]["text_ar"] if fired else "")
    pg.screenshot(path=f"{S}/nf_live_alert.png")
    # history paper
    pg.locator("nav button", has_text="السجل").click(); pg.wait_for_timeout(1500)
    check("virtual portfolio on History", pg.locator("#paper-h").count()>0 and pg.locator("text=NVDA").count()>0)
    pg.screenshot(path=f"{S}/nf_paper.png")
    # settings data source
    pg.locator("nav button", has_text="الإعدادات").click(); pg.wait_for_timeout(800)
    pg.locator("details.advanced summary").click(); pg.locator("button", has_text="Stooq").click(); pg.wait_for_timeout(800)
    check("data source switch saved", api("/api/settings")["data_source"]=="stooq")
    pg.locator("button", has_text="Yahoo Finance").first.click(); pg.wait_for_timeout(500)
    # report print button
    pg.locator("nav button", has_text="التقرير").click(); pg.wait_for_timeout(1500)
    check("report has PDF button", pg.locator("button", has_text="PDF").count()>0)
    check("no console errors", not errs, "; ".join(errs[:3]))
    b.close()
print("ALL OK" if all(res) else "SOME FAILED")
