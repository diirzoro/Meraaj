import { useState } from "react";
import mobileApi from "@/mobile/api/client";
import { Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, mInput, MField, useAsync } from "@/mobile/ui/kit";

/** كشف حساب المكتب (تجاري) — reads the SAME business endpoint the web uses; the backend
 *  pins an office user to its own office whatever it sends. Never a general ledger. */
export default function MStatement() {
  const [f, setF] = useState({ currency: "SAR", date_from: "", date_to: "" });
  const st = useAsync(() => mobileApi.officeStatement({
    currency: f.currency, date_from: f.date_from || undefined, date_to: f.date_to || undefined,
  }), [JSON.stringify(f)]);

  return (
    <Screen>
      <TopBar title="كشف حساب المكتب" subtitle="علاقتك التجارية مع معراج" back />
      <div className="p-4 space-y-3">
        <Card testid="m-statement-filters">
          <MField label="العملة">
            <select className={mInput} value={f.currency} data-testid="m-statement-currency"
                    onChange={(e) => setF({ ...f, currency: e.target.value })}>
              <option value="SAR">SAR</option><option value="USD">USD</option>
            </select>
          </MField>
          <div className="grid grid-cols-2 gap-3">
            <MField label="من تاريخ">
              <input type="date" className={mInput} value={f.date_from} data-testid="m-statement-from"
                     onChange={(e) => setF({ ...f, date_from: e.target.value })} />
            </MField>
            <MField label="إلى تاريخ">
              <input type="date" className={mInput} value={f.date_to} data-testid="m-statement-to"
                     onChange={(e) => setF({ ...f, date_to: e.target.value })} />
            </MField>
          </div>
        </Card>

        {st.loading ? <Skeleton rows={3} />
          : st.error ? <ErrorState message={st.error} onRetry={st.reload} />
          : (
            <>
              <div className="grid grid-cols-2 gap-3">
                <Card testid="m-statement-opening">
                  <p className="text-[11px] text-muted-foreground">رصيد افتتاحي</p>
                  <p className="text-sm mt-1"><Money value={st.data.opening_balance} /></p>
                </Card>
                <Card testid="m-statement-closing">
                  <p className="text-[11px] text-muted-foreground">رصيد ختامي</p>
                  <p className="text-sm mt-1"><Money value={st.data.closing_balance} /></p>
                </Card>
              </div>

              {(st.data.items || []).length === 0 ? <EmptyState title="لا حركات في هذا النطاق" /> : (
                <div className="space-y-3" data-testid="m-statement-rows">
                  {st.data.items.map((r) => (
                    <Card key={r.id} testid={`m-statement-row-${r.id}`}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-xs font-semibold text-[#0A2540]">{r.type_label}</p>
                          <p className="text-[11px] text-muted-foreground truncate">{r.description || "—"}</p>
                          <p className="text-[10px] text-muted-foreground mt-0.5">{String(r.date).slice(0, 10)}</p>
                        </div>
                        <div className="text-end shrink-0">
                          <div className={`text-xs ${r.direction === "in" ? "text-emerald-700" : "text-red-700"}`}>
                            {r.direction === "in" ? "+" : "-"}
                            <Money value={r.inflow || r.outflow} currency={r.currency} />
                          </div>
                          <p className="text-[10px] text-muted-foreground mt-1">
                            الرصيد: <Money value={r.running_balance} />
                          </p>
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>
              )}
            </>
          )}
      </div>
    </Screen>
  );
}
