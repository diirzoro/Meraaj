import { useState } from "react";
import { ChevronDown, ChevronLeft, Search } from "lucide-react";
import accApi from "@/mobile/api/accounting";
import { flattenTree } from "@/pages/accounting/AccountNode";
import { ScopeBanner } from "@/mobile/screens/MAccountingHub";
import {
  Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Chip, SearchField, useAsync,
} from "@/mobile/ui/kit";

const TYPE_AR = { asset: "أصول", liability: "خصوم", equity: "حقوق ملكية", revenue: "إيرادات", expense: "مصروفات" };
const TYPE_TONE = { asset: "good", liability: "warn", equity: "gold", revenue: "good", expense: "bad" };

/** Read-oriented mobile chart browser (structural COA management stays on the web). */
export default function MAccChart() {
  const tree = useAsync(() => accApi.accountsTree());
  const [collapsed, setCollapsed] = useState({});
  const [q, setQ] = useState("");
  const rows = flattenTree(tree.data?.roots, collapsed);
  const term = q.trim().toLowerCase();
  const visible = term
    ? rows.filter((r) => `${r.node.code} ${r.node.name_ar || ""} ${r.node.name || ""}`.toLowerCase().includes(term))
    : rows;

  return (
    <Screen refresh={tree.reload}>
      <TopBar title="الدليل المحاسبي" subtitle={tree.data?.entity_id || "meraaj-platform"} back />
      <div className="p-4 space-y-3.5">
        <ScopeBanner scope={tree.data?.account_scope} testid="m-chart-scope-note" label="نطاقك" />
        <SearchField value={q} onChange={setQ} placeholder="ابحث برقم أو اسم الحساب" testid="m-chart-search" />

        {tree.loading ? <Skeleton rows={4} />
          : tree.error ? <ErrorState message={tree.error} onRetry={tree.reload} />
          : visible.length === 0 ? <EmptyState title="لا حسابات مطابقة" />
          : (
            <Card className="p-0 overflow-hidden" testid="m-chart-rows">
              {visible.map((row) => (
                <div key={row.node.code}
                     className="flex items-center gap-2.5 px-3 py-3.5 border-b border-black/5 last:border-0"
                     style={{ paddingInlineStart: 12 + (term ? 0 : row.depth * 14) }}
                     data-testid={`m-chart-node-${row.node.code}`}>
                  {!term && row.kids > 0 ? (
                    <button onClick={() => setCollapsed((c) => ({ ...c, [row.node.code]: !row.collapsed }))}
                            data-testid={`m-chart-toggle-${row.node.code}`} aria-label="فتح/إغلاق"
                            className="w-8 h-8 rounded-full bg-[#0A2540]/[0.05] flex items-center justify-center text-[#0A2540]/50 shrink-0">
                      {row.collapsed ? <ChevronLeft className="w-4 h-4 rtl:rotate-180" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                  ) : <span className="w-8 shrink-0" />}
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-mono font-bold text-[#0A2540]" dir="ltr">{row.node.code}</p>
                    <p className="text-xs text-[#0A2540]/70 truncate mt-0.5">{row.node.name_ar || row.node.name}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <Chip tone={TYPE_TONE[row.node.type] || "neutral"}>
                      {TYPE_AR[row.node.type] || row.node.type}
                    </Chip>
                    {row.node.is_group ? <span className="text-[10px] text-muted-foreground">مجموعة</span> : null}
                    {row.node.out_of_scope ? <span className="text-[10px] text-amber-700">خارج نطاقك</span> : null}
                  </div>
                </div>
              ))}
            </Card>
          )}
      </div>
    </Screen>
  );
}
