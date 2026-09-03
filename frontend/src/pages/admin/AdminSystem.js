import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { fmtDate, ar } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Settings2, ShieldAlert, Activity, Search } from "lucide-react";

const TABS = [["settings", "الإعدادات و Feature Flags"], ["health", "صحة الخدمات"],
["audit", "سجل التدقيق"], ["anomalies", "عمليات غير طبيعية"], ["testdata", "تصنيف بيانات الاختبار"]];

export default function AdminSystem() {
  const [tab, setTab] = useState("settings");
  const [st, setSt] = useState(null);
  const [health, setHealth] = useState(null);
  const [audit, setAudit] = useState({ items: [] });
  const [anom, setAnom] = useState({ items: [] });
  const [q, setQ] = useState("");
  const [tdr, setTdr] = useState(null);
  const [draft, setDraft] = useState({});
  const [schema, setSchema] = useState(null);
  const [tech, setTech] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/admin/settings").then((r) => { setSt(r.data.settings); setDraft(r.data.settings); });
    api.get("/admin/settings/schema").then((r) => setSchema(r.data)).catch(() => setSchema(null));
    api.get("/admin/system/health").then((r) => setHealth(r.data));
    api.get(`/admin/audit?limit=100${q ? `&q=${encodeURIComponent(q)}` : ""}`).then((r) => setAudit(r.data));
    api.get("/admin/anomalies").then((r) => setAnom(r.data));
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
      <PageHeader title="إعدادات النظام والرقابة" subtitle="مركز الإعدادات وFeature Flags، صحة الخدمات، سجل التدقيق غير القابل للتعديل، وكشف العمليات غير الطبيعية — النسخ الاحتياطي في قسمه المستقل" />

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
              <Settings2 className="w-4 h-4 text-[#D4AF37]" /> وحدات النظام (تشغيل/إيقاف)
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {Object.entries(draft.feature_flags || {}).map(([k, v]) => {
                const meta = (schema?.flags || {})[k] || [k, ""];
                return (
                  <label key={k} className="text-xs bg-[#F4F6F8] rounded-lg px-3 py-2 flex items-start gap-2 cursor-pointer"
                    data-testid={`flag-${k}`}>
                    <input type="checkbox" className="mt-0.5" checked={!!v} onChange={(e) => setDraft({
                      ...draft, feature_flags: { ...draft.feature_flags, [k]: e.target.checked } })} />
                    <span>
                      <span className="font-semibold text-[#0A2540]">{meta[0]}</span>
                      {meta[1] && <span className="block text-[10px] text-muted-foreground">{meta[1]}</span>}
                    </span>
                  </label>
                );
              })}
            </div>
            <Button size="sm" className="mt-3 bg-[#0A2540] hover:bg-[#061A2E]" data-testid="save-flags-btn"
              disabled={busy} onClick={() => saveSection("feature_flags")}>
              {busy ? "جارٍ الحفظ..." : "حفظ الوحدات"}
            </Button>
            <div className="text-[10px] text-muted-foreground mt-2">
              إيقاف الوحدة يخفيها من الواجهة، والحماية الفعلية للعمليات الحساسة تبقى على مستوى الصلاحيات في الخادم.
            </div>
          </div>

          {Object.entries(schema?.sections || {}).map(([sec, meta]) => (
            <div key={sec} className="bg-white rounded-2xl border card-shadow p-5" data-testid={`section-${sec}`}>
              <div className="font-head font-bold text-[#0A2540] text-sm">{meta.label}</div>
              <div className="text-[11px] text-muted-foreground mb-3">{meta.desc}</div>
              <div className="grid sm:grid-cols-2 gap-3">
                {meta.fields.map((f) => (
                  <SettingField key={f.key} f={f} sec={sec} draft={draft} setDraft={setDraft} />
                ))}
              </div>
              {meta.note && (
                <div className="text-[10px] text-[#A16207] bg-[#FEFCE8] border border-[#FEF08A] rounded-lg px-3 py-2 mt-3">
                  {meta.note}
                </div>
              )}
              <Button size="sm" className="mt-3 bg-[#0A2540] hover:bg-[#061A2E]" data-testid={`save-${sec}`}
                disabled={busy} onClick={() => saveSection(sec)}>
                {busy ? "جارٍ الحفظ..." : "حفظ"}
              </Button>
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
                    <td className="px-3 py-2 text-[10px]">{ar(a.source)}</td>
                    <td className="px-3 py-2">{a.entity_label || ar(a.entity)}</td>
                    <td className="px-3 py-2 font-semibold text-[#0A2540]">{a.action_label || ar(a.action)}</td>
                    <td className="px-3 py-2">{a.actor || "—"}</td>
                    <td className="px-3 py-2 max-w-[160px] truncate">{a.reason || "—"}</td>
                    <td className="px-3 py-2 max-w-[260px] text-[10px] text-muted-foreground">
                      <span className="block truncate">{a.before_text || "—"}</span>
                      <span className="block truncate">← {a.after_text || "—"}</span>
                      <button className="underline text-[#0A2540]" data-testid={`audit-tech-${i}`}
                        onClick={() => setTech(a)}>عرض التفاصيل التقنية</button>
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

      {tab === "testdata" && (
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
      )}

      {tech && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
          onClick={() => setTech(null)} data-testid="audit-tech-dialog">
          <div className="bg-white rounded-2xl p-5 max-w-lg w-full max-h-[80vh] overflow-y-auto" dir="rtl"
            onClick={(e) => e.stopPropagation()}>
            <div className="font-head font-bold text-[#0A2540] text-sm mb-3">
              التفاصيل التقنية — {tech.action_label}
            </div>
            <div className="space-y-2 text-[11px]">
              {["before", "after"].map((k) => (
                <div key={k}>
                  <div className="font-semibold text-[#0A2540]">{k === "before" ? "قبل" : "بعد"}</div>
                  {Object.entries((tech.technical || {})[k] || {}).length === 0 ? (
                    <div className="text-muted-foreground">—</div>
                  ) : Object.entries((tech.technical || {})[k] || {}).map(([f, v]) => (
                    <div key={f} className="flex justify-between gap-3 border-b py-1">
                      <span className="text-muted-foreground">{f}</span>
                      <span className="font-semibold text-left" dir="auto">
                        {typeof v === "object" ? Object.entries(v || {}).map(([a2, b2]) => `${a2}: ${b2}`).join(" • ") : ar(v)}
                      </span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
            <Button size="sm" variant="outline" className="mt-4 w-full" onClick={() => setTech(null)}
              data-testid="audit-tech-close">إغلاق</Button>
          </div>
        </div>
      )}

    </>
  );
}

const SettingField = ({ f, sec, draft, setDraft }) => {
  const val = ((draft || {})[sec] || {})[f.key];
  const set = (v) => setDraft({ ...draft, [sec]: { ...(draft[sec] || {}), [f.key]: v } });
  const tid = `set-${sec}-${f.key}`;
  if (f.type === "switch") {
    return (
      <label className="text-xs bg-[#F4F6F8] rounded-lg px-3 py-2 flex items-center gap-2 cursor-pointer" data-testid={tid}>
        <input type="checkbox" checked={!!val} onChange={(e) => set(e.target.checked)} />
        {f.label}
      </label>
    );
  }
  if (f.type === "select") {
    return (
      <div>
        <Label className="text-[11px]">{f.label}</Label>
        <select className="h-9 w-full rounded-md border border-input px-2 text-xs bg-white" data-testid={tid}
          value={val ?? ""} disabled={f.readonly} onChange={(e) => set(e.target.value)}>
          {(f.options || []).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
      </div>
    );
  }
  if (f.type === "multiselect") {
    const arr = Array.isArray(val) ? val : [];
    return (
      <div>
        <Label className="text-[11px]">{f.label}</Label>
        <div className="flex flex-wrap gap-2 mt-1" data-testid={tid}>
          {(f.options || []).map(([k, l]) => (
            <label key={k} className={`text-[11px] px-3 py-1.5 rounded-lg border cursor-pointer ${arr.includes(k) ? "bg-[#0A2540] text-white border-[#0A2540]" : "bg-white"}`}>
              <input type="checkbox" className="hidden" checked={arr.includes(k)}
                onChange={() => set(arr.includes(k) ? arr.filter((x) => x !== k) : [...arr, k])} />{l}
            </label>
          ))}
        </div>
      </div>
    );
  }
  if (f.type === "tags") {
    const arr = Array.isArray(val) ? val : [];
    return (
      <div>
        <Label className="text-[11px]">{f.label}</Label>
        <Input className="h-9 text-xs" data-testid={tid} disabled={f.readonly}
          value={arr.join("، ")}
          onChange={(e) => set(e.target.value.split(/[،,]/).map((x) => x.trim()).filter(Boolean))} />
        <div className="text-[10px] text-muted-foreground">افصل بين القيم بفاصلة</div>
      </div>
    );
  }
  return (
    <div>
      <Label className="text-[11px]">{f.label}</Label>
      <Input type={f.type === "number" ? "number" : "text"} step={f.step} className="h-9 text-xs"
        data-testid={tid} disabled={f.readonly} value={val ?? ""}
        onChange={(e) => set(f.type === "number" ? (e.target.value === "" ? null : Number(e.target.value)) : e.target.value)} />
    </div>
  );
};
