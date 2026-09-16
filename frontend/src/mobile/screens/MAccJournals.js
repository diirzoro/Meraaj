import { useState } from "react";
import { toast } from "sonner";
import accApi from "@/mobile/api/accounting";
import { apiError } from "@/lib/api";
import { useShell } from "@/mobile/MobileShell";
import { Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, Sheet, StatusPill, useAsync } from "@/mobile/ui/kit";

export default function MAccJournals() {
  const { shell } = useShell();
  const caps = shell?.accounting?.capabilities || {};
  const list = useAsync(() => accApi.journals());
  const [openId, setOpenId] = useState(null);
  const detail = useAsync(() => (openId ? accApi.journal(openId) : Promise.resolve(null)), [openId]);
  const [busy, setBusy] = useState(false);

  const reverse = async () => {
    const reason = window.prompt("سبب العكس:");
    if (!reason || reason.trim().length < 3 || busy) return;
    setBusy(true);
    try {
      const r = await accApi.reverseJournal(openId, reason.trim());
      toast.success(`قيد عكسي: ${r.reversal?.entry_no || ""}`);
      setOpenId(null); list.reload();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Screen>
      <TopBar title="القيود اليومية" subtitle="القيد المُرحَّل غير قابل للتعديل" back />
      {list.loading ? <Skeleton rows={4} />
        : list.error ? <ErrorState message={list.error} onRetry={list.reload} />
        : (list.data?.items || []).length === 0 ? <EmptyState title="لا قيود" />
        : (
          <div className="p-4 space-y-3" data-testid="m-journal-list">
            {list.data.items.map((j) => (
              <Card key={j.id} testid={`m-journal-${j.entry_no}`} onClick={() => setOpenId(j.id)}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-mono font-bold text-[#0A2540]">{j.entry_no}</p>
                    <p className="text-[11px] text-muted-foreground truncate mt-1">{j.description}</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">
                      {String(j.date).slice(0, 10)} · {j.source_type}
                    </p>
                  </div>
                  <div className="text-end shrink-0 space-y-1">
                    <div className="text-xs"><Money value={j.total_debit} currency={j.currency} /></div>
                    <StatusPill status={String(j.status).toLowerCase()} />
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}

      <Sheet open={!!openId} onClose={() => setOpenId(null)} title={`قيد ${detail.data?.entry_no || ""}`}
             testid="m-journal-detail">
        {detail.loading ? <Skeleton rows={2} /> : detail.data && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div>التاريخ: <b>{String(detail.data.date).slice(0, 10)}</b></div>
              <div>الحالة: <b>{detail.data.status}</b></div>
              <div>المصدر: <b>{detail.data.source_type}</b></div>
              <div>المنفّذ المحاسبي: <b>{detail.data.metadata?.actor?.accounting_actor || detail.data.created_by || "—"}</b></div>
            </div>
            <div className="border-t pt-2">
              {(detail.data.lines || []).map((l, i) => (
                <div key={i} className="flex items-center justify-between py-1.5 text-[11px]"
                     data-testid={`m-journal-line-${i}`}>
                  <span className="font-mono text-[#0A2540]">{l.account_code}</span>
                  <span className="text-muted-foreground">
                    مدين <Money value={l.debit} /> · دائن <Money value={l.credit} />
                  </span>
                </div>
              ))}
            </div>
            {String(detail.data.status).toLowerCase() === "posted" && caps.journal_reverse && (
              <button onClick={reverse} disabled={busy} data-testid="m-journal-reverse"
                      className="w-full h-12 rounded-xl border border-red-200 text-red-600 text-sm font-semibold">
                عكس القيد
              </button>
            )}
          </div>
        )}
      </Sheet>
    </Screen>
  );
}
