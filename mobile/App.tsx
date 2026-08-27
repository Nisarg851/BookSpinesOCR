import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useState } from "react";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { getApiBaseUrl } from "./src/api";

type HealthState =
  | { status: "loading" }
  | { status: "ok"; body: string }
  | { status: "error"; message: string };

export default function App() {
  const [health, setHealth] = useState<HealthState>({ status: "loading" });
  const apiBase = getApiBaseUrl();

  const checkHealth = useCallback(async () => {
    setHealth({ status: "loading" });
    const url = `${apiBase}/api/health/`;
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 8000);
      const response = await fetch(url, { signal: controller.signal });
      clearTimeout(timeout);
      const text = await response.text();
      if (!response.ok) {
        setHealth({
          status: "error",
          message: `HTTP ${response.status} from ${url}`,
        });
        return;
      }
      setHealth({ status: "ok", body: text });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Unknown error contacting API";
      setHealth({
        status: "error",
        message: `${message}\nTried ${url}`,
      });
    }
  }, [apiBase]);

  useEffect(() => {
    void checkHealth();
  }, [checkHealth]);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Shelfie</Text>
      <Text style={styles.label}>API</Text>
      <Text style={styles.mono}>{apiBase}</Text>
      <Text style={styles.label}>Health</Text>
      {health.status === "loading" ? (
        <Text>Checking backend…</Text>
      ) : health.status === "ok" ? (
        <Text style={styles.ok}>{health.body}</Text>
      ) : (
        <Text style={styles.error}>{health.message}</Text>
      )}
      <Pressable style={styles.button} onPress={() => void checkHealth()}>
        <Text style={styles.buttonText}>Retry</Text>
      </Pressable>
      <StatusBar style="auto" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#fff",
    alignItems: "flex-start",
    justifyContent: "center",
    padding: 24,
    gap: 8,
  },
  title: {
    fontSize: 28,
    fontWeight: "600",
    marginBottom: 12,
  },
  label: {
    marginTop: 8,
    fontSize: 12,
    color: "#666",
    textTransform: "uppercase",
  },
  mono: {
    fontFamily: Platform.select({ ios: "Menlo", android: "monospace", default: "monospace" }),
    fontSize: 14,
  },
  ok: {
    color: "#0a7",
    fontFamily: Platform.select({ ios: "Menlo", android: "monospace", default: "monospace" }),
  },
  error: {
    color: "#b00",
  },
  button: {
    marginTop: 16,
    backgroundColor: "#111",
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
  },
  buttonText: {
    color: "#fff",
    fontWeight: "600",
  },
});
