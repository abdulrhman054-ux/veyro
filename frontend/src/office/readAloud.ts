/** Read-aloud: the device's own speech voice reads each line (for anyone who prefers listening,
 *  or can't comfortably read the screen). Uses the browser/OS Speech Synthesis; no network. */
export function canReadAloud() {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function readAloud(text: string, lang: "ar" | "en", onEnd?: () => void): () => void {
  if (!canReadAloud() || !text) { onEnd?.(); return () => {}; }
  const synth = window.speechSynthesis;
  synth.cancel();
  const u = new SpeechSynthesisUtterance(text.replace(/[*_#`]/g, ""));
  u.lang = lang === "ar" ? "ar-SA" : "en-US";
  const voice = synth.getVoices().find((v) => v.lang.toLowerCase().startsWith(lang));
  if (voice) u.voice = voice;
  u.rate = 1;
  let done = false;
  const finish = () => { if (!done) { done = true; onEnd?.(); } };
  u.onend = finish; u.onerror = finish;
  synth.speak(u);
  return () => { done = true; synth.cancel(); };
}
