import { STATUS, APPROVAL, CANCELLATION } from "@/lib/format";

export default function StatusBadge({ status }) {
  const s = STATUS[status] || STATUS.blue;
  return (
    <span
      data-testid={`status-badge-${status}`}
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${s.cls}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {s.label}
    </span>
  );
}

// Approval status pill (pending / approved / rejected / expired) — rahal bookings only.
export function ApprovalBadge({ status }) {
  const s = APPROVAL[status];
  if (!s) return null;
  return (
    <span data-testid={`approval-badge-${status}`}
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${s.cls}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {s.label}
    </span>
  );
}

// Cancellation status pill (requested / withdrawn / decided / rejected / expired).
export function CancellationBadge({ status }) {
  const s = CANCELLATION[status];
  if (!s || status === "none") return null;
  return (
    <span data-testid={`cancellation-badge-${status}`}
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${s.cls}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {s.label}
    </span>
  );
}
