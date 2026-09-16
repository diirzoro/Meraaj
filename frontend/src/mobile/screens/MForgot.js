import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { CheckCircle2, KeyRound, LifeBuoy } from "lucide-react";
import api, { apiError } from "@/lib/api";
import { TopBar, Screen, Card, PrimaryButton, mInput, MField, haptic } from "@/mobile/ui/kit";

/** Real end-to-end reset: request (anti-enumeration, no fake "email sent") then confirm
 *  with the token. Delivery of the token itself is an EXTERNAL DEPENDENCY (no email/SMS
 *  provider is configured), so it is handed over by Meraaj administration. */
export default function MForgot() {
  const [step, setStep] = useState("request");
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const request = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const { data } = await api.post("/auth/password-reset/request", { email: email.trim() });
      setNotice(data.message);
      setStep("confirm");
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const confirm = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const { data } = await api.post("/auth/password-reset/confirm", { token: token.trim(), password });
      haptic("success");
      toast.success(data.message);
      setStep("done");
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Screen>
      <TopBar title="استعادة كلمة المرور" subtitle={step === "request" ? "الخطوة ١" : step === "confirm" ? "الخطوة ٢" : "تم"} back />

      <div className="p-4 space-y-3.5">
        {step === "request" && (
          <>
            <Card testid="m-forgot-request">
              <div className="w-14 h-14 rounded-[20px] bg-[#0A2540]/[0.06] flex items-center justify-center mb-4">
                <LifeBuoy className="w-6 h-6 text-[#0A2540]" />
              </div>
              <p className="font-bold text-sm text-[#0A2540] mb-1">أدخل بريد حسابك</p>
              <p className="text-[11px] text-muted-foreground mb-4 leading-relaxed">
                نجهّز رمزاً آمناً صالحاً لساعة واحدة ولمرة واحدة فقط.
              </p>
              <MField label="البريد الإلكتروني">
                <input className={mInput} type="email" inputMode="email" value={email}
                       data-testid="m-forgot-email" onChange={(e) => setEmail(e.target.value)} />
              </MField>
              <PrimaryButton loading={busy} disabled={busy || !email} onClick={request}
                             data-testid="m-forgot-submit">متابعة</PrimaryButton>
            </Card>
            <p className="text-[11px] text-muted-foreground leading-relaxed px-2" data-testid="m-forgot-info">
              لا تُرسل رسائل بريد أو SMS حالياً، وتُسلّمك إدارة معراج رمز إعادة التعيين بعد
              التحقق من هويتك.
            </p>
          </>
        )}

        {step === "confirm" && (
          <Card testid="m-forgot-confirm">
            {notice && <p className="text-[11px] text-emerald-800 bg-emerald-50 rounded-2xl p-3.5 mb-4">{notice}</p>}
            <MField label="رمز إعادة التعيين">
              <input className={mInput} value={token} data-testid="m-forgot-token" dir="ltr"
                     onChange={(e) => setToken(e.target.value)} />
            </MField>
            <MField label="كلمة المرور الجديدة" hint="٨ أحرف على الأقل">
              <input className={mInput} type="password" value={password} data-testid="m-forgot-new-password"
                     onChange={(e) => setPassword(e.target.value)} />
            </MField>
            <PrimaryButton loading={busy} disabled={busy || token.length < 20 || password.length < 8}
                           onClick={confirm} data-testid="m-forgot-confirm-btn">
              <KeyRound className="w-4 h-4" /> تعيين كلمة المرور
            </PrimaryButton>
          </Card>
        )}

        {step === "done" && (
          <div className="py-10 text-center m-page-fade" data-testid="m-forgot-done">
            <CheckCircle2 className="w-20 h-20 text-emerald-500 mx-auto mb-5" />
            <p className="font-head text-lg font-bold text-[#0A2540]">تم تعيين كلمة المرور</p>
            <p className="text-xs text-muted-foreground mt-2">تم إنهاء كل الجلسات السابقة لحسابك.</p>
          </div>
        )}

        <Link to="/m/login" data-testid="m-forgot-back-login"
              className="block text-center text-sm font-bold text-[#0A2540] pt-2">
          رجوع إلى تسجيل الدخول
        </Link>
      </div>
    </Screen>
  );
}
