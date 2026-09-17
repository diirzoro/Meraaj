import { useParams } from "react-router-dom";
import { CalendarDays, CircleDollarSign, Users } from "lucide-react";
import mobileApi from "@/mobile/api/client";
import {
  Screen, TopBar, Card, Skeleton, ErrorState, Money, StatusPill, KpiCard, Chip, useAsync,
} from "@/mobile/ui/kit";

export default function MBookingDetail() {
  const { id } = useParams();
  const b = useAsync(() => mobileApi.booking(id), [id]);
  const tl = useAsync(() => mobileApi.bookingTimeline(id).catch(() => null), [id]);

  if (b.loading) return <Screen><TopBar title="تفاصيل الحجز" back /><Skeleton rows={4} /></Screen>;
  if (b.error) return <Screen><TopBar title="تفاصيل الحجز" back /><ErrorState message={b.error} onRetry={b.reload} /></Screen>;

  const d = b.data || {};
  const travelers = d.registrants || [];
  const timeline = Array.isArray(tl.data?.items) ? tl.data.items : Array.isArray(tl.data) ? tl.data : [];

  return (
    <Screen refresh={b.reload}>
      <TopBar title={d.package_title || "تفاصيل الحجز"} subtitle={`رقم ${id}`} back />

      <div className="p-4 space-y-3.5">
        <Card testid="m-booking-detail-summary">
          <div className="flex items-center justify-between gap-3 mb-4">
            <StatusPill status={d.status} />
            <Money value={d.amount_charged} currency={d.currency} className="text-lg" />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <KpiCard label="المسافرون" icon={Users} value={d.seats || travelers.length} />
            <KpiCard label="الغرفة" icon={CircleDollarSign} value={<span className="text-sm">{d.room_type || "—"}</span>} />
            <KpiCard label="تاريخ الحجز" icon={CalendarDays}
                     value={<span className="text-sm">{String(d.created_at || "").slice(0, 10)}</span>} />
          </div>
        </Card>

        <Card testid="m-booking-detail-travelers">
          <p className="font-bold text-sm text-[#0A2540] mb-3">المسافرون</p>
          {travelers.length === 0 ? (
            <p className="text-xs text-muted-foreground">لا بيانات مسافرين</p>
          ) : travelers.map((r, i) => (
            <div key={i} className="flex items-center justify-between py-3 border-b border-black/5 last:border-0">
              <div className="min-w-0">
                <p className="text-sm font-bold text-[#0A2540] truncate">{r.name}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5" dir="ltr">{r.passport_no}</p>
              </div>
              <Chip>{r.age} سنة</Chip>
            </div>
          ))}
        </Card>

        {timeline.length > 0 && (
          <Card testid="m-booking-detail-timeline">
            <p className="font-bold text-sm text-[#0A2540] mb-4">مسار الحجز</p>
            <div className="relative ps-4">
              <span className="absolute top-1 bottom-1 start-[3px] w-[2px] bg-[#0A2540]/10" />
              <div className="space-y-4">
                {timeline.map((e, i) => (
                  <div key={i} className="relative" data-testid={`m-timeline-${i}`}>
                    <span className="absolute -start-4 top-1 w-2.5 h-2.5 rounded-full bg-[#D4AF37] ring-4 ring-[#fffdf5]" />
                    <p className="text-sm font-bold text-[#0A2540]">{e.label || e.event || e.status}</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      {String(e.at || e.created_at || "").slice(0, 16).replace("T", " ")}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </Card>
        )}
      </div>
    </Screen>
  );
}
