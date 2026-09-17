/** Shared atoms for the accounting screens — one visual language with the rest of Meraaj. */
import { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { AlertTriangle, Loader2 } from "lucide-react";

export const ENTITY = "meraaj-platform";

export function Panel({ title, subtitle, action, children, testid }) {
  return (
    <section className="bg-white rounded-2xl border card-shadow p-5 mb-5" data-testid={testid}>
      {(title || action) && (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <div>
            {title && <h2 className="font-head text-base md:text-lg font-bold text-[#0A2540]">{title}</h2>}
            {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold text-muted-foreground mb-1">{label}</span>
      {children}
    </label>
  );
}

export const inputCls =
  "w-full h-10 rounded-lg border border-input bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#0A2540]/20";

export function Empty({ children = "لا توجد بيانات" }) {
  return <div className="py-10 text-center text-sm text-muted-foreground" data-testid="acc-empty">{children}</div>;
}

export function Loading() {
  return (
    <div className="py-10 flex items-center justify-center text-muted-foreground" data-testid="acc-loading">
      <Loader2 className="w-5 h-5 animate-spin" />
    </div>
  );
}

export function ErrorNote({ children, testid = "acc-error" }) {
  if (!children) return null;
  return (
    <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 text-red-800 text-sm p-3 mb-4" data-testid={testid}>
      <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

export function ScopeNote({ scope }) {
  if (!scope || scope.unrestricted) return null;
  return (
    <div className="rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-xs p-3 mb-4" data-testid="acc-scope-note">
      نطاقك المحاسبي: <b>{scope.label_ar}</b> — {(scope.codes || []).join(" · ") || "—"}
      <span className="block mt-1 text-amber-800/80">البيانات المعروضة مقصورة على هذه الحسابات فقط.</span>
    </div>
  );
}

export function Money({ value }) {
  const n = Number(value || 0);
  return <span className={n < 0 ? "text-red-600" : ""}>{n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>;
}

/** GET once with loading/error handling; `deps` re-fetches. */
export function useFetch(url, deps = [], initial = null) {
  const [data, setData] = useState(initial);
  const [loading, setLoading] = useState(!!url);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!url) return;
    let alive = true;
    setLoading(true); setError("");
    api.get(url)
      .then((r) => alive && setData(r.data))
      .catch((e) => alive && setError(apiError(e)))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, tick, ...deps]);
  return { data, loading, error, reload: () => setTick((t) => t + 1), setData };
}

/** Renders children only when the user holds the permission (UI convenience — the
 *  backend enforces the same permission independently). */
export function Gate({ perm, children, fallback = null }) {
  const { can } = useAuth();
  return can(perm) ? children : fallback;
}

export const STATUS_AR = {
  POSTED: "مُرحَّل", DRAFT: "مسودة", REVERSED: "معكوس", VOID: "ملغى",
  posted: "مُرحَّل", draft: "مسودة", pending_approval: "بانتظار الاعتماد",
  cancelled: "ملغى", approving: "جارٍ الاعتماد",
};

export function Badge({ children, tone = "slate" }) {
  const tones = {
    slate: "bg-slate-100 text-slate-700", green: "bg-emerald-100 text-emerald-700",
    amber: "bg-amber-100 text-amber-800", red: "bg-red-100 text-red-700",
    blue: "bg-blue-100 text-blue-700",
  };
  return <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold ${tones[tone]}`}>{children}</span>;
}

export function statusTone(s) {
  if (["POSTED", "posted"].includes(s)) return "green";
  if (["REVERSED", "cancelled", "VOID"].includes(s)) return "red";
  if (["pending_approval", "DRAFT", "draft"].includes(s)) return "amber";
  return "slate";
}
