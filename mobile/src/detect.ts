import { Platform } from "react-native";

import { getApiBaseUrl } from "./api";

export type CatalogBook = {
  id: number;
  title: string;
  author: string;
};

export type MatchResult = {
  id: number;
  catalog_book: CatalogBook | null;
  confidence: number;
  status: string;
};

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
  match: MatchResult | null;
};

export type DetectResponse = {
  ok: boolean;
  status?: string;
  message: string;
  photo_id?: number;
  detection_ms?: number | null;
  vlm_ms?: number | null;
  matching_ms?: number | null;
  latency?: {
    detection_ms: number | null;
    vlm_ms: number | null;
    matching_ms: number | null;
    total_ms: number;
  };
  spines: DetectedSpine[];
  photo?: {
    id: number;
    detection_ms: number | null;
    vlm_ms: number | null;
    matching_ms: number | null;
    latency?: DetectResponse["latency"];
    spines?: DetectedSpine[];
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

  const response = await fetch(`${getApiBaseUrl()}/api/photos/`, {
    method: "POST",
    body: form,
  });
  const data = (await response.json()) as DetectResponse;
  if (!response.ok && data.ok === false && !data.spines) {
    throw new Error(data.message || `Detect failed (${response.status})`);
  }
  return data;
}

export async function detectFromUrl(url: string): Promise<DetectResponse> {
  const response = await fetch(`${getApiBaseUrl()}/api/photos/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  const data = (await response.json()) as DetectResponse;
  if (!response.ok && data.ok === false && !data.spines) {
    throw new Error(data.message || `Detect failed (${response.status})`);
  }
  return data;
}

export async function confirmSpine(
  spineId: number,
  body: Record<string, unknown>
): Promise<unknown> {
  const response = await fetch(
    `${getApiBaseUrl()}/api/spines/${spineId}/confirm/`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }
  );
  return response.json();
}
