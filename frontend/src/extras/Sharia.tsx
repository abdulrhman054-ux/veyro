import { useEffect, useState, useSyncExternalStore } from "react";
import { api, type Settings } from "../api";
import { usePrefs } from "../prefs";

/** Optional Sharia screen (off by default). A badge per stock, a details box for the verdict/report, and the
 *  Settings section. Results come from /api/sharia/screen, separately from any analysis. */

export type ShariaReason = { code: string; value?: string | number; limit?: number; field?: string; industry?: string };
export type ShariaResult = {
  symbol: string; method: string; status: "compliant" | "not_compliant" | "unknown"; reasons: ShariaReason[];
  ratios: Record<string, number | null>; data_date: string | null; fetched_at: string | null; purification: number | null; source: string;
};
export type ShariaConf = { enabled: boolean; method: string; hide: boolean; methods?: Record<string, { ar: string; en: string }> };

// ---- one shared store: the current settings and the results fetched so far (batched, cached per method)
let conf: ShariaConf = { enabled: false, method: "aaoifi", hide: false };
const results = new Map<string, ShariaResult>();
const pending = new Set<string>();
const listeners = new Set<() => void>();
let version = 0;
let timer: ReturnType<typeof setTimeout> | null = null;
const emit = () => { version++; listeners.forEach((l) => l()); };
const key = (sym: string) => `${conf.method}:${sym.toUpperCase()}`;

export function setShariaConf(s: Settings["sharia"] | undefined) {
  if (!s) return;
  const changed = s.enabled !== conf.enabled || s.method !== conf.method || s.hide !== conf.hide;
  conf = { ...s };
  if (changed) emit();
}

function flush() {
  timer = null;
  const syms = [...pending];
  pending.clear();
  if (!syms.length) return;
  const method = conf.method;
  for (let i = 0; i < syms.length; i += 40) {
    const chunk = syms.slice(i, i + 40);
    api.post<{ results: Record<string, ShariaResult> }>("/api/sharia/screen", { symbols: chunk, method })
      .then((r) => { for (const [s, v] of Object.entries(r.results)) results.set(`${method}:${s}`, v); emit(); })
      .catch(() => { /* badge stays "checking"; the next request retries */ });
  }
}

function request(syms: string[]) {
  let added = false;
  for (const s of syms) {
    const u = s.toUpperCase();
    if (!u || results.has(key(u)) || pending.has(u)) continue;
    pending.add(u); added = true;
  }
  if (added && !timer) timer = setTimeout(flush, 120);
}

const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l); }; };

/** The current settings plus results for these symbols (fetched on demand while the screen is on). */
export function useSharia(symbols: string[]) {
  useSyncExternalStore(subscribe, () => version);
  const joined = symbols.join(",");
  useEffect(() => { if (conf.enabled && joined) request(joined.split(",")); }, [joined, conf.enabled, conf.method]); // eslint-disable-line react-hooks/exhaustive-deps
  const get = (s: string) => results.get(key(s));
  return { conf, get };
}

// ---- words
const METHOD_FALLBACK: Record<string, { ar: string; en: string }> = {
  aaoifi: { ar: "معيار أيوفي الشرعي رقم 21", en: "AAOIFI Shari'ah Standard No. 21" },
  sp: { ar: "مؤشرات إس آند بي الشرعية", en: "S&P Shariah Indices" },
  msci: { ar: "مؤشرات MSCI الإسلامية", en: "MSCI Islamic Index Series" },
};
export const methodName = (m: string, lang: "ar" | "en") => (conf.methods?.[m] ?? METHOD_FALLBACK[m] ?? { ar: m, en: m })[lang];

const ACT: Record<string, { ar: string; en: string }> = {
  conventional_finance: { ar: "بنوك أو تأمين تقليدي (قائم على الفائدة)", en: "conventional (interest-based) banking or insurance" },
  alcohol: { ar: "الكحول", en: "alcohol" }, gambling: { ar: "القمار", en: "gambling" }, pork: { ar: "لحم الخنزير", en: "pork" },
  adult: { ar: "ترفيه للكبار", en: "adult entertainment" }, tobacco: { ar: "التبغ", en: "tobacco" },
  media: { ar: "إعلام وترفيه تقليدي", en: "conventional media and entertainment" }, weapons: { ar: "أسلحة ودفاع", en: "weapons and defence" },
  hotels: { ar: "فنادق", en: "hotels" },
};
const FIELD: Record<string, { ar: string; en: string }> = {
  total_debt: { ar: "الديون", en: "debt" }, cash_st: { ar: "النقد والاستثمارات قصيرة الأجل", en: "cash and short-term investments" },
  receivables: { ar: "الذمم المدينة", en: "receivables" }, market_cap: { ar: "القيمة السوقية", en: "market value" },
  avg_market_cap_36m: { ar: "متوسط القيمة السوقية لـ 36 شهر", en: "36-month average market value" },
  total_assets: { ar: "إجمالي الأصول", en: "total assets" }, balance_sheet: { ar: "الميزانية العمومية", en: "balance sheet" },
  industry: { ar: "نشاط الشركة", en: "the company's industry" },
};
const pct = (v: unknown) => (typeof v === "number" ? `${(v * 100).toFixed(1)}%` : "—");

export function reasonText(r: ShariaReason, lang: "ar" | "en", method: string): string {
  const ar = lang === "ar";
  const den = method === "msci" ? (ar ? "إجمالي الأصول" : "total assets") : method === "sp" ? (ar ? "متوسط القيمة السوقية (36 شهر)" : "36-month average market value") : (ar ? "القيمة السوقية" : "market value");
  switch (r.code) {
    case "activity": return ar ? `النشاط الأساسي: ${ACT[String(r.value)]?.ar ?? r.value}` : `Core business: ${ACT[String(r.value)]?.en ?? r.value}`;
    case "debt_ratio": return ar ? `الديون بفائدة ${pct(r.value)} من ${den} (الحد ${pct(r.limit)})` : `Interest-bearing debt is ${pct(r.value)} of ${den} (limit ${pct(r.limit)})`;
    case "cash_ratio": return ar ? `النقد والأوراق بفائدة ${pct(r.value)} من ${den} (الحد ${pct(r.limit)})` : `Cash and interest-bearing securities are ${pct(r.value)} of ${den} (limit ${pct(r.limit)})`;
    case "receivables_ratio": return ar ? `الذمم المدينة ${pct(r.value)} من ${den} (الحد ${pct(r.limit)})` : `Receivables are ${pct(r.value)} of ${den} (limit ${pct(r.limit)})`;
    case "income_ratio": return ar ? `دخل الفوائد ${pct(r.value)} من الإيرادات (الحد ${pct(r.limit)})` : `Interest income is ${pct(r.value)} of revenue (limit ${pct(r.limit)})`;
    case "missing": return ar ? `ما فيه بيانات مجانية عن ${FIELD[String(r.field)]?.ar ?? r.field}` : `No free data on ${FIELD[String(r.field)]?.en ?? r.field}`;
    case "stale": return ar ? `آخر ميزانية قديمة (${r.value})، ما نحكم عليها` : `The latest balance sheet is too old (${r.value}) to judge`;
    case "no_data": return ar ? "ما قدرنا نجيب البيانات المالية" : "Couldn't get the company's financial data";
    case "not_equity": return ar ? "مو سهم شركة (صندوق أو عملة أو مؤشر): ما يُفحص هنا" : "Not a company share (fund, crypto or index): not screened here";
    case "islamic_finance": return ar ? "مصرف إسلامي: فحوص الفائدة ما تنطبق على البنوك، والحكم لهيئته الشرعية" : "Islamic bank: interest screens don't apply to banks; its own Sharia board certifies it";
    case "ambiguous_industry": return ar ? `النشاط (${r.industry}) يجمع أعمال مباحة وغير مباحة، فما نقدر نحكم آلياً` : `The industry (${r.industry}) mixes permissible and non-permissible businesses, so an automated screen can't tell`;
    case "activity_review": return ar ? `وصف الشركة يذكر ${ACT[String(r.value)]?.ar ?? r.value}، يحتاج مراجعة` : `The company description mentions ${ACT[String(r.value)]?.en ?? r.value}; needs a closer look`;
    case "currency_mismatch": return ar ? "القوائم المالية بعملة ثانية وما قدرنا نحوّلها" : "The accounts are in another currency and couldn't be converted";
    case "income_not_checked": return ar ? "دخل الفوائد غير منشور في البيانات المجانية، فما فحصناه" : "Interest income isn't reported in free data, so it wasn't checked";
    default: return r.code;
  }
}

export const disclaimer = (lang: "ar" | "en") => lang === "ar"
  ? "تقدير آلي من بيانات مالية عامة، وليس فتوى شرعية. تحقّق من هيئة شرعية معتمدة أو قائمة رسمية قبل الاستثمار."
  : "An automated estimate from public financial data, not a religious ruling (fatwa). Check with a recognised Sharia board or official list before investing.";

const LABEL = {
  compliant: { ar: "متوافق", en: "Compliant", icon: "✓", cls: "open" },
  not_compliant: { ar: "غير متوافق", en: "Not compliant", icon: "✗", cls: "closed" },
  unknown: { ar: "غير معروف", en: "Unknown", icon: "?", cls: "" },
} as const;

/** Small badge next to a symbol. Renders nothing while the screen is off. */
export function ShariaBadge({ symbol }: { symbol: string }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang;
  const { conf: c, get } = useSharia([symbol]);
  if (!c.enabled || !symbol) return null;
  const r = get(symbol);
  if (!r) return <span className="chip sharia" data-sharia="checking" aria-label={lang === "ar" ? "فحص شرعي: جاري" : "Sharia screen: checking"}>☪ …</span>;
  const L = LABEL[r.status];
  const tip = [`${lang === "ar" ? L.ar : L.en} · ${methodName(r.method, lang)}`, ...r.reasons.map((x) => reasonText(x, lang, r.method)),
    r.data_date ? (lang === "ar" ? `تاريخ البيانات المالية: ${r.data_date}` : `Financial data as of ${r.data_date}`) : "", disclaimer(lang)].filter(Boolean).join("\n");
  return <span className={`chip mkt sharia ${L.cls}`} data-sharia={r.status} title={tip} aria-label={tip}>
    <i />☪ {lang === "ar" ? L.ar : L.en}</span>;
}

/** True when this symbol should be hidden (the owner chose "hide non-compliant" and it failed the screen). */
export function useShariaHidden(symbols: string[]) {
  const { conf: c, get } = useSharia(symbols);
  return (s: string) => c.enabled && c.hide && get(s)?.status === "not_compliant";
}

/** Details for the verdict and the report: status, reasons, methodology, data date, purification, disclaimer. */
export function ShariaPanel({ symbol, compact = false }: { symbol: string; compact?: boolean }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang, ar = lang === "ar";
  const { conf: c, get } = useSharia([symbol]);
  if (!c.enabled || !symbol) return null;
  const r = get(symbol);
  if (compact) return (
    <span className="sharia-panel row" role="note" style={{ gap: 6, fontSize: 13, justifyContent: "center", flexBasis: "100%" }}
      aria-label={ar ? "الفحص الشرعي" : "Sharia screen"}>
      <ShariaBadge symbol={symbol} />
      {r && r.reasons.length > 0 && <span>{r.reasons.map((x) => reasonText(x, lang, r.method)).join(ar ? "؛ " : "; ")}</span>}
      <span className="muted" style={{ fontSize: 12 }}>{ar ? "تقدير آلي وليس فتوى" : "automated estimate, not a fatwa"}</span>
    </span>
  );
  return (
    <div className="sharia-panel stack" role="note" style={{ gap: 4, padding: compact ? 8 : 12, borderRadius: 14, background: "var(--cream)", textAlign: "start" }}
      aria-label={ar ? "الفحص الشرعي" : "Sharia screen"}>
      <div className="row" style={{ gap: 8 }}><b>{ar ? "الفحص الشرعي (اختياري)" : "Sharia screen (optional)"}</b><ShariaBadge symbol={symbol} /></div>
      {r && <>
        {r.reasons.length > 0 && <ul style={{ margin: 0, paddingInlineStart: 18, fontSize: 13, lineHeight: 1.7 }}>
          {r.reasons.map((x, i) => <li key={i}>{reasonText(x, lang, r.method)}</li>)}</ul>}
        <span className="muted" style={{ fontSize: 12 }}>
          {ar ? "المنهجية" : "Methodology"}: {methodName(r.method, lang)}
          {" · "}{ar ? "تاريخ البيانات المالية" : "Financial data as of"}: <span className="ltr">{r.data_date ?? (ar ? "غير متوفر" : "unavailable")}</span>
          {r.purification != null && <> · {ar ? "نسبة التطهير التقديرية للأرباح الموزعة" : "Estimated dividend purification"}: <span className="ltr">{(r.purification * 100).toFixed(2)}%</span></>}
        </span>
      </>}
      <span style={{ fontSize: 12, fontWeight: 700 }}>{disclaimer(lang)}</span>
    </div>
  );
}

/** Settings: off by default; methodology; hide non-compliant. */
export function ShariaSettings({ settings, onChange }: { settings: Settings; onChange: (s: Settings) => void }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang, ar = lang === "ar";
  const saved = settings.sharia ?? { enabled: false, method: "aaoifi", hide: false };
  const [local, setLocal] = useState<Partial<ShariaConf>>({});   // shown at once; the server's answer replaces it
  const s = { ...saved, ...local };
  const [err, setErr] = useState<string | null>(null);
  const save = (body: { sharia_enabled?: boolean; sharia_method?: string; sharia_hide?: boolean }) => {
    setLocal((l) => ({ ...l, ...(body.sharia_enabled !== undefined ? { enabled: body.sharia_enabled } : {}),
      ...(body.sharia_method !== undefined ? { method: body.sharia_method } : {}), ...(body.sharia_hide !== undefined ? { hide: body.sharia_hide } : {}) }));
    return api.put<Settings>("/api/settings", body).then((n) => { setErr(null); setLocal({}); onChange(n); })
      .catch(() => { setLocal({}); setErr(ar ? "ما انحفظ." : "Not saved."); });
  };
  return (
    <section className="card stack" aria-labelledby="s-sharia">
      <h2 id="s-sharia" style={{ fontSize: 22 }}>{ar ? "☪ الفحص الشرعي (اختياري)" : "☪ Sharia screening (optional)"}</h2>
      <p className="muted" style={{ margin: 0, lineHeight: 1.7 }}>{ar
        ? "لمن يرغب: يفحص كل شركة بقواعد معروفة (نشاط الشركة ونسب الديون والنقد ودخل الفوائد) ويعطي «متوافق» أو «غير متوافق» مع السبب أو «غير معروف» إذا البيانات ناقصة أو قديمة. مقفل افتراضياً، ولما يكون مقفل التطبيق يشتغل مثل ما هو."
        : "For those who want it: screens each company with published rules (its business, and its debt, cash and interest-income ratios) and shows Compliant, Not compliant with the reason, or Unknown when data is missing or stale. Off by default; when off, the app works exactly as before."}</p>
      <label className="toggle"><span>{ar ? "فعّل الفحص الشرعي" : "Turn on Sharia screening"}</span>
        <input type="checkbox" checked={s.enabled} onChange={(e) => void save({ sharia_enabled: e.target.checked })} /></label>
      {s.enabled && <>
        <label className="label" htmlFor="sharia-method">{ar ? "المنهجية" : "Methodology"}</label>
        <select id="sharia-method" className="field" value={s.method} onChange={(e) => void save({ sharia_method: e.target.value })}>
          {Object.keys(s.methods ?? METHOD_FALLBACK).map((m) => <option key={m} value={m}>{methodName(m, lang)}{m === "aaoifi" ? (ar ? " (الافتراضي)" : " (default)") : ""}</option>)}
        </select>
        <span className="muted" style={{ fontSize: 13, lineHeight: 1.7 }}>{s.method === "aaoifi"
          ? (ar ? "الديون بفائدة والنقد بفائدة كل واحد لا يتجاوز 30٪ من القيمة السوقية، ودخل غير مباح لا يتجاوز 5٪ من الإيرادات." : "Interest-bearing debt and interest-bearing cash each at most 30% of market value; non-permissible income at most 5% of revenue.")
          : s.method === "sp"
            ? (ar ? "الديون، والنقد والأوراق بفائدة، كل واحد أقل من 33٪ من متوسط القيمة السوقية لـ 36 شهر؛ الذمم المدينة أقل من 49٪؛ دخل غير مباح أقل من 5٪." : "Debt, and cash plus interest-bearing securities, each below 33% of the 36-month average market value; receivables below 49%; non-permissible income below 5%.")
            : (ar ? "الديون، والنقد والأوراق بفائدة، و(الذمم + النقد) كل واحد أقل من 33.33٪ من إجمالي الأصول؛ دخل غير مباح 5٪ كحد أقصى." : "Debt, cash plus interest-bearing securities, and receivables plus cash, each below 33.33% of total assets; non-permissible income at most 5%.")}</span>
        <label className="toggle"><span>{ar ? "أخفِ الأسهم غير المتوافقة من القوائم" : "Hide non-compliant stocks from lists"}</span>
          <input type="checkbox" checked={s.hide} onChange={(e) => void save({ sharia_hide: e.target.checked })} /></label>
      </>}
      <p style={{ margin: 0, fontSize: 13, fontWeight: 700, lineHeight: 1.7 }}>{disclaimer(lang)}</p>
      {err && <div className="warnstrip" role="alert">{err}</div>}
    </section>
  );
}
