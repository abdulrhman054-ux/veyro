import { useEffect, useRef, useState } from "react";
import { api, ApiError, type SessionFull, type Turn } from "../api";
import { SpriteSvg, charColor } from "../art/Sprite";
import { Markdown } from "../components/Markdown";
import { CONVICTION, NODE_LABEL, RATING, charName, charRole, fmtDate, fmtUsd, type CharKey } from "../i18n";
import { usePrefs } from "../prefs";
import { useVerdictText } from "../office/verdictText";
import { ProposeButton } from "../exec/OrderTicket";
import { KeyFigures, TeamAndMemory } from "./FrameworkPanels";
import { PageHeader } from "../components/PageHeader";
import { AskTeam, StarButton } from "../assistant/Assistant";
import { BudgetPlan } from "../office/BudgetPlan";

export function Report({ sessionId, active = true }: { sessionId: string | null; active?: boolean }) {
  const [s, setS] = useState<SessionFull | null>(null);
  const [missing, setMissing] = useState(false);
  const loaded = useRef<{ id: string; status: string } | null>(null);

  // The screen stays mounted between visits (open cards and scroll are kept). On each visit it only
  // reloads when a different session is asked for, or the one shown was still running.
  useEffect(() => {
    if (!active) return;
    let alive = true;
    (async () => {
      let id = sessionId;
      if (!id) {
        const r = await api.get<{ sessions: { id: string; status: string }[] }>("/api/sessions?light=1");
        id = r.sessions.find((x) => x.status === "done")?.id ?? null;
      }
      if (!id) { if (alive) { setS(null); setMissing(true); } return; }
      if (loaded.current?.id === id && loaded.current.status !== "running") return;
      if (loaded.current?.id !== id && alive) { setS(null); window.scrollTo(0, 0); }
      const full = await api.get<SessionFull>(`/api/sessions/${id}`);
      if (!alive) return;
      loaded.current = { id, status: full.status };
      setMissing(false); setS(full);
    })().catch(() => alive && setMissing(true));
    return () => { alive = false; };
  }, [sessionId, active]);

  return <ReportBody s={s} missing={missing} />;
}

const PHASES: { id: string; nodes: string[]; ar: string; en: string; subAr: string; subEn: string }[] = [
  { id: "analysts", nodes: ["Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst"], ar: "المحللون", en: "The analysts",
    subAr: "كل محلل يدرس السهم من زاويته: الشارت، المزاج العام، الأخبار، والقوائم المالية.", subEn: "Each analyst studies the stock from one angle: chart, crowd mood, news and financials." },
  { id: "debate", nodes: ["Bull Researcher", "Bear Researcher"], ar: "النقاش: الصعود ضد الهبوط", en: "The debate: bull vs bear",
    subAr: "بولت يدافع عن الصعود وبرونو عن الهبوط، جولة بجولة.", subEn: "Bolt argues the upside and Bruno the downside, round by round." },
  { id: "plan", nodes: ["Research Manager", "Trader"], ar: "خطة الاستثمار ومقترح الصفقة", en: "Investment plan and trade proposal",
    subAr: "ليو يحكم بين الطرفين ويحوّلها لخطة وصفقة مقترحة.", subEn: "Leo judges the debate and turns it into a plan and a proposed trade." },
  { id: "risk", nodes: ["Risk Team"], ar: "فريق المخاطر", en: "The risk team",
    subAr: "تانك يلخّص نقاش المخاطر: الجريء والحذر والمحايد.", subEn: "Tank sums up the risk debate: aggressive, conservative and neutral." },
  { id: "world", nodes: ["Global Link"], ar: "الأخبار العالمية", en: "World news link",
    subAr: "ألبي يربط أخبار العالم بحركة السهم.", subEn: "Albie links world headlines to the stock's move." },
  { id: "decision", nodes: ["Portfolio Manager"], ar: "القرار النهائي", en: "The final decision",
    subAr: "مدير المحفظة (ليو) يعلن القرار.", subEn: "The Portfolio Manager (Leo) announces the call." },
];

function ReportBody({ s, missing }: { s: SessionFull | null; missing: boolean }) {
  const { t, prefs } = usePrefs();
  const lang = prefs.lang;
  const ar = lang === "ar";
  const vt = useVerdictText(s?.id ?? null, s?.verdict ?? null, lang);
  const [openAll, setOpenAll] = useState<{ open: boolean; n: number }>({ open: false, n: 0 });
  if (missing) return <div className="card" style={{ textAlign: "center", padding: 40 }}><h2>{t.noReport}</h2></div>;
  if (!s) return <div className="card muted" aria-busy="true">…</div>;

  const v = s.verdict;
  const r = RATING[s.rating ?? "REVIEW"] ?? RATING.REVIEW;
  const c = CONVICTION[v?.conviction ?? "unstated"] ?? CONVICTION.unstated;
  const demo = s.mode === "demo";
  const budget = (s.config as { budget?: { amount: number; currency: string } | null } | null)?.budget ?? null;
  const known = new Set(PHASES.flatMap((p) => p.nodes));
  const phases = [...PHASES, { id: "other", nodes: [...new Set(s.turns.map((x) => x.node).filter((n) => !known.has(n)))], ar: "أخرى", en: "Other", subAr: "", subEn: "" }]
    .map((p) => ({ ...p, turns: s.turns.filter((x) => p.nodes.includes(x.node)) })).filter((p) => p.turns.length);
  const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div className="stack" style={{ gap: 18 }}>
    <PageHeader host="Benny" title={<>{t.report} · <span className="pixel ltr">{s.ticker}</span></>} side={<StarButton ticker={s.ticker} />}
      sub={ar ? "قرار ليو أولاً، بعدين مراحل النقاش بالترتيب، والأرقام والمصادر. بيني يكتب المحضر." : "Leo's call first, then each stage of the discussion in order, then figures and sources. Benny keeps the minutes."}
      say={ar ? "أكتب المحضر…" : "Writing the minutes…"} />

    <nav className="report-nav" aria-label={ar ? "أقسام التقرير" : "Report sections"}>
      <button className="chip mkt btn" onClick={() => jump("r-summary")}>{ar ? "الخلاصة" : "Summary"}</button>
      {phases.map((p, i) => <button key={p.id} className="chip mkt btn" onClick={() => jump(`r-${p.id}`)}><b className="pixel">{i + 1}</b> {ar ? p.ar : p.en}</button>)}
      <button className="chip mkt btn" onClick={() => jump("r-figures")}>{ar ? "الأرقام والإعداد" : "Figures & setup"}</button>
    </nav>

    <section id="r-summary" className="card cream report-summary" aria-label={t.verdictTag}>
      <div className="stack" style={{ alignItems: "center", gap: 6, textAlign: "center", minWidth: 200 }}>
        <SpriteSvg name="Leo" px={4} frame="wave" talk />
        <span className="tagname" style={{ background: charColor("Leo"), fontSize: 16 }}>{t.verdictTag}</span>
      </div>
      <div className="stack" style={{ gap: 6, flex: 1, minWidth: 240 }}>
        <div className={`verdict-word tone-${r.tone}`} style={{ fontSize: 48 }}>{ar ? r.ar : r.en}{demo && <span className="chip demo" style={{ marginInlineStart: 10, verticalAlign: "middle" }}>{t.demo}</span>}</div>
        {vt?.reason && <div style={{ fontSize: 18, fontWeight: 700 }}>{vt.reason}</div>}
        {vt?.line && <p style={{ margin: 0, lineHeight: 1.8 }}>{vt.line}</p>}
        <div className="row" style={{ gap: 8 }}>
          <b>{t.conviction}</b>
          <span className="meter" aria-hidden="true">{[1, 2, 3].map((i) => <span key={i} className={i <= c.level ? "on" : ""} />)}</span>
          <span>{ar ? c.ar : c.en}</span>
        </div>
        <div className="facts-row">
          <Fact label={t.priceAtVerdict} value={<span className="pixel ltr">{s.price_at_verdict ? fmtUsd(s.price_at_verdict, lang) : t.unavailable}</span>}
            note={s.price_source ? `${t.source}: ${s.price_source}` : undefined} />
          <Fact label={t.tradeDate} value={<span className="ltr">{s.trade_date}</span>} />
          <Fact label={t.sessionTime} value={fmtDate(s.finished_at ?? s.created_at, lang)} />
          {prefs.showCost && <Fact label={t.actualCost} value={<span className="pixel ltr">{demo ? t.free : s.cost_usd != null ? fmtUsd(s.cost_usd, lang, 3) : t.unknownPrice}</span>}
            note={s.provider ? `${s.provider} · ${s.quick_model} / ${s.deep_model}` : undefined} />}
        </div>
        <div className="row" style={{ gap: 10 }}>
          {s.rating && <ProposeButton sessionId={s.id} ticker={s.ticker} rating={s.rating} demo={demo} />}
          <span className="muted" style={{ fontSize: 13 }}>{v?.disclaimer ?? t.disclaimer}</span>
        </div>
      </div>
    </section>

    {budget && s.mode === "real" && s.status === "done" && <BudgetPlan url={`/api/sessions/${s.id}/allocation`} budget={budget} />}
    {s.mode === "real" && s.status === "done" && <AskTeam sessionId={s.id} />}

    <div className="report">
      <div className="right">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h1 style={{ fontSize: 26 }}>{t.whoSaid}</h1>
          <span className="row" style={{ gap: 6 }}>
            <button className="ghost btn" onClick={() => setOpenAll((o) => ({ open: true, n: o.n + 1 }))}>{ar ? "افتح الكل" : "Expand all"}</button>
            <button className="ghost btn" onClick={() => setOpenAll((o) => ({ open: false, n: o.n + 1 }))}>{ar ? "طوّ الكل" : "Collapse all"}</button>
            <button className="primary btn" onClick={() => {
              // Everything opened, then the system print dialog: choose "Save as PDF" (Arabic prints right-to-left as shown).
              setOpenAll((o) => ({ open: true, n: o.n + 1 }));
              // Arabic details are translated when opened: wait for them (up to a minute) so the PDF is complete.
              const t0 = Date.now();
              const waitThenPrint = () => {
                const pending = [...document.querySelectorAll(".detail")].some((d) => d.textContent?.includes(t.translating));
                if (pending && Date.now() - t0 < 60000) window.setTimeout(waitThenPrint, 500); else window.print();
              };
              window.setTimeout(waitThenPrint, 800);
            }}>{ar ? "🖨 حفظ PDF / طباعة" : "🖨 Save PDF / print"}</button>
          </span>
        </div>
        {phases.map((p, i) => (
          <section key={p.id} id={`r-${p.id}`} className="phase stack" style={{ gap: 10 }}>
            <div className="phase-h">
              <span className="phase-n pixel">{i + 1}</span>
              <div className="stack" style={{ gap: 0 }}>
                <b style={{ fontSize: 19 }}>{ar ? p.ar : p.en}</b>
                {(ar ? p.subAr : p.subEn) && <span className="muted" style={{ fontSize: 14 }}>{ar ? p.subAr : p.subEn}</span>}
              </div>
            </div>
            <div className="stack" style={{ gap: 12 }}>
              {p.turns.map((turn, k) => <TurnCard key={turn.id} turn={turn} demo={demo} round={p.id === "debate" ? Math.floor(k / 2) + 1 : null}
                defaultOpen={p.id === "decision"} openAll={openAll} />)}
            </div>
          </section>
        ))}
      </div>
      <div className="left" id="r-figures">
        <KeyFigures s={s} lang={lang} />
        <TeamAndMemory s={s} lang={lang} />
        <section className="card stack" style={{ gap: 8 }}>
          <h2 style={{ fontSize: 19 }}>{t.dataSources}</h2>
          {v?.sources?.length ? (
            <ul style={{ margin: 0, paddingInlineStart: 20 }}>
              {v.sources.map((src) => (
                <li key={src.tool}><span className="pixel ltr">{src.tool}</span> · <span className="ltr">{src.vendor}</span>
                  {!src.ok && <b className="neg"> · {t.unavailable}</b>}</li>
              ))}
            </ul>
          ) : <p className="muted" style={{ margin: 0 }}>{demo ? t.welcomeDemo : t.noSources}</p>}
          {!demo && <p className="muted" style={{ margin: 0, fontSize: 14 }}>{t.sentimentNote}</p>}
          <p className="muted" style={{ margin: 0, fontSize: 14 }}>{t.source}: Yahoo Finance (yfinance) · TradingAgents v0.5.1</p>
        </section>
        <div className="warnstrip" role="note">{v?.disclaimer ?? t.disclaimer}</div>
      </div>
    </div>
    </div>
  );
}

function Fact({ label, value, note }: { label: string; value: React.ReactNode; note?: string }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div style={{ fontWeight: 700 }}>{value}</div>
      {note && <div className="muted" style={{ fontSize: 12 }}>{note}</div>}
    </div>
  );
}

function TurnCard({ turn, demo, defaultOpen, openAll, round }: { turn: Turn; demo: boolean; defaultOpen: boolean; openAll?: { open: boolean; n: number }; round?: number | null }) {
  const { t, prefs } = usePrefs();
  const lang = prefs.lang;
  const ch = turn.character as CharKey;
  const [open, setOpen] = useState(defaultOpen);
  useEffect(() => { if (openAll && openAll.n > 0) setOpen(openAll.open); }, [openAll]);
  const [voice, setVoice] = useState<string | null>(lang === "ar" ? turn.voice_ar : turn.voice_en);
  const [detailAr, setDetailAr] = useState<string | null>(turn.detail_ar);
  const [busy, setBusy] = useState<"voice" | "detail" | null>(null);
  const [fail, setFail] = useState(false);
  const [showOrig, setShowOrig] = useState(false);

  // Keep each language pure: fetch the line in the current language if this session was run in the other one.
  useEffect(() => {
    const have = lang === "ar" ? turn.voice_ar : turn.voice_en;
    setVoice(have);
    if (!have && !demo) {
      setBusy("voice");
      api.post<Record<string, string>>(`/api/turns/${turn.id}/translate`, { what: lang === "ar" ? "voice_ar" : "voice_en" })
        .then((r) => setVoice(Object.values(r)[0])).catch(() => setFail(true)).finally(() => setBusy(null));
    }
  }, [lang, turn, demo]);

  useEffect(() => {
    if (open && lang === "ar" && !detailAr && !demo && busy !== "detail") {
      setBusy("detail"); setFail(false);
      api.post<{ detail_ar: string }>(`/api/turns/${turn.id}/translate`, { what: "detail_ar" })
        .then((r) => setDetailAr(r.detail_ar)).catch((e) => { setFail(true); if (e instanceof ApiError) console.info("translate:", e.code); })
        .finally(() => setBusy(null));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, lang]);

  const label = NODE_LABEL[turn.node]?.[lang] ?? turn.node;
  return (
    <article className="card" style={{ padding: 18, display: "flex", flexDirection: "column", gap: 10 }}>
      <div className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
        <div className="portrait"><SpriteSvg name={ch} px={3} /></div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
          <div className="row" style={{ gap: 8 }}>
            <span className="tagname" style={{ background: charColor(ch) }}>{charName(ch, lang)}</span>
            <span className="muted" style={{ fontWeight: 800, fontSize: 14 }}>{label}{round ? (lang === "ar" ? ` · الجولة ${round}` : ` · round ${round}`) : ""} · {charRole(ch, lang)}</span>
          </div>
          <div style={{ lineHeight: 1.7 }}>{voice ?? (busy === "voice" ? t.translating : fail ? t.translateFail : "")}</div>
        </div>
      </div>
      <button className="ghost btn" style={{ alignSelf: "flex-start" }} aria-expanded={open} onClick={() => setOpen(!open)}>{open ? t.hideDetails : t.details}</button>
      {open && (
        <div className="detail">
          <div style={{ fontWeight: 800, marginBottom: 4 }}>{t.fullAnalysis}</div>
          {lang === "en" || demo ? <Markdown text={turn.detail_en} dir="ltr" />
            : detailAr ? <Markdown text={detailAr} dir="rtl" />
            : <p className="muted">{busy === "detail" ? t.translating : fail ? t.translateFail : ""}</p>}
          {lang === "ar" && !demo && (
            <>
              <button className="ghost btn" style={{ marginTop: 8, height: 34, fontSize: 13 }} aria-expanded={showOrig} onClick={() => setShowOrig(!showOrig)}>{t.originalText}</button>
              {showOrig && <div style={{ marginTop: 8 }}><Markdown text={turn.detail_en} dir="ltr" /></div>}
            </>
          )}
        </div>
      )}
    </article>
  );
}
