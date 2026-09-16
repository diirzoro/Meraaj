import { Bus, Clock } from "lucide-react";
import mobileApi from "@/mobile/api/client";
import { Screen, TopBar, Card, Skeleton, useAsync } from "@/mobile/ui/kit";

/** TICKETS — place holder + adapter architecture ONLY.
 *  No provider is hardcoded and no booking flow is invented: the real screens
 *  (Search → Trip → Seat → Passenger → Price check → Booking → Issue → Cancel) are built
 *  against the transport company's contract once it arrives. */
export default function MTickets() {
  const info = useAsync(() => mobileApi.ticketProviders());

  return (
    <Screen>
      <TopBar title="التذاكر" subtitle="النقل البري — قيد التجهيز" back />
      <div className="p-4 space-y-3">
        <Card testid="m-tickets-placeholder">
          <div className="flex items-start gap-3">
            <div className="w-11 h-11 rounded-2xl bg-[#0A2540]/5 flex items-center justify-center shrink-0">
              <Bus className="w-5 h-5 text-[#0A2540]" />
            </div>
            <div>
              <p className="font-semibold text-sm text-[#0A2540]">الخدمة محفوظة وجاهزة للربط</p>
              <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed">
                تم تجهيز مكان الخدمة وطبقة المزوّدين (Provider Adapter) داخل التطبيق.
                سيُبنى تدفق الحجز على واجهة شركة النقل الحقيقية بعد استلام العقد — بلا أي
                بيانات أو أسعار تخمينية.
              </p>
            </div>
          </div>
        </Card>

        {info.loading ? <Skeleton rows={1} /> : (
          <Card testid="m-tickets-contract">
            <div className="flex items-center gap-2 mb-3">
              <Clock className="w-4 h-4 text-[#D4AF37]" />
              <p className="font-semibold text-sm text-[#0A2540]">ما نحتاجه من شركة النقل</p>
            </div>
            <ul className="space-y-2">
              {(info.data?.required_provider_contract || []).map((line, i) => (
                <li key={i} className="text-[11px] text-muted-foreground flex gap-2" data-testid={`m-tickets-req-${i}`}>
                  <span className="text-[#D4AF37]">•</span>
                  <span className="font-mono leading-relaxed" dir="ltr">{line}</span>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </Screen>
  );
}
