import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { money } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import AdPackageDialog, { EMPTY_PACKAGE, packagePayload } from "@/components/AdPackageDialog";
import { Plus } from "lucide-react";

const EMPTY = EMPTY_PACKAGE;   // single source of truth lives in AdPackageDialog

export default function AdminAdPackages() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const { can } = useAuth();

  const load = useCallback(() => {
    api.get("/admin/ad-packages").then((r) => setItems(r.data)).catch((e) => toast.error(apiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); load(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const toggle = (p) => {
    const reason = window.prompt(p.active ? "سبب تعطيل الباقة؟" : "سبب تفعيل الباقة؟");
    if (!reason || reason.trim().length < 3) return;
    act(() => api.patch(`/admin/ad-packages/${p.id}`,
      packagePayload({ ...EMPTY, ...p, active: !p.active, reason: reason.trim() })),
      p.active ? "تم تعطيل الباقة" : "تم تفعيل الباقة");
  };

  const remove = (p) => {
    if (!window.confirm(`حذف باقة «${p.name}» نهائياً؟ الحذف متاح فقط للباقة التي لم تُستخدم في أي إعلان أو حركة مالية.`)) return;
    const reason = window.prompt("سبب الحذف (يُسجَّل في التدقيق):");
    if (!reason || reason.trim().length < 3) return;
    act(() => api.delete(`/admin/ad-packages/${p.id}?reason=${encodeURIComponent(reason.trim())}`),
      "تم حذف الباقة");
  };

  return (
    <>
      <div className="flex justify-end mb-3">
        {can("ads.manage") && (
        <Button size="sm" className="bg-[#D4AF37] text-[#0A2540] hover:bg-[#c39f2f]" data-testid="pkg-new-btn"
          onClick={() => { setForm(EMPTY); setEditId(null); setOpen(true); }}>
          <Plus className="w-4 h-4" /> باقة إعلانية جديدة
        </Button>
        )}
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
                  {can("ads.manage") ? (
                    <>
                  <button className="text-[#0A2540] underline text-[10px]" data-testid={`pkg-edit-${p.id}`}
                    onClick={() => { setForm({ ...EMPTY, ...p, max_views: p.max_views ?? "", max_clicks: p.max_clicks ?? "", reason: "" }); setEditId(p.id); setOpen(true); }}>تعديل</button>
                  <button className="text-[#A16207] underline text-[10px]" data-testid={`pkg-toggle-${p.id}`}
                    onClick={() => toggle(p)}>{p.active ? "تعطيل" : "تفعيل"}</button>
                  <button className="text-[#B91C1C] underline text-[10px]" data-testid={`pkg-delete-${p.id}`}
                    onClick={() => remove(p)}>حذف</button>
                    </>
                  ) : (
                    <span className="text-[10px] text-muted-foreground">للعرض فقط</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="text-[10px] text-muted-foreground mt-2">
        تعديل سعر الباقة لا يؤثر على الإعلانات القائمة — لكل إعلان نسخة مجمّدة من شروط باقته وقت الشراء.
      </div>

      <AdPackageDialog open={open} onOpenChange={setOpen} initial={form} editId={editId}
        onSaved={() => { setForm(EMPTY); setEditId(null); load(); }} />
    </>
  );
}

