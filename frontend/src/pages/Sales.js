import { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { Stamp, Plane, CheckCircle2, Banknote } from "lucide-react";
import { toast } from "sonner";

export default function Sales() {
  const [items, setItems] = useState([]);
  const load = () => api.get("/bookings?role=seller").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);

  const dispatch = async (b) => {
    try { await api.post(`/bookings/${b.id}/dispatch`); toast.success("تم التفويج — بدأت فترة السماح 24 ساعة"); load(); }
    catch (e) { toast.error(apiError(e)); }
  };
  const settle = async (b) => {
    try { const { data } = await api.post(`/bookings/${b.id}/settle`); toast.success(`تمت التسوية — أُضيف ${money(data.released)} لرصيدك المتاح`); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  return (
    <>
      <PageHeader title="مبيعاتي (كبائع)" subtitle="إدارة الحجوزات على باكجاتك ودورة حياتها" />
      {items.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">لا توجد مبيعات بعد</div>
      ) : (
        <div className="space-y-4">
          {items.map((b) => (
            <div key={b.id} className="bg-white rounded-2xl border card-shadow p-5" data-testid={`sale-${b.id}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-head font-bold text-[#0A2540]">{b.package_title}</div>
                  <div className="text-xs text-muted-foreground mt-1">المشتري: {b.buyer_office_name} • انطلاق {fmtDate(b.departure_date)}</div>
                </div>
                <StatusBadge status={b.status} />
              </div>

              <div className="grid sm:grid-cols-3 gap-3 mt-4 text-sm">
                <Field label="المقاعد" value={b.seats} />
                <Field label="إيراد معلّق" value={money(b.net_cost_total, b.currency)} />
                <Field label="عمولة المنصة عند التسوية" value={money(b.platform_fee, b.currency)} />
              </div>

              <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t">
                {b.status === "blue" && <IssueVisasDialog booking={b} onDone={load} />}
                {b.status === "yellow" && (
                  <Button size="sm" className="bg-[#15803D] hover:bg-[#166534]" onClick={() => dispatch(b)} data-testid={`dispatch-${b.id}`}>
                    <Plane className="w-4 h-4 rtl:rotate-180" /> تم التفويج
                  </Button>
                )}
                {b.status === "green" && !b.settled && !b.dispute && (
                  <Button size="sm" variant="outline" onClick={() => settle(b)} data-testid={`settle-${b.id}`}>
                    <Banknote className="w-4 h-4" /> تسوية الرصيد (بعد 24 ساعة)
                  </Button>
                )}
                {b.cancellation?.stage === "awaiting_seller" && <CancelOfferDialog booking={b} onDone={load} />}
                {b.settled && <span className="text-xs text-[#15803D] flex items-center gap-1 self-center"><CheckCircle2 className="w-3.5 h-3.5" /> تمت التسوية</span>}
                {b.dispute && <span className="text-xs text-[#A16207] self-center">نزاع قيد المراجعة من الإدارة</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function IssueVisasDialog({ booking, onDone }) {
  const [open, setOpen] = useState(false);
  const [visas, setVisas] = useState(booking.registrants.map(() => ({ visa_no: "", visa_file: "" })));
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/bookings/${booking.id}/issue-visas`, {
        visas: visas.map((v, i) => ({ index: i, visa_no: v.visa_no, visa_file: v.visa_file || null })),
      });
      toast.success("تم إصدار التأشيرات — الحالة أصبحت صفراء");
      setOpen(false); onDone();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="bg-[#A16207] hover:bg-[#854d0e]" data-testid={`issue-visas-${booking.id}`}><Stamp className="w-4 h-4" /> إصدار التأشيرات</Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" dir="rtl">
        <DialogHeader><DialogTitle className="font-head text-[#0A2540]">إدخال أرقام التأشيرات (إجباري لكل مسجّل)</DialogTitle></DialogHeader>
        <div className="space-y-3">
          {booking.registrants.map((r, i) => (
            <div key={i} className="border rounded-xl p-4">
              <div className="text-sm font-semibold mb-2">{r.name} <span className="text-xs text-muted-foreground">— جواز {r.passport_no}</span></div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="mb-1.5 block text-xs">رقم التأشيرة *</Label>
                  <Input data-testid={`visa-no-${i}`} value={visas[i].visa_no} onChange={(e) => { const c = [...visas]; c[i].visa_no = e.target.value; setVisas(c); }} />
                </div>
                <div>
                  <Label className="mb-1.5 block text-xs">رابط ملف التأشيرة (اختياري)</Label>
                  <Input data-testid={`visa-file-${i}`} value={visas[i].visa_file} onChange={(e) => { const c = [...visas]; c[i].visa_file = e.target.value; setVisas(c); }} placeholder="https://..." />
                </div>
              </div>
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button className="bg-[#0A2540] hover:bg-[#061A2E]" data-testid={`confirm-visas-${booking.id}`}
                  onClick={submit} disabled={busy || visas.some((v) => !v.visa_no)}>
            {busy ? "جارٍ الحفظ..." : "تأكيد وتحويل للأصفر"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CancelOfferDialog({ booking, onDone }) {
  const [open, setOpen] = useState(false);
  const [deduction, setDeduction] = useState("");
  const submit = async () => {
    try {
      await api.post(`/bookings/${booking.id}/cancel-offer`, { deduction: Number(deduction) });
      toast.success("أُرسل عرض الخصم للمشتري");
      setOpen(false); onDone();
    } catch (e) { toast.error(apiError(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="destructive" data-testid={`cancel-offer-${booking.id}`}>الرد على طلب الإلغاء</Button>
      </DialogTrigger>
      <DialogContent dir="rtl">
        <DialogHeader><DialogTitle className="font-head text-[#0A2540]">تحديد المبلغ غير المسترد (قيمة التأشيرات)</DialogTitle></DialogHeader>
        <Label className="mb-2 block">المبلغ المراد خصمه</Label>
        <Input data-testid="deduction-input" type="number" value={deduction} onChange={(e) => setDeduction(e.target.value)} />
        <DialogFooter>
          <Button className="bg-[#0A2540] hover:bg-[#061A2E]" onClick={submit} disabled={!deduction} data-testid="submit-deduction-btn">إرسال العرض للمشتري</Button>
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
