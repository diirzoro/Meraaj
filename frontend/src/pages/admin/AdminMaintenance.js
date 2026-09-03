import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Lock, Eraser, Archive, Eye } from "lucide-react";

export default function AdminMaintenance() {
  const [d, setD] = useState(null);
  const [hist, setHist] = useState({ items: [] });
  const [prev, setPrev] = useState(null);
  const [del, setDel] = useState(null);      // {kind,label,matched,...}
  const [arch, setArch] = useState(null);    // {collection,label}
  const [form, setForm] = useState({ reason: "", confirm: "" });
  const [sched, setSched] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/admin/maintenance/policies").then((r) => { setD(r.data); setSched(r.data.scheduled_enabled); });
    api.get("/admin/maintenance/history").then((r) => setHist(r.data));
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); load(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const preview = async (kind, days) => {
    try {
      const r = await api.post("/admin/maintenance/preview", { kind, retention_days: days });
      setPrev(r.data);
    } catch (e) { toast.error(apiError(e)); }
  };

  const setRetention = (kind, days) => act(() => api.post("/admin/maintenance/retention", {
    retention: { [kind]: Number(days) }, reason: `تحديث مدة الاحتفاظ لـ${kind} إلى ${days} يوماً`,
  }), "تم تحديث مدة الاحتفاظ");

  if (!d) return <div className="text-center py-20 text-muted-foreground" data-testid="maintenance-loading">جارٍ التحميل...</div>;

  return (
    <>
      <PageHeader title="الصيانة وإدارة الاحتفاظ بالبيانات"
        subtitle="تنظيف مُحكم للبيانات التشغيلية المؤقتة فقط — بمعاينة إلزامية ووضع Dry-run وسجل تدقيق كامل. السجلات المالية والأمنية والطلبات والمستندات محميّة ولا تُحذف" />

      <div className="bg-white rounded-2xl border card-shadow p-5 mb-5" data-testid="rules-panel">
        <div className="flex items-center gap-2 font-head font-bold text-[#0A2540] text-sm mb-2">
          <Lock className="w-4 h-4 text-[#15803D]" /> قواعد ملزمة
        </div>
        <ul className="text-[11px] text-muted-foreground space-y-1 list-disc pr-5">
          {d.rules.map((r, i) => <li key={i} data-testid={`rule-${i}`}>{r}</li>)}
        </ul>
        <label className="mt-3 inline-flex items-center gap-2 text-xs bg-[#F4F6F8] rounded-lg px-3 py-2" data-testid="scheduled-toggle">
          <input type="checkbox" checked={sched} disabled={busy}
            onChange={(e) => {
              const v = e.target.checked;
              setSched(v);
              act(() => api.post("/admin/maintenance/retention", {
                retention: {}, scheduled_enabled: v,
                reason: v ? "تفعيل التنظيف المجدول اليومي" : "إيقاف التنظيف المجدول اليومي",
              }), v ? "تم تفعيل التنظيف المجدول" : "تم إيقاف التنظيف المجدول");
            }} />
          التنظيف المجدول اليومي للبيانات المؤهلة (حسب مدة الاحتفاظ المعتمدة)
        </label>
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto mb-5" data-testid="cleanable-table">
        <div className="px-5 py-3 font-head font-bold text-[#0A2540] text-sm flex items-center gap-2">
          <Eraser className="w-4 h-4 text-[#D4AF37]" /> بيانات تشغيلية قابلة للتنظيف
        </div>
        <table className="w-full text-xs min-w-[900px]">
          <thead className="bg-[#F4F6F8] text-muted-foreground">
            <tr>{["النوع", "المجموعة", "إجمالي السجلات", "مؤهّل الآن", "مدة الاحتفاظ", "ملاحظة", ""].map((h) => (
              <th key={h} className="text-right font-semibold px-3 py-2.5">{h}</th>))}</tr>
          </thead>
          <tbody>
            {d.cleanable.map((x) => (
              <tr key={x.kind} className="border-t hover:bg-[#FAFBFC]" data-testid={`clean-row-${x.kind}`}>
                <td className="px-3 py-2.5 font-semibold text-[#0A2540]">{x.label}</td>
                <td className="px-3 py-2.5 text-[10px]" dir="ltr">{x.collection}</td>
                <td className="px-3 py-2.5 tabular">{x.total_rows}</td>
                <td className={`px-3 py-2.5 tabular font-bold ${x.eligible_now ? "text-[#A16207]" : ""}`}>{x.eligible_now}</td>
                <td className="px-3 py-2.5">
                  <select className="h-8 rounded-md border border-input px-2 text-xs bg-white"
                    data-testid={`retention-${x.kind}`} value={x.retention_days} disabled={busy}
                    onChange={(e) => setRetention(x.kind, e.target.value)}>
                    {d.retention_choices.map((c) => <option key={c} value={c}>{`${c} يوماً`}</option>)}
                  </select>
                </td>
                <td className="px-3 py-2.5 text-[10px] text-muted-foreground max-w-[240px]">{x.note}</td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <button className="text-[#0A2540] underline font-semibold ml-2" data-testid={`preview-${x.kind}`}
                    onClick={() => preview(x.kind, x.retention_days)}>
                    <Eye className="w-3 h-3 inline" /> معاينة
                  </button>
                  <button className="text-[#B91C1C] underline font-semibold" data-testid={`cleanup-${x.kind}`}
                    disabled={!x.eligible_now}
                    onClick={async () => {
                      const r = await api.post("/admin/maintenance/preview",
                        { kind: x.kind, retention_days: x.retention_days });
                      setForm({ reason: "", confirm: "" });
                      setDel({ ...r.data, retention_days: x.retention_days });
                    }}>تنظيف</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto mb-5" data-testid="protected-table">
        <div className="px-5 py-3 font-head font-bold text-[#0A2540] text-sm flex items-center gap-2">
          <Lock className="w-4 h-4 text-[#B91C1C]" /> سجلات محميّة — لا تُحذف نهائياً
        </div>
        <table className="w-full text-xs min-w-[640px]">
          <thead className="bg-[#F4F6F8] text-muted-foreground">
            <tr>{["السجل", "المجموعة", "عدد السجلات", "الأرشفة", ""].map((h) => (
              <th key={h} className="text-right font-semibold px-3 py-2.5">{h}</th>))}</tr>
          </thead>
          <tbody>
            {d.protected.map((x) => (
              <tr key={x.collection} className="border-t" data-testid={`protected-row-${x.collection}`}>
                <td className="px-3 py-2.5 font-semibold text-[#0A2540]">{x.label}</td>
                <td className="px-3 py-2.5 text-[10px]" dir="ltr">{x.collection}</td>
                <td className="px-3 py-2.5 tabular">{x.rows}</td>
                <td className="px-3 py-2.5">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full border ${x.archivable ? "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]" : "bg-[#F4F6F8] text-muted-foreground"}`}>
                    {x.archivable ? "قابلة للأرشفة (مع بقاء الأصل)" : "تبقى كما هي"}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  {x.archivable && (
                    <button className="text-[#1D4ED8] underline font-semibold" data-testid={`archive-${x.collection}`}
                      onClick={() => { setForm({ reason: "", confirm: "" }); setArch(x); }}>
                      <Archive className="w-3 h-3 inline" /> أرشفة
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="maintenance-history">
        <div className="font-head font-bold text-[#0A2540] text-sm mb-3">سجل عمليات الصيانة</div>
        <div className="space-y-1.5 max-h-72 overflow-y-auto">
          {hist.items.length === 0 ? <div className="text-[11px] text-muted-foreground" data-testid="history-empty">لم تُنفَّذ أي عملية صيانة</div> :
            hist.items.map((x) => (
              <div key={x.id} className="text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-1.5" data-testid={`mrun-${x.id}`}>
                <b>{x.label || x.kind || x.collection}</b> — {x.archived !== undefined
                  ? `أُرشف ${x.archived} سجل (الأصل محفوظ)`
                  : `حُذف ${x.deleted} من ${x.matched} مطابق`} • {x.by} • {fmtDate(x.at)}
                <div className="text-muted-foreground">{x.reason}</div>
              </div>
            ))}
        </div>
      </div>

      {/* Mandatory preview */}
      <Dialog open={!!prev} onOpenChange={(o) => !o && setPrev(null)}>
        <DialogContent dir="rtl" className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="preview-dialog">
          <DialogHeader><DialogTitle>معاينة قبل التنظيف — {prev?.label}</DialogTitle></DialogHeader>
          {prev && (
            <div className="space-y-3 text-xs">
              <div className="grid sm:grid-cols-4 gap-2">
                <Box label="مطابق للحذف" v={prev.matched} danger />
                <Box label="إجمالي السجلات" v={prev.total_rows} />
                <Box label="سيتبقّى" v={prev.remaining_after} />
                <Box label="مدة الاحتفاظ" v={`${prev.retention_days} يوماً`} />
              </div>
              <div className="text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-2">
                أقدم سجل مطابق: {prev.oldest ? fmtDate(prev.oldest) : "—"} • أحدث سجل مطابق: {prev.newest ? fmtDate(prev.newest) : "—"}
                <br />{prev.note}
              </div>
              <div>
                <div className="font-semibold mb-1">عيّنة من السجلات (10 كحد أقصى)</div>
                <pre className="bg-[#0A2540] text-white rounded-lg p-3 text-[10px] overflow-x-auto max-h-52" dir="ltr"
                  data-testid="preview-sample">{JSON.stringify(prev.sample, null, 1)}</pre>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Cleanup confirmation */}
      <Dialog open={!!del} onOpenChange={(o) => !o && setDel(null)}>
        <DialogContent dir="rtl" className="max-w-md" data-testid="cleanup-dialog">
          <DialogHeader><DialogTitle>تنظيف — {del?.label}</DialogTitle></DialogHeader>
          {del && (
            <div className="space-y-3">
              <div className="text-xs bg-[#FEF2F2] border border-[#FECACA] text-[#B91C1C] rounded-lg px-3 py-2" data-testid="cleanup-warning">
                سيُحذف <b>{del.matched}</b> سجلاً من <code dir="ltr">{del.collection}</code> أقدم من {del.retention_days} يوماً.
                هذه بيانات تشغيلية مؤقتة فقط ولا تشمل أي سجل مالي أو أمني أو طلب أو مستند.
              </div>
              <Button variant="outline" size="sm" className="w-full" data-testid="dry-run-btn" disabled={busy}
                onClick={() => act(async () => {
                  const r = await api.post("/admin/maintenance/cleanup", {
                    kind: del.kind, retention_days: del.retention_days, dry_run: true,
                    reason: "تشغيل تجريبي (Dry-run) قبل التنظيف",
                  });
                  toast.success(`Dry-run: ${r.data.matched} سجلاً مطابقاً — لم يُحذف شيء`);
                }, "تم التشغيل التجريبي")}>تشغيل تجريبي (Dry-run) — بدون حذف</Button>
              <div><Label className="text-xs">السبب (إلزامي — 5 أحرف على الأقل)</Label>
                <Textarea rows={2} className="text-xs" value={form.reason} data-testid="cleanup-reason"
                  onChange={(e) => setForm({ ...form, reason: e.target.value })} /></div>
              <div><Label className="text-xs">اكتب عبارة التأكيد: أؤكد التنظيف</Label>
                <Input className="h-9 text-xs" value={form.confirm} data-testid="cleanup-confirm"
                  onChange={(e) => setForm({ ...form, confirm: e.target.value })} /></div>
              <Button className="w-full bg-[#B91C1C] hover:bg-[#991B1B]" data-testid="confirm-cleanup-btn"
                disabled={busy || form.reason.trim().length < 5 || form.confirm.trim() !== "أؤكد التنظيف"}
                onClick={() => act(async () => {
                  const r = await api.post("/admin/maintenance/cleanup", {
                    kind: del.kind, retention_days: del.retention_days, dry_run: false,
                    confirm_phrase: form.confirm.trim(), reason: form.reason.trim(),
                  });
                  toast.success(`تم حذف ${r.data.deleted} سجلاً`);
                  setDel(null);
                }, "تم التنظيف وتسجيله في سجل التدقيق")}>تنفيذ التنظيف</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Archive confirmation */}
      <Dialog open={!!arch} onOpenChange={(o) => !o && setArch(null)}>
        <DialogContent dir="rtl" className="max-w-md" data-testid="archive-dialog">
          <DialogHeader><DialogTitle>أرشفة — {arch?.label}</DialogTitle></DialogHeader>
          {arch && (
            <div className="space-y-3">
              <div className="text-xs bg-[#EFF6FF] border border-[#BFDBFE] text-[#1D4ED8] rounded-lg px-3 py-2">
                الأرشفة تنسخ السجلات الأقدم من سنة إلى <code dir="ltr">{arch.collection}_archive</code> مع
                <b> بقاء السجلات الأصلية كما هي</b> — لا حذف ولا تعديل، وتبقى قابلة للاسترجاع.
              </div>
              <div><Label className="text-xs">السبب (إلزامي — 5 أحرف على الأقل)</Label>
                <Textarea rows={2} className="text-xs" value={form.reason} data-testid="archive-reason"
                  onChange={(e) => setForm({ ...form, reason: e.target.value })} /></div>
              <Button className="w-full bg-[#0A2540] hover:bg-[#061A2E]" data-testid="confirm-archive-btn"
                disabled={busy || form.reason.trim().length < 5}
                onClick={() => act(async () => {
                  const r = await api.post("/admin/maintenance/archive", {
                    collection: arch.collection, older_than_days: 365, reason: form.reason.trim(),
                  });
                  toast.success(`أُرشف ${r.data.archived} سجلاً — الأصل محفوظ`);
                  setArch(null);
                }, "تمت الأرشفة")}>تنفيذ الأرشفة</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

const Box = ({ label, v, danger }) => (
  <div className="bg-[#F4F6F8] rounded-lg px-3 py-2">
    <div className="text-[10px] text-muted-foreground">{label}</div>
    <div className={`tabular text-sm font-bold ${danger ? "text-[#B91C1C]" : "text-[#0A2540]"}`}>{v}</div>
  </div>
);
