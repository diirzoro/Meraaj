import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/Layout";
import { money } from "@/lib/format";
import StatusBadge from "@/components/StatusBadge";
import { Wallet, Clock, CheckCircle2, Store, Package, ShoppingBag, ArrowLeft } from "lucide-react";

function WalletCard({ title, value, icon: Icon, tone }) {
  const tones = {
    gold: "from-[#0A2540] to-[#0A2540] text-white",
    pending: "bg-white",
    available: "bg-white",
  };
  const isGold = tone === "gold";
  return (
    <div data-testid={`wallet-card-${tone}`}
         className={`rounded-2xl border p-6 card-shadow ${isGold ? "bg-[#0A2540] text-white border-[#0A2540]" : "bg-white"}`}>
      <div className="flex items-center justify-between mb-4">
        <span className={`text-sm ${isGold ? "text-white/70" : "text-muted-foreground"}`}>{title}</span>
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${isGold ? "bg-[#D4AF37]" : "bg-[#F4F6F8]"}`}>
          <Icon className={`w-4 h-4 ${isGold ? "text-[#0A2540]" : "text-[#0A2540]"}`} />
        </div>
      </div>
      <div className={`tabular text-3xl font-bold ${isGold ? "text-[#D4AF37]" : "text-[#0A2540]"}`}>{value}</div>
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const [wallet, setWallet] = useState({ total: 0, pending: 0, available: 0 });
  const [recent, setRecent] = useState([]);

  useEffect(() => {
    api.get("/wallet").then((r) => setWallet(r.data)).catch(() => {});
    api.get("/bookings?role=buyer").then((r) => setRecent(r.data.slice(0, 5))).catch(() => {});
  }, []);

  return (
    <>
      <PageHeader title={`أهلاً، ${user?.office_name}`} subtitle="نظرة عامة على محفظتك ونشاطك في السوق" />

      <div className="grid md:grid-cols-3 gap-5 mb-8">
        <WalletCard title="الرصيد الإجمالي" value={money(wallet.total)} icon={Wallet} tone="gold" />
        <WalletCard title="الرصيد المعلق (ضمان)" value={money(wallet.pending)} icon={Clock} tone="pending" />
        <WalletCard title="الرصيد المتاح" value={money(wallet.available)} icon={CheckCircle2} tone="available" />
      </div>

      <div className="grid sm:grid-cols-3 gap-5 mb-8">
        {[
          { to: "/market", label: "تصفّح السوق", icon: Store },
          { to: "/packages/new", label: "أضف باكج للبيع", icon: Package },
          { to: "/wallet", label: "اشحن المحفظة", icon: ShoppingBag },
        ].map((a) => (
          <Link key={a.to} to={a.to} data-testid={`quick-${a.to.replace(/\//g, "")}`}
                className="hover-lift bg-white rounded-2xl border p-5 flex items-center gap-4 card-shadow">
            <div className="w-11 h-11 rounded-xl bg-[#F4F6F8] flex items-center justify-center">
              <a.icon className="w-5 h-5 text-[#0A2540]" />
            </div>
            <div className="flex-1 font-semibold text-[#0A2540]">{a.label}</div>
            <ArrowLeft className="w-4 h-4 text-muted-foreground" />
          </Link>
        ))}
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-hidden">
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <h3 className="font-head font-bold text-[#0A2540]">أحدث حجوزاتي</h3>
          <Link to="/bookings" className="text-sm text-[#0A2540] hover:underline">عرض الكل</Link>
        </div>
        {recent.length === 0 ? (
          <div className="p-10 text-center text-muted-foreground text-sm">لا توجد حجوزات بعد</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-muted-foreground text-xs">
              <tr className="border-b">
                <th className="text-start px-6 py-3 font-medium">الباكج</th>
                <th className="text-start px-6 py-3 font-medium">المقاعد</th>
                <th className="text-start px-6 py-3 font-medium">المبلغ</th>
                <th className="text-start px-6 py-3 font-medium">الحالة</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((b) => (
                <tr key={b.id} className="border-b last:border-0">
                  <td className="px-6 py-3 font-medium">{b.package_title}</td>
                  <td className="px-6 py-3 tabular">{b.seats}</td>
                  <td className="px-6 py-3 tabular">{money(b.amount_charged, b.currency)}</td>
                  <td className="px-6 py-3"><StatusBadge status={b.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
