/** MERAAJ MOBILE DESIGN SYSTEM — touch-first, RTL-first, native-feel.
 *  Deliberately NOT the dashboard components: no desktop tables, no sidebar,
 *  bottom sheets instead of modals, sheet pickers instead of raw <select>.
 *  Public API is a superset of the previous kit — screens keep working. */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle, CalendarDays, Camera, Check, ChevronDown, ChevronLeft, Inbox,
  Loader2, RefreshCw, Search, X,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import haptic from "@/mobile/ui/haptics";
import "@/mobile/ui/mobile.css";

export { haptic };

export const NAVY = "#0A2540";
export const GOLD = "#D4AF37";

/* ------------------------------------------------------------------ layout */

export function Screen({ children, className = "", refresh, testid }) {
  const body = <div className={`min-h-[100dvh] bg-[#F1F4F8] pb-28 ${className}`} data-testid={testid}>{children}</div>;
  return refresh ? <PullToRefresh onRefresh={refresh}>{body}</PullToRefresh> : body;
}

/** App bar: solid navy, fades its border in on scroll. `large` renders a big title. */
export function TopBar({ title, subtitle, back = false, right = null, large = false }) {
  const navigate = useNavigate();
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header data-testid="m-topbar"
            className={`sticky top-0 z-20 bg-[#0A2540] text-white px-4 pt-[max(0.85rem,env(safe-area-inset-top))] ${
              large ? "pb-5" : "pb-3.5"} ${scrolled ? "shadow-[0_6px_18px_-8px_rgba(10,37,64,0.65)]" : ""}`}>
      <div className="flex items-center gap-3">
        {back && (
          <button onClick={() => { haptic("light"); navigate(-1); }} data-testid="m-back-btn"
                  aria-label="رجوع"
                  className="w-10 h-10 -ms-1 rounded-full bg-white/10 flex items-center justify-center active:scale-90 transition-transform">
            <ChevronLeft className="w-5 h-5 rtl:rotate-180" />
          </button>
        )}
        <div className="min-w-0 flex-1">
          <h1 className={`font-head font-bold truncate ${large ? "text-2xl" : "text-lg"}`}>{title}</h1>
          {subtitle && <p className="text-xs text-white/60 truncate mt-0.5">{subtitle}</p>}
        </div>
        {right}
      </div>
    </header>
  );
}

export function SectionTitle({ children, action, onAction, testid }) {
  return (
    <div className="flex items-center justify-between mb-3 px-1">
      <h2 className="font-head text-base font-bold text-[#0A2540]">{children}</h2>
      {action && (
        <button onClick={onAction} data-testid={testid}
                className="text-xs font-bold text-[#0A2540]/70 active:opacity-60">{action}</button>
      )}
    </div>
  );
}

export function Card({ children, onClick, className = "", testid }) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag onClick={onClick ? (e) => { haptic("light"); onClick(e); } : undefined} data-testid={testid}
         className={`w-full text-start bg-white rounded-[22px] border border-black/[0.04] shadow-[0_4px_18px_-10px_rgba(10,37,64,0.25)] p-4 ${
           onClick ? "active:scale-[0.985] transition-transform" : ""} ${className}`}>
      {children}
    </Tag>
  );
}

export function ListRow({ icon: Icon, label, value, onClick, testid, danger = false, last = false }) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag onClick={onClick ? () => { haptic("light"); onClick(); } : undefined} data-testid={testid}
         className={`w-full flex items-center gap-3 px-4 py-4 text-start ${last ? "" : "border-b border-black/5"} ${
           onClick ? "active:bg-slate-50" : ""}`}>
      {Icon && (
        <span className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
          danger ? "bg-red-50" : "bg-[#0A2540]/[0.06]"}`}>
          <Icon className={`w-[18px] h-[18px] ${danger ? "text-red-600" : "text-[#0A2540]"}`} />
        </span>
      )}
      <span className={`text-sm flex-1 truncate ${danger ? "text-red-600 font-semibold" : "text-[#0A2540]"}`}>{label}</span>
      {value !== undefined && <span className="text-xs text-muted-foreground shrink-0">{value}</span>}
      {onClick && <ChevronLeft className="w-4 h-4 text-[#0A2540]/25 rtl:rotate-180 shrink-0" />}
    </Tag>
  );
}

export function KpiCard({ label, value, hint, icon: Icon, tone = "navy", onClick, testid }) {
  const tones = {
    navy: "bg-white text-[#0A2540]",
    gold: "bg-[#D4AF37]/12 text-[#0A2540]",
    warn: "bg-amber-50 text-amber-900",
    good: "bg-emerald-50 text-emerald-900",
    bad: "bg-red-50 text-red-900",
  };
  const Tag = onClick ? "button" : "div";
  return (
    <Tag onClick={onClick ? () => { haptic("light"); onClick(); } : undefined} data-testid={testid}
         className={`w-full text-start rounded-[22px] border border-black/[0.04] p-4 shadow-[0_4px_18px_-12px_rgba(10,37,64,0.3)] ${
           tones[tone]} ${onClick ? "active:scale-[0.985] transition-transform" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs opacity-70 font-semibold">{label}</p>
        {Icon && <Icon className="w-4 h-4 opacity-50 shrink-0" />}
      </div>
      <p className="text-xl font-bold mt-2 tabular-nums">{value}</p>
      {hint && <p className="text-[11px] opacity-60 mt-1 truncate">{hint}</p>}
    </Tag>
  );
}

/* ------------------------------------------------------------------ states */

export function Skeleton({ rows = 3 }) {
  return (
    <div className="space-y-3 p-4" data-testid="m-skeleton">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="bg-white rounded-[22px] p-4 border border-black/[0.04]">
          <div className="h-3.5 w-1/3 rounded-full m-shimmer mb-3" />
          <div className="h-3 w-2/3 rounded-full m-shimmer mb-2 opacity-70" />
          <div className="h-3 w-1/2 rounded-full m-shimmer opacity-50" />
        </div>
      ))}
    </div>
  );
}

export function EmptyState({ title = "لا توجد بيانات", hint, action }) {
  return (
    <div className="px-6 py-16 text-center m-page-fade" data-testid="m-empty">
      <div className="w-16 h-16 rounded-[22px] bg-white border border-black/[0.04] mx-auto flex items-center justify-center mb-4 shadow-[0_6px_20px_-12px_rgba(10,37,64,0.4)]">
        <Inbox className="w-7 h-7 text-[#0A2540]/35" />
      </div>
      <p className="font-semibold text-[#0A2540]">{title}</p>
      {hint && <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">{hint}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="px-6 py-14 text-center m-page-fade" data-testid="m-error">
      <div className="w-16 h-16 rounded-[22px] bg-red-50 border border-red-100 mx-auto flex items-center justify-center mb-4">
        <AlertCircle className="w-7 h-7 text-red-500" />
      </div>
      <p className="font-semibold text-[#0A2540]">تعذّر تحميل البيانات</p>
      <p className="text-xs text-muted-foreground mt-1.5 break-words">{message}</p>
      {onRetry && (
        <button onClick={() => { haptic("light"); onRetry(); }} data-testid="m-retry-btn"
                className="mt-5 h-12 px-6 rounded-full bg-[#0A2540] text-white text-sm font-bold inline-flex items-center gap-2 active:scale-95 transition-transform">
          <RefreshCw className="w-4 h-4" /> إعادة المحاولة
        </button>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------- buttons */

export function PrimaryButton({ children, loading, className = "", onClick, ...props }) {
  return (
    <button {...props} disabled={loading || props.disabled}
            onClick={onClick ? (e) => { haptic("medium"); onClick(e); } : undefined}
            className={`w-full h-14 rounded-2xl bg-[#0A2540] text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-40 active:scale-[0.98] transition-transform shadow-[0_10px_24px_-14px_rgba(10,37,64,0.9)] ${className}`}>
      {loading && <Loader2 className="w-4 h-4 animate-spin" />}
      {children}
    </button>
  );
}

export function GoldButton({ children, className = "", onClick, ...props }) {
  return (
    <button {...props} onClick={onClick ? (e) => { haptic("medium"); onClick(e); } : undefined}
            className={`w-full h-14 rounded-2xl bg-[#D4AF37] text-[#0A2540] font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-40 active:scale-[0.98] transition-transform shadow-[0_10px_24px_-14px_rgba(212,175,55,0.9)] ${className}`}>
      {children}
    </button>
  );
}

export function GhostButton({ children, className = "", onClick, ...props }) {
  return (
    <button {...props} onClick={onClick ? (e) => { haptic("light"); onClick(e); } : undefined}
            className={`w-full h-13 min-h-[3.25rem] rounded-2xl bg-white border border-black/[0.07] text-[#0A2540] font-semibold text-sm flex items-center justify-center gap-2 active:scale-[0.98] transition-transform ${className}`}>
      {children}
    </button>
  );
}

export function DangerButton({ children, className = "", onClick, ...props }) {
  return (
    <button {...props} onClick={onClick ? (e) => { haptic("warning"); onClick(e); } : undefined}
            className={`w-full h-14 rounded-2xl bg-white border border-red-200 text-red-600 font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-40 active:scale-[0.98] transition-transform ${className}`}>
      {children}
    </button>
  );
}

export function Fab({ icon: Icon, label, onClick, testid }) {
  return (
    <button onClick={() => { haptic("medium"); onClick(); }} data-testid={testid}
            className="fixed z-30 bottom-[calc(5.5rem+env(safe-area-inset-bottom))] end-4 h-13 min-h-[3.25rem] px-5 rounded-full bg-[#D4AF37] text-[#0A2540] font-bold text-sm flex items-center gap-2 shadow-[0_12px_28px_-12px_rgba(10,37,64,0.7)] active:scale-95 transition-transform">
      {Icon && <Icon className="w-5 h-5" />} {label}
    </button>
  );
}

/* ------------------------------------------------------------------ inputs */

export const mInput =
  "w-full h-14 rounded-2xl border border-black/[0.08] bg-white px-4 text-sm text-[#0A2540] placeholder:text-[#0A2540]/35 focus:outline-none focus:border-[#0A2540] focus:ring-4 focus:ring-[#0A2540]/5 transition-colors";

export function MField({ label, children, hint }) {
  return (
    <label className="block mb-4">
      {label && <span className="block text-xs font-bold text-[#0A2540] mb-2">{label}</span>}
      {children}
      {hint && <span className="block text-[11px] text-muted-foreground mt-1.5 leading-relaxed">{hint}</span>}
    </label>
  );
}

export function SearchField({ value, onChange, onSubmit, placeholder = "ابحث", testid }) {
  return (
    <div className="relative flex-1">
      <input className={`${mInput} ps-11 pe-10`} placeholder={placeholder} value={value} data-testid={testid}
             onChange={(e) => onChange(e.target.value)}
             onKeyDown={(e) => e.key === "Enter" && onSubmit?.()} />
      <Search className="w-[18px] h-[18px] absolute inset-y-0 my-auto start-4 text-[#0A2540]/35" />
      {value ? (
        <button onClick={() => { onChange(""); onSubmit?.(""); }} aria-label="مسح"
                className="absolute inset-y-0 end-3 my-auto w-7 h-7 rounded-full bg-[#0A2540]/6 flex items-center justify-center">
          <X className="w-3.5 h-3.5 text-[#0A2540]/50" />
        </button>
      ) : null}
    </div>
  );
}

/** Native-style picker: a row that opens a bottom sheet — never the browser dropdown. */
export function SheetSelect({ label, value, onChange, options = [], placeholder = "— اختر —", testid, hint, title }) {
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => String(o.value) === String(value));
  return (
    <div className="mb-4">
      {label && <span className="block text-xs font-bold text-[#0A2540] mb-2">{label}</span>}
      <button type="button" onClick={() => { haptic("light"); setOpen(true); }} data-testid={testid}
              className="w-full h-14 rounded-2xl border border-black/[0.08] bg-white px-4 flex items-center justify-between text-start active:scale-[0.99] transition-transform">
        <span className={`text-sm truncate ${selected ? "text-[#0A2540] font-semibold" : "text-[#0A2540]/40"}`}>
          {selected ? selected.label : placeholder}
        </span>
        <ChevronDown className="w-4 h-4 text-[#0A2540]/40 shrink-0" />
      </button>
      {hint && <span className="block text-[11px] text-muted-foreground mt-1.5">{hint}</span>}
      <Sheet open={open} onClose={() => setOpen(false)} title={title || label} testid={`${testid}-sheet`}>
        <div className="-mx-1">
          {options.length === 0 && <p className="text-xs text-muted-foreground px-1 py-3">لا خيارات متاحة</p>}
          {options.map((o) => {
            const active = String(o.value) === String(value);
            return (
              <button key={String(o.value)} type="button" data-testid={`${testid}-option-${o.value}`}
                      onClick={() => { haptic("light"); onChange(o.value); setOpen(false); }}
                      className="w-full flex items-center gap-3 px-3 py-4 rounded-2xl text-start active:bg-slate-50">
                <span className={`text-sm flex-1 ${active ? "font-bold text-[#0A2540]" : "text-[#0A2540]/80"}`}>{o.label}</span>
                {active && <Check className="w-4 h-4 text-[#D4AF37]" />}
              </button>
            );
          })}
        </div>
      </Sheet>
    </div>
  );
}

/** Date row — keeps the OS date picker (that IS the native control) but styled as a row. */
export function DateField({ label, value, onChange, testid, min, max }) {
  return (
    <label className="block mb-4">
      {label && <span className="block text-xs font-bold text-[#0A2540] mb-2">{label}</span>}
      <span className="relative block">
        <input type="date" value={value || ""} min={min} max={max} data-testid={testid}
               onChange={(e) => onChange(e.target.value)}
               className={`${mInput} pe-11 appearance-none`} />
        <CalendarDays className="w-[18px] h-[18px] absolute inset-y-0 my-auto end-4 text-[#0A2540]/35 pointer-events-none" />
      </span>
    </label>
  );
}

/** Camera / gallery / file picker styled as a mobile action, not a raw file input. */
export function FilePicker({ label, hint, accept, onFile, testid, busy, done, doneLabel = "تم الرفع" }) {
  const ref = useRef(null);
  return (
    <div className="mb-4">
      {label && <span className="block text-xs font-bold text-[#0A2540] mb-2">{label}</span>}
      <input ref={ref} type="file" accept={accept} capture="environment" data-testid={testid}
             className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
      <button type="button" onClick={() => { haptic("light"); ref.current?.click(); }}
              className={`w-full h-14 rounded-2xl border-2 border-dashed flex items-center justify-center gap-2 text-sm font-bold active:scale-[0.99] transition-transform ${
                done ? "border-emerald-300 bg-emerald-50 text-emerald-800"
                     : "border-[#0A2540]/20 bg-white text-[#0A2540]"}`}>
        {busy ? <Loader2 className="w-4 h-4 animate-spin" />
          : done ? <Check className="w-4 h-4" /> : <Camera className="w-4 h-4" />}
        {busy ? "جارٍ الرفع…" : done ? doneLabel : "التقاط صورة أو اختيار ملف"}
      </button>
      {hint && <span className="block text-[11px] text-muted-foreground mt-1.5 leading-relaxed">{hint}</span>}
    </div>
  );
}

/** Segmented control / filter chips row. items: [[value, label], ...] */
export function Segmented({ items, value, onChange, testid, testidPrefix, scroll = false }) {
  return (
    <div data-testid={testid}
         className={`flex gap-2 ${scroll ? "overflow-x-auto m-hscroll -mx-4 px-4" : ""}`}>
      {items.map(([v, l]) => {
        const active = v === value;
        return (
          <button key={v || "all"} onClick={() => { haptic("light"); onChange(v); }}
                  data-testid={testidPrefix ? `${testidPrefix}${v || "all"}` : undefined}
                  className={`h-11 px-4 rounded-full text-xs font-bold whitespace-nowrap transition-colors active:scale-95 ${
                    active ? "bg-[#0A2540] text-white shadow-[0_8px_18px_-12px_rgba(10,37,64,0.9)]"
                           : "bg-white border border-black/[0.06] text-[#0A2540]/70"}`}>
            {l}
          </button>
        );
      })}
    </div>
  );
}

export function Chip({ children, tone = "neutral" }) {
  const tones = {
    neutral: "bg-[#0A2540]/6 text-[#0A2540]",
    gold: "bg-[#D4AF37]/18 text-[#7a6216]",
    good: "bg-emerald-50 text-emerald-700",
    warn: "bg-amber-50 text-amber-800",
    bad: "bg-red-50 text-red-700",
  };
  return <span className={`text-[11px] font-bold rounded-full px-2.5 py-1 ${tones[tone]}`}>{children}</span>;
}

/* ------------------------------------------------------------------ sheets */

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
      <div className="absolute inset-0 bg-black/45 m-backdrop" onClick={onClose} data-testid="m-sheet-backdrop" />
      <div className="relative w-full bg-white rounded-t-[28px] p-5 pb-[max(1.5rem,env(safe-area-inset-bottom))] max-h-[88dvh] overflow-y-auto m-sheet">
        <div className="w-11 h-1.5 bg-slate-200 rounded-full mx-auto mb-4" />
        {title && <h2 className="font-head text-base font-bold text-[#0A2540] mb-4">{title}</h2>}
        {children}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- feedback */

export function StatusPill({ status }) {
  const map = {
    pending: ["بانتظار المراجعة", "bg-amber-100 text-amber-800"],
    pending_approval: ["بانتظار اعتماد", "bg-amber-100 text-amber-800"],
    approved: ["مقبول", "bg-emerald-100 text-emerald-700"],
    posted: ["مُرحَّل", "bg-emerald-100 text-emerald-700"],
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
  return <span className={`text-[11px] font-bold rounded-full px-2.5 py-1 whitespace-nowrap ${cls}`}>{label}</span>;
}

export function Money({ value, currency, className = "" }) {
  const n = Number(value || 0);
  return (
    <span className={`tabular-nums font-bold ${className}`} dir="ltr">
      {n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      {currency ? <span className="text-[11px] font-bold ms-1">{currency}</span> : null}
    </span>
  );
}

/* ------------------------------------------------------- pull to refresh */

const THRESHOLD = 68;

export function PullToRefresh({ onRefresh, children }) {
  const [pull, setPull] = useState(0);
  const [busy, setBusy] = useState(false);
  const start = useRef(null);

  const onTouchStart = (e) => {
    if (busy || window.scrollY > 0) return;
    start.current = e.touches[0].clientY;
  };
  const onTouchMove = (e) => {
    if (start.current === null || busy) return;
    const delta = e.touches[0].clientY - start.current;
    if (delta <= 0) { setPull(0); return; }
    setPull(Math.min(delta * 0.45, 90));
  };
  const onTouchEnd = async () => {
    if (start.current === null) return;
    const reached = pull >= THRESHOLD * 0.7;
    start.current = null;
    if (!reached) { setPull(0); return; }
    setBusy(true);
    setPull(46);
    haptic("light");
    try { await onRefresh(); } finally { setBusy(false); setPull(0); }
  };

  return (
    <div onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd}
         onTouchCancel={onTouchEnd} data-testid="m-ptr">
      <div className="relative">
        <div className="absolute inset-x-0 top-0 flex justify-center pointer-events-none"
             style={{ height: pull, opacity: pull > 6 ? 1 : 0 }}>
          <div className="mt-2 w-9 h-9 rounded-full bg-white shadow flex items-center justify-center">
            <RefreshCw className={`w-4 h-4 text-[#0A2540] ${busy ? "animate-spin" : ""}`}
                       style={{ transform: busy ? undefined : `rotate(${pull * 3}deg)` }} />
          </div>
        </div>
        <div className={`${start.current !== null ? "m-ptr-dragging" : "m-ptr-track"}`}
             style={{ transform: `translateY(${pull}px)` }}>
          {children}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ async */

/** Stale-while-revalidate cache so returning to a tab is instant (no blank reload). */
const CACHE = new Map();

export function useAsync(loader, deps = [], { cacheKey } = {}) {
  const cached = cacheKey ? CACHE.get(cacheKey) : undefined;
  const [data, setData] = useState(cached ?? null);
  const [loading, setLoading] = useState(cached === undefined);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    const hasCache = cacheKey ? CACHE.has(cacheKey) : false;
    if (!hasCache || tick > 0) setLoading(true);
    setError("");
    Promise.resolve(loader())
      .then((d) => {
        if (!alive) return;
        setData(d);
        if (cacheKey) CACHE.set(cacheKey, d);
      })
      .catch((e) => alive && setError(e?.response?.data?.detail || e?.message || "خطأ غير معروف"))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, reload, setData };
}

export function clearAsyncCache() { CACHE.clear(); }
