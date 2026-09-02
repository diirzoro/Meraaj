import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Database, ShieldCheck, PlayCircle, FlaskConical } from "lucide-react";

export default function AdminBackups() {
  const [d, setD] = useState(null);
  const [audit, setAudit] = useState([]);
  const [drillFile, setDrillFile] = useState("");
  const [runReason, setRunReason] = useState("");
  const [confirmRun, setConfirmRun] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/admin/backups").then((r) => setD(r.data));
    api.get("/admin/audit?limit=50&entity=backup").then((r) => setAudit(r.data.items || []));
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); load(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  if (!d) return <div className="text-center py-20 text-muted-foreground" data-testid="backups-loading">جارٍ التحميل...</div>;

  return (
    <>
      <PageHeader title="النسخ الاحتياطي والاستعادة"
        subtitle="قسم مستقل: نسخة يدوية، الجدولة اليومية، التشفير، سياسة الاحتفاظ، السجل الكامل، واختبار الاستعادة على قاعدة معزولة"
        action={<Button className="bg-[#0A2540] hover:bg-[#061A2E]" data-testid="open-run-backup"
          onClick={() => { setRunReason(""); setConfirmRun(true); }}>
          <PlayCircle className="w-4 h-4" /> تشغيل نسخة الآن
        </Button>} />

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        <Stat tid="stat-encryption" label="التشفير"
          v={d.encryption?.enabled ? "مُفعّل" : "غير مُفعّل"} ok={d.encryption?.enabled}
          sub={d.encryption?.algorithm} />
        <Stat tid="stat-schedule" label="الجدولة اليومية" v={d.schedule?.local_time}
          ok={d.schedule?.enabled} sub={d.schedule?.endpoint} />
        <Stat tid="stat-retention" label="سياسة الاحتفاظ" v={`${d.retention} نسخ`}
          sub={`حُذف بالسياسة: ${d.pruned_count}`} />
        <Stat tid="stat-restore" label="الاستعادة على القاعدة العاملة"
          v={d.restore_enabled ? "مسموحة (Test)" : "معطّلة"} danger={d.restore_enabled}
          sub={`البيئة: ${d.environment}`} />
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-5 mb-5" data-testid="guards-panel">
        <div className="flex items-center gap-2 font-head font-bold text-[#0A2540] text-sm mb-2">
          <ShieldCheck className="w-4 h-4 text-[#15803D]" /> حواجز الأمان
        </div>
        <div className="flex flex-wrap gap-2">
          {(d.restore_guards || []).map((g, i) => (
            <span key={i} className="text-[11px] bg-[#F0FDF4] text-[#15803D] border border-[#BBF7D0] rounded-full px-3 py-1"
              data-testid={`guard-${i}`}>{g}</span>
          ))}
        </div>
        <div className="text-[11px] text-muted-foreground mt-2">
          الاستعادة والترحيل ممنوعان منعًا قاطعًا على بيئة Live • آخر نسخة ناجحة: <b>{d.last_successful?.file || "—"}</b>
          {d.last_successful?.at ? ` • ${fmtDate(d.last_successful.at)}` : ""}
        </div>
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-5 mb-5" data-testid="drill-panel">
        <div className="flex items-center gap-2 font-head font-bold text-[#0A2540] text-sm mb-2">
          <FlaskConical className="w-4 h-4 text-[#D4AF37]" /> اختبار الاستعادة على قاعدة معزولة
        </div>
        <div className="text-[11px] text-muted-foreground mb-3">
          يفكّ التشفير ويستعيد النسخة إلى قاعدة مؤقتة منفصلة، يعدّ المجموعات والمستندات، ثم يحذف القاعدة المؤقتة.
          <b> قاعدة البيانات العاملة لا تُمَس إطلاقًا.</b>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <select className="h-9 rounded-md border border-input px-2 text-xs bg-white" data-testid="drill-file-select"
            value={drillFile} onChange={(e) => setDrillFile(e.target.value)}>
            <option value="">اختر ملف نسخة</option>
            {(d.files_on_disk || []).map((f) => (
              <option key={f.file} value={f.file}>{f.file} — {(f.size / 1048576).toFixed(2)} MB</option>
            ))}
          </select>
          <Button size="sm" variant="outline" data-testid="run-drill-btn" disabled={busy || !drillFile}
            onClick={() => act(async () => {
              const r = await api.post("/admin/backups/verify",
                { file: drillFile, reason: "اختبار استعادة على قاعدة مؤقتة" });
              toast.success(`نجح الاختبار: ${r.data.collections} مجموعة و${r.data.documents} مستند`);
            }, "تم اختبار الاستعادة")}>تشغيل الاختبار</Button>
        </div>
        <div className="mt-3 space-y-1.5">
          {(d.drills || []).length === 0 ? (
            <div className="text-[11px] text-muted-foreground" data-testid="drills-empty">لم يُجرَ اختبار استعادة بعد</div>
          ) : d.drills.map((x) => (
            <div key={x.id} className={`text-[11px] rounded-lg px-3 py-1.5 ${x.result === "success" ? "bg-[#F0FDF4] text-[#15803D]" : "bg-[#FEF2F2] text-[#B91C1C]"}`}
              data-testid={`drill-${x.id}`}>
              {fmtDate(x.at)} • {x.file} • {x.result === "success"
                ? `${x.collections} مجموعة / ${x.documents} مستند • ${x.decrypted ? "فُكّ التشفير" : "غير مشفّرة"}`
                : `فشل: ${(x.error || "").slice(0, 60)}`} • {x.by}
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto mb-5" data-testid="backups-table">
        <div className="px-5 py-3 font-head font-bold text-[#0A2540] text-sm flex items-center gap-2">
          <Database className="w-4 h-4 text-[#D4AF37]" /> سجل النسخ ({d.items.length})
        </div>
        <table className="w-full text-xs min-w-[760px]">
          <thead className="bg-[#F4F6F8] text-muted-foreground">
            <tr>{["التاريخ", "الملف", "الحجم", "مشفّرة", "النتيجة", "المنفّذ", "السبب"].map((h) => (
              <th key={h} className="text-right font-semibold px-3 py-2.5">{h}</th>))}</tr>
          </thead>
          <tbody>
            {d.items.length === 0 ? (
              <tr><td colSpan={7} className="text-center py-10 text-muted-foreground" data-testid="backups-empty">لا توجد نسخ بعد</td></tr>
            ) : d.items.map((b) => (
              <tr key={b.id} className="border-t" data-testid={`backup-${b.id}`}>
                <td className="px-3 py-2 whitespace-nowrap">{fmtDate(b.at)}</td>
                <td className="px-3 py-2 text-[10px] break-all">{b.file || "—"}{b.pruned ? " (محذوفة بالسياسة)" : ""}</td>
                <td className="px-3 py-2 tabular">{b.size ? `${(b.size / 1048576).toFixed(2)} MB` : "—"}</td>
                <td className="px-3 py-2">{b.encrypted ? "نعم" : "لا"}</td>
                <td className={`px-3 py-2 ${b.result === "success" ? "text-[#15803D]" : "text-[#B91C1C]"}`}>
                  {b.result === "success" ? "ناجحة" : `فاشلة: ${(b.error || "").slice(0, 40)}`}
                </td>
                <td className="px-3 py-2">{b.by}</td>
                <td className="px-3 py-2 max-w-[180px] truncate text-[10px]">{b.reason || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="backup-audit">
        <div className="font-head font-bold text-[#0A2540] text-sm mb-3">سجل التدقيق الخاص بالنسخ والاستعادة</div>
        <div className="space-y-1.5 max-h-64 overflow-y-auto">
          {audit.length === 0 ? <div className="text-[11px] text-muted-foreground">لا يوجد سجل</div> :
            audit.map((a, i) => (
              <div key={i} className="text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-1.5" data-testid={`backup-audit-${i}`}>
                <b>{a.action}</b> — {a.actor} • {fmtDate(a.at)}
                {a.reason ? <span className="text-muted-foreground"> • {a.reason}</span> : null}
              </div>
            ))}
        </div>
      </div>

      <Dialog open={confirmRun} onOpenChange={setConfirmRun}>
        <DialogContent dir="rtl" className="max-w-md" data-testid="run-backup-dialog">
          <DialogHeader><DialogTitle>تشغيل نسخة احتياطية الآن</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="text-xs bg-[#F4F6F8] rounded-lg px-3 py-2">
              ستُنشأ نسخة كاملة مشفّرة من قاعدة البيانات، وتُحذف أقدم نسخة تلقائيًا عند تجاوز {d.retention} نسخ.
            </div>
            <div><Label className="text-xs">السبب (إلزامي — يُسجَّل في سجل التدقيق)</Label>
              <Textarea rows={2} className="text-xs" value={runReason} data-testid="backup-reason"
                onChange={(e) => setRunReason(e.target.value)} /></div>
            <Button className="w-full bg-[#0A2540] hover:bg-[#061A2E]" data-testid="confirm-run-backup"
              disabled={busy || runReason.trim().length < 3}
              onClick={() => act(async () => {
                await api.post("/admin/backups/run", { reason: runReason.trim() });
                setConfirmRun(false);
              }, "تم إنشاء النسخة")}>تأكيد وتشغيل</Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

const Stat = ({ label, v, sub, ok, danger, tid }) => (
  <div className="bg-white rounded-2xl border p-4 card-shadow" data-testid={tid}>
    <div className={`text-lg font-bold ${danger ? "text-[#B91C1C]" : ok ? "text-[#15803D]" : "text-[#0A2540]"}`}>{v}</div>
    <div className="text-[11px] text-muted-foreground mt-1">{label}</div>
    {sub ? <div className="text-[10px] text-muted-foreground mt-0.5 break-all">{sub}</div> : null}
  </div>
);
