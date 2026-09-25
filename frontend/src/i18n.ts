export type Lang = "ar" | "en";
export type CharKey = "Ollie" | "Pip" | "Buzz" | "Benny" | "Bolt" | "Bruno" | "Tank" | "Leo" | "Albie";

export const CHAR_ORDER: CharKey[] = ["Ollie", "Buzz", "Pip", "Benny", "Bolt", "Bruno", "Tank", "Leo"];

export const CHAR_INFO: Record<CharKey, {
  ar: string; roleAr: string; roleEn: string; animalAr: string; animalEn: string;
  pitch: number; emote: string; catchAr: string; catchEn: string;
}> = {
  Ollie: { ar: "أولي", roleAr: "المحلل الفني", roleEn: "Technical Analyst", animalAr: "بومة", animalEn: "Owl", pitch: 420, emote: "!", catchAr: "هوو هوو!", catchEn: "hoot!" },
  Pip: { ar: "بيب", roleAr: "محلل أخبار السهم", roleEn: "Stock News Analyst", animalAr: "ببغاء", animalEn: "Macaw", pitch: 760, emote: "!!", catchAr: "سكوااك!", catchEn: "squawk!" },
  Buzz: { ar: "بَز", roleAr: "محلل المزاج العام", roleEn: "Sentiment Analyst", animalAr: "نحلة", animalEn: "Bee", pitch: 900, emote: "♪", catchAr: "بززز!", catchEn: "bzzz!" },
  Benny: { ar: "بيني", roleAr: "محلل الأساسيات", roleEn: "Fundamentals Analyst", animalAr: "قندس", animalEn: "Beaver", pitch: 520, emote: "…", catchAr: "قرمش!", catchEn: "chomp!" },
  Bolt: { ar: "بولت", roleAr: "باحث الصعود", roleEn: "Bull Researcher", animalAr: "ثور", animalEn: "Bull", pitch: 230, emote: "!", catchAr: "مووو!", catchEn: "moo-ve!" },
  Bruno: { ar: "برونو", roleAr: "باحث الهبوط", roleEn: "Bear Researcher", animalAr: "دب", animalEn: "Bear", pitch: 180, emote: "?", catchAr: "غرر…", catchEn: "grr…" },
  Tank: { ar: "تانك", roleAr: "فريق المخاطر", roleEn: "Risk Team", animalAr: "سلحفاة", animalEn: "Turtle", pitch: 300, emote: "…", catchAr: "على مهلك… بثبات.", catchEn: "slow and steady." },
  Leo: { ar: "ليو", roleAr: "صاحب القرار", roleEn: "Decision Maker", animalAr: "أسد", animalEn: "Lion", pitch: 260, emote: "!", catchAr: "زئير!", catchEn: "roar!" },
  Albie: { ar: "ألبي", roleAr: "ناقل الأخبار العالمية", roleEn: "World News Courier", animalAr: "طائر القطرس", animalEn: "Albatross", pitch: 640, emote: "✈", catchAr: "ريشتي تطير بالأخبار!", catchEn: "feathers full of news!" },
};

export const charName = (c: CharKey, l: Lang) => (l === "ar" ? CHAR_INFO[c].ar : c);
export const charRole = (c: CharKey, l: Lang) => (l === "ar" ? CHAR_INFO[c].roleAr : CHAR_INFO[c].roleEn);

export const NODE_LABEL: Record<string, { ar: string; en: string }> = {
  "Market Analyst": { ar: "التحليل الفني والسوق", en: "Market & technicals" },
  "Sentiment Analyst": { ar: "المزاج العام", en: "Social sentiment" },
  "News Analyst": { ar: "الأخبار", en: "News" },
  "Fundamentals Analyst": { ar: "الأساسيات المالية", en: "Fundamentals" },
  "Bull Researcher": { ar: "حجة الصعود", en: "Bull case" },
  "Bear Researcher": { ar: "حجة الهبوط", en: "Bear case" },
  "Research Manager": { ar: "خطة الاستثمار", en: "Investment plan" },
  "Trader": { ar: "مقترح الصفقة", en: "Trade proposal" },
  "Risk Team": { ar: "نقاش المخاطر", en: "Risk debate" },
  "Portfolio Manager": { ar: "القرار النهائي", en: "Final decision" },
  "Global Link": { ar: "ربط الأخبار العالمية بالسهم", en: "World news link" },
};

export const RATING: Record<string, { ar: string; en: string; tone: "buy" | "hold" | "sell" | "none" }> = {
  Buy: { ar: "شراء", en: "BUY", tone: "buy" },
  Overweight: { ar: "زيادة تدريجية", en: "OVERWEIGHT", tone: "buy" },
  Hold: { ar: "احتفاظ", en: "HOLD", tone: "hold" },
  Underweight: { ar: "تخفيف", en: "UNDERWEIGHT", tone: "sell" },
  Sell: { ar: "بيع", en: "SELL", tone: "sell" },
  REVIEW: { ar: "يحتاج مراجعة", en: "NEEDS REVIEW", tone: "none" },
  DEMO: { ar: "تجريبي", en: "DEMO", tone: "none" },
};

export const CONVICTION: Record<string, { ar: string; en: string; level: number }> = {
  low: { ar: "منخفضة", en: "Low", level: 1 },
  medium: { ar: "متوسطة", en: "Medium", level: 2 },
  high: { ar: "عالية", en: "High", level: 3 },
  unstated: { ar: "غير مذكورة في القرار", en: "Not stated in the decision", level: 0 },
};

const ar = {
  brand: "فيرو", tagline: "مكتب المجلس الذكي", office: "المكتب", report: "التقرير", history: "السجل", settings: "الإعدادات",
  nav: "التنقل الرئيسي", demo: "تجريبي", demoMode: "وضع تجريبي (بدون مفتاح ولا تكلفة)",
  single: "سهم واحد", watchlist: "قائمة أسهم", scan: "مسح السوق",
  ticker: "رمز السهم", tickers: "الرموز (حتى 5، افصل بفاصلة)", start: "ابدأ الجلسة", running: "الجلسة جارية…", again: "جلسة جديدة",
  stop: "إيقاف", startScan: "ابدأ المسح", startList: "حلّل القائمة",
  screener: "نوع المسح", candidates: "عدد الأسهم", preview: "اعرض المرشحين", candidatesFrom: "مرشحون حقيقيون من",
  estimate: "التكلفة التقديرية", estimateUnknown: "سعر هذا المزوّد غير معروف لنا، نعرض عدد الكلمات فقط",
  actualCost: "التكلفة الفعلية", free: "مجاناً",
  marketOpen: "السوق مفتوح", marketClosed: "السوق مقفل", marketUnknown: "حالة السوق غير متوفرة",
  sound: "الصوت", muted: "مكتوم", soundAria: "تشغيل أو كتم أصوات الشخصيات",
  themeAria: "تبديل النهار والليل", langBtn: "English", langAria: "Switch to English",
  welcome: "أهلاً! الفريق كله في المكتب ويشتغل. اكتب رمز السهم فوق واضغط «ابدأ الجلسة»، وبيتناقشون قدامك قبل ما يطلع القرار.",
  welcomeDemo: "أنت في الوضع التجريبي: الشخصيات بتعرض لك طريقة الشغل بدون تحليل حقيقي.",
  minutes: "محضر الجلسة", logEmpty: "هنا بنكتب خلاصة كلام كل واحد بعد ما يخلص.",
  thinking: "يفكّر…", verdictTag: "ليو · القرار", openReport: "افتح التقرير", conviction: "قوة القناعة",
  disclaimer: "تحليل للمساعدة على التفكير، وليس نصيحة مالية.",
  priceAtVerdict: "السعر وقت القرار", unavailable: "غير متوفر", source: "المصدر",
  chartUnavailable: "بيانات السعر غير متوفرة", lastClose: "آخر إغلاق",
  whoSaid: "وش قال كل واحد", details: "التفاصيل", hideDetails: "إخفاء التفاصيل", fullAnalysis: "التحليل الكامل",
  translating: "جاري الترجمة…", originalText: "النص الأصلي كما كتبه الإطار (إنجليزي)", translateFail: "ما قدرنا نترجم الآن. جرّب بعدين.",
  dataSources: "مصادر البيانات", noSources: "ما سُجّل استدعاء لأدوات بيانات في هذه الجلسة.",
  sentimentNote: "مصادر المزاج العام يجلبها محلل المزاج بنفسه ويذكرها داخل تقريره.",
  sessionTime: "وقت الجلسة", tradeDate: "تاريخ التحليل", noReport: "ما فيه تقرير للحين. ابدأ جلسة من المكتب.",
  historyTitle: "لوحة النتائج الصادقة", historySub: "نقارن كل قرار بالمؤشر المرجعي لسوقه (SPY للأسهم الأمريكية) من وقت القرار لليوم",
  colTicker: "السهم", colVerdict: "القرار", colDate: "التاريخ", colThen: "السعر وقتها", colNow: "السعر الآن",
  colRet: "التغير", colSpy: "المؤشر المرجعي بنفس الفترة", colScore: "النتيجة",
  beat: "تفوّق", lagged: "تأخر", neutral: "محايد", sessions: "عدد الجلسات", beatSpy: "قرارات تفوّقت على المؤشر",
  noHistory: "ما فيه جلسات سابقة للحين.", view: "عرض", scans: "عمليات المسح", ranking: "ترتيب الفريق",
  provider: "مزوّد النموذج", apiKey: "مفتاح API", pasteKey: "الصق المفتاح الجديد هنا", save: "حفظ", remove: "حذف",
  savedKey: "المفتاح المحفوظ", keyFromEnv: "من ملف ‎.env (للتطوير)", noKey: "ما فيه مفتاح",
  keyNote: "يُحفظ في خزنة ويندوز على جهازك فقط، ولا يظهر كاملاً مرة ثانية.",
  quickModel: "نموذج المحللين (سريع)", deepModel: "نموذج القرار (عميق)",
  modelAndKey: "النموذج والمفتاح", lookAndSound: "الشكل والصوت", language: "اللغة", appearance: "المظهر",
  day: "نهاري", night: "ليلي", system: "حسب الجهاز", intensity: "حيوية الحركة", calm: "هادئة", normal: "متوسطة", lively: "حيوية",
  reduceMotion: "تقليل الحركة", voices: "أصوات الشخصيات", showCost: "عرض التكلفة",
  about: "عن فيرو", aboutText: "فيرو مكتبك الصغير الدافئ: تسعة زملاء من الحيوانات يجتمعون حول أي سهم تختاره، يتناقشون قدامك بصوت عالي، وبعدين ليو يعلن القرار.",
  aboutPoints: [
    "أولي يقرأ الشارت، وبَز يسمع وش يقول الناس، وبيب يلاحق الأخبار، وبيني يحسب الأرقام.",
    "بولت يدافع عن الصعود وبرونو يدافع عن الهبوط، عشان تسمع الوجهين قبل أي قرار.",
    "تانك يراجع المخاطر بهدوء، وليو يوزن الكل ويعطيك توصية واضحة مع السبب.",
    "ألبي طائر القطرس يلف العالم ويجيب أخبار الأسواق والاقتصاد من أقوى الصحف، ويربطها بحركة سهمك.",
    "كل رقم تشوفه جاي من بيانات حقيقية، وإذا ما توفّر شي نقولها لك بصراحة.",
    "لوحة النتائج تقارن كل قرار بالسوق من غير تجميل، عشان تعرف متى أصاب ومتى أخطأ.",
  ],
  aboutPromise: "مفاتيحك تبقى على جهازك، والقرار الأخير دايماً لك.",
  builtOn: "مبني على TradingAgents (رخصة Apache-2.0).", licensedUnder: "", showLicense: "",
  artNote: "الشخصيات والرسومات أصلية ومستوحاة من أجواء القرى الدافئة، وليست منقولة من أي لعبة.",
  fontsNote: "الخطوط: Baloo Bhaijaan 2 و Pixelify Sans (رخصة SIL OFL).",
  saved: "انحفظ!", error: "صار خطأ", scanTitle: "مسح السوق", scanProgress: "تقدّم المسح",
  scanConfirm: "بنحلل {n} أسهم، كل سهم جلسة كاملة.", nowAnalyzing: "نحلل الآن", leaderboard: "ليو يعرض الترتيب",
  invalidTicker: "الرمز غير صحيح. مثال: NVDA", close: "إغلاق", skip: "تخطَّ",
  tokens: "كلمات", unknownPrice: "السعر غير معروف",
  moodMarket: "مزاج السوق (آخر إغلاق)", moodStock: "حركة السهم (آخر إغلاق)",
};

type Dict = typeof ar;

const en: Dict = {
  brand: "Veyro", tagline: "The AI Council Office", office: "Office", report: "Report", history: "History", settings: "Settings",
  nav: "Main navigation", demo: "Demo", demoMode: "Demo mode (no key, no cost)",
  single: "One stock", watchlist: "Watchlist", scan: "Market scan",
  ticker: "Ticker", tickers: "Tickers (up to 5, comma separated)", start: "Start session", running: "In session…", again: "New session",
  stop: "Stop", startScan: "Start scan", startList: "Analyse list",
  screener: "Scan type", candidates: "How many", preview: "Show candidates", candidatesFrom: "Real candidates from",
  estimate: "Estimated cost", estimateUnknown: "We don't know this provider's prices, so we show token counts only",
  actualCost: "Actual cost", free: "Free",
  marketOpen: "Market open", marketClosed: "Market closed", marketUnknown: "Market status unavailable",
  sound: "Sound", muted: "Muted", soundAria: "Mute or unmute character voices",
  themeAria: "Toggle day and night", langBtn: "عربي", langAria: "التبديل إلى العربية",
  welcome: "Hi there! The whole team is in the office. Type a ticker up top and press Start, and they'll debate it right in front of you before the verdict.",
  welcomeDemo: "You're in Demo mode: the characters show you how they work, without any real analysis.",
  minutes: "Session minutes", logEmpty: "Each character's takeaway lands here when they finish.",
  thinking: "Thinking…", verdictTag: "Leo · Verdict", openReport: "Open report", conviction: "Conviction",
  disclaimer: "Analysis to help you think, not financial advice.",
  priceAtVerdict: "Price at verdict", unavailable: "Unavailable", source: "Source",
  chartUnavailable: "Price data unavailable", lastClose: "Last close",
  whoSaid: "What everyone said", details: "Details", hideDetails: "Hide details", fullAnalysis: "Full analysis",
  translating: "Translating…", originalText: "Original text", translateFail: "Couldn't load that right now. Try again later.",
  dataSources: "Data sources", noSources: "No data-tool calls were recorded in this session.",
  sentimentNote: "Social sentiment sources are fetched by the sentiment analyst and cited in its report.",
  sessionTime: "Session time", tradeDate: "Analysis date", noReport: "No report yet. Start a session in the Office.",
  historyTitle: "The honest scoreboard", historySub: "Every call compared with its market's benchmark (SPY for US stocks) from the verdict until today",
  colTicker: "Ticker", colVerdict: "Verdict", colDate: "Date", colThen: "Price then", colNow: "Price now",
  colRet: "Change", colSpy: "Benchmark, same period", colScore: "Result",
  beat: "Beat", lagged: "Lagged", neutral: "Neutral", sessions: "Sessions", beatSpy: "Calls that beat the benchmark",
  noHistory: "No past sessions yet.", view: "View", scans: "Scans", ranking: "Team ranking",
  provider: "Model provider", apiKey: "API key", pasteKey: "Paste a new key here", save: "Save", remove: "Remove",
  savedKey: "Saved key", keyFromEnv: "from .env (development)", noKey: "No key",
  keyNote: "Stored in Windows Credential Manager on this PC only, never shown in full again.",
  quickModel: "Analyst model (quick)", deepModel: "Decision model (deep)",
  modelAndKey: "Model & key", lookAndSound: "Look & sound", language: "Language", appearance: "Appearance",
  day: "Day", night: "Night", system: "Match device", intensity: "Animation", calm: "Calm", normal: "Normal", lively: "Lively",
  reduceMotion: "Reduce motion", voices: "Character voices", showCost: "Show cost",
  about: "About Veyro", aboutText: "Veyro is your cosy little office: nine animal colleagues gather around any stock you pick, debate it out loud in front of you, and then Leo announces the call.",
  aboutPoints: [
    "Ollie reads the chart, Buzz listens to the crowd, Pip chases the news and Benny crunches the numbers.",
    "Bolt argues the upside and Bruno the downside, so you hear both sides before any call.",
    "Tank calmly reviews the risks, and Leo weighs everyone and gives you a clear recommendation with the reason.",
    "Albie the albatross circles the globe bringing markets and economy news from the strongest papers, and links it to your stock.",
    "Every number you see comes from real data, and if something is missing we tell you plainly.",
    "The scoreboard compares every call with the market, no sugar-coating, so you know when it was right and when it wasn't.",
  ],
  aboutPromise: "Your keys stay on your computer, and the final decision is always yours.",
  builtOn: "Built on TradingAgents (Apache-2.0 license).", licensedUnder: "", showLicense: "",
  artNote: "Characters and art are original, inspired by cosy village games, and not copied from any game.",
  fontsNote: "Fonts: Baloo Bhaijaan 2 and Pixelify Sans (SIL OFL).",
  saved: "Saved!", error: "Something went wrong", scanTitle: "Market scan", scanProgress: "Scan progress",
  scanConfirm: "We'll analyse {n} stocks, each one a full session.", nowAnalyzing: "Now analysing", leaderboard: "Leo presents the ranking",
  invalidTicker: "That ticker doesn't look right. Example: NVDA", close: "Close", skip: "Skip",
  tokens: "tokens", unknownPrice: "price unknown",
  moodMarket: "Market mood (last close)", moodStock: "Stock move (last close)",
};

export const DICT: Record<Lang, Dict> = { ar, en };
export type T = Dict;

export function fmtNum(n: number | null | undefined, lang: Lang, opts: Intl.NumberFormatOptions = {}) {
  if (n === null || n === undefined || Number.isNaN(n)) return null;
  return new Intl.NumberFormat(lang === "ar" ? "ar-SA-u-nu-latn" : "en-US", opts).format(n);
}
export const fmtUsd = (n: number | null | undefined, lang: Lang, digits = 2) =>
  fmtNum(n, lang, { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits });
export const fmtPct = (n: number | null | undefined, lang: Lang) =>
  n === null || n === undefined ? null : (n >= 0 ? "+" : "") + fmtNum(n * 100, lang, { maximumFractionDigits: 2, minimumFractionDigits: 2 }) + "%";
export function fmtDate(iso: string | null | undefined, lang: Lang, time = true) {
  if (!iso) return null;
  const d = new Date(iso);
  return new Intl.DateTimeFormat(lang === "ar" ? "ar-SA-u-nu-latn-ca-gregory" : "en-US",
    time ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" }).format(d);
}
