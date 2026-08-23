// Client-side image optimizer: validate → resize (keep aspect ratio, max 1200px on the
// longest side) → compress to WebP (JPEG fallback). Runs once at upload so the STORED
// payload is already small (not a CSS-only fix). Returns an optimized data URL.
export const MAX_DIMENSION = 1200;
export const QUALITY = 0.82; // ~82% — web-optimized, visually clean
const OK_TYPES = /^image\/(png|jpe?g|webp)$/i;

export function optimizeImage(file, { maxDim = MAX_DIMENSION, quality = QUALITY } = {}) {
  return new Promise((resolve, reject) => {
    if (!file || !OK_TYPES.test(file.type)) {
      reject(new Error("صيغة الصورة غير مدعومة (JPG / PNG / WebP فقط)"));
      return;
    }
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      let { width, height } = img;
      if (width > maxDim || height > maxDim) {
        if (width >= height) { height = Math.round(height * (maxDim / width)); width = maxDim; }
        else { width = Math.round(width * (maxDim / height)); height = maxDim; }
      }
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0, width, height);
      let dataUrl = canvas.toDataURL("image/webp", quality);
      if (!dataUrl.startsWith("data:image/webp")) {
        dataUrl = canvas.toDataURL("image/jpeg", quality); // browsers without WebP encode support
      }
      resolve({ dataUrl, width, height });
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("تعذّر قراءة الصورة")); };
    img.src = url;
  });
}
