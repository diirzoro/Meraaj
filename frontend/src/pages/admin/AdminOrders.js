import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
import { Link, useSearchParams } from "react-router-dom";
import { Search, RotateCcw, ChevronLeft, ChevronRight, AlertTriangle } from "lucide-react";

export const STATUS_LABEL = {
  blue: "حجز جديد", yellow: "تم إصدار التأشيرة", green: "تم التفويج", cancelled: "ملغى",
};
export const STATUS_CLASS = {
  blue: "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]",
  yellow: "bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]",
  green: "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]",
  cancelled: "bg-[#F4F6F8] text-[#64748B] border-[#E2E8F0]",
};
export const APPROVAL_LABEL = {
  pending: "بانتظار البائع", approved: "مقبول", rejected: "مرفوض", expired: "منتهي المهلة",
};

export default function AdminOrders() {
  const [sp, setSp] = useSearchParams();
  const [data, setData] = useState({ items: [], total: 0, amount_totals: { SAR: 0, USD: 0 } });
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState(sp.get("q") || "");

  const get = (k) => sp.get(k) || "";
  const page = Number(sp.get("page") || 1);

  const setParam = (k, v) => {
    const n = new URLSearchParams(sp);
    if (v) n.set(k, v); else n.delete(k);
    if (k !== "page") n.delete("page");
    setSp(n);
  };

  const load = useCallback(() => {
    setLoading(true);
    const p = new URLSearchParams(sp);
    if (!p.get("limit")) p.set("limit", "25");
    api.get(`/admin/bookings?${p.toString()}`)
      .then((r) => setData(r.data)).finally(() => setLoading(false));
  }, [sp]);
  useEffect(() => { load(); }, [load]);

  const reset = () => { setQ(""); setSp(new URLSearchParams()); };
  const limit = Number(sp.get("limit") || 25);
  const pages = Math.max(1, Math.ceil(data.total / limit));

  return (
    <>
      <PageHeader title="مركز إدارة الطلبات" subtitle="بحث وتصفية متقدمة لكل الحجوزات مع الوصول إلى تفاصيل الطلب وسجل الإجراءات" />

      <div className="bg-white rounded-2xl border card-shadow p-4 mb-5" data-testid="orders-filters">
        <div className="flex flex-wrap gap-3 items-end">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="w-4 h-4 absolute top-2.5 right-3 text-muted-foreground" />
            <input value={q} onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && setParam("q", q)}
              placeholder="ابحث برقم الطلب، البرنامج، المكتب، اسم المسافر أو رقم الجواز"
              data-testid="orders-search"
              className="w-full h-9 rounded-md border border-input pr-9 pl-3 text-xs" />
          </div>
          <Sel label="الحالة" v={get("status")} onChange={(v) => setParam("status", v)} tid="filter-status"
            opts={[["", "كل الحالات"], ["blue", "حجز جديد"], ["yellow", "تأشيرة صادرة"], ["green", "تم التفويج"], ["cancelled", "ملغى"]]} />
          <Sel label="قرار البائع" v={get("approval_status")} onChange={(v) => setParam("approval_status", v)} tid="filter-approval"
            opts={[["", "الكل"], ["pending", "بانتظار البائع"], ["approved", "مقبول"], ["rejected", "مرفوض"], ["expired", "منتهي المهلة"]]} />
          <Sel label="العملة" v={get("currency")} onChange={(v) => setParam("currency", v)} tid="filter-currency"
            opts={[["", "الكل"], ["SAR", "ريال"], ["USD", "دولار"]]} />
          <Sel label="المصدر" v={get("source")} onChange={(v) => setParam("source", v)} tid="filter-source"
            opts={[["", "الكل"], ["rahal", "رحّال"], ["meraaj", "معراج"]]} />
          <Sel label="الترتيب" v={get("sort")} onChange={(v) => setParam("sort", v)} tid="filter-sort"
            opts={[["newest", "الأحدث"], ["oldest", "الأقدم"], ["amount_desc", "الأعلى مبلغاً"], ["amount_asc", "الأقل مبلغاً"], ["departure_asc", "الأقرب سفراً"]]} />
          <Dt label="من تاريخ" v={get("date_from")} onChange={(v) => setParam("date_from", v)} tid="filter-from" />
          <Dt label="إلى تاريخ" v={get("date_to")} onChange={(v) => setParam("date_to", v)} tid="filter-to" />
          <label className="text-xs inline-flex items-center gap-1.5 h-9 px-3 rounded-md border cursor-pointer" data-testid="filter-attention">
            <input type="checkbox" checked={get("attention") === "1"}
              onChange={(e) => setParam("attention", e.target.checked ? "1" : "")} />
            تحتاج تدخلاً
          </label>
          <button onClick={() => setParam("q", q)} data-testid="orders-apply"
            className="h-9 px-4 rounded-md bg-[#0A2540] text-white text-xs font-semibold hover:bg-[#061A2E]">تطبيق</button>
          <button onClick={reset} data-testid="orders-reset"
            className="h-9 px-3 rounded-md border text-xs text-[#0A2540] inline-flex items-center gap-1.5"><RotateCcw className="w-3.5 h-3.5" /> تصفير</button>
        </div>
        <div className="text-[11px] text-muted-foreground mt-3" data-testid="orders-summary">
          النتائج: <span className="tabular font-bold text-[#0A2540]">{data.total}</span> طلب •
          إجمالي المبالغ: <span className="tabular font-bold">{money(data.amount_totals.SAR, "SAR")}</span> +
          <span className="tabular font-bold"> {money(data.amount_totals.USD, "USD")}</span>
        </div>
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto" data-testid="orders-table">
        <table className="w-full text-xs min-w-[900px]">
          <thead className="bg-[#F4F6F8] text-muted-foreground">
            <tr>
              {["الطلب", "البرنامج", "المشتري", "البائع", "المقاعد", "المبلغ", "الحالة", "قرار البائع", "الانطلاق", ""].map((h) => (
                <th key={h} className="text-right font-semibold px-3 py-2.5 whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={10} className="text-center py-12 text-muted-foreground">جارٍ التحميل...</td></tr>
            ) : data.items.length === 0 ? (
              <tr><td colSpan={10} className="text-center py-12 text-muted-foreground" data-testid="orders-empty">لا توجد طلبات مطابقة</td></tr>
            ) : data.items.map((b) => (
              <tr key={b.id} className="border-t hover:bg-[#FAFBFC]" data-testid={`order-row-${b.id}`}>
                <td className="px-3 py-2.5 font-mono text-[10px]">{b.id.slice(-6)}</td>
                <td className="px-3 py-2.5 font-semibold text-[#0A2540] max-w-[180px] truncate">
                  {b.package_title}
                  {b.rahal_ref && <span className="mr-1 text-[9px] px-1.5 py-0.5 rounded bg-[#FEFCE8] text-[#A16207]">رحّال</span>}
                </td>
                <td className="px-3 py-2.5">{b.buyer_office_name}</td>
                <td className="px-3 py-2.5">{b.seller_office_name}</td>
                <td className="px-3 py-2.5 tabular">{b.seats}</td>
                <td className="px-3 py-2.5 tabular font-bold">{money(b.gross_total, b.currency)}</td>
                <td className="px-3 py-2.5">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold whitespace-nowrap ${STATUS_CLASS[b.status] || ""}`}>
                    {STATUS_LABEL[b.status] || b.status}
                  </span>
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">{APPROVAL_LABEL[b.approval_status] || "—"}</td>
                <td className="px-3 py-2.5 whitespace-nowrap">{fmtDate(b.departure_date)}</td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  {b.needs_attention && (
                    <span className={`inline-flex items-center gap-1 text-[10px] font-semibold ${b.severity === "critical" ? "text-[#B91C1C]" : "text-[#A16207]"}`}
                      title={b.attention_reasons.join(" • ")}>
                      <AlertTriangle className="w-3 h-3" /> تدخل
                    </span>
                  )}
                  <Link to={`/admin/orders/${b.id}`} data-testid={`order-open-${b.id}`}
                    className="mr-2 text-[#0A2540] font-semibold underline">تفاصيل</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-5" data-testid="orders-pagination">
          <button disabled={page <= 1} onClick={() => setParam("page", String(page - 1))}
            data-testid="page-prev" className="h-8 px-3 rounded-md border text-xs disabled:opacity-40 inline-flex items-center gap-1">
            <ChevronRight className="w-3.5 h-3.5" /> السابق
          </button>
          <span className="text-xs tabular">صفحة {page} من {pages}</span>
          <button disabled={page >= pages} onClick={() => setParam("page", String(page + 1))}
            data-testid="page-next" className="h-8 px-3 rounded-md border text-xs disabled:opacity-40 inline-flex items-center gap-1">
            التالي <ChevronLeft className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </>
  );
}

const Sel = ({ label, v, onChange, opts, tid }) => (
  <label className="text-[11px] text-muted-foreground">
    {label}
    <select value={v} onChange={(e) => onChange(e.target.value)} data-testid={tid}
      className="block h-9 rounded-md border border-input px-2 text-xs mt-1 min-w-[120px]">
      {opts.map(([val, l]) => <option key={val} value={val}>{l}</option>)}
    </select>
  </label>
);

const Dt = ({ label, v, onChange, tid }) => (
  <label className="text-[11px] text-muted-foreground">
    {label}
    <input type="date" value={v} onChange={(e) => onChange(e.target.value)} data-testid={tid}
      className="block h-9 rounded-md border border-input px-2 text-xs mt-1" />
  </label>
);
