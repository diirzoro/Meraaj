import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money } from "@/lib/format";
import { Wallet, Clock, Building2, Package, ShoppingBag, ArrowUpCircle, ArrowLeftRight, ArrowDownCircle, ShieldAlert, TrendingUp, User } from "lucide-react";
import { Link } from "react-router-dom";

export default function AdminDashboard() {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/admin/dashboard").then((r) => setD(r.data)); }, []);
  if (!d) return <div className="text-center py-20 text-muted-foreground">جارٍ التحميل...</div>;

  return (
    <>
      <PageHeader title="لوحة المؤشرات المركزية" subtitle="Target Media — مراقبة السيولة والعمليات" />

      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-5 mb-6">
        <Big title="إجمالي السيولة في النظام" value={money(d.total_system_balance)} icon={Wallet} gold />
        <Big title="أرباح المنصة (Target Media)" value={money(d.platform_revenue)} icon={TrendingUp} />
        <Big title="إجمالي المتاح" value={money(d.total_available)} icon={ArrowUpCircle} />
        <Big title="إجمالي المعلّق (ضمان)" value={money(d.total_pending)} icon={Clock} />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-5 mb-8">
        <Small title="المكاتب" value={d.offices_count} icon={Building2} />
        <Small title="عدد الأفراد" value={d.individuals_count} icon={User} />
        <Small title="المسوّقون" value={d.marketers_count} icon={TrendingUp} />
        <Small title="البرامج" value={d.packages_count} icon={Package} />
        <Small title="الحجوزات" value={d.bookings_count} icon={ShoppingBag} />
      </div>

      <h3 className="font-head font-bold text-[#0A2540] mb-4">بانتظار الاعتماد</h3>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <Action to="/admin/finance" title="طلبات الشحن" count={d.pending_topups} icon={ArrowUpCircle} />
        <Action to="/admin/finance" title="تحويلات P2P" count={d.pending_transfers} icon={ArrowLeftRight} />
        <Action to="/admin/finance" title="طلبات السحب" count={d.pending_withdrawals} icon={ArrowDownCircle} />
        <Action to="/admin/disputes" title="نزاعات مفتوحة" count={d.open_disputes} icon={ShieldAlert} danger />
      </div>
    </>
  );
}

const Big = ({ title, value, icon: Icon, gold }) => (
  <div className={`rounded-2xl border p-6 card-shadow ${gold ? "bg-[#0A2540] text-white border-[#0A2540]" : "bg-white"}`} data-testid={`admin-stat-${title}`}>
    <div className="flex items-center justify-between mb-4">
      <span className={`text-sm ${gold ? "text-white/70" : "text-muted-foreground"}`}>{title}</span>
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${gold ? "bg-[#D4AF37]" : "bg-[#F4F6F8]"}`}><Icon className="w-4 h-4 text-[#0A2540]" /></div>
    </div>
    <div className={`tabular text-2xl sm:text-3xl font-bold whitespace-nowrap ${gold ? "text-[#D4AF37]" : "text-[#0A2540]"}`}>{value}</div>
  </div>
);

const Small = ({ title, value, icon: Icon }) => (
  <div className="bg-white rounded-2xl border p-5 card-shadow flex items-center gap-4">
    <div className="w-11 h-11 rounded-xl bg-[#F4F6F8] flex items-center justify-center"><Icon className="w-5 h-5 text-[#0A2540]" /></div>
    <div><div className="tabular text-2xl font-bold text-[#0A2540]">{value}</div><div className="text-xs text-muted-foreground">{title}</div></div>
  </div>
);

const Action = ({ to, title, count, icon: Icon, danger }) => (
  <Link to={to} className="hover-lift bg-white rounded-2xl border p-5 card-shadow block" data-testid={`admin-action-${title}`}>
    <div className="flex items-center justify-between mb-3">
      <Icon className={`w-5 h-5 ${danger ? "text-red-500" : "text-[#0A2540]"}`} />
      {count > 0 && <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${danger ? "bg-red-50 text-red-600" : "bg-[#FEFCE8] text-[#A16207]"}`}>{count}</span>}
    </div>
    <div className="font-semibold text-[#0A2540] text-sm">{title}</div>
  </Link>
);
