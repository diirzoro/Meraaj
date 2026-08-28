import { useEffect, useMemo, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, equiv, fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { Wallet, Clock, CheckCircle2, ArrowDownToLine, ArrowLeftRight, Upload } from "lucide-react";
import { toast } from "sonner";

const badge = { pending: "bg-[#FEFCE8] text-[#A16207]", approved: "bg-[#F0FDF4] text-[#15803D]", rejected: "bg-red-50 text-red-600" };
const stLabel = { pending: "قيد المراجعة", approved: "معتمد", rejected: "مرفوض" };
const EMPTY = { SAR: { available: 0, pending: 0, total: 0 }, USD: { available: 0, pending: 0, total: 0 } };
const availOf = (w, c) => (w?.[c]?.available ?? 0);

export default function WalletPage() {
  const [w, setW] = useState(EMPTY);
  const [txns, setTxns] = useState([]);
  const [topups, setTopups] = useState([]);
  const [transfers, setTransfers] = useState([]);
  const [withdrawals, setWithdrawals] = useState([]);
  const [tab, setTab] = useState("txns");
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    Promise.all([
      api.get("/wallet").then((r) => setW(r.data || EMPTY)),
      api.get("/wallet/transactions").then((r) => setTxns(r.data)),
      api.get("/wallet/topups").then((r) => setTopups(r.data)),
      api.get("/wallet/transfers").then((r) => setTransfers(r.data)),
      api.get("/wallet/withdrawals").then((r) => setWithdrawals(r.data)),
    ]).catch(() => toast.error("تعذّر تحميل بيانات المحفظة")).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  return (
    <>
      <PageHeader title="المحفظة المالية" subtitle="أرصدتك بعملتين منفصلتين (ريال ودولار)، الشحن، التحويلات، والسحوبات"
        action={<div className="flex flex-wrap gap-2">
          <TopupDialog onDone={load} />
          <TransferDialog onDone={load} wallet={w} />
          <WithdrawDialog onDone={load} wallet={w} />
        </div>} />

      <div className="grid md:grid-cols-2 gap-5 mb-8">
        <CurrencyWallet ccy="SAR" title="محفظة الريال السعودي" data={w.SAR} loading={loading} gold />
        <CurrencyWallet ccy="USD" title="محفظة الدولار الأمريكي" data={w.USD} loading={loading} />
      </div>

      <div className="flex gap-1 bg-white border rounded-xl p-1 card-shadow w-fit mb-5">
        {[["txns", "الحركات"], ["topups", "الشحن"], ["transfers", "التحويلات"], ["withdrawals", "السحوبات"]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`wallet-tab-${k}`}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === k ? "bg-[#0A2540] text-white" : "text-muted-foreground hover:text-[#0A2540]"}`}>{l}</button>
        ))}
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto">
        {tab === "txns" && <LedgerTable rows={txns} />}
        {tab === "topups" && <SimpleTable rows={topups} cols={[["amount", "المبلغ", true], ["method", "الطريقة"], ["status", "الحالة", false, false, true], ["created_at", "التاريخ", false, true]]} empty="لا توجد طلبات شحن" />}
        {tab === "transfers" && <SimpleTable rows={transfers} cols={[["to_office_name", "إلى/من"], ["amount", "المبلغ", true], ["status", "الحالة", false, false, true], ["created_at", "التاريخ", false, true]]} empty="لا توجد تحويلات" />}
        {tab === "withdrawals" && <SimpleTable rows={withdrawals} cols={[["amount", "المبلغ", true], ["method", "الطريقة"], ["status", "الحالة", false, false, true], ["created_at", "التاريخ", false, true]]} empty="لا توجد سحوبات" />}
      </div>
    </>
  );
}

function CurrencyWallet({ ccy, title, data, loading, gold }) {
  const d = data || { available: 0, pending: 0, total: 0 };
  return (
    <div data-testid={`wallet-${ccy}`} className={`rounded-2xl border p-6 card-shadow ${gold ? "bg-[#0A2540] text-white border-[#0A2540]" : "bg-white"}`}>
      <div className="flex items-center justify-between mb-5">
        <span className={`text-sm font-semibold ${gold ? "text-white/80" : "text-muted-foreground"}`}>{title}</span>
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${gold ? "bg-[#D4AF37]" : "bg-[#F4F6F8]"}`}><Wallet className="w-4 h-4 text-[#0A2540]" /></div>
      </div>
      <div className={`text-xs mb-1 ${gold ? "text-white/60" : "text-muted-foreground"}`}>الرصيد المتاح</div>
      <div data-testid={`wallet-${ccy}-available`} className={`tabular text-3xl font-bold mb-4 ${gold ? "text-[#D4AF37]" : "text-[#0A2540]"}`}>{loading ? "..." : money(d.available, ccy)}</div>
      <div className={`flex items-center justify-between text-sm pt-3 border-t ${gold ? "border-white/10" : ""}`}>
        <span className={`flex items-center gap-1.5 ${gold ? "text-white/70" : "text-muted-foreground"}`}><Clock className="w-3.5 h-3.5" /> المعلّق (ضمان)</span>
        <span data-testid={`wallet-${ccy}-pending`} className={`tabular font-semibold ${gold ? "text-white" : "text-[#0A2540]"}`}>{loading ? "..." : money(d.pending, ccy)}</span>
      </div>
    </div>
  );
}

function SimpleTable({ rows, cols, empty }) {
  if (!rows || rows.length === 0) return <div className="p-10 text-center text-muted-foreground text-sm">{empty}</div>;
  return (
    <table className="w-full text-sm min-w-[560px]">
      <thead className="text-muted-foreground text-xs border-b"><tr>{cols.map((c) => <th key={c[0]} className="text-start px-6 py-3 font-medium">{c[1]}</th>)}</tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={r.id || i} className="border-b last:border-0">
            {cols.map((c) => {
              const [key, , isMoney, isDate, isStatus] = c;
              let v = r[key];
              if (isMoney) return <td key={key} className={`px-6 py-3 tabular font-semibold ${v < 0 ? "text-red-600" : "text-[#0A2540]"}`}>{money(v, r.currency)}</td>;
              if (isDate) return <td key={key} className="px-6 py-3 text-muted-foreground text-xs">{fmtDate(v)}</td>;
              if (isStatus) return <td key={key} className="px-6 py-3"><span className={`text-xs px-2 py-1 rounded-md font-semibold ${badge[v]}`}>{stLabel[v] || v}</span></td>;
              return <td key={key} className="px-6 py-3">{v}</td>;
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const r2 = (x) => Math.round((Number(x) || 0) * 100) / 100;

// Account statement (كشف الحساب): Date | Statement | Ref | Debit | Credit | Running balance | Currency.
function LedgerTable({ rows }) {
  const [ccy, setCcy] = useState("all");
  const [q, setQ] = useState("");

  const enriched = useMemo(() => {
    const asc = [...(rows || [])].reverse(); // rows come newest-first → chronological
    const bal = { SAR: 0, USD: 0 };
    const out = asc.map((r) => {
      const c = r.currency === "SAR" ? "SAR" : "USD";
      bal[c] = r2(bal[c] + Number(r.amount || 0));
      return { ...r, running: bal[c] };
    });
    return out.reverse(); // back to newest-first for display
  }, [rows]);

  let view = enriched;
  if (ccy !== "all") view = view.filter((r) => (r.currency === "SAR" ? "SAR" : "USD") === ccy);
  if (q.trim()) view = view.filter((r) => (r.description || "").includes(q.trim()));

  return (
    <div>
      <div className="flex flex-col sm:flex-row gap-3 p-4 border-b bg-[#FAFBFC]">
        <select data-testid="ledger-currency" value={ccy} onChange={(e) => setCcy(e.target.value)}
          className="h-9 rounded-md border border-input bg-white px-3 text-sm sm:w-48">
          <option value="all">كل العملات</option>
          <option value="SAR">ريال سعودي (SAR)</option>
          <option value="USD">دولار أمريكي (USD)</option>
        </select>
        <Input data-testid="ledger-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="بحث في البيان" className="sm:w-64" />
      </div>
      {view.length === 0 ? (
        <div className="p-10 text-center text-muted-foreground text-sm">لا توجد حركات</div>
      ) : (
        <table className="w-full text-sm min-w-[720px]" data-testid="ledger-table">
          <thead className="text-muted-foreground text-xs border-b">
            <tr>
              <th className="text-start px-5 py-3 font-medium">التاريخ</th>
              <th className="text-start px-5 py-3 font-medium">البيان</th>
              <th className="text-start px-5 py-3 font-medium">المرجع</th>
              <th className="text-start px-5 py-3 font-medium">مدين</th>
              <th className="text-start px-5 py-3 font-medium">دائن</th>
              <th className="text-start px-5 py-3 font-medium">الرصيد الجاري</th>
              <th className="text-start px-5 py-3 font-medium">العملة</th>
            </tr>
          </thead>
          <tbody>
            {view.map((r, i) => {
              const amt = Number(r.amount || 0);
              return (
                <tr key={r.id || i} className="border-b last:border-0" data-testid={`ledger-row-${i}`}>
                  <td className="px-5 py-3 text-muted-foreground text-xs whitespace-nowrap">{fmtDate(r.created_at)}</td>
                  <td className="px-5 py-3">{r.description}</td>
                  <td className="px-5 py-3 text-muted-foreground text-xs font-mono">{r.ref ? `#${String(r.ref).slice(-6)}` : "—"}</td>
                  <td className="px-5 py-3 tabular font-semibold text-red-600">{amt < 0 ? money(Math.abs(amt), r.currency) : "—"}</td>
                  <td className="px-5 py-3 tabular font-semibold text-[#15803D]">{amt > 0 ? money(amt, r.currency) : "—"}</td>
                  <td className="px-5 py-3 tabular font-bold text-[#0A2540]">{money(r.running, r.currency)}</td>
                  <td className="px-5 py-3 text-xs font-semibold text-muted-foreground">{r.currency === "SAR" ? "ر.س" : "$"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

function CurrencySelect({ value, onChange, testid }) {
  return (
    <select data-testid={testid} value={value} onChange={(e) => onChange(e.target.value)}
            className="w-full h-9 rounded-md border border-input bg-transparent px-3 text-sm">
      <option value="SAR">ريال سعودي (SAR)</option>
      <option value="USD">دولار أمريكي (USD)</option>
    </select>
  );
}

function TopupDialog({ onDone }) {
  const [open, setOpen] = useState(false);
  const [successOpen, setSuccessOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ amount: "", currency: "SAR", method: "حوالة بنكية", receipt_url: "" });
  const [fileName, setFileName] = useState("");
  const onFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!/(image\/(png|jpe?g|webp)|application\/pdf)/.test(file.type)) { toast.error("الملف يجب أن يكون صورة (JPG/PNG) أو PDF"); return; }
    if (file.size > 20 * 1024 * 1024) { toast.error("حجم الملف يتجاوز 20 ميجابايت"); return; }
    const reader = new FileReader();
    reader.onload = () => { setF((p) => ({ ...p, receipt_url: reader.result })); setFileName(file.name); };
    reader.readAsDataURL(file);
  };
  const submit = async () => {
    if (busy) return; // prevent double submission
    setBusy(true);
    try {
      await api.post("/wallet/topups", { amount: Number(f.amount), currency: f.currency, method: f.method, receipt_url: f.receipt_url });
      setOpen(false);
      setF({ amount: "", currency: "SAR", method: "حوالة بنكية", receipt_url: "" }); setFileName("");
      setSuccessOpen(true);
      onDone();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };
  return (
    <>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild><Button className="bg-[#0A2540] hover:bg-[#061A2E]" data-testid="open-topup-btn"><Upload className="w-4 h-4" /> شحن المحفظة</Button></DialogTrigger>
        <DialogContent dir="rtl">
          <DialogHeader><DialogTitle className="font-head text-[#0A2540]">شحن المحفظة برفع إشعار حوالة</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div><Label className="mb-2 block">العملة (تُضاف كما هي دون تحويل)</Label>
              <CurrencySelect value={f.currency} onChange={(v) => setF({ ...f, currency: v })} testid="topup-currency" />
            </div>
            <div><Label className="mb-2 block">المبلغ</Label>
              <Input data-testid="topup-amount" type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} />
              {f.amount && <p className="text-xs text-muted-foreground mt-1 tabular">{money(f.amount, f.currency)} {equiv(f.amount, f.currency)}</p>}
            </div>
            <div><Label className="mb-2 block">طريقة الدفع</Label>
              <select data-testid="topup-method" value={f.method} onChange={(e) => setF({ ...f, method: e.target.value })} className="w-full h-9 rounded-md border border-input bg-transparent px-3 text-sm">
                <option>حوالة بنكية</option><option>صرافة</option><option>نقداً</option>
              </select>
            </div>
            <div><Label className="mb-2 block">إشعار الحوالة (صورة أو PDF)</Label>
              <input data-testid="topup-receipt-file" type="file" accept="image/png,image/jpeg,image/webp,application/pdf" onChange={onFile}
                     className="w-full text-sm file:me-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-[#0A2540] file:text-white file:cursor-pointer" />
              {fileName && <p className="text-xs text-[#15803D] mt-2">✓ تم اختيار: {fileName}</p>}
            </div>
          </div>
          <DialogFooter>
            <Button className="bg-[#0A2540] hover:bg-[#061A2E]" onClick={submit} disabled={busy || !f.amount || !f.receipt_url} data-testid="submit-topup-btn">
              {busy ? "جارٍ الإرسال..." : "إرسال الطلب"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={successOpen} onOpenChange={setSuccessOpen}>
        <DialogContent dir="rtl" className="max-w-sm" data-testid="topup-success-dialog">
          <DialogHeader><DialogTitle className="sr-only">تم إرسال طلب الشحن</DialogTitle></DialogHeader>
          <div className="flex flex-col items-center text-center py-4">
            <div className="w-16 h-16 rounded-full bg-[#F0FDF4] flex items-center justify-center mb-4">
              <CheckCircle2 className="w-9 h-9 text-[#15803D]" />
            </div>
            <h3 className="font-head text-xl font-bold text-[#0A2540] mb-2">تم إرسال طلب الشحن بنجاح</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">طلبك الآن قيد المراجعة من الإدارة، وسيُضاف الرصيد إلى محفظتك فور اعتماده.</p>
            <Button className="mt-6 w-full h-11 bg-[#0A2540] hover:bg-[#061A2E]" onClick={() => setSuccessOpen(false)} data-testid="topup-success-ok-btn">تمام</Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function TransferDialog({ onDone, wallet }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ to_email: "", amount: "", currency: "SAR", note: "" });
  const avail = availOf(wallet, f.currency);
  const submit = async () => {
    try { await api.post("/wallet/transfers", { to_email: f.to_email, amount: Number(f.amount), currency: f.currency, note: f.note }); toast.success("أُرسل طلب التحويل — بانتظار موافقة الإدارة"); setOpen(false); setF({ to_email: "", amount: "", currency: "SAR", note: "" }); onDone(); }
    catch (e) { toast.error(apiError(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button variant="outline" data-testid="open-transfer-btn"><ArrowLeftRight className="w-4 h-4" /> تحويل P2P</Button></DialogTrigger>
      <DialogContent dir="rtl">
        <DialogHeader><DialogTitle className="font-head text-[#0A2540]">تحويل رصيد لمكتب آخر</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div><Label className="mb-2 block">بريد المستلم (مكتب أو فرد)</Label><Input data-testid="transfer-email" value={f.to_email} onChange={(e) => setF({ ...f, to_email: e.target.value })} /></div>
          <div><Label className="mb-2 block">العملة</Label><CurrencySelect value={f.currency} onChange={(v) => setF({ ...f, currency: v })} testid="transfer-currency" /></div>
          <div><Label className="mb-2 block">المبلغ (المتاح {money(avail, f.currency)})</Label><Input data-testid="transfer-amount" type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></div>
          <div><Label className="mb-2 block">ملاحظة</Label><Textarea data-testid="transfer-note" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} rows={2} /></div>
        </div>
        <DialogFooter><Button className="bg-[#0A2540] hover:bg-[#061A2E]" onClick={submit} disabled={!f.to_email || !f.amount} data-testid="submit-transfer-btn">إرسال طلب التحويل</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function WithdrawDialog({ onDone, wallet }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ amount: "", currency: "SAR", method: "حوالة بنكية", details: "" });
  const avail = availOf(wallet, f.currency);
  const submit = async () => {
    try { await api.post("/wallet/withdrawals", { amount: Number(f.amount), currency: f.currency, method: f.method, details: f.details }); toast.success("أُرسل طلب السحب للإدارة"); setOpen(false); setF({ amount: "", currency: "SAR", method: "حوالة بنكية", details: "" }); onDone(); }
    catch (e) { toast.error(apiError(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button variant="outline" data-testid="open-withdraw-btn"><ArrowDownToLine className="w-4 h-4" /> سحب أرباح</Button></DialogTrigger>
      <DialogContent dir="rtl">
        <DialogHeader><DialogTitle className="font-head text-[#0A2540]">طلب سحب من الرصيد المتاح</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div><Label className="mb-2 block">العملة</Label><CurrencySelect value={f.currency} onChange={(v) => setF({ ...f, currency: v })} testid="withdraw-currency" /></div>
          <div><Label className="mb-2 block">المبلغ (المتاح {money(avail, f.currency)})</Label><Input data-testid="withdraw-amount" type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></div>
          <div><Label className="mb-2 block">طريقة الاستلام</Label>
            <select data-testid="withdraw-method" value={f.method} onChange={(e) => setF({ ...f, method: e.target.value })} className="w-full h-9 rounded-md border border-input bg-transparent px-3 text-sm">
              <option>حوالة بنكية</option><option>صرافة</option>
            </select>
          </div>
          <div><Label className="mb-2 block">تفاصيل الحساب/الصرافة</Label><Textarea data-testid="withdraw-details" value={f.details} onChange={(e) => setF({ ...f, details: e.target.value })} rows={2} /></div>
        </div>
        <DialogFooter><Button className="bg-[#0A2540] hover:bg-[#061A2E]" onClick={submit} disabled={!f.amount || !f.details} data-testid="submit-withdraw-btn">إرسال طلب السحب</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
