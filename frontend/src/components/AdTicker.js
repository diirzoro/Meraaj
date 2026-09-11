import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Megaphone, X, ArrowLeft, Pause, Play } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";

/* Display-only layer over the EXISTING ads API (/ads/public). No billing, no DB writes
   other than the impression/click counters the old slots already used. */

const SESSION_KEY = "meraaj_ad_popup_session";
const DAILY_KEY = "meraaj_ad_popup_daily";
const today = () => new Date().toISOString().slice(0, 10);

const readJson = (k, fallback) => {
  try { return JSON.parse(sessionStorage.getItem(k) || localStorage.getItem(k) || "null") || fallback; }
  catch { return fallback; }
};

const popupSeenThisSession = (id) => (readJson(SESSION_KEY, []) || []).includes(id);
const markPopupSession = (id) => {
  try {
    const list = readJson(SESSION_KEY, []);
    sessionStorage.setItem(SESSION_KEY, JSON.stringify([...new Set([...list, id])]));
  } catch { /* storage disabled */ }
};
const popupSeenToday = (id) => {
  const d = readJson(DAILY_KEY, {});
  return d.day === today() && (d.ids || []).includes(id);
};
const markPopupToday = (id) => {
  try {
    const d = readJson(DAILY_KEY, {});
    const base = d.day === today() ? d : { day: today(), ids: [] };
    localStorage.setItem(DAILY_KEY, JSON.stringify({ ...base, ids: [...new Set([...base.ids, id])] }));
  } catch { /* storage disabled */ }
};

const useLiveAds = (placement, limit) => {
  const [items, setItems] = useState([]);
  useEffect(() => {
    let alive = true;
    api.get(`/ads/public?placement=${placement}&limit=${limit}`)
      .then((r) => alive && setItems(r.data.items || []))
      .catch(() => alive && setItems([]));
    return () => { alive = false; };
  }, [placement, limit]);
  return items;
};

/** Details dialog shared by the ticker and the entry popup. */
const AdDetails = ({ ad, onClose }) => {
  const navigate = useNavigate();
  if (!ad) return null;
  const go = () => {
    if (ad.is_owner) {
      toast.info(ad.owner_note || "هذا إعلانك — لا يمكنك التفاعل مع هذا الإعلان لأنك صاحب الإعلان.");
      return;
    }
    api.post(`/ads/${ad.id}/click?source=public`).catch(() => {});
    onClose();
    if (ad.target_url) window.open(ad.target_url, "_blank", "noopener");
    else if (ad.linked_package_id) navigate(`/market/${ad.linked_package_id}`);
  };
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg p-0 overflow-hidden" dir="rtl" data-testid="ad-details-dialog">
        {ad.image_url && (
          <img src={ad.image_url} alt={ad.title} className="w-full h-44 object-cover" />
        )}
        <div className="p-5 space-y-3 text-right">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-[#D4AF37] text-[#0A2540]">
              {ad.kind_label || "إعلان"}
            </span>
            {ad.is_owner && (
              <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-white text-[#0A2540] border border-[#D4AF37]"
                data-testid="ad-details-owner-badge">إعلانك</span>
            )}
            <span className="text-[10px] text-muted-foreground">{ad.advertiser_name}</span>
            {ad.end_date && (
              <span className="text-[10px] text-muted-foreground">ينتهي {ad.end_date}</span>
            )}
          </div>
          <div className="font-head font-bold text-[#0A2540] text-lg" data-testid="ad-details-title">{ad.title}</div>
          {ad.description_ar && (
            <p className="text-xs text-muted-foreground leading-relaxed">{ad.description_ar}</p>
          )}
          <div className="flex gap-2 pt-1">
            {(ad.target_url || ad.linked_package_id) && (
              <Button className="flex-1 h-11 bg-[#0A2540] hover:bg-[#061A2E]" data-testid="ad-details-cta" onClick={go}>
                {ad.cta_label || "التفاصيل"} <ArrowLeft className="w-4 h-4" />
              </Button>
            )}
            {ad.is_owner && (
              <Button className="flex-1 h-11 bg-[#0A2540]/10 text-[#0A2540] hover:bg-[#0A2540]/20"
                data-testid="ad-details-owner-blocked" onClick={go}>هذا إعلانك</Button>
            )}
            <Button variant="outline" className="flex-1 h-11" data-testid="ad-details-close" onClick={onClose}>
              إغلاق
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

/** News-style marquee of the user's currently allowed, non-expired campaigns. */
export const AdTicker = ({ placement = "dashboard", limit = 8, className = "" }) => {
  const ads = useLiveAds(placement, limit);
  const [open, setOpen] = useState(null);
  const [paused, setPaused] = useState(false);
  const [hidden, setHidden] = useState(false);
  const counted = useRef(false);

  useEffect(() => {
    if (!ads.length || counted.current) return;
    counted.current = true;
    ads.forEach((a) => api.post(`/ads/${a.id}/view?source=public`).catch(() => {}));
  }, [ads]);

  const openAd = useCallback((a) => { setPaused(true); setOpen(a); }, []);
  if (!ads.length || hidden) return null;
  const loop = [...ads, ...ads];   // duplicated once for a seamless RTL loop

  return (
    <div className={className} data-testid="ad-ticker">
      <div className="relative flex items-stretch rounded-xl overflow-hidden bg-[#0A2540] border border-[#0A2540]">
        <div className="flex items-center gap-1.5 px-3 bg-[#D4AF37] text-[#0A2540] flex-shrink-0">
          <Megaphone className="w-3.5 h-3.5" />
          <span className="text-[10px] font-bold whitespace-nowrap hidden sm:inline">إعلانات وعروض</span>
        </div>
        <div className="flex-1 overflow-hidden py-2">
          <div className="flex w-max gap-8 ad-ticker-track"
            style={{ animationDuration: `${Math.max(18, ads.length * 9)}s`,
                     animationPlayState: paused ? "paused" : "running" }}>
            {loop.map((a, i) => (
              <button key={`${a.id}-${i}`} type="button" onClick={() => openAd(a)}
                data-testid={`ad-ticker-item-${a.id}`}
                className="flex items-center gap-2 text-white/90 hover:text-[#D4AF37] transition-colors">
                <span className="w-1.5 h-1.5 rounded-full bg-[#D4AF37] flex-shrink-0" />
                <span className="text-[11px] font-semibold whitespace-nowrap">{a.title}</span>
                {a.description_ar && (
                  <span className="text-[10px] text-white/55 whitespace-nowrap hidden sm:inline">
                    — {a.description_ar.slice(0, 70)}
                  </span>
                )}
                <span className="text-[10px] text-[#D4AF37] whitespace-nowrap">{a.cta_label || "التفاصيل"}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-1 px-2 flex-shrink-0">
          <button type="button" onClick={() => setPaused((p) => !p)} data-testid="ad-ticker-pause"
            className="text-white/60 hover:text-white p-1" aria-label={paused ? "تشغيل" : "إيقاف"}>
            {paused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
          </button>
          <button type="button" onClick={() => setHidden(true)} data-testid="ad-ticker-hide"
            className="text-white/60 hover:text-white p-1" aria-label="إخفاء الشريط">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      {open && <AdDetails ad={open} onClose={() => { setOpen(null); setPaused(false); }} />}
    </div>
  );
};

/** ONE campaign on login, highest priority first (the API already sorts by priority).
 *  policy: "session" (default) = once per login session, "daily" = once per day. */
export const AdEntryPopup = ({ placement = "dashboard", policy = "session" }) => {
  const ads = useLiveAds(placement, 6);
  const [ad, setAd] = useState(null);
  const picked = useRef(false);

  useEffect(() => {
    if (!ads.length || picked.current) return;
    const seen = policy === "daily" ? popupSeenToday : popupSeenThisSession;
    const next = ads.find((a) => !seen(a.id));
    if (!next) return;
    picked.current = true;
    markPopupSession(next.id);
    if (policy === "daily") markPopupToday(next.id);
    api.post(`/ads/${next.id}/view?source=public`).catch(() => {});
    const t = setTimeout(() => setAd(next), 900);   // let the dashboard paint first
    return () => clearTimeout(t);
  }, [ads, policy]);

  if (!ad) return null;
  return <AdDetails ad={ad} onClose={() => setAd(null)} />;
};
