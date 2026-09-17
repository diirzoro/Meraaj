import { useNavigate } from "react-router-dom";
import * as Icons from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useShell } from "@/mobile/MobileShell";
import {
  Screen, Card, Skeleton, ErrorState, EmptyState, KpiCard, ListRow, SectionTitle, Chip, Money, useAsync,
} from "@/mobile/ui/kit";

const GROUP_ICONS = {
  operations: Icons.Receipt, money: Icons.Wallet, accounting: Icons.Calculator,
  reports: Icons.FileText, marketing: Icons.Megaphone,
};

/** ADMIN MOBILE HOME — KPI-first, not a vertical sidebar.
 *  Sections come from `bootstrap.admin_sections`, which the BACKEND already filtered by
 *  RBAC; the KPI strip reuses the EXISTING `/api/admin/dashboard` (no new endpoint). */
export default function MAdminHome() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { shell, loading, error, reload, badges } = useShell();
  const sections = shell?.admin_sections || [];
  const stats = useAsync(() => api.get("/admin/dashboard").then((r) => r.data).catch(() => null),
    [], { cacheKey: "m-admin-dashboard" });
  const s = stats.data || {};

  const quick = [
    { key: "topups", label: "طلبات الشحن", icon: Icons.Wallet, route: "/m/admin/topups" },
    { key: "orders", label: "مركز الطلبات", icon: Icons.Receipt, route: "/m/admin/orders" },
    ...(shell?.accounting?.enabled
      ? [{ key: "accounting", label: "الحسابات", icon: Icons.Calculator, route: "/m/accounting" }] : []),
  ].filter((q) => sections.some((g) => g.children.some((c) => c.route === q.route)) || q.key === "accounting");

  const refresh = async () => { await Promise.all([reload(), stats.reload()]); };

  return (
    <Screen refresh={refresh}>
      <header className="bg-[#0A2540] text-white px-5 pt-[max(1.4rem,env(safe-area-inset-top))] pb-9 rounded-b-[32px] relative overflow-hidden"
              data-testid="m-admin-header">
        <div className="absolute -top-14 -start-10 w-48 h-48 rounded-full bg-[#D4AF37]/10" />
        <div className="relative flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-white/50 text-xs font-semibold">لوحة الإدارة — نسخة الجوال</p>
            <h1 className="font-head text-2xl font-bold truncate mt-0.5">{shell?.user?.name || user?.email}</h1>
          </div>
          <button onClick={() => navigate("/m/notifications")} data-testid="m-admin-bell"
                  className="relative w-11 h-11 rounded-2xl bg-white/10 flex items-center justify-center active:scale-90 transition-transform shrink-0">
            <Icons.Bell className="w-5 h-5" />
            {badges?.notifications > 0 && (
              <span className="absolute -top-1 -end-1 min-w-[18px] h-[18px] px-1 rounded-full bg-[#D4AF37] text-[#0A2540] text-[10px] font-bold flex items-center justify-center">
                {badges.notifications > 9 ? "9+" : badges.notifications}
              </span>
            )}
          </button>
        </div>
        <div className="relative flex flex-wrap gap-2 mt-4">
          <Chip tone="gold">الأقسام المسموحة: {badges?.admin_sections ?? 0}</Chip>
          {shell?.accounting?.enabled && (
            <span data-testid="m-admin-accounting-enabled"><Chip tone="good">محاسبة مُفعّلة</Chip></span>
          )}
        </div>
      </header>

      {/* KPI strip — EXISTING /api/admin/dashboard payload only (per-currency, no merging) */}
      <section className="px-4 -mt-5 relative">
        {stats.loading ? <Skeleton rows={1} /> : stats.data ? (
          <div className="space-y-3 m-stagger" data-testid="m-admin-kpis">
            <div className="grid grid-cols-2 gap-3">
              <KpiCard label="طلبات شحن معلّقة" icon={Icons.Clock} tone={s.pending_topups ? "warn" : "navy"}
                       testid="m-admin-kpi-topups" value={s.pending_topups ?? 0}
                       onClick={() => navigate("/m/admin/topups")} />
              <KpiCard label="إجمالي الحجوزات" icon={Icons.Receipt} testid="m-admin-kpi-bookings"
                       value={s.bookings_count ?? 0} onClick={() => navigate("/m/admin/orders")} />
              <KpiCard label="مكاتب مسجّلة" icon={Icons.Building2} testid="m-admin-kpi-offices"
                       value={s.offices_count ?? 0} hint={`${s.individuals_count ?? 0} فرد`} />
              <KpiCard label="برامج منشورة" icon={Icons.Landmark} testid="m-admin-kpi-packages"
                       value={s.packages_count ?? 0} />
            </div>

            <div className="grid grid-cols-2 gap-3">
              {["SAR", "USD"].map((c) => (
                <KpiCard key={c} label={`إيراد المنصة (${c})`} icon={Icons.TrendingUp} tone="gold"
                         testid={`m-admin-kpi-revenue-${c}`}
                         value={<Money value={s.platform_revenue?.[c] ?? 0} />}
                         hint={`سيولة: ${Number(s.liquidity?.[c]?.available ?? 0).toLocaleString("en-US")}`} />
              ))}
            </div>

            {(s.pending_withdrawals || s.pending_transfers || s.open_disputes) ? (
              <div className="flex gap-2 overflow-x-auto m-hscroll pb-1" data-testid="m-admin-alerts">
                {[["سحوبات معلّقة", s.pending_withdrawals], ["تحويلات معلّقة", s.pending_transfers],
                  ["نزاعات مفتوحة", s.open_disputes]].filter(([, v]) => v).map(([label, v]) => (
                  <span key={label} className="shrink-0 rounded-full bg-amber-50 border border-amber-200 text-amber-900 text-[11px] font-bold px-3.5 py-2">
                    {label}: {v}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      {/* quick actions */}
      {quick.length > 0 && (
        <section className="px-4 mt-7">
          <SectionTitle>إجراءات سريعة</SectionTitle>
          <div className="flex gap-3 overflow-x-auto m-hscroll pb-1">
            {quick.map((q) => (
              <button key={q.key} onClick={() => navigate(q.route)} data-testid={`m-admin-quick-${q.key}`}
                      className="w-28 shrink-0 bg-white rounded-[22px] border border-black/[0.04] p-4 flex flex-col items-center gap-2.5 active:scale-95 transition-transform shadow-[0_6px_20px_-14px_rgba(10,37,64,0.5)]">
                <span className="w-12 h-12 rounded-2xl bg-[#0A2540]/[0.06] flex items-center justify-center">
                  <q.icon className="w-5 h-5 text-[#0A2540]" />
                </span>
                <span className="text-[11px] font-bold text-[#0A2540] text-center leading-tight">{q.label}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* permitted sections */}
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !sections.length ? <Skeleton rows={3} /> : (
        <div className="p-4 pt-7 space-y-5">
          {sections.length === 0 && (
            <EmptyState title="لا توجد أقسام مسموحة" hint="لا تملك صلاحيات إدارية على الجوال" />
          )}
          {sections.map((g) => {
            const GIcon = GROUP_ICONS[g.group] || Icons.LayoutGrid;
            return (
              <div key={g.group} data-testid={`m-admin-group-${g.group}`}>
                <div className="flex items-center gap-2 mb-2.5 px-1">
                  <GIcon className="w-4 h-4 text-[#0A2540]/50" />
                  <h2 className="font-head text-sm font-bold text-[#0A2540]">{g.label}</h2>
                </div>
                <Card className="p-0 overflow-hidden">
                  {g.children.map((c, i) => (
                    <ListRow key={c.key} label={c.label} testid={`m-admin-item-${c.key}`}
                             onClick={() => navigate(c.route)} last={i === g.children.length - 1} />
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
