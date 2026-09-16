import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { Network, Eye, EyeOff } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { apiError } from "@/lib/api";
import { PrimaryButton, mInput, MField } from "@/mobile/ui/kit";

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
      const u = await login(form.email.trim(), form.password);
      if (u?.role === "super_admin") {
        toast.info("حسابات الإدارة تُستخدم من لوحة الويب");
        navigate("/admin", { replace: true });
        return;
      }
      navigate("/m/home", { replace: true });
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div dir="rtl" className="min-h-[100dvh] bg-[#0A2540] flex flex-col" data-testid="m-login">
      <div className="px-7 pt-[max(3rem,env(safe-area-inset-top))] pb-8 text-white">
        <div className="w-14 h-14 rounded-2xl bg-[#D4AF37] flex items-center justify-center mb-4">
          <Network className="w-7 h-7 text-[#0A2540]" />
        </div>
        <h1 className="font-head text-2xl font-bold">أهلاً بك</h1>
        <p className="text-white/55 text-sm mt-1">سجّل الدخول لمتابعة خدماتك في معراج</p>
      </div>

      <form onSubmit={submit}
            className="flex-1 bg-[#F4F6F8] rounded-t-3xl px-6 pt-7 pb-[max(2rem,env(safe-area-inset-bottom))]">
        <MField label="البريد الإلكتروني">
          <input className={mInput} type="email" inputMode="email" autoComplete="email"
                 data-testid="m-login-email" value={form.email}
                 onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </MField>
        <MField label="كلمة المرور">
          <div className="relative">
            <input className={mInput} type={show ? "text" : "password"} autoComplete="current-password"
                   data-testid="m-login-password" value={form.password}
                   onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <button type="button" onClick={() => setShow(!show)} data-testid="m-login-toggle-password"
                    className="absolute inset-y-0 end-3 flex items-center text-[#0A2540]/50">
              {show ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
            </button>
          </div>
        </MField>

        <PrimaryButton type="submit" loading={busy} data-testid="m-login-submit"
                       disabled={!form.email || form.password.length < 4}>
          تسجيل الدخول
        </PrimaryButton>

        <Link to="/m/forgot" data-testid="m-forgot-link"
              className="block text-center text-xs text-[#0A2540]/70 mt-4 underline">
          نسيت كلمة المرور؟
        </Link>
        <Link to="/m/register" data-testid="m-register-link"
              className="block text-center text-sm font-semibold text-[#0A2540] mt-6">
          ليس لديك حساب؟ إنشاء حساب جديد
        </Link>
      </form>
    </div>
  );
}
