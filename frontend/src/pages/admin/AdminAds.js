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
import { Megaphone, Plus, Eye, MousePointerClick, CheckCircle2, XCircle, PauseCircle } from "lucide-react";

const EMPTY = {
  kind: "ad", title: "", description_ar: "", advertiser_name: "", advertiser_type: "office",
  paid: false, contract_value: 0, currency: "SAR", start_date: "", end_date: "",
  image_url: "", target_url: "", audience: "all", placements: ["homepage"], priority: 10,
  cta_label: "", linked_package_id: "", linked_office_id: "", reason: "",
};

export default function AdminAds() {
  const [cat, setCat] = useState(null);
  const [d, setD] = useState({ items: [], stats: {} });
  const [tab, setTab] = useState("ad");
  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState(null);
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get(`/admin/ads?kind=${tab}`).then((r) => setD(r.data)).catch((e) => toast.error(apiError(e)));
  }, [tab]);

  useEffect(() => { api.get("/admin/ads/catalog").then((r) => setCat(r.data)); }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); load(); }
    catch (e) { toast.error(apiError(e)); }
    finally { setBusy(false); }
  };

  const save = () => act(async () => {
    const payload = { ...form, kind: tab, contract_value: Number(form.contract_value) || 0,
      priority: Number(form.priority) || 10,
      linked_package_id: form.linked_package_id || null,
      linked_office_id: form.linked_office_id || null };
    if (editId) await api.patch(`/admin/ads/${editId}`, payload);
    else await api.post("/admin/ads", payload);
    setOpen(false); setForm(EMPTY); setEditId(null);
  }, editId ? "تم تحديث الإعلان" : "تم إنشاء الإعلان كمسودة");

  const setStatus = (id, status, ask) => {
    const reason = window.prompt(ask);
    if (!reason || reason.trim().length < 3) return;
    act(() => api.post(`/admin/ads/${id}/status`, { status, reason: reason.trim() }), "تم تحديث الحالة");
  };

  const togglePlacement = (p) => setForm((f) => ({
    ...f, placements: f.placements.includes(p)
      ? f.placements.filter((x) => x !== p) : [...f.placements, p] }));

  if (!cat) return <div className="text-center py-20 text-muted-foreground" data-testid="ads-loading">جارٍ التحميل...</div>;

  return (
    <>
      <PageHeader title="الإعلانات والعروض" subtitle="حملات إعلانية وعروض ترويجية بجدولة ومواضع عرض واعتماد مزدوج (منشئ ومعتمد مختلفان) وقياس أداء" />

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-5" data-testid="ads-stats">
        <Stat label="الإجمالي" v={d.stats.total || 0} tid="ads-stat-total" />
        <Stat label="نشِط الآن" v={d.stats.active || 0} tid="ads-stat-active" />
        <Stat label="بانتظار الاعتماد" v={d.stats.pending || 0} tid="ads-stat-pending" />
        <Stat label="المشاهدات" v={d.stats.views || 0} tid="ads-stat-views" />
        <Stat label="قيمة العقود" v={money(d.stats.paid_value || 0, "SAR")} tid="ads-stat-value" />
      </div>

      <div className="flex flex-wrap gap-2 mb-5 items-center">
        {[["ad", "الإعلانات"], ["promotion", "العروض الترويجية"]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`ads-tab-${k}`}
            className={`px-3 h-9 rounded-lg text-xs font-semibold border ${tab === k ? "bg-[#0A2540] text-white border-[#0A2540]" : "bg-white text-[#0A2540] hover:bg-[#F4F6F8]"}`}>{l}</button>
        ))}
        <Button size="sm" className="bg-[#D4AF37] text-[#0A2540] hover:bg-[#c39f2f] mr-auto"
          data-testid="ads-new-btn" onClick={() => { setForm(EMPTY); setEditId(null); setOpen(true); }}>
          <Plus className="w-4 h-4" /> {tab === "ad" ? "إعلان جديد" : "عرض جديد"}
        </Button>
      </div>

      <div className="bg-white rounded-2xl border card-shadow table-scroll" data-testid="ads-table">
        <table className="w-full text-xs min-w-[900px]">
          <thead className="bg-[#F4F6F8] text-muted-foreground">
            <tr>{["العنوان", "المعلن", "النوع", "الفترة", "الموضع", "الحالة", "مشاهدات", "نقرات", "CTR", "إجراءات"].map((h) => (
              <th key={h} className="text-right font-semibold px-3 py-2.5 whitespace-nowrap">{h}</th>))}</tr>
          </thead>
          <tbody>
            {d.items.length === 0 ? (
              <tr><td colSpan={10} className="text-center py-12 text-muted-foreground" data-testid="ads-empty">
                لا توجد عناصر — أنشئ أول {tab === "ad" ? "إعلان" : "عرض"}</td></tr>
            ) : d.items.map((a) => (
              <tr key={a.id} className="border-t hover:bg-[#FAFBFC]" data-testid={`ad-row-${a.id}`}>
                <td className="px-3 py-2.5 font-semibold text-[#0A2540] max-w-[220px] truncate">{a.title}</td>
                <td className="px-3 py-2.5">{a.advertiser_name}</td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  {a.advertiser_type_label}
                  <span className={`block text-[10px] ${a.paid ? "text-[#15803D]" : "text-muted-foreground"}`}>
                    {a.paid ? `مدفوع • ${money(a.contract_value, a.currency)}` : "مجاني"}
                  </span>
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap text-[10px]">{a.start_date} ← {a.end_date}</td>
                <td className="px-3 py-2.5 text-[10px]">{(a.placement_labels || []).join("، ")}</td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full border whitespace-nowrap ${a.status === "active" ? "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]" : a.status === "pending_approval" ? "bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]" : a.status === "rejected" ? "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" : "bg-[#F4F6F8] text-[#64748B]"}`}>
                    {a.status_label}
                  </span>
                </td>
                <td className="px-3 py-2.5 tabular">{a.views || 0}</td>
                <td className="px-3 py-2.5 tabular">{a.clicks || 0}</td>
                <td className="px-3 py-2.5 tabular">{a.ctr}%</td>
                <td className="px-3 py-2.5 whitespace-nowrap space-x-1 space-x-reverse">
                  <button className="text-[#0A2540] underline text-[10px]" data-testid={`ad-edit-${a.id}`}
                    onClick={() => { setForm({ ...EMPTY, ...a, reason: "" }); setEditId(a.id); setOpen(true); }}>تعديل</button>
                  {a.status === "draft" && (
                    <button className="text-[#A16207] underline text-[10px]" data-testid={`ad-submit-${a.id}`}
                      onClick={() => setStatus(a.id, "pending_approval", "سبب إرسال الإعلان للاعتماد؟")}>إرسال للاعتماد</button>
                  )}
                  {(a.status === "pending_approval" || a.status === "paused") && (
                    <button className="text-[#15803D] underline text-[10px]" data-testid={`ad-approve-${a.id}`}
                      onClick={() => setStatus(a.id, "active", "سبب الاعتماد والنشر؟")}>اعتماد ونشر</button>
                  )}
                  {a.status === "active" && (
                    <button className="text-[#A16207] underline text-[10px]" data-testid={`ad-pause-${a.id}`}
                      onClick={() => setStatus(a.id, "paused", "سبب الإيقاف المؤقت؟")}>إيقاف مؤقت</button>
                  )}
                  {a.status === "pending_approval" && (
                    <button className="text-[#B91C1C] underline text-[10px]" data-testid={`ad-reject-${a.id}`}
                      onClick={() => setStatus(a.id, "rejected", "سبب الرفض؟")}>رفض</button>
                  )}
                  <button className="text-muted-foreground underline text-[10px]" data-testid={`ad-detail-${a.id}`}
                    onClick={async () => {
                      try { const r = await api.get(`/admin/ads/${a.id}`); setDetail(r.data); }
                      catch (e) { toast.error(apiError(e)); }
                    }}>السجل</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl max-h-[88vh] overflow-y-auto" dir="rtl" data-testid="ad-form-dialog">
          <DialogHeader><DialogTitle className="text-right text-sm">
            {editId ? "تعديل" : "إنشاء"} {tab === "ad" ? "إعلان" : "عرض ترويجي"}
          </DialogTitle></DialogHeader>
          <div className="grid sm:grid-cols-2 gap-3 text-xs">
            <F label="العنوان"><Input className="h-9 text-xs" value={form.title} data-testid="ad-title"
              onChange={(e) => setForm({ ...form, title: e.target.value })} /></F>
            <F label="اسم المعلن"><Input className="h-9 text-xs" value={form.advertiser_name} data-testid="ad-advertiser"
              onChange={(e) => setForm({ ...form, advertiser_name: e.target.value })} /></F>
            <F label="نوع المعلن">
              <select className="h-9 w-full rounded-md border border-input px-2 text-xs bg-white" data-testid="ad-type"
                value={form.advertiser_type} onChange={(e) => setForm({ ...form, advertiser_type: e.target.value })}>
                {Object.entries(cat.advertiser_types).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </F>
            <F label="الجمهور المستهدف">
              <select className="h-9 w-full rounded-md border border-input px-2 text-xs bg-white" data-testid="ad-audience"
                value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })}>
                {Object.entries(cat.audiences).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </F>
            <F label="مدفوع أم مجاني">
              <select className="h-9 w-full rounded-md border border-input px-2 text-xs bg-white" data-testid="ad-paid"
                value={form.paid ? "1" : "0"} onChange={(e) => setForm({ ...form, paid: e.target.value === "1" })}>
                <option value="0">مجاني</option><option value="1">مدفوع</option>
              </select>
            </F>
            <F label="قيمة العقد">
              <div className="flex gap-2">
                <Input type="number" className="h-9 text-xs" value={form.contract_value} data-testid="ad-value"
                  disabled={!form.paid} onChange={(e) => setForm({ ...form, contract_value: e.target.value })} />
                <select className="h-9 rounded-md border border-input px-2 text-xs bg-white" data-testid="ad-currency"
                  value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}>
                  <option value="SAR">ريال سعودي</option><option value="USD">دولار أمريكي</option>
                </select>
              </div>
            </F>
            <F label="تاريخ البداية"><Input type="date" className="h-9 text-xs" value={form.start_date} data-testid="ad-start"
              onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></F>
            <F label="تاريخ النهاية"><Input type="date" className="h-9 text-xs" value={form.end_date} data-testid="ad-end"
              onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></F>
            <F label="رابط الصورة/البانر"><Input className="h-9 text-xs" dir="ltr" value={form.image_url} data-testid="ad-image"
              onChange={(e) => setForm({ ...form, image_url: e.target.value })} /></F>
            <F label="الرابط المستهدف"><Input className="h-9 text-xs" dir="ltr" value={form.target_url} data-testid="ad-target-url"
              onChange={(e) => setForm({ ...form, target_url: e.target.value })} /></F>
            <F label="نص زر الإجراء"><Input className="h-9 text-xs" value={form.cta_label} data-testid="ad-cta"
              onChange={(e) => setForm({ ...form, cta_label: e.target.value })} /></F>
            <F label="الأولوية (الأصغر يظهر أولاً)"><Input type="number" className="h-9 text-xs" value={form.priority}
              data-testid="ad-priority" onChange={(e) => setForm({ ...form, priority: e.target.value })} /></F>
            <div className="sm:col-span-2">
              <Label className="text-[11px]">أماكن العرض</Label>
              <div className="flex flex-wrap gap-2 mt-1">
                {Object.entries(cat.placements).map(([k, l]) => (
                  <label key={k} className={`text-[11px] px-3 py-1.5 rounded-lg border cursor-pointer ${form.placements.includes(k) ? "bg-[#0A2540] text-white border-[#0A2540]" : "bg-white"}`}
                    data-testid={`ad-placement-${k}`}>
                    <input type="checkbox" className="hidden" checked={form.placements.includes(k)}
                      onChange={() => togglePlacement(k)} />{l}
                  </label>
                ))}
              </div>
            </div>
            {tab === "promotion" && (
              <>
                <F label="مرتبط ببرنامج (المعرّف)"><Input className="h-9 text-xs" dir="ltr" data-testid="ad-package"
                  value={form.linked_package_id || ""} onChange={(e) => setForm({ ...form, linked_package_id: e.target.value })} /></F>
                <F label="مرتبط بمكتب (المعرّف)"><Input className="h-9 text-xs" dir="ltr" data-testid="ad-office"
                  value={form.linked_office_id || ""} onChange={(e) => setForm({ ...form, linked_office_id: e.target.value })} /></F>
              </>
            )}
            <div className="sm:col-span-2">
              <Label className="text-[11px]">الوصف بالعربية</Label>
              <Textarea rows={3} className="text-xs" value={form.description_ar} data-testid="ad-description"
                onChange={(e) => setForm({ ...form, description_ar: e.target.value })} />
            </div>
            <div className="sm:col-span-2">
              <Label className="text-[11px]">سبب الإجراء (إلزامي — يُسجَّل في التدقيق)</Label>
              <Input className="h-9 text-xs" value={form.reason} data-testid="ad-reason"
                onChange={(e) => setForm({ ...form, reason: e.target.value })} />
            </div>
          </div>
          <div className="text-[10px] text-muted-foreground">
            يُنشأ العنصر كمسودة ولا يظهر للجمهور إلا بعد إرساله للاعتماد واعتماده من مسؤول آخر.
          </div>
          <Button className="bg-[#0A2540] hover:bg-[#061A2E] w-full" data-testid="ad-save-btn"
            disabled={busy || !form.title || !form.advertiser_name || !form.start_date || !form.end_date || form.reason.trim().length < 3}
            onClick={save}>{busy ? "جارٍ الحفظ..." : "حفظ"}</Button>
        </DialogContent>
      </Dialog>

      <Dialog open={!!detail} onOpenChange={() => setDetail(null)}>
        <DialogContent className="max-w-xl max-h-[85vh] overflow-y-auto" dir="rtl" data-testid="ad-detail-dialog">
          <DialogHeader><DialogTitle className="text-right text-sm">سجل الإعلان</DialogTitle></DialogHeader>
          {detail && (
            <div className="space-y-3 text-xs">
              <div className="bg-[#F4F6F8] rounded-lg px-3 py-2">
                <div className="font-bold text-[#0A2540]">{detail.ad.title}</div>
                <div className="text-[11px] text-muted-foreground">
                  {detail.ad.status_label} • أنشأه {detail.ad.created_by || "—"} •
                  {detail.ad.approved_by ? ` اعتمده ${detail.ad.approved_by}` : " لم يُعتمد بعد"}
                </div>
                <div className="flex gap-4 mt-2 text-[11px]">
                  <span className="inline-flex items-center gap-1"><Eye className="w-3 h-3" /> {detail.ad.views || 0}</span>
                  <span className="inline-flex items-center gap-1"><MousePointerClick className="w-3 h-3" /> {detail.ad.clicks || 0}</span>
                  <span>CTR: {detail.ad.ctr}%</span>
                </div>
              </div>
              {(detail.audit || []).map((a, i) => (
                <div key={i} className="border-r-2 border-[#D4AF37] pr-3 py-1" data-testid={`ad-audit-${i}`}>
                  <div className="font-semibold text-[#0A2540] text-[11px]">{a.action}</div>
                  <div className="text-[10px] text-muted-foreground">
                    {fmtDate(a.at)} • {a.actor} • {a.reason || "—"}
                  </div>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

const Stat = ({ label, v, tid }) => (
  <div className="bg-white rounded-2xl border card-shadow p-4" data-testid={tid}>
    <div className="text-[10px] text-muted-foreground mb-1">{label}</div>
    <div className="tabular font-bold text-[#0A2540] text-sm">{v}</div>
  </div>
);

const F = ({ label, children }) => (
  <div><Label className="text-[11px]">{label}</Label>{children}</div>
);

export const AdsIcons = { Megaphone, CheckCircle2, XCircle, PauseCircle };
