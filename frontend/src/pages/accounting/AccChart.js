import { useState } from "react";
import api, { apiError } from "@/lib/api";
import { toast } from "sonner";
import { PageHeader } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Plus, Power, Trash2, Pencil } from "lucide-react";
import { Panel, Field, inputCls, Loading, ErrorNote, ScopeNote, Empty, useFetch, Gate } from "./ui";
import AccountRow, { flattenTree, TYPE_AR } from "./AccountNode";

export default function AccChart() {
  const { data, loading, error, reload } = useFetch("/accounting/accounts/tree?include_inactive=true");
  const flat = useFetch("/accounting/accounts?include_inactive=true");
  const [picked, setPicked] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({ parent: "", name_ar: "", name_en: "", is_group: false });
  const [busy, setBusy] = useState(false);
  const [editName, setEditName] = useState("");
  const [collapsed, setCollapsed] = useState({});
  const rows = flattenTree(data?.roots, collapsed);

  const groups = (flat.data?.items || []).filter((a) => a.is_group);

  const create = async () => {
    setBusy(true);
    try {
      const parent = (flat.data?.items || []).find((a) => a.code === form.parent);
      await api.post("/accounting/accounts", {
        parent: form.parent, name: form.name_en || form.name_ar, name_ar: form.name_ar,
        type: parent?.type, is_group: form.is_group,
      });
      toast.success("تم إنشاء الحساب");
      setCreateOpen(false);
      setForm({ parent: "", name_ar: "", name_en: "", is_group: false });
      reload(); flat.reload();
    } catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const act = async (fn, okMsg) => {
    setBusy(true);
    try { await fn(); toast.success(okMsg); setPicked(null); reload(); flat.reload(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };

  const addBtn = (
    <Gate perm="accounting.accounts.manage">
      <Button onClick={() => setCreateOpen(true)} data-testid="coa-add-btn" className="bg-[#0A2540]">
        <Plus className="w-4 h-4 me-1" /> حساب جديد
      </Button>
    </Gate>
  );

  return (
    <>
      <PageHeader title="الدليل المحاسبي" action={addBtn}
        subtitle="شجرة حسابات الدفتر المركزي — الحماية النظامية وقيود الاستخدام التاريخي تُطبَّق في النواة" />

      <ErrorNote>{error}</ErrorNote>
      <ScopeNote scope={data?.account_scope} />

      <Panel testid="coa-panel" subtitle={`الجهة المحاسبية: ${data?.entity_id || "meraaj-platform"}`}>
        {loading && <Loading />}
        {!loading && rows.length === 0 && <Empty>لا توجد حسابات</Empty>}
        {!loading && rows.map((row) => (
          <AccountRow key={row.node.code} row={row} onPick={setPicked}
                      onToggle={(code, value) => setCollapsed((c) => ({ ...c, [code]: value }))} />
        ))}
      </Panel>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent data-testid="coa-create-dialog">
          <DialogHeader><DialogTitle>حساب جديد</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Field label="الحساب الأب (مجموعة)">
              <select className={inputCls} value={form.parent} data-testid="coa-parent-select"
                      onChange={(e) => setForm({ ...form, parent: e.target.value })}>
                <option value="">— اختر —</option>
                {groups.map((g) => (
                  <option key={g.code} value={g.code}>{g.code} — {g.name_ar || g.name}</option>
                ))}
              </select>
            </Field>
            <Field label="الاسم بالعربية">
              <input className={inputCls} value={form.name_ar} data-testid="coa-name-ar"
                     onChange={(e) => setForm({ ...form, name_ar: e.target.value })} />
            </Field>
            <Field label="الاسم بالإنجليزية (اختياري)">
              <input className={inputCls} value={form.name_en} data-testid="coa-name-en"
                     onChange={(e) => setForm({ ...form, name_en: e.target.value })} />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.is_group} data-testid="coa-is-group"
                     onChange={(e) => setForm({ ...form, is_group: e.target.checked })} />
              حساب مجموعة (لا يقبل قيوداً مباشرة)
            </label>
            <Button disabled={busy || !form.parent || !form.name_ar} onClick={create}
                    data-testid="coa-create-submit" className="w-full bg-[#0A2540]">إنشاء</Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!picked} onOpenChange={(v) => !v && setPicked(null)}>
        <DialogContent data-testid="coa-detail-dialog">
          <DialogHeader>
            <DialogTitle>{picked?.code} — {picked?.name_ar || picked?.name}</DialogTitle>
          </DialogHeader>
          {picked && (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>النوع: <b>{TYPE_AR[picked.type] || picked.type}</b></div>
                <div>الأب: <b>{picked.parent || "—"}</b></div>
                <div>الطبيعة: <b>{picked.is_group ? "مجموعة" : "حساب تفصيلي"}</b></div>
                <div>الحالة: <b>{picked.is_active === false ? "غير مفعّل" : "مفعّل"}</b></div>
                <div>نظامي: <b>{picked.is_system ? "نعم" : "لا"}</b></div>
                <div>الدور: <b>{picked.role || "—"}</b></div>
              </div>
              <Gate perm="accounting.accounts.manage">
                <div className="pt-2 border-t space-y-2">
                  <Field label="تعديل الاسم العربي">
                    <input className={inputCls} data-testid="coa-edit-name" defaultValue={picked.name_ar || ""}
                           onChange={(e) => setEditName(e.target.value)} />
                  </Field>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" disabled={busy || !editName} data-testid="coa-save-name"
                            onClick={() => act(() => api.patch(`/accounting/accounts/${picked.id}`, { name_ar: editName }), "تم التعديل")}>
                      <Pencil className="w-4 h-4 me-1" /> حفظ الاسم
                    </Button>
                    <Button size="sm" variant="outline" disabled={busy} data-testid="coa-toggle-active"
                            onClick={() => act(() => api.post(`/accounting/accounts/${picked.id}/${picked.is_active === false ? "activate" : "deactivate"}`), "تم التحديث")}>
                      <Power className="w-4 h-4 me-1" /> {picked.is_active === false ? "تفعيل" : "تعطيل"}
                    </Button>
                    <Button size="sm" variant="destructive" disabled={busy} data-testid="coa-delete"
                            onClick={() => act(() => api.delete(`/accounting/accounts/${picked.id}`), "تم الحذف")}>
                      <Trash2 className="w-4 h-4 me-1" /> حذف
                    </Button>
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    الحذف يُرفض من النواة إذا كان الحساب نظامياً أو مستخدماً في قيود أو له فروع.
                  </p>
                </div>
              </Gate>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
