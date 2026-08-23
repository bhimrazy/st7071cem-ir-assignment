import json
import threading
import time

import pytest

from miniseek.analyzer import Analyzer
from miniseek.collection import LOG_FILE, META_FILE, Collection
from miniseek.schema import Field, Schema

PUBLICATIONS = [
    {
        "id": "p1",
        "title": "Machine learning for diabetes risk prediction",
        "abstract": "Predicting diabetes risk in adults.",
        "url": "https://pureportal.coventry.ac.uk/p1",
    },
    {
        "id": "p2",
        "title": "Community health interventions",
        "abstract": "A study of community health outcomes.",
        "url": "https://pureportal.coventry.ac.uk/p2",
    },
]


@pytest.fixture
def schema() -> Schema:
    return Schema(
        fields=(
            Field("id", indexed=False),
            Field("title", weight=3.0),
            Field("abstract"),
            Field("url", indexed=False),
        )
    )


@pytest.fixture
def collection(tmp_path, schema) -> Collection:
    coll = Collection.open(tmp_path / "pubs", schema=schema)
    coll.add_many(PUBLICATIONS)
    return coll


def test_documents_are_indexed_and_retrievable(collection):
    assert len(collection) == 2
    assert collection.get("p1").fields["title"].startswith("Machine")
    assert collection.index.document_frequency("diabet") == 1


def test_missing_id_field_is_rejected(collection):
    with pytest.raises(ValueError, match="missing its id field"):
        collection.add({"title": "no id here"})


def test_non_indexed_fields_stay_out_of_the_index(collection):
    """Indexing URLs would make 'coventry' match the entire corpus."""
    assert collection.index.document_frequency("pureport") == 0
    assert collection.index.document_frequency("coventri") == 0


def test_stored_fields_filter_what_results_return(tmp_path, schema):
    schema = Schema(
        fields=(
            Field("id", indexed=False),
            Field("title"),
            Field("secret", indexed=True, stored=False),
        )
    )
    coll = Collection.open(tmp_path / "c", schema=schema)
    doc = coll.add({"id": "x", "title": "Visible", "secret": "hidden text"})
    assert coll.stored_fields(doc) == {"id": "x", "title": "Visible"}
    assert coll.index.document_frequency("hidden") == 1  # searchable, not shown


def test_list_and_numeric_fields_are_coerced(tmp_path, schema):
    coll = Collection.open(tmp_path / "c", schema=schema)
    coll.add({"id": "x", "title": ["Alice Smith", "Bob Jones"], "abstract": 2024})
    assert coll.index.document_frequency("alic") == 1
    assert coll.index.document_frequency("2024") == 1


def test_update_keeps_internal_id_stable(collection):
    before = collection.get("p1").internal_id
    collection.add(
        {
            **PUBLICATIONS[0],
            "title": "Nutrition and diet",
            "abstract": "Dietary intake.",
        }
    )
    assert collection.get("p1").internal_id == before
    assert len(collection) == 2
    assert collection.index.document_frequency("diabet") == 0  # stale term gone
    assert collection.index.document_frequency("nutrit") == 1


def test_delete_removes_from_store_and_index(collection):
    assert collection.delete("p2") is True
    assert collection.delete("p2") is False
    assert len(collection) == 1
    assert collection.index.document_frequency("commun") == 0


# ---- persistence -------------------------------------------------------


def test_reopening_restores_documents_and_index(tmp_path, schema):
    path = tmp_path / "pubs"
    with Collection.open(path, schema=schema) as coll:
        coll.add_many(PUBLICATIONS)

    reopened = Collection.open(path)
    assert len(reopened) == 2
    restored = reopened.get("p1")
    assert restored is not None
    assert restored.fields["title"].startswith("Machine")
    assert reopened.index.document_frequency("diabet") == 1
    assert reopened.schema.field("title").weight == 3.0


def test_reopening_restores_analyzer_config(tmp_path, schema):
    path = tmp_path / "pubs"
    with Collection.open(path, schema=schema, analyzer=Analyzer(stem=False)) as coll:
        coll.add({"id": "p1", "title": "Retrieving datasets"})

    reopened = Collection.open(path)
    assert reopened.analyzer.stem is False
    # Unstemmed on the way in must stay unstemmed on the way out, or queries
    # built by the reopened analyzer would never match the stored postings.
    assert reopened.index.document_frequency("retrieving") == 1


def test_deletes_survive_a_reopen(tmp_path, schema):
    path = tmp_path / "pubs"
    with Collection.open(path, schema=schema) as coll:
        coll.add_many(PUBLICATIONS)
        coll.delete("p1")

    reopened = Collection.open(path)
    assert len(reopened) == 1
    assert reopened.get("p1") is None
    assert reopened.index.document_frequency("diabet") == 0


def test_internal_ids_do_not_collide_after_reopen(tmp_path, schema):
    path = tmp_path / "pubs"
    with Collection.open(path, schema=schema) as coll:
        coll.add_many(PUBLICATIONS)
        existing = {d.internal_id for d in coll}

    with Collection.open(path) as reopened:
        fresh = reopened.add({"id": "p3", "title": "New paper"})
        assert fresh.internal_id not in existing


def test_writes_are_appends_not_rewrites(tmp_path, schema):
    """An update appends one line; it does not rewrite the whole log."""
    path = tmp_path / "pubs"
    with Collection.open(path, schema=schema) as coll:
        coll.add_many(PUBLICATIONS)
        coll.add({**PUBLICATIONS[0], "title": "Revised title"})
        coll.delete("p2")

    lines = (path / LOG_FILE).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 4
    assert [json.loads(line)["op"] for line in lines] == [
        "put",
        "put",
        "put",
        "delete",
    ]


def test_compaction_drops_superseded_entries(tmp_path, schema):
    path = tmp_path / "pubs"
    with Collection.open(path, schema=schema) as coll:
        coll.add_many(PUBLICATIONS)
        for i in range(5):
            coll.add({**PUBLICATIONS[0], "title": f"Revision {i}"})
        coll.delete("p2")

        coll.flush()  # appends are buffered until flush or close
        before = len((path / LOG_FILE).read_text().strip().splitlines())
        dropped = coll.compact()
        after = len((path / LOG_FILE).read_text().strip().splitlines())

    assert before == 8
    assert after == 1  # only the live version of p1 survives
    assert dropped == 7

    reopened = Collection.open(path)
    assert len(reopened) == 1
    restored = reopened.get("p1")
    assert restored is not None
    assert restored.fields["title"] == "Revision 4"


def test_opening_a_new_directory_without_schema_fails(tmp_path):
    with pytest.raises(ValueError, match="pass schema="):
        Collection.open(tmp_path / "nothing-here")


def test_unknown_format_version_is_rejected(tmp_path, schema):
    path = tmp_path / "pubs"
    Collection.open(path, schema=schema).close()
    meta_path = path / META_FILE
    meta = json.loads(meta_path.read_text())
    meta["version"] = 99
    meta_path.write_text(json.dumps(meta))

    with pytest.raises(ValueError, match="format version 99"):
        Collection.open(path)


def test_corrupt_log_entry_is_reported_with_its_line(tmp_path, schema):
    path = tmp_path / "pubs"
    with Collection.open(path, schema=schema) as coll:
        coll.add_many(PUBLICATIONS)
    with open(path / LOG_FILE, "a", encoding="utf-8") as handle:
        handle.write('{"op": "put", "id": "truncated"')  # died mid-append

    with pytest.raises(ValueError, match="line 3"):
        Collection.open(path)


def test_compaction_after_reopen_counts_existing_entries(tmp_path, schema):
    """A reopened collection must know the log already carries dead weight."""
    path = tmp_path / "pubs"
    with Collection.open(path, schema=schema, sync_interval=None) as coll:
        coll.add_many(PUBLICATIONS)
        coll.add({**PUBLICATIONS[0], "title": "Revised"})

    with Collection.open(path, sync_interval=None) as reopened:
        assert reopened.log_entries == 3  # not reset to zero on load
        assert reopened.dead_entries == 1
        assert reopened.compact() == 1


def test_dead_entry_accounting(tmp_path, schema):
    path = tmp_path / "pubs"
    with Collection.open(path, schema=schema, sync_interval=None) as coll:
        coll.add_many(PUBLICATIONS)
        assert coll.dead_entries == 0
        coll.add({**PUBLICATIONS[0], "title": "Revised"})
        assert coll.log_entries == 3
        assert coll.dead_entries == 1


# ---- background syncing ------------------------------------------------


def test_background_syncer_persists_without_an_explicit_flush(tmp_path, schema):
    path = tmp_path / "pubs"
    coll = Collection.open(path, schema=schema, sync_interval=0.05)
    try:
        coll.add_many(PUBLICATIONS)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if (path / LOG_FILE).read_text().count("\n") >= 2:
                break
            time.sleep(0.02)
        assert (path / LOG_FILE).read_text().count("\n") == 2
    finally:
        coll.close()


def test_small_collections_do_not_compact_constantly(tmp_path, schema):
    """Ratio alone would trigger endlessly on a tiny log for no real gain."""
    path = tmp_path / "pubs"
    with Collection.open(path, schema=schema, sync_interval=None) as coll:
        for i in range(10):
            coll.add({**PUBLICATIONS[0], "title": f"Revision {i}"})
        assert coll.log_entries == 10
        assert coll.dead_entries == 9  # ratio is terrible...
        assert coll.should_compact() is False  # ...but the log is tiny


def test_auto_compaction_triggers_once_the_log_is_wasteful(tmp_path, schema):
    path = tmp_path / "pubs"
    with Collection.open(
        path, schema=schema, sync_interval=None, compact_min_entries=20
    ) as coll:
        for i in range(30):
            coll.add({**PUBLICATIONS[0], "title": f"Revision {i}"})
        assert coll.should_compact() is True
        coll.sync()
        assert coll.log_entries == 1
        assert coll.should_compact() is False
        latest = coll.get("p1")
        assert latest is not None
        assert latest.fields["title"] == "Revision 29"


def test_compaction_is_disableable(tmp_path, schema):
    with Collection.open(
        tmp_path / "pubs", schema=schema, sync_interval=None, compact_ratio=None
    ) as coll:
        for i in range(100):
            coll.add({**PUBLICATIONS[0], "title": f"Revision {i}"})
        assert coll.should_compact() is False


def test_close_stops_the_background_thread(tmp_path, schema):
    before = threading.active_count()
    coll = Collection.open(tmp_path / "pubs", schema=schema, sync_interval=0.05)
    coll.add_many(PUBLICATIONS)
    assert threading.active_count() == before + 1
    coll.close()
    assert threading.active_count() == before


def test_concurrent_writers_do_not_corrupt_the_log(tmp_path, schema):
    """Mutations and background compaction share one lock."""
    path = tmp_path / "pubs"
    with Collection.open(
        path, schema=schema, sync_interval=0.01, compact_min_entries=20
    ) as coll:

        def writer(worker: int) -> None:
            for i in range(25):
                coll.add({"id": f"w{worker}-{i}", "title": f"Paper {worker} {i}"})

        threads = [threading.Thread(target=writer, args=(w,)) for w in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert len(Collection.open(path, sync_interval=None)) == 100


def test_in_memory_collection_needs_no_disk(schema):
    coll = Collection("mem", schema=schema)
    coll.add_many(PUBLICATIONS)
    assert len(coll) == 2
    assert coll.path is None
    coll.close()  # must not raise
    assert coll.compact() == 0
