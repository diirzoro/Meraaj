import { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";

export default function AdminCancellations() {
  const [items, setItems] = useState([]);
  const load = () => api.get("/admin/cancellations").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);

  return (
    <>
      <PageHeader title="طلبات الإلغاء" subtitle="السلطة النهائية للبت في إلغاء الحجوزات المعتمدة وتسوية المبالغ المحجوزة" />
      {items.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground" data-testid="cancellations-empty">لا توجد طلبات إلغاء قيد المراجعة</div>
      ) : (
        <div className="space-y-4">
          {items.map((b) => (
            <div key={b.id} className="bg-white rounded-2xl border card-shadow p-5" data-testid={`cancellation-${b.id}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-head font-bold text-[#0A2540]">{b.package_title}</div>
                  <div className="text-xs text-muted-foreground mt-1">المشتري: {b.buyer_office_name} • البائع: {b.seller_office_name} • انطلاق {fmtDate(b.departure_date)}</div>
                </div>
                <span className="text-xs px-3 py-1 rounded-full bg-[#FEF2F2] text-[#B91C1C] border border-[#FECACA] font-semibold">طلب إلغاء</span>
              </div>

              {b.cancellation_reason && (
                <div className="bg-[#FEFCE8] border border-[#FEF08A] rounded-lg p-3 mt-4 text-sm text-[#A16207]">
                  <span className="font-semibold">سبب المشتري: </span>{b.cancellation_reason}
                </div>
              )}

              {b.cancellation_position && (
                <div className="bg-[#F4F6F8] rounded-lg p-3 mt-3 text-sm" data-testid={`position-${b.id}`}>
                  <span className="font-semibold text-[#0A2540]">موقف صاحب الباكيج: </span>{b.cancellation_position}
                  {b.actual_costs_total != null && <span className="block text-xs text-muted-foreground mt-1">تكاليف فعلية منفّذة: {money(b.actual_costs_total, b.currency)}</span>}
                </div>
              )}

              <div className="grid sm:grid-cols-3 gap-3 mt-4 text-sm">
                <Field label="المبلغ المحجوز (المدفوع)" value={money(b.amount_charged, b.currency)} />
                <Field label="التكلفة الصافية للبائع" value={money(b.net_cost_total, b.currency)} />
                <Field label="المقاعد" value={b.seats} />
              </div>

              <div className="mt-4 pt-4 border-t">
                <DecisionDialog booking={b} onDone={load} />
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function DecisionDialog({ booking, onDone }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const original = Number(booking.amount_charged || 0);
  const net = Number(booking.net_cost_total || 0);
  const [decision, setDecision] = useState("cancelled");
  const [refund, setRefund] = useState(String(original));
  const [comp, setComp] = useState("0");
  const [reason, setReason] = useState("");

  const r2 = (x) => Math.round((Number(x) || 0) * 100) / 100;
  const refundN = r2(refund);
  const compN = r2(comp);
  const platformAdj = r2(original - refundN - compN);
  const valid = decision === "kept" || (refundN >= 0 && compN >= 0 && platformAdj >= -0.01);

  const preset = (kind) => {
    if (kind === "full") { setDecision("cancelled"); setRefund(String(r2(original))); setComp("0"); }
    if (kind === "partial") { setDecision("cancelled"); setRefund(String(r2(original - net))); setComp(String(r2(net))); }
    if (kind === "keep") { setDecision("kept"); }
  };

  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/admin/bookings/${booking.id}/cancellation-decision`, {
        decision,
        refund_amount: decision === "cancelled" ? refundN : 0,
        seller_compensation: decision === "cancelled" ? compN : 0,
        reason,
      });
      toast.success(decision === "cancelled" ? "تم إلغاء الحجز وتسوية المبالغ" : "تم إبقاء الحجز نشطاً");
      setOpen(false); onDone();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="bg-[#0A2540] hover:bg-[#061A2E]" size="sm" data-testid={`decide-${booking.id}`}>البت في طلب الإلغاء</Button>
      </DialogTrigger>
      <DialogContent dir="rtl" className="max-h-[90vh] overflow-y-auto">
        <DialogHeader><DialogTitle className="font-head text-[#0A2540]">قرار الإلغاء — {booking.package_title}</DialogTitle></DialogHeader>

        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" onClick={() => preset("full")} data-testid="preset-full">استرداد كامل</Button>
          <Button type="button" size="sm" variant="outline" onClick={() => preset("partial")} data-testid="preset-partial">استرداد جزئي (خصم التكلفة)</Button>
          <Button type="button" size="sm" variant="outline" onClick={() => preset("keep")} data-testid="preset-keep">إبقاء الحجز</Button>
        </div>

        <div className="mt-2">
          <Label className="mb-2 block">القرار</Label>
          <select data-testid="decision-select" value={decision} onChange={(e) => setDecision(e.target.value)}
            className="w-full h-9 rounded-md border border-input bg-transparent px-3 text-sm">
            <option value="cancelled">إلغاء الحجز وتسوية المبالغ</option>
            <option value="kept">إبقاء الحجز نشطاً</option>
          </select>
        </div>

        {decision === "cancelled" && (
          <div className="space-y-3 mt-1">
            <div>
              <Label className="mb-2 block">استرداد المشتري (المبلغ المحجوز {money(original, booking.currency)})</Label>
              <Input data-testid="refund-input" type="number" value={refund} onChange={(e) => setRefund(e.target.value)} />
            </div>
            <div>
              <Label className="mb-2 block">تعويض البائع</Label>
              <Input data-testid="comp-input" type="number" value={comp} onChange={(e) => setComp(e.target.value)} />
            </div>
            <div className={`rounded-lg p-3 text-sm ${valid ? "bg-[#F0FDF4] text-[#15803D]" : "bg-red-50 text-red-600"}`} data-testid="platform-adj">
              تسوية المنصة (المتبقّي): <span className="tabular font-bold">{money(platformAdj, booking.currency)}</span>
              {!valid && <div className="text-xs mt-1">المجموع يجب ألا يتجاوز المبلغ المحجوز والقيم غير سالبة.</div>}
            </div>
          </div>
        )}

        <div>
          <Label className="mb-2 block">سبب/ملاحظة القرار</Label>
          <Textarea data-testid="decision-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={3} />
        </div>

        <DialogFooter>
          <Button className="bg-[#0A2540] hover:bg-[#061A2E]" onClick={submit} disabled={busy || !valid} data-testid="submit-decision-btn">
            {busy ? "جارٍ التنفيذ..." : "تأكيد القرار"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const Field = ({ label, value }) => (
  <div className="bg-[#F4F6F8] rounded-lg px-4 py-3">
    <div className="text-xs text-muted-foreground">{label}</div>
    <div className="tabular font-bold text-[#0A2540]">{value}</div>
  </div>
);
