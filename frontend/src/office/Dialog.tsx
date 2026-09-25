import { useEffect, useRef, useState } from "react";
import { charColor } from "../art/Sprite";
import { VOICES, errorBonk, verdictJingle, voiceBlip } from "../audio";
import { CONVICTION, RATING, charName, fmtUsd, type CharKey, type Lang } from "../i18n";
import { usePrefs } from "../prefs";
import type { Verdict } from "../api";
import type { Line } from "./useSession";
import { useLineText } from "./lineText";
import { useVerdictText } from "./verdictText";
import { canReadAloud, readAloud } from "./readAloud";

/** Typewriter dialogue box. Click (or Enter/Space) finishes the line, click again advances. */
export function SpeechBox({ line, lang, onDone }: { line: Line; lang: Lang; onDone: () => void }) {
  const { motionOff, prefs } = usePrefs();
  const reading = prefs.readAloud && canReadAloud();
  const [spoken, setSpoken] = useState(!reading);   // with read-aloud on, a line waits until it has been heard
  useEffect(() => {
    setSpoken(!reading);
  }, [line.id, reading]);
  const fetched = useLineText(line.texts, line.turnId, lang, !line.demo && line.kind !== "error");
  // Never get stuck on an empty line: fall back to the other language, then to a short placeholder after a moment.
  const [gaveUp, setGaveUp] = useState(false);
  useEffect(() => { setGaveUp(false); const h = window.setTimeout(() => setGaveUp(true), 8000); return () => clearTimeout(h); }, [line.id]);
  const other = line.texts?.[lang === "ar" ? "en" : "ar"] || line.text || "";
  const text = fetched || (gaveUp ? other || (lang === "ar" ? "(السطر غير متوفر، التفاصيل في التقرير)" : "(line unavailable; details are in the report)") : "");
  const [n, setN] = useState(motionOff ? text.length : 0);
  const done = text.length > 0 && n >= text.length;
  const doneRef = useRef(onDone); doneRef.current = onDone;

  useEffect(() => {
    setN(motionOff ? text.length : 0);
  }, [line.id, text, motionOff]);
  useEffect(() => { if (line.kind === "error") errorBonk(); }, [line.id, line.kind]);

  useEffect(() => {
    if (!reading || !text) return;
    return readAloud(`${charName(line.character, lang)}: ${text}`, lang, () => setSpoken(true));
  }, [reading, text, line.id, line.character, lang]);

  useEffect(() => {
    if (!text) return;
    if (done) {
      if (!spoken) return;   // still being read aloud
      const hold = reading ? 900 : Math.min(15000, 2000 + text.length * 40);   // time to read it, longer lines stay longer
      const h = window.setTimeout(() => doneRef.current(), line.kind === "error" ? hold + 3000 : hold);
      return () => clearTimeout(h);
    }
    const h = window.setTimeout(() => {
      setN((v) => {
        const nv = Math.min(text.length, v + 1);
        voiceBlip(line.character, text[nv - 1], nv);
        return nv;
      });
    }, VOICES[line.character]?.msPerChar ?? 30);
    return () => clearTimeout(h);
  }, [n, done, text, line.kind, line.character, spoken, reading]);

  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => { const el = box.current; if (el) el.scrollTop = el.scrollHeight; }, [n]);   // long lines: follow the typing
  const advance = () => (done ? onDone() : setN(text.length));
  return (
    <button className={`dlg${line.kind === "error" ? " err" : ""}`} dir={lang === "ar" ? "rtl" : "ltr"} onClick={advance}
      aria-label={`${charName(line.character, lang)}: ${text}`}>
      <span className="tag" style={{ background: charColor(line.character) }}>{charName(line.character, lang)}</span>
      <span className="dtext scroll" ref={box} aria-hidden="true" style={{ display: "block" }}>{text ? text.slice(0, n) : "…"}{!done && <span className="caret" />}</span>
      {done && <span className="next" aria-hidden="true" />}
      {/* Screen readers hear each full line once, as it starts. */}
      <span className="sr-only" aria-live="polite">{text ? `${charName(line.character, lang)}: ${text}` : ""}</span>
    </button>
  );
}

const WORKING: Partial<Record<CharKey, { ar: string; en: string }>> = {
  Ollie: { ar: "يقرأ الشارت والمؤشرات", en: "is reading the chart and indicators" },
  Buzz: { ar: "يسمع وش يقول الناس", en: "is listening to what people say" },
  Pip: { ar: "يقرأ أخبار السهم", en: "is reading the stock's news" },
  Benny: { ar: "يحسب القوائم المالية", en: "is crunching the financial statements" },
  Bolt: { ar: "يجهّز حجة الصعود", en: "is building the bull case" },
  Bruno: { ar: "يجهّز حجة الهبوط", en: "is building the bear case" },
  Tank: { ar: "يراجع المخاطر مع فريقه", en: "is reviewing the risks with his team" },
  Leo: { ar: "يوزن كلام الفريق", en: "is weighing the whole team" },
  Albie: { ar: "طاير يجيب أخبار العالم", en: "is flying in with world news" },
};

/** Between lines: who is working right now, so a long model call never looks like a frozen office. */
export function WaitBox({ lang, agents, since, stopping, loaded }: { lang: Lang; agents: Record<CharKey, string>; since: number | null; stopping: boolean; loaded: boolean }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const h = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(h); }, []);
  const busy = (Object.keys(agents) as CharKey[]).filter((c) => agents[c] === "thinking");
  const secs = since ? Math.max(0, Math.round((now - since) / 1000)) : 0;
  const text = stopping
    ? (lang === "ar" ? "نوقف الجلسة… لحظة." : "Stopping the session… one moment.")
    : !loaded ? (lang === "ar" ? "الفريق يجهّز الطاولة…" : "The team is getting the table ready…")
    : busy.length ? busy.map((c) => `${charName(c, lang)} ${WORKING[c]?.[lang] ?? (lang === "ar" ? "يشتغل" : "is working")}`).join(lang === "ar" ? "، و" : ", and ") + "…"
    : (lang === "ar" ? "الفريق يرتّب الخطوة الجاية…" : "The team is lining up the next step…");
  return (
    <div className="dlg wait" dir={lang === "ar" ? "rtl" : "ltr"} role="status" aria-live="polite" style={{ cursor: "default" }}>
      <span className="tag" style={{ background: busy[0] ? charColor(busy[0]) : "#3E9A68" }}>{busy[0] ? charName(busy[0], lang) : (lang === "ar" ? "الفريق" : "The team")}</span>
      <span className="dtext" style={{ display: "block" }}>{text}<span className="dots3" aria-hidden="true"><i /><i /><i /></span></span>
      {!stopping && secs >= 20 && <span className="muted" style={{ fontSize: 14 }}>{lang === "ar"
        ? `صار لهم ${secs} ثانية. التحليل الحقيقي ياخذ دقائق، والكلام يطلع أول ما يخلصون.`
        : `${secs}s so far. Real analysis takes minutes; each line appears as soon as it's ready.`}</span>}
    </div>
  );
}

/** A session that ended without a verdict (stopped, failed, or the connection was lost). */
export function EndedBox({ lang, status }: { lang: Lang; status: string | null }) {
  const text = status === "cancelled"
    ? (lang === "ar" ? "وقّفنا الجلسة. تقدر تبدأ جلسة جديدة متى ما حبيت، وإذا كانت حقيقية تقدر تكملها من «السجل»." : "Session stopped. Start a new one any time; a real session can be resumed from History.")
    : status === "lost"
    ? (lang === "ar" ? "انقطع الاتصال بالجلسة (غالباً أُعيد تشغيل التطبيق). المحفوظ منها تلقاه في «السجل»." : "The connection to this session was lost (the app probably restarted). What was saved is in History.")
    : (lang === "ar" ? "انتهت الجلسة بدون قرار. التفاصيل في «السجل»، وتقدر تكملها من هناك." : "The session ended without a decision. Details are in History, and you can resume it from there.");
  return (
    <div className="dlg" dir={lang === "ar" ? "rtl" : "ltr"} role="status" style={{ cursor: "default" }}>
      <span className="tag" style={{ background: charColor("Leo") }}>{charName("Leo", lang)}</span>
      <span className="dtext" style={{ display: "block" }}>{text}</span>
    </div>
  );
}

export function IdleBox({ text, lang }: { text: string; lang: Lang }) {
  const { t } = usePrefs();
  return (
    <div className="dlg" dir={lang === "ar" ? "rtl" : "ltr"} style={{ cursor: "default" }}>
      <span className="tag" style={{ background: "#3E9A68" }}>{t.brand}</span>
      <span className="dtext" style={{ display: "block" }}>{text}</span>
      <span className="next" aria-hidden="true" />
    </div>
  );
}

const CONF = ["#F2A43A", "#6CC38E", "#E0453A", "#3F7FE0", "#F7CE4F", "#8A5CC7", "#FFFFFF"];

/** Tadawul (.SR) prices are riyals; everything else here is priced in dollars. */
export function priceText(v: number, ticker: string | null | undefined, lang: Lang) {
  if (ticker?.toUpperCase().endsWith(".SR")) {
    const n = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v);
    return lang === "ar" ? `${n} ريال` : `SAR ${n}`;
  }
  return fmtUsd(v, lang);
}

export function VerdictBox({ v, lang, onOpenReport, demo, sessionId, extra, ticker: sessionTicker }: { v: Verdict; lang: Lang; onOpenReport: () => void; demo: boolean; sessionId: string | null; extra?: React.ReactNode; ticker?: string | null }) {
  const { t, motionOff } = usePrefs();
  const r = RATING[v.rating] ?? RATING.REVIEW;
  const c = CONVICTION[v.conviction] ?? CONVICTION.unstated;
  useEffect(() => { verdictJingle(r.tone); }, [r.tone]);
  const { prefs } = usePrefs();
  const vtext = useVerdictText(sessionId, v, lang);
  useEffect(() => {
    if (!prefs.readAloud || !vtext) return;
    return readAloud(`${lang === "ar" ? r.ar : r.en}. ${vtext.reason ?? ""}`, lang);
  }, [prefs.readAloud, vtext, lang, r.ar, r.en]);
  const price = v.price?.price;
  const reason = useVerdictText(sessionId, v, lang)?.reason ?? null;
  return (
    <div className="dlg verdict-box" dir={lang === "ar" ? "rtl" : "ltr"} role="region" aria-label={t.verdictTag}>
      {!motionOff && r.tone !== "none" && CONF.map((col, i) => (
        <span key={i} className="conf" style={{ left: 60 + i * 105, background: col, animationDelay: `-${(i * 0.37) % 2}s` }} />
      ))}
      <span className="tag" style={{ background: charColor("Leo") }}>{t.verdictTag}</span>
      <div className={`verdict-word tone-${r.tone}`}>{lang === "ar" ? r.ar : r.en}{demo ? ` · ${t.demo}` : ""}</div>
      {reason && <div style={{ fontSize: 18, fontWeight: 600, marginTop: 2 }}>{reason}</div>}
      <div className="row" style={{ justifyContent: "center", marginTop: 10, gap: 14 }}>
        <span style={{ fontWeight: 800 }}>{t.conviction}:</span>
        <span className="meter" aria-hidden="true">{[1, 2, 3].map((i) => <span key={i} className={i <= c.level ? "on" : ""} />)}</span>
        <span style={{ fontWeight: 700 }}>{lang === "ar" ? c.ar : c.en}</span>
        <span style={{ fontWeight: 800 }}>· {t.priceAtVerdict}:</span>
        <span className="pixel ltr">{price ? priceText(price, sessionTicker, lang) : t.unavailable}</span>
      </div>
      <div className="row" style={{ justifyContent: "center", marginTop: 10 }}>
        <button className="primary green btn" style={{ height: 42, fontSize: 16 }} onClick={onOpenReport}>{t.openReport}</button>
        {extra}
        <span style={{ fontSize: 13, fontWeight: 700, color: "#7A6147" }}>{t.disclaimer}</span>
      </div>
    </div>
  );
}

export const leoName = (l: Lang) => charName("Leo" as CharKey, l);
