import { useState } from "react";
import accApi from "@/mobile/api/accounting";
import { Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, mInput, MField, PrimaryButton, useAsync } from "@/mobile/ui/kit";

export default function MAccLedger() {
  const accounts = useAsync(() => accApi.accounts());
  const [f, setF] = useState({ code: "", currency: "SAR", date_from: "", date_to: "" });
  const [applied, setApplied] = useState(null);
  const led = useAsync(() => (applied
    ? accApi.ledger(applied.code, { currency: applied.currency, page_size: 50,
        date_from: applied.date_from || undefined, date_to: applied.date_to || undefined })
    : Promise.resolve(null)), [JSON.stringify(applied)]);

  const leaves = (accounts.data?.items || []).filter((a) => !a.is_group);

  return (
    <Screen>
      <TopBar title="الأستاذ وكشف الحساب" subtitle="مشتق من القيود المُرحَّلة" back />
      <div className="p-4 space-y-3">
        <Card testid="m-ledger-filters">
          <MField label="الحساب">
            <select className={mInput} value={f.code} data-testid="m-ledger-account"
                    onChange={(e) => setF({ ...f, code: e.target.value })}>
              <option value="">— اختر حساباً —</option>
              {leaves.map((a) => <option key={a.code} value={a.code}>{a.code} — {a.name_ar || a.name}</option>)}
            </select>
          </MField>
          <div className="grid grid-cols-3 gap-2">
            <MField label="العملة">
              <select className={mInput} value={f.currency} data-testid="m-ledger-currency"
                      onChange={(e) => setF({ ...f, currency: e.target.value })}>
                <option value="SAR">SAR</option><option value="USD">USD</option>
              </select>
            </MField>
            <MField label="من">
              <input type="date" className={mInput} value={f.date_from} data-testid="m-ledger-from"
                     onChange={(e) => setF({ ...f, date_from: e.target.value })} />
            </MField>
            <MField label="إلى">
              <input type="date" className={mInput} value={f.date_to} data-testid="m-ledger-to"
                     onChange={(e) => setF({ ...f, date_to: e.target.value })} />
            </MField>
          </div>
          <PrimaryButton disabled={!f.code} onClick={() => setApplied({ ...f })} data-testid="m-ledger-run">
            عرض الحركة
          </PrimaryButton>
        </Card>

        {applied && (led.loading ? <Skeleton rows={3} />
          : led.error ? <ErrorState message={led.error} onRetry={led.reload} />
          : led.data && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <Card testid="m-ledger-opening">
                  <p className="text-[11px] text-muted-foreground">رصيد افتتاحي</p>
                  <p className="text-sm mt-1"><Money value={led.data.opening_balance_for_range} /></p>
                </Card>
                <Card testid="m-ledger-closing">
                  <p className="text-[11px] text-muted-foreground">رصيد ختامي</p>
                  <p className="text-sm mt-1"><Money value={led.data.closing_balance} /></p>
                </Card>
              </div>
              {(led.data.items || []).length === 0 ? <EmptyState title="لا حركة في هذا النطاق" /> : (
                <div className="space-y-3" data-testid="m-ledger-rows">
                  {led.data.items.map((l, i) => (
                    <Card key={i} testid={`m-ledger-row-${i}`}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-[11px] font-mono font-bold text-[#0A2540]">{l.entry_no}</p>
                          <p className="text-[11px] text-muted-foreground truncate">{l.description || l.memo}</p>
                          <p className="text-[10px] text-muted-foreground">{String(l.date).slice(0, 10)}</p>
                        </div>
                        <div className="text-end shrink-0 text-[11px]">
                          <div>مدين <Money value={l.debit} /></div>
                          <div>دائن <Money value={l.credit} /></div>
                          <div className="font-bold mt-0.5">الرصيد <Money value={l.running_balance} /></div>
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>
              )}
            </>
          ))}
      </div>
    </Screen>
  );
}
