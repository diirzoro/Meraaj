import { useNavigate } from "react-router-dom";
import mobileApi from "@/mobile/api/client";
import { Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, StatusPill, useAsync } from "@/mobile/ui/kit";

/** مبيعاتي — office sellers only; reuses `/api/bookings?role=seller`. */
export default function MSales() {
  const navigate = useNavigate();
  const list = useAsync(() => mobileApi.bookings("seller"));

  return (
    <Screen>
      <TopBar title="مبيعاتي" subtitle="حجوزات برامجك من المشترين" back />
      {list.loading ? <Skeleton rows={4} />
        : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
        : (list.data || []).length === 0 ? <EmptyState title="لا مبيعات بعد" />
        : (
          <div className="p-4 space-y-3" data-testid="m-sales-list">
            {list.data.map((b) => (
              <Card key={b.id} testid={`m-sale-${b.id}`} onClick={() => navigate(`/m/bookings/${b.id}`)}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold text-sm text-[#0A2540] truncate">{b.package_title}</p>
                    <p className="text-[11px] text-muted-foreground mt-1">
                      {b.buyer_office_name || "مشترٍ"} · {b.seats || (b.registrants || []).length} مسافر
                    </p>
                  </div>
                  <div className="text-end shrink-0 space-y-1">
                    <StatusPill status={b.status} />
                    <div className="text-xs"><Money value={b.net_cost_total ?? b.amount_charged} currency={b.currency} /></div>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
    </Screen>
  );
}
