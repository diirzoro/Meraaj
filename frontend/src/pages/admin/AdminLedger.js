import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Search, Download, Printer, Scale, RotateCcw, FileText } from "lucide-react";

export default function AdminLedger() {
  const [f, setF] = useState({ q: "", currency: "", txn_type: "", date_from: "", date_to: "", page: 1 });
  const [d, setD] = useState({ items: [], total: 0, inflow: {}, outflow: {}, net: {}, types: {} });
  const [recon, setRecon] = useState(null);
  const [voucher, setVoucher] = useState(null);
  const [voucherId, setVoucherId] = useState(null);
  const [loading, setLoading] = useState(true);

  const qs = useCallback(() => {
    const p = new URLSearchParams();
    Object.entries(f).forEach(([k, v]) => { if (v) p.set(k, v); });
    p.set("limit", "50");
    return p.toString();
  }, [f]);

  const load = useCallback(() => {
    setLoading(true);
    api.get(`/admin/ledger?${qs()}`).then((r) => setD(r.data)).finally(() => setLoading(false));
  }, [qs]);
  useEffect(() => { load(); }, [load]);

  const exportCsv = async () => {
    try {
      const r = await api.get(`/admin/ledger/export?${qs()}`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([r.data], { type: "text/csv;charset=utf-8" }));
      const a = document.createElement("a");
      a.href = url; a.download = "meraaj-ledger.csv"; a.click(); URL.revokeObjectURL(url);
      toast.success("تم تصدير الدفتر");
    } catch (e) { toast.error(apiError(e)); }
  };

  const pages = Math.max(1, Math.ceil(d.total / 50));

  return (
    <>
      <PageHeader title="دفتر الحركة المالي الموحّد" subtitle="كل قيد مالي في المنصة — قابل للتصفية والتصدير، مع سندات القبض والصرف والمطابقة المالية" />

      <div className="grid sm:grid-cols-2 gap-5 mb-5">
        {["SAR", "USD"].map((c) => (
          <div key={c} className="bg-white rounded-2xl border card-shadow p-5" data-testid={`ledger-tot-${c}`}>
            <div className="text-sm font-semibold text-muted-foreground mb-3">
              {c === "SAR" ? "الحركة — ريال سعودي" : "الحركة — دولار أمريكي"}
            </div>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <Box label="مدين (داخل)" v={money(d.inflow?.[c] || 0, c)} accent />
              <Box label="دائن (خارج)" v={money(d.outflow?.[c] || 0, c)} danger />
              <Box label="الصافي" v={money(d.net?.[c] || 0, c)} />
            </div>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-4 mb-5 flex flex-wrap gap-3 items-end" data-testid="ledger-filters">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 absolute top-2.5 right-3 text-muted-foreground" />
          <input value={f.q} onChange={(e) => setF({ ...f, q: e.target.value, page: 1 })} data-testid="ledger-search"
            placeholder="ابحث بالوصف أو المرجع" className="w-full h-9 rounded-md border border-input pr-9 pl-3 text-xs" />
        </div>
        <select value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value, page: 1 })} data-testid="ledger-currency"
          className="h-9 rounded-md border border-input px-2 text-xs">
          <option value="">كل العملات</option><option value="SAR">ريال</option><option value="USD">دولار</option>
        </select>
        <select value={f.txn_type} onChange={(e) => setF({ ...f, txn_type: e.target.value, page: 1 })} data-testid="ledger-type"
          className="h-9 rounded-md border border-input px-2 text-xs">
          <option value="">كل الأنواع</option>
          {Object.entries(d.types || {}).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <input type="date" value={f.date_from} onChange={(e) => setF({ ...f, date_from: e.target.value, page: 1 })}
          data-testid="ledger-from" className="h-9 rounded-md border border-input px-2 text-xs" />
        <input type="date" value={f.date_to} onChange={(e) => setF({ ...f, date_to: e.target.value, page: 1 })}
          data-testid="ledger-to" className="h-9 rounded-md border border-input px-2 text-xs" />
        <Button size="sm" variant="outline" onClick={() => setF({ q: "", currency: "", txn_type: "", date_from: "", date_to: "", page: 1 })}
          data-testid="ledger-reset"><RotateCcw className="w-3.5 h-3.5" /> تصفير</Button>
        <Button size="sm" className="bg-[#0A2540] hover:bg-[#061A2E]" onClick={exportCsv} data-testid="ledger-export">
          <Download className="w-4 h-4" /> تصدير Excel/CSV
        </Button>
        <Button size="sm" variant="outline" data-testid="recon-btn"
          onClick={async () => { const r = await api.get("/admin/reconciliation"); setRecon(r.data); }}>
          <Scale className="w-4 h-4" /> المطابقة المالية
        </Button>
        <span className="text-[11px] text-muted-foreground mr-auto" data-testid="ledger-count">
          {d.total} حركة
        </span>
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto" data-testid="ledger-table">
        <table className="w-full text-xs min-w-[880px]">
          <thead className="bg-[#F4F6F8] text-muted-foreground">
            <tr>{["التاريخ", "الحساب", "النوع", "الوصف", "المرجع", "المبلغ", ""].map((h) => (
              <th key={h} className="text-right font-semibold px-3 py-2.5">{h}</th>))}</tr>
          </thead>
          <tbody>
            {loading ? <tr><td colSpan={7} className="text-center py-12 text-muted-foreground">جارٍ التحميل...</td></tr>
              : d.items.length === 0 ? <tr><td colSpan={7} className="text-center py-12 text-muted-foreground" data-testid="ledger-empty">لا توجد حركات</td></tr>
                : d.items.map((t) => (
                  <tr key={t.id} className="border-t hover:bg-[#FAFBFC]" data-testid={`ledger-row-${t.id}`}>
                    <td className="px-3 py-2.5 whitespace-nowrap">{fmtDate(t.created_at)}</td>
                    <td className="px-3 py-2.5">{t.office_name}</td>
                    <td className="px-3 py-2.5"><span className="text-[10px] px-2 py-0.5 rounded bg-[#F4F6F8] text-[#0A2540]">{t.type_label}</span></td>
                    <td className="px-3 py-2.5 max-w-[280px] truncate">{t.description}</td>
                    <td className="px-3 py-2.5 font-mono text-[10px]">{(t.ref || "—").slice(-6)}</td>
                    <td className={`px-3 py-2.5 tabular font-bold ${Number(t.amount) < 0 ? "text-[#B91C1C]" : "text-[#15803D]"}`}>
                      {money(t.amount, t.currency)}
                    </td>
                    <td className="px-3 py-2.5">
                      <button data-testid={`voucher-${t.id}`} className="text-[#0A2540] underline inline-flex items-center gap-1"
                        onClick={async () => { const r = await api.get(`/admin/vouchers/${t.id}`); setVoucher(r.data); setVoucherId(t.id); }}>
                        <FileText className="w-3 h-3" /> سند
                      </button>
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-5" data-testid="ledger-pagination">
          <button disabled={f.page <= 1} onClick={() => setF({ ...f, page: f.page - 1 })} data-testid="ledger-prev"
            className="h-8 px-3 rounded-md border text-xs disabled:opacity-40">السابق</button>
          <span className="text-xs tabular">صفحة {f.page} من {pages}</span>
          <button disabled={f.page >= pages} onClick={() => setF({ ...f, page: f.page + 1 })} data-testid="ledger-next"
            className="h-8 px-3 rounded-md border text-xs disabled:opacity-40">التالي</button>
        </div>
      )}

      {/* Reconciliation */}
      <Dialog open={!!recon} onOpenChange={(o) => !o && setRecon(null)}>
        <DialogContent dir="rtl" className="max-w-2xl max-h-[80vh] overflow-y-auto" data-testid="recon-dialog">
          <DialogHeader><DialogTitle>المطابقة المالية (المحافظ مقابل الدفتر)</DialogTitle></DialogHeader>
          {recon && (
            <div className="space-y-4">
              <div className="grid sm:grid-cols-2 gap-3">
                {["SAR", "USD"].map((c) => (
                  <div key={c} className="bg-[#F4F6F8] rounded-lg p-3 text-xs space-y-1">
                    <div className="font-bold text-[#0A2540]">{c === "SAR" ? "ريال سعودي" : "دولار أمريكي"}</div>
                    <div>إجمالي المحافظ: <b className="tabular">{money(recon.wallets[c].total, c)}</b></div>
                    <div>متاح: <span className="tabular">{money(recon.wallets[c].available, c)}</span> • معلّق: <span className="tabular">{money(recon.wallets[c].pending, c)}</span></div>
                    <div>إجمالي الدفتر: <b className="tabular">{money(recon.ledger_totals[c], c)}</b></div>
                    <div>إيرادات المنصة: <span className="tabular">{money(recon.platform_revenue[c], c)}</span></div>
                  </div>
                ))}
              </div>
              <div className={`text-xs rounded-lg px-3 py-2 border ${recon.mismatch_count ? "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" : "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]"}`}>
                {recon.mismatch_count ? `${recon.mismatch_count} حساب غير مطابق` : "كل الحسابات مطابقة"}
              </div>
              {recon.mismatches.map((m, i) => (
                <div key={i} className="text-xs border rounded-lg px-3 py-2 flex justify-between" data-testid={`mismatch-${i}`}>
                  <span>{m.name} ({m.currency})</span>
                  <span className="tabular">محفظة {m.wallet_total} • دفتر {m.ledger_total} • فرق <b className="text-[#B91C1C]">{m.difference}</b></span>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Voucher */}
      <Dialog open={!!voucher} onOpenChange={(o) => !o && setVoucher(null)}>
        <DialogContent dir="rtl" className="max-w-md" data-testid="voucher-dialog">
          <DialogHeader><DialogTitle>{voucher?.kind_label} — {voucher?.voucher_no}</DialogTitle></DialogHeader>
          {voucher && (
            <div className="space-y-2 text-sm">
              <Row k="التاريخ" v={fmtDate(voucher.date)} />
              <Row k="الطرف" v={voucher.party.name} />
              <Row k="البريد" v={voucher.party.email} />
              <Row k="النوع" v={voucher.type_label} />
              <Row k="البيان" v={voucher.description} />
              <Row k="المرجع" v={voucher.ref || "—"} />
              <div className="bg-[#F4F6F8] rounded-lg px-3 py-2 flex justify-between items-center">
                <span className="text-xs text-muted-foreground">المبلغ</span>
                <span className="tabular text-lg font-bold text-[#0A2540]">{money(voucher.amount, voucher.currency)}</span>
              </div>
              <Button className="w-full bg-[#0A2540] hover:bg-[#061A2E]" data-testid="voucher-pdf-btn"
                onClick={async () => {
                  const r = await api.get(`/admin/vouchers/${voucher.txn_id || voucherId}/pdf`, { responseType: "blob" });
                  window.open(URL.createObjectURL(new Blob([r.data], { type: "application/pdf" })), "_blank");
                }}>
                <Printer className="w-4 h-4" /> تنزيل السند PDF
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

const Box = ({ label, v, accent, danger }) => (
  <div className="bg-[#F4F6F8] rounded-lg px-3 py-2">
    <div className="text-[10px] text-muted-foreground">{label}</div>
    <div className={`tabular text-sm font-bold ${danger ? "text-[#B91C1C]" : accent ? "text-[#15803D]" : "text-[#0A2540]"}`}>{v}</div>
  </div>
);

const Row = ({ k, v }) => (
  <div className="flex justify-between text-xs border-b pb-1.5">
    <span className="text-muted-foreground">{k}</span><span className="font-semibold text-[#0A2540]">{v}</span>
  </div>
);
