import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Megaphone, ArrowLeft } from "lucide-react";

/** Frequency cap: the same campaign is not shown to the same visitor more than
 *  MAX_PER_DAY times per placement per day. Stored locally, no PII, no DB write. */
const MAX_PER_DAY = 3;
const capKey = "meraaj_ad_caps";
const today = () => new Date().toISOString().slice(0, 10);

const readCaps = () => {
  try {
    const raw = JSON.parse(localStorage.getItem(capKey) || "{}");
    return raw.day === today() ? raw : { day: today(), seen: {} };
  } catch { return { day: today(), seen: {} }; }
};

const bumpCap = (key) => {
  const caps = readCaps();
  caps.seen[key] = (caps.seen[key] || 0) + 1;
  try { localStorage.setItem(capKey, JSON.stringify(caps)); } catch { /* storage disabled */ }
};

const underCap = (key) => (readCaps().seen[key] || 0) < MAX_PER_DAY;

/** Public advertisement slot. Only approved + active + in-window campaigns are returned
 *  by the API. Impressions/clicks are counted ONLY from here (source=public).
 *  variant: "banner" (homepage) | "card" (programs list) | "compact" (program details) */
export const AdSlot = ({ placement = "homepage", limit = 3, variant, className = "" }) => {
  const [ads, setAds] = useState([]);
  const kind = variant || (placement === "homepage" ? "banner"
    : placement === "program_details" ? "compact" : "card");

  useEffect(() => {
    let alive = true;
    api.get(`/ads/public?placement=${placement}&limit=${limit}`)
      .then((r) => {
        if (!alive) return;
        const allowed = (r.data.items || []).filter((a) => underCap(`${placement}:${a.id}`));
        setAds(allowed);
        allowed.forEach((a) => {
          bumpCap(`${placement}:${a.id}`);
          api.post(`/ads/${a.id}/view?source=public`).catch(() => {});
        });
      })
      .catch(() => setAds([]));
    return () => { alive = false; };
  }, [placement, limit]);

  const go = (a) => {
    api.post(`/ads/${a.id}/click?source=public`).catch(() => {});
    if (a.target_url) window.open(a.target_url, "_blank", "noopener");
  };

  if (!ads.length) return null;
  return (
    <div className={className} data-testid={`ad-slot-${placement}`}>
      {kind === "banner" && <BannerRow ads={ads} onGo={go} />}
      {kind === "card" && <CardRow ads={ads} onGo={go} />}
      {kind === "compact" && <CompactRow ads={ads} onGo={go} />}
    </div>
  );
};

/** Admin-only renderer: identical templates, zero counting. */
export const AdPreview = ({ ad, variant = "banner" }) => {
  const items = useMemo(() => [{
    id: ad.id || "preview", title: ad.title || "عنوان الإعلان",
    description_ar: ad.description_ar, image_url: ad.image_url,
    advertiser_name: ad.advertiser_name || "اسم المعلن",
    cta_label: ad.cta_label || "التفاصيل", end_date: ad.end_date,
    kind_label: ad.kind === "promotion" ? "عرض ترويجي" : "إعلان",
  }], [ad]);
  const noop = () => {};
  return (
    <div data-testid={`ad-preview-${variant}`}>
      {variant === "banner" && <BannerRow ads={items} onGo={noop} />}
      {variant === "card" && <CardRow ads={items} onGo={noop} />}
      {variant === "compact" && <CompactRow ads={items} onGo={noop} />}
    </div>
  );
};

const Tag = ({ a }) => (
  <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-[#D4AF37] text-[#0A2540] whitespace-nowrap">
    {a.kind_label || "إعلان"}
  </span>
);

const Expiry = ({ a }) => (a.end_date ? (
  <span className="text-[10px] text-muted-foreground whitespace-nowrap">ينتهي {a.end_date}</span>
) : null);

/* 1) Homepage banner — wide, image on the left, content right (RTL) */
const BannerRow = ({ ads, onGo }) => (
  <div className="space-y-3">
    {ads.map((a) => (
      <button key={a.id} type="button" onClick={() => onGo(a)} data-testid={`public-ad-${a.id}`}
        className="w-full text-right bg-[#0A2540] rounded-2xl overflow-hidden flex flex-col sm:flex-row-reverse items-stretch hover:shadow-xl transition-shadow group">
        {a.image_url && (
          <div className="sm:w-2/5 h-36 sm:h-auto overflow-hidden bg-[#061A2E]">
            <img src={a.image_url} alt={a.title} loading="lazy"
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700" />
          </div>
        )}
        <div className="flex-1 p-5 sm:p-7">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <Tag a={a} />
            <span className="text-[10px] text-white/60">{a.advertiser_name}</span>
            <Expiry a={a} />
          </div>
          <div className="font-head font-bold text-white text-lg sm:text-xl mb-1.5">{a.title}</div>
          {a.description_ar && (
            <div className="text-xs sm:text-sm text-white/70 max-w-xl line-clamp-2">{a.description_ar}</div>
          )}
          <span className="inline-flex items-center gap-1.5 mt-4 text-xs font-bold text-[#D4AF37]">
            {a.cta_label} <ArrowLeft className="w-3.5 h-3.5 group-hover:-translate-x-1 transition-transform" />
          </span>
        </div>
      </button>
    ))}
  </div>
);

/* 2) Programs list — horizontal ad card matching the marketplace cards */
const CardRow = ({ ads, onGo }) => (
  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
    {ads.map((a) => (
      <button key={a.id} type="button" onClick={() => onGo(a)} data-testid={`public-ad-${a.id}`}
        className="text-right bg-white rounded-xl border-2 border-dashed border-[#D4AF37]/60 card-shadow overflow-hidden flex items-center gap-3 p-3 hover:border-[#D4AF37] transition-colors group">
        {a.image_url ? (
          <img src={a.image_url} alt={a.title} loading="lazy"
            className="w-16 h-16 rounded-lg object-cover flex-shrink-0" />
        ) : (
          <div className="w-16 h-16 rounded-lg bg-[#F4F6F8] flex items-center justify-center flex-shrink-0">
            <Megaphone className="w-5 h-5 text-[#D4AF37]" />
          </div>
        )}
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5 mb-1"><Tag a={a} /><Expiry a={a} /></span>
          <span className="block font-bold text-[#0A2540] text-xs truncate">{a.title}</span>
          <span className="block text-[10px] text-muted-foreground truncate">{a.advertiser_name}</span>
          <span className="block text-[10px] font-semibold text-[#0A2540] underline mt-1 group-hover:text-[#D4AF37]">
            {a.cta_label}
          </span>
        </span>
      </button>
    ))}
  </div>
);

/* 3) Program details — compact single line, low visual weight */
const CompactRow = ({ ads, onGo }) => (
  <div className="space-y-2">
    {ads.map((a) => (
      <button key={a.id} type="button" onClick={() => onGo(a)} data-testid={`public-ad-${a.id}`}
        className="w-full text-right bg-[#F4F6F8] rounded-lg px-3 py-2 flex items-center gap-2 hover:bg-[#EDF1F5] transition-colors">
        <Tag a={a} />
        <span className="text-[11px] font-semibold text-[#0A2540] truncate flex-1">{a.title}</span>
        <span className="text-[10px] text-muted-foreground hidden sm:inline">{a.advertiser_name}</span>
        <span className="text-[10px] font-bold text-[#0A2540] underline whitespace-nowrap">{a.cta_label}</span>
      </button>
    ))}
  </div>
);
