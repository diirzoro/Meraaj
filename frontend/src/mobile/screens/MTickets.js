import { useNavigate } from "react-router-dom";
import { Bus, Clock, Landmark, Plane, Ship } from "lucide-react";
import { Screen, TopBar, Card, Chip, GhostButton } from "@/mobile/ui/kit";

/** TICKETS — a clean customer-facing "coming soon" screen.
 *  No provider, no prices, no fake search/booking: the real flow
 *  (Search → Trip → Seat → Passenger → Price check → Booking → Issue → Cancel) is built
 *  against the transport company's contract once it arrives. */
const KINDS = [
  { key: "land", label: "النقل البري", icon: Bus },
  { key: "air", label: "تذاكر الطيران", icon: Plane },
  { key: "sea", label: "النقل البحري", icon: Ship },
];

export default function MTickets() {
  const navigate = useNavigate();

  return (
    <Screen>
      <TopBar title="التذاكر" back />

      <div className="p-4 space-y-4">
        <div className="rounded-[26px] bg-[#0A2540] text-white p-6 relative overflow-hidden text-center"
             data-testid="m-tickets-placeholder">
          <div className="absolute -top-12 -end-10 w-40 h-40 rounded-full bg-[#D4AF37]/10" />
          <div className="relative">
            <div className="w-16 h-16 rounded-[22px] bg-[#D4AF37] mx-auto flex items-center justify-center mb-4">
              <Bus className="w-8 h-8 text-[#0A2540]" />
            </div>
            <p className="font-head text-lg font-bold">خدمة حجز التذاكر قريباً</p>
            <p className="text-xs text-white/60 mt-2 leading-relaxed">
              نعمل على إتاحة حجز التذاكر داخل التطبيق مباشرة، بأسعار ومقاعد فعلية من شركة النقل.
            </p>
            <span className="inline-flex mt-4">
              <Chip tone="gold"><Clock className="w-3 h-3 inline-block -mt-0.5 me-1" /> قيد التجهيز</Chip>
            </span>
          </div>
        </div>

        <Card testid="m-tickets-kinds">
          <p className="font-bold text-sm text-[#0A2540] mb-3">أنواع الخدمات المخطّطة</p>
          <div className="space-y-2.5">
            {KINDS.map((k) => (
              <div key={k.key} data-testid={`m-tickets-kind-${k.key}`}
                   className="flex items-center gap-3 rounded-2xl bg-[#F1F4F8] px-3.5 py-3">
                <span className="w-10 h-10 rounded-xl bg-white flex items-center justify-center shrink-0">
                  <k.icon className="w-[18px] h-[18px] text-[#0A2540]/55" />
                </span>
                <span className="text-sm font-semibold text-[#0A2540]/70 flex-1">{k.label}</span>
                <Chip>غير متاح حالياً</Chip>
              </div>
            ))}
          </div>
        </Card>

        <Card testid="m-tickets-meanwhile">
          <p className="font-bold text-sm text-[#0A2540]">إلى أن تتوفر</p>
          <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">
            يمكنك متابعة برامج العمرة وحجوزاتك ومحفظتك كالمعتاد.
          </p>
          <div className="mt-4">
            <GhostButton onClick={() => navigate("/m/programs")} data-testid="m-tickets-goto-programs">
              <Landmark className="w-4 h-4" /> تصفح برامج العمرة
            </GhostButton>
          </div>
        </Card>
      </div>
    </Screen>
  );
}
