import { Platform } from "react-native";

/**
 * Where the Django API lives for this device.
 *
 * Override with EXPO_PUBLIC_API_URL (see .env.example) when using a
 * physical phone — localhost on the device is the phone, not your PC.
 */
export function getApiBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_API_URL?.replace(/\/$/, "");
  if (fromEnv) {
    return fromEnv;
  }
  if (Platform.OS === "android") {
    return "http://10.0.2.2:8000";
  }
  return "http://127.0.0.1:8000";
}
