import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate, PKG_TYPE } from "@/lib/format";
import { MapPin, Users, CalendarDays, Search, Landmark } from "lucide-react";
import { Input } from "@/components/ui/input";

const TABS = [{ k: "", l: "الكل" }, { k: "umrah", l: "عمرة" }, { k: "tourism", l: "سياحة" }];

export default function Market() {
  const [items, setItems] = useState([]);
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    const params = {};
    if (type) params.type = type;
    if (q) params.q = q;
    api.get("/packages", { params }).then((r) => setItems(r.data)).finally(() => setLoading(false));
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [type]);

  return (
    <>
      <PageHeader title="سوق البكجات" subtitle="تصفّح باكجات العمرة والسياحة المتاحة من المكاتب الأخرى" />

      <div className="flex flex-wrap items-center gap-3 mb-6">
        <div className="flex bg-white border rounded-xl p-1 card-shadow">
          {TABS.map((t) => (
            <button key={t.k} data-testid={`market-tab-${t.k || "all"}`} onClick={() => setType(t.k)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                      type === t.k ? "bg-[#0A2540] text-white" : "text-muted-foreground hover:text-[#0A2540]"}`}>
              {t.l}
            </button>
          ))}
        </div>
        <div className="relative flex-1 min-w-[220px]">
          <Search className="w-4 h-4 absolute top-1/2 -translate-y-1/2 start-3 text-muted-foreground" />
          <Input data-testid="market-search" value={q} onChange={(e) => setQ(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && load()} placeholder="ابحث عن باكج..." className="ps-9" />
        </div>
      </div>

      {loading ? (
        <div className="text-center py-20 text-muted-foreground">جارٍ التحميل...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">لا توجد باكجات مطابقة</div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {items.map((p) => (
            <Link key={p.id} to={`/market/${p.id}`} data-testid={`pkg-card-${p.id}`}
                  className="hover-lift bg-white rounded-2xl border overflow-hidden card-shadow group">
              <div className="h-44 bg-[#0A2540] relative overflow-hidden">
                {p.images?.[0]
                  ? <img src={p.images[0]} alt={p.title} className="w-full h-full object-cover" />
                  : <div className="w-full h-full flex items-center justify-center"><Landmark className="w-12 h-12 text-white/15" /></div>}
                <span className="absolute top-3 start-3 bg-white/90 text-[#0A2540] text-xs font-semibold px-3 py-1 rounded-full">
                  {PKG_TYPE[p.type] || p.type}
                </span>
              </div>
              <div className="p-5">
                <h3 className="font-head font-bold text-[#0A2540] line-clamp-1">{p.title}</h3>
                <p className="text-xs text-muted-foreground mt-1">{p.seller_office_name}</p>
                <div className="flex flex-wrap gap-3 mt-3 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1"><CalendarDays className="w-3.5 h-3.5" /> {fmtDate(p.departure_date)}</span>
                  <span className="flex items-center gap-1"><MapPin className="w-3.5 h-3.5" /> {p.departure_city || "-"}</span>
                  <span className="flex items-center gap-1"><Users className="w-3.5 h-3.5" /> {p.available_seats} مقعد</span>
                </div>
                <div className="flex items-end justify-between mt-4 pt-4 border-t">
                  <div>
                    <div className="text-[11px] text-muted-foreground">سعر البيع للزبون</div>
                    <div className="tabular text-xl font-bold text-[#0A2540]">{money(p.final_sale_price, p.currency)}</div>
                  </div>
                  <span className="text-xs font-semibold text-[#15803D] bg-[#F0FDF4] px-2 py-1 rounded-md">
                    {p.buyer_office_commission != null ? `عمولتك ${money(p.buyer_office_commission, p.currency)}` : "احجز مباشرة"}
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
