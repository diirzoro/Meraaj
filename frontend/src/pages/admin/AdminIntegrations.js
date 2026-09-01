import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { PlugZap, RefreshCw, CheckCircle2, XCircle } from "lucide-react";

export default function AdminIntegrations() {
  const [h, setH] = useState(null);
  const [items, setItems] = useState([]);
  const [retry, setRetry] = useState(null);   // {id} | {all:true}
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    Promise.all([api.get("/admin/integrations/health"), api.get("/admin/integrations/outbox?limit=100")])
      .then(([a, b]) => { setH(a.data); setItems(b.data); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const doRetry = async () => {
    setBusy(true);
    try {
      const r = retry.all
        ? await api.post("/admin/integrations/outbox/retry-all", { reason })
        : await api.post(`/admin/integrations/outbox/${retry.id}/retry`, { reason });
      toast.success(retry.all
        ? `تمت محاولة ${r.data.attempted} حدثاً — المتبقي ${r.data.still_undelivered}`
        : `النتيجة: ${r.data.status}`);
      setRetry(null); setReason(""); load();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  if (!h) return <div className="text-center py-20 text-muted-foreground" data-testid="integrations-loading">جارٍ التحميل...</div>;

  return (
    <>
      <PageHeader title="صحة التكامل مع رحّال" subtitle="حالة الأحداث الصادرة والواردة، أسباب الفشل، وإعادة المعالجة اليدوية بصلاحية خاصة وسبب مُسجَّل" />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        <Stat label="إجمالي الأحداث الصادرة" v={h.outbox.total} tid="stat-outbox-total" />
        <Stat label="مُسلَّمة" v={h.outbox.by_status.delivered || 0} ok tid="stat-delivered" />
        <Stat label="غير مُسلَّمة" v={h.outbox.undelivered} danger tid="stat-undelivered" />
        <Stat label="أحداث واردة" v={h.inbound.total} tid="stat-inbound" />
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-5 mb-5" data-testid="failure-groups">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 font-head font-bold text-[#0A2540] text-sm">
            <PlugZap className="w-4 h-4 text-[#D4AF37]" /> أسباب الفشل مجمّعة
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={load} data-testid="integrations-refresh">
              <RefreshCw className="w-4 h-4" /> تحديث
            </Button>
            <Button size="sm" className="bg-[#0A2540] hover:bg-[#061A2E]" data-testid="retry-all-btn"
              disabled={!h.outbox.undelivered} onClick={() => setRetry({ all: true })}>
              إعادة معالجة الكل
            </Button>
          </div>
        </div>
        {h.outbox.failure_groups.length === 0 ? (
          <div className="text-xs text-muted-foreground" data-testid="failure-groups-empty">لا توجد أحداث فاشلة</div>
        ) : (
          <div className="space-y-2" data-testid="failure-groups-list">
            {h.outbox.failure_groups.map((g, i) => (
              <div key={i} className="text-xs bg-[#FEF2F2] border border-[#FECACA] rounded-lg px-3 py-2" data-testid={`failure-group-${i}`}>
                <div className="flex justify-between">
                  <b className="text-[#B91C1C]">{g.event}</b>
                  <span className="tabular">{g.count} حدث</span>
                </div>
                <div className="text-[11px] text-muted-foreground mt-1 break-words">
                  {g.last_error || "لم يُسجَّل سبب — لم تُرسل بعد (pending)"}
                </div>
              </div>
            ))}
          </div>
        )}
        <div className="text-[11px] text-muted-foreground mt-3">
          آخر تسليم ناجح: {h.outbox.last_delivered_at ? fmtDate(h.outbox.last_delivered_at) : "—"}
        </div>
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto mb-5" data-testid="outbox-table">
        <table className="w-full text-xs min-w-[820px]">
          <thead className="bg-[#F4F6F8] text-muted-foreground">
            <tr>{["التاريخ", "الحدث", "الوجهة", "المحاولات", "الحالة", "سبب الفشل", ""].map((x) => (
              <th key={x} className="text-right font-semibold px-3 py-2.5">{x}</th>))}</tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={7} className="text-center py-10 text-muted-foreground" data-testid="outbox-empty">لا توجد أحداث معلّقة</td></tr>
            ) : items.map((it) => (
              <tr key={it.id} className="border-t" data-testid={`outbox-row-${it.id}`}>
                <td className="px-3 py-2.5 whitespace-nowrap">{fmtDate(it.created_at)}</td>
                <td className="px-3 py-2.5 font-semibold text-[#0A2540]">{it.event}</td>
                <td className="px-3 py-2.5 max-w-[180px] truncate text-[10px]">{it.url}</td>
                <td className="px-3 py-2.5 tabular">{it.attempts}</td>
                <td className="px-3 py-2.5">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full border ${it.status === "delivered" ? "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]" : it.status === "failed" ? "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" : "bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]"}`}>
                    {it.status === "delivered" ? "مُسلَّم" : it.status === "failed" ? "فاشل" : "معلّق"}
                  </span>
                </td>
                <td className="px-3 py-2.5 max-w-[220px] truncate text-[10px] text-muted-foreground">{it.last_error || "—"}</td>
                <td className="px-3 py-2.5">
                  <button onClick={() => setRetry({ id: it.id })} data-testid={`retry-${it.id}`}
                    className="text-[#0A2540] underline font-semibold">إعادة المعالجة</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="inbound-log">
        <div className="font-head font-bold text-[#0A2540] text-sm mb-3">آخر الأحداث الواردة من رحّال</div>
        <div className="space-y-1.5">
          {h.inbound.recent.length === 0 ? <div className="text-xs text-muted-foreground">لا يوجد سجل</div> :
            h.inbound.recent.map((r, i) => (
              <div key={i} className="text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-1.5 flex items-center gap-2" data-testid={`inbound-${i}`}>
                {r.ok === false ? <XCircle className="w-3.5 h-3.5 text-[#B91C1C]" /> : <CheckCircle2 className="w-3.5 h-3.5 text-[#15803D]" />}
                <span className="font-semibold">{r.event || r.type || "حدث"}</span>
                <span className="text-muted-foreground mr-auto">{fmtDate(r.at)}</span>
              </div>
            ))}
        </div>
      </div>

      <Dialog open={!!retry} onOpenChange={(o) => !o && setRetry(null)}>
        <DialogContent dir="rtl" className="max-w-md" data-testid="retry-dialog">
          <DialogHeader><DialogTitle>{retry?.all ? "إعادة معالجة كل الأحداث الفاشلة" : "إعادة معالجة الحدث"}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="text-xs text-muted-foreground">
              إعادة المعالجة عملية حسّاسة تتطلب سبباً ويُسجَّل باسمك في سجل التدقيق. التوقيع HMAC وآلية Idempotency تمنع تكرار القيود.
            </div>
            <div><Label className="text-xs">السبب (إلزامي)</Label>
              <Textarea rows={2} value={reason} data-testid="retry-reason" onChange={(e) => setReason(e.target.value)} /></div>
            <Button className="w-full bg-[#0A2540] hover:bg-[#061A2E]" data-testid="confirm-retry"
              disabled={busy || reason.trim().length < 3} onClick={doRetry}>تنفيذ إعادة المعالجة</Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

const Stat = ({ label, v, ok, danger, tid }) => (
  <div className="bg-white rounded-2xl border p-4 card-shadow" data-testid={tid}>
    <div className={`tabular text-2xl font-bold ${danger ? "text-[#B91C1C]" : ok ? "text-[#15803D]" : "text-[#0A2540]"}`}>{v}</div>
    <div className="text-[11px] text-muted-foreground mt-1">{label}</div>
  </div>
);
