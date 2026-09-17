import { Navigate, useNavigate } from "react-router-dom";
import * as Icons from "lucide-react";
import { useShell } from "@/mobile/MobileShell";
import { Screen, TopBar, Card, ListRow, EmptyState, Skeleton, Chip } from "@/mobile/ui/kit";

/** ADMIN-ONLY accounting guard for the app: office/individual can never reach these
 *  screens, and an admin without accounting permissions sees nothing. The backend enforces
 *  the same rules on every call. */
export function AccountingGate({ capability, children }) {
  const { shell, loading } = useShell();
  if (loading && !shell) return <Screen><Skeleton rows={3} /></Screen>;
  const acc = shell?.accounting;
  if (shell?.experience !== "admin" || !acc?.enabled) return <Navigate to="/m/home" replace />;
  if (capability && !acc.capabilities?.[capability]) {
    return (
      <Screen>
        <TopBar title="غير مصرّح" back />
        <EmptyState title="لا تملك صلاحية هذه الوظيفة المحاسبية"
                    hint="الصلاحيات تُمنح من لوحة الصلاحيات والأمان" />
      </Screen>
    );
  }
  return children;
}

/** Shared scope banner — a scoped view must never look like the full picture. */
export function ScopeBanner({ scope, testid = "m-acc-scope-note", label = "نطاقك المحاسبي" }) {
  if (!scope || scope.unrestricted) return null;
  return (
    <div className="rounded-2xl bg-amber-50 border border-amber-200 text-amber-900 p-3.5 flex items-start gap-2.5"
         data-testid={testid}>
      <Icons.AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
      <p className="text-[11px] leading-relaxed">
        عرض جزئي بحدود {label}: <b>{scope.label_ar}</b>
        {(scope.codes || []).length ? ` — ${(scope.codes || []).join(" · ")}` : ""}
        <br />هذه ليست أرقام المنصة الكاملة.
      </p>
    </div>
  );
}

const ITEMS = [
  { cap: "chart_view", label: "الدليل المحاسبي", route: "/m/accounting/chart", icon: Icons.BookOpen },
  { cap: "vouchers_view", label: "السندات (قبض/صرف)", route: "/m/accounting/vouchers", icon: Icons.ReceiptText },
  { cap: "journals_view", label: "القيود اليومية", route: "/m/accounting/journals", icon: Icons.NotebookPen },
  { cap: "ledger_view", label: "الأستاذ وكشف الحساب", route: "/m/accounting/ledger", icon: Icons.Scale },
  { cap: "reports_view", label: "التقارير المالية", route: "/m/accounting/reports", icon: Icons.PieChart },
  { cap: "periods_view", label: "الفترات والإقفال", route: "/m/accounting/periods", icon: Icons.CalendarClock },
  { cap: "reconciliation_view", label: "المطابقة والتدقيق الذاتي", route: "/m/accounting/audit", icon: Icons.ShieldCheck },
];

export default function MAccountingHub() {
  const navigate = useNavigate();
  const { shell } = useShell();
  const acc = shell?.accounting || {};
  const items = ITEMS.filter((i) => acc.capabilities?.[i.cap]);

  return (
    <Screen>
      <TopBar title="الحسابات" subtitle={`الدفتر المركزي · ${acc.entity_id || "meraaj-platform"}`} large />
      <div className="p-4 space-y-4">
        <ScopeBanner scope={acc.account_scope} />

        {items.length === 0 ? (
          <EmptyState title="لا وظائف محاسبية متاحة لك" />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 m-stagger">
              {items.slice(0, 4).map((i) => (
                <button key={i.cap} onClick={() => navigate(i.route)} data-testid={`m-acc-item-${i.cap}`}
                        className="bg-white rounded-[22px] border border-black/[0.04] p-4 text-start active:scale-[0.97] transition-transform shadow-[0_6px_20px_-14px_rgba(10,37,64,0.5)]">
                  <span className="w-11 h-11 rounded-2xl bg-[#0A2540]/[0.06] flex items-center justify-center mb-3">
                    <i.icon className="w-5 h-5 text-[#0A2540]" />
                  </span>
                  <p className="text-xs font-bold text-[#0A2540] leading-snug">{i.label}</p>
                </button>
              ))}
            </div>
            {items.length > 4 && (
              <Card className="p-0 overflow-hidden" testid="m-acc-hub-items">
                {items.slice(4).map((i, idx, arr) => (
                  <ListRow key={i.cap} icon={i.icon} label={i.label} testid={`m-acc-item-${i.cap}`}
                           onClick={() => navigate(i.route)} last={idx === arr.length - 1} />
                ))}
              </Card>
            )}
          </>
        )}

        <div className="flex items-start gap-2.5 px-1">
          <Icons.Lock className="w-4 h-4 text-[#0A2540]/35 mt-0.5 shrink-0" />
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            كل ترحيل أو اعتماد أو عكس أو إقفال يتحقق منه السيرفر وفق الصلاحيات ونطاق الحسابات
            والرقابة المزدوجة — لا يمكن تجاوزه من التطبيق.
          </p>
        </div>
      </div>
    </Screen>
  );
}
