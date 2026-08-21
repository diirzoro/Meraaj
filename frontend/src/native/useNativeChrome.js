import { useEffect } from "react";
import { Capacitor } from "@capacitor/core";
import { StatusBar, Style } from "@capacitor/status-bar";
import { SplashScreen } from "@capacitor/splash-screen";

// Configures the native status bar / splash for a clean full-app feel.
// No-op on web (guarded by isNativePlatform).
export function useNativeChrome() {
  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;

    document.documentElement.dir = "rtl";
    document.documentElement.lang = "ar";
    document.body.classList.add("cap-native");

    (async () => {
      try {
        await StatusBar.setOverlaysWebView({ overlay: false });
        await StatusBar.setStyle({ style: Style.Dark }); // dark navy bar => light icons
        if (Capacitor.getPlatform() === "android") {
          await StatusBar.setBackgroundColor({ color: "#0A2540" });
        }
      } catch (_) { /* status bar not available */ }
      // Hide the splash only after native chrome is ready (config has launchAutoHide:false).
      try { await SplashScreen.hide({ fadeOutDuration: 250 }); } catch (_) {}
    })();
  }, []);
}
