import { PageHeader } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { RefreshCw, ShieldCheck, AlertTriangle } from "lucide-react";
import { Panel, Loading, ErrorNote, Empty, useFetch, Badge } from "./ui";

export default function AccSelfAudit() {
  const audit = useFetch("/accounting/self-audit");
  const chart = useFetch("/accounting/chart/validate");

  const checks = audit.data?.checks || [];
  const failed = checks.filter((c) => c.passed === false || c.ok === false);

  return (
    <>
      <PageHeader title="التدقيق الذاتي المحاسبي" subtitle="تشخيص سلامة للقراءة فقط — لا ترحيل ولا موازنة ولا إصلاح تلقائي"
        action={<Button variant="outline" data-testid="selfaudit-refresh" onClick={() => { audit.reload(); chart.reload(); }}>
          <RefreshCw className="w-4 h-4 me-1" /> إعادة التشغيل</Button>} />

      <ErrorNote>{audit.error || chart.error}</ErrorNote>

      <Panel testid="selfaudit-summary">
        {audit.loading ? <Loading /> : !audit.data ? <Empty /> : (
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2 text-sm">
              {failed.length === 0
                ? <><ShieldCheck className="w-5 h-5 text-emerald-600" /> <b data-testid="selfaudit-verdict">سليم — لا ملاحظات</b></>
                : <><AlertTriangle className="w-5 h-5 text-red-600" /> <b data-testid="selfaudit-verdict">{failed.length} ملاحظة تحتاج مراجعة</b></>}
            </div>
            <Badge>عدد الفحوصات: {checks.length}</Badge>
          </div>
        )}
      </Panel>

      <Panel testid="selfaudit-checks" title="الفحوصات">
        {checks.length === 0 ? <Empty>لا فحوصات</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-xs text-muted-foreground">
                <th className="py-2 text-start">الفحص</th><th className="text-start">النتيجة</th><th className="text-start">التفاصيل</th></tr></thead>
              <tbody>
                {checks.map((c, i) => (
                  <tr key={i} className="border-t" data-testid={`selfaudit-check-${i}`}>
                    <td className="py-2 text-xs">{c.name || c.check}</td>
                    <td><Badge tone={(c.passed ?? c.ok) ? "green" : "red"}>{(c.passed ?? c.ok) ? "ناجح" : "ملاحظة"}</Badge></td>
                    <td className="text-[11px] max-w-[26rem] truncate">{c.detail || c.message || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel testid="selfaudit-chart" title="سلامة الدليل المحاسبي">
        {chart.loading ? <Loading /> : !chart.data ? <Empty /> : (
          <pre className="text-[11px] bg-slate-50 rounded-lg p-3 overflow-x-auto" data-testid="selfaudit-chart-json">
            {JSON.stringify(chart.data, null, 2)}
          </pre>
        )}
      </Panel>
    </>
  );
}
