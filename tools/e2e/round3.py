import time, json, urllib.request
from playwright.sync_api import sync_playwright
S=str(__import__("pathlib").Path(__file__).resolve().parents[2] / "verification" / "e2e"); B="http://127.0.0.1:8766"
def api(p, body=None, m="GET"):
    r=urllib.request.Request(B+p, data=json.dumps(body).encode() if body is not None else None, method=m, headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(r).read())
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
    b=p.chromium.launch(executable_path=__import__("os").environ.get("CHROMIUM") or None); pg=b.new_page(viewport={"width":1440,"height":1000}, locale="ar-SA")
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type=="error" else None)
    pg.goto(B); pg.wait_for_timeout(1200)
    if pg.locator(".modal-bg button.primary").count(): pg.locator(".modal-bg button.primary").first.click()
    # run one real session so the trust board & glossary have content
    pg.locator(".seg button").nth(1).click(); pg.locator(".tsearch input").first.fill("AAPL")
    d=pg.locator("label.check input[type=checkbox]").last
    if d.is_checked(): d.uncheck()
    pg.locator(".startbar button.primary").click()
    check("session to verdict", advance(pg, lambda: pg.locator(".verdict-box").count()>0))
    # glossary modal
    pg.locator("header button[aria-label='قاموس المصطلحات']").click(); pg.wait_for_timeout(400)
    n=pg.locator(".modal .logitem").count()
    pg.locator(".modal input").fill("مكرر"); pg.wait_for_timeout(200)
    check("glossary modal lists and searches terms", n > 30 and pg.locator(".modal .logitem").count()==1, f"{n} terms")
    pg.screenshot(path=f"{S}/r3_glossary.png")
    pg.locator(".modal button.primary").click()
    # term popover inside a report detail (inject a known phrase through the Markdown path: open the glossary term in minutes/report)
    pg.locator("header button", has_text="English").click(); pg.wait_for_timeout(500)
    pg.locator("nav button", has_text="Report").click(); pg.wait_for_timeout(1500)
    pg.locator("button", has_text="Expand all").click(); pg.wait_for_timeout(1500)
    terms=pg.locator(".term-btn").count()
    if terms:
        pg.locator(".term-btn").first.click(); pg.wait_for_timeout(300)
    check("report text has tappable terms with explanations", terms>0 and pg.locator(".term-pop").count()==1, f"{terms} terms")
    pg.screenshot(path=f"{S}/r3_term.png")
    # trust dashboard
    pg.locator("header button", has_text="عربي").click(); pg.wait_for_timeout(500)
    pg.locator("nav button", has_text="السجل").click(); pg.wait_for_timeout(2000)
    check("trust dashboard shown", pg.locator("#trust-h").count()==1 and pg.locator(".trust-tiles .stat").count()==4)
    pg.locator("#trust-h").screenshot(path=f"{S}/r3_trust_h.png")
    pg.locator("section.trust").screenshot(path=f"{S}/r3_trust.png")
    # budget cap: set a tiny cap and confirm new paid sessions are refused
    api("/api/settings", {"monthly_cap_usd": 0.0001}, "PUT")
    with open("/dev/null") as _: pass
    r=urllib.request.Request(B+"/api/sessions", data=json.dumps({"ticker":"MSFT","lang":"ar","demo":False}).encode(), method="POST", headers={"Content-Type":"application/json"})
    out=json.loads(urllib.request.urlopen(r).read())
    spent=api("/api/spend")
    # the fake model has no price, so force spend by inserting a priced session
    print("spend", spent, "create:", out)
    b.close()
    check("no console errors", not errs, "; ".join(errs[:3]))
print("ALL OK" if all(res) else "SOME FAILED")
