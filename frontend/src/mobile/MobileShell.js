/** Server-driven mobile shell context: tabs, services, feature flags and badges all come
 *  from `/api/v1/mobile/bootstrap`, so adding a service does not need a store release. */
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import mobileApi from "@/mobile/api/client";
import initPush from "@/mobile/push";

const ShellContext = createContext(null);

export function MobileShellProvider({ children }) {
  const { user } = useAuth();
  const [shell, setShell] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!user) { setShell(null); setLoading(false); return; }
    setLoading(true); setError("");
    try {
      const data = await mobileApi.bootstrap();
      setShell(data);
      initPush(data);            // no-op on web / when push is not configured server-side
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || "تعذّر تحميل إعدادات التطبيق");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => { load(); }, [load]);

  const value = {
    shell, loading, error, reload: load,
    tabs: shell?.tabs || [],
    services: shell?.services || [],
    features: shell?.features || {},
    badges: shell?.badges || {},
    wallet: shell?.wallet || {},
    experience: shell?.experience || null,
    feature: (key) => Boolean(shell?.features?.[key]),
  };
  return <ShellContext.Provider value={value}>{children}</ShellContext.Provider>;
}

export const useShell = () => useContext(ShellContext) || {
  shell: null, loading: false, error: "", tabs: [], services: [], features: {},
  badges: {}, wallet: {}, feature: () => false, reload: () => {},
};
