"""Parsing a pureportal page into a structured publication record.

The portal embeds Highwire Press ``citation_*`` meta tags -- the same
machine-readable metadata Google Scholar itself consumes. Preferring those
over scraping the rendered markup is the single most important decision in
this module: meta tags are a documented contract intended for machines, while
CSS class names are an implementation detail that changes whenever the site is
restyled.

The rendered HTML is used only for the abstract, which has no meta tag.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup

# The department this vertical search engine is restricted to. Matched
# case-insensitively as a substring because the portal writes it with a
# trailing abbreviation: "Centre for Healthcare and Community Transformation (HCT)".
CHCT_NAME = "centre for healthcare and community transformation"


@dataclass(slots=True)
class Publication:
    """One publication, as stored in the search index."""

    id: str
    title: str
    url: str
    authors: list[str] = field(default_factory=list)
    author_profiles: list[str] = field(default_factory=list)
    institutions: list[str] = field(default_factory=list)
    abstract: str = ""
    journal: str = ""
    year: str = ""
    doi: str = ""
    keywords: str = ""
    crawled_at: str = ""

    @property
    def is_chct(self) -> bool:
        """Whether any listed author institution is the target department.

        This is what makes the engine *vertical*: the brief requires that at
        least one co-author belongs to CHCT.
        """
        return any(CHCT_NAME in inst.lower() for inst in self.institutions)

    def to_document(self) -> dict[str, Any]:
        """Shape expected by PUBLICATION_SCHEMA."""
        return {
            "id": self.id,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "journal": self.journal,
            "year": self.year,
            "url": self.url,
            "doi": self.doi,
            "author_profiles": self.author_profiles,
            "crawled_at": self.crawled_at,
        }


def slugify(name: str) -> str:
    """Convert a display name to the portal's profile-URL slug.

    "Celine Brookes-Smith" -> "celine-brookes-smith". Accents are folded
    because the portal's slugs are ASCII while the displayed names are not.
    """
    folded = unicodedata.normalize("NFKD", name)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower().strip()
    return re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")


def _meta_values(soup: BeautifulSoup, name: str) -> list[str]:
    return [
        tag["content"].strip()
        for tag in soup.find_all("meta", attrs={"name": name})
        if tag.get("content")
    ]


def _meta_value(soup: BeautifulSoup, name: str) -> str:
    values = _meta_values(soup, name)
    return values[0] if values else ""


def extract_publication(html: str, url: str) -> Publication | None:
    """Parse a publication page. Returns None if it is not one.

    Returning None rather than raising is deliberate: a crawl walks links of
    uncertain type, and hitting a non-publication page is an ordinary event,
    not an error.
    """
    soup = BeautifulSoup(html, "lxml")

    title = _meta_value(soup, "citation_title")
    if not title:
        return None  # no citation metadata => not a publication page

    authors = _meta_values(soup, "citation_author")
    institutions = _meta_values(soup, "citation_author_institution")

    # Pair author names with their profile pages. Only internal staff have
    # profiles, so external co-authors correctly get an empty string rather
    # than a wrong link -- the lists stay index-aligned for the UI.
    profile_links = {
        slugify(match.group(1)): f"https://pureportal.coventry.ac.uk/en/persons/{match.group(1)}/"
        for anchor in soup.find_all("a", href=True)
        if (match := re.search(r"/en/persons/([^/\"?#]+)", anchor["href"]))
    }
    author_profiles = [profile_links.get(slugify(author), "") for author in authors]

    # Publication date is "YYYY/MM" or "YYYY"; we only index the year.
    raw_date = _meta_value(soup, "citation_publication_date")
    year = raw_date[:4] if raw_date[:4].isdigit() else ""

    return Publication(
        id=url,
        title=title,
        url=url,
        authors=authors,
        author_profiles=author_profiles,
        institutions=institutions,
        abstract=_extract_abstract(soup),
        journal=_meta_value(soup, "citation_journal_title"),
        year=year,
        doi=_meta_value(soup, "citation_doi"),
        keywords=_meta_value(soup, "citation_keywords"),
        crawled_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


def _extract_abstract(soup: BeautifulSoup) -> str:
    """Pull the abstract from the rendered page.

    No meta tag carries it, so this is the one place we depend on markup.
    Several selectors are tried in order because Pure renders different
    publication types (article, chapter, conference paper) slightly
    differently, and an abstract is valuable enough to be worth the fallbacks.
    """
    for selector in (
        "div.textblock",
        "div.rendering_abstractportal",
        "div.abstract",
    ):
        node = soup.select_one(selector)
        if node and (text := node.get_text(" ", strip=True)):
            return text
    return ""


def extract_person_links(html: str) -> list[str]:
    """Absolute profile URLs linked from a page (e.g. an organisation page)."""
    soup = BeautifulSoup(html, "lxml")
    slugs = {
        match.group(1)
        for anchor in soup.find_all("a", href=True)
        if (match := re.search(r"/en/persons/([^/\"?#]+)", anchor["href"]))
    }
    return sorted(
        f"https://pureportal.coventry.ac.uk/en/persons/{slug}/" for slug in slugs
    )


def extract_publication_links(html: str) -> list[str]:
    """Absolute publication URLs linked from a page."""
    soup = BeautifulSoup(html, "lxml")
    slugs = {
        match.group(1)
        for anchor in soup.find_all("a", href=True)
        if (match := re.search(r"/en/publications/([^/\"?#]+)", anchor["href"]))
    }
    return sorted(
        f"https://pureportal.coventry.ac.uk/en/publications/{slug}/" for slug in slugs
    )
