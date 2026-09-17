import { useNavigate } from "react-router-dom";
import { Building2, Users } from "lucide-react";
import mobileApi from "@/mobile/api/client";
import {
  Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, StatusPill, useAsync,
} from "@/mobile/ui/kit";

/** مبيعاتي — office sellers only; reuses `/api/bookings?role=seller`. */
export default function MSales() {
  const navigate = useNavigate();
  const list = useAsync(() => mobileApi.bookings("seller"), [], { cacheKey: "m-sales" });

  return (
    <Screen refresh={list.reload}>
      <TopBar title="مبيعاتي" subtitle="حجوزات برامجك من المشترين" back />
      {list.loading ? <Skeleton rows={4} />
        : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
        : (list.data || []).length === 0 ? <EmptyState title="لا مبيعات بعد" hint="ستظهر هنا حجوزات المشترين لبرامجك" />
        : (
          <div className="p-4 space-y-3.5 m-stagger" data-testid="m-sales-list">
            {list.data.map((b) => (
              <Card key={b.id} testid={`m-sale-${b.id}`} onClick={() => navigate(`/m/bookings/${b.id}`)}>
                <div className="flex items-start gap-3">
                  <span className="w-11 h-11 rounded-2xl bg-[#D4AF37]/15 flex items-center justify-center shrink-0">
                    <Building2 className="w-5 h-5 text-[#7a6216]" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="font-bold text-sm text-[#0A2540] line-clamp-1">{b.package_title}</p>
                    <p className="text-[11px] text-muted-foreground mt-1 flex items-center gap-1.5">
                      {b.buyer_office_name || "مشترٍ"}
                      <span className="opacity-40">·</span>
                      <Users className="w-3 h-3" />{b.seats || (b.registrants || []).length}
                    </p>
                    <div className="flex items-center justify-between mt-3">
                      <StatusPill status={b.status} />
                      <Money value={b.net_cost_total ?? b.amount_charged} currency={b.currency} className="text-sm" />
                    </div>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
    </Screen>
  );
}
