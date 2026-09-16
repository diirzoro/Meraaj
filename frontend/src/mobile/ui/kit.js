/** Mobile UI kit — touch-first, RTL-first. Deliberately NOT the dashboard components:
 *  no desktop tables, no sidebar, bottom sheets instead of modals. */
import { useEffect, useState } from "react";
import { AlertCircle, ChevronLeft, Inbox, Loader2, RefreshCw } from "lucide-react";
import { useNavigate } from "react-router-dom";

export function Screen({ children, className = "" }) {
  return <div className={`min-h-[100dvh] bg-[#F4F6F8] pb-24 ${className}`}>{children}</div>;
}

export function TopBar({ title, subtitle, back = false, right = null }) {
  const navigate = useNavigate();
  return (
    <header className="sticky top-0 z-20 bg-[#0A2540] text-white px-4 pt-[max(0.75rem,env(safe-area-inset-top))] pb-3"
            data-testid="m-topbar">
      <div className="flex items-center gap-3">
        {back && (
          <button onClick={() => navigate(-1)} data-testid="m-back-btn"
                  className="w-9 h-9 -ms-1 rounded-full bg-white/10 flex items-center justify-center active:scale-95 transition-transform">
            <ChevronLeft className="w-5 h-5 rtl:rotate-180" />
          </button>
        )}
        <div className="min-w-0 flex-1">
          <h1 className="font-head text-lg font-bold truncate">{title}</h1>
          {subtitle && <p className="text-[11px] text-white/60 truncate">{subtitle}</p>}
        </div>
        {right}
      </div>
    </header>
  );
}

export function Card({ children, onClick, className = "", testid }) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag onClick={onClick} data-testid={testid}
         className={`w-full text-start bg-white rounded-2xl border border-black/5 shadow-[0_2px_10px_rgba(10,37,64,0.06)] p-4 ${
           onClick ? "active:scale-[0.99] transition-transform" : ""} ${className}`}>
      {children}
    </Tag>
  );
}

export function Skeleton({ rows = 3 }) {
  return (
    <div className="space-y-3 p-4" data-testid="m-skeleton">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="bg-white rounded-2xl p-4 border border-black/5">
          <div className="h-3 w-1/3 bg-slate-200 rounded animate-pulse mb-3" />
          <div className="h-3 w-2/3 bg-slate-100 rounded animate-pulse mb-2" />
          <div className="h-3 w-1/2 bg-slate-100 rounded animate-pulse" />
        </div>
      ))}
    </div>
  );
}

export function EmptyState({ title = "لا توجد بيانات", hint, action }) {
  return (
    <div className="px-6 py-14 text-center" data-testid="m-empty">
      <div className="w-14 h-14 rounded-2xl bg-white border mx-auto flex items-center justify-center mb-3">
        <Inbox className="w-6 h-6 text-[#0A2540]/40" />
      </div>
      <p className="font-semibold text-[#0A2540]">{title}</p>
      {hint && <p className="text-xs text-muted-foreground mt-1">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="px-6 py-12 text-center" data-testid="m-error">
      <div className="w-14 h-14 rounded-2xl bg-red-50 border border-red-100 mx-auto flex items-center justify-center mb-3">
        <AlertCircle className="w-6 h-6 text-red-500" />
      </div>
      <p className="font-semibold text-[#0A2540]">تعذّر تحميل البيانات</p>
      <p className="text-xs text-muted-foreground mt-1 break-words">{message}</p>
      {onRetry && (
        <button onClick={onRetry} data-testid="m-retry-btn"
                className="mt-4 h-11 px-5 rounded-xl bg-[#0A2540] text-white text-sm font-semibold inline-flex items-center gap-2 active:scale-95 transition-transform">
          <RefreshCw className="w-4 h-4" /> إعادة المحاولة
        </button>
      )}
    </div>
  );
}

export function PrimaryButton({ children, loading, className = "", ...props }) {
  return (
    <button {...props} disabled={loading || props.disabled}
            className={`w-full h-12 rounded-xl bg-[#0A2540] text-white font-semibold text-sm flex items-center justify-center gap-2 disabled:opacity-50 active:scale-[0.98] transition-transform ${className}`}>
      {loading && <Loader2 className="w-4 h-4 animate-spin" />}
      {children}
    </button>
  );
}

export function GoldButton({ children, className = "", ...props }) {
  return (
    <button {...props}
            className={`w-full h-12 rounded-xl bg-[#D4AF37] text-[#0A2540] font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50 active:scale-[0.98] transition-transform ${className}`}>
      {children}
    </button>
  );
}

export const mInput =
  "w-full h-12 rounded-xl border border-black/10 bg-white px-4 text-sm focus:outline-none focus:border-[#0A2540]";

export function MField({ label, children, hint }) {
  return (
    <label className="block mb-3">
      <span className="block text-xs font-semibold text-[#0A2540] mb-1.5">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-muted-foreground mt-1">{hint}</span>}
    </label>
  );
}

/** Bottom sheet — the mobile-native replacement for a desktop dialog. */
export function Sheet({ open, onClose, title, children, testid = "m-sheet" }) {
  useEffect(() => {
    if (!open) return undefined;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [open]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end" data-testid={testid}>
      <div className="absolute inset-0 bg-black/45" onClick={onClose} data-testid="m-sheet-backdrop" />
      <div className="relative w-full bg-white rounded-t-3xl p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] max-h-[88dvh] overflow-y-auto animate-in">
        <div className="w-10 h-1.5 bg-slate-200 rounded-full mx-auto mb-4" />
        {title && <h2 className="font-head text-base font-bold text-[#0A2540] mb-3">{title}</h2>}
        {children}
      </div>
    </div>
  );
}

export function StatusPill({ status }) {
  const map = {
    pending: ["بانتظار المراجعة", "bg-amber-100 text-amber-800"],
    approved: ["مقبول", "bg-emerald-100 text-emerald-700"],
    rejected: ["مرفوض", "bg-red-100 text-red-700"],
    blue: ["قيد التنفيذ", "bg-blue-100 text-blue-700"],
    yellow: ["بانتظار إجراء", "bg-amber-100 text-amber-800"],
    green: ["مكتمل", "bg-emerald-100 text-emerald-700"],
    cancelled: ["ملغى", "bg-red-100 text-red-700"],
    expired: ["منتهي", "bg-slate-200 text-slate-600"],
    dispatched: ["تم التسليم", "bg-blue-100 text-blue-700"],
    listed: ["متاح", "bg-emerald-100 text-emerald-700"],
  };
  const [label, cls] = map[status] || [status || "—", "bg-slate-100 text-slate-700"];
  return <span className={`text-[11px] font-semibold rounded-full px-2 py-0.5 ${cls}`}>{label}</span>;
}

export function Money({ value, currency }) {
  const n = Number(value || 0);
  return (
    <span className="tabular-nums font-bold">
      {n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      {currency ? <span className="text-[11px] font-semibold ms-1">{currency}</span> : null}
    </span>
  );
}

/** Pull-to-refresh-ish: a simple manual refresher that also handles weak networks. */
export function useAsync(loader, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true); setError("");
    Promise.resolve(loader())
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e?.response?.data?.detail || e?.message || "خطأ غير معروف"))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);
  return { data, loading, error, reload: () => setTick((t) => t + 1), setData };
}
