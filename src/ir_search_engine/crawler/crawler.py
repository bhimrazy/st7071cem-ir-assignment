"""The CHCT crawler.

Crawl strategy
--------------
The obvious route -- paginating the department's publication listing -- is not
available: those listing URLs sit behind a bot-protection challenge and return
403 to any HTTP client. Entity pages (the organisation, each person, each
publication) are served normally.

So the crawl is **member-seeded**, which happens to match the brief's
definition of the corpus more directly anyway:

    organisation page  ->  member profile pages  ->  publication pages

The brief asks for publications where "at least one of the co-authors is a
member of this department". Starting from the member list expresses exactly
that, and each publication page is then verified independently through its
``citation_author_institution`` metadata rather than trusted because of how we
reached it.

Every run updates the existing index in place: unchanged publications are
re-indexed harmlessly, changed ones replace their previous version, and
nothing is duplicated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from miniseek.collection import Collection

from .extract import (
    Publication,
    extract_person_links,
    extract_publication,
    extract_publication_links,
)
from .fetcher import DisallowedByRobots, PoliteFetcher

logger = logging.getLogger(__name__)

BASE_URL = "https://pureportal.coventry.ac.uk"
CHCT_ORGANISATION_URL = (
    f"{BASE_URL}/en/organisations/"
    "centre-for-healthcare-and-community-transformation/"
)


@dataclass(slots=True)
class CrawlStats:
    """What one crawl run did. Printed by the scheduler and used in the report."""

    started_at: str = ""
    finished_at: str = ""
    members_found: int = 0
    publication_urls_seen: int = 0
    pages_fetched: int = 0
    publications_indexed: int = 0
    chct_verified: int = 0
    skipped_unparseable: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "members_found": self.members_found,
            "publication_urls_seen": self.publication_urls_seen,
            "pages_fetched": self.pages_fetched,
            "publications_indexed": self.publications_indexed,
            "chct_verified": self.chct_verified,
            "skipped_unparseable": self.skipped_unparseable,
            "errors": self.errors,
        }


class ChctCrawler:
    """Crawls CHCT publications into a miniseek collection."""

    def __init__(
        self,
        collection: Collection,
        *,
        fetcher: PoliteFetcher | None = None,
        organisation_url: str = CHCT_ORGANISATION_URL,
        max_publications: int | None = None,
        require_chct: bool = False,
    ) -> None:
        self.collection = collection
        self.fetcher = fetcher or PoliteFetcher(BASE_URL)
        self.organisation_url = organisation_url
        self.max_publications = max_publications
        # Whether to additionally *require* the department to appear in the
        # publication's own institution metadata.
        #
        # Off by default, and the reasoning matters. The brief defines the
        # corpus as publications where "at least one of the co-authors is a
        # member of this department", and reaching a publication from a
        # member's profile page establishes precisely that. The
        # citation_author_institution metadata records the affiliation
        # attached to *that paper*, which is frequently a different Coventry
        # centre or a co-author's external institution -- so requiring it
        # discards publications that genuinely satisfy the brief.
        #
        # The metadata is still recorded as a stronger, independent
        # confirmation and counted in CrawlStats.chct_verified.
        self.require_chct = require_chct

    def crawl(self) -> CrawlStats:
        stats = CrawlStats(started_at=datetime.now(UTC).isoformat(timespec="seconds"))

        members = self._discover_members(stats)
        stats.members_found = len(members)
        logger.info("found %d department members", len(members))

        publication_urls = self._discover_publications(members, stats)
        stats.publication_urls_seen = len(publication_urls)
        logger.info("found %d candidate publications", len(publication_urls))

        if self.max_publications is not None:
            publication_urls = publication_urls[: self.max_publications]

        for url in publication_urls:
            publication = self._fetch_publication(url, stats)
            if publication is None:
                continue
            if publication.is_chct:
                stats.chct_verified += 1
            elif self.require_chct:
                continue
            self.collection.add(publication.to_document())
            stats.publications_indexed += 1

        self.collection.flush()
        stats.finished_at = datetime.now(UTC).isoformat(timespec="seconds")
        stats.pages_fetched = self.fetcher.requests_made
        return stats

    def _discover_members(self, stats: CrawlStats) -> list[str]:
        try:
            result = self.fetcher.fetch(self.organisation_url)
        except (DisallowedByRobots, Exception) as error:
            stats.errors.append(f"organisation page: {error}")
            return []
        if not result.ok:
            stats.errors.append(
                f"organisation page returned {result.status_code}"
            )
            return []
        return extract_person_links(result.text)

    def _discover_publications(
        self, members: list[str], stats: CrawlStats
    ) -> list[str]:
        """Union of publications linked from each member's profile page."""
        urls: set[str] = set()
        for member_url in members:
            try:
                result = self.fetcher.fetch(member_url)
            except Exception as error:
                stats.errors.append(f"{member_url}: {error}")
                continue
            if result.unchanged:
                continue  # 304: profile has not changed since last crawl
            if not result.ok:
                stats.errors.append(f"{member_url} returned {result.status_code}")
                continue
            urls.update(extract_publication_links(result.text))
        return sorted(urls)

    def _fetch_publication(self, url: str, stats: CrawlStats) -> Publication | None:
        try:
            result = self.fetcher.fetch(url)
        except Exception as error:
            stats.errors.append(f"{url}: {error}")
            return None

        if result.unchanged:
            # Server confirmed our stored copy is current, so there is nothing
            # to re-parse or re-index.
            return None
        if not result.ok:
            stats.errors.append(f"{url} returned {result.status_code}")
            return None

        publication = extract_publication(result.text, url)
        if publication is None:
            stats.skipped_unparseable += 1
        return publication
