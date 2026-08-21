import { useEffect, useRef } from "react";
import { Capacitor } from "@capacitor/core";
import { App as CapApp } from "@capacitor/app";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";

// Routes that act as "home" per role — pressing back here asks to exit instead of navigating up.
const ROOT_ROUTES = ["/", "/dashboard", "/admin", "/login"];
const DOUBLE_BACK_MS = 1800;

// Native Android hardware back button. No-op on web (guarded by isNativePlatform).
export function useAndroidBackButton() {
  const location = useLocation();
  const navigate = useNavigate();
  const lastBackAt = useRef(0);

  useEffect(() => {
    if (!Capacitor.isNativePlatform() || Capacitor.getPlatform() !== "android") return;

    let mounted = true;
    const handlePromise = CapApp.addListener("backButton", async ({ canGoBack }) => {
      if (!mounted) return;
      const atRoot = ROOT_ROUTES.includes(location.pathname);

      if (!atRoot) {
        if (canGoBack) navigate(-1);
        else navigate("/dashboard", { replace: true });
        return;
      }

      const now = Date.now();
      if (now - lastBackAt.current <= DOUBLE_BACK_MS) {
        await CapApp.exitApp();
        return;
      }
      lastBackAt.current = now;
      toast("اضغط زر الرجوع مرة أخرى للخروج");
    });

    return () => {
      mounted = false;
      handlePromise.then((h) => h.remove());
    };
  }, [location.pathname, navigate]);
}
