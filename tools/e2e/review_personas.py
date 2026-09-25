"""Persona walkthrough for docs/REVIEW.md: drives the real UI against the stubbed test server (ui_server.py)
in Arabic and English, desktop and 390 px, and saves screenshots to verification/review/.
Usage: start tools/e2e/ui_server.py (port 8766), then  .venv/bin/python tools/e2e/review_personas.py [part ...]"""
import json, os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8766"
OUT = Path(__file__).resolve().parents[2] / "verification" / "review"
OUT.mkdir(parents=True, exist_ok=True)
NOTES: list[str] = []
errors: list[str] = []
PARTS = set(sys.argv[1:]) or {"first", "beginner", "retail", "active", "settings"}


def note(s):
    NOTES.append(s); print(s, flush=True)


def shot(page, name, full=True):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)


def advance_until(page, cond, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        d = page.locator("button.dlg")
        if d.count():
            try: d.first.click(timeout=500)
            except Exception: pass
        time.sleep(0.3)
    return False


def open_app(b, lang, width, first_visit=False):
    ctx = b.new_context(viewport={"width": width, "height": 900 if width > 500 else 844}, locale="ar-SA" if lang == "ar" else "en-US")
    if not first_visit:
        ctx.add_init_script(f"localStorage.setItem('veyro.prefs.v1', JSON.stringify({{lang:'{lang}', sound:false}}));"
                            "localStorage.setItem('veyro.welcomed','1');")
    elif lang == "en":   # a new visitor whose browser is English: the app still opens in Arabic (default)
        ctx = b.new_context(viewport={"width": width, "height": 900 if width > 500 else 844}, locale="en-US")
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{lang}/{width}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"{lang}/{width}: {e}"))
    page.goto(BASE); page.wait_for_timeout(1200)
    if not first_visit and page.locator(".modal-bg button.primary").count():
        page.locator(".modal-bg button.primary").first.click()
    return ctx, page


def nav(page, ar, en):
    for _ in range(3):
        if not page.locator(".modal-bg").count():
            break
        close = page.locator(".modal-bg button", has_text="إغلاق").or_(page.locator(".modal-bg button", has_text="Close"))
        if close.count():
            close.first.click()
        else:
            page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    page.locator("nav button", has_text=ar).or_(page.locator("nav button", has_text=en)).first.click()
    page.wait_for_timeout(900)


def demo_off(page):
    d = page.locator(".startbar label.check input[type=checkbox]").last
    if d.is_checked():
        d.uncheck()


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
    combos = [(lg, w) for lg in ("ar", "en") for w in (1440, 390)]

    if "first" in PARTS:
        for lg, w in combos:
            ctx, page = open_app(b, lg, w, first_visit=True)
            note(f"first-run {lg}/{w}: html lang={page.evaluate('document.documentElement.lang')} (browser locale {'en-US' if lg=='en' else 'default'})")
            shot(page, f"p0_first_run_{lg}_{w}", full=False)
            sw = page.evaluate("document.documentElement.scrollWidth")
            note(f"first-run {lg}/{w}: scrollWidth={sw}")
            ctx.close()

    if "beginner" in PARTS:
        for lg, w in combos:
            for mkt, cur in (("sa", "SAR"), ("us", "USD"), ("both", "SAR")):
                ctx, page = open_app(b, lg, w)
                page.locator(".seg button").first.click()
                page.locator(".startbar select").first.select_option(mkt)
                page.locator("label.budget input").fill("1000")
                page.locator("label.budget select").select_option(cur)
                page.locator(".startbar button", has_text="اقترح لي").or_(page.locator(".startbar button", has_text="Suggest for me")).first.click()
                page.wait_for_timeout(1500)
                picks = page.locator(".chip.pick").all_inner_texts()
                note(f"beginner {lg}/{w}/{mkt}/1000 {cur}: picks={picks}")
                shot(page, f"p1_beginner_picks_{mkt}_{lg}_{w}")
                if mkt == "both" or (mkt == "sa" and w == 1440):
                    demo_off(page)
                    page.locator(".startbar button.primary").click()
                    ok = advance_until(page, lambda: page.locator(".beginner-guide, [aria-label='دليل المبتدئ'], [aria-label='Beginner guide']").count() > 0, 600)
                    page.wait_for_timeout(2500)
                    note(f"  guide shown={ok}")
                    shot(page, f"p1_beginner_guide_{mkt}_{lg}_{w}")
                    g = page.locator("[aria-label='دليل المبتدئ'], [aria-label='Beginner guide']")
                    if g.count():
                        note("  guide text: " + g.first.inner_text()[:1500].replace("\n", " | "))
                ctx.close()

    if "retail" in PARTS:
        for lg, w in combos:
            ctx, page = open_app(b, lg, w)
            page.locator(".seg button").nth(1).click()
            demo_off(page)
            inp = page.locator(".tsearch input").first
            inp.fill(""); inp.type("ارامكو" if lg == "ar" else "apple", delay=30); page.wait_for_timeout(900)
            note(f"retail {lg}/{w}: search hits={page.locator('.tsearch-list li').all_inner_texts()}")
            shot(page, f"p2_search_{lg}_{w}", full=False)
            inp.press("Enter"); page.wait_for_timeout(300)
            page.locator(".startbar button.primary").click(); page.wait_for_timeout(300)
            if page.locator("[role=alertdialog]").count():
                page.locator("[role=alertdialog] button.primary").first.click()
            page.wait_for_timeout(2500)
            shot(page, f"p2_running_{lg}_{w}", full=False)
            # debate arena
            advance_until(page, lambda: page.locator(".scene-debate, [data-scene=debate]").count() > 0, 120)
            shot(page, f"p2_debate_{lg}_{w}", full=False)
            # leave and come back
            nav(page, "الإعدادات", "Settings"); nav(page, "المكتب", "Office")
            shot(page, f"p2_back_to_office_{lg}_{w}", full=False)
            ok = advance_until(page, lambda: page.locator(".verdict-box").count() > 0, 300)
            note(f"  verdict reached={ok}")
            shot(page, f"p2_verdict_{lg}_{w}")
            vb = page.locator(".verdict-box")
            if vb.count():
                note("  verdict text: " + vb.first.inner_text()[:800].replace("\n", " | "))
            # Stop at the very end (after verdict): should be a no-op
            nav(page, "التقرير", "Report"); page.wait_for_timeout(1500)
            shot(page, f"p2_report_{lg}_{w}")
            ctx.close()

    if "active" in PARTS:
        lg, w = ("ar", 1440)
        for lg, w in (("ar", 1440), ("en", 390)):
            ctx, page = open_app(b, lg, w)
            page.locator(".seg button").nth(2).click()
            demo_off(page)
            add = page.locator(".tsearch input").first
            for tk in ("AAPL", "MSFT", "NVDA", "KO"):
                add.fill(tk); add.press("Enter"); page.wait_for_timeout(200)
            page.locator("label.budget input").fill("2000")
            page.locator("label.budget select").select_option("USD")
            eco = page.locator(".startbar label.check input[type=checkbox]").first
            eco.check()
            shot(page, f"p3_watchlist_setup_{lg}_{w}")
            page.locator(".startbar button.primary").click(); page.wait_for_timeout(500)
            if page.locator("[role=alertdialog]").count():
                shot(page, f"p3_confirm_{lg}_{w}", full=False)
                page.locator("[role=alertdialog] button.primary").first.click()
            ok = advance_until(page, lambda: page.locator(".ranking, .budget-plan, [aria-label*='خطة'], [aria-label*='plan']").count() > 0, 600)
            page.wait_for_timeout(2500)
            note(f"active {lg}/{w}: ranking/plan shown={ok}")
            shot(page, f"p3_ranking_plan_{lg}_{w}")
            plan = page.locator(".budget-plan, [aria-label*='خطة'], [aria-label*='plan']")
            if plan.count():
                note("  plan: " + plan.first.inner_text()[:1200].replace("\n", " | "))
            nav(page, "السجل", "History"); page.wait_for_timeout(1500)
            shot(page, f"p3_history_{lg}_{w}")
            nav(page, "مباشر", "Live"); page.wait_for_timeout(2500)
            shot(page, f"p3_live_{lg}_{w}")
            ctx.close()

    if "settings" in PARTS:
        for lg, w in (("ar", 1440), ("en", 1440), ("en", 390)):
            ctx, page = open_app(b, lg, w)
            nav(page, "الإعدادات", "Settings"); page.wait_for_timeout(800)
            shot(page, f"p4_settings_{lg}_{w}")
            note(f"settings {lg}/{w}: quick={page.locator('#quick option').all_inner_texts()[:12]}")
            # non-Claude provider: prices and the recommended pair
            prov = page.locator("section[aria-labelledby=s-model] .segbtns").first.locator("button")
            note(f"  providers shown: {prov.all_inner_texts()}")
            if prov.count() > 1:
                prov.nth(1).click(); page.wait_for_timeout(1200)
                note(f"  after switching to {prov.nth(1).inner_text()}: quick={page.locator('#quick option').all_inner_texts()[:6]}; estimate={page.locator('section[aria-labelledby=s-model] .toggle').last.inner_text()!r}")
                shot(page, f"p4_settings_other_provider_{lg}_{w}")
                prov.first.click(); page.wait_for_timeout(800)
            # accessibility: extra-large text + high contrast
            page.locator("button", has_text="كبير جداً").or_(page.locator("button", has_text="Extra large")).first.click()
            page.locator("label.toggle", has_text="تباين").or_(page.locator("label.toggle", has_text="High contrast")).locator("input").check()
            page.wait_for_timeout(500)
            nav(page, "المكتب", "Office")
            shot(page, f"p4_office_xl_contrast_{lg}_{w}", full=False)
            note(f"  xl+contrast scrollWidth={page.evaluate('document.documentElement.scrollWidth')}")
            nav(page, "الأوامر", "Orders"); page.wait_for_timeout(800)
            shot(page, f"p4_orders_{lg}_{w}")
            note(f"  orders text: {page.locator('main > div:not([hidden])').first.inner_text()[:300]!r}")
            ctx.close()
    b.close()

note("console errors: " + json.dumps(errors[:20], ensure_ascii=False))
(OUT / f"notes_{'_'.join(sorted(PARTS))}.txt").write_text("\n".join(NOTES), encoding="utf-8")
