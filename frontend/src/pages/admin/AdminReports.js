import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { FileSpreadsheet, Download, Printer, Search } from "lucide-react";

export default function AdminReports() {
  const [cat, setCat] = useState({ reports: {}, saved: [] });
  const [sel, setSel] = useState("sales");
  const [flt, setFlt] = useState({ date_from: "", date_to: "", currency: "" });
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => { api.get("/admin/reports").then((r) => setCat(r.data)); }, []);
  useEffect(() => { load(); }, [load]);

  const body = () => ({ report: sel, ...Object.fromEntries(Object.entries(flt).filter(([, v]) => v)) });

  const run = async () => {
    setBusy(true);
    try { const r = await api.post("/admin/reports/run", body()); setRes(r.data); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const exportCsv = async () => {
    try {
      const r = await api.post("/admin/reports/export", body(), { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([r.data], { type: "text/csv;charset=utf-8" }));
      const a = document.createElement("a");
      a.href = url; a.download = `meraaj-${sel}.csv`; a.click(); URL.revokeObjectURL(url);
      toast.success("تم التصدير");
    } catch (e) { toast.error(apiError(e)); }
  };

  return (
    <>
      <PageHeader title="مركز التقارير" subtitle="١٣ تقريراً بفلاتر وحفظ وطباعة وتصدير إلى Excel — والطباعة تنتج PDF عربي صحيح الاتجاه" />

      <div className="bg-white rounded-2xl border card-shadow p-4 mb-5" data-testid="reports-panel">
        <div className="flex flex-wrap gap-2 mb-4">
          {Object.entries(cat.reports).map(([k, l]) => (
            <button key={k} onClick={() => { setSel(k); setRes(null); }} data-testid={`report-${k}`}
              className={`px-3 h-8 rounded-lg text-[11px] font-semibold border transition-colors ${sel === k ? "bg-[#0A2540] text-white border-[#0A2540]" : "bg-white text-[#0A2540] hover:bg-[#F4F6F8]"}`}>
              {l}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-3 items-end">
          <div><Label className="text-[11px]">من تاريخ</Label>
            <Input type="date" className="h-9 text-xs" value={flt.date_from} data-testid="report-from"
              onChange={(e) => setFlt({ ...flt, date_from: e.target.value })} /></div>
          <div><Label className="text-[11px]">إلى تاريخ</Label>
            <Input type="date" className="h-9 text-xs" value={flt.date_to} data-testid="report-to"
              onChange={(e) => setFlt({ ...flt, date_to: e.target.value })} /></div>
          <div><Label className="text-[11px]">العملة</Label>
            <select value={flt.currency} onChange={(e) => setFlt({ ...flt, currency: e.target.value })}
              data-testid="report-currency" className="h-9 rounded-md border border-input px-2 text-xs bg-white">
              <option value="">الكل</option><option value="SAR">ريال</option><option value="USD">دولار</option>
            </select></div>
          <Button size="sm" className="bg-[#0A2540] hover:bg-[#061A2E]" onClick={run} disabled={busy} data-testid="run-report-btn">
            <Search className="w-4 h-4" /> تشغيل التقرير
          </Button>
          <Button size="sm" variant="outline" onClick={exportCsv} disabled={!res} data-testid="export-report-btn">
            <Download className="w-4 h-4" /> تصدير Excel
          </Button>
          <Button size="sm" variant="outline" onClick={() => window.print()} disabled={!res} data-testid="print-report-btn">
            <Printer className="w-4 h-4" /> طباعة / PDF
          </Button>
          <Button size="sm" variant="outline" disabled={!res} data-testid="save-report-btn"
            onClick={async () => {
              const name = window.prompt("اسم التقرير المحفوظ؟");
              if (!name) return;
              await api.post("/admin/reports/save", { name, report: sel, filters: flt });
              toast.success("تم حفظ التقرير"); load();
            }}>حفظ الفلاتر</Button>
        </div>
        {cat.saved.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3" data-testid="saved-reports">
            {cat.saved.map((s) => (
              <button key={s.id} data-testid={`saved-${s.id}`}
                onClick={() => { setSel(s.report); setFlt({ date_from: "", date_to: "", currency: "", ...s.filters }); }}
                className="text-[10px] px-2 py-1 rounded-full bg-[#F4F6F8] border text-[#0A2540]">{s.name}</button>
            ))}
          </div>
        )}
      </div>

      {res && (
        <div className="bg-white rounded-2xl border card-shadow overflow-x-auto" data-testid="report-result">
          <div className="p-4 border-b flex items-center justify-between">
            <div className="flex items-center gap-2 font-head font-bold text-[#0A2540] text-sm">
              <FileSpreadsheet className="w-4 h-4 text-[#D4AF37]" /> {res.title}
            </div>
            <span className="text-[11px] text-muted-foreground" data-testid="report-count">
              {res.row_count} سجل {res.row_count > 500 ? "(معروض 500 — التصدير يشمل الكل)" : ""} • {fmtDate(res.generated_at)}
            </span>
          </div>
          <table className="w-full text-xs">
            <thead className="bg-[#F4F6F8] text-muted-foreground">
              <tr>{res.columns.map((c) => <th key={c} className="text-right font-semibold px-3 py-2 whitespace-nowrap">{c}</th>)}</tr>
            </thead>
            <tbody>
              {res.rows.length === 0 ? (
                <tr><td colSpan={res.columns.length} className="text-center py-10 text-muted-foreground" data-testid="report-empty">لا توجد بيانات</td></tr>
              ) : res.rows.map((r, i) => (
                <tr key={i} className="border-t hover:bg-[#FAFBFC]" data-testid={`report-row-${i}`}>
                  {r.map((c, j) => <td key={j} className="px-3 py-2 whitespace-nowrap">{String(c ?? "—").slice(0, 60)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
