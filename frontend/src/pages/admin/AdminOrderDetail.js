import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api, { apiError } from "@/lib/api";
import { money, fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { STATUS_LABEL, STATUS_CLASS, APPROVAL_LABEL } from "./AdminOrders";
import {
  ChevronLeft, Printer, AlertTriangle, FileText, StickyNote, ListChecks, Clock, ShieldCheck,
} from "lucide-react";

const DOC_LABEL = { passport: "جواز", visa: "تأشيرة", photo: "صورة", ticket: "تذكرة", other: "أخرى" };

export default function AdminOrderDetail() {
  const { id } = useParams();
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [task, setTask] = useState({ title: "", assignee: "", due_date: "", priority: "normal" });
  const [escReason, setEscReason] = useState("");

  const load = useCallback(() => api.get(`/admin/bookings/${id}/full`).then((r) => setD(r.data)), [id]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); await load(); }
    catch (e) { toast.error(apiError(e)); }
    finally { setBusy(false); }
  };

  if (!d) return <div className="text-center py-20 text-muted-foreground" data-testid="order-detail-loading">جارٍ التحميل...</div>;
  const b = d.booking, f = d.financials, c = f.currency;

  return (
    <div data-testid="order-detail">
      {/* Breadcrumbs */}
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-3" data-testid="order-breadcrumbs">
        <Link to="/admin" className="hover:text-[#0A2540]">لوحة القيادة</Link>
        <ChevronLeft className="w-3 h-3" />
        <Link to="/admin/orders" className="hover:text-[#0A2540]">مركز الطلبات</Link>
        <ChevronLeft className="w-3 h-3" />
        <span className="text-[#0A2540] font-semibold">طلب {b.id.slice(-6)}</span>
      </div>

      {/* Sticky header actions */}
      <div className="bg-white rounded-2xl border card-shadow p-5 mb-5 sticky top-0 z-10">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="font-head font-bold text-lg text-[#0A2540]">{b.package_title}</h1>
            <div className="text-xs text-muted-foreground mt-1">
              {b.buyer_office_name} ← {b.seller_office_name} • انطلاق {fmtDate(b.departure_date)} •
              {b.rahal_ref ? " مصدر: رحّال" : " مصدر: معراج"} • {b.seats} مقعد
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`text-xs px-3 py-1 rounded-full border font-semibold ${STATUS_CLASS[b.status] || ""}`} data-testid="order-status">
              {STATUS_LABEL[b.status] || b.status}
            </span>
            {b.approval_status && (
              <span className="text-xs px-3 py-1 rounded-full border bg-[#F4F6F8] text-[#0A2540] font-semibold" data-testid="order-approval">
                {APPROVAL_LABEL[b.approval_status] || b.approval_status}
              </span>
            )}
            <Button size="sm" variant="outline" onClick={() => window.print()} data-testid="order-print">
              <Printer className="w-4 h-4" /> طباعة / تصدير
            </Button>
          </div>
        </div>

        {b.needs_attention && (
          <div className="mt-4 flex flex-wrap gap-2" data-testid="order-attention">
            {b.attention_reasons.map((r, i) => (
              <span key={i} className={`text-[11px] px-2.5 py-1 rounded-full border ${b.severity === "critical" ? "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" : "bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]"}`}>{r}</span>
            ))}
          </div>
        )}
        <div className="mt-4 pt-4 border-t text-[11px] text-muted-foreground flex items-start gap-2">
          <ShieldCheck className="w-4 h-4 text-[#15803D] shrink-0" />
          دورة الطلب محفوظة: قرار القبول/الرفض يبقى للبائع. الإدارة تراقب وتُصعّد، وقرار الإلغاء النهائي من صفحة «طلبات الإلغاء».
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 space-y-5">
          {/* Financials */}
          <Card title="التفصيل المالي والعمولات" icon={FileText} tid="order-financials">
            <div className="grid sm:grid-cols-3 gap-3">
              <F label="المبلغ المدفوع (إجمالي)" v={money(f.gross, c)} big />
              <F label="صافي البائع" v={money(f.seller_net, c)} />
              <F label="عمولة المشتري" v={money(f.buyer_commission, c)} />
              <F label="عمولة المنصة" v={money(f.platform_fee, c)} />
              <F label="أرباح المنصة" v={money(f.platform_profit, c)} />
              <F label="عمولة المسوّق" v={money(f.marketer_commission, c)} />
              <F label="نوع الغرفة" v={b.room_type || "—"} />
              <F label="تمت التسوية" v={f.settled ? "نعم" : "لا"} />
              <F label="تسليم رحّال" v={b.delivery_status || "—"} />
            </div>
            {d.transactions.length > 0 && (
              <div className="mt-4 border-t pt-3">
                <div className="text-xs font-semibold text-[#0A2540] mb-2">الحركات المالية المرتبطة</div>
                <div className="space-y-1.5">
                  {d.transactions.map((t) => (
                    <div key={t.id} className="flex items-center justify-between text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-1.5">
                      <span>{t.description}</span>
                      <span className={`tabular font-bold ${Number(t.amount) < 0 ? "text-[#B91C1C]" : "text-[#15803D]"}`}>
                        {money(t.amount, t.currency)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>

          {/* Travelers + documents */}
          <Card title={`المسافرون والمستندات (${(b.registrants || []).length})`} icon={FileText} tid="order-travelers">
            {(b.registrants || []).map((r, i) => {
              const docs = d.documents.filter((x) => x.registrant_index === i);
              const miss = (d.missing_documents.find((m) => m.index === i) || {}).missing || [];
              return (
                <div key={i} className="border rounded-xl p-3 mb-2" data-testid={`traveler-${i}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm font-semibold text-[#0A2540]">
                      {r.name} <span className="text-[11px] text-muted-foreground font-normal">
                        • جواز {r.passport_no || "—"} • {r.category || "adult"} {r.visa_no ? `• تأشيرة ${r.visa_no}` : ""}
                      </span>
                    </div>
                    {miss.length > 0 && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#FEF2F2] text-[#B91C1C] border border-[#FECACA]">
                        ناقص: {miss.map((m) => DOC_LABEL[m]).join(" / ")}
                      </span>
                    )}
                  </div>
                  {docs.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {docs.map((doc) => (
                        <span key={doc.id} className="text-[10px] px-2 py-0.5 rounded bg-[#F4F6F8] text-[#0A2540]" data-testid={`order-doc-${doc.id}`}>
                          {DOC_LABEL[doc.doc_type] || doc.doc_type}: {doc.filename}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </Card>

          {/* Timeline */}
          <Card title="سجل الإجراءات (من قام بماذا ومتى)" icon={Clock} tid="order-timeline">
            {d.timeline.length === 0 ? <Empty text="لا توجد أحداث" /> : (
              <div className="space-y-2">
                {d.timeline.map((e) => (
                  <div key={e.id} className="flex items-start gap-3 text-xs border-r-2 border-[#D4AF37] pr-3">
                    <div className="flex-1">
                      <div className="font-semibold text-[#0A2540]">{e.event}</div>
                      {e.reason && <div className="text-muted-foreground">السبب: {e.reason}</div>}
                      <div className="text-[10px] text-muted-foreground">{e.actor_type} • {fmtDate(e.at)}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-5">
          <Card title="الأطراف" icon={ShieldCheck} tid="order-parties">
            {[["المشتري", d.buyer], ["البائع", d.seller]].map(([lab, p]) => (
              <div key={lab} className="bg-[#F4F6F8] rounded-lg px-3 py-2 mb-2 text-xs">
                <div className="text-[10px] text-muted-foreground">{lab}</div>
                <div className="font-bold text-[#0A2540]">{p?.name || "—"}</div>
                <div className="text-muted-foreground">{p?.email} • {p?.phone}</div>
                <div className="text-[10px] mt-0.5">الحالة: {p?.status || "active"}</div>
              </div>
            ))}
          </Card>

          {/* Escalation */}
          <Card title="التصعيد الإداري" icon={AlertTriangle} tid="order-escalation">
            {b.escalated ? (
              <>
                <div className="text-xs bg-[#FEF2F2] text-[#B91C1C] rounded-lg px-3 py-2 mb-3">
                  مُصعَّد: {b.escalation_reason}
                </div>
                <Button size="sm" variant="outline" disabled={busy} data-testid="de-escalate-btn"
                  onClick={() => act(() => api.post(`/admin/bookings/${id}/de-escalate`), "تم إغلاق التصعيد")}>
                  إغلاق التصعيد
                </Button>
              </>
            ) : (
              <>
                <Label className="text-xs mb-1 block">سبب التصعيد (إلزامي)</Label>
                <Textarea rows={2} value={escReason} onChange={(e) => setEscReason(e.target.value)} data-testid="escalate-reason" />
                <Button size="sm" className="mt-2 bg-[#0A2540] hover:bg-[#061A2E]" disabled={busy || escReason.trim().length < 3}
                  data-testid="escalate-btn"
                  onClick={() => act(() => api.post(`/admin/bookings/${id}/escalate`, { reason: escReason }), "تم تصعيد الطلب")}>
                  تصعيد الطلب
                </Button>
              </>
            )}
          </Card>

          {/* Internal notes */}
          <Card title={`ملاحظات داخلية (${d.notes.length})`} icon={StickyNote} tid="order-notes">
            <div className="text-[10px] text-muted-foreground mb-2">لا تظهر للعميل ولا للمكاتب</div>
            <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} data-testid="note-input" />
            <Button size="sm" className="mt-2 bg-[#0A2540] hover:bg-[#061A2E]" disabled={busy || note.trim().length < 2}
              data-testid="add-note-btn"
              onClick={() => act(async () => { await api.post(`/admin/bookings/${id}/notes`, { text: note }); setNote(""); }, "تمت إضافة الملاحظة")}>
              إضافة ملاحظة
            </Button>
            <div className="mt-3 space-y-2">
              {d.notes.map((n) => (
                <div key={n.id} className="text-xs bg-[#FEFCE8] border border-[#FEF08A] rounded-lg px-3 py-2" data-testid={`note-${n.id}`}>
                  {n.text}
                  <div className="text-[10px] text-muted-foreground mt-1">{n.author_email} • {fmtDate(n.created_at)}</div>
                </div>
              ))}
            </div>
          </Card>

          {/* Tasks */}
          <Card title={`مهام الموظفين (${d.tasks.length})`} icon={ListChecks} tid="order-tasks">
            <div className="space-y-2">
              <Input placeholder="عنوان المهمة" value={task.title} onChange={(e) => setTask({ ...task, title: e.target.value })} data-testid="task-title" className="h-8 text-xs" />
              <Input placeholder="المسؤول" value={task.assignee} onChange={(e) => setTask({ ...task, assignee: e.target.value })} data-testid="task-assignee" className="h-8 text-xs" />
              <div className="flex gap-2">
                <Input type="date" value={task.due_date} onChange={(e) => setTask({ ...task, due_date: e.target.value })} data-testid="task-due" className="h-8 text-xs" />
                <select value={task.priority} onChange={(e) => setTask({ ...task, priority: e.target.value })} data-testid="task-priority"
                  className="h-8 rounded-md border border-input px-2 text-xs">
                  <option value="low">منخفضة</option><option value="normal">عادية</option>
                  <option value="high">عالية</option><option value="urgent">عاجلة</option>
                </select>
              </div>
              <Button size="sm" className="bg-[#0A2540] hover:bg-[#061A2E] w-full" disabled={busy || task.title.trim().length < 2}
                data-testid="add-task-btn"
                onClick={() => act(async () => { await api.post(`/admin/bookings/${id}/tasks`, task); setTask({ title: "", assignee: "", due_date: "", priority: "normal" }); }, "تمت إضافة المهمة")}>
                إضافة مهمة
              </Button>
            </div>
            <div className="mt-3 space-y-2">
              {d.tasks.map((t) => (
                <div key={t.id} className="text-xs bg-[#F4F6F8] rounded-lg px-3 py-2" data-testid={`task-${t.id}`}>
                  <div className="font-semibold text-[#0A2540]">{t.title}</div>
                  <div className="text-[10px] text-muted-foreground">
                    {t.assignee || "غير محدد"} • {t.due_date || "بدون موعد"} • {t.priority}
                  </div>
                  <select value={t.status} data-testid={`task-status-${t.id}`}
                    onChange={(e) => act(() => api.patch(`/admin/tasks/${t.id}`, { status: e.target.value }), "تم تحديث المهمة")}
                    className="mt-1.5 h-7 rounded-md border border-input px-2 text-[11px] bg-white">
                    <option value="open">مفتوحة</option><option value="in_progress">قيد التنفيذ</option>
                    <option value="done">منجزة</option><option value="cancelled">ملغاة</option>
                  </select>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

const Card = ({ title, icon: Icon, children, tid }) => (
  <div className="bg-white rounded-2xl border card-shadow p-5" data-testid={tid}>
    <div className="flex items-center gap-2 mb-4 font-head font-bold text-[#0A2540] text-sm">
      <Icon className="w-4 h-4 text-[#D4AF37]" /> {title}
    </div>
    {children}
  </div>
);

const F = ({ label, v, big }) => (
  <div className="bg-[#F4F6F8] rounded-lg px-3 py-2">
    <div className="text-[10px] text-muted-foreground">{label}</div>
    <div className={`tabular font-bold text-[#0A2540] ${big ? "text-lg" : "text-sm"}`}>{v}</div>
  </div>
);

const Empty = ({ text }) => <div className="text-xs text-muted-foreground py-4 text-center">{text}</div>;
