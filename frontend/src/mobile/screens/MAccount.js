import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Building2, FileText, LogOut, Receipt, ShieldCheck, Smartphone, TrendingUp, User, Wallet,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useShell } from "@/mobile/MobileShell";
import { APP_VERSION } from "@/mobile/api/client";
import { Screen, TopBar, Card, ListRow, DangerButton, Chip, clearAsyncCache } from "@/mobile/ui/kit";

export default function MAccount() {
  const { user, logout } = useAuth();
  const { shell } = useShell();
  const navigate = useNavigate();

  const doLogout = async () => {
    await logout();
    clearAsyncCache();
    toast.success("تم تسجيل الخروج");
    navigate("/m/login", { replace: true });
  };

  const isOffice = user?.role === "office";
  const activity = [
    { key: "bookings", label: "حجوزاتي", icon: Receipt, to: "/m/bookings" },
    ...(isOffice ? [{ key: "sales", label: "مبيعاتي", icon: TrendingUp, to: "/m/sales" }] : []),
    { key: "wallet", label: "المحفظة والحركات", icon: Wallet, to: "/m/wallet" },
    ...(isOffice ? [{ key: "statement", label: "كشف حساب المكتب", icon: FileText, to: "/m/statement" }] : []),
  ];

  return (
    <Screen>
      <TopBar title="حسابي" large />

      <div className="p-4 space-y-5">
        {/* identity */}
        <Card testid="m-account-identity">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-[22px] bg-[#0A2540] flex items-center justify-center shrink-0">
              {isOffice ? <Building2 className="w-7 h-7 text-[#D4AF37]" /> : <User className="w-7 h-7 text-[#D4AF37]" />}
            </div>
            <div className="min-w-0">
              <p className="font-head font-bold text-base text-[#0A2540] truncate">
                {shell?.user?.name || user?.office_name || user?.owner_name}
              </p>
              <p className="text-xs text-muted-foreground truncate mt-0.5">{user?.email}</p>
              <div className="flex gap-1.5 mt-2">
                <Chip>{isOffice ? "حساب مكتب" : "حساب فرد"}</Chip>
                {shell?.user?.is_staff ? <Chip tone="gold">موظف مكتب</Chip> : null}
              </div>
            </div>
          </div>
        </Card>

        {/* activity */}
        <div>
          <p className="text-[11px] font-bold text-[#0A2540]/45 px-2 mb-2">نشاطي</p>
          <Card className="p-0 overflow-hidden" testid="m-account-links">
            {activity.map((r, i) => (
              <ListRow key={r.key} icon={r.icon} label={r.label} testid={`m-account-link-${r.key}`}
                       onClick={() => navigate(r.to)} last={i === activity.length - 1} />
            ))}
          </Card>
        </div>

        {/* app info */}
        <div>
          <p className="text-[11px] font-bold text-[#0A2540]/45 px-2 mb-2">التطبيق</p>
          <Card className="p-0 overflow-hidden" testid="m-account-version">
            <ListRow icon={Smartphone} label="إصدار التطبيق" value={APP_VERSION} />
            <ListRow icon={ShieldCheck} label="واجهة الخدمات" value={shell?.api_version || "v1"} last />
          </Card>
          <p className="text-[11px] text-muted-foreground leading-relaxed mt-3 px-2" data-testid="m-account-security">
            كل عملية مالية أو حجز يتحقق منها السيرفر وفق صلاحياتك؛ التطبيق لا يحتفظ بكلمة المرور
            ولا يحدد الأسعار أو العمولات.
          </p>
        </div>

        <DangerButton onClick={doLogout} data-testid="m-account-logout">
          <LogOut className="w-4 h-4 rtl:rotate-180" /> تسجيل الخروج
        </DangerButton>
      </div>
    </Screen>
  );
}
