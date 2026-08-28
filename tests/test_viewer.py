"""The viewer's data functions. The HTTP layer is a thin wrapper over these,
so testing them covers what could actually be wrong."""

import pytest

from miniseek.collection import Collection
from miniseek.schema import Field, Schema
from miniseek.viewer import describe, documents, open_for_viewing, page

SCHEMA = Schema(
    fields=(
        Field("id", indexed=False),
        Field("title", weight=3.0),
        Field("authors", weight=2.0),
        Field("year", indexed=False),
    )
)

CORPUS = [
    {"id": "a", "title": "Diabetes prevention", "authors": "Pearce", "year": "2024"},
    {"id": "b", "title": "Community health", "authors": "Ali", "year": "2023"},
    {"id": "c", "title": "Machine learning", "authors": "Pearce", "year": "2025"},
]


@pytest.fixture
def collection() -> Collection:
    coll = Collection("papers", schema=SCHEMA)
    coll.add_many(CORPUS)
    return coll


def test_describe_reports_counts(collection):
    stats = describe(collection)["stats"]
    assert stats["documents"] == 3
    assert stats["vocabulary"] > 0


def test_describe_reports_every_field_with_its_weight(collection):
    fields = {f["name"]: f for f in describe(collection)["fields"]}
    assert set(fields) == {"id", "title", "authors", "year"}
    assert fields["title"]["weight"] == 3.0
    assert fields["title"]["indexed"] is True
    assert fields["year"]["indexed"] is False


def test_unindexed_fields_have_no_average_length(collection):
    """An average length over a field that was never tokenised would be zero,
    which reads as a fact about the data rather than an absence of one."""
    fields = {f["name"]: f for f in describe(collection)["fields"]}
    assert fields["year"]["average_length"] is None
    assert fields["title"]["average_length"] > 0


def test_describe_reports_the_analyzer_settings(collection):
    analyzer = describe(collection)["analyzer"]
    assert analyzer["stem"] is True
    assert analyzer["min_token_length"] == 2


def test_documents_are_returned_with_both_ids(collection):
    result = documents(collection)
    assert result["total"] == 3
    assert [d["id"] for d in result["documents"]] == ["a", "b", "c"]
    assert result["documents"][0]["internal_id"] == 0


def test_documents_paginate(collection):
    result = documents(collection, offset=1, limit=1)
    assert result["total"] == 3  # the whole collection, not the window
    assert [d["id"] for d in result["documents"]] == ["b"]


def test_filter_is_a_substring_match_not_a_search(collection):
    """'machin' would match after stemming; a substring filter should not,
    while a genuine substring of the stored text should."""
    assert documents(collection, contains="machine")["total"] == 1
    assert documents(collection, contains="machin")["total"] == 1
    assert documents(collection, contains="learnings")["total"] == 0


def test_filter_is_case_insensitive_and_searches_every_stored_field(collection):
    assert documents(collection, contains="PEARCE")["total"] == 2
    assert documents(collection, contains="2023")["total"] == 1


def test_filter_reaches_inside_nested_values():
    """Authors are stored as dicts in the real index, so filtering has to see
    their contents rather than a Python repr of the list."""
    schema = Schema(fields=(Field("id", indexed=False), Field("authors")))
    coll = Collection("t", schema=schema)
    coll.add({"id": "x", "authors": [{"name": "Gemma Pearce", "profile_url": "u"}]})
    assert documents(coll, contains="gemma")["total"] == 1


def test_viewing_a_directory_that_is_not_a_collection_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="no miniseek collection"):
        open_for_viewing(tmp_path)


def test_a_saved_collection_is_readable_without_being_told_its_schema(tmp_path):
    """The point of a generic viewer: schema and analyzer come off disk, so it
    opens any collection without knowing what is in it."""
    with Collection.open(tmp_path, schema=SCHEMA, name="papers") as writer:
        writer.add_many(CORPUS)

    with open_for_viewing(tmp_path) as viewer:
        described = describe(viewer)
        assert described["name"] == "papers"
        assert described["stats"]["documents"] == 3
        assert {f["name"] for f in described["fields"]} == {
            "id",
            "title",
            "authors",
            "year",
        }


def test_reading_a_collection_does_not_touch_it(tmp_path):
    """The bug this flag exists for: an ordinary open rewrites meta.json on
    close even when nothing was added, so a viewer left a fingerprint on every
    collection it looked at."""
    with Collection.open(tmp_path, schema=SCHEMA, name="papers") as writer:
        writer.add_many(CORPUS)

    before = {
        p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()
    }

    with open_for_viewing(tmp_path) as viewer:
        describe(viewer)
        documents(viewer)

    after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()}
    assert after == before


def test_a_read_only_collection_refuses_writes_loudly(tmp_path):
    """Silence would be worse than an error: a read-only collection has no log
    handle, so an unguarded add would report success and vanish on reopen."""
    with Collection.open(tmp_path, schema=SCHEMA, name="papers") as writer:
        writer.add_many(CORPUS)

    with open_for_viewing(tmp_path) as viewer:
        with pytest.raises(RuntimeError, match="read-only"):
            viewer.add({"id": "d", "title": "Sneaking in", "authors": "X"})
        with pytest.raises(RuntimeError, match="read-only"):
            viewer.delete("a")

    with open_for_viewing(tmp_path) as reopened:
        assert len(reopened) == 3


def test_read_only_refuses_a_collection_that_does_not_exist(tmp_path):
    with pytest.raises(FileNotFoundError):
        Collection.open(tmp_path / "nope", schema=SCHEMA, read_only=True)


def test_the_page_is_served_from_a_file_beside_the_module():
    html = page().decode("utf-8")
    assert html.startswith("<!doctype html>")
    assert 'id="docs"' in html
