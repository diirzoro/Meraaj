import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bus, Landmark, Plane, Users } from "lucide-react";
import mobileApi from "@/mobile/api/client";
import { useAuth } from "@/context/AuthContext";
import {
  Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, StatusPill, Segmented,
  PrimaryButton, useAsync,
} from "@/mobile/ui/kit";

/** Unified bookings hub. `kind` is carried per booking so transport tickets can appear
 *  here later without a new screen. */
const KIND = {
  umrah: { label: "عمرة", icon: Landmark },
  flight: { label: "طيران", icon: Plane },
  land_transport: { label: "نقل بري", icon: Bus },
};
const STATUS_TABS = [["", "الكل"], ["blue", "قيد التنفيذ"], ["yellow", "بانتظار إجراء"], ["green", "مكتملة"],
  ["cancelled", "ملغاة"]];

export default function MBookings() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [role, setRole] = useState("buyer");
  const [status, setStatus] = useState("");
  const list = useAsync(() => mobileApi.bookings(role), [role], { cacheKey: `m-bookings-${role}` });
  const isOffice = user?.role === "office";

  const items = (list.data || []).filter((b) => !status || b.status === status);

  return (
    <Screen refresh={list.reload}>
      <TopBar title="حجوزاتي" subtitle="مركز موحّد لكل أنواع الحجوزات" large />

      <div className="px-4 pt-4 space-y-3">
        {isOffice && (
          <Segmented items={[["buyer", "كمشتري"], ["seller", "كبائع"]]} value={role} onChange={setRole}
                     testid="m-bookings-role-tabs" testidPrefix="m-bookings-role-" />
        )}
        <Segmented items={STATUS_TABS} value={status} onChange={setStatus} scroll
                   testid="m-bookings-status-tabs" testidPrefix="m-bookings-status-" />
      </div>

      {list.loading ? <Skeleton rows={4} />
        : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
        : items.length === 0
          ? <EmptyState title={status ? "لا حجوزات بهذه الحالة" : "لا حجوزات"}
                        hint="ستظهر هنا حجوزات العمرة وحجوزات التذاكر مستقبلاً"
                        action={<PrimaryButton onClick={() => navigate("/m/programs")} data-testid="m-bookings-browse">
                          تصفح البرامج</PrimaryButton>} />
          : (
            <div className="p-4 space-y-3.5 m-stagger" data-testid="m-bookings-list">
              {items.map((b) => {
                const kind = KIND[b.kind || "umrah"] || KIND.umrah;
                const Icon = kind.icon;
                return (
                  <Card key={b.id} testid={`m-booking-${b.id}`} onClick={() => navigate(`/m/bookings/${b.id}`)}>
                    <div className="flex items-start gap-3">
                      <span className="w-11 h-11 rounded-2xl bg-[#0A2540]/[0.06] flex items-center justify-center shrink-0">
                        <Icon className="w-5 h-5 text-[#0A2540]" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="font-bold text-sm text-[#0A2540] line-clamp-1">{b.package_title}</p>
                        <p className="text-[11px] text-muted-foreground mt-1 flex items-center gap-1.5">
                          {kind.label}
                          <span className="opacity-40">·</span>
                          <Users className="w-3 h-3" />{b.seats || (b.registrants || []).length}
                          <span className="opacity-40">·</span>
                          {String(b.created_at).slice(0, 10)}
                        </p>
                        <div className="flex items-center justify-between mt-3">
                          <StatusPill status={b.status} />
                          <Money value={b.amount_charged} currency={b.currency} className="text-sm" />
                        </div>
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
    </Screen>
  );
}
