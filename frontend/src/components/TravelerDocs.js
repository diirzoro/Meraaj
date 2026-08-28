import { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { Upload, Trash2, FileText, Download } from "lucide-react";
import { toast } from "sonner";

const TYPES = [["passport", "جواز السفر"], ["visa", "التأشيرة"], ["photo", "صورة"], ["other", "أخرى"]];
const typeLabel = (t) => (TYPES.find((x) => x[0] === t) || [null, t])[1];
const API = process.env.REACT_APP_BACKEND_URL + "/api";

export default function TravelerDocs({ bookingId, registrantIndex }) {
  const [docs, setDocs] = useState([]);
  const [docType, setDocType] = useState("passport");
  const [busy, setBusy] = useState(false);

  const load = () => api.get(`/bookings/${bookingId}/documents?registrant_index=${registrantIndex}`)
    .then((r) => setDocs(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [bookingId, registrantIndex]);

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) { toast.error("حجم الملف يتجاوز 10 ميجابايت"); return; }
    setBusy(true);
    try {
      const b64 = await new Promise((res, rej) => {
        const rd = new FileReader(); rd.onload = () => res(rd.result); rd.onerror = rej; rd.readAsDataURL(file);
      });
      await api.post(`/bookings/${bookingId}/documents`, {
        registrant_index: registrantIndex, doc_type: docType, filename: file.name, content_base64: b64,
      });
      toast.success("تم رفع الملف");
      load();
    } catch (err) { toast.error(apiError(err)); } finally { setBusy(false); }
  };

  const del = async (id) => {
    try { await api.delete(`/documents/${id}`); toast.success("تم حذف الملف"); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  return (
    <div className="mt-3 border-t pt-3" data-testid={`docs-${registrantIndex}`}>
      <div className="text-xs font-semibold text-[#0A2540] mb-2">المستندات ({docs.length})</div>
      {docs.length > 0 && (
        <div className="space-y-1.5 mb-3">
          {docs.map((d) => (
            <div key={d.id} className="flex items-center justify-between bg-[#F4F6F8] rounded-lg px-3 py-2 text-xs" data-testid={`doc-${d.id}`}>
              <span className="flex items-center gap-2 min-w-0">
                <FileText className="w-3.5 h-3.5 text-[#0A2540] shrink-0" />
                <span className="font-semibold shrink-0">{typeLabel(d.doc_type)}</span>
                <span className="text-muted-foreground truncate">{d.filename}</span>
              </span>
              <span className="flex items-center gap-3 shrink-0">
                <a href={`${API}/documents/${d.id}/download`} target="_blank" rel="noreferrer"
                   className="text-[#0A2540] hover:opacity-70" data-testid={`doc-download-${d.id}`}><Download className="w-3.5 h-3.5" /></a>
                <button onClick={() => del(d.id)} className="text-red-500 hover:text-red-700" data-testid={`doc-delete-${d.id}`}><Trash2 className="w-3.5 h-3.5" /></button>
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-center gap-2">
        <select value={docType} onChange={(e) => setDocType(e.target.value)} data-testid={`doc-type-${registrantIndex}`}
                className="h-8 rounded-md border border-input bg-transparent px-2 text-xs">
          {TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <label className="inline-flex items-center gap-1.5 text-xs bg-[#0A2540] text-white rounded-md px-3 h-8 cursor-pointer hover:bg-[#061A2E]" data-testid={`doc-upload-${registrantIndex}`}>
          <Upload className="w-3.5 h-3.5" /> {busy ? "جارٍ الرفع..." : "رفع ملف"}
          <input type="file" className="hidden" accept="image/png,image/jpeg,image/webp,application/pdf" onChange={onFile} disabled={busy} />
        </label>
      </div>
    </div>
  );
}
