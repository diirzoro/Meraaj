import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Check, X, Upload, ExternalLink } from "lucide-react";

export default function AdminWithdrawals() {
  const [d, setD] = useState({ items: [], stages: [], stage_labels: {}, totals: {} });
  const [status, setStatus] = useState("pending");
  const [detail, setDetail] = useState(null);
  const [receipt, setReceipt] = useState({ receipt_url: "", reference: "" });
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get(`/admin/withdrawals/queue?status=${status}`).then((r) => setD(r.data));
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const open = async (id) => {
    const r = await api.get(`/admin/withdrawals/${id}/detail`);
    setDetail(r.data); setReceipt({ receipt_url: r.data.receipt_url || "", reference: r.data.bank_reference || "" });
    setNote("");
  };

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); load(); if (detail) await open(detail.id); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const stages = d.stages || [];

  return (
    <>
      <PageHeader title="دورة طلبات السحب" subtitle="طلب البائع ← مراجعة الإدارة ← اعتماد داخلي ← إحالة للمحاسبة ← تنفيذ التحويل ← رفع الإيصال ← إغلاق" />

      <div className="bg-white rounded-2xl border card-shadow p-4 mb-5 flex flex-wrap gap-3 items-center">
        <div className="flex rounded-lg border overflow-hidden">
          {[["pending", "المعلّقة"], ["approved", "المعتمدة"], ["all", "الكل"]].map(([v, l]) => (
            <button key={v} onClick={() => setStatus(v)} data-testid={`wd-status-${v}`}
              className={`px-3 h-9 text-xs font-semibold ${status === v ? "bg-[#0A2540] text-white" : "bg-white text-[#0A2540] hover:bg-[#F4F6F8]"}`}>{l}</button>
          ))}
        </div>
        <span className="text-xs text-muted-foreground mr-auto" data-testid="wd-totals">
          {d.items.length} طلب • {money(d.totals?.SAR || 0, "SAR")} + {money(d.totals?.USD || 0, "USD")}
        </span>
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto" data-testid="wd-table">
        <table className="w-full text-xs min-w-[820px]">
          <thead className="bg-[#F4F6F8] text-muted-foreground">
            <tr>{["التاريخ", "المكتب", "المبلغ", "الطريقة", "الحالة المالية", "مرحلة الدورة", "الإيصال", ""].map((h) => (
              <th key={h} className="text-right font-semibold px-3 py-2.5">{h}</th>))}</tr>
          </thead>
          <tbody>
            {d.items.length === 0 ? (
              <tr><td colSpan={8} className="text-center py-12 text-muted-foreground" data-testid="wd-empty">لا توجد طلبات</td></tr>
            ) : d.items.map((w) => (
              <tr key={w.id} className="border-t hover:bg-[#FAFBFC]" data-testid={`wd-row-${w.id}`}>
                <td className="px-3 py-2.5 whitespace-nowrap">{fmtDate(w.created_at)}</td>
                <td className="px-3 py-2.5 font-semibold text-[#0A2540]">{w.office_name}</td>
                <td className="px-3 py-2.5 tabular font-bold">{money(w.amount, w.currency)}</td>
                <td className="px-3 py-2.5">{w.method}</td>
                <td className="px-3 py-2.5">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full border ${w.status === "approved" ? "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]" : w.status === "rejected" ? "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" : "bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]"}`}>
                    {w.status === "approved" ? "معتمد" : w.status === "rejected" ? "مرفوض" : "معلّق"}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  <span className="text-[10px] px-2 py-0.5 rounded bg-[#F4F6F8] text-[#0A2540]">
                    {w.stage_index + 1}/{stages.length} — {w.stage_label}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  {w.receipt_url ? (
                    <a href={w.receipt_url} target="_blank" rel="noreferrer" className="text-[#0A2540] underline inline-flex items-center gap-1">
                      <ExternalLink className="w-3 h-3" /> عرض
                    </a>) : "—"}
                </td>
                <td className="px-3 py-2.5">
                  <button onClick={() => open(w.id)} data-testid={`wd-open-${w.id}`} className="text-[#0A2540] underline font-semibold">إدارة</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent dir="rtl" className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="wd-dialog">
          <DialogHeader><DialogTitle>طلب سحب — {detail?.office_name}</DialogTitle></DialogHeader>
          {detail && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-xs">
                <Box label="المبلغ" v={money(detail.amount, detail.currency)} />
                <Box label="رصيد المكتب المتاح" v={money(detail.office?.available || 0, detail.currency)} />
                <Box label="الطريقة" v={detail.method} />
                <Box label="البيانات" v={detail.details} />
              </div>

              {/* Stage stepper */}
              <div>
                <div className="text-xs font-semibold text-[#0A2540] mb-2">مراحل الدورة</div>
                <div className="space-y-1.5">
                  {stages.map((s, i) => {
                    const done = i <= (detail.stage ? stages.indexOf(detail.stage) : 0);
                    return (
                      <div key={s} className={`flex items-center justify-between text-xs rounded-lg px-3 py-1.5 border ${done ? "bg-[#F0FDF4] border-[#BBF7D0] text-[#15803D]" : "bg-[#F4F6F8] border-transparent text-muted-foreground"}`}>
                        <span>{i + 1}. {d.stage_labels[s]}</span>
                        {!done && (
                          <button disabled={busy} data-testid={`wd-stage-${s}`}
                            onClick={() => act(() => api.post(`/admin/withdrawals/${detail.id}/stage`, { stage: s, note }), "تم تحديث المرحلة")}
                            className="text-[10px] px-2 py-0.5 rounded bg-[#0A2540] text-white">انقل لهذه المرحلة</button>
                        )}
                      </div>
                    );
                  })}
                </div>
                <Textarea rows={2} placeholder="ملاحظة على المرحلة (اختياري)" value={note} data-testid="wd-stage-note"
                  onChange={(e) => setNote(e.target.value)} className="mt-2 text-xs" />
              </div>

              {/* Financial approval (existing engine, unchanged) */}
              {detail.status === "pending" && (
                <div className="flex gap-2">
                  <Button size="sm" className="bg-[#15803D] hover:bg-[#116632]" disabled={busy} data-testid="wd-approve"
                    onClick={() => act(() => api.post(`/admin/withdrawals/${detail.id}/review`, { approve: true }), "تم اعتماد السحب وخصم المبلغ")}>
                    <Check className="w-4 h-4" /> اعتماد مالي وتنفيذ الخصم
                  </Button>
                  <Button size="sm" variant="outline" className="text-red-600" disabled={busy} data-testid="wd-reject"
                    onClick={() => act(() => api.post(`/admin/withdrawals/${detail.id}/review`, { approve: false }), "تم رفض الطلب")}>
                    <X className="w-4 h-4" /> رفض
                  </Button>
                </div>
              )}

              {/* Receipt */}
              <div className="border-t pt-3">
                <div className="text-xs font-semibold text-[#0A2540] mb-2">إيصال التحويل</div>
                <Label className="text-xs">رابط الإيصال</Label>
                <Input value={receipt.receipt_url} data-testid="wd-receipt-url" className="h-8 text-xs"
                  onChange={(e) => setReceipt({ ...receipt, receipt_url: e.target.value })} />
                <Label className="text-xs mt-2 block">مرجع الحوالة البنكية</Label>
                <Input value={receipt.reference} data-testid="wd-receipt-ref" className="h-8 text-xs"
                  onChange={(e) => setReceipt({ ...receipt, reference: e.target.value })} />
                <Button size="sm" className="mt-2 bg-[#0A2540] hover:bg-[#061A2E]" data-testid="wd-receipt-save"
                  disabled={busy || receipt.receipt_url.trim().length < 5}
                  onClick={() => act(() => api.post(`/admin/withdrawals/${detail.id}/receipt`, receipt), "تم رفع الإيصال")}>
                  <Upload className="w-4 h-4" /> حفظ الإيصال
                </Button>
              </div>

              {/* History */}
              {(detail.stage_history || []).length > 0 && (
                <div className="border-t pt-3">
                  <div className="text-xs font-semibold text-[#0A2540] mb-2">سجل الدورة</div>
                  <div className="space-y-1.5">
                    {detail.stage_history.map((h, i) => (
                      <div key={i} className="text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-1.5">
                        {h.label} — {h.by} • {fmtDate(h.at)} {h.note ? `• ${h.note}` : ""}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

const Box = ({ label, v }) => (
  <div className="bg-[#F4F6F8] rounded-lg px-3 py-2">
    <div className="text-[10px] text-muted-foreground">{label}</div>
    <div className="tabular text-sm font-bold text-[#0A2540] break-words">{v}</div>
  </div>
);
