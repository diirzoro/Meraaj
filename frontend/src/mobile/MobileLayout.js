import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Home, Receipt, Wallet, Bell, User } from "lucide-react";
import { useShell } from "@/mobile/MobileShell";

const ICONS = { home: Home, bookings: Receipt, wallet: Wallet, notifications: Bell, account: User };

/** Bottom-tab shell. Deliberately has NO sidebar and never renders dashboard chrome. */
export default function MobileLayout() {
  const { tabs, badges } = useShell();
  const { pathname } = useLocation();
  const items = tabs.length ? tabs : [
    { key: "home", label: "الرئيسية", route: "/m/home" },
    { key: "bookings", label: "حجوزاتي", route: "/m/bookings" },
    { key: "wallet", label: "المحفظة", route: "/m/wallet" },
    { key: "notifications", label: "الإشعارات", route: "/m/notifications" },
    { key: "account", label: "حسابي", route: "/m/account" },
  ];

  return (
    <div dir="rtl" className="bg-[#F4F6F8] min-h-[100dvh]">
      <Outlet />
      <nav data-testid="m-bottom-nav"
           className="fixed bottom-0 inset-x-0 z-30 bg-white border-t border-black/5 pb-[env(safe-area-inset-bottom)]">
        <div className="grid grid-cols-5">
          {items.map((t) => {
            const Icon = ICONS[t.key] || Home;
            const active = pathname === t.route || pathname.startsWith(`${t.route}/`);
            const badge = t.key === "notifications" ? badges.notifications
              : t.key === "bookings" ? badges.active_bookings : 0;
            return (
              <NavLink key={t.key} to={t.route} data-testid={`m-tab-${t.key}`}
                       className="relative flex flex-col items-center gap-1 py-2.5 active:scale-95 transition-transform">
                <span className={`relative ${active ? "text-[#0A2540]" : "text-[#0A2540]/40"}`}>
                  <Icon className="w-[22px] h-[22px]" />
                  {badge > 0 && (
                    <span data-testid={`m-tab-badge-${t.key}`}
                          className="absolute -top-1.5 -end-2 min-w-[17px] h-[17px] px-1 rounded-full bg-[#D4AF37] text-[#0A2540] text-[10px] font-bold flex items-center justify-center">
                      {badge > 9 ? "9+" : badge}
                    </span>
                  )}
                </span>
                <span className={`text-[10px] font-semibold ${active ? "text-[#0A2540]" : "text-[#0A2540]/45"}`}>
                  {t.label}
                </span>
                {active && <span className="absolute top-0 w-8 h-0.5 rounded-full bg-[#D4AF37]" />}
              </NavLink>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
