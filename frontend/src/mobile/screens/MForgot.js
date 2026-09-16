import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { LifeBuoy, KeyRound } from "lucide-react";
import api, { apiError } from "@/lib/api";
import { TopBar, Screen, Card, PrimaryButton, mInput, MField } from "@/mobile/ui/kit";

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
      toast.success(data.message);
      setStep("done");
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Screen>
      <TopBar title="استعادة كلمة المرور" back />
      <div className="p-4 space-y-3">
        <Card testid="m-forgot-info">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#0A2540]/5 flex items-center justify-center shrink-0">
              <LifeBuoy className="w-5 h-5 text-[#0A2540]" />
            </div>
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              لا تُرسل رسائل بريد أو SMS حالياً (لا يوجد مزوّد إرسال مُهيّأ). يُجهّز النظام
              رابطاً آمناً صالحاً لساعة واحدة ولمرة واحدة، وتُسلّمك إدارة معراج رمز إعادة
              التعيين بعد التحقق من هويتك.
            </p>
          </div>
        </Card>

        {step === "request" && (
          <Card testid="m-forgot-request">
            <MField label="البريد الإلكتروني للحساب">
              <input className={mInput} type="email" inputMode="email" value={email}
                     data-testid="m-forgot-email" onChange={(e) => setEmail(e.target.value)} />
            </MField>
            <PrimaryButton loading={busy} disabled={busy || !email} onClick={request}
                           data-testid="m-forgot-submit">تجهيز طلب إعادة التعيين</PrimaryButton>
          </Card>
        )}

        {step === "confirm" && (
          <Card testid="m-forgot-confirm">
            {notice && <p className="text-[11px] text-emerald-800 bg-emerald-50 rounded-xl p-3 mb-3">{notice}</p>}
            <MField label="رمز إعادة التعيين">
              <input className={mInput} value={token} data-testid="m-forgot-token"
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
          <Card testid="m-forgot-done">
            <p className="text-sm font-bold text-[#0A2540]">تم تعيين كلمة المرور</p>
            <p className="text-[11px] text-muted-foreground mt-1">تم إنهاء كل الجلسات السابقة لحسابك.</p>
          </Card>
        )}

        <Link to="/m/login" data-testid="m-forgot-back-login"
              className="block text-center text-sm font-semibold text-[#0A2540]">
          رجوع إلى تسجيل الدخول
        </Link>
      </div>
    </Screen>
  );
}
