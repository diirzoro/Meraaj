import { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Check, X, ExternalLink } from "lucide-react";
import { toast } from "sonner";

export default function AdminFinance() {
  const [tab, setTab] = useState("topups");
  const [topups, setTopups] = useState([]);
  const [transfers, setTransfers] = useState([]);
  const [withdrawals, setWithdrawals] = useState([]);
  const [preview, setPreview] = useState(null);

  const load = () => {
    api.get("/admin/topups?status=pending").then((r) => setTopups(r.data));
    api.get("/admin/transfers?status=pending").then((r) => setTransfers(r.data));
    api.get("/admin/withdrawals?status=pending").then((r) => setWithdrawals(r.data));
  };
  useEffect(() => { load(); }, []);

  const review = async (kind, id, approve) => {
    try { await api.post(`/admin/${kind}/${id}/review`, { approve }); toast.success(approve ? "تم الاعتماد" : "تم الرفض"); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  return (
    <>
      <PageHeader title="المركز المالي" subtitle="اعتماد ومراجعة العمليات المالية" />

      <div className="flex gap-1 bg-white border rounded-xl p-1 card-shadow w-fit mb-5">
        {[["topups", `الشحن (${topups.length})`], ["transfers", `التحويلات (${transfers.length})`], ["withdrawals", `السحوبات (${withdrawals.length})`]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`fin-tab-${k}`}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === k ? "bg-[#0A2540] text-white" : "text-muted-foreground hover:text-[#0A2540]"}`}>{l}</button>
        ))}
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto">
        {tab === "topups" && (
          <Table empty="لا توجد طلبات شحن" head={["المكتب", "المبلغ", "الطريقة", "الإشعار", "التاريخ", ""]}>
            {topups.map((t) => (
              <tr key={t.id} className="border-b last:border-0" data-testid={`topup-row-${t.id}`}>
                <td className="px-6 py-3 font-medium">{t.office_name}</td>
                <td className="px-6 py-3 tabular font-semibold text-[#0A2540]">{money(t.amount, t.currency)}</td>
                <td className="px-6 py-3">{t.method}</td>
                <td className="px-6 py-3">{t.receipt_url ? <button onClick={() => setPreview(t.receipt_url)} className="text-[#0A2540] flex items-center gap-1 text-xs hover:underline" data-testid={`view-receipt-${t.id}`}><ExternalLink className="w-3.5 h-3.5" /> عرض</button> : "-"}</td>
                <td className="px-6 py-3 text-xs text-muted-foreground">{fmtDate(t.created_at)}</td>
                <td className="px-6 py-3"><Actions onOk={() => review("topups", t.id, true)} onNo={() => review("topups", t.id, false)} /></td>
              </tr>
            ))}
          </Table>
        )}
        {tab === "transfers" && (
          <Table empty="لا توجد تحويلات" head={["من", "إلى", "المبلغ", "التاريخ", ""]}>
            {transfers.map((t) => (
              <tr key={t.id} className="border-b last:border-0" data-testid={`transfer-row-${t.id}`}>
                <td className="px-6 py-3 font-medium">{t.from_office_name}</td>
                <td className="px-6 py-3">{t.to_office_name}</td>
                <td className="px-6 py-3 tabular font-semibold text-[#0A2540]">{money(t.amount, t.currency)}</td>
                <td className="px-6 py-3 text-xs text-muted-foreground">{fmtDate(t.created_at)}</td>
                <td className="px-6 py-3"><Actions onOk={() => review("transfers", t.id, true)} onNo={() => review("transfers", t.id, false)} /></td>
              </tr>
            ))}
          </Table>
        )}
        {tab === "withdrawals" && (
          <Table empty="لا توجد سحوبات" head={["المكتب", "المبلغ", "الطريقة", "التفاصيل", "التاريخ", ""]}>
            {withdrawals.map((t) => (
              <tr key={t.id} className="border-b last:border-0" data-testid={`withdraw-row-${t.id}`}>
                <td className="px-6 py-3 font-medium">{t.office_name}</td>
                <td className="px-6 py-3 tabular font-semibold text-[#0A2540]">{money(t.amount, t.currency)}</td>
                <td className="px-6 py-3">{t.method}</td>
                <td className="px-6 py-3 text-xs max-w-[180px] truncate">{t.details}</td>
                <td className="px-6 py-3 text-xs text-muted-foreground">{fmtDate(t.created_at)}</td>
                <td className="px-6 py-3"><Actions onOk={() => review("withdrawals", t.id, true)} onNo={() => review("withdrawals", t.id, false)} /></td>
              </tr>
            ))}
          </Table>
        )}
      </div>

      <Dialog open={!!preview} onOpenChange={() => setPreview(null)}>
        <DialogContent dir="rtl"><DialogHeader><DialogTitle className="font-head text-[#0A2540]">إشعار الحوالة</DialogTitle></DialogHeader>
          {preview && (String(preview).includes("application/pdf") || String(preview).toLowerCase().endsWith(".pdf")
            ? <a href={preview} target="_blank" rel="noreferrer" className="block text-center bg-[#0A2540] text-white rounded-lg py-3 font-semibold">فتح ملف الإشعار (PDF)</a>
            : <img src={preview} alt="receipt" className="w-full rounded-lg border" />)}
        </DialogContent>
      </Dialog>
    </>
  );
}

const Table = ({ head, children, empty }) => {
  const rows = Array.isArray(children) ? children : [children];
  const has = rows.filter(Boolean).length > 0;
  if (!has) return <div className="p-10 text-center text-muted-foreground text-sm">{empty}</div>;
  return (
    <table className="w-full text-sm min-w-[640px]">
      <thead className="text-muted-foreground text-xs border-b"><tr>{head.map((h, i) => <th key={i} className="text-start px-6 py-3 font-medium">{h}</th>)}</tr></thead>
      <tbody>{children}</tbody>
    </table>
  );
};

const Actions = ({ onOk, onNo }) => (
  <div className="flex gap-2">
    <Button size="sm" className="bg-[#15803D] hover:bg-[#166534] h-8" onClick={onOk} data-testid="approve-btn"><Check className="w-4 h-4" /> اعتماد</Button>
    <Button size="sm" variant="outline" className="h-8 text-red-600 border-red-200" onClick={onNo} data-testid="reject-btn"><X className="w-4 h-4" /> رفض</Button>
  </div>
);
