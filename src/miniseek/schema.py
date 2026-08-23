"""A term in the title is a stronger signal than the same term in an abstract, so
fields are kept apart in the index and weighted separately at ranking time."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Field:
    """One field of a document.

    `indexed` and `stored` are independent on purpose, which is a distinction
    worth being deliberate about:

    - indexed, not stored: searchable but never displayed (e.g. a keywords blob)
    - stored, not indexed: displayed but never searched (e.g. a URL)
    - both: the common case (e.g. a title)
    """

    name: str
    indexed: bool = True
    stored: bool = True
    weight: float = 1.0

    def __post_init__(self) -> None:
        if self.weight <= 0:
            raise ValueError(f"field {self.name!r}: weight must be positive")
        if not (self.indexed or self.stored):
            raise ValueError(
                f"field {self.name!r}: a field that is neither indexed nor "
                "stored would be discarded entirely"
            )


@dataclass(frozen=True, slots=True)
class Schema:
    """The set of fields in a collection, plus which one is the primary key."""

    fields: tuple[Field, ...]
    id_field: str = "id"

    def __post_init__(self) -> None:
        names = [f.name for f in self.fields]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ValueError(f"duplicate field names: {sorted(duplicates)}")
        if not self.indexed_fields:
            raise ValueError("schema must have at least one indexed field")

    @property
    def indexed_fields(self) -> tuple[Field, ...]:
        return tuple(f for f in self.fields if f.indexed)

    @property
    def stored_fields(self) -> tuple[Field, ...]:
        return tuple(f for f in self.fields if f.stored)

    def field(self, name: str) -> Field:
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(f"no such field: {name!r}")

    def weights(self) -> dict[str, float]:
        return {f.name: f.weight for f in self.indexed_fields}

    def to_dict(self) -> dict[str, object]:
        return {
            "id_field": self.id_field,
            "fields": [
                {
                    "name": f.name,
                    "indexed": f.indexed,
                    "stored": f.stored,
                    "weight": f.weight,
                }
                for f in self.fields
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Schema:
        return cls(
            fields=tuple(Field(**f) for f in data["fields"]),
            id_field=data.get("id_field", "id"),
        )
