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
    const t = setTimeout(() => navigate(user ? "/m/home" : "/m/login", { replace: true }), 600);
    return () => clearTimeout(t);
  }, [loading, cfg.loading, blocked, user, navigate]);

  return (
    <div dir="rtl" className="min-h-[100dvh] bg-[#0A2540] flex flex-col items-center justify-center text-white px-8"
         data-testid="m-splash">
      <div className="w-20 h-20 rounded-3xl bg-[#D4AF37] flex items-center justify-center mb-5 animate-in">
        <Network className="w-10 h-10 text-[#0A2540]" />
      </div>
      <h1 className="font-head text-2xl font-bold">معراج نتورك</h1>
      <p className="text-white/50 text-xs mt-1">Meraaj Network · تطبيق الخدمات</p>
      {blocked ? (
        <div className="mt-8 text-center" data-testid="m-force-update">
          <p className="font-semibold">يتوفر تحديث إلزامي للتطبيق</p>
          <p className="text-xs text-white/60 mt-1">
            النسخة الحالية {APP_VERSION} · الحد الأدنى المدعوم {cfg.data.min_supported_app}
          </p>
        </div>
      ) : (
        <Loader2 className="w-5 h-5 animate-spin text-white/50 mt-8" />
      )}
    </div>
  );
}
