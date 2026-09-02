import { useCallback, useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { fmtDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { ShieldCheck, KeyRound, LogOut, UserX, Search } from "lucide-react";

const TABS = [["roles", "الأدوار والصلاحيات"], ["dual", "الموافقة المزدوجة"],
["approvals", "طلبات الاعتماد"], ["sessions", "الجلسات والدخول"], ["2fa", "المصادقة الثنائية"]];

export default function AdminRoles() {
  const [tab, setTab] = useState("roles");
  const [cat, setCat] = useState(null);
  const [users, setUsers] = useState([]);
  const [summary, setSummary] = useState(null);
  const [filter, setFilter] = useState("");
  const [q, setQ] = useState("");
  const [sessions, setSessions] = useState([]);
  const [history, setHistory] = useState({ sessions: [], failed_attempts: [] });
  const [approvals, setApprovals] = useState([]);
  const [edit, setEdit] = useState(null);
  const [dual, setDual] = useState({});
  const [twofa, setTwofa] = useState(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/admin/rbac/catalog").then((r) => { setCat(r.data); setDual(r.data.settings || {}); });
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (filter === "assigned") p.set("unassigned", "false");
    if (filter === "unassigned") p.set("unassigned", "true");
    if (filter === "staff") p.set("staff_only", "true");
    api.get(`/admin/rbac/users?${p.toString()}`).then((r) => { setUsers(r.data.items); setSummary(r.data.summary); });
    api.get("/admin/sessions?active_only=false&limit=100").then((r) => setSessions(r.data));
    api.get("/admin/login-history").then((r) => setHistory(r.data));
    api.get("/admin/approvals").then((r) => setApprovals(r.data));
  }, [q, filter]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); load(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  if (!cat) return <div className="text-center py-20 text-muted-foreground" data-testid="roles-loading">جارٍ التحميل...</div>;

  return (
    <>
      <PageHeader title="الصلاحيات والأمان (Enterprise RBAC)" subtitle="أدوار تفصيلية، صلاحيات حسّاسة منفصلة، موافقة شخص ثانٍ، جلسات نشطة ومصادقة ثنائية" />

      <div className="flex flex-wrap gap-2 mb-5" data-testid="roles-tabs">
        {TABS.map(([v, l]) => (
          <button key={v} onClick={() => setTab(v)} data-testid={`tab-${v}`}
            className={`px-3 h-9 rounded-lg text-xs font-semibold border transition-colors ${tab === v ? "bg-[#0A2540] text-white border-[#0A2540]" : "bg-white text-[#0A2540] hover:bg-[#F4F6F8]"}`}>
            {l}
          </button>
        ))}
      </div>

      {tab === "roles" && (
        <>
          <div className="bg-white rounded-2xl border card-shadow p-4 mb-5">
            <div className="text-xs font-semibold text-[#0A2540] mb-2">الأدوار المعتمدة ({Object.keys(cat.roles).length})</div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(cat.roles).map(([k, r]) => (
                <span key={k} className="text-[10px] px-2 py-1 rounded-full bg-[#F4F6F8] text-[#0A2540] border" data-testid={`role-chip-${k}`}
                  title={(r.perms || []).map((p) => cat.permissions[p] || p).join(" • ")}>
                  {r.ar} <span className="text-muted-foreground">({r.perms[0] === "*" ? "كل الصلاحيات" : `${r.perms.length} صلاحية`})</span>
                </span>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-2xl border card-shadow p-4 mb-3 flex flex-wrap gap-3 items-center">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="w-4 h-4 absolute top-2.5 right-3 text-muted-foreground" />
              <input value={q} onChange={(e) => setQ(e.target.value)} data-testid="rbac-search"
                placeholder="ابحث بالبريد أو الاسم" className="w-full h-9 rounded-md border border-input pr-9 pl-3 text-xs" />
            </div>
            <select value={filter} onChange={(e) => setFilter(e.target.value)} data-testid="rbac-filter"
              className="h-9 rounded-md border border-input px-2 text-xs bg-white">
              <option value="">كل الحسابات</option>
              <option value="assigned">لها أدوار مؤسسية</option>
              <option value="unassigned">بلا أدوار مؤسسية</option>
              <option value="staff">حسابات موظفين فقط</option>
            </select>
            {summary && (
              <span className="text-[11px] text-muted-foreground mr-auto" data-testid="rbac-summary">
                معروض {summary.total_returned} • بأدوار {summary.with_roles} • بلا أدوار {summary.without_roles} •
                موظفون {summary.staff_accounts} • حسابات اختبار QA {summary.qa_accounts}
              </span>
            )}
          </div>

          <div className="bg-white rounded-2xl border card-shadow overflow-x-auto" data-testid="rbac-users-table">
            <table className="w-full text-xs min-w-[860px]">
              <thead className="bg-[#F4F6F8] text-muted-foreground">
                <tr>{["المستخدم", "النوع", "أدوار Enterprise", "الصلاحيات", "الحالة", "2FA", ""].map((h) => (
                  <th key={h} className="text-right font-semibold px-3 py-2.5">{h}</th>))}</tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-t hover:bg-[#FAFBFC]" data-testid={`rbac-user-${u.id}`}>
                    <td className="px-3 py-2.5">
                      <div className="font-semibold text-[#0A2540]">{u.office_name || u.email}</div>
                      <div className="text-[10px] text-muted-foreground">{u.email}</div>
                    </td>
                    <td className="px-3 py-2.5">
                      {u.role}{u.is_rahal && " • رحّال"}
                      {u.is_staff && <span className="mr-1 text-[9px] px-1.5 py-0.5 rounded bg-[#EFF6FF] text-[#1D4ED8]">موظف مكتب</span>}
                      {u.is_staff && !u.has_own_wallet && <span className="mr-1 text-[9px] px-1.5 py-0.5 rounded bg-[#F0FDF4] text-[#15803D]">محفظة المكتب</span>}
                      {u.is_qa_account && <span className="mr-1 text-[9px] px-1.5 py-0.5 rounded bg-[#F4F6F8] text-muted-foreground">QA</span>}
                    </td>
                    <td className="px-3 py-2.5">
                      {(u.enterprise_roles || []).length === 0 ? (
                        <span className="text-[10px] text-muted-foreground" data-testid={`roles-note-${u.id}`}>{u.roles_note || "—"}</span>
                      ) : u.enterprise_roles.map((r) => cat.roles[r]?.ar || r).join(", ")}
                    </td>
                    <td className="px-3 py-2.5 tabular">{u.permissions.includes("*") ? "الكل" : u.permissions.length}</td>
                    <td className="px-3 py-2.5">{u.status}</td>
                    <td className="px-3 py-2.5">{u.twofa_enabled ? "مفعّلة" : "—"}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <button onClick={() => setEdit({ ...u, roles: u.enterprise_roles || [], reason: "" })}
                        data-testid={`edit-roles-${u.id}`} className="text-[#0A2540] underline font-semibold">الأدوار</button>
                      <button data-testid={`force-logout-${u.id}`} className="mr-2 text-[#1D4ED8] underline"
                        onClick={() => { const r = window.prompt("سبب إنهاء الجلسات؟"); if (r && r.length >= 3) act(() => api.post(`/admin/users/${u.id}/force-logout`, { reason: r }), "تم إنهاء الجلسات"); }}>
                        إنهاء الجلسات
                      </button>
                      {u.role !== "super_admin" && (
                        <button data-testid={`suspend-${u.id}`} className="mr-2 text-[#B91C1C] underline"
                          onClick={() => { const r = window.prompt(u.status === "active" ? "سبب التعليق؟" : "سبب إعادة التفعيل؟"); if (r && r.length >= 3) act(() => api.post(`/admin/users/${u.id}/suspend`, { suspend: u.status === "active", reason: r }), "تم تحديث الحساب"); }}>
                          {u.status === "active" ? "تعليق" : "تفعيل"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === "dual" && (
        <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="dual-control">
          <div className="text-xs text-muted-foreground mb-3">
            حدّد العمليات التي تحتاج موافقة شخص ثانٍ. منشئ العملية لا يمكنه اعتمادها (مطبّق في الخادم).
          </div>
          <div className="space-y-2">
            {Object.entries(cat.dual_control).map(([k, l]) => (
              <label key={k} className="flex items-center gap-2 text-xs bg-[#F4F6F8] rounded-lg px-3 py-2" data-testid={`dual-${k}`}>
                <input type="checkbox" checked={!!dual[k]} onChange={(e) => setDual({ ...dual, [k]: e.target.checked })} />
                {l}
              </label>
            ))}
          </div>
          <Button size="sm" className="mt-3 bg-[#0A2540] hover:bg-[#061A2E]" data-testid="save-dual-btn" disabled={busy}
            onClick={() => act(() => api.post("/admin/rbac/dual-control", { required: dual, reason: "تحديث سياسة الموافقة المزدوجة" }), "تم حفظ السياسة")}>
            حفظ السياسة
          </Button>
        </div>
      )}

      {tab === "approvals" && (
        <div className="bg-white rounded-2xl border card-shadow overflow-x-auto" data-testid="approvals-table">
          <table className="w-full text-xs min-w-[760px]">
            <thead className="bg-[#F4F6F8] text-muted-foreground">
              <tr>{["العملية", "الهدف", "السبب", "المنشئ", "المعتمِد", "الحالة", ""].map((h) => (
                <th key={h} className="text-right font-semibold px-3 py-2.5">{h}</th>))}</tr>
            </thead>
            <tbody>
              {approvals.length === 0 ? (
                <tr><td colSpan={7} className="text-center py-10 text-muted-foreground" data-testid="approvals-empty">لا توجد طلبات اعتماد</td></tr>
              ) : approvals.map((a) => (
                <tr key={a.id} className="border-t" data-testid={`approval-${a.id}`}>
                  <td className="px-3 py-2.5 font-semibold text-[#0A2540]">{a.operation_label}</td>
                  <td className="px-3 py-2.5 text-[10px]">{a.target}</td>
                  <td className="px-3 py-2.5">{a.reason}</td>
                  <td className="px-3 py-2.5">{a.maker}</td>
                  <td className="px-3 py-2.5">{a.checker || "—"}</td>
                  <td className="px-3 py-2.5">{a.status}</td>
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    {a.status === "pending" && (
                      <>
                        <button className="text-[#15803D] underline" data-testid={`approve-${a.id}`}
                          onClick={() => act(() => api.post(`/admin/approvals/${a.id}/decide`, { approve: true }), "تم الاعتماد")}>اعتماد</button>
                        <button className="mr-2 text-[#B91C1C] underline" data-testid={`reject-${a.id}`}
                          onClick={() => act(() => api.post(`/admin/approvals/${a.id}/decide`, { approve: false }), "تم الرفض")}>رفض</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "sessions" && (
        <div className="grid lg:grid-cols-2 gap-5">
          <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="sessions-list">
            <div className="flex items-center gap-2 text-sm font-head font-bold text-[#0A2540] mb-3">
              <LogOut className="w-4 h-4 text-[#D4AF37]" /> الجلسات ({sessions.length})
            </div>
            <div className="space-y-1.5 max-h-96 overflow-y-auto">
              {sessions.length === 0 ? <div className="text-xs text-muted-foreground">لا توجد جلسات مسجّلة بعد</div> :
                sessions.map((s) => (
                  <div key={s.id} className={`text-[11px] rounded-lg px-3 py-2 ${s.revoked ? "bg-[#FEF2F2]" : "bg-[#F4F6F8]"}`} data-testid={`session-${s.id}`}>
                    <div className="font-semibold text-[#0A2540]">{s.email} • {s.role}</div>
                    <div className="text-muted-foreground">{s.ip || "—"} • {(s.user_agent || "").slice(0, 60)}</div>
                    <div className="text-[10px] text-muted-foreground">{fmtDate(s.created_at)} {s.revoked ? "• مُنهاة" : ""}</div>
                  </div>
                ))}
            </div>
          </div>
          <div className="bg-white rounded-2xl border card-shadow p-5" data-testid="failed-attempts">
            <div className="flex items-center gap-2 text-sm font-head font-bold text-[#0A2540] mb-3">
              <UserX className="w-4 h-4 text-[#B91C1C]" /> محاولات الدخول الفاشلة
            </div>
            <div className="space-y-1.5 max-h-96 overflow-y-auto">
              {history.failed_attempts.length === 0 ? <div className="text-xs text-muted-foreground">لا توجد محاولات فاشلة</div> :
                history.failed_attempts.map((a) => (
                  <div key={a.id} className="text-[11px] bg-[#FEFCE8] rounded-lg px-3 py-1.5">
                    {a.email} • محاولات {a.count} {a.locked_until ? `• مقفل حتى ${fmtDate(a.locked_until)}` : ""}
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}

      {tab === "2fa" && (
        <div className="bg-white rounded-2xl border card-shadow p-5 max-w-lg" data-testid="twofa-panel">
          <div className="flex items-center gap-2 text-sm font-head font-bold text-[#0A2540] mb-3">
            <KeyRound className="w-4 h-4 text-[#D4AF37]" /> المصادقة الثنائية لحسابك الإداري
          </div>
          {!twofa ? (
            <Button size="sm" className="bg-[#0A2540] hover:bg-[#061A2E]" data-testid="setup-2fa-btn"
              onClick={async () => { const r = await api.post("/admin/2fa/setup"); setTwofa(r.data); }}>
              إعداد المصادقة الثنائية (TOTP)
            </Button>
          ) : (
            <div className="space-y-3">
              <div className="text-xs bg-[#F4F6F8] rounded-lg px-3 py-2 break-all" data-testid="twofa-secret">
                المفتاح: <b>{twofa.secret}</b>
                <div className="text-[10px] text-muted-foreground mt-1">أضِفه في Google Authenticator ثم أدخل الرمز للتأكيد.</div>
              </div>
              <div><Label className="text-xs">الرمز (6 أرقام)</Label>
                <Input value={code} data-testid="twofa-code" onChange={(e) => setCode(e.target.value)} className="h-8 text-xs" /></div>
              <Button size="sm" className="bg-[#15803D] hover:bg-[#116632]" data-testid="verify-2fa-btn"
                disabled={busy || code.length !== 6}
                onClick={() => act(async () => { await api.post("/admin/2fa/verify", { code }); setCode(""); }, "تم تفعيل المصادقة الثنائية")}>
                تأكيد وتفعيل
              </Button>
            </div>
          )}
          <div className="text-[10px] text-muted-foreground mt-3">
            ملاحظة: التفعيل يسجّل في سجل التدقيق. فرض 2FA على كل الحسابات الإدارية يُدار من مركز الإعدادات.
          </div>
        </div>
      )}

      <Dialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)}>
        <DialogContent dir="rtl" className="max-w-md max-h-[85vh] overflow-y-auto" data-testid="roles-dialog">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><ShieldCheck className="w-4 h-4" /> أدوار {edit?.email}</DialogTitle></DialogHeader>
          {edit && (
            <div className="space-y-3">
              <div className="space-y-1.5">
                {Object.entries(cat.roles).filter(([k]) => k !== "super_admin").map(([k, r]) => (
                  <label key={k} className="flex items-center gap-2 text-xs bg-[#F4F6F8] rounded-lg px-3 py-1.5" data-testid={`role-opt-${k}`}>
                    <input type="checkbox" checked={edit.roles.includes(k)}
                      onChange={(e) => setEdit({ ...edit, roles: e.target.checked ? [...edit.roles, k] : edit.roles.filter((x) => x !== k) })} />
                    {r.ar} <span className="text-[10px] text-muted-foreground">— {r.perms.length} صلاحية</span>
                  </label>
                ))}
              </div>
              <div><Label className="text-xs">السبب (إلزامي)</Label>
                <Textarea rows={2} value={edit.reason} data-testid="roles-reason"
                  onChange={(e) => setEdit({ ...edit, reason: e.target.value })} /></div>
              <Button className="w-full bg-[#0A2540] hover:bg-[#061A2E]" data-testid="save-roles-btn"
                disabled={busy || edit.reason.trim().length < 3}
                onClick={() => act(async () => { await api.post(`/admin/rbac/users/${edit.id}/roles`, { roles: edit.roles, reason: edit.reason }); setEdit(null); }, "تم حفظ الأدوار")}>
                حفظ
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
