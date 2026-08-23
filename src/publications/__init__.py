"""The publication collection: schema and how to open it.

Shared by the crawler (which writes), the API (which reads) and the scheduler,
so all three agree on field names and weights.
"""

from __future__ import annotations

import os
from pathlib import Path

from miniseek.collection import Collection
from miniseek.schema import Field, Schema

# Where the crawled corpus lives. Overridable so tests and the scheduler can
# point at a scratch directory instead of the real one.
DEFAULT_DATA_DIR = Path(
    os.environ.get(
        "IR_DATA_DIR",
        Path(__file__).resolve().parents[2] / "data" / "publications",
    )
)

# Field weights encode editorial judgement about evidence strength:
# a query term in the title says far more about relevance than the same term
# in an abstract, and an author-name match is a strong signal for the
# "find this researcher's work" queries a vertical engine gets constantly.
PUBLICATION_SCHEMA = Schema(
    fields=(
        Field("id", indexed=False, stored=True),
        Field("title", indexed=True, stored=True, weight=3.0),
        Field("authors", indexed=True, stored=True, weight=2.0),
        Field("abstract", indexed=True, stored=True, weight=1.0),
        Field("journal", indexed=True, stored=True, weight=1.0),
        # Year is stored for display and sorting but not indexed: "2024" as a
        # search term matches every paper from that year, which is a filter,
        # not a relevance signal.
        Field("year", indexed=False, stored=True),
        Field("url", indexed=False, stored=True),
        Field("doi", indexed=False, stored=True),
        # Author profile links, required by the brief. Not indexed for the
        # same reason as url: every value contains "pureportal.coventry.ac.uk".
        Field("author_profiles", indexed=False, stored=True),
        Field("crawled_at", indexed=False, stored=True),
    ),
    id_field="id",
)


def open_publications(path: str | os.PathLike[str] | None = None) -> Collection:
    """Open (or create) the publication collection."""
    return Collection.open(
        Path(path) if path is not None else DEFAULT_DATA_DIR,
        schema=PUBLICATION_SCHEMA,
        name="publications",
    )
