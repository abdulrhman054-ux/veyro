import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { usePrefs } from "../prefs";

export type SearchHit = { symbol: string; name: string | null; exchange: string | null; type: string | null; source: string };

/** Same rule as the backend (letters/digits first, then . - = ^), e.g. NVDA, 2222.SR, BTC-USD. */
export const TICKER = /^[A-Z0-9][A-Z0-9.\-=^]{0,14}$/;

const TYPE_LABEL: Record<string, { ar: string; en: string }> = {
  EQUITY: { ar: "سهم", en: "Stock" }, ETF: { ar: "صندوق", en: "ETF" }, INDEX: { ar: "مؤشر", en: "Index" },
  CRYPTOCURRENCY: { ar: "عملة رقمية", en: "Crypto" },
};

/** A ticker box that also finds symbols by company name (Arabic or English). */
export function TickerSearch({ value, onChange, onPick, onEnter, disabled, placeholder, width = 150, clearOnPick = false, invalid }: {
  value: string; onChange: (v: string) => void; onPick: (symbol: string) => void; onEnter?: () => void;
  disabled?: boolean; placeholder?: string; width?: number; clearOnPick?: boolean; invalid?: boolean;
}) {
  const { prefs } = usePrefs();
  const lang = prefs.lang;
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [loading, setLoading] = useState(false);
  const typed = useRef(false);   // only search after the user types, not when the value is set from outside
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const q = value.trim();
    if (!typed.current || q.length < 2) { setHits([]); setLoading(false); return; }
    let alive = true;
    setLoading(true);
    const h = window.setTimeout(() => {
      api.get<{ results: SearchHit[] }>(`/api/market/search?q=${encodeURIComponent(q)}`)
        .then((r) => { if (alive) { setHits(r.results); setActive(-1); setOpen(true); } })
        .catch(() => { if (alive) setHits([]); })
        .finally(() => { if (alive) setLoading(false); });
    }, 280);
    return () => { alive = false; clearTimeout(h); };
  }, [value]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const pick = (h: SearchHit) => {
    typed.current = false;
    setOpen(false); setHits([]);
    onPick(h.symbol);
    if (clearOnPick) onChange("");
  };

  const showList = open && !disabled && value.trim().length >= 2;
  return (
    <div className="tsearch" ref={box} style={{ width }}>
      <input className="field pixel ticker ltr" value={value} maxLength={40} disabled={disabled} aria-invalid={invalid}
        placeholder={placeholder ?? (lang === "ar" ? "رمز أو اسم الشركة" : "Symbol or company")}
        role="combobox" aria-expanded={showList} aria-autocomplete="list" aria-controls="tsearch-list"
        onChange={(e) => { typed.current = true; const v = e.target.value; onChange(/[؀-ۿ]/.test(v) ? v : v.toUpperCase()); }}
        onFocus={() => hits.length && setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && hits.length) { e.preventDefault(); setOpen(true); setActive((a) => (a + 1) % hits.length); }
          else if (e.key === "ArrowUp" && hits.length) { e.preventDefault(); setActive((a) => (a <= 0 ? hits.length - 1 : a - 1)); }
          else if (e.key === "Escape") setOpen(false);
          else if (e.key === "Enter") {
            if (showList && active >= 0 && hits[active]) { e.preventDefault(); pick(hits[active]); return; }
            // A name typed (e.g. «أرامكو» or "apple") rather than a symbol: take the best match. "APPLE" looks like a
            // symbol, so a typed word only counts as one if the search results contain that exact symbol.
            const typedSym = value.trim().toUpperCase();
            if (hits[0] && (!TICKER.test(typedSym) || !hits.some((h) => h.symbol === typedSym))) { e.preventDefault(); pick(hits[0]); return; }
            setOpen(false); onEnter?.();
          }
        }} />
      {showList && (hits.length > 0 || loading) && (
        <ul className="tsearch-list" id="tsearch-list" role="listbox">
          {loading && hits.length === 0 && <li className="muted">{lang === "ar" ? "نبحث…" : "Searching…"}</li>}
          {hits.map((h, i) => (
            <li key={h.symbol} role="option" aria-selected={i === active} className={i === active ? "on" : ""}
              onMouseDown={(e) => { e.preventDefault(); pick(h); }} onMouseEnter={() => setActive(i)}>
              <b className="pixel ltr">{h.symbol}</b>
              <span className="nm">{h.name ?? ""}</span>
              <span className="muted tp">{[h.type ? TYPE_LABEL[h.type]?.[lang] ?? h.type : null, h.exchange].filter(Boolean).join(" · ")}</span>
            </li>
          ))}
        </ul>
      )}
      {showList && !loading && hits.length === 0 && !TICKER.test(value.trim().toUpperCase()) && (
        <ul className="tsearch-list" role="listbox"><li className="muted">{lang === "ar" ? "ما لقينا نتائج. جرّب اسم ثاني أو الرمز." : "No matches. Try another name or the symbol."}</li></ul>
      )}
    </div>
  );
}
