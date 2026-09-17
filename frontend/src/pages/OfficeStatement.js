import { useState } from "react";
import { PageHeader } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { Printer } from "lucide-react";
import { Panel, Field, inputCls, Loading, ErrorNote, Empty, useFetch, Money, Badge } from "./accounting/ui";

/** كشف حساب المكتب — BUSINESS statement. Never a ledger: no COA, no TB/P&L/BS. */
export default function OfficeStatement() {
  const { user, can } = useAuth();
  const privileged = user?.role === "super_admin" || can("office.statement.view");
  const offices = useFetch(privileged ? "/office-statement/offices" : null);
  const [f, setF] = useState({ office_id: "", currency: "SAR", date_from: "", date_to: "", txn_type: "" });

  const qs = new URLSearchParams();
  Object.entries(f).forEach(([k, v]) => { if (v) qs.set(k, v); });
  const st = useFetch(`/office-statement?${qs.toString()}`, [qs.toString()]);

  return (
    <>
      <PageHeader title="كشف حساب المكتب"
        subtitle="العلاقة التجارية بين المكتب ومعراج — ليس أستاذاً محاسبياً ولا دليل حسابات"
        action={<Button variant="outline" onClick={() => window.print()} data-testid="office-statement-print">
          <Printer className="w-4 h-4 me-1" /> طباعة</Button>} />

      <ErrorNote>{st.error}</ErrorNote>

      <Panel testid="office-statement-filters">
        <div className="grid sm:grid-cols-5 gap-3">
          {privileged && (
            <div className="sm:col-span-2">
              <Field label="المكتب">
                <select className={inputCls} value={f.office_id} data-testid="office-statement-office"
                        onChange={(e) => setF({ ...f, office_id: e.target.value })}>
                  <option value="">— مكتبي —</option>
                  {(offices.data?.items || []).map((o) => (
                    <option key={o.id} value={o.id}>{o.name || o.email}</option>
                  ))}
                </select>
              </Field>
            </div>
          )}
          <Field label="العملة">
            <select className={inputCls} value={f.currency} data-testid="office-statement-currency"
                    onChange={(e) => setF({ ...f, currency: e.target.value })}>
              <option value="SAR">SAR</option><option value="USD">USD</option>
            </select>
          </Field>
          <Field label="من تاريخ"><input type="date" className={inputCls} value={f.date_from} data-testid="office-statement-from"
            onChange={(e) => setF({ ...f, date_from: e.target.value })} /></Field>
          <Field label="إلى تاريخ"><input type="date" className={inputCls} value={f.date_to} data-testid="office-statement-to"
            onChange={(e) => setF({ ...f, date_to: e.target.value })} /></Field>
          <Field label="نوع الحركة">
            <select className={inputCls} value={f.txn_type} data-testid="office-statement-type"
                    onChange={(e) => setF({ ...f, txn_type: e.target.value })}>
              <option value="">— الكل —</option>
              {Object.entries(st.data?.movement_types || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
        </div>
      </Panel>

      {st.loading ? <Loading /> : !st.data ? <Empty /> : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-5 text-sm">
            <div className="bg-white rounded-2xl border card-shadow p-4" data-testid="office-statement-opening">
              <div className="text-[11px] text-muted-foreground">رصيد افتتاحي</div>
              <div className="font-bold"><Money value={st.data.opening_balance} /></div></div>
            <div className="bg-white rounded-2xl border card-shadow p-4"><div className="text-[11px] text-muted-foreground">وارد</div>
              <div className="font-bold text-emerald-700"><Money value={st.data.totals?.inflow} /></div></div>
            <div className="bg-white rounded-2xl border card-shadow p-4"><div className="text-[11px] text-muted-foreground">صادر</div>
              <div className="font-bold text-red-700"><Money value={st.data.totals?.outflow} /></div></div>
            <div className="bg-white rounded-2xl border card-shadow p-4" data-testid="office-statement-closing">
              <div className="text-[11px] text-muted-foreground">رصيد ختامي</div>
              <div className="font-bold"><Money value={st.data.closing_balance} /></div></div>
            <div className="bg-white rounded-2xl border card-shadow p-4"><div className="text-[11px] text-muted-foreground">المحفظة (متاح/معلّق)</div>
              <div className="font-bold text-xs"><Money value={st.data.wallet?.available} /> / <Money value={st.data.wallet?.pending} /></div></div>
          </div>

          <Panel testid="office-statement-rows" title={`حركات ${st.data.office?.name || ""}`}
                 subtitle={`${st.data.count} حركة — ${st.data.currency}`}>
            {(st.data.items || []).length === 0 ? <Empty>لا حركات في هذا النطاق</Empty> : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-xs text-muted-foreground">
                    <th className="py-2 text-start">التاريخ</th><th className="text-start">نوع الحركة</th>
                    <th className="text-start">البيان</th><th className="text-start">المرجع</th>
                    <th className="text-start">وارد</th><th className="text-start">صادر</th>
                    <th className="text-start">الرصيد الجاري</th><th className="text-start">المنفّذ</th></tr></thead>
                  <tbody>
                    {st.data.items.map((r) => (
                      <tr key={r.id} className="border-t" data-testid={`office-statement-row-${r.id}`}>
                        <td className="py-2 text-xs whitespace-nowrap">{String(r.date).slice(0, 10)}</td>
                        <td className="text-xs"><Badge tone={r.direction === "in" ? "green" : "amber"}>{r.type_label}</Badge></td>
                        <td className="text-xs max-w-[16rem] truncate">{r.description || "—"}</td>
                        <td className="font-mono text-[10px]">{r.reference || "—"}</td>
                        <td className="text-emerald-700">{r.inflow ? <Money value={r.inflow} /> : "—"}</td>
                        <td className="text-red-700">{r.outflow ? <Money value={r.outflow} /> : "—"}</td>
                        <td className="font-semibold"><Money value={r.running_balance} /></td>
                        <td className="text-[11px]">{r.actor || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
          <p className="text-[11px] text-muted-foreground">{st.data.note}</p>
        </>
      )}
    </>
  );
}
