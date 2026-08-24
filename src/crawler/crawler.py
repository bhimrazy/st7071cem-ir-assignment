from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, NamedTuple

from .extract import (
    Publication,
    belongs_to_organisation,
    extract_person_links,
    extract_publication,
    extract_publication_links,
)
from .fetcher import DisallowedByRobots, Fetcher, FetchResult, PoliteFetcher

logger = logging.getLogger(__name__)


def _is_publication(url: str) -> bool:
    """The portal's URL scheme already says what a page is."""
    return "/en/publications/" in url


class PageResult(NamedTuple):
    """Links to follow next, and a line for the log saying what happened."""

    links: list[str]
    note: str


def _short(url: str) -> str:
    """The trailing slug, for readable logs."""
    return url.rstrip("/").rsplit("/", 1)[-1][:44]


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


BASE_URL = "https://pureportal.coventry.ac.uk"
# A guard on the listing walk, not an expectation. Reaching it means a listing
# paginates further than any organisation here plausibly needs.
MAX_LISTING_PAGES = 5
DEFAULT_ORGANISATION_SLUG = (
    "/organisations/centre-for-healthcare-and-community-transformation"
)
DEFAULT_ORGANISATION_URL = (
    f"{BASE_URL}/en/organisations/centre-for-healthcare-and-community-transformation/"
)


@dataclass(slots=True)
class CrawlStats:
    """What one crawl run did. Printed by the scheduler and used in the report."""

    started_at: str = ""
    finished_at: str = ""
    members_seeded: int = 0
    members_found: int = 0
    profiles_rejected: int = 0
    queue_remaining: int = 0
    publication_urls_seen: int = 0
    pages_fetched: int = 0
    publications_kept: int = 0
    affiliation_verified: int = 0
    skipped_unparseable: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "members_seeded": self.members_seeded,
            "members_found": self.members_found,
            "profiles_rejected": self.profiles_rejected,
            "queue_remaining": self.queue_remaining,
            "publication_urls_seen": self.publication_urls_seen,
            "pages_fetched": self.pages_fetched,
            "publications_kept": self.publications_kept,
            "affiliation_verified": self.affiliation_verified,
            "skipped_unparseable": self.skipped_unparseable,
            "errors": self.errors,
        }


@dataclass(slots=True)
class CrawlResult:
    """What one crawl produced: the records, and how the run went."""

    stats: CrawlStats
    publications: list[Publication]


class PortalCrawler:
    """Collects one organisation's publications from a Pure portal.

    It only gathers records. Storing and indexing them is somebody else's job,
    which is why nothing here imports the search library.

    Nothing here is specific to a department: the organisation is the page it
    starts from and the slug it recognises on a profile. The defaults point at
    the centre this coursework is about.
    """

    def __init__(
        self,
        *,
        fetcher: Fetcher | None = None,
        organisation_url: str = DEFAULT_ORGANISATION_URL,
        organisation_slug: str = DEFAULT_ORGANISATION_SLUG,
        max_publications: int | None = None,
        require_affiliation: bool = False,
    ) -> None:
        self.fetcher = fetcher or PoliteFetcher(BASE_URL)
        self.organisation_url = organisation_url
        self.organisation_slug = organisation_slug
        self.max_publications = max_publications
        # Reaching a publication through a member's profile already satisfies
        # the brief. Requiring the organisation to *also* appear in the paper's
        # own institution metadata discards valid work, because that metadata
        # records the affiliation on that paper, often a different centre. It is
        # counted either way as affiliation_verified.
        self.require_affiliation = require_affiliation
        # Filled during crawl(); a fresh list per run.
        self._collected: list[Publication] = []

    def crawl(self) -> CrawlResult:
        """Visit every page the queue reaches, adding the links each reveals.

        It terminates because no URL is queued twice, and it stays inside the
        organisation because only a profile that links the organisation is
        allowed to contribute publications.
        """
        stats = CrawlStats(started_at=_timestamp())
        self._collected = []
        queue = deque(self._seed(stats))
        seen = set(queue)

        while queue and not self._reached_limit(stats):
            url = queue.popleft()
            page = self._visit(url, stats)

            fresh = [link for link in page.links if link not in seen]
            seen.update(fresh)
            queue.extend(fresh)

            logger.info(
                "[%3d] %-11s %-46s %3d left | %s%s",
                len(seen) - len(queue),
                "publication" if _is_publication(url) else "profile",
                _short(url),
                len(queue),
                page.note,
                f", +{len(fresh)} queued" if fresh else "",
            )

        stats.queue_remaining = len(queue)
        stats.finished_at = _timestamp()
        stats.pages_fetched = self.fetcher.requests_made
        return CrawlResult(stats=stats, publications=self._collected)

    def _visit(self, url: str, stats: CrawlStats) -> PageResult:
        """Read one page and act on it, according to what kind it is."""
        result = self._fetch(url, stats)
        if result is None:
            return PageResult([], "unreachable")
        if _is_publication(url):
            return self._keep_publication(result.text, url, stats)
        return self._read_profile(result.text, url, stats)

    def _seed(self, stats: CrawlStats) -> list[str]:
        """Everything the organisation exposes: its listings, or failing that,
        whatever the organisation page itself links.

        The listings are the complete answer and the organisation page is a
        handful of highlights, so the listings are tried first. On this portal
        they are behind a bot check and the fallback is what actually runs.
        """
        logger.info("seed  %s", self.organisation_url)
        result = self._fetch(self.organisation_url, stats)
        if result is None:
            logger.warning("seed  organisation page unreachable, nothing to crawl")
            return []

        publications = self._listing("publications", extract_publication_links, stats)
        members = self._listing("persons", extract_person_links, stats)

        # This only bootstraps the queue; it is a handful of links, not the
        # full department. Co-author expansion during the crawl (see
        # _keep_publication) is what actually reaches the rest of it.
        if not publications:
            publications = extract_publication_links(result.text)
            logger.info(
                "seed  %d publications linked on the page instead", len(publications)
            )
        if not members:
            members = extract_person_links(result.text)
            logger.info("seed  %d members linked on the page instead", len(members))

        stats.members_seeded = len(members)
        # Publications first, so the corpus starts filling immediately and
        # --limit cuts off at a predictable place.
        return publications + members

    def _listing(
        self,
        section: str,
        extract: Callable[[str], list[str]],
        stats: CrawlStats,
    ) -> list[str]:
        """Page through one of the organisation's listings, if it serves us.

        Pure paginates with `?page=` from 0. Stops on the first page that
        cannot be read or that adds nothing, so an empty result means the
        listing is unavailable rather than empty.
        """
        found: list[str] = []
        for page in range(MAX_LISTING_PAGES):
            url = f"{self.organisation_url.rstrip('/')}/{section}/?page={page}"
            result = self._fetch(url, stats, record_errors=False)
            if result is None:
                logger.info("seed  %s page %d unavailable", section, page)
                break
            new = [link for link in extract(result.text) if link not in found]
            logger.info("seed  %s page %d gave %d new links", section, page, len(new))
            if not new:
                break
            found.extend(new)
        return found

    def _keep_publication(self, html: str, url: str, stats: CrawlStats) -> PageResult:
        """Store one publication, and hand back its co-authors' profiles."""
        stats.publication_urls_seen += 1
        publication = extract_publication(html, url)
        if publication is None:
            stats.skipped_unparseable += 1
            return PageResult([], "not a publication page")

        if publication.is_affiliated:
            stats.affiliation_verified += 1
        if publication.is_affiliated or not self.require_affiliation:
            self._collected.append(publication)
            stats.publications_kept += 1
            note = f"kept ({stats.publications_kept} so far)"
        else:
            note = "skipped, not affiliated"

        # Every profile the page links, not just the ones pairing matched to a
        # name: pairing is for display, and a link we cannot attribute is still
        # a member worth visiting.
        profiles = extract_person_links(html)
        return PageResult(profiles, f"{note}, {len(profiles)} profile links")

    def _read_profile(self, html: str, url: str, stats: CrawlStats) -> PageResult:
        """Take this person's publications, if they belong to the organisation."""
        if not belongs_to_organisation(html, self.organisation_slug):
            stats.profiles_rejected += 1
            return PageResult([], "not a member")

        stats.members_found += 1
        publications = extract_publication_links(html)
        return PageResult(publications, f"member, {len(publications)} publications")

    def _fetch(
        self, url: str, stats: CrawlStats, *, record_errors: bool = True
    ) -> FetchResult | None:
        """One page, or None if it could not be read. A 304 counts as nothing new.

        `record_errors` is off when probing a listing, because a bot check
        there is expected and the fallback handles it.
        """
        try:
            result = self.fetcher.fetch(url)
        except (DisallowedByRobots, Exception) as error:
            if record_errors:
                stats.errors.append(f"{url}: {error}")
            return None
        if result.unchanged:
            return None
        if not result.ok:
            if record_errors:
                stats.errors.append(f"{url} returned {result.status_code}")
            return None
        return result

    def _reached_limit(self, stats: CrawlStats) -> bool:
        return (
            self.max_publications is not None
            and stats.publications_kept >= self.max_publications
        )
