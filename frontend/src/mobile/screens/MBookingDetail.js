import { useParams } from "react-router-dom";
import mobileApi from "@/mobile/api/client";
import { Screen, TopBar, Card, Skeleton, ErrorState, Money, StatusPill, useAsync } from "@/mobile/ui/kit";

export default function MBookingDetail() {
  const { id } = useParams();
  const b = useAsync(() => mobileApi.booking(id), [id]);
  const tl = useAsync(() => mobileApi.bookingTimeline(id).catch(() => null), [id]);

  if (b.loading) return <Screen><TopBar title="تفاصيل الحجز" back /><Skeleton rows={4} /></Screen>;
  if (b.error) return <Screen><TopBar title="تفاصيل الحجز" back /><ErrorState message={b.error} onRetry={b.reload} /></Screen>;

  const d = b.data || {};
  const rows = [
    ["الحالة", <StatusPill key="s" status={d.status} />],
    ["المبلغ المحتسب", <Money key="a" value={d.amount_charged} currency={d.currency} />],
    ["عدد المسافرين", d.seats || (d.registrants || []).length],
    ["تاريخ الحجز", String(d.created_at || "").slice(0, 16).replace("T", " ")],
    ["نوع الغرفة", d.room_type || "—"],
  ];

  return (
    <Screen>
      <TopBar title={d.package_title || "تفاصيل الحجز"} subtitle={`رقم ${id}`} back />
      <div className="p-4 space-y-3">
        <Card testid="m-booking-detail-summary">
          {rows.map(([k, v]) => (
            <div key={k} className="flex items-center justify-between py-2 border-b last:border-0 text-xs">
              <span className="text-muted-foreground">{k}</span>
              <span className="font-semibold text-[#0A2540]">{v}</span>
            </div>
          ))}
        </Card>

        <Card testid="m-booking-detail-travelers">
          <p className="font-semibold text-sm text-[#0A2540] mb-3">المسافرون</p>
          {(d.registrants || []).length === 0 ? (
            <p className="text-xs text-muted-foreground">لا بيانات مسافرين</p>
          ) : (d.registrants || []).map((r, i) => (
            <div key={i} className="flex items-center justify-between py-2 border-b last:border-0 text-xs">
              <span className="text-[#0A2540] font-semibold">{r.name}</span>
              <span className="text-muted-foreground">{r.passport_no} · {r.age}</span>
            </div>
          ))}
        </Card>

        {Array.isArray(tl.data?.items || tl.data) && (
          <Card testid="m-booking-detail-timeline">
            <p className="font-semibold text-sm text-[#0A2540] mb-3">مسار الحجز</p>
            <div className="space-y-3">
              {(tl.data.items || tl.data).map((e, i) => (
                <div key={i} className="flex gap-3" data-testid={`m-timeline-${i}`}>
                  <span className="w-2 h-2 rounded-full bg-[#D4AF37] mt-1.5 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-[#0A2540]">{e.label || e.event || e.status}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {String(e.at || e.created_at || "").slice(0, 16).replace("T", " ")}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </Screen>
  );
}
