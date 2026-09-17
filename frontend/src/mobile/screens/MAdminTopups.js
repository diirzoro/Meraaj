import { useState } from "react";
import { toast } from "sonner";
import { Building2, Image as ImageIcon } from "lucide-react";
import api, { apiError } from "@/lib/api";
import {
  Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, StatusPill, PrimaryButton,
  DangerButton, GhostButton, Segmented, Sheet, useAsync, haptic,
} from "@/mobile/ui/kit";

const TABS = [["pending", "قيد المراجعة"], ["approved", "معتمدة"], ["rejected", "مرفوضة"]];

/** Admin top-up review on mobile. The backend only accepts a review while the request is
 *  still `pending`, so a double tap or a retry can never credit a wallet twice. */
export default function MAdminTopups() {
  const [status, setStatus] = useState("pending");
  const list = useAsync(() => api.get(`/admin/topups?status=${status}`).then((r) => r.data), [status],
    { cacheKey: `m-admin-topups-${status}` });
  const [open, setOpen] = useState(null);
  const [confirm, setConfirm] = useState(null); // "approve" | "reject"
  const [busy, setBusy] = useState(false);

  const review = async (approve) => {
    if (busy) return;
    setBusy(true);
    try {
      await api.post(`/admin/topups/${open.id}/review`, { approve });
      haptic("success");
      toast.success(approve ? "تم اعتماد الشحن وإضافة الرصيد" : "تم رفض الطلب");
      setConfirm(null); setOpen(null); list.reload();
    } catch (e) { haptic("error"); toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Screen refresh={list.reload}>
      <TopBar title="طلبات شحن الرصيد" subtitle="الاعتماد يضيف الرصيد في السيرفر" back />
      <div className="p-4">
        <Segmented items={TABS} value={status} onChange={setStatus}
                   testid="m-admin-topups-tabs" testidPrefix="m-admin-topups-tab-" />
      </div>

      {list.loading ? <Skeleton rows={3} />
        : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
        : (list.data || []).length === 0 ? <EmptyState title="لا طلبات" />
        : (
          <div className="px-4 space-y-3.5 m-stagger" data-testid="m-admin-topups-list">
            {list.data.map((t) => (
              <Card key={t.id} testid={`m-admin-topup-${t.id}`} onClick={() => setOpen(t)}>
                <div className="flex items-start gap-3">
                  <span className="w-11 h-11 rounded-2xl bg-[#0A2540]/[0.06] flex items-center justify-center shrink-0">
                    <Building2 className="w-5 h-5 text-[#0A2540]" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold text-[#0A2540] truncate">{t.office_name}</p>
                    <p className="text-[11px] text-muted-foreground mt-1">
                      {t.method} · {String(t.created_at).slice(0, 10)}
                    </p>
                    <div className="flex items-center justify-between mt-3">
                      <StatusPill status={t.status} />
                      <Money value={t.amount} currency={t.currency} className="text-sm" />
                    </div>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

      <Sheet open={!!open} onClose={() => { setOpen(null); setConfirm(null); }} title="مراجعة طلب الشحن"
             testid="m-admin-topup-sheet">
        {open && (
          <div className="space-y-4">
            <div className="rounded-2xl bg-[#F1F4F8] p-4 space-y-2">
              {[["المكتب", open.office_name], ["الطريقة", open.method]].map(([k, v]) => (
                <div key={k} className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{k}</span>
                  <span className="font-bold text-[#0A2540]">{v}</span>
                </div>
              ))}
              <div className="flex items-center justify-between text-xs pt-2 border-t border-black/5">
                <span className="text-muted-foreground">المبلغ</span>
                <Money value={open.amount} currency={open.currency} className="text-base" />
              </div>
            </div>

            {open.receipt_url && (
              <a href={open.receipt_url} target="_blank" rel="noreferrer" data-testid="m-admin-topup-receipt"
                 className="flex items-center justify-center gap-2 h-14 rounded-2xl bg-white border border-black/[0.07] text-sm font-bold text-[#0A2540] active:scale-[0.98] transition-transform">
                <ImageIcon className="w-4 h-4" /> عرض الإيصال
              </a>
            )}

            {open.status === "pending" && (confirm ? (
              <div className="space-y-3">
                <p className="text-xs text-center text-[#0A2540] font-semibold">
                  {confirm === "approve"
                    ? "تأكيد الاعتماد؟ سيُضاف الرصيد إلى محفظة المكتب."
                    : "تأكيد رفض الطلب؟"}
                </p>
                {confirm === "approve" ? (
                  <PrimaryButton loading={busy} onClick={() => review(true)} data-testid="m-admin-topup-approve-confirm">
                    نعم، اعتماد وإضافة الرصيد
                  </PrimaryButton>
                ) : (
                  <DangerButton loading={busy} onClick={() => review(false)} data-testid="m-admin-topup-reject-confirm">
                    نعم، رفض الطلب
                  </DangerButton>
                )}
                <GhostButton onClick={() => setConfirm(null)}>تراجع</GhostButton>
              </div>
            ) : (
              <div className="space-y-3">
                <PrimaryButton onClick={() => setConfirm("approve")} data-testid="m-admin-topup-approve">
                  اعتماد وإضافة الرصيد
                </PrimaryButton>
                <DangerButton onClick={() => setConfirm("reject")} data-testid="m-admin-topup-reject">
                  رفض الطلب
                </DangerButton>
              </div>
            ))}
          </div>
        )}
      </Sheet>
    </Screen>
  );
}
