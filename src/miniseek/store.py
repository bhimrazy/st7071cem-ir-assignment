"""Documents are what gets persisted, because the index is derived data: analysis
is lossy, so documents can regenerate the index but not the other way round."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Document:
    """A stored document.

    Two identities on purpose. `id` is the external one the caller supplies --
    a URL, a DOI, something meaningful. `internal_id` is a compact integer used
    as the key throughout the inverted index, where postings are compared and
    intersected constantly and integers are far cheaper than strings.
    """

    id: str
    internal_id: int
    fields: dict[str, Any] = field(default_factory=dict)


class DocumentStore:
    """In-memory documents plus the external-id to internal-id mapping."""

    __slots__ = ("_by_external", "_by_internal", "_next_id")

    def __init__(self) -> None:
        self._by_internal: dict[int, Document] = {}
        self._by_external: dict[str, int] = {}
        self._next_id = 0

    def put(self, external_id: str, fields: dict[str, Any]) -> Document:
        """Insert or replace a document, returning the stored copy.

        Updating an existing document keeps its internal id. That stability
        matters: it means a re-crawl updates postings in place rather than
        leaving the old integer orphaned across the index.
        """
        internal_id = self._by_external.get(external_id)
        if internal_id is None:
            internal_id = self._next_id
            self._next_id += 1
            self._by_external[external_id] = internal_id

        document = Document(id=external_id, internal_id=internal_id, fields=fields)
        self._by_internal[internal_id] = document
        return document

    def remove(self, external_id: str) -> Document | None:
        internal_id = self._by_external.pop(external_id, None)
        if internal_id is None:
            return None
        return self._by_internal.pop(internal_id)

    def get(self, external_id: str) -> Document | None:
        internal_id = self._by_external.get(external_id)
        return None if internal_id is None else self._by_internal[internal_id]

    def by_internal_id(self, internal_id: int) -> Document | None:
        return self._by_internal.get(internal_id)

    @property
    def next_internal_id(self) -> int:
        """Persisted so ids stay stable across a restart."""
        return self._next_id

    def restore_next_internal_id(self, value: int) -> None:
        self._next_id = max(self._next_id, value)

    def __contains__(self, external_id: object) -> bool:
        return external_id in self._by_external

    def __len__(self) -> int:
        return len(self._by_internal)

    def __iter__(self) -> Iterator[Document]:
        return iter(self._by_internal.values())

    def __repr__(self) -> str:
        return f"<DocumentStore documents={len(self)}>"
