import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/Layout";
import { money, equiv, fmtDate, PKG_TYPE } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { MapPin, Users, CalendarDays, Building2, Plane, Hotel, Plus, Trash2, ShoppingCart, Landmark, CheckCircle2, Bus, BedDouble, ListChecks } from "lucide-react";

const ROOM_AR = { double: "ثنائية", twin: "ثنائية", triple: "ثلاثية", quad: "رباعية", quint: "خماسية", single: "فردية" };
const TRANSPORT_AR = { bus: "باص", flight: "طيران", air: "طيران", train: "قطار", car: "سيارة" };
const roomAr = (v) => ROOM_AR[String(v || "").toLowerCase()] || v;
const transAr = (v) => TRANSPORT_AR[String(v || "").toLowerCase()] || v || "-";
import { toast } from "sonner";

export default function PackageDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [pkg, setPkg] = useState(null);
  const [open, setOpen] = useState(false);
  const [regs, setRegs] = useState([{ name: "", passport_no: "", age: "", category: "adult", photo: "" }]);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.get(`/packages/${id}`).then((r) => setPkg(r.data)).catch(() => toast.error("تعذّر تحميل البرنامج")); }, [id]);

  if (!pkg) return <div className="text-center py-20 text-muted-foreground">جارٍ التحميل...</div>;

  const isOwner = pkg.seller_id === user?.id;
  const isOffice = user?.role === "office";
  const CATS = {
    adult: { label: "بالغ", offered: true },
    child: { label: "طفل", offered: pkg.child_sale_price != null || pkg.child_net_cost != null },
    infant: { label: "رضيع", offered: pkg.infant_sale_price != null || pkg.infant_net_cost != null },
  };
  const setReg = (i, k) => (e) => { const c = [...regs]; c[i][k] = e.target.value; setRegs(c); };
  const addReg = (category = "adult") => setRegs([...regs, { name: "", passport_no: "", age: "", category, photo: "" }]);
  const rmReg = (i) => setRegs(regs.filter((_, x) => x !== i));
  const onPhoto = (i) => (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    if (file.size > 3 * 1024 * 1024) { toast.error("حجم الصورة يتجاوز 3 ميجابايت"); return; }
    const reader = new FileReader();
    reader.onload = () => { const c = [...regs]; c[i].photo = reader.result; setRegs(c); };
    reader.readAsDataURL(file);
  };

  // Per-traveler charge on the buyer's wallet, by category (child/infant fall back to adult if unset)
  const pick = (cat, childKey, infantKey, adultVal) =>
    cat === "child" ? (pkg[childKey] ?? adultVal) : cat === "infant" ? (pkg[infantKey] ?? adultVal) : adultVal;
  const chargeOf = (cat) => {
    if (isOffice) {
      const net = Number(pick(cat, "child_net_cost", "infant_net_cost", pkg.net_cost_per_seat || 0));
      const comm = Number(pick(cat, "child_commission", "infant_commission", pkg.buyer_office_commission || 0));
      return +(net + comm * 0.1).toFixed(2);
    }
    return +Number(pick(cat, "child_sale_price", "infant_sale_price", pkg.final_sale_price || 0)).toFixed(2);
  };

  const seats = regs.length;
  const required = +regs.reduce((s, r) => s + chargeOf(r.category), 0).toFixed(2);

  const book = async () => {
    setBusy(true);
    try {
      await api.post("/bookings", {
        package_id: id,
        registrants: regs.map((r) => ({ name: r.name, passport_no: r.passport_no, age: Number(r.age), category: r.category, photo: r.photo || undefined })),
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
              ? <img src={pkg.images[0]} alt={pkg.title} className="w-full h-full object-cover" data-testid="pkg-hero-image" />
              : <Landmark className="w-16 h-16 text-white/15" />}
          </div>
          {pkg.images?.length > 1 && (
            <div className="grid grid-cols-4 gap-3" data-testid="pkg-gallery">
              {pkg.images.slice(1, 5).map((src, i) => (
                <div key={i} className="rounded-xl overflow-hidden border h-20 bg-[#F4F6F8]">
                  <img src={src} alt={`${pkg.title} ${i + 2}`} className="w-full h-full object-cover" />
                </div>
              ))}
            </div>
          )}

          <div className="bg-white rounded-2xl border card-shadow p-6">
            <h3 className="font-head font-bold text-[#0A2540] mb-4">تفاصيل الرحلة</h3>
            <div className="grid sm:grid-cols-2 gap-4 text-sm">
              <Info icon={CalendarDays} label="تاريخ الانطلاق" value={fmtDate(pkg.departure_date)} />
              <Info icon={CalendarDays} label="تاريخ العودة" value={fmtDate(pkg.return_date)} />
              {pkg.departure_city && <Info icon={MapPin} label="مدينة الانطلاق" value={pkg.departure_city} />}
              <Info icon={Plane} label="النقل" value={transAr(pkg.transport)} />
              <Info icon={Users} label="المقاعد المتاحة" value={`${pkg.available_seats} / ${pkg.total_seats}`} />
              <Info icon={Building2} label="البائع" value={pkg.seller_office_name} />
            </div>
            {pkg.description && <p className="text-sm text-muted-foreground mt-5 leading-relaxed">{pkg.description}</p>}
          </div>

          {pkg.room_pricing?.length > 0 && (
            <div className="bg-white rounded-2xl border card-shadow p-6" data-testid="pkg-room-pricing">
              <h3 className="font-head font-bold text-[#0A2540] mb-4 flex items-center gap-2"><BedDouble className="w-4 h-4" /> أسعار الغرف</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-muted-foreground text-xs border-b"><tr>
                    <th className="text-start py-2">نوع الغرفة</th>
                    {isOffice && <th className="text-start py-2">الصافي</th>}
                    {isOffice && <th className="text-start py-2">العمولة</th>}
                    <th className="text-start py-2">سعر العميل</th>
                  </tr></thead>
                  <tbody>
                    {pkg.room_pricing.map((r, i) => (
                      <tr key={i} className="border-b last:border-0">
                        <td className="py-2 font-semibold text-[#0A2540]">{roomAr(r.room_type)}</td>
                        {isOffice && <td className="py-2 tabular">{money(r.net, pkg.currency)}</td>}
                        {isOffice && <td className="py-2 tabular text-[#15803D]">{money(r.commission, pkg.currency)}</td>}
                        <td className="py-2 tabular font-bold">{money(r.customer, pkg.currency)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {pkg.transports?.length > 0 && (
            <div className="bg-white rounded-2xl border card-shadow p-6" data-testid="pkg-transports">
              <h3 className="font-head font-bold text-[#0A2540] mb-4 flex items-center gap-2"><Bus className="w-4 h-4" /> النقل والمواصلات</h3>
              <div className="space-y-2 text-sm">
                {pkg.transports.map((t, i) => (
                  <div key={i} className="flex flex-wrap gap-x-4 gap-y-1 border-b last:border-0 pb-2 last:pb-0">
                    <span className="font-semibold text-[#0A2540]">{transAr(t.type || t.bus_type || t.name)}</span>
                    {t.company && <span className="text-muted-foreground">الشركة: {t.company}</span>}
                    {t.seats != null && <span className="text-muted-foreground">مقاعد: {t.seats}</span>}
                    {t.route && <span className="text-muted-foreground">المسار: {t.route}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {pkg.components?.length > 0 && (
            <div className="bg-white rounded-2xl border card-shadow p-6" data-testid="pkg-components">
              <h3 className="font-head font-bold text-[#0A2540] mb-4 flex items-center gap-2"><ListChecks className="w-4 h-4" /> مكونات البرنامج</h3>
              <div className="grid sm:grid-cols-2 gap-2 text-sm">
                {pkg.components.map((c, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#15803D] shrink-0 mt-0.5" />
                    <span className="text-[#0A2540]">{typeof c === "string" ? c : (c.name || c.title || c.label || JSON.stringify(c))}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

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
          {pkg.features?.length > 0 && (
            <div className="bg-white rounded-2xl border card-shadow p-6" data-testid="pkg-features">
              <h3 className="font-head font-bold text-[#0A2540] mb-4 flex items-center gap-2"><CheckCircle2 className="w-4 h-4" /> مميزات البرنامج</h3>
              <div className="grid sm:grid-cols-2 gap-3">
                {pkg.features.map((f, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <CheckCircle2 className="w-4 h-4 text-[#15803D] shrink-0 mt-0.5" />
                    <span className="text-[#0A2540]">{f}</span>
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
            {pkg.currency === "SAR" && <div className="text-xs text-muted-foreground tabular mt-0.5">{equiv(pkg.final_sale_price, "SAR")}</div>}
            {(CATS.child.offered || CATS.infant.offered) && (
              <div className="mt-3 space-y-1 text-xs bg-[#F4F6F8] rounded-lg p-3" data-testid="tier-prices">
                {CATS.child.offered && <div className="flex justify-between"><span className="text-muted-foreground">سعر الطفل</span><span className="tabular font-semibold">{money(chargeOf("child"), pkg.currency)}</span></div>}
                {CATS.infant.offered && <div className="flex justify-between"><span className="text-muted-foreground">سعر الرضيع</span><span className="tabular font-semibold">{money(chargeOf("infant"), pkg.currency)}</span></div>}
              </div>
            )}
            {isOffice && (
              <div className="mt-4 space-y-2 text-sm">
                <Row label="التكلفة الصافية (تدفعها أنت)" value={money(pkg.net_cost_per_seat, pkg.currency)} />
                <Row label="عمولتك كموزّع" value={money(pkg.buyer_office_commission, pkg.currency)} pos />
              </div>
            )}

            {isOwner ? (
              <div className="mt-5 text-center text-sm bg-[#F4F6F8] rounded-lg py-3 text-muted-foreground">هذا البرنامج من إضافتك</div>
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
                          <span className="text-xs font-semibold px-2 py-0.5 rounded bg-[#EFF6FF] text-[#1D4ED8]" data-testid={`reg-cat-${i}`}>{CATS[r.category]?.label || "بالغ"} — {money(chargeOf(r.category), pkg.currency)}</span>
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
                          {r.category === "infant" && (
                            <div className="col-span-2">
                              <Label className="mb-1.5 block text-xs">صورة الرضيع (اختياري)</Label>
                              <input type="file" accept="image/*" data-testid={`reg-photo-${i}`} onChange={onPhoto(i)}
                                     className="w-full text-xs file:me-2 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:bg-[#0A2540] file:text-white file:cursor-pointer" />
                              {r.photo && <span className="text-[11px] text-[#15803D] mt-1 inline-block">✓ تم إرفاق الصورة</span>}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                    <div className="flex flex-wrap gap-2">
                      <Button variant="outline" size="sm" onClick={() => addReg("adult")} data-testid="add-adult-btn"><Plus className="w-4 h-4" /> بالغ</Button>
                      {CATS.child.offered && <Button variant="outline" size="sm" onClick={() => addReg("child")} data-testid="add-child-btn"><Plus className="w-4 h-4" /> طفل</Button>}
                      {CATS.infant.offered && <Button variant="outline" size="sm" onClick={() => addReg("infant")} data-testid="add-infant-btn"><Plus className="w-4 h-4" /> رضيع</Button>}
                    </div>

                    <div className="bg-[#F4F6F8] rounded-xl p-4 text-sm space-y-2">
                      {["adult", "child", "infant"].map((cat) => {
                        const items = regs.filter((r) => r.category === cat);
                        if (items.length === 0) return null;
                        return <Row key={cat} label={`${CATS[cat].label} × ${items.length}`} value={money(items.length * chargeOf(cat), pkg.currency)} />;
                      })}
                      <div className="border-t pt-2 flex justify-between font-bold text-[#0A2540]">
                        <span>الإجمالي المخصوم من رصيدك المتاح</span>
                        <span className="tabular" data-testid="booking-total">{money(required, pkg.currency)}</span>
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
