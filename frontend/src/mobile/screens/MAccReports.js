import { useState } from "react";
import accApi from "@/mobile/api/accounting";
import { Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, mInput, MField, useAsync } from "@/mobile/ui/kit";

const TABS = [["tb", "ميزان المراجعة"], ["is", "قائمة الدخل"], ["bs", "المركز المالي"]];

export default function MAccReports() {
  const [tab, setTab] = useState("tb");
  const [currency, setCurrency] = useState("SAR");
  const rep = useAsync(() => (
    tab === "tb" ? accApi.trialBalance(currency)
      : tab === "is" ? accApi.incomeStatement(currency)
      : accApi.balanceSheet(currency)
  ), [tab, currency]);

  const d = rep.data || {};
  const rows = tab === "tb" ? (d.rows || d.items || [])
    : tab === "is" ? [...(d.revenue?.rows || []), ...(d.expenses?.rows || [])]
    : [...(d.assets?.rows || []), ...(d.liabilities?.rows || []), ...(d.equity?.rows || [])];

  const summary = tab === "tb"
    ? [["إجمالي مدين", d.total_debit], ["إجمالي دائن", d.total_credit]]
    : tab === "is"
      ? [["الإيرادات", d.revenue?.total], ["المصروفات", d.expenses?.total],
         ["صافي النتيجة", d.net_result ?? d.net_income]]
      : [["الأصول", d.assets?.total], ["الخصوم", d.liabilities?.total],
         ["حقوق الملكية", d.equity?.total]];

  return (
    <Screen>
      <TopBar title="التقارير المالية" subtitle="تُحتسب في النواة لحظة العرض" back />
      <div className="p-4 space-y-3">
        <div className="flex gap-2 overflow-x-auto" data-testid="m-reports-tabs">
          {TABS.map(([k, l]) => (
            <button key={k} onClick={() => setTab(k)} data-testid={`m-reports-tab-${k}`}
                    className={`h-10 px-4 rounded-full text-xs font-bold whitespace-nowrap ${tab === k ? "bg-[#0A2540] text-white" : "bg-white border text-[#0A2540]"}`}>
              {l}
            </button>
          ))}
        </div>
        <Card>
          <MField label="العملة">
            <select className={mInput} value={currency} data-testid="m-reports-currency"
                    onChange={(e) => setCurrency(e.target.value)}>
              <option value="SAR">SAR</option><option value="USD">USD</option>
            </select>
          </MField>
        </Card>

        {rep.loading ? <Skeleton rows={3} />
          : rep.error ? <ErrorState message={rep.error} onRetry={rep.reload} />
          : (
            <>
              <div className="grid grid-cols-2 gap-3" data-testid="m-reports-summary">
                {summary.map(([label, value]) => (
                  <Card key={label}>
                    <p className="text-[11px] text-muted-foreground">{label}</p>
                    <p className="text-sm mt-1"><Money value={value} currency={currency} /></p>
                  </Card>
                ))}
              </div>
              {rows.length === 0 ? <EmptyState title="لا أرصدة" /> : (
                <Card className="p-0 overflow-hidden" testid="m-reports-rows">
                  {rows.map((r, i) => (
                    <div key={i} className="flex items-center justify-between px-4 py-2.5 border-b last:border-0"
                         data-testid={`m-report-row-${i}`}>
                      <div className="min-w-0">
                        <p className="text-[11px] font-mono text-[#0A2540]">{r.code || r.account_code}</p>
                        <p className="text-[11px] text-muted-foreground truncate">{r.name_ar || r.name}</p>
                      </div>
                      <div className="text-end text-[11px] shrink-0">
                        {tab === "tb"
                          ? <><div>مدين <Money value={r.debit} /></div><div>دائن <Money value={r.credit} /></div></>
                          : <Money value={r.balance ?? r.amount} />}
                      </div>
                    </div>
                  ))}
                </Card>
              )}
            </>
          )}
      </div>
    </Screen>
  );
}
