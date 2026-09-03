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
import { Database, ShieldCheck, PlayCircle, FlaskConical, Upload } from "lucide-react";

const SRC_AR = { manual: "يدوية", cron: "مجدولة", uploaded: "مستوردة" };
const DEST_AR = {
  server: "سيرفر التطبيق", download: "تنزيل للمستخدم", cloud: "تخزين سحابي",
  server_and_download: "السيرفر + تنزيل",
};

export default function AdminBackups() {
  const [d, setD] = useState(null);
  const [store, setStore] = useState(null);
  const [audit, setAudit] = useState([]);
  const [drillFile, setDrillFile] = useState("");
  const [runReason, setRunReason] = useState("");
  const [dest, setDest] = useState("server_and_download");
  const [confirmRun, setConfirmRun] = useState(false);
  const [upReason, setUpReason] = useState("");
  const [upFile, setUpFile] = useState(null);
  const [upRes, setUpRes] = useState(null);
  const [check, setCheck] = useState(null);
  const [restore, setRestore] = useState({ file: "", confirm_phrase: "", reason: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/admin/backups").then((r) => setD(r.data));
    api.get("/admin/backups/storage").then((r) => setStore(r.data));
    api.get("/admin/audit?limit=50&entity=backup").then((r) => setAudit(r.data.items || []));
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); if (ok) toast.success(ok); load(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  // Streams the encrypted archive through the browser download dialog, so the authorized
  // user picks any folder, disk or external drive on ANY computer they are signed in from.
  const downloadFile = async (filename) => {
    setBusy(true);
    try {
      const r = await api.get(`/admin/backups/${filename}/download`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([r.data], { type: "application/octet-stream" }));
      const a = document.createElement("a");
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("تم تنزيل النسخة بنجاح — اختر مكان الحفظ من نافذة المتصفح");
      load();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
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

      <div className="bg-white rounded-2xl border card-shadow p-5 mb-5" data-testid="storage-panel">
        <div className="font-head font-bold text-[#0A2540] text-sm mb-2">وجهات التخزين المتاحة</div>
        <div className="grid sm:grid-cols-2 gap-2">
          {(store?.destinations || []).map((x) => (
            <div key={x.key} className={`rounded-xl border px-3 py-2 text-[11px] ${x.available ? "bg-[#F0FDF4] border-[#BBF7D0]" : "bg-[#F4F6F8] border-[#E5E7EB] opacity-70"}`}
              data-testid={`dest-info-${x.key}`}>
              <div className="font-bold text-[#0A2540]">{x.ar} {x.available ? "" : "— غير مُهيَّأة"}</div>
              <div className="text-muted-foreground mt-0.5">{x.note}</div>
            </div>
          ))}
        </div>
        {store && !store.cloud.configured && (
          <div className="text-[10px] text-muted-foreground mt-2" data-testid="cloud-req">
            لتفعيل التخزين السحابي أضيفوا المتغيّرات: {store.cloud.required_env.join(" • ")}
          </div>
        )}
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-5 mb-5" data-testid="upload-panel">
        <div className="flex items-center gap-2 font-head font-bold text-[#0A2540] text-sm mb-2">
          <Upload className="w-4 h-4 text-[#D4AF37]" /> استيراد نسخة احتياطية مشفّرة
        </div>
        <div className="text-[11px] text-muted-foreground mb-3">
          يُتحقَّق من التشفير وسلامة الملف <b>قبل قبوله</b>، وأي ملف يفشل التحقق يُرفض ويُحذف فورًا ولا يُخزَّن.
          الامتدادات المسموحة: <code dir="ltr">.archive.gz</code> أو <code dir="ltr">.archive.gz.enc</code>
        </div>
        <div className="grid sm:grid-cols-[1fr_1fr_auto] gap-2 items-end">
          <div><Label className="text-xs">ملف النسخة</Label>
            <Input type="file" className="h-9 text-xs" data-testid="upload-file"
              onChange={(e) => setUpFile(e.target.files?.[0] || null)} /></div>
          <div><Label className="text-xs">السبب (إلزامي)</Label>
            <Input className="h-9 text-xs" value={upReason} data-testid="upload-reason"
              onChange={(e) => setUpReason(e.target.value)} /></div>
          <Button size="sm" className="bg-[#0A2540] hover:bg-[#061A2E]" data-testid="upload-btn"
            disabled={busy || !upFile || upReason.trim().length < 3}
            onClick={() => act(async () => {
              const fd = new FormData();
              fd.append("file", upFile);
              fd.append("reason", upReason.trim());
              setUpRes(null);
              const r = await api.post("/admin/backups/upload", fd,
                { headers: { "Content-Type": "multipart/form-data" } });
              setUpRes(r.data);
              toast.success(`تم استيراد النسخة بنجاح — التحقق: سليمة (${(r.data.size / 1048576).toFixed(2)} MB)`);
              setUpFile(null); setUpReason("");
            })}>استيراد وتحقق</Button>
        </div>
        {upRes && (
          <div className="mt-3 rounded-xl border border-[#BBF7D0] bg-[#F0FDF4] px-3 py-2 text-[11px] text-[#15803D] space-y-1"
            data-testid="upload-summary">
            <div className="font-bold">تم قبول الملف وتخزينه بعد التحقق الكامل</div>
            <div data-testid="upload-summary-file">اسم الملف: <b dir="ltr">{upRes.file}</b></div>
            <div data-testid="upload-summary-size">الحجم: <b>{(upRes.size / 1048576).toFixed(2)} ميجابايت</b></div>
            <div data-testid="upload-summary-enc">
              التشفير: <b>{upRes.encrypted ? "مشفّر AES-256-CBC + PBKDF2 (فُكّ التشفير بنجاح)" : "غير مشفّر"}</b>
            </div>
            <div data-testid="upload-summary-sha" className="break-all">
              بصمة التحقق SHA-256: <b dir="ltr">{upRes.sha256}</b>
            </div>
            <div data-testid="upload-summary-result">
              نتيجة التحقق: <b>{upRes.integrity === "valid" ? "سليمة (أرشيف mongodump صالح)" : upRes.integrity}</b> •
              التخزين: <b>{upRes.storage === "gridfs" ? "GridFS داخل قاعدة البيانات" : upRes.storage}</b>
            </div>
          </div>
        )}
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
              <option key={f.file} value={f.file}>{`${f.file} — ${(f.size / 1048576).toFixed(2)} MB`}</option>
            ))}
            {(d.files_imported || []).map((f) => (
              <option key={f.file} value={f.file}>{`${f.file} — مستوردة (${(f.size / 1048576).toFixed(2)} MB)`}</option>
            ))}
          </select>
          <Button size="sm" variant="outline" data-testid="run-drill-btn" disabled={busy || !drillFile}
            onClick={() => act(async () => {
              const r = await api.post("/admin/backups/verify",
                { file: drillFile, reason: "اختبار استعادة على قاعدة مؤقتة" });
              toast.success(`تم اختبار الاستعادة بنجاح على قاعدة معزولة: ${r.data.collections} مجموعة و${r.data.documents} مستند`);
            })}>تشغيل الاختبار</Button>
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

      <div className="bg-white rounded-2xl border card-shadow p-5 mb-5" data-testid="restore-panel">
        <div className="font-head font-bold text-[#0A2540] text-sm mb-2">
          الاستعادة إلى قاعدة البيانات العاملة
        </div>
        <div className="text-[11px] bg-[#FEF2F2] border border-[#FECACA] text-[#B91C1C] rounded-lg px-3 py-2 mb-3">
          عملية شديدة الخطورة: تستبدل بيانات العمل الحالية. محميّة بأربعة حواجز
          (تفعيل <code dir="ltr">ALLOW_RESTORE</code> + عبارة تأكيد حرفية + سبب إلزامي + رفض قاطع على Live).
          {!d.restore_enabled && " الاستعادة معطّلة حاليًا في هذه البيئة، لذلك الزر غير مُتاح."}
        </div>
        <div className="grid sm:grid-cols-[1fr_1fr_auto] gap-2 items-end">
          <div><Label className="text-xs">ملف النسخة</Label>
            <select className="w-full h-9 rounded-md border border-input px-2 text-xs bg-white"
              data-testid="restore-file-select" value={restore.file} disabled={!d.restore_enabled}
              onChange={(e) => setRestore({ ...restore, file: e.target.value })}>
              <option value="">اختر ملف نسخة</option>
              {(d.files_on_disk || []).map((f) => <option key={f.file} value={f.file}>{f.file}</option>)}
            </select></div>
          <div><Label className="text-xs">اكتب: أؤكد الاستعادة</Label>
            <Input className="h-9 text-xs" value={restore.confirm_phrase} disabled={!d.restore_enabled}
              data-testid="restore-confirm" onChange={(e) => setRestore({ ...restore, confirm_phrase: e.target.value })} /></div>
          <Button size="sm" className="bg-[#B91C1C] hover:bg-[#991B1B]" data-testid="restore-btn"
            disabled={busy || !d.restore_enabled || !restore.file
              || restore.confirm_phrase.trim() !== "أؤكد الاستعادة" || restore.reason.trim().length < 3}
            onClick={() => {
              if (!window.confirm("تأكيد نهائي: سيتم استبدال بيانات قاعدة العمل بالكامل. هل تريد المتابعة؟")) return;
              act(async () => {
                await api.post("/admin/backups/restore", restore);
                toast.success("تمت الاستعادة إلى قاعدة العمل");
                setRestore({ file: "", confirm_phrase: "", reason: "" });
              });
            }}>استعادة</Button>
          <div className="sm:col-span-3"><Label className="text-xs">السبب (إلزامي)</Label>
            <Input className="h-9 text-xs" value={restore.reason} disabled={!d.restore_enabled}
              data-testid="restore-reason" onChange={(e) => setRestore({ ...restore, reason: e.target.value })} /></div>
        </div>
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto mb-5" data-testid="backups-table">
        <div className="px-5 py-3 font-head font-bold text-[#0A2540] text-sm flex items-center gap-2">
          <Database className="w-4 h-4 text-[#D4AF37]" /> سجل النسخ ({d.items.length})
        </div>
        <table className="w-full text-xs min-w-[1000px]">
          <thead className="bg-[#F4F6F8] text-muted-foreground">
            <tr>{["التاريخ", "الملف", "الحجم", "المصدر", "الوجهة", "مشفّرة", "السلامة", "النتيجة", "المنفّذ", "السبب", ""].map((h) => (
              <th key={h} className="text-right font-semibold px-3 py-2.5">{h}</th>))}</tr>
          </thead>
          <tbody>
            {d.items.length === 0 ? (
              <tr><td colSpan={11} className="text-center py-10 text-muted-foreground" data-testid="backups-empty">لا توجد نسخ بعد</td></tr>
            ) : d.items.map((b) => (
              <tr key={b.id} className="border-t" data-testid={`backup-${b.id}`}>
                <td className="px-3 py-2 whitespace-nowrap">{fmtDate(b.at)}</td>
                <td className="px-3 py-2 text-[10px] break-all">{b.file || "—"}{b.pruned ? " (محذوفة بالسياسة)" : ""}</td>
                <td className="px-3 py-2 tabular">{b.size ? `${(b.size / 1048576).toFixed(2)} MB` : "—"}</td>
                <td className="px-3 py-2">{SRC_AR[b.source] || "يدوية"}</td>
                <td className="px-3 py-2">{DEST_AR[b.destination] || (b.storage === "gridfs" ? "مستوردة (GridFS)" : "السيرفر")}</td>
                <td className="px-3 py-2">{b.encrypted ? "نعم" : "لا"}</td>
                <td className={`px-3 py-2 ${b.integrity === "valid" ? "text-[#15803D]" : b.integrity === "invalid" ? "text-[#B91C1C]" : ""}`}>
                  {b.integrity === "valid" ? "سليمة" : b.integrity === "invalid" ? "تالفة" : "لم تُفحص"}
                </td>
                <td className={`px-3 py-2 ${b.result === "success" ? "text-[#15803D]" : "text-[#B91C1C]"}`}>
                  {b.result === "success" ? "ناجحة" : `فاشلة: ${(b.error || "").slice(0, 40)}`}
                </td>
                <td className="px-3 py-2">{b.by}</td>
                <td className="px-3 py-2 max-w-[160px] truncate text-[10px]">{b.reason || "—"}</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  {b.file && !b.pruned && (
                    <>
                      <button className="text-[#0A2540] underline font-semibold ml-2" disabled={busy}
                        data-testid={`download-${b.id}`} onClick={() => downloadFile(b.file)}>تنزيل</button>
                      <button className="text-[#0A2540] underline" disabled={busy}
                        data-testid={`validate-${b.id}`}
                        onClick={() => act(async () => {
                          const r = await api.post("/admin/backups/validate", { file: b.file });
                          setCheck(r.data);
                          r.data.valid
                            ? toast.success("تم التحقق من النسخة بنجاح — التشفير والسلامة سليمان")
                            : toast.error(`فشل التحقق: ${r.data.reason}`);
                        })}>تحقق</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {check && (
        <div className={`rounded-2xl border p-4 mb-5 text-[11px] ${check.valid ? "bg-[#F0FDF4] border-[#BBF7D0] text-[#15803D]" : "bg-[#FEF2F2] border-[#FECACA] text-[#B91C1C]"}`}
          data-testid="validation-result">
          <b>نتيجة التحقق:</b> {check.file} — {check.valid ? "سليمة" : `تالفة (${check.reason})`} •
          مشفّرة: {check.encrypted ? "نعم" : "لا"} • أرشيف مضغوط: {check.gzip_archive ? "نعم" : "لا"} •
          الحجم: {check.size ? (check.size / 1048576).toFixed(2) : 0} MB
          {check.sha256 ? <div className="mt-1 break-all" dir="ltr">SHA-256: {check.sha256}</div> : null}
        </div>
      )}

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
            <div>
              <Label className="text-xs">وجهة النسخة (إلزامي)</Label>
              <div className="space-y-1.5 mt-1">
                {(store?.destinations || []).map((x) => (
                  <label key={x.key} className={`flex items-start gap-2 text-[11px] rounded-lg px-3 py-2 border cursor-pointer ${dest === x.key ? "bg-[#F0FDF4] border-[#BBF7D0]" : "bg-[#F4F6F8] border-transparent"} ${x.available ? "" : "opacity-50 cursor-not-allowed"}`}
                    data-testid={`dest-opt-${x.key}`}>
                    <input type="radio" name="dest" value={x.key} checked={dest === x.key}
                      disabled={!x.available} onChange={() => setDest(x.key)} className="mt-0.5" />
                    <span className="block">
                      <b className="text-[#0A2540]">{x.ar}</b>
                      <span className="block text-muted-foreground">{x.note}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
            <div className="text-[11px] bg-[#FEFCE8] border border-[#FEF08A] text-[#A16207] rounded-lg px-3 py-2" data-testid="dest-selected">
              الوجهة المختارة: <b>{(store?.destinations || []).find((x) => x.key === dest)?.ar || "—"}</b> — تُسجَّل في سجل التدقيق مع العملية.
            </div>
            <div><Label className="text-xs">السبب (إلزامي — يُسجَّل في سجل التدقيق)</Label>
              <Textarea rows={2} className="text-xs" value={runReason} data-testid="backup-reason"
                onChange={(e) => setRunReason(e.target.value)} /></div>
            <Button className="w-full bg-[#0A2540] hover:bg-[#061A2E]" data-testid="confirm-run-backup"
              disabled={busy || runReason.trim().length < 3}
              onClick={() => act(async () => {
                const r = await api.post("/admin/backups/run",
                  { reason: runReason.trim(), destination: dest });
                toast.success(`تم إنشاء النسخة بنجاح — ${r.data.destination_label}`);
                setConfirmRun(false);
                if (r.data.download_url) await downloadFile(r.data.file);
              })}>تأكيد وتشغيل</Button>
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
