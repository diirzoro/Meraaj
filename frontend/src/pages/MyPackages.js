import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { money, fmtDate, PKG_TYPE } from "@/lib/format";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Plus, Users, Pencil, Trash2, Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";

export default function MyPackages() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [regFor, setRegFor] = useState(null);
  const [regs, setRegs] = useState([]);
  const [regLoading, setRegLoading] = useState(false);
  const [delFor, setDelFor] = useState(null);
  const [delBusy, setDelBusy] = useState(false);

  const load = () => api.get("/packages/mine").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);

  const toggle = async (id) => {
    try { await api.patch(`/packages/${id}/toggle`); toast.success("تم تحديث حالة العرض"); load(); }
    catch { toast.error("تعذّر التحديث"); }
  };

  const openRegistrants = async (p) => {
    setRegFor(p); setRegLoading(true); setRegs([]);
    try { const r = await api.get(`/packages/${p.id}/registrants`); setRegs(r.data); }
    catch (e) { toast.error(apiError(e)); }
    finally { setRegLoading(false); }
  };

  const confirmDelete = async () => {
    if (!delFor) return;
    setDelBusy(true);
    try {
      await api.delete(`/packages/${delFor.id}`);
      toast.success("تم حذف البرنامج");
      setDelFor(null); load();
    } catch (e) { toast.error(apiError(e)); }
    finally { setDelBusy(false); }
  };

  const isRahal = (p) => p.source === "rahal";

  return (
    <>
      <PageHeader title="برامجي (كبائع)" subtitle="البرامج التي أضفتها للبيع في السوق"
        action={<Button data-testid="new-pkg-btn" onClick={() => navigate("/packages/new")} className="bg-[#0A2540] hover:bg-[#061A2E]"><Plus className="w-4 h-4" /> برنامج جديد</Button>} />

      {items.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">لم تضف أي برنامج بعد</div>
      ) : (
        <div className="bg-white rounded-2xl border card-shadow overflow-x-auto table-scroll">
          <table className="w-full text-sm min-w-[820px]">
            <thead className="text-muted-foreground text-xs border-b">
              <tr>
                <th className="text-start px-6 py-3 font-medium">البرنامج</th>
                <th className="text-start px-6 py-3 font-medium">النوع</th>
                <th className="text-start px-6 py-3 font-medium">الانطلاق</th>
                <th className="text-start px-6 py-3 font-medium">العودة</th>
                <th className="text-start px-6 py-3 font-medium">المقاعد</th>
                <th className="text-start px-6 py-3 font-medium">سعر البيع</th>
                <th className="text-start px-6 py-3 font-medium">إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} className="border-b last:border-0" data-testid={`mypkg-row-${p.id}`}>
                  <td className="px-6 py-4 font-medium">
                    {p.title}
                    {isRahal(p) && <span className="ms-2 text-[10px] bg-[#EFF6FF] text-[#1D4ED8] border border-[#BFDBFE] rounded px-1.5 py-0.5">رحّال</span>}
                  </td>
                  <td className="px-6 py-4">{PKG_TYPE[p.type] || p.type}</td>
                  <td className="px-6 py-4">{fmtDate(p.departure_date)}</td>
                  <td className="px-6 py-4">{fmtDate(p.return_date)}</td>
                  <td className="px-6 py-4 tabular"><span className="flex items-center gap-1"><Users className="w-3.5 h-3.5" />{p.available_seats}/{p.total_seats}</span></td>
                  <td className="px-6 py-4 tabular font-semibold text-[#0A2540]">{money(p.final_sale_price, p.currency)}</td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Button variant="outline" size="sm" data-testid={`registrants-btn-${p.id}`} onClick={() => openRegistrants(p)}>
                        <Users className="w-3.5 h-3.5" /> المسجّلون
                      </Button>
                      <Button variant={p.status === "listed" ? "outline" : "secondary"} size="sm"
                              data-testid={`toggle-pkg-${p.id}`} onClick={() => toggle(p.id)}>
                        {p.status === "listed" ? <><EyeOff className="w-3.5 h-3.5" /> إخفاء</> : <><Eye className="w-3.5 h-3.5" /> عرض</>}
                      </Button>
                      {!isRahal(p) && (
                        <>
                          <Button variant="outline" size="sm" data-testid={`edit-pkg-${p.id}`} onClick={() => navigate(`/packages/${p.id}/edit`)}>
                            <Pencil className="w-3.5 h-3.5" /> تعديل
                          </Button>
                          <Button variant="outline" size="sm" data-testid={`delete-pkg-${p.id}`}
                                  onClick={() => setDelFor(p)} className="text-destructive border-destructive/30 hover:bg-destructive/5">
                            <Trash2 className="w-3.5 h-3.5" /> حذف
                          </Button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={!!regFor} onOpenChange={(o) => !o && setRegFor(null)}>
        <DialogContent data-testid="registrants-dialog">
          <DialogHeader>
            <DialogTitle>المسجّلون في: {regFor?.title}</DialogTitle>
          </DialogHeader>
          <div className="flex flex-wrap items-center gap-3 text-xs mb-1">
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#1D4ED8]" /> حجز جديد</span>
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#A16207]" /> تم إصدار التأشيرة</span>
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#15803D]" /> تم التفويج</span>
          </div>
          {regLoading ? (
            <div className="py-8 text-center text-muted-foreground text-sm">جارٍ التحميل...</div>
          ) : regs.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground text-sm" data-testid="registrants-empty">لا يوجد مسجّلون في هذا البرنامج بعد</div>
          ) : (
            <div className="space-y-3 max-h-[55vh] overflow-y-auto">
              {regs.map((b) => (
                <div key={b.id} className="border rounded-xl p-3" data-testid={`reg-booking-${b.id}`}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="font-medium text-sm">{b.buyer_office_name}</div>
                    <StatusBadge status={b.status} />
                  </div>
                  <div className="text-xs text-muted-foreground mb-2">{b.seats} مقعد · {b.registrants?.length || 0} مسافر</div>
                  <div className="flex flex-wrap gap-1.5">
                    {(b.registrants || []).map((r, i) => (
                      <span key={i} className="text-[11px] bg-[#F4F6F8] rounded px-2 py-1">{r.name}{r.visa_no ? ` · تأشيرة ${r.visa_no}` : ""}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!delFor} onOpenChange={(o) => !o && setDelFor(null)}>
        <DialogContent data-testid="delete-dialog">
          <DialogHeader>
            <DialogTitle>حذف البرنامج</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            هل أنت متأكد من حذف «{delFor?.title}»؟ لا يمكن التراجع. الحذف متاح فقط إذا لم يكن هناك أي حجز نشط (أزرق/أصفر/أخضر).
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDelFor(null)} data-testid="delete-cancel-btn">إلغاء</Button>
            <Button className="bg-destructive text-white hover:bg-destructive/90" disabled={delBusy}
                    onClick={confirmDelete} data-testid="delete-confirm-btn">
              {delBusy ? "جارٍ الحذف..." : "تأكيد الحذف"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
