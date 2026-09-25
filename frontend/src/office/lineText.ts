import { useEffect, useState } from "react";
import { api } from "../api";
import type { Lang } from "../i18n";

type Texts = Partial<Record<Lang, string>>;
const cache = new Map<number, Texts>();
const inflight = new Map<string, Promise<string | null>>();

/** The line in the viewer's language. Never shows the other language: if the session ran in
 *  the other language, the in-character line is created on demand (and cached). */
export function useLineText(texts: Texts | undefined, turnId: number | undefined, lang: Lang, allowFetch = true): string | null {
  const known = texts?.[lang] ?? (turnId ? cache.get(turnId)?.[lang] : undefined) ?? null;
  const [fetched, setFetched] = useState<string | null>(null);
  useEffect(() => {
    setFetched(null);
    if (known || !turnId || !allowFetch) return;
    const key = `${turnId}:${lang}`;
    let p = inflight.get(key);
    if (!p) {
      p = api.post<Record<string, string>>(`/api/turns/${turnId}/translate`, { what: `voice_${lang}` })
        .then((r) => Object.values(r)[0] ?? null).catch(() => null);
      inflight.set(key, p);
    }
    let alive = true;
    p.then((v) => {
      if (v && turnId) cache.set(turnId, { ...(cache.get(turnId) ?? {}), [lang]: v });
      if (alive) setFetched(v);
    });
    return () => { alive = false; };
  }, [known, turnId, lang, allowFetch]);
  return known ?? fetched;
}
