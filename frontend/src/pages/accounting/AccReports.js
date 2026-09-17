import { useState } from "react";
import { PageHeader } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Printer } from "lucide-react";
import { Panel, Field, inputCls, Loading, ErrorNote, Empty, useFetch, Money, Badge } from "./ui";

const TABS = [
  { key: "tb", label: "ميزان المراجعة" },
  { key: "is", label: "قائمة الدخل" },
  { key: "bs", label: "الميزانية / المركز المالي" },
];

const today = () => new Date().toISOString().slice(0, 10);
const yearStart = () => `${new Date().getFullYear()}-01-01`;

export default function AccReports() {
  const [tab, setTab] = useState("tb");
  const [f, setF] = useState({ currency: "SAR", from: yearStart(), to: today(), as_of: today() });
  const [applied, setApplied] = useState(null);

  const url = (() => {
    if (!applied) return null;
    const c = `currency=${applied.currency}`;
    if (tab === "tb") return `/accounting/reports/trial-balance?${c}&as_of=${new Date(applied.as_of).toISOString()}`;
    if (tab === "is") return `/accounting/reports/income-statement?${c}&from_date=${new Date(applied.from).toISOString()}&to_date=${new Date(applied.to).toISOString()}`;
    return `/accounting/reports/balance-sheet?${c}&as_of=${new Date(applied.as_of).toISOString()}`;
  })();
  const rep = useFetch(url, [url]);

  const rows = (() => {
    const d = rep.data;
    if (!d) return [];
    if (tab === "tb") return d.rows || d.items || [];
    if (tab === "is") return [...(d.revenue?.rows || []), ...(d.expenses?.rows || [])];
    return [...(d.assets?.rows || []), ...(d.liabilities?.rows || []), ...(d.equity?.rows || [])];
  })();

  return (
    <>
      <PageHeader title="التقارير المالية" subtitle="تُحتسب من النواة المحاسبية لحظة العرض — لا أرصدة محسوبة في الواجهة" />

      <div className="flex flex-wrap gap-2 mb-5" data-testid="reports-tabs">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => { setTab(t.key); setApplied(null); }} data-testid={`reports-tab-${t.key}`}
                  className={`h-10 px-4 rounded-lg text-sm font-semibold ${tab === t.key ? "bg-[#0A2540] text-white" : "bg-white border text-[#0A2540] hover:bg-slate-50"}`}>
            {t.label}
          </button>
        ))}
      </div>

      <ErrorNote>{rep.error}</ErrorNote>

      <Panel testid="reports-filters">
        <div className="grid sm:grid-cols-4 gap-3">
          <Field label="العملة">
            <select className={inputCls} value={f.currency} data-testid="reports-currency"
                    onChange={(e) => setF({ ...f, currency: e.target.value })}>
              <option value="SAR">SAR</option><option value="USD">USD</option>
            </select>
          </Field>
          {tab === "is" ? (
            <>
              <Field label="من تاريخ"><input type="date" className={inputCls} value={f.from} data-testid="reports-from"
                onChange={(e) => setF({ ...f, from: e.target.value })} /></Field>
              <Field label="إلى تاريخ"><input type="date" className={inputCls} value={f.to} data-testid="reports-to"
                onChange={(e) => setF({ ...f, to: e.target.value })} /></Field>
            </>
          ) : (
            <Field label="كما في تاريخ"><input type="date" className={inputCls} value={f.as_of} data-testid="reports-asof"
              onChange={(e) => setF({ ...f, as_of: e.target.value })} /></Field>
          )}
          <div className="flex items-end gap-2">
            <Button className="bg-[#0A2540]" data-testid="reports-run" onClick={() => setApplied({ ...f })}>عرض التقرير</Button>
            <Button variant="outline" onClick={() => window.print()} data-testid="reports-print"><Printer className="w-4 h-4" /></Button>
          </div>
        </div>
      </Panel>

      {applied && (
        <Panel testid="reports-result" title={TABS.find((t) => t.key === tab).label}>
          {rep.loading ? <Loading /> : !rep.data ? <Empty /> : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 text-sm" data-testid="reports-summary">
                {tab === "tb" && <>
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-[11px] text-muted-foreground">إجمالي مدين</div><div className="font-bold"><Money value={rep.data.total_debit} /></div></div>
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-[11px] text-muted-foreground">إجمالي دائن</div><div className="font-bold"><Money value={rep.data.total_credit} /></div></div>
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-[11px] text-muted-foreground">التوازن</div><div><Badge tone={rep.data.balanced ? "green" : "red"}>{rep.data.balanced ? "متوازن" : "غير متوازن"}</Badge></div></div>
                </>}
                {tab === "is" && <>
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-[11px] text-muted-foreground">الإيرادات</div><div className="font-bold"><Money value={rep.data.revenue?.total} /></div></div>
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-[11px] text-muted-foreground">المصروفات</div><div className="font-bold"><Money value={rep.data.expenses?.total} /></div></div>
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-[11px] text-muted-foreground">صافي النتيجة</div><div className="font-bold" data-testid="reports-net"><Money value={rep.data.net_result ?? rep.data.net_income} /></div></div>
                </>}
                {tab === "bs" && <>
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-[11px] text-muted-foreground">الأصول</div><div className="font-bold"><Money value={rep.data.assets?.total} /></div></div>
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-[11px] text-muted-foreground">الخصوم</div><div className="font-bold"><Money value={rep.data.liabilities?.total} /></div></div>
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-[11px] text-muted-foreground">حقوق الملكية</div><div className="font-bold"><Money value={rep.data.equity?.total} /></div></div>
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-[11px] text-muted-foreground">التوازن</div><div><Badge tone={rep.data.balanced ? "green" : "red"}>{rep.data.balanced ? "متوازن" : "غير متوازن"}</Badge></div></div>
                </>}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-xs text-muted-foreground">
                    <th className="py-2 text-start">الحساب</th><th className="text-start">الاسم</th>
                    {tab === "tb" ? <><th className="text-start">مدين</th><th className="text-start">دائن</th></>
                      : <th className="text-start">الرصيد</th>}</tr></thead>
                  <tbody>
                    {rows.map((r, i) => (
                      <tr key={i} className="border-t" data-testid={`report-row-${i}`}>
                        <td className="py-2 font-mono text-[11px]">{r.code || r.account_code}</td>
                        <td className="text-xs">{r.name_ar || r.name}</td>
                        {tab === "tb" ? <><td><Money value={r.debit} /></td><td><Money value={r.credit} /></td></>
                          : <td className="font-semibold"><Money value={r.balance ?? r.amount} /></td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {rows.length === 0 && <Empty>لا أرصدة في هذا النطاق</Empty>}
            </>
          )}
        </Panel>
      )}
    </>
  );
}
