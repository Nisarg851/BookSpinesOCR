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
  View,
} from "react-native";

import { getApiBaseUrl } from "../api";
import type { CaptureNav } from "../navigation";
import { uploadShelfPhoto } from "../photos";
import type { UploadOutcome } from "../types";

type BusyPhase = "idle" | "picking" | "uploading";

const PROGRESS_LINES = [
  "Uploading photo…",
  "Detecting book spines…",
  "Reading titles with VLM (this can take a minute per spine)…",
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

export default function CaptureScreen() {
  const navigation = useNavigation<CaptureNav>();
  const [busy, setBusy] = useState<BusyPhase>("idle");
  const [progressLine, setProgressLine] = useState(PROGRESS_LINES[0]);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [previewUri, setPreviewUri] = useState<string | null>(null);
  const [userMessage, setUserMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<
    "info" | "error" | "zero" | null
  >(null);
  const progressIndex = useRef(0);

  const isBusy = busy !== "idle";
  const apiBase = getApiBaseUrl();

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

  const pickFromLibrary = useCallback(async () => {
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
      contentContainerStyle={styles.container}
      keyboardShouldPersistTaps="handled"
    >
      <Text style={styles.title}>Shelfie</Text>
      <Text style={styles.subtitle}>
        Photograph a bookshelf. We’ll detect spines, read titles, and match
        them to the catalog.
      </Text>

      <Text style={styles.label}>Backend</Text>
      <Text style={styles.mono}>{apiBase}</Text>

      <View style={styles.row}>
        <Pressable
          style={[styles.button, isBusy && styles.buttonDisabled]}
          disabled={isBusy}
          onPress={() => void captureWithCamera()}
        >
          <Text style={styles.buttonText}>Take photo</Text>
        </Pressable>
        <Pressable
          style={[styles.button, styles.buttonSecondary, isBusy && styles.buttonDisabled]}
          disabled={isBusy}
          onPress={() => void pickFromLibrary()}
        >
          <Text style={styles.buttonTextSecondary}>Choose from library</Text>
        </Pressable>
      </View>

      {busy === "uploading" ? (
        <View style={styles.loadingBox}>
          <ActivityIndicator size="large" color="#111" />
          <Text style={styles.loadingTitle}>{progressLine}</Text>
          <Text style={styles.loadingHint}>
            {elapsedSec}s elapsed · usually 30s–a few minutes depending on how
            many spines we find
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
          <Image source={{ uri: previewUri }} style={styles.preview} />
        </View>
      ) : null}
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
  title: {
    fontSize: 28,
    fontWeight: "600",
    marginBottom: 4,
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
