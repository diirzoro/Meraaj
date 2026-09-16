import { toast } from "sonner";
import { BellRing, CheckCheck } from "lucide-react";
import mobileApi, { apiError } from "@/mobile/api/client";
import { useShell } from "@/mobile/MobileShell";
import { Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, useAsync } from "@/mobile/ui/kit";

/** Reuses the EXISTING notifications collection/endpoints. Push transport is not wired
 *  yet (feature flag `push_notifications`), but the read model the app renders is final. */
export default function MNotifications() {
  const { reload: reloadShell } = useShell();
  const list = useAsync(() => mobileApi.notifications());

  const readAll = async () => {
    try {
      await mobileApi.markAllNotificationsRead();
      toast.success("تم تعليم الكل كمقروء");
      list.reload(); reloadShell();
    } catch (e) { toast.error(apiError(e)); }
  };

  const open = async (n) => {
    if (n.read) return;
    try { await mobileApi.markNotificationRead(n.id); list.reload(); reloadShell(); }
    catch { /* a read receipt is not worth blocking the UI */ }
  };

  return (
    <Screen>
      <TopBar title="الإشعارات" subtitle={`غير مقروءة: ${list.data?.unread ?? 0}`}
              right={<button onClick={readAll} data-testid="m-notifications-read-all"
                             className="w-9 h-9 rounded-full bg-white/10 flex items-center justify-center">
                <CheckCheck className="w-4 h-4" /></button>} />

      {list.loading ? <Skeleton rows={4} />
        : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
        : (list.data?.items || []).length === 0
          ? <EmptyState title="لا إشعارات" hint="ستصلك إشعارات الحجوزات والشحن وتغيّر الحالات" />
          : (
            <div className="p-4 space-y-3" data-testid="m-notifications-list">
              {list.data.items.map((n) => (
                <Card key={n.id} testid={`m-notification-${n.id}`} onClick={() => open(n)}
                      className={n.read ? "" : "border-[#D4AF37]/50"}>
                  <div className="flex items-start gap-3">
                    <span className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${n.read ? "bg-slate-100" : "bg-[#D4AF37]/15"}`}>
                      <BellRing className={`w-4 h-4 ${n.read ? "text-slate-400" : "text-[#D4AF37]"}`} />
                    </span>
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-[#0A2540]">{n.title || n.kind}</p>
                      <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">{n.body || n.message}</p>
                      <p className="text-[10px] text-muted-foreground mt-1">
                        {String(n.at || "").slice(0, 16).replace("T", " ")}
                      </p>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
    </Screen>
  );
}
