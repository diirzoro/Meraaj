/** PUSH ARCHITECTURE (client side).
 *
 *  The Capacitor push plugin is imported DYNAMICALLY and everything is a no-op when it is
 *  absent (web preview) or when the server reports push is not configured. Nothing here
 *  fakes a delivery, and in-app notifications keep working regardless.
 *  EXTERNAL CONFIGURATION REQUIRED: FCM (Android) / APNs (iOS) credentials.
 */
import mobileApi from "@/mobile/api/client";

export async function initPush(shell) {
  const isNative = window.Capacitor?.isNativePlatform?.();
  if (!isNative) return { enabled: false, reason: "not_native" };
  if (!shell?.features?.push_notifications) {
    return { enabled: false, reason: "server_push_not_configured" };
  }
  try {
    const mod = await import(/* webpackIgnore: true */ "@capacitor/push-notifications");
    const Push = mod.PushNotifications;
    const perm = await Push.checkPermissions();
    const granted = perm.receive === "granted"
      ? true
      : (await Push.requestPermissions()).receive === "granted";
    if (!granted) return { enabled: false, reason: "permission_denied" };
    Push.addListener("registration", async (t) => {
      try {
        await mobileApi.registerDevice({ token: t.value, platform: "android" });
      } catch { /* the app must keep working even if token sync fails */ }
    });
    await Push.register();
    return { enabled: true };
  } catch (e) {
    return { enabled: false, reason: "plugin_unavailable" };
  }
}

export default initPush;
