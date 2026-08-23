"""Tests for the search API.

Each test seeds its own in-memory collection rather than depending on the
real crawled corpus, since the crawl may not have run yet -- see
`ir_search_engine.main.create_app`, which accepts a collection to inject.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from ir_search_engine.publications import PUBLICATION_SCHEMA
from miniseek.collection import Collection

PUBLICATIONS = [
    {
        "id": "https://pureportal.coventry.ac.uk/pub/1",
        "title": "Machine learning for diabetes risk prediction",
        "authors": ["Alice Smith", "Bob Jones"],
        "abstract": "A study predicting diabetes risk in adult populations "
        "using machine learning models.",
        "journal": "Journal of Health Informatics",
        "year": 2023,
        "url": "https://pureportal.coventry.ac.uk/pub/1",
        "doi": "10.1000/diabetes1",
        "author_profiles": [
            "https://pureportal.coventry.ac.uk/en/persons/alice-smith",
            "https://pureportal.coventry.ac.uk/en/persons/bob-jones",
        ],
        "crawled_at": "2026-08-01T00:00:00Z",
    },
    {
        "id": "https://pureportal.coventry.ac.uk/pub/2",
        "title": "Community health interventions in urban populations",
        "authors": ["Carol Lee"],
        "abstract": "A qualitative study of community health outcomes "
        "following targeted interventions.",
        "journal": "Community Health Review",
        "year": 2022,
        "url": "https://pureportal.coventry.ac.uk/pub/2",
        "doi": "10.1000/health2",
        "author_profiles": [
            "https://pureportal.coventry.ac.uk/en/persons/carol-lee",
        ],
        "crawled_at": "2026-08-02T00:00:00Z",
    },
    {
        "id": "https://pureportal.coventry.ac.uk/pub/3",
        "title": "Diabetes management strategies for elderly patients",
        "authors": ["Alice Smith"],
        "abstract": "Reviewing diabetes management approaches suited to "
        "elderly patients in community settings.",
        "journal": "Journal of Health Informatics",
        "year": 2024,
        "url": "https://pureportal.coventry.ac.uk/pub/3",
        "doi": "10.1000/diabetes3",
        "author_profiles": [
            "https://pureportal.coventry.ac.uk/en/persons/alice-smith",
        ],
        "crawled_at": "2026-08-03T00:00:00Z",
    },
]


@pytest.fixture
def seeded_collection(tmp_path) -> Iterator[Collection]:
    collection = Collection.open(
        tmp_path / "publications",
        schema=PUBLICATION_SCHEMA,
        name="publications",
        sync_interval=None,
    )
    collection.add_many(PUBLICATIONS)
    yield collection
    collection.close()


@pytest.fixture
def empty_collection(tmp_path) -> Iterator[Collection]:
    collection = Collection.open(
        tmp_path / "empty",
        schema=PUBLICATION_SCHEMA,
        name="publications",
        sync_interval=None,
    )
    yield collection
    collection.close()


@pytest.fixture
def client(seeded_collection) -> Iterator[TestClient]:
    app = create_app(collection=seeded_collection)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def empty_client(empty_collection) -> Iterator[TestClient]:
    app = create_app(collection=empty_collection)
    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_returns_ranked_hits(client: TestClient) -> None:
    response = client.get("/api/search", params={"q": "diabetes"})
    assert response.status_code == 200
    body = response.json()

    assert body["query"] == "diabetes"
    assert body["scorer"] == "bm25"
    assert body["total"] == 2
    assert len(body["hits"]) == 2
    assert "elapsed_ms" in body and body["elapsed_ms"] >= 0

    ids = [hit["id"] for hit in body["hits"]]
    assert "https://pureportal.coventry.ac.uk/pub/1" in ids
    assert "https://pureportal.coventry.ac.uk/pub/3" in ids
    # Community health publication does not mention diabetes.
    assert "https://pureportal.coventry.ac.uk/pub/2" not in ids

    # Ranked: highest score first.
    scores = [hit["score"] for hit in body["hits"]]
    assert scores == sorted(scores, reverse=True)


def test_search_hit_includes_display_fields(client: TestClient) -> None:
    response = client.get("/api/search", params={"q": "diabetes"})
    hit = response.json()["hits"][0]

    assert hit["title"]
    assert hit["authors"]
    assert hit["author_profiles"]
    assert hit["journal"]
    assert hit["url"].startswith("https://pureportal.coventry.ac.uk")


def test_search_tf_idf_scorer(client: TestClient) -> None:
    response = client.get(
        "/api/search", params={"q": "diabetes", "scorer": "tf-idf"}
    )
    assert response.status_code == 200
    assert response.json()["scorer"] == "tf-idf"


def test_search_unknown_scorer_is_rejected(client: TestClient) -> None:
    response = client.get(
        "/api/search", params={"q": "diabetes", "scorer": "nonsense"}
    )
    assert response.status_code == 422


def test_search_pagination(client: TestClient) -> None:
    first_page = client.get(
        "/api/search", params={"q": "diabetes health community", "limit": 1, "offset": 0}
    ).json()
    second_page = client.get(
        "/api/search", params={"q": "diabetes health community", "limit": 1, "offset": 1}
    ).json()

    assert len(first_page["hits"]) == 1
    assert len(second_page["hits"]) == 1
    assert first_page["hits"][0]["id"] != second_page["hits"][0]["id"]
    assert first_page["total"] == second_page["total"]


def test_search_invalid_limit_is_rejected(client: TestClient) -> None:
    assert client.get("/api/search", params={"q": "x", "limit": 0}).status_code == 422
    assert client.get("/api/search", params={"q": "x", "limit": 1000}).status_code == 422


def test_search_invalid_offset_is_rejected(client: TestClient) -> None:
    response = client.get("/api/search", params={"q": "x", "offset": -1})
    assert response.status_code == 422


def test_search_empty_query_returns_no_results(client: TestClient) -> None:
    response = client.get("/api/search", params={"q": ""})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["hits"] == []


def test_search_no_matches(client: TestClient) -> None:
    response = client.get("/api/search", params={"q": "quantum astrophysics"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["hits"] == []


def test_stats_endpoint(client: TestClient) -> None:
    response = client.get("/api/stats")
    assert response.status_code == 200
    body = response.json()

    assert body["document_count"] == 3
    assert body["vocabulary_size"] > 0
    assert body["last_crawled_at"] == "2026-08-03T00:00:00Z"
    assert set(body["scorers"]) == {"bm25", "tf-idf"}


def test_empty_collection_search_does_not_crash(empty_client: TestClient) -> None:
    response = empty_client.get("/api/search", params={"q": "diabetes"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["hits"] == []


def test_empty_collection_stats_does_not_crash(empty_client: TestClient) -> None:
    response = empty_client.get("/api/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["document_count"] == 0
    assert body["vocabulary_size"] == 0
    assert body["last_crawled_at"] is None


# ---- author endpoint ---------------------------------------------------


def test_author_lists_their_publications(client: TestClient) -> None:
    response = client.get("/api/authors/Alice Smith")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Alice Smith"
    assert body["publication_count"] == 2  # pub/1 and pub/3
    assert body["publication_count"] == len(body["publications"])
    assert body["co_author_count"] == 1    # Bob Jones
    assert body["first_year"] == "2023"
    assert body["last_year"] == "2024"


def test_author_exposes_the_pureportal_profile_link(client: TestClient) -> None:
    """The brief requires a link to the author's profile page."""
    body = client.get("/api/authors/Alice Smith").json()
    assert body["profile_url"] == (
        "https://pureportal.coventry.ac.uk/en/persons/alice-smith"
    )


def test_author_publications_carry_no_relevance_score(client: TestClient) -> None:
    """An author listing is a filter, not a ranked answer to a query."""
    body = client.get("/api/authors/Alice Smith").json()
    assert all("score" not in publication for publication in body["publications"])


def test_author_publications_are_newest_first(client: TestClient) -> None:
    body = client.get("/api/authors/Alice Smith").json()
    years = [str(p["year"] or "") for p in body["publications"]]
    assert years == sorted(years, reverse=True)


def test_author_matching_is_exact_not_a_search(client: TestClient) -> None:
    """A substring of a real name must not resolve to that author."""
    assert client.get("/api/authors/Alice").status_code == 404


def test_unknown_author_returns_404(client: TestClient) -> None:
    assert client.get("/api/authors/Nobody At All").status_code == 404


def test_author_endpoint_on_empty_collection(empty_client: TestClient) -> None:
    assert empty_client.get("/api/authors/Anyone").status_code == 404


# ---- default listing (browse) -----------------------------------------


def test_publications_listing_returns_the_corpus(client: TestClient) -> None:
    body = client.get("/api/publications").json()
    assert body["total"] == 3
    assert len(body["publications"]) == 3


def test_publications_listing_is_newest_first(client: TestClient) -> None:
    """No query means no relevance, so recency is the sensible ordering."""
    body = client.get("/api/publications").json()
    years = [str(p["year"] or "") for p in body["publications"]]
    assert years == sorted(years, reverse=True)


def test_publications_listing_carries_no_score(client: TestClient) -> None:
    body = client.get("/api/publications").json()
    assert all("score" not in p for p in body["publications"])


def test_publications_listing_paginates(client: TestClient) -> None:
    first = client.get("/api/publications", params={"limit": 2}).json()
    second = client.get("/api/publications", params={"limit": 2, "offset": 2}).json()
    assert len(first["publications"]) == 2
    assert len(second["publications"]) == 1
    assert first["total"] == second["total"] == 3
    ids = [p["id"] for p in first["publications"] + second["publications"]]
    assert len(set(ids)) == 3


def test_publications_listing_rejects_bad_pagination(client: TestClient) -> None:
    assert client.get("/api/publications", params={"limit": 0}).status_code == 422
    assert client.get("/api/publications", params={"offset": -1}).status_code == 422


def test_publications_listing_on_empty_collection(empty_client: TestClient) -> None:
    body = empty_client.get("/api/publications").json()
    assert body["total"] == 0
    assert body["publications"] == []
