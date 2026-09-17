import { toast } from "sonner";
import { BellRing, CheckCheck } from "lucide-react";
import mobileApi, { apiError } from "@/mobile/api/client";
import { useShell } from "@/mobile/MobileShell";
import {
  Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, useAsync, haptic,
} from "@/mobile/ui/kit";

/** Reuses the EXISTING notifications collection/endpoints. Push transport is not wired
 *  yet (feature flag `push_notifications`), but the read model the app renders is final. */
export default function MNotifications() {
  const { reload: reloadShell } = useShell();
  const list = useAsync(() => mobileApi.notifications(), [], { cacheKey: "m-notifications" });

  const readAll = async () => {
    try {
      await mobileApi.markAllNotificationsRead();
      haptic("success");
      toast.success("تم تعليم الكل كمقروء");
      list.reload(); reloadShell();
    } catch (e) { toast.error(apiError(e)); }
  };

  const open = async (n) => {
    if (n.read) return;
    try { await mobileApi.markNotificationRead(n.id); list.reload(); reloadShell(); }
    catch { /* a read receipt is not worth blocking the UI */ }
  };

  const refresh = async () => { await Promise.all([list.reload(), reloadShell()]); };

  return (
    <Screen refresh={refresh}>
      <TopBar title="الإشعارات" subtitle={`غير مقروءة: ${list.data?.unread ?? 0}`} large
              right={<button onClick={readAll} data-testid="m-notifications-read-all" aria-label="تعليم الكل كمقروء"
                             className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center active:scale-90 transition-transform">
                <CheckCheck className="w-4 h-4" /></button>} />

      {list.loading ? <Skeleton rows={4} />
        : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
        : (list.data?.items || []).length === 0
          ? <EmptyState title="لا إشعارات" hint="ستصلك إشعارات الحجوزات والشحن وتغيّر الحالات" />
          : (
            <div className="p-4 space-y-3 m-stagger" data-testid="m-notifications-list">
              {list.data.items.map((n) => (
                <Card key={n.id} testid={`m-notification-${n.id}`} onClick={() => open(n)}
                      className={n.read ? "" : "border-[#D4AF37]/45 bg-[#fffdf5]"}>
                  <div className="flex items-start gap-3">
                    <span className={`w-11 h-11 rounded-2xl flex items-center justify-center shrink-0 ${
                      n.read ? "bg-slate-100" : "bg-[#D4AF37]/15"}`}>
                      <BellRing className={`w-[18px] h-[18px] ${n.read ? "text-slate-400" : "text-[#D4AF37]"}`} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start gap-2">
                        <p className="text-sm font-bold text-[#0A2540] flex-1">{n.title || n.kind}</p>
                        {!n.read && <span className="w-2 h-2 rounded-full bg-[#D4AF37] mt-1.5 shrink-0" />}
                      </div>
                      <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{n.body || n.message}</p>
                      <p className="text-[10.5px] text-muted-foreground mt-1.5">
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
