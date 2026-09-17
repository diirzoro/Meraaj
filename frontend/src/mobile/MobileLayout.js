import { useRef } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Home, Receipt, Wallet, Bell, User, Calculator } from "lucide-react";
import { useShell } from "@/mobile/MobileShell";
import { haptic } from "@/mobile/ui/kit";

const ICONS = { home: Home, bookings: Receipt, wallet: Wallet, notifications: Bell, account: User,
  operations: Receipt, accounting: Calculator };

const FALLBACK_TABS = [
  { key: "home", label: "الرئيسية", route: "/m/home" },
  { key: "bookings", label: "حجوزاتي", route: "/m/bookings" },
  { key: "wallet", label: "المحفظة", route: "/m/wallet" },
  { key: "notifications", label: "الإشعارات", route: "/m/notifications" },
  { key: "account", label: "حسابي", route: "/m/account" },
];

/** Bottom-tab shell. NO sidebar, never any dashboard chrome.
 *  Adds native push/pop page transitions driven by the history index. */
export default function MobileLayout() {
  const { tabs, badges } = useShell();
  const location = useLocation();
  const lastIdx = useRef(0);
  const idx = window.history.state?.idx ?? 0;
  const dir = idx === lastIdx.current ? "fade" : idx > lastIdx.current ? "push" : "pop";
  lastIdx.current = idx;

  const items = tabs.length ? tabs : FALLBACK_TABS;

  return (
    <div dir="rtl" className="m-app bg-[#F1F4F8] min-h-[100dvh]">
      <div key={location.pathname} className={`m-page-${dir}`}>
        <Outlet />
      </div>

      <nav data-testid="m-bottom-nav"
           className="fixed bottom-0 inset-x-0 z-30 bg-white/95 backdrop-blur border-t border-black/5 pb-[env(safe-area-inset-bottom)] shadow-[0_-8px_24px_-18px_rgba(10,37,64,0.5)]">
        <div className="grid grid-cols-5">
          {items.map((t) => {
            const Icon = ICONS[t.key] || Home;
            const active = location.pathname === t.route || location.pathname.startsWith(`${t.route}/`);
            const badge = t.key === "notifications" ? badges.notifications
              : t.key === "bookings" ? badges.active_bookings : 0;
            return (
              <NavLink key={t.key} to={t.route} data-testid={`m-tab-${t.key}`} onClick={() => haptic("light")}
                       className="relative flex flex-col items-center gap-1 pt-2.5 pb-2 active:scale-90 transition-transform">
                <span className={`relative transition-colors ${active ? "text-[#0A2540]" : "text-[#0A2540]/35"}`}>
                  <Icon className="w-[23px] h-[23px]" strokeWidth={active ? 2.4 : 1.9} />
                  {badge > 0 && (
                    <span data-testid={`m-tab-badge-${t.key}`}
                          className="absolute -top-1.5 -end-2.5 min-w-[18px] h-[18px] px-1 rounded-full bg-[#D4AF37] text-[#0A2540] text-[10px] font-bold flex items-center justify-center">
                      {badge > 9 ? "9+" : badge}
                    </span>
                  )}
                </span>
                <span className={`text-[10.5px] font-bold transition-colors ${active ? "text-[#0A2540]" : "text-[#0A2540]/40"}`}>
                  {t.label}
                </span>
                {active && <span className="absolute top-0 w-9 h-[3px] rounded-full bg-[#D4AF37]" />}
              </NavLink>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
