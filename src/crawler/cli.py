from __future__ import annotations

import argparse
import json
import logging
import sys

from crawler.crawler import BASE_URL, ChctCrawler
from crawler.fetcher import PoliteFetcher
from crawler.scheduler import WEEKLY_SECONDS, CrawlState, run_forever
from publications import DEFAULT_DATA_DIR, open_publications

log = logging.getLogger("crawl")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crawl CHCT publications.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="run a single crawl")
    mode.add_argument("--schedule", action="store_true", help="run weekly, forever")
    mode.add_argument("--status", action="store_true", help="show last-run info")
    parser.add_argument(
        "--limit", type=int, help="maximum publications to index (for testing)"
    )
    parser.add_argument(
        "--interval-hours", type=float, help="override the weekly schedule"
    )
    parser.add_argument("--data-dir", help="where the collection is stored")
    parser.add_argument("-v", "--verbose", action="store_true")
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
        _report_status(state, data_dir, interval)
        return 0

    def crawl_once() -> dict:
        collection = open_publications(data_dir)
        fetcher = PoliteFetcher(BASE_URL)
        log.info("crawl delay from robots.txt: %.1fs", fetcher.crawl_delay)
        try:
            crawler = ChctCrawler(
                collection, fetcher=fetcher, max_publications=args.limit
            )
            stats = crawler.crawl()
        finally:
            fetcher.close()
            collection.close()

        payload = stats.as_dict() | {"fetcher": fetcher.stats()}
        log.info("crawl finished: %s", json.dumps(payload))
        return payload

    if args.once:
        state.write(crawl_once())
        return 0

    run_forever(crawl_once, state, interval_seconds=interval)
    return 0


def _report_status(state: CrawlState, data_dir: object, interval: float) -> None:
    last = state.last_run()
    log.info("data directory: %s", data_dir)
    log.info("last run:       %s", last.isoformat() if last else "never")
    log.info("due in:         %.1f hours", state.seconds_until_due(interval) / 3600)
    if stats := state.read().get("last_stats"):
        log.info("last stats:     %s", json.dumps(stats))


if __name__ == "__main__":
    sys.exit(main())
