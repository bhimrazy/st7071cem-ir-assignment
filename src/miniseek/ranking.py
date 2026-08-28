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

    @property
    def name(self) -> str:
        """What to call this scorer in a result and in the API.

        Read-only on purpose. A plain `name: str` would demand a *settable*
        attribute, which rules out any implementation that derives its name
        rather than storing one -- `Coordinated` wraps another scorer and
        reports that scorer's name. Nothing renames a scorer, so requiring
        the write was overreach.
        """
        ...

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


@dataclass(slots=True)
class Coordinated:
    """Scales another scorer's output by how much of the query a document covers.

    Both models above sum a contribution per matching term, and say nothing
    about the terms that did *not* match. One strong term can therefore
    outscore genuine coverage. On this corpus, searching
    "digital intervention mental health" put a paper matching three of the
    four terms above one matching all four, and "sleep quality students"
    buried the only two-of-three match under five documents matching a single
    term. Both are the same failure: a query is a statement of what the reader
    wants, and matching more of it should count for something.

    The fix is Lucene's classic coordination factor -- multiply by the
    fraction of the query the document actually contains:

        coord(q, d) = matching query terms in d / query terms that exist

    The denominator counts only terms the index has ever seen, so a query
    containing a word in no document ("transformation", which stems to a term
    with df=0 here) does not quietly penalise every result. Without that, the
    factor would be a constant below 1 -- harmless to the ordering, but it
    would make the scores lie about how well anything matched.

    This multiplies rather than adds so it stays a proportion of whatever the
    inner model produced, which keeps BM25 and TF-IDF comparable afterwards:
    each is scaled by the same factor, so the comparison in the report still
    measures the two models against each other rather than against two
    different corrections.

    Lucene dropped coord when it moved to BM25, on the grounds that BM25's
    saturation already limits how far one repeated term can carry a document.
    That reasoning holds for long documents; it holds less well here, where
    the fields are a title and an abstract and a single well-placed title
    term is easily enough to win outright.
    """

    inner: Scorer

    @property
    def name(self) -> str:
        """The inner scorer's name, since this is a correction and not a model.

        Keeping the name means `?scorer=bm25` still selects BM25 and the API
        contract does not change; what changed is that BM25 now accounts for
        query coverage.
        """
        return self.inner.name

    def score(
        self,
        index: InvertedIndex,
        query_terms: Counter[str],
        field_weights: dict[str, float],
    ) -> dict[int, float]:
        scores = self.inner.score(index, query_terms, field_weights)

        # Only terms the index knows can be covered, so only they can count
        # towards the denominator.
        findable = [t for t in query_terms if index.document_frequency(t) > 0]
        if len(findable) < 2:
            # One term (or none): every candidate covers all of the findable
            # query, so the factor is 1.0 for everything and the multiply is
            # pure arithmetic. Skipping it keeps single-term search exact.
            return scores

        overlap: Counter[int] = Counter()
        for term in findable:
            overlap.update(index.postings(term).keys())

        total = float(len(findable))
        return {
            doc_id: score * (overlap[doc_id] / total)
            for doc_id, score in scores.items()
        }


# Coordination is on by default because the uncoordinated ranking is wrong in
# a way a reader notices immediately. The bare scorers stay importable so the
# report can quantify what the correction is worth rather than assert it.
DEFAULT_SCORER: Scorer = Coordinated(Bm25Scorer())
SCORERS: dict[str, Scorer] = {
    "tf-idf": Coordinated(TfIdfScorer()),
    "bm25": Coordinated(Bm25Scorer()),
}
