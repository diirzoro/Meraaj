import { useState } from "react";
import { PageHeader } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Printer } from "lucide-react";
import { Panel, Field, inputCls, Loading, ErrorNote, ScopeNote, Empty, useFetch, Money, Badge } from "./ui";

export default function AccLedger() {
  const accounts = useFetch("/accounting/accounts?include_inactive=true");
  const [f, setF] = useState({ account_code: "", currency: "SAR", date_from: "", date_to: "", page: 1 });
  const [applied, setApplied] = useState(null);

  const url = applied
    ? `/accounting/ledger/${encodeURIComponent(applied.account_code)}?currency=${applied.currency}` +
      `${applied.date_from ? `&date_from=${applied.date_from}` : ""}${applied.date_to ? `&date_to=${applied.date_to}` : ""}` +
      `&page=${applied.page}&page_size=50`
    : null;
  const led = useFetch(url, [url]);
  const leaves = (accounts.data?.items || []).filter((a) => !a.is_group);

  return (
    <>
      <PageHeader title="الأستاذ العام وكشف الحساب المحاسبي"
        subtitle="عرض مشتق من القيود المُرحَّلة — ليس كشف حساب المكتب التجاري" />

      <ErrorNote>{accounts.error || led.error}</ErrorNote>
      <ScopeNote scope={accounts.data?.account_scope} />

      <Panel testid="ledger-filters">
        <div className="grid sm:grid-cols-5 gap-3">
          <div className="sm:col-span-2">
            <Field label="الحساب">
              <select className={inputCls} value={f.account_code} data-testid="ledger-account"
                      onChange={(e) => setF({ ...f, account_code: e.target.value })}>
                <option value="">— اختر حساباً —</option>
                {leaves.map((a) => <option key={a.code} value={a.code}>{a.code} — {a.name_ar || a.name}</option>)}
              </select>
            </Field>
          </div>
          <Field label="العملة">
            <select className={inputCls} value={f.currency} data-testid="ledger-currency"
                    onChange={(e) => setF({ ...f, currency: e.target.value })}>
              <option value="SAR">SAR</option><option value="USD">USD</option>
            </select>
          </Field>
          <Field label="من تاريخ"><input type="date" className={inputCls} data-testid="ledger-from"
            value={f.date_from} onChange={(e) => setF({ ...f, date_from: e.target.value })} /></Field>
          <Field label="إلى تاريخ"><input type="date" className={inputCls} data-testid="ledger-to"
            value={f.date_to} onChange={(e) => setF({ ...f, date_to: e.target.value })} /></Field>
        </div>
        <div className="flex gap-2 mt-3">
          <Button disabled={!f.account_code} className="bg-[#0A2540]" data-testid="ledger-run"
                  onClick={() => setApplied({ ...f, page: 1 })}>عرض الحركة</Button>
          <Button variant="outline" onClick={() => window.print()} data-testid="ledger-print"><Printer className="w-4 h-4 me-1" /> طباعة</Button>
        </div>
      </Panel>

      {applied && (
        <Panel testid="ledger-result" title={`حركة الحساب ${applied.account_code}`}>
          {led.loading ? <Loading /> : !led.data ? <Empty /> : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 text-sm">
                <div className="rounded-lg bg-slate-50 p-3" data-testid="ledger-opening">
                  <div className="text-[11px] text-muted-foreground">الرصيد الافتتاحي</div>
                  <div className="font-bold"><Money value={led.data.opening_balance_for_range} /></div>
                </div>
                <div className="rounded-lg bg-slate-50 p-3"><div className="text-[11px] text-muted-foreground">إجمالي مدين</div>
                  <div className="font-bold"><Money value={led.data.total_debit} /></div></div>
                <div className="rounded-lg bg-slate-50 p-3"><div className="text-[11px] text-muted-foreground">إجمالي دائن</div>
                  <div className="font-bold"><Money value={led.data.total_credit} /></div></div>
                <div className="rounded-lg bg-slate-50 p-3" data-testid="ledger-closing"><div className="text-[11px] text-muted-foreground">الرصيد الختامي</div>
                  <div className="font-bold"><Money value={led.data.closing_balance} /></div></div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-xs text-muted-foreground">
                    <th className="py-2 text-start">التاريخ</th><th className="text-start">القيد</th>
                    <th className="text-start">البيان</th><th className="text-start">المصدر</th>
                    <th className="text-start">مدين</th><th className="text-start">دائن</th>
                    <th className="text-start">الرصيد الجاري</th></tr></thead>
                  <tbody>
                    {(led.data.items || []).map((l, i) => (
                      <tr key={i} className="border-t" data-testid={`ledger-line-${i}`}>
                        <td className="py-2 text-xs whitespace-nowrap">{String(l.date).slice(0, 10)}</td>
                        <td className="font-mono text-[11px]">{l.entry_no}</td>
                        <td className="text-xs max-w-[16rem] truncate">{l.description || l.memo}</td>
                        <td className="text-[11px]">{l.source_type}</td>
                        <td><Money value={l.debit} /></td>
                        <td><Money value={l.credit} /></td>
                        <td className="font-semibold"><Money value={l.running_balance} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {(led.data.items || []).length === 0 && <Empty>لا حركة في هذا النطاق</Empty>}
              <div className="flex items-center gap-2 mt-4">
                <Button size="sm" variant="outline" disabled={applied.page <= 1} data-testid="ledger-prev"
                        onClick={() => setApplied({ ...applied, page: applied.page - 1 })}>السابق</Button>
                <Badge>صفحة {applied.page}</Badge>
                <Button size="sm" variant="outline" data-testid="ledger-next"
                        disabled={(led.data.items || []).length < 50}
                        onClick={() => setApplied({ ...applied, page: applied.page + 1 })}>التالي</Button>
              </div>
            </>
          )}
        </Panel>
      )}
    </>
  );
}
