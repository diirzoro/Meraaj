import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Building2, FileText, LogOut, ShieldCheck, Smartphone, User } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useShell } from "@/mobile/MobileShell";
import { APP_VERSION } from "@/mobile/api/client";
import { Screen, TopBar, Card } from "@/mobile/ui/kit";

export default function MAccount() {
  const { user, logout } = useAuth();
  const { shell } = useShell();
  const navigate = useNavigate();

  const doLogout = async () => {
    await logout();
    toast.success("تم تسجيل الخروج");
    navigate("/m/login", { replace: true });
  };

  const rows = [
    ...(user?.role === "office"
      ? [{ key: "statement", label: "كشف حساب المكتب", icon: FileText, to: "/m/statement" }]
      : []),
    { key: "wallet", label: "المحفظة والحركات", icon: Building2, to: "/m/wallet" },
    { key: "bookings", label: "حجوزاتي", icon: User, to: "/m/bookings" },
  ];

  return (
    <Screen>
      <TopBar title="حسابي" />
      <div className="p-4 space-y-3">
        <Card testid="m-account-identity">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-[#0A2540] flex items-center justify-center">
              <User className="w-6 h-6 text-[#D4AF37]" />
            </div>
            <div className="min-w-0">
              <p className="font-semibold text-sm text-[#0A2540] truncate">
                {shell?.user?.name || user?.office_name || user?.owner_name}
              </p>
              <p className="text-[11px] text-muted-foreground truncate">{user?.email}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                {user?.role === "office" ? "حساب مكتب" : "حساب فرد"}
                {shell?.user?.is_staff ? " · موظف مكتب" : ""}
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-0 overflow-hidden" testid="m-account-links">
          {rows.map((r) => (
            <button key={r.key} onClick={() => navigate(r.to)} data-testid={`m-account-link-${r.key}`}
                    className="w-full flex items-center gap-3 px-4 py-3.5 border-b last:border-0 text-start active:bg-slate-50">
              <r.icon className="w-[18px] h-[18px] text-[#0A2540]/60" />
              <span className="text-sm text-[#0A2540] flex-1">{r.label}</span>
            </button>
          ))}
        </Card>

        <Card testid="m-account-security">
          <div className="flex items-start gap-3">
            <ShieldCheck className="w-5 h-5 text-[#0A2540]/60 mt-0.5" />
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              كل عملية مالية أو حجز يتحقق منها السيرفر وفق صلاحياتك؛ التطبيق لا يحتفظ بكلمة
              المرور ولا يحدد الأسعار أو العمولات.
            </p>
          </div>
        </Card>

        <Card testid="m-account-version">
          <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
            <Smartphone className="w-4 h-4" />
            <span>إصدار التطبيق {APP_VERSION} · واجهة {shell?.api_version || "v1"}</span>
          </div>
        </Card>

        <button onClick={doLogout} data-testid="m-account-logout"
                className="w-full h-12 rounded-xl bg-white border border-red-200 text-red-600 text-sm font-semibold flex items-center justify-center gap-2">
          <LogOut className="w-4 h-4 rtl:rotate-180" /> تسجيل الخروج
        </button>
      </div>
    </Screen>
  );
}
