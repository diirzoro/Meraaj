import { useState } from "react";
import { toast } from "sonner";
import { CalendarClock, Lock, Unlock } from "lucide-react";
import accApi from "@/mobile/api/accounting";
import { apiError } from "@/lib/api";
import { useShell } from "@/mobile/MobileShell";
import {
  Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, StatusPill, Sheet, mInput, MField,
  PrimaryButton, GhostButton, KpiCard, useAsync, haptic,
} from "@/mobile/ui/kit";

const YEAR = new Date().getFullYear();

export default function MAccPeriods() {
  const { shell } = useShell();
  const caps = shell?.accounting?.capabilities || {};
  const [year] = useState(YEAR);
  const periods = useAsync(() => accApi.periods(year), [year]);
  const yr = useAsync(() => accApi.yearStatus(year).catch(() => null), [year]);
  const [action, setAction] = useState(null); // { period, kind }
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (busy || reason.trim().length < 3 || !action) return;
    setBusy(true);
    try {
      if (action.kind === "close") await accApi.closePeriod(action.period.id, reason.trim());
      else await accApi.reopenPeriod(action.period.id, reason.trim());
      haptic("success");
      toast.success(action.kind === "close" ? "تم إقفال الفترة" : "تمت إعادة الفتح");
      setAction(null); setReason(""); periods.reload(); yr.reload();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Screen refresh={periods.reload}>
      <TopBar title="الفترات والإقفال" subtitle={`السنة المالية ${year}`} back />
      <div className="p-4 space-y-3.5">
        <KpiCard label="حالة السنة المالية" icon={CalendarClock} testid="m-periods-year"
                 tone={yr.data?.closed ? "warn" : "good"}
                 value={yr.data?.closed ? "مُقفلة" : "مفتوحة"}
                 hint={yr.data?.closing_entry_no ? `قيد الإقفال ${yr.data.closing_entry_no}` : undefined} />

        {periods.loading ? <Skeleton rows={3} />
          : periods.error ? <ErrorState message={periods.error} onRetry={periods.reload} />
          : (periods.data?.items || []).length === 0 ? <EmptyState title="لا فترات لهذه السنة" />
          : (
            <div className="space-y-3 m-stagger" data-testid="m-periods-list">
              {periods.data.items.map((p) => (
                <Card key={p.id} testid={`m-period-${p.id}`}>
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-mono font-bold text-[#0A2540]" dir="ltr">
                        {p.code || `${p.fiscal_year}-${p.period_no}`}
                      </p>
                      <p className="text-[11px] text-muted-foreground mt-1" dir="ltr">
                        {String(p.start_date).slice(0, 10)} → {String(p.end_date).slice(0, 10)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <StatusPill status={p.status === "CLOSED" ? "cancelled" : "green"} />
                      {p.status !== "CLOSED" && caps.period_close && (
                        <button disabled={busy} data-testid={`m-period-close-${p.id}`} aria-label="إقفال"
                                onClick={() => { haptic("light"); setAction({ period: p, kind: "close" }); }}
                                className="w-10 h-10 rounded-full bg-[#0A2540]/[0.06] flex items-center justify-center active:scale-90 transition-transform">
                          <Lock className="w-4 h-4 text-[#0A2540]" />
                        </button>
                      )}
                      {p.status === "CLOSED" && caps.period_reopen && (
                        <button disabled={busy} data-testid={`m-period-reopen-${p.id}`} aria-label="إعادة فتح"
                                onClick={() => { haptic("light"); setAction({ period: p, kind: "reopen" }); }}
                                className="w-10 h-10 rounded-full bg-red-50 flex items-center justify-center active:scale-90 transition-transform">
                          <Unlock className="w-4 h-4 text-red-600" />
                        </button>
                      )}
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}

        <p className="text-[11px] text-muted-foreground px-1 leading-relaxed">
          الإقفال السنوي لا يمسح التقارير التاريخية؛ وتقارير الأداء تستبعد قيود الإقفال.
          الإقفال السنوي وإعادة فتح السنة يُنفَّذان من لوحة الويب للحد من المخاطر على الجوال.
        </p>
      </div>

      <Sheet open={!!action} onClose={() => { setAction(null); setReason(""); }} testid="m-period-action-sheet"
             title={action?.kind === "close" ? "إقفال الفترة" : "إعادة فتح الفترة"}>
        {action && (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground leading-relaxed">
              الفترة: <b className="font-mono text-[#0A2540]">{action.period.code
                || `${action.period.fiscal_year}-${action.period.period_no}`}</b>
            </p>
            <MField label="سبب العملية" hint="٣ أحرف على الأقل — يُسجَّل في سجل التدقيق">
              <input className={mInput} value={reason} data-testid="m-period-reason"
                     onChange={(e) => setReason(e.target.value)} />
            </MField>
            <PrimaryButton loading={busy} disabled={busy || reason.trim().length < 3} onClick={run}
                           data-testid="m-period-action-confirm">تأكيد</PrimaryButton>
            <GhostButton onClick={() => { setAction(null); setReason(""); }}>تراجع</GhostButton>
          </div>
        )}
      </Sheet>
    </Screen>
  );
}
