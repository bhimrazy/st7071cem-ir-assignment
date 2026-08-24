"""Crawler tests. Entirely offline -- no test may touch the network."""

from __future__ import annotations

import time

import pytest

from crawler.crawler import PortalCrawler
from crawler.extract import (
    extract_person_links,
    extract_publication,
    extract_publication_links,
    slugify,
)
from crawler.fetcher import FetchResult
from crawler.politeness import RateLimiter
from crawler.scheduler import CrawlState

PUBLICATION_HTML = """
<html><head>
<meta name="citation_title" content="Diabetes prevention in community settings">
<meta name="citation_author" content="Gemma Pearce">
<meta name="citation_author" content="External Collaborator">
<meta name="citation_author_institution"
      content="Centre for Healthcare and Community Transformation (HCT)">
<meta name="citation_author_institution" content="Some Other University">
<meta name="citation_journal_title" content="Health Science Reports">
<meta name="citation_publication_date" content="2024/03">
<meta name="citation_doi" content="10.1000/example">
</head><body>
<a href="/en/persons/gemma-pearce/">Gemma Pearce</a>
<div class="textblock">A study of community-based diabetes prevention.</div>
</body></html>
"""

ORGANISATION_HTML = """
<html><body>
<a href="/en/persons/gemma-pearce/">Gemma Pearce</a>
<a href="/en/persons/sally-abbott/">Sally Abbott</a>
<a href="/en/persons/gemma-pearce/">Gemma Pearce again</a>
</body></html>
"""

# A member profile: it links the organisation, which is what qualifies it.
PERSON_HTML = """
<html><body>
<a href="/en/organisations/centre-for-healthcare-and-community-transformation/">HCT</a>
<a href="/en/publications/diabetes-prevention/">Diabetes prevention</a>
<a href="/en/publications/another-paper/">Another paper</a>
</body></html>
"""

NON_PUBLICATION_HTML = "<html><head><title>Not a publication</title></head></html>"


# ---- extraction --------------------------------------------------------


def test_extracts_citation_metadata():
    pub = extract_publication(PUBLICATION_HTML, "https://example.org/pub/")
    assert pub is not None
    assert pub.title == "Diabetes prevention in community settings"
    assert pub.authors == ["Gemma Pearce", "External Collaborator"]
    assert pub.journal == "Health Science Reports"
    assert pub.year == "2024"
    assert pub.doi == "10.1000/example"
    assert pub.abstract.startswith("A study of community-based")


def test_author_profiles_stay_index_aligned_with_authors():
    """External co-authors have no profile, but must not shift the pairing."""
    pub = extract_publication(PUBLICATION_HTML, "https://example.org/pub/")
    assert pub is not None
    assert len(pub.author_profiles) == len(pub.authors)
    assert pub.author_profiles[0].endswith("/en/persons/gemma-pearce/")
    assert pub.author_profiles[1] == ""


def test_abbreviated_citation_names_still_find_their_profile():
    """Citations abbreviate the given name; profile slugs spell it out."""
    html = PUBLICATION_HTML.replace(
        '<meta name="citation_author" content="Gemma Pearce">',
        '<meta name="citation_author" content="G Pearce">',
    )
    pub = extract_publication(html, "https://example.org/p/")
    assert pub is not None
    assert pub.author_profiles[0].endswith("/en/persons/gemma-pearce/")


def test_ambiguous_names_are_left_unpaired():
    """Two J Smiths and one profile each must not be guessed at."""
    html = PUBLICATION_HTML.replace(
        '<meta name="citation_author" content="Gemma Pearce">',
        '<meta name="citation_author" content="J Smith">',
    ).replace(
        '<a href="/en/persons/gemma-pearce/">Gemma Pearce</a>',
        '<a href="/en/persons/john-smith/">John Smith</a>'
        '<a href="/en/persons/jack-smith/">Jack Smith</a>',
    )
    pub = extract_publication(html, "https://example.org/p/")
    assert pub is not None
    assert pub.author_profiles[0] == ""  # fits john-smith and jack-smith


def test_affiliation_detected_from_institution_metadata():
    pub = extract_publication(PUBLICATION_HTML, "https://example.org/pub/")
    assert pub is not None
    assert pub.is_affiliated is True


def test_unaffiliated_publication_is_flagged():
    html = PUBLICATION_HTML.replace(
        "Centre for Healthcare and Community Transformation (HCT)",
        "Faculty of Engineering",
    )
    pub = extract_publication(html, "https://example.org/p/")
    assert pub is not None
    assert pub.is_affiliated is False


def test_page_without_citation_metadata_is_not_a_publication():
    assert extract_publication(NON_PUBLICATION_HTML, "https://example.org/") is None


def test_missing_optional_fields_do_not_crash():
    minimal = '<html><head><meta name="citation_title" content="Bare"></head></html>'
    pub = extract_publication(minimal, "https://example.org/p/")
    assert pub is not None
    assert pub.title == "Bare"
    assert pub.authors == []
    assert pub.year == ""
    assert pub.abstract == ""
    assert pub.is_affiliated is False


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Celine Brookes-Smith", "celine-brookes-smith"),
        ("Gemma Pearce", "gemma-pearce"),
        ("Lorna O'Doherty", "lorna-o-doherty"),
        ("José García", "jose-garcia"),
    ],
)
def test_slugify_matches_portal_url_style(name, expected):
    assert slugify(name) == expected


def test_link_extraction_deduplicates():
    people = extract_person_links(ORGANISATION_HTML)
    assert len(people) == 2
    assert all(
        u.startswith("https://pureportal.coventry.ac.uk/en/persons/") for u in people
    )

    pubs = extract_publication_links(PERSON_HTML)
    assert len(pubs) == 2


# ---- politeness --------------------------------------------------------


def test_rate_limiter_enforces_minimum_interval():
    limiter = RateLimiter(0.15)
    limiter.wait()
    started = time.monotonic()
    limiter.wait()
    assert time.monotonic() - started >= 0.15


def test_rate_limiter_does_not_delay_the_first_request():
    started = time.monotonic()
    RateLimiter(5.0).wait()
    assert time.monotonic() - started < 0.5


# ---- orchestration -----------------------------------------------------


class FakeFetcher:
    """Stands in for PoliteFetcher so the crawl logic can be tested offline."""

    def __init__(self, pages: dict[str, str], unchanged: set[str] | None = None):
        self.pages = pages
        self.unchanged = unchanged or set()
        self.requests_made = 0
        self.requested: list[str] = []

    def fetch(self, url: str, *, conditional: bool = True) -> FetchResult:
        self.requests_made += 1
        self.requested.append(url)
        if url in self.unchanged:
            return FetchResult(url=url, status_code=304, text="")
        if url not in self.pages:
            return FetchResult(url=url, status_code=404, text="")
        return FetchResult(url=url, status_code=200, text=self.pages[url])

    def stats(self) -> dict:
        return {"requests_made": self.requests_made}


ORG_URL = "https://pureportal.coventry.ac.uk/en/organisations/chct/"
PERSON_URL = "https://pureportal.coventry.ac.uk/en/persons/gemma-pearce/"
PUB_URL = "https://pureportal.coventry.ac.uk/en/publications/diabetes-prevention/"
PUB2_URL = "https://pureportal.coventry.ac.uk/en/publications/another-paper/"


@pytest.fixture
def pages() -> dict[str, str]:
    return {
        ORG_URL: '<a href="/en/persons/gemma-pearce/">P</a>',
        PERSON_URL: PERSON_HTML,
        PUB_URL: PUBLICATION_HTML,
        PUB2_URL: PUBLICATION_HTML.replace(
            "Diabetes prevention in community settings", "Another paper"
        ),
    }


def _urls(result) -> set[str]:
    return {publication.url for publication in result.publications}


def test_crawl_walks_org_then_people_then_publications(pages):
    fetcher = FakeFetcher(pages)
    result = PortalCrawler(fetcher=fetcher, organisation_url=ORG_URL).crawl()

    assert result.stats.members_found == 1
    assert result.stats.publication_urls_seen == 2
    assert result.stats.publications_kept == 2
    assert PUB_URL in _urls(result)
    kept = next(p for p in result.publications if p.url == PUB_URL)
    assert kept.journal == "Health Science Reports"


def test_recrawl_finds_the_same_publications(pages):
    urls = None
    for _ in range(3):
        result = PortalCrawler(
            fetcher=FakeFetcher(pages), organisation_url=ORG_URL
        ).crawl()
        urls = _urls(result)
    assert urls == {PUB_URL, PUB2_URL}


def test_unchanged_pages_are_skipped(pages):
    """A 304 means our copy is current, so there is nothing to parse."""
    fetcher = FakeFetcher(pages, unchanged={PUB_URL})
    result = PortalCrawler(fetcher=fetcher, organisation_url=ORG_URL).crawl()
    assert result.stats.publications_kept == 1  # only the changed one


def test_require_affiliation_filters_on_institution_metadata(pages):
    pages[PUB2_URL] = PUBLICATION_HTML.replace(
        "Centre for Healthcare and Community Transformation (HCT)",
        "Faculty of Engineering",
    ).replace("Diabetes prevention in community settings", "Engineering paper")

    result = PortalCrawler(
        fetcher=FakeFetcher(pages),
        organisation_url=ORG_URL,
        require_affiliation=True,
    ).crawl()
    assert result.stats.publications_kept == 1
    assert result.stats.affiliation_verified == 1


def test_verification_is_counted_without_being_required(pages):
    pages[PUB2_URL] = PUBLICATION_HTML.replace(
        "Centre for Healthcare and Community Transformation (HCT)",
        "Faculty of Engineering",
    ).replace("Diabetes prevention in community settings", "Engineering paper")

    result = PortalCrawler(fetcher=FakeFetcher(pages), organisation_url=ORG_URL).crawl()
    assert result.stats.publications_kept == 2  # member-sourced, so kept
    assert (
        result.stats.affiliation_verified == 1
    )  # but only one independently confirmed


def test_unreachable_pages_are_recorded_not_fatal():
    fetcher = FakeFetcher({ORG_URL: '<a href="/en/persons/ghost/">G</a>'})
    result = PortalCrawler(fetcher=fetcher, organisation_url=ORG_URL).crawl()
    assert result.stats.members_seeded == 1
    assert result.stats.members_found == 0  # the profile could not be read
    assert result.stats.errors  # the 404 was recorded
    assert result.stats.publications_kept == 0


def test_max_publications_limits_the_crawl(pages):
    result = PortalCrawler(
        fetcher=FakeFetcher(pages),
        organisation_url=ORG_URL,
        max_publications=1,
    ).crawl()
    assert result.stats.publications_kept == 1


# ---- scheduling --------------------------------------------------------


def test_state_reports_due_when_never_run(tmp_path):
    assert CrawlState(tmp_path).is_due() is True
    assert CrawlState(tmp_path).last_run() is None


def test_state_is_not_due_immediately_after_a_run(tmp_path):
    """Restarting the process must not trigger an immediate re-crawl."""
    state = CrawlState(tmp_path)
    state.write({"publications_indexed": 5})
    assert state.is_due() is False
    assert state.seconds_until_due() > 0
    assert state.read()["last_stats"]["publications_indexed"] == 5


def test_state_survives_a_corrupt_file(tmp_path):
    state = CrawlState(tmp_path)
    state.path.write_text("not json")
    assert state.read() == {}
    assert state.is_due() is True


# ---- co-author expansion ------------------------------------------------

COAUTHOR_SLUG = "/en/persons/sally-abbott/"
COAUTHOR_URL = f"https://pureportal.coventry.ac.uk{COAUTHOR_SLUG}"
OUTSIDER_URL = "https://pureportal.coventry.ac.uk/en/persons/other-centre/"
PUB3_URL = "https://pureportal.coventry.ac.uk/en/publications/third-paper/"

MEMBER_PROFILE_HTML = """
<html><body>
<a href="/en/organisations/centre-for-healthcare-and-community-transformation/">HCT</a>
<a href="/en/publications/third-paper/">Third paper</a>
</body></html>
"""

OUTSIDER_PROFILE_HTML = """
<html><body>
<a href="/en/organisations/centre-for-arts-memory-and-communities/">Other centre</a>
<a href="/en/publications/unrelated-paper/">Unrelated</a>
</body></html>
"""


@pytest.fixture
def expansion_pages() -> dict[str, str]:
    """A publication naming two Coventry co-authors the org page never linked."""
    linked = PUBLICATION_HTML.replace(
        '<a href="/en/persons/gemma-pearce/">Gemma Pearce</a>',
        '<a href="/en/persons/gemma-pearce/">Gemma Pearce</a>'
        f'<a href="{COAUTHOR_SLUG}">Sally Abbott</a>'
        '<a href="/en/persons/other-centre/">Other Centre</a>',
    ).replace(
        '<meta name="citation_author" content="External Collaborator">',
        '<meta name="citation_author" content="Sally Abbott">'
        '<meta name="citation_author" content="Other Centre">',
    )
    return {
        ORG_URL: '<a href="/en/persons/gemma-pearce/">P</a>',
        PERSON_URL: PERSON_HTML,
        PUB_URL: linked,
        PUB2_URL: linked.replace(
            "Diabetes prevention in community settings", "Another paper"
        ),
        COAUTHOR_URL: MEMBER_PROFILE_HTML,
        OUTSIDER_URL: OUTSIDER_PROFILE_HTML,
        PUB3_URL: PUBLICATION_HTML.replace(
            "Diabetes prevention in community settings", "Third paper"
        ),
    }


def test_coauthors_extend_the_frontier(expansion_pages):
    result = PortalCrawler(
        fetcher=FakeFetcher(expansion_pages), organisation_url=ORG_URL
    ).crawl()

    assert result.stats.members_seeded == 1
    assert (
        result.stats.members_found == 2
    )  # Gemma plus Sally, not the other-centre author
    assert result.stats.profiles_rejected == 1
    assert PUB3_URL in _urls(result)  # reached only through Sally


def test_a_url_is_never_fetched_twice(expansion_pages):
    """Two members sharing a publication must not re-fetch it."""
    fetcher = FakeFetcher(expansion_pages)
    PortalCrawler(fetcher=fetcher, organisation_url=ORG_URL).crawl()

    assert len(fetcher.requested) == len(set(fetcher.requested))


# ---- the listing route -------------------------------------------------


def test_listings_are_used_when_the_portal_serves_them():
    """A portal without a bot check is paged through, not just sampled."""
    listing = ORG_URL.rstrip("/")
    pages = {
        ORG_URL: '<a href="/en/persons/gemma-pearce/">P</a>',
        f"{listing}/publications/?page=0": (
            '<a href="/en/publications/diabetes-prevention/">1</a>'
        ),
        f"{listing}/publications/?page=1": (
            '<a href="/en/publications/another-paper/">2</a>'
        ),
        f"{listing}/persons/?page=0": '<a href="/en/persons/gemma-pearce/">P</a>',
        PERSON_URL: PERSON_HTML,
        PUB_URL: PUBLICATION_HTML,
        PUB2_URL: PUBLICATION_HTML.replace(
            "Diabetes prevention in community settings", "Another paper"
        ),
    }
    fetcher = FakeFetcher(pages)
    result = PortalCrawler(fetcher=fetcher, organisation_url=ORG_URL).crawl()

    # Page 2 is requested and comes back empty, which is how paging stops.
    assert f"{listing}/publications/?page=2" in fetcher.requested
    assert result.stats.publications_kept == 2
    assert not result.stats.errors  # a missing listing page is not an error


def test_falls_back_when_listings_are_blocked(pages):
    """This portal's listings are 403, so the organisation page is the seed."""
    fetcher = FakeFetcher(pages)
    result = PortalCrawler(fetcher=fetcher, organisation_url=ORG_URL).crawl()

    assert any("/publications/?page=0" in url for url in fetcher.requested)
    assert result.stats.members_seeded == 1  # read off the organisation page
    assert not result.stats.errors
