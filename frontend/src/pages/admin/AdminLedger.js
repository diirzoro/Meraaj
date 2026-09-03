import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Search, Download, Printer, Scale, RotateCcw, FileText } from "lucide-react";

export default function AdminLedger() {
  const [f, setF] = useState({ q: "", office_q: "", ref: "", currency: "", txn_type: "", date_from: "", date_to: "", page: 1 });
  const [d, setD] = useState({ items: [], total: 0, inflow: {}, outflow: {}, net: {}, types: {} });
  const [recon, setRecon] = useState(null);
  const [prev, setPrev] = useState(null);
  const [stmt, setStmt] = useState(null);
  const [voucher, setVoucher] = useState(null);
  const [voucherId, setVoucherId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const qs = useCallback(() => {
    const p = new URLSearchParams();
    Object.entries(f).forEach(([k, v]) => { if (v) p.set(k, v); });
    p.set("limit", "50");
    return p.toString();
  }, [f]);

  const load = useCallback(() => {
    setLoading(true);
    setErr("");
    api.get(`/admin/ledger?${qs()}`)
      .then((r) => setD(r.data))
      .catch((e) => { setErr(apiError(e)); toast.error(apiError(e)); })
      .finally(() => setLoading(false));
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
        <input value={f.office_q} onChange={(e) => setF({ ...f, office_q: e.target.value, page: 1 })}
          data-testid="ledger-office" placeholder="المكتب / المستخدم"
          className="h-9 rounded-md border border-input px-3 text-xs min-w-[150px]" />
        <input value={f.ref} onChange={(e) => setF({ ...f, ref: e.target.value, page: 1 })}
          data-testid="ledger-ref" placeholder="مرجع الطلب"
          className="h-9 rounded-md border border-input px-3 text-xs min-w-[130px]" />
        <select value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value, page: 1 })} data-testid="ledger-currency"
          className="h-9 rounded-md border border-input px-2 text-xs">
          <option value="">كل العملات</option><option value="SAR">ريال سعودي</option><option value="USD">دولار أمريكي</option>
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
        <Button size="sm" variant="outline" onClick={() => setF({ q: "", office_q: "", ref: "", currency: "", txn_type: "", date_from: "", date_to: "", page: 1 })}
          data-testid="ledger-reset"><RotateCcw className="w-3.5 h-3.5" /> تصفير</Button>
        <Button size="sm" className="bg-[#0A2540] hover:bg-[#061A2E]" onClick={exportCsv} data-testid="ledger-export">
          <Download className="w-4 h-4" /> تصدير Excel/CSV
        </Button>
        <Button size="sm" variant="outline" data-testid="recon-btn"
          onClick={async () => { const r = await api.get("/admin/reconciliation"); setRecon(r.data); }}>
          <Scale className="w-4 h-4" /> المطابقة المالية
        </Button>
        <Button size="sm" variant="outline" data-testid="recon-preview-btn"
          onClick={async () => {
            try {
              const r = await api.get("/admin/reconciliation/preview");
              setPrev(r.data);
            } catch (e) { toast.error(apiError(e)); }
          }}>
          <Scale className="w-4 h-4" /> معاينة قيود التسوية (Dry-run)
        </Button>
        <span className="text-[11px] text-muted-foreground mr-auto" data-testid="ledger-count">
          {d.total} حركة
        </span>
      </div>

      {err && (
        <div className="bg-[#FEF2F2] border border-[#FECACA] text-[#B91C1C] rounded-xl px-4 py-3 text-xs mb-5"
          data-testid="ledger-error">
          تعذّر تحميل الدفتر: {err}
        </div>
      )}

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
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <button data-testid={`voucher-${t.id}`} className="text-[#0A2540] underline inline-flex items-center gap-1"
                        onClick={async () => { const r = await api.get(`/admin/vouchers/${t.id}`); setVoucher(r.data); setVoucherId(t.id); }}>
                        <FileText className="w-3 h-3" /> سند
                      </button>
                      {t.ref && (
                        <button data-testid={`statement-${t.id}`} className="mr-2 text-[#0A2540] underline"
                          onClick={async () => {
                            try {
                              const r = await api.get(`/admin/bookings/${t.ref}/financials`);
                              setStmt(r.data);
                            } catch (e) { toast.error(apiError(e)); }
                          }}>البيان المالي</button>
                      )}
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

      {/* Reconciliation dry-run preview: account by account, before/after, no writes */}
      <Dialog open={!!prev} onOpenChange={(o) => !o && setPrev(null)}>
        <DialogContent dir="rtl" className="max-w-4xl max-h-[85vh] overflow-y-auto" data-testid="recon-preview-dialog">
          <DialogHeader><DialogTitle>معاينة قيود التسوية — حساب بحساب (بدون أي تنفيذ)</DialogTitle></DialogHeader>
          {prev && (
            <div className="space-y-3">
              <div className="text-xs bg-[#FEFCE8] border border-[#FEF08A] text-[#A16207] rounded-lg px-3 py-2" data-testid="recon-preview-note">
                {prev.note}
              </div>
              <div className="grid sm:grid-cols-4 gap-3 text-xs">
                <Box label="حسابات غير مطابقة" v={prev.count} />
                <Box label="إجمالي القيود المقترحة SAR" v={money(prev.totals.SAR, "SAR")} />
                <Box label="إجمالي القيود المقترحة USD" v={money(prev.totals.USD, "USD")} />
                <Box label="تعديلات على الأرصدة" v={prev.wallet_writes} accent />
              </div>
              <div className="text-[11px] text-muted-foreground" data-testid="recon-idempotency">
                الحماية من التكرار: {prev.idempotency} • التنفيذ الفعلي: {prev.execution_enabled ? "مُفعّل" : "معطّل حتى اعتمادكم"}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-[11px] min-w-[900px]">
                  <thead className="bg-[#F4F6F8] text-muted-foreground">
                    <tr>{["الحساب", "البريد", "العملة", "محفظة (قبل)", "دفتر (قبل)", "الفرق",
                      "محفظة (بعد)", "دفتر (بعد)", "القيد", "الحالة"].map((h) => (
                        <th key={h} className="text-right font-semibold px-2 py-2">{h}</th>))}</tr>
                  </thead>
                  <tbody>
                    {prev.items.map((r, i) => (
                      <tr key={i} className="border-t" data-testid={`recon-preview-row-${i}`}>
                        <td className="px-2 py-1.5 font-semibold text-[#0A2540]">{r.name}</td>
                        <td className="px-2 py-1.5 text-[10px]">{r.account_email}</td>
                        <td className="px-2 py-1.5">{r.currency}</td>
                        <td className="px-2 py-1.5 tabular">{r.before.wallet_total}</td>
                        <td className="px-2 py-1.5 tabular">{r.before.ledger_total}</td>
                        <td className="px-2 py-1.5 tabular font-bold text-[#B91C1C]">{r.difference}</td>
                        <td className="px-2 py-1.5 tabular">{r.after.wallet_total} <span className="text-[9px] text-[#15803D]">(بلا تغيير)</span></td>
                        <td className="px-2 py-1.5 tabular">{r.after.ledger_total}</td>
                        <td className="px-2 py-1.5 text-[10px]">{r.description}</td>
                        <td className="px-2 py-1.5">{r.already_adjusted ? "مُسوّى مسبقاً" : "بانتظار الاعتماد"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Per-order financial statement (read-only) */}
      <Dialog open={!!stmt} onOpenChange={(o) => !o && setStmt(null)}>
        <DialogContent dir="rtl" className="max-w-3xl max-h-[85vh] overflow-y-auto" data-testid="statement-dialog">
          <DialogHeader><DialogTitle>البيان المالي للطلب — {stmt?.package_title}</DialogTitle></DialogHeader>
          {stmt && (
            <div className="space-y-3">
              <div className="text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-2" data-testid="stmt-parties">
                المشتري: <b>{stmt.parties?.buyer?.name || "—"}</b> • البائع: <b>{stmt.parties?.seller?.name || "—"}</b> •
                العملة: <b>{stmt.financials.currency}</b> • الحالة: <b>{stmt.financials.status}</b> •
                التسوية: <b>{stmt.financials.settled ? "تمّت" : "لم تتم"}</b>
              </div>
              <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-2" data-testid="stmt-grid">
                <SM label="المدفوع" v={money(stmt.financials.paid, stmt.financials.currency)} tone="in" tid="stmt-paid" />
                <SM label="المعلّق (ضمان)" v={money(stmt.financials.pending, stmt.financials.currency)} tone="hold" tid="stmt-pending" />
                <SM label="المحرر" v={money(stmt.financials.released, stmt.financials.currency)} tone="in" tid="stmt-released" />
                <SM label="المسترد" v={money(stmt.financials.refunded, stmt.financials.currency)} tone="out" tid="stmt-refunded" />
                <SM label="المستحق على المشتري" v={money(stmt.financials.due_from_buyer, stmt.financials.currency)} tone="out" tid="stmt-due-buyer" />
                <SM label="المستحق للبائع" v={money(stmt.financials.due_to_seller, stmt.financials.currency)} tone="hold" tid="stmt-due-seller" />
                <SM label="عمولة المنصة" v={money(stmt.financials.platform_commission, stmt.financials.currency)} tid="stmt-commission" />
                <SM label="صافي المنصة" v={money(stmt.financials.platform_net, stmt.financials.currency)} tone="in" tid="stmt-net" />
                <SM label="المبلغ المحوّل" v={money(stmt.financials.transferred, stmt.financials.currency)} tone="in" tid="stmt-transferred" />
                <SM label="المتبقي" v={money(stmt.financials.remaining, stmt.financials.currency)} tone="hold" tid="stmt-remaining" />
              </div>
              <div className="text-[10px] text-muted-foreground">{stmt.financials.note}</div>
              {stmt.reconciliation && (
                <div className="border-t pt-3" data-testid="stmt-reconciliation">
                  <div className="text-xs font-semibold text-[#0A2540] mb-2">
                    مطابقة البيان المالي مع الدفتر (عرض وتدقيق فقط)
                  </div>
                  <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2 mb-2">
                    <SM label="صافي المشتري" v={money(stmt.reconciliation.buyer_net, stmt.reconciliation.currency)} tid="rec-buyer-net" />
                    <SM label="المُحرَّر للبائع" v={money(stmt.reconciliation.seller_released, stmt.reconciliation.currency)} tid="rec-released" />
                    <SM label={`عمولة المنصة — ${stmt.reconciliation.commission_source === "snapshot" ? "المصدر المعتمد" : stmt.reconciliation.commission_source === "movement" ? "حركة مسجّلة" : "مشتقّة من الفرق"}`}
                      v={money(stmt.reconciliation.platform_retained, stmt.reconciliation.currency)} tid="rec-commission" />
                    <SM label="فرق غير مفسَّر" v={money(stmt.reconciliation.unexplained_difference || 0, stmt.reconciliation.currency)} tid="rec-unexplained" />
                  </div>
                  <div className={`text-[11px] rounded-lg px-3 py-2 mb-2 ${stmt.reconciliation.balanced
                    ? "bg-[#F0FDF4] text-[#15803D] border border-[#BBF7D0]"
                    : "bg-[#FEFCE8] text-[#A16207] border border-[#FEF08A]"}`} data-testid="rec-identity">
                    {stmt.reconciliation.identity} — {stmt.reconciliation.balanced ? "مطابقة سليمة" : "تحتاج مراجعة"}
                  </div>
                  <ul className="text-[10px] text-muted-foreground space-y-1 list-disc pr-4" data-testid="rec-explanation">
                    {stmt.reconciliation.explanation.map((line, i) => <li key={i}>{line}</li>)}
                  </ul>
                  <div className="text-[10px] text-muted-foreground mt-1">{stmt.reconciliation.note}</div>
                </div>
              )}
              <div className="border-t pt-3">
                <div className="text-xs font-semibold text-[#0A2540] mb-2">سجل الحركات المالية الكامل ({stmt.movements.length})</div>
                <div className="space-y-1.5" data-testid="stmt-movements">
                  {stmt.movements.map((m) => (
                    <div key={m.id} className="flex flex-wrap items-center gap-2 text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-1.5"
                      data-testid={`stmt-movement-${m.id}`}>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-white border">
                        {m.party === "buyer" ? "المشتري" : m.party === "seller" ? "البائع" : "أخرى"}
                      </span>
                      <span className="font-semibold text-[#0A2540]">{m.type}</span>
                      <span className="text-muted-foreground flex-1 min-w-[120px]">{m.description}</span>
                      <span className="text-[10px] text-muted-foreground">{fmtDate(m.created_at)}</span>
                      <span className={`tabular font-bold ${Number(m.amount) < 0 ? "text-[#B91C1C]" : "text-[#15803D]"}`}>
                        {money(m.amount, m.currency)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
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

const SM = ({ label, v, tone, tid }) => {
  const cls = tone === "in" ? "bg-[#F0FDF4] border-[#BBF7D0] text-[#15803D]"
    : tone === "out" ? "bg-[#FEF2F2] border-[#FECACA] text-[#B91C1C]"
      : tone === "hold" ? "bg-[#FEFCE8] border-[#FEF08A] text-[#A16207]"
        : "bg-[#F4F6F8] border-[#E5E7EB] text-[#0A2540]";
  return (
    <div className={`rounded-xl border px-3 py-2 ${cls}`} data-testid={tid}>
      <div className="text-[10px] opacity-80">{label}</div>
      <div className="tabular text-sm font-bold">{v}</div>
    </div>
  );
};

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
