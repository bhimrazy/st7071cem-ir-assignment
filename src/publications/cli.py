from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from . import archive
from .index import open_publications
from .paths import CRAWLS_DIR, INDEX_DIR

log = logging.getLogger("index")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the search index from a crawl.")
    parser.add_argument("--crawl", help="crawl id to index (default: the newest)")
    parser.add_argument("--crawls-dir", help="where crawls are kept")
    parser.add_argument("--index-dir", help="where the index is written")
    parser.add_argument(
        "--append",
        action="store_true",
        help="add to the existing index instead of rebuilding it",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    )

    crawls_dir = Path(args.crawls_dir) if args.crawls_dir else CRAWLS_DIR
    index_dir = Path(args.index_dir) if args.index_dir else INDEX_DIR

    crawl = (
        archive.load(args.crawl, crawls_dir)
        if args.crawl
        else archive.latest(crawls_dir)
    )
    if crawl is None:
        log.error("no crawls under %s; run: uv run ir-crawl --once", crawls_dir)
        return 1

    log.info(
        "indexing crawl %s (%d publications)", crawl.crawl_id, crawl.publication_count
    )

    # Rebuilding by default, because the index is derived data and a stale
    # document that the newest crawl no longer contains should not survive.
    if index_dir.exists() and not args.append:
        shutil.rmtree(index_dir)
        log.info("rebuilt from empty")

    with open_publications(index_dir) as collection:
        added = collection.add_many(crawl.records())
        collection.flush()
        log.info("index holds %d documents at %s", len(collection), index_dir)

    log.info("added %d documents", added)
    return 0


if __name__ == "__main__":
    sys.exit(main())
