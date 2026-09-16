import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, SlidersHorizontal } from "lucide-react";
import mobileApi from "@/mobile/api/client";
import { Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, Sheet, mInput, MField, PrimaryButton, useAsync } from "@/mobile/ui/kit";

const SORTS = [["newest", "الأحدث"], ["price_asc", "الأقل سعراً"], ["price_desc", "الأعلى سعراً"],
  ["date_asc", "الأقرب مغادرة"], ["best_selling", "الأكثر مبيعاً"]];

export default function MPrograms() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [filters, setFilters] = useState({ sort: "newest", min_price: "", max_price: "", date_from: "" });
  const [applied, setApplied] = useState({ sort: "newest" });
  const [sheet, setSheet] = useState(false);
  const list = useAsync(() => mobileApi.programs({ ...applied, q: applied.q || undefined }), [JSON.stringify(applied)]);

  const apply = () => {
    setApplied({ q: q.trim() || undefined, sort: filters.sort,
      min_price: filters.min_price || undefined, max_price: filters.max_price || undefined,
      date_from: filters.date_from || undefined });
    setSheet(false);
  };

  return (
    <Screen>
      <TopBar title="برامج العمرة" subtitle="بيانات حقيقية من سوق معراج" back />
      <div className="p-4 flex gap-2">
        <div className="relative flex-1">
          <input className={`${mInput} ps-10`} placeholder="ابحث باسم البرنامج" value={q}
                 data-testid="m-programs-search" onChange={(e) => setQ(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && apply()} />
          <Search className="w-4 h-4 absolute inset-y-0 my-auto start-3.5 text-[#0A2540]/40" />
        </div>
        <button onClick={() => setSheet(true)} data-testid="m-programs-filter-btn"
                className="w-12 h-12 rounded-xl bg-white border border-black/10 flex items-center justify-center active:scale-95 transition-transform">
          <SlidersHorizontal className="w-5 h-5 text-[#0A2540]" />
        </button>
      </div>

      {list.loading ? <Skeleton rows={4} />
        : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
        : (list.data || []).length === 0
          ? <EmptyState title="لا توجد برامج مطابقة" hint="جرّب تعديل البحث أو عوامل التصفية" />
          : (
            <div className="px-4 space-y-3" data-testid="m-programs-list">
              {list.data.map((p) => (
                <Card key={p.id} testid={`m-program-${p.id}`} onClick={() => navigate(`/m/programs/${p.id}`)}>
                  <p className="font-semibold text-sm text-[#0A2540]">{p.title}</p>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground mt-2">
                    {p.departure_date && <span>المغادرة {String(p.departure_date).slice(0, 10)}</span>}
                    {p.duration_days ? <span>{p.duration_days} ليلة</span> : null}
                    <span>{p.available_seats} مقعد متاح</span>
                  </div>
                  <div className="flex items-center justify-between mt-3 pt-3 border-t">
                    <span className="text-[11px] text-muted-foreground">يبدأ من</span>
                    <Money value={p.start_price ?? p.final_sale_price} currency={p.currency} />
                  </div>
                </Card>
              ))}
            </div>
          )}

      <Sheet open={sheet} onClose={() => setSheet(false)} title="تصفية وترتيب" testid="m-programs-filter-sheet">
        <MField label="الترتيب">
          <select className={mInput} value={filters.sort} data-testid="m-filter-sort"
                  onChange={(e) => setFilters({ ...filters, sort: e.target.value })}>
            {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </MField>
        <div className="grid grid-cols-2 gap-3">
          <MField label="أدنى سعر">
            <input className={mInput} inputMode="decimal" value={filters.min_price} data-testid="m-filter-min"
                   onChange={(e) => setFilters({ ...filters, min_price: e.target.value })} />
          </MField>
          <MField label="أعلى سعر">
            <input className={mInput} inputMode="decimal" value={filters.max_price} data-testid="m-filter-max"
                   onChange={(e) => setFilters({ ...filters, max_price: e.target.value })} />
          </MField>
        </div>
        <MField label="المغادرة من تاريخ">
          <input type="date" className={mInput} value={filters.date_from} data-testid="m-filter-date"
                 onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} />
        </MField>
        <PrimaryButton onClick={apply} data-testid="m-filter-apply">تطبيق</PrimaryButton>
      </Sheet>
    </Screen>
  );
}
