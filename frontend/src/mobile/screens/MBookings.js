import { useState } from "react";
import { useNavigate } from "react-router-dom";
import mobileApi from "@/mobile/api/client";
import { useAuth } from "@/context/AuthContext";
import { Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, StatusPill, useAsync } from "@/mobile/ui/kit";

/** Unified bookings hub. `kind` is carried per booking so transport tickets can appear
 *  here later without a new screen. */
const KIND_LABEL = { umrah: "عمرة", flight: "طيران", land_transport: "نقل بري" };

export default function MBookings() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [role, setRole] = useState("buyer");
  const list = useAsync(() => mobileApi.bookings(role), [role]);
  const isOffice = user?.role === "office";

  return (
    <Screen>
      <TopBar title="حجوزاتي" subtitle="مركز موحّد لكل أنواع الحجوزات" />
      {isOffice && (
        <div className="px-4 pt-4 flex gap-2" data-testid="m-bookings-role-tabs">
          {[["buyer", "كمشتري"], ["seller", "كبائع"]].map(([v, l]) => (
            <button key={v} onClick={() => setRole(v)} data-testid={`m-bookings-role-${v}`}
                    className={`h-10 px-4 rounded-full text-xs font-bold ${role === v ? "bg-[#0A2540] text-white" : "bg-white border text-[#0A2540]"}`}>
              {l}
            </button>
          ))}
        </div>
      )}

      {list.loading ? <Skeleton rows={4} />
        : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
        : (list.data || []).length === 0
          ? <EmptyState title="لا حجوزات" hint="ستظهر هنا حجوزات العمرة وحجوزات التذاكر مستقبلاً"
                        action={<button onClick={() => navigate("/m/programs")} data-testid="m-bookings-browse"
                                        className="h-11 px-5 rounded-xl bg-[#0A2540] text-white text-sm font-semibold">تصفح البرامج</button>} />
          : (
            <div className="p-4 space-y-3" data-testid="m-bookings-list">
              {list.data.map((b) => (
                <Card key={b.id} testid={`m-booking-${b.id}`} onClick={() => navigate(`/m/bookings/${b.id}`)}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-semibold text-sm text-[#0A2540] truncate">{b.package_title}</p>
                      <p className="text-[11px] text-muted-foreground mt-1">
                        {KIND_LABEL[b.kind || "umrah"]} · {b.seats || (b.registrants || []).length} مسافر ·
                        {" "}{String(b.created_at).slice(0, 10)}
                      </p>
                    </div>
                    <div className="text-end shrink-0 space-y-1">
                      <StatusPill status={b.status} />
                      <div className="text-xs"><Money value={b.amount_charged} currency={b.currency} /></div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
    </Screen>
  );
}
