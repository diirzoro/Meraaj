import { useEffect } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Layout, { PublicLayout } from "@/components/Layout";
import NativeBridge from "@/native/NativeBridge";

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
import AdminFinance from "@/pages/admin/AdminFinance";
import AdminOffices from "@/pages/admin/AdminOffices";
import AdminDisputes from "@/pages/admin/AdminDisputes";

function Loader() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F4F6F8]">
      <div className="w-10 h-10 border-4 border-[#0A2540] border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

function Protected({ role, children }) {
  const { user, loading } = useAuth();
  if (loading || user === null) return <Loader />;
  if (!user) return <Navigate to="/login" replace />;
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
      <Route path="/" element={<Landing />} />
      <Route path="/embed/market" element={<EmbedMarket />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route path="/dashboard" element={<Protected role="member"><Dashboard /></Protected>} />
      <Route path="/market" element={<PublicOrMember><Market /></PublicOrMember>} />
      <Route path="/market/:id" element={<PublicOrMember><PackageDetail /></PublicOrMember>} />
      <Route path="/packages" element={<Protected role="office"><MyPackages /></Protected>} />
      <Route path="/packages/new" element={<Protected role="office"><CreatePackage /></Protected>} />
      <Route path="/bookings" element={<Protected role="member"><Bookings /></Protected>} />
      <Route path="/sales" element={<Protected role="office"><Sales /></Protected>} />
      <Route path="/wallet" element={<Protected role="member"><WalletPage /></Protected>} />
      <Route path="/marketer" element={<Protected role="individual"><Marketer /></Protected>} />

      <Route path="/admin" element={<Protected role="admin"><AdminDashboard /></Protected>} />
      <Route path="/admin/finance" element={<Protected role="admin"><AdminFinance /></Protected>} />
      <Route path="/admin/offices" element={<Protected role="admin"><AdminOffices /></Protected>} />
      <Route path="/admin/disputes" element={<Protected role="admin"><AdminDisputes /></Protected>} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <NativeBridge />
        <AppRoutes />
        <Toaster position="top-center" richColors dir="rtl" />
      </BrowserRouter>
    </AuthProvider>
  );
}
