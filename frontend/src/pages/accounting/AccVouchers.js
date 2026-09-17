import { useState } from "react";
import api, { apiError } from "@/lib/api";
import { toast } from "sonner";
import { PageHeader } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "@/context/AuthContext";
import { Printer, Plus, Check, Ban } from "lucide-react";
import { Panel, Field, inputCls, Loading, ErrorNote, ScopeNote, Empty, useFetch, Gate, Badge, Money, STATUS_AR, statusTone } from "./ui";

const TABS = [
  { kind: "receipt", label: "سند قبض", perm: "accounting.vouchers.receipt" },
  { kind: "payment", label: "سند صرف", perm: "accounting.vouchers.payment" },
];

export default function AccVouchers() {
  const { can } = useAuth();
  const [tab, setTab] = useState("receipt");
  const list = useFetch(`/accounting/vouchers?kind=${tab}`, [tab]);
  const accounts = useFetch("/accounting/accounts?include_inactive=false");
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ cash_account: "", counter_account: "", amount: "", currency: "SAR", party: "", description: "" });

  const leaves = (accounts.data?.items || []).filter((a) => !a.is_group);
  const activeTab = TABS.find((t) => t.kind === tab);
  const dual = list.data?.dual_control?.[tab];

  const submit = async () => {
    setBusy(true);
    try {
      const r = await api.post("/accounting/vouchers", { kind: tab, ...form });
      toast.success(r.data.requires_approval ? "السند بانتظار اعتماد شخص ثانٍ" : `تم الترحيل — قيد ${r.data.entry_no}`);
      setOpen(false);
      setForm({ cash_account: "", counter_account: "", amount: "", currency: "SAR", party: "", description: "" });
      list.reload();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const approve = async (id) => {
    setBusy(true);
    try { const r = await api.post(`/accounting/vouchers/${id}/approve`); toast.success(`تم الاعتماد والترحيل — قيد ${r.data.entry_no}`); list.reload(); setDetail(null); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const cancel = async (id) => {
    const reason = window.prompt("سبب الإلغاء (يُسجَّل ويُنشئ قيد عكس):");
    if (!reason || reason.trim().length < 3) return;
    setBusy(true);
    try { await api.post(`/accounting/vouchers/${id}/cancel?reason=${encodeURIComponent(reason)}`); toast.success("تم الإلغاء بقيد عكسي"); list.reload(); setDetail(null); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title="السندات" subtitle="سند قبض وسند صرف محاسبيان — كل سند يُرحَّل عبر النواة المحاسبية فقط"
        action={can(activeTab.perm) && (
          <Button onClick={() => setOpen(true)} data-testid="voucher-new-btn" className="bg-[#0A2540]">
            <Plus className="w-4 h-4 me-1" /> {activeTab.label} جديد
          </Button>)} />

      <div className="flex gap-2 mb-5" data-testid="voucher-tabs">
        {TABS.map((t) => (
          <button key={t.kind} onClick={() => setTab(t.kind)} data-testid={`voucher-tab-${t.kind}`}
                  className={`h-10 px-5 rounded-lg text-sm font-semibold transition-colors ${tab === t.kind ? "bg-[#0A2540] text-white" : "bg-white border text-[#0A2540] hover:bg-slate-50"}`}>
            {t.label}
          </button>
        ))}
      </div>

      <ErrorNote>{list.error}</ErrorNote>
      {dual && (
        <div className="rounded-lg bg-blue-50 border border-blue-200 text-blue-900 text-xs p-3 mb-4" data-testid="voucher-dual-note">
          هذه العملية تحت الرقابة المزدوجة (Maker–Checker): السند يُنشأ بانتظار اعتماد شخص ثانٍ ولا يُرحَّل قبل الاعتماد.
        </div>
      )}

      <Panel testid="voucher-list">
        {list.loading ? <Loading /> : (list.data?.items || []).length === 0 ? <Empty>لا توجد سندات</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-xs text-muted-foreground text-start">
                <th className="py-2 text-start">التاريخ</th><th className="text-start">الطرف</th>
                <th className="text-start">من/إلى</th><th className="text-start">المبلغ</th>
                <th className="text-start">الحالة</th><th className="text-start">القيد</th><th /></tr></thead>
              <tbody>
                {list.data.items.map((v) => (
                  <tr key={v.id} className="border-t" data-testid={`voucher-row-${v.id}`}>
                    <td className="py-2 whitespace-nowrap text-xs">{String(v.date).slice(0, 10)}</td>
                    <td className="text-xs">{v.party || "—"}</td>
                    <td className="font-mono text-[11px]">{v.cash_account} ↔ {v.counter_account}</td>
                    <td className="font-semibold"><Money value={v.amount} /> {v.currency}</td>
                    <td><Badge tone={statusTone(v.status)}>{STATUS_AR[v.status] || v.status}</Badge></td>
                    <td className="font-mono text-[11px]">{v.entry_no || "—"}</td>
                    <td className="text-end">
                      <Button size="sm" variant="outline" data-testid={`voucher-open-${v.id}`} onClick={() => setDetail(v)}>تفاصيل</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="voucher-create-dialog">
          <DialogHeader><DialogTitle>{activeTab.label} جديد</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Field label={tab === "receipt" ? "الصندوق/البنك المستلم (مدين)" : "الصندوق/البنك الدافع (دائن)"}>
              <select className={inputCls} value={form.cash_account} data-testid="voucher-cash-account"
                      onChange={(e) => setForm({ ...form, cash_account: e.target.value })}>
                <option value="">— اختر —</option>
                {leaves.map((a) => <option key={a.code} value={a.code}>{a.code} — {a.name_ar || a.name}</option>)}
              </select>
            </Field>
            <Field label="الحساب المقابل">
              <select className={inputCls} value={form.counter_account} data-testid="voucher-counter-account"
                      onChange={(e) => setForm({ ...form, counter_account: e.target.value })}>
                <option value="">— اختر —</option>
                {leaves.map((a) => <option key={a.code} value={a.code}>{a.code} — {a.name_ar || a.name}</option>)}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="المبلغ">
                <input className={inputCls} value={form.amount} data-testid="voucher-amount" inputMode="decimal"
                       onChange={(e) => setForm({ ...form, amount: e.target.value })} />
              </Field>
              <Field label="العملة">
                <select className={inputCls} value={form.currency} data-testid="voucher-currency"
                        onChange={(e) => setForm({ ...form, currency: e.target.value })}>
                  <option value="SAR">SAR</option><option value="USD">USD</option>
                </select>
              </Field>
            </div>
            <Field label="الطرف (اسم المكتب/الشخص)">
              <input className={inputCls} value={form.party} data-testid="voucher-party"
                     onChange={(e) => setForm({ ...form, party: e.target.value })} />
            </Field>
            <Field label="البيان">
              <input className={inputCls} value={form.description} data-testid="voucher-description"
                     onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </Field>
            <Button disabled={busy || !form.cash_account || !form.counter_account || !form.amount}
                    onClick={submit} data-testid="voucher-submit" className="w-full bg-[#0A2540]">
              {dual ? "إرسال للاعتماد" : "ترحيل السند"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!detail} onOpenChange={(v) => !v && setDetail(null)}>
        <DialogContent data-testid="voucher-detail-dialog">
          <DialogHeader><DialogTitle>{detail?.kind_label} — {detail?.entry_no || STATUS_AR[detail?.status]}</DialogTitle></DialogHeader>
          {detail && (
            <div className="space-y-3 text-sm print:text-black" id="voucher-print">
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>التاريخ: <b>{String(detail.date).slice(0, 10)}</b></div>
                <div>المبلغ: <b><Money value={detail.amount} /> {detail.currency}</b></div>
                <div>مدين: <b className="font-mono">{detail.kind === "receipt" ? detail.cash_account : detail.counter_account}</b></div>
                <div>دائن: <b className="font-mono">{detail.kind === "receipt" ? detail.counter_account : detail.cash_account}</b></div>
                <div>الطرف: <b>{detail.party || "—"}</b></div>
                <div>الحالة: <b>{STATUS_AR[detail.status] || detail.status}</b></div>
                <div>أنشأه: <b>{detail.created_by || "—"}</b></div>
                <div>اعتمده: <b>{detail.approved_by || "—"}</b></div>
                <div>رحّله: <b>{detail.posted_by || "—"}</b></div>
                <div>ألغاه: <b>{detail.cancelled_by || "—"}</b></div>
                <div>قيد العكس: <b className="font-mono">{detail.reversal_entry_no || "—"}</b></div>
              </div>
              <p className="text-xs text-muted-foreground">{detail.description}</p>
              <div className="flex flex-wrap gap-2 pt-2 border-t">
                <Button size="sm" variant="outline" onClick={() => window.print()} data-testid="voucher-print">
                  <Printer className="w-4 h-4 me-1" /> طباعة
                </Button>
                {detail.status === "pending_approval" && (
                  <Gate perm="accounting.vouchers.approve">
                    <Button size="sm" disabled={busy} className="bg-emerald-600" data-testid="voucher-approve"
                            onClick={() => approve(detail.id)}><Check className="w-4 h-4 me-1" /> اعتماد وترحيل</Button>
                  </Gate>
                )}
                {detail.status !== "cancelled" && (
                  <Gate perm="accounting.vouchers.cancel">
                    <Button size="sm" variant="destructive" disabled={busy} data-testid="voucher-cancel"
                            onClick={() => cancel(detail.id)}><Ban className="w-4 h-4 me-1" /> إلغاء بقيد عكسي</Button>
                  </Gate>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground">لا يُعدَّل السند المُرحَّل ولا يُحذف — التصحيح يتم بقيد عكسي فقط.</p>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
