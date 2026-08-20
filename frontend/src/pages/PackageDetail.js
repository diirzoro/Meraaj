import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate, PKG_TYPE } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { MapPin, Users, CalendarDays, Building2, Plane, Hotel, Plus, Trash2, ShoppingCart, Landmark } from "lucide-react";
import { toast } from "sonner";

export default function PackageDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [pkg, setPkg] = useState(null);
  const [open, setOpen] = useState(false);
  const [regs, setRegs] = useState([{ name: "", passport_no: "", age: "" }]);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.get(`/packages/${id}`).then((r) => setPkg(r.data)).catch(() => toast.error("تعذّر تحميل الباكج")); }, [id]);

  if (!pkg) return <div className="text-center py-20 text-muted-foreground">جارٍ التحميل...</div>;

  const isOwner = pkg.seller_id === user?.id;
  const isOffice = user?.role === "office";
  const setReg = (i, k) => (e) => { const c = [...regs]; c[i][k] = e.target.value; setRegs(c); };
  const addReg = () => setRegs([...regs, { name: "", passport_no: "", age: "" }]);
  const rmReg = (i) => setRegs(regs.filter((_, x) => x !== i));

  const seats = regs.length;
  const netTotal = (pkg.net_cost_per_seat || 0) * seats;
  const platformFee = isOffice ? +((pkg.buyer_office_commission || 0) * seats * 0.1).toFixed(2) : 0;
  const required = isOffice
    ? +(netTotal + platformFee).toFixed(2)
    : +((pkg.final_sale_price || 0) * seats).toFixed(2);

  const book = async () => {
    setBusy(true);
    try {
      await api.post("/bookings", {
        package_id: id,
        registrants: regs.map((r) => ({ name: r.name, passport_no: r.passport_no, age: Number(r.age) })),
        ref: localStorage.getItem("meraaj_ref") || undefined,
      });
      toast.success("تم إنشاء الحجز وتجميد الرصيد بنجاح");
      setOpen(false);
      navigate("/bookings");
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title={pkg.title} subtitle={`${PKG_TYPE[pkg.type] || pkg.type} • ${pkg.seller_office_name}`} />

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="rounded-2xl overflow-hidden border card-shadow h-72 bg-[#0A2540] flex items-center justify-center">
            {pkg.images?.[0]
              ? <img src={pkg.images[0]} alt={pkg.title} className="w-full h-full object-cover" />
              : <Landmark className="w-16 h-16 text-white/15" />}
          </div>

          <div className="bg-white rounded-2xl border card-shadow p-6">
            <h3 className="font-head font-bold text-[#0A2540] mb-4">تفاصيل الرحلة</h3>
            <div className="grid sm:grid-cols-2 gap-4 text-sm">
              <Info icon={CalendarDays} label="تاريخ الانطلاق" value={fmtDate(pkg.departure_date)} />
              <Info icon={CalendarDays} label="تاريخ العودة" value={fmtDate(pkg.return_date)} />
              <Info icon={MapPin} label="مدينة الانطلاق" value={pkg.departure_city || "-"} />
              <Info icon={Plane} label="النقل" value={pkg.transport || "-"} />
              <Info icon={Users} label="المقاعد المتاحة" value={`${pkg.available_seats} / ${pkg.total_seats}`} />
              <Info icon={Building2} label="البائع" value={pkg.seller_office_name} />
            </div>
            {pkg.description && <p className="text-sm text-muted-foreground mt-5 leading-relaxed">{pkg.description}</p>}
          </div>

          {pkg.hotels?.length > 0 && (
            <div className="bg-white rounded-2xl border card-shadow p-6">
              <h3 className="font-head font-bold text-[#0A2540] mb-4 flex items-center gap-2"><Hotel className="w-4 h-4" /> الفنادق</h3>
              <div className="space-y-3">
                {pkg.hotels.map((h, i) => (
                  <div key={i} className="flex items-center justify-between text-sm border-b last:border-0 pb-3 last:pb-0">
                    <div><span className="font-semibold">{h.name}</span> <span className="text-muted-foreground">— {h.city}</span></div>
                    <span className="text-muted-foreground">{h.nights} ليالٍ</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="space-y-5">
          <div className="bg-white rounded-2xl border card-shadow p-6 sticky top-8">
            <div className="text-sm text-muted-foreground">سعر البيع النهائي للزبون</div>
            <div className="tabular text-3xl font-bold text-[#0A2540] mt-1">{money(pkg.final_sale_price, pkg.currency)}</div>
            {isOffice && (
              <div className="mt-4 space-y-2 text-sm">
                <Row label="التكلفة الصافية (تدفعها أنت)" value={money(pkg.net_cost_per_seat, pkg.currency)} />
                <Row label="عمولتك كموزّع" value={money(pkg.buyer_office_commission, pkg.currency)} pos />
              </div>
            )}

            {isOwner ? (
              <div className="mt-5 text-center text-sm bg-[#F4F6F8] rounded-lg py-3 text-muted-foreground">هذا الباكج من إضافتك</div>
            ) : (
              <Dialog open={open} onOpenChange={setOpen}>
                <DialogTrigger asChild>
                  <Button data-testid="open-booking-btn" className="w-full mt-5 h-11 bg-[#0A2540] hover:bg-[#061A2E]">
                    <ShoppingCart className="w-4 h-4" /> احجز الآن
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" dir="rtl">
                  <DialogHeader><DialogTitle className="font-head text-[#0A2540]">تسجيل المعتمرين / المسافرين</DialogTitle></DialogHeader>
                  <div className="space-y-4">
                    {regs.map((r, i) => (
                      <div key={i} className="border rounded-xl p-4 relative">
                        <div className="flex items-center justify-between mb-3">
                          <span className="text-xs font-semibold text-muted-foreground">مسجّل #{i + 1}</span>
                          {regs.length > 1 && (
                            <button onClick={() => rmReg(i)} data-testid={`remove-reg-${i}`} className="text-destructive"><Trash2 className="w-4 h-4" /></button>
                          )}
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                          <div className="col-span-2">
                            <Label className="mb-1.5 block text-xs">الاسم الكامل</Label>
                            <Input data-testid={`reg-name-${i}`} value={r.name} onChange={setReg(i, "name")} />
                          </div>
                          <div>
                            <Label className="mb-1.5 block text-xs">رقم الجواز</Label>
                            <Input data-testid={`reg-passport-${i}`} value={r.passport_no} onChange={setReg(i, "passport_no")} />
                          </div>
                          <div>
                            <Label className="mb-1.5 block text-xs">العمر</Label>
                            <Input data-testid={`reg-age-${i}`} type="number" value={r.age} onChange={setReg(i, "age")} />
                          </div>
                        </div>
                      </div>
                    ))}
                    <Button variant="outline" onClick={addReg} data-testid="add-reg-btn" className="w-full"><Plus className="w-4 h-4" /> إضافة مسجّل</Button>

                    <div className="bg-[#F4F6F8] rounded-xl p-4 text-sm space-y-2">
                      {isOffice ? (
                        <>
                          <Row label={`التكلفة الصافية × ${seats}`} value={money(netTotal, pkg.currency)} />
                          <Row label="عمولة المنصة (10% من عمولتك)" value={money(platformFee, pkg.currency)} />
                        </>
                      ) : (
                        <Row label={`سعر البيع × ${seats}`} value={money((pkg.final_sale_price || 0) * seats, pkg.currency)} />
                      )}
                      <div className="border-t pt-2 flex justify-between font-bold text-[#0A2540]">
                        <span>الإجمالي المخصوم من رصيدك المتاح</span>
                        <span className="tabular">{money(required, pkg.currency)}</span>
                      </div>
                    </div>
                  </div>
                  <DialogFooter>
                    <Button data-testid="confirm-booking-btn" onClick={book} disabled={busy || regs.some((r) => !r.name || !r.passport_no || !r.age)}
                            className="w-full h-11 bg-[#0A2540] hover:bg-[#061A2E]">
                      {busy ? "جارٍ الحجز..." : `تأكيد الحجز — ${money(required, pkg.currency)}`}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

const Info = ({ icon: Icon, label, value }) => (
  <div className="flex items-center gap-3">
    <div className="w-9 h-9 rounded-lg bg-[#F4F6F8] flex items-center justify-center shrink-0"><Icon className="w-4 h-4 text-[#0A2540]" /></div>
    <div><div className="text-xs text-muted-foreground">{label}</div><div className="font-semibold text-[#0A2540]">{value}</div></div>
  </div>
);

const Row = ({ label, value, pos }) => (
  <div className="flex justify-between">
    <span className="text-muted-foreground">{label}</span>
    <span className={`tabular font-semibold ${pos ? "text-[#15803D]" : "text-[#0A2540]"}`}>{value}</span>
  </div>
);
