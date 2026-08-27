import * as ImagePicker from "expo-image-picker";
import { useNavigation } from "@react-navigation/native";
import { useCallback, useEffect, useRef, useState } from "react";
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
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { getApiBaseUrl } from "../api";
import FullImageModal from "../components/FullImageModal";
import type { CaptureNav } from "../navigation";
import {
  checkHealth,
  uploadShelfPhoto,
  uploadShelfPhotoFromUrl,
  type HealthOutcome,
} from "../photos";
import type { UploadOutcome } from "../types";

type BusyPhase = "idle" | "picking" | "uploading";

type HealthState =
  | { status: "loading" }
  | { status: "ok"; detail: string }
  | { status: "error"; detail: string };

const PROGRESS_LINES = [
  "Uploading photo…",
  "Detecting book spines…",
  "Reading titles with OpenAI (usually a few seconds)…",
  "Matching against the catalog…",
  "Still working — hang tight…",
];

function outcomeMessage(outcome: UploadOutcome): string {
  switch (outcome.kind) {
    case "zero_spines":
      return (
        outcome.data.message ||
        "No book spines were detected in this photo. Try a closer, better-lit shot of the shelf edge-on."
      );
    case "timeout":
      return outcome.message;
    case "network":
      return outcome.message;
    case "upload_failed":
      return outcome.message;
    case "success":
      return "";
  }
}

function healthFromOutcome(outcome: HealthOutcome): HealthState {
  if (outcome.kind === "ok") {
    return { status: "ok", detail: outcome.body };
  }
  return { status: "error", detail: outcome.message };
}

export default function CaptureScreen() {
  const navigation = useNavigation<CaptureNav>();
  const insets = useSafeAreaInsets();
  const [busy, setBusy] = useState<BusyPhase>("idle");
  const [progressLine, setProgressLine] = useState(PROGRESS_LINES[0]);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [previewUri, setPreviewUri] = useState<string | null>(null);
  const [urlInput, setUrlInput] = useState("");
  const [userMessage, setUserMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<
    "info" | "error" | "zero" | null
  >(null);
  const [fullImageUri, setFullImageUri] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthState>({ status: "loading" });
  const [healthDetailOpen, setHealthDetailOpen] = useState(false);
  const progressIndex = useRef(0);

  const isBusy = busy !== "idle";
  const apiBase = getApiBaseUrl();

  const refreshHealth = useCallback(async () => {
    setHealth({ status: "loading" });
    setHealthDetailOpen(false);
    const outcome = await checkHealth();
    setHealth(healthFromOutcome(outcome));
  }, []);

  const onHealthPress = useCallback(() => {
    if (health.status === "loading") {
      return;
    }
    if (health.status === "ok") {
      setHealthDetailOpen((open) => !open);
      return;
    }
    void refreshHealth();
  }, [health.status, refreshHealth]);

  useEffect(() => {
    void refreshHealth();
  }, [refreshHealth]);

  useEffect(() => {
    if (busy !== "uploading") {
      return;
    }
    progressIndex.current = 0;
    setProgressLine(PROGRESS_LINES[0]);
    setElapsedSec(0);

    const tick = setInterval(() => {
      setElapsedSec((s) => s + 1);
    }, 1000);

    const rotate = setInterval(() => {
      progressIndex.current = Math.min(
        progressIndex.current + 1,
        PROGRESS_LINES.length - 1
      );
      setProgressLine(PROGRESS_LINES[progressIndex.current]);
    }, 12_000);

    return () => {
      clearInterval(tick);
      clearInterval(rotate);
    };
  }, [busy]);

  const handleOutcome = useCallback(
    (outcome: UploadOutcome, imageUri: string) => {
      if (outcome.kind === "success" || outcome.kind === "zero_spines") {
        const photoId = outcome.data.photo_id;
        if (photoId == null) {
          setMessageKind("error");
          setUserMessage(
            "Server accepted the photo but did not return a photo id."
          );
          return;
        }
        setUserMessage(null);
        setMessageKind(null);
        navigation.navigate("Review", {
          photoId,
          result: outcome.data,
          imageUri,
        });
        return;
      }

      setMessageKind("error");
      setUserMessage(outcomeMessage(outcome));
    },
    [navigation]
  );

  const uploadUri = useCallback(
    async (uri: string, mimeType: string) => {
      setBusy("uploading");
      setUserMessage(null);
      setMessageKind(null);
      setPreviewUri(uri);
      try {
        const outcome = await uploadShelfPhoto(uri, mimeType);
        handleOutcome(outcome, uri);
      } finally {
        setBusy("idle");
      }
    },
    [handleOutcome]
  );

  const submitUrl = useCallback(async () => {
    const url = urlInput.trim();
    if (!url) {
      setMessageKind("error");
      setUserMessage("Paste an image URL first.");
      return;
    }
    setBusy("uploading");
    setUserMessage(null);
    setMessageKind(null);
    setPreviewUri(url);
    try {
      const outcome = await uploadShelfPhotoFromUrl(url);
      handleOutcome(outcome, url);
    } finally {
      setBusy("idle");
    }
  }, [handleOutcome, urlInput]);

  const pickFromDevice = useCallback(async () => {
    setBusy("picking");
    setUserMessage(null);
    try {
      const permission =
        await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        setMessageKind("error");
        setUserMessage(
          "Photo library permission is required to pick a bookshelf photo."
        );
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
      await uploadUri(asset.uri, asset.mimeType ?? "image/jpeg");
    } finally {
      setBusy((b) => (b === "picking" ? "idle" : b));
    }
  }, [uploadUri]);

  const captureWithCamera = useCallback(async () => {
    setBusy("picking");
    setUserMessage(null);
    try {
      const permission = await ImagePicker.requestCameraPermissionsAsync();
      if (!permission.granted) {
        setMessageKind("error");
        setUserMessage("Camera permission is required to photograph a shelf.");
        return;
      }
      const shot = await ImagePicker.launchCameraAsync({ quality: 0.85 });
      if (shot.canceled || !shot.assets[0]) {
        return;
      }
      const asset = shot.assets[0];
      await uploadUri(asset.uri, asset.mimeType ?? "image/jpeg");
    } finally {
      setBusy((b) => (b === "picking" ? "idle" : b));
    }
  }, [uploadUri]);

  return (
    <ScrollView
      contentContainerStyle={[
        styles.container,
        { paddingTop: Math.max(insets.top, 16) + 8 },
      ]}
      keyboardShouldPersistTaps="handled"
    >
      <View style={styles.titleRow}>
        <Text style={styles.title}>Book Spines OCR</Text>
        <Pressable
          onPress={() => navigation.navigate("Library")}
          style={styles.navButton}
        >
          <Text style={styles.navButtonText}>Library</Text>
        </Pressable>
      </View>
      <Text style={styles.subtitle}>
        Photograph a bookshelf. We’ll detect spines, read titles, and match
        them to the catalog.
      </Text>

      <Text style={styles.label}>Backend</Text>
      <Text style={styles.mono}>{apiBase}</Text>
      <Pressable onPress={onHealthPress} hitSlop={6} style={styles.healthBadge}>
        {health.status === "loading" ? (
          <Text style={styles.healthMuted}>checking…</Text>
        ) : health.status === "ok" ? (
          <Text style={styles.healthOk}>
            healthy{healthDetailOpen ? " ▾" : " ▸"}
          </Text>
        ) : (
          <Text style={styles.healthBad}>down — tap to retry</Text>
        )}
      </Pressable>
      {health.status === "ok" && healthDetailOpen ? (
        <Text style={styles.healthDetail}>{health.detail}</Text>
      ) : null}
      {health.status === "error" ? (
        <Text style={styles.healthDetailError}>{health.detail}</Text>
      ) : null}

      <View style={styles.row}>
        <Pressable
          style={[styles.button, isBusy && styles.buttonDisabled]}
          disabled={isBusy}
          onPress={() => void captureWithCamera()}
        >
          <Text style={styles.buttonText}>Take photo</Text>
        </Pressable>
        <Pressable
          style={[
            styles.button,
            styles.buttonSecondary,
            isBusy && styles.buttonDisabled,
          ]}
          disabled={isBusy}
          onPress={() => void pickFromDevice()}
        >
          <Text style={styles.buttonTextSecondary}>Choose from device</Text>
        </Pressable>
      </View>

      <Text style={styles.label}>Or image URL</Text>
      <TextInput
        style={styles.input}
        placeholder="https://example.com/bookshelf.jpg"
        placeholderTextColor="#9ca3af"
        autoCapitalize="none"
        autoCorrect={false}
        value={urlInput}
        onChangeText={setUrlInput}
        editable={!isBusy}
        keyboardType="url"
      />
      <Pressable
        style={[styles.button, isBusy && styles.buttonDisabled]}
        disabled={isBusy}
        onPress={() => void submitUrl()}
      >
        <Text style={styles.buttonText}>Detect from URL</Text>
      </Pressable>

      {busy === "uploading" ? (
        <View style={styles.loadingBox}>
          <ActivityIndicator size="large" color="#111" />
          <Text style={styles.loadingTitle}>{progressLine}</Text>
          <Text style={styles.loadingHint}>
            {elapsedSec}s elapsed · usually a few seconds to a minute depending
            on how many spines we find
          </Text>
        </View>
      ) : null}

      {userMessage ? (
        <View
          style={[
            styles.messageBox,
            messageKind === "zero" && styles.messageZero,
            messageKind === "error" && styles.messageError,
          ]}
        >
          <Text style={styles.messageTitle}>
            {messageKind === "zero"
              ? "No spines found"
              : messageKind === "error"
                ? "Something went wrong"
                : "Note"}
          </Text>
          <Text style={styles.messageBody}>{userMessage}</Text>
        </View>
      ) : null}

      {previewUri && busy !== "uploading" ? (
        <View style={styles.previewWrap}>
          <Text style={styles.label}>Last photo</Text>
          <Pressable onPress={() => setFullImageUri(previewUri)}>
            <Image source={{ uri: previewUri }} style={styles.preview} />
          </Pressable>
        </View>
      ) : null}

      <FullImageModal
        uri={fullImageUri}
        onClose={() => setFullImageUri(null)}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#fff",
    padding: 24,
    paddingBottom: 48,
    gap: 10,
    flexGrow: 1,
  },
  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 14,
    marginBottom: 4,
  },
  title: {
    flexShrink: 1,
    fontSize: 28,
    fontWeight: "600",
  },
  navButton: {
    borderWidth: 1,
    borderColor: "#111",
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: "#111",
  },
  navButtonText: {
    fontSize: 14,
    fontWeight: "600",
    color: "#fff"
  },
  subtitle: {
    color: "#444",
    fontSize: 15,
    lineHeight: 22,
    marginBottom: 8,
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
    color: "#333",
  },
  healthBadge: {
    alignSelf: "flex-start",
    marginTop: 2,
  },
  healthOk: {
    color: "#0a7",
    fontWeight: "700",
    fontSize: 13,
  },
  healthBad: {
    color: "#b00",
    fontWeight: "700",
    fontSize: 13,
  },
  healthMuted: {
    color: "#888",
    fontSize: 13,
  },
  healthDetail: {
    fontFamily: Platform.select({
      ios: "Menlo",
      android: "monospace",
      default: "monospace",
    }),
    fontSize: 12,
    color: "#333",
    backgroundColor: "#f5f5f5",
    padding: 10,
    borderRadius: 6,
  },
  healthDetailError: {
    fontSize: 13,
    color: "#b00",
    lineHeight: 18,
  },
  row: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
    marginTop: 16,
  },
  button: {
    backgroundColor: "#111",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 8,
    alignSelf: "flex-start",
  },
  buttonSecondary: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: "#111",
  },
  buttonDisabled: {
    opacity: 0.45,
  },
  buttonText: {
    color: "#fff",
    fontWeight: "600",
  },
  buttonTextSecondary: {
    color: "#111",
    fontWeight: "600",
  },
  input: {
    borderWidth: 1,
    borderColor: "#ccc",
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    width: "100%",
    color: "#111",
    fontSize: 15,
  },
  loadingBox: {
    marginTop: 20,
    padding: 16,
    backgroundColor: "#f5f5f5",
    borderRadius: 8,
    gap: 10,
    alignItems: "center",
  },
  loadingTitle: {
    fontSize: 15,
    fontWeight: "600",
    textAlign: "center",
  },
  loadingHint: {
    fontSize: 13,
    color: "#555",
    textAlign: "center",
  },
  messageBox: {
    marginTop: 16,
    padding: 14,
    borderRadius: 8,
    backgroundColor: "#f5f5f5",
    gap: 6,
  },
  messageZero: {
    backgroundColor: "#fff8e6",
    borderWidth: 1,
    borderColor: "#e0c56a",
  },
  messageError: {
    backgroundColor: "#fdeeee",
    borderWidth: 1,
    borderColor: "#e0a0a0",
  },
  messageTitle: {
    fontWeight: "600",
    fontSize: 15,
  },
  messageBody: {
    fontSize: 14,
    color: "#333",
    lineHeight: 20,
  },
  previewWrap: {
    marginTop: 16,
    gap: 8,
  },
  preview: {
    width: "100%",
    height: 220,
    resizeMode: "contain",
    backgroundColor: "#f3f3f3",
    borderRadius: 8,
  },
});
