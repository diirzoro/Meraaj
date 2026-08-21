import { useEffect, useState, useRef } from "react";
import api, { apiError, setToken } from "@/lib/api";
import { money, fmtDate, PKG_TYPE } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Network, MapPin, Users, CalendarDays, ShoppingCart, Plus, Trash2, Search } from "lucide-react";
import { toast } from "sonner";

const TABS = [{ k: "", l: "الكل" }, { k: "umrah", l: "عمرة" }, { k: "tourism", l: "سياحة" }];

export default function EmbedMarket() {
  const [phase, setPhase] = useState("auth"); // auth | ready | error
  const [items, setItems] = useState([]);
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(null);
  const rootRef = useRef(null);

  // Report height to the Rahal parent frame for auto-resize
  const postHeight = () => {
    try {
      const h = document.body.scrollHeight;
      window.parent?.postMessage({ source: "meraaj", type: "resize", height: h }, "*");
    } catch {}
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    (async () => {
      try {
        if (token) {
          const { data } = await api.post("/integrations/rahal/sso", { token });
          setToken(data.access_token);
        }
        await api.get("/auth/me"); // validate session
        setPhase("ready");
        window.parent?.postMessage({ source: "meraaj", type: "ready" }, "*");
      } catch (e) {
        setPhase("error");
      }
    })();
  }, []);

  const load = () => {
    const p = {};
    if (type) p.type = type;
    if (q) p.q = q;
    api.get("/packages", { params: p }).then((r) => setItems(r.data)).catch(() => {});
  };
  useEffect(() => { if (phase === "ready") load(); /* eslint-disable-next-line */ }, [phase, type]);
  useEffect(() => { postHeight(); }, [items, sel]);

  if (phase === "auth") {
    return <div className="min-h-[300px] flex items-center justify-center" dir="rtl">
      <div className="w-9 h-9 border-4 border-[#0A2540] border-t-transparent rounded-full animate-spin" /></div>;
  }
  if (phase === "error") {
    return <div className="min-h-[300px] flex items-center justify-center text-center p-8" dir="rtl">
      <div>
        <p className="font-head font-bold text-[#0A2540] mb-2">تعذّر فتح سوق معراج</p>
        <p className="text-sm text-muted-foreground">رمز الدخول من رحال غير صالح أو منتهي. أعد المحاولة من داخل رحال.</p>
      </div></div>;
  }

  return (
    <div ref={rootRef} className="min-h-screen bg-[#F4F6F8] p-5" dir="rtl">
      <div className="flex items-center gap-3 mb-5">
        <div className="w-9 h-9 rounded-xl bg-[#0A2540] flex items-center justify-center"><Network className="w-5 h-5 text-[#D4AF37]" /></div>
        <div><div className="font-head font-bold text-[#0A2540]">سوق معراج نتورك</div>
          <div className="text-[11px] text-muted-foreground">داخل رحال</div></div>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-5">
        <div className="flex bg-white border rounded-xl p-1">
          {TABS.map((t) => (
            <button key={t.k} data-testid={`embed-tab-${t.k || "all"}`} onClick={() => setType(t.k)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${type === t.k ? "bg-[#0A2540] text-white" : "text-muted-foreground hover:text-[#0A2540]"}`}>{t.l}</button>
          ))}
        </div>
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 absolute top-1/2 -translate-y-1/2 start-3 text-muted-foreground" />
          <Input data-testid="embed-search" value={q} onChange={(e) => setQ(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && load()} placeholder="ابحث عن برنامج..." className="ps-9 bg-white" />
        </div>
      </div>

      {items.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground text-sm">لا توجد برنامجات مطابقة</div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {items.map((p) => (
            <button key={p.id} onClick={() => setSel(p)} data-testid={`embed-pkg-${p.id}`}
                    className="text-start bg-white rounded-2xl border overflow-hidden hover:shadow-lg transition-shadow">
              <div className="h-36 bg-[#0A2540] relative">
                {p.images?.[0] && <img src={p.images[0]} alt={p.title} className="w-full h-full object-cover" />}
                <span className="absolute top-2 start-2 bg-white/90 text-[#0A2540] text-xs font-semibold px-2 py-0.5 rounded-full">{PKG_TYPE[p.type] || p.type}</span>
              </div>
              <div className="p-4">
                <h3 className="font-head font-bold text-[#0A2540] line-clamp-1">{p.title}</h3>
                <p className="text-xs text-muted-foreground mt-1">{p.seller_office_name}</p>
                <div className="flex flex-wrap gap-2 mt-2 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1"><CalendarDays className="w-3 h-3" /> {fmtDate(p.departure_date)}</span>
                  <span className="flex items-center gap-1"><Users className="w-3 h-3" /> {p.available_seats} مقعد</span>
                </div>
                <div className="mt-3 pt-3 border-t flex items-center justify-between">
                  {p.net_cost_per_seat != null
                    ? <div><div className="text-[10px] text-muted-foreground">التكلفة الصافية</div><div className="tabular font-bold text-[#0A2540]">{money(p.net_cost_per_seat, p.currency)}</div></div>
                    : <div className="tabular font-bold text-[#0A2540]">{money(p.final_sale_price, p.currency)}</div>}
                  {p.buyer_office_commission != null && <span className="text-[11px] font-semibold text-[#15803D] bg-[#F0FDF4] px-2 py-1 rounded">عمولتك {money(p.buyer_office_commission, p.currency)}</span>}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      <EmbedBookingDialog pkg={sel} onClose={() => setSel(null)} onBooked={() => { setSel(null); load(); }} />
    </div>
  );
}

function EmbedBookingDialog({ pkg, onClose, onBooked }) {
  const [regs, setRegs] = useState([{ name: "", passport_no: "", age: "" }]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (pkg) setRegs([{ name: "", passport_no: "", age: "" }]); }, [pkg]);
  if (!pkg) return null;

  const isOffice = pkg.net_cost_per_seat != null;
  const seats = regs.length;
  const netTotal = (pkg.net_cost_per_seat || 0) * seats;
  const platformFee = isOffice ? +((pkg.buyer_office_commission || 0) * seats * 0.1).toFixed(2) : 0;
  const required = isOffice ? +(netTotal + platformFee).toFixed(2) : +((pkg.final_sale_price || 0) * seats).toFixed(2);
  const setReg = (i, k) => (e) => { const c = [...regs]; c[i][k] = e.target.value; setRegs(c); };

  const book = async () => {
    setBusy(true);
    try {
      await api.post("/bookings", {
        package_id: pkg.id,
        registrants: regs.map((r) => ({ name: r.name, passport_no: r.passport_no, age: Number(r.age) })),
      });
      toast.success("تم إنشاء الحجز بنجاح داخل معراج");
      window.parent?.postMessage({ source: "meraaj", type: "booking_created", package_ref: pkg.rahal_ref || null }, "*");
      onBooked();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={!!pkg} onOpenChange={onClose}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" dir="rtl">
        <DialogHeader><DialogTitle className="font-head text-[#0A2540]">{pkg.title}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          {regs.map((r, i) => (
            <div key={i} className="border rounded-xl p-3 relative">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-muted-foreground">مسجّل #{i + 1}</span>
                {regs.length > 1 && <button onClick={() => setRegs(regs.filter((_, x) => x !== i))} className="text-destructive"><Trash2 className="w-4 h-4" /></button>}
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="col-span-2"><Label className="mb-1 block text-xs">الاسم الكامل</Label><Input data-testid={`embed-reg-name-${i}`} value={r.name} onChange={setReg(i, "name")} /></div>
                <div><Label className="mb-1 block text-xs">رقم الجواز</Label><Input data-testid={`embed-reg-passport-${i}`} value={r.passport_no} onChange={setReg(i, "passport_no")} /></div>
                <div><Label className="mb-1 block text-xs">العمر</Label><Input data-testid={`embed-reg-age-${i}`} type="number" value={r.age} onChange={setReg(i, "age")} /></div>
              </div>
            </div>
          ))}
          <Button variant="outline" onClick={() => setRegs([...regs, { name: "", passport_no: "", age: "" }])} data-testid="embed-add-reg" className="w-full"><Plus className="w-4 h-4" /> إضافة مسجّل</Button>
          <div className="bg-[#F4F6F8] rounded-xl p-3 text-sm flex justify-between font-bold text-[#0A2540]">
            <span>الإجمالي المخصوم من رصيدك</span><span className="tabular">{money(required, pkg.currency)}</span>
          </div>
        </div>
        <DialogFooter>
          <Button data-testid="embed-confirm-booking" onClick={book} disabled={busy || regs.some((r) => !r.name || !r.passport_no || !r.age)}
                  className="w-full h-11 bg-[#0A2540] hover:bg-[#061A2E]"><ShoppingCart className="w-4 h-4" /> {busy ? "جارٍ الحجز..." : `تأكيد الحجز — ${money(required, pkg.currency)}`}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
