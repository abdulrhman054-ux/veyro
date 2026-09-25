"""Generate the Veyro design-canvas artboards (.dc.html) from the shared sprite data.

Output: <scratch>/canvas/project/*.dc.html  (published to the Design artifact)
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import sprites as S  # noqa: E402

OUT = pathlib.Path(sys.argv[1]) / "project"
OUT.mkdir(parents=True, exist_ok=True)

FONTS = {
    "baloo_ar": "/_blob/64bb138faec8799aab8b51cc9b09444e",
    "baloo_lat": "/_blob/90d688119bb6fc1362f9befd88a7db18",
    "pix_lat": "/_blob/f36ce7e3432dcabff78319ef70dc2a20",
    "pix_ext": "/_blob/bcd32f7881a12d8d1feca9f87e0efece",
}

AR_RANGE = "U+0600-06FF, U+0750-077F, U+0870-088E, U+0890-0891, U+0897-08E1, U+08E3-08FF, U+200C-200E, U+2010-2011, U+204F, U+2E41, U+FB50-FDFF, U+FE70-FE74, U+FE76-FEFC"
LAT_RANGE = "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD"
EXT_RANGE = "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+1E00-1E9F, U+20A0-20C0, U+2C60-2C7F, U+A720-A7FF"

FONT_CSS = f"""
@font-face{{font-family:'Baloo Bhaijaan 2';font-weight:400 800;font-display:swap;src:url("{FONTS['baloo_ar']}") format('woff2');unicode-range:{AR_RANGE}}}
@font-face{{font-family:'Baloo Bhaijaan 2';font-weight:400 800;font-display:swap;src:url("{FONTS['baloo_lat']}") format('woff2');unicode-range:{LAT_RANGE}}}
@font-face{{font-family:'Pixelify Sans';font-weight:400 700;font-display:swap;src:url("{FONTS['pix_lat']}") format('woff2');unicode-range:{LAT_RANGE}}}
@font-face{{font-family:'Pixelify Sans';font-weight:400 700;font-display:swap;src:url("{FONTS['pix_ext']}") format('woff2');unicode-range:{EXT_RANGE}}}
"""

THEME_CSS = """
.vy{--page:#FBF6E9;--ink:#5C4331;--muted:#7D6449;--card:#FFFFFF;--cream:#FFF8E4;--line:#E3D5B8;--shade:#E6D3AA;
--floor:#F2E2C0;--floor2:#EAD6AE;--wall:#CDEBD9;--wall2:#C2E4D0;--trim:#B99463;--sky:#A9DDF5;--cloud:#FFFFFF;
--desk:#C98B55;--desktop:#E0A56C;--deskedge:#9A6436;--leaf:#3E9A68;--leafl:#6CC38E;--orange:#F2A43A;--orangedk:#C97F1F;
--board:#FFFFFF;--boardrim:#9AA7B8;--glow:transparent;--dlg:#FFF8E4;--dlgink:#5C4331;--star:transparent;--moon:transparent;--sun:#FFE07A}
.vy.night{--page:#1E1A2C;--ink:#F3E9D2;--muted:#C9B998;--card:#2A2440;--cream:#342D4E;--line:#4B4268;--shade:#15121F;
--floor:#3A3152;--floor2:#342B4A;--wall:#2F4760;--wall2:#2A4057;--trim:#6B5236;--sky:#1B2447;--cloud:#3A4470;
--desk:#8A5A36;--desktop:#A36E44;--deskedge:#5B3A20;--leaf:#6CC38E;--leafl:#8FD9A8;--orange:#F2A43A;--orangedk:#B8741A;
--board:#F5F1E6;--boardrim:#6E7A8C;--glow:rgba(255,214,120,.45);--dlg:#FFF3D6;--dlgink:#5C4331;--star:#FFF6C8;--moon:#FFF1B8;--sun:transparent}
"""

ANIM_CSS = """
.pixel{font-family:'Pixelify Sans','Baloo Bhaijaan 2',monospace}
@keyframes showA{0%{opacity:1}50%{opacity:0}}
@keyframes showB{0%{opacity:0}50%{opacity:1}}
@keyframes blink{0%,92%{opacity:0}93%,97%{opacity:1}98%,100%{opacity:0}}
@keyframes talk{0%{opacity:1}50%{opacity:0}}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-2px)}}
@keyframes hop{0%,100%{transform:translateY(-22px)}30%{transform:translateY(-36px)}55%{transform:translateY(-22px)}70%{transform:translateY(-27px)}}
@keyframes emote{0%{transform:translateY(8px) scale(.4);opacity:0}30%{transform:translateY(-4px) scale(1.15);opacity:1}45%,100%{transform:none;opacity:1}}
@keyframes emoteBob{0%,100%{margin-top:0}50%{margin-top:-5px}}
@keyframes cloud{from{transform:translateX(-80px)}to{transform:translateX(260px)}}
@keyframes steam{0%{transform:translateY(0);opacity:.9}100%{transform:translateY(-18px);opacity:0}}
@keyframes plane{0%{transform:translate(1060px,20px) rotate(-8deg);opacity:0}5%{opacity:1}45%{transform:translate(420px,-16px) rotate(4deg)}90%{transform:translate(-120px,40px) rotate(-6deg);opacity:1}100%{transform:translate(-160px,40px);opacity:0}}
@keyframes draw{from{stroke-dashoffset:320}to{stroke-dashoffset:0}}
@keyframes arrow{0%,100%{transform:translateY(0)}50%{transform:translateY(5px)}}
@keyframes caret{50%{opacity:0}}
@keyframes pop{0%{transform:scale(.3) rotate(-6deg)}60%{transform:scale(1.12) rotate(2deg)}100%{transform:none}}
@keyframes boxin{0%{transform:translateY(30px) scale(.9);opacity:0}100%{transform:none;opacity:1}}
@keyframes leaf{0%,100%{transform:rotate(-5deg)}50%{transform:rotate(5deg)}}
@keyframes tagwiggle{0%,100%{transform:rotate(-4deg)}50%{transform:rotate(-1deg)}}
@keyframes slidein{from{transform:translateY(-10px);opacity:0}to{transform:none;opacity:1}}
@keyframes notein{0%{transform:scale(0) rotate(-30deg)}70%{transform:scale(1.2) rotate(6deg)}100%{transform:scale(1) rotate(-4deg)}}
@keyframes confetti{0%{transform:translateY(-20px) rotate(0);opacity:1}100%{transform:translateY(240px) rotate(540deg);opacity:0}}
@keyframes twinkle{0%,100%{opacity:1}50%{opacity:.25}}
@keyframes glow{0%,100%{box-shadow:0 0 14px 4px var(--glow)}50%{box-shadow:0 0 22px 8px var(--glow)}}
.btn{transition:transform .12s steps(2)}.btn:hover{transform:translateY(-3px)}.btn:active{transform:translateY(2px)}
@media (prefers-reduced-motion: reduce){.vy *{animation:none!important;transition:none!important}}
"""

OFFICE_CSS = """
.room{position:relative;width:1000px;height:740px;border-radius:28px;overflow:hidden;background-color:var(--floor);background-image:linear-gradient(45deg,var(--floor2) 25%,transparent 25%,transparent 75%,var(--floor2) 75%),linear-gradient(45deg,var(--floor2) 25%,transparent 25%,transparent 75%,var(--floor2) 75%);background-size:48px 48px;background-position:0 0,24px 24px;box-shadow:0 6px 0 var(--shade),0 14px 30px rgba(40,28,20,.18)}
.wall{position:absolute;left:0;top:0;width:1000px;height:150px;background:var(--wall);background-image:repeating-linear-gradient(90deg,var(--wall2) 0 12px,var(--wall) 12px 36px);border-bottom:10px solid var(--trim)}
.window{position:absolute;top:22px;width:170px;height:96px;background:var(--sky);border:8px solid #FFFFFF;box-shadow:0 0 0 4px var(--trim);overflow:hidden}
.window .c{position:absolute;height:14px;background:var(--cloud);box-shadow:12px -8px 0 2px var(--cloud),24px 0 0 var(--cloud);animation:cloud 14s linear infinite}
.window .st{position:absolute;width:4px;height:4px;background:var(--star);animation:twinkle 2.4s steps(2) infinite}
.window .moon{position:absolute;right:18px;top:12px;width:22px;height:22px;border-radius:50%;background:var(--moon);box-shadow:-6px 0 0 0 var(--sky) inset}
.window .sun{position:absolute;right:16px;top:10px;width:20px;height:20px;background:var(--sun)}
.wb{position:absolute;left:330px;top:14px;width:340px;height:118px;box-sizing:border-box;background:var(--board);border:8px solid var(--boardrim);border-radius:6px;box-shadow:0 6px 0 #6E7A8C}
.wb path.ln{stroke-dasharray:320;animation:draw 3s steps(20) infinite alternate}
.clock{position:absolute;left:250px;top:36px;width:44px;height:44px;border-radius:50%;background:#FFFFFF;border:5px solid var(--trim)}
.clock i{position:absolute;left:19px;top:8px;width:4px;height:14px;background:#5C4331}.clock b{position:absolute;left:19px;top:18px;width:12px;height:4px;background:#5C4331}
.agent{position:absolute;width:150px;height:200px}
.sprite{position:absolute;left:15px;top:0;width:120px;height:130px;animation:bob 1.4s steps(2) infinite}
.fr{position:absolute;left:0;top:0;opacity:0}
.fr.ta{animation:showA .6s steps(1) infinite}.fr.tb{animation:showB .6s steps(1) infinite}
.fr.bl{animation:blink 4.6s steps(1) infinite}
.agent.is-active .sprite{animation:hop .9s steps(6) infinite}
.agent.is-active .fr.ta,.agent.is-active .fr.tb{animation:none;opacity:0}
.agent.is-active .fr.dn{animation:showA .5s steps(1) infinite}
.agent.is-active .fr.wv{animation:showB .5s steps(1) infinite}
.agent.is-active .fr.mo{animation:talk .24s steps(1) infinite}
.agent.is-done .fr.ta,.agent.is-done .fr.tb{animation:none;opacity:0}
.agent.is-done .fr.dn{opacity:1}
.agent.is-done .sprite{animation:bob 2.4s steps(2) infinite}
.emote{position:absolute;top:-8px;left:112px;min-width:40px;height:40px;padding:0 8px;box-sizing:border-box;background:#FFFFFF;border-radius:20px;display:none;align-items:center;justify-content:center;font-size:24px;font-weight:700;box-shadow:0 4px 0 #E3D5B8;z-index:6}
.agent.is-active .emote{display:flex;animation:emote .5s steps(5) both,emoteBob 1s steps(2) .5s infinite}
.desk{position:absolute;left:5px;top:96px;width:140px;height:50px;background:var(--desk);border-radius:6px 6px 2px 2px;box-shadow:inset 0 10px 0 var(--desktop),0 5px 0 var(--deskedge);z-index:2}
.desk.gold{box-shadow:inset 0 10px 0 var(--desktop),0 5px 0 var(--deskedge),0 0 0 4px #F7CE4F}
.lap{position:absolute;left:84px;top:-26px;width:46px;height:30px;background:#DDE3EA;border:3px solid #9AA7B8;border-radius:4px;animation:glow 3s steps(3) infinite}
.lap b{position:absolute;left:16px;top:8px;width:12px;height:12px;border-radius:50%;background:#F07F5A}
.mug{position:absolute;left:14px;top:-16px;width:18px;height:18px;background:#FFFFFF;border:3px solid #9AA7B8;border-radius:2px 2px 6px 6px}
.mug i{position:absolute;top:-10px;width:4px;height:8px;background:#FFFFFF;border-radius:2px;animation:steam 1.6s steps(4) infinite}
.mug i:nth-child(1){left:3px}.mug i:nth-child(2){left:10px;animation-delay:.8s}
.note{position:absolute;left:56px;top:14px;width:30px;height:30px;background:#FFE680;box-shadow:0 3px 0 #E0C458;display:none;align-items:center;justify-content:center}
.agent.is-done .note{display:flex;animation:notein .5s steps(5) both}
.plate{position:absolute;top:152px;left:50%;transform:translateX(-50%);padding:2px 14px;border-radius:12px;color:#FFFFFF;font-weight:700;font-size:17px;white-space:nowrap;box-shadow:0 3px 0 rgba(0,0,0,.18)}
.rl{position:absolute;top:180px;width:150px;text-align:center;font-size:13px;font-weight:700;color:var(--muted)}
.dlg{position:absolute;left:110px;top:566px;width:780px;min-height:150px;box-sizing:border-box;padding:36px 44px 26px;background:var(--dlg);color:var(--dlgink);border-radius:60px 56px 64px 52px;box-shadow:0 6px 0 #E6D3AA,0 16px 34px rgba(40,28,20,.22);z-index:10;animation:boxin .35s steps(4) both}
.tag{position:absolute;top:-22px;inset-inline-start:60px;padding:5px 22px;border-radius:22px;color:#FFFFFF;font-size:21px;font-weight:700;animation:tagwiggle 1.4s steps(2) infinite}
.dtext{font-size:22px;line-height:1.75;font-weight:500}
.next{position:absolute;bottom:14px;inset-inline-end:48px;width:0;height:0;border-left:11px solid transparent;border-right:11px solid transparent;border-top:14px solid #F2A43A;animation:arrow .6s steps(2) infinite}
.caret{display:inline-block;width:3px;height:22px;background:#F2A43A;vertical-align:middle;margin-inline-start:3px;animation:caret .6s steps(1) infinite}
.verdict{animation:pop .6s steps(6) both}
.conf{position:absolute;top:0;width:10px;height:10px;animation:confetti 2.2s steps(12) infinite}
.plane{position:absolute;left:0;top:150px;z-index:8;animation:plane 13s linear infinite}
.leaf{animation:leaf 2.4s steps(2) infinite;transform-origin:bottom center}
.logitem{animation:slidein .4s steps(4) both}
.tab{height:42px;padding:0 18px;border-radius:21px;display:flex;align-items:center;font-weight:800;font-size:16px;text-decoration:none;color:var(--ink)}
.tab:hover{color:var(--ink);background:var(--cream)}
.tab.on{background:var(--leafl);color:#FFFFFF;box-shadow:0 4px 0 var(--leaf)}
.pill{height:44px;padding:0 16px;border-radius:22px;border:3px solid var(--line);background:var(--card);color:var(--ink);font-family:inherit;font-size:15px;font-weight:700;cursor:pointer;display:flex;align-items:center;gap:8px}
"""

# ---------------------------------------------------------------- characters
ORDER = ["Ollie", "Pip", "Buzz", "Benny", "Bolt", "Bruno", "Tank", "Leo"]
META = {
    "Ollie": dict(ar="أولي", role_ar="المحلل الفني", role_en="Technical Analyst", animal_ar="بومة", animal_en="Owl",
                  cp_en="hoot!", cp_ar="هوو هوو!", pitch=420, emote="!", pitch_word="mid"),
    "Pip": dict(ar="بيب", role_ar="محلل الأخبار", role_en="News Analyst", animal_ar="ببغاء مكاو", animal_en="Scarlet macaw",
                cp_en="squawk!", cp_ar="سكوااك!", pitch=760, emote="!!", pitch_word="high"),
    "Buzz": dict(ar="بَز", role_ar="محلل المزاج العام", role_en="Sentiment Analyst", animal_ar="نحلة", animal_en="Bee",
                 cp_en="bzzz!", cp_ar="بززز!", pitch=900, emote="♪", pitch_word="very high"),
    "Benny": dict(ar="بيني", role_ar="محلل الأساسيات", role_en="Fundamentals Analyst", animal_ar="قندس", animal_en="Beaver",
                  cp_en="chomp!", cp_ar="قرمش!", pitch=520, emote="…", pitch_word="mid"),
    "Bolt": dict(ar="بولت", role_ar="باحث الصعود", role_en="Bull Researcher", animal_ar="ثور", animal_en="Bull",
                 cp_en="moo-ve!", cp_ar="مووو!", pitch=230, emote="!", pitch_word="low"),
    "Bruno": dict(ar="برونو", role_ar="باحث الهبوط", role_en="Bear Researcher", animal_ar="دب بني", animal_en="Brown bear",
                  cp_en="grr…", cp_ar="غرر…", pitch=180, emote="?", pitch_word="very low"),
    "Tank": dict(ar="تانك", role_ar="فريق المخاطر", role_en="Risk Team", animal_ar="سلحفاة", animal_en="Turtle",
                 cp_en="slow and steady.", cp_ar="على مهلك… بثبات.", pitch=300, emote="…", pitch_word="low-mid"),
    "Leo": dict(ar="ليو", role_ar="صاحب القرار", role_en="Decision Maker", animal_ar="أسد", animal_en="Lion",
                cp_en="roar!", cp_ar="زئير!", pitch=260, emote="!", pitch_word="low"),
}
LINES = {
    "Ollie": ("راقبت الشارت طول الصباح… الاتجاه صاعد، بس قدامه مقاومة واضحة. خلونا نصبر شوي، هوو هوو!",
              "I watched the chart all morning… the trend is up, but there's clear resistance ahead. Let's be patient, hoot!"),
    "Pip": ("قريت كل الأخبار! النبرة العامة إيجابية، وما لقيت شي يخوّف للحين، سكوااك!",
            "I read every headline! The overall tone is positive, and nothing scary so far, squawk!"),
    "Buzz": ("الكل يتكلم عن السهم! الحماس عالي مرة… ولما الكل يتحمس كذا لازم ننتبه، بززز!",
             "Everyone's buzzing about this stock! Hype is sky-high… and when it's this loud, we should be careful, bzzz!"),
    "Benny": ("حسبت الأرقام: الإيرادات تكبر والهوامش حلوة، بس السعر غالي شوي مقارنة بالقطاع، قرمش!",
              "I crunched the numbers: revenue is growing and margins look healthy, but the price is rich for its sector, chomp!"),
    "Bolt": ("يا جماعة الأساسيات قوية والزخم معنا! أي نزول أشوفه فرصة دخول، مووو!",
             "Folks, the fundamentals are strong and momentum is with us! Any dip looks like an entry to me, moo-ve!"),
    "Bruno": ("هدّوا اللعب شوي… التقييم منفوخ، ولو جات النتائج مخيبة بيطيح بقوة، غرر…",
              "Hold your horses… the valuation is stretched, and a weak earnings report could hit it hard, grr…"),
    "Tank": ("شويّة شويّة… لو دخلنا، ندخل بحجم صغير ووقف خسارة واضح. على مهلك… بثبات.",
             "Easy now… if we go in, we go in small with a clear stop-loss. slow and steady."),
    "Leo": ("سمعتكم كلكم! القرار: نحتفظ، ونراقب كسر المقاومة كإشارة شراء. زئير!",
            "I've heard you all! The call: Hold, and watch for a breakout above resistance as a buy signal. roar!"),
}
META["Albie"] = dict(ar="ألبي", role_ar="ناقل الأخبار العالمية", role_en="World News Courier", animal_ar="طائر القطرس",
                    animal_en="Albatross", cp_en="feathers full of news!", cp_ar="ريشتي تطير بالأخبار!", pitch=640, emote="✈",
                    pitch_word="chatty glide")
CAST = ORDER + ["Albie"]
COLOR = {n: S.DATA["characters"][n]["color"] for n in CAST}
# Office seats, right-to-left speaking flow in the Arabic layout.
SEATS = {"Ollie": (825, 160), "Pip": (635, 160), "Leo": (425, 160), "Buzz": (215, 160), "Benny": (25, 160),
         "Bolt": (720, 355), "Bruno": (425, 355), "Tank": (130, 355)}


def overlay(name, **kw):
    """SVG with only the pixels that differ from the plain frame (blink lids / open mouth)."""
    base = S.grid(name, frame="down")
    alt = S.grid(name, frame="down", **kw)
    runs = {}
    for y in range(S.H):
        for x in range(S.W):
            if alt[y][x] != base[y][x]:
                runs.setdefault(S.color(name, alt[y][x]), []).append(f"M{x} {y}h1v1h-1z")
    body = "".join(f'<path fill="{c}" d="{"".join(d)}"></path>' for c, d in runs.items())
    return body


def sprite_svg(name, cls, px=5, frame="down", body=None):
    b = body if body is not None else S.paths(name, frame=frame)
    return (f'<svg class="fr {cls}" width="{24 * px}" height="{26 * px}" viewBox="0 0 24 26" '
            f'shape-rendering="crispEdges" aria-hidden="true">{b}</svg>')


def still(name, px=4, frame="down", talk=False, blink=False):
    return (f'<svg width="{24 * px}" height="{26 * px}" viewBox="0 0 24 26" shape-rendering="crispEdges" '
            f'aria-hidden="true" style="display: block">{S.paths(name, frame=frame, talk=talk, blink=blink)}</svg>')


def agent_block(name, idx, cls_hole):
    x, y = SEATS[name]
    m = META[name]
    delay = f"-{idx * 0.37:.2f}s"
    frames = (sprite_svg(name, "ta", frame="typeA") + sprite_svg(name, "tb", frame="typeB")
              + sprite_svg(name, "dn", frame="down") + sprite_svg(name, "wv", frame="wave")
              + sprite_svg(name, "bl", body=overlay(name, blink=True))
              + sprite_svg(name, "mo", body=overlay(name, talk=True)))
    gold = " gold" if name == "Leo" else ""
    check = ('<svg width="18" height="18" viewBox="0 0 9 9" shape-rendering="crispEdges" aria-hidden="true">'
             '<path fill="#27A05E" d="M7 1h2v2H8v1H7v1H6v1H5v1H4v1H3V7H2V6H1V5H0V4h2v1h1v1h1V5h1V4h1V3h1z"></path></svg>')
    return f"""<div class="agent {cls_hole}" style="left: {x}px; top: {y}px">
<div class="sprite" style="animation-delay: {delay}">{frames}</div>
<div class="emote pixel" style="color: {COLOR[name]}">{m['emote']}</div>
<div class="desk{gold}"><div class="mug"><i></i><i></i></div><div class="lap"><b></b></div><div class="note">{check}</div></div>
<div class="plate" style="background: {COLOR[name]}">{{{{ nm.{name} }}}}</div><div class="rl">{{{{ rl.{name} }}}}</div>
</div>"""


LEAF_LOGO = ('<svg class="leaf" width="44" height="44" viewBox="0 0 12 12" shape-rendering="crispEdges" aria-hidden="true">'
             '<path d="M5 0h3v1h2v2h1v4h-1v2H8v1H6v2H5v-2H3V9H2V7H1V3h1V1h3z" fill="#4A3426"></path>'
             '<path d="M5 1h3v1h2v1h0v4H9v2H6v1H5V9H3V7H2V3h1V2h2z" fill="#6CC38E"></path>'
             '<path d="M5 3h1v6H5z" fill="#3E9A68"></path></svg>')
PLANT = ('<svg width="60" height="90" viewBox="0 0 12 18" shape-rendering="crispEdges" aria-hidden="true">'
         '<path d="M5 0h2v2h2v2h2v4H9v2H7v1H5v-1H3V8H1V4h2V2h2z" fill="{leaf}"></path>'
         '<path d="M3 11h6v2H8v5H4v-5H3z" fill="{pot}"></path></svg>')
PLANE = ('<svg width="46" height="26" viewBox="0 0 23 13" shape-rendering="crispEdges" aria-hidden="true">'
         '<path d="M0 6h1V5h4V4h4V3h4V2h4V1h4V0h2v1h-1v2h-1v2h-1v2h-1v2h-1v2h-1v2h-1v-1h-1v-1h-1v-1h-1V9h-1v1h-1v1H9V9H8V8H1V7H0z" '
         'fill="#FFFFFF" stroke="#9AA7B8" stroke-width=".3"></path></svg>')
SUN_ICON = ('<svg width="20" height="20" viewBox="0 0 10 10" shape-rendering="crispEdges" aria-hidden="true"><path fill="currentColor" '
            'd="M4 0h2v2H4zM4 8h2v2H4zM0 4h2v2H0zM8 4h2v2H8zM3 3h4v4H3zM1 1h1v1H1zM8 1h1v1H8zM1 8h1v1H1zM8 8h1v1H8z"></path></svg>')
MOON_ICON = ('<svg width="20" height="20" viewBox="0 0 10 10" shape-rendering="crispEdges" aria-hidden="true"><path fill="currentColor" '
             'd="M3 0h4v1H5v1H4v2H3v2h1v2h1v1h2v1H3V9H2V8H1V6H0V4h1V2h1V1h1z"></path></svg>')
SPEAKER_ICON = ('<svg width="20" height="20" viewBox="0 0 10 10" shape-rendering="crispEdges" aria-hidden="true"><path fill="currentColor" '
                'd="M0 3h2V2h1V1h1V0h1v10H4V9H3V8H2V7H0zM7 2h1v1h1v4H8v1H7V7h1V3H7z"></path></svg>')
GEAR_ICON = ('<svg width="20" height="20" viewBox="0 0 11 11" shape-rendering="crispEdges" aria-hidden="true"><path fill="currentColor" '
             'd="M4 0h3v2h1V1h1v1h1v1H9v1h2v3H9v1h1v1H9v1H8V9H7v2H4V9H3v1H2V9H1V8h1V7H0V4h2V3H1V2h1V1h1v1h1zM4 4v3h3V4z"></path></svg>')


def helmet(extra=""):
    return f"<helmet>\n<style>{FONT_CSS}\nbody{{margin:0}}\n{THEME_CSS}{ANIM_CSS}{extra}</style>\n</helmet>"


def doc(title, lang, body, script):
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<title>{title}</title>
<script src="./support.js"></script>
</head>
<body>
<x-dc>
{helmet(OFFICE_CSS)}
{body}
</x-dc>
{script}
</body>
</html>
"""


# ---------------------------------------------------------------- Office (interactive)
def office(default_lang, default_theme):
    agents = "\n".join(agent_block(n, i, f"{{{{ cls.{n} }}}}") for i, n in enumerate(ORDER))
    lines_js = json.dumps([
        {"key": n, "color": COLOR[n], "pitch": META[n]["pitch"], "ar": LINES[n][0], "en": LINES[n][1]} for n in ORDER
    ], ensure_ascii=False)
    names_js = json.dumps({n: {"ar": META[n]["ar"], "en": n} for n in ORDER}, ensure_ascii=False)
    roles_js = json.dumps({n: {"ar": META[n]["role_ar"], "en": META[n]["role_en"]} for n in ORDER}, ensure_ascii=False)
    stars = "".join(f'<div class="st" style="left: {x}px; top: {y}px; animation-delay: -{d}s"></div>'
                    for x, y, d in [(14, 12, 0.3), (48, 40, 1.1), (92, 20, 0.7), (120, 58, 1.9), (30, 66, 1.4)])
    body = f"""<div dir="{{{{ t.dir }}}}" lang="{{{{ t.lang }}}}" class="vy {{{{ themeCls }}}}" style="width: 1440px; height: 900px; box-sizing: border-box; padding: 22px 36px; display: flex; flex-direction: column; gap: 18px; background: var(--page); color: var(--ink); font-family: 'Baloo Bhaijaan 2', Tahoma, sans-serif; overflow: hidden">

<header style="display: flex; align-items: center; justify-content: space-between; gap: 20px; height: 70px">
<div style="display: flex; align-items: center; gap: 12px">
{LEAF_LOGO}
<div style="display: flex; flex-direction: column">
<div style="font-size: 30px; font-weight: 800; line-height: 1.1; color: var(--leaf)">{{{{ t.brand }}}}</div>
<div style="font-size: 13px; font-weight: 700; color: var(--muted)">{{{{ t.tagline }}}}</div>
</div>
</div>

<nav aria-label="{{{{ t.navLabel }}}}" style="display: flex; gap: 6px; padding: 5px; border-radius: 26px; background: var(--card); border: 3px solid var(--line)">
<a class="tab on" href="Main.dc.html">{{{{ t.office }}}}</a>
<a class="tab" href="Report.dc.html">{{{{ t.report }}}}</a>
<a class="tab" href="History.dc.html">{{{{ t.history }}}}</a>
<a class="tab" href="Settings.dc.html">{{{{ t.settings }}}}</a>
</nav>

<div style="display: flex; align-items: center; gap: 10px">
<label for="sym" style="font-size: 15px; font-weight: 800">{{{{ t.ticker }}}}</label>
<input id="sym" class="pixel" value="NVDA" dir="ltr" style="width: 130px; height: 48px; box-sizing: border-box; border: 3px solid var(--line); border-radius: 24px; background: var(--card); color: var(--ink); font-size: 21px; text-align: center">
<button class="btn" onClick="{{{{ start }}}}" style="height: 50px; padding: 0 26px; border: none; border-radius: 25px; background: #F2A43A; color: #3B2410; font-family: inherit; font-size: 18px; font-weight: 800; cursor: pointer; box-shadow: 0 5px 0 #C97F1F">{{{{ startLabel }}}}</button>
</div>

<div style="display: flex; align-items: center; gap: 8px">
<span class="pixel" style="height: 30px; padding: 0 12px; border-radius: 15px; background: #FFE680; color: #6B4E00; font-size: 14px; font-weight: 700; display: flex; align-items: center">{{{{ t.demo }}}}</span>
<button class="btn pill" onClick="{{{{ toggleLang }}}}" aria-label="{{{{ t.langAria }}}}">{{{{ t.langBtn }}}}</button>
<button class="btn pill" onClick="{{{{ toggleTheme }}}}" aria-label="{{{{ t.themeAria }}}}" style="width: 44px; padding: 0; justify-content: center"><sc-if value="{{{{ isNight }}}}" hint-placeholder-val="{{{{ false }}}}">{SUN_ICON}</sc-if><sc-if value="{{{{ isDay }}}}" hint-placeholder-val="{{{{ true }}}}">{MOON_ICON}</sc-if></button>
<button class="btn pill" onClick="{{{{ toggleSound }}}}" aria-label="{{{{ t.soundAria }}}}" style="opacity: {{{{ soundOpacity }}}}">{SPEAKER_ICON}<span>{{{{ soundLabel }}}}</span></button>
<a class="btn pill" href="Settings.dc.html" aria-label="{{{{ t.settings }}}}" style="width: 44px; padding: 0; justify-content: center; box-sizing: border-box">{GEAR_ICON}</a>
</div>
</header>

<div style="display: flex; gap: 26px; flex-grow: 1; min-height: 0">

<div class="room" dir="ltr">
<div class="wall"></div>
<div class="window" style="left: 50px"><div class="sun"></div><div class="moon"></div>{stars}<div class="c" style="top: 26px; width: 30px"></div><div class="c" style="top: 62px; width: 24px; animation-delay: -7s"></div></div>
<div class="window" style="left: 780px">{stars}<div class="c" style="top: 40px; width: 28px; animation-delay: -3s"></div><div class="c" style="top: 70px; width: 22px; animation-delay: -10s"></div></div>
<div class="clock"><i></i><b></b></div>
<div class="wb">
<div class="pixel" style="position: absolute; top: 4px; left: 10px; font-size: 15px; font-weight: 700; color: #5C4331">NVDA</div>
<div class="pixel" style="position: absolute; top: 4px; right: 10px; font-size: 12px; font-weight: 700; color: #B86E00">DEMO</div>
<svg width="324" height="102" viewBox="0 0 324 102" aria-hidden="true"><path d="M14 84 L60 66 L96 74 L140 46 L180 54 L220 28 L262 36 L306 16" fill="none" stroke="#9AA7B8" stroke-width="2" stroke-dasharray="4 6"></path><path class="ln" d="M14 84 L60 66 L96 74 L140 46 L180 54 L220 28 L262 36 L306 16" fill="none" stroke="#3E9A68" stroke-width="6" stroke-linejoin="round"></path></svg>
</div>
<div class="leaf" style="position: absolute; left: 12px; top: 470px">{PLANT.format(leaf="#4E9E62", pot="#D9774E")}</div>
<div class="leaf" style="position: absolute; left: 928px; top: 470px; animation-delay: -1.2s">{PLANT.format(leaf="#6CC38E", pot="#E8A04A")}</div>
<div class="plane">{PLANE}</div>
{agents}

<sc-if value="{{{{ idle }}}}" hint-placeholder-val="{{{{ true }}}}">
<div class="dlg" dir="{{{{ t.dir }}}}">
<div class="tag" style="background: #3E9A68">{{{{ t.brand }}}}</div>
<div class="dtext">{{{{ t.welcome }}}}</div>
<div class="next"></div>
</div>
</sc-if>
<sc-if value="{{{{ speaking }}}}" hint-placeholder-val="{{{{ false }}}}">
<div class="dlg" dir="{{{{ t.dir }}}}">
<div class="tag" style="background: {{{{ cur.color }}}}">{{{{ cur.name }}}}</div>
<div class="dtext">{{{{ cur.typed }}}}<span class="caret"></span></div>
<div class="next"></div>
</div>
</sc-if>
<sc-if value="{{{{ finished }}}}" hint-placeholder-val="{{{{ false }}}}">
<div class="dlg" dir="{{{{ t.dir }}}}" style="text-align: center; overflow: hidden; padding-top: 30px">
<div class="conf" style="left: 80px; background: #F2A43A"></div><div class="conf" style="left: 220px; background: #6CC38E; animation-delay: -.6s"></div><div class="conf" style="left: 380px; background: #E0453A; animation-delay: -1.2s"></div><div class="conf" style="left: 530px; background: #3F7FE0; animation-delay: -.3s"></div><div class="conf" style="left: 660px; background: #F7CE4F; animation-delay: -1.7s"></div>
<div class="tag" style="background: #E08A1E">{{{{ t.verdictTag }}}}</div>
<div class="verdict" style="display: flex; flex-direction: column; align-items: center; gap: 2px">
<div style="font-size: 44px; font-weight: 800; color: #C46F0A; line-height: 1.2">{{{{ t.hold }}}}</div>
<div style="font-size: 18px; font-weight: 600">{{{{ t.reason }}}}</div>
<div style="display: flex; gap: 14px; align-items: center; margin-top: 8px">
<a class="btn" href="Report.dc.html" style="height: 42px; padding: 0 22px; border-radius: 21px; background: #6CC38E; color: #16402A; font-weight: 800; font-size: 16px; display: flex; align-items: center; text-decoration: none; box-shadow: 0 4px 0 #3E9A68">{{{{ t.openReport }}}}</a>
<span style="font-size: 13px; color: #7D6449">{{{{ t.disclaimer }}}}</span>
</div>
</div>
</div>
</sc-if>
</div>

<aside style="flex-grow: 1; min-width: 0; height: 740px; box-sizing: border-box; padding: 20px; border-radius: 28px; background: var(--card); background-image: repeating-linear-gradient(180deg,transparent 0 35px,var(--line) 35px 36px); box-shadow: 0 6px 0 var(--shade); display: flex; flex-direction: column; gap: 12px; overflow: hidden">
<div style="display: flex; align-items: center; justify-content: space-between">
<div style="font-size: 21px; font-weight: 800">{{{{ t.minutes }}}}</div>
<div class="pixel" style="font-size: 15px; color: var(--muted)" dir="ltr">{{{{ progress }}}}</div>
</div>
<div style="display: flex; gap: 6px">
<sc-for list="{{{{ dots }}}}" as="d" hint-placeholder-count="8">
<div title="{{{{ d.name }}}}" style="width: 22px; height: 22px; border-radius: 6px; background: {{{{ d.bg }}}}"></div>
</sc-for>
</div>
<div style="display: flex; justify-content: space-between; padding: 8px 12px; border-radius: 14px; background: var(--cream); font-size: 14px; font-weight: 700">
<span>{{{{ t.costLabel }}}}</span><span class="pixel" dir="ltr">{{{{ t.costValue }}}}</span>
</div>
<sc-if value="{{{{ logEmpty }}}}" hint-placeholder-val="{{{{ true }}}}">
<div style="font-size: 16px; color: var(--muted); line-height: 1.8; padding-top: 6px">{{{{ t.logEmpty }}}}</div>
</sc-if>
<div style="display: flex; flex-direction: column; gap: 10px; overflow: hidden">
<sc-for list="{{{{ log }}}}" as="item" hint-placeholder-count="3">
<div class="logitem" style="padding: 10px 14px; border-radius: 18px; background: var(--cream)">
<div style="font-size: 15px; font-weight: 800; color: {{{{ item.color }}}}">{{{{ item.name }}}}</div>
<div style="font-size: 14px; line-height: 1.6">{{{{ item.text }}}}</div>
</div>
</sc-for>
</div>
</aside>
</div>
</div>"""

    T = {
        "ar": dict(dir="rtl", lang="ar", brand="فيرو", tagline="مكتب المجلس الذكي", navLabel="التنقل", office="المكتب",
                   report="التقرير", history="السجل", settings="الإعدادات", ticker="رمز السهم", demo="تجريبي",
                   langBtn="English", langAria="Switch to English", themeAria="تبديل الوضع الليلي والنهاري",
                   soundAria="تشغيل أو كتم أصوات الشخصيات", welcome="أهلاً! الفريق كله في المكتب ويشتغل. اكتب رمز السهم فوق واضغط «ابدأ الجلسة»، وبيتناقشون قدامك قبل ما يطلع القرار.",
                   verdictTag="ليو · القرار", hold="احتفاظ", reason="نراقب كسر المقاومة كإشارة شراء · الثقة: متوسطة",
                   openReport="افتح التقرير", disclaimer="تحليل للمساعدة، وليس نصيحة مالية.", minutes="محضر الجلسة",
                   costLabel="التكلفة التقديرية", costValue="[يظهر قبل البدء]", logEmpty="هنا بنكتب خلاصة كلام كل واحد بعد ما يخلص.",
                   start="ابدأ الجلسة", running="الجلسة جارية…", again="أعد الجلسة", soundOn="الصوت", soundOff="مكتوم"),
        "en": dict(dir="ltr", lang="en", brand="Veyro", tagline="The AI Council Office", navLabel="Navigation", office="Office",
                   report="Report", history="History", settings="Settings", ticker="Ticker", demo="Demo",
                   langBtn="عربي", langAria="التبديل إلى العربية", themeAria="Toggle day and night",
                   soundAria="Mute or unmute character voices", welcome="Hi there! The whole team is in the office. Type a ticker up top and press Start, and they'll debate it right in front of you before the verdict.",
                   verdictTag="Leo · Verdict", hold="HOLD", reason="Watch for a breakout above resistance as a buy signal · Confidence: medium",
                   openReport="Open report", disclaimer="Analysis to help you think, not financial advice.", minutes="Session minutes",
                   costLabel="Estimated cost", costValue="[shown before start]", logEmpty="Each character's takeaway lands here when they finish.",
                   start="Start session", running="In session…", again="Run again", soundOn="Sound", soundOff="Muted"),
    }
    t_js = json.dumps(T, ensure_ascii=False)
    props = json.dumps({
        "lang": {"editor": "enum", "options": ["ar", "en"], "default": default_lang},
        "theme": {"editor": "enum", "options": ["day", "night"], "default": default_theme},
        "speed": {"editor": "range", "default": 1, "min": 0.5, "max": 3, "step": 0.5, "unit": "x"},
        "$preview": {"width": 1440, "height": 900},
    }, ensure_ascii=False).replace("'", "&#39;").replace("&", "&amp;") if False else json.dumps({
        "lang": {"editor": "enum", "options": ["ar", "en"], "default": default_lang},
        "theme": {"editor": "enum", "options": ["day", "night"], "default": default_theme},
        "speed": {"editor": "range", "default": 1, "min": 0.5, "max": 3, "step": 0.5, "unit": "x"},
        "$preview": {"width": 1440, "height": 900},
    })
    script = f"""<script type="text/x-dc" data-dc-script data-props='{props}'>
class Component extends DCLogic {{
  constructor(props) {{
    super(props);
    this.state = {{ step: -1, chars: 0, hold: 0, log: [], running: false, sound: true, lang: null, theme: null }};
    this.lines = {lines_js};
    this.names = {names_js};
    this.roles = {roles_js};
    this.T = {t_js};
    this.tick = this.tick.bind(this);
  }}
  componentWillUnmount() {{ if (this.timer) clearInterval(this.timer); }}
  lang() {{ return this.state.lang || this.props.lang || '{default_lang}'; }}
  theme() {{ return this.state.theme || this.props.theme || '{default_theme}'; }}
  blip(pitch, ch) {{
    if (!this.state.sound || !this.ac || ch === ' ' || ch === '،' || ch === '.' || ch === ',') return;
    try {{
      const t = this.ac.currentTime;
      const o = this.ac.createOscillator();
      const g = this.ac.createGain();
      o.type = 'square';
      o.frequency.setValueAtTime(pitch * (0.85 + Math.random() * 0.4), t);
      o.frequency.exponentialRampToValueAtTime(pitch * 0.7, t + 0.06);
      g.gain.setValueAtTime(0.04, t);
      g.gain.exponentialRampToValueAtTime(0.001, t + 0.07);
      o.connect(g); g.connect(this.ac.destination);
      o.start(t); o.stop(t + 0.08);
    }} catch (e) {{}}
  }}
  tick() {{
    const s = this.state;
    if (s.step < 0 || s.step > 7) return;
    const line = this.lines[s.step];
    const text = line[this.lang()];
    const sp = this.props.speed ?? 1;
    if (s.chars < text.length) {{
      const n = Math.min(text.length, s.chars + Math.ceil(sp));
      if (n % 2 === 0) this.blip(line.pitch, text[n - 1]);
      this.setState({{ chars: n }});
      return;
    }}
    if (s.hold < Math.round(40 / sp)) {{ this.setState({{ hold: s.hold + 1 }}); return; }}
    const log = [{{ key: line.key }}].concat(s.log);
    if (s.step === 7) {{ clearInterval(this.timer); this.timer = null; this.setState({{ step: 8, log: log, running: false, hold: 0 }}); }}
    else {{ this.setState({{ step: s.step + 1, chars: 0, hold: 0, log: log }}); }}
  }}
  renderVals() {{
    const s = this.state;
    const L = this.lang();
    const t = this.T[L];
    const idxOf = (k) => this.lines.findIndex((l) => l.key === k);
    const cls = {{}}; const nm = {{}}; const rl = {{}};
    Object.keys(this.names).forEach((k) => {{
      const i = idxOf(k);
      cls[k] = s.step === i ? 'is-active' : (s.step > i ? 'is-done' : '');
      nm[k] = this.names[k][L];
      rl[k] = this.roles[k][L];
    }});
    const speaking = s.step >= 0 && s.step <= 7;
    const cl = speaking ? this.lines[s.step] : null;
    const cur = cl ? {{ name: this.names[cl.key][L], color: cl.color, typed: cl[L].slice(0, s.chars) }} : {{ name: '', color: '#3E9A68', typed: '' }};
    const doneCount = Math.max(0, Math.min(8, s.step));
    const night = this.theme() === 'night';
    return {{
      t: t, cls: cls, nm: nm, rl: rl,
      themeCls: night ? 'night' : 'day', isNight: night, isDay: !night,
      idle: s.step === -1, speaking: speaking, finished: s.step === 8, cur: cur,
      log: s.log.map((e) => {{ const l = this.lines[idxOf(e.key)]; return {{ name: this.names[e.key][L], color: l.color, text: l[L] }}; }}),
      logEmpty: s.log.length === 0,
      progress: doneCount + ' / 8',
      dots: this.lines.map((l, i) => ({{ name: this.names[l.key][L], bg: i < doneCount ? l.color : (i === s.step ? '#F2A43A' : 'var(--line)') }})),
      startLabel: s.running ? t.running : (s.step === 8 ? t.again : t.start),
      soundLabel: s.sound ? t.soundOn : t.soundOff,
      soundOpacity: s.sound ? 1 : 0.6,
      toggleSound: () => this.setState({{ sound: !s.sound }}),
      toggleLang: () => this.setState({{ lang: L === 'ar' ? 'en' : 'ar' }}),
      toggleTheme: () => this.setState({{ theme: night ? 'day' : 'night' }}),
      start: () => {{
        if (s.running) return;
        try {{ if (!this.ac) {{ const AC = window.AudioContext || window.webkitAudioContext; if (AC) this.ac = new AC(); }} if (this.ac && this.ac.state === 'suspended') this.ac.resume(); }} catch (e) {{}}
        if (this.timer) clearInterval(this.timer);
        this.setState({{ step: 0, chars: 0, hold: 0, log: [], running: true }});
        this.timer = setInterval(this.tick, 38);
      }}
    }};
  }}
}}
</script>"""
    return doc("Veyro Office", default_lang, body, script)


# ---------------------------------------------------------------- shared static header
def static_header(active, lang="ar"):
    tabs = [("Main.dc.html", "المكتب", "Office"), ("Report.dc.html", "التقرير", "Report"),
            ("History.dc.html", "السجل", "History"), ("Settings.dc.html", "الإعدادات", "Settings")]
    li = 1 if lang == "ar" else 2
    nav = "".join(f'<a class="tab{" on" if t[0] == active else ""}" href="{t[0]}">{t[li]}</a>' for t in tabs)
    brand = "فيرو" if lang == "ar" else "Veyro"
    tag = "مكتب المجلس الذكي" if lang == "ar" else "The AI Council Office"
    return f"""<header style="display: flex; align-items: center; justify-content: space-between; gap: 20px; height: 70px">
<div style="display: flex; align-items: center; gap: 12px">{LEAF_LOGO}
<div style="display: flex; flex-direction: column"><div style="font-size: 30px; font-weight: 800; line-height: 1.1; color: var(--leaf)">{brand}</div><div style="font-size: 13px; font-weight: 700; color: var(--muted)">{tag}</div></div></div>
<nav aria-label="{'التنقل' if lang == 'ar' else 'Navigation'}" style="display: flex; gap: 6px; padding: 5px; border-radius: 26px; background: var(--card); border: 3px solid var(--line)">{nav}</nav>
<div style="display: flex; gap: 8px; align-items: center"><span class="pixel" style="height: 30px; padding: 0 12px; border-radius: 15px; background: #FFE680; color: #6B4E00; font-size: 14px; font-weight: 700; display: flex; align-items: center">{'تجريبي' if lang == 'ar' else 'Demo'}</span></div>
</header>"""


def page(title, active, inner, w, h, script_body="", props_extra=None, lang="ar", theme="day"):
    props = {"$preview": {"width": w, "height": h}}
    if props_extra:
        props.update(props_extra)
    body = f"""<div dir="{'rtl' if lang == 'ar' else 'ltr'}" class="vy {theme}" style="width: {w}px; height: {h}px; box-sizing: border-box; padding: 22px 36px; display: flex; flex-direction: column; gap: 22px; background: var(--page); color: var(--ink); font-family: 'Baloo Bhaijaan 2', Tahoma, sans-serif; overflow: hidden">
{static_header(active, lang)}
{inner}
</div>"""
    script = f"""<script type="text/x-dc" data-dc-script data-props='{json.dumps(props)}'>
class Component extends DCLogic {{
{script_body or "  renderVals() { return {}; }"}
}}
</script>"""
    return doc(title, lang, body, script)


CARD = "border-radius: 28px; background: var(--card); box-shadow: 0 6px 0 var(--shade)"


# ---------------------------------------------------------------- Report
def report():
    cards = []
    for i, n in enumerate(ORDER):
        m = META[n]
        cards.append(f"""<div style="{CARD}; padding: 18px 20px; display: flex; flex-direction: column; gap: 10px">
<div style="display: flex; align-items: center; gap: 14px">
<div style="width: 72px; height: 78px; border-radius: 18px; background: var(--cream); display: flex; align-items: center; justify-content: center; flex-shrink: 0">{still(n, 3)}</div>
<div style="display: flex; flex-direction: column; gap: 2px; flex-grow: 1">
<div style="display: flex; align-items: center; gap: 8px"><span style="padding: 1px 12px; border-radius: 10px; background: {COLOR[n]}; color: #FFFFFF; font-weight: 800; font-size: 16px">{m['ar']}</span><span style="font-size: 14px; font-weight: 700; color: var(--muted)">{m['role_ar']}</span></div>
<div style="font-size: 16px; line-height: 1.6">{LINES[n][0]}</div>
</div>
</div>
<button class="btn" onClick="{{{{ toggle{i} }}}}" aria-expanded="{{{{ open{i} }}}}" style="align-self: flex-start; height: 36px; padding: 0 16px; border-radius: 18px; border: 3px solid var(--line); background: var(--card); color: var(--ink); font-family: inherit; font-size: 14px; font-weight: 800; cursor: pointer">{{{{ label{i} }}}}</button>
<sc-if value="{{{{ open{i} }}}}" hint-placeholder-val="{{{{ {'true' if i == 0 else 'false'} }}}}">
<div style="border-radius: 18px; background: var(--cream); padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; font-size: 14px; line-height: 1.7">
<div style="font-weight: 800">التحليل الكامل</div>
<div style="color: var(--muted)">[هنا يظهر التقرير الكامل لـ{m['ar']} كما كتبه الإطار، مع ترجمته العربية المفصّلة، بدون اختصار.]</div>
<div style="font-weight: 800">البيانات المستخدمة</div>
<div style="color: var(--muted)">[المؤشرات والأرقام التي جلبها الإطار فعلياً، مع مصدر كل رقم.]</div>
</div>
</sc-if>
</div>""")
    inner = f"""<div style="display: flex; gap: 26px; flex-grow: 1; min-height: 0">
<div style="width: 440px; flex-shrink: 0; display: flex; flex-direction: column; gap: 18px">
<div style="{CARD}; padding: 26px; display: flex; flex-direction: column; align-items: center; gap: 8px; position: relative; overflow: hidden; background: var(--cream)">
<div class="leaf" style="animation-duration: 1.6s">{still('Leo', 6, frame='wave', talk=True)}</div>
<div class="tag" style="position: static; background: #E08A1E">ليو · القرار</div>
<div class="verdict" style="font-size: 64px; font-weight: 800; color: #C46F0A; line-height: 1.1">احتفاظ</div>
<div style="font-size: 18px; font-weight: 600; text-align: center">نراقب كسر المقاومة كإشارة شراء</div>
<div style="display: flex; align-items: center; gap: 10px; margin-top: 6px"><span style="font-weight: 800">الثقة</span>
<div style="display: flex; gap: 4px" dir="ltr"><span style="width: 26px; height: 14px; background: #F2A43A"></span><span style="width: 26px; height: 14px; background: #F2A43A"></span><span style="width: 26px; height: 14px; background: #F2A43A"></span><span style="width: 26px; height: 14px; background: var(--line)"></span><span style="width: 26px; height: 14px; background: var(--line)"></span></div><span style="font-weight: 700">متوسطة</span></div>
</div>
<div style="{CARD}; padding: 20px 22px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; font-size: 15px">
<div><div style="color: var(--muted); font-weight: 700">السهم</div><div class="pixel" style="font-size: 22px; font-weight: 700">NVDA</div></div>
<div><div style="color: var(--muted); font-weight: 700">السعر وقت القرار</div><div class="pixel" style="font-size: 22px" dir="ltr">[$ —]</div></div>
<div><div style="color: var(--muted); font-weight: 700">وقت الجلسة</div><div style="font-weight: 700">[التاريخ والوقت]</div></div>
<div><div style="color: var(--muted); font-weight: 700">التكلفة الفعلية</div><div class="pixel" dir="ltr">[$ —]</div></div>
</div>
<div style="{CARD}; padding: 20px 22px; display: flex; flex-direction: column; gap: 8px; font-size: 15px">
<div style="font-weight: 800; font-size: 18px">مصادر البيانات</div>
<div>أسعار ومؤشرات فنية · <span class="pixel" dir="ltr">yfinance</span></div>
<div>قوائم مالية وإفصاحات · <span class="pixel" dir="ltr">SEC EDGAR</span></div>
<div>أخبار · [المصدر الذي جلب منه الإطار الأخبار]</div>
<div style="color: var(--muted); font-size: 14px">أي مصدر ما اشتغل يظهر هنا بوضوح، وما نعوّضه بأرقام من عندنا.</div>
</div>
<div style="padding: 12px 18px; border-radius: 18px; background: #FFE9C7; color: #6B4210; font-weight: 700; font-size: 15px">تحليل للمساعدة على التفكير، وليس نصيحة مالية. القرار النهائي لك.</div>
</div>
<div style="flex-grow: 1; min-width: 0; display: flex; flex-direction: column; gap: 14px; overflow: hidden">
<div style="display: flex; align-items: baseline; justify-content: space-between"><div style="font-size: 24px; font-weight: 800">وش قال كل واحد</div><div style="font-size: 14px; color: var(--muted); font-weight: 700">اضغط «التفاصيل» عشان تشوف التحليل الكامل</div></div>
<div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: start">
{"".join(cards)}
</div>
</div>
</div>"""
    toggles = "\n".join(
        f"      open{i}: !!s.o{i}, label{i}: s.o{i} ? 'إخفاء التفاصيل' : 'التفاصيل', toggle{i}: () => this.setState({{ o{i}: !s.o{i} }}),"
        for i in range(8))
    sb = f"""  constructor(props) {{ super(props); this.state = {{ o0: true }}; }}
  renderVals() {{
    const s = this.state;
    return {{
{toggles}
    }};
  }}"""
    return page("Veyro Report", "Report.dc.html", inner, 1440, 1320, sb)


# ---------------------------------------------------------------- History
def history():
    rows = [("NVDA", "احتفاظ", "#C46F0A", "#FFE9C7"), ("AAPL", "شراء", "#1F7A4A", "#DDF3E5"),
            ("TSLA", "بيع", "#B23A2E", "#FBE0DC"), ("MSFT", "شراء", "#1F7A4A", "#DDF3E5")]
    trs = "".join(f"""<div role="row" style="display: grid; grid-template-columns: 1.1fr 1fr 1fr 1fr 1fr 1fr 0.8fr; gap: 10px; align-items: center; padding: 14px 18px; border-radius: 20px; background: var(--cream)">
<div role="cell" class="pixel" style="font-size: 20px; font-weight: 700">{t}</div>
<div role="cell"><span style="padding: 3px 14px; border-radius: 12px; background: {bg}; color: {c}; font-weight: 800">{v}</span></div>
<div role="cell">[التاريخ]</div>
<div role="cell" class="pixel" dir="ltr" style="text-align: end">[$ —]</div>
<div role="cell" class="pixel" dir="ltr" style="text-align: end">[$ —]</div>
<div role="cell" class="pixel" dir="ltr" style="text-align: end">[± %] / SPY [± %]</div>
<div role="cell" style="font-weight: 800; color: var(--muted)">[—]</div>
</div>""" for t, v, c, bg in rows)
    heads = ["السهم", "القرار", "التاريخ", "السعر وقتها", "السعر الآن", "السهم مقابل SPY", "النتيجة"]
    head = "".join(f'<div role="columnheader">{h}</div>' for h in heads)
    inner = f"""<div style="display: flex; gap: 26px; flex-grow: 1; min-height: 0">
<div style="flex-grow: 1; min-width: 0; {CARD}; padding: 24px; display: flex; flex-direction: column; gap: 14px">
<div style="display: flex; justify-content: space-between; align-items: center"><div style="font-size: 26px; font-weight: 800">لوحة النتائج الصادقة</div>
<div style="font-size: 14px; color: var(--muted); font-weight: 700">نقارن كل قرار بأداء SPY في نفس الفترة</div></div>
<div role="table" aria-label="الجلسات السابقة" style="display: flex; flex-direction: column; gap: 10px">
<div role="row" style="display: grid; grid-template-columns: 1.1fr 1fr 1fr 1fr 1fr 1fr 0.8fr; gap: 10px; padding: 0 18px; font-size: 14px; font-weight: 800; color: var(--muted)">{head}</div>
{trs}
</div>
<div style="font-size: 14px; color: var(--muted)">القيم بين الأقواس تمتلئ من بيانات حقيقية وقت الجلسة ووقت الفتح. لو ما توفّر السعر نكتب «غير متوفر».</div>
</div>
<div style="width: 360px; flex-shrink: 0; display: flex; flex-direction: column; gap: 18px">
<div style="{CARD}; padding: 24px; display: flex; flex-direction: column; align-items: center; gap: 10px; background: var(--cream)">
{still('Tank', 5, frame='down')}
<div style="font-size: 20px; font-weight: 800; text-align: center">تانك يقول:</div>
<div style="font-size: 16px; line-height: 1.7; text-align: center">نحسب كم مرة كان القرار صح مقارنة بالسوق… بدون تجميل. على مهلك… بثبات.</div>
</div>
<div style="{CARD}; padding: 22px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px">
<div><div style="color: var(--muted); font-weight: 700">عدد الجلسات</div><div class="pixel" style="font-size: 30px; font-weight: 700">[—]</div></div>
<div><div style="color: var(--muted); font-weight: 700">تفوّق على SPY</div><div class="pixel" style="font-size: 30px; font-weight: 700">[— / —]</div></div>
</div>
</div>
</div>"""
    return page("Veyro History", "History.dc.html", inner, 1440, 900)


# ---------------------------------------------------------------- Settings / About
def settings():
    def seg(items, on_hole):
        return "".join(
            f'<button class="btn" onClick="{{{{ pick{on_hole}{i} }}}}" aria-pressed="{{{{ on{on_hole}{i} }}}}" style="flex-grow: 1; height: 44px; border-radius: 22px; border: 3px solid {{{{ bd{on_hole}{i} }}}}; background: {{{{ bg{on_hole}{i} }}}}; color: var(--ink); font-family: inherit; font-size: 15px; font-weight: 800; cursor: pointer">{lab}</button>'
            for i, lab in enumerate(items))

    lbl = "font-size: 15px; font-weight: 800; color: var(--muted)"
    sel = "height: 46px; border-radius: 23px; border: 3px solid var(--line); background: var(--card); color: var(--ink); padding: 0 16px; font-family: inherit; font-size: 15px"
    inner = f"""<div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px; flex-grow: 1; align-items: start">
<div style="{CARD}; padding: 26px; display: flex; flex-direction: column; gap: 14px">
<div style="font-size: 22px; font-weight: 800">النموذج والمفتاح</div>
<div style="{lbl}">مزوّد النموذج</div>
<div style="display: flex; gap: 8px">{seg(["Claude", "OpenAI", "DeepSeek"], "P")}</div>
<label for="key" style="{lbl}">مفتاح API</label>
<div style="display: flex; gap: 8px; align-items: center">
<input id="key" type="password" placeholder="الصق المفتاح الجديد هنا" dir="ltr" style="flex-grow: 1; min-width: 0; height: 46px; box-sizing: border-box; border-radius: 23px; border: 3px solid var(--line); background: var(--card); color: var(--ink); padding: 0 16px; font-size: 15px">
<button class="btn" style="height: 46px; padding: 0 18px; border-radius: 23px; border: none; background: #6CC38E; color: #16402A; font-family: inherit; font-size: 15px; font-weight: 800; cursor: pointer; box-shadow: 0 4px 0 #3E9A68">حفظ</button>
</div>
<div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; border-radius: 16px; background: var(--cream)"><span style="font-weight: 700">المفتاح المحفوظ</span><span class="pixel" dir="ltr">sk-…abcd</span></div>
<div style="font-size: 14px; line-height: 1.7; color: var(--muted)">يُحفظ في خزنة ويندوز على جهازك فقط، ولا يظهر كاملاً مرة ثانية.</div>
<label for="quick" style="{lbl}">نموذج المحللين (سريع)</label>
<select id="quick" style="{sel}"><option>Claude Haiku 4.5</option><option>Claude Sonnet 5</option></select>
<label for="deep" style="{lbl}">نموذج القرار (عميق)</label>
<select id="deep" style="{sel}"><option>Claude Opus 5.5</option><option>Claude Sonnet 5</option></select>
</div>
<div style="{CARD}; padding: 26px; display: flex; flex-direction: column; gap: 14px">
<div style="font-size: 22px; font-weight: 800">الشكل والصوت</div>
<div style="{lbl}">اللغة</div>
<div style="display: flex; gap: 8px">{seg(["العربية", "English"], "L")}</div>
<div style="{lbl}">المظهر</div>
<div style="display: flex; gap: 8px">{seg(["نهاري", "ليلي", "حسب الجهاز"], "T")}</div>
<div style="{lbl}">حيوية الحركة</div>
<div style="display: flex; gap: 8px">{seg(["هادئة", "متوسطة", "حيوية"], "A")}</div>
<div style="display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border-radius: 16px; background: var(--cream)"><label for="rm" style="font-weight: 700">تقليل الحركة</label><input id="rm" type="checkbox" style="width: 22px; height: 22px"></div>
<div style="display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border-radius: 16px; background: var(--cream)"><label for="snd" style="font-weight: 700">أصوات الشخصيات</label><input id="snd" type="checkbox" checked style="width: 22px; height: 22px"></div>
<div style="display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border-radius: 16px; background: var(--cream)"><label for="cost" style="font-weight: 700">عرض التكلفة</label><input id="cost" type="checkbox" checked style="width: 22px; height: 22px"></div>
</div>
<div style="{CARD}; padding: 26px; display: flex; flex-direction: column; gap: 14px; background: var(--cream)">
<div style="font-size: 22px; font-weight: 800">عن فيرو</div>
<div style="display: flex; gap: 4px; justify-content: center; flex-wrap: wrap">{"".join(still(n, 2) for n in ORDER)}</div>
<div style="font-size: 17px; font-weight: 600; line-height: 1.8">فيرو مكتبك الصغير الدافئ: ثمانية زملاء من الحيوانات يجتمعون حول أي سهم تختاره، يتناقشون قدامك بصوت عالي، وبعدين ليو يعلن القرار.</div>
<div style="display: flex; flex-direction: column; gap: 6px; font-size: 14px; line-height: 1.7">
<div>أولي يقرأ الشارت، وبَز يسمع وش يقول الناس، وبيب يلاحق الأخبار، وبيني يحسب الأرقام.</div>
<div>بولت يدافع عن الصعود وبرونو يدافع عن الهبوط، عشان تسمع الوجهين قبل أي قرار.</div>
<div>تانك يراجع المخاطر بهدوء، وليو يوزن الكل ويعطيك توصية واضحة مع السبب.</div>
<div>كل رقم تشوفه جاي من بيانات حقيقية، وإذا ما توفّر شي نقولها لك بصراحة.</div>
</div>
<div style="font-size: 15px; line-height: 1.8">مفاتيحك تبقى على جهازك، والقرار الأخير دايماً لك.</div>
<div style="font-size: 13px; color: var(--muted)">مبني على TradingAgents (رخصة <span dir="ltr">Apache-2.0</span>).</div>
</div>
</div>"""
    groups = {"P": 3, "L": 2, "T": 3, "A": 3}
    defaults = {"P": 0, "L": 0, "T": 0, "A": 1}
    lines = []
    for g, n in groups.items():
        for i in range(n):
            lines.append(f"      on{g}{i}: s.{g} === {i}, bg{g}{i}: s.{g} === {i} ? '#E4F5EA' : 'var(--card)', bd{g}{i}: s.{g} === {i} ? '#6CC38E' : 'var(--line)', pick{g}{i}: () => this.setState({{ {g}: {i} }}),")
    sb = f"""  constructor(props) {{ super(props); this.state = {json.dumps(defaults)}; }}
  renderVals() {{
    const s = this.state;
    return {{
{chr(10).join(lines)}
    }};
  }}"""
    return page("Veyro Settings", "Settings.dc.html", inner, 1440, 900, sb)


# ---------------------------------------------------------------- Cast sheet
def cast():
    cells = []
    for i, n in enumerate(CAST):
        m = META[n]
        cells.append(f"""<div style="{CARD}; padding: 18px; display: flex; flex-direction: column; gap: 10px; align-items: center">
<div style="display: flex; gap: 6px; align-items: flex-end" dir="ltr">
<div style="display: flex; flex-direction: column; align-items: center; gap: 2px">{still(n, 3, frame='typeA')}<span style="font-size: 11px; color: var(--muted)">typing</span></div>
<div style="display: flex; flex-direction: column; align-items: center; gap: 2px">{still(n, 3, frame='wave', talk=True)}<span style="font-size: 11px; color: var(--muted)">talking</span></div>
<div style="display: flex; flex-direction: column; align-items: center; gap: 2px">{still(n, 3, blink=True)}<span style="font-size: 11px; color: var(--muted)">blink</span></div>
</div>
<div style="display: flex; gap: 8px; align-items: center"><span style="padding: 1px 12px; border-radius: 10px; background: {COLOR[n]}; color: #FFFFFF; font-weight: 800; font-size: 17px">{m['ar']}</span><span class="pixel" style="font-weight: 700; font-size: 17px">{n}</span></div>
<div style="font-size: 14px; font-weight: 700; text-align: center">{m['role_ar']} · {m['animal_ar']}</div>
<div style="font-size: 13px; color: var(--muted); text-align: center" dir="ltr">{m['role_en']} · {m['animal_en']}</div>
<div style="display: flex; gap: 8px; font-size: 14px"><span style="padding: 2px 10px; border-radius: 10px; background: var(--cream)">{m['cp_ar']}</span><span class="pixel" style="padding: 2px 10px; border-radius: 10px; background: var(--cream)" dir="ltr">{m['cp_en']}</span></div>
<div class="pixel" style="font-size: 12px; color: var(--muted)" dir="ltr">voice: {m['pitch_word']} · {m['pitch']} Hz</div>
</div>""")
    inner = f"""<div style="display: flex; flex-direction: column; gap: 14px">
<div style="display: flex; justify-content: space-between; align-items: baseline"><div style="font-size: 28px; font-weight: 800">فريق المكتب</div><div style="font-size: 15px; color: var(--muted); font-weight: 700">تسعة زملاء، لكل واحد صوته وحركته وعبارته</div></div>
<div style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 18px">{"".join(cells)}</div>
</div>"""
    return page("Veyro Cast", "", inner, 1440, 1540)


files = {
    "Main.dc.html": office("ar", "day"),
    "OfficeNightEN.dc.html": office("en", "night"),
    "Report.dc.html": report(),
    "History.dc.html": history(),
    "Settings.dc.html": settings(),
    "Cast.dc.html": cast(),
}
for name, text in files.items():
    (OUT / name).write_text(text, encoding="utf-8")
    print(name, len(text))
