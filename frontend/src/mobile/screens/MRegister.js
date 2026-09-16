import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { Building2, User } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { apiError } from "@/lib/api";
import {
  TopBar, Screen, Card, PrimaryButton, GhostButton, SheetSelect, mInput, MField, haptic,
} from "@/mobile/ui/kit";

const GOVS = ["صنعاء", "عدن", "تعز", "الحديدة", "حضرموت", "إب", "ذمار", "مأرب", "أخرى"]
  .map((g) => ({ value: g, label: g }));

/** Same `/api/auth/register` the web uses — only the presentation is mobile (2 steps). */
export default function MRegister() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [type, setType] = useState("individual");
  const [f, setF] = useState({ office_name: "", owner_name: "", name: "", email: "",
    phone: "", governorate: "صنعاء", address: "", commercial_license: "", password: "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const step1Valid = type === "individual" ? f.name.trim().length > 2 : f.office_name.trim() && f.owner_name.trim();

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await register(type === "individual"
        ? { account_type: "individual", name: f.name, email: f.email, phone: f.phone,
            governorate: f.governorate, password: f.password }
        : { account_type: "office", office_name: f.office_name, owner_name: f.owner_name,
            email: f.email, phone: f.phone, governorate: f.governorate, address: f.address,
            commercial_license: f.commercial_license, password: f.password });
      haptic("success");
      toast.success("تم إنشاء الحساب");
      navigate("/m/home", { replace: true });
    } catch (err) { toast.error(apiError(err)); } finally { setBusy(false); }
  };

  return (
    <Screen className="pb-10">
      <TopBar title="إنشاء حساب" subtitle={`الخطوة ${step} من ٢`} back />
      <div className="px-4 pt-4 flex gap-2" data-testid="m-register-steps">
        {[1, 2].map((s) => (
          <div key={s} className={`h-1.5 flex-1 rounded-full transition-colors ${step >= s ? "bg-[#0A2540]" : "bg-[#0A2540]/12"}`} />
        ))}
      </div>

      <form onSubmit={submit} className="p-4" data-testid="m-register-form">
        {step === 1 ? (
          <div className="space-y-3.5">
            <div className="grid grid-cols-2 gap-3">
              {[["individual", "فرد / معتمر", User], ["office", "مكتب سفريات", Building2]].map(([key, label, Icon]) => (
                <button key={key} type="button" onClick={() => { haptic("light"); setType(key); }}
                        data-testid={`m-register-type-${key}`}
                        className={`rounded-[22px] border-2 p-5 flex flex-col items-center gap-2.5 transition-colors ${
                          type === key ? "border-[#0A2540] bg-white" : "border-transparent bg-white/70"}`}>
                  <Icon className={`w-7 h-7 ${type === key ? "text-[#0A2540]" : "text-[#0A2540]/35"}`} />
                  <span className="text-xs font-bold text-[#0A2540]">{label}</span>
                </button>
              ))}
            </div>

            <Card>
              {type === "individual" ? (
                <MField label="الاسم الكامل">
                  <input className={mInput} value={f.name} onChange={set("name")} data-testid="m-register-name" />
                </MField>
              ) : (
                <>
                  <MField label="اسم المكتب">
                    <input className={mInput} value={f.office_name} onChange={set("office_name")} data-testid="m-register-office" />
                  </MField>
                  <MField label="اسم المالك">
                    <input className={mInput} value={f.owner_name} onChange={set("owner_name")} data-testid="m-register-owner" />
                  </MField>
                </>
              )}
              <SheetSelect label="المحافظة" value={f.governorate} options={GOVS} testid="m-register-gov"
                           onChange={(v) => setF({ ...f, governorate: v })} />
              {type === "office" && (
                <MField label="السجل التجاري (اختياري)">
                  <input className={mInput} value={f.commercial_license} onChange={set("commercial_license")}
                         data-testid="m-register-license" />
                </MField>
              )}
            </Card>

            <PrimaryButton type="button" disabled={!step1Valid} onClick={() => setStep(2)} data-testid="m-register-next">
              متابعة
            </PrimaryButton>
          </div>
        ) : (
          <div className="space-y-3.5">
            <Card>
              <MField label="البريد الإلكتروني">
                <input className={mInput} type="email" inputMode="email" autoComplete="email"
                       value={f.email} onChange={set("email")} data-testid="m-register-email" />
              </MField>
              <MField label="رقم الجوال">
                <input className={mInput} inputMode="tel" value={f.phone} onChange={set("phone")}
                       data-testid="m-register-phone" />
              </MField>
              <MField label="كلمة المرور" hint="٨ أحرف على الأقل">
                <input className={mInput} type="password" autoComplete="new-password" value={f.password}
                       onChange={set("password")} data-testid="m-register-password" />
              </MField>
            </Card>

            <PrimaryButton type="submit" loading={busy} data-testid="m-register-submit"
                           disabled={!f.email || f.password.length < 8}>إنشاء الحساب</PrimaryButton>
            <GhostButton type="button" onClick={() => setStep(1)} data-testid="m-register-back-step">
              رجوع
            </GhostButton>
          </div>
        )}

        <Link to="/m/login" className="block text-center text-sm font-bold text-[#0A2540] mt-6">
          لديك حساب؟ تسجيل الدخول
        </Link>
      </form>
    </Screen>
  );
}
