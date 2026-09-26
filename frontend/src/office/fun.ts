import { useEffect, useRef, useState } from "react";
import type { CharKey, Lang } from "../i18n";
import { toneScore } from "./scenes";
import { startJingle } from "../audio";

/** Easter eggs and jokes. None of this touches the analysis: it only reacts to what is already on screen. */

/** Tap a character: one of these, in their own voice. */
export const REACTIONS: Record<CharKey, { ar: string[]; en: string[] }> = {
  Albie: {
    ar: ["يا جماعة عندي لكم لفّة على العالم!", "من فوق الغيوم شفت أخبار كثيرة!", "تأخرت؟ الرحلة كانت ترانزيت في دبي 😅", "لا تسألني عن الطقس، أنا أجيب الأخبار بس!"],
    en: ["Fresh off the jet stream!", "I saw so much news from above the clouds!", "Late? My flight had a layover 😅", "Don't ask me about the weather, I only carry the news!"],
  },
  Ollie: {
    ar: ["هوو؟ أنا أراقب الشارت!", "نظارتي نظيفة اليوم، هوو هوو!", "سهرت أرسم خطوط ترند… نمت على الدعم 😴", "الشموع اليابانية؟ لا، أنا أحب الشموع المعطّرة."],
    en: ["Hoo? I'm watching the chart!", "Freshly polished glasses, hoot!", "Up all night drawing trend lines… fell asleep on support 😴", "Candlesticks? I prefer scented candles."],
  },
  Pip: {
    ar: ["عندك خبر؟ قلّي قلّي!", "سكوااك! لا تشدّ ريشي!", "عاجل: بيب يبي فطور! 🥐", "قريت الخبر مرتين… وما زلت ما فهمت العنوان!"],
    en: ["Got news? Tell me tell me!", "Squawk! Mind the feathers!", "BREAKING: Pip wants breakfast! 🥐", "Read that headline twice… still don't get it!"],
  },
  Buzz: {
    ar: ["بززز! الكل يسولف اليوم!", "ودّك نرقص رقصة النحل؟", "قروب الواتساب يقول «الصاروخ جاي» 🚀… كالعادة", "إذا الكل متفق، أنا أبدأ أشك 🐝"],
    en: ["Bzzz! Everyone's chatting today!", "Want to see my waggle dance?", "The group chat says 'to the moon' 🚀… as always", "When everyone agrees, I start to worry 🐝"],
  },
  Benny: {
    ar: ["لحظة… أحسب الأرقام، قرمش!", "القهوة والجداول، أحلى صباح!", "الميزانية ما تكذب… بس أحياناً تتجمّل 🧐", "عدّيت الأصفار ثلاث مرات. قرمش!"],
    en: ["One sec… crunching numbers, chomp!", "Coffee and spreadsheets, perfect morning!", "Balance sheets don't lie… they just wear makeup 🧐", "Counted the zeros three times. Chomp!"],
  },
  Bolt: {
    ar: ["مووو! متحمس للجلسة!", "كل نزول فرصة، صح؟", "أنا ثور، طبيعي أشوف كل شي صاعد 🐂", "اشترِ النزول! …أي نزول؟ كله!"],
    en: ["Moo-ve! Ready to go!", "Every dip's a chance, right?", "I'm a bull, everything looks like up to me 🐂", "Buy the dip! …which dip? All of them!"],
  },
  Bruno: {
    ar: ["غرر… خلني أركّز.", "أنا بس حذر، مو زعلان!", "كل ما قال بولت «صاروخ» أتذكر 2008 🐻", "أنا ما أنام شتوي، أنا أنتظر التصحيح."],
    en: ["Grr… let me focus.", "I'm careful, not grumpy!", "Every time Bolt says 'rocket' I remember 2008 🐻", "I don't hibernate, I wait for the correction."],
  },
  Tank: {
    ar: ["على مهلك… بثبات.", "الخوذة للسلامة، طبعاً!", "وقف الخسارة مثل حزام الأمان 🛡️", "السلحفاة وصلت قبل الأرنب، تذكّر!"],
    en: ["Slow and steady.", "Hard hat for safety, of course!", "A stop-loss is a seat belt 🛡️", "The tortoise beat the hare, remember!"],
  },
  Leo: {
    ar: ["أهلاً بك في المجلس! زئير!", "القرار يحتاج صبر، وأنا صبور.", "أنا ملك الغابة… بس السوق ما يدري 🦁", "اجتماع ثاني؟ طيب، بس أحد يجيب قهوة."],
    en: ["Welcome to the council! Roar!", "Good calls need patience. I have plenty.", "King of the jungle… the market didn't get the memo 🦁", "Another meeting? Fine, someone bring coffee."],
  },
};

/** Tapping the same character five times in a row. */
export const POKED: Record<CharKey, { ar: string; en: string }> = {
  Albie: { ar: "خلاص! بطير وأرجع بكرة ✈️", en: "That's it! I'm flying off till tomorrow ✈️" },
  Ollie: { ar: "هوووو! خربت نظارتي! 🦉💫", en: "HOOOO! You smudged my glasses! 🦉💫" },
  Pip: { ar: "سكوااااك! بنشر عنك خبر عاجل! 📰", en: "SQUAAAWK! I'm running a story about you! 📰" },
  Buzz: { ar: "بززززز! بلّغت القروب عنك! 🐝", en: "BZZZZZ! I told the group chat about you! 🐝" },
  Benny: { ar: "طيب… بحسب كم مرة ضغطت: خمس. قرمش 🧮", en: "Okay… I counted your taps: five. Chomp 🧮" },
  Bolt: { ar: "موووو! طاقتي فوق 100٪! 🐂⚡", en: "MOOOO! Energy over 100%! 🐂⚡" },
  Bruno: { ar: "غررر! هذي سادس إشارة بيع أشوفها اليوم 🐻", en: "GRRR! That's the sixth sell signal I've seen today 🐻" },
  Tank: { ar: "…على… مهلك… يا… صديقي 🐢", en: "…slow… down… my… friend 🐢" },
  Leo: { ar: "زئييير! الجلسة مرفوعة للاستراحة! 🦁", en: "ROOOAR! This meeting is adjourned for a break! 🦁" },
};

/** Said now and then between sessions, when the office is idle. */
export const IDLE_QUIPS: Partial<Record<CharKey, { ar: string[]; en: string[] }>> = {
  Bolt: { ar: ["متى نبدأ؟ عندي حجج جاهزة!"], en: ["When do we start? I've got arguments ready!"] },
  Bruno: { ar: ["هدوء السوق يقلقني…"], en: ["A quiet market worries me…"] },
  Benny: { ar: ["أحد شاف آلتي الحاسبة؟"], en: ["Has anyone seen my calculator?"] },
  Buzz: { ar: ["الناس ساكتين اليوم… غريبة!"], en: ["Everyone's quiet today… weird!"] },
  Ollie: { ar: ["هوو… الشارت يناديني."], en: ["Hoo… the chart is calling me."] },
  Pip: { ar: ["ما في خبر؟ أجل أنا الخبر!"], en: ["No news? Then I'm the news!"] },
  Tank: { ar: ["أنا جاهز… من أمس."], en: ["I'm ready… since yesterday."] },
  Leo: { ar: ["اختر سهم وأجمع لك الفريق."], en: ["Pick a stock and I'll gather the team."] },
};

/** The line Bruno pops in with when the team warns about risk, or the call is to sell. */
export const DONT_BUY = { ar: "ورع، لا تشتري هذا! 🙅", en: "Kid, don't buy this! 🙅" };

/** A clear risk warning: clearly more warning words than hopeful ones in the line being spoken. */
export function isWarning(text: string | null | undefined): boolean {
  const s = toneScore(text);
  return s.n - s.p >= 2;
}

export function pick<T>(xs: T[]): T { return xs[Math.floor(Math.random() * xs.length)]; }
export function quipFor(c: CharKey, lang: Lang, pool: Partial<Record<CharKey, { ar: string[]; en: string[] }>>): string | null {
  const p = pool[c]?.[lang];
  return p?.length ? pick(p) : null;
}

const KONAMI = ["ArrowUp", "ArrowUp", "ArrowDown", "ArrowDown", "ArrowLeft", "ArrowRight", "ArrowLeft", "ArrowRight", "b", "a"];

/** Party mode: the Konami code (↑↑↓↓←→←→BA) anywhere outside a text box, or tapping the wall clock five times. */
export function useParty(ms = 9000) {
  const [party, setParty] = useState(0);
  const keys = useRef<string[]>([]);
  const taps = useRef<number[]>([]);
  const start = () => { startJingle(); setParty(Date.now()); };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable)) return;
      const office = document.querySelector(".office") as HTMLElement | null;
      if (!office || office.offsetParent === null) return;   // only while the Office is on screen
      const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      keys.current = [...keys.current, k].slice(-KONAMI.length);
      if (keys.current.join() === KONAMI.join()) { keys.current = []; start(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => {
    if (!party) return;
    const h = window.setTimeout(() => setParty(0), ms);
    return () => clearTimeout(h);
  }, [party, ms]);
  const tapClock = () => {
    const now = Date.now();
    taps.current = [...taps.current.filter((t) => now - t < 3000), now];
    if (taps.current.length >= 5) { taps.current = []; start(); }
  };
  return { party: party > 0, partyKey: party, tapClock };
}
