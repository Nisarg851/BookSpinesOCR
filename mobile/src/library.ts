import { getApiBaseUrl } from "./api";
import type { CatalogBook } from "./types";

export type LibraryEntry = {
  id: number;
  title: string;
  author: string;
  catalog_book: CatalogBook | null;
  match_result: number | null;
  crop_url: string | null;
  created_at: string;
};

export async function fetchLibrary(): Promise<LibraryEntry[]> {
  const response = await fetch(`${getApiBaseUrl()}/api/library/`);
  if (!response.ok) {
    throw new Error(`Could not load library (HTTP ${response.status})`);
  }
  const data = (await response.json()) as
    | LibraryEntry[]
    | { results: LibraryEntry[] };
  if (Array.isArray(data)) {
    return data;
  }
  if (Array.isArray(data.results)) {
    return data.results;
  }
  return [];
}
