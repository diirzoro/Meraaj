import { useState } from "react";
import { toast } from "sonner";
import accApi from "@/mobile/api/accounting";
import { apiError } from "@/lib/api";
import { useShell } from "@/mobile/MobileShell";
import {
  Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, Sheet, StatusPill, mInput,
  MField, DangerButton, GhostButton, useAsync, haptic,
} from "@/mobile/ui/kit";

export default function MAccJournals() {
  const { shell } = useShell();
  const caps = shell?.accounting?.capabilities || {};
  const list = useAsync(() => accApi.journals());
  const [openId, setOpenId] = useState(null);
  const detail = useAsync(() => (openId ? accApi.journal(openId) : Promise.resolve(null)), [openId]);
  const [reversing, setReversing] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const reverse = async () => {
    if (busy || reason.trim().length < 3) return;
    setBusy(true);
    try {
      const r = await accApi.reverseJournal(openId, reason.trim());
      haptic("success");
      toast.success(`قيد عكسي: ${r.reversal?.entry_no || ""}`);
      setOpenId(null); setReversing(false); setReason(""); list.reload();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Screen refresh={list.reload}>
      <TopBar title="القيود اليومية" subtitle="القيد المُرحَّل غير قابل للتعديل" back />
      {list.loading ? <Skeleton rows={4} />
        : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
        : (list.data?.items || []).length === 0 ? <EmptyState title="لا قيود" />
        : (
          <div className="p-4 space-y-3.5 m-stagger" data-testid="m-journal-list">
            {list.data.items.map((j) => (
              <Card key={j.id} testid={`m-journal-${j.entry_no}`} onClick={() => setOpenId(j.id)}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-mono font-bold text-[#0A2540]" dir="ltr">{j.entry_no}</p>
                    <p className="text-xs text-[#0A2540]/75 line-clamp-1 mt-1.5">{j.description}</p>
                    <p className="text-[10.5px] text-muted-foreground mt-1">
                      {String(j.date).slice(0, 10)} · {j.source_type}
                    </p>
                  </div>
                  <div className="text-end shrink-0 space-y-1.5">
                    <div className="text-sm"><Money value={j.total_debit} currency={j.currency} /></div>
                    <StatusPill status={String(j.status).toLowerCase()} />
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

      <Sheet open={!!openId} onClose={() => { setOpenId(null); setReversing(false); }}
             title={`قيد ${detail.data?.entry_no || ""}`} testid="m-journal-detail">
        {detail.loading ? <Skeleton rows={2} /> : detail.data && (
          <div className="space-y-4">
            <div className="rounded-2xl bg-[#F1F4F8] p-4 space-y-2">
              {[["التاريخ", String(detail.data.date).slice(0, 10)], ["الحالة", detail.data.status],
                ["المصدر", detail.data.source_type],
                ["المنفّذ المحاسبي", detail.data.metadata?.actor?.accounting_actor || detail.data.created_by || "—"],
              ].map(([k, v]) => (
                <div key={k} className="flex items-center justify-between text-[11px]">
                  <span className="text-muted-foreground">{k}</span>
                  <span className="font-bold text-[#0A2540]">{v}</span>
                </div>
              ))}
            </div>

            <div>
              <p className="text-xs font-bold text-[#0A2540] mb-2">أطراف القيد</p>
              {(detail.data.lines || []).map((l, i) => (
                <div key={i} className="flex items-center justify-between py-2.5 border-b border-black/5 last:border-0"
                     data-testid={`m-journal-line-${i}`}>
                  <span className="font-mono text-xs font-bold text-[#0A2540]" dir="ltr">{l.account_code}</span>
                  <span className="text-[11px] text-muted-foreground">
                    مدين <Money value={l.debit} /> · دائن <Money value={l.credit} />
                  </span>
                </div>
              ))}
            </div>

            {String(detail.data.status).toLowerCase() === "posted" && caps.journal_reverse && (
              reversing ? (
                <div className="space-y-3">
                  <MField label="سبب العكس" hint="٣ أحرف على الأقل — يُسجَّل في القيد العكسي">
                    <input className={mInput} value={reason} data-testid="m-journal-reverse-reason"
                           onChange={(e) => setReason(e.target.value)} />
                  </MField>
                  <DangerButton loading={busy} disabled={busy || reason.trim().length < 3}
                                onClick={reverse} data-testid="m-journal-reverse-confirm">
                    تأكيد عكس القيد
                  </DangerButton>
                  <GhostButton onClick={() => { setReversing(false); setReason(""); }}>تراجع</GhostButton>
                </div>
              ) : (
                <DangerButton onClick={() => setReversing(true)} data-testid="m-journal-reverse">
                  عكس القيد
                </DangerButton>
              )
            )}
          </div>
        )}
      </Sheet>
    </Screen>
  );
}
