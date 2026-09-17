import { useState } from "react";
import api, { apiError } from "@/lib/api";
import { toast } from "sonner";
import { PageHeader } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Panel, inputCls, Loading, ErrorNote, Empty, useFetch, Gate, Badge } from "./ui";

/** ربط الحسابات — the semantic bridge between business events and accounts.
 *  Account numbers are NEVER hardcoded anywhere: every flow resolves through a link. */
export default function AccLinks() {
  const links = useFetch("/accounting/integration/account-links");
  const accounts = useFetch("/accounting/accounts?include_inactive=false");
  const events = useFetch("/accounting/integration/events");
  const [busy, setBusy] = useState(false);

  const leaves = (accounts.data?.items || []).filter((a) => !a.is_group);
  const items = links.data?.links || links.data?.items || [];

  const setLink = async (key, code) => {
    setBusy(true);
    try {
      if (!code) await api.delete(`/accounting/integration/account-links/${encodeURIComponent(key)}`);
      else await api.post(`/accounting/integration/account-links/${encodeURIComponent(key)}?account_code=${encodeURIComponent(code)}`);
      toast.success("تم التحديث"); links.reload();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title="ربط الحسابات بالعمليات" subtitle="كل حدث تجاري يصل إلى حسابه عبر رابط دلالي — لا أرقام حسابات مكتوبة في الكود" />
      <ErrorNote>{links.error || accounts.error}</ErrorNote>

      <Panel testid="links-panel" title="الروابط الدلالية">
        {links.loading ? <Loading /> : items.length === 0 ? <Empty>لا روابط</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-xs text-muted-foreground">
                <th className="py-2 text-start">المفتاح</th><th className="text-start">الوصف</th>
                <th className="text-start">الحساب</th><th className="text-start">الحالة</th></tr></thead>
              <tbody>
                {items.map((l) => (
                  <tr key={l.key} className="border-t" data-testid={`link-row-${l.key}`}>
                    <td className="py-2 font-mono text-[11px]">{l.key}</td>
                    <td className="text-xs">{l.label_ar || l.description || "—"}</td>
                    <td>
                      <Gate perm="accounting.links.manage" fallback={<span className="font-mono text-xs">{l.account_code || "—"}</span>}>
                        <select className={`${inputCls} h-9 max-w-[18rem]`} disabled={busy} value={l.account_code || ""}
                                data-testid={`link-select-${l.key}`} onChange={(e) => setLink(l.key, e.target.value)}>
                          <option value="">— غير مربوط —</option>
                          {leaves.map((a) => <option key={a.code} value={a.code}>{a.code} — {a.name_ar || a.name}</option>)}
                        </select>
                      </Gate>
                    </td>
                    <td><Badge tone={l.account_code ? "green" : "amber"}>{l.account_code ? "مربوط" : "ناقص"}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel testid="links-events" title="خريطة الأحداث المالية" subtitle="الأحداث التجارية وأثرها المحاسبي">
        {events.loading ? <Loading /> : (events.data?.events || []).length === 0 ? <Empty /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-xs text-muted-foreground">
                <th className="py-2 text-start">الحدث</th><th className="text-start">الاسم</th>
                <th className="text-start">قيد محاسبي؟</th><th className="text-start">ملاحظة</th></tr></thead>
              <tbody>
                {events.data.events.map((e) => (
                  <tr key={e.key} className="border-t" data-testid={`event-row-${e.key}`}>
                    <td className="py-2 font-mono text-[11px]">{e.key}</td>
                    <td className="text-xs">{e.label_ar}</td>
                    <td><Badge tone={e.posts_journal ? "green" : "slate"}>{e.posts_journal ? "نعم" : "لا"}</Badge></td>
                    <td className="text-[11px] max-w-[24rem]">{e.note || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
