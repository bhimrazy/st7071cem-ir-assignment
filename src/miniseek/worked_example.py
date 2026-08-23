from __future__ import annotations

import logging
import sys
from math import log

from miniseek.collection import Collection
from miniseek.schema import Field, Schema
from miniseek.store import Document

log_ = logging.getLogger("bm25")

K1 = 1.2
B = 0.75

DOCUMENTS = {
    "D1": "diabetes prevention trial",
    "D2": "diabetes diabetes diabetes management study",
    "D3": "community health nutrition exercise housing social care diabetes",
    "D4": "machine learning methods",
}


def idf(total_documents: int, document_frequency: int) -> float:
    return log(
        1.0 + (total_documents - document_frequency + 0.5) / (document_frequency + 0.5)
    )


def _require(collection: Collection, doc_id: str) -> Document:
    """Every document here was just added, so a miss is a bug, not a state."""
    document = collection.get(doc_id)
    if document is None:
        raise LookupError(f"{doc_id} is missing from the collection")
    return document


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # One field at weight 1.0, so the engine's score is directly comparable
    # to the textbook single-field formula.
    schema = Schema(fields=(Field("id", indexed=False), Field("body")))
    collection = Collection("worked-example", schema=schema)
    for doc_id, text in DOCUMENTS.items():
        collection.add({"id": doc_id, "body": text})

    index = collection.index
    total = index.document_count
    df = index.document_frequency("diabet")
    avgdl = index.average_field_length("body")
    term_idf = idf(total, df)

    log_.info(f"N={total}  df(diabet)={df}  avgdl={avgdl:.4f}  k1={K1}  b={B}")
    log_.info(f"IDF = {term_idf:.6f}\n")

    log_.info("IDF across every possible df:")
    for possible_df in range(1, total + 1):
        log_.info(f"  df={possible_df}  IDF={idf(total, possible_df):.6f}")

    log_.info(
        f"\n{'doc':4} {'tf':>3} {'|d|':>4} {'|d|/avgdl':>10} "
        f"{'denom':>8} {'sat':>7} {'score':>10}"
    )
    by_hand: dict[str, float] = {}
    for doc_id in DOCUMENTS:
        document = _require(collection, doc_id)
        posting = index.postings("diabet").get(document.internal_id)
        tf = posting.frequency_in("body") if posting else 0
        length = index.field_length(document.internal_id, "body")
        if tf == 0:
            log_.info(
                f"{doc_id:4} {tf:>3} {length:>4} {'-':>10} {'-':>8} "
                f"{'-':>7} {0.0:>10.6f}"
            )
            continue
        ratio = length / avgdl
        denominator = tf + K1 * (1.0 - B + B * ratio)
        saturated = tf * (K1 + 1.0) / denominator
        by_hand[doc_id] = term_idf * saturated
        log_.info(
            f"{doc_id:4} {tf:>3} {length:>4} {ratio:>10.4f} "
            f"{denominator:>8.4f} {saturated:>7.4f} {by_hand[doc_id]:>10.6f}"
        )

    log_.info("\nengine output vs hand calculation:")
    for hit in collection.search("diabetes", scorer="bm25"):
        expected = by_hand.get(hit.id, 0.0)
        status = "OK" if abs(hit.score - expected) < 1e-9 else "MISMATCH"
        log_.info(f"  {hit.id}  {hit.score:.6f}   hand={expected:.6f}  [{status}]")

    log_.info(f"\nsaturation curve at |d| = avgdl (asymptote k1+1 = {K1 + 1}):")
    for tf in (1, 2, 3, 5, 10, 25, 100, 1000):
        log_.info(f"  tf={tf:>5}  {tf * (K1 + 1) / (tf + K1):.4f}")

    log_.info("\nlength normalisation sweep for D3 (the long document):")
    d3 = _require(collection, "D3")
    length = index.field_length(d3.internal_id, "body")
    for b in (0.0, 0.25, 0.5, 0.75, 1.0):
        denominator = 1 + K1 * (1.0 - b + b * length / avgdl)
        log_.info(f"  b={b:<5} score={term_idf * 1 * (K1 + 1) / denominator:.6f}")

    collection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
