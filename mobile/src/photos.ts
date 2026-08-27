import { Platform } from "react-native";

import { getApiBaseUrl } from "./api";
import type { PhotoResponse, UploadOutcome } from "./types";

/** Pipeline can take minutes (multi-spine VLM). Abort before the UI looks hung forever. */
const UPLOAD_TIMEOUT_MS = 10 * 60 * 1000;

async function appendImage(
  form: FormData,
  uri: string,
  mimeType: string
): Promise<void> {
  if (Platform.OS === "web") {
    const blob = await fetch(uri).then((r) => r.blob());
    form.append("image", blob, "shelf.jpg");
    return;
  }
  form.append("image", {
    uri,
    name: "shelf.jpg",
    type: mimeType,
  } as unknown as Blob);
}

function isZeroSpines(data: PhotoResponse): boolean {
  if (data.zero_detections) {
    return true;
  }
  if (data.detection_status === "zero_detections") {
    return true;
  }
  return Array.isArray(data.spines) && data.spines.length === 0 && data.ok;
}

/**
 * POST /api/photos/ with a local image URI.
 * Returns a typed outcome so the capture screen can show distinct copy.
 */
export async function uploadShelfPhoto(
  uri: string,
  mimeType = "image/jpeg"
): Promise<UploadOutcome> {
  const url = `${getApiBaseUrl()}/api/photos/`;
  const form = new FormData();
  await appendImage(form, uri, mimeType);

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: "POST",
      body: form,
      signal: controller.signal,
    });

    let data: PhotoResponse;
    try {
      data = (await response.json()) as PhotoResponse;
    } catch {
      return {
        kind: "upload_failed",
        status: response.status,
        message: `Server returned a non-JSON response (HTTP ${response.status}). Is Django running at ${getApiBaseUrl()}?`,
      };
    }

    if (!response.ok) {
      return {
        kind: "upload_failed",
        status: response.status,
        message:
          data.message ||
          data.detection_message ||
          `Upload failed (HTTP ${response.status}).`,
      };
    }

    if (isZeroSpines(data)) {
      return { kind: "zero_spines", data };
    }

    return { kind: "success", data };
  } catch (err) {
    if (
      (err instanceof Error && err.name === "AbortError") ||
      (typeof DOMException !== "undefined" &&
        err instanceof DOMException &&
        err.name === "AbortError")
    ) {
      return {
        kind: "timeout",
        message:
          "Timed out waiting for the server. Detection plus spine reading can take several minutes — check that Django is still running, then try again.",
      };
    }
    const detail = err instanceof Error ? err.message : "Unknown network error";
    return {
      kind: "network",
      message: `Couldn’t reach ${getApiBaseUrl()}. ${detail}`,
    };
  } finally {
    clearTimeout(timeout);
  }
}
