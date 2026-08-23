"""Two models behind one protocol so they can be compared on identical data:
TF-IDF with cosine similarity (SMART lnc.ltc), and BM25. Both rest on the same
idea, that a term matters more when it is frequent in this document and rare
across the corpus."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import log, log10
from typing import Protocol

from .index import InvertedIndex


class Scorer(Protocol):
    """Anything that can rank documents for a query.

    Keeping this a protocol is what makes the two models swappable, and lets
    the report compare them on identical data rather than by assertion.
    """

    name: str

    def score(
        self,
        index: InvertedIndex,
        query_terms: Counter[str],
        field_weights: dict[str, float],
    ) -> dict[int, float]:
        """Return {doc_id: score} for documents matching at least one term."""
        ...


def _candidates(index: InvertedIndex, query_terms: Counter[str]) -> set[int]:
    """Documents containing at least one query term.

    Only these can score above zero, so scoring anything else is wasted work.
    This is why the inverted index exists: the candidate set is assembled from
    a handful of dictionary lookups rather than a scan of the corpus.
    """
    candidates: set[int] = set()
    for term in query_terms:
        candidates |= index.postings(term).keys()
    return candidates


@dataclass(slots=True)
class TfIdfScorer:
    """Vector space model with cosine similarity (SMART notation: lnc.ltc).

    Documents and queries are both vectors over the vocabulary; relevance is
    the cosine of the angle between them. Cosine rather than raw overlap
    because it is **length-invariant** -- a document is not more relevant
    merely for being longer.

    The two sides are weighted differently, which the SMART code spells out:

        document  lnc = log tf, no idf, cosine normalised
        query     ltc = log tf, idf,    cosine normalised

    IDF is applied on the query side only. Applying it to both would square
    the term's influence, and leaving it off the document side is what keeps
    document norms independent of corpus size -- so indexing a new document
    never invalidates the norms already computed.
    """

    name: str = "tf-idf"

    def score(
        self,
        index: InvertedIndex,
        query_terms: Counter[str],
        field_weights: dict[str, float],
    ) -> dict[int, float]:
        total_documents = index.document_count
        if total_documents == 0:
            return {}

        # Seeded with every candidate at zero so that a document matching only
        # a zero-IDF term still appears. Skipping such terms outright would
        # make a search for a word present in every document return *nothing*.
        scores: dict[int, float] = dict.fromkeys(_candidates(index, query_terms), 0.0)

        for term, query_count in query_terms.items():
            document_frequency = index.document_frequency(term)
            if document_frequency == 0:
                continue

            # A term in every document carries no discriminating power, and
            # log10(N/N) = 0 removes it from the ranking automatically.
            idf = log10(total_documents / document_frequency)
            query_weight = (1.0 + log10(query_count)) * idf
            if query_weight == 0.0:
                continue

            for doc_id, posting in index.postings(term).items():
                for field_name, positions in posting.positions.items():
                    weight = field_weights.get(field_name)
                    if weight is None:
                        continue
                    norm = index.field_norm(doc_id, field_name)
                    if norm == 0.0:
                        continue
                    document_weight = 1.0 + log10(len(positions))
                    scores[doc_id] = scores.get(doc_id, 0.0) + (
                        weight * query_weight * document_weight / norm
                    )
        return scores


@dataclass(slots=True)
class Bm25Scorer:
    """Okapi BM25 -- the default in Lucene, Elasticsearch and Typesense.

    BM25 fixes two things the vector space model handles crudely:

    **Term frequency saturates.** In tf-idf, a document mentioning "diabetes"
    100 times scores far above one mentioning it 10 times. In practice it is
    not ten times more relevant. BM25 grows tf towards an asymptote set by
    `k1`, so extra repetitions add progressively less.

    **Length normalisation is tunable.** `b` controls how strongly a document
    is penalised for being longer than average: b=1 applies it fully, b=0 not
    at all. Cosine normalisation is all-or-nothing by comparison.

    Defaults k1=1.2, b=0.75 are the values Robertson et al. found robust
    across the TREC collections, and remain the standard starting point.
    """

    k1: float = 1.2
    b: float = 0.75
    name: str = "bm25"

    def score(
        self,
        index: InvertedIndex,
        query_terms: Counter[str],
        field_weights: dict[str, float],
    ) -> dict[int, float]:
        total_documents = index.document_count
        if total_documents == 0:
            return {}

        average_lengths = {
            field: index.average_field_length(field) for field in field_weights
        }

        scores: dict[int, float] = dict.fromkeys(_candidates(index, query_terms), 0.0)

        for term in query_terms:
            document_frequency = index.document_frequency(term)
            if document_frequency == 0:
                continue

            # The probabilistic IDF. The +1 keeps it positive: without it a
            # term appearing in more than half the corpus would score
            # negatively and actively push its own matches down the ranking.
            idf = log(
                1.0
                + (total_documents - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )

            for doc_id, posting in index.postings(term).items():
                for field_name, positions in posting.positions.items():
                    weight = field_weights.get(field_name)
                    if weight is None:
                        continue
                    average_length = average_lengths.get(field_name, 0.0)
                    if average_length == 0.0:
                        continue

                    term_frequency = float(len(positions))
                    length_ratio = (
                        index.field_length(doc_id, field_name) / average_length
                    )
                    denominator = term_frequency + self.k1 * (
                        1.0 - self.b + self.b * length_ratio
                    )
                    saturated = term_frequency * (self.k1 + 1.0) / denominator
                    scores[doc_id] = scores.get(doc_id, 0.0) + (
                        weight * idf * saturated
                    )
        return scores


DEFAULT_SCORER: Scorer = Bm25Scorer()
SCORERS: dict[str, Scorer] = {
    "tf-idf": TfIdfScorer(),
    "bm25": Bm25Scorer(),
}
