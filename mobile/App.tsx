import { StatusBar } from "expo-status-bar";
import * as ImagePicker from "expo-image-picker";
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Image,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { getApiBaseUrl } from "./src/api";
import {
  detectFromUri,
  detectFromUrl,
  type DetectedSpine,
  type DetectResponse,
} from "./src/detect";

type HealthState =
  | { status: "loading" }
  | { status: "ok"; body: string }
  | { status: "error"; message: string };

export default function App() {
  const [health, setHealth] = useState<HealthState>({ status: "loading" });
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [urlInput, setUrlInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DetectResponse | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
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

  const runDetect = useCallback(async (fn: () => Promise<DetectResponse>) => {
    setBusy(true);
    setActionError(null);
    setResult(null);
    try {
      const data = await fn();
      setResult(data);
      if (!data.ok && data.status !== "zero_detections") {
        setActionError(data.message || `Detection status: ${data.status}`);
      }
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Detection request failed"
      );
    } finally {
      setBusy(false);
    }
  }, []);

  const pickFromLibrary = useCallback(async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setActionError("Photo library permission is required.");
      return;
    }
    const picked = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.85,
    });
    if (picked.canceled || !picked.assets[0]) {
      return;
    }
    const asset = picked.assets[0];
    setImageUri(asset.uri);
    await runDetect(() =>
      detectFromUri(asset.uri, asset.mimeType ?? "image/jpeg")
    );
  }, [runDetect]);

  const captureWithCamera = useCallback(async () => {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      setActionError("Camera permission is required.");
      return;
    }
    const shot = await ImagePicker.launchCameraAsync({ quality: 0.85 });
    if (shot.canceled || !shot.assets[0]) {
      return;
    }
    const asset = shot.assets[0];
    setImageUri(asset.uri);
    await runDetect(() =>
      detectFromUri(asset.uri, asset.mimeType ?? "image/jpeg")
    );
  }, [runDetect]);

  const submitUrl = useCallback(async () => {
    const url = urlInput.trim();
    if (!url) {
      setActionError("Paste an image URL first.");
      return;
    }
    setImageUri(url);
    await runDetect(() => detectFromUrl(url));
  }, [runDetect, urlInput]);

  return (
    <ScrollView contentContainerStyle={styles.container}>
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

      <Text style={styles.section}>Detect books</Text>
      <Text style={styles.hint}>
        Camera, photo library, or image URL. Originals are not kept on the
        server — only crop regions for later reading.
      </Text>

      <View style={styles.row}>
        <Pressable
          style={[styles.button, busy && styles.buttonDisabled]}
          disabled={busy}
          onPress={() => void captureWithCamera()}
        >
          <Text style={styles.buttonText}>Camera</Text>
        </Pressable>
        <Pressable
          style={[styles.button, busy && styles.buttonDisabled]}
          disabled={busy}
          onPress={() => void pickFromLibrary()}
        >
          <Text style={styles.buttonText}>Photo library</Text>
        </Pressable>
      </View>

      <TextInput
        style={styles.input}
        placeholder="https://example.com/bookshelf.jpg"
        autoCapitalize="none"
        autoCorrect={false}
        value={urlInput}
        onChangeText={setUrlInput}
        editable={!busy}
      />
      <Pressable
        style={[styles.button, busy && styles.buttonDisabled]}
        disabled={busy}
        onPress={() => void submitUrl()}
      >
        <Text style={styles.buttonText}>Detect from URL</Text>
      </Pressable>

      {busy ? (
        <View style={styles.busyRow}>
          <ActivityIndicator />
          <Text>Running local YOLO detection…</Text>
        </View>
      ) : null}

      {actionError ? <Text style={styles.error}>{actionError}</Text> : null}

      {imageUri ? (
        <View style={styles.previewWrap}>
          <Text style={styles.label}>Preview</Text>
          <Image source={{ uri: imageUri }} style={styles.preview} />
          {result?.spines?.length ? (
            <BoxOverlay spines={result.spines} />
          ) : null}
        </View>
      ) : null}

      {result ? (
        <View style={styles.results}>
          <Text style={styles.label}>Result</Text>
          <Text style={styles.mono}>
            status={result.status} · detection_ms={result.detection_ms ?? "—"} ·
            spines={result.spines.length}
          </Text>
          <Text>{result.message}</Text>
          {result.spines.map((spine) => (
            <View key={spine.id} style={styles.spineRow}>
              {spine.crop_url ? (
                <Image
                  source={{ uri: spine.crop_url }}
                  style={styles.crop}
                />
              ) : (
                <View style={[styles.crop, styles.cropPlaceholder]} />
              )}
              <View style={styles.spineMeta}>
                <Text style={styles.mono}>#{spine.id}</Text>
                <Text style={styles.mono}>
                  conf={spine.confidence.toFixed(3)}
                </Text>
                <Text style={styles.mono}>
                  [{spine.x1.toFixed(0)}, {spine.y1.toFixed(0)}] → [
                  {spine.x2.toFixed(0)}, {spine.y2.toFixed(0)}]
                </Text>
              </View>
            </View>
          ))}
        </View>
      ) : null}

      <StatusBar style="auto" />
    </ScrollView>
  );
}

/** Simple list of boxes — full image overlay needs measured layout; crops are the proof. */
function BoxOverlay({ spines }: { spines: DetectedSpine[] }) {
  return (
    <Text style={styles.hint}>
      {spines.length} region(s) detected — crops listed below
    </Text>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#fff",
    padding: 24,
    paddingBottom: 48,
    gap: 8,
  },
  title: {
    fontSize: 28,
    fontWeight: "600",
    marginBottom: 12,
  },
  section: {
    marginTop: 20,
    fontSize: 18,
    fontWeight: "600",
  },
  hint: {
    color: "#555",
    marginBottom: 4,
  },
  label: {
    marginTop: 8,
    fontSize: 12,
    color: "#666",
    textTransform: "uppercase",
  },
  mono: {
    fontFamily: Platform.select({
      ios: "Menlo",
      android: "monospace",
      default: "monospace",
    }),
    fontSize: 13,
  },
  ok: {
    color: "#0a7",
    fontFamily: Platform.select({
      ios: "Menlo",
      android: "monospace",
      default: "monospace",
    }),
  },
  error: {
    color: "#b00",
    marginTop: 8,
  },
  row: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 8,
  },
  button: {
    backgroundColor: "#111",
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
    alignSelf: "flex-start",
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    color: "#fff",
    fontWeight: "600",
  },
  input: {
    borderWidth: 1,
    borderColor: "#ccc",
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginTop: 8,
    width: "100%",
  },
  busyRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 12,
  },
  previewWrap: {
    marginTop: 12,
    gap: 8,
  },
  preview: {
    width: "100%",
    height: 220,
    resizeMode: "contain",
    backgroundColor: "#f3f3f3",
    borderRadius: 8,
  },
  results: {
    marginTop: 16,
    gap: 10,
  },
  spineRow: {
    flexDirection: "row",
    gap: 12,
    alignItems: "center",
  },
  crop: {
    width: 56,
    height: 96,
    borderRadius: 4,
    backgroundColor: "#eee",
  },
  cropPlaceholder: {
    borderWidth: 1,
    borderColor: "#ccc",
  },
  spineMeta: {
    flex: 1,
    gap: 2,
  },
});
