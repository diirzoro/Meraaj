import { useEffect } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Layout, { PublicLayout } from "@/components/Layout";
import NativeBridge from "@/native/NativeBridge";
import SessionManager from "@/components/SessionManager";

import Login from "@/pages/Login";
import Register from "@/pages/Register";
import LandingPage from "@/pages/Landing";
import Dashboard from "@/pages/Dashboard";
import Market from "@/pages/Market";
import PackageDetail from "@/pages/PackageDetail";
import MyPackages from "@/pages/MyPackages";
import CreatePackage from "@/pages/CreatePackage";
import Bookings from "@/pages/Bookings";
import Sales from "@/pages/Sales";
import WalletPage from "@/pages/Wallet";
import Marketer from "@/pages/Marketer";
import EmbedMarket from "@/pages/EmbedMarket";
import AdminDashboard from "@/pages/admin/AdminDashboard";
import AdminOrders from "@/pages/admin/AdminOrders";
import AdminOrderDetail from "@/pages/admin/AdminOrderDetail";
import AdminLedger from "@/pages/admin/AdminLedger";
import AdminWithdrawals from "@/pages/admin/AdminWithdrawals";
import AdminCommissions from "@/pages/admin/AdminCommissions";
import AdminCredit from "@/pages/admin/AdminCredit";
import AdminPrograms from "@/pages/admin/AdminPrograms";
import AdminTravelers from "@/pages/admin/AdminTravelers";
import AdminIntegrations from "@/pages/admin/AdminIntegrations";
import AdminOrgs from "@/pages/admin/AdminOrgs";
import AdminBackups from "@/pages/admin/AdminBackups";
import AdminMaintenance from "@/pages/admin/AdminMaintenance";
import AdminRoles from "@/pages/admin/AdminRoles";
import AdminNotifications from "@/pages/admin/AdminNotifications";
import AdminReports from "@/pages/admin/AdminReports";
import AdminSystem from "@/pages/admin/AdminSystem";
import AdminFinance from "@/pages/admin/AdminFinance";
import AdminCancellations from "@/pages/admin/AdminCancellations";
import MyAds from "@/pages/MyAds";
import AdminAds from "@/pages/admin/AdminAds";
import AdminDisputes from "@/pages/admin/AdminDisputes";
import AccChart from "@/pages/accounting/AccChart";
import AccVouchers from "@/pages/accounting/AccVouchers";
import AccJournals from "@/pages/accounting/AccJournals";
import AccLedger from "@/pages/accounting/AccLedger";
import AccPeriods from "@/pages/accounting/AccPeriods";
import AccCurrencies from "@/pages/accounting/AccCurrencies";
import AccReports from "@/pages/accounting/AccReports";
import AccLinks from "@/pages/accounting/AccLinks";
import AccReconciliation from "@/pages/accounting/AccReconciliation";
import AccSelfAudit from "@/pages/accounting/AccSelfAudit";
import OfficeStatement from "@/pages/OfficeStatement";

import { MobileShellProvider, useShell } from "@/mobile/MobileShell";
import MobileLayout from "@/mobile/MobileLayout";
import MAdminHome from "@/mobile/screens/MAdminHome";
import MAccountingHub, { AccountingGate } from "@/mobile/screens/MAccountingHub";
import MAccChart from "@/mobile/screens/MAccChart";
import MAccVouchers from "@/mobile/screens/MAccVouchers";
import MAccJournals from "@/mobile/screens/MAccJournals";
import MAccLedger from "@/mobile/screens/MAccLedger";
import MAccReports from "@/mobile/screens/MAccReports";
import MAccPeriods from "@/mobile/screens/MAccPeriods";
import MAccAudit from "@/mobile/screens/MAccAudit";
import MAdminOrders from "@/mobile/screens/MAdminOrders";
import MAdminTopups from "@/mobile/screens/MAdminTopups";
import MSplash from "@/mobile/screens/MSplash";
import MLogin from "@/mobile/screens/MLogin";
import MRegister from "@/mobile/screens/MRegister";
import MForgot from "@/mobile/screens/MForgot";
import MHome from "@/mobile/screens/MHome";
import MPrograms from "@/mobile/screens/MPrograms";
import MProgramDetail from "@/mobile/screens/MProgramDetail";
import MBookingFlow from "@/mobile/screens/MBookingFlow";
import MBookings from "@/mobile/screens/MBookings";
import MBookingDetail from "@/mobile/screens/MBookingDetail";
import MWallet from "@/mobile/screens/MWallet";
import MTopup from "@/mobile/screens/MTopup";
import MNotifications from "@/mobile/screens/MNotifications";
import MAccount from "@/mobile/screens/MAccount";
import MTickets from "@/mobile/screens/MTickets";
import MStatement from "@/mobile/screens/MStatement";
import MSales from "@/mobile/screens/MSales";

function Loader() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F4F6F8]">
      <div className="w-10 h-10 border-4 border-[#0A2540] border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

function Protected({ role, perm, children }) {
  const { user, loading, permissions, can } = useAuth();
  if (loading || user === null) return <Loader />;
  if (!user) return <Navigate to="/login" replace />;
  if (perm && permissions.length === 0) return <Loader />;
  if (perm && !can(perm)) return <Navigate to={user.role === "super_admin" ? "/admin" : "/dashboard"} replace />;
  // `role` omitted => permission-only route: any authenticated role holding the permission
  // may open it (accounting employees are office/staff accounts, not super admins).
  if (!role) return <Layout>{children}</Layout>;
  if (user.role === "super_admin" && role !== "admin") return <Navigate to="/admin" replace />;
  if (role === "admin" && user.role !== "super_admin") return <Navigate to="/dashboard" replace />;
  if (role === "office" && user.role !== "office") return <Navigate to="/dashboard" replace />;
  if (role === "individual" && user.role !== "individual") return <Navigate to="/dashboard" replace />;
  if (role === "member" && !["office", "individual"].includes(user.role)) return <Navigate to="/dashboard" replace />;
  return <Layout>{children}</Layout>;
}

function Landing() {
  const { user } = useAuth();
  if (user) return <Navigate to={user.role === "super_admin" ? "/admin" : "/dashboard"} replace />;
  return <LandingPage />;
}

const IS_NATIVE = typeof window !== "undefined"
  && (window.Capacitor?.isNativePlatform?.() || window.location.protocol === "capacitor:");

/** Auth + shell gate for the mobile app. Admin accounts get the ADMIN MOBILE EXPERIENCE
 *  (same auth, same RBAC) — they are no longer redirected to the web dashboard. */
function MobileGuard() {
  const { user, loading } = useAuth();
  if (loading || user === null) return <Loader />;
  if (!user) return <Navigate to="/m/login" replace />;
  return (
    <MobileShellProvider>
      <MobileLayout />
    </MobileShellProvider>
  );
}

/** Home is experience-aware: the backend decides which experience the identity gets. */
function MobileHome() {
  const { shell, loading } = useShell();
  if (loading && !shell) return <Loader />;
  return shell?.experience === "admin" ? <MAdminHome /> : <MHome />;
}

/** On a native install the root opens the APP shell, never the website. */
function RootEntry() {
  if (IS_NATIVE) return <Navigate to="/m" replace />;
  return <Landing />;
}

// Public pages that logged-in members also use: show the app Layout when authenticated,
// otherwise a lightweight public shell (browse market/details without logging in).
function PublicOrMember({ children }) {
  const { user, loading } = useAuth();
  if (loading || user === null) return <Loader />;
  return user ? <Layout>{children}</Layout> : <PublicLayout>{children}</PublicLayout>;
}

function AppRoutes() {
  return (
    <Routes>
      {/* ---------------- MOBILE APP (native shell — no dashboard chrome) ---------------- */}
      <Route path="/m" element={<MSplash />} />
      <Route path="/m/login" element={<MLogin />} />
      <Route path="/m/register" element={<MRegister />} />
      <Route path="/m/forgot" element={<MForgot />} />
      <Route element={<MobileGuard />}>
        <Route path="/m/home" element={<MobileHome />} />
        <Route path="/m/accounting" element={<AccountingGate><MAccountingHub /></AccountingGate>} />
        <Route path="/m/accounting/chart" element={<AccountingGate capability="chart_view"><MAccChart /></AccountingGate>} />
        <Route path="/m/accounting/vouchers" element={<AccountingGate capability="vouchers_view"><MAccVouchers /></AccountingGate>} />
        <Route path="/m/accounting/journals" element={<AccountingGate capability="journals_view"><MAccJournals /></AccountingGate>} />
        <Route path="/m/accounting/ledger" element={<AccountingGate capability="ledger_view"><MAccLedger /></AccountingGate>} />
        <Route path="/m/accounting/reports" element={<AccountingGate capability="reports_view"><MAccReports /></AccountingGate>} />
        <Route path="/m/accounting/periods" element={<AccountingGate capability="periods_view"><MAccPeriods /></AccountingGate>} />
        <Route path="/m/accounting/audit" element={<AccountingGate capability="reconciliation_view"><MAccAudit /></AccountingGate>} />
        <Route path="/m/admin/operations" element={<MAdminOrders />} />
        <Route path="/m/admin/orders" element={<MAdminOrders />} />
        <Route path="/m/admin/topups" element={<MAdminTopups />} />
        <Route path="/m/programs" element={<MPrograms />} />
        <Route path="/m/programs/:id" element={<MProgramDetail />} />
        <Route path="/m/programs/:id/book" element={<MBookingFlow />} />
        <Route path="/m/bookings" element={<MBookings />} />
        <Route path="/m/bookings/:id" element={<MBookingDetail />} />
        <Route path="/m/wallet" element={<MWallet />} />
        <Route path="/m/wallet/topup" element={<MTopup />} />
        <Route path="/m/notifications" element={<MNotifications />} />
        <Route path="/m/account" element={<MAccount />} />
        <Route path="/m/tickets" element={<MTickets />} />
        <Route path="/m/statement" element={<MStatement />} />
        <Route path="/m/sales" element={<MSales />} />
      </Route>
      <Route path="/" element={<RootEntry />} />
      <Route path="/embed/market" element={<EmbedMarket />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route path="/dashboard" element={<Protected role="member"><Dashboard /></Protected>} />
      <Route path="/market" element={<PublicOrMember><Market /></PublicOrMember>} />
      <Route path="/market/:id" element={<PublicOrMember><PackageDetail /></PublicOrMember>} />
      <Route path="/packages" element={<Protected role="office"><MyPackages /></Protected>} />
      <Route path="/packages/new" element={<Protected role="office"><CreatePackage /></Protected>} />
      <Route path="/packages/:id/edit" element={<Protected role="office"><CreatePackage /></Protected>} />
      <Route path="/bookings" element={<Protected role="member"><Bookings /></Protected>} />
      <Route path="/sales" element={<Protected role="office"><Sales /></Protected>} />
      <Route path="/wallet" element={<Protected role="member"><WalletPage /></Protected>} />
      <Route path="/my-ads" element={<Protected role="member" perm="ads.view"><MyAds /></Protected>} />
      <Route path="/marketer" element={<Protected role="individual"><Marketer /></Protected>} />

      <Route path="/admin" element={<Protected role="admin"><AdminDashboard /></Protected>} />
      <Route path="/admin/orders" element={<Protected role="admin"><AdminOrders /></Protected>} />
      <Route path="/admin/orders/:id" element={<Protected role="admin"><AdminOrderDetail /></Protected>} />
      <Route path="/admin/ledger" element={<Protected role="admin"><AdminLedger /></Protected>} />
      <Route path="/admin/withdrawals" element={<Protected role="admin"><AdminWithdrawals /></Protected>} />
      <Route path="/admin/commissions" element={<Protected role="admin"><AdminCommissions /></Protected>} />
      <Route path="/admin/credit" element={<Protected role="admin"><AdminCredit /></Protected>} />
      <Route path="/admin/programs" element={<Protected role="admin"><AdminPrograms /></Protected>} />
      <Route path="/admin/travelers" element={<Protected role="admin"><AdminTravelers /></Protected>} />
      <Route path="/admin/integrations" element={<Protected role="admin"><AdminIntegrations /></Protected>} />
      <Route path="/admin/orgs" element={<Protected role="admin"><AdminOrgs /></Protected>} />
      <Route path="/admin/roles" element={<Protected role="admin"><AdminRoles /></Protected>} />
      <Route path="/admin/notifications" element={<Protected role="admin"><AdminNotifications /></Protected>} />
      <Route path="/admin/reports" element={<Protected role="admin"><AdminReports /></Protected>} />
      <Route path="/admin/system" element={<Protected role="admin"><AdminSystem /></Protected>} />
      <Route path="/admin/backups" element={<Protected role="admin"><AdminBackups /></Protected>} />
      <Route path="/admin/maintenance" element={<Protected role="admin"><AdminMaintenance /></Protected>} />
      <Route path="/admin/finance" element={<Protected role="admin"><AdminFinance /></Protected>} />
      {/* Unified into /admin/orgs — old route kept as a backward-compatible redirect
          until every function is manually confirmed as transferred. */}
      <Route path="/admin/offices" element={<Navigate to="/admin/orgs" replace />} />
      <Route path="/admin/cancellations" element={<Protected role="admin"><AdminCancellations /></Protected>} />
      <Route path="/admin/ads" element={<Protected role="admin" perm="ads.view"><AdminAds /></Protected>} />
      <Route path="/admin/disputes" element={<Protected role="admin"><AdminDisputes /></Protected>} />

      {/* ---- الحسابات (permission-only routes: enforced again in the backend) ---- */}
      <Route path="/accounting/chart" element={<Protected perm="accounting.accounts.view"><AccChart /></Protected>} />
      <Route path="/accounting/vouchers" element={<Protected perm="accounting.vouchers.view"><AccVouchers /></Protected>} />
      <Route path="/accounting/journals" element={<Protected perm="accounting.journals.view"><AccJournals /></Protected>} />
      <Route path="/accounting/ledger" element={<Protected perm="accounting.ledger.view"><AccLedger /></Protected>} />
      <Route path="/accounting/periods" element={<Protected perm="accounting.periods.view"><AccPeriods /></Protected>} />
      <Route path="/accounting/currencies" element={<Protected perm="accounting.currency.view"><AccCurrencies /></Protected>} />
      <Route path="/accounting/links" element={<Protected perm="accounting.links.view"><AccLinks /></Protected>} />
      <Route path="/accounting/reports" element={<Protected perm="accounting.reports.view"><AccReports /></Protected>} />
      <Route path="/accounting/reconciliation" element={<Protected perm="accounting.reconciliation.view"><AccReconciliation /></Protected>} />
      <Route path="/accounting/self-audit" element={<Protected perm="accounting.selfaudit.run"><AccSelfAudit /></Protected>} />
      <Route path="/office-statement" element={<Protected><OfficeStatement /></Protected>} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <NativeBridge />
        <SessionManager />
        <AppRoutes />
        <Toaster position="top-center" richColors dir="rtl" />
      </BrowserRouter>
    </AuthProvider>
  );
}
