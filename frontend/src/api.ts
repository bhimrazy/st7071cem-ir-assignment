// Relative /api URLs throughout: Vite proxies them in development and FastAPI
// serves the same origin in production, so no host is ever hard-coded.

import type {
  AuthorResponse,
  BrowseResponse,
  ClassifyResponse,
  ClusteringOverview,
  ScorerName,
  SearchResponse,
  StatsResponse,
} from "./types"

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail =
      (body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : null) ?? `request failed with status ${response.status}`
    throw new ApiError(detail, response.status)
  }
  return response.json() as Promise<T>
}

export interface SearchParams {
  query: string
  limit: number
  offset: number
  scorer: ScorerName
}

export function search({
  query,
  limit,
  offset,
  scorer,
}: SearchParams): Promise<SearchResponse> {
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
    offset: String(offset),
    scorer,
  })
  return getJson<SearchResponse>(`/api/search?${params.toString()}`)
}

export function fetchStats(): Promise<StatsResponse> {
  return getJson<StatsResponse>("/api/stats")
}

export function fetchAuthor(name: string): Promise<AuthorResponse> {
  return getJson<AuthorResponse>(`/api/authors/${encodeURIComponent(name)}`)
}

export function fetchPublications(limit: number, offset: number): Promise<BrowseResponse> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  return getJson<BrowseResponse>(`/api/publications?${params.toString()}`)
}

export function fetchClusteringOverview(): Promise<ClusteringOverview> {
  return getJson<ClusteringOverview>("/api/clustering/overview")
}

export async function classifyDocument(text: string): Promise<ClassifyResponse> {
  const response = await fetch("/api/clustering/classify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  })
  if (!response.ok) {
    throw new ApiError(
      `could not classify that document (status ${response.status})`,
      response.status,
    )
  }
  return response.json() as Promise<ClassifyResponse>
}
