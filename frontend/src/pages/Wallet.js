import { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate } from "@/lib/format";
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

export default function WalletPage() {
  const [w, setW] = useState({ total: 0, pending: 0, available: 0 });
  const [txns, setTxns] = useState([]);
  const [topups, setTopups] = useState([]);
  const [transfers, setTransfers] = useState([]);
  const [withdrawals, setWithdrawals] = useState([]);
  const [tab, setTab] = useState("txns");

  const load = () => {
    api.get("/wallet").then((r) => setW(r.data));
    api.get("/wallet/transactions").then((r) => setTxns(r.data));
    api.get("/wallet/topups").then((r) => setTopups(r.data));
    api.get("/wallet/transfers").then((r) => setTransfers(r.data));
    api.get("/wallet/withdrawals").then((r) => setWithdrawals(r.data));
  };
  useEffect(() => { load(); }, []);

  return (
    <>
      <PageHeader title="المحفظة المالية" subtitle="أرصدتك، الشحن، التحويلات، والسحوبات"
        action={<div className="flex flex-wrap gap-2">
          <TopupDialog onDone={load} />
          <TransferDialog onDone={load} available={w.available} />
          <WithdrawDialog onDone={load} available={w.available} />
        </div>} />

      <div className="grid md:grid-cols-3 gap-5 mb-8">
        <Balance id="total" title="الرصيد الإجمالي" value={money(w.total)} icon={Wallet} gold />
        <Balance id="pending" title="الرصيد المعلق (ضمان)" value={money(w.pending)} icon={Clock} />
        <Balance id="available" title="الرصيد المتاح" value={money(w.available)} icon={CheckCircle2} />
      </div>

      <div className="flex gap-1 bg-white border rounded-xl p-1 card-shadow w-fit mb-5">
        {[["txns", "الحركات"], ["topups", "الشحن"], ["transfers", "التحويلات"], ["withdrawals", "السحوبات"]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`wallet-tab-${k}`}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === k ? "bg-[#0A2540] text-white" : "text-muted-foreground hover:text-[#0A2540]"}`}>{l}</button>
        ))}
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto">
        {tab === "txns" && <SimpleTable rows={txns} cols={[["description", "الوصف"], ["amount", "المبلغ", true], ["created_at", "التاريخ", false, true]]} empty="لا توجد حركات" />}
        {tab === "topups" && <SimpleTable rows={topups} cols={[["amount", "المبلغ", true], ["method", "الطريقة"], ["status", "الحالة", false, false, true], ["created_at", "التاريخ", false, true]]} empty="لا توجد طلبات شحن" />}
        {tab === "transfers" && <SimpleTable rows={transfers} cols={[["to_office_name", "إلى/من"], ["amount", "المبلغ", true], ["status", "الحالة", false, false, true], ["created_at", "التاريخ", false, true]]} empty="لا توجد تحويلات" />}
        {tab === "withdrawals" && <SimpleTable rows={withdrawals} cols={[["amount", "المبلغ", true], ["method", "الطريقة"], ["status", "الحالة", false, false, true], ["created_at", "التاريخ", false, true]]} empty="لا توجد سحوبات" />}
      </div>
    </>
  );
}

function Balance({ id, title, value, icon: Icon, gold }) {
  return (
    <div data-testid={`wallet-balance-${id}`} className={`rounded-2xl border p-6 card-shadow ${gold ? "bg-[#0A2540] text-white border-[#0A2540]" : "bg-white"}`}>
      <div className="flex items-center justify-between mb-4">
        <span className={`text-sm ${gold ? "text-white/70" : "text-muted-foreground"}`}>{title}</span>
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${gold ? "bg-[#D4AF37]" : "bg-[#F4F6F8]"}`}><Icon className="w-4 h-4 text-[#0A2540]" /></div>
      </div>
      <div className={`tabular text-3xl font-bold ${gold ? "text-[#D4AF37]" : "text-[#0A2540]"}`}>{value}</div>
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

function TopupDialog({ onDone }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ amount: "", method: "حوالة بنكية", receipt_url: "" });
  const submit = async () => {
    try { await api.post("/wallet/topups", { amount: Number(f.amount), method: f.method, receipt_url: f.receipt_url }); toast.success("أُرسل طلب الشحن للإدارة للمراجعة"); setOpen(false); setF({ amount: "", method: "حوالة بنكية", receipt_url: "" }); onDone(); }
    catch (e) { toast.error(apiError(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button className="bg-[#0A2540] hover:bg-[#061A2E]" data-testid="open-topup-btn"><Upload className="w-4 h-4" /> شحن المحفظة</Button></DialogTrigger>
      <DialogContent dir="rtl">
        <DialogHeader><DialogTitle className="font-head text-[#0A2540]">شحن المحفظة برفع إشعار حوالة</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div><Label className="mb-2 block">المبلغ</Label><Input data-testid="topup-amount" type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></div>
          <div><Label className="mb-2 block">طريقة الدفع</Label>
            <select data-testid="topup-method" value={f.method} onChange={(e) => setF({ ...f, method: e.target.value })} className="w-full h-9 rounded-md border border-input bg-transparent px-3 text-sm">
              <option>حوالة بنكية</option><option>صرافة</option><option>نقداً</option>
            </select>
          </div>
          <div><Label className="mb-2 block">رابط صورة الإشعار</Label><Input data-testid="topup-receipt" value={f.receipt_url} onChange={(e) => setF({ ...f, receipt_url: e.target.value })} placeholder="https://..." /></div>
        </div>
        <DialogFooter><Button className="bg-[#0A2540] hover:bg-[#061A2E]" onClick={submit} disabled={!f.amount || !f.receipt_url} data-testid="submit-topup-btn">إرسال الطلب</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function TransferDialog({ onDone, available }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ to_email: "", amount: "", note: "" });
  const submit = async () => {
    try { await api.post("/wallet/transfers", { to_email: f.to_email, amount: Number(f.amount), note: f.note }); toast.success("أُرسل طلب التحويل — بانتظار موافقة الإدارة"); setOpen(false); setF({ to_email: "", amount: "", note: "" }); onDone(); }
    catch (e) { toast.error(apiError(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button variant="outline" data-testid="open-transfer-btn"><ArrowLeftRight className="w-4 h-4" /> تحويل P2P</Button></DialogTrigger>
      <DialogContent dir="rtl">
        <DialogHeader><DialogTitle className="font-head text-[#0A2540]">تحويل رصيد لمكتب آخر</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div><Label className="mb-2 block">بريد المكتب المستلم</Label><Input data-testid="transfer-email" value={f.to_email} onChange={(e) => setF({ ...f, to_email: e.target.value })} /></div>
          <div><Label className="mb-2 block">المبلغ (المتاح {money(available)})</Label><Input data-testid="transfer-amount" type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></div>
          <div><Label className="mb-2 block">ملاحظة</Label><Textarea data-testid="transfer-note" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} rows={2} /></div>
        </div>
        <DialogFooter><Button className="bg-[#0A2540] hover:bg-[#061A2E]" onClick={submit} disabled={!f.to_email || !f.amount} data-testid="submit-transfer-btn">إرسال طلب التحويل</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function WithdrawDialog({ onDone, available }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ amount: "", method: "حوالة بنكية", details: "" });
  const submit = async () => {
    try { await api.post("/wallet/withdrawals", { amount: Number(f.amount), method: f.method, details: f.details }); toast.success("أُرسل طلب السحب للإدارة"); setOpen(false); setF({ amount: "", method: "حوالة بنكية", details: "" }); onDone(); }
    catch (e) { toast.error(apiError(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button variant="outline" data-testid="open-withdraw-btn"><ArrowDownToLine className="w-4 h-4" /> سحب أرباح</Button></DialogTrigger>
      <DialogContent dir="rtl">
        <DialogHeader><DialogTitle className="font-head text-[#0A2540]">طلب سحب من الرصيد المتاح</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div><Label className="mb-2 block">المبلغ (المتاح {money(available)})</Label><Input data-testid="withdraw-amount" type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></div>
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
