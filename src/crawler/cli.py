from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from crawler.crawler import BASE_URL, DEFAULT_ORGANISATION_URL, PortalCrawler
from crawler.fetcher import PoliteFetcher
from crawler.scheduler import WEEKLY_SECONDS, CrawlState, run_forever
from publications import archive
from publications.paths import CRAWLS_DIR, DATA_DIR, PROJECT_ROOT

DEFAULT_LISTINGS_DIR = DATA_DIR / "listings"

log = logging.getLogger("crawl")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Crawl an organisation's publications."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="run a single crawl")
    mode.add_argument("--schedule", action="store_true", help="run weekly, forever")
    mode.add_argument("--status", action="store_true", help="show past crawls")
    parser.add_argument(
        "--limit", type=int, help="maximum publications to keep (for testing)"
    )
    parser.add_argument(
        "--interval-hours", type=float, help="override the weekly schedule"
    )
    parser.add_argument("--crawls-dir", help="where crawl output is written")
    parser.add_argument(
        "--listing-snapshots",
        default=str(DEFAULT_LISTINGS_DIR),
        help=(
            "folder of hand-saved listing pages (<section>-page<N>.html), read "
            "instead of fetching a listing the portal blocks for us "
            f"(default: {DEFAULT_LISTINGS_DIR})"
        ),
    )
    parser.add_argument(
        "--cache-dir",
        nargs="?",
        const=str(PROJECT_ROOT / ".cache"),
        help=(
            "cache every successfully fetched page and reuse it on later runs, "
            "for local testing without repeatedly hitting the live site. "
            "Bare flag caches to <project root>/.cache; give a path to choose "
            "another. Off by default -- a real weekly crawl needs to keep "
            "re-fetching, or it will never notice a page changed."
        ),
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore --cache-dir and always fetch live",
    )
    parser.add_argument(
        "--log-file",
        help="also write logs here (default: <crawls-dir>/crawl.log)",
    )
    parser.add_argument(
        "--no-log-file", action="store_true", help="log to the console only"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    crawls_dir = Path(args.crawls_dir) if args.crawls_dir else CRAWLS_DIR

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if not args.no_log_file:
        log_path = Path(args.log_file) if args.log_file else crawls_dir / "crawl.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path))

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
        handlers=handlers,
    )
    # httpx/httpcore narrate every request at our own log level, duplicating
    # what the crawler already logs about the same page. Keep only warnings
    # and worse from them, even with -v.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    if not args.no_log_file:
        log.info("logging to %s", log_path)
    state = CrawlState(crawls_dir)
    interval = args.interval_hours * 3600 if args.interval_hours else WEEKLY_SECONDS

    if args.status:
        _report_status(state, crawls_dir, interval)
        return 0

    def crawl_once() -> dict:
        cache_dir = None if args.no_cache else args.cache_dir
        fetcher = PoliteFetcher(BASE_URL, cache_dir=cache_dir)
        log.info("crawl delay from robots.txt: %.1fs", fetcher.crawl_delay)
        try:
            result = PortalCrawler(
                fetcher=fetcher,
                max_publications=args.limit,
                listing_snapshot_dir=args.listing_snapshots,
            ).crawl()
        finally:
            fetcher.close()

        manifest = result.stats.as_dict() | {
            "organisation_url": DEFAULT_ORGANISATION_URL,
            "fetcher": fetcher.stats(),
        }
        crawl = archive.write(
            (publication.to_document() for publication in result.publications),
            manifest,
            root=crawls_dir,
        )
        log.info("wrote %d publications to %s", crawl.publication_count, crawl.path)
        log.info("index it with: uv run ir-index")
        return manifest

    if args.once:
        state.write(crawl_once())
        return 0

    run_forever(crawl_once, state, interval_seconds=interval)
    return 0


def _report_status(state: CrawlState, crawls_dir: object, interval: float) -> None:
    last = state.last_run()
    log.info("crawls directory: %s", crawls_dir)
    log.info("last run:         %s", last.isoformat() if last else "never")
    log.info("due in:           %.1f hours", state.seconds_until_due(interval) / 3600)
    for crawl in archive.all_crawls(Path(str(crawls_dir))):
        log.info(
            "  %s  %3d publications  %s",
            crawl.crawl_id,
            crawl.publication_count,
            crawl.manifest.get("finished_at", ""),
        )


if __name__ == "__main__":
    sys.exit(main())
