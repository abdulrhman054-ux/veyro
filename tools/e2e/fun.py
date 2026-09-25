"""Easter eggs: tap jokes, five-tap pokes, party mode (Konami code or five taps on the clock), and Bruno's
"Kid, don't buy this!" when the risk team clearly warns or the call is to sell - and never otherwise.
Run with the test server started as FAKE_RATING=Sell (run_all.sh does this for this suite)."""
import os, time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8766"
OUT = str(__import__("pathlib").Path(__file__).resolve().parents[2] / "verification" / "e2e") + "/"
res, errors = [], []
KONAMI = ["ArrowUp", "ArrowUp", "ArrowDown", "ArrowDown", "ArrowLeft", "ArrowRight", "ArrowLeft", "ArrowRight", "b", "a"]


def check(n, ok, d=""):
    res.append((n, ok, d)); print(("PASS " if ok else "FAIL ") + n + (f" :: {d}" if d else ""), flush=True)


def wait_for(page, cond, timeout=300, advance=True):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond(): return True
        if advance and page.locator("button.dlg").count():
            try: page.locator("button.dlg").first.click(timeout=500)
            except Exception: pass
        time.sleep(0.25)
    return False


def warn_quip(page):
    return page.locator(".agent.c-Bruno [data-quip=warn]")


def start(page, ticker, demo):
    page.locator(".seg button").nth(1).click()
    d = page.locator(".startbar label.check input[type=checkbox]").last
    if d.is_checked() != demo: d.click()
    page.locator(".tsearch input").first.fill(ticker)
    page.locator(".startbar button.primary").click(); page.wait_for_timeout(500)
    if page.locator("[role=alertdialog] button.ghost").count(): page.locator("[role=alertdialog] button.ghost").first.click()


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
    for lang, loc in (("ar", "ar-SA"), ("en", "en-US")):
        ctx = b.new_context(viewport={"width": 1440, "height": 950}, locale=loc)
        ctx.add_init_script(f"localStorage.setItem('veyro.welcomed','1'); localStorage.setItem('veyro.prefs.v1', JSON.stringify({{lang: '{lang}'}}));")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(BASE); page.wait_for_timeout(1500)
        L = lang.upper()

        # --- the office layout: no character stands over another's name or role
        hidden = page.evaluate("""(() => {
          const hit = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
          const ags = [...document.querySelectorAll('.room .agent:not(.offstage)')], out = [];
          for (const a of ags) for (const lab of a.querySelectorAll('.plate, .rl')) {
            const r = lab.getBoundingClientRect();
            for (const b of ags) if (b !== a && hit(r, b.querySelector('.sprite').getBoundingClientRect()))
              out.push(a.className.match(/c-(\\w+)/)[1] + ' under ' + b.className.match(/c-(\\w+)/)[1]);
          }
          return out; })()""")
        check(f"{L}: no character covers another's name or role", not hidden, "; ".join(hidden))
        page.screenshot(path=OUT + f"fun_office_{lang}.png", clip={"x": 0, "y": 0, "width": 1440, "height": 950})

        # --- tap a character once: a joke; five times quickly: they've had enough
        bolt = page.locator(".agent.c-Bolt button.hit")
        bolt.click(); page.wait_for_timeout(200)
        check(f"{L}: one tap, a joke in the character's voice", page.locator(".agent.c-Bolt [data-react=tap]").count() == 1,
              page.locator(".agent.c-Bolt [data-react=tap]").inner_text() if page.locator(".agent.c-Bolt [data-react=tap]").count() else "")
        page.wait_for_timeout(2500)
        leo = page.locator(".agent.c-Leo button.hit")
        for _ in range(5):
            leo.click(); page.wait_for_timeout(150)
        poked = page.locator(".agent.c-Leo [data-react=poked]")
        check(f"{L}: five taps, the character reacts differently (and spins)", poked.count() == 1 and page.locator(".agent.c-Leo.poked").count() == 1,
              poked.inner_text() if poked.count() else "")
        page.screenshot(path=OUT + f"fun_poke_{lang}.png", clip={"x": 0, "y": 0, "width": 1440, "height": 950})
        page.wait_for_timeout(3500)

        # --- the Konami code does nothing while typing, and starts the party otherwise
        page.locator(".tsearch input").first.click()
        for k in KONAMI: page.keyboard.press(k)
        check(f"{L}: Konami code typed in a text box does nothing", page.locator(".room.party").count() == 0)
        page.locator(".tsearch input").first.fill("")
        page.locator("body").click(position={"x": 5, "y": 5})
        for k in KONAMI: page.keyboard.press(k)
        page.wait_for_timeout(1200)
        check(f"{L}: Konami code starts party mode", page.locator(".room.party .disco").count() == 1 and page.locator(".party-banner").count() == 1
              and page.locator(".agent.c-Leo [data-quip=party]").count() == 1)
        page.screenshot(path=OUT + f"fun_party_{lang}.png", clip={"x": 0, "y": 0, "width": 1440, "height": 950})
        page.wait_for_timeout(9000)
        check(f"{L}: the party ends by itself", page.locator(".room.party").count() == 0)
        clock = page.locator(".clock")
        for _ in range(5):
            clock.click(force=True); page.wait_for_timeout(120)
        check(f"{L}: five taps on the wall clock also start it (phones have no arrow keys)", page.locator(".room.party").count() == 1)
        page.wait_for_timeout(9500)

        # --- demo: the risk team's line is a clear warning, so Bruno walks in
        start(page, "2222.SR" if lang == "ar" else "AAPL", demo=True)
        seen = wait_for(page, lambda: warn_quip(page).count() > 0, 240, advance=False)
        txt = warn_quip(page).inner_text() if warn_quip(page).count() else ""
        want = "ورع، لا تشتري هذا!" if lang == "ar" else "Kid, don't buy this!"
        check(f"{L}: risk warning -> Bruno says '{want}'", seen and want in txt and page.locator(".room.scene-risk").count() == 1, txt)
        page.wait_for_timeout(900)
        page.screenshot(path=OUT + f"fun_dont_buy_risk_{lang}.png", clip={"x": 0, "y": 0, "width": 1440, "height": 950})
        check(f"{L}: ...next to the risk team's own line, not instead of it", page.locator(".dlg .tag").first.inner_text().strip() in ("تانك", "Tank"),
              page.locator(".dlg .tag").first.inner_text() if page.locator(".dlg .tag").count() else "")
        wait_for(page, lambda: page.locator("main > div:not([hidden]) .verdict-box").count() > 0, 240)
        check(f"{L}: no 'don't buy' at a verdict that isn't a sell", warn_quip(page).count() == 0)

        if lang == "en":
            # --- real (fake-model) run: the risk line is neutral -> no cameo; the call is Sell -> Bruno says it
            start(page, "MSFT", demo=False)
            cameo = [False]
            def at_verdict():
                if page.locator(".room.scene-risk").count() and warn_quip(page).count(): cameo[0] = True
                return page.locator("main > div:not([hidden]) .verdict-box").count() > 0
            wait_for(page, at_verdict, 300)
            check("EN: a risk line that isn't a clear warning gets no cameo", not cameo[0])
            page.wait_for_timeout(1200)
            check("EN: a SELL verdict -> Bruno says 'Kid, don't buy this!'", warn_quip(page).count() == 1 and "SELL" in page.locator(".verdict-box").inner_text().upper())
            over = page.evaluate("""(() => {
              const q = document.querySelector('.agent.c-Bruno [data-quip=warn]').getBoundingClientRect(), st = document.querySelector('.stage').getBoundingClientRect();
              const hit = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
              const out = [...document.querySelectorAll('.room .agent:not(.offstage):not(.c-Bruno)')].filter(a => [...a.querySelectorAll('.plate, .sprite')].some(e => hit(q, e.getBoundingClientRect())))
                .map(a => a.className.match(/c-(\\w+)/)[1]);
              if (q.right > st.right + 1 || q.left < st.left - 1) out.push('off the stage');
              return out; })()""")
            check("EN: Bruno's line covers nobody's name or face and stays on the stage", not over, "; ".join(over))
            page.screenshot(path=OUT + "fun_dont_buy_sell_en.png", clip={"x": 0, "y": 0, "width": 1440, "height": 950})
        ctx.close()

    # --- phone width: the joke bubble still fits on the scaled stage, no horizontal scroll
    ctx = b.new_context(viewport={"width": 390, "height": 844}, locale="ar-SA")
    ctx.add_init_script("localStorage.setItem('veyro.welcomed','1');")
    page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE); page.wait_for_timeout(1200)
    clock = page.locator(".clock")
    for _ in range(5):
        clock.click(force=True); page.wait_for_timeout(120)
    page.wait_for_timeout(1000)
    check("390 px: party mode works by tapping the clock", page.locator(".room.party").count() == 1)
    check("390 px: no horizontal scroll", page.evaluate("document.documentElement.scrollWidth") <= 392)
    page.screenshot(path=OUT + "fun_party_390.png")
    b.close()

check("no console errors", not errors, "; ".join(errors[:5]))
print("ALL OK" if all(ok for _, ok, _ in res) else "SOME FAILED")
