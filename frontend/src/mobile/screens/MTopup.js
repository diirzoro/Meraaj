import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Info } from "lucide-react";
import mobileApi, { apiError } from "@/mobile/api/client";
import { Screen, TopBar, Card, PrimaryButton, mInput, MField, useAsync, StatusPill, Money } from "@/mobile/ui/kit";

const METHODS = [["bank_transfer", "حوالة بنكية"], ["exchange", "صرافة"], ["cash", "إيداع نقدي"]];

/** Top-up = a REQUEST, credited only after admin approval (existing Meraaj flow).
 *  The submit is single-shot: a retry on a weak network must never create two requests. */
export default function MTopup() {
  const navigate = useNavigate();
  const [f, setF] = useState({ amount: "", currency: "SAR", method: "bank_transfer", receipt_url: "" });
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const mine = useAsync(() => mobileApi.topups());

  const submit = async () => {
    if (busy || sent) return;
    setBusy(true);
    try {
      await mobileApi.createTopup({ amount: Number(f.amount), currency: f.currency,
        method: f.method, receipt_url: f.receipt_url.trim() });
      setSent(true);
      toast.success("تم إرسال طلب الشحن — سيُعتمد بعد المراجعة");
      mine.reload();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Screen>
      <TopBar title="شحن الرصيد" subtitle="يُضاف الرصيد بعد اعتماد الإدارة" back />
      <div className="p-4 space-y-3">
        <Card testid="m-topup-form">
          <MField label="المبلغ">
            <input className={mInput} inputMode="decimal" value={f.amount} data-testid="m-topup-amount"
                   onChange={(e) => setF({ ...f, amount: e.target.value })} />
          </MField>
          <MField label="العملة">
            <select className={mInput} value={f.currency} data-testid="m-topup-currency"
                    onChange={(e) => setF({ ...f, currency: e.target.value })}>
              <option value="SAR">SAR</option><option value="USD">USD</option>
            </select>
          </MField>
          <MField label="طريقة الإيداع">
            <select className={mInput} value={f.method} data-testid="m-topup-method"
                    onChange={(e) => setF({ ...f, method: e.target.value })}>
              {METHODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </MField>
          <MField label="رابط الإيصال" hint="ارفع صورة الإيصال في أي خدمة مشاركة وألصق الرابط">
            <input className={mInput} value={f.receipt_url} data-testid="m-topup-receipt"
                   onChange={(e) => setF({ ...f, receipt_url: e.target.value })} />
          </MField>

          <div className="flex items-start gap-2 bg-[#0A2540]/5 rounded-xl p-3 mb-3">
            <Info className="w-4 h-4 text-[#0A2540] mt-0.5 shrink-0" />
            <p className="text-[11px] text-[#0A2540] leading-relaxed">
              لا يُخصم ولا يُضاف أي رصيد من التطبيق: الإضافة تتم في السيرفر بعد اعتماد الطلب.
            </p>
          </div>

          <PrimaryButton loading={busy} disabled={busy || sent || !f.amount || !f.receipt_url}
                         onClick={submit} data-testid="m-topup-submit">
            {sent ? "تم إرسال الطلب" : "إرسال طلب الشحن"}
          </PrimaryButton>
          {sent && (
            <button onClick={() => navigate("/m/wallet")} data-testid="m-topup-back-wallet"
                    className="w-full h-12 text-sm font-semibold text-[#0A2540] mt-2">رجوع إلى المحفظة</button>
          )}
        </Card>

        <Card testid="m-topup-history">
          <p className="font-semibold text-sm text-[#0A2540] mb-3">طلباتي السابقة</p>
          {(mine.data || []).length === 0 ? (
            <p className="text-xs text-muted-foreground">لا طلبات سابقة</p>
          ) : (mine.data || []).slice(0, 6).map((t) => (
            <div key={t.id} className="flex items-center justify-between py-2 border-b last:border-0"
                 data-testid={`m-topup-row-${t.id}`}>
              <div className="text-xs">
                <p className="font-semibold text-[#0A2540]"><Money value={t.amount} currency={t.currency} /></p>
                <p className="text-[11px] text-muted-foreground">{String(t.created_at).slice(0, 10)}</p>
              </div>
              <StatusPill status={t.status} />
            </div>
          ))}
        </Card>
      </div>
    </Screen>
  );
}
