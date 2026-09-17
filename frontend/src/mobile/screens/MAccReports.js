import { useState } from "react";
import accApi from "@/mobile/api/accounting";
import { useShell } from "@/mobile/MobileShell";
import { ScopeBanner } from "@/mobile/screens/MAccountingHub";
import {
  Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, KpiCard, Segmented, SheetSelect, useAsync,
} from "@/mobile/ui/kit";

const TABS = [["tb", "ميزان المراجعة"], ["is", "قائمة الدخل"], ["bs", "المركز المالي"]];
const CURRENCIES = [{ value: "SAR", label: "ريال سعودي (SAR)" }, { value: "USD", label: "دولار أمريكي (USD)" }];

export default function MAccReports() {
  const { shell } = useShell();
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
    ? [["إجمالي مدين", d.total_debit, "navy"], ["إجمالي دائن", d.total_credit, "navy"]]
    : tab === "is"
      ? [["الإيرادات", d.revenue?.total, "good"], ["المصروفات", d.expenses?.total, "bad"],
         ["صافي النتيجة", d.net_result ?? d.net_income, "gold"]]
      : [["الأصول", d.assets?.total, "navy"], ["الخصوم", d.liabilities?.total, "warn"],
         ["حقوق الملكية", d.equity?.total, "gold"]];

  return (
    <Screen refresh={rep.reload}>
      <TopBar title="التقارير المالية" subtitle="تُحتسب في النواة لحظة العرض" back />
      <div className="p-4 space-y-3.5">
        <Segmented items={TABS} value={tab} onChange={setTab} scroll
                   testid="m-reports-tabs" testidPrefix="m-reports-tab-" />
        <ScopeBanner scope={d.account_scope || shell?.accounting?.account_scope}
                     testid="m-reports-scope-note" label="نطاقك المحاسبي" />
        <Card>
          <SheetSelect label="العملة" value={currency} options={CURRENCIES} testid="m-reports-currency"
                       onChange={setCurrency} />
        </Card>

        {rep.loading ? <Skeleton rows={3} />
          : rep.error ? <ErrorState message={rep.error} onRetry={rep.reload} />
          : (
            <>
              <div className="grid grid-cols-2 gap-3" data-testid="m-reports-summary">
                {summary.map(([label, value, tone]) => (
                  <KpiCard key={label} label={label} tone={tone}
                           value={<Money value={value} currency={currency} />} />
                ))}
              </div>
              {rows.length === 0 ? <EmptyState title="لا أرصدة" /> : (
                <Card className="p-0 overflow-hidden" testid="m-reports-rows">
                  {rows.map((r, i) => (
                    <div key={i} className="flex items-center justify-between px-4 py-3.5 border-b border-black/5 last:border-0"
                         data-testid={`m-report-row-${i}`}>
                      <div className="min-w-0">
                        <p className="text-xs font-mono font-bold text-[#0A2540]" dir="ltr">{r.code || r.account_code}</p>
                        <p className="text-xs text-[#0A2540]/70 truncate mt-0.5">{r.name_ar || r.name}</p>
                      </div>
                      <div className="text-end text-[11px] shrink-0 ms-3">
                        {tab === "tb"
                          ? <><div className="text-muted-foreground">مدين <Money value={r.debit} /></div>
                              <div className="text-muted-foreground">دائن <Money value={r.credit} /></div></>
                          : <Money value={r.balance ?? r.amount} className="text-sm" />}
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
