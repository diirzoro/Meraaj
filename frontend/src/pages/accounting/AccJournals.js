import { useState } from "react";
import api, { apiError } from "@/lib/api";
import { toast } from "sonner";
import { PageHeader } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Plus, RotateCcw, Trash2 } from "lucide-react";
import { Panel, Field, inputCls, Loading, ErrorNote, Empty, useFetch, Gate, Badge, Money, STATUS_AR, statusTone } from "./ui";

const emptyLine = () => ({ account_code: "", debit: "", credit: "", memo: "" });

export default function AccJournals() {
  const [source, setSource] = useState("");
  const list = useFetch(`/accounting/journal/entries?limit=100${source ? `&source_type=${source}` : ""}`, [source]);
  const accounts = useFetch("/accounting/accounts?include_inactive=false");
  const [detailId, setDetailId] = useState(null);
  const detail = useFetch(detailId ? `/accounting/journal/entries/${detailId}` : null, [detailId]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState({ date: new Date().toISOString().slice(0, 10), currency: "SAR", description: "", lines: [emptyLine(), emptyLine()] });
  const [validation, setValidation] = useState(null);

  const leaves = (accounts.data?.items || []).filter((a) => !a.is_group);
  const payload = () => ({
    date: new Date(draft.date).toISOString(), currency: draft.currency,
    source_type: "manual", description: draft.description,
    lines: draft.lines.filter((l) => l.account_code).map((l) => ({
      account_code: l.account_code, debit: l.debit || "0", credit: l.credit || "0",
      currency: draft.currency, memo: l.memo || "",
    })),
  });

  const totals = draft.lines.reduce((a, l) => ({
    debit: a.debit + Number(l.debit || 0), credit: a.credit + Number(l.credit || 0),
  }), { debit: 0, credit: 0 });

  const validate = async () => {
    setBusy(true); setValidation(null);
    try { const r = await api.post("/accounting/journal/validate", payload()); setValidation(r.data); toast.success("القيد صالح للترحيل"); }
    catch (e) { setValidation({ error: apiError(e) }); toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const post = async () => {
    setBusy(true);
    try {
      const r = await api.post("/accounting/journal/post", payload());
      toast.success(`تم الترحيل — قيد ${r.data.entry_no}`);
      setOpen(false); setValidation(null);
      setDraft({ date: new Date().toISOString().slice(0, 10), currency: "SAR", description: "", lines: [emptyLine(), emptyLine()] });
      list.reload();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const reverse = async (id) => {
    const reason = window.prompt("سبب العكس:");
    if (!reason || reason.trim().length < 3) return;
    setBusy(true);
    try { const r = await api.post(`/accounting/journal/entries/${id}/reverse?reason=${encodeURIComponent(reason)}`); toast.success(`قيد عكسي: ${r.data.reversal?.entry_no || ""}`); list.reload(); setDetailId(null); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title="القيود اليومية" subtitle="القيد المُرحَّل غير قابل للتعديل أو الحذف — التصحيح بقيد عكسي"
        action={<Gate perm="accounting.journals.create">
          <Button onClick={() => setOpen(true)} data-testid="journal-new-btn" className="bg-[#0A2540]">
            <Plus className="w-4 h-4 me-1" /> قيد يدوي
          </Button></Gate>} />

      <ErrorNote>{list.error}</ErrorNote>

      <Panel testid="journal-list" action={
        <input className={`${inputCls} sm:w-64`} placeholder="تصفية بمصدر القيد (source_type)" data-testid="journal-source-filter"
               value={source} onChange={(e) => setSource(e.target.value.trim())} />}>
        {list.loading ? <Loading /> : (list.data?.items || []).length === 0 ? <Empty>لا توجد قيود</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-xs text-muted-foreground">
                <th className="py-2 text-start">رقم القيد</th><th className="text-start">التاريخ</th>
                <th className="text-start">البيان</th><th className="text-start">مدين</th>
                <th className="text-start">دائن</th><th className="text-start">المصدر</th>
                <th className="text-start">الحالة</th><th /></tr></thead>
              <tbody>
                {list.data.items.map((j) => (
                  <tr key={j.id} className="border-t" data-testid={`journal-row-${j.entry_no}`}>
                    <td className="py-2 font-mono text-[11px]">{j.entry_no}</td>
                    <td className="text-xs whitespace-nowrap">{String(j.date).slice(0, 10)}</td>
                    <td className="text-xs max-w-[18rem] truncate">{j.description}</td>
                    <td><Money value={j.total_debit} /></td>
                    <td><Money value={j.total_credit} /></td>
                    <td className="text-[11px]">{j.source_type}</td>
                    <td><Badge tone={statusTone(j.status)}>{STATUS_AR[j.status] || j.status}</Badge></td>
                    <td className="text-end"><Button size="sm" variant="outline" data-testid={`journal-open-${j.entry_no}`} onClick={() => setDetailId(j.id)}>تفاصيل</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl" data-testid="journal-create-dialog">
          <DialogHeader><DialogTitle>قيد يومية يدوي</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="grid sm:grid-cols-3 gap-3">
              <Field label="التاريخ"><input type="date" className={inputCls} value={draft.date} data-testid="journal-date"
                onChange={(e) => setDraft({ ...draft, date: e.target.value })} /></Field>
              <Field label="العملة">
                <select className={inputCls} value={draft.currency} data-testid="journal-currency"
                        onChange={(e) => setDraft({ ...draft, currency: e.target.value })}>
                  <option value="SAR">SAR</option><option value="USD">USD</option>
                </select></Field>
              <Field label="البيان"><input className={inputCls} value={draft.description} data-testid="journal-description"
                onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></Field>
            </div>

            <div className="space-y-2">
              {draft.lines.map((l, i) => (
                <div key={i} className="grid grid-cols-12 gap-2 items-end" data-testid={`journal-line-${i}`}>
                  <div className="col-span-5">
                    <select className={inputCls} value={l.account_code} data-testid={`journal-line-account-${i}`}
                            onChange={(e) => { const ls = [...draft.lines]; ls[i] = { ...l, account_code: e.target.value }; setDraft({ ...draft, lines: ls }); }}>
                      <option value="">— الحساب —</option>
                      {leaves.map((a) => <option key={a.code} value={a.code}>{a.code} — {a.name_ar || a.name}</option>)}
                    </select>
                  </div>
                  <div className="col-span-3">
                    <input className={inputCls} placeholder="مدين" inputMode="decimal" value={l.debit} data-testid={`journal-line-debit-${i}`}
                           onChange={(e) => { const ls = [...draft.lines]; ls[i] = { ...l, debit: e.target.value, credit: "" }; setDraft({ ...draft, lines: ls }); }} />
                  </div>
                  <div className="col-span-3">
                    <input className={inputCls} placeholder="دائن" inputMode="decimal" value={l.credit} data-testid={`journal-line-credit-${i}`}
                           onChange={(e) => { const ls = [...draft.lines]; ls[i] = { ...l, credit: e.target.value, debit: "" }; setDraft({ ...draft, lines: ls }); }} />
                  </div>
                  <button className="col-span-1 text-red-600" data-testid={`journal-line-remove-${i}`}
                          onClick={() => setDraft({ ...draft, lines: draft.lines.filter((_, x) => x !== i) })}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
              <Button size="sm" variant="outline" data-testid="journal-add-line"
                      onClick={() => setDraft({ ...draft, lines: [...draft.lines, emptyLine()] })}>+ سطر</Button>
            </div>

            <div className="flex items-center gap-4 text-sm border-t pt-3" data-testid="journal-totals">
              <span>إجمالي مدين: <b><Money value={totals.debit} /></b></span>
              <span>إجمالي دائن: <b><Money value={totals.credit} /></b></span>
              <Badge tone={Math.abs(totals.debit - totals.credit) < 0.005 && totals.debit > 0 ? "green" : "amber"}>
                {Math.abs(totals.debit - totals.credit) < 0.005 && totals.debit > 0 ? "متوازن" : "غير متوازن"}
              </Badge>
            </div>
            {validation?.error && <ErrorNote testid="journal-validation-error">{validation.error}</ErrorNote>}

            <div className="flex gap-2">
              <Button variant="outline" disabled={busy} onClick={validate} data-testid="journal-validate">تحقق (مسودة)</Button>
              <Gate perm="accounting.journals.post">
                <Button disabled={busy} onClick={post} data-testid="journal-post" className="bg-[#0A2540]">ترحيل</Button>
              </Gate>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!detailId} onOpenChange={(v) => !v && setDetailId(null)}>
        <DialogContent className="max-w-3xl" data-testid="journal-detail-dialog">
          <DialogHeader><DialogTitle>قيد {detail.data?.entry_no}</DialogTitle></DialogHeader>
          {detail.loading ? <Loading /> : detail.data && (
            <div className="space-y-3 text-sm">
              <div className="grid sm:grid-cols-3 gap-2 text-xs">
                <div>التاريخ: <b>{String(detail.data.date).slice(0, 10)}</b></div>
                <div>الحالة: <b>{STATUS_AR[detail.data.status] || detail.data.status}</b></div>
                <div>العملة: <b>{detail.data.currency}</b></div>
                <div>المصدر: <b>{detail.data.source_type}</b></div>
                <div>مرجع المصدر: <b className="font-mono text-[10px]">{detail.data.source_id || "—"}</b></div>
                <div>مفتاح المصدر: <b className="font-mono text-[10px]">{detail.data.source_key || "—"}</b></div>
                <div>منفّذ العمل (تجاري): <b>{detail.data.metadata?.business_actor?.name || detail.data.metadata?.actor?.business_actor || "—"}</b></div>
                <div>المنفّذ المحاسبي: <b>{detail.data.metadata?.accounting_actor?.name || detail.data.metadata?.actor?.accounting_actor || detail.data.created_by || "—"}</b></div>
                <div>رحّله: <b>{detail.data.posted_by || detail.data.created_by || "—"}</b></div>
                <div>عكسه: <b>{detail.data.reversed_by || "—"}</b></div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-xs text-muted-foreground"><th className="text-start py-1">الحساب</th><th className="text-start">بيان السطر</th><th className="text-start">مدين</th><th className="text-start">دائن</th></tr></thead>
                  <tbody>
                    {(detail.data.lines || []).map((l, i) => (
                      <tr key={i} className="border-t" data-testid={`journal-detail-line-${i}`}>
                        <td className="py-1 font-mono text-[11px]">{l.account_code}</td>
                        <td className="text-xs">{l.memo || "—"}</td>
                        <td><Money value={l.debit} /></td>
                        <td><Money value={l.credit} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {String(detail.data.status).toLowerCase() === "posted" && (
                <Gate perm="accounting.journals.reverse">
                  <Button size="sm" variant="destructive" disabled={busy} data-testid="journal-reverse"
                          onClick={() => reverse(detail.data.id)}><RotateCcw className="w-4 h-4 me-1" /> عكس القيد</Button>
                </Gate>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
