import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { DICT, type Lang, type T } from "./i18n";
import { setSound } from "./audio";

export type Theme = "day" | "night" | "system";
export type Intensity = "calm" | "normal" | "lively";
export type Prefs = { lang: Lang; theme: Theme; intensity: Intensity; reduceMotion: boolean; sound: boolean; showCost: boolean };

const DEFAULTS: Prefs = { lang: "ar", theme: "day", intensity: "normal", reduceMotion: false, sound: true, showCost: true };
const KEY = "veyro.prefs.v1";

function load(): Prefs {
  try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") }; } catch { return DEFAULTS; }
}

type Ctx = { prefs: Prefs; set: (p: Partial<Prefs>) => void; t: T; night: boolean; motionOff: boolean };
const PrefsCtx = createContext<Ctx | null>(null);

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [prefs, setPrefs] = useState<Prefs>(load);
  const [sysNight, setSysNight] = useState(() => matchMedia("(prefers-color-scheme: dark)").matches);
  const [sysReduce, setSysReduce] = useState(() => matchMedia("(prefers-reduced-motion: reduce)").matches);

  useEffect(() => {
    const a = matchMedia("(prefers-color-scheme: dark)"); const b = matchMedia("(prefers-reduced-motion: reduce)");
    const fa = () => setSysNight(a.matches); const fb = () => setSysReduce(b.matches);
    a.addEventListener("change", fa); b.addEventListener("change", fb);
    return () => { a.removeEventListener("change", fa); b.removeEventListener("change", fb); };
  }, []);

  const night = prefs.theme === "night" || (prefs.theme === "system" && sysNight);
  const motionOff = prefs.reduceMotion || sysReduce;

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch { /* private mode */ }
    setSound(prefs.sound);
    const h = document.documentElement;
    h.lang = prefs.lang; h.dir = prefs.lang === "ar" ? "rtl" : "ltr";
    h.dataset.theme = night ? "night" : "day";
    h.dataset.intensity = motionOff ? "off" : prefs.intensity;
    document.title = prefs.lang === "ar" ? "فيرو · مكتب المجلس" : "Veyro · Council Office";
  }, [prefs, night, motionOff]);

  const value = useMemo<Ctx>(() => ({
    prefs, night, motionOff, t: DICT[prefs.lang],
    set: (p) => setPrefs((o) => ({ ...o, ...p })),
  }), [prefs, night, motionOff]);
  return <PrefsCtx.Provider value={value}>{children}</PrefsCtx.Provider>;
}

export function usePrefs() {
  const c = useContext(PrefsCtx);
  if (!c) throw new Error("PrefsProvider missing");
  return c;
}
