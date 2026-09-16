import { useState } from "react";
import { toast } from "sonner";
import api, { apiError } from "@/lib/api";
import { Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, StatusPill, PrimaryButton, Sheet, useAsync } from "@/mobile/ui/kit";

/** Admin top-up review on mobile. The backend only accepts a review while the request is
 *  still `pending`, so a double tap or a retry can never credit a wallet twice. */
export default function MAdminTopups() {
  const [status, setStatus] = useState("pending");
  const list = useAsync(() => api.get(`/admin/topups?status=${status}`).then((r) => r.data), [status]);
  const [open, setOpen] = useState(null);
  const [busy, setBusy] = useState(false);

  const review = async (approve) => {
    if (busy) return;
    setBusy(true);
    try {
      await api.post(`/admin/topups/${open.id}/review`, { approve });
      toast.success(approve ? "تم اعتماد الشحن وإضافة الرصيد" : "تم رفض الطلب");
      setOpen(null); list.reload();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Screen>
      <TopBar title="طلبات شحن الرصيد" subtitle="الاعتماد يضيف الرصيد في السيرفر" back />
      <div className="p-4 flex gap-2" data-testid="m-admin-topups-tabs">
        {[["pending", "قيد المراجعة"], ["approved", "معتمدة"], ["rejected", "مرفوضة"]].map(([v, l]) => (
          <button key={v} onClick={() => setStatus(v)} data-testid={`m-admin-topups-tab-${v}`}
                  className={`h-10 px-3 rounded-full text-[11px] font-bold ${status === v ? "bg-[#0A2540] text-white" : "bg-white border text-[#0A2540]"}`}>
            {l}
          </button>
        ))}
      </div>

      {list.loading ? <Skeleton rows={3} />
        : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
        : (list.data || []).length === 0 ? <EmptyState title="لا طلبات" />
        : (
          <div className="px-4 space-y-3" data-testid="m-admin-topups-list">
            {list.data.map((t) => (
              <Card key={t.id} testid={`m-admin-topup-${t.id}`} onClick={() => setOpen(t)}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-[#0A2540] truncate">{t.office_name}</p>
                    <p className="text-[11px] text-muted-foreground mt-1">{t.method} · {String(t.created_at).slice(0, 10)}</p>
                  </div>
                  <div className="text-end shrink-0 space-y-1">
                    <div className="text-sm"><Money value={t.amount} currency={t.currency} /></div>
                    <StatusPill status={t.status} />
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

      <Sheet open={!!open} onClose={() => setOpen(null)} title="مراجعة طلب الشحن" testid="m-admin-topup-sheet">
        {open && (
          <div className="space-y-3">
            <div className="text-[11px] space-y-1">
              <div>المكتب: <b>{open.office_name}</b></div>
              <div>المبلغ: <b><Money value={open.amount} currency={open.currency} /></b></div>
              <div>الطريقة: <b>{open.method}</b></div>
            </div>
            {open.receipt_url && (
              <a href={open.receipt_url} target="_blank" rel="noreferrer" data-testid="m-admin-topup-receipt"
                 className="block text-center h-11 leading-[2.75rem] rounded-xl bg-white border text-sm font-semibold text-[#0A2540]">
                عرض الإيصال
              </a>
            )}
            {open.status === "pending" && (
              <>
                <PrimaryButton loading={busy} onClick={() => review(true)} data-testid="m-admin-topup-approve">
                  اعتماد وإضافة الرصيد
                </PrimaryButton>
                <button onClick={() => review(false)} disabled={busy} data-testid="m-admin-topup-reject"
                        className="w-full h-12 rounded-xl border border-red-200 text-red-600 text-sm font-semibold">
                  رفض الطلب
                </button>
              </>
            )}
          </div>
        )}
      </Sheet>
    </Screen>
  );
}
