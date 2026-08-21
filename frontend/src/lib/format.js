export const SAR_RATE = 3.77;

export const money = (n, currency = "USD") => {
  const v = Number(n || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const sym = currency === "USD" ? "$" : currency === "SAR" ? "﷼" : currency;
  return `${v} ${sym}`;
};

export const equiv = (amount, currency = "USD") => {
  const a = Number(amount || 0);
  if (currency === "SAR") return `≈ $${(a / SAR_RATE).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return `≈ ${Math.round(a * SAR_RATE).toLocaleString("en-US")} ﷼`;
};

export const STATUS = {
  blue: { label: "قيد التسجيل", cls: "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]" },
  yellow: { label: "تم إصدار التأشيرات", cls: "bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]" },
  green: { label: "تم التفويج", cls: "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]" },
  cancelled: { label: "ملغي", cls: "bg-gray-100 text-gray-500 border-gray-200" },
};

export const PKG_TYPE = { umrah: "عمرة", tourism: "سياحة" };

export const fmtDate = (s) => {
  if (!s) return "-";
  try { return new Date(s).toLocaleDateString("ar-EG", { year: "numeric", month: "short", day: "numeric" }); }
  catch { return s; }
};
