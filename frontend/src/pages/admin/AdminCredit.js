import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Search, Snowflake, ShieldCheck, History } from "lucide-react";

const ALERT_CLASS = {
  ok: "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]",
  warning: "bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]",
  high: "bg-[#FFF7ED] text-[#C2410C] border-[#FED7AA]",
  critical: "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]",
};
const ALERT_LABEL = { ok: "سليم", warning: "≥70%", high: "≥90%", critical: "بلغ الحد" };

export default function AdminCredit() {
  const [d, setD] = useState({ items: [], totals: { SAR: {}, USD: {} }, total: 0 });
  const [q, setQ] = useState("");
  const [onlyExposed, setOnlyExposed] = useState(true);
  const [page, setPage] = useState(1);
  const [edit, setEdit] = useState(null);   // {office_id,name,currency,limit,reason}
  const [frz, setFrz] = useState(null);     // {office_id,name,currency,frozen,reason}
  const [events, setEvents] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    const p = new URLSearchParams({ page: String(page), limit: "50" });
    if (q) p.set("q", q);
    if (onlyExposed && !q) p.set("only_exposed", "true");
    api.get(`/admin/credit?${p}`).then((r) => setD(r.data));
  }, [q, onlyExposed, page]);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      await api.post(`/admin/credit/${edit.office_id}`, {
        currency: edit.currency, limit: Number(edit.limit), reason: edit.reason,
      });
      toast.success("تم تحديث السقف الائتماني"); setEdit(null); load();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const freeze = async () => {
    setBusy(true);
    try {
      await api.post(`/admin/credit/${frz.office_id}/freeze`,
        { currency: frz.currency, frozen: frz.frozen, reason: frz.reason });
      toast.success(frz.frozen ? "تم تجميد الحساب" : "تم إلغاء التجميد");
      setFrz(null); load();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title="السقف الائتماني والانكشاف" subtitle="حد رقابي لكل مكتب — يسمح بالسالب داخل الحد فقط، ويرفض أي حجز يتجاوز المتاح" />

      <div className="grid sm:grid-cols-2 gap-5 mb-5">
        {["SAR", "USD"].map((c) => (
          <div key={c} className="bg-white rounded-2xl border card-shadow p-5" data-testid={`credit-total-${c}`}>
            <div className="text-sm font-semibold text-muted-foreground mb-3">
              {c === "SAR" ? "إجمالي — ريال سعودي" : "إجمالي — دولار أمريكي"}
            </div>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <Box label="سقوف ممنوحة" v={money(d.totals[c]?.limit || 0, c)} />
              <Box label="مستخدم (مديونية)" v={money(d.totals[c]?.used || 0, c)} danger />
              <Box label="متاح" v={money(d.totals[c]?.headroom || 0, c)} accent />
            </div>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-4 mb-5 flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="w-4 h-4 absolute top-2.5 right-3 text-muted-foreground" />
          <input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} data-testid="credit-search"
            placeholder="ابحث باسم المكتب أو البريد (البحث يتجاوز فلتر الانكشاف)"
            className="w-full h-9 rounded-md border border-input pr-9 pl-3 text-xs" />
        </div>
        <label className="text-xs inline-flex items-center gap-2" data-testid="credit-only-exposed">
          <input type="checkbox" checked={onlyExposed} disabled={!!q}
            onChange={(e) => { setOnlyExposed(e.target.checked); setPage(1); }} />
          إظهار من له سقف أو مديونية فقط
        </label>
        <Button size="sm" variant="outline" data-testid="credit-events-btn"
          onClick={async () => { const r = await api.get("/admin/credit-events"); setEvents(r.data); }}>
          <History className="w-4 h-4" /> سجل التعديلات
        </Button>
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto" data-testid="credit-table">
        <table className="w-full text-xs min-w-[820px]">
          <thead className="bg-[#F4F6F8] text-muted-foreground">
            <tr>{["المكتب", "العملة", "السقف", "الرصيد", "المستخدم", "المتاح", "الاستخدام", ""].map((h) => (
              <th key={h} className="text-right font-semibold px-3 py-2.5">{h}</th>))}</tr>
          </thead>
          <tbody>
            {d.items.length === 0 ? (
              <tr><td colSpan={8} className="text-center py-12 text-muted-foreground" data-testid="credit-empty">لا توجد نتائج</td></tr>
            ) : d.items.flatMap((row) => ["SAR", "USD"].filter((c) => row.currencies[c]).map((c) => {
              const cc = row.currencies[c];
              return (
                <tr key={row.office_id + c} className="border-t hover:bg-[#FAFBFC]" data-testid={`credit-row-${row.office_id}-${c}`}>
                  <td className="px-3 py-2.5 font-semibold text-[#0A2540]">{row.name}
                    {cc.frozen && <span className="mr-1.5 text-[10px] px-1.5 py-0.5 rounded bg-[#EFF6FF] text-[#1D4ED8]">مجمّد</span>}
                  </td>
                  <td className="px-3 py-2.5">{c === "SAR" ? "ريال" : "دولار"}</td>
                  <td className="px-3 py-2.5 tabular">{money(cc.limit, c)}</td>
                  <td className={`px-3 py-2.5 tabular ${cc.balance < 0 ? "text-[#B91C1C] font-bold" : ""}`}>{money(cc.balance, c)}</td>
                  <td className="px-3 py-2.5 tabular">{money(cc.used, c)}</td>
                  <td className="px-3 py-2.5 tabular">{money(cc.headroom, c)}</td>
                  <td className="px-3 py-2.5">
                    <span className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold ${ALERT_CLASS[cc.alert]}`}>
                      {cc.utilization}% • {ALERT_LABEL[cc.alert]}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    <button data-testid={`set-limit-${row.office_id}-${c}`}
                      onClick={() => setEdit({ office_id: row.office_id, name: row.name, currency: c, limit: cc.limit, reason: "" })}
                      className="text-[#0A2540] underline font-semibold">تعديل السقف</button>
                    <button data-testid={`freeze-${row.office_id}-${c}`}
                      onClick={() => setFrz({ office_id: row.office_id, name: row.name, currency: c, frozen: !cc.frozen, reason: "" })}
                      className="mr-2 text-[#1D4ED8] underline inline-flex items-center gap-1">
                      {cc.frozen ? <ShieldCheck className="w-3 h-3" /> : <Snowflake className="w-3 h-3" />}
                      {cc.frozen ? "إلغاء التجميد" : "تجميد"}
                    </button>
                  </td>
                </tr>
              );
            }))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-center gap-3 mt-5" data-testid="credit-pagination">
        <button disabled={page <= 1} onClick={() => setPage(page - 1)} data-testid="credit-prev"
          className="h-8 px-3 rounded-md border text-xs disabled:opacity-40">السابق</button>
        <span className="text-xs tabular">صفحة {page} من {Math.max(1, Math.ceil((d.total || 0) / 50))} • {d.items.length} معروض من {d.total || 0}</span>
        <button disabled={page >= Math.ceil((d.total || 0) / 50)} onClick={() => setPage(page + 1)} data-testid="credit-next"
          className="h-8 px-3 rounded-md border text-xs disabled:opacity-40">التالي</button>
      </div>

      <Dialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)}>
        <DialogContent dir="rtl" className="max-w-md" data-testid="limit-dialog">
          <DialogHeader><DialogTitle>السقف الائتماني — {edit?.name}</DialogTitle></DialogHeader>
          {edit && (
            <div className="space-y-3">
              <div className="text-xs text-muted-foreground">العملة: {edit.currency === "SAR" ? "ريال سعودي" : "دولار أمريكي"}</div>
              <div><Label className="text-xs">السقف</Label>
                <Input type="number" value={edit.limit} data-testid="limit-input"
                  onChange={(e) => setEdit({ ...edit, limit: e.target.value })} /></div>
              <div><Label className="text-xs">السبب (إلزامي — يُسجَّل في سجل التدقيق)</Label>
                <Textarea rows={2} value={edit.reason} data-testid="limit-reason"
                  onChange={(e) => setEdit({ ...edit, reason: e.target.value })} /></div>
              <Button className="w-full bg-[#0A2540] hover:bg-[#061A2E]" data-testid="save-limit-btn"
                disabled={busy || edit.reason.trim().length < 3} onClick={save}>حفظ</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!frz} onOpenChange={(o) => !o && setFrz(null)}>
        <DialogContent dir="rtl" className="max-w-md" data-testid="freeze-dialog">
          <DialogHeader><DialogTitle>{frz?.frozen ? "تجميد الحساب ائتمانياً" : "إلغاء التجميد"} — {frz?.name}</DialogTitle></DialogHeader>
          {frz && (
            <div className="space-y-3">
              <div className="text-xs text-muted-foreground">
                العملة: {frz.currency === "SAR" ? "ريال سعودي" : "دولار أمريكي"}
                {frz.frozen && " — التجميد يمنع المكتب من إتمام أي حجز جديد حتى لو كان رصيده كافياً."}
              </div>
              <div><Label className="text-xs">السبب (إلزامي — يُسجَّل في سجل التدقيق)</Label>
                <Textarea rows={2} value={frz.reason} data-testid="freeze-reason"
                  onChange={(e) => setFrz({ ...frz, reason: e.target.value })} /></div>
              <Button className={`w-full ${frz.frozen ? "bg-[#B91C1C] hover:bg-[#991B1B]" : "bg-[#0A2540] hover:bg-[#061A2E]"}`}
                data-testid="confirm-freeze-btn" disabled={busy || frz.reason.trim().length < 3} onClick={freeze}>
                {frz.frozen ? "تجميد" : "إلغاء التجميد"}
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!events} onOpenChange={(o) => !o && setEvents(null)}>
        <DialogContent dir="rtl" className="max-w-lg max-h-[80vh] overflow-y-auto" data-testid="credit-events-dialog">
          <DialogHeader><DialogTitle>سجل تعديلات الحدود الائتمانية</DialogTitle></DialogHeader>
          <div className="space-y-2">
            {(events || []).length === 0 ? <div className="text-xs text-muted-foreground">لا يوجد سجل</div> :
              (events || []).map((e) => (
                <div key={e.id} className="text-xs bg-[#F4F6F8] rounded-lg px-3 py-2">
                  <b>{e.office_name}</b> — {e.action === "limit_changed" ? `السقف ${e.old_limit} ← ${e.new_limit}` : e.action} ({e.currency})
                  <div className="text-[10px] text-muted-foreground mt-0.5">{e.reason} • {e.by} • {fmtDate(e.at)}</div>
                </div>
              ))}
          </div>
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
