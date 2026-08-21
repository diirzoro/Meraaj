import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Copy, Link2, TrendingUp, Sparkles, Wallet } from "lucide-react";
import { toast } from "sonner";

export default function Marketer() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const load = () => api.get("/individual/affiliate").then((r) => setData(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const activate = async () => {
    setBusy(true);
    try { await api.post("/individual/become-marketer"); toast.success("تم تفعيل وضع المسوّق"); load(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(data.link);
      toast.success("تم نسخ رابط الإحالة");
    } catch {
      try {
        const ta = document.createElement("textarea");
        ta.value = data.link; document.body.appendChild(ta); ta.select();
        document.execCommand("copy"); document.body.removeChild(ta);
        toast.success("تم نسخ رابط الإحالة");
      } catch {
        toast.error("تعذّر النسخ، انسخ الرابط يدوياً");
      }
    }
  };

  if (!data) return <div className="text-center py-20 text-muted-foreground">جارٍ التحميل...</div>;

  return (
    <>
      <PageHeader title="التسويق بالعمولة" subtitle="روّج لبرامج المنصة واكسب عمولة على كل حجز عبر رابطك" />

      {!data.is_marketer ? (
        <div className="max-w-lg mx-auto bg-white rounded-2xl border card-shadow p-10 text-center" data-testid="become-marketer-card">
          <div className="w-16 h-16 rounded-2xl bg-[#0A2540] flex items-center justify-center mx-auto mb-6">
            <Sparkles className="w-8 h-8 text-[#D4AF37]" />
          </div>
          <h3 className="font-head text-2xl font-bold text-[#0A2540] mb-3">فعّل وضع المسوّق</h3>
          <p className="text-muted-foreground text-sm mb-8 leading-relaxed">
            احصل على رابط إحالة خاص بك. أي حجز يتم عبر رابطك يمنحك عمولة تحفيزية تُضاف مباشرة إلى محفظتك.
          </p>
          <Button data-testid="activate-marketer-btn" onClick={activate} disabled={busy}
                  className="bg-[#0A2540] hover:bg-[#061A2E] h-11 px-8">
            {busy ? "جارٍ التفعيل..." : "تفعيل الآن"}
          </Button>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid sm:grid-cols-2 gap-5">
            <div className="rounded-2xl border p-6 card-shadow bg-[#0A2540] text-white" data-testid="earnings-card">
              <div className="flex items-center justify-between mb-4">
                <span className="text-sm text-white/70">إجمالي عمولات التسويق</span>
                <div className="w-9 h-9 rounded-lg bg-[#D4AF37] flex items-center justify-center"><TrendingUp className="w-4 h-4 text-[#0A2540]" /></div>
              </div>
              <div className="flex items-baseline gap-4">
                <div className="tabular text-3xl font-bold text-[#D4AF37]">{money(data.total_earned?.SAR || 0, "SAR")}</div>
                <div className="tabular text-xl font-bold text-white/80">{money(data.total_earned?.USD || 0, "USD")}</div>
              </div>
            </div>
            <div className="rounded-2xl border p-6 card-shadow bg-white flex flex-col justify-center">
              <span className="text-sm text-muted-foreground mb-2 flex items-center gap-2"><Wallet className="w-4 h-4" /> رمز الإحالة</span>
              <div className="tabular text-2xl font-bold text-[#0A2540] tracking-widest">{data.affiliate_code}</div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border card-shadow p-6">
            <Label>رابط الإحالة الخاص بك</Label>
            <div className="flex gap-2 mt-2">
              <div className="flex-1 flex items-center gap-2 bg-[#F4F6F8] rounded-lg px-4 py-3 text-sm text-[#0A2540] overflow-x-auto">
                <Link2 className="w-4 h-4 shrink-0" /> <span className="truncate" data-testid="affiliate-link">{data.link}</span>
              </div>
              <Button onClick={copy} data-testid="copy-link-btn" className="bg-[#0A2540] hover:bg-[#061A2E]"><Copy className="w-4 h-4" /> نسخ</Button>
            </div>
            <p className="text-xs text-muted-foreground mt-3">شارك هذا الرابط؛ أي زائر يحجز بعد فتحه تُسجّل لك عمولته.</p>
          </div>

          <div className="bg-white rounded-2xl border card-shadow overflow-hidden">
            <div className="px-6 py-4 border-b"><h3 className="font-head font-bold text-[#0A2540]">سجل العمولات</h3></div>
            {data.transactions.length === 0 ? (
              <div className="p-10 text-center text-muted-foreground text-sm">لا توجد عمولات بعد</div>
            ) : (
              <table className="w-full text-sm">
                <tbody>
                  {data.transactions.map((t) => (
                    <tr key={t.id} className="border-b last:border-0">
                      <td className="px-6 py-3">{t.description}</td>
                      <td className="px-6 py-3 tabular font-semibold text-[#15803D] text-left">{money(t.amount, t.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </>
  );
}

function Label({ children }) {
  return <span className="text-sm font-medium text-[#0A2540]">{children}</span>;
}
