import { useState } from "react";
import { SpriteSvg } from "../art/Sprite";
import { click, speakBlips, unlockAudio } from "../audio";
import { usePrefs } from "../prefs";

const KEY = "veyro.welcomed";
const TXT = {
  ar: {
    hi: "أهلاً وسهلاً في فيرو! أنا ليو.",
    steps: ["اكتب رمز السهم فوق (مثل NVDA) واضغط «ابدأ الجلسة».", "تفرّج على الفريق يتناقش قدامك، واضغط على أي شخصية تسولف معك.", "أنا أعلن القرار في الأخير، وتقدر تفتح التقرير الكامل."],
    tip: "ما عندك مفتاح؟ فعّل «الوضع التجريبي» وجرّب ببلاش.", go: "يلا نبدأ!",
  },
  en: {
    hi: "Welcome to Veyro! I'm Leo.",
    steps: ["Type a ticker up top (like NVDA) and press Start session.", "Watch the team debate in front of you, and click anyone to say hi.", "I announce the call at the end, and you can open the full report."],
    tip: "No key yet? Turn on Demo mode and try it for free.", go: "Let's go!",
  },
};

/** A short, friendly first-visit guide. Shown once. */
export function Welcome() {
  const { prefs } = usePrefs();
  const t = TXT[prefs.lang];
  const [show, setShow] = useState(() => { try { return !localStorage.getItem(KEY); } catch { return false; } });
  if (!show) return null;
  const close = () => { unlockAudio(); click(); speakBlips("Leo", t.go); try { localStorage.setItem(KEY, "1"); } catch { /* private mode */ } setShow(false); };
  return (
    <div className="modal-bg" role="dialog" aria-modal="true" aria-label={t.hi}>
      <div className="modal" style={{ maxWidth: 520, textAlign: "center" }}>
        <SpriteSvg name="Leo" px={5} frame="wave" talk />
        <h2 style={{ fontSize: 26, margin: "8px 0 14px" }}>{t.hi}</h2>
        <ol style={{ textAlign: "start", lineHeight: 1.9, fontSize: 17, paddingInlineStart: 24, margin: 0 }}>
          {t.steps.map((s) => <li key={s}>{s}</li>)}
        </ol>
        <p className="muted" style={{ fontWeight: 700 }}>{t.tip}</p>
        <button className="primary btn" onClick={close} autoFocus>{t.go}</button>
      </div>
    </div>
  );
}
