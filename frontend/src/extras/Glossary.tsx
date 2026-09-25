import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { usePrefs } from "../prefs";
import { CATS, TERMS, TERM_RE, idForMatch, termById, type Cat } from "./glossary";

/** A finance word in the text: tap it for a one-line plain explanation. */
function TermChip({ id, children }: { id: string; children: ReactNode }) {
  const { prefs } = usePrefs();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  const t = termById(id)!;
  useEffect(() => {
    if (!open) return;
    const f = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", f); document.addEventListener("keydown", k);
    return () => { document.removeEventListener("mousedown", f); document.removeEventListener("keydown", k); };
  }, [open]);
  const ar = prefs.lang === "ar";
  return (
    <span className="term" ref={box}>
      <button type="button" className="term-btn" aria-expanded={open} onClick={(e) => { e.stopPropagation(); setOpen(!open); }}>{children}</button>
      {open && <span className="term-pop" role="tooltip" dir={ar ? "rtl" : "ltr"}><b>{ar ? t.ar : t.en}</b><br />{ar ? t.def_ar : t.def_en}</span>}
    </span>
  );
}

/** Text with its finance terms linked (first mention of each, at most 8 per block). */
export function Glossed({ text }: { text: string }) {
  const parts = useMemo(() => {
    const out: ReactNode[] = [];
    const seen = new Set<string>();
    let last = 0, k = 0;
    TERM_RE.lastIndex = 0;
    for (let m = TERM_RE.exec(text); m; m = TERM_RE.exec(text)) {
      const id = idForMatch(m[0]);
      if (!id || seen.has(id) || seen.size >= 8) continue;
      seen.add(id);
      if (m.index > last) out.push(text.slice(last, m.index));
      out.push(<TermChip key={k++} id={id}>{m[0]}</TermChip>);
      last = m.index + m[0].length;
    }
    if (last < text.length) out.push(text.slice(last));
    return out;
  }, [text]);
  return <>{parts}</>;
}

/** The whole glossary, searchable (header 📖 button). */
export function GlossaryModal({ onClose }: { onClose: () => void }) {
  const { prefs, t } = usePrefs();
  const ar = prefs.lang === "ar";
  const [q, setQ] = useState("");
  const [cat, setCat] = useState<Cat | "all">("all");
  const list = TERMS.filter((x) => (cat === "all" || x.cat === cat)
    && (!q.trim() || [x.ar, x.en, x.def_ar, x.def_en, ...x.match].some((s) => s.toLowerCase().includes(q.trim().toLowerCase()))))
    .sort((a, b) => (ar ? a.ar.localeCompare(b.ar, "ar") : a.en.localeCompare(b.en)));
  return (
    <div className="modal-bg" role="dialog" aria-modal="true" aria-label={ar ? "قاموس المصطلحات" : "Glossary"} onClick={onClose}>
      <div className="modal stack" style={{ gap: 12, maxWidth: 720 }} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ fontSize: 24, margin: 0 }}>📖 {ar ? "قاموس المصطلحات المالية" : "Finance glossary"}</h2>
        <p className="muted" style={{ margin: 0 }}>{ar ? "أي كلمة تحتها خط منقّط في التقارير تقدر تضغط عليها وتطلع شرحها." : "Any dotted-underlined word in the reports can be tapped for its meaning."}</p>
        <input className="field" autoFocus placeholder={ar ? `ابحث في ${TERMS.length} مصطلح…` : `Search ${TERMS.length} terms…`} value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="segbtns" role="group" aria-label={ar ? "الفئات" : "Categories"} style={{ flexWrap: "wrap" }}>
          <button aria-pressed={cat === "all"} onClick={() => setCat("all")}>{ar ? "الكل" : "All"}</button>
          {CATS.map((c) => <button key={c.id} aria-pressed={cat === c.id} onClick={() => setCat(c.id)}>{ar ? c.ar : c.en}</button>)}
        </div>
        <div className="stack" style={{ gap: 8 }}>
          {list.map((x) => (
            <div key={x.id} className="logitem"><b>{ar ? x.ar : x.en}</b>{ar && <span className="muted ltr" style={{ fontSize: 12 }}> · {x.en}</span>}
              <div style={{ lineHeight: 1.8 }}>{ar ? x.def_ar : x.def_en}</div></div>
          ))}
          {!list.length && <span className="muted">{ar ? "ما لقينا المصطلح." : "No matching term."}</span>}
        </div>
        <div className="row" style={{ justifyContent: "flex-end" }}><button className="primary btn" onClick={onClose}>{t.close}</button></div>
      </div>
    </div>
  );
}
