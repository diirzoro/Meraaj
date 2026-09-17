import accApi from "@/mobile/api/accounting";
import { useShell } from "@/mobile/MobileShell";
import { AlertTriangle, ShieldCheck } from "lucide-react";
import {
  Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Chip, useAsync,
} from "@/mobile/ui/kit";

/** READ-ONLY diagnostics: detection only, never repair (no "fix all"). */
export default function MAccAudit() {
  const { shell } = useShell();
  const caps = shell?.accounting?.capabilities || {};
  const recon = useAsync(() => accApi.reconciliation());
  const audit = useAsync(() => (caps.self_audit ? accApi.selfAudit() : Promise.resolve(null)));

  const sections = Object.entries(recon.data?.sections || {});
  const checks = audit.data?.checks || [];
  const failed = checks.filter((c) => (c.passed ?? c.ok) === false);
  const refresh = async () => { await Promise.all([recon.reload(), audit.reload()]); };

  return (
    <Screen refresh={refresh}>
      <TopBar title="المطابقة والتدقيق الذاتي" subtitle="كشف فقط — بلا إصلاح تلقائي" back />
      <div className="p-4 space-y-3.5">
        {caps.self_audit && (
          <div data-testid="m-audit-verdict"
               className={`rounded-[26px] p-5 border ${failed.length === 0
                 ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200"}`}>
            {audit.loading ? <Skeleton rows={1} /> : (
              <div className="flex items-center gap-3.5">
                <span className="w-14 h-14 rounded-2xl bg-white flex items-center justify-center shrink-0">
                  {failed.length === 0 ? <ShieldCheck className="w-7 h-7 text-emerald-600" />
                    : <AlertTriangle className="w-7 h-7 text-red-600" />}
                </span>
                <div className="min-w-0">
                  <p className="font-head text-base font-bold text-[#0A2540]">
                    {failed.length === 0 ? "سليم" : `${failed.length} ملاحظة تحتاج مراجعة`}
                  </p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {checks.length} فحص محاسبي تم تنفيذه
                  </p>
                </div>
              </div>
            )}
          </div>
        )}

        {recon.loading ? <Skeleton rows={2} />
          : recon.error ? <ErrorState message={recon.error} onRetry={recon.reload} />
          : sections.length === 0 ? <EmptyState title="لا بيانات مطابقة" />
          : sections.map(([name, rows]) => (
            <Card key={name} testid={`m-recon-${name}`}>
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-bold text-[#0A2540] truncate" dir="ltr">{name}</p>
                <Chip tone={(rows || []).length ? "warn" : "good"}>
                  {(rows || []).length ? `${rows.length} ملاحظة` : "لا ملاحظات"}
                </Chip>
              </div>
              {(rows || []).slice(0, 5).map((r, i) => (
                <p key={i} className="text-[11px] text-muted-foreground mt-2.5 break-words bg-[#F1F4F8] rounded-xl p-2.5"
                   data-testid={`m-recon-row-${name}-${i}`} dir="ltr">
                  {r.issue || r.kind || ""} · {r.source_key || r.event_id || r.reference || ""}
                </p>
              ))}
            </Card>
          ))}
      </div>
    </Screen>
  );
}
