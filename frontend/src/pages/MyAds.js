import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AdPreview } from "@/components/AdSlot";
import { toast } from "sonner";
import { Megaphone, Plus, Send } from "lucide-react";

const EMPTY = {
  kind: "ad", title: "", description_ar: "", advertiser_name: "", advertiser_type: "office",
  paid: false, contract_value: 0, currency: "SAR", start_date: "", end_date: "",
  image_url: "", target_url: "", audience: "all", placements: ["homepage"],
  cta_label: "", linked_package_id: "", priority: 10, reason: "",
};

export default function MyAds() {
  const [d, setD] = useState(null);
  const [pkgs, setPkgs] = useState({ items: [], wallet: {} });
  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [subFor, setSubFor] = useState(null);
  const [subPkg, setSubPkg] = useState("");
  const [subReason, setSubReason] = useState("");

  const load = useCallback(() => {
    api.get("/ads/mine").then((r) => setD(r.data)).catch((e) => toast.error(apiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get(`/ad-packages?kind=${form.kind}`).then((r) => setPkgs(r.data)).catch(() => {});
  }, [form.kind]);

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); load(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const missing = [
    !form.title?.trim() && "العنوان",
    !form.advertiser_name?.trim() && "اسم المعلن",
    !form.start_date && "تاريخ البداية",
    !form.end_date && "تاريخ النهاية",
    !form.placements?.length && "مكان عرض واحد على الأقل",
    (form.reason || "").trim().length < 3 && "سبب الإجراء",
  ].filter(Boolean);

  const save = () => {
    if (missing.length) return toast.error(`أكمل: ${missing.join(" • ")}`);
    act(async () => {
      if (editId) await api.patch(`/ads/mine/${editId}`, form);
      else await api.post("/ads/mine", form);
      setOpen(false); setForm(EMPTY); setEditId(null);
    }, "تم حفظ المسودة");
  };

  const affordable = (p) => !p.paid || p.price <= 0
    || (pkgs.wallet?.[p.currency] ?? 0) + 1e-9 >= p.price;

  const doSubmit = () => {
    const p = pkgs.items.find((x) => x.id === subPkg);
    if (!p) return toast.error("اختر باقة إعلانية");
    if (!affordable(p)) return toast.error("الرصيد المتاح لا يكفي قيمة الباقة — اشحن المحفظة");
    if (subReason.trim().length < 3) return toast.error("اكتب سبب الإرسال للاعتماد");
    act(async () => {
      await api.post(`/ads/mine/${subFor.id}/status`,
        { status: "pending_approval", reason: subReason.trim(), package_id: p.id });
      setSubFor(null); setSubPkg(""); setSubReason("");
    }, "أُرسل للاعتماد وحُجزت قيمة الباقة من رصيدك");
  };

  const cancel = (ad) => act(() => api.post(`/ads/mine/${ad.id}/status`,
    { status: "draft", reason: "إلغاء الإرسال وفكّ الحجز" }), "أُلغي الإرسال وفُكّ الحجز");

  const requestCancel = (ad) => {
    const reason = window.prompt("سبب طلب إلغاء الإعلان؟ (إلزامي)");
    if (!reason || reason.trim().length < 3) return;
    act(() => api.post(`/ads/mine/${ad.id}/cancellation-request`, { reason: reason.trim() }),
      "أُرسل طلب الإلغاء لمراجعة إدارة معراج — لا حركة على رصيدك حتى القرار");
  };

  if (!d) return <div className="text-center py-20 text-muted-foreground" data-testid="myads-loading">جارٍ التحميل...</div>;

  return (
    <>
      <PageHeader title="إعلاناتي وعروضي" subtitle="أنشئ حملتك، اختر الباقة، أرسلها لاعتماد معراج — قيمة الباقة تُحجز من رصيدك وتُفكّ كاملة عند الرفض أو الإلغاء" />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5" data-testid="myads-wallet">
        <S label="المتاح (ريال)" v={money((d.wallet?.SAR || {}).available || 0, "SAR")} tid="myads-sar" />
        <S label="المحجوز (ريال)" v={money((d.wallet?.SAR || {}).pending || 0, "SAR")} tid="myads-sar-held" />
        <S label="المتاح (دولار)" v={money((d.wallet?.USD || {}).available || 0, "USD")} tid="myads-usd" />
        <S label="عدد حملاتي" v={d.items.length} tid="myads-count" />
      </div>

      <div className="flex gap-2 mb-4">
        <Button size="sm" className="bg-[#D4AF37] text-[#0A2540] hover:bg-[#c39f2f]" data-testid="myads-new"
          onClick={() => { setForm({ ...EMPTY, kind: "ad" }); setEditId(null); setOpen(true); }}>
          <Plus className="w-4 h-4" /> إعلان جديد
        </Button>
        <Button size="sm" variant="outline" data-testid="myads-new-promo"
          onClick={() => { setForm({ ...EMPTY, kind: "promotion" }); setEditId(null); setOpen(true); }}>
          <Megaphone className="w-4 h-4" /> عرض ترويجي
        </Button>
      </div>

      <div className="bg-white rounded-2xl border card-shadow table-scroll mb-5" data-testid="myads-table">
        <table className="w-full text-xs min-w-[860px]">
          <thead className="bg-[#F4F6F8] text-muted-foreground">
            <tr>{["العنوان", "النوع", "الباقة", "المحجوز", "الفترة", "الحالة", "مشاهدات", "نقرات", "المتبقي", "إجراءات"].map((h) => (
              <th key={h} className="text-right font-semibold px-3 py-2.5 whitespace-nowrap">{h}</th>))}</tr>
          </thead>
          <tbody>
            {d.items.length === 0 ? (
              <tr><td colSpan={10} className="text-center py-12 text-muted-foreground" data-testid="myads-empty">لا توجد حملات — ابدأ بإنشاء إعلان</td></tr>
            ) : d.items.map((a) => (
              <tr key={a.id} className="border-t" data-testid={`myad-${a.id}`}>
                <td className="px-3 py-2.5 font-semibold text-[#0A2540] max-w-[200px] truncate">{a.title}</td>
                <td className="px-3 py-2.5 whitespace-nowrap">{a.kind_label}</td>
                <td className="px-3 py-2.5 whitespace-nowrap">{a.package_name || "—"}
                  {a.package_price ? <span className="block text-[10px] text-muted-foreground">{money(a.package_price, a.package_currency)}</span> : null}
                </td>
                <td className="px-3 py-2.5 tabular whitespace-nowrap">{a.held_amount ? money(a.held_amount, a.package_currency) : "—"}</td>
                <td className="px-3 py-2.5 text-[10px] whitespace-nowrap">{a.start_date} ← {a.end_date}</td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <span className="text-[10px] px-2 py-0.5 rounded-full border whitespace-nowrap">{a.status_label}</span>
                  {a.rejection_reason && <span className="block text-[10px] text-[#B91C1C]">سبب الرفض: {a.rejection_reason}</span>}
                  {a.completion_reason && <span className="block text-[10px] text-muted-foreground">{a.completion_reason}</span>}
                  {a.cancellation && (
                    <span className="block text-[10px] text-muted-foreground" data-testid={`myad-cancel-state-${a.id}`}>
                      طلب الإلغاء: {a.cancellation.state === "requested" ? "قيد المراجعة"
                        : a.cancellation.state === "accepted" ? "مقبول" : "مرفوض"}
                      {a.cancellation.decision_reason ? ` — ${a.cancellation.decision_reason}` : ""}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2.5 tabular">{a.views || 0}</td>
                <td className="px-3 py-2.5 tabular">{a.clicks || 0}</td>
                <td className="px-3 py-2.5 text-[10px] whitespace-nowrap">
                  {a.remaining_views != null ? `مشاهدات: ${a.remaining_views}` : "—"}
                  {a.remaining_clicks != null ? ` • نقرات: ${a.remaining_clicks}` : ""}
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap space-x-1 space-x-reverse">
                  {["draft", "rejected"].includes(a.status) && (
                    <>
                      <button className="text-[#0A2540] underline text-[10px]" data-testid={`myad-edit-${a.id}`}
                        onClick={() => { setForm({ ...EMPTY, ...a, reason: "" }); setEditId(a.id); setOpen(true); }}>تعديل</button>
                      <button className="text-[#15803D] underline text-[10px]" data-testid={`myad-submit-${a.id}`}
                        onClick={() => {
                          setSubFor(a); setSubPkg(""); setSubReason("");
                          api.get(`/ad-packages?kind=${a.kind}`).then((r) => setPkgs(r.data)).catch(() => {});
                        }}>إرسال للاعتماد</button>
                    </>
                  )}
                  {a.status === "pending_approval" && (
                    <button className="text-[#A16207] underline text-[10px]" data-testid={`myad-cancel-${a.id}`}
                      onClick={() => cancel(a)}>إلغاء الإرسال</button>
                  )}
                  {["active", "paused", "pending_approval"].includes(a.status) && (
                    <button className="text-[#B91C1C] underline text-[10px]" data-testid={`myad-cancel-request-${a.id}`}
                      onClick={() => requestCancel(a)}>طلب إلغاء الإعلان</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-4" data-testid="myads-txns">
        <div className="text-xs font-semibold text-[#0A2540] mb-2">حركات الإعلانات على رصيدي</div>
        {(d.transactions || []).length === 0 ? (
          <div className="text-[11px] text-muted-foreground">لا توجد حركات بعد</div>
        ) : d.transactions.slice(0, 12).map((t) => (
          <div key={t.id} className="flex flex-wrap justify-between gap-2 border-b py-1.5 text-[11px]">
            <span>{t.description}</span>
            <span className="tabular font-semibold">{money(t.amount, t.currency)}</span>
            <span className="text-muted-foreground">{fmtDate(t.created_at)}</span>
          </div>
        ))}
      </div>

      <Dialog open={!!subFor} onOpenChange={(v) => !v && setSubFor(null)}>
        <DialogContent className="max-w-lg max-h-[88vh] overflow-y-auto" dir="rtl" data-testid="myad-submit-dialog">
          <DialogHeader><DialogTitle className="text-right text-sm">إرسال للاعتماد واختيار الباقة</DialogTitle></DialogHeader>
          <div className="text-[11px] text-muted-foreground" data-testid="myad-submit-wallet">
            رصيدي المتاح: {money(pkgs.wallet?.SAR || 0, "SAR")} • {money(pkgs.wallet?.USD || 0, "USD")}
          </div>
          <div className="space-y-2">
            {pkgs.items.length === 0 && (
              <div className="text-[11px] text-[#A16207]" data-testid="myad-nopkg">لا توجد باقات مفعّلة لهذا النوع — راجع إدارة معراج</div>
            )}
            {pkgs.items.map((p) => {
              const ok = affordable(p);
              return (
                <label key={p.id} data-testid={`myad-pkg-${p.id}`}
                  className={`block rounded-xl border px-3 py-2 text-[11px] cursor-pointer ${subPkg === p.id ? "border-[#0A2540] bg-[#F4F6F8]" : "bg-white"} ${ok ? "" : "opacity-60"}`}>
                  <input type="radio" className="hidden" name="pkg" disabled={!ok}
                    checked={subPkg === p.id} onChange={() => setSubPkg(p.id)} />
                  <div className="flex justify-between gap-2">
                    <b className="text-[#0A2540]">{p.name}</b>
                    <span className="tabular font-semibold">{p.paid ? money(p.price, p.currency) : "مجانية"}</span>
                  </div>
                  <div className="text-muted-foreground">
                    {p.duration_days} يوم
                    {p.max_views ? ` • حتى ${p.max_views} مشاهدة` : ""}
                    {p.max_clicks ? ` • حتى ${p.max_clicks} نقرة` : ""}
                    {p.max_placements ? ` • حتى ${p.max_placements} موضع` : ""}
                  </div>
                  {!ok && <div className="text-[#B91C1C]">الرصيد المتاح لا يكفي — اشحن المحفظة</div>}
                </label>
              );
            })}
          </div>
          <div>
            <Label className="text-[11px]">سبب الإرسال (يُسجَّل في التدقيق)</Label>
            <Input className="h-9 text-xs" value={subReason} data-testid="myad-submit-reason"
              onChange={(e) => setSubReason(e.target.value)} />
          </div>
          <div className="bg-[#F4F6F8] rounded-lg px-3 py-2 text-[11px]">
            تُحجز قيمة الباقة من رصيدك المتاح الآن، وتُخصم نهائياً عند اعتماد الإعلان، وتعود كاملة عند الرفض أو إلغاء الإرسال.
          </div>
          <Button className="bg-[#0A2540] hover:bg-[#061A2E] w-full" data-testid="myad-submit-confirm"
            disabled={busy} onClick={doSubmit}><Send className="w-4 h-4" /> {busy ? "جارٍ الإرسال..." : "إرسال وحجز قيمة الباقة"}</Button>
        </DialogContent>
      </Dialog>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl max-h-[88vh] overflow-y-auto" dir="rtl" data-testid="myad-dialog">
          <DialogHeader><DialogTitle className="text-right text-sm">
            {editId ? "تعديل" : "إنشاء"} {form.kind === "promotion" ? "عرض ترويجي" : "إعلان"}
          </DialogTitle></DialogHeader>
          <div className="grid sm:grid-cols-2 gap-3 text-xs">
            <F label="العنوان"><Input className="h-9 text-xs" value={form.title} data-testid="myad-title"
              onChange={(e) => setForm({ ...form, title: e.target.value })} /></F>
            <F label="اسم المعلن (كما يظهر للجمهور)"><Input className="h-9 text-xs" value={form.advertiser_name}
              data-testid="myad-advertiser" onChange={(e) => setForm({ ...form, advertiser_name: e.target.value })} /></F>
            <F label="تاريخ البداية"><Input type="date" className="h-9 text-xs" value={form.start_date}
              data-testid="myad-start" onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></F>
            <F label="تاريخ النهاية"><Input type="date" className="h-9 text-xs" value={form.end_date}
              data-testid="myad-end" onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></F>
            <F label="نص زر الإجراء"><Input className="h-9 text-xs" value={form.cta_label}
              data-testid="myad-cta" onChange={(e) => setForm({ ...form, cta_label: e.target.value })} /></F>
            <F label="الرابط المستهدف"><Input className="h-9 text-xs" dir="ltr" value={form.target_url}
              data-testid="myad-url" onChange={(e) => setForm({ ...form, target_url: e.target.value })} /></F>
            <F label="الجمهور">
              <select className="h-9 w-full rounded-md border border-input px-2 text-xs bg-white" data-testid="myad-audience"
                value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })}>
                {Object.entries(d.audiences).filter(([k]) => k !== "specific").map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </F>
            <div className="sm:col-span-2">
              <Label className="text-[11px]">صورة/بانر (رفع من الجهاز)</Label>
              <input type="file" accept="image/*" className="text-[11px]" data-testid="myad-file"
                onChange={async (e) => {
                  const file = e.target.files?.[0]; if (!file) return;
                  const fd = new FormData(); fd.append("file", file);
                  try {
                    const r = await api.post("/ads/upload-image", fd, { headers: { "Content-Type": "multipart/form-data" } });
                    setForm((f) => ({ ...f, image_url: r.data.image_url })); toast.success("تم رفع الصورة");
                  } catch (er) { toast.error(apiError(er)); }
                }} />
              {form.image_url && <img src={form.image_url} alt="بانر" className="w-20 h-12 object-cover rounded border mt-1" />}
            </div>
            <div className="sm:col-span-2">
              <Label className="text-[11px]">أماكن الظهور المطلوبة</Label>
              <div className="flex flex-wrap gap-2 mt-1">
                {Object.entries(d.placements).map(([k, l]) => (
                  <label key={k} className={`text-[11px] px-3 py-1.5 rounded-lg border cursor-pointer ${form.placements.includes(k) ? "bg-[#0A2540] text-white border-[#0A2540]" : "bg-white"}`}
                    data-testid={`myad-placement-${k}`}>
                    <input type="checkbox" className="hidden" checked={form.placements.includes(k)}
                      onChange={() => setForm((f) => ({ ...f, placements: f.placements.includes(k) ? f.placements.filter((x) => x !== k) : [...f.placements, k] }))} />{l}
                  </label>
                ))}
              </div>
            </div>
            <div className="sm:col-span-2">
              <Label className="text-[11px]">الوصف بالعربية</Label>
              <Textarea rows={3} className="text-xs" value={form.description_ar} data-testid="myad-desc"
                onChange={(e) => setForm({ ...form, description_ar: e.target.value })} />
            </div>
            <div className="sm:col-span-2">
              <Label className="text-[11px]">سبب الإجراء (يُسجَّل في التدقيق)</Label>
              <Input className="h-9 text-xs" value={form.reason} data-testid="myad-reason"
                onChange={(e) => setForm({ ...form, reason: e.target.value })} />
            </div>
          </div>

          <div className="border-t pt-3">
            <div className="text-[11px] font-semibold text-[#0A2540] mb-1">معاينة (لا تُحتسب مشاهدة)</div>
            <AdPreview ad={form} variant="card" />
          </div>
          <div className="bg-[#F4F6F8] rounded-lg px-3 py-2 text-[11px]" data-testid="myad-packages">
            <b>الباقات المتاحة:</b>
            {pkgs.items.length === 0 ? " لا توجد باقات مفعّلة حالياً — راجع إدارة معراج"
              : pkgs.items.map((p) => (
                <span key={p.id} className="block">
                  {p.name} — {p.paid ? money(p.price, p.currency) : "مجانية"} — {p.duration_days} يوم
                  {p.max_clicks ? ` — حتى ${p.max_clicks} نقرة` : ""}{p.max_views ? ` — حتى ${p.max_views} مشاهدة` : ""}
                </span>
              ))}
            <span className="block mt-1 text-muted-foreground">تُحجز قيمة الباقة عند الإرسال للاعتماد، وتُخصم نهائياً عند الاعتماد، وتعود كاملة عند الرفض أو الإلغاء.</span>
          </div>
          {missing.length > 0 && (
            <div className="bg-[#FEFCE8] border border-[#FEF08A] text-[#A16207] rounded-lg px-3 py-2 text-[11px]" data-testid="myad-missing">
              الحقول الناقصة: {missing.join(" • ")}
            </div>
          )}
          <Button className="bg-[#0A2540] hover:bg-[#061A2E] w-full" data-testid="myad-save"
            disabled={busy} onClick={save}><Send className="w-4 h-4" /> {busy ? "جارٍ الحفظ..." : "حفظ كمسودة"}</Button>
        </DialogContent>
      </Dialog>
    </>
  );
}

const S = ({ label, v, tid }) => (
  <div className="bg-white rounded-2xl border card-shadow p-4" data-testid={tid}>
    <div className="text-[10px] text-muted-foreground mb-1">{label}</div>
    <div className="tabular font-bold text-[#0A2540] text-sm">{v}</div>
  </div>
);

const F = ({ label, children }) => (
  <div><Label className="text-[11px]">{label}</Label>{children}</div>
);
