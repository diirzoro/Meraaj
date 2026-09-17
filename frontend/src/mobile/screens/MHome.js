import { useNavigate } from "react-router-dom";
import * as Icons from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useShell } from "@/mobile/MobileShell";
import mobileApi from "@/mobile/api/client";
import {
  Screen, Card, Skeleton, ErrorState, EmptyState, Money, StatusPill, SectionTitle, Chip, useAsync,
} from "@/mobile/ui/kit";

const ICON_MAP = {
  kaaba: Icons.Landmark, bus: Icons.Bus, receipt: Icons.Receipt, wallet: Icons.Wallet,
  "plus-circle": Icons.PlusCircle, bell: Icons.Bell, user: Icons.User,
  "trending-up": Icons.TrendingUp, "file-text": Icons.FileText,
};

const cover = (p) => p?.cover_image || (Array.isArray(p?.images) ? p.images[0] : null);

export default function MHome() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { services, wallet, badges, loading: shellLoading, error: shellError, reload } = useShell();
  const feed = useAsync(() => mobileApi.home(), [], { cacheKey: "m-home-feed" });

  const primaryCurrency = (wallet?.SAR?.available || 0) >= (wallet?.USD?.available || 0) ? "SAR" : "USD";
  const refresh = async () => { await Promise.all([reload(), feed.reload()]); };

  return (
    <Screen refresh={refresh}>
      {/* ---- identity + wallet hero ---- */}
      <header className="bg-[#0A2540] text-white px-5 pt-[max(1.4rem,env(safe-area-inset-top))] pb-10 rounded-b-[32px] relative overflow-hidden"
              data-testid="m-home-header">
        <div className="absolute -top-16 -start-10 w-48 h-48 rounded-full bg-[#D4AF37]/10" />
        <div className="relative flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-white/50 text-xs font-semibold">مرحباً</p>
            <h1 className="font-head text-2xl font-bold truncate mt-0.5">
              {user?.office_name || user?.owner_name || user?.email}
            </h1>
          </div>
          <button onClick={() => navigate("/m/notifications")} data-testid="m-home-bell"
                  className="relative w-11 h-11 rounded-2xl bg-white/10 flex items-center justify-center active:scale-90 transition-transform shrink-0">
            <Icons.Bell className="w-5 h-5" />
            {badges?.notifications > 0 && (
              <span className="absolute -top-1 -end-1 min-w-[18px] h-[18px] px-1 rounded-full bg-[#D4AF37] text-[#0A2540] text-[10px] font-bold flex items-center justify-center">
                {badges.notifications > 9 ? "9+" : badges.notifications}
              </span>
            )}
          </button>
        </div>

        <div className="relative mt-6 bg-white/[0.08] rounded-3xl p-5 border border-white/10" data-testid="m-home-balance">
          <p className="text-[11px] text-white/55 font-semibold">الرصيد المتاح</p>
          <p className="text-[32px] leading-tight mt-1">
            <Money value={wallet?.[primaryCurrency]?.available} currency={primaryCurrency} />
          </p>
          <div className="flex gap-2 mt-4">
            <button onClick={() => navigate("/m/wallet/topup")} data-testid="m-home-topup-btn"
                    className="flex-1 h-12 rounded-2xl bg-[#D4AF37] text-[#0A2540] text-xs font-bold flex items-center justify-center gap-1.5 active:scale-95 transition-transform">
              <Icons.PlusCircle className="w-4 h-4" /> شحن الرصيد
            </button>
            <button onClick={() => navigate("/m/wallet")} data-testid="m-home-wallet-btn"
                    className="flex-1 h-12 rounded-2xl bg-white/10 text-white text-xs font-bold flex items-center justify-center gap-1.5 active:scale-95 transition-transform">
              <Icons.Wallet className="w-4 h-4" /> المحفظة
            </button>
          </div>
          {badges?.pending_topups > 0 && (
            <p className="text-[11px] text-[#D4AF37] mt-3 flex items-center gap-1.5" data-testid="m-home-pending-topups">
              <Icons.Clock className="w-3.5 h-3.5" />
              لديك {badges.pending_topups} طلب شحن قيد المراجعة
            </p>
          )}
        </div>
      </header>

      {/* ---- services (server-driven) ---- */}
      <section className="px-4 -mt-5 relative">
        {shellError && <ErrorState message={shellError} onRetry={reload} />}
        {shellLoading && !services.length ? <Skeleton rows={2} /> : (
          <div className="bg-white rounded-[26px] border border-black/[0.04] p-4 shadow-[0_8px_26px_-16px_rgba(10,37,64,0.5)]">
            <div className="grid grid-cols-4 gap-y-5 gap-x-2 m-stagger" data-testid="m-home-services">
              {services.map((s) => {
                const Icon = ICON_MAP[s.icon] || Icons.Circle;
                const soon = s.status !== "live";
                return (
                  <button key={s.key} onClick={() => navigate(s.route)} data-testid={`m-service-${s.key}`}
                          className="relative flex flex-col items-center gap-2 active:scale-90 transition-transform">
                    <span className={`w-14 h-14 rounded-[20px] flex items-center justify-center ${
                      soon ? "bg-slate-100" : "bg-[#0A2540]/[0.06]"}`}>
                      <Icon className={`w-6 h-6 ${soon ? "text-[#0A2540]/35" : "text-[#0A2540]"}`} />
                    </span>
                    <span className="text-[11px] font-bold text-[#0A2540]/80 text-center leading-tight">{s.label}</span>
                    {soon && (
                      <span className="absolute -top-1 end-0 text-[9px] bg-[#D4AF37]/20 text-[#7a6216] rounded-full px-1.5 font-bold">
                        قريباً
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </section>

      {/* ---- featured programs carousel ---- */}
      <section className="mt-8">
        <div className="px-4">
          <SectionTitle action="عرض الكل" onAction={() => navigate("/m/programs")} testid="m-home-all-programs">
            برامج متاحة
          </SectionTitle>
        </div>
        {feed.loading ? <Skeleton rows={2} />
          : feed.error ? <ErrorState message={feed.error} onRetry={feed.reload} />
          : (feed.data?.featured_programs || []).length === 0
            ? <EmptyState title="لا توجد برامج منشورة حالياً" />
            : (
              <div className="flex gap-3 overflow-x-auto m-hscroll px-4 pb-2">
                {feed.data.featured_programs.slice(0, 6).map((p) => (
                  <button key={p.id} data-testid={`m-home-program-${p.id}`}
                          onClick={() => navigate(`/m/programs/${p.id}`)}
                          className="w-[250px] shrink-0 bg-white rounded-[24px] border border-black/[0.04] overflow-hidden text-start shadow-[0_6px_22px_-14px_rgba(10,37,64,0.45)] active:scale-[0.98] transition-transform">
                    <div className="h-28 bg-[#0A2540] relative">
                      {cover(p) ? (
                        <img src={cover(p)} alt="" className="w-full h-full object-cover" loading="lazy" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <Icons.Landmark className="w-8 h-8 text-[#D4AF37]/60" />
                        </div>
                      )}
                      <span className="absolute bottom-2 start-2">
                        <Chip tone="gold">{p.available_seats} مقعد</Chip>
                      </span>
                    </div>
                    <div className="p-3.5">
                      <p className="font-bold text-sm text-[#0A2540] line-clamp-2 min-h-[2.5rem]">{p.title}</p>
                      <div className="flex items-center justify-between mt-2.5">
                        <span className="text-[11px] text-muted-foreground">
                          {p.departure_date ? String(p.departure_date).slice(0, 10) : "بلا تاريخ"}
                        </span>
                        <Money value={p.final_sale_price} currency={p.currency} className="text-sm" />
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
      </section>

      {/* ---- recent bookings ---- */}
      <section className="px-4 mt-7">
        <SectionTitle action="حجوزاتي" onAction={() => navigate("/m/bookings")} testid="m-home-all-bookings">
          أحدث حجوزاتي
        </SectionTitle>
        {feed.loading ? <Skeleton rows={1} />
          : (feed.data?.recent_bookings || []).length === 0
            ? <EmptyState title="لا حجوزات بعد" hint="ابدأ بحجز برنامج عمرة من الأعلى" />
            : (
              <div className="space-y-3 m-stagger">
                {feed.data.recent_bookings.map((b) => (
                  <Card key={b.id} testid={`m-home-booking-${b.id}`} onClick={() => navigate(`/m/bookings/${b.id}`)}>
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-bold text-sm text-[#0A2540] truncate">{b.package_title}</p>
                        <p className="text-[11px] text-muted-foreground mt-1">{String(b.created_at).slice(0, 10)}</p>
                      </div>
                      <div className="text-end shrink-0 space-y-1.5">
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
