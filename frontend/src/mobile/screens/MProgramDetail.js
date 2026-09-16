import { useNavigate, useParams } from "react-router-dom";
import { CalendarDays, Hotel, Plane, Users } from "lucide-react";
import mobileApi from "@/mobile/api/client";
import { Screen, TopBar, Card, Skeleton, ErrorState, Money, PrimaryButton, useAsync } from "@/mobile/ui/kit";

export default function MProgramDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const p = useAsync(() => mobileApi.program(id), [id]);

  if (p.loading) return <Screen><TopBar title="تفاصيل البرنامج" back /><Skeleton rows={4} /></Screen>;
  if (p.error) return <Screen><TopBar title="تفاصيل البرنامج" back /><ErrorState message={p.error} onRetry={p.reload} /></Screen>;

  const d = p.data || {};
  const rooms = d.rooms || [];
  const soldOut = !d.available_seats;

  return (
    <Screen>
      <TopBar title={d.title || "تفاصيل البرنامج"} subtitle={d.type === "umrah" ? "برنامج عمرة" : d.type} back />
      <div className="p-4 space-y-3">
        <Card testid="m-program-summary">
          <div className="grid grid-cols-2 gap-3 text-xs text-[#0A2540]">
            <div className="flex items-center gap-2"><CalendarDays className="w-4 h-4 text-[#0A2540]/50" />
              <span>{d.departure_date ? String(d.departure_date).slice(0, 10) : "—"}</span></div>
            <div className="flex items-center gap-2"><Plane className="w-4 h-4 text-[#0A2540]/50" />
              <span>{d.return_date ? String(d.return_date).slice(0, 10) : "—"}</span></div>
            <div className="flex items-center gap-2"><Hotel className="w-4 h-4 text-[#0A2540]/50" />
              <span className="truncate">{d.hotel_name || d.city || "—"}</span></div>
            <div className="flex items-center gap-2"><Users className="w-4 h-4 text-[#0A2540]/50" />
              <span>{d.available_seats ?? 0} مقعد متاح</span></div>
          </div>
        </Card>

        {d.description && (
          <Card testid="m-program-description">
            <p className="text-xs leading-relaxed text-muted-foreground whitespace-pre-line">{d.description}</p>
          </Card>
        )}

        {rooms.length > 0 && (
          <Card testid="m-program-rooms">
            <p className="font-semibold text-sm text-[#0A2540] mb-3">أنواع الغرف والأسعار</p>
            <div className="space-y-2">
              {rooms.map((r, i) => (
                <div key={i} className="flex items-center justify-between text-xs border-b last:border-0 pb-2 last:pb-0"
                     data-testid={`m-program-room-${i}`}>
                  <span className="text-[#0A2540] font-semibold">{r.room_type || r.type || `غرفة ${i + 1}`}</span>
                  <Money value={r.final_sale_price ?? r.sale_price ?? d.final_sale_price} currency={d.currency} />
                </div>
              ))}
            </div>
          </Card>
        )}

        <Card testid="m-program-price">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">السعر المعروض للمسافر</span>
            <span className="text-lg"><Money value={d.final_sale_price} currency={d.currency} /></span>
          </div>
          <p className="text-[11px] text-muted-foreground mt-2">
            المبلغ النهائي والعمولة يحتسبهما السيرفر عند إتمام الحجز وفق نوع حسابك.
          </p>
        </Card>

        <PrimaryButton disabled={soldOut} data-testid="m-program-book-btn"
                       onClick={() => navigate(`/m/programs/${id}/book`)}>
          {soldOut ? "لا توجد مقاعد متاحة" : "متابعة الحجز"}
        </PrimaryButton>
      </div>
    </Screen>
  );
}
