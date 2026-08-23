"""Run the CHCT crawler.

    uv run python scripts/crawl.py --once            # one crawl, then exit
    uv run python scripts/crawl.py --once --limit 10 # small run, for testing
    uv run python scripts/crawl.py --schedule        # weekly loop
    uv run python scripts/crawl.py --status          # when did it last run?

For real deployment prefer the OS scheduler over --schedule, e.g. a weekly
cron entry:

    0 3 * * 1  cd /path/to/backend && uv run python scripts/crawl.py --once
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from crawler import ChctCrawler, PoliteFetcher
from crawler.crawler import BASE_URL
from crawler.scheduler import WEEKLY_SECONDS, CrawlState, run_forever
from publications import DEFAULT_DATA_DIR, open_publications


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crawl CHCT publications.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="run a single crawl")
    mode.add_argument("--schedule", action="store_true", help="run weekly, forever")
    mode.add_argument("--status", action="store_true", help="show last-run info")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="maximum publications to index (for testing)",
    )
    parser.add_argument(
        "--interval-hours",
        type=float,
        default=None,
        help="override the weekly interval (for testing)",
    )
    parser.add_argument("--data-dir", default=None, help="collection directory")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    )

    data_dir = args.data_dir or DEFAULT_DATA_DIR
    state = CrawlState(data_dir)
    interval = args.interval_hours * 3600 if args.interval_hours else WEEKLY_SECONDS

    if args.status:
        last = state.last_run()
        print(f"data directory : {data_dir}")
        print(f"last run       : {last.isoformat() if last else 'never'}")
        print(f"due in         : {state.seconds_until_due(interval) / 3600:.1f} hours")
        stats = state.read().get("last_stats")
        if stats:
            print("last stats     :")
            print(json.dumps(stats, indent=2))
        return 0

    def crawl_once() -> dict:
        collection = open_publications(data_dir)
        fetcher = PoliteFetcher(BASE_URL)
        print(f"crawl delay from robots.txt: {fetcher.crawl_delay:.1f}s")
        try:
            crawler = ChctCrawler(
                collection, fetcher=fetcher, max_publications=args.limit
            )
            stats = crawler.crawl()
        finally:
            fetcher.close()
            collection.close()

        payload = stats.as_dict() | {"fetcher": fetcher.stats()}
        print(json.dumps(payload, indent=2))
        return payload

    if args.once:
        stats = crawl_once()
        state.write(stats)
        return 0

    run_forever(crawl_once, state, interval_seconds=interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
