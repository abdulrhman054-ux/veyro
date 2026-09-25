import { useEffect, useState } from "react";
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

export function Report({ sessionId }: { sessionId: string | null }) {
  const [s, setS] = useState<SessionFull | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    setS(null); setMissing(false);
    (async () => {
      let id = sessionId;
      if (!id) {
        const r = await api.get<{ sessions: { id: string; status: string }[] }>("/api/sessions");
        id = r.sessions.find((x) => x.status === "done")?.id ?? null;
      }
      if (!id) { setMissing(true); return; }
      setS(await api.get<SessionFull>(`/api/sessions/${id}`));
    })().catch(() => setMissing(true));
  }, [sessionId]);

  return <ReportBody s={s} missing={missing} />;
}

function ReportBody({ s, missing }: { s: SessionFull | null; missing: boolean }) {
  const { t, prefs } = usePrefs();
  const lang = prefs.lang;
  const vt = useVerdictText(s?.id ?? null, s?.verdict ?? null, lang);
  if (missing) return <div className="card" style={{ textAlign: "center", padding: 40 }}><h2>{t.noReport}</h2></div>;
  if (!s) return <div className="card muted" aria-busy="true">…</div>;

  const v = s.verdict;
  const r = RATING[s.rating ?? "REVIEW"] ?? RATING.REVIEW;
  const c = CONVICTION[v?.conviction ?? "unstated"] ?? CONVICTION.unstated;
  const demo = s.mode === "demo";

  return (
    <div className="stack" style={{ gap: 18 }}>
    <PageHeader host="Benny" title={<>{t.report} · <span className="pixel ltr">{s.ticker}</span></>} side={<StarButton ticker={s.ticker} />}
      sub={lang === "ar" ? "قرار ليو، وأرقام الفريق، وكلام كل واحد بالتفصيل. بيني يكتب المحضر." : "Leo's call, the team's figures and everyone's full notes. Benny keeps the minutes."}
      say={lang === "ar" ? "أكتب المحضر…" : "Writing the minutes…"} />
    <div className="report">
      <div className="left">
        <section className="card cream" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, textAlign: "center" }} aria-label={t.verdictTag}>
          <SpriteSvg name="Leo" px={5} frame="wave" talk />
          <span className="tagname" style={{ background: charColor("Leo"), fontSize: 18 }}>{t.verdictTag}</span>
          <div className={`verdict-word tone-${r.tone}`} style={{ fontSize: 56 }}>{lang === "ar" ? r.ar : r.en}</div>
          {vt?.reason && <div style={{ fontSize: 17, fontWeight: 600 }}>{vt.reason}</div>}
          {vt?.line && <p style={{ margin: "4px 0 0", lineHeight: 1.7 }}>{vt.line}</p>}
          <div className="row" style={{ justifyContent: "center", marginTop: 6 }}>
            <b>{t.conviction}</b>
            <span className="meter" aria-hidden="true">{[1, 2, 3].map((i) => <span key={i} className={i <= c.level ? "on" : ""} />)}</span>
            <span>{lang === "ar" ? c.ar : c.en}</span>
          </div>
          {demo && <span className="chip demo">{t.demo}</span>}
          {s.rating && <div style={{ marginTop: 6 }}><ProposeButton sessionId={s.id} ticker={s.ticker} rating={s.rating} demo={demo} /></div>}
        </section>

        <section className="card" style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 12 }}>
          <Fact label={t.colTicker} value={<span className="pixel ltr" style={{ fontSize: 22 }}>{s.ticker}</span>} />
          <Fact label={t.priceAtVerdict} value={<span className="pixel ltr" style={{ fontSize: 20 }}>{s.price_at_verdict ? fmtUsd(s.price_at_verdict, lang) : t.unavailable}</span>}
            note={s.price_source ? `${t.source}: ${s.price_source}` : undefined} />
          <Fact label={t.sessionTime} value={fmtDate(s.finished_at ?? s.created_at, lang)} />
          <Fact label={t.tradeDate} value={<span className="ltr">{s.trade_date}</span>} />
          {prefs.showCost && <Fact label={t.actualCost} value={<span className="pixel ltr">{demo ? t.free : s.cost_usd != null ? fmtUsd(s.cost_usd, lang, 3) : t.unknownPrice}</span>}
            note={s.provider ? `${s.provider} · ${s.quick_model} / ${s.deep_model}` : undefined} />}
        </section>

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

        <KeyFigures s={s} lang={lang} />
        <TeamAndMemory s={s} lang={lang} />
        <div className="warnstrip" role="note">{v?.disclaimer ?? t.disclaimer}</div>
      </div>

      <div className="right">
        {s.mode === "real" && s.status === "done" && <AskTeam sessionId={s.id} />}
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h1 style={{ fontSize: 26 }}>{t.whoSaid}</h1>
        </div>
        <div className="grid2">
          {s.turns.map((turn, i) => <TurnCard key={turn.id} turn={turn} demo={demo} defaultOpen={i === 0} />)}
        </div>
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

function TurnCard({ turn, demo, defaultOpen }: { turn: Turn; demo: boolean; defaultOpen: boolean }) {
  const { t, prefs } = usePrefs();
  const lang = prefs.lang;
  const ch = turn.character as CharKey;
  const [open, setOpen] = useState(defaultOpen);
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
            <span className="muted" style={{ fontWeight: 800, fontSize: 14 }}>{label} · {charRole(ch, lang)}</span>
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
