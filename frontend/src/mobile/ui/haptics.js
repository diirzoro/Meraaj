/** Haptics — dynamic import, fully no-op on web or when the plugin is missing.
 *  Never throws, never blocks a user action. */
let mod = null;
let tried = false;

async function plugin() {
  if (!window.Capacitor?.isNativePlatform?.()) return null;
  if (tried) return mod;
  tried = true;
  try {
    mod = await import("@capacitor/haptics");
  } catch {
    mod = null;
  }
  return mod;
}

/** kind: "light" | "medium" | "success" | "warning" | "error" */
export async function haptic(kind = "light") {
  const m = await plugin();
  if (!m) return;
  try {
    if (kind === "success") return m.Haptics.notification({ type: m.NotificationType.Success });
    if (kind === "warning") return m.Haptics.notification({ type: m.NotificationType.Warning });
    if (kind === "error") return m.Haptics.notification({ type: m.NotificationType.Error });
    return m.Haptics.impact({ style: kind === "medium" ? m.ImpactStyle.Medium : m.ImpactStyle.Light });
  } catch {
    /* haptics are a nicety, never a dependency */
  }
}

export default haptic;
