import { useState } from "react";
import accApi from "@/mobile/api/accounting";
import { flattenTree } from "@/pages/accounting/AccountNode";
import { Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, useAsync } from "@/mobile/ui/kit";
import { ChevronDown, ChevronLeft } from "lucide-react";

const TYPE_AR = { asset: "أصول", liability: "خصوم", equity: "حقوق ملكية", revenue: "إيرادات", expense: "مصروفات" };

/** Read-oriented mobile chart browser (structural COA management stays on the web). */
export default function MAccChart() {
  const tree = useAsync(() => accApi.accountsTree());
  const [collapsed, setCollapsed] = useState({});
  const rows = flattenTree(tree.data?.roots, collapsed);
  const scope = tree.data?.account_scope;

  return (
    <Screen>
      <TopBar title="الدليل المحاسبي" subtitle={tree.data?.entity_id || "meraaj-platform"} back />
      <div className="p-4 space-y-3">
        {scope && !scope.unrestricted && (
          <div className="rounded-2xl bg-amber-50 border border-amber-200 text-amber-900 text-[11px] p-3"
               data-testid="m-chart-scope-note">
            معروض بحدود نطاقك: <b>{scope.label_ar}</b>
          </div>
        )}
        {tree.loading ? <Skeleton rows={4} />
          : tree.error ? <ErrorState message={tree.error} onRetry={tree.reload} />
          : rows.length === 0 ? <EmptyState title="لا حسابات" />
          : (
            <Card className="p-0 overflow-hidden" testid="m-chart-rows">
              {rows.map((row) => (
                <div key={row.node.code} className="flex items-center gap-2 px-3 py-2.5 border-b last:border-0"
                     style={{ paddingInlineStart: 12 + row.depth * 14 }}
                     data-testid={`m-chart-node-${row.node.code}`}>
                  {row.kids > 0 ? (
                    <button onClick={() => setCollapsed((c) => ({ ...c, [row.node.code]: !row.collapsed }))}
                            data-testid={`m-chart-toggle-${row.node.code}`} className="text-[#0A2540]/40">
                      {row.collapsed ? <ChevronLeft className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                  ) : <span className="w-4" />}
                  <div className="min-w-0 flex-1">
                    <p className="text-[11px] font-mono font-bold text-[#0A2540]">{row.node.code}</p>
                    <p className="text-[11px] text-muted-foreground truncate">
                      {row.node.name_ar || row.node.name} · {TYPE_AR[row.node.type] || row.node.type}
                      {row.node.is_group ? " · مجموعة" : ""}
                      {row.node.out_of_scope ? " · خارج نطاقك" : ""}
                    </p>
                  </div>
                </div>
              ))}
            </Card>
          )}
      </div>
    </Screen>
  );
}
