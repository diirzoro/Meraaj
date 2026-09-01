import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { Bell, RefreshCw, ListChecks } from "lucide-react";

export default function AdminNotifications() {
  const [tpl, setTpl] = useState({ kinds: {}, items: [] });
  const [log, setLog] = useState({ items: [], stats: {} });
  const [tasks, setTasks] = useState([]);
  const [form, setForm] = useState({ kind: "", title: "", body: "", active: true });
  const [scanRes, setScanRes] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/admin/notification-templates").then((r) => setTpl(r.data));
    api.get("/admin/notification-log?limit=100").then((r) => setLog(r.data));
    api.get("/admin/tasks").then((r) => setTasks(r.data));
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); load(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title="الإشعارات والمهام" subtitle="إشعارات داخل النظام بقوالب قابلة للإدارة، سجل إرسال، وفحص تنبيهات المستندات والجوازات والسقوف والمهام المتأخرة" />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        <Stat label="قوالب مُعرَّفة" v={tpl.items.length} tid="stat-templates" />
        <Stat label="إشعارات مُسلَّمة" v={log.stats.delivered || 0} ok tid="stat-delivered" />
        <Stat label="فشل الإرسال" v={log.stats.failed || 0} danger tid="stat-failed" />
        <Stat label="مهام مفتوحة" v={tasks.filter((t) => t.status === "open" || t.status === "in_progress").length} tid="stat-tasks" />
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-5 mb-5" data-testid="scan-panel">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 font-head font-bold text-[#0A2540] text-sm">
              <RefreshCw className="w-4 h-4 text-[#D4AF37]" /> فحص التنبيهات الآن
            </div>
            <div className="text-[11px] text-muted-foreground mt-1">
              يفحص المستندات الناقصة، الجوازات القاربة على الانتهاء، تجاوز 70% من السقف الائتماني، والمهام المتأخرة (ويصعّدها).
            </div>
          </div>
          <Button size="sm" className="bg-[#0A2540] hover:bg-[#061A2E]" data-testid="scan-btn" disabled={busy}
            onClick={() => act(async () => {
              const r = await api.post("/admin/notifications/scan");
              setScanRes(r.data);
              toast.success(`تم إنشاء ${r.data.total} تنبيهاً`);
            }, "تم الفحص")}>تشغيل الفحص</Button>
        </div>
        {scanRes && (
          <div className="mt-3 text-xs bg-[#F0FDF4] border border-[#BBF7D0] text-[#15803D] rounded-lg px-3 py-2" data-testid="scan-result">
            نتيجة الفحص: {scanRes.total} تنبيهاً جديداً — مستندات ناقصة {scanRes.created.documents_missing} •
            جوازات {scanRes.created.passport_expiring} • سقوف ائتمانية {scanRes.created.credit_threshold} •
            مهام متأخرة {scanRes.created.task_overdue}
          </div>
        )}
      </div>

      <div className="grid lg:grid-cols-2 gap-5 mb-5">
        <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="templates-panel">
          <div className="flex items-center gap-2 font-head font-bold text-[#0A2540] text-sm mb-3">
            <Bell className="w-4 h-4 text-[#D4AF37]" /> قوالب الإشعارات
          </div>
          <div className="space-y-2 mb-4 max-h-56 overflow-y-auto">
            {tpl.items.length === 0 ? <div className="text-xs text-muted-foreground">لا توجد قوالب — تُستخدم النصوص الافتراضية</div> :
              tpl.items.map((t) => (
                <div key={t.id} className="text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-2" data-testid={`template-${t.kind}`}>
                  <b>{tpl.kinds[t.kind] || t.kind}</b> {t.active ? "" : "(معطّل)"}
                  <div className="text-muted-foreground">{t.title}</div>
                </div>
              ))}
          </div>
          <div className="space-y-2 border-t pt-3">
            <div><Label className="text-xs">نوع الإشعار</Label>
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} data-testid="template-kind"
                className="w-full h-9 rounded-md border border-input px-2 text-xs bg-white">
                <option value="">اختر النوع</option>
                {Object.entries(tpl.kinds).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select></div>
            <div><Label className="text-xs">العنوان</Label>
              <Input className="h-8 text-xs" value={form.title} data-testid="template-title"
                onChange={(e) => setForm({ ...form, title: e.target.value })} /></div>
            <div><Label className="text-xs">النص</Label>
              <Textarea rows={2} className="text-xs" value={form.body} data-testid="template-body"
                onChange={(e) => setForm({ ...form, body: e.target.value })} /></div>
            <label className="text-xs flex items-center gap-2" data-testid="template-active">
              <input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /> نشط
            </label>
            <Button size="sm" className="bg-[#0A2540] hover:bg-[#061A2E]" data-testid="save-template-btn"
              disabled={busy || !form.kind || form.title.length < 2}
              onClick={() => act(async () => { await api.post("/admin/notification-templates", form); setForm({ kind: "", title: "", body: "", active: true }); }, "تم حفظ القالب")}>
              حفظ القالب
            </Button>
            <div className="text-[10px] text-muted-foreground">
              قنوات البريد وWhatsApp مُعدّة للإضافة لاحقاً من إعدادات التكامل — الإشعارات الداخلية تعمل الآن.
            </div>
          </div>
        </div>

        <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="log-panel">
          <div className="font-head font-bold text-[#0A2540] text-sm mb-3">سجل الإرسال</div>
          <div className="space-y-1.5 max-h-96 overflow-y-auto">
            {log.items.length === 0 ? <div className="text-xs text-muted-foreground">لا يوجد سجل</div> :
              log.items.map((x) => (
                <div key={x.id} className={`text-[11px] rounded-lg px-3 py-1.5 ${x.status === "failed" ? "bg-[#FEF2F2] text-[#B91C1C]" : "bg-[#F4F6F8]"}`}
                  data-testid={`log-${x.id}`}>
                  {tpl.kinds[x.kind] || x.kind} • {x.channel} • {x.status === "failed" ? `فشل: ${x.error}` : "مُسلَّم"}
                  <span className="text-[10px] text-muted-foreground mr-2">{fmtDate(x.at)}</span>
                </div>
              ))}
          </div>
        </div>
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="tasks-panel">
        <div className="flex items-center gap-2 font-head font-bold text-[#0A2540] text-sm mb-3">
          <ListChecks className="w-4 h-4 text-[#D4AF37]" /> مركز المهام ({tasks.length})
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs min-w-[700px]">
            <thead className="bg-[#F4F6F8] text-muted-foreground">
              <tr>{["المهمة", "الطلب", "المسؤول", "الأولوية", "الاستحقاق", "الحالة"].map((h) => (
                <th key={h} className="text-right font-semibold px-3 py-2">{h}</th>))}</tr>
            </thead>
            <tbody>
              {tasks.length === 0 ? (
                <tr><td colSpan={6} className="text-center py-8 text-muted-foreground" data-testid="tasks-empty">لا توجد مهام</td></tr>
              ) : tasks.map((t) => (
                <tr key={t.id} className="border-t" data-testid={`task-row-${t.id}`}>
                  <td className="px-3 py-2 font-semibold text-[#0A2540]">{t.title}
                    {t.escalated && <span className="mr-1 text-[9px] px-1.5 py-0.5 rounded bg-[#FEF2F2] text-[#B91C1C]">مُصعَّدة</span>}
                  </td>
                  <td className="px-3 py-2 text-[10px]">{(t.package_title || "").slice(0, 24)}</td>
                  <td className="px-3 py-2">{t.assignee || "—"}</td>
                  <td className="px-3 py-2">{t.priority}</td>
                  <td className="px-3 py-2">{t.due_date || "—"}</td>
                  <td className="px-3 py-2">
                    <select value={t.status} data-testid={`task-status-${t.id}`}
                      onChange={(e) => act(() => api.patch(`/admin/tasks/${t.id}`, { status: e.target.value }), "تم تحديث المهمة")}
                      className="h-7 rounded-md border border-input px-2 text-[11px] bg-white">
                      <option value="open">مفتوحة</option><option value="in_progress">قيد التنفيذ</option>
                      <option value="done">منجزة</option><option value="cancelled">ملغاة</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

const Stat = ({ label, v, ok, danger, tid }) => (
  <div className="bg-white rounded-2xl border p-4 card-shadow" data-testid={tid}>
    <div className={`tabular text-2xl font-bold ${danger ? "text-[#B91C1C]" : ok ? "text-[#15803D]" : "text-[#0A2540]"}`}>{v}</div>
    <div className="text-[11px] text-muted-foreground mt-1">{label}</div>
  </div>
);
