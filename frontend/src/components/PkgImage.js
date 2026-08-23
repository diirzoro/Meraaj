import { useState } from "react";
import { Landmark } from "lucide-react";

// Package image with graceful fallback: shows a placeholder when there is no src
// OR when the image fails to load (e.g. a dead external Rahaal URL) instead of the
// browser's broken-image glyph.
export function PkgImage({ src, alt = "", iconClass = "w-12 h-12 text-white/15" }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return (
      <div className="w-full h-full flex items-center justify-center">
        <Landmark className={iconClass} />
      </div>
    );
  }
  return <img src={src} alt={alt} onError={() => setFailed(true)} className="w-full h-full object-cover" />;
}
