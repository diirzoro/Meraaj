import { Navigate, useNavigate } from "react-router-dom";
import * as Icons from "lucide-react";
import { useShell } from "@/mobile/MobileShell";
import { Screen, TopBar, Card, EmptyState, Skeleton } from "@/mobile/ui/kit";

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
  const scope = acc.account_scope;

  return (
    <Screen>
      <TopBar title="الحسابات" subtitle={`الدفتر المركزي · ${acc.entity_id || "meraaj-platform"}`} />
      <div className="p-4 space-y-3">
        {scope && !scope.unrestricted && (
          <div className="rounded-2xl bg-amber-50 border border-amber-200 text-amber-900 text-[11px] p-3"
               data-testid="m-acc-scope-note">
            نطاقك المحاسبي: <b>{scope.label_ar}</b> — {(scope.codes || []).join(" · ")}
          </div>
        )}
        {items.length === 0 ? (
          <EmptyState title="لا وظائف محاسبية متاحة لك" />
        ) : (
          <Card className="p-0 overflow-hidden" testid="m-acc-hub-items">
            {items.map((i) => (
              <button key={i.cap} onClick={() => navigate(i.route)} data-testid={`m-acc-item-${i.cap}`}
                      className="w-full flex items-center gap-3 px-4 py-3.5 border-b last:border-0 text-start active:bg-slate-50">
                <i.icon className="w-[18px] h-[18px] text-[#0A2540]/60" />
                <span className="text-sm text-[#0A2540] flex-1">{i.label}</span>
                <Icons.ChevronLeft className="w-4 h-4 text-[#0A2540]/30 rtl:rotate-180" />
              </button>
            ))}
          </Card>
        )}
        <p className="text-[11px] text-muted-foreground px-1">
          كل ترحيل أو اعتماد أو عكس أو إقفال يتحقق منه السيرفر وفق الصلاحيات ونطاق الحسابات
          والرقابة المزدوجة — لا يمكن تجاوزه من التطبيق.
        </p>
      </div>
    </Screen>
  );
}
