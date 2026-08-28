import { useEffect, useState } from "react";
import api from "@/lib/api";
import { fmtDateTime, EVENT_LABELS, ACTOR_LABELS } from "@/lib/format";

// Append-only audit trail for a booking (Enterprise P2P timeline).
export default function Timeline({ bookingId }) {
  const [events, setEvents] = useState(null);

  useEffect(() => {
    if (!bookingId) return;
    setEvents(null);
    api.get(`/bookings/${bookingId}/timeline`)
      .then((r) => setEvents(r.data))
      .catch(() => setEvents([]));
  }, [bookingId]);

  if (events === null) return <div className="py-6 text-center text-sm text-muted-foreground">جارٍ تحميل السجل...</div>;
  if (events.length === 0) return <div className="py-6 text-center text-sm text-muted-foreground">لا توجد أحداث مسجّلة بعد</div>;

  return (
    <ol className="relative border-s-2 border-[#E5E7EB] ms-3 space-y-5 py-2" data-testid="booking-timeline">
      {events.map((e, i) => (
        <li key={e.id || i} className="ms-5 relative" data-testid={`timeline-event-${i}`}>
          <span className="absolute -start-[27px] top-1 w-3.5 h-3.5 rounded-full bg-[#D4AF37] border-2 border-white ring-1 ring-[#E5E7EB]" />
          <div className="text-sm font-semibold text-[#0A2540]">{EVENT_LABELS[e.event] || e.event}</div>
          <div className="text-xs text-muted-foreground mt-0.5">
            {fmtDateTime(e.at)} • {ACTOR_LABELS[e.actor_type] || e.actor_type}
          </div>
          {e.reason && <div className="text-xs text-[#A16207] mt-1">السبب: {e.reason}</div>}
        </li>
      ))}
    </ol>
  );
}
