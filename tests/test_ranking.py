from collections import Counter

import pytest

from miniseek.collection import Collection
from miniseek.index import InvertedIndex
from miniseek.ranking import Bm25Scorer, TfIdfScorer
from miniseek.schema import Field, Schema

CORPUS = [
    {
        "id": "a",
        "title": "Diabetes prevention in adults",
        "abstract": "A trial of diabetes prevention.",
    },
    {
        "id": "b",
        "title": "Community health outcomes",
        "abstract": "Diabetes is mentioned once here among many other topics "
        "including nutrition, exercise, housing and social care.",
    },
    {
        "id": "c",
        "title": "Machine learning methods",
        "abstract": "Neural networks and deep learning.",
    },
]


@pytest.fixture
def collection() -> Collection:
    schema = Schema(
        fields=(
            Field("id", indexed=False),
            Field("title", weight=3.0),
            Field("abstract", weight=1.0),
        )
    )
    coll = Collection("test", schema=schema)
    coll.add_many(CORPUS)
    return coll


@pytest.mark.parametrize("scorer", ["tf-idf", "bm25"])
def test_only_matching_documents_are_returned(collection, scorer):
    results = collection.search("diabetes", scorer=scorer)
    assert {hit.id for hit in results} == {"a", "b"}
    assert results.total == 2
    assert all(hit.score > 0 for hit in results)


@pytest.mark.parametrize("scorer", ["tf-idf", "bm25"])
def test_title_matches_outrank_abstract_matches(collection, scorer):
    """Field weighting: 'diabetes' in a title beats 'diabetes' in an abstract."""
    results = collection.search("diabetes", scorer=scorer)
    assert [hit.id for hit in results] == ["a", "b"]


@pytest.mark.parametrize("scorer", ["tf-idf", "bm25"])
def test_rare_terms_outweigh_common_ones(collection, scorer):
    """IDF: 'diabetes' (df=2) should pull harder than 'health' (df=1)..."""
    results = collection.search("machine learning", scorer=scorer)
    assert results.hits[0].id == "c"


def test_results_are_sorted_by_descending_score(collection):
    results = collection.search("diabetes prevention health")
    scores = [hit.score for hit in results]
    assert scores == sorted(scores, reverse=True)


def test_query_is_analyzed_like_the_documents(collection):
    """The whole point of the shared analyzer, checked end to end."""
    assert {h.id for h in collection.search("DIABETES")} == {"a", "b"}
    assert {h.id for h in collection.search("diabetic")} == {"a", "b"}
    assert {h.id for h in collection.search("Learning")} == {"c"}


def test_stopword_only_query_returns_nothing(collection):
    results = collection.search("the of and")
    assert results.total == 0
    assert results.hits == []


def test_empty_query_returns_nothing(collection):
    assert collection.search("").total == 0


def test_unmatched_query_returns_nothing(collection):
    assert collection.search("quantum chromodynamics").total == 0


def test_hits_carry_stored_fields_only(collection):
    hit = collection.search("diabetes").hits[0]
    assert hit.fields["title"] == "Diabetes prevention in adults"
    assert hit.id == "a"


def test_pagination_windows_the_ranking(collection):
    everything = collection.search("diabetes health learning", limit=10)
    assert everything.total == 3

    page = collection.search("diabetes health learning", limit=2)
    assert len(page.hits) == 2
    assert page.total == 3  # total counts all matches, not just this page

    second = collection.search("diabetes health learning", limit=2, offset=2)
    assert len(second.hits) == 1
    assert [h.id for h in page] + [h.id for h in second] == [h.id for h in everything]


def test_scorer_choice_is_reported(collection):
    assert collection.search("diabetes", scorer="bm25").scorer == "bm25"
    assert collection.search("diabetes", scorer="tf-idf").scorer == "tf-idf"


def test_unknown_scorer_name_is_rejected(collection):
    with pytest.raises(ValueError, match="unknown scorer"):
        collection.search("diabetes", scorer="pagerank")


def test_scorer_instance_can_be_passed_directly(collection):
    results = collection.search("diabetes", scorer=Bm25Scorer(k1=2.0, b=0.5))
    assert results.hits[0].id == "a"


def test_term_in_every_document_contributes_nothing_to_tfidf():
    """log10(N/N) = 0, so a universal term cannot separate documents."""
    schema = Schema(fields=(Field("id", indexed=False), Field("title")))
    coll = Collection("t", schema=schema)
    coll.add_many(
        [
            {"id": "1", "title": "health study"},
            {"id": "2", "title": "health study"},
        ]
    )
    assert coll.search("health", scorer="tf-idf").total == 2
    assert all(h.score == 0.0 for h in coll.search("health", scorer="tf-idf"))


def test_bm25_keeps_universal_terms_positive():
    """BM25's +1 keeps IDF positive where raw tf-idf would zero out."""
    schema = Schema(fields=(Field("id", indexed=False), Field("title")))
    coll = Collection("t", schema=schema)
    coll.add_many(
        [
            {"id": "1", "title": "health study"},
            {"id": "2", "title": "health study"},
        ]
    )
    assert all(h.score > 0 for h in coll.search("health", scorer="bm25"))


def test_bm25_saturates_term_frequency():
    """Ten mentions must not score ten times one mention."""
    schema = Schema(
        fields=(
            Field("id", indexed=False),
            Field("body"),
        )
    )
    coll = Collection("t", schema=schema)
    coll.add({"id": "once", "body": "diabetes " + "filler " * 30})
    coll.add({"id": "many", "body": "diabetes " * 10 + "filler " * 21})

    scores = {h.id: h.score for h in coll.search("diabetes", scorer="bm25")}
    ratio = scores["many"] / scores["once"]
    assert 1.0 < ratio < 3.0  # more, but far from 10x


def test_bm25_length_normalisation_is_tunable():
    schema = Schema(fields=(Field("id", indexed=False), Field("body")))
    coll = Collection("t", schema=schema)
    coll.add({"id": "short", "body": "diabetes"})
    coll.add({"id": "long", "body": "diabetes " + "unrelated " * 50})

    with_penalty = {
        h.id: h.score for h in coll.search("diabetes", scorer=Bm25Scorer(b=1.0))
    }
    without = {h.id: h.score for h in coll.search("diabetes", scorer=Bm25Scorer(b=0.0))}

    assert with_penalty["short"] > with_penalty["long"]
    assert without["short"] == pytest.approx(without["long"])


def test_empty_index_scores_nothing():
    for scorer in (TfIdfScorer(), Bm25Scorer()):
        assert scorer.score(InvertedIndex(), Counter({"x": 1}), {"title": 1.0}) == {}


def test_deleted_documents_leave_the_ranking(collection):
    assert collection.delete("a") is True
    assert {h.id for h in collection.search("diabetes")} == {"b"}
