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
import { Search, History, AlertTriangle } from "lucide-react";

const STATE_LABEL = { listed: "معروض", unlisted: "موقوف", archived: "مؤرشف" };
const FIELDS = [
  ["title", "اسم البرنامج", "text"], ["departure_date", "تاريخ الانطلاق", "date"],
  ["return_date", "تاريخ العودة", "date"], ["net_cost_per_seat", "تكلفة المقعد (صافي البائع)", "number"],
  ["final_sale_price", "سعر البيع النهائي", "number"], ["buyer_office_commission", "عمولة المكتب المشتري", "number"],
  ["child_net_cost", "تكلفة الطفل", "number"], ["child_sale_price", "سعر بيع الطفل", "number"],
  ["child_commission", "عمولة الطفل", "number"], ["infant_net_cost", "تكلفة الرضيع", "number"],
  ["infant_sale_price", "سعر بيع الرضيع", "number"], ["infant_commission", "عمولة الرضيع", "number"],
  ["total_seats", "المقاعد المخصصة", "number"], ["fx_rate", "سعر التحويل", "number"],
];

export default function AdminPrograms() {
  const [f, setF] = useState({ q: "", source: "", status: "", currency: "", page: 1 });
  const [d, setD] = useState({ items: [], total: 0 });
  const [detail, setDetail] = useState(null);
  const [edits, setEdits] = useState({});
  const [reason, setReason] = useState("");
  const [imgUrl, setImgUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [newP, setNewP] = useState(null);
  const [offices, setOffices] = useState([]);

  const load = useCallback(() => {
    const p = new URLSearchParams({ page: String(f.page), limit: "25" });
    ["q", "source", "status", "currency"].forEach((k) => { if (f[k]) p.set(k, f[k]); });
    api.get(`/admin/programs?${p}`).then((r) => setD(r.data));
  }, [f]);
  useEffect(() => { load(); }, [load]);

  const open = async (id) => {
    const r = await api.get(`/admin/programs/${id}`);
    setDetail(r.data); setEdits({}); setReason(""); setImgUrl("");
  };

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); load(); if (detail) await open(detail.package.id); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const pages = Math.max(1, Math.ceil(d.total / 25));
  const p = detail?.package;

  return (
    <>
      <PageHeader title="إدارة البرامج والمقاعد"
        subtitle="إضافة برنامج، تعديل الأسعار والعمولات والمقاعد والصور والتواريخ، العرض والإيقاف والأرشفة — مع سجل كامل لكل تعديل"
        action={<Button className="bg-[#15803D] hover:bg-[#166534]" data-testid="new-program-btn"
          onClick={() => {
            api.get("/admin/orgs?status=active&limit=200").then((r) => setOffices(r.data.items || []));
            setNewP({
              seller_id: "", type: "umrah", title: "", departure_date: "", return_date: "",
              departure_city: "", net_cost_per_seat: "", final_sale_price: "",
              buyer_office_commission: "", currency: "USD", total_seats: "", status: "listed", reason: "",
            });
          }}>برنامج جديد</Button>} />

      <div className="bg-white rounded-2xl border card-shadow p-4 mb-5 flex flex-wrap gap-3 items-center" data-testid="programs-filters">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="w-4 h-4 absolute top-2.5 right-3 text-muted-foreground" />
          <input value={f.q} onChange={(e) => setF({ ...f, q: e.target.value, page: 1 })} data-testid="programs-search"
            placeholder="ابحث باسم البرنامج أو المكتب أو مرجع رحّال"
            className="w-full h-9 rounded-md border border-input pr-9 pl-3 text-xs" />
        </div>
        <select value={f.source} onChange={(e) => setF({ ...f, source: e.target.value, page: 1 })} data-testid="programs-source"
          className="h-9 rounded-md border border-input px-2 text-xs">
          <option value="">كل المصادر</option><option value="meraaj">معراج</option><option value="rahal">رحّال</option>
        </select>
        <select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value, page: 1 })} data-testid="programs-status"
          className="h-9 rounded-md border border-input px-2 text-xs">
          <option value="">كل الحالات</option><option value="listed">معروض</option>
          <option value="unlisted">موقوف</option><option value="archived">مؤرشف</option>
        </select>
        <select value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value, page: 1 })} data-testid="programs-currency"
          className="h-9 rounded-md border border-input px-2 text-xs">
          <option value="">كل العملات</option><option value="SAR">ريال</option><option value="USD">دولار</option>
        </select>
        <span className="text-[11px] text-muted-foreground mr-auto" data-testid="programs-count">{d.total} برنامج</span>
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto" data-testid="programs-table">
        <table className="w-full text-xs min-w-[900px]">
          <thead className="bg-[#F4F6F8] text-muted-foreground">
            <tr>{["البرنامج", "المكتب", "المصدر", "الانطلاق", "السعر", "مخصص", "مباع", "متبقٍ", "الحالة", ""].map((h) => (
              <th key={h} className="text-right font-semibold px-3 py-2.5">{h}</th>))}</tr>
          </thead>
          <tbody>
            {d.items.length === 0 ? (
              <tr><td colSpan={10} className="text-center py-12 text-muted-foreground" data-testid="programs-empty">لا توجد برامج</td></tr>
            ) : d.items.map((x) => (
              <tr key={x.id} className="border-t hover:bg-[#FAFBFC]" data-testid={`program-row-${x.id}`}>
                <td className="px-3 py-2.5 font-semibold text-[#0A2540] max-w-[200px] truncate">
                  {x.title}
                  {x.price_mismatch && <span className="mr-1 text-[9px] px-1.5 py-0.5 rounded bg-[#FEF2F2] text-[#B91C1C]">تعارض سعر</span>}
                </td>
                <td className="px-3 py-2.5">{x.seller_office_name}</td>
                <td className="px-3 py-2.5">{x.source === "rahal" ? "رحّال" : "معراج"}</td>
                <td className="px-3 py-2.5 whitespace-nowrap">{fmtDate(x.departure_date)}{x.is_expired && " (منتهٍ)"}</td>
                <td className="px-3 py-2.5 tabular">{money(x.final_sale_price, x.currency)}</td>
                <td className="px-3 py-2.5 tabular">{x.allocated_seats}</td>
                <td className="px-3 py-2.5 tabular">{x.sold_seats}</td>
                <td className={`px-3 py-2.5 tabular font-bold ${x.remaining_seats === 0 ? "text-[#B91C1C]" : ""}`}>{x.remaining_seats}</td>
                <td className="px-3 py-2.5">
                  <span className="text-[10px] px-2 py-0.5 rounded bg-[#F4F6F8] text-[#0A2540]">{STATE_LABEL[x.status] || x.status}</span>
                </td>
                <td className="px-3 py-2.5">
                  <button onClick={() => open(x.id)} data-testid={`program-open-${x.id}`} className="text-[#0A2540] underline font-semibold">إدارة</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-5" data-testid="programs-pagination">
          <button disabled={f.page <= 1} onClick={() => setF({ ...f, page: f.page - 1 })} data-testid="programs-prev"
            className="h-8 px-3 rounded-md border text-xs disabled:opacity-40">السابق</button>
          <span className="text-xs tabular">صفحة {f.page} من {pages}</span>
          <button disabled={f.page >= pages} onClick={() => setF({ ...f, page: f.page + 1 })} data-testid="programs-next"
            className="h-8 px-3 rounded-md border text-xs disabled:opacity-40">التالي</button>
        </div>
      )}

      <Dialog open={!!newP} onOpenChange={(o) => !o && setNewP(null)}>
        <DialogContent dir="rtl" className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="new-program-dialog">
          <DialogHeader><DialogTitle>إنشاء برنامج جديد</DialogTitle></DialogHeader>
          {newP && (
            <div className="grid sm:grid-cols-2 gap-2">
              <div className="sm:col-span-2"><Label className="text-[11px]">المكتب البائع</Label>
                <select className="w-full h-8 rounded-md border border-input px-2 text-xs bg-white" data-testid="newp-seller"
                  value={newP.seller_id} onChange={(e) => setNewP({ ...newP, seller_id: e.target.value })}>
                  <option value="">اختر المكتب</option>
                  {offices.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                </select></div>
              <div><Label className="text-[11px]">النوع</Label>
                <select className="w-full h-8 rounded-md border border-input px-2 text-xs bg-white" data-testid="newp-type"
                  value={newP.type} onChange={(e) => setNewP({ ...newP, type: e.target.value })}>
                  <option value="umrah">عمرة</option><option value="tourism">سياحة</option>
                </select></div>
              <div><Label className="text-[11px]">العملة</Label>
                <select className="w-full h-8 rounded-md border border-input px-2 text-xs bg-white" data-testid="newp-currency"
                  value={newP.currency} onChange={(e) => setNewP({ ...newP, currency: e.target.value })}>
                  <option value="USD">دولار أمريكي</option><option value="SAR">ريال سعودي</option>
                </select></div>
              {[["title", "اسم البرنامج", "text"], ["departure_city", "مدينة الانطلاق", "text"],
                ["departure_date", "تاريخ الانطلاق", "date"], ["return_date", "تاريخ العودة", "date"],
                ["net_cost_per_seat", "تكلفة المقعد (صافي البائع)", "number"],
                ["final_sale_price", "سعر البيع النهائي", "number"],
                ["buyer_office_commission", "عمولة المكتب المشتري", "number"],
                ["total_seats", "عدد المقاعد", "number"]].map(([k, lab, t]) => (
                <div key={k}><Label className="text-[11px]">{lab}</Label>
                  <Input className="h-8 text-xs" type={t} value={newP[k]} data-testid={`newp-${k}`}
                    onChange={(e) => setNewP({ ...newP, [k]: t === "number" ? Number(e.target.value) : e.target.value })} /></div>
              ))}
              <div><Label className="text-[11px]">الحالة عند الإنشاء</Label>
                <select className="w-full h-8 rounded-md border border-input px-2 text-xs bg-white" data-testid="newp-status"
                  value={newP.status} onChange={(e) => setNewP({ ...newP, status: e.target.value })}>
                  <option value="listed">معروض</option><option value="unlisted">موقوف (مسودة)</option>
                </select></div>
              <div className="sm:col-span-2"><Label className="text-[11px]">سبب الإنشاء (إلزامي)</Label>
                <Textarea rows={2} className="text-xs" value={newP.reason} data-testid="newp-reason"
                  onChange={(e) => setNewP({ ...newP, reason: e.target.value })} /></div>
              <Button className="sm:col-span-2 bg-[#0A2540] hover:bg-[#061A2E]" data-testid="create-program-btn"
                disabled={busy || !newP.seller_id || newP.title.length < 3 || !newP.departure_date
                  || !newP.return_date || !newP.total_seats || newP.reason.trim().length < 3}
                onClick={() => act(async () => { await api.post("/admin/programs", newP); setNewP(null); },
                  "تم إنشاء البرنامج")}>إنشاء</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent dir="rtl" className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="program-dialog">
          <DialogHeader><DialogTitle>{p?.title}</DialogTitle></DialogHeader>
          {p && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <Box label="المقاعد المخصصة" v={p.allocated_seats} />
                <Box label="المباعة" v={p.sold_seats} />
                <Box label="المتبقية" v={p.remaining_seats} />
                <Box label="العملة" v={p.currency} />
              </div>
              {p.price_warnings && (
                <div className="text-xs bg-[#FEF2F2] text-[#B91C1C] border border-[#FECACA] rounded-lg px-3 py-2 flex items-start gap-2" data-testid="price-warning">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  تعارض في الأسعار مع رحّال: {JSON.stringify(p.price_warnings)}
                </div>
              )}

              <div className="border-t pt-3">
                <div className="text-xs font-semibold text-[#0A2540] mb-2">تعديل البيانات والأسعار والمقاعد</div>
                <div className="grid sm:grid-cols-2 gap-2">
                  {FIELDS.map(([k, lab, type]) => (
                    <div key={k}>
                      <Label className="text-[11px]">{lab}</Label>
                      <Input type={type} className="h-8 text-xs" data-testid={`field-${k}`}
                        defaultValue={p[k] ?? ""} onChange={(e) => setEdits({
                          ...edits, [k]: type === "number" ? Number(e.target.value) : e.target.value })} />
                    </div>
                  ))}
                  <div>
                    <Label className="text-[11px]">العملة</Label>
                    <select defaultValue={p.currency} data-testid="field-currency"
                      onChange={(e) => setEdits({ ...edits, currency: e.target.value })}
                      className="w-full h-8 rounded-md border border-input px-2 text-xs bg-white">
                      <option value="SAR">ريال سعودي</option><option value="USD">دولار أمريكي</option>
                    </select>
                  </div>
                  <div>
                    <Label className="text-[11px]">انتهاء التفويض</Label>
                    <Input type="date" className="h-8 text-xs" data-testid="field-auth-exp"
                      defaultValue={(p.authorization_expires_at || "").slice(0, 10)}
                      onChange={(e) => setEdits({ ...edits, authorization_expires_at: e.target.value })} />
                  </div>
                </div>
                <Label className="text-[11px] mt-2 block">سبب التعديل (إلزامي)</Label>
                <Textarea rows={2} value={reason} data-testid="program-reason" onChange={(e) => setReason(e.target.value)} className="text-xs" />
                <Button size="sm" className="mt-2 bg-[#0A2540] hover:bg-[#061A2E]" data-testid="save-program-btn"
                  disabled={busy || reason.trim().length < 3 || Object.keys(edits).length === 0}
                  onClick={() => act(() => api.patch(`/admin/programs/${p.id}`, { changes: edits, reason }), "تم حفظ التعديلات")}>
                  حفظ التعديلات
                </Button>
              </div>

              <div className="border-t pt-3">
                <div className="text-xs font-semibold text-[#0A2540] mb-2">صور البرنامج ({(p.images || []).length})</div>
                <div className="flex gap-2">
                  <Input placeholder="رابط الصورة" value={imgUrl} data-testid="program-image-url" className="h-8 text-xs"
                    onChange={(e) => setImgUrl(e.target.value)} />
                  <Button size="sm" variant="outline" data-testid="add-image-btn" disabled={busy || imgUrl.length < 5}
                    onClick={() => act(async () => {
                      await api.post(`/admin/programs/${p.id}/images`, { images: [...(p.images || []), imgUrl] });
                      setImgUrl("");
                    }, "تمت إضافة الصورة")}>إضافة</Button>
                </div>
                <div className="flex flex-wrap gap-2 mt-2">
                  {(p.images || []).map((img, i) => (
                    <div key={i} className="relative" data-testid={`program-image-${i}`}>
                      <img src={img} alt="" className="w-20 h-14 object-cover rounded border" />
                      <button className="absolute top-0 left-0 bg-[#B91C1C] text-white text-[10px] px-1 rounded"
                        data-testid={`remove-image-${i}`}
                        onClick={() => act(() => api.post(`/admin/programs/${p.id}/images`,
                          { images: (p.images || []).filter((_, j) => j !== i) }), "تم حذف الصورة")}>×</button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="border-t pt-3 flex flex-wrap gap-2">
                {["listed", "unlisted", "archived"].map((s) => (
                  <Button key={s} size="sm" variant={p.status === s ? "default" : "outline"} data-testid={`state-${s}`}
                    disabled={busy || p.status === s || reason.trim().length < 3}
                    onClick={() => act(() => api.post(`/admin/programs/${p.id}/state`, { state: s, reason }), "تم تحديث الحالة")}>
                    {s === "listed" ? "عرض" : s === "unlisted" ? "إيقاف" : "أرشفة"}
                  </Button>
                ))}
                <span className="text-[10px] text-muted-foreground self-center">تغيير الحالة يحتاج سبباً أيضاً</span>
              </div>

              <div className="border-t pt-3">
                <div className="flex items-center gap-2 text-xs font-semibold text-[#0A2540] mb-2">
                  <History className="w-3.5 h-3.5" /> سجل التعديلات ({detail.events.length})
                </div>
                <div className="space-y-1.5 max-h-52 overflow-y-auto">
                  {detail.events.length === 0 ? <div className="text-xs text-muted-foreground">لا يوجد سجل</div> :
                    detail.events.map((e) => (
                      <div key={e.id} className="text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-1.5" data-testid={`program-event-${e.id}`}>
                        <b>{e.action}</b> — {e.actor} • {fmtDate(e.at)}
                        {e.reason ? <div className="text-muted-foreground">{e.reason}</div> : null}
                        {e.after ? <div className="text-[10px] text-muted-foreground">{JSON.stringify(e.after)}</div> : null}
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
    <div className="tabular text-sm font-bold text-[#0A2540]">{v}</div>
  </div>
);
