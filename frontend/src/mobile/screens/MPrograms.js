import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Landmark, SlidersHorizontal, CalendarDays, Users } from "lucide-react";
import mobileApi from "@/mobile/api/client";
import {
  Screen, TopBar, Skeleton, ErrorState, EmptyState, Money, Sheet, SheetSelect, DateField,
  SearchField, PrimaryButton, GhostButton, Chip, mInput, MField, useAsync,
} from "@/mobile/ui/kit";

const SORTS = [
  { value: "newest", label: "الأحدث" },
  { value: "price_asc", label: "الأقل سعراً" },
  { value: "price_desc", label: "الأعلى سعراً" },
  { value: "date_asc", label: "الأقرب مغادرة" },
  { value: "best_selling", label: "الأكثر مبيعاً" },
];

const cover = (p) => p?.cover_image || (Array.isArray(p?.images) ? p.images[0] : null);

export default function MPrograms() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [filters, setFilters] = useState({ sort: "newest", min_price: "", max_price: "", date_from: "" });
  const [applied, setApplied] = useState({ sort: "newest" });
  const [sheet, setSheet] = useState(false);
  const list = useAsync(() => mobileApi.programs({ ...applied, q: applied.q || undefined }),
    [JSON.stringify(applied)], { cacheKey: `m-programs-${JSON.stringify(applied)}` });

  const apply = () => {
    setApplied({ q: q.trim() || undefined, sort: filters.sort,
      min_price: filters.min_price || undefined, max_price: filters.max_price || undefined,
      date_from: filters.date_from || undefined });
    setSheet(false);
  };
  const activeFilters = ["min_price", "max_price", "date_from"].filter((k) => applied[k]).length
    + (applied.sort && applied.sort !== "newest" ? 1 : 0);

  return (
    <Screen refresh={list.reload}>
      <TopBar title="برامج العمرة" subtitle="من سوق معراج مباشرة" back />

      <div className="p-4 flex gap-2.5">
        <SearchField value={q} onChange={setQ} onSubmit={apply} placeholder="ابحث باسم البرنامج"
                     testid="m-programs-search" />
        <button onClick={() => setSheet(true)} data-testid="m-programs-filter-btn"
                className="relative w-14 h-14 rounded-2xl bg-white border border-black/[0.07] flex items-center justify-center active:scale-95 transition-transform shrink-0">
          <SlidersHorizontal className="w-5 h-5 text-[#0A2540]" />
          {activeFilters > 0 && (
            <span className="absolute -top-1 -end-1 w-5 h-5 rounded-full bg-[#D4AF37] text-[#0A2540] text-[10px] font-bold flex items-center justify-center">
              {activeFilters}
            </span>
          )}
        </button>
      </div>

      {list.loading ? <Skeleton rows={4} />
        : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
        : (list.data || []).length === 0
          ? <EmptyState title="لا توجد برامج مطابقة" hint="جرّب تعديل البحث أو عوامل التصفية" />
          : (
            <div className="px-4 space-y-4 m-stagger" data-testid="m-programs-list">
              {list.data.map((p) => (
                <button key={p.id} data-testid={`m-program-${p.id}`} onClick={() => navigate(`/m/programs/${p.id}`)}
                        className="w-full text-start bg-white rounded-[24px] border border-black/[0.04] overflow-hidden shadow-[0_6px_22px_-14px_rgba(10,37,64,0.45)] active:scale-[0.985] transition-transform">
                  <div className="h-36 bg-[#0A2540] relative">
                    {cover(p) ? (
                      <img src={cover(p)} alt="" className="w-full h-full object-cover" loading="lazy" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center">
                        <Landmark className="w-10 h-10 text-[#D4AF37]/50" />
                      </div>
                    )}
                    <div className="absolute inset-x-0 bottom-0 p-3 bg-gradient-to-t from-black/60 to-transparent">
                      <p className="font-head font-bold text-white text-[15px] line-clamp-1">{p.title}</p>
                    </div>
                  </div>
                  <div className="p-4">
                    <div className="flex flex-wrap gap-2">
                      {p.departure_date && (
                        <Chip><CalendarDays className="w-3 h-3 inline-block -mt-0.5 me-1" />
                          {String(p.departure_date).slice(0, 10)}</Chip>
                      )}
                      {p.duration_days ? <Chip>{p.duration_days} ليلة</Chip> : null}
                      <Chip tone={p.available_seats > 0 ? "good" : "bad"}>
                        <Users className="w-3 h-3 inline-block -mt-0.5 me-1" />{p.available_seats} مقعد
                      </Chip>
                    </div>
                    <div className="flex items-center justify-between mt-4 pt-3.5 border-t border-black/5">
                      <span className="text-[11px] text-muted-foreground font-semibold">يبدأ من</span>
                      <Money value={p.start_price ?? p.final_sale_price} currency={p.currency} className="text-base" />
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}

      <Sheet open={sheet} onClose={() => setSheet(false)} title="تصفية وترتيب" testid="m-programs-filter-sheet">
        <SheetSelect label="الترتيب" value={filters.sort} options={SORTS} testid="m-filter-sort"
                     onChange={(v) => setFilters({ ...filters, sort: v })} />
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
        <DateField label="المغادرة من تاريخ" value={filters.date_from} testid="m-filter-date"
                   onChange={(v) => setFilters({ ...filters, date_from: v })} />
        <PrimaryButton onClick={apply} data-testid="m-filter-apply">تطبيق</PrimaryButton>
        <div className="mt-2">
          <GhostButton onClick={() => {
            setFilters({ sort: "newest", min_price: "", max_price: "", date_from: "" });
            setQ(""); setApplied({ sort: "newest" }); setSheet(false);
          }}>مسح التصفية</GhostButton>
        </div>
      </Sheet>
    </Screen>
  );
}
