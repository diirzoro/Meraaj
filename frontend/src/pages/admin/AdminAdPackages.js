import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus } from "lucide-react";

const EMPTY = {
  name: "", kind: "ad", price: 0, currency: "SAR", duration_days: 30,
  max_views: "", max_clicks: "", max_placements: 1, allowed_placements: [],
  allowed_audiences: ["all"], priority: 10, paid: true, for_account_type: "all",
  requires_verified_org: false, active: true, reason: "",
};

export default function AdminAdPackages() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/admin/ad-packages").then((r) => setItems(r.data)).catch((e) => toast.error(apiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const payload = (f) => ({
    ...f,
    price: Number(f.price) || 0,
    duration_days: Number(f.duration_days) || 1,
    max_placements: Number(f.max_placements) || 1,
    priority: Number(f.priority) || 10,
    max_views: f.max_views === "" || f.max_views === null ? null : Number(f.max_views),
    max_clicks: f.max_clicks === "" || f.max_clicks === null ? null : Number(f.max_clicks),
  });

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); load(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const save = () => {
    if ((form.name || "").trim().length < 2) return toast.error("اكتب اسم الباقة");
    if (form.paid && !(Number(form.price) > 0)) return toast.error("الباقة المدفوعة تحتاج سعراً أكبر من صفر");
    if ((form.reason || "").trim().length < 3) return toast.error("اكتب سبب الإجراء");
    act(async () => {
      if (editId) await api.patch(`/admin/ad-packages/${editId}`, payload(form));
      else await api.post("/admin/ad-packages", payload(form));
      setOpen(false); setForm(EMPTY); setEditId(null);
    }, editId ? "تم تحديث الباقة" : "تم إنشاء الباقة");
  };

  const toggle = (p) => {
    const reason = window.prompt(p.active ? "سبب تعطيل الباقة؟" : "سبب تفعيل الباقة؟");
    if (!reason || reason.trim().length < 3) return;
    act(() => api.patch(`/admin/ad-packages/${p.id}`,
      payload({ ...EMPTY, ...p, active: !p.active, reason: reason.trim() })),
      p.active ? "تم تعطيل الباقة" : "تم تفعيل الباقة");
  };

  return (
    <>
      <div className="flex justify-end mb-3">
        <Button size="sm" className="bg-[#D4AF37] text-[#0A2540] hover:bg-[#c39f2f]" data-testid="pkg-new-btn"
          onClick={() => { setForm(EMPTY); setEditId(null); setOpen(true); }}>
          <Plus className="w-4 h-4" /> باقة إعلانية جديدة
        </Button>
      </div>

      <div className="bg-white rounded-2xl border card-shadow table-scroll" data-testid="pkg-table">
        <table className="w-full text-xs min-w-[860px]">
          <thead className="bg-[#F4F6F8] text-muted-foreground">
            <tr>{["الباقة", "النوع", "السعر", "المدة", "حدود", "المواضع", "الحساب", "الحالة", "إجراءات"].map((h) => (
              <th key={h} className="text-right font-semibold px-3 py-2.5 whitespace-nowrap">{h}</th>))}</tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={9} className="text-center py-12 text-muted-foreground" data-testid="pkg-empty">لا توجد باقات — أنشئ أول باقة إعلانية</td></tr>
            ) : items.map((p) => (
              <tr key={p.id} className="border-t" data-testid={`pkg-row-${p.id}`}>
                <td className="px-3 py-2.5 font-semibold text-[#0A2540]">{p.name}</td>
                <td className="px-3 py-2.5 whitespace-nowrap">{p.kind === "promotion" ? "عرض ترويجي" : p.kind === "both" ? "إعلان وعرض" : "إعلان"}</td>
                <td className="px-3 py-2.5 tabular whitespace-nowrap">{p.paid ? money(p.price, p.currency) : "مجانية"}</td>
                <td className="px-3 py-2.5 tabular whitespace-nowrap">{p.duration_days} يوم</td>
                <td className="px-3 py-2.5 text-[10px] whitespace-nowrap">
                  {p.max_views ? `مشاهدات: ${p.max_views}` : "مشاهدات: بلا حد"}
                  {p.max_clicks ? ` • نقرات: ${p.max_clicks}` : " • نقرات: بلا حد"}
                </td>
                <td className="px-3 py-2.5 tabular">{p.max_placements}</td>
                <td className="px-3 py-2.5 whitespace-nowrap text-[10px]">
                  {p.for_account_type === "offices" ? "المكاتب" : p.for_account_type === "individuals" ? "الأفراد" : "الجميع"}
                  {p.requires_verified_org ? " • يتطلب توثيق" : ""}
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full border ${p.active ? "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]" : "bg-[#F4F6F8] text-[#64748B]"}`}>
                    {p.active ? "مفعّلة" : "معطّلة"}
                  </span>
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap space-x-2 space-x-reverse">
                  <button className="text-[#0A2540] underline text-[10px]" data-testid={`pkg-edit-${p.id}`}
                    onClick={() => { setForm({ ...EMPTY, ...p, max_views: p.max_views ?? "", max_clicks: p.max_clicks ?? "", reason: "" }); setEditId(p.id); setOpen(true); }}>تعديل</button>
                  <button className="text-[#A16207] underline text-[10px]" data-testid={`pkg-toggle-${p.id}`}
                    onClick={() => toggle(p)}>{p.active ? "تعطيل" : "تفعيل"}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="text-[10px] text-muted-foreground mt-2">
        تعديل سعر الباقة لا يؤثر على الإعلانات القائمة — لكل إعلان نسخة مجمّدة من شروط باقته وقت الشراء.
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl max-h-[88vh] overflow-y-auto" dir="rtl" data-testid="pkg-dialog">
          <DialogHeader><DialogTitle className="text-right text-sm">{editId ? "تعديل باقة" : "باقة إعلانية جديدة"}</DialogTitle></DialogHeader>
          <div className="grid sm:grid-cols-2 gap-3 text-xs">
            <F label="اسم الباقة"><Input className="h-9 text-xs" value={form.name} data-testid="pkg-name"
              onChange={(e) => setForm({ ...form, name: e.target.value })} /></F>
            <F label="النوع">
              <select className="h-9 w-full rounded-md border border-input px-2 text-xs bg-white" data-testid="pkg-kind"
                value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                <option value="ad">إعلان</option><option value="promotion">عرض ترويجي</option><option value="both">كليهما</option>
              </select>
            </F>
            <F label="مدفوعة أم مجانية">
              <select className="h-9 w-full rounded-md border border-input px-2 text-xs bg-white" data-testid="pkg-paid"
                value={form.paid ? "1" : "0"} onChange={(e) => setForm({ ...form, paid: e.target.value === "1" })}>
                <option value="1">مدفوعة</option><option value="0">مجانية</option>
              </select>
            </F>
            <F label="السعر والعملة">
              <div className="flex gap-2">
                <Input type="number" className="h-9 text-xs" value={form.price} data-testid="pkg-price"
                  disabled={!form.paid} onChange={(e) => setForm({ ...form, price: e.target.value })} />
                <select className="h-9 rounded-md border border-input px-2 text-xs bg-white" data-testid="pkg-currency"
                  value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}>
                  <option value="SAR">ريال سعودي</option><option value="USD">دولار أمريكي</option>
                </select>
              </div>
            </F>
            <F label="المدة (أيام)"><Input type="number" className="h-9 text-xs" value={form.duration_days}
              data-testid="pkg-duration" onChange={(e) => setForm({ ...form, duration_days: e.target.value })} /></F>
            <F label="عدد المواضع المسموح"><Input type="number" className="h-9 text-xs" value={form.max_placements}
              data-testid="pkg-placements" onChange={(e) => setForm({ ...form, max_placements: e.target.value })} /></F>
            <F label="حد المشاهدات (فارغ = بلا حد)"><Input type="number" className="h-9 text-xs" value={form.max_views}
              data-testid="pkg-max-views" onChange={(e) => setForm({ ...form, max_views: e.target.value })} /></F>
            <F label="حد النقرات (فارغ = بلا حد)"><Input type="number" className="h-9 text-xs" value={form.max_clicks}
              data-testid="pkg-max-clicks" onChange={(e) => setForm({ ...form, max_clicks: e.target.value })} /></F>
            <F label="متاحة لحسابات">
              <select className="h-9 w-full rounded-md border border-input px-2 text-xs bg-white" data-testid="pkg-account"
                value={form.for_account_type} onChange={(e) => setForm({ ...form, for_account_type: e.target.value })}>
                <option value="all">الجميع</option><option value="offices">المكاتب</option><option value="individuals">الأفراد</option>
              </select>
            </F>
            <F label="تتطلب مؤسسة موثّقة">
              <select className="h-9 w-full rounded-md border border-input px-2 text-xs bg-white" data-testid="pkg-verified"
                value={form.requires_verified_org ? "1" : "0"}
                onChange={(e) => setForm({ ...form, requires_verified_org: e.target.value === "1" })}>
                <option value="0">لا</option><option value="1">نعم</option>
              </select>
            </F>
            <F label="الأولوية (الأصغر يظهر أولاً)"><Input type="number" className="h-9 text-xs" value={form.priority}
              data-testid="pkg-priority" onChange={(e) => setForm({ ...form, priority: e.target.value })} /></F>
            <F label="الحالة">
              <select className="h-9 w-full rounded-md border border-input px-2 text-xs bg-white" data-testid="pkg-active"
                value={form.active ? "1" : "0"} onChange={(e) => setForm({ ...form, active: e.target.value === "1" })}>
                <option value="1">مفعّلة</option><option value="0">معطّلة</option>
              </select>
            </F>
            <div className="sm:col-span-2">
              <Label className="text-[11px]">سبب الإجراء (إلزامي — يُسجَّل في التدقيق)</Label>
              <Input className="h-9 text-xs" value={form.reason} data-testid="pkg-reason"
                onChange={(e) => setForm({ ...form, reason: e.target.value })} />
            </div>
          </div>
          <Button className="bg-[#0A2540] hover:bg-[#061A2E] w-full" data-testid="pkg-save-btn"
            disabled={busy} onClick={save}>{busy ? "جارٍ الحفظ..." : "حفظ الباقة"}</Button>
        </DialogContent>
      </Dialog>
    </>
  );
}

const F = ({ label, children }) => (
  <div><Label className="text-[11px]">{label}</Label>{children}</div>
);
