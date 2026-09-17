import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { CheckCircle2, Info, ShieldCheck } from "lucide-react";
import mobileApi, { apiError } from "@/mobile/api/client";
import api from "@/lib/api";
import {
  Screen, TopBar, Card, PrimaryButton, GhostButton, SheetSelect, FilePicker, mInput, MField,
  useAsync, StatusPill, Money, haptic,
} from "@/mobile/ui/kit";

const METHODS = [
  { value: "bank_transfer", label: "حوالة بنكية" },
  { value: "exchange", label: "صرافة" },
  { value: "cash", label: "إيداع نقدي" },
];
const CURRENCIES = [{ value: "SAR", label: "ريال سعودي (SAR)" }, { value: "USD", label: "دولار أمريكي (USD)" }];
const QUICK = [500, 1000, 2500, 5000];

/** Top-up = a REQUEST, credited only after admin approval (existing Meraaj flow).
 *  The submit is single-shot: a retry on a weak network must never create two requests. */
export default function MTopup() {
  const navigate = useNavigate();
  const [f, setF] = useState({ amount: "", currency: "SAR", method: "bank_transfer", receipt_url: "" });
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [uploading, setUploading] = useState(false);
  const mine = useAsync(() => mobileApi.topups());

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const body = new FormData();
      body.append("file", file);
      const { data } = await api.post("/wallet/topups/receipt", body,
        { headers: { "Content-Type": "multipart/form-data" } });
      setF((prev) => ({ ...prev, receipt_url: data.receipt_url }));
      haptic("success");
      toast.success("تم رفع الإيصال");
    } catch (e) { toast.error(apiError(e)); } finally { setUploading(false); }
  };

  const submit = async () => {
    if (busy || sent) return;
    setBusy(true);
    try {
      await mobileApi.createTopup({ amount: Number(f.amount), currency: f.currency,
        method: f.method, receipt_url: f.receipt_url.trim() });
      setSent(true);
      haptic("success");
      toast.success("تم إرسال طلب الشحن — سيُعتمد بعد المراجعة");
      mine.reload();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  if (sent) {
    return (
      <Screen>
        <TopBar title="تم إرسال الطلب" />
        <div className="p-6 text-center m-page-fade" data-testid="m-topup-success">
          <CheckCircle2 className="w-20 h-20 text-emerald-500 mx-auto mb-5" />
          <p className="font-head text-lg font-bold text-[#0A2540]">وصل طلب الشحن للإدارة</p>
          <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
            يُضاف الرصيد إلى محفظتك في السيرفر بعد اعتماد الطلب.
          </p>
          <Card className="mt-6 text-start" testid="m-topup-success-amount">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">المبلغ المطلوب</span>
              <Money value={f.amount} currency={f.currency} className="text-base" />
            </div>
          </Card>
          <div className="mt-6 space-y-3">
            <PrimaryButton onClick={() => navigate("/m/wallet")} data-testid="m-topup-back-wallet">
              رجوع إلى المحفظة
            </PrimaryButton>
            <GhostButton onClick={() => navigate("/m/home")}>الرئيسية</GhostButton>
          </div>
        </div>
      </Screen>
    );
  }

  return (
    <Screen>
      <TopBar title="شحن الرصيد" subtitle="يُضاف الرصيد بعد اعتماد الإدارة" back />
      <div className="p-4 space-y-3.5">
        <Card testid="m-topup-form">
          <MField label="المبلغ">
            <input className={`${mInput} text-lg font-bold`} inputMode="decimal" value={f.amount}
                   data-testid="m-topup-amount" placeholder="0.00"
                   onChange={(e) => setF({ ...f, amount: e.target.value })} />
          </MField>
          <div className="flex gap-2 mb-4 -mt-1">
            {QUICK.map((v) => (
              <button key={v} onClick={() => { haptic("light"); setF({ ...f, amount: String(v) }); }}
                      data-testid={`m-topup-quick-${v}`}
                      className="flex-1 h-10 rounded-full bg-[#0A2540]/[0.05] text-[11px] font-bold text-[#0A2540] active:scale-95 transition-transform">
                {v.toLocaleString("en-US")}
              </button>
            ))}
          </div>

          <SheetSelect label="العملة" value={f.currency} options={CURRENCIES} testid="m-topup-currency"
                       onChange={(v) => setF({ ...f, currency: v })} />
          <SheetSelect label="طريقة الإيداع" value={f.method} options={METHODS} testid="m-topup-method"
                       onChange={(v) => setF({ ...f, method: v })} />

          <FilePicker label="صورة الإيصال" testid="m-topup-receipt-file"
                      accept="image/png,image/jpeg,image/webp,application/pdf"
                      busy={uploading} done={!!f.receipt_url} doneLabel="تم رفع الإيصال"
                      hint="التقط صورة الإيصال أو اخترها من المعرض (PNG/JPEG/WEBP/PDF حتى ٥ ميجابايت)"
                      onFile={upload} />
          {f.receipt_url && (
            <p className="text-[11px] text-emerald-800 bg-emerald-50 rounded-xl p-3 mb-4"
               data-testid="m-topup-receipt-ok">تم رفع الإيصال وربطه بالطلب</p>
          )}

          <div className="flex items-start gap-2.5 bg-[#0A2540]/[0.04] rounded-2xl p-3.5 mb-4">
            <Info className="w-4 h-4 text-[#0A2540] mt-0.5 shrink-0" />
            <p className="text-[11px] text-[#0A2540] leading-relaxed">
              لا يُخصم ولا يُضاف أي رصيد من التطبيق: الإضافة تتم في السيرفر بعد اعتماد الطلب.
            </p>
          </div>

          <PrimaryButton loading={busy} disabled={busy || !f.amount || !f.receipt_url}
                         onClick={submit} data-testid="m-topup-submit">
            إرسال طلب الشحن
          </PrimaryButton>
        </Card>

        <Card testid="m-topup-history">
          <p className="font-bold text-sm text-[#0A2540] mb-3">طلباتي السابقة</p>
          {(mine.data || []).length === 0 ? (
            <p className="text-xs text-muted-foreground">لا طلبات سابقة</p>
          ) : (mine.data || []).slice(0, 6).map((t) => (
            <div key={t.id} className="flex items-center justify-between py-3 border-b border-black/5 last:border-0"
                 data-testid={`m-topup-row-${t.id}`}>
              <div>
                <p className="text-sm font-bold text-[#0A2540]"><Money value={t.amount} currency={t.currency} /></p>
                <p className="text-[11px] text-muted-foreground mt-0.5">{String(t.created_at).slice(0, 10)}</p>
              </div>
              <StatusPill status={t.status} />
            </div>
          ))}
        </Card>

        <div className="flex items-start gap-2.5 px-2">
          <ShieldCheck className="w-4 h-4 text-[#0A2540]/40 mt-0.5 shrink-0" />
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            الطلب يُرسل مرة واحدة فقط؛ إعادة المحاولة على شبكة ضعيفة لا تنشئ طلباً مكرراً.
          </p>
        </div>
      </div>
    </Screen>
  );
}
