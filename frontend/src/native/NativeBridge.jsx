import { useAndroidBackButton } from "@/native/useAndroidBackButton";
import { useNativeChrome } from "@/native/useNativeChrome";

// Mounted once inside the Router. Wires native behaviors; renders nothing.
export default function NativeBridge() {
  useNativeChrome();
  useAndroidBackButton();
  return null;
}
