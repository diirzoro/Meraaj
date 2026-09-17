import { useState } from "react";
import api, { apiError } from "@/lib/api";
import { toast } from "sonner";
import { PageHeader } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";
import { Panel, Field, inputCls, Loading, ErrorNote, Empty, useFetch, Gate, Badge } from "./ui";

export default function AccCurrencies() {
  const settings = useFetch("/accounting/currencies");
  const rates = useFetch("/accounting/fx/rates");
  const [busy, setBusy] = useState(false);
  const [rate, setRate] = useState({ from_currency: "USD", to_currency: "SAR", rate: "", date: new Date().toISOString().slice(0, 10) });

  const addRate = async () => {
    setBusy(true);
    try {
      await api.post(`/accounting/fx/rates?from_currency=${rate.from_currency}&to_currency=${rate.to_currency}` +
        `&rate=${encodeURIComponent(rate.rate)}&date=${new Date(rate.date).toISOString()}`);
      toast.success("تم إضافة سعر الصرف"); setRate({ ...rate, rate: "" }); rates.reload();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const toggle = async (cur, active) => {
    setBusy(true);
    try { await api.post(`/accounting/currencies/${cur}/active?active=${active}`); toast.success("تم التحديث"); settings.reload(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title="العملات والمصارفة" subtitle="العملات المعتمدة وأسعار الصرف بتاريخها — لا إعادة تقييم (مؤجّلة)" />
      <ErrorNote>{settings.error || rates.error}</ErrorNote>

      <Panel testid="currencies-panel" title="العملات">
        {settings.loading ? <Loading /> : !settings.data ? <Empty /> : (
          <>
            <div className="text-sm mb-3">العملة الأساسية: <b data-testid="base-currency">{settings.data.base_currency}</b></div>
            <div className="flex flex-wrap gap-2">
              {(settings.data.currencies || []).map((c) => (
                <div key={c.code || c} className="flex items-center gap-2 border rounded-lg px-3 py-2" data-testid={`currency-${c.code || c}`}>
                  <span className="font-mono text-sm">{c.code || c}</span>
                  <Badge tone={c.active === false ? "red" : "green"}>{c.active === false ? "غير مفعّلة" : "مفعّلة"}</Badge>
                  <Gate perm="accounting.currency.manage">
                    <Button size="sm" variant="outline" disabled={busy} data-testid={`currency-toggle-${c.code || c}`}
                            onClick={() => toggle(c.code || c, c.active === false)}>
                      {c.active === false ? "تفعيل" : "تعطيل"}
                    </Button>
                  </Gate>
                </div>
              ))}
            </div>
          </>
        )}
      </Panel>

      <Gate perm="accounting.currency.manage">
        <Panel testid="fx-add" title="إضافة سعر صرف">
          <div className="grid sm:grid-cols-5 gap-3 items-end">
            <Field label="من"><input className={inputCls} value={rate.from_currency} data-testid="fx-from"
              onChange={(e) => setRate({ ...rate, from_currency: e.target.value.toUpperCase() })} /></Field>
            <Field label="إلى"><input className={inputCls} value={rate.to_currency} data-testid="fx-to"
              onChange={(e) => setRate({ ...rate, to_currency: e.target.value.toUpperCase() })} /></Field>
            <Field label="السعر"><input className={inputCls} inputMode="decimal" value={rate.rate} data-testid="fx-rate"
              onChange={(e) => setRate({ ...rate, rate: e.target.value })} /></Field>
            <Field label="التاريخ"><input type="date" className={inputCls} value={rate.date} data-testid="fx-date"
              onChange={(e) => setRate({ ...rate, date: e.target.value })} /></Field>
            <Button disabled={busy || !rate.rate} onClick={addRate} className="bg-[#0A2540]" data-testid="fx-add-btn">
              <Plus className="w-4 h-4 me-1" /> إضافة
            </Button>
          </div>
        </Panel>
      </Gate>

      <Panel testid="fx-rates" title="أسعار الصرف">
        {rates.loading ? <Loading /> : (rates.data?.items || []).length === 0 ? <Empty>لا أسعار مسجّلة</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-xs text-muted-foreground">
                <th className="py-2 text-start">التاريخ</th><th className="text-start">الاتجاه</th>
                <th className="text-start">السعر</th><th className="text-start">أضافه</th></tr></thead>
              <tbody>
                {rates.data.items.map((r, i) => (
                  <tr key={i} className="border-t" data-testid={`fx-row-${i}`}>
                    <td className="py-2 text-xs">{String(r.date).slice(0, 10)}</td>
                    <td className="font-mono text-xs">{r.from_currency} → {r.to_currency}</td>
                    <td className="font-semibold">{r.rate}</td>
                    <td className="text-[11px]">{r.created_by || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <p className="text-[11px] text-muted-foreground">مؤجّل بقرار معتمد: إعادة تقييم العملات (ACC-009)، التقارير الموحّدة للعملات (ACC-010)، وترحيل العملة الأساسية تاريخياً (ACC-012).</p>
    </>
  );
}
