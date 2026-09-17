import { useState } from "react";
import api, { apiError } from "@/lib/api";
import { toast } from "sonner";
import { PageHeader } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Lock, Unlock, CalendarPlus, ShieldAlert } from "lucide-react";
import { Panel, Field, inputCls, Loading, ErrorNote, Empty, useFetch, Gate, Badge } from "./ui";

const YEAR = new Date().getFullYear();

export default function AccPeriods() {
  const [year, setYear] = useState(YEAR);
  const periods = useFetch(`/accounting/periods?fiscal_year=${year}`, [year]);
  const yearStatus = useFetch(`/accounting/year-close/${year}`, [year]);
  const [busy, setBusy] = useState(false);

  const run = async (fn, msg) => {
    setBusy(true);
    try { await fn(); toast.success(msg); periods.reload(); yearStatus.reload(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const confirmThen = (question, fn, msg) => {
    const reason = window.prompt(`${question}\nاكتب السبب للتأكيد:`);
    if (!reason || reason.trim().length < 3) return;
    run(() => fn(reason.trim()), msg);
  };

  return (
    <>
      <PageHeader title="الفترات والإقفال" subtitle="الفترات المحاسبية والإقفال السنوي — عمليات عالية الخطورة تتطلب صلاحية صريحة وسبباً مسجّلاً" />
      <ErrorNote>{periods.error}</ErrorNote>

      <Panel testid="periods-year" title="السنة المالية">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="السنة">
            <input type="number" className={`${inputCls} w-32`} value={year} data-testid="periods-year-input"
                   onChange={(e) => setYear(Number(e.target.value))} />
          </Field>
          <Gate perm="accounting.periods.manage">
            <Button variant="outline" disabled={busy} data-testid="periods-generate"
                    onClick={() => run(() => api.post(`/accounting/periods/generate?fiscal_year=${year}`), "تم توليد فترات السنة")}>
              <CalendarPlus className="w-4 h-4 me-1" /> توليد فترات السنة
            </Button>
          </Gate>
          <Gate perm="accounting.year.close">
            <Button disabled={busy} className="bg-[#0A2540]" data-testid="periods-year-close"
                    onClick={() => confirmThen(`إقفال السنة ${year} نهائياً؟ سيُنشأ قيد إقفال لنتيجة النشاط.`,
                      (reason) => api.post(`/accounting/year-close/${year}?reason=${encodeURIComponent(reason)}`), "تم الإقفال السنوي")}>
              <Lock className="w-4 h-4 me-1" /> إقفال السنة
            </Button>
          </Gate>
          <Gate perm="accounting.year.reopen">
            <Button variant="destructive" disabled={busy} data-testid="periods-year-reopen"
                    onClick={() => confirmThen(`إعادة فتح السنة ${year}؟ عملية مُراقبة تُسجَّل بالكامل.`,
                      (reason) => api.post(`/accounting/year-close/${year}/reopen?reason=${encodeURIComponent(reason)}`), "تمت إعادة الفتح")}>
              <Unlock className="w-4 h-4 me-1" /> إعادة فتح السنة
            </Button>
          </Gate>
        </div>
        {yearStatus.data && (
          <div className="mt-4 grid sm:grid-cols-4 gap-3 text-xs" data-testid="periods-year-status">
            <div className="rounded-lg bg-slate-50 p-3">الحالة: <b>{yearStatus.data.closed ? "مُقفلة" : "مفتوحة"}</b></div>
            <div className="rounded-lg bg-slate-50 p-3">قيد الإقفال: <b className="font-mono">{yearStatus.data.closing_entry_no || "—"}</b></div>
            <div className="rounded-lg bg-slate-50 p-3">أقفلها: <b>{yearStatus.data.closed_by || "—"}</b></div>
            <div className="rounded-lg bg-slate-50 p-3">أعاد فتحها: <b>{yearStatus.data.reopened_by || "—"}</b></div>
          </div>
        )}
        <p className="text-[11px] text-muted-foreground mt-3 flex items-start gap-1">
          <ShieldAlert className="w-3.5 h-3.5 mt-0.5" />
          الإقفال السنوي لا يمسح التقارير التاريخية: تقارير الأداء تستبعد قيود الإقفال افتراضياً.
        </p>
      </Panel>

      <Panel testid="periods-list" title="الفترات المحاسبية">
        {periods.loading ? <Loading /> : (periods.data?.items || []).length === 0 ? <Empty>لا توجد فترات لهذه السنة</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-xs text-muted-foreground">
                <th className="py-2 text-start">الفترة</th><th className="text-start">من</th><th className="text-start">إلى</th>
                <th className="text-start">الحالة</th><th className="text-start">بواسطة</th><th /></tr></thead>
              <tbody>
                {periods.data.items.map((p) => (
                  <tr key={p.id} className="border-t" data-testid={`period-row-${p.code || p.id}`}>
                    <td className="py-2 font-mono text-[11px]">{p.code || `${p.fiscal_year}-${p.period_no}`}</td>
                    <td className="text-xs">{String(p.start_date).slice(0, 10)}</td>
                    <td className="text-xs">{String(p.end_date).slice(0, 10)}</td>
                    <td><Badge tone={p.status === "CLOSED" ? "red" : "green"}>{p.status === "CLOSED" ? "مُقفلة" : "مفتوحة"}</Badge></td>
                    <td className="text-[11px]">{p.closed_by || p.reopened_by || "—"}</td>
                    <td className="text-end space-x-1 rtl:space-x-reverse">
                      {p.status !== "CLOSED" ? (
                        <Gate perm="accounting.periods.close">
                          <Button size="sm" variant="outline" disabled={busy} data-testid={`period-close-${p.id}`}
                                  onClick={() => confirmThen(`إقفال الفترة ${p.code}؟`,
                                    (reason) => api.post(`/accounting/periods/${p.id}/close?reason=${encodeURIComponent(reason)}`), "تم إقفال الفترة")}>
                            إقفال
                          </Button>
                        </Gate>
                      ) : (
                        <Gate perm="accounting.periods.reopen">
                          <Button size="sm" variant="outline" disabled={busy} data-testid={`period-reopen-${p.id}`}
                                  onClick={() => confirmThen(`إعادة فتح الفترة ${p.code}؟`,
                                    (reason) => api.post(`/accounting/periods/${p.id}/reopen?reason=${encodeURIComponent(reason)}`), "تمت إعادة الفتح")}>
                            إعادة فتح
                          </Button>
                        </Gate>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
