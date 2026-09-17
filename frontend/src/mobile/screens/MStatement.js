import { useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import mobileApi from "@/mobile/api/client";
import {
  Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, KpiCard, Sheet, SheetSelect,
  DateField, PrimaryButton, useAsync,
} from "@/mobile/ui/kit";

const CURRENCIES = [{ value: "SAR", label: "ريال سعودي (SAR)" }, { value: "USD", label: "دولار أمريكي (USD)" }];

/** كشف حساب المكتب (تجاري) — reads the SAME business endpoint the web uses; the backend
 *  pins an office user to its own office whatever it sends. Never a general ledger. */
export default function MStatement() {
  const [f, setF] = useState({ currency: "SAR", date_from: "", date_to: "" });
  const [draft, setDraft] = useState(f);
  const [sheet, setSheet] = useState(false);
  const st = useAsync(() => mobileApi.officeStatement({
    currency: f.currency, date_from: f.date_from || undefined, date_to: f.date_to || undefined,
  }), [JSON.stringify(f)]);

  return (
    <Screen refresh={st.reload}>
      <TopBar title="كشف حساب المكتب" subtitle="علاقتك التجارية مع معراج" back
              right={<button onClick={() => { setDraft(f); setSheet(true); }} data-testid="m-statement-filter-btn"
                             aria-label="تصفية"
                             className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center">
                <SlidersHorizontal className="w-4 h-4" /></button>} />

      <div className="p-4 space-y-3.5">
        {st.loading ? <Skeleton rows={3} />
          : st.error ? <ErrorState message={st.error} onRetry={st.reload} />
          : (
            <>
              <div className="grid grid-cols-2 gap-3">
                <KpiCard label="رصيد افتتاحي" testid="m-statement-opening"
                         value={<Money value={st.data.opening_balance} currency={f.currency} />} />
                <KpiCard label="رصيد ختامي" tone="gold" testid="m-statement-closing"
                         value={<Money value={st.data.closing_balance} currency={f.currency} />} />
              </div>

              {(st.data.items || []).length === 0 ? <EmptyState title="لا حركات في هذا النطاق" /> : (
                <div className="space-y-3 m-stagger" data-testid="m-statement-rows">
                  {st.data.items.map((r) => (
                    <Card key={r.id} testid={`m-statement-row-${r.id}`}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-bold text-[#0A2540]">{r.type_label}</p>
                          <p className="text-[11px] text-muted-foreground truncate mt-0.5">{r.description || "—"}</p>
                          <p className="text-[10.5px] text-muted-foreground mt-1">{String(r.date).slice(0, 10)}</p>
                        </div>
                        <div className="text-end shrink-0">
                          <div className={`text-sm font-bold ${r.direction === "in" ? "text-emerald-700" : "text-red-700"}`}>
                            {r.direction === "in" ? "+" : "-"}
                            <Money value={r.inflow || r.outflow} currency={r.currency} />
                          </div>
                          <p className="text-[10.5px] text-muted-foreground mt-1.5">
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

      <Sheet open={sheet} onClose={() => setSheet(false)} title="تصفية الكشف" testid="m-statement-filters">
        <SheetSelect label="العملة" value={draft.currency} options={CURRENCIES} testid="m-statement-currency"
                     onChange={(v) => setDraft({ ...draft, currency: v })} />
        <div className="grid grid-cols-2 gap-3">
          <DateField label="من تاريخ" value={draft.date_from} testid="m-statement-from"
                     onChange={(v) => setDraft({ ...draft, date_from: v })} />
          <DateField label="إلى تاريخ" value={draft.date_to} testid="m-statement-to"
                     onChange={(v) => setDraft({ ...draft, date_to: v })} />
        </div>
        <PrimaryButton onClick={() => { setF(draft); setSheet(false); }} data-testid="m-statement-apply">
          تطبيق
        </PrimaryButton>
      </Sheet>
    </Screen>
  );
}
