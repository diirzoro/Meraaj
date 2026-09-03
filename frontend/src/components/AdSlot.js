import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Megaphone } from "lucide-react";

/** Public advertisement slot. Shows only approved + active + in-window campaigns.
 *  Counts one view per render and one click on interaction. */
export const AdSlot = ({ placement = "homepage", limit = 3, className = "" }) => {
  const [ads, setAds] = useState([]);

  useEffect(() => {
    let alive = true;
    api.get(`/ads/public?placement=${placement}&limit=${limit}`)
      .then((r) => {
        if (!alive) return;
        const items = r.data.items || [];
        setAds(items);
        items.forEach((a) => api.post(`/ads/${a.id}/view`).catch(() => {}));
      })
      .catch(() => setAds([]));
    return () => { alive = false; };
  }, [placement, limit]);

  if (!ads.length) return null;

  const go = (a) => {
    api.post(`/ads/${a.id}/click`).catch(() => {});
    if (a.target_url) window.open(a.target_url, "_blank", "noopener");
  };

  return (
    <div className={`grid gap-4 ${ads.length > 1 ? "sm:grid-cols-2 lg:grid-cols-3" : ""} ${className}`}
      data-testid={`ad-slot-${placement}`}>
      {ads.map((a) => (
        <button key={a.id} type="button" onClick={() => go(a)} data-testid={`public-ad-${a.id}`}
          className="text-right bg-white rounded-2xl border card-shadow overflow-hidden hover:shadow-lg transition-shadow group">
          {a.image_url ? (
            <div className="h-32 w-full overflow-hidden bg-[#F4F6F8]">
              <img src={a.image_url} alt={a.title}
                className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
            </div>
          ) : (
            <div className="h-2 w-full bg-[#D4AF37]" />
          )}
          <div className="p-4">
            <div className="flex items-center gap-2 mb-1">
              <Megaphone className="w-3.5 h-3.5 text-[#D4AF37]" />
              <span className="text-[10px] text-muted-foreground">
                {a.kind === "promotion" ? "عرض ترويجي" : "إعلان"} • {a.advertiser_name}
              </span>
            </div>
            <div className="font-head font-bold text-[#0A2540] text-sm mb-1">{a.title}</div>
            {a.description_ar && (
              <div className="text-xs text-muted-foreground line-clamp-2">{a.description_ar}</div>
            )}
            <div className="mt-3 text-[11px] font-semibold text-[#0A2540] underline">{a.cta_label}</div>
          </div>
        </button>
      ))}
    </div>
  );
};
