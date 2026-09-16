import { useNavigate } from "react-router-dom";
import * as Icons from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useShell } from "@/mobile/MobileShell";
import { Screen, Card, Skeleton, ErrorState, EmptyState } from "@/mobile/ui/kit";

const GROUP_ICONS = {
  operations: Icons.Receipt, money: Icons.Wallet, accounting: Icons.Calculator,
  reports: Icons.FileText, marketing: Icons.Megaphone,
};

/** ADMIN MOBILE HOME — built from `bootstrap.admin_sections`, which the BACKEND already
 *  filtered by RBAC. A group never appears without an allowed child, and nothing here is
 *  inferred from the role name. */
export default function MAdminHome() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { shell, loading, error, reload, badges } = useShell();
  const sections = shell?.admin_sections || [];

  return (
    <Screen>
      <header className="bg-[#0A2540] text-white px-5 pt-[max(1.25rem,env(safe-area-inset-top))] pb-7 rounded-b-3xl"
              data-testid="m-admin-header">
        <p className="text-white/55 text-xs">لوحة الإدارة — نسخة الجوال</p>
        <h1 className="font-head text-xl font-bold truncate">{shell?.user?.name || user?.email}</h1>
        <div className="flex gap-2 mt-4">
          <span className="text-[11px] bg-white/10 rounded-full px-3 py-1">
            الأقسام المسموحة: {badges?.admin_sections ?? 0}
          </span>
          {shell?.accounting?.enabled && (
            <span className="text-[11px] bg-[#D4AF37]/20 text-[#D4AF37] rounded-full px-3 py-1"
                  data-testid="m-admin-accounting-enabled">
              محاسبة مُفعّلة
            </span>
          )}
        </div>
      </header>

      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !sections.length ? <Skeleton rows={3} /> : (
        <div className="p-4 space-y-4">
          {sections.length === 0 && (
            <EmptyState title="لا توجد أقسام مسموحة" hint="لا تملك صلاحيات إدارية على الجوال" />
          )}
          {sections.map((g) => {
            const GIcon = GROUP_ICONS[g.group] || Icons.LayoutGrid;
            return (
              <div key={g.group} data-testid={`m-admin-group-${g.group}`}>
                <div className="flex items-center gap-2 mb-2 px-1">
                  <GIcon className="w-4 h-4 text-[#0A2540]/60" />
                  <h2 className="font-head text-sm font-bold text-[#0A2540]">{g.label}</h2>
                </div>
                <Card className="p-0 overflow-hidden">
                  {g.children.map((c) => (
                    <button key={c.key} onClick={() => navigate(c.route)}
                            data-testid={`m-admin-item-${c.key}`}
                            className="w-full flex items-center gap-3 px-4 py-3.5 border-b last:border-0 text-start active:bg-slate-50">
                      <span className="text-sm text-[#0A2540] flex-1">{c.label}</span>
                      <Icons.ChevronLeft className="w-4 h-4 text-[#0A2540]/30 rtl:rotate-180" />
                    </button>
                  ))}
                </Card>
              </div>
            );
          })}
        </div>
      )}
    </Screen>
  );
}
