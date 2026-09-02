import { useState, useRef } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  LayoutDashboard, Store, Package, ShoppingBag, TicketCheck, Wallet,
  Banknote, ShieldAlert, LogOut, Building2, Network, Menu, X, TrendingUp, Ban,
  BookOpen, ArrowDownCircle, Percent, Gauge, Bell, FileSpreadsheet, Settings2,
} from "lucide-react";

const officeNav = [
  { to: "/dashboard", label: "الرئيسية", icon: LayoutDashboard },
  { to: "/market", label: "سوق البرامج", icon: Store },
  { to: "/packages", label: "برامجي (بائع)", icon: Package },
  { to: "/sales", label: "مبيعاتي", icon: TicketCheck },
  { to: "/bookings", label: "حجوزاتي (مشتري)", icon: ShoppingBag },
  { to: "/wallet", label: "المحفظة", icon: Wallet },
];

const individualNav = [
  { to: "/dashboard", label: "الرئيسية", icon: LayoutDashboard },
  { to: "/market", label: "البحث عن رحلات", icon: Store },
  { to: "/bookings", label: "حجوزاتي", icon: ShoppingBag },
  { to: "/wallet", label: "المحفظة", icon: Wallet },
  { to: "/marketer", label: "التسويق بالعمولة", icon: TrendingUp },
];

const adminNav = [
  { to: "/admin", label: "لوحة المؤشرات", icon: LayoutDashboard },
  { to: "/admin/orders", label: "مركز الطلبات", icon: ShoppingBag },
  { to: "/admin/finance", label: "المركز المالي", icon: Banknote },
  { to: "/admin/ledger", label: "الدفتر المالي", icon: BookOpen },
  { to: "/admin/withdrawals", label: "دورة السحوبات", icon: ArrowDownCircle },
  { to: "/admin/commissions", label: "محرك العمولات", icon: Percent },
  { to: "/admin/credit", label: "السقف الائتماني", icon: Gauge },
  { to: "/admin/programs", label: "البرامج والمقاعد", icon: Package },
  { to: "/admin/travelers", label: "المسافرون والمستندات", icon: TicketCheck },
  { to: "/admin/integrations", label: "صحة التكامل", icon: Network },
  { to: "/admin/orgs", label: "المؤسسات والمكاتب", icon: Building2 },
  { to: "/admin/roles", label: "الصلاحيات والأمان", icon: ShieldAlert },
  { to: "/admin/notifications", label: "الإشعارات والمهام", icon: Bell },
  { to: "/admin/reports", label: "التقارير", icon: FileSpreadsheet },
  { to: "/admin/system", label: "إعدادات النظام", icon: Settings2 },
  { to: "/admin/cancellations", label: "طلبات الإلغاء", icon: Ban },
  { to: "/admin/disputes", label: "النزاعات", icon: ShieldAlert },
];

function navFor(role) {
  if (role === "super_admin") return adminNav;
  if (role === "individual") return individualNav;
  return officeNav;
}

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const nav = navFor(user?.role);

  const doLogout = async () => { localStorage.removeItem("meraaj_resume_route"); await logout(); navigate("/login"); };

  // Edge-swipe to open / swipe to close the mobile sidebar (RTL: sidebar sits on the right).
  const sx = useRef(0), sy = useRef(0);
  const onTouchStart = (e) => { sx.current = e.touches[0].clientX; sy.current = e.touches[0].clientY; };
  const onTouchEnd = (e) => {
    if (typeof window === "undefined" || window.innerWidth >= 1024) return;
    const dx = e.changedTouches[0].clientX - sx.current;
    const dy = e.changedTouches[0].clientY - sy.current;
    if (Math.abs(dx) < 60 || Math.abs(dy) > Math.abs(dx)) return; // ignore vertical scrolls
    if (!open && sx.current > window.innerWidth - 40 && dx < 0) setOpen(true);
    else if (open && dx > 0) setOpen(false);
  };

  return (
    <div className="min-h-screen bg-[#F4F6F8]" onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
      {/* Mobile top bar */}
      <div className="lg:hidden fixed top-0 inset-x-0 z-30 bg-[#0A2540] text-white h-14 flex items-center justify-between px-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-[#D4AF37] flex items-center justify-center"><Network className="w-4 h-4 text-[#0A2540]" /></div>
          <span className="font-head font-bold">معراج نتورك</span>
        </div>
        <button onClick={() => setOpen(true)} data-testid="menu-open-btn"><Menu className="w-6 h-6" /></button>
      </div>

      {open && <div className="lg:hidden fixed inset-0 bg-black/40 z-30" onClick={() => setOpen(false)} />}

      <aside
        data-testid="sidebar"
        className={`w-[min(18rem,85vw)] lg:w-72 bg-[#0A2540] text-white flex flex-col fixed top-0 bottom-0 start-0 z-40 transition-transform duration-300 ${
          open ? "translate-x-0" : "translate-x-full lg:translate-x-0"
        }`}
      >
        <div className="px-6 py-6 border-b border-white/10 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#D4AF37] flex items-center justify-center"><Network className="w-5 h-5 text-[#0A2540]" /></div>
            <div>
              <div className="font-head font-bold text-lg leading-tight">معراج نتورك</div>
              <div className="text-[11px] text-white/50">Meraaj Network</div>
            </div>
          </div>
          <button className="lg:hidden" onClick={() => setOpen(false)} data-testid="menu-close-btn"><X className="w-5 h-5" /></button>
        </div>

        <nav className="flex-1 px-3 py-4 pb-24 space-y-1 overflow-y-auto">
          {nav.map((item) => (
            <NavLink
              key={item.to} to={item.to} end={item.to === "/admin"}
              onClick={() => setOpen(false)}
              data-testid={`nav-${item.to.replace(/\//g, "") || "home"}`}
              className={({ isActive }) =>
                `sidebar-link flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium ${
                  isActive ? "bg-white/10 text-white" : "text-white/60 hover:bg-white/5 hover:text-white"
                }`
              }
            >
              <item.icon className="w-[18px] h-[18px]" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="px-3 py-4 border-t border-white/10">
          <div className="px-4 py-2 flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-white/10 flex items-center justify-center"><Building2 className="w-4 h-4" /></div>
            <div className="min-w-0">
              <div className="text-sm font-semibold truncate">{user?.office_name}</div>
              <div className="text-[11px] text-white/50 truncate">{user?.email}</div>
            </div>
          </div>
          <button onClick={doLogout} data-testid="logout-btn"
                  className="sidebar-link mt-1 w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm text-white/60 hover:bg-white/5 hover:text-white">
            <LogOut className="w-[18px] h-[18px] rtl:rotate-180" /> تسجيل الخروج
          </button>
        </div>
      </aside>

      <main className="lg:ms-72 min-h-screen pt-14 lg:pt-0">
        <div className="max-w-6xl mx-auto px-5 sm:px-8 py-8 animate-fade-up">{children}</div>
      </main>
    </div>
  );
}

export function PageHeader({ title, subtitle, action }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between mb-8 gap-4">
      <div>
        <h1 className="font-head text-2xl sm:text-3xl font-bold text-[#0A2540]">{title}</h1>
        {subtitle && <p className="text-muted-foreground mt-1 text-sm">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}


export function PublicLayout({ children }) {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-[#F4F6F8]" dir="rtl">
      <header className="sticky top-0 z-40 bg-[#0A2540] border-b border-white/10">
        <div className="max-w-6xl mx-auto px-5 sm:px-8 h-16 flex items-center justify-between">
          <button onClick={() => navigate("/")} className="flex items-center gap-3" data-testid="public-logo-btn">
            <div className="w-9 h-9 rounded-xl bg-[#D4AF37] flex items-center justify-center"><Network className="w-5 h-5 text-[#0A2540]" /></div>
            <div className="text-white text-start">
              <div className="font-head font-bold leading-tight">معراج نتورك</div>
              <div className="text-[10px] text-white/50">Meraaj Network</div>
            </div>
          </button>
          <div className="flex items-center gap-2 sm:gap-3">
            <NavLink to="/market" data-testid="public-nav-market"
                     className="text-white/80 hover:text-white text-sm font-medium hidden sm:block">سوق البرامج</NavLink>
            <button onClick={() => navigate("/login")} data-testid="public-login-btn"
                    className="text-white hover:bg-white/10 h-9 px-4 rounded-md text-sm">تسجيل الدخول</button>
            <button onClick={() => navigate("/register")} data-testid="public-register-btn"
                    className="bg-[#D4AF37] hover:bg-[#c39f2f] text-[#0A2540] font-semibold h-9 px-4 rounded-md text-sm">إنشاء حساب</button>
          </div>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-5 sm:px-8 py-8 animate-fade-up">{children}</main>
    </div>
  );
}
