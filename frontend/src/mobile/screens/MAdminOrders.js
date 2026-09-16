import { useState } from "react";
import api from "@/lib/api";
import { Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, StatusPill, useAsync } from "@/mobile/ui/kit";

/** Admin orders on mobile — read-oriented monitoring; risky decisions stay on the web. */
export default function MAdminOrders() {
  const [status, setStatus] = useState("");
  const list = useAsync(() => api.get(`/admin/orders${status ? `?status=${status}` : ""}`)
    .then((r) => r.data).catch(() => api.get("/admin/dashboard").then(() => [])), [status]);
  const items = list.data?.items || (Array.isArray(list.data) ? list.data : []);

  return (
    <Screen>
      <TopBar title="مركز الطلبات" subtitle="متابعة الحجوزات" back />
      <div className="p-4 flex gap-2 overflow-x-auto" data-testid="m-admin-orders-tabs">
        {[["", "الكل"], ["blue", "قيد التنفيذ"], ["yellow", "بانتظار إجراء"], ["green", "مكتملة"],
          ["cancelled", "ملغاة"]].map(([v, l]) => (
          <button key={v || "all"} onClick={() => setStatus(v)} data-testid={`m-admin-orders-tab-${v || "all"}`}
                  className={`h-10 px-3 rounded-full text-[11px] font-bold whitespace-nowrap ${status === v ? "bg-[#0A2540] text-white" : "bg-white border text-[#0A2540]"}`}>
            {l}
          </button>
        ))}
      </div>

      {list.loading ? <Skeleton rows={4} />
        : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
        : items.length === 0 ? <EmptyState title="لا طلبات" />
        : (
          <div className="px-4 space-y-3" data-testid="m-admin-orders-list">
            {items.slice(0, 60).map((b) => (
              <Card key={b.id} testid={`m-admin-order-${b.id}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-[#0A2540] truncate">{b.package_title}</p>
                    <p className="text-[11px] text-muted-foreground mt-1 truncate">
                      {b.buyer_office_name || "—"} → {b.seller_office_name || "—"}
                    </p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">{String(b.created_at).slice(0, 10)}</p>
                  </div>
                  <div className="text-end shrink-0 space-y-1">
                    <div className="text-xs"><Money value={b.amount_charged} currency={b.currency} /></div>
                    <StatusPill status={b.status} />
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
    </Screen>
  );
}
