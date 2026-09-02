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
import { PlugZap, RefreshCw, CheckCircle2, XCircle, Radar, Settings2 } from "lucide-react";

export default function AdminIntegrations() {
  const [h, setH] = useState(null);
  const [items, setItems] = useState([]);
  const [target, setTarget] = useState(null);
  const [probe, setProbe] = useState(null);
  const [detail, setDetail] = useState(null);
  const [urlForm, setUrlForm] = useState({ webhook_url: "", reason: "" });
  const [retry, setRetry] = useState(null);   // {id} | {all:true}
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    Promise.all([
      api.get("/admin/integrations/health"),
      api.get("/admin/integrations/outbox?limit=100"),
      api.get("/admin/integrations/target"),
    ]).then(([a, b, c]) => {
      setH(a.data); setItems(b.data); setTarget(c.data);
      setUrlForm((f) => ({ ...f, webhook_url: f.webhook_url || c.data.url || "" }));
    });
  }, []);
  useEffect(() => { load(); }, [load]);

  const runProbe = async () => {
    setBusy(true);
    try {
      const r = await api.post("/admin/integrations/probe");
      setProbe(r.data);
      r.data.owner === "ok" ? toast.success(r.data.verdict) : toast.error(r.data.verdict);
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const saveTarget = async () => {
    setBusy(true);
    try {
      await api.post("/admin/integrations/target", urlForm);
      toast.success("تم تحديث وجهة التكامل وتسجيلها في سجل التدقيق");
      setUrlForm({ ...urlForm, reason: "" }); load();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const openDetail = async (id) => {
    try {
      const r = await api.get(`/admin/integrations/outbox/${id}`);
      setDetail(r.data);
    } catch (e) { toast.error(apiError(e)); }
  };

  const doRetry = async () => {
    setBusy(true);
    try {
      const r = retry.all
        ? await api.post("/admin/integrations/outbox/retry-all", { reason })
        : await api.post(`/admin/integrations/outbox/${retry.id}/retry`, { reason });
      toast.success(retry.all
        ? `تمت محاولة ${r.data.attempted} حدثاً — المتبقي ${r.data.still_undelivered}`
        : `النتيجة: ${r.data.status}${r.data.last_error ? " — " + r.data.last_error : ""}`);
      setRetry(null); setReason(""); setDetail(null); load();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  if (!h) return <div className="text-center py-20 text-muted-foreground" data-testid="integrations-loading">جارٍ التحميل...</div>;

  return (
    <>
      <PageHeader title="صحة التكامل مع رحّال" subtitle="حالة الأحداث الصادرة والواردة، أسباب الفشل، وإعادة المعالجة اليدوية بصلاحية خاصة وسبب مُسجَّل" />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        <Stat label="إجمالي الأحداث الصادرة" v={h.outbox.total} tid="stat-outbox-total" />
        <Stat label="مُسلَّمة" v={h.outbox.by_status.delivered || 0} ok tid="stat-delivered" />
        <Stat label="غير مُسلَّمة" v={h.outbox.undelivered} danger tid="stat-undelivered" />
        <Stat label="أحداث واردة" v={h.inbound.total} tid="stat-inbound" />
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-5 mb-5" data-testid="target-panel">
        <div className="flex items-center gap-2 font-head font-bold text-[#0A2540] text-sm mb-3">
          <Settings2 className="w-4 h-4 text-[#D4AF37]" /> وجهة التكامل والتحقق منها
        </div>
        <div className="grid md:grid-cols-2 gap-3 text-[11px] mb-3">
          <Row k="العنوان الفعّال" v={target?.url || "غير مضبوط"} tid="target-url" />
          <Row k="مصدر الإعداد" v={target?.source === "settings" ? "إعداد إداري (يتقدّم على البيئة)" : "متغير البيئة RAHAL_WEBHOOK_URL"} tid="target-source" />
          <Row k="Base URL" v={target?.base_url || "—"} tid="target-base" />
          <Row k="المسار / الطريقة" v={`${target?.path || "—"} • ${target?.method}`} tid="target-path" />
          <Row k="هيدر التوقيع" v={target?.signature_header} tid="target-sighdr" />
          <Row k="بصمة السر المشترك" v={target?.secret_fingerprint} tid="target-fingerprint" />
        </div>
        <div className="text-[10px] text-muted-foreground mb-3">
          صيغة التوقيع: {target?.signature_algo} — على رحّال أن تكون بصمة سرّه مطابقة للبصمة أعلاه.
        </div>
        <div className="grid md:grid-cols-[1fr_1fr_auto] gap-2 items-end border-t pt-3">
          <div><Label className="text-xs">عنوان Webhook الصحيح لرحّال</Label>
            <Input className="h-9 text-xs" dir="ltr" value={urlForm.webhook_url} data-testid="target-url-input"
              onChange={(e) => setUrlForm({ ...urlForm, webhook_url: e.target.value })} /></div>
          <div><Label className="text-xs">سبب التغيير (إلزامي)</Label>
            <Input className="h-9 text-xs" value={urlForm.reason} data-testid="target-reason-input"
              onChange={(e) => setUrlForm({ ...urlForm, reason: e.target.value })} /></div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={saveTarget} data-testid="save-target-btn"
              disabled={busy || urlForm.reason.trim().length < 3 || !urlForm.webhook_url}>حفظ الوجهة</Button>
            <Button size="sm" className="bg-[#0A2540] hover:bg-[#061A2E]" onClick={runProbe}
              disabled={busy} data-testid="probe-btn"><Radar className="w-4 h-4" /> فحص الوجهة</Button>
          </div>
        </div>
        {probe && (
          <div className={`mt-3 text-[11px] rounded-lg px-3 py-2 border ${probe.owner === "ok" ? "bg-[#F0FDF4] border-[#BBF7D0] text-[#15803D]" : "bg-[#FEF2F2] border-[#FECACA] text-[#B91C1C]"}`}
            data-testid="probe-result">
            <div className="font-bold">{probe.verdict}</div>
            <div className="text-[10px] mt-1 break-all text-current/80">
              POST {probe.url} → HTTP {probe.http_status ?? "—"} ({probe.latency_ms}ms)
              {probe.transport_error ? ` • خطأ اتصال: ${probe.transport_error}` : ""}
            </div>
            {probe.response_body && (
              <pre className="text-[10px] mt-1 bg-white/60 rounded p-2 overflow-x-auto" dir="ltr" data-testid="probe-body">{probe.response_body}</pre>
            )}
            <div className="text-[10px] mt-1">
              المسؤول عن الإصلاح: {probe.owner === "rahal" ? "فريق رحّال" : probe.owner === "ok" ? "لا شيء — سليم" : "مشترك"}
            </div>
          </div>
        )}
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-5 mb-5" data-testid="failure-groups">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 font-head font-bold text-[#0A2540] text-sm">
            <PlugZap className="w-4 h-4 text-[#D4AF37]" /> أسباب الفشل مجمّعة
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={load} data-testid="integrations-refresh">
              <RefreshCw className="w-4 h-4" /> تحديث
            </Button>
            <Button size="sm" className="bg-[#0A2540] hover:bg-[#061A2E]" data-testid="retry-all-btn"
              disabled={!h.outbox.undelivered} onClick={() => setRetry({ all: true })}>
              إعادة معالجة الكل
            </Button>
          </div>
        </div>
        {h.outbox.failure_groups.length === 0 ? (
          <div className="text-xs text-muted-foreground" data-testid="failure-groups-empty">لا توجد أحداث فاشلة</div>
        ) : (
          <div className="space-y-2" data-testid="failure-groups-list">
            {h.outbox.failure_groups.map((g, i) => (
              <div key={i} className="text-xs bg-[#FEF2F2] border border-[#FECACA] rounded-lg px-3 py-2" data-testid={`failure-group-${i}`}>
                <div className="flex justify-between">
                  <b className="text-[#B91C1C]">{g.event}</b>
                  <span className="tabular">{g.count} حدث</span>
                </div>
                <div className="text-[11px] text-muted-foreground mt-1 break-words">
                  {g.last_error || "لم يُسجَّل سبب — لم تُرسل بعد (pending)"}
                </div>
              </div>
            ))}
          </div>
        )}
        <div className="text-[11px] text-muted-foreground mt-3">
          آخر تسليم ناجح: {h.outbox.last_delivered_at ? fmtDate(h.outbox.last_delivered_at) : "—"}
        </div>
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-5 mb-5" data-testid="destinations-panel">
        <div className="font-head font-bold text-[#0A2540] text-sm mb-3">توزيع الأحداث حسب الوجهة</div>
        <div className="space-y-1.5">
          {(h.outbox.by_destination || []).map((x, i) => (
            <div key={i} className="text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-1.5 flex flex-wrap gap-2 items-center"
              data-testid={`destination-${i}`}>
              <span className={`text-[10px] px-2 py-0.5 rounded-full border ${x.status === "delivered" ? "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]" : "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]"}`}>
                {x.status === "delivered" ? "مُسلَّم" : x.status === "failed" ? "فاشل" : x.status}
              </span>
              <span className="break-all" dir="ltr">{x.url}</span>
              <span className="tabular mr-auto">{x.count}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-2xl border card-shadow overflow-x-auto mb-5" data-testid="outbox-table">
        <table className="w-full text-xs min-w-[820px]">
          <thead className="bg-[#F4F6F8] text-muted-foreground">
            <tr>{["التاريخ", "الحدث", "الوجهة", "المحاولات", "الحالة", "سبب الفشل", ""].map((x) => (
              <th key={x} className="text-right font-semibold px-3 py-2.5">{x}</th>))}</tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={7} className="text-center py-10 text-muted-foreground" data-testid="outbox-empty">لا توجد أحداث معلّقة</td></tr>
            ) : items.map((it) => (
              <tr key={it.id} className="border-t" data-testid={`outbox-row-${it.id}`}>
                <td className="px-3 py-2.5 whitespace-nowrap">{fmtDate(it.created_at)}</td>
                <td className="px-3 py-2.5 font-semibold text-[#0A2540]">{it.event}</td>
                <td className="px-3 py-2.5 max-w-[180px] truncate text-[10px]">{it.url}</td>
                <td className="px-3 py-2.5 tabular">{it.attempts}</td>
                <td className="px-3 py-2.5">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full border ${it.status === "delivered" ? "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]" : it.status === "failed" ? "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" : "bg-[#FEFCE8] text-[#A16207] border-[#FEF08A]"}`}>
                    {it.status === "delivered" ? "مُسلَّم" : it.status === "failed" ? "فاشل" : "معلّق"}
                  </span>
                </td>
                <td className="px-3 py-2.5 max-w-[260px] text-[10px]">
                  {it.diagnosis?.cause === "business" ? (
                    <span className="text-[#A16207]" data-testid={`biz-reason-${it.id}`}>
                      <b>{it.diagnosis.title}</b>
                      {it.diagnosis.required_reference && <> — المرجع المطلوب: <code dir="ltr">{it.diagnosis.required_reference}</code></>}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">{it.diagnosis?.title || it.last_error || "—"}</span>
                  )}
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <button onClick={() => openDetail(it.id)} data-testid={`detail-${it.id}`}
                    className="text-[#0A2540] underline font-semibold ml-2">السبب الدقيق</button>
                  {it.diagnosis?.retry_useful === false ? (
                    <span className="text-[10px] text-muted-foreground" data-testid={`no-retry-${it.id}`}>
                      إعادة المعالجة لا تُفيد
                    </span>
                  ) : (
                    <button onClick={() => setRetry({ id: it.id })} data-testid={`retry-${it.id}`}
                      className="text-[#0A2540] underline font-semibold">إعادة المعالجة</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="inbound-log">
        <div className="font-head font-bold text-[#0A2540] text-sm mb-3">آخر الأحداث الواردة من رحّال</div>
        <div className="space-y-1.5">
          {h.inbound.recent.length === 0 ? <div className="text-xs text-muted-foreground">لا يوجد سجل</div> :
            h.inbound.recent.map((r, i) => (
              <div key={i} className="text-[11px] bg-[#F4F6F8] rounded-lg px-3 py-1.5 flex items-center gap-2" data-testid={`inbound-${i}`}>
                {r.ok === false ? <XCircle className="w-3.5 h-3.5 text-[#B91C1C]" /> : <CheckCircle2 className="w-3.5 h-3.5 text-[#15803D]" />}
                <span className="font-semibold">{r.event || r.type || "حدث"}</span>
                <span className="text-muted-foreground mr-auto">{fmtDate(r.at)}</span>
              </div>
            ))}
        </div>
      </div>

      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent dir="rtl" className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="detail-dialog">
          <DialogHeader><DialogTitle>السبب الدقيق لفشل الحدث</DialogTitle></DialogHeader>
          {detail && (
            <div className="space-y-3 text-[11px]">
              <div className="grid sm:grid-cols-2 gap-2">
                <Row k="نوع الحدث" v={detail.event} tid="detail-event" />
                <Row k="الحالة" v={detail.status} tid="detail-status" />
                <Row k="رمز HTTP" v={detail.http_status ?? "—"} tid="detail-http" />
                <Row k="عدد المحاولات" v={detail.attempts} tid="detail-attempts" />
                <Row k="الوجهة" v={detail.url} tid="detail-url" />
                <Row k="أُنشئ في" v={fmtDate(detail.created_at)} tid="detail-created" />
              </div>
              <div className={`rounded-lg px-3 py-2 border ${detail.diagnosis?.cause === "business" ? "bg-[#FEFCE8] border-[#FEF08A] text-[#A16207]" : "bg-[#FEF2F2] border-[#FECACA] text-[#B91C1C]"}`}
                data-testid="detail-diagnosis">
                <b>{detail.diagnosis?.title}</b>
                <div className="mt-1">{detail.diagnosis?.reason_ar}</div>
                {detail.diagnosis?.required_reference && (
                  <div className="mt-1">المرجع المطلوب من رحّال: <code dir="ltr" data-testid="detail-required-ref">{detail.diagnosis.required_reference}</code></div>
                )}
                <div className="mt-1"><b>الإجراء التالي:</b> {detail.diagnosis?.next_action}</div>
                <div className="mt-1 text-[10px]">
                  المسؤول: {detail.diagnosis?.owner === "rahal" ? "فريق رحّال" : detail.diagnosis?.owner === "ok" ? "لا شيء" : "مشترك"}
                  {detail.diagnosis?.retry_useful === false && " • إعادة المعالجة لن تُفيد قبل معالجة السبب"}
                </div>
              </div>
              <div className="bg-[#FEF2F2] border border-[#FECACA] text-[#B91C1C] rounded-lg px-3 py-2" data-testid="detail-error">
                <b>نص الخطأ الحرفي من الخادم:</b>
                <pre className="mt-1 whitespace-pre-wrap" dir="ltr">{detail.last_error || "—"}</pre>
              </div>
              <div>
                <b>سجل المحاولات:</b>
                <div className="mt-1 space-y-1" data-testid="detail-attempt-history">
                  {(detail.attempt_history || []).length === 0 ? (
                    <div className="text-muted-foreground">لم يُسجَّل تفصيل للمحاولات السابقة (أحداث قديمة) — أعد المعالجة لتسجيلها.</div>
                  ) : detail.attempt_history.map((a, i) => (
                    <div key={i} className="bg-[#F4F6F8] rounded px-2 py-1" dir="ltr">
                      {a.at?.slice(0, 19)} • HTTP {a.http_status ?? "ERR"} • {a.ms}ms • {a.error || "OK"}
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <b>الجسم الموقّع المُرسل:</b>
                <pre className="mt-1 bg-[#F4F6F8] rounded p-2 overflow-x-auto text-[10px]" dir="ltr" data-testid="detail-body">{detail.signed_body}</pre>
              </div>
              <div>
                <b>أمر إعادة الإنتاج (curl):</b>
                <pre className="mt-1 bg-[#0A2540] text-white rounded p-2 overflow-x-auto text-[10px]" dir="ltr" data-testid="detail-curl">{detail.curl}</pre>
              </div>
              <Button className="w-full bg-[#0A2540] hover:bg-[#061A2E]" data-testid="detail-retry-btn"
                disabled={detail.diagnosis?.retry_useful === false}
                onClick={() => setRetry({ id: detail.id })}>
                {detail.diagnosis?.retry_useful === false
                  ? "إعادة المعالجة معطّلة — السبب يحتاج معالجة من رحّال أولاً"
                  : "إعادة المعالجة بسبب مُسجَّل"}
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!retry} onOpenChange={(o) => !o && setRetry(null)}>
        <DialogContent dir="rtl" className="max-w-md" data-testid="retry-dialog">
          <DialogHeader><DialogTitle>{retry?.all ? "إعادة معالجة كل الأحداث الفاشلة" : "إعادة معالجة الحدث"}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="text-xs text-muted-foreground">
              إعادة المعالجة عملية حسّاسة تتطلب سبباً ويُسجَّل باسمك في سجل التدقيق. التوقيع HMAC وآلية Idempotency تمنع تكرار القيود.
            </div>
            <div><Label className="text-xs">السبب (إلزامي)</Label>
              <Textarea rows={2} value={reason} data-testid="retry-reason" onChange={(e) => setReason(e.target.value)} /></div>
            <Button className="w-full bg-[#0A2540] hover:bg-[#061A2E]" data-testid="confirm-retry"
              disabled={busy || reason.trim().length < 3} onClick={doRetry}>تنفيذ إعادة المعالجة</Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

const Stat = ({ label, v, ok, danger, tid }) => (
  <div className="bg-white rounded-2xl border p-4 card-shadow" data-testid={tid}>
    <div className={`tabular text-2xl font-bold ${danger ? "text-[#B91C1C]" : ok ? "text-[#15803D]" : "text-[#0A2540]"}`}>{v}</div>
    <div className="text-[11px] text-muted-foreground mt-1">{label}</div>
  </div>
);

const Row = ({ k, v, tid }) => (
  <div className="flex gap-2 bg-[#F4F6F8] rounded-lg px-3 py-1.5" data-testid={tid}>
    <span className="text-muted-foreground shrink-0">{k}:</span>
    <span className="font-semibold text-[#0A2540] break-all" dir="auto">{String(v ?? "—")}</span>
  </div>
);
