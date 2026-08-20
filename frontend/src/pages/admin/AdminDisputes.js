import { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import StatusBadge from "@/components/StatusBadge";
import { toast } from "sonner";

export default function AdminDisputes() {
  const [items, setItems] = useState([]);
  const load = () => api.get("/admin/disputes").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);

  const resolve = async (id, resolution) => {
    try { await api.post(`/admin/disputes/${id}/resolve`, { resolution }); toast.success("تم حسم النزاع"); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  const open = items.filter((b) => b.dispute?.status === "open");
  const resolved = items.filter((b) => b.dispute?.status !== "open");

  return (
    <>
      <PageHeader title="إدارة النزاعات" subtitle="حسم اعتراضات فترة التفويج (24 ساعة) والتدخل اليدوي في الأرصدة المعلّقة" />

      {open.length === 0 && resolved.length === 0 && <div className="text-center py-20 text-muted-foreground">لا توجد نزاعات</div>}

      {open.length > 0 && <h3 className="font-head font-bold text-[#0A2540] mb-4">نزاعات مفتوحة</h3>}
      <div className="space-y-4 mb-8">
        {open.map((b) => (
          <div key={b.id} className="bg-white rounded-2xl border card-shadow p-5" data-testid={`dispute-${b.id}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="font-head font-bold text-[#0A2540]">{b.package_title}</div>
                <div className="text-xs text-muted-foreground mt-1">المشتري: {b.buyer_office_name} • البائع: {b.seller_office_name}</div>
              </div>
              <StatusBadge status={b.status} />
            </div>
            <div className="bg-[#FEFCE8] border border-[#FEF08A] rounded-lg p-3 mt-4 text-sm text-[#A16207]">
              <span className="font-semibold">سبب الاعتراض: </span>{b.dispute?.reason || "-"}
            </div>
            <div className="grid sm:grid-cols-2 gap-3 mt-4 text-sm">
              <div className="bg-[#F4F6F8] rounded-lg px-4 py-3"><div className="text-xs text-muted-foreground">الرصيد المعلّق</div><div className="tabular font-bold text-[#0A2540]">{money(b.net_cost_total, b.currency)}</div></div>
              <div className="bg-[#F4F6F8] rounded-lg px-4 py-3"><div className="text-xs text-muted-foreground">المدفوع من المشتري</div><div className="tabular font-bold text-[#0A2540]">{money(b.amount_charged, b.currency)}</div></div>
            </div>
            <div className="flex gap-2 mt-4 pt-4 border-t">
              <Button size="sm" className="bg-[#0A2540] hover:bg-[#061A2E]" onClick={() => resolve(b.id, "refund_buyer")} data-testid={`refund-buyer-${b.id}`}>إرجاع الأموال للمشتري</Button>
              <Button size="sm" variant="outline" onClick={() => resolve(b.id, "release_seller")} data-testid={`release-seller-${b.id}`}>فك الرصيد للبائع</Button>
            </div>
          </div>
        ))}
      </div>

      {resolved.length > 0 && (
        <>
          <h3 className="font-head font-bold text-[#0A2540] mb-4">نزاعات محسومة</h3>
          <div className="space-y-3">
            {resolved.map((b) => (
              <div key={b.id} className="bg-white rounded-2xl border card-shadow p-4 flex items-center justify-between text-sm" data-testid={`resolved-dispute-${b.id}`}>
                <div><span className="font-semibold text-[#0A2540]">{b.package_title}</span> <span className="text-xs text-muted-foreground">— {b.buyer_office_name}</span></div>
                <span className="text-xs px-2 py-1 rounded-md bg-[#F0FDF4] text-[#15803D] font-semibold">
                  {b.dispute?.resolution === "refund_buyer" ? "أُرجعت للمشتري" : "فُكّت للبائع"}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
