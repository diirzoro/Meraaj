import { useState } from "react";
import { toast } from "sonner";
import accApi from "@/mobile/api/accounting";
import { apiError } from "@/lib/api";
import { useShell } from "@/mobile/MobileShell";
import { Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, StatusPill, useAsync } from "@/mobile/ui/kit";

const YEAR = new Date().getFullYear();

export default function MAccPeriods() {
  const { shell } = useShell();
  const caps = shell?.accounting?.capabilities || {};
  const [year] = useState(YEAR);
  const periods = useAsync(() => accApi.periods(year), [year]);
  const yr = useAsync(() => accApi.yearStatus(year).catch(() => null), [year]);
  const [busy, setBusy] = useState(false);

  const run = async (fn, msg) => {
    const reason = window.prompt("اكتب سبب العملية للتأكيد:");
    if (!reason || reason.trim().length < 3 || busy) return;
    setBusy(true);
    try { await fn(reason.trim()); toast.success(msg); periods.reload(); yr.reload(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Screen>
      <TopBar title="الفترات والإقفال" subtitle={`السنة المالية ${year}`} back />
      <div className="p-4 space-y-3">
        <Card testid="m-periods-year">
          <p className="text-[11px] text-muted-foreground">حالة السنة</p>
          <p className="text-sm font-bold text-[#0A2540] mt-1">
            {yr.data?.closed ? "مُقفلة" : "مفتوحة"}
            {yr.data?.closing_entry_no ? ` · قيد الإقفال ${yr.data.closing_entry_no}` : ""}
          </p>
          <p className="text-[11px] text-muted-foreground mt-2">
            الإقفال السنوي لا يمسح التقارير التاريخية؛ تقارير الأداء تستبعد قيود الإقفال.
          </p>
        </Card>

        {periods.loading ? <Skeleton rows={3} />
          : periods.error ? <ErrorState message={periods.error} onRetry={periods.reload} />
          : (periods.data?.items || []).length === 0 ? <EmptyState title="لا فترات لهذه السنة" />
          : (
            <div className="space-y-3" data-testid="m-periods-list">
              {periods.data.items.map((p) => (
                <Card key={p.id} testid={`m-period-${p.id}`}>
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-xs font-mono font-bold text-[#0A2540]">
                        {p.code || `${p.fiscal_year}-${p.period_no}`}
                      </p>
                      <p className="text-[11px] text-muted-foreground">
                        {String(p.start_date).slice(0, 10)} → {String(p.end_date).slice(0, 10)}
                      </p>
                    </div>
                    <div className="text-end shrink-0 space-y-1">
                      <StatusPill status={p.status === "CLOSED" ? "cancelled" : "green"} />
                      {p.status !== "CLOSED" && caps.period_close && (
                        <button disabled={busy} data-testid={`m-period-close-${p.id}`}
                                onClick={() => run((r) => accApi.closePeriod(p.id, r), "تم إقفال الفترة")}
                                className="block text-[11px] font-bold text-[#0A2540] underline">إقفال</button>
                      )}
                      {p.status === "CLOSED" && caps.period_reopen && (
                        <button disabled={busy} data-testid={`m-period-reopen-${p.id}`}
                                onClick={() => run((r) => accApi.reopenPeriod(p.id, r), "تمت إعادة الفتح")}
                                className="block text-[11px] font-bold text-red-600 underline">إعادة فتح</button>
                      )}
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        <p className="text-[11px] text-muted-foreground px-1">
          الإقفال السنوي وإعادة فتح السنة يُنفَّذان من لوحة الويب للحد من المخاطر على الجوال.
        </p>
      </div>
    </Screen>
  );
}
