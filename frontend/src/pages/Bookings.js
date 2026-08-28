import { useEffect, useMemo, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
import StatusBadge, { ApprovalBadge, CancellationBadge } from "@/components/StatusBadge";
import Timeline from "@/components/Timeline";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { FileText, XCircle, AlertTriangle, Download, History, Undo2, Search } from "lucide-react";
import { toast } from "sonner";

const isRahal = (b) => b.approval_status != null;
const catOf = (b) => {
  if (b.approval_status === "pending") return "pending";
  if (b.status === "cancelled" || ["rejected", "expired"].includes(b.approval_status)) return "cancelled";
  return "active";
};
const TABS = [["pending", "قيد الموافقة"], ["active", "نشطة"], ["cancelled", "ملغاة"], ["all", "الكل"]];

export default function Bookings() {
  const [items, setItems] = useState([]);
  const [sel, setSel] = useState(null);
  const [tab, setTab] = useState("all");
  const [q, setQ] = useState("");
  const [tl, setTl] = useState(null);

  const load = () => api.get("/bookings?role=buyer").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);

  const counts = useMemo(() => {
    const c = { pending: 0, active: 0, cancelled: 0, all: items.length };
    items.forEach((b) => { c[catOf(b)] += 1; });
    return c;
  }, [items]);

  const view = useMemo(() => {
    let v = tab === "all" ? items : items.filter((b) => catOf(b) === tab);
    if (q.trim()) {
      const s = q.trim();
      v = v.filter((b) => (b.package_title || "").includes(s) || (b.seller_office_name || "").includes(s));
    }
    return v;
  }, [items, tab, q]);

  const cancelReq = async (b) => {
    try {
      const { data } = await api.post(`/bookings/${b.id}/cancel-request`);
      toast.success(data.status === "cancelled" ? `تم الإلغاء واسترداد ${money(data.refund, b.currency)}` : "أُرسل طلب الإلغاء للبائع");
      load();
    } catch (e) { toast.error(apiError(e)); }
  };

  const withdraw = async (b) => {
    try {
      const { data } = await api.post(`/bookings/${b.id}/cancel-request`);
      toast.success(`تم سحب الطلب واسترداد ${money(data.refund, b.currency)}`);
      load();
    } catch (e) { toast.error(apiError(e)); }
  };

  const requestApprovedCancel = async (b, reason) => {
    try {
      await api.post(`/bookings/${b.id}/cancel-request`, { reason });
      toast.success("أُرسل طلب الإلغاء إلى الإدارة للبت النهائي");
      load();
    } catch (e) { toast.error(apiError(e)); }
  };

  const acceptOffer = async (b) => {
    try { const { data } = await api.post(`/bookings/${b.id}/cancel-accept`); toast.success(`تم الإلغاء واسترداد ${money(data.refund, b.currency)}`); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  const dispute = async (b, reason) => {
    try { await api.post(`/bookings/${b.id}/dispute`, { reason }); toast.success("تم فتح نزاع، ستراجعه الإدارة"); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  return (
    <>
      <PageHeader title="حجوزاتي (كمشتري)" subtitle="متابعة الحجوزات التي اشتريتها من السوق ودورة حياتها" />

      <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-5">
        <div className="flex gap-1 bg-white border rounded-xl p-1 card-shadow w-fit overflow-x-auto">
          {TABS.map(([k, l]) => (
            <button key={k} onClick={() => setTab(k)} data-testid={`bookings-tab-${k}`}
              className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${tab === k ? "bg-[#0A2540] text-white" : "text-muted-foreground hover:text-[#0A2540]"}`}>
              {l} <span className={`ms-1 tabular ${tab === k ? "text-[#D4AF37]" : "text-[#0A2540]/60"}`}>{counts[k]}</span>
            </button>
          ))}
        </div>
        <div className="relative sm:ms-auto sm:w-64">
          <Search className="w-4 h-4 absolute top-1/2 -translate-y-1/2 start-3 text-muted-foreground" />
          <Input data-testid="bookings-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="بحث بالبرنامج أو البائع" className="ps-9" />
        </div>
      </div>

      {view.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground" data-testid="bookings-empty">لا توجد حجوزات في هذا التبويب</div>
      ) : (
        <div className="space-y-4">
          {view.map((b) => (
            <div key={b.id} className="bg-white rounded-2xl border card-shadow p-5" data-testid={`booking-${b.id}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-head font-bold text-[#0A2540]">{b.package_title}</div>
                  <div className="text-xs text-muted-foreground mt-1">البائع: {b.seller_office_name} • انطلاق {fmtDate(b.departure_date)}</div>
                </div>
                <div className="flex flex-wrap gap-2 justify-end">
                  {isRahal(b) && b.approval_status !== "approved" && <ApprovalBadge status={b.approval_status} />}
                  <StatusBadge status={b.status} />
                  {b.cancellation_status && b.cancellation_status !== "none" && <CancellationBadge status={b.cancellation_status} />}
                </div>
              </div>

              <div className="grid sm:grid-cols-3 gap-3 mt-4 text-sm">
                <Field label="المقاعد" value={b.seats} />
                <Field label="المبلغ المدفوع" value={money(b.amount_charged, b.currency)} />
                <Field label="عمولتك المتوقعة" value={money(b.buyer_commission_total, b.currency)} pos />
              </div>

              {b.cancellation_final && (
                <div className="bg-[#F4F6F8] rounded-lg p-3 mt-3 text-xs text-[#0A2540]" data-testid={`cancel-final-${b.id}`}>
                  <span className="font-semibold">قرار الإدارة: </span>
                  {b.cancellation_final.decision === "cancelled" ? "تم الإلغاء" : "تم إبقاء الحجز"}
                  {b.cancellation_final.decision === "cancelled" && ` • استرداد ${money(b.cancellation_final.refund_amount, b.currency)}`}
                </div>
              )}

              <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t">
                <Button variant="outline" size="sm" onClick={() => setSel(b)} data-testid={`view-booking-${b.id}`}>
                  <FileText className="w-4 h-4" /> المسجّلون والتأشيرات
                </Button>
                <Button variant="outline" size="sm" onClick={() => setTl(b)} data-testid={`timeline-btn-${b.id}`}>
                  <History className="w-4 h-4" /> السجل الزمني
                </Button>

                {/* rahal pending → withdraw (full unwind) */}
                {isRahal(b) && b.approval_status === "pending" && (
                  <Button variant="destructive" size="sm" onClick={() => withdraw(b)} data-testid={`withdraw-${b.id}`}>
                    <Undo2 className="w-4 h-4" /> سحب الطلب
                  </Button>
                )}
                {/* rahal approved → request cancellation (Super Admin decides) */}
                {isRahal(b) && b.approval_status === "approved" && (!b.cancellation_status || b.cancellation_status === "none") && b.status !== "cancelled" && (
                  <ApprovedCancelDialog booking={b} onSubmit={requestApprovedCancel} />
                )}

                {/* legacy / manual bookings */}
                {!isRahal(b) && b.status === "blue" && (
                  <Button variant="destructive" size="sm" onClick={() => cancelReq(b)} data-testid={`cancel-${b.id}`}>
                    <XCircle className="w-4 h-4" /> طلب إلغاء
                  </Button>
                )}
                {!isRahal(b) && b.status === "yellow" && !b.cancellation && (
                  <Button variant="destructive" size="sm" onClick={() => cancelReq(b)} data-testid={`cancel-${b.id}`}>
                    <XCircle className="w-4 h-4" /> طلب إلغاء
                  </Button>
                )}
                {b.cancellation?.stage === "awaiting_buyer" && (
                  <Button size="sm" className="bg-[#A16207] hover:bg-[#854d0e]" onClick={() => acceptOffer(b)} data-testid={`accept-offer-${b.id}`}>
                    قبول خصم {money(b.cancellation.deduction, b.currency)} والإلغاء
                  </Button>
                )}
                {b.status === "green" && !b.settled && !b.dispute && <DisputeDialog booking={b} onSubmit={dispute} />}
                {b.dispute && <span className="text-xs text-[#A16207] flex items-center gap-1 self-center"><AlertTriangle className="w-3.5 h-3.5" /> نزاع {b.dispute.status === "open" ? "مفتوح" : "مُغلق"}</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      <RegistrantsDialog booking={sel} onClose={() => setSel(null)} />
      <TimelineDialog booking={tl} onClose={() => setTl(null)} />
    </>
  );
}

function ApprovedCancelDialog({ booking, onSubmit }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="destructive" size="sm" data-testid={`request-cancel-${booking.id}`}><XCircle className="w-4 h-4" /> طلب إلغاء</Button>
      </DialogTrigger>
      <DialogContent dir="rtl">
        <DialogHeader><DialogTitle className="font-head text-[#0A2540]">طلب إلغاء حجز معتمد</DialogTitle></DialogHeader>
        <p className="text-sm text-muted-foreground -mt-2 mb-1">سيُرفع الطلب للإدارة للبت النهائي في المبالغ (لن يُسترد المبلغ تلقائياً).</p>
        <Label className="mb-2 block">سبب الإلغاء</Label>
        <Textarea data-testid="cancel-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={4} />
        <DialogFooter>
          <Button className="bg-[#0A2540] hover:bg-[#061A2E]" data-testid="submit-cancel-request-btn"
            onClick={() => { onSubmit(booking, reason); setOpen(false); setReason(""); }} disabled={!reason}>إرسال الطلب للإدارة</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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

function TimelineDialog({ booking, onClose }) {
  if (!booking) return null;
  return (
    <Dialog open={!!booking} onOpenChange={onClose}>
      <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto" dir="rtl" data-testid="timeline-dialog">
        <DialogHeader><DialogTitle className="font-head text-[#0A2540]">السجل الزمني للحجز</DialogTitle></DialogHeader>
        <Timeline bookingId={booking.id} />
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
