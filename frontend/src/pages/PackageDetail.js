import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/Layout";
import { PkgImage } from "@/components/PkgImage";
import { money, equiv, fmtDate, PKG_TYPE, roomCustomer } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { MapPin, Users, CalendarDays, Building2, Plane, Hotel, Plus, Trash2, ShoppingCart, CheckCircle2, Bus, BedDouble, ListChecks, Share2, Paperclip, X } from "lucide-react";
import { DOC_TYPES, docLabel } from "@/components/TravelerDocs";

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
  const [regs, setRegs] = useState([{ name: "", passport_no: "", age: "", category: "adult", photo: "", docs: [] }]);
  const [busy, setBusy] = useState(false);
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [docType, setDocType] = useState({});
  const [progress, setProgress] = useState(null);

  useEffect(() => {
    api.get(`/packages/${id}`).then((r) => {
      setPkg(r.data);
      if (r.data?.room_pricing?.length) setSelectedRoom(r.data.room_pricing[0].room_type);
    }).catch(() => toast.error("تعذّر تحميل البرنامج"));
  }, [id]);

  if (!pkg) return <div className="text-center py-20 text-muted-foreground">جارٍ التحميل...</div>;

  const isOwner = pkg.seller_id === user?.id;
  const isOffice = user?.role === "office";
  const selRoom = (pkg.room_pricing || []).find((r) => r.room_type === selectedRoom) || null;
  const roomHas = (cat) => (selRoom ? roomCustomer(selRoom.customer, cat) != null : false);
  const CATS = {
    adult: { label: "بالغ", offered: true },
    child: { label: "طفل", offered: pkg.child_sale_price != null || pkg.child_net_cost != null || roomHas("child") },
    infant: { label: "رضيع", offered: pkg.infant_sale_price != null || pkg.infant_net_cost != null || roomHas("infant") },
  };
  const setReg = (i, k) => (e) => { const c = [...regs]; c[i][k] = e.target.value; setRegs(c); };
  const addReg = (category = "adult") => setRegs([...regs, { name: "", passport_no: "", age: "", category, photo: "", docs: [] }]);
  const rmReg = (i) => setRegs(regs.filter((_, x) => x !== i));
  const stageDocs = (i) => async (e) => {
    const files = Array.from(e.target.files || []); e.target.value = "";
    if (!files.length) return;
    const dt = docType[i] || "passport";
    const added = [];
    for (const file of files) {
      if (file.size > 20 * 1024 * 1024) { toast.error(`${file.name}: يتجاوز 20 ميجابايت`); continue; }
      const b64 = await new Promise((res, rej) => { const rd = new FileReader(); rd.onload = () => res(rd.result); rd.onerror = rej; rd.readAsDataURL(file); });
      added.push({ doc_type: dt, filename: file.name, content_base64: b64 });
    }
    const c = [...regs]; c[i].docs = [...(c[i].docs || []), ...added]; setRegs(c);
  };
  const rmDoc = (i, di) => { const c = [...regs]; c[i].docs = c[i].docs.filter((_, x) => x !== di); setRegs(c); };
  const onPhoto = (i) => (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    if (file.size > 20 * 1024 * 1024) { toast.error("حجم الصورة يتجاوز 20 ميجابايت"); return; }
    const reader = new FileReader();
    reader.onload = () => { const c = [...regs]; c[i].photo = reader.result; setRegs(c); };
    reader.readAsDataURL(file);
  };

  // Per-traveler charge on the buyer's wallet, by category (child/infant fall back to adult if unset)
  const pick = (cat, childKey, infantKey, adultVal) =>
    cat === "child" ? (pkg[childKey] ?? adultVal) : cat === "infant" ? (pkg[infantKey] ?? adultVal) : adultVal;
  const chargeOf = (cat) => {
    if (isOffice) {
      const net = roomCustomer(selRoom?.net, cat)
        ?? Number(pick(cat, "child_net_cost", "infant_net_cost", pkg.net_cost_per_seat || 0));
      const comm = roomCustomer(selRoom?.commission, cat)
        ?? Number(pick(cat, "child_commission", "infant_commission", pkg.buyer_office_commission || 0));
      const v = Number(net) + Number(comm) * 0.1;
      return Number.isNaN(v) ? 0 : +v.toFixed(2);
    }
    const rc = selRoom ? roomCustomer(selRoom.customer, cat) : null;
    if (rc != null) return +Number(rc).toFixed(2);
    const f = Number(pick(cat, "child_sale_price", "infant_sale_price", pkg.final_sale_price || 0));
    return Number.isNaN(f) ? 0 : +f.toFixed(2);
  };

  const shareTrip = async () => {
    const link = `${window.location.origin}/market/${id}?ref=${user.id}`;
    const price = roomCustomer(pkg.room_pricing?.[0]?.customer, "adult") || Number(pkg.final_sale_price) || 0;
    const text = [
      `🕋 ${pkg.title}`,
      pkg.route ? `🚌 المسار: ${pkg.route}` : "",
      `📅 ${fmtDate(pkg.departure_date)} ← ${fmtDate(pkg.return_date)}`,
      pkg.features?.length ? `✨ ${pkg.features.join("، ")}` : "",
      `💰 يبدأ من ${money(price, pkg.currency)}`,
      `🔗 احجز الآن عبر رابطي: ${link}`,
    ].filter(Boolean).join("\n");
    try {
      if (navigator.share) await navigator.share({ title: pkg.title, text });
      else { await navigator.clipboard.writeText(text); toast.success("تم نسخ نص المشاركة مع رابطك المخصص"); }
    } catch { /* user cancelled */ }
  };

  const seats = regs.length;
  const required = +regs.reduce((s, r) => s + chargeOf(r.category), 0).toFixed(2);

  const book = async () => {
    setBusy(true);
    try {
      const { data: created } = await api.post("/bookings", {
        package_id: id,
        room_type: selectedRoom || undefined,
        registrants: regs.map((r) => ({ name: r.name, passport_no: r.passport_no, age: Number(r.age), category: r.category, photo: r.photo || undefined })),
        ref: localStorage.getItem("meraaj_ref") || undefined,
      });
      toast.success("تم إنشاء الحجز وتجميد الرصيد بنجاح");
      // Upload staged traveler documents to the new booking (with progress)
      const staged = regs.flatMap((r, i) => (r.docs || []).map((d) => ({ ...d, registrant_index: i, passport_no: r.passport_no })));
      if (staged.length) {
        setProgress({ done: 0, total: staged.length });
        for (let k = 0; k < staged.length; k++) {
          const d = staged[k];
          try {
            await api.post(`/bookings/${created.id}/documents`, {
              registrant_index: d.registrant_index, doc_type: d.doc_type, filename: d.filename,
              content_base64: d.content_base64, passport_no: d.doc_type === "passport" ? (d.passport_no || undefined) : undefined,
            });
          } catch { /* skip a failed file, continue */ }
          setProgress({ done: k + 1, total: staged.length });
        }
        toast.success(`تم رفع ${staged.length} مستنداً للحجز`);
      }
      setProgress(null);
      setOpen(false);
      navigate("/bookings");
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title={pkg.title} subtitle={`${PKG_TYPE[pkg.type] || pkg.type} • ${pkg.seller_office_name}`} />

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="rounded-2xl overflow-hidden border card-shadow h-72 bg-[#0A2540] flex items-center justify-center" data-testid="pkg-hero-image">
            <PkgImage src={pkg.images?.[0]} alt={pkg.title} iconClass="w-16 h-16 text-white/15" />
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
              {pkg.route && <Info icon={MapPin} label="مسار الرحلة" value={pkg.route} />}
              <Info icon={Plane} label="النقل" value={transAr(pkg.transport)} />
              <Info icon={Users} label="التوفّر" value={pkg.is_full ? "ممتلئ / تم التفويج" : "متاح"} />
              <Info icon={Building2} label="البائع" value={pkg.seller_office_name} />
            </div>
            {pkg.description && <p className="text-sm text-muted-foreground mt-5 leading-relaxed">{pkg.description}</p>}
          </div>

          {pkg.room_pricing?.length > 0 && (() => {
            const anyChild = pkg.room_pricing.some((r) => roomCustomer(r?.customer, "child") != null);
            const anyInfant = pkg.room_pricing.some((r) => roomCustomer(r?.customer, "infant") != null);
            return (
            <div className="bg-white rounded-2xl border card-shadow p-6" data-testid="pkg-room-pricing">
              <h3 className="font-head font-bold text-[#0A2540] mb-1 flex items-center gap-2"><BedDouble className="w-4 h-4" /> أسعار الغرف</h3>
              {!isOwner && <p className="text-xs text-muted-foreground mb-4">اختر نوع الغرفة ليُحسب سعر الحجز تلقائياً حسب اختيارك.</p>}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-muted-foreground text-xs border-b"><tr>
                    {!isOwner && <th className="py-2 w-8"></th>}
                    <th className="text-start py-2">نوع الغرفة</th>
                    {isOffice && <th className="text-start py-2">الصافي</th>}
                    {isOffice && <th className="text-start py-2">العمولة</th>}
                    <th className="text-start py-2">سعر البالغ</th>
                    {anyChild && <th className="text-start py-2">سعر الطفل</th>}
                    {anyInfant && <th className="text-start py-2">سعر الرضيع</th>}
                  </tr></thead>
                  <tbody>
                    {pkg.room_pricing.map((r, i) => {
                      const selected = r.room_type === selectedRoom;
                      return (
                      <tr key={i} data-testid={`room-row-${i}`} onClick={() => !isOwner && setSelectedRoom(r.room_type)}
                          className={`border-b last:border-0 ${!isOwner ? "cursor-pointer" : ""} ${selected && !isOwner ? "bg-[#F0F7FF]" : ""}`}>
                        {!isOwner && (
                          <td className="py-2">
                            <input type="radio" name="room-select" checked={selected} readOnly
                                   data-testid={`room-select-${r.room_type}`} className="accent-[#0A2540] w-4 h-4 align-middle" />
                          </td>
                        )}
                        <td className="py-2 font-semibold text-[#0A2540]">{roomAr(r.room_type)}</td>
                        {isOffice && <td className="py-2 tabular">{roomCustomer(r.net, "adult") != null ? money(roomCustomer(r.net, "adult"), pkg.currency) : "—"}</td>}
                        {isOffice && <td className="py-2 tabular text-[#15803D]">{roomCustomer(r.commission, "adult") != null ? money(roomCustomer(r.commission, "adult"), pkg.currency) : "—"}</td>}
                        <td className="py-2 tabular font-bold" data-testid={`room-adult-${i}`}>{money(roomCustomer(r?.customer, "adult") || 0, pkg.currency)}</td>
                        {anyChild && <td className="py-2 tabular" data-testid={`room-child-${i}`}>{roomCustomer(r?.customer, "child") != null ? money(roomCustomer(r?.customer, "child"), pkg.currency) : "—"}</td>}
                        {anyInfant && <td className="py-2 tabular" data-testid={`room-infant-${i}`}>{roomCustomer(r?.customer, "infant") != null ? money(roomCustomer(r?.customer, "infant"), pkg.currency) : "—"}</td>}
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            );
          })()}

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
            {(() => {
              const mainPrice = (selRoom ? roomCustomer(selRoom.customer, "adult") : null) || Number(pkg.final_sale_price) || 0;
              return (<>
                <div className="text-sm text-muted-foreground">سعر البيع النهائي للزبون{selRoom ? ` — ${roomAr(selRoom.room_type)}` : ""}</div>
                <div className="tabular text-3xl font-bold text-[#0A2540] mt-1" data-testid="pkg-main-price">{money(mainPrice, pkg.currency)}</div>
                {pkg.currency === "SAR" && <div className="text-xs text-muted-foreground tabular mt-0.5">{equiv(mainPrice, "SAR")}</div>}
              </>);
            })()}
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
              <div className="mt-5 space-y-2">
                <div className="text-center text-sm bg-[#F4F6F8] rounded-lg py-3 text-muted-foreground">هذا البرنامج من إضافتك</div>
                <Button data-testid="share-trip-btn" onClick={shareTrip} className="w-full h-11 bg-[#25D366] hover:bg-[#1EBE57] text-white"><Share2 className="w-4 h-4" /> مشاركة الرحلة برابطك</Button>
              </div>
            ) : !user ? (
              <Button data-testid="open-booking-btn" onClick={() => navigate(`/login?next=/market/${id}`)}
                      className="w-full mt-5 h-11 bg-[#0A2540] hover:bg-[#061A2E]">
                <ShoppingCart className="w-4 h-4" /> احجز الآن
              </Button>
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

                        <div className="mt-3 border-t pt-3">
                          <Label className="mb-1.5 block text-xs flex items-center gap-1"><Paperclip className="w-3.5 h-3.5" /> مستندات المسافر (جواز/تأشيرة/تذكرة… عدة ملفات)</Label>
                          {(r.docs || []).length > 0 && (
                            <div className="space-y-1 mb-2">
                              {r.docs.map((d, di) => (
                                <div key={di} className="flex items-center justify-between bg-[#F4F6F8] rounded-md px-2 py-1.5 text-[11px]" data-testid={`stage-doc-${i}-${di}`}>
                                  <span className="flex items-center gap-2 min-w-0">
                                    <span className="font-semibold shrink-0">{docLabel(d.doc_type)}</span>
                                    {d.content_base64?.startsWith("data:image") && <img alt="" src={d.content_base64} className="w-6 h-6 rounded object-cover shrink-0" />}
                                    <span className="text-muted-foreground truncate">{d.filename}</span>
                                  </span>
                                  <button type="button" onClick={() => rmDoc(i, di)} className="text-red-500 shrink-0" data-testid={`stage-doc-remove-${i}-${di}`}><X className="w-3.5 h-3.5" /></button>
                                </div>
                              ))}
                            </div>
                          )}
                          <div className="flex items-center gap-2">
                            <select value={docType[i] || "passport"} onChange={(e) => setDocType({ ...docType, [i]: e.target.value })}
                                    data-testid={`stage-doc-type-${i}`} className="h-8 rounded-md border border-input bg-transparent px-2 text-xs">
                              {DOC_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                            </select>
                            <label className="inline-flex items-center gap-1.5 text-xs bg-white border border-[#0A2540] text-[#0A2540] rounded-md px-3 h-8 cursor-pointer hover:bg-[#0A2540]/5" data-testid={`stage-doc-add-${i}`}>
                              <Plus className="w-3.5 h-3.5" /> إضافة ملفات
                              <input type="file" multiple className="hidden" accept="image/png,image/jpeg,image/webp,application/pdf" onChange={stageDocs(i)} />
                            </label>
                          </div>
                        </div>
                      </div>
                    ))}
                    <div className="flex flex-wrap gap-2">
                      <Button variant="outline" size="sm" onClick={() => addReg("adult")} data-testid="add-adult-btn"><Plus className="w-4 h-4" /> بالغ</Button>
                      {CATS.child.offered && <Button variant="outline" size="sm" onClick={() => addReg("child")} data-testid="add-child-btn"><Plus className="w-4 h-4" /> طفل</Button>}
                      {CATS.infant.offered && <Button variant="outline" size="sm" onClick={() => addReg("infant")} data-testid="add-infant-btn"><Plus className="w-4 h-4" /> رضيع</Button>}
                    </div>

                    <div className="bg-[#F4F6F8] rounded-xl p-4 text-sm space-y-2">
                      {selRoom && <Row label="نوع الغرفة المختارة" value={roomAr(selRoom.room_type)} />}
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
                      {progress ? `جارٍ رفع المستندات ${progress.done}/${progress.total}...` : busy ? "جارٍ الحجز..." : `تأكيد الحجز — ${money(required, pkg.currency)}`}
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
