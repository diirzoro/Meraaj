import { PageHeader } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { RefreshCw, ShieldCheck } from "lucide-react";
import { Panel, Loading, ErrorNote, Empty, useFetch, Badge } from "./ui";

export default function AccReconciliation() {
  const recon = useFetch("/accounting/integration/reconciliation?limit=500");
  const fails = useFetch("/accounting/integration/failures?limit=100");

  const sections = Object.entries(recon.data?.sections || {});

  return (
    <>
      <PageHeader title="المطابقة المحاسبية" subtitle="مطابقة الأعمال ↔ المحاسبة — كشف فقط، لا إصلاح تلقائي"
        action={<Button variant="outline" data-testid="recon-refresh" onClick={() => { recon.reload(); fails.reload(); }}>
          <RefreshCw className="w-4 h-4 me-1" /> تحديث</Button>} />

      <ErrorNote>{recon.error || fails.error}</ErrorNote>

      <div className="rounded-lg bg-blue-50 border border-blue-200 text-blue-900 text-xs p-3 mb-5" data-testid="recon-readonly-note">
        هذه الشاشة تشخيصية للقراءة فقط: لا يوجد زر «إصلاح الكل»، ولا ترحيل تلقائي، ولا تعديل على القيود.
      </div>

      <Panel testid="recon-summary" title="الملخّص">
        {recon.loading ? <Loading /> : !recon.data ? <Empty /> : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            {Object.entries(recon.data.totals || {}).map(([k, v]) => (
              <div key={k} className="rounded-lg bg-slate-50 p-3" data-testid={`recon-total-${k}`}>
                <div className="text-[11px] text-muted-foreground">{k}</div>
                <div className="font-bold">{String(v)}</div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      {sections.map(([name, rows]) => (
        <Panel key={name} testid={`recon-section-${name}`} title={name}
               subtitle={`${(rows || []).length} سجل`}>
          {(rows || []).length === 0 ? (
            <div className="flex items-center gap-2 text-sm text-emerald-700" data-testid={`recon-clean-${name}`}>
              <ShieldCheck className="w-4 h-4" /> لا ملاحظات
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-xs text-muted-foreground">
                  <th className="py-2 text-start">النوع</th><th className="text-start">الحدث</th>
                  <th className="text-start">المرجع</th><th className="text-start">التفاصيل</th></tr></thead>
                <tbody>
                  {(rows || []).slice(0, 100).map((r, i) => (
                    <tr key={i} className="border-t" data-testid={`recon-row-${name}-${i}`}>
                      <td className="py-2"><Badge tone="amber">{r.issue || r.kind || name}</Badge></td>
                      <td className="text-xs">{r.event_type || r.source_type || "—"}</td>
                      <td className="font-mono text-[10px]">{r.source_key || r.event_id || r.reference || "—"}</td>
                      <td className="text-[11px] max-w-[22rem] truncate">{r.message || r.detail || JSON.stringify(r).slice(0, 120)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      ))}

      <Panel testid="recon-failures" title="فشل التكامل المحاسبي">
        {fails.loading ? <Loading /> : (fails.data?.items || []).length === 0 ? <Empty>لا فشل مسجّل</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-xs text-muted-foreground">
                <th className="py-2 text-start">التاريخ</th><th className="text-start">الحدث</th>
                <th className="text-start">المرجع</th><th className="text-start">الخطأ</th></tr></thead>
              <tbody>
                {fails.data.items.map((r, i) => (
                  <tr key={i} className="border-t" data-testid={`recon-failure-${i}`}>
                    <td className="py-2 text-xs">{String(r.at || "").slice(0, 16)}</td>
                    <td className="text-xs">{r.event_type}</td>
                    <td className="font-mono text-[10px]">{r.source_key || r.event_id}</td>
                    <td className="text-[11px] text-red-700 max-w-[22rem] truncate">{r.error}</td>
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
