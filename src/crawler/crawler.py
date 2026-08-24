from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

from .extract import (
    Person,
    Publication,
    belongs_to_organisation,
    extract_person,
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


# Local to Kathmandu rather than UTC, so a timestamp in a log or a manifest
# reads the same as the clock on the wall.
KATHMANDU = ZoneInfo("Asia/Kathmandu")


def _timestamp() -> str:
    return datetime.now(KATHMANDU).isoformat(timespec="seconds")


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
    people: list[Person]


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
        listing_snapshot_dir: Path | str | None = None,
    ) -> None:
        self.fetcher = fetcher or PoliteFetcher(BASE_URL)
        self.organisation_url = organisation_url
        self.organisation_slug = organisation_slug
        self.max_publications = max_publications
        # A folder of listing pages saved by hand (the portal's bot check blocks
        # them for us, but not for a person browsing normally). A file named
        # "<section>-page<N>.html" here is used instead of fetching that page.
        self.listing_snapshot_dir = (
            Path(listing_snapshot_dir) if listing_snapshot_dir else None
        )
        # Reaching a publication through a member's profile already satisfies
        # the brief. Requiring the organisation to *also* appear in the paper's
        # own institution metadata discards valid work, because that metadata
        # records the affiliation on that paper, often a different centre. It is
        # counted either way as affiliation_verified.
        self.require_affiliation = require_affiliation
        # Filled during crawl(); a fresh list per run.
        self._collected: list[Publication] = []
        self._people: list[Person] = []

    def crawl(self) -> CrawlResult:
        """Crawl in three phases: every publication the listing names --
        fetching each co-author's profile the moment it's referenced, rather
        than waiting for phase 2 -- then whichever listed member profiles
        weren't already picked up that way, then whatever either phase
        referenced that still hasn't been crawled *and is on the listing*.

        Fetching a co-author's profile inline in phase 1 is what makes
        persons.jsonl reflect the authors of whatever publications actually
        got kept, even on a `--limit`-capped test crawl that never reaches
        phase 2. Phase 3 is what makes the whole thing terminate and stay
        inside the organisation even when the listing is incomplete or
        missing entirely: it keeps expanding through new links until nothing
        new turns up, exactly the way the whole crawl used to work before
        there was a listing to seed from.

        A member's profile lists everything they have ever published, not
        just work affiliated with this centre, so phase 3 only chases a
        profile-referenced publication down when it's also one the listing
        itself named -- being *reachable* through a member isn't reason
        enough to treat it as belonging to the organisation. If the listing
        gave us nothing at all (both it and the organisation-page fallback
        came up empty), there is nothing to check against, so every
        referenced publication is pursued instead -- the same full BFS
        reachability this crawler relied on before there was a listing.
        """
        stats = CrawlStats(started_at=_timestamp())
        self._collected = []
        self._people = []
        # Every URL actually fetched so far, whichever phase did it -- the
        # single source of truth for "don't fetch this again".
        visited: set[str] = set()
        # Publications a visited profile lists, however that profile was
        # reached (phase 1's inline fetch or phase 2's listing walk). What
        # phase 3 still needs to crawl is this, minus what's already visited
        # and (see docstring) filtered down to known_publications.
        referenced_publications: set[str] = set()

        publication_urls, member_urls = self._seed(stats)
        known_publications = set(publication_urls)

        logger.info(
            "Phase 1: crawling %d publication(s) from the listing, fetching "
            "each co-author's profile as soon as it's referenced",
            len(publication_urls),
        )
        queue = deque(publication_urls)
        while queue and not self._reached_limit(stats):
            url = queue.popleft()
            page = self._visit(url, stats)
            visited.add(url)
            logger.info(
                "  done: %s (%d kept so far)", page.note, stats.publications_kept
            )
            for author_url in page.links:
                if author_url in visited:
                    logger.info(
                        "  already have %s from an earlier publication, skipping",
                        author_url,
                    )
                    continue
                visited.add(author_url)
                profile = self._visit(author_url, stats)
                referenced_publications.update(profile.links)
        stats.queue_remaining = len(queue)

        if not self._reached_limit(stats):
            pending_members = [url for url in member_urls if url not in visited]
            logger.info(
                "Phase 2: crawling %d member profile(s) from the listing not "
                "already fetched in phase 1 (%d of %d already have one)",
                len(pending_members),
                len(member_urls) - len(pending_members),
                len(member_urls),
            )
            for url in pending_members:
                page = self._visit(url, stats)
                visited.add(url)
                referenced_publications.update(page.links)
                logger.info(
                    "  done: %s (%d members found so far)",
                    page.note,
                    stats.members_found,
                )

            missing = referenced_publications - visited
            skipped_unlisted = 0
            if known_publications:
                before = len(missing)
                missing &= known_publications
                skipped_unlisted = before - len(missing)

            if missing:
                logger.info(
                    "Phase 3: %d publication link(s) referenced by a profile "
                    "but not yet crawled; crawling them too%s",
                    len(missing),
                    f" ({skipped_unlisted} other referenced link(s) skipped -- "
                    "not on the listing)"
                    if skipped_unlisted
                    else "",
                )
                queue = deque(missing)
                visited.update(queue)
                while queue and not self._reached_limit(stats):
                    page = self._visit(queue.popleft(), stats)
                    fresh = [
                        link
                        for link in page.links
                        if link not in visited
                        and (
                            not known_publications
                            or not _is_publication(link)
                            or link in known_publications
                        )
                    ]
                    visited.update(fresh)
                    queue.extend(fresh)
                    logger.info(
                        "  done: %s, %d new link(s) found", page.note, len(fresh)
                    )
                stats.queue_remaining += len(queue)
            elif skipped_unlisted:
                logger.info(
                    "Phase 3: %d publication link(s) referenced by a profile "
                    "but not on the listing; not crawling them",
                    skipped_unlisted,
                )
            else:
                logger.info(
                    "Phase 3: nothing missing -- everything referenced was "
                    "already crawled"
                )
        else:
            stats.queue_remaining += len(
                [url for url in member_urls if url not in visited]
            )

        stats.finished_at = _timestamp()
        stats.pages_fetched = self.fetcher.requests_made
        return CrawlResult(
            stats=stats, publications=self._collected, people=self._people
        )

    def _visit(self, url: str, stats: CrawlStats) -> PageResult:
        """Read one page and act on it, according to what kind it is."""
        kind = "publication" if _is_publication(url) else "profile"
        logger.info("Visiting %s page: %s", kind, url)
        result = self._fetch(url, stats)
        if result is None:
            logger.info("  could not be read, skipping it")
            return PageResult([], "page could not be read")
        if kind == "publication":
            return self._keep_publication(result.text, url, stats)
        return self._read_profile(result.text, url, stats)

    def _seed(self, stats: CrawlStats) -> tuple[list[str], list[str]]:
        """The organisation's publications and its members, as two separate
        lists, from its listings or -- failing that -- the organisation page
        itself.

        The listings are the complete answer and the organisation page is a
        handful of highlights, so the listings are tried first. On this portal
        they are behind a bot check and the fallback is what actually runs.
        """
        logger.info("Visiting the organisation page: %s", self.organisation_url)
        result = self._fetch(self.organisation_url, stats)
        if result is None:
            logger.warning("  could not be read, so there is nothing to crawl")
            return [], []
        logger.info("  read successfully")

        publications = self._listing("publications", extract_publication_links, stats)
        members = self._listing("persons", extract_person_links, stats)

        # This only bootstraps phase 1/2; it is a handful of links, not the
        # full department. Phase 3 (see crawl()) is what actually reaches the
        # rest of it when this fallback is what ran.
        if not publications:
            publications = extract_publication_links(result.text)
            logger.info(
                "No publications listing available; using the %d publication "
                "link(s) on the organisation page itself instead",
                len(publications),
            )
        if not members:
            members = extract_person_links(result.text)
            logger.info(
                "No persons listing available; using the %d member link(s) "
                "on the organisation page itself instead",
                len(members),
            )

        stats.members_seeded = len(members)
        return publications, members

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
            logger.info("Visiting %s listing, page %d: %s", section, page, url)
            result = self._fetch(url, stats, record_errors=False)
            if result is not None:
                html = result.text
            else:
                snapshot_path = self._snapshot_path(section, page)
                if not snapshot_path.is_file():
                    logger.info("  no saved copy of this page either, stopping here")
                    break
                logger.info("  using the saved copy instead: %s", snapshot_path)
                html = snapshot_path.read_text(encoding="utf-8")
            links = extract(html)
            new = [link for link in links if link not in found]
            logger.info(
                "  found %d link(s) on this page, %d of them new", len(links), len(new)
            )
            if not new:
                break
            found.extend(new)
        return found

    def _snapshot_path(self, section: str, page: int) -> Path:
        """Where a hand-saved copy of one listing page would be, if provided."""
        directory = self.listing_snapshot_dir or Path()
        return directory / f"{section}-page{page}.html"

    def _keep_publication(self, html: str, url: str, stats: CrawlStats) -> PageResult:
        """Store one publication, and hand back its co-authors' profiles."""
        stats.publication_urls_seen += 1
        publication = extract_publication(html, url)
        if publication is None:
            stats.skipped_unparseable += 1
            logger.info("  this is not a publication page, skipping it")
            return PageResult([], "not a publication page")

        logger.info(
            "  found %r by %d author(s), published in %s (%s)",
            publication.title,
            len(publication.authors),
            publication.journal or "an unknown venue",
            publication.year or "unknown year",
        )

        if publication.is_affiliated:
            stats.affiliation_verified += 1
        if publication.is_affiliated or not self.require_affiliation:
            self._collected.append(publication)
            stats.publications_kept += 1
            note = f"kept publication ({stats.publications_kept} so far)"
        else:
            note = "skipped, not affiliated with the organisation"

        # Every profile the page links, not just the ones pairing matched to a
        # name: pairing is for display, and a link we cannot attribute is still
        # a member worth visiting.
        profiles = extract_person_links(html)
        logger.info("  references %d author profile link(s)", len(profiles))
        return PageResult(profiles, note)

    def _read_profile(self, html: str, url: str, stats: CrawlStats) -> PageResult:
        """Take this person's publications, if they belong to the organisation."""
        if not belongs_to_organisation(html, self.organisation_slug):
            stats.profiles_rejected += 1
            logger.info(
                "  not a member of the organisation, skipping their publications"
            )
            return PageResult([], "not a member of the organisation")

        stats.members_found += 1
        person = extract_person(html, url)
        if person is not None:
            self._people.append(person)
            logger.info(
                "  found %r, with a %d-character biography",
                person.name,
                len(person.biography),
            )

        publications = extract_publication_links(html)
        logger.info("  lists %d publication link(s)", len(publications))
        return PageResult(publications, "confirmed member")

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
            logger.info("  failed to fetch: %s", error)
            if record_errors:
                stats.errors.append(f"{url}: {error}")
            return None
        if result.unchanged:
            logger.info("  unchanged since last crawl (304), nothing to parse")
            return None
        if not result.ok:
            logger.info(
                "  failed to fetch: HTTP %d (blocked, or the page is gone)",
                result.status_code,
            )
            if record_errors:
                stats.errors.append(f"{url} returned {result.status_code}")
            return None
        return result

    def _reached_limit(self, stats: CrawlStats) -> bool:
        return (
            self.max_publications is not None
            and stats.publications_kept >= self.max_publications
        )
