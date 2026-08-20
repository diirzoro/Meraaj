import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Network } from "lucide-react";
import { toast } from "sonner";

const GOVS = ["صنعاء", "عدن", "تعز", "الحديدة", "حضرموت", "إب", "ذمار", "مأرب", "أخرى"];

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [f, setF] = useState({
    office_name: "", owner_name: "", email: "", phone: "",
    governorate: "صنعاء", address: "", password: "",
  });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await register(f);
      toast.success("تم إنشاء حساب المكتب بنجاح");
      navigate("/dashboard");
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-[#F4F6F8]" dir="rtl">
      <form onSubmit={submit} className="w-full max-w-xl bg-white rounded-2xl card-shadow border p-8" data-testid="register-form">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-xl bg-[#0A2540] flex items-center justify-center">
            <Network className="w-5 h-5 text-[#D4AF37]" />
          </div>
          <div>
            <h2 className="font-head text-xl font-bold text-[#0A2540]">إنشاء حساب مكتب</h2>
            <p className="text-xs text-muted-foreground">انضم إلى شبكة معراج نتورك</p>
          </div>
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <Label className="mb-2 block">اسم المكتب *</Label>
            <Input data-testid="reg-office-name" required value={f.office_name} onChange={set("office_name")} />
          </div>
          <div>
            <Label className="mb-2 block">اسم المالك *</Label>
            <Input data-testid="reg-owner-name" required value={f.owner_name} onChange={set("owner_name")} />
          </div>
          <div>
            <Label className="mb-2 block">البريد الإلكتروني *</Label>
            <Input data-testid="reg-email" type="email" required value={f.email} onChange={set("email")} />
          </div>
          <div>
            <Label className="mb-2 block">رقم الهاتف *</Label>
            <Input data-testid="reg-phone" required value={f.phone} onChange={set("phone")} placeholder="+967..." />
          </div>
          <div>
            <Label className="mb-2 block">المحافظة *</Label>
            <select data-testid="reg-gov" value={f.governorate} onChange={set("governorate")}
                    className="w-full h-9 rounded-md border border-input bg-transparent px-3 text-sm">
              {GOVS.map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
          </div>
          <div>
            <Label className="mb-2 block">العنوان *</Label>
            <Input data-testid="reg-address" required value={f.address} onChange={set("address")} />
          </div>
          <div className="sm:col-span-2">
            <Label className="mb-2 block">كلمة المرور *</Label>
            <Input data-testid="reg-password" type="password" required minLength={6}
                   value={f.password} onChange={set("password")} placeholder="6 أحرف على الأقل" />
          </div>
        </div>

        <Button data-testid="register-submit" disabled={busy}
                className="w-full mt-6 bg-[#0A2540] hover:bg-[#061A2E] h-11">
          {busy ? "جارٍ الإنشاء..." : "إنشاء الحساب"}
        </Button>
        <p className="text-center text-sm text-muted-foreground mt-5">
          لديك حساب؟{" "}
          <Link to="/login" className="text-[#0A2540] font-semibold hover:underline" data-testid="go-login">
            سجّل الدخول
          </Link>
        </p>
      </form>
    </div>
  );
}
