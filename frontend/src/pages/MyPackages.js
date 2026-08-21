import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate, PKG_TYPE } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Plus, Users } from "lucide-react";
import { toast } from "sonner";

export default function MyPackages() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);

  const load = () => api.get("/packages/mine").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);

  const toggle = async (id) => {
    try { await api.patch(`/packages/${id}/toggle`); toast.success("تم تحديث حالة العرض"); load(); }
    catch { toast.error("تعذّر التحديث"); }
  };

  return (
    <>
      <PageHeader title="برامجي (كبائع)" subtitle="البرامج التي أضفتها للبيع في السوق"
        action={<Button data-testid="new-pkg-btn" onClick={() => navigate("/packages/new")} className="bg-[#0A2540] hover:bg-[#061A2E]"><Plus className="w-4 h-4" /> برنامج جديد</Button>} />

      {items.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">لم تضف أي برنامج بعد</div>
      ) : (
        <div className="bg-white rounded-2xl border card-shadow overflow-x-auto">
          <table className="w-full text-sm min-w-[640px]">
            <thead className="text-muted-foreground text-xs border-b">
              <tr>
                <th className="text-start px-6 py-3 font-medium">البرنامج</th>
                <th className="text-start px-6 py-3 font-medium">النوع</th>
                <th className="text-start px-6 py-3 font-medium">الانطلاق</th>
                <th className="text-start px-6 py-3 font-medium">المقاعد</th>
                <th className="text-start px-6 py-3 font-medium">سعر البيع</th>
                <th className="text-start px-6 py-3 font-medium">الحالة</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} className="border-b last:border-0" data-testid={`mypkg-row-${p.id}`}>
                  <td className="px-6 py-4 font-medium">{p.title}</td>
                  <td className="px-6 py-4">{PKG_TYPE[p.type] || p.type}</td>
                  <td className="px-6 py-4">{fmtDate(p.departure_date)}</td>
                  <td className="px-6 py-4 tabular"><span className="flex items-center gap-1"><Users className="w-3.5 h-3.5" />{p.available_seats}/{p.total_seats}</span></td>
                  <td className="px-6 py-4 tabular font-semibold text-[#0A2540]">{money(p.final_sale_price, p.currency)}</td>
                  <td className="px-6 py-4">
                    <Button variant={p.status === "listed" ? "outline" : "secondary"} size="sm"
                            data-testid={`toggle-pkg-${p.id}`} onClick={() => toggle(p.id)}>
                      {p.status === "listed" ? "معروض — إخفاء" : "مخفي — عرض"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
