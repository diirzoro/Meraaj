import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { Network, Eye, EyeOff } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { apiError } from "@/lib/api";
import { PrimaryButton, mInput, MField, haptic } from "@/mobile/ui/kit";

/** Reuses the EXISTING Meraaj auth (no second user system). Tokens are stored by
 *  AuthContext; the password never leaves the request body. */
export default function MLogin() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "" });
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      // Every role — individual, office AND admin — enters the APP shell; the backend
      // decides the experience in `/v1/mobile/bootstrap`.
      await login(form.email.trim(), form.password);
      haptic("success");
      navigate("/m/home", { replace: true });
    } catch (err) {
      haptic("error");
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div dir="rtl" className="m-app min-h-[100dvh] bg-[#0A2540] flex flex-col" data-testid="m-login">
      <div className="px-7 pt-[max(3.5rem,env(safe-area-inset-top))] pb-10 text-white relative overflow-hidden">
        <div className="absolute -top-16 -start-12 w-52 h-52 rounded-full bg-[#D4AF37]/10" />
        <div className="relative">
          <div className="w-16 h-16 rounded-[22px] bg-[#D4AF37] flex items-center justify-center mb-5">
            <Network className="w-8 h-8 text-[#0A2540]" />
          </div>
          <h1 className="font-head text-3xl font-bold">أهلاً بك</h1>
          <p className="text-white/55 text-sm mt-1.5">سجّل الدخول لمتابعة خدماتك في معراج</p>
        </div>
      </div>

      <form onSubmit={submit}
            className="flex-1 bg-[#F1F4F8] rounded-t-[32px] px-6 pt-8 pb-[max(2rem,env(safe-area-inset-bottom))] m-page-fade">
        <MField label="البريد الإلكتروني">
          <input className={mInput} type="email" inputMode="email" autoComplete="email"
                 data-testid="m-login-email" value={form.email}
                 onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </MField>
        <MField label="كلمة المرور">
          <div className="relative">
            <input className={`${mInput} pe-12`} type={show ? "text" : "password"} autoComplete="current-password"
                   data-testid="m-login-password" value={form.password}
                   onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <button type="button" onClick={() => setShow(!show)} data-testid="m-login-toggle-password"
                    aria-label="إظهار كلمة المرور"
                    className="absolute inset-y-0 end-3.5 flex items-center text-[#0A2540]/45">
              {show ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
            </button>
          </div>
        </MField>

        <PrimaryButton type="submit" loading={busy} data-testid="m-login-submit"
                       disabled={!form.email || form.password.length < 4}>
          تسجيل الدخول
        </PrimaryButton>

        <Link to="/m/forgot" data-testid="m-forgot-link"
              className="block text-center text-xs font-semibold text-[#0A2540]/70 mt-5">
          نسيت كلمة المرور؟
        </Link>
        <Link to="/m/register" data-testid="m-register-link"
              className="block text-center text-sm font-bold text-[#0A2540] mt-7">
          ليس لديك حساب؟ إنشاء حساب جديد
        </Link>
      </form>
    </div>
  );
}
