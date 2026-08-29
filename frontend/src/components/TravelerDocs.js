import { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Upload, Trash2, FileText, Download, Eye, Printer, Camera } from "lucide-react";
import { toast } from "sonner";

export const DOC_TYPES = [["passport", "جواز السفر"], ["visa", "التأشيرة"], ["photo", "صورة"], ["ticket", "تذكرة السفر"], ["other", "أخرى"]];
export const docLabel = (t) => (DOC_TYPES.find((x) => x[0] === t) || [null, t])[1];
const MAX_FILE = 20 * 1024 * 1024; // 20MB per single file
const isPdf = (m, n) => m === "application/pdf" || /\.pdf$/i.test(n || "");

// Fetch the private document as an authenticated Blob (Bearer header via axios),
// so preview/download/print never hit the 401 that raw <img>/<a>/window.open cause.
async function fetchBlob(id) {
  const r = await api.get(`/documents/${id}/download`, { responseType: "blob" });
  return r.data;
}

export default function TravelerDocs({ bookingId, registrantIndex, passportNo }) {
  const [docs, setDocs] = useState([]);
  const [docType, setDocType] = useState("passport");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null); // { doc, url }

  const load = () => api.get(`/bookings/${bookingId}/documents?registrant_index=${registrantIndex}`)
    .then((r) => setDocs(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [bookingId, registrantIndex]);

  const onFile = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;
    const big = files.find((f) => f.size > MAX_FILE);
    if (big) { toast.error(`${big.name}: يتجاوز 20 ميجابايت للملف الواحد`); return; }
    setBusy(true);
    try {
      for (const file of files) {
        const b64 = await new Promise((res, rej) => {
          const rd = new FileReader(); rd.onload = () => res(rd.result); rd.onerror = rej; rd.readAsDataURL(file);
        });
        await api.post(`/bookings/${bookingId}/documents`, {
          registrant_index: registrantIndex, doc_type: docType, filename: file.name,
          content_base64: b64,
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

  const openPreview = async (d) => {
    try {
      const blob = await fetchBlob(d.id);
      setPreview({ doc: d, url: URL.createObjectURL(blob) });
    } catch (e) { toast.error("تعذر جلب المستند"); }
  };
  const closePreview = () => { if (preview?.url) URL.revokeObjectURL(preview.url); setPreview(null); };

  const download = async (d) => {
    try {
      const blob = await fetchBlob(d.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = d.filename || "document";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (e) { toast.error("تعذر تنزيل المستند"); }
  };

  const printDoc = async (d) => {
    // Open the print window synchronously within the user gesture (avoids popup blockers),
    // then load the authenticated blob into it once fetched.
    const w = window.open("", "_blank");
    if (!w) { toast.error("رجاءً اسمح بالنوافذ المنبثقة للطباعة"); return; }
    try {
      w.document.write('<!doctype html><html dir="rtl"><head><meta charset="utf-8"><title>طباعة</title></head><body style="margin:0;font-family:sans-serif;padding:16px">جارٍ التحميل…</body></html>');
      const blob = await fetchBlob(d.id);
      const url = URL.createObjectURL(blob);
      if (isPdf(d.mime, d.filename)) {
        w.location.href = url;
        w.onload = () => { w.focus(); w.print(); };
      } else {
        w.document.open();
        w.document.write(`<!doctype html><html dir="rtl"><head><meta charset="utf-8"><title>${d.filename || "مستند"}</title></head><body style="margin:0;display:flex;justify-content:center"><img src="${url}" style="max-width:100%" onload="window.focus();window.print();" /></body></html>`);
        w.document.close();
      }
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) { try { w.close(); } catch (_) {} toast.error("تعذر طباعة المستند"); }
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
                <span className="font-semibold shrink-0">{docLabel(d.doc_type)}</span>
                {d.passport_no && <span className="text-[#A16207] shrink-0">({d.passport_no})</span>}
                <span className="text-muted-foreground truncate">{d.filename}</span>
              </span>
              <span className="flex items-center gap-3 shrink-0">
                <button onClick={() => openPreview(d)} className="text-[#0A2540] hover:opacity-70" data-testid={`doc-preview-${d.id}`}><Eye className="w-3.5 h-3.5" /></button>
                <button onClick={() => printDoc(d)} className="text-[#0A2540] hover:opacity-70" data-testid={`doc-print-${d.id}`}><Printer className="w-3.5 h-3.5" /></button>
                <button onClick={() => download(d)} className="text-[#0A2540] hover:opacity-70" data-testid={`doc-download-${d.id}`}><Download className="w-3.5 h-3.5" /></button>
                <button onClick={() => del(d.id)} className="text-red-500 hover:text-red-700" data-testid={`doc-delete-${d.id}`}><Trash2 className="w-3.5 h-3.5" /></button>
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <select value={docType} onChange={(e) => setDocType(e.target.value)} data-testid={`doc-type-${registrantIndex}`}
                className="h-8 rounded-md border border-input bg-transparent px-2 text-xs">
          {DOC_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <label className="inline-flex items-center gap-1.5 text-xs bg-[#0A2540] text-white rounded-md px-3 h-8 cursor-pointer hover:bg-[#061A2E]" data-testid={`doc-upload-${registrantIndex}`}>
          <Upload className="w-3.5 h-3.5" /> {busy ? "جارٍ الرفع..." : "رفع ملفات"}
          <input type="file" multiple className="hidden" accept="image/png,image/jpeg,image/webp,application/pdf" onChange={onFile} disabled={busy} />
        </label>
        <label className="inline-flex items-center gap-1.5 text-xs bg-white border border-[#0A2540] text-[#0A2540] rounded-md px-3 h-8 cursor-pointer hover:bg-[#0A2540]/5" data-testid={`doc-camera-${registrantIndex}`}>
          <Camera className="w-3.5 h-3.5" /> مسح / تصوير
          <input type="file" accept="image/*" capture="environment" className="hidden" onChange={onFile} disabled={busy} />
        </label>
        <span className="text-[10px] text-muted-foreground">20MB لكل ملف</span>
      </div>

      <Dialog open={!!preview} onOpenChange={(o) => !o && closePreview()}>
        <DialogContent dir="rtl" className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="doc-preview-dialog">
          <DialogHeader><DialogTitle className="font-head text-[#0A2540] text-base">{preview && `${docLabel(preview.doc.doc_type)} — ${preview.doc.filename}`}</DialogTitle></DialogHeader>
          {preview && (isPdf(preview.doc.mime, preview.doc.filename)
            ? <iframe title="preview" src={preview.url} className="w-full h-[70vh] rounded-lg border" />
            : <img alt="preview" src={preview.url} className="w-full rounded-lg border object-contain max-h-[70vh]" />)}
          {preview && (
            <div className="flex gap-2 justify-end">
              <Button variant="outline" size="sm" onClick={() => printDoc(preview.doc)} data-testid="preview-print-btn"><Printer className="w-4 h-4" /> طباعة</Button>
              <Button size="sm" className="bg-[#0A2540] hover:bg-[#061A2E]" onClick={() => download(preview.doc)} data-testid="preview-download-btn"><Download className="w-4 h-4" /> تنزيل</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
