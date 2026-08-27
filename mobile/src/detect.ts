import { Platform } from "react-native";

import { getApiBaseUrl } from "./api";

export type DetectedSpine = {
  id: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  confidence: number;
  crop_url: string | null;
  vlm_status: "PENDING" | "OK" | "UNREADABLE";
  vlm_title: string;
  vlm_author: string;
};

export type DetectResponse = {
  ok: boolean;
  status: string;
  message: string;
  detection_ms: number | null;
  vlm_ms: number | null;
  vlm_reads?: number;
  spines: DetectedSpine[];
  photo?: {
    id: number;
    detection_ms: number | null;
    vlm_ms: number | null;
  };
};

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

export async function detectFromUri(
  uri: string,
  mimeType = "image/jpeg"
): Promise<DetectResponse> {
  const form = new FormData();
  await appendImage(form, uri, mimeType);

  const response = await fetch(`${getApiBaseUrl()}/api/detect/`, {
    method: "POST",
    body: form,
  });
  const data = (await response.json()) as DetectResponse;
  if (!response.ok && !data.status) {
    throw new Error(`Detect failed (${response.status})`);
  }
  return data;
}

export async function detectFromUrl(url: string): Promise<DetectResponse> {
  const response = await fetch(`${getApiBaseUrl()}/api/detect/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  const data = (await response.json()) as DetectResponse;
  if (!response.ok && !data.status) {
    throw new Error(`Detect failed (${response.status})`);
  }
  return data;
}
