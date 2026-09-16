import { useState } from "react";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import accApi from "@/mobile/api/accounting";
import { apiError } from "@/lib/api";
import { useShell } from "@/mobile/MobileShell";
import {
  Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, Sheet, SheetSelect, mInput,
  MField, PrimaryButton, DangerButton, GhostButton, StatusPill, Segmented, useAsync, haptic,
} from "@/mobile/ui/kit";

const KINDS = [["receipt", "سند قبض", "voucher_receipt"], ["payment", "سند صرف", "voucher_payment"]];
const CURRENCIES = [{ value: "SAR", label: "ريال سعودي (SAR)" }, { value: "USD", label: "دولار أمريكي (USD)" }];

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
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [idem, setIdem] = useState(() => crypto.randomUUID());
  const [f, setF] = useState({ cash_account: "", counter_account: "", amount: "", currency: "SAR", party: "", description: "" });

  const options = (accounts.data?.items || []).filter((a) => !a.is_group)
    .map((a) => ({ value: a.code, label: `${a.code} — ${a.name_ar || a.name}` }));
  const canCreate = caps[KINDS.find(([k]) => k === kind)[2]];

  const submit = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await accApi.createVoucher({ kind, ...f }, idem);
      haptic("success");
      toast.success(r.requires_approval ? "بانتظار اعتماد شخص ثانٍ" : `تم الترحيل — ${r.entry_no}`);
      setSheet(false); setIdem(crypto.randomUUID());
      setF({ cash_account: "", counter_account: "", amount: "", currency: "SAR", party: "", description: "" });
      list.reload();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const act = async (fn, msg) => {
    if (busy) return;
    setBusy(true);
    try { await fn(); haptic("success"); toast.success(msg); setDetail(null); setCancelling(false); setReason(""); list.reload(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Screen refresh={list.reload}>
      <TopBar title="السندات" subtitle="تُرحَّل عبر النواة المحاسبية فقط" back
              right={canCreate && (
                <button onClick={() => { haptic("light"); setSheet(true); }} data-testid="m-voucher-new"
                        className="h-10 px-3.5 rounded-full bg-[#D4AF37] text-[#0A2540] text-[11px] font-bold flex items-center gap-1 active:scale-95 transition-transform">
                  <Plus className="w-3.5 h-3.5" /> سند جديد
                </button>)} />

      <div className="p-4 space-y-3.5">
        <Segmented items={KINDS.map(([k, l]) => [k, l])} value={kind} onChange={setKind}
                   testid="m-voucher-tabs" testidPrefix="m-voucher-tab-" />

        {list.data?.dual_control?.[kind] && (
          <p className="text-[11px] bg-blue-50 border border-blue-200 text-blue-900 rounded-2xl p-3.5 leading-relaxed"
             data-testid="m-voucher-dual-note">
            رقابة مزدوجة مُفعّلة: السند لا يُرحَّل قبل اعتماد شخص ثانٍ.
          </p>
        )}

        {list.loading ? <Skeleton rows={3} />
          : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
          : (list.data?.items || []).length === 0 ? <EmptyState title="لا سندات" />
          : (
            <div className="space-y-3.5 m-stagger" data-testid="m-voucher-list">
              {list.data.items.map((v) => (
                <Card key={v.id} testid={`m-voucher-${v.id}`} onClick={() => setDetail(v)}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-bold text-[#0A2540] truncate">{v.party || v.kind_label}</p>
                      <p className="text-[11px] text-muted-foreground font-mono mt-1.5" dir="ltr">
                        {v.cash_account} ↔ {v.counter_account}
                      </p>
                      <p className="text-[10.5px] text-muted-foreground mt-1">{String(v.date).slice(0, 10)}</p>
                    </div>
                    <div className="text-end shrink-0 space-y-1.5">
                      <div className="text-sm"><Money value={v.amount} currency={v.currency} /></div>
                      <StatusPill status={v.status} />
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
      </div>

      {/* create */}
      <Sheet open={sheet} onClose={() => setSheet(false)} title="سند جديد" testid="m-voucher-sheet">
        <SheetSelect label="الصندوق/البنك" value={f.cash_account} options={options} testid="m-voucher-cash"
                     onChange={(v) => setF({ ...f, cash_account: v })} />
        <SheetSelect label="الحساب المقابل" value={f.counter_account} options={options} testid="m-voucher-counter"
                     onChange={(v) => setF({ ...f, counter_account: v })} />
        <MField label="المبلغ">
          <input className={`${mInput} text-lg font-bold`} inputMode="decimal" value={f.amount}
                 data-testid="m-voucher-amount" placeholder="0.00"
                 onChange={(e) => setF({ ...f, amount: e.target.value })} />
        </MField>
        <SheetSelect label="العملة" value={f.currency} options={CURRENCIES} testid="m-voucher-currency"
                     onChange={(v) => setF({ ...f, currency: v })} />
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

      {/* detail + actions */}
      <Sheet open={!!detail} onClose={() => { setDetail(null); setCancelling(false); }}
             title={detail?.kind_label} testid="m-voucher-detail">
        {detail && (
          <div className="space-y-4">
            <div className="rounded-2xl bg-[#F1F4F8] p-4 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">المبلغ</span>
                <Money value={detail.amount} currency={detail.currency} className="text-base" />
              </div>
              {[["القيد", detail.entry_no], ["أنشأه", detail.created_by], ["اعتمده", detail.approved_by],
                ["رحّله", detail.posted_by], ["قيد العكس", detail.reversal_entry_no]].map(([k, v]) => (
                <div key={k} className="flex items-center justify-between text-[11px]">
                  <span className="text-muted-foreground">{k}</span>
                  <span className="font-bold text-[#0A2540] font-mono" dir="ltr">{v || "—"}</span>
                </div>
              ))}
            </div>

            {cancelling ? (
              <div className="space-y-3">
                <MField label="سبب الإلغاء" hint="٣ أحرف على الأقل — يُسجَّل في القيد العكسي">
                  <input className={mInput} value={reason} data-testid="m-voucher-cancel-reason"
                         onChange={(e) => setReason(e.target.value)} />
                </MField>
                <DangerButton loading={busy} disabled={busy || reason.trim().length < 3}
                              data-testid="m-voucher-cancel-confirm"
                              onClick={() => act(() => accApi.cancelVoucher(detail.id, reason.trim()), "تم الإلغاء بقيد عكسي")}>
                  تأكيد الإلغاء بقيد عكسي
                </DangerButton>
                <GhostButton onClick={() => { setCancelling(false); setReason(""); }}>تراجع</GhostButton>
              </div>
            ) : (
              <>
                {detail.status === "pending_approval" && caps.voucher_approve && (
                  <PrimaryButton loading={busy} data-testid="m-voucher-approve"
                                 onClick={() => act(() => accApi.approveVoucher(detail.id), "تم الاعتماد والترحيل")}>
                    اعتماد وترحيل
                  </PrimaryButton>
                )}
                {detail.status !== "cancelled" && caps.voucher_cancel && (
                  <DangerButton data-testid="m-voucher-cancel" onClick={() => setCancelling(true)}>
                    إلغاء بقيد عكسي
                  </DangerButton>
                )}
              </>
            )}
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              لا تعديل ولا حذف للسند المُرحَّل — التصحيح بقيد عكسي فقط.
            </p>
          </div>
        )}
      </Sheet>
    </Screen>
  );
}
