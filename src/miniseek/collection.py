"""Schema, analyzer, document store and inverted index, persisted together.

Documents are the source of truth and the index is rebuilt from them on load,
so the two cannot drift apart. Documents live in an append-only log: a write
appends one line rather than rewriting a whole file, and `compact()` later
rewrites the log keeping only the live version of each document. A background
thread fsyncs on an interval, trading a small window of recent writes against
paying for durability on every append.

On disk:

    collection_dir/
      meta.json        schema, analyzer config, next internal id
      documents.log    one JSON operation per line
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from .analyzer import Analyzer
from .index import InvertedIndex
from .ranking import DEFAULT_SCORER, SCORERS, Scorer
from .schema import Schema
from .store import Document, DocumentStore


@dataclass(slots=True)
class SearchHit:
    """One ranked result: which document, how relevant, and what to display."""

    id: str
    score: float
    fields: dict[str, Any] = dataclass_field(default_factory=dict)


@dataclass(slots=True)
class SearchResults:
    """A page of hits plus the totals a UI needs to paginate.

    `total` is every matching document, not just the ones in this page, so the
    interface can say "showing 10 of 47".
    """

    hits: list[SearchHit]
    total: int
    query: str
    scorer: str

    def __len__(self) -> int:
        return len(self.hits)

    def __iter__(self) -> Iterator[SearchHit]:
        return iter(self.hits)


FORMAT_VERSION = 1
META_FILE = "meta.json"
LOG_FILE = "documents.log"

DEFAULT_SYNC_INTERVAL = 1.0
DEFAULT_COMPACT_RATIO = 2.0
DEFAULT_COMPACT_MIN_ENTRIES = 64


def _field_text(value: Any) -> str:
    """One field value as text. A dict indexes by its "name"/"text" key,
    not its str() repr."""
    if isinstance(value, dict):
        return str(value.get("name") or value.get("text") or "")
    return str(value)


class Collection:
    """A searchable set of documents sharing one schema.

    Safe to use from multiple threads: every mutation and every log operation
    is serialised through one lock, which the background syncer also respects.
    """

    __slots__ = (
        "_lock",
        "_log",
        "_log_entries",
        "_path",
        "_read_only",
        "_stop",
        "_syncer",
        "analyzer",
        "compact_min_entries",
        "compact_ratio",
        "index",
        "name",
        "schema",
        "store",
        "sync_interval",
    )

    def __init__(
        self,
        name: str,
        schema: Schema,
        analyzer: Analyzer | None = None,
        path: str | os.PathLike[str] | None = None,
        *,
        sync_interval: float | None = None,
        compact_ratio: float | None = DEFAULT_COMPACT_RATIO,
        compact_min_entries: int = DEFAULT_COMPACT_MIN_ENTRIES,
        read_only: bool = False,
    ) -> None:
        self.name = name
        self.schema = schema
        self.analyzer = analyzer or Analyzer()
        self.index = InvertedIndex()
        self.store = DocumentStore()
        self.sync_interval = sync_interval
        self.compact_ratio = compact_ratio
        self.compact_min_entries = compact_min_entries
        self._path = Path(path) if path is not None else None
        self._read_only = read_only
        self._log = None
        self._log_entries = 0
        self._lock = threading.RLock()
        self._syncer: threading.Thread | None = None
        self._stop = threading.Event()

    # ---- writing -------------------------------------------------------

    def add(self, document: Mapping[str, Any]) -> Document:
        """Index a document. Must carry the schema's id field.

        Adding an id that already exists updates it in place.
        """
        raw_id = document.get(self.schema.id_field)
        if raw_id is None:
            raise ValueError(
                f"document is missing its id field {self.schema.id_field!r}"
            )
        external_id = str(raw_id)
        fields = dict(document)

        with self._lock:
            stored = self.store.put(external_id, fields)
            self.index.add(stored.internal_id, self._analyze(fields))
            self._append({"op": "put", "id": external_id, "doc": fields})
        return stored

    def add_many(self, documents: Iterable[Mapping[str, Any]]) -> int:
        return sum(1 for doc in documents if self.add(doc))

    def delete(self, external_id: str) -> bool:
        with self._lock:
            removed = self.store.remove(external_id)
            if removed is None:
                return False
            self.index.remove(removed.internal_id)
            self._append({"op": "delete", "id": external_id})
            return True

    def _analyze(self, fields: Mapping[str, Any]) -> dict[str, list[str]]:
        """Run the analyzer over indexed fields only.

        Values are coerced to text so a list of authors or a numeric year is
        indexed sensibly rather than crashing.
        """
        analyzed: dict[str, list[str]] = {}
        for field in self.schema.indexed_fields:
            value = fields.get(field.name)
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                text = " ".join(_field_text(v) for v in value)
            else:
                text = _field_text(value)
            analyzed[field.name] = self.analyzer.analyze(text)
        return analyzed

    # ---- reading -------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        offset: int = 0,
        scorer: Scorer | str | None = None,
    ) -> SearchResults:
        """Rank documents against a free-text query.

        The query goes through the *same* analyzer as the documents did, which
        is what lets "Retrieving" match an indexed "retrieval".
        """
        if isinstance(scorer, str):
            try:
                chosen = SCORERS[scorer]
            except KeyError:
                raise ValueError(
                    f"unknown scorer {scorer!r}; available: {sorted(SCORERS)}"
                ) from None
        else:
            chosen = scorer or DEFAULT_SCORER

        terms = Counter(self.analyzer.analyze(query))
        if not terms:
            # Either an empty query or one made entirely of stopwords. There
            # is nothing to look up, and returning everything would be worse
            # than returning nothing.
            return SearchResults(hits=[], total=0, query=query, scorer=chosen.name)

        with self._lock:
            scores = chosen.score(self.index, terms, self.schema.weights())
            ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
            window = ranked[offset : offset + limit]
            hits = [
                SearchHit(
                    id=document.id,
                    score=score,
                    fields=self.stored_fields(document),
                )
                for doc_id, score in window
                if (document := self.store.by_internal_id(doc_id)) is not None
            ]

        return SearchResults(
            hits=hits, total=len(ranked), query=query, scorer=chosen.name
        )

    def get(self, external_id: str) -> Document | None:
        return self.store.get(external_id)

    def document_for(self, internal_id: int) -> Document | None:
        return self.store.by_internal_id(internal_id)

    def stored_fields(self, document: Document) -> dict[str, Any]:
        """The subset of a document that search results should return."""
        names = {f.name for f in self.schema.stored_fields}
        return {k: v for k, v in document.fields.items() if k in names}

    def __len__(self) -> int:
        return len(self.store)

    def __iter__(self) -> Iterator[Document]:
        return iter(self.store)

    def __repr__(self) -> str:
        return (
            f"<Collection {self.name!r} documents={len(self)} "
            f"terms={self.index.vocabulary_size}>"
        )

    # ---- persistence ---------------------------------------------------

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def log_entries(self) -> int:
        """Entries currently in the log, live and superseded together."""
        return self._log_entries

    @property
    def dead_entries(self) -> int:
        """Superseded entries that compaction would reclaim."""
        return max(self._log_entries - len(self.store), 0)

    def _append(self, operation: dict[str, Any]) -> None:
        # A read-only collection has no log handle, so without this the write
        # would be dropped on the floor and reported as success -- the caller
        # would be told the document was indexed and find it gone on reopen.
        if self._read_only:
            raise RuntimeError(
                f"collection {self.name!r} is open read-only; reopen it "
                "without read_only=True to modify it"
            )
        if self._log is None:
            return
        self._log.write(json.dumps(operation, ensure_ascii=False) + "\n")
        self._log_entries += 1

    def flush(self) -> None:
        """Push buffered writes to the OS and on to disk.

        Without the fsync the data sits in the OS page cache, so a power loss
        could lose writes the caller was told had been indexed.
        """
        with self._lock:
            if self._log is None:
                return
            self._log.flush()
            os.fsync(self._log.fileno())

    def should_compact(self) -> bool:
        """True once dead entries outweigh live ones enough to be worth it.

        The minimum-entries floor stops a tiny collection from compacting
        constantly: with 2 documents and 5 log entries the ratio looks awful
        but the work saved is nil.
        """
        if self._path is None or self.compact_ratio is None:
            return False
        if self._log_entries < self.compact_min_entries:
            return False
        live = max(len(self.store), 1)
        return self._log_entries / live >= self.compact_ratio

    def sync(self) -> None:
        """Make durable, and compact if the log has grown wasteful."""
        with self._lock:
            self.flush()
            if self.should_compact():
                self.compact()

    @classmethod
    def open(
        cls,
        path: str | os.PathLike[str],
        *,
        schema: Schema | None = None,
        analyzer: Analyzer | None = None,
        name: str | None = None,
        sync_interval: float | None = DEFAULT_SYNC_INTERVAL,
        compact_ratio: float | None = DEFAULT_COMPACT_RATIO,
        compact_min_entries: int = DEFAULT_COMPACT_MIN_ENTRIES,
        read_only: bool = False,
    ) -> Self:
        """Open an existing collection, or create one if the directory is new.

        Reopening ignores the `schema` and `analyzer` arguments in favour of
        what was persisted. Silently re-analyzing an existing corpus with
        different settings would leave queries unable to match anything already
        indexed, with no error to explain why.

        Pass `sync_interval=None` to disable the background syncer and take
        responsibility for calling `flush()` yourself.

        Pass `read_only=True` to open without touching the directory at all.
        Ordinary opening is not as passive as it looks: it holds the log open
        for appending, and `close()` rewrites `meta.json` on the way out even
        if nothing was ever added. That is harmless for a writer and wrong for
        a reader, which should be able to inspect a collection another process
        owns without leaving a fingerprint on it.
        """
        directory = Path(path)
        meta_path = directory / META_FILE
        options = {
            "sync_interval": None if read_only else sync_interval,
            "compact_ratio": compact_ratio,
            "compact_min_entries": compact_min_entries,
            "read_only": read_only,
        }

        if meta_path.exists():
            collection = cls._load(directory, options)
        else:
            if read_only:
                raise FileNotFoundError(f"no collection at {directory} to read")
            if schema is None:
                raise ValueError(
                    f"no collection at {directory} -- pass schema= to create one"
                )
            directory.mkdir(parents=True, exist_ok=True)
            collection = cls(
                name=name or directory.name,
                schema=schema,
                analyzer=analyzer,
                path=directory,
                **options,
            )
            collection._write_meta()

        # Leaving the log unopened is what makes read-only stick: flush() and
        # close() both no-op on a null handle, so nothing is written even by
        # the shutdown path.
        if not read_only:
            collection._log = open(directory / LOG_FILE, "a", encoding="utf-8")
        collection._start_syncer()
        return collection

    @classmethod
    def _load(cls, directory: Path, options: dict[str, Any]) -> Self:
        meta = json.loads((directory / META_FILE).read_text(encoding="utf-8"))
        version = meta.get("version")
        if version != FORMAT_VERSION:
            raise ValueError(
                f"collection at {directory} uses format version {version}, "
                f"this build reads version {FORMAT_VERSION}"
            )

        collection = cls(
            name=meta["name"],
            schema=Schema.from_dict(meta["schema"]),
            analyzer=Analyzer.from_config(meta["analyzer"]),
            path=directory,
            **options,
        )
        collection._replay(directory / LOG_FILE)
        # Only advance past ids actually seen, so a truncated log cannot
        # cause a fresh document to reuse a live internal id.
        collection.store.restore_next_internal_id(meta.get("next_internal_id", 0))
        return collection

    def _replay(self, log_path: Path) -> None:
        """Rebuild store and index by replaying the log, last write winning."""
        if not log_path.exists():
            return
        entries = 0
        with open(log_path, encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    operation = json.loads(line)
                except json.JSONDecodeError as error:
                    # A partial final line means the process died mid-append.
                    # Everything before it is intact, so keep it and stop.
                    raise ValueError(
                        f"{log_path}: corrupt entry on line {line_number}; "
                        "run compaction on the last good prefix to recover"
                    ) from error

                entries += 1
                if operation["op"] == "put":
                    fields = operation["doc"]
                    stored = self.store.put(operation["id"], fields)
                    self.index.add(stored.internal_id, self._analyze(fields))
                elif operation["op"] == "delete":
                    removed = self.store.remove(operation["id"])
                    if removed is not None:
                        self.index.remove(removed.internal_id)
        # Counted so a reopened collection knows how much dead weight the log
        # is already carrying, rather than assuming it starts clean.
        self._log_entries = entries

    def _write_meta(self) -> None:
        if self._path is None:
            return
        meta = {
            "version": FORMAT_VERSION,
            "name": self.name,
            "schema": self.schema.to_dict(),
            "analyzer": self.analyzer.config(),
            "next_internal_id": self.store.next_internal_id,
        }
        _atomic_write(self._path / META_FILE, json.dumps(meta, indent=2))

    def compact(self) -> int:
        """Rewrite the log with only the live version of each document.

        Returns how many entries were dropped. The new log is written to a
        temporary file and atomically renamed, so an interrupted compaction
        leaves the original log untouched rather than half-destroyed.
        """
        with self._lock:
            if self._path is None or self._read_only:
                return 0

            live = [
                {"op": "put", "id": doc.id, "doc": doc.fields} for doc in self.store
            ]
            dropped = max(self._log_entries - len(live), 0)

            payload = "".join(json.dumps(op, ensure_ascii=False) + "\n" for op in live)
            if self._log is not None:
                self._log.close()
            _atomic_write(self._path / LOG_FILE, payload)
            self._write_meta()
            self._log = open(self._path / LOG_FILE, "a", encoding="utf-8")
            self._log_entries = len(live)
            return dropped

    # ---- background syncing --------------------------------------------

    def _start_syncer(self) -> None:
        if self.sync_interval is None or self._path is None:
            return
        self._stop.clear()
        self._syncer = threading.Thread(
            target=self._sync_loop,
            name=f"miniseek-sync[{self.name}]",
            daemon=True,  # never keep the interpreter alive
        )
        self._syncer.start()

    def _sync_loop(self) -> None:
        # wait() doubles as the sleep and the shutdown signal, so close()
        # returns immediately instead of waiting out a full interval.
        while not self._stop.wait(self.sync_interval):
            try:
                self.sync()
            except OSError, ValueError:
                # A background thread that dies on a transient IO error would
                # silently stop persisting. Keep looping; close() still syncs.
                continue

    def close(self) -> None:
        self._stop.set()
        syncer, self._syncer = self._syncer, None
        if syncer is not None:
            syncer.join(timeout=5)
        with self._lock:
            if self._log is not None:
                self.flush()
                self._write_meta()
                self._log.close()
                self._log = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def _atomic_write(path: Path, text: str) -> None:
    """Write via a temp file and rename, so readers never see a partial file.

    os.replace is atomic on POSIX and Windows, so the file at `path` is always
    either the complete old version or the complete new one.
    """
    directory = path.parent
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=directory, delete=False
    ) as tmp:
        tmp.write(text)
        tmp.flush()
        os.fsync(tmp.fileno())
        temp_name = tmp.name
    os.replace(temp_name, path)
