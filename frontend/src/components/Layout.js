import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  LayoutDashboard, Store, Package, ShoppingBag, TicketCheck, Wallet,
  Users, Banknote, ShieldAlert, LogOut, Building2, Network, Menu, X, TrendingUp,
} from "lucide-react";

const officeNav = [
  { to: "/dashboard", label: "الرئيسية", icon: LayoutDashboard },
  { to: "/market", label: "سوق البكجات", icon: Store },
  { to: "/packages", label: "بكجاتي (بائع)", icon: Package },
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
  { to: "/admin/finance", label: "المركز المالي", icon: Banknote },
  { to: "/admin/offices", label: "إدارة المكاتب", icon: Users },
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

  const doLogout = async () => { await logout(); navigate("/login"); };

  return (
    <div className="min-h-screen bg-[#F4F6F8]">
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
        className={`w-72 bg-[#0A2540] text-white flex flex-col fixed top-0 bottom-0 start-0 z-40 transition-transform duration-300 ${
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

        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
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
