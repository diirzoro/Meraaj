import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { IDLE_TIMEOUT_MS, RESUME_KEY } from "@/config";

// Routes that must never be auto-locked or hijacked by the refresh redirect
const skip = (p) => p.startsWith("/embed") || p === "/login" || p === "/register";

export default function SessionManager() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const refreshHandled = useRef(false);

  // (2) Full browser refresh / hard reload -> send an authenticated user to their home.
  // Only fires on an actual document reload; SPA navigation, deep links, SSO and login
  // redirects (navigation type "navigate"/"back_forward") are left untouched.
  useEffect(() => {
    if (loading || refreshHandled.current) return;
    refreshHandled.current = true;
    let isReload = false;
    try {
      const nav = performance.getEntriesByType("navigation")[0];
      isReload = nav ? nav.type === "reload"
                     : (performance.navigation && performance.navigation.type === 1);
    } catch { /* noop */ }
    if (!isReload || !user) return;
    const p = window.location.pathname;
    if (skip(p)) return;
    const home = user.role === "super_admin" ? "/admin" : "/dashboard";
    if (p !== home) navigate(home, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, user]);

  // (1) Idle session auto-lock: reset on real activity; on expiry save the current
  // deep route then log out through the existing auth flow.
  useEffect(() => {
    if (!user || location.pathname.startsWith("/embed")) return;
    const ms = Number(localStorage.getItem("meraaj_idle_ms")) || IDLE_TIMEOUT_MS; // QA override
    let timer;
    const expire = async () => {
      const path = location.pathname + location.search;
      if (!skip(location.pathname) && location.pathname !== "/") {
        try { localStorage.setItem(RESUME_KEY, path); } catch { /* noop */ }
      }
      await logout();
      navigate("/login", { replace: true });
    };
    const reset = () => { clearTimeout(timer); timer = setTimeout(expire, ms); };
    const events = ["mousemove", "mousedown", "keydown", "scroll", "touchstart", "click"];
    events.forEach((e) => window.addEventListener(e, reset, { passive: true }));
    reset();
    return () => { clearTimeout(timer); events.forEach((e) => window.removeEventListener(e, reset)); };
  }, [user, location.pathname, location.search, logout, navigate]);

  return null;
}
