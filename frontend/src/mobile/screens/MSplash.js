import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Network, Loader2 } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import mobileApi, { APP_VERSION } from "@/mobile/api/client";
import { useAsync } from "@/mobile/ui/kit";

/** Splash: version gate + session restore. Runs before anything money-related. */
export default function MSplash() {
  const navigate = useNavigate();
  const { user, loading } = useAuth();
  const cfg = useAsync(() => mobileApi.config().catch(() => null));

  const blocked = cfg.data?.min_supported_app && APP_VERSION < cfg.data.min_supported_app;

  useEffect(() => {
    if (loading || cfg.loading || blocked) return;
    const t = setTimeout(() => navigate(user ? "/m/home" : "/m/login", { replace: true }), 700);
    return () => clearTimeout(t);
  }, [loading, cfg.loading, blocked, user, navigate]);

  return (
    <div dir="rtl" className="m-app min-h-[100dvh] bg-[#0A2540] flex flex-col items-center justify-center text-white px-8 relative overflow-hidden"
         data-testid="m-splash">
      <div className="absolute -top-20 -start-16 w-72 h-72 rounded-full bg-[#D4AF37]/10" />
      <div className="absolute -bottom-24 -end-16 w-72 h-72 rounded-full bg-[#D4AF37]/[0.07]" />
      <div className="relative flex flex-col items-center m-page-fade">
        <div className="w-24 h-24 rounded-[30px] bg-[#D4AF37] flex items-center justify-center mb-6 shadow-[0_18px_40px_-18px_rgba(212,175,55,0.9)]">
          <Network className="w-12 h-12 text-[#0A2540]" />
        </div>
        <h1 className="font-head text-3xl font-bold">معراج نتورك</h1>
        <p className="text-white/45 text-xs mt-2">Meraaj Network · تطبيق الخدمات</p>
        {blocked ? (
          <div className="mt-10 text-center" data-testid="m-force-update">
            <p className="font-bold">يتوفر تحديث إلزامي للتطبيق</p>
            <p className="text-xs text-white/55 mt-1.5" dir="ltr">
              {APP_VERSION} → {cfg.data.min_supported_app}
            </p>
          </div>
        ) : (
          <Loader2 className="w-5 h-5 animate-spin text-white/40 mt-10" />
        )}
      </div>
      <p className="absolute bottom-[max(1.5rem,env(safe-area-inset-bottom))] text-[10px] text-white/25">
        إصدار {APP_VERSION}
      </p>
    </div>
  );
}
