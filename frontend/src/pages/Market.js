import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, equiv, fmtDate, PKG_TYPE, roomCustomer } from "@/lib/format";
import { MapPin, Users, CalendarDays, Search, Landmark, Bus, Wifi, Coffee, RotateCcw, Clock, TrendingUp } from "lucide-react";
import { PkgImage } from "@/components/PkgImage";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const TABS = [{ k: "", l: "الكل" }, { k: "umrah", l: "عمرة" }, { k: "tourism", l: "سياحة" }];
const DURATIONS = [
  { k: "", l: "أي مدة" },
  { k: "short", l: "٧ أيام أو أقل", max: 7 },
  { k: "mid", l: "٨–١٤ يوم", min: 8, max: 14 },
  { k: "long", l: "١٥ يوم فأكثر", min: 15 },
];
const QUICK_FEATURES = [
  { k: "breakfast", l: "إفطار مجاني", icon: Coffee },
  { k: "near_haram", l: "قريب من الحرم", icon: Landmark },
  { k: "vip_transport", l: "مواصلات VIP", icon: Bus },
  { k: "wifi", l: "واي فاي", icon: Wifi },
];
const SORTS = [
  { k: "newest", l: "الأحدث" },
  { k: "price_asc", l: "الأقل سعراً" },
  { k: "price_desc", l: "الأعلى سعراً" },
  { k: "date_asc", l: "الأقرب انطلاقاً" },
  { k: "duration_asc", l: "الأقصر مدة" },
  { k: "best_selling", l: "الأكثر مبيعاً" },
];

export default function Market() {
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [duration, setDuration] = useState("");
  const [features, setFeatures] = useState([]);
  const [sort, setSort] = useState("newest");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const toggleFeature = (k) => setFeatures((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));
  const reset = () => {
    setType(""); setQ(""); setMinPrice(""); setMaxPrice(""); setDateFrom("");
    setDateTo(""); setDuration(""); setFeatures([]); setSort("newest");
  };

  useEffect(() => {
    const run = () => {
      setLoading(true);
      const params = {};
      if (type) params.type = type;
      if (q) params.q = q;
      if (minPrice) params.min_price = minPrice;
      if (maxPrice) params.max_price = maxPrice;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const d = DURATIONS.find((x) => x.k === duration);
      if (d?.min != null) params.min_days = d.min;
      if (d?.max != null) params.max_days = d.max;
      if (features.length) params.features = features.join(",");
      if (sort) params.sort = sort;
      api.get("/packages", { params }).then((r) => setItems(r.data)).finally(() => setLoading(false));
    };
    const t = setTimeout(run, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line
  }, [type, q, minPrice, maxPrice, dateFrom, dateTo, duration, features, sort]);

  const activeFilters = [minPrice, maxPrice, dateFrom, dateTo, duration].filter(Boolean).length + features.length + (type ? 1 : 0);

  return (
    <>
      <PageHeader title="سوق البرامج" subtitle="ابحث وصفِّ برامج العمرة والسياحة المتاحة من المكاتب" />

      {/* Filter bar */}
      <div className="bg-white rounded-2xl border card-shadow p-4 sm:p-5 mb-6 space-y-4" data-testid="market-filters">
        {/* search + sort */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="w-4 h-4 absolute top-1/2 -translate-y-1/2 start-3 text-muted-foreground" />
            <Input data-testid="market-search" value={q} onChange={(e) => setQ(e.target.value)}
                   placeholder="ابحث عن برنامج بالاسم..." className="ps-9" />
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-muted-foreground whitespace-nowrap">ترتيب حسب</label>
            <select data-testid="market-sort" value={sort} onChange={(e) => setSort(e.target.value)}
                    className="h-10 rounded-lg border border-input bg-transparent px-3 text-sm font-medium">
              {SORTS.map((s) => <option key={s.k} value={s.k}>{s.l}</option>)}
            </select>
          </div>
          <Button variant="outline" onClick={reset} data-testid="market-reset" className="h-10 gap-1.5">
            <RotateCcw className="w-4 h-4" /> مسح {activeFilters > 0 ? `(${activeFilters})` : ""}
          </Button>
        </div>

        {/* type tabs */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex bg-[#F4F6F8] rounded-xl p-1">
            {TABS.map((t) => (
              <button key={t.k} data-testid={`market-tab-${t.k || "all"}`} onClick={() => setType(t.k)}
                      className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                        type === t.k ? "bg-[#0A2540] text-white" : "text-muted-foreground hover:text-[#0A2540]"}`}>
                {t.l}
              </button>
            ))}
          </div>
        </div>

        {/* price + date row */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div>
            <label className="text-xs text-muted-foreground mb-1.5 block">السعر من</label>
            <Input data-testid="market-min-price" type="number" value={minPrice} placeholder="0"
                   onChange={(e) => setMinPrice(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1.5 block">السعر إلى</label>
            <Input data-testid="market-max-price" type="number" value={maxPrice} placeholder="∞"
                   onChange={(e) => setMaxPrice(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1.5 block">الانطلاق من</label>
            <Input data-testid="market-date-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1.5 block">الانطلاق إلى</label>
            <Input data-testid="market-date-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
        </div>

        {/* duration chips */}
        <div>
          <label className="text-xs text-muted-foreground mb-2 block">مدة الرحلة</label>
          <div className="flex flex-wrap gap-2">
            {DURATIONS.map((d) => (
              <button key={d.k || "any"} data-testid={`market-duration-${d.k || "any"}`} onClick={() => setDuration(d.k)}
                      className={`px-3.5 py-1.5 rounded-full text-sm border transition-colors ${
                        duration === d.k ? "bg-[#0A2540] text-white border-[#0A2540]" : "bg-white text-[#0A2540] border-input hover:border-[#0A2540]"}`}>
                {d.l}
              </button>
            ))}
          </div>
        </div>

        {/* quick features */}
        <div>
          <label className="text-xs text-muted-foreground mb-2 block">مميزات سريعة</label>
          <div className="flex flex-wrap gap-2">
            {QUICK_FEATURES.map((f) => {
              const on = features.includes(f.k);
              return (
                <button key={f.k} data-testid={`market-feature-${f.k}`} onClick={() => toggleFeature(f.k)}
                        className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-sm border transition-colors ${
                          on ? "bg-[#D4AF37] text-[#0A2540] border-[#D4AF37] font-semibold" : "bg-white text-[#0A2540] border-input hover:border-[#D4AF37]"}`}>
                  <f.icon className="w-3.5 h-3.5" /> {f.l}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="text-sm text-muted-foreground mb-4" data-testid="market-result-count">
        {loading ? "جارٍ التحميل..." : `${items.length} برنامج مطابق`}
      </div>

      {loading ? (
        <div className="text-center py-20 text-muted-foreground">جارٍ التحميل...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground" data-testid="market-empty">لا توجد برامج مطابقة للفلاتر المحددة</div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {items.map((p) => {
            const start = p.start_price != null ? p.start_price : (Number(p.final_sale_price) || 0);
            const hasRooms = Array.isArray(p.room_pricing) && p.room_pricing.length > 0;
            return (
              <Link key={p.id} to={`/market/${p.id}`} data-testid={`pkg-card-${p.id}`}
                    className="hover-lift bg-white rounded-2xl border overflow-hidden card-shadow group">
                <div className="aspect-[4/3] bg-[#0A2540] relative overflow-hidden">
                  <PkgImage src={p.images?.[0]} alt={p.title} />
                  <span className="absolute top-3 start-3 bg-white/90 text-[#0A2540] text-xs font-semibold px-3 py-1 rounded-full">
                    {PKG_TYPE[p.type] || p.type}
                  </span>
                  {p.seller_deals > 0 && (
                    <span data-testid={`pkg-deals-${p.id}`}
                          className="absolute top-3 end-3 flex items-center gap-1 bg-[#D4AF37] text-[#0A2540] text-[11px] font-bold px-2.5 py-1 rounded-full">
                      <TrendingUp className="w-3 h-3" /> {p.seller_deals} صفقة
                    </span>
                  )}
                </div>
                <div className="p-5">
                  <h3 className="font-head font-bold text-[#0A2540] line-clamp-1">{p.title}</h3>
                  <p className="text-xs text-muted-foreground mt-1">{p.seller_office_name}</p>
                  <div className="flex flex-wrap gap-3 mt-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1"><CalendarDays className="w-3.5 h-3.5" /> {fmtDate(p.departure_date)}</span>
                    {p.duration_days != null && <span className="flex items-center gap-1"><Clock className="w-3.5 h-3.5" /> {p.duration_days} يوم</span>}
                    <span className="flex items-center gap-1"><Users className="w-3.5 h-3.5" /> {p.available_seats} مقعد</span>
                  </div>
                  <div className="flex items-end justify-between mt-4 pt-4 border-t">
                    <div>
                      <div className="text-[11px] text-muted-foreground">{hasRooms ? "يبدأ من" : "سعر البيع للزبون"}</div>
                      <div className="flex items-center gap-2">
                        <div className="tabular text-xl font-bold text-[#0A2540]" data-testid={`pkg-price-${p.id}`}>{money(start, p.currency)}</div>
                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${p.currency === "USD" ? "bg-[#ECFDF5] text-[#047857]" : "bg-[#EFF6FF] text-[#1D4ED8]"}`}>{p.currency === "USD" ? "USD" : "SAR"}</span>
                      </div>
                      {p.currency === "SAR" && <div className="text-[10px] text-muted-foreground tabular">{equiv(start, "SAR")}</div>}
                    </div>
                    <span className="text-xs font-semibold text-[#15803D] bg-[#F0FDF4] px-2 py-1 rounded-md">
                      {p.buyer_office_commission != null ? `عمولتك ${money(p.buyer_office_commission, p.currency)}` : "احجز مباشرة"}
                    </span>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}
