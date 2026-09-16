import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { CheckCircle2, Trash2, UserPlus } from "lucide-react";
import mobileApi, { apiError } from "@/mobile/api/client";
import { Screen, TopBar, Card, Skeleton, ErrorState, Money, PrimaryButton, mInput, MField, useAsync } from "@/mobile/ui/kit";

const CATEGORIES = [["adult", "بالغ"], ["child", "طفل"], ["infant", "رضيع"]];
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

  const d = p.data || {};
  const rooms = d.rooms || [];
  const estimate = useMemo(() => {
    const unit = Number((rooms.find((r) => (r.room_type || r.type) === roomType) || {})
      .final_sale_price ?? d.final_sale_price ?? 0);
    return unit * travelers.length;
  }, [rooms, roomType, d.final_sale_price, travelers.length]);

  const valid = travelers.length > 0 && travelers.every((t) => t.name.trim() && t.passport_no.trim() && t.age !== "");

  const submit = async () => {
    if (submitting || done) return;
    setSubmitting(true);
    try {
      const res = await mobileApi.createBooking({
        package_id: id, room_type: roomType || null,
        registrants: travelers.map((t) => ({ name: t.name.trim(), passport_no: t.passport_no.trim(),
          age: Number(t.age), category: t.category })),
      });
      setDone(res);
      toast.success("تم إنشاء الحجز");
    } catch (e) {
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
        <div className="p-6 text-center" data-testid="m-booking-confirmation">
          <CheckCircle2 className="w-16 h-16 text-emerald-500 mx-auto mb-4" />
          <p className="font-head text-lg font-bold text-[#0A2540]">تم إنشاء حجزك</p>
          <p className="text-xs text-muted-foreground mt-1">رقم الحجز: {done.id}</p>
          <Card className="mt-5 text-start" testid="m-booking-confirmation-amount">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground text-xs">المبلغ المحتسب من السيرفر</span>
              <Money value={done.amount_charged} currency={done.currency} />
            </div>
          </Card>
          <div className="mt-6 space-y-3">
            <PrimaryButton onClick={() => navigate(`/m/bookings/${done.id}`)} data-testid="m-booking-goto-detail">
              تفاصيل الحجز
            </PrimaryButton>
            <button onClick={() => navigate("/m/home")} data-testid="m-booking-goto-home"
                    className="w-full h-12 text-sm font-semibold text-[#0A2540]">الرئيسية</button>
          </div>
        </div>
      </Screen>
    );
  }

  return (
    <Screen>
      <TopBar title="إتمام الحجز" subtitle={`${step === 1 ? "المسافرون" : "المراجعة"} · ${d.title || ""}`} back />
      <div className="px-4 pt-4 flex gap-2" data-testid="m-booking-steps">
        {[1, 2].map((s) => (
          <div key={s} className={`h-1.5 flex-1 rounded-full ${step >= s ? "bg-[#0A2540]" : "bg-[#0A2540]/15"}`} />
        ))}
      </div>

      {step === 1 ? (
        <div className="p-4 space-y-3">
          {rooms.length > 0 && (
            <Card testid="m-booking-room">
              <MField label="نوع الغرفة">
                <select className={mInput} value={roomType} data-testid="m-booking-room-select"
                        onChange={(e) => setRoomType(e.target.value)}>
                  <option value="">— الافتراضي —</option>
                  {rooms.map((r, i) => (
                    <option key={i} value={r.room_type || r.type}>{r.room_type || r.type}</option>
                  ))}
                </select>
              </MField>
            </Card>
          )}

          {travelers.map((t, i) => (
            <Card key={i} testid={`m-traveler-${i}`}>
              <div className="flex items-center justify-between mb-3">
                <p className="font-semibold text-sm text-[#0A2540]">مسافر {i + 1}</p>
                {travelers.length > 1 && (
                  <button onClick={() => setTravelers(travelers.filter((_, x) => x !== i))}
                          data-testid={`m-traveler-remove-${i}`} className="text-red-600">
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
              <MField label="الاسم كما في جواز السفر">
                <input className={mInput} value={t.name} data-testid={`m-traveler-name-${i}`}
                       onChange={(e) => { const a = [...travelers]; a[i] = { ...t, name: e.target.value }; setTravelers(a); }} />
              </MField>
              <div className="grid grid-cols-2 gap-3">
                <MField label="رقم الجواز">
                  <input className={mInput} value={t.passport_no} data-testid={`m-traveler-passport-${i}`}
                         onChange={(e) => { const a = [...travelers]; a[i] = { ...t, passport_no: e.target.value }; setTravelers(a); }} />
                </MField>
                <MField label="العمر">
                  <input className={mInput} inputMode="numeric" value={t.age} data-testid={`m-traveler-age-${i}`}
                         onChange={(e) => { const a = [...travelers]; a[i] = { ...t, age: e.target.value }; setTravelers(a); }} />
                </MField>
              </div>
              <MField label="الفئة">
                <select className={mInput} value={t.category} data-testid={`m-traveler-category-${i}`}
                        onChange={(e) => { const a = [...travelers]; a[i] = { ...t, category: e.target.value }; setTravelers(a); }}>
                  {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </MField>
            </Card>
          ))}

          <button onClick={() => setTravelers([...travelers, emptyTraveler()])} data-testid="m-traveler-add"
                  className="w-full h-12 rounded-xl border-2 border-dashed border-[#0A2540]/25 text-sm font-semibold text-[#0A2540] flex items-center justify-center gap-2">
            <UserPlus className="w-4 h-4" /> إضافة مسافر
          </button>

          <PrimaryButton disabled={!valid} onClick={() => setStep(2)} data-testid="m-booking-next">
            المراجعة
          </PrimaryButton>
        </div>
      ) : (
        <div className="p-4 space-y-3">
          <Card testid="m-booking-review">
            <p className="font-semibold text-sm text-[#0A2540] mb-3">{d.title}</p>
            <div className="space-y-2 text-xs">
              {travelers.map((t, i) => (
                <div key={i} className="flex items-center justify-between border-b last:border-0 pb-2 last:pb-0">
                  <span className="text-[#0A2540]">{t.name}</span>
                  <span className="text-muted-foreground">
                    {CATEGORIES.find(([v]) => v === t.category)?.[1]} · {t.passport_no}
                  </span>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between mt-4 pt-3 border-t text-sm">
              <span className="text-xs text-muted-foreground">تقدير مبدئي ({travelers.length} مسافر)</span>
              <Money value={estimate} currency={d.currency} />
            </div>
            <p className="text-[11px] text-amber-700 bg-amber-50 rounded-lg p-2 mt-3">
              المبلغ النهائي والعمولة والخصم من المحفظة يحتسبها السيرفر عند التأكيد — هذا
              التقدير للعرض فقط.
            </p>
          </Card>

          <PrimaryButton loading={submitting} disabled={submitting} onClick={submit} data-testid="m-booking-confirm">
            تأكيد الحجز
          </PrimaryButton>
          <button onClick={() => setStep(1)} data-testid="m-booking-back-step"
                  className="w-full h-12 text-sm font-semibold text-[#0A2540]">تعديل المسافرين</button>
        </div>
      )}
    </Screen>
  );
}
