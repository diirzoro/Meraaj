import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { Search, FileWarning, Copy, CalendarX, Users, Trash2, Download } from "lucide-react";

const PP_CLASS = {
  ok: "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]",
  warning: "bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]",
  expired: "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]",
  unknown: "bg-[#F4F6F8] text-[#64748B] border-[#E2E8F0]",
};

export default function AdminTravelers() {
  const [f, setF] = useState({ q: "", missing_only: false, passport_issue: false, duplicates_only: false, page: 1 });
  const [d, setD] = useState({ items: [], total: 0, stats: {}, limits: {} });
  const [detail, setDetail] = useState(null);
  const [del, setDel] = useState(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    const p = new URLSearchParams({ page: String(f.page), limit: "25" });
    if (f.q) p.set("q", f.q);
    ["missing_only", "passport_issue", "duplicates_only"].forEach((k) => { if (f[k]) p.set(k, "true"); });
    api.get(`/admin/travelers?${p}`).then((r) => setD(r.data));
  }, [f]);
  useEffect(() => { load(); }, [load]);

  const doDelete = async () => {
    setBusy(true);
    try {
      await api.post(`/admin/documents/${del.id}/delete`, { reason });
      toast.success("تم حذف المستند وتسجيله في سجل التدقيق");
      setDel(null); setReason(""); setDetail(null); load();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const pages = Math.max(1, Math.ceil(d.total / 25));

  return (
    <>
      <PageHeader title="المسافرون والمستندات" subtitle="ملف موحّد لكل مسافر مرتبط بالطلب والبرنامج والجواز — مع كشف الناقص والتكرار وانتهاء الجوازات" />

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-5">
        <Stat icon={Users} label="المسافرون" v={d.stats.travelers || 0} tid="stat-travelers" />
        <Stat icon={FileWarning} label="مستندات ناقصة" v={d.stats.with_missing_docs || 0} danger tid="stat-missing" />
        <Stat icon={CalendarX} label="جوازات منتهية" v={d.stats.expired_passports || 0} danger tid="stat-expired" />
        <Stat icon={CalendarX} label="تنتهي قريباً" v={d.stats.expiring_passports || 0} tid="stat-expiring" />
        <Stat icon={Copy} label="تكرار" v={d.stats.duplicates || 0} tid="stat-duplicates" />
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-4 mb-5 flex flex-wrap gap-3 items-center" data-testid="travelers-filters">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="w-4 h-4 absolute top-2.5 right-3 text-muted-foreground" />
          <input value={f.q} onChange={(e) => setF({ ...f, q: e.target.value, page: 1 })} data-testid="travelers-search"
            placeholder="ابحث بالاسم أو رقم الجواز أو البرنامج"
            className="w-full h-9 rounded-md border border-input pr-9 pl-3 text-xs" />
        </div>
        {[["missing_only", "مستندات ناقصة"], ["passport_issue", "مشاكل جوازات"], ["duplicates_only", "تكرار"]].map(([k, l]) => (
          <label key={k} className="text-xs inline-flex items-center gap-1.5 h-9 px-3 rounded-md border cursor-pointer" data-testid={`filter-${k}`}>
            <input type="checkbox" checked={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.checked, page: 1 })} /> {l}
          </label>
        ))}
        <span className="text-[11px] text-muted-foreground mr-auto">
          الحد: {d.limits.per_file_mb || 10}MB للملف • {d.limits.per_batch_mb || 20}MB للدفعة
        </span>
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto" data-testid="travelers-table">
        <table className="w-full text-xs min-w-[820px]">
          <thead className="bg-[#F4F6F8] text-muted-foreground">
            <tr>{["المسافر", "رقم الجواز", "الفئة", "الطلبات", "المستندات", "الناقص", "حالة الجواز", ""].map((h) => (
              <th key={h} className="text-right font-semibold px-3 py-2.5">{h}</th>))}</tr>
          </thead>
          <tbody>
            {d.items.length === 0 ? (
              <tr><td colSpan={8} className="text-center py-12 text-muted-foreground" data-testid="travelers-empty">لا توجد نتائج</td></tr>
            ) : d.items.map((t) => (
              <tr key={t.key} className="border-t hover:bg-[#FAFBFC]" data-testid={`traveler-row-${t.key}`}>
                <td className="px-3 py-2.5 font-semibold text-[#0A2540]">{t.name}
                  {t.is_duplicate && <span className="mr-1.5 text-[9px] px-1.5 py-0.5 rounded bg-[#EFF6FF] text-[#1D4ED8]">مكرر</span>}
                </td>
                <td className="px-3 py-2.5 font-mono text-[11px]">{t.passport_no || "—"}</td>
                <td className="px-3 py-2.5">{t.category}</td>
                <td className="px-3 py-2.5 tabular">{t.bookings_count}</td>
                <td className="px-3 py-2.5 tabular">{t.documents_count}</td>
                <td className="px-3 py-2.5">
                  {t.missing_labels.length ? (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#FEF2F2] text-[#B91C1C] border border-[#FECACA]">
                      {t.missing_labels.join(" / ")}
                    </span>) : <span className="text-[#15803D]">مكتمل</span>}
                </td>
                <td className="px-3 py-2.5">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full border ${PP_CLASS[t.passport_status.level]}`}>
                    {t.passport_status.label}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  <button onClick={() => setDetail(t)} data-testid={`traveler-open-${t.key}`} className="text-[#0A2540] underline font-semibold">الملف</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-5" data-testid="travelers-pagination">
          <button disabled={f.page <= 1} onClick={() => setF({ ...f, page: f.page - 1 })} data-testid="travelers-prev"
            className="h-8 px-3 rounded-md border text-xs disabled:opacity-40">السابق</button>
          <span className="text-xs tabular">صفحة {f.page} من {pages} • {d.total}</span>
          <button disabled={f.page >= pages} onClick={() => setF({ ...f, page: f.page + 1 })} data-testid="travelers-next"
            className="h-8 px-3 rounded-md border text-xs disabled:opacity-40">التالي</button>
        </div>
      )}

      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent dir="rtl" className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="traveler-dialog">
          <DialogHeader><DialogTitle>ملف المسافر — {detail?.name}</DialogTitle></DialogHeader>
          {detail && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <Box label="رقم الجواز" v={detail.passport_no || "—"} />
                <Box label="الفئة" v={detail.category} />
                <Box label="انتهاء الجواز" v={detail.passport_expiry || "غير مسجّل"} />
                <Box label="عدد الطلبات" v={detail.bookings_count} />
              </div>
              {detail.bookings.map((b, i) => (
                <div key={i} className="border rounded-xl p-3" data-testid={`traveler-booking-${b.booking_id}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm font-semibold text-[#0A2540]">{b.package_title}</div>
                    <Link to={`/admin/orders/${b.booking_id}`} className="text-[11px] text-[#0A2540] underline">فتح الطلب</Link>
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">
                    {b.buyer} ← {b.seller} • انطلاق {fmtDate(b.departure_date)} • الحالة {b.status}
                  </div>
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {b.documents.map((doc) => (
                      <span key={doc.id} className="text-[10px] px-2 py-1 rounded bg-[#F4F6F8] text-[#0A2540] inline-flex items-center gap-1.5"
                        data-testid={`doc-${doc.id}`}>
                        {doc.label}: {doc.filename}
                        <a href={`${process.env.REACT_APP_BACKEND_URL}/api/documents/${doc.id}/download`} target="_blank" rel="noreferrer"
                          className="text-[#0A2540]" data-testid={`doc-download-${doc.id}`}><Download className="w-3 h-3" /></a>
                        <button onClick={() => setDel(doc)} data-testid={`doc-delete-${doc.id}`} className="text-[#B91C1C]">
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                    {b.missing.length > 0 && (
                      <span className="text-[10px] px-2 py-1 rounded bg-[#FEF2F2] text-[#B91C1C] border border-[#FECACA]">
                        ناقص: {b.missing.map((m) => d.doc_labels[m] || m).join(" / ")}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!del} onOpenChange={(o) => !o && setDel(null)}>
        <DialogContent dir="rtl" className="max-w-md" data-testid="doc-delete-dialog">
          <DialogHeader><DialogTitle>حذف نهائي للمستند</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="text-xs bg-[#FEF2F2] text-[#B91C1C] border border-[#FECACA] rounded-lg px-3 py-2">
              {del?.filename} — الحذف نهائي ويُسجَّل في سجل التدقيق باسمك.
            </div>
            <div><Label className="text-xs">السبب (إلزامي — 5 أحرف على الأقل)</Label>
              <Textarea rows={2} value={reason} data-testid="doc-delete-reason" onChange={(e) => setReason(e.target.value)} /></div>
            <Button className="w-full bg-[#B91C1C] hover:bg-[#991B1B]" data-testid="confirm-doc-delete"
              disabled={busy || reason.trim().length < 5} onClick={doDelete}>حذف نهائي</Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

const Stat = ({ icon: Icon, label, v, danger, tid }) => (
  <div className="bg-white rounded-2xl border p-4 card-shadow flex items-center gap-3" data-testid={tid}>
    <div className="w-9 h-9 rounded-xl bg-[#F4F6F8] flex items-center justify-center">
      <Icon className={`w-4 h-4 ${danger ? "text-[#B91C1C]" : "text-[#0A2540]"}`} />
    </div>
    <div><div className="tabular text-lg font-bold text-[#0A2540]">{v}</div><div className="text-[11px] text-muted-foreground">{label}</div></div>
  </div>
);

const Box = ({ label, v }) => (
  <div className="bg-[#F4F6F8] rounded-lg px-3 py-2">
    <div className="text-[10px] text-muted-foreground">{label}</div>
    <div className="text-sm font-bold text-[#0A2540] break-words">{v}</div>
  </div>
);
