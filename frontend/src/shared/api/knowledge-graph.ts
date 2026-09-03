import type { EntityDetail, Recommendation, SearchResult } from "./knowledge-graph-model";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8001/api";

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal });
  if (!response.ok) {
    let detail = "";
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ? `: ${payload.detail}` : "";
    } catch {
      detail = "";
    }
    throw new Error(`API request failed: ${response.status}${detail}`);
  }
  return response.json() as Promise<T>;
}

export function searchEntities(query: string, limit = 25, signal?: AbortSignal): Promise<SearchResult[]> {
  return request<SearchResult[]>(`/search?q=${encodeURIComponent(query)}&limit=${limit}`, signal);
}

export function getEntity(uri: string): Promise<EntityDetail> {
  return request<EntityDetail>(`/entity?uri=${encodeURIComponent(uri)}`);
}

export function getRecommendations(uri: string, limit?: number, signal?: AbortSignal): Promise<Recommendation[]> {
  const query = new URLSearchParams({ uri });
  if (limit !== undefined) {
    query.set("limit", String(limit));
  }
  return request<Recommendation[]>(`/recommendations?${query.toString()}`, signal);
}

export function getFeaturedRecommendations(uri: string, signal?: AbortSignal): Promise<Recommendation[]> {
  const query = new URLSearchParams({ uri });
  return request<Recommendation[]>(`/recommendations/featured?${query.toString()}`, signal);
}
