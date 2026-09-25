import type { Lang } from "../i18n";

/** Human, fully-localised wording for audit-log rows (the backend stores stable English codes). */
const EVENT: Record<string, { ar: string; en: string }> = {
  proposed: { ar: "تذكرة جاهزة", en: "Ticket prepared" },
  rejected: { ar: "رُفض بسبب الحدود", en: "Rejected by limits" },
  confirmed: { ar: "أكّدته أنت", en: "Confirmed by you" },
  submitted: { ar: "أُرسل للوسيط", en: "Sent to broker" },
  filled: { ar: "تنفّذ", en: "Filled" },
  partially_filled: { ar: "تنفّذ جزئياً", en: "Partially filled" },
  cancelled: { ar: "أُلغي", en: "Cancelled" },
  cancel_requested: { ar: "طلبت إلغاءه", en: "You asked to cancel" },
  failed: { ar: "فشل", en: "Failed" },
  kill_switch: { ar: "زر الطوارئ", en: "Kill switch" },
  liquidate: { ar: "بيع كل المراكز", en: "Sold all positions" },
  mode_changed: { ar: "تغيير الوضع", en: "Mode changed" },
  limits_saved: { ar: "حفظ الحدود", en: "Limits saved" },
  keys_saved: { ar: "حفظ المفاتيح", en: "Keys saved" },
  keys_deleted: { ar: "حذف المفاتيح", en: "Keys removed" },
  keys_rejected: { ar: "مفاتيح مرفوضة", en: "Keys rejected" },
};
const MODE: Record<string, { ar: string; en: string }> = {
  off: { ar: "مغلق", en: "Off" }, paper: { ar: "تجريبي", en: "Paper" }, live: { ar: "حقيقي", en: "Live" },
};
const CHECK: Record<string, { ar: string; en: string }> = {
  max_order: { ar: "أقصى مبلغ للأمر", en: "max per order" }, symbol_exposure: { ar: "التعرّض للسهم", en: "exposure per stock" },
  daily_loss: { ar: "خسارة اليوم", en: "daily loss" }, orders_today: { ar: "عدد أوامر اليوم", en: "orders today" },
  cash_only: { ar: "النقد المتوفر", en: "cash available" }, no_short: { ar: "الأسهم المملوكة", en: "shares owned" },
  account_ok: { ar: "حالة الحساب", en: "account status" },
};
const STATUS: Record<string, { ar: string; en: string }> = {
  accepted: { ar: "مقبول", en: "accepted" }, new: { ar: "جديد", en: "new" }, filled: { ar: "منفّذ", en: "filled" },
  canceled: { ar: "ملغى", en: "cancelled" }, expired: { ar: "منتهي", en: "expired" }, rejected: { ar: "مرفوض", en: "rejected" },
  partially_filled: { ar: "منفّذ جزئياً", en: "partially filled" },
};

export const eventLabel = (e: string, l: Lang) => EVENT[e]?.[l] ?? e;
export const modeLabel = (m: string, l: Lang) => MODE[m]?.[l] ?? m;
export const statusLabel = (s: string, l: Lang) => STATUS[s]?.[l] ?? s;

export function detailText(msg: string | null, l: Lang): string {
  if (!msg) return "";
  const ar = l === "ar";
  let m: RegExpMatchArray | null;
  if (msg === "all checks passed") return ar ? "اجتاز كل فحوص تانك" : "Passed all of Tank's checks";
  if (msg === "user confirmed ticket") return ar ? "ضغطت «أؤكد الأمر»" : "You pressed Confirm";
  if (msg === "user cancelled order") return ar ? "ألغيته من شاشة الأوامر" : "Cancelled from the Orders screen";
  if ((m = msg.match(/^blocked (?:at confirm )?by: (.+)$/))) {
    const names = m[1].split(",").map((x) => CHECK[x.trim()]?.[l] ?? x.trim()).join(ar ? "، " : ", ");
    return (msg.includes("at confirm") ? (ar ? "رُفض وقت التأكيد: " : "Rejected at confirmation: ") : (ar ? "تجاوز: " : "Over the limit: ")) + names;
  }
  if ((m = msg.match(/^status=(\w+)$/))) return (ar ? "حالة الوسيط: " : "Broker status: ") + statusLabel(m[1], l);
  if ((m = msg.match(/^broker status (\w+)$/))) return (ar ? "حالة الوسيط: " : "Broker status: ") + statusLabel(m[1], l);
  if ((m = msg.match(/^filled ([\d.]+) @ ([\d.]+)$/))) return ar ? `تنفّذ ${m[1]} سهم بسعر ${m[2]}$` : `Filled ${m[1]} shares at $${m[2]}`;
  if ((m = msg.match(/^(\w+) -> (\w+)$/))) return `${modeLabel(m[1], l)} ${ar ? "←" : "→"} ${modeLabel(m[2], l)}`;
  if ((m = msg.match(/^cancelled (\d+) open orders; execution off(.*)$/))) return ar ? `أُلغي ${m[1]} أمر مفتوح وأُوقف التنفيذ` : `Cancelled ${m[1]} open orders and turned execution off`;
  if ((m = msg.match(/^closed (\d+) positions/))) return ar ? `أُغلق ${m[1]} مركز (بتأكيدك)` : `Closed ${m[1]} positions (you confirmed)`;
  if ((m = msg.match(/^(paper|live) keys saved \((.+)\)$/))) return ar ? `حُفظت مفاتيح ${modeLabel(m[1], l)} (${m[2]})` : `${modeLabel(m[1], l)} keys saved (${m[2]})`;
  if ((m = msg.match(/^(paper|live) keys removed$/))) return ar ? `حُذفت مفاتيح ${modeLabel(m[1], l)}` : `${modeLabel(m[1], l)} keys removed`;
  if ((m = msg.match(/^(paper|live) keys failed validation/))) return ar ? `مفاتيح ${modeLabel(m[1], l)} ما اشتغلت مع Alpaca` : `${modeLabel(m[1], l)} keys didn't work with Alpaca`;
  if (msg.startsWith("{")) {
    try {
      const j = JSON.parse(msg);
      return ar
        ? `للأمر ${j.max_order_usd}$ · للسهم ${j.max_symbol_exposure_usd}$ · خسارة يومية ${j.daily_loss_limit_usd}$ · ${j.max_orders_per_day} أوامر يومياً`
        : `per order $${j.max_order_usd} · per stock $${j.max_symbol_exposure_usd} · daily loss $${j.daily_loss_limit_usd} · ${j.max_orders_per_day} orders/day`;
    } catch { /* fall through */ }
  }
  if (msg.startsWith("broker error") || msg.startsWith("cancel failed")) return ar ? "رد الوسيط بخطأ" : "The broker returned an error";
  return ar ? "—" : msg;
}
