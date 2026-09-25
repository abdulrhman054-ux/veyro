import { useEffect, useState, type ReactNode } from "react";
import { api, type Settings } from "../api";
import { SpriteSvg, charColor } from "../art/Sprite";
import { PageHeader } from "../components/PageHeader";
import { ShariaSettings } from "../extras/Sharia";
import { DailyAssistantSettings } from "../assistant/Assistant";
import { CHAR_ORDER, charName, fmtUsd } from "../i18n";
import { usePrefs, type Intensity, type Theme } from "../prefs";

const MODEL_LABEL: Record<string, string> = {
  "claude-fable-5-1": "Claude Fable 5.1", "claude-fable-5": "Claude Fable 5", "claude-opus-5-5": "Claude Opus 5.5",
  "claude-opus-5": "Claude Opus 5", "claude-opus-4-8": "Claude Opus 4.8", "claude-opus-4-7": "Claude Opus 4.7",
  "claude-opus-4-6": "Claude Opus 4.6", "claude-sonnet-5": "Claude Sonnet 5", "claude-sonnet-4-6": "Claude Sonnet 4.6",
  "claude-haiku-4-5": "Claude Haiku 4.5",
};

/** Longest-prefix price lookup, same rule as the backend. */
function priceOf(model: string, pricing: Record<string, [number, number]> | undefined) {
  if (!pricing) return null;
  const k = Object.keys(pricing).sort((a, b) => b.length - a.length).find((p) => model === p || model.startsWith(p + "-") || model.startsWith(p + "@"));
  return k ? pricing[k] : null;
}

export function SettingsScreen({ settings, onChange, extra }: { settings: Settings | null; onChange: (s: Settings) => void; extra?: ReactNode }) {
  const { t, prefs, set } = usePrefs();
  const lang = prefs.lang;
  const [key, setKey] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [test, setTest] = useState<ConnTest | null>(null);
  const [testing, setTesting] = useState(false);
  const [ws, setWs] = useState("");
  const [live, setLive] = useState<{ id: string; name: string }[] | null>(null);
  const [liveState, setLiveState] = useState<"idle" | "loading" | "error">("idle");
  const [liveFor, setLiveFor] = useState<string | null>(null);
  const loadLive = async () => {
    if (!settings) return;
    setLiveState("loading");
    try {
      const r = await api.get<{ models: { id: string; name: string }[] }>(`/api/models/live?provider=${settings.provider}`);
      setLive(r.models); setLiveFor(settings.provider); setLiveState("idle");
    } catch { setLiveState("error"); }
  };
  useEffect(() => { if (msg) { const h = setTimeout(() => setMsg(null), 2200); return () => clearTimeout(h); } }, [msg]);

  if (!settings) return <div className="card" aria-busy="true">…</div>;
  const p = settings.providers[settings.provider];
  const k = settings.keys[settings.provider];
  const liveHere = liveFor === settings.provider ? live : null;
  const rec = p.recommend;
  const onRec = !!rec && rec.quick === settings.quick_model && rec.deep === settings.deep_model;

  const put = async (body: Partial<{ provider: string; quick_model: string; deep_model: string }>) => {
    try { onChange(await api.put<Settings>("/api/settings", body)); setMsg(t.saved); } catch { setMsg(t.error); }
  };
  const saveKey = async () => {
    if (!key.trim()) return;
    setTesting(true); setTest(null);
    try {
      const r = await api.post<Settings & { test?: ConnTest }>("/api/keys", { provider: settings.provider, key: key.trim() });
      onChange(r); setKey(""); setMsg(t.saved); if (r.test) setTest(r.test);
    } catch { setMsg(t.error); }
    setTesting(false);
  };
  const putModel = async (body: { quick_model?: string; deep_model?: string }, custom: boolean) => {
    try {
      onChange(await api.put<Settings>("/api/settings", { provider: settings.provider, ...body, custom_model: custom }));
      setMsg(t.saved);
      if (custom && k?.present) void runTest();   // a typed model ID is checked straight away
    } catch { setMsg(lang === "ar" ? "معرّف النموذج غير صالح" : "That model ID isn't valid"); }
  };
  const runTest = async () => {
    setTesting(true); setTest(null);
    // Read the body directly: a failed test is an answer with details, not an exception.
    try { const r = await fetch("/api/keys/test", { method: "POST" }); setTest(await r.json()); }
    catch { setTest({ ok: false, code: "network", models: {} }); }
    setTesting(false);
  };
  const saveWs = async () => {
    try { onChange(await api.put<Settings>("/api/settings", { anthropic_workspace_id: ws.trim() })); setWs(""); setMsg(t.saved); void runTest(); }
    catch { setMsg(lang === "ar" ? "المعرّف لازم يبدأ بـ wrkspc_" : "The ID must start with wrkspc_"); }
  };
  const removeKey = async () => { onChange(await api.del<Settings>(`/api/keys/${settings.provider}`)); setMsg(t.saved); };

  const Seg = <V extends string>({ value, options, onPick, label }: { value: V; options: [V, string][]; onPick: (v: V) => void; label: string }) => (
    <div className="segbtns" role="group" aria-label={label}>
      {options.map(([v, l]) => <button key={v} aria-pressed={value === v} onClick={() => onPick(v)}>{l}</button>)}
    </div>
  );
  const e = settings.estimate;

  return (
    <div className="stack" style={{ gap: 20 }}>
      <PageHeader host="Ollie" title={lang === "ar" ? "الإعدادات" : "Settings"}
        sub={lang === "ar" ? "الأساسيات هنا وبسيطة، والمتقدم مطوي تحت لمن يحتاجه. أولي يشرح لك بهدوء." : "The basics are here and simple; advanced options are folded below. Ollie explains, calmly."}
        say={lang === "ar" ? "خلوني أوضح لكم…" : "Let me walk you through it…"} />
      <nav className="settings-jump row" aria-label={lang === "ar" ? "أقسام الإعدادات" : "Settings sections"}>
        {([["s-model", t.modelAndKey], ["fees-h", lang === "ar" ? "الرسوم" : "Fees"], ["s-sharia", lang === "ar" ? "الفحص الشرعي" : "Sharia"],
          ["s-look", t.lookAndSound], ["s-about", t.about]] as const).map(([id, label]) => (
          <a key={id} className="chip mkt" href={`#${id}`} onClick={(e) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>{label}</a>
        ))}
      </nav>
      <div className="grid3">
        <section className="card stack" aria-labelledby="s-model">
          <h2 id="s-model" style={{ fontSize: 22 }}>{t.modelAndKey}</h2>
          <div className="label">{t.provider}</div>
          <Seg label={t.provider} value={settings.provider} options={Object.entries(settings.providers).filter(([, v]) => !v.extra).map(([id, v]) => [id, v.label])} onPick={(v) => put({ provider: v })} />
          <label className="row" style={{ gap: 8 }}>
            <span className="label">{lang === "ar" ? "أو أي ذكاء اصطناعي آخر يدعمه الإطار" : "Or any other AI the framework supports"}</span>
            <select className="field" style={{ height: 40, flex: 1, minWidth: 160 }} value={p.extra ? settings.provider : ""}
              onChange={(ev) => ev.target.value && put({ provider: ev.target.value })}>
              <option value="">{lang === "ar" ? "اختر…" : "Choose…"}</option>
              {Object.entries(settings.providers).filter(([, v]) => v.extra).map(([id, v]) => <option key={id} value={id}>{v.label}</option>)}
            </select>
          </label>
          {p.needs_key === false ? (
            <p className="toggle" style={{ margin: 0 }}>{lang === "ar" ? "يشتغل على جهازك بدون مفتاح (لازم يكون Ollama مثبّت وشغّال)." : "Runs on your computer with no key (Ollama must be installed and running)."}</p>
          ) : <>
          <label className="label" htmlFor="apikey">{t.apiKey}</label>
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <input id="apikey" className="field ltr" style={{ flex: 1, minWidth: 0 }} type="password" autoComplete="off" spellCheck={false}
              placeholder={t.pasteKey} value={key} onChange={(ev) => setKey(ev.target.value)} />
            <button className="primary green btn" style={{ height: 46, fontSize: 16 }} onClick={saveKey} disabled={!key.trim()}>{t.save}</button>
          </div>
          <div className="toggle">
            <span>{t.savedKey}</span>
            <span className="row" style={{ gap: 8 }}>
              <span className="pixel ltr">{k?.present ? k.masked : t.noKey}</span>
              {k?.source === "env" && <span className="muted" style={{ fontSize: 12 }}>{t.keyFromEnv}</span>}
              {k?.source === "app" && <button className="ghost btn" style={{ height: 32 }} onClick={removeKey}>{t.remove}</button>}
            </span>
          </div>
          <p className="muted" style={{ margin: 0, fontSize: 14, lineHeight: 1.7 }}>{t.keyNote}</p>
          <button className="ghost btn" style={{ alignSelf: "flex-start" }} onClick={runTest} disabled={testing || !k?.present}>
            {testing ? (lang === "ar" ? "نختبر…" : "Testing…") : (lang === "ar" ? "اختبر الاتصال" : "Test connection")}</button>
          {test && <ConnResult test={test} lang={lang} />}
          {settings.provider === "anthropic" && (
            <div className="stack" style={{ gap: 6, padding: 10, borderRadius: 16, background: test?.code === "workspace" ? "var(--holdbg)" : "var(--cream)" }}>
              <label className="label" htmlFor="ws">{lang === "ar" ? "معرّف مساحة العمل (Workspace ID), فقط إذا طلبه مفتاحك" : "Workspace ID, only if your key needs it"}</label>
              <div className="row" style={{ flexWrap: "nowrap" }}>
                <input id="ws" className="field ltr" style={{ flex: 1, minWidth: 0, height: 40 }} spellCheck={false} placeholder={settings.anthropic_workspace_id ?? "wrkspc_…"}
                  value={ws} onChange={(ev) => setWs(ev.target.value)} />
                <button className="ghost btn" disabled={!ws.trim()} onClick={saveWs}>{t.save}</button>
              </div>
              <span className="muted" style={{ fontSize: 12, lineHeight: 1.6 }}>{lang === "ar"
                ? "تلقاه في console.anthropic.com ← Settings ← Workspaces، ويبدأ بـ wrkspc_. أو أنشئ مفتاح داخل مساحة عمل وما تحتاج هذا."
                : "Find it at console.anthropic.com → Settings → Workspaces; it starts with wrkspc_. Or create a key inside a workspace and skip this."}</span>
            </div>
          )}
          </>}
          {rec && (rec.quick || rec.deep) && (
            <div className="stack" style={{ gap: 6, padding: 10, borderRadius: 16, background: onRec ? "var(--buybg)" : "var(--cream)" }}>
              <b style={{ fontSize: 15 }}>★ {lang === "ar" ? "التوصية" : "Recommended"}: <span className="ltr">{MODEL_LABEL[rec.quick ?? ""] ?? rec.quick ?? "—"} · {MODEL_LABEL[rec.deep ?? ""] ?? rec.deep ?? "—"}</span></b>
              <span style={{ fontSize: 13, lineHeight: 1.7 }}>{lang === "ar" ? rec.why_ar : rec.why_en}</span>
              {onRec ? <span style={{ fontSize: 13, fontWeight: 800, color: "var(--buy)" }}>✓ {lang === "ar" ? "مستخدمة الآن" : "In use"}</span>
                : <button className="ghost btn" style={{ alignSelf: "flex-start" }} disabled={!rec.quick || !rec.deep}
                    onClick={() => putModel({ quick_model: rec.quick!, deep_model: rec.deep! }, !(p.quick.includes(rec.quick!) && p.deep.includes(rec.deep!)))}>
                    {lang === "ar" ? "استخدم الموصى به" : "Use the recommended pair"}</button>}
            </div>
          )}
          <ModelPicker id="quick" label={t.quickModel} value={settings.quick_model} options={p.quick} lang={lang} pricing={settings.pricing}
            live={liveHere} recommended={rec?.quick ?? null} onPick={(m, custom) => putModel({ quick_model: m }, custom)} />
          <ModelPicker id="deep" label={t.deepModel} value={settings.deep_model} options={p.deep} lang={lang} pricing={settings.pricing}
            live={liveHere} recommended={rec?.deep ?? null} onPick={(m, custom) => putModel({ deep_model: m }, custom)} />
          {p.listable && (
            <div className="row" style={{ gap: 8 }}>
              <button className="ghost btn" onClick={loadLive} disabled={(p.needs_key !== false && !k?.present) || liveState === "loading"}>
                {liveState === "loading" ? (lang === "ar" ? "نجيب القائمة…" : "Loading…") : (lang === "ar" ? `حمّل كل نماذج ${p.label} المتاحة لي` : `Load every ${p.label} model I can use`)}
              </button>
              {liveHere && <span className="muted" style={{ fontSize: 13 }}>{lang === "ar" ? `${liveHere.length} نموذج متاح` : `${liveHere.length} models available`}</span>}
              {liveState === "error" && <span className="muted" style={{ fontSize: 13 }}>{lang === "ar" ? "ما قدرنا نجيب القائمة. اختبر الاتصال أولاً." : "Couldn't load the list. Test the connection first."}</span>}
            </div>
          )}
          <p className="muted" style={{ margin: 0, fontSize: 13, lineHeight: 1.7 }}>{lang === "ar"
            ? "السريع: للمحللين والنقاش وكلام الشخصيات (أغلب الاستهلاك). العميق: لقرار ليو وخطة الاستثمار. تقدر تختار أي نموذج في الخانتين."
            : "Quick: analysts, debate and the characters' lines (most of the usage). Deep: Leo's decision and investment plan. Any model works in either slot."}</p>
          <BudgetCap settings={settings} onChange={onChange} lang={lang} />
          <BrokerFees settings={settings} onChange={onChange} lang={lang} />
          <div className="toggle"><span>{t.estimate}</span>
            <span className="pixel ltr">{e.known && e.low != null && e.high != null ? `${fmtUsd(e.low, lang)} – ${fmtUsd(e.high, lang)}` : t.unknownPrice}</span></div>
          <CustomPrices settings={settings} onChange={onChange} lang={lang} pricing={settings.pricing} />
        </section>

        <ShariaSettings settings={settings} onChange={onChange} />

        <section className="card stack" aria-labelledby="s-look">
          <h2 id="s-look" style={{ fontSize: 22 }}>{t.lookAndSound}</h2>
          <div className="label">{t.language}</div>
          <Seg label={t.language} value={prefs.lang} options={[["ar", "العربية"], ["en", "English"]]} onPick={(v) => set({ lang: v })} />
          <div className="label">{t.appearance}</div>
          <Seg<Theme> label={t.appearance} value={prefs.theme} options={[["day", t.day], ["night", t.night], ["system", t.system]]} onPick={(v) => set({ theme: v })} />
          <div className="label">{t.intensity}</div>
          <Seg<Intensity> label={t.intensity} value={prefs.intensity} options={[["calm", t.calm], ["normal", t.normal], ["lively", t.lively]]} onPick={(v) => set({ intensity: v })} />
          <label className="toggle"><span>{t.reduceMotion}</span><input type="checkbox" checked={prefs.reduceMotion} onChange={(ev) => set({ reduceMotion: ev.target.checked })} /></label>
          <label className="toggle"><span>{t.voices}</span><input type="checkbox" checked={prefs.sound} onChange={(ev) => set({ sound: ev.target.checked })} /></label>
          <label className="toggle"><span>{t.showCost}</span><input type="checkbox" checked={prefs.showCost} onChange={(ev) => set({ showCost: ev.target.checked })} /></label>
          <div className="label">{lang === "ar" ? "سهولة الاستخدام" : "Accessibility"}</div>
          <Seg label={lang === "ar" ? "حجم الخط" : "Text size"} value={prefs.textSize}
            options={[["normal", lang === "ar" ? "عادي" : "Normal"], ["large", lang === "ar" ? "كبير" : "Large"], ["xlarge", lang === "ar" ? "كبير جداً" : "Extra large"]]}
            onPick={(v) => set({ textSize: v })} />
          <label className="toggle"><span>{lang === "ar" ? "تباين عالٍ (ألوان أوضح)" : "High contrast"}</span><input type="checkbox" checked={prefs.contrast} onChange={(ev) => set({ contrast: ev.target.checked })} /></label>
          <label className="toggle"><span>{lang === "ar" ? "اقرأ كلام الشخصيات بصوت عالٍ" : "Read the characters' lines aloud"}</span><input type="checkbox" checked={prefs.readAloud} onChange={(ev) => set({ readAloud: ev.target.checked })} /></label>
          <p className="muted kbd-hint" style={{ margin: 0, lineHeight: 1.9 }}>{lang === "ar"
            ? <>اختصارات: <kbd>/</kbd> البحث عن سهم · <kbd>Space</kbd> السطر التالي · <kbd>Esc</kbd> إيقاف الجلسة</>
            : <>Shortcuts: <kbd>/</kbd> find a stock · <kbd>Space</kbd> next line · <kbd>Esc</kbd> stop the session</>}</p>
        </section>

        <section className="card cream stack" aria-labelledby="s-about">
          <h2 id="s-about" style={{ fontSize: 22 }}>{t.about}</h2>
          <div className="cast-grid">{[...CHAR_ORDER, "Albie" as const].map((c) => (
            <div key={c} className="cast-cell"><SpriteSvg name={c} px={2} /><span className="tagname" style={{ background: charColor(c), fontSize: 12, padding: "0 8px" }}>{charName(c, lang)}</span></div>
          ))}</div>
          <p style={{ margin: 0, lineHeight: 1.8, fontSize: 17, fontWeight: 600 }}>{t.aboutText}</p>
          <div className="stack" style={{ gap: 8 }}>
            {t.aboutPoints.map((pt, i) => (
              <div key={i} className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap", gap: 10 }}>
                <SpriteSvg name={(["Ollie", "Bolt", "Leo", "Albie", "Benny", "Tank"] as const)[i % 6]} px={1} />
                <span style={{ lineHeight: 1.7 }}>{pt}</span>
              </div>
            ))}
          </div>
          <p style={{ margin: 0, lineHeight: 1.8 }}>{t.aboutPromise}</p>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>{t.builtOn}</p>
          <p className="muted" style={{ margin: 0, fontSize: 14, lineHeight: 1.7 }}>{t.artNote}</p>
          <p className="muted" style={{ margin: 0, fontSize: 14 }}>{t.fontsNote}</p>
          <p className="muted" style={{ margin: 0, fontSize: 14 }}>{t.disclaimer}</p>
        </section>
      </div>
      <DailyAssistantSettings />
      <details className="card advanced">
        <summary style={{ cursor: "pointer", fontSize: 20, fontWeight: 800 }}>
          {lang === "ar" ? "إعدادات متقدمة (اختيارية)" : "Advanced settings (optional)"}
          <span className="muted" style={{ fontSize: 14, fontWeight: 600, marginInlineStart: 10 }}>
            {lang === "ar" ? "فريق التحليل، مصادر إضافية، والتنفيذ عبر Alpaca" : "analysis team, extra data sources, Alpaca execution"}
          </span>
        </summary>
        <div className="stack" style={{ gap: 20, marginTop: 16 }}>
          <section className="card stack" aria-labelledby="ds-h">
            <h2 id="ds-h" style={{ fontSize: 22 }}>{lang === "ar" ? "مصدر بيانات السوق" : "Market data source"}</h2>
            <Seg label={lang === "ar" ? "مصدر البيانات" : "Data source"} value={settings.data_source ?? "yahoo"}
              options={[["yahoo", "Yahoo Finance"], ["stooq", "Stooq"], ["alpha_vantage", "Alpha Vantage"]]}
              onPick={(v) => put({ data_source: v } as never)} />
            <p className="muted" style={{ margin: 0, fontSize: 13, lineHeight: 1.8 }}>{lang === "ar"
              ? "Yahoo: الافتراضي، يغطي السعودي والأمريكي والمعادن والبث المباشر. Stooq: مجاني بدون مفتاح، أسهم أمريكية ومؤشرات ومعادن فورية وعملات، بدون تداول. Alpha Vantage: بمفتاحك (المجاني حوالي 25 طلب باليوم)، أسهم أمريكية، ويصير هو مصدر TradingAgents في التحليل. أي شي ما يغطيه المصدر المختار يجي من Yahoo، وكل سعر يذكر مصدره."
              : "Yahoo: the default; covers Saudi, US, metals and the live stream. Stooq: free, no key; US stocks, indices, spot metals and FX, no Tadawul. Alpha Vantage: your key (free tier about 25 requests a day), US stocks, and it becomes TradingAgents' own data vendor for the analysis. Anything the chosen source doesn't cover comes from Yahoo, and every price names its source."}</p>
            {settings.data_source === "alpha_vantage" && !settings.data_keys.alpha_vantage.present && (
              <div className="warnstrip">{lang === "ar" ? "أضف مفتاح Alpha Vantage تحت (مصادر بيانات اختيارية)، وإلا نستخدم Yahoo." : "Add your Alpha Vantage key below (optional data sources); until then Yahoo is used."}</div>)}
          </section>
          <TeamSettings settings={settings} onChange={onChange} />
          {extra}
        </div>
      </details>
      {msg && <div className="toast" role="status">{msg}</div>}
    </div>
  );
}


const ANALYST_CHAR: Record<string, "Ollie" | "Buzz" | "Pip" | "Benny"> = { market: "Ollie", social: "Buzz", news: "Pip", fundamentals: "Benny" };

function TeamSettings({ settings, onChange }: { settings: Settings; onChange: (s: Settings) => void }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang;
  const ar = lang === "ar";
  const [err, setErr] = useState<string | null>(null);
  const [fred, setFred] = useState("");
  const [av, setAv] = useState("");
  const [jev, setJev] = useState("");
  const team = settings.team;
  const put = async (body: Record<string, unknown>) => {
    setErr(null);
    try { onChange(await api.put<Settings>("/api/settings", body)); } catch { setErr(ar ? "لازم محلل واحد على الأقل." : "Keep at least one analyst."); }
  };
  const toggle = (a: string) => {
    const next = team.analysts.includes(a) ? team.analysts.filter((x) => x !== a) : [...team.analysts, a];
    void put({ analysts: next });
  };
  const saveData = async (source: "fred" | "alpha_vantage" | "typesafe", key: string) => {
    try { onChange(await api.post<Settings>("/api/data_keys", { source, key: key.trim() })); if (source === "fred") setFred(""); else if (source === "alpha_vantage") setAv(""); else setJev(""); } catch { setErr(ar ? "مفتاح غير صالح." : "Invalid key."); }
  };
  const Rounds = ({ value, onPick, label }: { value: number; onPick: (n: number) => void; label: string }) => (
    <div className="segbtns" role="group" aria-label={label}>{[1, 2, 3].map((n) => <button key={n} aria-pressed={value === n} onClick={() => onPick(n)}>{n}</button>)}</div>
  );
  return (
    <section className="card stack" aria-labelledby="team-h">
      <h2 id="team-h" style={{ fontSize: 22 }}>{ar ? "فريق التحليل (خصائص TradingAgents)" : "Analysis team (TradingAgents options)"}</h2>
      <div className="grid2">
        <div className="stack">
          <div className="label">{ar ? "المحللون الحاضرون" : "Analysts attending"}</div>
          {Object.entries(ANALYST_CHAR).map(([a, c]) => (
            <label key={a} className="toggle">
              <span className="row"><SpriteSvg name={c} px={2} /> {ar ? { market: "أولي · التحليل الفني", social: "بَز · المزاج العام", news: "بيب · الأخبار", fundamentals: "بيني · الأساسيات" }[a] : { market: "Ollie · Technicals", social: "Buzz · Sentiment", news: "Pip · News", fundamentals: "Benny · Fundamentals" }[a]}</span>
              <input type="checkbox" checked={team.analysts.includes(a)} onChange={() => toggle(a)} />
            </label>
          ))}
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>{ar ? "الغايب يروح استراحة قهوة في المكتب. فريق أصغر = جلسة أسرع وأرخص. للعملات الرقمية بيني يستريح تلقائياً." : "Anyone left out takes a coffee break in the office. A smaller team is faster and cheaper. For crypto, Benny rests automatically."}</p>
        </div>
        <div className="stack">
          <div className="label">{ar ? "جولات نقاش بولت وبرونو" : "Bull vs Bear debate rounds"}</div>
          <Rounds value={team.debate_rounds} onPick={(n) => put({ debate_rounds: n })} label="debate" />
          <div className="label">{ar ? "جولات نقاش فريق المخاطر (تانك)" : "Risk team rounds (Tank)"}</div>
          <Rounds value={team.risk_rounds} onPick={(n) => put({ risk_rounds: n })} label="risk" />
          <div className="label">{ar ? "مصادر بيانات اختيارية" : "Optional data sources"}</div>
          {([["fred", "FRED (macro)", fred, setFred], ["alpha_vantage", "Alpha Vantage", av, setAv], ["typesafe", "Jev (TypeSafe)", jev, setJev]] as const).map(([k, label, v, setV]) => (
            <div key={k} className="row" style={{ flexWrap: "nowrap" }}>
              <span className="pixel ltr" style={{ minWidth: 110 }}>{label}</span>
              <input className="field ltr" style={{ flex: 1, minWidth: 0, height: 40 }} type="password" autoComplete="off" value={v} placeholder={settings.data_keys[k].present ? settings.data_keys[k].masked ?? "" : (ar ? "مفتاح اختياري" : "optional key")} onChange={(e) => setV(e.target.value)} />
              <button className="ghost btn" disabled={!v.trim()} onClick={() => saveData(k, v)}>{ar ? "حفظ" : "Save"}</button>
            </div>
          ))}
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>{ar ? "المصدر الأساسي Yahoo Finance مجاني وشغّال دائماً. هذي المفاتيح تضيف بيانات فقط (Jev ينقّي منشورات التواصل من الضجيج)." : "Yahoo Finance is the free default and always on. These keys only add data (Jev filters noise out of social posts)."}</p>
        </div>
      </div>
      <div className="grid2">
        <div className="stack">
          <div className="label">{ar ? "مزوّدون إضافيون يدعمهم الإطار" : "More providers the framework supports"}</div>
          <div className="segbtns" role="group">
            {Object.entries(settings.providers).filter(([, v]) => v.extra).map(([id, v]) => (
              <button key={id} aria-pressed={settings.provider === id} onClick={() => put({ provider: id })}>{v.label}</button>
            ))}
          </div>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>{ar ? "Ollama يشتغل على جهازك مجاناً وبدون مفتاح. أسعار هذي المزوّدات غير معروفة لنا، فنعرض عدد الكلمات فقط." : "Ollama runs free on your computer with no key. We don't know these providers' prices, so we show token counts only."}</p>
        </div>
        <div className="stack">
          <div className="label">{ar ? "عمق تفكير النموذج" : "Model reasoning depth"}</div>
          <div className="segbtns" role="group">
            {(["default", "low", "medium", "high"] as const).map((dp) => (
              <button key={dp} aria-pressed={(settings.reasoning_depth ?? "default") === dp} onClick={() => put({ reasoning_depth: dp })}>
                {ar ? { default: "تلقائي", low: "خفيف", medium: "متوسط", high: "عميق" }[dp] : { default: "Auto", low: "Light", medium: "Medium", high: "Deep" }[dp]}
              </button>
            ))}
          </div>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>{ar ? "أعمق = أدق غالباً لكن أبطأ وأغلى. يطبّق على Claude وOpenAI وGemini." : "Deeper is often more careful, but slower and pricier. Applies to Claude, OpenAI and Gemini."}</p>
        </div>
      </div>
      {err && <div className="warnstrip" role="alert">{err}</div>}
    </section>
  );
}

/** Monthly spending cap for analyses: once reached, no new paid session starts until next month (or you raise it). */
function BudgetCap({ settings, onChange, lang }: { settings: Settings; onChange: (s: Settings) => void; lang: "ar" | "en" }) {
  const ar = lang === "ar";
  const sp = settings.spend;
  const [v, setV] = useState(sp?.cap ? String(sp.cap) : "");
  const [msg, setMsg] = useState<string | null>(null);
  const save = async () => {
    const n = v.trim() === "" ? 0 : Number(v);
    if (!(n >= 0)) { setMsg(ar ? "اكتب رقم صحيح." : "Enter a valid number."); return; }
    try { onChange(await api.put<Settings>("/api/settings", { monthly_cap_usd: n })); setMsg(ar ? "انحفظ ✓" : "Saved ✓"); } catch { setMsg(ar ? "ما انحفظ." : "Not saved."); }
  };
  const pct = sp?.cap ? Math.min(1, sp.spent / sp.cap) : 0;
  return (
    <div className="stack" style={{ gap: 6, padding: 10, borderRadius: 16, background: "var(--cream)" }}>
      <label className="label" htmlFor="cap">{ar ? "سقف ميزانية التحليل الشهرية (دولار)" : "Monthly analysis budget cap (USD)"}</label>
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <input id="cap" className="field ltr" inputMode="decimal" style={{ flex: 1, minWidth: 0, height: 40 }} placeholder={ar ? "بدون سقف" : "no cap"}
          value={v} onChange={(e) => { setV(e.target.value); setMsg(null); }} />
        <button className="ghost btn" onClick={save}>{ar ? "حفظ" : "Save"}</button>
      </div>
      {sp && <>
        <div className="capbar" aria-hidden="true"><i style={{ width: `${pct * 100}%`, background: pct >= 1 ? "var(--sell)" : pct > 0.8 ? "var(--orange)" : "var(--buy)" }} /></div>
        <span style={{ fontSize: 13 }}>{ar ? `صرفت هذا الشهر ${"$"}${sp.spent.toFixed(2)}${sp.cap ? ` من ${"$"}${sp.cap}` : ""} في ${sp.sessions} جلسة.` : `Spent this month: $${sp.spent.toFixed(2)}${sp.cap ? ` of $${sp.cap}` : ""} across ${sp.sessions} sessions.`}
          {!!sp.other_calls && <span className="muted">{ar ? ` منها ${"$"}${(sp.other_usd ?? 0).toFixed(2)} على ${sp.other_calls} طلب جانبي (ترجمة، ألبي، اسأل الفريق، دليل المبتدئ).` : ` Includes $${(sp.other_usd ?? 0).toFixed(2)} on ${sp.other_calls} side requests (translations, Albie, Ask the team, the beginner guide).`}</span>}
          {!!sp.reserved && <span className="muted">{ar ? ` ومحجوز ${"$"}${sp.reserved.toFixed(2)} لجلسات شغالة الحين.` : ` Plus $${sp.reserved.toFixed(2)} held for sessions running now.`}</span>}
          {sp.unpriced_sessions > 0 && <span className="muted">{ar ? ` (${sp.unpriced_sessions} جلسة فيها نموذج سعره غير معروف: انحسب الجزء المعروف فقط، فالسقف ما يحميك كامل مع هالمزوّد)` : ` (${sp.unpriced_sessions} sessions used a model with an unknown price: only the priced part is counted, so the cap can't fully protect you with that provider)`}</span>}</span>
      </>}
      <span className="muted" style={{ fontSize: 12 }}>{ar ? "لما يوصل الصرف للسقف، ما تبدأ جلسات مدفوعة جديدة (الوضع التجريبي يبقى متاح). المسح يوقف عند السقف." : "Once spending reaches the cap no new paid session starts (demo still works); scans stop at the cap."}</span>
      {msg && <span style={{ fontSize: 13 }}>{msg}</span>}
    </div>
  );
}

/** The owner's broker fees per market, used by Leo's plan. Veyro doesn't guess them: until entered, the plan says so. */
function BrokerFees({ settings, onChange, lang }: { settings: Settings; onChange: (s: Settings) => void; lang: "ar" | "en" }) {
  const ar = lang === "ar";
  const f = settings.broker_fees;
  const [edit, setEdit] = useState<Record<string, { rate: string; min: string; vat: string }>>(() => Object.fromEntries((["sa", "us"] as const).map((m) => [m, {
    rate: f?.[m]?.set ? String(+(f[m].rate * 100).toFixed(4)) : "", min: f?.[m]?.set ? String(f[m].min) : "", vat: f?.[m]?.set ? String(+(f[m].vat * 100).toFixed(2)) : "" }])));
  const [msg, setMsg] = useState<string | null>(null);
  const save = async (m: "sa" | "us") => {
    const e = edit[m];
    const rate = Number(e.rate || 0) / 100, minimum = Number(e.min || 0), vat = Number(e.vat || 0) / 100;
    if (![rate, minimum, vat].every((x) => x >= 0 && Number.isFinite(x))) { setMsg(ar ? "اكتب أرقام صحيحة." : "Enter valid numbers."); return; }
    try { onChange(await api.put<Settings>("/api/fees", { market: m, rate, minimum, vat })); setMsg(ar ? "انحفظ ✓" : "Saved ✓"); }
    catch { setMsg(ar ? "ما انحفظ (تأكد إن النسبة أقل من 5٪)." : "Not saved (the rate must be under 5%)."); }
  };
  const set = (m: string, k: "rate" | "min" | "vat", v: string) => { setEdit((x) => ({ ...x, [m]: { ...x[m], [k]: v } })); setMsg(null); };
  return (
    <div className="stack" style={{ gap: 6, padding: 10, borderRadius: 16, background: "var(--cream)" }} aria-labelledby="fees-h">
      <b id="fees-h">{ar ? "رسوم الوسيط (لخطة ليو)" : "Broker fees (for Leo's plan)"}</b>
      <span className="muted" style={{ fontSize: 12, lineHeight: 1.6 }}>{ar
        ? "اكتبها من جدول رسوم وسيطك. ما نخمّنها: إذا ما كتبتها، الخطة تقول إنها ما تشمل الرسوم."
        : "Copy them from your broker's fee schedule. We don't guess: if left empty, the plan says fees aren't included."}</span>
      {(["sa", "us"] as const).map((m) => (
        <div key={m} className="row" style={{ gap: 6, flexWrap: "wrap" }}>
          <b style={{ minWidth: 70 }}>{m === "sa" ? (ar ? "السعودي" : "Saudi") : (ar ? "الأمريكي" : "US")}</b>
          <input className="field ltr" style={{ width: 90, height: 36 }} inputMode="decimal" placeholder="%" aria-label={ar ? "العمولة ٪" : "Commission %"} value={edit[m].rate} onChange={(e) => set(m, "rate", e.target.value)} />
          <input className="field ltr" style={{ width: 90, height: 36 }} inputMode="decimal" placeholder={m === "sa" ? (ar ? "حد أدنى ريال" : "min SAR") : "min $"} aria-label={ar ? "الحد الأدنى" : "Minimum"} value={edit[m].min} onChange={(e) => set(m, "min", e.target.value)} />
          <input className="field ltr" style={{ width: 80, height: 36 }} inputMode="decimal" placeholder={ar ? "ضريبة ٪" : "VAT %"} aria-label={ar ? "ضريبة القيمة المضافة ٪" : "VAT %"} value={edit[m].vat} onChange={(e) => set(m, "vat", e.target.value)} />
          <button className="ghost btn mini" onClick={() => void save(m)}>{ar ? "حفظ" : "Save"}</button>
          {f?.[m]?.set && <span className="muted" style={{ fontSize: 12 }}>✓</span>}
        </div>
      ))}
      {msg && <span style={{ fontSize: 13 }}>{msg}</span>}
    </div>
  );
}

/** Models Veyro has no price for (most non-Claude ones): the owner can type the price from the provider's pricing
 *  page, so the estimate and the monthly cap count them. Never filled in by Veyro. */
function CustomPrices({ settings, onChange, lang, pricing }: { settings: Settings; onChange: (s: Settings) => void; lang: "ar" | "en"; pricing?: Record<string, [number, number]> }) {
  const ar = lang === "ar";
  const models = [...new Set([settings.quick_model, settings.deep_model].filter((m): m is string => !!m))]
    .filter((m) => !priceOf(m, pricing) || settings.custom_prices?.[m]);
  const [vals, setVals] = useState<Record<string, [string, string]>>({});
  const [msg, setMsg] = useState<string | null>(null);
  if (!models.length) return null;
  const save = async (m: string) => {
    const [i, o] = (vals[m] ?? ["", ""]).map((x) => Number(x || 0));
    if (!(i >= 0 && o >= 0)) { setMsg(ar ? "اكتب أرقام صحيحة." : "Enter valid numbers."); return; }
    try { onChange(await api.put<Settings>("/api/prices", { model: m, input: i, output: o })); setMsg(ar ? "انحفظ ✓" : "Saved ✓"); }
    catch { setMsg(ar ? "ما انحفظ." : "Not saved."); }
  };
  return (
    <div className="stack" style={{ gap: 6, padding: 10, borderRadius: 16, background: "var(--cream)" }}>
      <b>{ar ? "سعر النموذج (غير معروف لفيرو)" : "Model price (unknown to Veyro)"}</b>
      <span className="muted" style={{ fontSize: 12, lineHeight: 1.6 }}>{ar
        ? "بدون سعر، التقدير وسقف الميزانية ما يقدرون يحسبون هالنموذج. اكتب السعر من صفحة أسعار المزوّد (دولار لكل مليون توكن)."
        : "Without a price, the estimate and the budget cap can't count this model. Copy the price from the provider's pricing page (USD per 1M tokens)."}</span>
      {models.map((m) => {
        const cur = settings.custom_prices?.[m];
        const v = vals[m] ?? [cur ? String(cur[0]) : "", cur ? String(cur[1]) : ""];
        return (
          <div key={m} className="row" style={{ gap: 6 }}>
            <span className="pixel ltr" style={{ minWidth: 120 }}>{m}</span>
            <input className="field ltr" style={{ width: 90, height: 36 }} inputMode="decimal" placeholder={ar ? "إدخال $" : "input $"} aria-label={ar ? `سعر الإدخال ${m}` : `Input price ${m}`}
              value={v[0]} onChange={(e) => { setVals((x) => ({ ...x, [m]: [e.target.value, v[1]] })); setMsg(null); }} />
            <input className="field ltr" style={{ width: 90, height: 36 }} inputMode="decimal" placeholder={ar ? "إخراج $" : "output $"} aria-label={ar ? `سعر الإخراج ${m}` : `Output price ${m}`}
              value={v[1]} onChange={(e) => { setVals((x) => ({ ...x, [m]: [v[0], e.target.value] })); setMsg(null); }} />
            <button className="ghost btn mini" onClick={() => void save(m)}>{ar ? "حفظ" : "Save"}</button>
          </div>
        );
      })}
      {msg && <span style={{ fontSize: 13 }}>{msg}</span>}
    </div>
  );
}

type ConnTest = { ok: boolean; code: string | null; models: Record<string, { model: string; ok: boolean; code?: string }>; workspace?: boolean; provider?: string };

const CONN_MSG: Record<string, { ar: string; en: string }> = {
  workspace: { ar: "مفتاحك صحيح بس ما هو مربوط بمساحة عمل، فلازم تضيف «معرّف مساحة العمل» تحت.", en: "Your key is valid but not tied to a workspace, so add the Workspace ID below." },
  auth: { ar: "المفتاح مرفوض. تأكد إنك نسخته كامل وإنه فعّال.", en: "The key was rejected. Check you copied all of it and that it's active." },
  no_key: { ar: "ما فيه مفتاح محفوظ.", en: "No key saved." },
  model: { ar: "النموذج المختار مو متاح لحسابك. جرّب نموذج ثاني.", en: "The chosen model isn't available to your account. Try another." },
  rate: { ar: "وصلت حد الاستخدام. استنى شوي.", en: "Rate limit reached. Wait a bit." },
  network: { ar: "ما قدرنا نوصل للإنترنت.", en: "Couldn't reach the internet." },
  unknown: { ar: "صار خطأ غير متوقع.", en: "Something unexpected went wrong." },
};

function ConnResult({ test, lang }: { test: ConnTest; lang: "ar" | "en" }) {
  const good = test.ok;
  return (
    <div className="stack" role="status" style={{ gap: 4, padding: 10, borderRadius: 14, background: good ? "var(--buybg)" : "var(--sellbg)", color: good ? "var(--buy)" : "var(--sell)" }}>
      <b>{test.provider && <span className="ltr">{test.provider} · </span>}{good ? (lang === "ar" ? "✓ الاتصال شغّال! الفريق جاهز." : "✓ Connected! The team is ready.") : `✗ ${(CONN_MSG[test.code ?? "unknown"] ?? CONN_MSG.unknown)[lang]}`}</b>
      {Object.entries(test.models).map(([role, m]) => (
        <span key={role} className="ltr" style={{ fontSize: 13 }}>{m.ok ? "✓" : "✗"} {m.model}</span>
      ))}
    </div>
  );
}

/** The framework's model list, plus "another model…" where any model ID can be typed. */
function ModelPicker({ id, label, value, options, lang, onPick, pricing, live, recommended }: {
  id: string; label: string; value: string | null; options: string[]; lang: "ar" | "en"; onPick: (m: string, custom: boolean) => void;
  pricing?: Record<string, [number, number]>; live?: { id: string; name: string }[] | null; recommended?: string | null;
}) {
  const CUSTOM = "__custom__";
  value = value ?? "";
  const extra = (live ?? []).filter((m) => !options.includes(m.id));
  const known = options.includes(value) || extra.some((m) => m.id === value);
  const names: Record<string, string> = Object.fromEntries((live ?? []).map((m) => [m.id, m.name]));
  const optLabel = (m: string) => {
    const pr = priceOf(m, pricing);
    const nm = (m === recommended ? "★ " : "") + (MODEL_LABEL[m] ?? names[m] ?? m);
    return pr ? `${nm} · $${pr[0]}/$${pr[1]}` : nm;
  };
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState(known ? "" : value);
  return (
    <>
      <label className="label" htmlFor={id}>{label}</label>
      <select id={id} className="field" value={typing ? CUSTOM : value}
        onChange={(ev) => { const v = ev.target.value; if (v === CUSTOM) { setTyping(true); } else { setTyping(false); onPick(v, !options.includes(v)); } }}>
        {options.map((m) => <option key={m} value={m}>{optLabel(m)}</option>)}
        {extra.length > 0 && <optgroup label={lang === "ar" ? "من حسابك" : "From your account"}>
          {extra.map((m) => <option key={m.id} value={m.id}>{optLabel(m.id)}</option>)}
        </optgroup>}
        {!value && <option value="" disabled>{lang === "ar" ? "اختر نموذجاً…" : "Pick a model…"}</option>}
        {!known && value && <option value={value}>{(lang === "ar" ? "مخصص: " : "Custom: ") + value}</option>}
        <option value={CUSTOM}>{lang === "ar" ? "✎ نموذج آخر (اكتب المعرّف)…" : "✎ Another model (type its ID)…"}</option>
      </select>
      {typing && (
        <div className="row" style={{ flexWrap: "nowrap" }}>
          <input className="field ltr" style={{ flex: 1, minWidth: 0, height: 40 }} spellCheck={false} autoFocus value={text}
            placeholder={lang === "ar" ? "مثال: claude-sonnet-5" : "e.g. claude-sonnet-5"} onChange={(ev) => setText(ev.target.value)}
            aria-label={lang === "ar" ? "معرّف النموذج" : "Model ID"} />
          <button className="ghost btn" disabled={!text.trim()} onClick={() => { onPick(text.trim(), true); setTyping(false); }}>{lang === "ar" ? "استخدمه" : "Use it"}</button>
        </div>
      )}
    </>
  );
}
