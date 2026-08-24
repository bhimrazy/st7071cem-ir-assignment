"""Read-only throughout: the crawler owns writing to the collection, so the API
can run safely against a corpus a separate crawl process is updating."""

from __future__ import annotations

import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_collection
from api.models import (
    AuthorPublication,
    AuthorResponse,
    BrowseResponse,
    HealthResponse,
    PublicationHit,
    SearchResponse,
    StatsResponse,
)
from miniseek.collection import Collection
from miniseek.ranking import SCORERS

router = APIRouter(prefix="/api", tags=["search"])

# A literal type (rather than a bare `str`) is what makes FastAPI reject an
# unknown scorer with a 422 automatically, instead of the handler having to
# check it and raise by hand.
ScorerName = Literal["bm25", "tf-idf"]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/search", response_model=SearchResponse)
def search(
    collection: Annotated[Collection, Depends(get_collection)],
    q: Annotated[str, Query(description="Free-text query.")] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
    scorer: Annotated[ScorerName, Query()] = "bm25",
) -> SearchResponse:
    """Rank publications against `q` and return one page of hits.

    An empty or all-stopword query is not an error: it simply matches
    nothing, the same way Google Scholar shows a blank results page rather
    than an error for an empty search box.
    """
    started = time.perf_counter()
    results = collection.search(q, limit=limit, offset=offset, scorer=scorer)
    elapsed_ms = (time.perf_counter() - started) * 1000

    hits = [PublicationHit(score=hit.score, **hit.fields) for hit in results.hits]
    return SearchResponse(
        hits=hits,
        total=results.total,
        query=results.query,
        scorer=results.scorer,
        limit=limit,
        offset=offset,
        elapsed_ms=elapsed_ms,
    )


@router.get("/publications", response_model=BrowseResponse)
def publications(
    collection: Annotated[Collection, Depends(get_collection)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BrowseResponse:
    """Browse the corpus, newest first, with no query.

    Sorted by year rather than ranked: with no query there is nothing for a
    relevance score to measure, and recency is the ordering a reader of a
    research listing expects.
    """
    documents = sorted(
        collection,
        key=lambda d: str(d.fields.get("year") or ""),
        reverse=True,
    )
    window = documents[offset : offset + limit]
    return BrowseResponse(
        publications=[
            AuthorPublication(
                **{
                    key: value
                    for key, value in document.fields.items()
                    if key in AuthorPublication.model_fields
                }
            )
            for document in window
        ],
        total=len(documents),
        limit=limit,
        offset=offset,
    )


@router.get("/authors/{name}", response_model=AuthorResponse)
def author(
    collection: Annotated[Collection, Depends(get_collection)],
    name: str,
) -> AuthorResponse:
    """Everything this author wrote, assembled from our own index.

    Deliberately an exact match on the stored author list rather than a search
    for the name. A search would rank by relevance and could both miss
    publications and include papers by someone with a similar name; an author
    listing needs to be exhaustive and precise, which is a filter, not a query.
    """
    documents = [
        document
        for document in collection
        if any(a.get("name") == name for a in document.fields.get("authors", []))
    ]
    if not documents:
        raise HTTPException(status_code=404, detail=f"no publications for {name!r}")

    profile_url = ""
    co_authors: set[str] = set()
    for document in documents:
        for entry in document.fields.get("authors", []):
            if entry.get("name") == name:
                profile_url = profile_url or entry.get("profile_url", "")
            elif co_author := entry.get("name"):
                co_authors.add(co_author)

    years = sorted(y for d in documents if (y := str(d.fields.get("year") or "")))

    # Newest first: an author listing is browsed chronologically, not by
    # relevance, since there is no query to be relevant to.
    documents.sort(key=lambda d: str(d.fields.get("year") or ""), reverse=True)

    return AuthorResponse(
        name=name,
        profile_url=profile_url or None,
        publication_count=len(documents),
        co_author_count=len(co_authors),
        first_year=years[0] if years else None,
        last_year=years[-1] if years else None,
        publications=[
            AuthorPublication(
                **{
                    key: value
                    for key, value in document.fields.items()
                    if key in AuthorPublication.model_fields
                }
            )
            for document in documents
        ],
    )


@router.get("/stats", response_model=StatsResponse)
def stats(collection: Annotated[Collection, Depends(get_collection)]) -> StatsResponse:
    """Corpus-level statistics for the UI footer and the report."""
    crawled_at_values = [
        crawled_at
        for document in collection
        if (crawled_at := document.fields.get("crawled_at"))
    ]
    return StatsResponse(
        document_count=len(collection),
        vocabulary_size=collection.index.vocabulary_size,
        last_crawled_at=max(crawled_at_values) if crawled_at_values else None,
        scorers=sorted(SCORERS),
    )
