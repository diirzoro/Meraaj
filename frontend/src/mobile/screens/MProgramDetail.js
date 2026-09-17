import { useNavigate, useParams } from "react-router-dom";
import { CalendarDays, ChevronLeft, Hotel, Landmark, Plane, Users } from "lucide-react";
import mobileApi from "@/mobile/api/client";
import {
  Screen, TopBar, Card, Skeleton, ErrorState, Money, PrimaryButton, Chip, useAsync,
} from "@/mobile/ui/kit";

const cover = (p) => p?.cover_image || (Array.isArray(p?.images) ? p.images[0] : null);

export default function MProgramDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const p = useAsync(() => mobileApi.program(id), [id]);

  if (p.loading) return <Screen><TopBar title="تفاصيل البرنامج" back /><Skeleton rows={4} /></Screen>;
  if (p.error) return <Screen><TopBar title="تفاصيل البرنامج" back /><ErrorState message={p.error} onRetry={p.reload} /></Screen>;

  const d = p.data || {};
  const rooms = d.rooms || [];
  const soldOut = !d.available_seats;
  const img = cover(d);

  return (
    <Screen className="pb-40">
      {/* hero with a floating back button instead of a web header */}
      <div className="relative h-60 bg-[#0A2540]">
        {img ? <img src={img} alt="" className="w-full h-full object-cover" />
          : <div className="w-full h-full flex items-center justify-center"><Landmark className="w-14 h-14 text-[#D4AF37]/50" /></div>}
        <div className="absolute inset-0 bg-gradient-to-t from-[#0A2540] via-[#0A2540]/25 to-transparent" />
        <button onClick={() => navigate(-1)} data-testid="m-back-btn" aria-label="رجوع"
                className="absolute top-[max(1rem,env(safe-area-inset-top))] start-4 w-11 h-11 rounded-full bg-black/35 backdrop-blur text-white flex items-center justify-center active:scale-90 transition-transform">
          <ChevronLeft className="w-5 h-5 rtl:rotate-180" />
        </button>
        <div className="absolute inset-x-0 bottom-0 p-5">
          <p className="text-[11px] text-white/70 font-semibold">
            {d.type === "umrah" ? "برنامج عمرة" : d.type || "برنامج"}
          </p>
          <h1 className="font-head text-xl font-bold text-white mt-1 leading-snug">{d.title}</h1>
        </div>
      </div>

      <div className="p-4 space-y-3.5 -mt-5 relative">
        <Card testid="m-program-summary">
          <div className="grid grid-cols-2 gap-4">
            {[
              [CalendarDays, "المغادرة", d.departure_date ? String(d.departure_date).slice(0, 10) : "—"],
              [Plane, "العودة", d.return_date ? String(d.return_date).slice(0, 10) : "—"],
              [Hotel, "الإقامة", d.hotel_name || d.city || "—"],
              [Users, "المقاعد المتاحة", `${d.available_seats ?? 0}`],
            ].map(([Icon, label, value]) => (
              <div key={label} className="flex items-start gap-2.5">
                <span className="w-9 h-9 rounded-xl bg-[#0A2540]/[0.06] flex items-center justify-center shrink-0">
                  <Icon className="w-4 h-4 text-[#0A2540]" />
                </span>
                <div className="min-w-0">
                  <p className="text-[11px] text-muted-foreground">{label}</p>
                  <p className="text-xs font-bold text-[#0A2540] truncate">{value}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {d.description && (
          <Card testid="m-program-description">
            <p className="font-bold text-sm text-[#0A2540] mb-2">عن البرنامج</p>
            <p className="text-xs leading-relaxed text-muted-foreground whitespace-pre-line">{d.description}</p>
          </Card>
        )}

        {rooms.length > 0 && (
          <Card testid="m-program-rooms">
            <p className="font-bold text-sm text-[#0A2540] mb-3">أنواع الغرف والأسعار</p>
            <div className="space-y-1">
              {rooms.map((r, i) => (
                <div key={i} className="flex items-center justify-between py-2.5 border-b border-black/5 last:border-0"
                     data-testid={`m-program-room-${i}`}>
                  <Chip>{r.room_type || r.type || `غرفة ${i + 1}`}</Chip>
                  <Money value={r.final_sale_price ?? r.sale_price ?? d.final_sale_price} currency={d.currency} />
                </div>
              ))}
            </div>
          </Card>
        )}

        <Card testid="m-program-price">
          <p className="text-[11px] text-muted-foreground">
            المبلغ النهائي والعمولة يحتسبهما السيرفر عند إتمام الحجز وفق نوع حسابك.
          </p>
        </Card>
      </div>

      {/* sticky price + CTA bar — native detail-screen pattern */}
      <div className="fixed bottom-0 inset-x-0 z-20 bg-white/95 backdrop-blur border-t border-black/5 px-4 pt-3 pb-[max(0.9rem,env(safe-area-inset-bottom))]">
        <div className="flex items-center gap-3">
          <div className="min-w-0">
            <p className="text-[10px] text-muted-foreground font-semibold">السعر للمسافر</p>
            <Money value={d.final_sale_price} currency={d.currency} className="text-lg" />
          </div>
          <div className="flex-1">
            <PrimaryButton disabled={soldOut} data-testid="m-program-book-btn"
                           onClick={() => navigate(`/m/programs/${id}/book`)}>
              {soldOut ? "لا توجد مقاعد" : "متابعة الحجز"}
            </PrimaryButton>
          </div>
        </div>
      </div>
    </Screen>
  );
}
