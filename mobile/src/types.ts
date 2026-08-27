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
  /** Short reason when VLM timed out / returned bad JSON / empty title. */
  vlm_note?: string;
  match: MatchResult | null;
};

export type PhotoLatency = {
  detection_ms: number | null;
  vlm_ms: number | null;
  matching_ms: number | null;
  total_ms: number;
};

export type PhotoResponse = {
  ok: boolean;
  status?: string;
  message: string;
  photo_id?: number;
  detection_status?: string;
  detection_message?: string;
  zero_detections?: boolean;
  detection_ms?: number | null;
  vlm_ms?: number | null;
  matching_ms?: number | null;
  latency?: PhotoLatency;
  spines: DetectedSpine[];
};

/** Discriminated upload outcomes for honest UI copy. */
export type UploadOutcome =
  | { kind: "success"; data: PhotoResponse }
  | { kind: "zero_spines"; data: PhotoResponse }
  | { kind: "timeout"; message: string }
  | { kind: "network"; message: string }
  | { kind: "upload_failed"; message: string; status?: number };
