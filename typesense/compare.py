"""Run the same query against miniseek and Typesense, side by side.

uv run python typesense/compare.py "mental health"
uv run python typesense/compare.py --typo
"""

from __future__ import annotations

import argparse
import sys

import httpx
from load import COLLECTION, DEFAULT_API_KEY, DEFAULT_URL, QUERY_BY, QUERY_BY_WEIGHTS

from miniseek.collection import Collection
from publications.index import open_publications
from publications.paths import INDEX_DIR

# Picked to make the two disagree in instructive ways: a plain query, one where
# miniseek's stemming collides, and one where query coverage matters.
DEFAULT_QUERIES = [
    "mental health",
    "community transformation",
    "sleep quality students",
    "diabetes prevention",
]

TYPO_QUERIES = ["diabites prevention", "mentl health", "randomised trail"]


def miniseek_hits(collection: Collection, query: str, limit: int, scorer: str):
    return [
        (hit.score, hit.fields.get("title", ""))
        for hit in collection.search(query, limit=limit, scorer=scorer)
    ]


def typesense_hits(client: httpx.Client, query: str, limit: int, typos: int):
    response = client.get(
        f"/collections/{COLLECTION}/documents/search",
        params={
            "q": query,
            "query_by": QUERY_BY,
            "query_by_weights": QUERY_BY_WEIGHTS,
            "per_page": limit,
            "num_typos": typos,
        },
    )
    response.raise_for_status()
    body = response.json()
    hits = [
        (hit["text_match"], hit["document"].get("title", ""))
        for hit in body.get("hits", [])
    ]
    return hits, body.get("found", 0)


def show(query, left, left_total, right, right_total) -> None:
    print(f"\n\033[1m{query!r}\033[0m")
    print(f"  miniseek — {left_total} match(es)")
    for rank, (score, title) in enumerate(left, 1):
        print(f"    {rank}. {score:9.3f}  {title[:62]}")
    print(f"  typesense — {right_total} match(es)")
    for rank, (score, title) in enumerate(right, 1):
        print(f"    {rank}. {score:>9}  {title[:62]}")
    if left and right:
        agree = left[0][1] == right[0][1]
        print(f"  -> {'same top hit' if agree else 'DIFFERENT top hit'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare miniseek and Typesense on the same corpus."
    )
    parser.add_argument("queries", nargs="*", help="queries (default: a fixed set)")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--api-key", default=DEFAULT_API_KEY)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--scorer", default="bm25", choices=["bm25", "tf-idf"])
    parser.add_argument(
        "--typo",
        action="store_true",
        help="run misspelled queries, which only Typesense can answer",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    queries = TYPO_QUERIES if args.typo else (args.queries or DEFAULT_QUERIES)

    headers = {"X-TYPESENSE-API-KEY": args.api_key}
    with (
        httpx.Client(base_url=args.url, headers=headers, timeout=30.0) as client,
        open_publications(INDEX_DIR, read_only=True) as collection,
    ):
        try:
            client.get("/health").raise_for_status()
        except httpx.HTTPError as error:
            print(
                f"cannot reach Typesense at {args.url} ({error}).\n"
                "Start it with:  cd typesense && docker compose up -d\n"
                "then load it:   uv run python typesense/load.py",
                file=sys.stderr,
            )
            return 1

        print(f"miniseek scorer: {args.scorer} · field weights {QUERY_BY_WEIGHTS}")
        if args.typo:
            print("misspelled queries: miniseek has no typo tolerance at all")

        for query in queries:
            left = miniseek_hits(collection, query, args.limit, args.scorer)
            left_total = collection.search(query, limit=1, scorer=args.scorer).total
            right, right_total = typesense_hits(
                client, query, args.limit, typos=2 if args.typo else 0
            )
            show(query, left, left_total, right, right_total)

    return 0


if __name__ == "__main__":
    sys.exit(main())
