import { useState } from "react";
import { toast } from "sonner";
import accApi from "@/mobile/api/accounting";
import { apiError } from "@/lib/api";
import { useShell } from "@/mobile/MobileShell";
import { Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, Sheet, mInput, MField, PrimaryButton, StatusPill, useAsync } from "@/mobile/ui/kit";

const KINDS = [["receipt", "سند قبض", "voucher_receipt"], ["payment", "سند صرف", "voucher_payment"]];

/** Mobile vouchers: create / approve / cancel. The submit carries an Idempotency-Key and
 *  is locked after the first tap, so a weak network cannot post the same voucher twice. */
export default function MAccVouchers() {
  const { shell } = useShell();
  const caps = shell?.accounting?.capabilities || {};
  const [kind, setKind] = useState("receipt");
  const list = useAsync(() => accApi.vouchers(kind), [kind]);
  const accounts = useAsync(() => accApi.accounts());
  const [sheet, setSheet] = useState(false);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [idem, setIdem] = useState(() => crypto.randomUUID());
  const [f, setF] = useState({ cash_account: "", counter_account: "", amount: "", currency: "SAR", party: "", description: "" });

  const leaves = (accounts.data?.items || []).filter((a) => !a.is_group);
  const canCreate = caps[KINDS.find(([k]) => k === kind)[2]];

  const submit = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await accApi.createVoucher({ kind, ...f }, idem);
      toast.success(r.requires_approval ? "بانتظار اعتماد شخص ثانٍ" : `تم الترحيل — ${r.entry_no}`);
      setSheet(false); setIdem(crypto.randomUUID());
      setF({ cash_account: "", counter_account: "", amount: "", currency: "SAR", party: "", description: "" });
      list.reload();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const act = async (fn, msg) => {
    if (busy) return;
    setBusy(true);
    try { await fn(); toast.success(msg); setDetail(null); list.reload(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Screen>
      <TopBar title="السندات" subtitle="تُرحَّل عبر النواة المحاسبية فقط" back
              right={canCreate && (
                <button onClick={() => setSheet(true)} data-testid="m-voucher-new"
                        className="h-9 px-3 rounded-full bg-[#D4AF37] text-[#0A2540] text-[11px] font-bold">
                  سند جديد
                </button>)} />

      <div className="p-4 flex gap-2" data-testid="m-voucher-tabs">
        {KINDS.map(([k, label]) => (
          <button key={k} onClick={() => setKind(k)} data-testid={`m-voucher-tab-${k}`}
                  className={`h-10 px-4 rounded-full text-xs font-bold ${kind === k ? "bg-[#0A2540] text-white" : "bg-white border text-[#0A2540]"}`}>
            {label}
          </button>
        ))}
      </div>

      {list.data?.dual_control?.[kind] && (
        <p className="mx-4 mb-3 text-[11px] bg-blue-50 border border-blue-200 text-blue-900 rounded-xl p-3"
           data-testid="m-voucher-dual-note">
          رقابة مزدوجة مُفعّلة: السند لا يُرحَّل قبل اعتماد شخص ثانٍ.
        </p>
      )}

      {list.loading ? <Skeleton rows={3} />
        : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
        : (list.data?.items || []).length === 0 ? <EmptyState title="لا سندات" />
        : (
          <div className="px-4 space-y-3" data-testid="m-voucher-list">
            {list.data.items.map((v) => (
              <Card key={v.id} testid={`m-voucher-${v.id}`} onClick={() => setDetail(v)}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-[#0A2540] truncate">{v.party || v.kind_label}</p>
                    <p className="text-[11px] text-muted-foreground font-mono mt-1">
                      {v.cash_account} ↔ {v.counter_account}
                    </p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">{String(v.date).slice(0, 10)}</p>
                  </div>
                  <div className="text-end shrink-0 space-y-1">
                    <div className="text-sm"><Money value={v.amount} currency={v.currency} /></div>
                    <StatusPill status={v.status} />
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

      <Sheet open={sheet} onClose={() => setSheet(false)} title="سند جديد" testid="m-voucher-sheet">
        <MField label="الصندوق/البنك">
          <select className={mInput} value={f.cash_account} data-testid="m-voucher-cash"
                  onChange={(e) => setF({ ...f, cash_account: e.target.value })}>
            <option value="">— اختر —</option>
            {leaves.map((a) => <option key={a.code} value={a.code}>{a.code} — {a.name_ar || a.name}</option>)}
          </select>
        </MField>
        <MField label="الحساب المقابل">
          <select className={mInput} value={f.counter_account} data-testid="m-voucher-counter"
                  onChange={(e) => setF({ ...f, counter_account: e.target.value })}>
            <option value="">— اختر —</option>
            {leaves.map((a) => <option key={a.code} value={a.code}>{a.code} — {a.name_ar || a.name}</option>)}
          </select>
        </MField>
        <div className="grid grid-cols-2 gap-3">
          <MField label="المبلغ">
            <input className={mInput} inputMode="decimal" value={f.amount} data-testid="m-voucher-amount"
                   onChange={(e) => setF({ ...f, amount: e.target.value })} />
          </MField>
          <MField label="العملة">
            <select className={mInput} value={f.currency} data-testid="m-voucher-currency"
                    onChange={(e) => setF({ ...f, currency: e.target.value })}>
              <option value="SAR">SAR</option><option value="USD">USD</option>
            </select>
          </MField>
        </div>
        <MField label="الطرف">
          <input className={mInput} value={f.party} data-testid="m-voucher-party"
                 onChange={(e) => setF({ ...f, party: e.target.value })} />
        </MField>
        <MField label="البيان">
          <input className={mInput} value={f.description} data-testid="m-voucher-desc"
                 onChange={(e) => setF({ ...f, description: e.target.value })} />
        </MField>
        <PrimaryButton loading={busy} disabled={busy || !f.cash_account || !f.counter_account || !f.amount}
                       onClick={submit} data-testid="m-voucher-submit">حفظ السند</PrimaryButton>
      </Sheet>

      <Sheet open={!!detail} onClose={() => setDetail(null)} title={detail?.kind_label} testid="m-voucher-detail">
        {detail && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div>المبلغ: <b><Money value={detail.amount} currency={detail.currency} /></b></div>
              <div>القيد: <b className="font-mono">{detail.entry_no || "—"}</b></div>
              <div>أنشأه: <b>{detail.created_by || "—"}</b></div>
              <div>اعتمده: <b>{detail.approved_by || "—"}</b></div>
              <div>رحّله: <b>{detail.posted_by || "—"}</b></div>
              <div>قيد العكس: <b className="font-mono">{detail.reversal_entry_no || "—"}</b></div>
            </div>
            {detail.status === "pending_approval" && caps.voucher_approve && (
              <PrimaryButton loading={busy} data-testid="m-voucher-approve"
                             onClick={() => act(() => accApi.approveVoucher(detail.id), "تم الاعتماد والترحيل")}>
                اعتماد وترحيل
              </PrimaryButton>
            )}
            {detail.status !== "cancelled" && caps.voucher_cancel && (
              <button data-testid="m-voucher-cancel" disabled={busy}
                      onClick={() => {
                        const reason = window.prompt("سبب الإلغاء:");
                        if (reason && reason.trim().length >= 3) act(() => accApi.cancelVoucher(detail.id, reason.trim()), "تم الإلغاء بقيد عكسي");
                      }}
                      className="w-full h-12 rounded-xl border border-red-200 text-red-600 text-sm font-semibold">
                إلغاء بقيد عكسي
              </button>
            )}
            <p className="text-[11px] text-muted-foreground">لا تعديل ولا حذف للسند المُرحَّل — التصحيح بقيد عكسي فقط.</p>
          </div>
        )}
      </Sheet>
    </Screen>
  );
}
