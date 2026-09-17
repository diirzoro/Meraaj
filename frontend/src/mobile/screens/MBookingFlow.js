import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { CheckCircle2, Trash2, UserPlus } from "lucide-react";
import mobileApi, { apiError } from "@/mobile/api/client";
import {
  Screen, TopBar, Card, Skeleton, ErrorState, Money, PrimaryButton, GhostButton, SheetSelect,
  mInput, MField, useAsync, haptic,
} from "@/mobile/ui/kit";

const CATEGORIES = [{ value: "adult", label: "بالغ" }, { value: "child", label: "طفل" }, { value: "infant", label: "رضيع" }];
const CAT_LABEL = (v) => CATEGORIES.find((c) => c.value === v)?.label || v;
const emptyTraveler = () => ({ name: "", passport_no: "", age: "", category: "adult" });

/** Travelers → Review → Confirm. The price the user sees is informational: the SERVER
 *  recomputes the authoritative amount, commission and balance check on POST /api/bookings.
 *  The submit button is locked after the first attempt so a weak network cannot create a
 *  duplicate booking. */
export default function MBookingFlow() {
  const { id } = useParams();
  const navigate = useNavigate();
  const p = useAsync(() => mobileApi.program(id), [id]);
  const [step, setStep] = useState(1);
  const [roomType, setRoomType] = useState("");
  const [travelers, setTravelers] = useState([emptyTraveler()]);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(null);
  const [idemKey] = useState(() => (window.crypto?.randomUUID?.() || `bk-${Date.now()}-${Math.random()}`));

  const d = p.data || {};
  const rooms = d.rooms || [];
  const roomOptions = [{ value: "", label: "— الافتراضي —" },
    ...rooms.map((r, i) => ({ value: r.room_type || r.type || `room-${i}`, label: r.room_type || r.type || `غرفة ${i + 1}` }))];

  const estimate = useMemo(() => {
    const unit = Number((rooms.find((r) => (r.room_type || r.type) === roomType) || {})
      .final_sale_price ?? d.final_sale_price ?? 0);
    return unit * travelers.length;
  }, [rooms, roomType, d.final_sale_price, travelers.length]);

  const valid = travelers.length > 0 && travelers.every((t) => t.name.trim() && t.passport_no.trim() && t.age !== "");
  const patch = (i, next) => setTravelers(travelers.map((t, x) => (x === i ? { ...t, ...next } : t)));

  const submit = async () => {
    if (submitting || done) return;
    setSubmitting(true);
    try {
      const res = await mobileApi.createBooking({
        package_id: id, room_type: roomType || null,
        registrants: travelers.map((t) => ({ name: t.name.trim(), passport_no: t.passport_no.trim(),
          age: Number(t.age), category: t.category })),
      }, idemKey);
      setDone(res);
      haptic("success");
      toast.success("تم إنشاء الحجز");
    } catch (e) {
      haptic("error");
      toast.error(apiError(e));
    } finally {
      setSubmitting(false);
    }
  };

  if (p.loading) return <Screen><TopBar title="حجز البرنامج" back /><Skeleton rows={3} /></Screen>;
  if (p.error) return <Screen><TopBar title="حجز البرنامج" back /><ErrorState message={p.error} onRetry={p.reload} /></Screen>;

  if (done) {
    return (
      <Screen>
        <TopBar title="تم الحجز" />
        <div className="p-6 text-center m-page-fade" data-testid="m-booking-confirmation">
          <CheckCircle2 className="w-20 h-20 text-emerald-500 mx-auto mb-5" />
          <p className="font-head text-lg font-bold text-[#0A2540]">تم إنشاء حجزك</p>
          <p className="text-xs text-muted-foreground mt-1.5" dir="ltr">{done.id}</p>
          <Card className="mt-6 text-start" testid="m-booking-confirmation-amount">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground text-xs">المبلغ المحتسب من السيرفر</span>
              <Money value={done.amount_charged} currency={done.currency} className="text-base" />
            </div>
          </Card>
          <div className="mt-6 space-y-3">
            <PrimaryButton onClick={() => navigate(`/m/bookings/${done.id}`)} data-testid="m-booking-goto-detail">
              تفاصيل الحجز
            </PrimaryButton>
            <GhostButton onClick={() => navigate("/m/home")} data-testid="m-booking-goto-home">الرئيسية</GhostButton>
          </div>
        </div>
      </Screen>
    );
  }

  return (
    <Screen className="pb-32">
      <TopBar title="إتمام الحجز" subtitle={`${step === 1 ? "المسافرون" : "المراجعة"} · ${d.title || ""}`} back />
      <div className="px-4 pt-4 flex gap-2" data-testid="m-booking-steps">
        {[1, 2].map((s) => (
          <div key={s} className={`h-1.5 flex-1 rounded-full transition-colors ${step >= s ? "bg-[#0A2540]" : "bg-[#0A2540]/12"}`} />
        ))}
      </div>

      {step === 1 ? (
        <div className="p-4 space-y-3.5">
          {rooms.length > 0 && (
            <Card testid="m-booking-room">
              <SheetSelect label="نوع الغرفة" value={roomType} options={roomOptions}
                           testid="m-booking-room-select" onChange={setRoomType} />
            </Card>
          )}

          {travelers.map((t, i) => (
            <Card key={i} testid={`m-traveler-${i}`}>
              <div className="flex items-center justify-between mb-3.5">
                <p className="font-bold text-sm text-[#0A2540]">مسافر {i + 1}</p>
                {travelers.length > 1 && (
                  <button onClick={() => setTravelers(travelers.filter((_, x) => x !== i))}
                          data-testid={`m-traveler-remove-${i}`} aria-label="حذف المسافر"
                          className="w-9 h-9 rounded-full bg-red-50 text-red-600 flex items-center justify-center active:scale-90 transition-transform">
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
              <MField label="الاسم كما في جواز السفر">
                <input className={mInput} value={t.name} data-testid={`m-traveler-name-${i}`}
                       onChange={(e) => patch(i, { name: e.target.value })} />
              </MField>
              <div className="grid grid-cols-2 gap-3">
                <MField label="رقم الجواز">
                  <input className={mInput} value={t.passport_no} data-testid={`m-traveler-passport-${i}`} dir="ltr"
                         onChange={(e) => patch(i, { passport_no: e.target.value })} />
                </MField>
                <MField label="العمر">
                  <input className={mInput} inputMode="numeric" value={t.age} data-testid={`m-traveler-age-${i}`}
                         onChange={(e) => patch(i, { age: e.target.value })} />
                </MField>
              </div>
              <SheetSelect label="الفئة" value={t.category} options={CATEGORIES}
                           testid={`m-traveler-category-${i}`} onChange={(v) => patch(i, { category: v })} />
            </Card>
          ))}

          <button onClick={() => { haptic("light"); setTravelers([...travelers, emptyTraveler()]); }}
                  data-testid="m-traveler-add"
                  className="w-full h-14 rounded-2xl border-2 border-dashed border-[#0A2540]/20 text-sm font-bold text-[#0A2540] flex items-center justify-center gap-2 active:scale-[0.99] transition-transform">
            <UserPlus className="w-4 h-4" /> إضافة مسافر
          </button>

          <PrimaryButton disabled={!valid} onClick={() => setStep(2)} data-testid="m-booking-next">
            المراجعة
          </PrimaryButton>
        </div>
      ) : (
        <div className="p-4 space-y-3.5">
          <Card testid="m-booking-review">
            <p className="font-bold text-sm text-[#0A2540] mb-3.5">{d.title}</p>
            <div className="space-y-1">
              {travelers.map((t, i) => (
                <div key={i} className="flex items-center justify-between py-2.5 border-b border-black/5 last:border-0">
                  <span className="text-sm font-semibold text-[#0A2540] truncate">{t.name}</span>
                  <span className="text-[11px] text-muted-foreground shrink-0" dir="ltr">
                    {CAT_LABEL(t.category)} · {t.passport_no}
                  </span>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between mt-4 pt-3.5 border-t border-black/5">
              <span className="text-xs text-muted-foreground">تقدير مبدئي ({travelers.length} مسافر)</span>
              <Money value={estimate} currency={d.currency} className="text-base" />
            </div>
            <p className="text-[11px] text-amber-800 bg-amber-50 rounded-2xl p-3 mt-3.5 leading-relaxed">
              المبلغ النهائي والعمولة والخصم من المحفظة يحتسبها السيرفر عند التأكيد — هذا
              التقدير للعرض فقط.
            </p>
          </Card>

          <PrimaryButton loading={submitting} disabled={submitting} onClick={submit} data-testid="m-booking-confirm">
            تأكيد الحجز
          </PrimaryButton>
          <GhostButton onClick={() => setStep(1)} data-testid="m-booking-back-step">تعديل المسافرين</GhostButton>
        </div>
      )}
    </Screen>
  );
}
