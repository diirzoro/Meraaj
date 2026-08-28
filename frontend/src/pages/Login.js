import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiError } from "@/lib/api";
import { RESUME_KEY } from "@/config";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Network, ShieldCheck, Wallet, Store, Link2 } from "lucide-react";
import { toast } from "sonner";

const RAHAL_SSO_URL = process.env.REACT_APP_RAHAL_SSO_URL || "";

export default function Login() {
  const { login, ssoLogin } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [suspended, setSuspended] = useState(false);
  const [rahalOpen, setRahalOpen] = useState(false);

  const goAfterAuth = (u) => {
    const params = new URLSearchParams(window.location.search);
    const next = params.get("next");
    const resume = localStorage.getItem(RESUME_KEY);
    localStorage.removeItem(RESUME_KEY);
    const roleOk = (p) => !!p && !p.startsWith("/login") && !p.startsWith("/register") && !p.startsWith("/embed")
      && (p.startsWith("/admin") ? u.role === "super_admin" : u.role !== "super_admin");
    let dest;
    if (next && roleOk(next)) dest = next;
    else if (resume && roleOk(resume)) dest = resume;
    else dest = u.role === "super_admin" ? "/admin" : "/dashboard";
    navigate(dest, { replace: true });
  };

  const exchangeRahal = async (token) => {
    const u = await ssoLogin(token);
    toast.success("تم الدخول عبر حساب رحّال");
    goAfterAuth(u);
    return u;
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("suspended") === "1") setSuspended(true);
    const rahalToken = params.get("rahal_token") || params.get("token");
    if (rahalToken) {
      // strip the token from the URL before exchanging (avoid leaking it in history)
      window.history.replaceState(null, "", "/login");
      exchangeRahal(rahalToken).catch((e) => toast.error(apiError(e)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const u = await login(email, password);
      toast.success("مرحباً بعودتك");
      goAfterAuth(u);
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  const onRahalClick = () => {
    if (RAHAL_SSO_URL) { window.location.href = RAHAL_SSO_URL; return; }
    setRahalOpen(true);
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2" dir="rtl">
      <div className="hidden lg:flex flex-col justify-between bg-[#0A2540] text-white p-12 relative overflow-hidden">
        <div className="absolute -top-24 -start-24 w-96 h-96 rounded-full bg-[#D4AF37]/10 blur-3xl" />
        <div className="flex items-center gap-3 relative">
          <div className="w-11 h-11 rounded-xl bg-[#D4AF37] flex items-center justify-center">
            <Network className="w-6 h-6 text-[#0A2540]" />
          </div>
          <div>
            <div className="font-head font-bold text-xl">معراج نتورك</div>
            <div className="text-xs text-white/50">Meraaj Network — Target Media</div>
          </div>
        </div>

        <div className="relative">
          <h1 className="font-head text-4xl font-bold leading-snug mb-4">
            سوق البرامج <span className="text-[#D4AF37]">الموحّد</span><br /> للعمرة والسياحة
          </h1>
          <p className="text-white/60 leading-relaxed max-w-md">
            منصة تربط مكاتب السفر لبيع وشراء البرامج بنظام محافظ مسبقة الدفع وضمان مالي كامل يحمي الطرفين.
          </p>
          <div className="grid grid-cols-3 gap-4 mt-10 max-w-md">
            {[[Store, "سوق موحّد"], [Wallet, "محافظ وضمان"], [ShieldCheck, "حماية النزاعات"]].map(([Icon, t], i) => (
              <div key={i} className="bg-white/5 border border-white/10 rounded-xl p-4">
                <Icon className="w-5 h-5 text-[#D4AF37] mb-2" />
                <div className="text-xs text-white/70">{t}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="text-white/30 text-xs relative">© 2026 Target Media</div>
      </div>

      <div className="flex items-center justify-center p-8">
        <form onSubmit={submit} className="w-full max-w-sm" data-testid="login-form">
          <h2 className="font-head text-2xl font-bold text-[#0A2540] mb-1">تسجيل الدخول</h2>
          <p className="text-muted-foreground text-sm mb-8">أدخل بياناتك للوصول إلى حسابك</p>

          {suspended && (
            <div data-testid="suspended-banner" className="mb-6 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3">
              حسابك موقوف من قبل الإدارة. يرجى التواصل مع الدعم.
            </div>
          )}

          <div className="space-y-4">
            <div>
              <Label className="mb-2 block">البريد الإلكتروني</Label>
              <Input data-testid="login-email" type="email" value={email} required
                     onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
            </div>
            <div>
              <Label className="mb-2 block">كلمة المرور</Label>
              <Input data-testid="login-password" type="password" value={password} required
                     onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
            </div>
          </div>

          <Button data-testid="login-submit" disabled={busy}
                  className="w-full mt-6 bg-[#0A2540] hover:bg-[#061A2E] h-11">
            {busy ? "جارٍ الدخول..." : "دخول"}
          </Button>

          <div className="flex items-center gap-3 my-6">
            <div className="h-px flex-1 bg-border" />
            <span className="text-xs text-muted-foreground">أو</span>
            <div className="h-px flex-1 bg-border" />
          </div>

          <Button type="button" variant="outline" onClick={onRahalClick} data-testid="rahal-login-btn"
                  className="w-full h-11 border-[#D4AF37] text-[#0A2540] hover:bg-[#D4AF37]/10">
            <Link2 className="w-4 h-4" /> الدخول بحساب رحّال
          </Button>

          <p className="text-center text-sm text-muted-foreground mt-6">
            مكتب جديد؟{" "}
            <Link to="/register" className="text-[#0A2540] font-semibold hover:underline" data-testid="go-register">
              أنشئ حساب مكتب
            </Link>
          </p>
        </form>
      </div>

      <RahalTokenDialog open={rahalOpen} onOpenChange={setRahalOpen} onExchange={exchangeRahal} />
    </div>
  );
}

function RahalTokenDialog({ open, onOpenChange, onExchange }) {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try { await onExchange(token.trim()); onOpenChange(false); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent dir="rtl" data-testid="rahal-token-dialog">
        <DialogHeader><DialogTitle className="font-head text-[#0A2540]">الدخول بحساب رحّال</DialogTitle></DialogHeader>
        <p className="text-sm text-muted-foreground -mt-2">الصق رمز الدخول الصادر من نظام رحّال للمتابعة.</p>
        <Label className="mb-1 block">رمز الدخول (Token)</Label>
        <Textarea data-testid="rahal-token-input" value={token} onChange={(e) => setToken(e.target.value)} rows={4} placeholder="eyJhbGciOiJI..." />
        <DialogFooter>
          <Button className="bg-[#0A2540] hover:bg-[#061A2E]" onClick={submit} disabled={busy || !token.trim()} data-testid="rahal-token-submit">
            {busy ? "جارٍ التحقق..." : "متابعة"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
