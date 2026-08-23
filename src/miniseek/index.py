"""A forward index maps document to terms, which makes "which documents contain
this word" a full scan. Inverting it to term to documents makes the same
question one dictionary lookup, whatever the corpus size.

Postings carry frequency, which ranking needs, and positions, which phrase
queries would need."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from math import log10, sqrt
from types import MappingProxyType


@dataclass(slots=True)
class Posting:
    """One document's occurrences of one term, broken down by field.

    Positions are term offsets within a field, not character offsets: in the
    analyzed title ["machin", "learn", "health"], "learn" is at position 1.
    They are stored per field because adjacency is only meaningful inside a
    single field -- the last word of a title is not adjacent to the first word
    of an abstract.
    """

    doc_id: int
    positions: dict[str, list[int]] = field(default_factory=dict)

    @property
    def term_frequency(self) -> int:
        """Total occurrences of this term across all fields of the document."""
        return sum(len(p) for p in self.positions.values())

    def frequency_in(self, field_name: str) -> int:
        return len(self.positions.get(field_name, ()))

    def fields(self) -> tuple[str, ...]:
        return tuple(self.positions)


class InvertedIndex:
    """Maps analyzed terms to the documents containing them.

    Documents are identified by an internal integer id. Mapping external ids
    (URLs, DOIs) onto those integers is deliberately somebody else's job --
    integers keep the postings compact and comparisons cheap.
    """

    __slots__ = (
        "_field_lengths",
        "_field_norms",
        "_postings",
        "_terms_by_doc",
        "_total_field_length",
    )

    def __init__(self) -> None:
        # term -> doc_id -> Posting
        self._postings: dict[str, dict[int, Posting]] = defaultdict(dict)
        # doc_id -> field name -> number of terms (needed for BM25 normalisation)
        self._field_lengths: dict[int, dict[str, int]] = {}
        # doc_id -> its distinct terms, so deletion doesn't scan the whole index
        self._terms_by_doc: dict[int, set[str]] = {}
        # running totals, so average field length stays O(1)
        self._total_field_length: dict[str, int] = defaultdict(int)
        # doc_id -> field -> cosine normalisation factor, precomputed at index
        # time because recomputing per query would mean walking every term of
        # every candidate document on every search
        self._field_norms: dict[int, dict[str, float]] = {}

    # ---- writing -------------------------------------------------------

    def add(self, doc_id: int, analyzed: Mapping[str, Sequence[str]]) -> None:
        """Index one document from its already-analyzed fields.

        `analyzed` maps field name to the ordered term list produced by the
        Analyzer. Re-adding an existing doc_id replaces it, which is what makes
        the weekly re-crawl an update rather than a duplicate.
        """
        if doc_id in self._field_lengths:
            self.remove(doc_id)

        lengths: dict[str, int] = {}
        norms: dict[str, float] = {}
        distinct_terms: set[str] = set()

        for field_name, terms in analyzed.items():
            lengths[field_name] = len(terms)
            self._total_field_length[field_name] += len(terms)
            for position, term in enumerate(terms):
                doc_postings = self._postings[term]
                posting = doc_postings.get(doc_id)
                if posting is None:
                    posting = doc_postings[doc_id] = Posting(doc_id)
                posting.positions.setdefault(field_name, []).append(position)
                distinct_terms.add(term)

            # Document side of the classic lnc.ltc scheme: log-weighted term
            # frequency with no IDF. Leaving IDF off the document side is what
            # keeps this norm stable -- it depends only on the document's own
            # term counts, so adding another document never invalidates it.
            counts = Counter(terms)
            norms[field_name] = sqrt(
                sum((1.0 + log10(count)) ** 2 for count in counts.values())
            )

        self._field_lengths[doc_id] = lengths
        self._field_norms[doc_id] = norms
        self._terms_by_doc[doc_id] = distinct_terms

    def remove(self, doc_id: int) -> bool:
        """Delete a document. Returns False if it was not indexed."""
        terms = self._terms_by_doc.pop(doc_id, None)
        if terms is None:
            return False

        for term in terms:
            doc_postings = self._postings.get(term)
            if doc_postings is None:
                continue
            doc_postings.pop(doc_id, None)
            # Drop the term entirely once nothing references it, otherwise
            # document_frequency would count empty posting lists.
            if not doc_postings:
                del self._postings[term]

        for field_name, length in self._field_lengths.pop(doc_id).items():
            self._total_field_length[field_name] -= length
        self._field_norms.pop(doc_id, None)

        return True

    # ---- reading -------------------------------------------------------

    @property
    def document_count(self) -> int:
        """N -- the corpus size, the numerator of the IDF calculation."""
        return len(self._field_lengths)

    @property
    def vocabulary_size(self) -> int:
        return len(self._postings)

    def terms(self) -> Iterator[str]:
        return iter(self._postings)

    def postings(self, term: str) -> Mapping[int, Posting]:
        """Documents containing `term`, as a read-only view (empty if absent)."""
        return MappingProxyType(self._postings.get(term, {}))

    def document_frequency(self, term: str) -> int:
        """df -- how many documents contain the term.

        A high df means a common, uninformative term. IDF is built from this.
        """
        return len(self._postings.get(term, ()))

    def contains_document(self, doc_id: int) -> bool:
        return doc_id in self._field_lengths

    def field_length(self, doc_id: int, field_name: str) -> int:
        return self._field_lengths.get(doc_id, {}).get(field_name, 0)

    def document_length(self, doc_id: int) -> int:
        return sum(self._field_lengths.get(doc_id, {}).values())

    def field_norm(self, doc_id: int, field_name: str) -> float:
        """Cosine normalisation factor for one field of one document.

        Dividing by this is what stops a long abstract outranking a precise
        title purely by containing more words.
        """
        return self._field_norms.get(doc_id, {}).get(field_name, 0.0)

    def terms_in_document(self, doc_id: int) -> frozenset[str]:
        return frozenset(self._terms_by_doc.get(doc_id, ()))

    def average_field_length(self, field_name: str) -> float:
        """Mean length of a field across the corpus.

        BM25 compares a document's length against this average to stop long
        documents from scoring highly purely because they contain more words.
        """
        if not self._field_lengths:
            return 0.0
        return self._total_field_length[field_name] / len(self._field_lengths)

    def __len__(self) -> int:
        return self.document_count

    def __repr__(self) -> str:
        return (
            f"<InvertedIndex documents={self.document_count} "
            f"terms={self.vocabulary_size}>"
        )
