import accApi from "@/mobile/api/accounting";
import { useShell } from "@/mobile/MobileShell";
import { ShieldCheck, AlertTriangle } from "lucide-react";
import { Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, useAsync } from "@/mobile/ui/kit";

/** READ-ONLY diagnostics: detection only, never repair (no "fix all"). */
export default function MAccAudit() {
  const { shell } = useShell();
  const caps = shell?.accounting?.capabilities || {};
  const recon = useAsync(() => accApi.reconciliation());
  const audit = useAsync(() => (caps.self_audit ? accApi.selfAudit() : Promise.resolve(null)));

  const sections = Object.entries(recon.data?.sections || {});
  const checks = audit.data?.checks || [];
  const failed = checks.filter((c) => (c.passed ?? c.ok) === false);

  return (
    <Screen>
      <TopBar title="المطابقة والتدقيق الذاتي" subtitle="كشف فقط — بلا إصلاح تلقائي" back />
      <div className="p-4 space-y-3">
        {caps.self_audit && (
          <Card testid="m-audit-verdict">
            {audit.loading ? <Skeleton rows={1} /> : (
              <div className="flex items-center gap-2">
                {failed.length === 0
                  ? <><ShieldCheck className="w-5 h-5 text-emerald-600" />
                      <span className="text-sm font-bold text-[#0A2540]">سليم — {checks.length} فحص بلا ملاحظات</span></>
                  : <><AlertTriangle className="w-5 h-5 text-red-600" />
                      <span className="text-sm font-bold text-[#0A2540]">{failed.length} ملاحظة تحتاج مراجعة</span></>}
              </div>
            )}
          </Card>
        )}

        {recon.loading ? <Skeleton rows={2} />
          : recon.error ? <ErrorState message={recon.error} onRetry={recon.reload} />
          : sections.length === 0 ? <EmptyState title="لا بيانات مطابقة" />
          : sections.map(([name, rows]) => (
            <Card key={name} testid={`m-recon-${name}`}>
              <div className="flex items-center justify-between">
                <p className="text-xs font-bold text-[#0A2540]">{name}</p>
                <span className={`text-[11px] font-bold ${(rows || []).length ? "text-amber-700" : "text-emerald-700"}`}>
                  {(rows || []).length ? `${rows.length} ملاحظة` : "لا ملاحظات"}
                </span>
              </div>
              {(rows || []).slice(0, 5).map((r, i) => (
                <p key={i} className="text-[11px] text-muted-foreground mt-2 break-words"
                   data-testid={`m-recon-row-${name}-${i}`}>
                  {r.issue || r.kind || ""} · {r.source_key || r.event_id || r.reference || ""}
                </p>
              ))}
            </Card>
          ))}
      </div>
    </Screen>
  );
}
