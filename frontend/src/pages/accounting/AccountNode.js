import { ChevronDown, ChevronLeft } from "lucide-react";
import { Badge } from "./ui";

export const TYPE_AR = {
  asset: "أصول", liability: "خصوم", equity: "حقوق ملكية",
  revenue: "إيرادات", expense: "مصروفات",
};

function tagsFor(node) {
  const tags = [];
  if (node.is_group) tags.push(["مجموعة", "blue"]);
  if (node.out_of_scope) tags.push(["خارج نطاقك", "amber"]);
  if (node.is_system) tags.push(["نظامي", "slate"]);
  if (node.is_active === false) tags.push(["غير مفعّل", "red"]);
  return tags;
}

/** Flatten the chart into visible rows (iterative walk — collapsed nodes hide their subtree). */
export function flattenTree(roots, collapsed) {
  const rows = [];
  const stack = (roots || []).map((n) => ({ node: n, depth: 0 })).reverse();
  while (stack.length) {
    const { node, depth } = stack.pop();
    const kids = node.children || [];
    const isCollapsed = collapsed[node.code] ?? depth >= 1;
    rows.push({ node, depth, kids: kids.length, collapsed: isCollapsed });
    if (!isCollapsed) {
      for (let i = kids.length - 1; i >= 0; i -= 1) stack.push({ node: kids[i], depth: depth + 1 });
    }
  }
  return rows;
}

export default function AccountRow({ row, onToggle, onPick }) {
  const { node, depth, kids, collapsed } = row;
  return (
    <div className="flex items-center gap-2 py-2 border-b last:border-0"
         style={{ paddingInlineStart: depth * 16 }}>
      {kids > 0 ? (
        <button onClick={() => onToggle(node.code, !collapsed)} data-testid={`coa-toggle-${node.code}`}
                className="text-muted-foreground">
          {collapsed ? <ChevronLeft className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
      ) : <span className="w-4" />}
      <button className="flex-1 text-start" onClick={() => onPick(node)} data-testid={`coa-node-${node.code}`}>
        <span className="font-mono text-xs text-[#0A2540] font-semibold">{node.code}</span>
        <span className="mx-2 text-sm">{node.name_ar || node.name}</span>
        <span className="text-[11px] text-muted-foreground">{TYPE_AR[node.type] || node.type}</span>
        {tagsFor(node).map(([text, tone]) => (
          <span className="ms-2" key={text}><Badge tone={tone}>{text}</Badge></span>
        ))}
      </button>
    </div>
  );
}
