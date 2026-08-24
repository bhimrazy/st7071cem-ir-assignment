"""The portal embeds Highwire Press `citation_*` meta tags, the same metadata
Google Scholar consumes. Those are a documented contract for machines, whereas
CSS class names change whenever the site is restyled. Only the abstract is
taken from the rendered markup, because it has no meta tag."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup, Tag

# The organisation this vertical engine is restricted to, as it appears in
# institution metadata and in a profile URL. Matched as a substring because the
# portal appends an abbreviation: "... Community Transformation (HCT)".
ORGANISATION_NAME = "centre for healthcare and community transformation"
ORGANISATION_SLUG = "/organisations/centre-for-healthcare-and-community-transformation"


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
    def is_affiliated(self) -> bool:
        """Whether any listed author institution is the target organisation."""
        return any(ORGANISATION_NAME in inst.lower() for inst in self.institutions)

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


def _author_key(name_or_slug: str) -> tuple[str, str]:
    """First initial and surname, the part a citation and a profile agree on.

    Citation metadata abbreviates ("L Lees Deutsch") while the profile slug
    spells the given name out ("liz-lees-deutsch"), so the full strings never
    match. The initial and the last word survive both.
    """
    parts = [part for part in slugify(name_or_slug).split("-") if part]
    if not parts:
        return ("", "")
    return (parts[0][:1], parts[-1])


def _attr(tag: Tag, name: str) -> str:
    """One attribute as text.

    BeautifulSoup returns a list for attributes HTML defines as multi-valued,
    such as `class`, so a bare `tag[name]` is not always a string.
    """
    value = tag.get(name)
    if isinstance(value, list):
        return " ".join(value).strip()
    return (value or "").strip()


def _meta_values(soup: BeautifulSoup, name: str) -> list[str]:
    return [
        content
        for tag in soup.find_all("meta", attrs={"name": name})
        if isinstance(tag, Tag) and (content := _attr(tag, "content"))
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
    author_profiles = _pair_authors_to_profiles(authors, extract_person_links(html))

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


def _pair_authors_to_profiles(authors: list[str], profiles: list[str]) -> list[str]:
    """One profile URL per author, or "" where the page links none.

    Exact slug matches are taken first. What is left is matched on initial and
    surname, but only when exactly one profile fits, so two co-authors called
    "J Smith" both stay unpaired rather than one being linked to the other.
    """
    by_slug = {_slug_of(url): url for url in profiles}
    remaining = dict(by_slug)

    paired: list[str | None] = []
    for author in authors:
        url = remaining.pop(slugify(author), None)
        paired.append(url)

    candidates: dict[tuple[str, str], list[str]] = {}
    for slug, url in remaining.items():
        candidates.setdefault(_author_key(slug), []).append(url)

    for index, (author, url) in enumerate(zip(authors, paired, strict=True)):
        if url is not None:
            continue
        fits = candidates.get(_author_key(author), [])
        paired[index] = fits[0] if len(fits) == 1 else ""
    return [url or "" for url in paired]


def _slug_of(profile_url: str) -> str:
    return profile_url.rstrip("/").rsplit("/", 1)[-1]


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
        if isinstance(anchor, Tag)
        and (match := re.search(r"/en/persons/([^/\"?#]+)", _attr(anchor, "href")))
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
        if isinstance(anchor, Tag)
        and (match := re.search(r"/en/publications/([^/\"?#]+)", _attr(anchor, "href")))
    }
    return sorted(
        f"https://pureportal.coventry.ac.uk/en/publications/{slug}/" for slug in slugs
    )


def belongs_to_organisation(html: str, slug: str = ORGANISATION_SLUG) -> bool:
    """Whether a profile page links this organisation.

    Matched on the link rather than the visible name, because the name also
    appears on pages that only mention the centre in passing.
    """
    soup = BeautifulSoup(html, "lxml")
    return any(
        slug in _attr(anchor, "href")
        for anchor in soup.find_all("a", href=True)
        if isinstance(anchor, Tag)
    )
