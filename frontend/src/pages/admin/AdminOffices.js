import { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { MessageCircle, RefreshCw } from "lucide-react";
import { toast } from "sonner";

export default function AdminOffices() {
  const [offices, setOffices] = useState([]);
  const [resyncing, setResyncing] = useState(false);
  const load = () => api.get("/admin/offices").then((r) => setOffices(r.data));
  useEffect(() => { load(); }, []);

  const resync = async () => {
    if (resyncing) return;
    setResyncing(true);
    try {
      const r = await api.post("/admin/packages/resync");
      toast.success(`تمت إعادة المزامنة — حُدّث ${r.data.updated} برنامج، وأُرسل ${r.data.rahal_notified} إلى رحال`);
    } catch (e) { toast.error(apiError(e)); } finally { setResyncing(false); }
  };

  const setStatus = async (id, status) => {
    try { await api.patch(`/admin/offices/${id}/status`, { status }); toast.success(status === "active" ? "تم التفعيل" : "تم الإيقاف"); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  // Normalize a stored phone into a wa.me-ready international number (digits only, no leading zeros/+)
  const waNumber = (raw) => {
    const digits = String(raw || "").replace(/\D/g, "").replace(/^0+/, "");
    return digits.length >= 8 ? digits : null;
  };

  return (
    <>
      <PageHeader title="إدارة المكاتب" subtitle="تفعيل، إيقاف، ومراقبة أرصدة المكاتب"
        action={<Button onClick={resync} disabled={resyncing} data-testid="batch-resync-btn" className="bg-[#0A2540] hover:bg-[#061A2E]"><RefreshCw className={`w-4 h-4 ${resyncing ? "animate-spin" : ""}`} /> {resyncing ? "جارٍ المزامنة..." : "إعادة مزامنة الأسعار"}</Button>} />
      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto">
        {offices.length === 0 ? <div className="p-10 text-center text-muted-foreground text-sm">لا توجد مكاتب</div> : (
          <table className="w-full text-sm min-w-[760px]">
            <thead className="text-muted-foreground text-xs border-b"><tr>
              {["المكتب", "البريد", "المالك", "المحافظة", "الهاتف", "واتساب", "متاح (ريال)", "متاح (دولار)", "الحالة", ""].map((h, i) => <th key={i} className="text-start px-6 py-3 font-medium">{h}</th>)}
            </tr></thead>
            <tbody>
              {offices.map((o) => (
                <tr key={o.id} className="border-b last:border-0" data-testid={`office-row-${o.id}`}>
                  <td className="px-6 py-4 font-medium">{o.office_name}</td>
                  <td className="px-6 py-4 text-xs text-muted-foreground">{o.email}</td>
                  <td className="px-6 py-4">{o.owner_name}</td>
                  <td className="px-6 py-4">{o.governorate}</td>
                  <td className="px-6 py-4 text-xs">{o.phone}</td>
                  <td className="px-6 py-4">
                    {waNumber(o.phone) ? (
                      <a href={`https://wa.me/${waNumber(o.phone)}?text=${encodeURIComponent(`مرحباً ${o.office_name || ""}، معك إدارة معراج نتورك`)}`}
                         target="_blank" rel="noopener noreferrer" data-testid={`whatsapp-${o.id}`}
                         className="inline-flex items-center gap-1.5 text-[#15803D] bg-[#F0FDF4] hover:bg-[#DCFCE7] border border-[#BBF7D0] px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors">
                        <MessageCircle className="w-3.5 h-3.5" /> {waNumber(o.phone)}
                      </a>
                    ) : <span className="text-xs text-muted-foreground">—</span>}
                  </td>
                  <td className="px-6 py-4 tabular font-semibold text-[#0A2540]">{money(o.wallet?.SAR?.available, "SAR")}</td>
                  <td className="px-6 py-4 tabular font-semibold text-[#0A2540]">{money(o.wallet?.USD?.available, "USD")}</td>
                  <td className="px-6 py-4">
                    <span className={`text-xs px-2 py-1 rounded-md font-semibold ${o.status === "active" ? "bg-[#F0FDF4] text-[#15803D]" : "bg-red-50 text-red-600"}`}>
                      {o.status === "active" ? "مفعّل" : "موقوف"}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    {o.status === "active"
                      ? <Button size="sm" variant="outline" className="h-8 text-red-600 border-red-200" onClick={() => setStatus(o.id, "suspended")} data-testid={`suspend-${o.id}`}>إيقاف</Button>
                      : <Button size="sm" className="h-8 bg-[#15803D] hover:bg-[#166534]" onClick={() => setStatus(o.id, "active")} data-testid={`activate-${o.id}`}>تفعيل</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
