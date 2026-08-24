// Mirrors src/api/models.py.

export type ScorerName = "bm25" | "tf-idf"

export interface AuthorInfo {
  name: string
  profile_url: string
}

export interface PublicationHit {
  id: string
  score: number
  title: string | null
  authors: AuthorInfo[]
  abstract: string | null
  journal: string | null
  year: number | string | null
  url: string | null
  doi: string | null
  crawled_at: string | null
}

export interface SearchResponse {
  hits: PublicationHit[]
  total: number
  query: string
  scorer: ScorerName
  limit: number
  offset: number
  elapsed_ms: number
}

export interface StatsResponse {
  document_count: number
  vocabulary_size: number
  last_crawled_at: string | null
  scorers: ScorerName[]
}

export interface AuthorPublication {
  id: string
  title: string | null
  authors: AuthorInfo[]
  abstract: string | null
  journal: string | null
  year: number | string | null
  url: string | null
  doi: string | null
}

export interface AuthorResponse {
  name: string
  profile_url: string | null
  publication_count: number
  co_author_count: number
  first_year: string | null
  last_year: string | null
  publications: AuthorPublication[]
}

export interface BrowseResponse {
  publications: AuthorPublication[]
  total: number
  limit: number
  offset: number
}

/* --- Task 2: document clustering --- */

export interface CorpusInfo {
  total: number
  categories: string[]
  counts: Record<string, number>
  source: string
  original_source: string
  citation: string
  licence_note: string
}

export interface ClusterSummary {
  cluster_id: number
  category: string
  size: number
  top_terms: string[]
}

export interface ElbowPoint {
  k: number
  inertia: number
  silhouette: number
  adjusted_rand_index: number | null
}

export interface ClusteringMetrics {
  adjusted_rand_index: number
  normalized_mutual_info: number
  homogeneity: number
  completeness: number
  v_measure: number
  accuracy: number
}

export interface ConfusionMatrix {
  rows: string[]
  cols: string[]
  matrix: number[][]
}

export interface ProjectedDocument {
  x: number
  y: number
  cluster_id: number
  category: string
  true_category: string
}

export interface ClusteringOverview {
  generated_at: string
  corpus: CorpusInfo
  vocabulary_size: number
  k: number
  inertia: number
  silhouette: number
  clusters: ClusterSummary[]
  elbow: ElbowPoint[]
  metrics: ClusteringMetrics
  confusion: ConfusionMatrix
  projection: ProjectedDocument[]
  examples: string[]
}

export interface ClassifyResponse {
  category: string
  cluster_id: number
  distances: Record<string, number>
  margin: number
  matched_terms: string[]
  matched_term_count: number
}
