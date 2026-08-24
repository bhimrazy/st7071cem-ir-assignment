"""The handover between crawling and indexing: one directory per crawl,
holding the records as JSON Lines plus a manifest describing the run."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .paths import CRAWLS_DIR

FORMAT_VERSION = 1
RECORDS_FILE = "publications.jsonl"
PEOPLE_FILE = "persons.jsonl"
MANIFEST_FILE = "manifest.json"
# A crawl still being written carries this suffix, so an interrupted run is
# never mistaken for a finished one.
PARTIAL_SUFFIX = ".partial"


@dataclass(frozen=True, slots=True)
class Crawl:
    """One finished crawl on disk."""

    path: Path
    manifest: dict[str, Any]

    @property
    def crawl_id(self) -> str:
        return self.path.name

    @property
    def publication_count(self) -> int:
        return int(self.manifest.get("publications", 0))

    @property
    def person_count(self) -> int:
        return int(self.manifest.get("people", 0))

    def records(self) -> Iterator[dict[str, Any]]:
        """The crawled publications, one per line, in the order found."""
        yield from _read_jsonl(self.path / RECORDS_FILE)

    def people(self) -> Iterator[dict[str, Any]]:
        """The crawled member profiles, one per line."""
        yield from _read_jsonl(self.path / PEOPLE_FILE)


def _read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.is_file():
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def new_crawl_id(now: datetime | None = None) -> str:
    """A sortable, filesystem-safe id, so the newest crawl is the last one."""
    moment = now or datetime.now(UTC)
    return moment.strftime("%Y%m%dT%H%M%SZ")


def write(
    records: Iterable[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    *,
    people: Iterable[Mapping[str, Any]] = (),
    root: Path = CRAWLS_DIR,
    crawl_id: str | None = None,
) -> Crawl:
    """Write one crawl, then publish it by renaming into place."""
    crawl_id = crawl_id or new_crawl_id()
    staging = root / (crawl_id + PARTIAL_SUFFIX)
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    count = _write_jsonl(staging / RECORDS_FILE, records)
    person_count = _write_jsonl(staging / PEOPLE_FILE, people)

    full = {
        "format_version": FORMAT_VERSION,
        "crawl_id": crawl_id,
        "publications": count,
        "people": person_count,
        **dict(manifest),
    }
    (staging / MANIFEST_FILE).write_text(
        json.dumps(full, indent=2) + "\n", encoding="utf-8"
    )

    final = root / crawl_id
    if final.exists():
        shutil.rmtree(final)
    staging.rename(final)
    return Crawl(path=final, manifest=full)


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> int:
    count = 0
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(dict(record), ensure_ascii=False) + "\n")
            count += 1
    return count


def all_crawls(root: Path = CRAWLS_DIR) -> list[Crawl]:
    """Every finished crawl, oldest first. Partial ones are skipped."""
    if not root.is_dir():
        return []
    crawls = []
    for path in sorted(root.iterdir()):
        manifest_path = path / MANIFEST_FILE
        if not manifest_path.is_file():
            continue
        crawls.append(
            Crawl(
                path=path,
                manifest=json.loads(manifest_path.read_text(encoding="utf-8")),
            )
        )
    return crawls


def latest(root: Path = CRAWLS_DIR) -> Crawl | None:
    crawls = all_crawls(root)
    return crawls[-1] if crawls else None


def load(crawl_id: str, root: Path = CRAWLS_DIR) -> Crawl:
    for crawl in all_crawls(root):
        if crawl.crawl_id == crawl_id:
            return crawl
    raise FileNotFoundError(f"no crawl {crawl_id!r} under {root}")
