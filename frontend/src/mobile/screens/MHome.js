import { useNavigate } from "react-router-dom";
import * as Icons from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useShell } from "@/mobile/MobileShell";
import mobileApi from "@/mobile/api/client";
import { Screen, Card, Skeleton, ErrorState, EmptyState, Money, StatusPill, useAsync } from "@/mobile/ui/kit";

const ICON_MAP = {
  kaaba: Icons.Landmark, bus: Icons.Bus, receipt: Icons.Receipt, wallet: Icons.Wallet,
  "plus-circle": Icons.PlusCircle, bell: Icons.Bell, user: Icons.User,
  "trending-up": Icons.TrendingUp, "file-text": Icons.FileText,
};

export default function MHome() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { services, wallet, badges, loading: shellLoading, error: shellError, reload } = useShell();
  const feed = useAsync(() => mobileApi.home());

  const primaryCurrency = (wallet?.SAR?.available || 0) >= (wallet?.USD?.available || 0) ? "SAR" : "USD";

  return (
    <Screen>
      <header className="bg-[#0A2540] text-white px-5 pt-[max(1.25rem,env(safe-area-inset-top))] pb-8 rounded-b-3xl"
              data-testid="m-home-header">
        <p className="text-white/55 text-xs">مرحباً</p>
        <h1 className="font-head text-xl font-bold truncate">
          {user?.office_name || user?.owner_name || user?.email}
        </h1>
        <div className="mt-5 bg-white/10 rounded-2xl p-4 backdrop-blur" data-testid="m-home-balance">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[11px] text-white/60">الرصيد المتاح</p>
              <p className="text-2xl mt-0.5">
                <Money value={wallet?.[primaryCurrency]?.available} currency={primaryCurrency} />
              </p>
            </div>
            <button onClick={() => navigate("/m/wallet/topup")} data-testid="m-home-topup-btn"
                    className="h-11 px-4 rounded-xl bg-[#D4AF37] text-[#0A2540] text-xs font-bold active:scale-95 transition-transform">
              شحن الرصيد
            </button>
          </div>
          {badges?.pending_topups > 0 && (
            <p className="text-[11px] text-[#D4AF37] mt-2" data-testid="m-home-pending-topups">
              لديك {badges.pending_topups} طلب شحن قيد المراجعة
            </p>
          )}
        </div>
      </header>

      <section className="px-4 -mt-4">
        {shellError && <ErrorState message={shellError} onRetry={reload} />}
        {shellLoading && !services.length ? <Skeleton rows={2} /> : (
          <div className="grid grid-cols-3 gap-3" data-testid="m-home-services">
            {services.map((s) => {
              const Icon = ICON_MAP[s.icon] || Icons.Circle;
              const soon = s.status !== "live";
              return (
                <button key={s.key} onClick={() => navigate(s.route)} data-testid={`m-service-${s.key}`}
                        className="relative bg-white rounded-2xl border border-black/5 p-3 flex flex-col items-center gap-2 active:scale-95 transition-transform">
                  <span className="w-11 h-11 rounded-xl bg-[#0A2540]/5 flex items-center justify-center">
                    <Icon className="w-5 h-5 text-[#0A2540]" />
                  </span>
                  <span className="text-[11px] font-semibold text-[#0A2540] text-center leading-tight">{s.label}</span>
                  {soon && (
                    <span className="absolute top-1.5 end-1.5 text-[9px] bg-amber-100 text-amber-800 rounded-full px-1.5 font-bold">
                      قريباً
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </section>

      <section className="px-4 mt-6">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-head text-base font-bold text-[#0A2540]">برامج متاحة</h2>
          <button onClick={() => navigate("/m/programs")} data-testid="m-home-all-programs"
                  className="text-xs font-semibold text-[#0A2540]/70">عرض الكل</button>
        </div>
        {feed.loading ? <Skeleton rows={2} />
          : feed.error ? <ErrorState message={feed.error} onRetry={feed.reload} />
          : (feed.data?.featured_programs || []).length === 0
            ? <EmptyState title="لا توجد برامج منشورة حالياً" />
            : (
              <div className="space-y-3">
                {feed.data.featured_programs.slice(0, 4).map((p) => (
                  <Card key={p.id} testid={`m-home-program-${p.id}`} onClick={() => navigate(`/m/programs/${p.id}`)}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-semibold text-sm text-[#0A2540] truncate">{p.title}</p>
                        <p className="text-[11px] text-muted-foreground mt-1">
                          {p.departure_date ? `المغادرة ${String(p.departure_date).slice(0, 10)}` : "بلا تاريخ محدد"}
                          {" · "}{p.available_seats} مقعد متاح
                        </p>
                      </div>
                      <div className="text-end shrink-0">
                        <Money value={p.final_sale_price} currency={p.currency} />
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
      </section>

      <section className="px-4 mt-6">
        <h2 className="font-head text-base font-bold text-[#0A2540] mb-3">أحدث حجوزاتي</h2>
        {feed.loading ? <Skeleton rows={1} />
          : (feed.data?.recent_bookings || []).length === 0
            ? <EmptyState title="لا حجوزات بعد" hint="ابدأ بحجز برنامج عمرة من الأعلى" />
            : (
              <div className="space-y-3">
                {feed.data.recent_bookings.map((b) => (
                  <Card key={b.id} testid={`m-home-booking-${b.id}`} onClick={() => navigate(`/m/bookings/${b.id}`)}>
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-semibold text-sm text-[#0A2540] truncate">{b.package_title}</p>
                        <p className="text-[11px] text-muted-foreground mt-1">{String(b.created_at).slice(0, 10)}</p>
                      </div>
                      <div className="text-end shrink-0 space-y-1">
                        <StatusPill status={b.status} />
                        <div className="text-xs"><Money value={b.amount_charged} currency={b.currency} /></div>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
      </section>
    </Screen>
  );
}
