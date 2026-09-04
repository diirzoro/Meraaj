import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Percent, Plus, History, Calculator } from "lucide-react";

const EMPTY = {
  name: "", mode: "percent", value: 0.1, charge_side: "buyer", priority: 0, active: true, note: "",
  scope: { buyer_type: "any", currency: "any", package_type: "any", source: "any", seller_id: "", package_id: "" },
};

const LABEL = {
  buyer_type: { any: "الكل", office: "مكتب", individual: "فرد" },
  currency: { any: "الكل", SAR: "ريال", USD: "دولار" },
  package_type: { any: "الكل", umrah: "عمرة", tourism: "سياحة" },
  source: { any: "الكل", meraaj: "معراج", rahal: "رحّال" },
  charge_side: { buyer: "خصم من المشتري", seller: "خصم من البائع", split: "مناصفة" },
};

export default function AdminCommissions() {
  const [d, setD] = useState({ rules: [], default_pct: 0.1 });
  const [form, setForm] = useState(null);
  const [events, setEvents] = useState(null);
  const [prev, setPrev] = useState({ buyer_type: "office", currency: "SAR", package_type: "umrah", source: "meraaj", base_amount: 1000, seats: 1 });
  const [prevRes, setPrevRes] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api.get("/admin/commission-rules").then((r) => setD(r.data)), []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      const body = { ...form, value: Number(form.value), priority: Number(form.priority) };
      if (form.id) await api.patch(`/admin/commission-rules/${form.id}`, body);
      else await api.post("/admin/commission-rules", body);
      toast.success("تم حفظ القاعدة"); setForm(null); load();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const deactivate = async (id) => {
    try { await api.delete(`/admin/commission-rules/${id}`); toast.success("تم تعطيل القاعدة"); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  const runPreview = async () => {
    try {
      const r = await api.post("/admin/commission-rules/preview", { ...prev, base_amount: Number(prev.base_amount), seats: Number(prev.seats) });
      setPrevRes(r.data);
    } catch (e) { toast.error(apiError(e)); }
  };

  return (
    <>
      <PageHeader title="محرك العمولات" subtitle="قواعد مرنة بدل النسبة الثابتة — وتُحفظ نسخة من القاعدة داخل كل طلب فلا تتغير الطلبات القديمة" />

      <div className="grid lg:grid-cols-3 gap-5 mb-6">
        <div className="bg-white rounded-2xl border card-shadow p-5 lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2 font-head font-bold text-[#0A2540] text-sm">
              <Percent className="w-4 h-4 text-[#D4AF37]" /> القواعد ({d.rules.length})
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" data-testid="rule-events-btn"
                onClick={async () => { const r = await api.get("/admin/commission-events"); setEvents(r.data); }}>
                <History className="w-4 h-4" /> سجل التعديلات
              </Button>
              <Button size="sm" className="bg-[#0A2540] hover:bg-[#061A2E]" data-testid="new-rule-btn"
                onClick={() => setForm({ ...EMPTY })}><Plus className="w-4 h-4" /> قاعدة جديدة</Button>
            </div>
          </div>
          <div className="bg-[#FEFCE8] border border-[#FEF08A] rounded-lg px-3 py-2 text-xs text-[#A16207] mb-3">
            القاعدة الافتراضية عند عدم وجود قاعدة مطابقة: <b>عمولة منصة {(d.default_pct * 100).toFixed(0)}%</b> — سلوك النظام الحالي بلا تغيير.
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[760px]" data-testid="rules-table">
              <thead className="bg-[#F4F6F8] text-muted-foreground">
                <tr>{["القاعدة", "النوع", "القيمة", "جهة الخصم", "النطاق", "الأولوية", "الحالة", ""].map((h) => (
                  <th key={h} className="text-right font-semibold px-3 py-2">{h}</th>))}</tr>
              </thead>
              <tbody>
                {d.rules.length === 0 ? (
                  <tr><td colSpan={8} className="text-center py-10 text-muted-foreground" data-testid="rules-empty">لا توجد قواعد — يعمل النظام بالنسبة الافتراضية</td></tr>
                ) : d.rules.map((r) => (
                  <tr key={r.id} className="border-t" data-testid={`rule-${r.id}`}>
                    <td className="px-3 py-2 font-semibold text-[#0A2540]">{r.name}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{r.mode === "percent" ? "نسبة" : "قيمة ثابتة"}</td>
                    <td className="px-3 py-2 tabular">{r.mode === "percent" ? `${(r.value * 100).toFixed(2)}%` : r.value}</td>
                    <td className="px-3 py-2">{LABEL.charge_side[r.charge_side] || r.charge_side}</td>
                    <td className="px-3 py-2 text-[10px] text-muted-foreground">
                      {LABEL.buyer_type[r.scope?.buyer_type]} • {LABEL.currency[r.scope?.currency]} • {LABEL.package_type[r.scope?.package_type]} • {LABEL.source[r.scope?.source]}
                    </td>
                    <td className="px-3 py-2 tabular">{r.priority}</td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      <span className={`text-[10px] px-2 py-0.5 rounded-full border whitespace-nowrap ${r.active ? "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]" : "bg-[#F4F6F8] text-[#64748B]"}`}>
                        {r.active ? "نشطة" : "معطلة"}
                      </span>
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      <button onClick={() => setForm({ ...EMPTY, ...r, scope: { ...EMPTY.scope, ...(r.scope || {}) } })}
                        data-testid={`edit-rule-${r.id}`} className="text-[#0A2540] underline font-semibold">تعديل</button>
                      {r.active && <button onClick={() => deactivate(r.id)} data-testid={`off-rule-${r.id}`}
                        className="mr-2 text-red-600 underline">تعطيل</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Preview / simulator */}
        <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="commission-preview">
          <div className="flex items-center gap-2 mb-4 font-head font-bold text-[#0A2540] text-sm">
            <Calculator className="w-4 h-4 text-[#D4AF37]" /> محاكي العمولة
          </div>
          <div className="space-y-2">
            <Sel label="نوع المشتري" v={prev.buyer_type} onChange={(v) => setPrev({ ...prev, buyer_type: v })} tid="prev-buyer"
              opts={[["office", "مكتب"], ["individual", "فرد"]]} />
            <Sel label="العملة" v={prev.currency} onChange={(v) => setPrev({ ...prev, currency: v })} tid="prev-currency"
              opts={[["SAR", "ريال"], ["USD", "دولار"]]} />
            <Sel label="نوع البرنامج" v={prev.package_type} onChange={(v) => setPrev({ ...prev, package_type: v })} tid="prev-type"
              opts={[["umrah", "عمرة"], ["tourism", "سياحة"]]} />
            <Sel label="المصدر" v={prev.source} onChange={(v) => setPrev({ ...prev, source: v })} tid="prev-source"
              opts={[["meraaj", "معراج"], ["rahal", "رحّال"]]} />
            <div>
              <Label className="text-xs">وعاء الحساب (عمولة المشتري)</Label>
              <Input type="number" value={prev.base_amount} data-testid="prev-base" className="h-8 text-xs"
                onChange={(e) => setPrev({ ...prev, base_amount: e.target.value })} />
            </div>
            <div>
              <Label className="text-xs">عدد المقاعد</Label>
              <Input type="number" value={prev.seats} data-testid="prev-seats" className="h-8 text-xs"
                onChange={(e) => setPrev({ ...prev, seats: e.target.value })} />
            </div>
            <Button size="sm" className="w-full bg-[#0A2540] hover:bg-[#061A2E]" onClick={runPreview} data-testid="run-preview">احسب</Button>
          </div>
          {prevRes && (
            <div className="mt-4 bg-[#F4F6F8] rounded-lg p-3 text-xs space-y-1" data-testid="preview-result">
              <div>القاعدة المطبقة: <b className="text-[#0A2540]">{prevRes.rule_name}</b></div>
              <div>النوع: {prevRes.mode === "percent" ? "نسبة" : "قيمة"} — {prevRes.mode === "percent" ? `${(prevRes.value * 100).toFixed(2)}%` : prevRes.value}</div>
              <div>جهة الخصم: {LABEL.charge_side[prevRes.charge_side]}</div>
              <div className="tabular text-base font-bold text-[#15803D]">عمولة المنصة: {money(prevRes.amount, prev.currency)}</div>
            </div>
          )}
        </div>
      </div>

      {/* Rule dialog */}
      <Dialog open={!!form} onOpenChange={(o) => !o && setForm(null)}>
        <DialogContent dir="rtl" className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="rule-dialog">
          <DialogHeader><DialogTitle>{form?.id ? "تعديل قاعدة" : "قاعدة عمولة جديدة"}</DialogTitle></DialogHeader>
          {form && (
            <div className="space-y-3">
              <div><Label className="text-xs">اسم القاعدة</Label>
                <Input value={form.name} data-testid="rule-name" onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
              <div className="grid grid-cols-2 gap-3">
                <Sel label="النوع" v={form.mode} onChange={(v) => setForm({ ...form, mode: v })} tid="rule-mode"
                  opts={[["percent", "نسبة"], ["fixed", "قيمة ثابتة لكل مقعد"]]} />
                <div><Label className="text-xs">{form.mode === "percent" ? "النسبة (0.10 = 10%)" : "القيمة لكل مقعد"}</Label>
                  <Input type="number" step="0.01" value={form.value} data-testid="rule-value"
                    onChange={(e) => setForm({ ...form, value: e.target.value })} /></div>
              </div>
              <Sel label="جهة الخصم" v={form.charge_side} onChange={(v) => setForm({ ...form, charge_side: v })} tid="rule-side"
                opts={[["buyer", "المشتري"], ["seller", "البائع"], ["split", "مناصفة"]]} />
              <div className="grid grid-cols-2 gap-3">
                <Sel label="نوع المشتري" v={form.scope.buyer_type} tid="rule-scope-buyer"
                  onChange={(v) => setForm({ ...form, scope: { ...form.scope, buyer_type: v } })}
                  opts={[["any", "الكل"], ["office", "مكتب"], ["individual", "فرد"]]} />
                <Sel label="العملة" v={form.scope.currency} tid="rule-scope-currency"
                  onChange={(v) => setForm({ ...form, scope: { ...form.scope, currency: v } })}
                  opts={[["any", "الكل"], ["SAR", "ريال"], ["USD", "دولار"]]} />
                <Sel label="نوع البرنامج" v={form.scope.package_type} tid="rule-scope-type"
                  onChange={(v) => setForm({ ...form, scope: { ...form.scope, package_type: v } })}
                  opts={[["any", "الكل"], ["umrah", "عمرة"], ["tourism", "سياحة"]]} />
                <Sel label="المصدر" v={form.scope.source} tid="rule-scope-source"
                  onChange={(v) => setForm({ ...form, scope: { ...form.scope, source: v } })}
                  opts={[["any", "الكل"], ["meraaj", "معراج"], ["rahal", "رحّال"]]} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label className="text-xs">الأولوية (الأعلى يُطبق أولاً)</Label>
                  <Input type="number" value={form.priority} data-testid="rule-priority"
                    onChange={(e) => setForm({ ...form, priority: e.target.value })} /></div>
                <label className="text-xs flex items-center gap-2 mt-6" data-testid="rule-active">
                  <input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /> نشطة
                </label>
              </div>
              <Button className="w-full bg-[#0A2540] hover:bg-[#061A2E]" disabled={busy || form.name.trim().length < 2}
                onClick={save} data-testid="save-rule-btn">حفظ القاعدة</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Events dialog */}
      <Dialog open={!!events} onOpenChange={(o) => !o && setEvents(null)}>
        <DialogContent dir="rtl" className="max-w-lg max-h-[80vh] overflow-y-auto" data-testid="events-dialog">
          <DialogHeader><DialogTitle>سجل تعديلات العمولات</DialogTitle></DialogHeader>
          <div className="space-y-2">
            {(events || []).length === 0 ? <div className="text-xs text-muted-foreground">لا يوجد سجل</div> :
              (events || []).map((e) => (
                <div key={e.id} className="text-xs bg-[#F4F6F8] rounded-lg px-3 py-2">
                  <b>{e.action}</b> — {e.by} • {fmtDate(e.at)}
                  {e.after && <div className="text-[10px] mt-1">القيمة: {e.before?.value} ← {e.after?.value}</div>}
                </div>
              ))}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

const Sel = ({ label, v, onChange, opts, tid }) => (
  <div>
    <Label className="text-xs">{label}</Label>
    <select value={v} onChange={(e) => onChange(e.target.value)} data-testid={tid}
      className="w-full h-9 rounded-md border border-input px-2 text-xs bg-white">
      {opts.map(([val, l]) => <option key={val} value={val}>{l}</option>)}
    </select>
  </div>
);
