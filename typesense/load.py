"""Load the crawled publications into a local Typesense, shaped like the
miniseek collection. Run `docker compose up -d` first."""

from __future__ import annotations

import argparse
import json
import sys

import httpx

from publications import archive
from publications.paths import CRAWLS_DIR

DEFAULT_URL = "http://127.0.0.1:8108"
DEFAULT_API_KEY = "localdev"
COLLECTION = "publications"

# miniseek weights fields in the schema, Typesense per query. Same numbers as
# publications/index.py.
QUERY_BY = "title,authors,abstract,journal"
QUERY_BY_WEIGHTS = "3,2,1,1"

SCHEMA = {
    "name": COLLECTION,
    "fields": [
        {"name": "title", "type": "string"},
        {"name": "authors", "type": "string[]", "facet": True},
        {"name": "abstract", "type": "string", "optional": True},
        {"name": "journal", "type": "string", "optional": True, "facet": True},
        {"name": "year", "type": "int32", "optional": True, "facet": True},
        {"name": "url", "type": "string", "index": False, "optional": True},
        {"name": "doi", "type": "string", "index": False, "optional": True},
    ],
    "default_sorting_field": "",
}


def to_typesense(record: dict) -> dict:
    """One crawled publication as a Typesense document.

    The id is the URL's trailing slug rather than the URL itself: Typesense
    puts the id in the path of its per-document endpoints, so slashes are a
    nuisance. The full URL stays in `url`.
    """
    url = record.get("url") or record["id"]
    year = record.get("year") or ""
    document = {
        "id": url.rstrip("/").rsplit("/", 1)[-1],
        "title": record.get("title") or "",
        "authors": [a["name"] for a in record.get("authors", []) if a.get("name")],
        "abstract": record.get("abstract") or "",
        "journal": record.get("journal") or "",
        "url": url,
        "doi": record.get("doi") or "",
    }
    if year.isdigit():
        document["year"] = int(year)
    return document


def load(client: httpx.Client, records: list[dict]) -> int:
    """Recreate the collection and import every record.

    Dropped rather than upserted so a schema change between runs cannot leave
    the comparison measuring two different shapes.
    """
    client.delete(f"/collections/{COLLECTION}")
    client.post("/collections", json=SCHEMA).raise_for_status()

    payload = "\n".join(
        json.dumps(to_typesense(r), ensure_ascii=False) for r in records
    )
    imported = client.post(
        f"/collections/{COLLECTION}/documents/import",
        params={"action": "create"},
        content=payload.encode("utf-8"),
        headers={"Content-Type": "text/plain"},
    )
    imported.raise_for_status()

    # Import answers 200 even when rows fail, one JSON result per line, so the
    # status code alone would report success for an empty collection.
    failures = [
        line
        for line in imported.text.splitlines()
        if line and not json.loads(line).get("success")
    ]
    if failures:
        print(f"{len(failures)} document(s) failed to import:", file=sys.stderr)
        for line in failures[:5]:
            print(f"  {line}", file=sys.stderr)
        raise SystemExit(1)

    return len(records)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load the crawled publications into a local Typesense."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Typesense base URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY)
    parser.add_argument("--crawl", help="crawl id to load (default: the newest)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    crawl = (
        archive.load(args.crawl, CRAWLS_DIR)
        if args.crawl
        else archive.latest(CRAWLS_DIR)
    )
    if crawl is None:
        print("no crawls found; run: uv run ir-crawl --once", file=sys.stderr)
        return 1

    records = list(crawl.records())
    headers = {"X-TYPESENSE-API-KEY": args.api_key}

    with httpx.Client(base_url=args.url, headers=headers, timeout=30.0) as client:
        try:
            client.get("/health").raise_for_status()
        except httpx.HTTPError as error:
            print(
                f"cannot reach Typesense at {args.url} ({error}).\n"
                "Start it with:  cd typesense && docker compose up -d",
                file=sys.stderr,
            )
            return 1

        count = load(client, records)

    print(f"loaded {count} documents from crawl {crawl.crawl_id} into {COLLECTION!r}")
    print("try:  uv run python typesense/compare.py 'mental health'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
