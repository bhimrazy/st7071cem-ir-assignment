from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from crawler.crawler import BASE_URL, DEFAULT_ORGANISATION_URL, PortalCrawler
from crawler.fetcher import PoliteFetcher
from crawler.scheduler import (
    WEEKLY_SECONDS,
    CrawlState,
    format_duration,
    parse_interval,
    run_forever,
)
from publications import archive
from publications.paths import CRAWLS_DIR, DATA_DIR

DEFAULT_LISTINGS_DIR = DATA_DIR / "listings"
LOG_FORMAT = "%(asctime)s  %(levelname)-7s %(name)s  %(message)s"

log = logging.getLogger("crawl")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Crawl an organisation's publications.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  ir-crawl --once\n"
            "  ir-crawl --once --limit 4                 # quick test crawl\n"
            "  ir-crawl --schedule                        # weekly, the default\n"
            "  ir-crawl --schedule 100h\n"
            "  ir-crawl --schedule 2weeks\n"
            "  ir-crawl --schedule 1month\n"
            "  ir-crawl --schedule 3months\n"
            "  ir-crawl --schedule 1min --limit 4         # exercise the loop fast\n"
            "  ir-crawl --once --limit 4 --skip-delay     # fastest local test\n"
            "  ir-crawl --status\n"
        ),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="run a single crawl")
    mode.add_argument(
        "--schedule",
        nargs="?",
        const="1week",
        metavar="INTERVAL",
        help=(
            "run repeatedly, forever, waiting INTERVAL between crawls -- a "
            "number plus a unit: minutes (min), hours (h), days (d), weeks "
            "(w), or months (mo). E.g. 1min, 100h, 2weeks, 1month. Defaults "
            "to 1week if you just pass the bare flag. See the examples below."
        ),
    )
    mode.add_argument("--status", action="store_true", help="show past crawls")
    parser.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="stop after keeping N publications, for a quick test crawl",
    )
    parser.add_argument("--crawls-dir", help="where crawl output is written")
    parser.add_argument(
        "--skip-delay",
        action="store_true",
        help=(
            "don't wait between requests -- normally robots.txt's Crawl-delay "
            "(5s here). For a fast local test crawl only -- a real crawl "
            "against the live portal should leave this alone."
        ),
    )
    parser.add_argument(
        "--log-file",
        help=(
            "also write logs here, instead of inside this run's own crawl "
            "directory (the default)"
        ),
    )
    parser.add_argument(
        "--no-log-file", action="store_true", help="log to the console only"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    crawls_dir = Path(args.crawls_dir) if args.crawls_dir else CRAWLS_DIR

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format=LOG_FORMAT,
        handlers=[logging.StreamHandler()],
    )
    # httpx/httpcore narrate every request at our own log level, duplicating
    # what the crawler already logs about the same page. Keep only warnings
    # and worse from them, even with -v.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    state = CrawlState(crawls_dir)
    if args.schedule:
        try:
            interval = parse_interval(args.schedule)
        except ValueError as error:
            parser.error(str(error))
    else:
        interval = WEEKLY_SECONDS

    if args.status:
        _report_status(state, crawls_dir, interval)
        return 0

    def crawl_once() -> dict:
        # Chosen upfront so the log can be written under this run's own crawl
        # id from the first line, not just after archive.write() picks one.
        crawl_id = archive.new_crawl_id()
        log_handler, log_path = _open_run_log(args, crawls_dir, crawl_id)

        try:
            fetcher = PoliteFetcher(
                BASE_URL, min_delay=0.0 if args.skip_delay else None
            )
            source = "--skip-delay" if args.skip_delay else "robots.txt"
            log.info("crawl delay: %.1fs (from %s)", fetcher.crawl_delay, source)
            try:
                result = PortalCrawler(
                    fetcher=fetcher,
                    max_publications=args.limit,
                    listing_snapshot_dir=DEFAULT_LISTINGS_DIR,
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
                people=(person.to_document() for person in result.people),
                root=crawls_dir,
                crawl_id=crawl_id,
            )
            log.info(
                "wrote %d publications and %d profiles to %s",
                crawl.publication_count,
                crawl.person_count,
                crawl.path,
            )
            log.info("index it with: uv run ir-index")
            return manifest
        finally:
            # archive.write() owns crawl.path and would have wiped anything
            # placed there before it existed, so the log is moved in now,
            # last, once that directory is guaranteed to be there.
            if log_handler is not None:
                logging.getLogger().removeHandler(log_handler)
                log_handler.close()
                if log_path is not None and not args.log_file:
                    final_dir = crawls_dir / crawl_id
                    if final_dir.is_dir():
                        log_path.replace(final_dir / "crawl.log")

    if args.once:
        state.write(crawl_once())
        return 0

    run_forever(crawl_once, state, interval_seconds=interval)
    return 0


def _open_run_log(
    args: argparse.Namespace, crawls_dir: Path, crawl_id: str
) -> tuple[logging.Handler | None, Path | None]:
    """Start logging this run to a file, if wanted.

    Written under `crawls_dir` first rather than straight into the crawl's
    own (not-yet-existing) directory -- crawl_once() moves it there once
    archive.write() has actually created that directory.
    """
    if args.no_log_file:
        return None, None
    log_path = Path(args.log_file) if args.log_file else crawls_dir / f"{crawl_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.getLogger().addHandler(handler)
    log.info("logging to %s", log_path)
    return handler, log_path


def _report_status(state: CrawlState, crawls_dir: object, interval: float) -> None:
    last = state.last_run()
    log.info("crawls directory: %s", crawls_dir)
    log.info("last run:         %s", last.isoformat() if last else "never")
    log.info("due in:           %s", format_duration(state.seconds_until_due(interval)))
    for crawl in archive.all_crawls(Path(str(crawls_dir))):
        log.info(
            "  %s  %3d publications  %3d profiles  %s",
            crawl.crawl_id,
            crawl.publication_count,
            crawl.person_count,
            crawl.manifest.get("finished_at", ""),
        )


if __name__ == "__main__":
    sys.exit(main())
