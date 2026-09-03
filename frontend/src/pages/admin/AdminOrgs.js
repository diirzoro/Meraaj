import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Search, Building2, Plus, Trash2, RefreshCw, MessageCircle } from "lucide-react";

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
  const [resyncing, setResyncing] = useState(false);
  const [newOrg, setNewOrg] = useState(null);
  const [editOrg, setEditOrg] = useState(null);
  const [editBranch, setEditBranch] = useState(null);
  const [editStaff, setEditStaff] = useState(null);
  const [cat, setCat] = useState({ roles: {} });

  useEffect(() => { api.get("/admin/rbac/catalog").then((r) => setCat(r.data)); }, []);

  // Normalize a stored phone into a wa.me-ready international number (moved from /admin/offices)
  const waNumber = (raw) => {
    const digits = String(raw || "").replace(/\D/g, "").replace(/^0+/, "");
    return digits.length >= 8 ? digits : null;
  };

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

  const resync = async () => {
    if (resyncing) return;
    setResyncing(true);
    try {
      const r = await api.post("/admin/packages/resync");
      toast.success(`تمت إعادة المزامنة — حُدّث ${r.data.updated} برنامج، وأُرسل ${r.data.rahal_notified} إلى رحال`);
    } catch (e) { toast.error(apiError(e)); } finally { setResyncing(false); }
  };

  const setStatus = (id, status) =>
    act(() => api.patch(`/admin/offices/${id}/status`, { status }),
      status === "active" ? "تم التفعيل" : "تم الإيقاف");

  return (
    <>
      <PageHeader title="المؤسسات والمكاتب"
        subtitle="القسم الموحّد: الحالة القانونية والتشغيلية والمالية، الأرصدة بالريال والدولار، التفعيل والإيقاف، الفروع والموظفون، الائتمان والتعرّض، والطلبات والنزاعات"
        action={<div className="flex flex-wrap gap-2">
          <Button onClick={() => { setNewOrg({ office_name: "", owner_name: "", email: "", password: "", phone: "", governorate: "", commercial_license: "", reason: "" }); }}
            data-testid="new-org-btn" className="bg-[#15803D] hover:bg-[#166534]">
            <Plus className="w-4 h-4" /> مؤسسة/مكتب جديد
          </Button>
          <Button onClick={resync} disabled={resyncing} data-testid="batch-resync-btn"
            className="bg-[#0A2540] hover:bg-[#061A2E]">
            <RefreshCw className={`w-4 h-4 ${resyncing ? "animate-spin" : ""}`} />
            {resyncing ? "جارٍ المزامنة..." : "إعادة مزامنة الأسعار"}
          </Button>
        </div>} />

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
            <tr>{["المؤسسة", "المالك", "المحافظة", "المخاطر", "واتساب", "متاح (ريال)", "متاح (دولار)",
              "الفروع", "الموظفون", "الطلبات", "نزاعات", "الحالة", ""].map((h) => (
              <th key={h} className="text-right font-semibold px-3 py-2.5">{h}</th>))}</tr>
          </thead>
          <tbody>
            {d.items.length === 0 ? (
              <tr><td colSpan={13} className="text-center py-12 text-muted-foreground" data-testid="orgs-empty">لا توجد نتائج</td></tr>
            ) : d.items.map((x) => (
              <tr key={x.id} className="border-t hover:bg-[#FAFBFC]" data-testid={`org-row-${x.id}`}>
                <td className="px-3 py-2.5 font-semibold text-[#0A2540]">{x.name}
                  {x.is_rahal && <span className="mr-1 text-[9px] px-1.5 py-0.5 rounded bg-[#FEFCE8] text-[#A16207]">رحّال</span>}
                </td>
                <td className="px-3 py-2.5">{x.owner}</td>
                <td className="px-3 py-2.5">{x.governorate}</td>
                <td className="px-3 py-2.5">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full border ${RISK_CLASS[x.risk_class]}`}>{RISK_LABEL[x.risk_class]}</span>
                </td>
                <td className="px-3 py-2.5">
                  {waNumber(x.phone) ? (
                    <a href={`https://wa.me/${waNumber(x.phone)}?text=${encodeURIComponent(`مرحباً ${x.name || ""}، معك إدارة معراج نتورك`)}`}
                      target="_blank" rel="noopener noreferrer" data-testid={`whatsapp-${x.id}`}
                      className="inline-flex items-center gap-1 text-[#15803D] bg-[#F0FDF4] hover:bg-[#DCFCE7] border border-[#BBF7D0] px-2 py-1 rounded-lg text-[10px] font-semibold transition-colors">
                      <MessageCircle className="w-3 h-3" /> {waNumber(x.phone)}
                    </a>
                  ) : <span className="text-[10px] text-muted-foreground">—</span>}
                </td>
                <td className="px-3 py-2.5 tabular font-semibold text-[#0A2540]">{money(x.balance.SAR, "SAR")}</td>
                <td className="px-3 py-2.5 tabular font-semibold text-[#0A2540]">{money(x.balance.USD, "USD")}</td>
                <td className="px-3 py-2.5 tabular">{x.branches_count}</td>
                <td className="px-3 py-2.5 tabular">{x.staff_count}</td>
                <td className="px-3 py-2.5 tabular">{x.bookings_count}</td>
                <td className={`px-3 py-2.5 tabular ${x.open_disputes ? "text-[#B91C1C] font-bold" : ""}`}>{x.open_disputes}</td>
                <td className="px-3 py-2.5">
                  <span className={`text-[10px] px-2 py-0.5 rounded-md font-semibold ${x.status === "active" ? "bg-[#F0FDF4] text-[#15803D]" : "bg-[#FEF2F2] text-[#B91C1C]"}`}
                    data-testid={`org-status-${x.id}`}>{x.status === "active" ? "مفعّل" : "موقوف"}</span>
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <button onClick={() => open(x.id)} data-testid={`org-open-${x.id}`} className="text-[#0A2540] underline font-semibold ml-2">الملف</button>
                  {x.status === "active"
                    ? <button className="text-[#B91C1C] underline font-semibold" disabled={busy}
                      onClick={() => { if (window.confirm(`تأكيد إيقاف «${x.name}»؟`)) setStatus(x.id, "suspended"); }} data-testid={`suspend-${x.id}`}>إيقاف</button>
                    : <button className="text-[#15803D] underline font-semibold" disabled={busy}
                      onClick={() => { if (window.confirm(`تأكيد إعادة تفعيل «${x.name}»؟`)) setStatus(x.id, "active"); }} data-testid={`activate-${x.id}`}>تفعيل</button>}
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

      {/* Create organization */}
      <Dialog open={!!newOrg} onOpenChange={(o) => !o && setNewOrg(null)}>
        <DialogContent dir="rtl" className="max-w-lg" data-testid="new-org-dialog">
          <DialogHeader><DialogTitle>إنشاء مؤسسة/مكتب جديد</DialogTitle></DialogHeader>
          {newOrg && (
            <div className="grid sm:grid-cols-2 gap-2">
              {[["office_name", "اسم المكتب"], ["owner_name", "اسم المالك"], ["email", "بريد الدخول"],
                ["password", "كلمة المرور (8 أحرف على الأقل)"], ["phone", "الهاتف"],
                ["governorate", "المحافظة"], ["commercial_license", "السجل التجاري"]].map(([k, lab]) => (
                <div key={k}><Label className="text-[11px]">{lab}</Label>
                  <Input className="h-8 text-xs" type={k === "password" ? "password" : "text"}
                    value={newOrg[k]} data-testid={`neworg-${k}`}
                    onChange={(e) => setNewOrg({ ...newOrg, [k]: e.target.value })} /></div>
              ))}
              <div className="sm:col-span-2"><Label className="text-[11px]">سبب الإنشاء (إلزامي)</Label>
                <Textarea rows={2} className="text-xs" value={newOrg.reason} data-testid="neworg-reason"
                  onChange={(e) => setNewOrg({ ...newOrg, reason: e.target.value })} /></div>
              <Button className="sm:col-span-2 bg-[#0A2540] hover:bg-[#061A2E]" data-testid="create-org-btn"
                disabled={busy || newOrg.reason.trim().length < 3 || newOrg.office_name.length < 2
                  || newOrg.owner_name.length < 2 || newOrg.email.length < 5 || newOrg.password.length < 8}
                onClick={() => act(async () => { await api.post("/admin/orgs", newOrg); setNewOrg(null); },
                  "تم إنشاء المؤسسة وتسجيلها في سجل التدقيق")}>إنشاء</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Edit organization info */}
      <Dialog open={!!editOrg} onOpenChange={(o) => !o && setEditOrg(null)}>
        <DialogContent dir="rtl" className="max-w-lg" data-testid="edit-org-dialog">
          <DialogHeader><DialogTitle>تعديل بيانات المؤسسة</DialogTitle></DialogHeader>
          {editOrg && (
            <div className="grid sm:grid-cols-2 gap-2">
              {[["office_name", "اسم المكتب"], ["owner_name", "اسم المالك"], ["phone", "الهاتف"],
                ["governorate", "المحافظة"], ["commercial_license", "السجل التجاري"]].map(([k, lab]) => (
                <div key={k}><Label className="text-[11px]">{lab}</Label>
                  <Input className="h-8 text-xs" value={editOrg[k] || ""} data-testid={`editorg-${k}`}
                    onChange={(e) => setEditOrg({ ...editOrg, [k]: e.target.value })} /></div>
              ))}
              <div className="sm:col-span-2 text-[10px] text-muted-foreground">
                البريد وكلمة المرور والدور والمحفظة حقول محميّة ولا تُعدَّل من هنا.
              </div>
              <div className="sm:col-span-2"><Label className="text-[11px]">سبب التعديل (إلزامي)</Label>
                <Textarea rows={2} className="text-xs" value={editOrg.reason} data-testid="editorg-reason"
                  onChange={(e) => setEditOrg({ ...editOrg, reason: e.target.value })} /></div>
              <Button className="sm:col-span-2 bg-[#0A2540] hover:bg-[#061A2E]" data-testid="save-org-info-btn"
                disabled={busy || (editOrg.reason || "").trim().length < 3}
                onClick={() => act(async () => {
                  const { id, ...body } = editOrg;
                  await api.patch(`/admin/orgs/${id}`, body); setEditOrg(null);
                }, "تم تعديل بيانات المؤسسة")}>حفظ</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Edit branch */}
      <Dialog open={!!editBranch} onOpenChange={(o) => !o && setEditBranch(null)}>
        <DialogContent dir="rtl" className="max-w-md" data-testid="edit-branch-dialog">
          <DialogHeader><DialogTitle>تعديل الفرع</DialogTitle></DialogHeader>
          {editBranch && (
            <div className="space-y-2">
              {[["name", "اسم الفرع"], ["city", "المدينة"], ["phone", "الهاتف"], ["manager", "المدير"]].map(([k, lab]) => (
                <div key={k}><Label className="text-[11px]">{lab}</Label>
                  <Input className="h-8 text-xs" value={editBranch[k] || ""} data-testid={`editbranch-${k}`}
                    onChange={(e) => setEditBranch({ ...editBranch, [k]: e.target.value })} /></div>
              ))}
              <div><Label className="text-[11px]">سبب التعديل (إلزامي)</Label>
                <Textarea rows={2} className="text-xs" value={editBranch.reason || ""} data-testid="editbranch-reason"
                  onChange={(e) => setEditBranch({ ...editBranch, reason: e.target.value })} /></div>
              <Button className="w-full bg-[#0A2540] hover:bg-[#061A2E]" data-testid="save-branch-btn"
                disabled={busy || (editBranch.reason || "").trim().length < 3}
                onClick={() => act(async () => {
                  const { id, ...body } = editBranch;
                  await api.patch(`/admin/branches/${id}`, body); setEditBranch(null);
                }, "تم تعديل الفرع")}>حفظ</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Edit staff + roles */}
      <Dialog open={!!editStaff} onOpenChange={(o) => !o && setEditStaff(null)}>
        <DialogContent dir="rtl" className="max-w-md max-h-[85vh] overflow-y-auto" data-testid="edit-staff-dialog">
          <DialogHeader><DialogTitle>تعديل الموظف وصلاحياته</DialogTitle></DialogHeader>
          {editStaff && (
            <div className="space-y-2">
              {[["name", "الاسم"], ["job_title", "المسمى الوظيفي"], ["phone", "الهاتف"]].map(([k, lab]) => (
                <div key={k}><Label className="text-[11px]">{lab}</Label>
                  <Input className="h-8 text-xs" value={editStaff[k] || ""} data-testid={`editstaff-${k}`}
                    onChange={(e) => setEditStaff({ ...editStaff, [k]: e.target.value })} /></div>
              ))}
              <div>
                <Label className="text-[11px]">الأدوار المؤسسية</Label>
                <div className="grid grid-cols-2 gap-1 mt-1">
                  {Object.entries(cat.roles || {}).map(([k, v]) => (
                    <label key={k} className="text-[10px] bg-[#F4F6F8] rounded px-2 py-1 flex items-center gap-1.5"
                      data-testid={`staffrole-${k}`}>
                      <input type="checkbox" checked={(editStaff.roles || []).includes(k)}
                        onChange={(e) => setEditStaff({
                          ...editStaff,
                          roles: e.target.checked ? [...(editStaff.roles || []), k]
                            : (editStaff.roles || []).filter((r) => r !== k),
                        })} />
                      {v.ar || k}
                    </label>
                  ))}
                </div>
              </div>
              <div><Label className="text-[11px]">سبب التعديل (إلزامي)</Label>
                <Textarea rows={2} className="text-xs" value={editStaff.reason || ""} data-testid="editstaff-reason"
                  onChange={(e) => setEditStaff({ ...editStaff, reason: e.target.value })} /></div>
              <Button className="w-full bg-[#0A2540] hover:bg-[#061A2E]" data-testid="save-staff-btn"
                disabled={busy || (editStaff.reason || "").trim().length < 3}
                onClick={() => act(async () => {
                  const { id, ...body } = editStaff;
                  await api.patch(`/admin/staff/${id}`, body); setEditStaff(null);
                }, "تم تعديل الموظف")}>حفظ</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!detail} onOpenChange={(v) => !v && setDetail(null)}>
        <DialogContent dir="rtl" className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="org-dialog">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Building2 className="w-4 h-4" /> {o?.office_name}</DialogTitle></DialogHeader>
          {o && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <Box label="البريد" v={o.email} />
                <Box label="الهاتف" v={o.phone} />
                <Box label="السجل التجاري" v={o.commercial_license || "—"} />
                <Box label="الحالة" v={o.status === "active" ? "مفعّل" : "موقوف"} />
                <Box label="متاح (ريال)" v={money(o.wallet?.SAR?.available, "SAR")} />
                <Box label="معلّق (ريال)" v={money(o.wallet?.SAR?.pending, "SAR")} />
                <Box label="متاح (دولار)" v={money(o.wallet?.USD?.available, "USD")} />
                <Box label="معلّق (دولار)" v={money(o.wallet?.USD?.pending, "USD")} />
              </div>

              <div className="flex flex-wrap gap-2 items-center">
                {o.status === "active" ? (
                  <Button size="sm" variant="outline" className="text-[#B91C1C] border-[#FECACA]" disabled={busy}
                    data-testid="org-suspend-btn"
                    onClick={() => { if (window.confirm(`تأكيد إيقاف «${o.office_name}»؟ سيُمنع من الدخول وإتمام أي عملية.`)) setStatus(o.id, "suspended"); }}>إيقاف المؤسسة</Button>
                ) : (
                  <Button size="sm" className="bg-[#15803D] hover:bg-[#166534]" disabled={busy}
                    data-testid="org-activate-btn"
                    onClick={() => { if (window.confirm(`تأكيد إعادة تفعيل «${o.office_name}»؟`)) setStatus(o.id, "active"); }}>إعادة التفعيل</Button>
                )}
                {waNumber(o.phone) && (
                  <a href={`https://wa.me/${waNumber(o.phone)}?text=${encodeURIComponent(`مرحباً ${o.office_name || ""}، معك إدارة معراج نتورك`)}`}
                    target="_blank" rel="noopener noreferrer" data-testid="org-whatsapp"
                    className="inline-flex items-center gap-1.5 text-[#15803D] bg-[#F0FDF4] hover:bg-[#DCFCE7] border border-[#BBF7D0] px-3 py-1.5 rounded-lg text-xs font-semibold">
                    <MessageCircle className="w-3.5 h-3.5" /> مراسلة واتساب
                  </a>
                )}
                <Button size="sm" variant="outline" data-testid="edit-org-btn"
                  onClick={() => setEditOrg({
                    id: o.id, office_name: o.office_name, owner_name: o.owner_name,
                    phone: o.phone, governorate: o.governorate,
                    commercial_license: o.commercial_license, reason: "",
                  })}>تعديل بيانات المؤسسة</Button>
                <Link to="/admin/credit" className="text-xs underline text-[#0A2540] self-center" data-testid="org-credit-link">
                  إدارة السقف الائتماني
                </Link>
              </div>

              <div className="border-t pt-3" data-testid="org-credit">
                <div className="text-xs font-semibold text-[#0A2540] mb-2">الائتمان والتعرّض</div>
                <div className="grid sm:grid-cols-2 gap-2">
                  {["SAR", "USD"].map((c) => {
                    const s = detail.credit_summary?.[c];
                    return (
                      <div key={c} className="bg-[#F4F6F8] rounded-lg px-3 py-2 text-[11px]" data-testid={`org-credit-${c}`}>
                        <div className="font-bold text-[#0A2540] mb-1">{c === "SAR" ? "الريال" : "الدولار"}</div>
                        {!s ? <span className="text-muted-foreground">لا يوجد سقف ائتماني</span> : (
                          <div className="space-y-0.5">
                            <div>السقف: <b>{money(s.limit, c)}</b>{s.frozen && <span className="mr-1 text-[#B91C1C]">مجمّد</span>}</div>
                            <div>التعرّض الحالي: <b>{money(s.used, c)}</b> ({s.utilization}%)</div>
                            <div>المتبقي من السقف: <b>{money(s.credit_headroom, c)}</b></div>
                            <div>القوة الشرائية: <b>{money(s.spending_power, c)}</b></div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
                <div className="text-[10px] text-muted-foreground mt-1">
                  تعديل السقوف والتجميد يتم من «التحكم الائتماني» بسبب مُسجَّل في سجل التدقيق.
                </div>
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
                    <span className="flex gap-2">
                      <button className="text-[#0A2540] underline" data-testid={`edit-branch-${b.id}`}
                        onClick={() => setEditBranch({ id: b.id, name: b.name, city: b.city, phone: b.phone, manager: b.manager, reason: "" })}>تعديل</button>
                      <button className="text-[#B91C1C]" data-testid={`del-branch-${b.id}`}
                        onClick={() => { if (window.confirm(`تأكيد حذف الفرع «${b.name}»؟`)) act(() => api.delete(`/admin/branches/${b.id}`), "تم حذف الفرع"); }}>حذف</button>
                    </span>
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
                  <div key={s.id} className="text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-1.5 mb-1 flex flex-wrap justify-between gap-2" data-testid={`staff-${s.id}`}>
                    <span>{s.name} — {s.job_title || "—"} • {s.login_email || s.email || s.phone || ""}
                      {s.linked_user_id && <span className="mr-1 text-[9px] px-1.5 py-0.5 rounded bg-[#F0FDF4] text-[#15803D]">حساب دخول (محفظة المكتب)</span>}
                    </span>
                    <span className="flex gap-2">
                      <button className="text-[#0A2540] underline" data-testid={`edit-staff-${s.id}`}
                        onClick={() => setEditStaff({ id: s.id, name: s.name, job_title: s.job_title, phone: s.phone, roles: s.roles || [], reason: "" })}>تعديل/صلاحيات</button>
                      {!s.linked_user_id && (
                        <button className="text-[#0A2540] underline" data-testid={`staff-account-${s.id}`}
                          onClick={() => {
                            const email = window.prompt("بريد دخول الموظف؟");
                            if (!email) return;
                            const pw = window.prompt("كلمة مرور مؤقتة (8 أحرف على الأقل)؟");
                            if (!pw || pw.length < 8) return;
                            act(() => api.post(`/admin/staff/${s.id}/account`, { email, password: pw, roles: ["limited_user"] }), "تم إنشاء حساب الموظف");
                          }}>إنشاء حساب دخول</button>
                      )}
                      {s.linked_user_id && (
                        <button className="text-[#B45309] underline" data-testid={`staff-disable-${s.id}`}
                          onClick={() => act(() => api.post(`/admin/staff/${s.id}/account/disable`), "تم تعطيل حساب الموظف")}>تعطيل الحساب</button>
                      )}
                      <button className="text-[#B91C1C]" data-testid={`del-staff-${s.id}`}
                        onClick={() => { if (window.confirm(`تأكيد حذف الموظف «${s.name}»؟`)) act(() => api.delete(`/admin/staff/${s.id}`), "تم حذف الموظف"); }}>حذف</button>
                    </span>
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
                  الموظف يحصل على حساب دخول مستقل بصلاحيات محدودة، ويعمل على <b>محفظة المكتب نفسها</b> — لا تُنشأ له محفظة أو حساب مالي منفصل.
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
