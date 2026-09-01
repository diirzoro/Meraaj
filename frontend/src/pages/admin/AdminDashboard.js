import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money } from "@/lib/format";
import { Link, useNavigate } from "react-router-dom";
import {
  Building2, Package, ShoppingBag, ArrowUpCircle, ArrowLeftRight,
  ArrowDownCircle, ShieldAlert, TrendingUp, User, AlertTriangle, Ban,
  Clock, PlugZap, ListChecks, RefreshCw,
} from "lucide-react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";

const PERIODS = [
  ["day", "اليوم"], ["week", "أسبوعي"], ["month", "شهري"], ["year", "سنوي"],
];

export default function AdminDashboard() {
  const nav = useNavigate();
  const [period, setPeriod] = useState("month");
  const [currency, setCurrency] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [d, setD] = useState(null);
  const [queue, setQueue] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = () => {
    setBusy(true);
    const p = new URLSearchParams({ period });
    if (currency) p.set("currency", currency);
    if (from && to) { p.set("date_from", from); p.set("date_to", to); }
    Promise.all([
      api.get(`/admin/analytics?${p.toString()}`),
      api.get("/admin/attention?limit=8"),
    ]).then(([a, q]) => { setD(a.data); setQueue(q.data); }).finally(() => setBusy(false));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [period, currency, from, to]);

  const ccys = currency ? [currency] : ["SAR", "USD"];
  const series = useMemo(() => (d?.series || []).map((s) => ({
    name: s.bucket, gross: s.gross, revenue: s.revenue, bookings: s.bookings,
  })), [d]);

  const goOrders = (qs) => nav(`/admin/orders${qs ? `?${qs}` : ""}`);

  if (!d) return <div className="text-center py-20 text-muted-foreground" data-testid="admin-dash-loading">جارٍ تحميل لوحة القيادة...</div>;

  const s = d.sales, at = d.attention;
  const growth = (c) => {
    const prev = d.comparison?.previous_gross?.[c] || 0;
    const cur = s.gross?.[c] || 0;
    if (!prev) return cur ? 100 : 0;
    return Math.round(((cur - prev) / prev) * 100);
  };

  return (
    <>
      <PageHeader title="لوحة القيادة التنفيذية" subtitle="Target Media — مؤشرات حقيقية قابلة للفلترة والضغط للوصول إلى التفاصيل" />

      {/* Filters */}
      <div className="bg-white rounded-2xl border card-shadow p-4 mb-6 flex flex-wrap items-end gap-3" data-testid="dash-filters">
        <div className="flex rounded-lg border overflow-hidden">
          {PERIODS.map(([v, l]) => (
            <button key={v} onClick={() => { setPeriod(v); setFrom(""); setTo(""); }}
              data-testid={`period-${v}`}
              className={`px-3 h-9 text-xs font-semibold transition-colors ${period === v && !from ? "bg-[#0A2540] text-white" : "bg-white text-[#0A2540] hover:bg-[#F4F6F8]"}`}>
              {l}
            </button>
          ))}
        </div>
        <label className="text-xs text-muted-foreground">
          من
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} data-testid="dash-date-from"
            className="block h-9 rounded-md border border-input px-2 text-xs mt-1" />
        </label>
        <label className="text-xs text-muted-foreground">
          إلى
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} data-testid="dash-date-to"
            className="block h-9 rounded-md border border-input px-2 text-xs mt-1" />
        </label>
        <select value={currency} onChange={(e) => setCurrency(e.target.value)} data-testid="dash-currency"
          className="h-9 rounded-md border border-input px-2 text-xs">
          <option value="">كل العملات</option>
          <option value="SAR">ريال سعودي</option>
          <option value="USD">دولار أمريكي</option>
        </select>
        <button onClick={load} disabled={busy} data-testid="dash-refresh"
          className="h-9 px-3 rounded-md border text-xs font-semibold text-[#0A2540] hover:bg-[#F4F6F8] inline-flex items-center gap-1.5">
          <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} /> تحديث
        </button>
        <span className="text-[11px] text-muted-foreground mr-auto">
          الفترة: {d.range.from} ← {d.range.to} • {s.bookings_count} حجز
        </span>
      </div>

      {/* Risk alerts */}
      {d.alerts?.length > 0 && (
        <div className="bg-white rounded-2xl border card-shadow p-4 mb-6" data-testid="dash-alerts">
          <div className="flex items-center gap-2 mb-3 font-head font-bold text-[#0A2540] text-sm">
            <AlertTriangle className="w-4 h-4 text-[#B45309]" /> تنبيهات المخاطر والعمليات غير الطبيعية
          </div>
          <div className="space-y-2">
            {d.alerts.slice(0, 6).map((a, i) => (
              <div key={i} data-testid={`alert-${i}`}
                className={`text-xs rounded-lg px-3 py-2 border ${a.level === "critical" ? "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" : a.level === "warning" ? "bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]" : "bg-[#F4F6F8] text-[#0A2540]"}`}>
                {a.message}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sales & revenue per currency */}
      <div className="grid md:grid-cols-2 gap-5 mb-6">
        {ccys.map((c) => (
          <div key={c} data-testid={`sales-card-${c}`} className="rounded-2xl border card-shadow p-6 bg-white">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-semibold text-muted-foreground">
                {c === "SAR" ? "المبيعات — ريال سعودي" : "المبيعات — دولار أمريكي"}
              </span>
              <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${growth(c) >= 0 ? "bg-[#F0FDF4] text-[#15803D]" : "bg-[#FEF2F2] text-[#B91C1C]"}`}>
                {growth(c) >= 0 ? "▲" : "▼"} {Math.abs(growth(c))}%
              </span>
            </div>
            <button onClick={() => goOrders(`currency=${c}`)} className="text-right block w-full" data-testid={`gross-${c}`}>
              <div className="text-xs text-muted-foreground mb-1">إجمالي المبيعات</div>
              <div className="tabular text-3xl font-bold text-[#0A2540] hover:text-[#D4AF37] transition-colors">{money(s.gross[c], c)}</div>
            </button>
            <div className="grid grid-cols-2 gap-3 mt-4 pt-4 border-t text-xs">
              <Mini label="عمولة المنصة" value={money(s.platform_commission[c], c)} />
              <Mini label="صافي الأرباح" value={money(s.net_profit[c], c)} accent />
              <Mini label="مستحقات البائعين (معلّق)" value={money(d.escrow.pending[c], c)} />
              <Mini label="أموال محرّرة" value={money(d.escrow.released[c], c)} />
              <Mini label="مبالغ مستردة" value={money(d.escrow.refunded[c], c)} />
              <Mini label="الانكشاف (أرصدة سالبة)" value={money(d.exposure[c], c)} danger />
              <Mini label="سيولة متاحة" value={money(d.liquidity[c].available, c)} />
              <Mini label="طلبات سحب معلّقة" value={money(d.withdrawals.pending_amount[c], c)} />
            </div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid lg:grid-cols-2 gap-5 mb-6">
        <ChartCard title="حركة المبيعات وإيراد المنصة">
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={series}>
              <defs>
                <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0A2540" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#0A2540" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} reversed />
              <YAxis tick={{ fontSize: 10 }} orientation="right" />
              <Tooltip />
              <Area type="monotone" dataKey="gross" name="المبيعات" stroke="#0A2540" fill="url(#g1)" strokeWidth={2} />
              <Area type="monotone" dataKey="revenue" name="إيراد المنصة" stroke="#D4AF37" fill="none" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="عدد الحجوزات">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={series}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} reversed />
              <YAxis tick={{ fontSize: 10 }} orientation="right" allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="bookings" name="حجوزات" fill="#D4AF37" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Order states — clickable */}
      <h3 className="font-head font-bold text-[#0A2540] mb-3">حالات الطلبات (اضغط للتفاصيل)</h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
        <Tile title="حجوزات جديدة" value={d.bookings_by_status.blue || 0} onClick={() => goOrders("status=blue")} tid="tile-blue" />
        <Tile title="تم إصدار التأشيرة" value={d.bookings_by_status.yellow || 0} onClick={() => goOrders("status=yellow")} tid="tile-yellow" />
        <Tile title="تم التفويج" value={d.bookings_by_status.green || 0} onClick={() => goOrders("status=green")} tid="tile-green" />
        <Tile title="ملغاة" value={d.bookings_by_status.cancelled || 0} onClick={() => goOrders("status=cancelled")} tid="tile-cancelled" />
        <Tile title="بانتظار قبول البائع" value={d.bookings_by_approval.pending || 0} onClick={() => goOrders("approval_status=pending")} tid="tile-pending" />
        <Tile title="مرفوضة" value={d.bookings_by_approval.rejected || 0} onClick={() => goOrders("approval_status=rejected")} tid="tile-rejected" />
      </div>

      {/* Attention queue */}
      <h3 className="font-head font-bold text-[#0A2540] mb-3">طلبات متأخرة تحتاج تدخل الإدارة</h3>
      <div className="bg-white rounded-2xl border card-shadow overflow-hidden mb-8" data-testid="attention-queue">
        {queue.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">لا توجد طلبات تحتاج تدخلاً حالياً</div>
        ) : queue.map((b) => (
          <Link key={b.id} to={`/admin/orders/${b.id}`} data-testid={`attention-${b.id}`}
            className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 border-b last:border-0 hover:bg-[#F4F6F8]">
            <div className="min-w-0">
              <div className="font-semibold text-sm text-[#0A2540] truncate">{b.package_title}</div>
              <div className="text-[11px] text-muted-foreground">{b.buyer_office_name} ← {b.seller_office_name}</div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {b.attention_reasons.slice(0, 2).map((r, i) => (
                <span key={i} className={`text-[10px] px-2 py-0.5 rounded-full border ${b.severity === "critical" ? "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" : "bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]"}`}>{r}</span>
              ))}
              <span className="tabular text-xs font-bold text-[#0A2540]">{money(b.gross_total, b.currency)}</span>
            </div>
          </Link>
        ))}
      </div>

      {/* Operational counters */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
        <Small title="المكاتب" value={d.parties.offices} icon={Building2} />
        <Small title="الأفراد" value={d.parties.individuals} icon={User} />
        <Small title="المسوّقون" value={d.parties.marketers} icon={TrendingUp} />
        <Small title="برامج نشطة" value={d.programs.active} icon={Package} />
        <Small title="برامج منتهية" value={d.programs.expired} icon={Clock} />
        <Small title="برامج موقوفة" value={d.programs.unlisted} icon={Ban} />
      </div>

      <h3 className="font-head font-bold text-[#0A2540] mb-3">بانتظار الاعتماد والمعالجة</h3>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <Action to="/admin/finance" title="طلبات الشحن" count={at.pending_topups} icon={ArrowUpCircle} />
        <Action to="/admin/finance" title="تحويلات P2P" count={at.pending_transfers} icon={ArrowLeftRight} />
        <Action to="/admin/finance" title="طلبات السحب" count={at.pending_withdrawals} icon={ArrowDownCircle} />
        <Action to="/admin/cancellations" title="طلبات الإلغاء" count={at.cancellation_requests} icon={Ban} danger />
        <Action to="/admin/disputes" title="نزاعات مفتوحة" count={at.open_disputes} icon={ShieldAlert} danger />
        <Action to="/admin/orders?attention=1" title="طلبات مُصعَّدة" count={at.escalated} icon={AlertTriangle} />
        <Action to="/admin/orders?attention=1" title="مهام مفتوحة" count={at.open_tasks} icon={ListChecks} />
        <Action to="/admin/orders?attention=1" title="أحداث لم تُسلَّم لرحّال" count={at.failed_outbox} icon={PlugZap} />
      </div>
    </>
  );
}

const Mini = ({ label, value, accent, danger }) => (
  <div className="bg-[#F4F6F8] rounded-lg px-3 py-2">
    <div className="text-[10px] text-muted-foreground">{label}</div>
    <div className={`tabular text-sm font-bold ${danger ? "text-[#B91C1C]" : accent ? "text-[#15803D]" : "text-[#0A2540]"}`}>{value}</div>
  </div>
);

const ChartCard = ({ title, children }) => (
  <div className="bg-white rounded-2xl border card-shadow p-5">
    <div className="font-head font-bold text-[#0A2540] text-sm mb-4">{title}</div>
    {children}
  </div>
);

const Tile = ({ title, value, onClick, tid }) => (
  <button onClick={onClick} data-testid={tid}
    className="hover-lift bg-white rounded-2xl border p-4 card-shadow text-right">
    <div className="tabular text-2xl font-bold text-[#0A2540]">{value}</div>
    <div className="text-xs text-muted-foreground mt-1">{title}</div>
  </button>
);

const Small = ({ title, value, icon: Icon }) => (
  <div className="bg-white rounded-2xl border p-4 card-shadow flex items-center gap-3">
    <div className="w-10 h-10 rounded-xl bg-[#F4F6F8] flex items-center justify-center"><Icon className="w-4 h-4 text-[#0A2540]" /></div>
    <div><div className="tabular text-xl font-bold text-[#0A2540]">{value}</div><div className="text-[11px] text-muted-foreground">{title}</div></div>
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
