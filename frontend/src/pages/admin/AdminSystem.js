import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Settings2, ShieldAlert, Database, Activity, Search } from "lucide-react";

const TABS = [["settings", "الإعدادات و Feature Flags"], ["health", "صحة الخدمات"],
["audit", "سجل التدقيق"], ["anomalies", "عمليات غير طبيعية"], ["backup", "النسخ الاحتياطي"]];

export default function AdminSystem() {
  const [tab, setTab] = useState("settings");
  const [st, setSt] = useState(null);
  const [health, setHealth] = useState(null);
  const [audit, setAudit] = useState({ items: [] });
  const [anom, setAnom] = useState({ items: [] });
  const [backups, setBackups] = useState({ items: [] });
  const [q, setQ] = useState("");
  const [drillFile, setDrillFile] = useState("");
  const [tdr, setTdr] = useState(null);
  const [draft, setDraft] = useState({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/admin/settings").then((r) => { setSt(r.data.settings); setDraft(r.data.settings); });
    api.get("/admin/system/health").then((r) => setHealth(r.data));
    api.get(`/admin/audit?limit=100${q ? `&q=${encodeURIComponent(q)}` : ""}`).then((r) => setAudit(r.data));
    api.get("/admin/anomalies").then((r) => setAnom(r.data));
    api.get("/admin/backups").then((r) => setBackups(r.data));
  }, [q]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); load(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const saveSection = (section) => act(() => api.post("/admin/settings", {
    section, values: draft[section], reason: `تحديث إعدادات: ${section}`,
  }), "تم حفظ الإعدادات");

  if (!st) return <div className="text-center py-20 text-muted-foreground" data-testid="system-loading">جارٍ التحميل...</div>;

  return (
    <>
      <PageHeader title="إعدادات النظام والرقابة" subtitle="مركز الإعدادات وFeature Flags، صحة الخدمات، سجل التدقيق غير القابل للتعديل، كشف العمليات غير الطبيعية، والنسخ الاحتياطي" />

      <div className="flex flex-wrap gap-2 mb-5" data-testid="system-tabs">
        {TABS.map(([v, l]) => (
          <button key={v} onClick={() => setTab(v)} data-testid={`systab-${v}`}
            className={`px-3 h-9 rounded-lg text-xs font-semibold border ${tab === v ? "bg-[#0A2540] text-white border-[#0A2540]" : "bg-white text-[#0A2540] hover:bg-[#F4F6F8]"}`}>{l}</button>
        ))}
      </div>

      {tab === "settings" && (
        <div className="space-y-5">
          <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="flags-panel">
            <div className="flex items-center gap-2 font-head font-bold text-[#0A2540] text-sm mb-3">
              <Settings2 className="w-4 h-4 text-[#D4AF37]" /> Feature Flags
            </div>
            <div className="grid sm:grid-cols-3 gap-2">
              {Object.entries(draft.feature_flags || {}).map(([k, v]) => (
                <label key={k} className="text-xs bg-[#F4F6F8] rounded-lg px-3 py-2 flex items-center gap-2" data-testid={`flag-${k}`}>
                  <input type="checkbox" checked={!!v} onChange={(e) => setDraft({
                    ...draft, feature_flags: { ...draft.feature_flags, [k]: e.target.checked } })} />
                  {k}
                </label>
              ))}
            </div>
            <Button size="sm" className="mt-3 bg-[#0A2540] hover:bg-[#061A2E]" data-testid="save-flags-btn"
              disabled={busy} onClick={() => saveSection("feature_flags")}>حفظ</Button>
          </div>

          {["currencies", "documents", "credit", "reasons", "locale", "numbering", "integrations", "order_flow", "funds_release"].map((sec) => (
            <div key={sec} className="bg-white rounded-2xl border card-shadow p-5" data-testid={`section-${sec}`}>
              <div className="font-head font-bold text-[#0A2540] text-sm mb-2">{sec}</div>
              <Textarea rows={4} className="text-[11px] font-mono" data-testid={`json-${sec}`}
                defaultValue={JSON.stringify(draft[sec], null, 2)}
                onChange={(e) => { try { setDraft({ ...draft, [sec]: JSON.parse(e.target.value) }); } catch { /* invalid json while typing */ } }} />
              <Button size="sm" className="mt-2 bg-[#0A2540] hover:bg-[#061A2E]" data-testid={`save-${sec}`}
                disabled={busy} onClick={() => saveSection(sec)}>حفظ</Button>
            </div>
          ))}
        </div>
      )}

      {tab === "health" && health && (
        <div className="space-y-5">
          <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="health-panel">
            <div className="flex items-center gap-2 font-head font-bold text-[#0A2540] text-sm mb-3">
              <Activity className="w-4 h-4 text-[#D4AF37]" /> حالة الخدمات
            </div>
            <div className="space-y-2">
              {health.checks.map((c, i) => (
                <div key={i} className={`text-xs rounded-lg px-3 py-2 flex justify-between border ${c.status === "ok" ? "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]" : c.status === "warn" ? "bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]" : "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]"}`}
                  data-testid={`health-${i}`}>
                  <span>{c.service}</span><span>{c.detail || c.error || c.status}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-white rounded-2xl border card-shadow p-5">
            <div className="font-head font-bold text-[#0A2540] text-sm mb-3">أحجام البيانات</div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
              {Object.entries(health.collections).map(([k, v]) => (
                <div key={k} className="bg-[#F4F6F8] rounded-lg px-3 py-2" data-testid={`coll-${k}`}>
                  <div className="text-[10px] text-muted-foreground">{k}</div>
                  <div className="tabular font-bold text-[#0A2540]">{v}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === "audit" && (
        <>
          <div className="bg-white rounded-2xl border card-shadow p-4 mb-3">
            <div className="relative">
              <Search className="w-4 h-4 absolute top-2.5 right-3 text-muted-foreground" />
              <input value={q} onChange={(e) => setQ(e.target.value)} data-testid="audit-search"
                placeholder="ابحث في سجل التدقيق (منفّذ، إجراء، سبب)"
                className="w-full h-9 rounded-md border border-input pr-9 pl-3 text-xs" />
            </div>
          </div>
          <div className="bg-white rounded-2xl border card-shadow overflow-x-auto" data-testid="audit-table">
            <table className="w-full text-xs min-w-[860px]">
              <thead className="bg-[#F4F6F8] text-muted-foreground">
                <tr>{["التاريخ", "المصدر", "الكيان", "الإجراء", "المنفّذ", "السبب", "قبل ← بعد"].map((h) => (
                  <th key={h} className="text-right font-semibold px-3 py-2.5">{h}</th>))}</tr>
              </thead>
              <tbody>
                {audit.items.length === 0 ? (
                  <tr><td colSpan={7} className="text-center py-10 text-muted-foreground" data-testid="audit-empty">لا يوجد سجل</td></tr>
                ) : audit.items.map((a, i) => (
                  <tr key={i} className="border-t" data-testid={`audit-row-${i}`}>
                    <td className="px-3 py-2 whitespace-nowrap">{fmtDate(a.at)}</td>
                    <td className="px-3 py-2 text-[10px]">{a.source}</td>
                    <td className="px-3 py-2">{a.entity}</td>
                    <td className="px-3 py-2 font-semibold text-[#0A2540]">{a.action}</td>
                    <td className="px-3 py-2">{a.actor || "—"}</td>
                    <td className="px-3 py-2 max-w-[160px] truncate">{a.reason || "—"}</td>
                    <td className="px-3 py-2 max-w-[220px] truncate text-[10px] text-muted-foreground">
                      {a.before ? JSON.stringify(a.before) : "—"} ← {a.after ? JSON.stringify(a.after) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === "anomalies" && (
        <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="anomalies-panel">
          <div className="flex items-center gap-2 font-head font-bold text-[#0A2540] text-sm mb-3">
            <ShieldAlert className="w-4 h-4 text-[#B91C1C]" /> عمليات غير طبيعية ({anom.total || 0})
          </div>
          <div className="space-y-2">
            {anom.items.length === 0 ? <div className="text-xs text-muted-foreground">لا توجد ملاحظات</div> :
              anom.items.map((a, i) => (
                <div key={i} className={`text-xs rounded-lg px-3 py-2 border ${a.level === "critical" ? "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" : a.level === "warning" ? "bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]" : "bg-[#F4F6F8]"}`}
                  data-testid={`anomaly-${i}`}>{a.message}</div>
              ))}
          </div>
        </div>
      )}

      {tab === "backup" && (
        <div className="space-y-5">
          <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="backup-panel">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 font-head font-bold text-[#0A2540] text-sm">
                  <Database className="w-4 h-4 text-[#D4AF37]" /> نسخ قاعدة البيانات
                </div>
                <div className="text-[11px] text-muted-foreground mt-1">
                  التشفير: {backups.encrypted ? "مُفعّل (BACKUP_PASSPHRASE)" : "غير مُفعّل — أضف BACKUP_PASSPHRASE"} •
                  الاحتفاظ بآخر {backups.retention} نسخ • الاستعادة: {backups.restore_enabled ? "مسموحة (Test)" : "معطّلة"}
                </div>
              </div>
              <Button size="sm" className="bg-[#0A2540] hover:bg-[#061A2E]" data-testid="run-backup-btn" disabled={busy}
                onClick={() => act(() => api.post("/admin/backups/run", { reason: "نسخ احتياطي يدوي من لوحة الإدارة" }), "تم إنشاء النسخة")}>
                تشغيل نسخة الآن
              </Button>
            </div>
            <div className="mt-3 text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-2" data-testid="backup-env">
              البيئة: <b>{backups.environment}</b> • ملفات على القرص: <b>{(backups.files_on_disk || []).length}</b> •
              الاستعادة والترحيل ممنوعان تمامًا على Live • جدولة يومية 01:00 بتوقيت الرياض
            </div>
          </div>

          <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="testdata-panel">
            <div className="font-head font-bold text-[#0A2540] text-sm mb-2">تصنيف بيانات الاختبار (بدون أي حذف)</div>
            {!tdr ? (
              <Button size="sm" variant="outline" data-testid="testdata-btn"
                onClick={() => act(async () => { const r = await api.get("/admin/system/test-data-report"); setTdr(r.data); }, "تم إنشاء التقرير")}>
                إنشاء التقرير
              </Button>
            ) : (
              <div className="space-y-3">
                <div className="text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-2" data-testid="testdata-db">
                  القاعدة: <b>{tdr.database}</b> • البيئة: <b>{tdr.environment}</b><br />{tdr.isolation_note}
                </div>
                <table className="w-full text-[11px]">
                  <thead className="bg-[#F4F6F8] text-muted-foreground">
                    <tr>{["المجموعة", "الإجمالي", "بيانات QA", "بيانات حقيقية", "قاعدة التصنيف"].map((h) => (
                      <th key={h} className="text-right font-semibold px-2 py-2">{h}</th>))}</tr>
                  </thead>
                  <tbody>
                    {tdr.rows.map((r) => (
                      <tr key={r.collection} className="border-t" data-testid={`testdata-${r.collection}`}>
                        <td className="px-2 py-1.5 font-semibold">{r.collection}</td>
                        <td className="px-2 py-1.5 tabular">{r.total}</td>
                        <td className="px-2 py-1.5 tabular text-[#A16207]">{r.qa}</td>
                        <td className="px-2 py-1.5 tabular text-[#15803D]">{r.real}</td>
                        <td className="px-2 py-1.5 text-[10px] text-muted-foreground">{r.rule}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="text-[11px] bg-[#FEFCE8] border border-[#FEF08A] text-[#A16207] rounded-lg px-3 py-2" data-testid="testdata-verdict">
                  {tdr.repetition_verdict}<br />{tdr.deletion_policy}
                </div>
              </div>
            )}
          </div>

          <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="drill-panel">
            <div className="font-head font-bold text-[#0A2540] text-sm mb-2">اختبار الاستعادة (Restore Drill)</div>
            <div className="text-[11px] text-muted-foreground mb-3">
              يفكّ التشفير ويستعيد النسخة إلى قاعدة مؤقتة منفصلة، يعدّ المجموعات والمستندات، ثم يحذفها.
              <b> قاعدة البيانات العاملة لا تُمَس إطلاقًا.</b>
            </div>
            <div className="flex flex-wrap gap-2 items-center">
              <select className="h-9 rounded-md border border-input px-2 text-xs bg-white" data-testid="drill-file-select"
                value={drillFile} onChange={(e) => setDrillFile(e.target.value)}>
                <option value="">اختر ملف نسخة</option>
                {(backups.files_on_disk || []).map((f) => (
                  <option key={f.file} value={f.file}>{f.file} — {(f.size / 1048576).toFixed(2)} MB</option>
                ))}
              </select>
              <Button size="sm" variant="outline" data-testid="run-drill-btn" disabled={busy || !drillFile}
                onClick={() => act(async () => {
                  const r = await api.post("/admin/backups/verify",
                    { file: drillFile, reason: "اختبار استعادة على قاعدة مؤقتة" });
                  toast.success(`نجح الاختبار: ${r.data.collections} مجموعة و${r.data.documents} مستند`);
                }, "تم اختبار الاستعادة")}>تشغيل اختبار الاستعادة</Button>
            </div>
            <div className="mt-3 space-y-1.5">
              {(backups.drills || []).length === 0 ? (
                <div className="text-[11px] text-muted-foreground" data-testid="drills-empty">لم يُجرَ اختبار استعادة بعد</div>
              ) : backups.drills.map((d) => (
                <div key={d.id} className={`text-[11px] rounded-lg px-3 py-1.5 ${d.result === "success" ? "bg-[#F0FDF4] text-[#15803D]" : "bg-[#FEF2F2] text-[#B91C1C]"}`}
                  data-testid={`drill-${d.id}`}>
                  {fmtDate(d.at)} • {d.file} • {d.result === "success"
                    ? `${d.collections} مجموعة / ${d.documents} مستند • ${d.decrypted ? "فُكّ التشفير" : "غير مشفّرة"}`
                    : `فشل: ${(d.error || "").slice(0, 60)}`} • {d.by}
                </div>
              ))}
            </div>
          </div>
          <div className="bg-white rounded-2xl border card-shadow overflow-x-auto" data-testid="backups-table">
            <table className="w-full text-xs min-w-[700px]">
              <thead className="bg-[#F4F6F8] text-muted-foreground">
                <tr>{["التاريخ", "الملف", "الحجم", "مشفّرة", "النتيجة", "المنفّذ"].map((h) => (
                  <th key={h} className="text-right font-semibold px-3 py-2.5">{h}</th>))}</tr>
              </thead>
              <tbody>
                {backups.items.length === 0 ? (
                  <tr><td colSpan={6} className="text-center py-10 text-muted-foreground" data-testid="backups-empty">لا توجد نسخ بعد</td></tr>
                ) : backups.items.map((b) => (
                  <tr key={b.id} className="border-t" data-testid={`backup-${b.id}`}>
                    <td className="px-3 py-2 whitespace-nowrap">{fmtDate(b.at)}</td>
                    <td className="px-3 py-2 text-[10px] break-all">{b.file || "—"}{b.pruned ? " (محذوفة بالسياسة)" : ""}</td>
                    <td className="px-3 py-2 tabular">{b.size ? `${(b.size / 1048576).toFixed(2)} MB` : "—"}</td>
                    <td className="px-3 py-2">{b.encrypted ? "نعم" : "لا"}</td>
                    <td className={`px-3 py-2 ${b.result === "success" ? "text-[#15803D]" : "text-[#B91C1C]"}`}>
                      {b.result === "success" ? "ناجحة" : `فاشلة: ${(b.error || "").slice(0, 40)}`}
                    </td>
                    <td className="px-3 py-2">{b.by}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
