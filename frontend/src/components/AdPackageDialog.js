import { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";

/** SINGLE SOURCE OF TRUTH for the ad-package form: fields, validation and payload live only
 *  here. Used by the Packages tab AND by "+ إضافة باقة" inside the ad/promotion form. */

export const EMPTY_PACKAGE = {
  name: "", kind: "ad", price: 0, currency: "SAR", duration_days: 30,
  max_views: "", max_clicks: "", max_placements: 1, allowed_placements: [],
  allowed_audiences: ["all"], priority: 10, paid: true, for_account_type: "all",
  requires_verified_org: false, active: true, reason: "",
};

export const packagePayload = (f) => ({
  ...f,
  price: Number(f.price) || 0,
  duration_days: Number(f.duration_days) || 1,
  max_placements: Number(f.max_placements) || 1,
  priority: Number(f.priority) || 10,
  max_views: f.max_views === "" || f.max_views === null ? null : Number(f.max_views),
  max_clicks: f.max_clicks === "" || f.max_clicks === null ? null : Number(f.max_clicks),
});

const F = ({ label, children }) => (
  <div><Label className="text-[11px]">{label}</Label>{children}</div>
);

export default function AdPackageDialog({ open, onOpenChange, initial, editId, onSaved }) {
  const [form, setForm] = useState(initial || EMPTY_PACKAGE);
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (open) setForm({ ...EMPTY_PACKAGE, ...(initial || {}) }); }, [open, initial]);

  const save = async () => {
    if ((form.name || "").trim().length < 2) return toast.error("اكتب اسم الباقة");
    if (form.paid && !(Number(form.price) > 0)) return toast.error("الباقة المدفوعة تحتاج سعراً أكبر من صفر");
    if ((form.reason || "").trim().length < 3) return toast.error("اكتب سبب الإجراء");
    setBusy(true);
    try {
      const body = packagePayload(form);
      const r = editId
        ? await api.patch(`/admin/ad-packages/${editId}`, body)
        : await api.post("/admin/ad-packages", body);
      toast.success(editId ? "تم تحديث الباقة" : "تم إنشاء الباقة");
      onOpenChange(false);
      if (onSaved) await onSaved({ id: r.data.id || editId, ...body });
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl max-h-[88vh] overflow-y-auto" dir="rtl" data-testid="pkg-dialog">
        <DialogHeader><DialogTitle className="text-right text-sm">{editId ? "تعديل باقة" : "باقة إعلانية جديدة"}</DialogTitle></DialogHeader>
        <div className="grid sm:grid-cols-2 gap-3 text-xs">
          <F label="اسم الباقة"><Input className="h-10 text-xs" value={form.name} data-testid="pkg-name"
            onChange={(e) => setForm({ ...form, name: e.target.value })} /></F>
          <F label="النوع">
            <select className="h-10 w-full rounded-md border border-input px-2 text-xs bg-white" data-testid="pkg-kind"
              value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
              <option value="ad">إعلان</option><option value="promotion">عرض ترويجي</option><option value="both">كليهما</option>
            </select>
          </F>
          <F label="مدفوعة أم مجانية">
            <select className="h-10 w-full rounded-md border border-input px-2 text-xs bg-white" data-testid="pkg-paid"
              value={form.paid ? "1" : "0"} onChange={(e) => setForm({ ...form, paid: e.target.value === "1" })}>
              <option value="1">مدفوعة</option><option value="0">مجانية</option>
            </select>
          </F>
          <F label="السعر والعملة">
            <div className="flex gap-2">
              <Input type="number" className="h-10 text-xs" value={form.price} data-testid="pkg-price"
                disabled={!form.paid} onChange={(e) => setForm({ ...form, price: e.target.value })} />
              <select className="h-10 rounded-md border border-input px-2 text-xs bg-white" data-testid="pkg-currency"
                value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}>
                <option value="SAR">ريال سعودي</option><option value="USD">دولار أمريكي</option>
              </select>
            </div>
          </F>
          <F label="المدة (أيام)"><Input type="number" className="h-10 text-xs" value={form.duration_days}
            data-testid="pkg-duration" onChange={(e) => setForm({ ...form, duration_days: e.target.value })} /></F>
          <F label="عدد المواضع المسموح"><Input type="number" className="h-10 text-xs" value={form.max_placements}
            data-testid="pkg-placements" onChange={(e) => setForm({ ...form, max_placements: e.target.value })} /></F>
          <F label="حد المشاهدات (فارغ = بلا حد)"><Input type="number" className="h-10 text-xs" value={form.max_views}
            data-testid="pkg-max-views" onChange={(e) => setForm({ ...form, max_views: e.target.value })} /></F>
          <F label="حد النقرات (فارغ = بلا حد)"><Input type="number" className="h-10 text-xs" value={form.max_clicks}
            data-testid="pkg-max-clicks" onChange={(e) => setForm({ ...form, max_clicks: e.target.value })} /></F>
          <F label="متاحة لحسابات">
            <select className="h-10 w-full rounded-md border border-input px-2 text-xs bg-white" data-testid="pkg-account"
              value={form.for_account_type} onChange={(e) => setForm({ ...form, for_account_type: e.target.value })}>
              <option value="all">الجميع</option><option value="offices">المكاتب</option><option value="individuals">الأفراد</option>
            </select>
          </F>
          <F label="تتطلب مؤسسة موثّقة">
            <select className="h-10 w-full rounded-md border border-input px-2 text-xs bg-white" data-testid="pkg-verified"
              value={form.requires_verified_org ? "1" : "0"}
              onChange={(e) => setForm({ ...form, requires_verified_org: e.target.value === "1" })}>
              <option value="0">لا</option><option value="1">نعم</option>
            </select>
          </F>
          <F label="الأولوية (الأصغر يظهر أولاً)"><Input type="number" className="h-10 text-xs" value={form.priority}
            data-testid="pkg-priority" onChange={(e) => setForm({ ...form, priority: e.target.value })} /></F>
          <F label="الحالة">
            <select className="h-10 w-full rounded-md border border-input px-2 text-xs bg-white" data-testid="pkg-active"
              value={form.active ? "1" : "0"} onChange={(e) => setForm({ ...form, active: e.target.value === "1" })}>
              <option value="1">مفعّلة</option><option value="0">معطّلة</option>
            </select>
          </F>
          <div className="sm:col-span-2">
            <Label className="text-[11px]">سبب الإجراء (إلزامي — يُسجَّل في التدقيق)</Label>
            <Input className="h-10 text-xs" value={form.reason} data-testid="pkg-reason"
              onChange={(e) => setForm({ ...form, reason: e.target.value })} />
          </div>
        </div>
        <Button className="bg-[#0A2540] hover:bg-[#061A2E] w-full h-11" data-testid="pkg-save-btn"
          disabled={busy} onClick={save}>{busy ? "جارٍ الحفظ..." : "حفظ الباقة"}</Button>
      </DialogContent>
    </Dialog>
  );
}
