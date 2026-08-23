import pytest

from miniseek.index import InvertedIndex


@pytest.fixture
def index() -> InvertedIndex:
    """A tiny pre-analyzed corpus; terms are already stemmed."""
    idx = InvertedIndex()
    idx.add(
        1, {"title": ["machin", "learn", "diabet"], "abstract": ["machin", "learn"]}
    )
    idx.add(2, {"title": ["commun", "health"], "abstract": ["health", "outcom"]})
    idx.add(3, {"title": ["deep", "learn"], "abstract": ["machin", "learn", "deep"]})
    return idx


def test_postings_record_frequency_and_positions(index):
    posting = index.postings("learn")[3]
    assert posting.positions == {"title": [1], "abstract": [1]}
    assert posting.term_frequency == 2
    assert posting.frequency_in("title") == 1
    assert posting.frequency_in("missing") == 0


def test_repeated_term_accumulates_positions():
    idx = InvertedIndex()
    idx.add(1, {"body": ["health", "data", "health"]})
    assert idx.postings("health")[1].positions == {"body": [0, 2]}
    assert idx.postings("health")[1].term_frequency == 2


def test_document_frequency_drives_idf(index):
    assert index.document_frequency("learn") == 2  # common, less discriminating
    assert index.document_frequency("diabet") == 1  # rare, discriminating
    assert index.document_frequency("absent") == 0
    assert index.document_count == 3


def test_missing_term_returns_empty_mapping(index):
    assert index.postings("absent") == {}


def test_postings_view_is_read_only(index):
    with pytest.raises(TypeError):
        index.postings("learn")[99] = None  # type: ignore[index]


def test_boolean_and_is_a_set_intersection(index):
    hits = index.postings("machin").keys() & index.postings("learn").keys()
    assert sorted(hits) == [1, 3]


def test_field_lengths_and_averages(index):
    assert index.field_length(1, "title") == 3
    assert index.document_length(1) == 5
    assert index.average_field_length("title") == pytest.approx(7 / 3)


def test_average_field_length_of_empty_index():
    assert InvertedIndex().average_field_length("title") == 0.0


def test_readding_a_document_replaces_rather_than_duplicates(index):
    """This is what makes the weekly re-crawl an update, not a duplication."""
    index.add(
        1, {"title": ["machin", "learn", "diabet"], "abstract": ["machin", "learn"]}
    )
    assert index.document_count == 3
    assert index.document_frequency("machin") == 2
    assert index.postings("machin")[1].term_frequency == 2


def test_reindexing_with_new_content_drops_stale_terms(index):
    index.add(1, {"title": ["nutrit"], "abstract": []})
    assert index.document_frequency("diabet") == 0
    assert index.document_frequency("nutrit") == 1
    assert index.field_length(1, "title") == 1


def test_remove_evicts_terms_and_updates_statistics(index):
    assert index.remove(3) is True
    assert index.remove(3) is False  # idempotent
    assert index.document_count == 2
    assert index.document_frequency("deep") == 0
    assert "deep" not in set(index.terms())  # no empty posting list left behind
    assert index.contains_document(3) is False
    assert index.average_field_length("title") == pytest.approx(5 / 2)


def test_vocabulary_size_counts_distinct_terms(index):
    assert index.vocabulary_size == len(set(index.terms()))
    assert len(index) == index.document_count
