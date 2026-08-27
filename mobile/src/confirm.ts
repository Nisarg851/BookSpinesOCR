import { getApiBaseUrl } from "./api";
import type { CatalogBook } from "./types";

export type ConfirmAction =
  | { action: "accept" }
  | { action: "discard" }
  | { action: "correct"; catalog_book_id: number }
  | { action: "correct"; title: string; author: string };

export type ConfirmResponse = {
  ok: boolean;
  message?: string;
  match?: {
    id: number;
    status: string;
    confidence: number;
    catalog_book_id: number | null;
  };
  library_entry?: {
    id: number;
    title: string;
    author: string;
  } | null;
};

export async function confirmSpine(
  spineId: number,
  body: ConfirmAction
): Promise<ConfirmResponse> {
  const response = await fetch(
    `${getApiBaseUrl()}/api/spines/${spineId}/confirm/`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }
  );
  let data: ConfirmResponse;
  try {
    data = (await response.json()) as ConfirmResponse;
  } catch {
    throw new Error(`Confirm failed (HTTP ${response.status}, non-JSON body)`);
  }
  if (!response.ok || data.ok === false) {
    throw new Error(data.message || `Confirm failed (HTTP ${response.status})`);
  }
  return data;
}

/** Full catalog is small (~130 rows) — load once and filter client-side. */
export async function fetchCatalog(): Promise<CatalogBook[]> {
  const response = await fetch(`${getApiBaseUrl()}/api/catalog/`);
  if (!response.ok) {
    throw new Error(`Could not load catalog (HTTP ${response.status})`);
  }
  const data = (await response.json()) as CatalogBook[] | { results: CatalogBook[] };
  if (Array.isArray(data)) {
    return data;
  }
  if (Array.isArray(data.results)) {
    return data.results;
  }
  return [];
}

export function filterCatalog(
  books: CatalogBook[],
  query: string,
  limit = 8
): CatalogBook[] {
  const q = query.trim().toLowerCase();
  if (!q) {
    return [];
  }
  const scored: { book: CatalogBook; score: number }[] = [];
  for (const book of books) {
    const title = book.title.toLowerCase();
    const author = book.author.toLowerCase();
    let score = 0;
    if (title.startsWith(q)) score += 3;
    else if (title.includes(q)) score += 2;
    if (author.includes(q)) score += 1;
    if (score > 0) {
      scored.push({ book, score });
    }
  }
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, limit).map((s) => s.book);
}
