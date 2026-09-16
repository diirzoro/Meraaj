import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { Building2, User } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { apiError } from "@/lib/api";
import { TopBar, Screen, PrimaryButton, mInput, MField } from "@/mobile/ui/kit";

const GOVS = ["صنعاء", "عدن", "تعز", "الحديدة", "حضرموت", "إب", "ذمار", "مأرب", "أخرى"];

/** Same `/api/auth/register` the web uses — only the presentation is mobile. */
export default function MRegister() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [type, setType] = useState("individual");
  const [f, setF] = useState({ office_name: "", owner_name: "", name: "", email: "",
    phone: "", governorate: "صنعاء", address: "", commercial_license: "", password: "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

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
      toast.success("تم إنشاء الحساب");
      navigate("/m/home", { replace: true });
    } catch (err) { toast.error(apiError(err)); } finally { setBusy(false); }
  };

  return (
    <Screen className="pb-8">
      <TopBar title="إنشاء حساب" subtitle="انضم إلى شبكة معراج" back />
      <form onSubmit={submit} className="p-4" data-testid="m-register-form">
        <div className="grid grid-cols-2 gap-3 mb-4">
          {[["individual", "فرد / معتمر", User], ["office", "مكتب سفريات", Building2]].map(([key, label, Icon]) => (
            <button key={key} type="button" onClick={() => setType(key)} data-testid={`m-register-type-${key}`}
                    className={`rounded-2xl border-2 p-4 flex flex-col items-center gap-2 ${type === key ? "border-[#0A2540] bg-white" : "border-transparent bg-white/60"}`}>
              <Icon className={`w-6 h-6 ${type === key ? "text-[#0A2540]" : "text-[#0A2540]/40"}`} />
              <span className="text-xs font-semibold text-[#0A2540]">{label}</span>
            </button>
          ))}
        </div>

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
        <MField label="البريد الإلكتروني">
          <input className={mInput} type="email" inputMode="email" value={f.email} onChange={set("email")} data-testid="m-register-email" />
        </MField>
        <MField label="رقم الجوال">
          <input className={mInput} inputMode="tel" value={f.phone} onChange={set("phone")} data-testid="m-register-phone" />
        </MField>
        <MField label="المحافظة">
          <select className={mInput} value={f.governorate} onChange={set("governorate")} data-testid="m-register-gov">
            {GOVS.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </MField>
        {type === "office" && (
          <MField label="السجل التجاري (اختياري)">
            <input className={mInput} value={f.commercial_license} onChange={set("commercial_license")} data-testid="m-register-license" />
          </MField>
        )}
        <MField label="كلمة المرور" hint="٨ أحرف على الأقل">
          <input className={mInput} type="password" value={f.password} onChange={set("password")} data-testid="m-register-password" />
        </MField>

        <PrimaryButton type="submit" loading={busy} data-testid="m-register-submit"
                       disabled={!f.email || f.password.length < 8}>إنشاء الحساب</PrimaryButton>
        <Link to="/m/login" className="block text-center text-sm font-semibold text-[#0A2540] mt-5">
          لديك حساب؟ تسجيل الدخول
        </Link>
      </form>
    </Screen>
  );
}
