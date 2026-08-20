import { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { FileText, XCircle, AlertTriangle, Download } from "lucide-react";
import { toast } from "sonner";

export default function Bookings() {
  const [items, setItems] = useState([]);
  const [sel, setSel] = useState(null);

  const load = () => api.get("/bookings?role=buyer").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);

  const cancelReq = async (b) => {
    try {
      const { data } = await api.post(`/bookings/${b.id}/cancel-request`);
      toast.success(data.status === "cancelled" ? `تم الإلغاء واسترداد ${money(data.refund)}` : "أُرسل طلب الإلغاء للبائع");
      load();
    } catch (e) { toast.error(apiError(e)); }
  };

  const acceptOffer = async (b) => {
    try { const { data } = await api.post(`/bookings/${b.id}/cancel-accept`); toast.success(`تم الإلغاء واسترداد ${money(data.refund)}`); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  const dispute = async (b, reason) => {
    try { await api.post(`/bookings/${b.id}/dispute`, { reason }); toast.success("تم فتح نزاع، ستراجعه الإدارة"); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  return (
    <>
      <PageHeader title="حجوزاتي (كمشتري)" subtitle="متابعة الحجوزات التي اشتريتها من السوق" />
      {items.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">لا توجد حجوزات</div>
      ) : (
        <div className="space-y-4">
          {items.map((b) => (
            <div key={b.id} className="bg-white rounded-2xl border card-shadow p-5" data-testid={`booking-${b.id}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-head font-bold text-[#0A2540]">{b.package_title}</div>
                  <div className="text-xs text-muted-foreground mt-1">البائع: {b.seller_office_name} • انطلاق {fmtDate(b.departure_date)}</div>
                </div>
                <StatusBadge status={b.status} />
              </div>

              <div className="grid sm:grid-cols-3 gap-3 mt-4 text-sm">
                <Field label="المقاعد" value={b.seats} />
                <Field label="المبلغ المدفوع" value={money(b.amount_charged, b.currency)} />
                <Field label="عمولتك المتوقعة" value={money(b.buyer_commission_total, b.currency)} pos />
              </div>

              <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t">
                <Button variant="outline" size="sm" onClick={() => setSel(b)} data-testid={`view-booking-${b.id}`}>
                  <FileText className="w-4 h-4" /> المسجّلون والتأشيرات
                </Button>

                {(b.status === "blue") && (
                  <Button variant="destructive" size="sm" onClick={() => cancelReq(b)} data-testid={`cancel-${b.id}`}>
                    <XCircle className="w-4 h-4" /> طلب إلغاء
                  </Button>
                )}
                {b.status === "yellow" && !b.cancellation && (
                  <Button variant="destructive" size="sm" onClick={() => cancelReq(b)} data-testid={`cancel-${b.id}`}>
                    <XCircle className="w-4 h-4" /> طلب إلغاء
                  </Button>
                )}
                {b.cancellation?.stage === "awaiting_buyer" && (
                  <Button size="sm" className="bg-[#A16207] hover:bg-[#854d0e]" onClick={() => acceptOffer(b)} data-testid={`accept-offer-${b.id}`}>
                    قبول خصم {money(b.cancellation.deduction, b.currency)} والإلغاء
                  </Button>
                )}
                {b.status === "green" && !b.settled && !b.dispute && (
                  <DisputeDialog booking={b} onSubmit={dispute} />
                )}
                {b.dispute && <span className="text-xs text-[#A16207] flex items-center gap-1 self-center"><AlertTriangle className="w-3.5 h-3.5" /> نزاع {b.dispute.status === "open" ? "مفتوح" : "مُغلق"}</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      <RegistrantsDialog booking={sel} onClose={() => setSel(null)} />
    </>
  );
}

function DisputeDialog({ booking, onSubmit }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" data-testid={`dispute-${booking.id}`}><AlertTriangle className="w-4 h-4" /> فتح نزاع (خلال 24 ساعة)</Button>
      </DialogTrigger>
      <DialogContent dir="rtl">
        <DialogHeader><DialogTitle className="font-head text-[#0A2540]">فتح طلب نزاع</DialogTitle></DialogHeader>
        <Label className="mb-2 block">سبب الاعتراض</Label>
        <Textarea data-testid="dispute-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={4} />
        <DialogFooter>
          <Button className="bg-[#0A2540] hover:bg-[#061A2E]" data-testid="submit-dispute-btn"
                  onClick={() => { onSubmit(booking, reason); setOpen(false); }} disabled={!reason}>إرسال النزاع</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RegistrantsDialog({ booking, onClose }) {
  if (!booking) return null;
  return (
    <Dialog open={!!booking} onOpenChange={onClose}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" dir="rtl">
        <DialogHeader><DialogTitle className="font-head text-[#0A2540]">المسجّلون والتأشيرات</DialogTitle></DialogHeader>
        <div className="space-y-3">
          {booking.registrants.map((r, i) => (
            <div key={i} className="border rounded-xl p-4 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-semibold">{r.name}</span>
                <span className="text-xs text-muted-foreground">العمر {r.age}</span>
              </div>
              <div className="text-xs text-muted-foreground mt-1">جواز: {r.passport_no}</div>
              <div className="mt-2 flex items-center justify-between">
                <span className="text-xs">التأشيرة: <span className="font-semibold">{r.visa_no || "لم تُصدر بعد"}</span></span>
                {r.visa_file && <a href={r.visa_file} target="_blank" rel="noreferrer" className="text-xs text-[#0A2540] flex items-center gap-1 hover:underline"><Download className="w-3.5 h-3.5" /> ملف التأشيرة</a>}
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

const Field = ({ label, value, pos }) => (
  <div className="bg-[#F4F6F8] rounded-lg px-4 py-3">
    <div className="text-xs text-muted-foreground">{label}</div>
    <div className={`tabular font-bold ${pos ? "text-[#15803D]" : "text-[#0A2540]"}`}>{value}</div>
  </div>
);
