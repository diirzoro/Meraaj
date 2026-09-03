export const SAR_RATE = 3.77;

export const money = (n, currency = "USD") => {
  const v = Number(n || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const sym = currency === "USD" ? "$" : currency === "SAR" ? "ر.س" : currency;
  return `${v} ${sym}`;
};

export const equiv = (amount, currency = "USD") => {
  const a = Number(amount || 0);
  if (currency === "SAR") return `≈ $${(a / SAR_RATE).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return `≈ ${Math.round(a * SAR_RATE).toLocaleString("en-US")} ر.س`;
};

export const STATUS = {
  blue: { label: "قيد التسجيل", cls: "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]" },
  yellow: { label: "تم إصدار التأشيرات", cls: "bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]" },
  green: { label: "تم التفويج", cls: "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]" },
  cancelled: { label: "ملغي", cls: "bg-gray-100 text-gray-500 border-gray-200" },
};

export const PKG_TYPE = { umrah: "عمرة", tourism: "سياحة" };

// Enterprise P2P approval lifecycle (rahal bookings)
export const APPROVAL = {
  pending: { label: "بانتظار موافقة البائع", cls: "bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]" },
  approved: { label: "معتمد", cls: "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]" },
  rejected: { label: "مرفوض", cls: "bg-red-50 text-red-600 border-red-200" },
  expired: { label: "منتهي المهلة", cls: "bg-gray-100 text-gray-500 border-gray-200" },
};

export const CANCELLATION = {
  requested: { label: "طلب إلغاء قيد المراجعة", cls: "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" },
  withdrawn: { label: "طلب مسحوب", cls: "bg-gray-100 text-gray-500 border-gray-200" },
  decided: { label: "أُلغي بقرار الإدارة", cls: "bg-gray-100 text-gray-500 border-gray-200" },
  rejected: { label: "رُفض الإلغاء (نشط)", cls: "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]" },
  expired: { label: "منتهي", cls: "bg-gray-100 text-gray-500 border-gray-200" },
};

// Audit-trail event codes → Arabic (fallback to raw code)
export const EVENT_LABELS = {
  booking_created: "تم إنشاء الحجز",
  booking_requested: "تم إرسال طلب الحجز (بانتظار الموافقة)",
  seller_approved: "وافق صاحب الباكيج على الحجز",
  seller_rejected: "رفض صاحب الباكيج الحجز",
  buyer_withdrew: "سحب المشتري الطلب",
  cancellation_requested: "طلب إلغاء من المشتري",
  rahal_position: "استلام موقف صاحب الباكيج بشأن الإلغاء",
  cancellation_cancelled: "قرار الإدارة: إلغاء الحجز وتسوية المبالغ",
  cancellation_kept: "قرار الإدارة: إبقاء الحجز نشطاً",
  auto_expired: "انتهت مهلة الموافقة تلقائياً",
};

export const ACTOR_LABELS = {
  buyer: "المشتري", seller: "البائع", rahal_owner: "صاحب الباكيج",
  super_admin: "الإدارة", system: "النظام",
};

export const fmtDateTime = (s) => {
  if (!s) return "-";
  try {
    return new Date(s).toLocaleString("ar-EG", {
      year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch { return s; }
};

// Rahal sends room_pricing[].customer as an object {adult, child, infant}.
// Manual (Meraaj) programs store it as a plain number (adult only). Support both.
export const roomCustomer = (customer, cat = "adult") => {
  if (customer == null) return null;
  const toNum = (v) => {
    if (v == null) return null;
    const n = Number(v);
    return Number.isNaN(n) ? null : n;
  };
  if (typeof customer === "object") {
    const v = customer[cat] != null ? customer[cat] : customer.adult; // fall back to adult
    return toNum(v);
  }
  return cat === "adult" ? toNum(customer) : null;
};

// Internal code → Arabic label for display (DB values never change).
export const VALUE_AR = {
  active: "نشط", cancelled: "ملغي", completed: "مكتمل", pending: "قيد الانتظار",
  requested: "مطلوب", approved: "معتمد", rejected: "مرفوض", expired: "منتهي",
  legacy: "طلب قديم (تم قبل تفعيل الموافقات)", draft: "مسودة", listed: "معروض",
  archived: "مؤرشف", suspended: "موقوف", paid: "مدفوع", closed: "مغلق",
  blue: "قيد التسجيل", yellow: "صدرت التأشيرات", green: "تم التفويج",
  office: "مكتب", individual: "فرد", marketer: "مسوّق", staff: "موظف",
  super_admin: "الإدارة العليا", admin: "إدارة", rahal: "رحّال", meraaj: "معراج",
  manual: "يدوي", uploaded: "مستوردة", success: "ناجحة", failed: "فاشلة",
  valid: "سليمة", invalid: "غير سليمة", percent: "نسبة", fixed: "قيمة ثابتة",
  delivered: "مُسلَّم", under_review: "قيد المراجعة", executed: "منفّذ",
  preview: "بيئة المعاينة", test: "بيئة الاختبار", live: "البيئة الحقيقية",
  unknown: "غير محددة", promotion: "عرض ترويجي", ad: "إعلان",
  pending_approval: "بانتظار الاعتماد", paused: "موقوف مؤقتاً",
};

export const ar = (v) => {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "نعم" : "لا";
  return VALUE_AR[String(v).trim()] || String(v);
};

export const CCY_AR = { SAR: "ريال سعودي", USD: "دولار أمريكي", YER: "ريال يمني" };

export const fmtDate = (s) => {
  if (!s) return "-";
  try { return new Date(s).toLocaleDateString("ar-EG", { year: "numeric", month: "short", day: "numeric" }); }
  catch { return s; }
};
