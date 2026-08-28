import { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Upload, Trash2, FileText, Download, Eye, Printer } from "lucide-react";
import { toast } from "sonner";

export const DOC_TYPES = [["passport", "جواز السفر"], ["visa", "التأشيرة"], ["photo", "صورة"], ["ticket", "تذكرة السفر"], ["other", "أخرى"]];
export const docLabel = (t) => (DOC_TYPES.find((x) => x[0] === t) || [null, t])[1];
const MAX_FILE = 10 * 1024 * 1024;
const MAX_BATCH = 20 * 1024 * 1024;
const API = process.env.REACT_APP_BACKEND_URL + "/api";
const isPdf = (m, n) => m === "application/pdf" || /\.pdf$/i.test(n || "");

export default function TravelerDocs({ bookingId, registrantIndex, passportNo }) {
  const [docs, setDocs] = useState([]);
  const [docType, setDocType] = useState("passport");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);

  const load = () => api.get(`/bookings/${bookingId}/documents?registrant_index=${registrantIndex}`)
    .then((r) => setDocs(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [bookingId, registrantIndex]);

  const onFile = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;
    const big = files.find((f) => f.size > MAX_FILE);
    if (big) { toast.error(`${big.name}: يتجاوز 10 ميجابايت للملف الواحد`); return; }
    const total = files.reduce((s, f) => s + f.size, 0);
    if (total > MAX_BATCH) { toast.error("إجمالي حجم الملفات يجب ألا يتجاوز 20MB"); return; }
    setBusy(true);
    try {
      for (const file of files) {
        const b64 = await new Promise((res, rej) => {
          const rd = new FileReader(); rd.onload = () => res(rd.result); rd.onerror = rej; rd.readAsDataURL(file);
        });
        await api.post(`/bookings/${bookingId}/documents`, {
          registrant_index: registrantIndex, doc_type: docType, filename: file.name,
          content_base64: b64, batch_total_bytes: total,
          passport_no: docType === "passport" ? (passportNo || undefined) : undefined,
        });
      }
      toast.success("تم رفع الملفات");
      load();
    } catch (err) { toast.error(apiError(err)); } finally { setBusy(false); }
  };

  const del = async (id) => {
    try { await api.delete(`/documents/${id}`); toast.success("تم حذف الملف"); load(); }
    catch (e) { toast.error(apiError(e)); }
  };
  const printDoc = (d) => window.open(`${API}/documents/${d.id}/download`, "_blank");

  return (
    <div className="mt-3 border-t pt-3" data-testid={`docs-${registrantIndex}`}>
      <div className="text-xs font-semibold text-[#0A2540] mb-2">المستندات ({docs.length})</div>
      {docs.length > 0 && (
        <div className="space-y-1.5 mb-3">
          {docs.map((d) => (
            <div key={d.id} className="flex items-center justify-between bg-[#F4F6F8] rounded-lg px-3 py-2 text-xs" data-testid={`doc-${d.id}`}>
              <span className="flex items-center gap-2 min-w-0">
                <FileText className="w-3.5 h-3.5 text-[#0A2540] shrink-0" />
                <span className="font-semibold shrink-0">{docLabel(d.doc_type)}</span>
                {d.passport_no && <span className="text-[#A16207] shrink-0">({d.passport_no})</span>}
                <span className="text-muted-foreground truncate">{d.filename}</span>
              </span>
              <span className="flex items-center gap-3 shrink-0">
                <button onClick={() => setPreview(d)} className="text-[#0A2540] hover:opacity-70" data-testid={`doc-preview-${d.id}`}><Eye className="w-3.5 h-3.5" /></button>
                <button onClick={() => printDoc(d)} className="text-[#0A2540] hover:opacity-70" data-testid={`doc-print-${d.id}`}><Printer className="w-3.5 h-3.5" /></button>
                <a href={`${API}/documents/${d.id}/download`} target="_blank" rel="noreferrer" className="text-[#0A2540] hover:opacity-70" data-testid={`doc-download-${d.id}`}><Download className="w-3.5 h-3.5" /></a>
                <button onClick={() => del(d.id)} className="text-red-500 hover:text-red-700" data-testid={`doc-delete-${d.id}`}><Trash2 className="w-3.5 h-3.5" /></button>
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-center gap-2">
        <select value={docType} onChange={(e) => setDocType(e.target.value)} data-testid={`doc-type-${registrantIndex}`}
                className="h-8 rounded-md border border-input bg-transparent px-2 text-xs">
          {DOC_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <label className="inline-flex items-center gap-1.5 text-xs bg-[#0A2540] text-white rounded-md px-3 h-8 cursor-pointer hover:bg-[#061A2E]" data-testid={`doc-upload-${registrantIndex}`}>
          <Upload className="w-3.5 h-3.5" /> {busy ? "جارٍ الرفع..." : "رفع ملفات"}
          <input type="file" multiple className="hidden" accept="image/png,image/jpeg,image/webp,application/pdf" onChange={onFile} disabled={busy} />
        </label>
      </div>

      <Dialog open={!!preview} onOpenChange={(o) => !o && setPreview(null)}>
        <DialogContent dir="rtl" className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="doc-preview-dialog">
          <DialogHeader><DialogTitle className="font-head text-[#0A2540] text-base">{preview && `${docLabel(preview.doc_type)} — ${preview.filename}`}</DialogTitle></DialogHeader>
          {preview && (isPdf(preview.mime, preview.filename)
            ? <iframe title="preview" src={`${API}/documents/${preview.id}/download`} className="w-full h-[70vh] rounded-lg border" />
            : <img alt="preview" src={`${API}/documents/${preview.id}/download`} className="w-full rounded-lg border object-contain max-h-[70vh]" />)}
          {preview && (
            <div className="flex gap-2 justify-end">
              <Button variant="outline" size="sm" onClick={() => printDoc(preview)}><Printer className="w-4 h-4" /> طباعة</Button>
              <a href={`${API}/documents/${preview.id}/download`} target="_blank" rel="noreferrer">
                <Button size="sm" className="bg-[#0A2540] hover:bg-[#061A2E]"><Download className="w-4 h-4" /> تنزيل</Button>
              </a>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
