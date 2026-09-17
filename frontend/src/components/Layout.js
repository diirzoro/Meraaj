import { useState, useRef } from "react";
import { NavLink, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  LayoutDashboard, Store, Package, ShoppingBag, TicketCheck, Wallet,
  Banknote, ShieldAlert, LogOut, Building2, Network, Menu, X, TrendingUp, Ban,
  Database, Eraser, ChevronDown, Calculator, ReceiptText, NotebookPen, Scale,
  Coins, CalendarClock, GitCompare, ShieldCheck,
  BookOpen, ArrowDownCircle, Percent, Gauge, Bell, FileSpreadsheet, Settings2, Megaphone,
} from "lucide-react";

/** NAVIGATION MODEL — `items` are leaves, `group` entries are collapsible parents.
 *  A group is rendered ONLY if at least one of its children is visible to the user, and every
 *  child carries its OWN permission (never one broad accounting.* grant). Hiding a link is
 *  convenience only: every route and API re-checks the same permission in the backend. */

const ACCOUNTING_GROUP = {
  group: "accounting", label: "الحسابات", icon: Calculator, children: [
    { to: "/accounting/chart", label: "الدليل المحاسبي", icon: BookOpen, perm: "accounting.accounts.view" },
    { to: "/accounting/vouchers", label: "السندات", icon: ReceiptText, perm: "accounting.vouchers.view" },
    { to: "/accounting/journals", label: "القيود اليومية", icon: NotebookPen, perm: "accounting.journals.view" },
    { to: "/accounting/ledger", label: "الأستاذ وكشف الحساب", icon: Scale, perm: "accounting.ledger.view" },
    { to: "/accounting/currencies", label: "العملات والمصارفة", icon: Coins, perm: "accounting.currency.view" },
    { to: "/accounting/periods", label: "الفترات والإقفال", icon: CalendarClock, perm: "accounting.periods.view" },
    { to: "/accounting/links", label: "ربط الحسابات", icon: Network, perm: "accounting.links.view" },
    { to: "/accounting/reconciliation", label: "المطابقة المحاسبية", icon: GitCompare, perm: "accounting.reconciliation.view" },
    { to: "/accounting/self-audit", label: "التدقيق الذاتي", icon: ShieldCheck, perm: "accounting.selfaudit.run" },
  ],
};

const officeNav = [
  { to: "/dashboard", label: "الرئيسية", icon: LayoutDashboard },
  { to: "/market", label: "سوق البرامج", icon: Store },
  { group: "office-business", label: "أعمالي", icon: Package, children: [
    { to: "/packages", label: "برامجي (بائع)", icon: Package },
    { to: "/sales", label: "مبيعاتي", icon: TicketCheck },
    { to: "/bookings", label: "حجوزاتي (مشتري)", icon: ShoppingBag },
    { to: "/my-ads", label: "إعلاناتي وعروضي", icon: Megaphone, perm: "ads.view" },
  ] },
  { group: "office-money", label: "الحساب المالي", icon: Banknote, children: [
    { to: "/wallet", label: "المحفظة", icon: Wallet },
    { to: "/office-statement", label: "كشف حساب المكتب", icon: FileSpreadsheet },
  ] },
  ACCOUNTING_GROUP,
  { group: "office-reports", label: "التقارير", icon: FileSpreadsheet, children: [
    { to: "/accounting/reports", label: "التقارير المالية", icon: Scale, perm: "accounting.reports.view" },
  ] },
];

const individualNav = [
  { to: "/dashboard", label: "الرئيسية", icon: LayoutDashboard },
  { to: "/market", label: "البحث عن رحلات", icon: Store },
  { to: "/bookings", label: "حجوزاتي", icon: ShoppingBag },
  { to: "/wallet", label: "المحفظة", icon: Wallet },
  { to: "/marketer", label: "التسويق بالعمولة", icon: TrendingUp },
];

const adminNav = [
  { to: "/admin", label: "الرئيسية", icon: LayoutDashboard },
  { group: "operations", label: "العمليات", icon: ShoppingBag, children: [
    { to: "/admin/orders", label: "مركز الطلبات", icon: ShoppingBag },
    { to: "/admin/programs", label: "البرامج والمقاعد", icon: Package },
    { to: "/admin/travelers", label: "المسافرون والمستندات", icon: TicketCheck },
    { to: "/admin/withdrawals", label: "دورة السحوبات", icon: ArrowDownCircle },
    { to: "/admin/cancellations", label: "طلبات الإلغاء", icon: Ban },
    { to: "/admin/disputes", label: "النزاعات", icon: ShieldAlert },
  ] },
  { group: "business-finance", label: "المالية التجارية", icon: Banknote, children: [
    { to: "/admin/finance", label: "المركز المالي", icon: Banknote },
    { to: "/admin/ledger", label: "الدفتر المالي (تجاري)", icon: BookOpen },
    { to: "/admin/commissions", label: "محرك العمولات", icon: Percent },
    { to: "/admin/credit", label: "السقف الائتماني", icon: Gauge },
    { to: "/office-statement", label: "كشف حساب المكتب", icon: FileSpreadsheet },
  ] },
  ACCOUNTING_GROUP,
  { group: "reports", label: "التقارير", icon: FileSpreadsheet, children: [
    { to: "/accounting/reports", label: "التقارير المالية", icon: Scale, perm: "accounting.reports.view" },
    { to: "/admin/reports", label: "التقارير التشغيلية", icon: FileSpreadsheet },
  ] },
  { group: "org-management", label: "إدارة المكاتب والمنظمات", icon: Building2, children: [
    { to: "/admin/orgs", label: "المؤسسات والمكاتب", icon: Building2 },
  ] },
  { group: "marketing", label: "التسويق", icon: Megaphone, children: [
    { to: "/admin/ads", label: "الإعلانات والعروض", icon: Megaphone, perm: "ads.view" },
  ] },
  { group: "system", label: "النظام والإدارة", icon: Settings2, children: [
    { to: "/admin/roles", label: "الصلاحيات والأمان", icon: ShieldAlert },
    { to: "/admin/system", label: "إعدادات النظام", icon: Settings2 },
    { to: "/admin/integrations", label: "صحة التكامل", icon: Network },
    { to: "/admin/notifications", label: "الإشعارات والمهام", icon: Bell },
    { to: "/admin/backups", label: "النسخ الاحتياطي", icon: Database },
    { to: "/admin/maintenance", label: "الصيانة والاحتفاظ", icon: Eraser },
  ] },
];

function navFor(role) {
  if (role === "super_admin") return adminNav;
  if (role === "individual") return individualNav;
  return officeNav;
}

/** Keep only entries the user may actually open; drop groups that end up empty. */
function visibleNav(role, can) {
  return navFor(role).reduce((acc, item) => {
    if (!item.group) {
      if (!item.perm || can(item.perm)) acc.push(item);
      return acc;
    }
    const children = item.children.filter((c) => !c.perm || can(c.perm));
    if (children.length) acc.push({ ...item, children });
    return acc;
  }, []);
}

const GROUP_STATE_KEY = "meraaj_nav_groups";

function NavLeaf({ item, depth = 0, onNavigate }) {
  return (
    <NavLink
      to={item.to} end={item.to === "/admin"} onClick={onNavigate}
      data-testid={`nav-${item.to.replace(/\//g, "") || "home"}`}
      className={({ isActive }) =>
        `sidebar-link flex items-center gap-3 py-2.5 rounded-lg text-sm font-medium ${
          depth ? "ps-9 pe-4" : "px-4 py-3"
        } ${isActive ? "bg-white/10 text-white" : "text-white/60 hover:bg-white/5 hover:text-white"}`
      }
    >
      <item.icon className="w-[18px] h-[18px] shrink-0" />
      <span className="truncate">{item.label}</span>
    </NavLink>
  );
}

function NavGroup({ item, openGroups, toggle, onNavigate }) {
  const { pathname } = useLocation();
  const hasActive = item.children.some((c) => pathname === c.to || pathname.startsWith(`${c.to}/`));
  const open = openGroups[item.group] ?? hasActive;   // an active child auto-opens its parent
  return (
    <div data-testid={`nav-group-${item.group}`}>
      <button
        onClick={() => toggle(item.group, !open)}
        data-testid={`nav-group-toggle-${item.group}`}
        aria-expanded={open}
        className={`w-full sidebar-link flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-semibold ${
          hasActive ? "text-white" : "text-white/70 hover:bg-white/5 hover:text-white"
        }`}
      >
        <item.icon className="w-[18px] h-[18px] shrink-0" />
        <span className="flex-1 text-start truncate">{item.label}</span>
        <ChevronDown className={`w-4 h-4 transition-transform ${open ? "" : "-rotate-90 rtl:rotate-90"}`} />
      </button>
      {open && (
        <div className="mt-1 space-y-1 border-s border-white/10 ms-5" data-testid={`nav-group-children-${item.group}`}>
          {item.children.map((c) => <NavLeaf key={c.to} item={c} depth={1} onNavigate={onNavigate} />)}
        </div>
      )}
    </div>
  );
}

export default function Layout({ children }) {
  const { user, logout, can } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const nav = visibleNav(user?.role, can);
  // Multiple groups may stay open; the choice survives navigation and reloads.
  const [openGroups, setOpenGroups] = useState(() => {
    try { return JSON.parse(localStorage.getItem(GROUP_STATE_KEY) || "{}"); } catch { return {}; }
  });
  const toggleGroup = (key, value) => {
    setOpenGroups((prev) => {
      const next = { ...prev, [key]: value };
      localStorage.setItem(GROUP_STATE_KEY, JSON.stringify(next));
      return next;
    });
  };

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
          {nav.map((item) => (item.group
            ? <NavGroup key={item.group} item={item} openGroups={openGroups}
                        toggle={toggleGroup} onNavigate={() => setOpen(false)} />
            : <NavLeaf key={item.to} item={item} onNavigate={() => setOpen(false)} />))}
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
