import { useEffect, useState } from "react";
import { api, type Verdict } from "../api";
import type { Lang } from "../i18n";

type VT = { line: string; reason: string };
const cache = new Map<string, VT>();

/** Leo's verdict line and reason in the viewer's language (voiced in character on demand). */
export function useVerdictText(sessionId: string | null, v: Verdict | null, lang: Lang): VT | null {
  const known = v?.texts?.[lang] ?? (sessionId ? cache.get(`${sessionId}:${lang}`) : undefined) ?? null;
  const [got, setGot] = useState<VT | null>(null);
  useEffect(() => {
    setGot(null);
    if (known || !sessionId || !v || v.rating === "DEMO") return;
    let alive = true;
    api.post<VT>(`/api/sessions/${sessionId}/verdict_text`, { lang })
      .then((r) => { cache.set(`${sessionId}:${lang}`, r); if (alive) setGot(r); }).catch(() => {});
    return () => { alive = false; };
  }, [known, sessionId, v, lang]);
  return known ?? got;
}
