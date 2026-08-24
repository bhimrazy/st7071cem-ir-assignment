from __future__ import annotations

import os
from pathlib import Path

from miniseek.collection import Collection
from miniseek.schema import Field, Schema

from .paths import INDEX_DIR

# Field weights encode editorial judgement about evidence strength:
# a query term in the title says far more about relevance than the same term
# in an abstract, and an author-name match is a strong signal for the
# "find this researcher's work" queries a vertical engine gets constantly.
PUBLICATION_SCHEMA = Schema(
    fields=(
        Field("id", indexed=False, stored=True),
        Field("title", indexed=True, stored=True, weight=3.0),
        # Each entry is {"name": ..., "profile_url": ...}. Only the name is
        # indexed, the profile URL is display-only.
        Field("authors", indexed=True, stored=True, weight=2.0),
        Field("abstract", indexed=True, stored=True, weight=1.0),
        Field("journal", indexed=True, stored=True, weight=1.0),
        # Year is stored for display and sorting but not indexed: "2024" as a
        # search term matches every paper from that year, which is a filter,
        # not a relevance signal.
        Field("year", indexed=False, stored=True),
        Field("url", indexed=False, stored=True),
        Field("doi", indexed=False, stored=True),
        Field("crawled_at", indexed=False, stored=True),
    ),
    id_field="id",
)


def open_publications(path: str | os.PathLike[str] | None = None) -> Collection:
    """Open (or create) the searchable index built from a crawl."""
    return Collection.open(
        Path(path) if path is not None else INDEX_DIR,
        schema=PUBLICATION_SCHEMA,
        name="publications",
    )
