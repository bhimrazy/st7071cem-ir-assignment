"""Pydantic response models for both tasks' APIs.

Declared explicitly rather than returned as raw dicts so FastAPI can generate
a typed OpenAPI schema at /docs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PublicationHit(BaseModel):
    """One ranked publication, with every field the UI needs to render it.

    Fields are optional because a stored document is not guaranteed to carry
    every schema field -- a crawl glitch might leave `doi` empty, and the
    model should describe that reality rather than pretend it can't happen.
    """

    id: str
    score: float
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    journal: str | None = None
    year: int | str | None = None
    url: str | None = None
    doi: str | None = None
    author_profiles: list[str] = Field(default_factory=list)
    crawled_at: str | None = None


class SearchResponse(BaseModel):
    """A page of ranked results, plus what the UI needs to render "N results
    in X ms" and drive pagination."""

    hits: list[PublicationHit]
    total: int
    query: str
    scorer: str
    limit: int
    offset: int
    elapsed_ms: float


class AuthorPublication(BaseModel):
    """One publication in an author's list. No score: this is a filtered
    listing of everything they wrote, not a ranked answer to a query."""

    id: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    author_profiles: list[str] = Field(default_factory=list)
    abstract: str | None = None
    journal: str | None = None
    year: int | str | None = None
    url: str | None = None
    doi: str | None = None


class AuthorResponse(BaseModel):
    """An author profile assembled from our own index.

    `profile_url` is the link out to the author's pureportal page, which the
    coursework brief requires. It is empty for external co-authors, who have
    no Coventry profile.
    """

    name: str
    profile_url: str | None = None
    publication_count: int
    co_author_count: int
    first_year: str | None = None
    last_year: str | None = None
    publications: list[AuthorPublication]


class BrowseResponse(BaseModel):
    """A page of the corpus with no query applied.

    Used for the default listing shown before anyone searches, so the landing
    page presents the collection rather than an empty box. There is no score,
    because there is no query for anything to be relevant to.
    """

    publications: list[AuthorPublication]
    total: int
    limit: int
    offset: int


class StatsResponse(BaseModel):
    """Corpus statistics for the UI footer and the report."""

    document_count: int
    vocabulary_size: int
    last_crawled_at: str | None
    scorers: list[str]


class HealthResponse(BaseModel):
    status: str


# --- Task 2: document clustering -------------------------------------------


class CorpusInfo(BaseModel):
    """The clustering corpus and where it came from, so the UI can cite it."""

    total: int
    categories: list[str]
    counts: dict[str, int]
    source: str
    original_source: str
    citation: str
    licence_note: str


class ClusterSummary(BaseModel):
    cluster_id: int
    category: str
    size: int
    top_terms: list[str]


class ElbowPointModel(BaseModel):
    k: int
    inertia: float
    silhouette: float
    adjusted_rand_index: float | None = None


class ClusteringMetrics(BaseModel):
    adjusted_rand_index: float
    normalized_mutual_info: float
    homogeneity: float
    completeness: float
    v_measure: float
    accuracy: float


class ConfusionMatrix(BaseModel):
    rows: list[str]
    cols: list[str]
    matrix: list[list[int]]


class ProjectedDocument(BaseModel):
    """One training document placed in 2D by PCA, for the scatter plot."""

    x: float
    y: float
    cluster_id: int
    category: str
    true_category: str


class ClusteringOverview(BaseModel):
    """Everything the clustering page renders, computed once at fit time."""

    generated_at: str
    corpus: CorpusInfo
    vocabulary_size: int
    k: int
    inertia: float
    silhouette: float
    clusters: list[ClusterSummary]
    elbow: list[ElbowPointModel]
    metrics: ClusteringMetrics
    confusion: ConfusionMatrix
    projection: list[ProjectedDocument]
    examples: list[str]


class ClassifyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class ClassifyResponse(BaseModel):
    """Which cluster a submitted document was assigned to, and how clearly."""

    category: str
    cluster_id: int
    # Distance to every centroid, so the UI can show how close the runners-up
    # were rather than just naming a winner.
    distances: dict[str, float]
    margin: float
    matched_terms: list[str]
    matched_term_count: int
