import { Platform } from "react-native";

import { getApiBaseUrl } from "./api";
import type { PhotoResponse, UploadOutcome } from "./types";

/** Pipeline can take minutes (multi-spine VLM). Abort before the UI looks hung forever. */
const UPLOAD_TIMEOUT_MS = 10 * 60 * 1000;
const HEALTH_TIMEOUT_MS = 8000;

export type HealthOutcome =
  | { kind: "ok"; body: string }
  | { kind: "error"; message: string };

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

function failureMessage(data: PhotoResponse, httpStatus: number): string {
  const det = data.detection_status;
  if (det === "unreadable_image") {
    return (
      data.detection_message ||
      data.message ||
      "That file isn’t a readable image (corrupt or wrong format)."
    );
  }
  if (det === "model_load_failed") {
    return (
      data.detection_message ||
      data.message ||
      "Local book detection failed to load or run on this image."
    );
  }
  if (det === "timeout") {
    return (
      data.detection_message ||
      data.message ||
      "Book detection timed out on the server."
    );
  }
  return (
    data.message ||
    data.detection_message ||
    `Upload failed (HTTP ${httpStatus}).`
  );
}

async function parsePhotoResponse(
  response: Response
): Promise<UploadOutcome> {
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
      message: failureMessage(data, response.status),
    };
  }

  if (isZeroSpines(data)) {
    return { kind: "zero_spines", data };
  }

  return { kind: "success", data };
}

function mapFetchError(err: unknown): UploadOutcome {
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
}

export async function checkHealth(): Promise<HealthOutcome> {
  const url = `${getApiBaseUrl()}/api/health/`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
  try {
    const response = await fetch(url, { signal: controller.signal });
    const text = await response.text();
    if (!response.ok) {
      return {
        kind: "error",
        message: `HTTP ${response.status}`,
      };
    }
    return { kind: "ok", body: text };
  } catch (err) {
    if (
      (err instanceof Error && err.name === "AbortError") ||
      (typeof DOMException !== "undefined" &&
        err instanceof DOMException &&
        err.name === "AbortError")
    ) {
      return { kind: "error", message: "timed out" };
    }
    const detail = err instanceof Error ? err.message : "unreachable";
    return { kind: "error", message: detail };
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * POST /api/photos/ with a local image URI.
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
    return await parsePhotoResponse(response);
  } catch (err) {
    return mapFetchError(err);
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * POST /api/photos/ with a remote image URL (server downloads it).
 */
export async function uploadShelfPhotoFromUrl(
  imageUrl: string
): Promise<UploadOutcome> {
  const trimmed = imageUrl.trim();
  if (!trimmed) {
    return {
      kind: "upload_failed",
      message: "Paste an image URL first.",
    };
  }
  if (!/^https?:\/\//i.test(trimmed)) {
    return {
      kind: "upload_failed",
      message: "Image URL must start with http:// or https://",
    };
  }

  const url = `${getApiBaseUrl()}/api/photos/`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: trimmed }),
      signal: controller.signal,
    });
    return await parsePhotoResponse(response);
  } catch (err) {
    return mapFetchError(err);
  } finally {
    clearTimeout(timeout);
  }
}
