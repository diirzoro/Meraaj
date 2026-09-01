import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Search, Building2, Plus, Trash2 } from "lucide-react";

const RISK_CLASS = {
  low: "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]",
  medium: "bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]",
  high: "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]",
};
const RISK_LABEL = { low: "منخفض", medium: "متوسط", high: "مرتفع" };

export default function AdminOrgs() {
  const [f, setF] = useState({ q: "", status: "", risk: "", page: 1 });
  const [d, setD] = useState({ items: [], total: 0 });
  const [detail, setDetail] = useState(null);
  const [prof, setProf] = useState({ risk_class: "medium", account_manager: "", relationship_manager: "", notes: "", legal_docs: [], reason: "" });
  const [doc, setDoc] = useState({ type: "", number: "", expires_at: "" });
  const [branch, setBranch] = useState({ name: "", city: "", phone: "", manager: "" });
  const [staff, setStaff] = useState({ name: "", job_title: "", phone: "", email: "", branch_id: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    const p = new URLSearchParams({ page: String(f.page), limit: "25" });
    ["q", "status", "risk"].forEach((k) => { if (f[k]) p.set(k, f[k]); });
    api.get(`/admin/orgs?${p}`).then((r) => setD(r.data));
  }, [f]);
  useEffect(() => { load(); }, [load]);

  const open = async (id) => {
    const r = await api.get(`/admin/orgs/${id}`);
    setDetail(r.data);
    setProf({
      risk_class: r.data.profile?.risk_class || "medium",
      account_manager: r.data.profile?.account_manager || "",
      relationship_manager: r.data.profile?.relationship_manager || "",
      notes: r.data.profile?.notes || "",
      legal_docs: r.data.profile?.legal_docs || [], reason: "",
    });
  };

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); load(); if (detail) await open(detail.office.id); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const pages = Math.max(1, Math.ceil(d.total / 25));
  const o = detail?.office;

  return (
    <>
      <PageHeader title="المؤسسات والمكاتب" subtitle="ملف شامل لكل مؤسسة: الحالة القانونية والتشغيلية والمالية، الفروع والموظفون، وتصنيف المخاطر" />

      <div className="bg-white rounded-2xl border card-shadow p-4 mb-5 flex flex-wrap gap-3 items-center" data-testid="orgs-filters">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="w-4 h-4 absolute top-2.5 right-3 text-muted-foreground" />
          <input value={f.q} onChange={(e) => setF({ ...f, q: e.target.value, page: 1 })} data-testid="orgs-search"
            placeholder="ابحث بالاسم أو البريد أو رقم السجل" className="w-full h-9 rounded-md border border-input pr-9 pl-3 text-xs" />
        </div>
        <select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value, page: 1 })} data-testid="orgs-status"
          className="h-9 rounded-md border border-input px-2 text-xs">
          <option value="">كل الحالات</option><option value="active">مفعّل</option><option value="suspended">موقوف</option>
        </select>
        <select value={f.risk} onChange={(e) => setF({ ...f, risk: e.target.value, page: 1 })} data-testid="orgs-risk"
          className="h-9 rounded-md border border-input px-2 text-xs">
          <option value="">كل التصنيفات</option><option value="low">مخاطر منخفضة</option>
          <option value="medium">متوسطة</option><option value="high">مرتفعة</option>
        </select>
        <span className="text-[11px] text-muted-foreground mr-auto" data-testid="orgs-count">{d.total} مؤسسة</span>
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto" data-testid="orgs-table">
        <table className="w-full text-xs min-w-[900px]">
          <thead className="bg-[#F4F6F8] text-muted-foreground">
            <tr>{["المؤسسة", "المالك", "المحافظة", "المخاطر", "الفروع", "الموظفون", "الطلبات", "نزاعات", "الرصيد", ""].map((h) => (
              <th key={h} className="text-right font-semibold px-3 py-2.5">{h}</th>))}</tr>
          </thead>
          <tbody>
            {d.items.length === 0 ? (
              <tr><td colSpan={10} className="text-center py-12 text-muted-foreground" data-testid="orgs-empty">لا توجد نتائج</td></tr>
            ) : d.items.map((x) => (
              <tr key={x.id} className="border-t hover:bg-[#FAFBFC]" data-testid={`org-row-${x.id}`}>
                <td className="px-3 py-2.5 font-semibold text-[#0A2540]">{x.name}
                  {x.is_rahal && <span className="mr-1 text-[9px] px-1.5 py-0.5 rounded bg-[#FEFCE8] text-[#A16207]">رحّال</span>}
                  {x.status !== "active" && <span className="mr-1 text-[9px] px-1.5 py-0.5 rounded bg-[#FEF2F2] text-[#B91C1C]">موقوف</span>}
                </td>
                <td className="px-3 py-2.5">{x.owner}</td>
                <td className="px-3 py-2.5">{x.governorate}</td>
                <td className="px-3 py-2.5">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full border ${RISK_CLASS[x.risk_class]}`}>{RISK_LABEL[x.risk_class]}</span>
                </td>
                <td className="px-3 py-2.5 tabular">{x.branches_count}</td>
                <td className="px-3 py-2.5 tabular">{x.staff_count}</td>
                <td className="px-3 py-2.5 tabular">{x.bookings_count}</td>
                <td className={`px-3 py-2.5 tabular ${x.open_disputes ? "text-[#B91C1C] font-bold" : ""}`}>{x.open_disputes}</td>
                <td className="px-3 py-2.5 tabular text-[10px]">{money(x.balance.SAR, "SAR")}<br />{money(x.balance.USD, "USD")}</td>
                <td className="px-3 py-2.5">
                  <button onClick={() => open(x.id)} data-testid={`org-open-${x.id}`} className="text-[#0A2540] underline font-semibold">الملف</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-5" data-testid="orgs-pagination">
          <button disabled={f.page <= 1} onClick={() => setF({ ...f, page: f.page - 1 })} data-testid="orgs-prev"
            className="h-8 px-3 rounded-md border text-xs disabled:opacity-40">السابق</button>
          <span className="text-xs tabular">صفحة {f.page} من {pages}</span>
          <button disabled={f.page >= pages} onClick={() => setF({ ...f, page: f.page + 1 })} data-testid="orgs-next"
            className="h-8 px-3 rounded-md border text-xs disabled:opacity-40">التالي</button>
        </div>
      )}

      <Dialog open={!!detail} onOpenChange={(v) => !v && setDetail(null)}>
        <DialogContent dir="rtl" className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="org-dialog">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Building2 className="w-4 h-4" /> {o?.office_name}</DialogTitle></DialogHeader>
          {o && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <Box label="البريد" v={o.email} />
                <Box label="الهاتف" v={o.phone} />
                <Box label="السجل التجاري" v={o.commercial_license || "—"} />
                <Box label="الحالة" v={o.status} />
              </div>

              <div className="border-t pt-3">
                <div className="text-xs font-semibold text-[#0A2540] mb-2">الملف التشغيلي والمخاطر</div>
                <div className="grid sm:grid-cols-2 gap-2">
                  <div><Label className="text-[11px]">تصنيف المخاطر</Label>
                    <select value={prof.risk_class} onChange={(e) => setProf({ ...prof, risk_class: e.target.value })}
                      data-testid="org-risk" className="w-full h-8 rounded-md border border-input px-2 text-xs bg-white">
                      <option value="low">منخفض</option><option value="medium">متوسط</option><option value="high">مرتفع</option>
                    </select></div>
                  <div><Label className="text-[11px]">مسؤول الحساب</Label>
                    <Input className="h-8 text-xs" value={prof.account_manager} data-testid="org-am"
                      onChange={(e) => setProf({ ...prof, account_manager: e.target.value })} /></div>
                  <div><Label className="text-[11px]">مدير العلاقة</Label>
                    <Input className="h-8 text-xs" value={prof.relationship_manager} data-testid="org-rm"
                      onChange={(e) => setProf({ ...prof, relationship_manager: e.target.value })} /></div>
                  <div><Label className="text-[11px]">ملاحظات</Label>
                    <Input className="h-8 text-xs" value={prof.notes} data-testid="org-notes"
                      onChange={(e) => setProf({ ...prof, notes: e.target.value })} /></div>
                </div>

                <div className="mt-3">
                  <div className="text-[11px] font-semibold text-[#0A2540] mb-1">المستندات القانونية وتواريخ انتهائها</div>
                  <div className="flex flex-wrap gap-2 mb-2">
                    {prof.legal_docs.map((x, i) => {
                      const expired = x.expires_at && x.expires_at < new Date().toISOString().slice(0, 10);
                      return (
                        <span key={i} data-testid={`legal-doc-${i}`}
                          className={`text-[10px] px-2 py-1 rounded border inline-flex items-center gap-1.5 ${expired ? "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" : "bg-[#F4F6F8] text-[#0A2540]"}`}>
                          {x.type} {x.number} • {x.expires_at || "بدون تاريخ"}
                          <button onClick={() => setProf({ ...prof, legal_docs: prof.legal_docs.filter((_, j) => j !== i) })}
                            data-testid={`remove-legal-${i}`}><Trash2 className="w-3 h-3" /></button>
                        </span>);
                    })}
                  </div>
                  <div className="flex gap-2">
                    <Input placeholder="النوع (سجل/رخصة)" className="h-8 text-xs" value={doc.type} data-testid="legal-type"
                      onChange={(e) => setDoc({ ...doc, type: e.target.value })} />
                    <Input placeholder="الرقم" className="h-8 text-xs" value={doc.number} data-testid="legal-number"
                      onChange={(e) => setDoc({ ...doc, number: e.target.value })} />
                    <Input type="date" className="h-8 text-xs" value={doc.expires_at} data-testid="legal-expiry"
                      onChange={(e) => setDoc({ ...doc, expires_at: e.target.value })} />
                    <Button size="sm" variant="outline" data-testid="add-legal-btn" disabled={!doc.type}
                      onClick={() => { setProf({ ...prof, legal_docs: [...prof.legal_docs, doc] }); setDoc({ type: "", number: "", expires_at: "" }); }}>
                      <Plus className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>

                <Label className="text-[11px] mt-2 block">سبب التعديل (إلزامي)</Label>
                <Textarea rows={2} className="text-xs" value={prof.reason} data-testid="org-reason"
                  onChange={(e) => setProf({ ...prof, reason: e.target.value })} />
                <Button size="sm" className="mt-2 bg-[#0A2540] hover:bg-[#061A2E]" data-testid="save-org-btn"
                  disabled={busy || prof.reason.trim().length < 3}
                  onClick={() => act(() => api.post(`/admin/orgs/${o.id}/profile`, prof), "تم حفظ الملف")}>حفظ</Button>
              </div>

              <div className="border-t pt-3">
                <div className="text-xs font-semibold text-[#0A2540] mb-2">الفروع ({detail.branches.length})</div>
                {detail.branches.map((b) => (
                  <div key={b.id} className="text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-1.5 mb-1 flex justify-between" data-testid={`branch-${b.id}`}>
                    <span>{b.name} — {b.city} • مدير: {b.manager || "—"}</span>
                    <button className="text-[#B91C1C]" data-testid={`del-branch-${b.id}`}
                      onClick={() => act(() => api.delete(`/admin/branches/${b.id}`), "تم حذف الفرع")}>حذف</button>
                  </div>
                ))}
                <div className="flex flex-wrap gap-2 mt-2">
                  <Input placeholder="اسم الفرع" className="h-8 text-xs flex-1" value={branch.name} data-testid="branch-name"
                    onChange={(e) => setBranch({ ...branch, name: e.target.value })} />
                  <Input placeholder="المدينة" className="h-8 text-xs w-28" value={branch.city} data-testid="branch-city"
                    onChange={(e) => setBranch({ ...branch, city: e.target.value })} />
                  <Input placeholder="المدير" className="h-8 text-xs w-28" value={branch.manager} data-testid="branch-manager"
                    onChange={(e) => setBranch({ ...branch, manager: e.target.value })} />
                  <Button size="sm" variant="outline" data-testid="add-branch-btn" disabled={busy || branch.name.length < 2}
                    onClick={() => act(async () => { await api.post(`/admin/orgs/${o.id}/branches`, branch); setBranch({ name: "", city: "", phone: "", manager: "" }); }, "تمت إضافة الفرع")}>
                    إضافة فرع
                  </Button>
                </div>
              </div>

              <div className="border-t pt-3">
                <div className="text-xs font-semibold text-[#0A2540] mb-2">الموظفون ({detail.staff.length})</div>
                {detail.staff.map((s) => (
                  <div key={s.id} className="text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-1.5 mb-1 flex justify-between" data-testid={`staff-${s.id}`}>
                    <span>{s.name} — {s.job_title || "—"} • {s.email || s.phone || ""}</span>
                    <button className="text-[#B91C1C]" data-testid={`del-staff-${s.id}`}
                      onClick={() => act(() => api.delete(`/admin/staff/${s.id}`), "تم حذف الموظف")}>حذف</button>
                  </div>
                ))}
                <div className="flex flex-wrap gap-2 mt-2">
                  <Input placeholder="الاسم" className="h-8 text-xs flex-1" value={staff.name} data-testid="staff-name"
                    onChange={(e) => setStaff({ ...staff, name: e.target.value })} />
                  <Input placeholder="المسمى" className="h-8 text-xs w-28" value={staff.job_title} data-testid="staff-title"
                    onChange={(e) => setStaff({ ...staff, job_title: e.target.value })} />
                  <Input placeholder="البريد" className="h-8 text-xs w-40" value={staff.email} data-testid="staff-email"
                    onChange={(e) => setStaff({ ...staff, email: e.target.value })} />
                  <Button size="sm" variant="outline" data-testid="add-staff-btn" disabled={busy || staff.name.length < 2}
                    onClick={() => act(async () => { await api.post(`/admin/orgs/${o.id}/staff`, staff); setStaff({ name: "", job_title: "", phone: "", email: "", branch_id: "" }); }, "تمت إضافة الموظف")}>
                    إضافة موظف
                  </Button>
                </div>
                <div className="text-[10px] text-muted-foreground mt-2">
                  ملاحظة: سجلات الموظفين إدارية. منح الموظف حساب دخول يشارك محفظة المكتب يتطلب فصل الكيانات المذكور في DEV_NOTES.
                </div>
              </div>

              <div className="border-t pt-3 grid sm:grid-cols-2 gap-3">
                <div>
                  <div className="text-xs font-semibold text-[#0A2540] mb-1">آخر الطلبات</div>
                  {detail.recent_bookings.slice(0, 6).map((b) => (
                    <div key={b.id} className="text-[11px] bg-[#F4F6F8] rounded px-2 py-1 mb-1">
                      {b.package_title} • {money(b.amount_charged, b.currency)} • {b.status}
                    </div>
                  ))}
                </div>
                <div>
                  <div className="text-xs font-semibold text-[#0A2540] mb-1">آخر الحركات المالية</div>
                  {detail.recent_transactions.slice(0, 6).map((t) => (
                    <div key={t.id} className="text-[11px] bg-[#F4F6F8] rounded px-2 py-1 mb-1">
                      {t.description} • {money(t.amount, t.currency)} • {fmtDate(t.created_at)}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

const Box = ({ label, v }) => (
  <div className="bg-[#F4F6F8] rounded-lg px-3 py-2">
    <div className="text-[10px] text-muted-foreground">{label}</div>
    <div className="text-sm font-bold text-[#0A2540] break-words">{v}</div>
  </div>
);
