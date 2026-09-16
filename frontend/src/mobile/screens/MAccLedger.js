import { useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import accApi from "@/mobile/api/accounting";
import {
  Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, KpiCard, Sheet, SheetSelect,
  DateField, PrimaryButton, useAsync,
} from "@/mobile/ui/kit";

const CURRENCIES = [{ value: "SAR", label: "ريال سعودي (SAR)" }, { value: "USD", label: "دولار أمريكي (USD)" }];

export default function MAccLedger() {
  const accounts = useAsync(() => accApi.accounts());
  const [f, setF] = useState({ code: "", currency: "SAR", date_from: "", date_to: "" });
  const [applied, setApplied] = useState(null);
  const [sheet, setSheet] = useState(true);
  const led = useAsync(() => (applied
    ? accApi.ledger(applied.code, { currency: applied.currency, page_size: 50,
        date_from: applied.date_from || undefined, date_to: applied.date_to || undefined })
    : Promise.resolve(null)), [JSON.stringify(applied)]);

  const options = (accounts.data?.items || []).filter((a) => !a.is_group)
    .map((a) => ({ value: a.code, label: `${a.code} — ${a.name_ar || a.name}` }));
  const selected = options.find((o) => o.value === applied?.code);

  return (
    <Screen refresh={applied ? led.reload : undefined}>
      <TopBar title="الأستاذ وكشف الحساب" subtitle={selected ? selected.label : "اختر حساباً"} back
              right={<button onClick={() => setSheet(true)} data-testid="m-ledger-filter-btn" aria-label="تصفية"
                             className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center">
                <SlidersHorizontal className="w-4 h-4" /></button>} />

      <div className="p-4 space-y-3.5">
        {!applied && !sheet && (
          <EmptyState title="لم تختر حساباً" hint="اضغط زر التصفية لاختيار الحساب والفترة"
                      action={<PrimaryButton onClick={() => setSheet(true)}>اختيار حساب</PrimaryButton>} />
        )}

        {applied && (led.loading ? <Skeleton rows={3} />
          : led.error ? <ErrorState message={led.error} onRetry={led.reload} />
          : led.data && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <KpiCard label="رصيد افتتاحي" testid="m-ledger-opening"
                         value={<Money value={led.data.opening_balance_for_range} currency={applied.currency} />} />
                <KpiCard label="رصيد ختامي" tone="gold" testid="m-ledger-closing"
                         value={<Money value={led.data.closing_balance} currency={applied.currency} />} />
              </div>
              {(led.data.items || []).length === 0 ? <EmptyState title="لا حركة في هذا النطاق" /> : (
                <div className="space-y-3 m-stagger" data-testid="m-ledger-rows">
                  {led.data.items.map((l, i) => (
                    <Card key={i} testid={`m-ledger-row-${i}`}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-xs font-mono font-bold text-[#0A2540]" dir="ltr">{l.entry_no}</p>
                          <p className="text-xs text-[#0A2540]/70 line-clamp-1 mt-1">{l.description || l.memo}</p>
                          <p className="text-[10.5px] text-muted-foreground mt-1">{String(l.date).slice(0, 10)}</p>
                        </div>
                        <div className="text-end shrink-0 text-[11px] space-y-0.5">
                          <div className="text-muted-foreground">مدين <Money value={l.debit} /></div>
                          <div className="text-muted-foreground">دائن <Money value={l.credit} /></div>
                          <div className="text-[#0A2540] pt-1 border-t border-black/5 mt-1">
                            الرصيد <Money value={l.running_balance} />
                          </div>
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>
              )}
            </>
          ))}
      </div>

      <Sheet open={sheet} onClose={() => setSheet(false)} title="الحساب والفترة" testid="m-ledger-filters">
        <SheetSelect label="الحساب" value={f.code} options={options} testid="m-ledger-account"
                     placeholder="— اختر حساباً —" onChange={(v) => setF({ ...f, code: v })} />
        <SheetSelect label="العملة" value={f.currency} options={CURRENCIES} testid="m-ledger-currency"
                     onChange={(v) => setF({ ...f, currency: v })} />
        <div className="grid grid-cols-2 gap-3">
          <DateField label="من" value={f.date_from} testid="m-ledger-from"
                     onChange={(v) => setF({ ...f, date_from: v })} />
          <DateField label="إلى" value={f.date_to} testid="m-ledger-to"
                     onChange={(v) => setF({ ...f, date_to: v })} />
        </div>
        <PrimaryButton disabled={!f.code} data-testid="m-ledger-run"
                       onClick={() => { setApplied({ ...f }); setSheet(false); }}>
          عرض الحركة
        </PrimaryButton>
      </Sheet>
    </Screen>
  );
}
